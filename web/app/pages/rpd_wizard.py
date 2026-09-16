"""
rpd_wizard.py – Step 1 of Unified Pipeline: RPD Verification & Generation (/project/{id}/rpd)
Allows interactive verification of curriculum plan extraction, hours balance,
competency descriptors (З-У-В), generates 100% compliant RPD DOCX,
and bridges verified data directly into OMD.
"""

import os
import json
import logging
from pathlib import Path
from nicegui import ui, background_tasks

from ..db import get_project, update_project_status, update_project_files, update_project_meta, processing_dir, results_dir
from ..auth import current_user, require_login
from ..pipeline import run_rpd_generation, run_rpd_to_omd_bridge
from .shared import page_layout, _step_indicator
from rpd_app.core.curriculum_parser import CurriculumParser
from rpd_app.core.course_presets import (
    get_preset_for_environmental_digital_tech,
    build_generic_context_from_parsed
)

logger = logging.getLogger("rpd_wizard")

def _assert_owner(project, user):
    return project and project["user_id"] == user["user_id"]


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

    if not context and plan_path and Path(plan_path).exists():
        try:
            parser = CurriculumParser(plan_path)
            meta = parser.extract_metadata()
            target_course = project.get("course_name") or project.get("course_code") or proj_name
            disc = parser.extract_discipline_details(target_course)
            sem = disc["semesters"][0] if disc.get("semesters") else 1
            coreqs = parser.extract_corequisites(sem, disc.get("code", ""))
            comps = parser.extract_competency_details(disc.get("competency_codes", []))

            if "цифровые технологии" in target_course.lower() and "природоохран" in target_course.lower():
                context = get_preset_for_environmental_digital_tech()
            else:
                context = build_generic_context_from_parsed(meta, disc, comps, coreqs)

            with open(context_file, "w", encoding="utf-8") as f:
                json.dump(context, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed to parse plan in wizard: %s", exc)
            context = get_preset_for_environmental_digital_tech()

    with page_layout(f"Мастер РПД: {context.get('course_name', proj_name)}", user):
        _step_indicator(1, project)

        with ui.card().classes("app-card w-full mb-6").style("padding: 24px 32px;"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.column().classes("gap-1"):
                    ui.label("Интеллектуальный конструктор РПД").classes("text-xl font-bold text-white")
                    ui.label(
                        "Проверьте извлеченные из учебного плана данные. "
                        "После подтверждения будет сгенерирована рабочая программа (14 правил оформления), "
                        "которая послужит основой для ОМД."
                    ).classes("text-sm text-gray-400")
                ui.badge("14 правил верстки РГАУ-МСХА", color="indigo-7").classes("text-xs px-3 py-1")

        # ── Multi-Tab Wizard Form ─────────────────────────────────────────────
        with ui.card().classes("app-card w-full").style("padding: 24px 32px;"):
            with ui.tabs().classes("w-full mb-6") as tabs:
                t1 = ui.tab("1. Титул и метаданные", icon="badge")
                t2 = ui.tab("2. Часы и трудоемкость", icon="schedule")
                t3 = ui.tab("3. Компетенции (Табл. 1)", icon="assignment_turned_in")
                t4 = ui.tab("4. Тематический план", icon="menu_book")
                t5 = ui.tab("5. Литература и авторы", icon="school")

            with ui.tab_panels(tabs, value=t1).classes("w-full bg-transparent"):
                # ── Tab 1: Метаданные ────────────────────────────────────────
                with ui.tab_panel(t1):
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        in_dir_code = ui.input("Код направления", value=context.get("direction_code", "")).props("outlined dark color=indigo")
                        in_dir_name = ui.input("Наименование направления", value=context.get("direction_name", "")).props("outlined dark color=indigo")
                        in_profile = ui.input("Направленность (профиль)", value=context.get("profile", "")).props("outlined dark color=indigo")
                        in_qual = ui.select(options=["магистр", "бакалавр", "специалист"], label="Квалификация", value=context.get("qualification", "магистр")).props("outlined dark color=indigo")
                        in_inst = ui.input("Институт", value=context.get("institute", "")).props("outlined dark color=indigo")
                        in_dept = ui.input("Кафедра", value=context.get("department", "")).props("outlined dark color=indigo")
                        in_head_fio = ui.input("Заведующий кафедрой (ФИО)", value=context.get("department_head_fio", "")).props("outlined dark color=indigo")
                        in_head_status = ui.input("Статус зав. кафедрой (должность)", value=context.get("department_head_status", "Заведующий кафедрой")).props("outlined dark color=indigo")
                        in_year = ui.input("Год набора", value=str(context.get("start_year", "2026"))).props("outlined dark color=indigo")
                        in_curr_year = ui.input("Учебный год", value=str(context.get("current_year", "2026"))).props("outlined dark color=indigo")

                # ── Tab 2: Часы и баланс ─────────────────────────────────────
                with ui.tab_panel(t2):
                    with ui.grid(columns=3).classes("w-full gap-4"):
                        in_code = ui.input("Код дисциплины", value=context.get("course_code", "")).props("outlined dark color=indigo")
                        in_name = ui.input("Наименование дисциплины", value=context.get("course_name", "")).props("outlined dark color=indigo").classes("col-span-2")
                        in_sem = ui.number("Семестр", value=int(context.get("semester", 4)), min=1, max=12).props("outlined dark color=indigo")
                        in_course_yr = ui.input("Курс обучения", value=str(context.get("course_year", 2))).props("outlined dark color=indigo readonly")
                        in_control = ui.select(options=["зачет с оценкой", "экзамен", "зачет"], label="Форма контроля", value=context.get("control_form", "зачет с оценкой")).props("outlined dark color=indigo")

                        in_zet = ui.number("ЗЕТ", value=float(str(context.get("total_zet", 3)).replace(",", "."))).props("outlined dark color=indigo")
                        in_total = ui.number("Всего часов", value=float(str(context.get("total_hours", 108)).replace(",", "."))).props("outlined dark color=indigo")
                        in_lec = ui.number("Лекции (час)", value=float(str(context.get("lecture_hours", 12)).replace(",", "."))).props("outlined dark color=indigo")
                        in_prac = ui.number("Практические (час)", value=float(str(context.get("practical_hours", 12)).replace(",", "."))).props("outlined dark color=indigo")
                        in_lab = ui.number("Лабораторные (час)", value=float(str(context.get("lab_hours", 0) or 0).replace(",", "."))).props("outlined dark color=indigo")
                        in_srs = ui.number("СРС (час)", value=float(str(context.get("srs_hours", 83.65)).replace(",", "."))).props("outlined dark color=indigo")
                        in_kra = ui.number("Контроль / КРА (час)", value=float(str(context.get("kra_hours", 0.35)).replace(",", "."))).props("outlined dark color=indigo")

                    balance_badge = ui.badge("Баланс часов: расчет...", color="positive").classes("text-sm py-1 px-3 mt-4")

                    def recalc_balance():
                        tot = (in_lec.value or 0) + (in_prac.value or 0) + (in_lab.value or 0) + (in_srs.value or 0) + (in_kra.value or 0)
                        target = in_total.value or ((in_zet.value or 0) * 36)
                        diff = round(tot - target, 2)
                        if abs(diff) < 0.05:
                            balance_badge.set_text(f"✓ Баланс часов сошелся: {tot} ч. из {target} ч.")
                            balance_badge.props("color=positive")
                        else:
                            balance_badge.set_text(f"Внимание: расхождение баланса: {tot} ч. из {target} ч. ({diff:+} ч.)")
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
                with ui.tab_panel(t3):
                    ui.label("Декомпозиция индикаторов компетенций (Таблица 1):").classes("text-sm text-gray-400 mb-4")
                    comps_list = context.get("competencies_nested", [])

                    for comp in comps_list:
                        with ui.expansion(f"{comp.get('code')}: {comp.get('title')}", icon="verified").classes("w-full mb-3"):
                            if comp.get("ind_first"):
                                ind = comp["ind_first"]
                                with ui.card().classes("w-full bg-slate-900/50 p-4 mb-2 border border-slate-700/50"):
                                    ui.label(f"Индикатор {ind.get('code')}: {ind.get('title', '')}").classes("font-semibold text-indigo-300 mb-2")
                                    k_inp = ui.input("Знать", value=ind.get("know", "")).props("outlined dark color=indigo").classes("w-full mb-2")
                                    a_inp = ui.input("Уметь", value=ind.get("able", "")).props("outlined dark color=indigo").classes("w-full mb-2")
                                    m_inp = ui.input("Владеть", value=ind.get("master", "")).props("outlined dark color=indigo").classes("w-full")
                                    comp_widget_list.append((ind, k_inp, a_inp, m_inp))

                            for oind in comp.get("other_indicators", []):
                                with ui.card().classes("w-full bg-slate-900/50 p-4 mb-2 border border-slate-700/50"):
                                    ui.label(f"Индикатор {oind.get('code')}: {oind.get('title', '')}").classes("font-semibold text-indigo-300 mb-2")
                                    k_inp = ui.input("Знать", value=oind.get("know", "")).props("outlined dark color=indigo").classes("w-full mb-2")
                                    a_inp = ui.input("Уметь", value=oind.get("able", "")).props("outlined dark color=indigo").classes("w-full mb-2")
                                    m_inp = ui.input("Владеть", value=oind.get("master", "")).props("outlined dark color=indigo").classes("w-full")
                                    comp_widget_list.append((oind, k_inp, a_inp, m_inp))

                # ── Tab 4: Тематический план ────────────────────────────────
                with ui.tab_panel(t4):
                    ui.label("Разделы и тематическая структура дисциплины (Таблицы 2, 3 и 4):").classes("text-sm text-gray-400 mb-4")
                    for s in context.get("sections", []):
                        with ui.row().classes("w-full items-center justify-between p-3 bg-slate-900/50 border border-slate-700/50 rounded-lg mb-2"):
                            ui.label(s.get("name", "")).classes("font-medium text-sm flex-1 text-gray-200")
                            ui.badge(f"Лекции: {s.get('lec', 0)} ч.", color="indigo-8")
                            ui.badge(f"Практика: {s.get('prac', 0)} ч.", color="teal-8")
                            ui.badge(f"СРС: {s.get('srs', 0)} ч.", color="amber-9")

                # ── Tab 5: Литература и разработчики ─────────────────────────
                dev_widget_list = []
                with ui.tab_panel(t5):
                    ui.label("Разработчики рабочей программы:").classes("text-sm font-semibold text-indigo-300 mb-2")
                    for dev in context.get("developers_list", []):
                        with ui.row().classes("w-full gap-4 mb-2"):
                            p_inp = ui.input("Должность", value=dev.get("position", "")).props("outlined dark color=indigo").classes("flex-1")
                            f_inp = ui.input("ФИО, ученая степень", value=dev.get("fio_rank", "")).props("outlined dark color=indigo").classes("flex-1")
                            dev_widget_list.append((dev, p_inp, f_inp))

                    ui.separator().classes("my-4").style("border-color: rgba(99,102,241,0.2);")
                    ui.label("Основная литература:").classes("text-sm font-semibold text-indigo-300 mb-2")
                    for lit in context.get("main_literature_list", []):
                        ui.label(f"• {lit}").classes("text-xs text-gray-300 mb-1")

            # ── Action Bar ────────────────────────────────────────────────────
            ui.separator().classes("my-6").style("border-color: rgba(99,102,241,0.2);")

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

                context["total_zet"] = str(in_zet.value)
                context["total_hours"] = str(in_total.value).rstrip("0").rstrip(".")
                context["lecture_hours"] = str(in_lec.value).rstrip("0").rstrip(".")
                context["practical_hours"] = str(in_prac.value).rstrip("0").rstrip(".")
                context["lab_hours"] = str(in_lab.value).rstrip("0").rstrip(".") if in_lab.value else ""
                context["contact_auditory_hours"] = str(int((in_lec.value or 0) + (in_prac.value or 0)))
                context["contact_hours"] = str(round((in_lec.value or 0) + (in_prac.value or 0) + (in_kra.value or 0), 2)).replace(".", ",")
                context["srs_hours"] = str(in_srs.value).replace(".", ",")
                context["srs_self_hours"] = str(in_srs.value).replace(".", ",")
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

                # Save З-У-В inputs
                for target_dict, k_inp, a_inp, m_inp in comp_widget_list:
                    target_dict["know"] = k_inp.value
                    target_dict["able"] = a_inp.value
                    target_dict["master"] = m_inp.value

                # Save developer inputs
                for target_dict, p_inp, f_inp in dev_widget_list:
                    target_dict["position"] = p_inp.value
                    target_dict["fio_rank"] = f_inp.value

                # Clean any lingering widget or un-serializable references
                clean_context = sanitize_for_json(context)
                context.clear()
                context.update(clean_context)

                # Save to disk
                proc_dir.mkdir(parents=True, exist_ok=True)
                with open(context_file, "w", encoding="utf-8") as f:
                    json.dump(clean_context, f, indent=2, ensure_ascii=False)

                return clean_context

            rpd_status_label = ui.label("").classes("text-sm text-gray-300 mb-2")
            download_rpd_btn = ui.button("Скачать готовую РПД (.docx)", icon="download").props("color=positive size=md").classes("hidden")

            async def do_generate_rpd():
                save_ui_to_context()
                rpd_status_label.set_text("Генерация РПД с проверкой 14 правил верстки...")
                try:
                    await run_rpd_generation(
                        project_id=project_id,
                        username=user["username"],
                        project_name=proj_name,
                        plan_path=plan_path,
                        course_name=context.get("course_name", proj_name),
                        custom_context=context
                    )
                    proj_updated = get_project(project_id)
                    rpd_p = proj_updated.get("rpd_path")
                    if rpd_p and Path(rpd_p).exists():
                        fname = Path(rpd_p).name
                        rpd_status_label.set_text(f"✓ РПД успешно сформирована: {fname}")
                        download_rpd_btn.classes(remove="hidden")
                        download_rpd_btn.on_click(lambda: ui.download(rpd_p, filename=fname))
                        ui.notify("РПД успешно сгенерирована!", type="positive")
                except Exception as exc:
                    rpd_status_label.set_text(f"Ошибка генерации РПД: {exc}")
                    ui.notify(f"Ошибка: {exc}", type="negative")

            async def do_proceed_to_omd():
                save_ui_to_context()
                # Run bridge to ensure variables.yml is up to date with RPD data
                await run_rpd_to_omd_bridge(
                    project_id=project_id,
                    username=user["username"],
                    project_name=proj_name
                )
                ui.navigate.to(f"/project/{project_id}/variables")

            with ui.row().classes("w-full justify-between items-center gap-4"):
                with ui.row().classes("gap-3 items-center"):
                    ui.button("Сгенерировать РПД", icon="auto_fix_high", on_click=do_generate_rpd).classes("primary-btn")
                    download_rpd_btn

                ui.button("Перейти к формированию ОМД →", icon="arrow_forward", on_click=do_proceed_to_omd).classes("success-btn")

        # If RPD is already generated, show download button initially
        existing_rpd = project.get("rpd_path")
        if existing_rpd and Path(existing_rpd).exists():
            fname = Path(existing_rpd).name
            rpd_status_label.set_text(f"✓ РПД ранее сгенерирована: {fname}")
            download_rpd_btn.classes(remove="hidden")
            download_rpd_btn.on_click(lambda: ui.download(existing_rpd, filename=fname))
