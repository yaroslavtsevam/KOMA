"""
rpd_wizard.py – Step 2: RPD Verification & General Data (/project/{id}/rpd)
              + Step 4: RPD Final & Step Redo (/project/{id}/rpd_final)
Allows interactive verification of curriculum plan extraction, hours balance,
competency descriptors (З-У-В), generates 100% compliant RPD DOCX,
and bridges verified data directly into OMD.
"""

import os
import json
import logging
from pathlib import Path
from nicegui import app, ui, background_tasks

from ..db import (
    get_project, update_project_status, update_project_files, update_project_meta,
    update_project_department, processing_dir, results_dir
)
from ..auth import current_user, require_login
from ..pipeline import run_rpd_generation, run_rpd_to_omd_bridge, run_rpd_ai_pregeneration
from .shared import page_layout, _step_indicator
from rpd_app.core.curriculum_parser import CurriculumParser
from tools.rpd_ai_generator import generate_baseline_rpd_context
from rpd_app.core.course_presets import (
    get_preset_for_environmental_digital_tech,
    build_generic_context_from_parsed
)
from rpd_app.data.timiryazev_structure import (
    get_institutes, get_departments_by_institute, get_all_departments, find_institute_for_department,
    normalize_institute
)

logger = logging.getLogger("rpd_wizard")

def _assert_owner(project, user):
    return project and project["user_id"] == user["user_id"]


def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert any numeric representation (e.g. '83,65', '-0,41', 12, None) to float."""
    if val is None:
        return default
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return default


def sanitize_for_json(data):
    """Recursively strip non-serializable objects and keys ending with _inp."""
    if isinstance(data, dict):
        return {
            k: sanitize_for_json(v)
            for k, v in data.items()
            if not k.endswith("_inp") and not hasattr(v, "props")
        }
    elif isinstance(data, list):
        return [sanitize_for_json(item) for item in data if not hasattr(item, "props")]
    elif isinstance(data, (str, int, float, bool)) or data is None:
        return data
    return str(data)


# ── Step 2: RPD General Data & Builder ───────────────────────────────────────

@ui.page("/project/{project_id}/rpd")
async def rpd_wizard_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    proj_name = project["name"]
    proc_dir = processing_dir(proj_name)
    context_file = proc_dir / "rpd_context.json"

    # Find curriculum plan PDF
    plan_path = project.get("plan_path")
    if not plan_path or not Path(plan_path).exists():
        inp_dir = Path("input") / proj_name
        if inp_dir.exists():
            plx = list(inp_dir.glob("*.plx.pdf")) or list(inp_dir.glob("*.pdf"))
            if plx:
                plan_path = str(plx[0])
                update_project_files(project_id, plan_path=plan_path)

    # Load or extract RPD context
    context = {}
    if context_file.exists():
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                context = json.load(f)
        except Exception as e:
            logger.warning("Failed to load existing rpd_context.json: %s", e)

    if context and context.get("institute"):
        context["institute"] = normalize_institute(context["institute"]) or context["institute"]

    # Detect if existing context is an old generic stub or has empty/unextracted competencies
    is_old_stub = False
    if context:
        first_comp = (context.get("competencies_nested") or [{}])[0]
        ind_first = first_comp.get("ind_first") or {}
        if ind_first.get("know") == "Теоретические основы дисциплины.":
            is_old_stub = True
        if context.get("competencies_count") == "0" or not context.get("competencies_short_list"):
            is_old_stub = True
        if "Б1.В.09.03" in (context.get("course_code") or "") and first_comp.get("code") == "ОПК-1":
            is_old_stub = True

    # Initialize curriculum plan parser for catalog and extraction
    plan_parser = None
    program_competencies_catalog = {}
    if plan_path and Path(plan_path).exists():
        try:
            plan_parser = CurriculumParser(str(plan_path))
            program_competencies_catalog = plan_parser.list_all_program_competencies()
        except Exception as exc:
            logger.warning("Could not initialize plan parser for catalog: %s", exc)

    if (not context or is_old_stub) and plan_parser:
        try:
            meta = plan_parser.extract_metadata()
            target_course = project.get("course_code") or project.get("course_name") or proj_name
            disc = plan_parser.extract_discipline_details(target_course)
            sem = disc["semesters"][0] if disc.get("semesters") else 1
            coreqs = plan_parser.extract_corequisites(sem, disc.get("code", ""))
            comps = plan_parser.extract_competency_details(disc.get("competency_codes", []))

            context = generate_baseline_rpd_context(meta, disc, comps, coreqs)

            proc_dir.mkdir(parents=True, exist_ok=True)
            with open(context_file, "w", encoding="utf-8") as f:
                json.dump(context, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed to parse plan and generate baseline context in wizard: %s", exc)
            if not context:
                context = get_preset_for_environmental_digital_tech()

    course_display = context.get("course_name") or project.get("course_name") or proj_name

    with page_layout(f"Шаг 2: Данные РПД: {course_display}", user):
        _step_indicator(2, project)

        with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-6"):
            # Header info card with compact status indicator
            token_usage = context.get("token_usage")
            with ui.card().classes("app-card w-full p-6"):
                with ui.row().classes("w-full justify-between items-start"):
                    with ui.column().classes("gap-1"):
                        ui.label(f"{project.get('course_code', '')} {course_display}").classes("text-xl font-bold text-white")
                        ui.label(f"Учебный план: {project.get('plan_filename', 'Загруженный план')} • Магистерская программа").classes("text-xs text-indigo-300")
                    with ui.row().classes("items-center gap-2"):
                        if os.environ.get("GOOGLE_API_KEY"):
                            ui.badge("🟢 Gemini 3.7 Flash подключен", color="emerald-9").classes("px-3 py-1.5 text-xs text-emerald-200")
                        else:
                            ui.badge("⚪ Gemini Offline", color="slate-8").classes("px-3 py-1.5 text-xs text-gray-400")
                        if token_usage:
                            tot_tok = token_usage.get("total_tokens", 0)
                            ui.badge(f"Токенов: {tot_tok:,}", color="indigo-8").classes("px-2.5 py-1 text-xs text-indigo-200")
                        ui.badge("Черновик параметров РПД", color="indigo-9").classes("px-3 py-1.5 text-xs")

            async def do_launch_ai_generation():
                save_ui_to_context()
                target_c = context.get("course_code") or project.get("course_code") or context.get("course_name") or proj_name
                app.storage.user[f"return_to_{project_id}"] = f"/project/{project_id}/rpd_final"
                background_tasks.create(
                    run_rpd_ai_pregeneration(
                        project_id=project_id,
                        username=user["username"],
                        project_name=proj_name,
                        plan_path=str(plan_path),
                        course_name=target_c,
                        regenerate=True
                    )
                )
                ui.notify("Запущена AI-генерация содержания РПД...", type="info")
                ui.navigate.to(f"/project/{project_id}/processing")

        # ── Multi-Tab Wizard Form ─────────────────────────────────────────────
        dev_widget_list = []
        with ui.card().classes("app-card w-full").style("padding: 24px 32px;"):
            with ui.tabs().classes("w-full mb-6") as tabs:
                t1 = ui.tab("1. Титул, метаданные и авторы", icon="badge")
                t2 = ui.tab("2. Часы и трудоемкость", icon="schedule")
                t3 = ui.tab("3. Компетенции (Табл. 1)", icon="assignment_turned_in")
                t4 = ui.tab("4. Тематический план", icon="menu_book")
                t5 = ui.tab("5. Литература и ресурсы", icon="library_books")

            with ui.tab_panels(tabs, value=t1).classes("w-full bg-transparent"):
                # ── Tab 1: Метаданные и авторы ──────────────────────────────
                with ui.tab_panel(t1):
                    ui.label("Основные реквизиты образовательной программы:").classes("text-sm font-semibold text-indigo-300 mb-2")
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        in_dir_code = ui.input("Код направления", value=context.get("direction_code", "")).props("outlined dark color=indigo")
                        in_dir_name = ui.input("Наименование направления", value=context.get("direction_name", "")).props("outlined dark color=indigo")
                        in_profile = ui.input("Направленность (профиль)", value=context.get("profile", "")).props("outlined dark color=indigo")
                        qual_options = ["магистр", "бакалавр", "специалист"]
                        raw_qual = str(context.get("qualification") or "магистр").strip().lower()
                        if "магистр" in raw_qual:
                            cur_qual = "магистр"
                        elif "бакалавр" in raw_qual:
                            cur_qual = "бакалавр"
                        elif "специалист" in raw_qual:
                            cur_qual = "специалист"
                        else:
                            cur_qual = raw_qual
                        if cur_qual not in qual_options:
                            qual_options.append(cur_qual)
                        in_qual = ui.select(options=qual_options, label="Квалификация", value=cur_qual).props("outlined dark color=indigo")

                        all_insts = get_institutes()
                        all_depts = get_all_departments()
                        raw_inst = context.get("institute") or project.get("institute")
                        norm_inst = normalize_institute(raw_inst) if raw_inst else None
                        cur_inst = norm_inst or (all_insts[1] if len(all_insts) > 1 else all_insts[0])
                        if cur_inst not in all_insts:
                            all_insts.insert(0, cur_inst)

                        cur_dept = context.get("department") or project.get("department") or "Кафедра экологии"
                        if cur_dept not in all_depts:
                            all_depts.insert(0, cur_dept)

                        in_inst = ui.select(options=all_insts, label="Институт (РГАУ-МСХА)", value=cur_inst).props("outlined dark color=indigo")
                        in_dept = ui.select(options=all_depts, label="Кафедра создания РПД и ОМД", value=cur_dept, with_input=True).props("outlined dark color=indigo")

                        def on_wizard_inst_change(e):
                            if e.value:
                                depts = get_departments_by_institute(e.value)
                                if depts:
                                    if in_dept.value not in depts:
                                        in_dept.value = depts[0]
                                    in_dept.options = depts
                        in_inst.on_value_change(on_wizard_inst_change)

                        in_head_fio = ui.input("Заведующий кафедрой (ФИО)", value=context.get("department_head_fio", "")).props("outlined dark color=indigo")
                        in_head_status = ui.input("Статус зав. кафедрой (должность)", value=context.get("department_head_status", "Заведующий кафедрой")).props("outlined dark color=indigo")
                        in_year = ui.input("Год набора", value=str(context.get("start_year", "2026"))).props("outlined dark color=indigo")
                        in_curr_year = ui.input("Учебный год", value=str(context.get("current_year", "2026"))).props("outlined dark color=indigo")

                    ui.separator().classes("my-5").style("border-color: rgba(99,102,241,0.2);")
                    ui.label("Разработчик(и) рабочей программы:").classes("text-sm font-semibold text-indigo-300 mb-2")
                    devs = context.get("developers_list") or [
                        {"label": "Разработчик", "position": "доцент кафедры", "fio_rank": context.get("developer_fio_rank", "Тихонова М.В., к.б.н., доцент")}
                    ]
                    for dev in devs:
                        with ui.row().classes("w-full gap-4 mb-2"):
                            p_inp = ui.input("Должность разработчика", value=dev.get("position", "")).props("outlined dark color=indigo").classes("flex-1")
                            f_inp = ui.input("ФИО, ученая степень, ученое звание", value=dev.get("fio_rank", "")).props("outlined dark color=indigo").classes("flex-1")
                            dev_widget_list.append((dev, p_inp, f_inp))

                # ── Tab 2: Часы и баланс (Strict Non-Negative SRS) ───────────
                with ui.tab_panel(t2):
                    raw_srs = max(0.0, _safe_float(context.get("srs_hours", 83.65)))
                    with ui.grid(columns=3).classes("w-full gap-4"):
                        in_code = ui.input("Код дисциплины", value=context.get("course_code", "")).props("outlined dark color=indigo")
                        in_name = ui.input("Наименование дисциплины", value=context.get("course_name", "")).props("outlined dark color=indigo").classes("col-span-2")
                        in_sem = ui.number("Семестр", value=int(_safe_float(context.get("semester", 4), 4)), min=1, max=12).props("outlined dark color=indigo")
                        in_course_yr = ui.input("Курс обучения", value=str(context.get("course_year", 2))).props("outlined dark color=indigo readonly")

                        ctrl_options = ["зачет с оценкой", "экзамен", "зачет"]
                        raw_ctrl = str(context.get("control_form") or "зачет с оценкой").strip().lower()
                        if "дифф" in raw_ctrl or "оценк" in raw_ctrl:
                            cur_ctrl = "зачет с оценкой"
                        elif "экзамен" in raw_ctrl:
                            cur_ctrl = "экзамен"
                        elif "зачет" in raw_ctrl:
                            cur_ctrl = "зачет"
                        else:
                            cur_ctrl = raw_ctrl
                        if cur_ctrl not in ctrl_options:
                            ctrl_options.insert(0, cur_ctrl)
                        in_control = ui.select(options=ctrl_options, label="Форма контроля", value=cur_ctrl).props("outlined dark color=indigo")
                        in_use_brs = ui.checkbox("Балльно-рейтинговая система (БРС)", value=context.get("use_brs", True)).props("dark color=indigo").classes("mt-2")

                        in_zet = ui.number("ЗЕТ", value=_safe_float(context.get("total_zet", 3))).props("outlined dark color=indigo")
                        in_total = ui.number("Всего часов", value=_safe_float(context.get("total_hours", 108))).props("outlined dark color=indigo")
                        in_lec = ui.number("Лекции (час)", value=_safe_float(context.get("lecture_hours", 12))).props("outlined dark color=indigo")
                        in_prac = ui.number("Практические (час)", value=_safe_float(context.get("practical_hours", 12))).props("outlined dark color=indigo")
                        in_lab = ui.number("Лабораторные (час)", value=_safe_float(context.get("lab_hours", 0))).props("outlined dark color=indigo")
                        in_srs = ui.number("СРС (час)", value=raw_srs, min=0).props("outlined dark color=indigo")
                        in_kra = ui.number("Контроль / КРА (час)", value=_safe_float(context.get("kra_hours", 0.35))).props("outlined dark color=indigo")

                    with ui.row().classes("w-full items-center justify-between mt-4"):
                        balance_badge = ui.badge("Баланс часов: расчет...", color="positive").classes("text-sm py-1 px-3")

                        def auto_balance_srs():
                            target = in_total.value or ((in_zet.value or 0) * 36)
                            contact_and_kra = (in_lec.value or 0) + (in_prac.value or 0) + (in_lab.value or 0) + (in_kra.value or 0)
                            calc_srs = max(0.0, round(target - contact_and_kra, 2))
                            in_srs.value = calc_srs
                            recalc_balance()
                            ui.notify(f"СРС сбалансировано: {calc_srs} ч.", type="info")

                        ui.button("⚖ Сбалансировать СРС автоматически", icon="balance", on_click=auto_balance_srs).props("outline color=indigo dense size=sm")

                    def recalc_balance():
                        srs_clamped = max(0.0, in_srs.value or 0.0)
                        if in_srs.value != srs_clamped:
                            in_srs.value = srs_clamped
                        tot = (in_lec.value or 0) + (in_prac.value or 0) + (in_lab.value or 0) + srs_clamped + (in_kra.value or 0)
                        target = in_total.value or ((in_zet.value or 0) * 36)
                        diff = round(tot - target, 2)
                        if abs(diff) < 0.05:
                            balance_badge.set_text(f"✓ Баланс часов сошелся: {round(tot, 2)} ч. из {target} ч.")
                            balance_badge.props("color=positive")
                        else:
                            balance_badge.set_text(f"Внимание: расхождение баланса: {round(tot, 2)} ч. из {target} ч. ({diff:+} ч.)")
                            balance_badge.props("color=negative")

                    for fld in [in_lec, in_prac, in_lab, in_srs, in_kra, in_total, in_zet]:
                        fld.on_value_change(lambda e: recalc_balance())
                    recalc_balance()

                    def update_sem(e):
                        if e.value:
                            in_course_yr.value = str((int(e.value) + 1) // 2)
                    in_sem.on_value_change(update_sem)

                # ── Tab 3: Компетенции (З-У-В) ──────────────────────────────
                comp_widget_list = []

                def sync_inputs_to_model():
                    for target_dict, k_inp, a_inp, m_inp in comp_widget_list:
                        try:
                            if hasattr(k_inp, "value") and k_inp.value is not None:
                                target_dict["know"] = k_inp.value
                            if hasattr(a_inp, "value") and a_inp.value is not None:
                                target_dict["able"] = a_inp.value
                            if hasattr(m_inp, "value") and m_inp.value is not None:
                                target_dict["master"] = m_inp.value
                        except Exception:
                            pass

                with ui.tab_panel(t3):
                    with ui.card().classes("w-full bg-slate-900/40 border border-indigo-500/20 p-4 mb-4 rounded-xl"):
                        with ui.row().classes("w-full justify-between items-center mb-1"):
                            ui.label("Верификация компетенций дисциплины (Таблица 1)").classes("text-base font-bold text-white")
                            ui.badge("Матрица компетенций плана", color="indigo-7").classes("text-xs px-2.5 py-0.5")
                        ui.label(
                            "Проверьте компетенции и индикаторы, закрепленные за данной дисциплиной в официальном учебном плане. "
                            "Вы можете удалить лишние компетенции или добавить любые компетенции из полного каталога учебного плана."
                        ).classes("text-xs text-gray-400 mb-3")

                        chips_row = ui.row().classes("w-full gap-2 flex-wrap items-center")

                    # Панель добавления компетенций из каталога учебного плана
                    with ui.card().classes("w-full bg-gradient-to-r from-indigo-950/40 to-slate-900/60 border border-indigo-500/30 p-4 mb-4 rounded-xl"):
                        ui.label("Добавить компетенцию из каталога учебного плана:").classes("text-xs font-bold text-indigo-300 mb-2")
                        with ui.row().classes("w-full gap-3 items-center"):
                            comp_options = {}
                            for c_code, c_info in program_competencies_catalog.items():
                                ind_str = f"({', '.join(c_info['indicators'])})" if c_info.get("indicators") else ""
                                title_preview = c_info.get('title', '')[:70] + "..." if len(c_info.get('title', '')) > 70 else c_info.get('title', '')
                                comp_options[c_code] = f"{c_code}: {title_preview} {ind_str}"

                            if not comp_options:
                                comp_options = {
                                    "ПКдпо-2": "ПКдпо-2: Эколого-экономическое обоснование новой техники и технологий",
                                    "ПКдпо-3": "ПКдпо-3: Локализация аварийных выбросов и сбросов",
                                    "ПКдпо-1": "ПКдпо-1: Наилучшие доступные технологии и производственный экоконтроль",
                                    "ПКос-1": "ПКос-1: Охрана и рациональное использование ресурсов",
                                    "ПКос-2": "ПКос-2: Геоинформационные и цифровые технологии",
                                    "УК-1": "УК-1: Системное и критическое мышление",
                                    "УК-2": "УК-2: Разработка и реализация проектов",
                                    "УК-3": "УК-3: Командная работа и лидерство",
                                    "ОПК-1": "ОПК-1: Фундаментальные знания предметной области"
                                }

                            first_avail = next(iter(comp_options.keys())) if comp_options else None
                            sel_comp = ui.select(
                                options=comp_options,
                                label="Выберите компетенцию программы",
                                value=first_avail
                            ).props("outlined dark dense color=indigo").classes("flex-1 text-xs")

                            async def add_selected_competency():
                                sync_inputs_to_model()
                                chosen_code = sel_comp.value
                                if not chosen_code:
                                    ui.notify("Выберите компетенцию из списка", type="warning")
                                    return

                                comps_nested = context.setdefault("competencies_nested", [])
                                existing_codes = [c.get("code") for c in comps_nested]
                                if chosen_code in existing_codes:
                                    ui.notify(f"Компетенция {chosen_code} уже есть в рабочей программе", type="info")
                                    return

                                # Извлекаем дефиницию и индикаторы
                                if plan_parser:
                                    extracted = plan_parser.extract_competency_details([chosen_code])
                                else:
                                    dummy_parser = CurriculumParser(str(plan_path)) if plan_path and Path(plan_path).exists() else None
                                    extracted = dummy_parser.extract_competency_details([chosen_code]) if dummy_parser else []

                                if extracted:
                                    new_c = extracted[0]
                                    inds = new_c.get("indicators", [])
                                    ind_first = {
                                        "code": inds[0]["code"] if inds else f"{chosen_code}.1",
                                        "title": inds[0].get("title", f"Индикатор {chosen_code}.1"),
                                        "know": inds[0].get("know", ""),
                                        "able": inds[0].get("can", inds[0].get("able", "")),
                                        "master": inds[0].get("master", "")
                                    }
                                    other_inds = []
                                    for oi in inds[1:]:
                                        other_inds.append({
                                            "code": oi["code"],
                                            "title": oi.get("title", f"Индикатор {oi['code']}"),
                                            "know": oi.get("know", ""),
                                            "able": oi.get("can", oi.get("able", "")),
                                            "master": oi.get("master", "")
                                        })
                                else:
                                    ind_first = {
                                        "code": f"{chosen_code}.1",
                                        "title": f"Индикатор достижения компетенции {chosen_code}.1",
                                        "know": f"Знает теоретические основы и стандарты в рамках {chosen_code}.",
                                        "able": f"Умеет применять методы и инструменты {chosen_code} на практике.",
                                        "master": f"Владеет навыками реализации профессиональных решений {chosen_code}."
                                    }
                                    other_inds = []

                                new_item = {
                                    "num": str(len(comps_nested) + 1),
                                    "code": chosen_code,
                                    "title": new_c.get("title", f"Компетенция {chosen_code}") if extracted else f"Компетенция {chosen_code}",
                                    "ind_first": ind_first,
                                    "other_indicators": other_inds
                                }
                                comps_nested.append(new_item)
                                ui.notify(f"✓ Компетенция {chosen_code} успешно добавлена в программу!", type="positive")
                                render_all_competencies()

                            ui.button("+ Добавить в программу", icon="add_circle", on_click=add_selected_competency).classes("primary-btn text-xs").props("dense")

                    comps_container = ui.column().classes("w-full gap-3")

                    def render_all_competencies():
                        comp_widget_list.clear()
                        chips_row.clear()
                        comps_container.clear()

                        comps_list = context.get("competencies_nested", [])

                        # Рендеринг бейджей верификации
                        with chips_row:
                            ui.label("Закрепленные компетенции:").classes("text-xs font-semibold text-gray-300 mr-2")
                            if not comps_list:
                                ui.label("Компетенции не добавлены. Выберите из каталога выше.").classes("text-xs text-amber-400 italic")
                            for idx, c in enumerate(comps_list):
                                ind_cnt = (1 if c.get("ind_first") else 0) + len(c.get("other_indicators", []))
                                with ui.badge(f"{c.get('code')} ({ind_cnt} инд.)", color="indigo-8").classes("px-2.5 py-1 text-xs items-center gap-1.5"):
                                    def _make_rm_chip(i):
                                        return lambda: remove_competency(i)
                                    ui.icon("close", size="xs").classes("cursor-pointer hover:text-red-300").on("click", _make_rm_chip(idx))

                        # Рендеринг карточек компетенций с декомпозицией З-У-В
                        with comps_container:
                            for idx, comp in enumerate(comps_list):
                                comp["num"] = str(idx + 1)
                                with ui.expansion(f"{comp.get('code')}: {comp.get('title')}", icon="verified").classes("w-full bg-slate-900/50 border border-slate-700/50 rounded-lg").props("default-opened" if idx == 0 else ""):
                                    with ui.row().classes("w-full justify-between items-center px-4 py-2 border-b border-slate-800"):
                                        ui.label(f"Компетенция {comp.get('code')} (Позиция №{comp['num']})").classes("text-xs font-bold text-indigo-300")
                                        def _make_rm_comp(i):
                                            return lambda: remove_competency(i)
                                        ui.button("Удалить компетенцию", icon="delete", on_click=_make_rm_comp(idx)).props("flat color=red dense size=xs")

                                    # ind_first
                                    if comp.get("ind_first"):
                                        ind = comp["ind_first"]
                                        with ui.card().classes("w-full bg-slate-950/60 p-4 my-2 border border-slate-800/80 rounded-lg"):
                                            with ui.row().classes("w-full justify-between items-center mb-2"):
                                                ui.label(f"Индикатор {ind.get('code')}: {ind.get('title', '')}").classes("font-semibold text-xs text-indigo-300")
                                            k_inp = ui.input("Знать", value=ind.get("know", "")).props("outlined dark color=indigo").classes("w-full mb-2 text-xs")
                                            a_inp = ui.input("Уметь", value=ind.get("able", "")).props("outlined dark color=indigo").classes("w-full mb-2 text-xs")
                                            m_inp = ui.input("Владеть", value=ind.get("master", "")).props("outlined dark color=indigo").classes("w-full text-xs")
                                            comp_widget_list.append((ind, k_inp, a_inp, m_inp))

                                    # other_indicators
                                    for o_idx, oind in enumerate(comp.get("other_indicators", [])):
                                        with ui.card().classes("w-full bg-slate-950/60 p-4 my-2 border border-slate-800/80 rounded-lg"):
                                            with ui.row().classes("w-full justify-between items-center mb-2"):
                                                ui.label(f"Индикатор {oind.get('code')}: {oind.get('title', '')}").classes("font-semibold text-xs text-indigo-300")
                                                def _make_rm_ind(c_ref, ind_i):
                                                    return lambda: remove_indicator(c_ref, ind_i)
                                                ui.button("Удалить индикатор", icon="close", on_click=_make_rm_ind(comp, o_idx)).props("flat color=red dense size=xs")
                                            k_inp = ui.input("Знать", value=oind.get("know", "")).props("outlined dark color=indigo").classes("w-full mb-2 text-xs")
                                            a_inp = ui.input("Уметь", value=oind.get("able", "")).props("outlined dark color=indigo").classes("w-full mb-2 text-xs")
                                            m_inp = ui.input("Владеть", value=oind.get("master", "")).props("outlined dark color=indigo").classes("w-full text-xs")
                                            comp_widget_list.append((oind, k_inp, a_inp, m_inp))

                                    # Добавить индикатор к данной компетенции
                                    with ui.row().classes("w-full justify-end px-2 py-1"):
                                        def _make_add_ind(c_ref):
                                            return lambda: add_indicator_to_comp(c_ref)
                                        ui.button("+ Добавить индикатор", icon="add", on_click=_make_add_ind(comp)).props("outline color=indigo dense size=xs")

                    def remove_competency(i):
                        sync_inputs_to_model()
                        comps_list = context.get("competencies_nested", [])
                        if 0 <= i < len(comps_list):
                            rm = comps_list.pop(i)
                            ui.notify(f"Компетенция {rm.get('code')} удалена", type="info")
                            render_all_competencies()

                    def remove_indicator(comp, o_idx):
                        sync_inputs_to_model()
                        other = comp.get("other_indicators", [])
                        if 0 <= o_idx < len(other):
                            rm = other.pop(o_idx)
                            ui.notify(f"Индикатор {rm.get('code')} удален", type="info")
                            render_all_competencies()

                    def add_indicator_to_comp(comp):
                        sync_inputs_to_model()
                        c_code = comp.get("code", "ПК-1")
                        curr_cnt = 1 + len(comp.get("other_indicators", []))
                        next_num = curr_cnt + 1
                        new_ind = {
                            "code": f"{c_code}.{next_num}",
                            "title": f"Индикатор достижения компетенции {c_code}.{next_num}",
                            "know": f"Знает нормативно-технические регламенты и основы {c_code}.{next_num}.",
                            "able": f"Умеет выполнять расчеты и формировать решения по {c_code}.{next_num}.",
                            "master": f"Владеет программным обеспечением и методиками в рамках {c_code}.{next_num}."
                        }
                        comp.setdefault("other_indicators", []).append(new_ind)
                        ui.notify(f"Индикатор {new_ind['code']} добавлен к {c_code}", type="positive")
                        render_all_competencies()

                    render_all_competencies()

                # ── Tab 4: Тематический план ────────────────────────────────
                with ui.tab_panel(t4):
                    sec_list = context.get("sections", [])
                    ui.label(f"Разделы и тематическая структура дисциплины (всего {len(sec_list)} разделов, адаптировано к часам):").classes("text-sm text-gray-400 mb-4")
                    t4_map = {str(sec.get("num", i + 1)): sec for i, sec in enumerate(context.get("t4_sections", []))}
                    for idx, s in enumerate(sec_list):
                        sec_num_str = str(idx + 1)
                        sec_t4 = t4_map.get(sec_num_str, {})
                        with ui.expansion(f"{s.get('name', f'Раздел {sec_num_str}')}", icon="folder").classes("w-full mb-3 bg-slate-900/50 border border-slate-700/50 rounded-lg"):
                            with ui.row().classes("w-full p-2 items-center gap-3"):
                                ui.badge(f"Лекции: {s.get('lec', 0)} ч.", color="indigo-8")
                                ui.badge(f"Практика: {s.get('prac', 0)} ч.", color="teal-8")
                                ui.badge(f"СРС: {max(0.0, _safe_float(s.get('srs', 0)))} ч.", color="amber-9")
                                ui.badge(f"Всего: {s.get('total', 0)} ч.", color="purple-8")
                            if sec_t4.get("lessons"):
                                ui.separator().classes("my-2")
                                for les in sec_t4.get("lessons", []):
                                    with ui.row().classes("w-full justify-between items-center text-xs text-gray-300 py-1 px-2 hover:bg-slate-800/40 rounded"):
                                        ui.label(f"{les.get('title', '')} ({les.get('theme', '')})").classes("font-medium flex-1")
                                        ui.label(f"Контроль: {les.get('control', 'Устный опрос')}").classes("text-gray-400 mr-2")
                                        ui.badge(f"{les.get('hours', 2)} ч.", color="blue-9")

                # ── Tab 5: Литература и ресурсы ─────────────────────────────
                with ui.tab_panel(t5):
                    ui.label("Основная учебная литература (ЭБС «Лань», «Юрайт»):").classes("text-sm font-semibold text-indigo-300 mb-2")
                    main_lit_list = list(context.get("main_literature_list", []))
                    main_lit_col = ui.column().classes("w-full gap-1 mb-2")

                    def render_main_lit():
                        main_lit_col.clear()
                        with main_lit_col:
                            for idx, lit in enumerate(main_lit_list):
                                with ui.row().classes("w-full items-center justify-between gap-2 p-1.5 rounded bg-slate-900/40 hover:bg-slate-800/60 border border-slate-800"):
                                    ui.label(f"{idx+1}. {lit}").classes("text-xs text-gray-200 flex-1")
                                    def _make_rm_main(i):
                                        return lambda: (main_lit_list.pop(i), context.update({"main_literature_list": main_lit_list, "main_lit_count": str(len(main_lit_list))}), render_main_lit())
                                    ui.button(icon="delete", on_click=_make_rm_main(idx)).props("flat color=red round dense size=sm").tooltip("Удалить пункт")

                    render_main_lit()
                    with ui.row().classes("w-full gap-2 mb-4"):
                        in_add_main = ui.input(placeholder="Библиографическое описание источника...").props("outlined dark dense").classes("flex-1 text-xs")
                        def _add_main_item():
                            val = (in_add_main.value or "").strip()
                            if val:
                                main_lit_list.append(val)
                                context["main_literature_list"] = main_lit_list
                                context["main_lit_count"] = str(len(main_lit_list))
                                in_add_main.value = ""
                                render_main_lit()
                        ui.button("+ Добавить", on_click=_add_main_item).props("outline color=indigo dense size=sm")

                    ui.separator().classes("my-4").style("border-color: rgba(99,102,241,0.2);")
                    ui.label("Дополнительная литература:").classes("text-sm font-semibold text-indigo-300 mb-2")
                    add_lit_list = list(context.get("additional_literature_list", []))
                    add_lit_col = ui.column().classes("w-full gap-1 mb-2")

                    def render_add_lit():
                        add_lit_col.clear()
                        with add_lit_col:
                            for idx, lit in enumerate(add_lit_list):
                                with ui.row().classes("w-full items-center justify-between gap-2 p-1.5 rounded bg-slate-900/40 hover:bg-slate-800/60 border border-slate-800"):
                                    ui.label(f"{idx+1}. {lit}").classes("text-xs text-gray-200 flex-1")
                                    def _make_rm_add(i):
                                        return lambda: (add_lit_list.pop(i), context.update({"additional_literature_list": add_lit_list, "add_lit_count": str(len(add_lit_list))}), render_add_lit())
                                    ui.button(icon="delete", on_click=_make_rm_add(idx)).props("flat color=red round dense size=sm").tooltip("Удалить пункт")

                    render_add_lit()
                    with ui.row().classes("w-full gap-2 mb-4"):
                        in_add_add = ui.input(placeholder="Библиографическое описание источника...").props("outlined dark dense").classes("flex-1 text-xs")
                        def _add_add_item():
                            val = (in_add_add.value or "").strip()
                            if val:
                                add_lit_list.append(val)
                                context["additional_literature_list"] = add_lit_list
                                context["add_lit_count"] = str(len(add_lit_list))
                                in_add_add.value = ""
                                render_add_lit()
                        ui.button("+ Добавить", on_click=_add_add_item).props("outline color=indigo dense size=sm")

            # ── Action Bar ────────────────────────────────────────────────────
            ui.separator().classes("my-6").style("border-color: rgba(99,102,241,0.2);")

            def save_ui_to_context():
                context["direction_code"] = in_dir_code.value
                context["direction_name"] = in_dir_name.value
                context["profile"] = in_profile.value
                context["qualification"] = in_qual.value
                context["qualification_plural"] = "магистров" if in_qual.value == "магистр" else "бакалавров"
                context["institute"] = in_inst.value
                context["department"] = in_dept.value
                context["department_head_fio"] = in_head_fio.value
                context["department_head_status"] = in_head_status.value
                context["start_year"] = in_year.value
                context["current_year"] = in_curr_year.value

                context["course_code"] = in_code.value
                context["course_name"] = in_name.value
                context["semester"] = str(in_sem.value)
                context["course_year"] = in_course_yr.value
                context["control_form"] = in_control.value
                context["control_form_genitive"] = "зачета с оценкой" if "оценк" in in_control.value else ("экзамена" if "экзамен" in in_control.value else "зачета")
                context["control_phrase"] = f"{in_control.value} в {in_sem.value} семестре"
                context["semester_phrase"] = f"{in_sem.value} семестре"

                srs_val = max(0.0, _safe_float(in_srs.value))
                context["total_zet"] = str(in_zet.value)
                context["total_hours"] = str(in_total.value).rstrip("0").rstrip(".")
                context["lecture_hours"] = str(in_lec.value).rstrip("0").rstrip(".")
                context["practical_hours"] = str(in_prac.value).rstrip("0").rstrip(".")
                context["lab_hours"] = str(in_lab.value).rstrip("0").rstrip(".") if in_lab.value else ""
                context["contact_auditory_hours"] = str(int((in_lec.value or 0) + (in_prac.value or 0)))
                context["contact_hours"] = str(round((in_lec.value or 0) + (in_prac.value or 0) + (in_kra.value or 0), 2)).replace(".", ",")
                context["srs_hours"] = str(round(srs_val, 2)).replace(".", ",")
                context["srs_self_hours"] = str(round(srs_val, 2)).replace(".", ",")
                context["kra_hours"] = str(in_kra.value).replace(".", ",")

                context["sem_1_hdr"] = f"№{in_sem.value}"
                context["sem_1_total_hours"] = context["total_hours"]
                context["sem_1_contact_hours"] = context["contact_hours"]
                context["sem_1_contact_auditory_hours"] = context["contact_auditory_hours"]
                context["sem_1_lecture_hours"] = context["lecture_hours"]
                context["sem_1_practical_hours"] = context["practical_hours"]
                context["sem_1_lab_hours"] = context["lab_hours"]
                context["sem_1_kra_hours"] = context["kra_hours"]
                context["sem_1_srs_hours"] = context["srs_hours"]
                context["sem_1_srs_self_hours"] = context["srs_self_hours"]

                # Ensure section srs is non-negative
                for s in context.get("sections", []):
                    s["srs"] = max(0.0, _safe_float(s.get("srs", 0)))

                # Save З-У-В inputs and update competency metadata
                sync_inputs_to_model()
                comps_nested = context.get("competencies_nested", [])
                context["competencies_count"] = str(len(comps_nested))
                context["competencies_short_list"] = ", ".join(c.get("code", "") for c in comps_nested)
                context["competencies_list"] = ", ".join(c.get("code", "") for c in comps_nested)
                all_codes = []
                for c in comps_nested:
                    if c.get("ind_first") and c["ind_first"].get("code"):
                        all_codes.append(c["ind_first"]["code"])
                    for oi in c.get("other_indicators", []):
                        if oi.get("code"):
                            all_codes.append(oi["code"])
                context["competency_codes"] = all_codes
                context["user_verified_competencies"] = True

                # Save developer inputs
                for target_dict, p_inp, f_inp in dev_widget_list:
                    target_dict["position"] = p_inp.value
                    target_dict["fio_rank"] = f_inp.value
                if dev_widget_list:
                    context["developer_fio_rank"] = dev_widget_list[0][2].value

                context["use_brs"] = bool(in_use_brs.value)
                context["brs_assessment_text"] = "Для аттестации обучающихся используется балльно-рейтинговая система (БРС) оценивания." if in_use_brs.value else "Для аттестации обучающихся используется традиционная система оценивания."
                dept_clean = in_dept.value.strip() if in_dept.value else ""
                inst_clean = in_inst.value.strip() if in_inst.value else ""
                update_project_department(project_id, dept_clean, inst_clean)

                clean_context = sanitize_for_json(context)
                context.clear()
                context.update(clean_context)

                proc_dir.mkdir(parents=True, exist_ok=True)
                with open(context_file, "w", encoding="utf-8") as f:
                    json.dump(clean_context, f, indent=2, ensure_ascii=False)

                return clean_context

            async def do_save_and_to_rpd_final():
                save_ui_to_context()
                try:
                    await run_rpd_generation(
                        project_id=project_id,
                        username=user["username"],
                        project_name=proj_name,
                        plan_path=plan_path,
                        course_name=context.get("course_code") or context.get("course_name", proj_name),
                        custom_context=context
                    )
                except Exception as exc:
                    logger.warning("Auto compile RPD failed: %s", exc)
                ui.navigate.to(f"/project/{project_id}/rpd_final")

            with ui.row().classes("w-full justify-between items-center gap-4 flex-wrap"):
                ui.button(
                    "← Назад к параметрам курса (Шаг 1)",
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to(f"/project/{project_id}/parameters")
                ).props("flat").classes("text-gray-400")

                with ui.row().classes("gap-3 items-center"):
                    def do_manual_save():
                        save_ui_to_context()
                        ui.notify("Изменения успешно сохранены", type="positive")

                    ui.button(
                        "💾 Сохранить изменения",
                        icon="save",
                        on_click=do_manual_save
                    ).props("outline color=indigo dark").tooltip("Сохранить отредактированные предварительные данные РПД")

                    if os.environ.get("GOOGLE_API_KEY"):
                        ui.button(
                            "⚡ Сгенерировать содержание РПД (ИИ)",
                            icon="bolt",
                            on_click=do_launch_ai_generation
                        ).classes("primary-btn").tooltip("Синтезировать З-У-В, разделы и оценочные средства через Gemini 3.7 Flash")

                    ui.button(
                        "Сохранить и перейти к финалу РПД (Шаг 4) →",
                        icon="arrow_forward",
                        on_click=do_save_and_to_rpd_final
                    ).props("color=emerald dark size=md")


# ── Step 4: RPD Final & Step Redo ────────────────────────────────────────────

@ui.page("/project/{project_id}/rpd_final")
async def rpd_final_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    proj_name = project["name"]
    proc_dir = processing_dir(proj_name)
    res_dir = results_dir(proj_name)
    context_file = proc_dir / "rpd_context.json"

    context = {}
    if context_file.exists():
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                context = json.load(f)
        except Exception:
            pass

    # Find latest RPD docx
    rpd_path = project.get("rpd_path")
    docx_files = [f for f in res_dir.glob("*.docx") if not f.name.startswith("~$")]
    if docx_files:
        latest_docx = max(docx_files, key=lambda f: f.stat().st_mtime)
        rpd_path = str(latest_docx)
        update_project_files(project_id, rpd_path=rpd_path)
        update_project_meta(project_id, rpd_path=rpd_path)

    plan_path = project.get("plan_path")
    course_display = context.get("course_name") or project.get("course_name") or proj_name

    with page_layout(f"Шаг 4: РПД финал: {course_display}", user):
        _step_indicator(4, project)

        with ui.card().classes("app-card w-full mb-6").style("padding: 24px 32px;"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.column().classes("gap-1"):
                    ui.label("Шаг 4: РПД финал — Проверка и экспорт рабочей программы").classes("text-xl font-bold text-white")
                    ui.label(
                        f"Дисциплина: {course_display} ({context.get('course_code', '')}) • "
                        f"Трудоемкость: {context.get('total_zet', '')} ЗЕТ ({context.get('total_hours', '')} ч.) • "
                        f"Контроль: {context.get('control_form', '')}"
                    ).classes("text-sm text-gray-400")
                ui.badge("14 правил верстки", color="positive").classes("text-xs px-3 py-1")

        # ── Status and Token Usage Cards ──────────────────────────────────────
        with ui.grid(columns=2).classes("w-full gap-6 mb-6"):
            with ui.card().classes("bg-slate-900/60 border border-emerald-500/40 p-5 rounded-xl flex flex-col justify-between"):
                with ui.column().classes("gap-2"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("verified", color="positive", size="1.8rem")
                        ui.label("Рабочая программа сформирована").classes("text-lg font-bold text-white")
                    ui.label(
                        "Все 14 академических правил оформления РГАУ-МСХА соблюдены: "
                        "альбомная Таблица 1 с декомпозицией З-У-В, сквозной баланс часов лекций, практик и СРС, "
                        "учебно-тематический план занятий (Таблица 5), формы СРС (Таблица 6), интерактивные формы (Таблица 7), "
                        "фонд оценочных средств и профильное ПО (Таблица 10)."
                    ).classes("text-xs text-gray-300 leading-relaxed")

                rpd_status_lbl = ui.label("").classes("text-xs text-indigo-300 mt-2")

                async def generate_and_download_rpd():
                    nonlocal rpd_path
                    rpd_status_lbl.set_text("Компиляция .docx документа...")
                    try:
                        await run_rpd_generation(
                            project_id=project_id,
                            username=user["username"],
                            project_name=proj_name,
                            plan_path=plan_path,
                            course_name=context.get("course_code") or course_display,
                            custom_context=context
                        )
                        proj_upd = get_project(project_id)
                        rpd_path = proj_upd.get("rpd_path")
                        if rpd_path and Path(rpd_path).exists():
                            rpd_status_lbl.set_text(f"✓ Готово: {Path(rpd_path).name}")
                            ui.download(rpd_path, filename=Path(rpd_path).name)
                            ui.notify("РПД успешно скомпилирована!", type="positive")
                    except Exception as e:
                        rpd_status_lbl.set_text(f"Ошибка: {e}")
                        ui.notify(f"Ошибка компиляции: {e}", type="negative")

                if rpd_path and Path(rpd_path).exists():
                    fn = Path(rpd_path).name
                    ui.button(f"Скачать РПД (.docx)", icon="download", on_click=lambda: ui.download(rpd_path, filename=fn)).classes("success-btn w-full mt-4")
                    ui.button("🔄 Пересобрать документ из контекста", icon="refresh", on_click=generate_and_download_rpd).props("outline size=sm").classes("w-full mt-2 text-indigo-300")
                else:
                    ui.button("Скомпилировать и скачать РПД (.docx)", icon="build", on_click=generate_and_download_rpd).classes("primary-btn w-full mt-4")

            # Token card
            token_usage = context.get("token_usage")
            with ui.card().classes("bg-slate-900/60 border border-indigo-500/40 p-5 rounded-xl flex flex-col justify-between"):
                with ui.column().classes("gap-2"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("insights", color="amber", size="1.8rem")
                        ui.label("Статистика ИИ генерации (Gemini)").classes("text-lg font-bold text-white")
                    if token_usage:
                        m_name = token_usage.get("model", "gemini-3.7-flash")
                        prompt_tok = token_usage.get("prompt_tokens", 0)
                        cand_tok = token_usage.get("candidate_tokens", 0)
                        tot_tok = token_usage.get("total_tokens", prompt_tok + cand_tok)
                        cost_usd = token_usage.get("cost_usd") or token_usage.get("estimated_cost_usd", 0.0)
                        cost_rub = token_usage.get("cost_rub") or token_usage.get("estimated_cost_rub", cost_usd * 95.0)
                        ui.label(f"Модель: {m_name}").classes("text-xs font-semibold text-indigo-300")
                        with ui.grid(columns=3).classes("w-full gap-2 text-center my-2"):
                            with ui.card().classes("bg-slate-950/60 p-2 rounded"):
                                ui.label("Входных").classes("text-[10px] text-gray-400")
                                ui.label(f"{prompt_tok:,}").classes("text-xs font-bold text-white")
                            with ui.card().classes("bg-slate-950/60 p-2 rounded"):
                                ui.label("Выходных").classes("text-[10px] text-gray-400")
                                ui.label(f"{cand_tok:,}").classes("text-xs font-bold text-white")
                            with ui.card().classes("bg-slate-950/60 p-2 rounded"):
                                ui.label("Стоимость").classes("text-[10px] text-gray-400")
                                ui.label(f"~{cost_rub:.2f} ₽").classes("text-xs font-bold text-emerald-400")
                    else:
                        ui.label("Использован структурированный расширенный академический каркас.").classes("text-xs text-gray-400")

                # AI Regen modal trigger
                def open_regen_dialog():
                    with ui.dialog() as dlg, ui.card().classes("app-card p-6 min-w-[420px] max-w-lg"):
                        with ui.row().classes("items-center gap-3 mb-2"):
                            ui.icon("refresh", color="amber", size="2rem")
                            ui.label("Перегенерация содержания РПД через ИИ").classes("text-lg font-bold text-white")
                        ui.label(
                            "Нейросеть Gemini выполнит повторный синтез индикаторов З-У-В, разделов, тем и литературы. "
                            "Все текущие ручные правки содержания будут обновлены."
                        ).classes("text-xs text-gray-300 mb-4")
                        with ui.row().classes("w-full justify-end gap-3"):
                            ui.button("Отмена", on_click=dlg.close).props("flat color=grey")
                            async def start_regen():
                                dlg.close()
                                app.storage.user[f"return_to_{project_id}"] = f"/project/{project_id}/rpd_final"
                                background_tasks.create(
                                    run_rpd_ai_pregeneration(
                                        project_id=project_id,
                                        username=user["username"],
                                        project_name=proj_name,
                                        plan_path=str(plan_path),
                                        course_name=context.get("course_code") or course_display,
                                        regenerate=True
                                    )
                                )
                                ui.notify("Запущена AI-перегенерация РПД...", type="info")
                                ui.navigate.to(f"/project/{project_id}/processing")
                            ui.button("⚡ Перегенерировать (AI)", on_click=start_regen).classes("primary-btn")
                    dlg.open()

                if os.environ.get("GOOGLE_API_KEY"):
                    ui.button("🔄 Перегенерировать контент (AI)", icon="auto_awesome", on_click=open_regen_dialog).props("outline color=amber size=sm").classes("w-full mt-4")

        # ── Summary & Preview Accordion ───────────────────────────────────────
        with ui.card().classes("app-card w-full mb-6 p-6"):
            ui.label("Сводные данные утвержденной РПД").classes("text-base font-semibold text-indigo-300 mb-4")

            # Metrics
            num_sec = len(context.get("sections", []))
            num_lessons = sum(len(s.get("lessons", [])) for s in context.get("t4_sections", []))
            num_srs = sum(len(s.get("themes", [])) for s in context.get("t5_sections", []))
            num_inter = len(context.get("interactive_items", []))
            num_cases = len(context.get("practical_works_list", []))
            num_tests = len(context.get("test_questions_list", []))
            num_oral = len(context.get("oral_questions_list", []))
            num_exam = len(context.get("exam_credit_questions_list", []))
            num_soft = len(context.get("software_items", []))

            # Hours badge bar
            with ui.row().classes("w-full gap-3 mb-3 flex-wrap"):
                ui.badge(f"Всего: {context.get('total_hours', 108)} ч.", color="indigo-8").classes("px-3 py-1 text-xs")
                ui.badge(f"Лекции: {context.get('lecture_hours', 0)} ч.", color="blue-8").classes("px-3 py-1 text-xs")
                ui.badge(f"Практики: {context.get('practical_hours', 0)} ч.", color="teal-8").classes("px-3 py-1 text-xs")
                ui.badge(f"Лабораторные: {context.get('lab_hours', 0) or 0} ч.", color="cyan-8").classes("px-3 py-1 text-xs")
                ui.badge(f"КРА: {context.get('kra_hours', 0)} ч.", color="slate-7").classes("px-3 py-1 text-xs")
                ui.badge(f"СРС: {context.get('srs_hours', 0)} ч.", color="amber-9").classes("px-3 py-1 text-xs")

            # Content depth metrics bar
            with ui.row().classes("w-full gap-2 mb-4 flex-wrap"):
                ui.badge(f"Разделов: {num_sec}", color="purple-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"Занятий (Табл. 5): {num_lessons}", color="indigo-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"Тем СРС (Табл. 6): {num_srs}", color="blue-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"Интерактивных форм: {num_inter}", color="teal-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"Кейсов: {num_cases}", color="cyan-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"Тестов: {num_tests}", color="emerald-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"Вопросов к экзамену: {num_exam}", color="amber-9").classes("px-2.5 py-0.5 text-xs")
                ui.badge(f"ПО: {num_soft}", color="slate-8").classes("px-2.5 py-0.5 text-xs")

            with ui.expansion("Компетенции и индикаторы З-У-В (Таблица 1)", icon="verified").classes("w-full mb-2 bg-slate-900/40 rounded-lg"):
                for comp in context.get("competencies_nested", []):
                    with ui.card().classes("w-full bg-slate-950/50 p-3 mb-2 border border-slate-800"):
                        ui.label(f"{comp.get('code')}: {comp.get('title')}").classes("font-semibold text-xs text-indigo-300 mb-1")
                        if comp.get("ind_first"):
                            ind = comp["ind_first"]
                            ui.label(f"• Индикатор {ind.get('code')}: {ind.get('title', '')}").classes("text-[11px] text-gray-300 mb-1 font-medium")
                            ui.label(f"Знать: {ind.get('know', '')}").classes("text-[10px] text-gray-400 pl-2")
                            ui.label(f"Уметь: {ind.get('able', '')}").classes("text-[10px] text-gray-400 pl-2")
                            ui.label(f"Владеть: {ind.get('master', '')}").classes("text-[10px] text-gray-400 pl-2 mb-1")
                        for oind in comp.get("other_indicators", []):
                            ui.label(f"• Индикатор {oind.get('code')}: {oind.get('title', '')}").classes("text-[11px] text-gray-300 mb-1 font-medium")
                            ui.label(f"Знать: {oind.get('know', '')}").classes("text-[10px] text-gray-400 pl-2")
                            ui.label(f"Уметь: {oind.get('able', '')}").classes("text-[10px] text-gray-400 pl-2")
                            ui.label(f"Владеть: {oind.get('master', '')}").classes("text-[10px] text-gray-400 pl-2 mb-1")

            with ui.expansion(f"Тематический план занятий (Таблица 5) — {num_lessons} занятий", icon="format_list_numbered").classes("w-full mb-2 bg-slate-900/40 rounded-lg"):
                for sec in context.get("t4_sections", []):
                    ui.label(sec.get("title", "")).classes("text-xs font-bold text-indigo-300 px-2 pt-2")
                    for lesson in sec.get("lessons", []):
                        with ui.row().classes("w-full justify-between items-center text-xs py-1 px-3 border-b border-slate-800/60"):
                            ui.label(f"[{lesson.get('theme', '')}] {lesson.get('title', '')}").classes("text-gray-200 flex-1")
                            ui.label(f"{lesson.get('hours', 2)} ч. | {lesson.get('control', 'Опрос')}").classes("text-gray-400")

            with ui.expansion(f"Самостоятельная работа студентов (Таблица 6) — {num_srs} тем", icon="menu_book").classes("w-full mb-2 bg-slate-900/40 rounded-lg"):
                for sec in context.get("t5_sections", []):
                    ui.label(sec.get("title", "")).classes("text-xs font-bold text-indigo-300 px-2 pt-2")
                    for t in sec.get("themes", []):
                        with ui.column().classes("w-full py-1.5 px-3 border-b border-slate-800/60 gap-0.5"):
                            ui.label(f"• {t.get('name', '')}").classes("text-xs font-medium text-gray-200")
                            ui.label(t.get("questions", "")).classes("text-[11px] text-gray-400 whitespace-pre-line pl-3")

            with ui.expansion(f"Интерактивные формы занятий (Таблица 7) — {num_inter} форм", icon="groups").classes("w-full mb-2 bg-slate-900/40 rounded-lg"):
                for item in context.get("interactive_items", []):
                    with ui.row().classes("w-full justify-between items-center text-xs py-1.5 px-3 border-b border-slate-800/60"):
                        ui.label(f"{item.get('num', '')}. {item.get('theme', '')} ({item.get('form', '')})").classes("text-gray-200 flex-1")
                        ui.label(item.get("tech", "")).classes("text-teal-300")

            with ui.expansion(f"Фонд оценочных средств (Кейсов: {num_cases}, Тестов: {num_tests}, Экзамен: {num_exam})", icon="quiz").classes("w-full mb-2 bg-slate-900/40 rounded-lg"):
                ui.label("Практические кейс-задания:").classes("text-xs font-semibold text-indigo-300 mb-1 px-2 pt-2")
                for pw in context.get("practical_works_list", []):
                    with ui.card().classes("w-full bg-slate-950/50 p-2 mb-2 border border-slate-800"):
                        ui.label(f"{pw.get('title', '')}").classes("text-xs font-bold text-white mb-1")
                        ui.label(pw.get("case_desc", "")).classes("text-[11px] text-gray-300 mb-2")
                        for q in pw.get("questions", []):
                            ui.label(f"  {q.get('label_num', '')}{q.get('text', '')}").classes("text-[10px] text-gray-400 pl-2")

                ui.label("Тестовые задания (примеры):").classes("text-xs font-semibold text-indigo-300 mt-2 mb-1 px-2")
                for tq in context.get("test_questions_list", [])[:4]:
                    with ui.column().classes("w-full text-xs py-1 px-3 border-b border-slate-800/60 gap-0.5"):
                        ui.label(f"{tq.get('label_num', '')}{tq.get('question', '')}").classes("text-gray-200 font-medium")
                        ui.label(f"  a) {tq.get('a', '')}").classes("text-[11px] text-emerald-400 pl-2")
                        ui.label(f"  b) {tq.get('b', '')}").classes("text-[11px] text-gray-400 pl-2")

                ui.label("Вопросы к экзамену / зачету (выборка):").classes("text-xs font-semibold text-indigo-300 mt-2 mb-1 px-2")
                for eq in context.get("exam_credit_questions_list", [])[:6]:
                    ui.label(f"• {eq.get('label_num', '')}{eq.get('text', '')}").classes("text-[11px] text-gray-300 pl-3 py-0.5")

            with ui.expansion(f"Литература и программное обеспечение (Таблица 10: {num_soft} наименований)", icon="library_books").classes("w-full bg-slate-900/40 rounded-lg"):
                ui.label("Основная литература (ЭБС «Лань» и «Юрайт»):").classes("text-xs font-semibold text-indigo-300 mb-1 px-2 pt-2")
                for lit in context.get("main_literature_list", []):
                    ui.label(f"• {lit}").classes("text-[11px] text-gray-300 mb-1 pl-3")
                ui.label("Дополнительная литература:").classes("text-xs font-semibold text-indigo-300 mt-2 mb-1 px-2")
                for lit in context.get("additional_literature_list", []):
                    ui.label(f"• {lit}").classes("text-[11px] text-gray-300 mb-1 pl-3")
                ui.label("Специализированное программное обеспечение (Таблица 10):").classes("text-xs font-semibold text-indigo-300 mt-2 mb-1 px-2")
                for sw in context.get("software_items", []):
                    with ui.row().classes("w-full justify-between items-center text-xs py-1 px-3 border-b border-slate-800/60"):
                        ui.label(f"{sw.get('num', '')}. {sw.get('name', '')} ({sw.get('type', '')})").classes("text-gray-200 flex-1")
                        ui.label(f"{sw.get('license', '')} ({sw.get('year', '')})").classes("text-gray-400")

        # ── Navigation / Step Redo Bar ─────────────────────────────────────────
        with ui.card().classes("app-card w-full p-6"):
            with ui.row().classes("w-full justify-between items-center gap-4"):
                ui.button(
                    "← Изменить общие данные (Шаг 2)",
                    icon="edit",
                    on_click=lambda: ui.navigate.to(f"/project/{project_id}/rpd")
                ).props("flat").classes("text-gray-400")

                ui.button(
                    "Далее: Настройка ОМД (Шаг 5) →",
                    icon="arrow_forward",
                    on_click=lambda: ui.navigate.to(f"/project/{project_id}/omd_parameters")
                ).classes("success-btn").props("size=lg")

