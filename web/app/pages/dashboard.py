"""
dashboard.py – Project list + unified new-project dialog (/dashboard)
Supports curriculum plan parsing via PyMuPDF, course selection, and sequential RPD -> OMD pipeline.
"""

import os
import shutil
import logging
from pathlib import Path
from nicegui import ui, events
from ..db import (
    get_user_projects, create_project, update_project_files, update_project_status,
    delete_project, input_dir, processing_dir, results_dir,
)
from ..auth import current_user, require_login
from .shared import page_layout, STATUS_LABELS
from rpd_app.core.curriculum_parser import CurriculumParser
from rpd_app.data.timiryazev_structure import (
    get_institutes, get_departments_by_institute, get_all_departments, find_institute_for_department
)

logger = logging.getLogger("dashboard")

STATUS_STEP = {
    "new":                  "/parameters",
    "plan_uploaded":        "/rpd",
    "rpd_wizard":           "/rpd",
    "generating_rpd":       "/rpd",
    "generating_rpd_content": "/processing",
    "rpd_ready":            "/rpd_final",
    "processing_structure": "/processing",
    "variables":            "/variables",
    "generating_questions": "/processing",
    "questions":            "/variables",
    "generating_docx":      "/processing",
    "done":                 "/download",
    "error":                "/rpd",
}

PRESET_PLANS = {
    "21.04.02 Землеустройство и кадастры (магистратура, 2026 г.)": str(
        Path("RPD-research/цифровые технологии в природоохранной деятельности на предприятии/Учебные_планы/21.04.02_Zemleustroistvo_i_kadastry_(mag.)_CTvZA_2026.plx.pdf").resolve()
    ),
    "05.03.06 Экология и природопользование (бакалавриат, 2026 г.)": str(
        Path("RPD-research/инновационные технологии в экологии и агроэкологии/05.03.06_Ekologicheskii_monitoring_i_agroekologiya_2026.plx.pdf").resolve()
    )
}


@ui.page("/dashboard")
async def dashboard_page():
    if not require_login():
        return

    user = current_user()
    projects = get_user_projects(user["user_id"])

    with page_layout("Мои проекты", user):
        # ── New project button ────────────────────────────────────────────────
        with ui.row().classes("w-full justify-end mb-4"):
            with ui.dialog() as new_dlg, ui.card().classes("app-card").style(
                "min-width: 620px; max-width: 800px; padding: 32px;"
            ):
                ui.label("Создание нового проекта").classes("text-xl font-bold text-white mb-2")
                ui.label(
                    "Загрузите учебный план для сквозной генерации РПД и ОМД, "
                    "или выберите существующую РПД для формирования только ОМД."
                ).classes("text-xs text-gray-400 mb-6")

                with ui.tabs().classes("w-full mb-4") as mode_tabs:
                    t_plan = ui.tab("Учебный план (РПД → ОМД)", icon="school")
                    t_legacy = ui.tab("Существующая РПД (только ОМД)", icon="description")

                upload_state = {
                    "mode": "plan",
                    "plan_path": None,
                    "plan_filename": None,
                    "all_disciplines": [],
                    "selected_code": "",
                    "selected_name": "",
                    "legacy_pdf_path": None,
                    "legacy_filename": None,
                }

                proj_name = (
                    ui.input(
                        label="Название проекта",
                        placeholder="Например: 21.04.02_Цифровые_технологии",
                    )
                    .props("outlined dark color=indigo")
                    .classes("w-full mb-4")
                )

                disc_select = ui.select(
                    label="Выберите дисциплину из учебного плана",
                    options={},
                    with_input=True
                ).props("outlined dark color=indigo").classes("w-full mb-3")

                all_institutes = get_institutes()
                all_depts = get_all_departments()

                with ui.row().classes("w-full gap-3 mb-4"):
                    inst_select = ui.select(
                        label="Институт (РГАУ-МСХА)",
                        options=all_institutes,
                        value=all_institutes[1] if len(all_institutes) > 1 else all_institutes[0]
                    ).props("outlined dark color=indigo").classes("flex-1")

                    dept_select = ui.select(
                        label="Кафедра создания РПД и ОМД",
                        options=all_depts,
                        value="Кафедра экологии",
                        with_input=True
                    ).props("outlined dark color=indigo").classes("flex-1")

                def on_inst_change(e):
                    if e.value:
                        depts = get_departments_by_institute(e.value)
                        if depts:
                            if dept_select.value not in depts:
                                dept_select.value = depts[0]
                            dept_select.options = depts
                inst_select.on_value_change(on_inst_change)

                def on_dept_change(e):
                    if e.value:
                        matched_inst = find_institute_for_department(e.value)
                        if matched_inst and inst_select.value != matched_inst:
                            inst_select.value = matched_inst
                dept_select.on_value_change(on_dept_change)

                def on_discipline_selected(code):
                    if not code:
                        return
                    upload_state["selected_code"] = code
                    name = ""
                    for d in upload_state["all_disciplines"]:
                        if d["code"] == code:
                            name = d["name"]
                            dept_name = d.get("department", "")
                            if dept_name:
                                matched_inst = find_institute_for_department(dept_name)
                                if matched_inst:
                                    inst_select.value = matched_inst
                                    depts = get_departments_by_institute(matched_inst)
                                    if dept_name not in depts:
                                        depts.append(dept_name)
                                    dept_select.options = depts
                                    dept_select.value = dept_name
                                elif dept_name in all_depts:
                                    dept_select.value = dept_name
                            break
                    upload_state["selected_name"] = name
                    # Suggest clean project name
                    clean_c = code.replace(".", "_").replace(" ", "_")
                    clean_n = "".join(ch for ch in name if ch.isalnum() or ch in "_-")[:30]
                    proj_name.value = f"{clean_c}_{clean_n}"

                disc_select.on_value_change(lambda e: on_discipline_selected(e.value))

                def parse_and_populate_plan(plan_file_path: str, filename: str):
                    try:
                        parser = CurriculumParser(plan_file_path)
                        discs = parser.list_disciplines()
                        upload_state["all_disciplines"] = discs
                        upload_state["plan_path"] = plan_file_path
                        upload_state["plan_filename"] = filename

                        options = {d["code"]: f"{d['code']} — {d['name']}" for d in discs}
                        disc_select.options = options

                        # Pick first or environmental tech default
                        default_code = None
                        for code, lbl in options.items():
                            if "цифров" in lbl.lower() and "природоохран" in lbl.lower():
                                default_code = code
                                break
                        if not default_code and options:
                            default_code = list(options.keys())[0]

                        disc_select.value = default_code
                        if default_code:
                            on_discipline_selected(default_code)

                        ui.notify(f"План прочитан: найдено дисциплин: {len(discs)}", type="positive")
                    except Exception as err:
                        logger.exception("Failed to parse plan: %s", err)
                        ui.notify(f"Ошибка парсинга плана: {err}", type="negative")

                with ui.tab_panels(mode_tabs, value=t_plan).classes("w-full bg-transparent"):
                    with ui.tab_panel(t_plan):
                        upload_state["mode"] = "plan"
                        ui.label("Выберите предустановленный план или загрузите новый (.plx.pdf / .pdf):").classes("text-xs text-gray-400 mb-2")

                        preset_opts = {k: k for k, path in PRESET_PLANS.items() if Path(path).exists()}
                        plan_preset_select = ui.select(
                            label="Образцы планов РГАУ-МСХА",
                            options=preset_opts,
                            value=list(preset_opts.keys())[0] if preset_opts else None
                        ).props("outlined dark color=indigo").classes("w-full mb-3")

                        def on_preset_change(e):
                            if e.value and e.value in PRESET_PLANS:
                                p_path = PRESET_PLANS[e.value]
                                parse_and_populate_plan(p_path, Path(p_path).name)

                        plan_preset_select.on_value_change(on_preset_change)

                        async def handle_plan_upload(e: events.UploadEventArguments):
                            f = e.file
                            filename = getattr(f, "name", None) or getattr(f, "filename", "plan.plx.pdf")
                            tmp_dir = Path(os.environ.get("DATA_DIR", "/app/data")) / "tmp_uploads"
                            tmp_dir.mkdir(parents=True, exist_ok=True)
                            dest = tmp_dir / filename
                            if hasattr(f, "save"):
                                await f.save(str(dest))
                            else:
                                content = await f.read()
                                with open(str(dest), "wb") as fout:
                                    fout.write(content)
                            parse_and_populate_plan(str(dest), filename)

                        ui.upload(
                            label="Или загрузить файл плана (.plx.pdf / .pdf)",
                            auto_upload=True,
                            on_upload=handle_plan_upload,
                            max_file_size=100_000_000,
                        ).props("accept=.pdf,.plx.pdf flat color=indigo dark").classes("w-full mb-4")

                        # Initialize with first preset if present
                        if plan_preset_select.value:
                            init_p = PRESET_PLANS[plan_preset_select.value]
                            parse_and_populate_plan(init_p, Path(init_p).name)

                    with ui.tab_panel(t_legacy):
                        upload_state["mode"] = "legacy"
                        ui.label("Загрузите готовый файл РПД в формате PDF:").classes("text-xs text-gray-400 mb-2")

                        legacy_label = ui.label("Файл не выбран").classes("text-xs text-gray-500 mb-3")

                        async def handle_legacy_upload(e: events.UploadEventArguments):
                            f = e.file
                            filename = getattr(f, "name", None) or getattr(f, "filename", "rpd.pdf")
                            tmp_dir = Path(os.environ.get("DATA_DIR", "/app/data")) / "tmp_uploads"
                            tmp_dir.mkdir(parents=True, exist_ok=True)
                            dest = tmp_dir / filename
                            if hasattr(f, "save"):
                                await f.save(str(dest))
                            else:
                                content = await f.read()
                                with open(str(dest), "wb") as fout:
                                    fout.write(content)
                            upload_state["legacy_pdf_path"] = str(dest)
                            upload_state["legacy_filename"] = filename
                            legacy_label.set_text(f"✓  {filename}")
                            legacy_label.style("color: #10b981; font-weight: 600;")
                            if not proj_name.value:
                                proj_name.value = Path(filename).stem
                            ui.notify(f"Файл «{filename}» загружен", type="positive")

                        ui.upload(
                            label="Выбрать файл РПД (.pdf)",
                            auto_upload=True,
                            on_upload=handle_legacy_upload,
                            max_file_size=100_000_000,
                        ).props("accept=.pdf flat color=indigo dark").classes("w-full mb-4")

                with ui.row().classes("gap-3 justify-end w-full mt-4"):
                    ui.button("Отмена", on_click=new_dlg.close).props("flat")

                    def do_create():
                        name = proj_name.value.strip()
                        if not name:
                            ui.notify("Введите название проекта", type="warning")
                            return

                        safe_name = "".join(
                            c if c.isalnum() or c in "-_." else "_" for c in name
                        )
                        inp = input_dir(safe_name)
                        proc = processing_dir(safe_name)
                        results_dir(safe_name)

                        if mode_tabs.value == t_plan:
                            if not upload_state["plan_path"]:
                                ui.notify("Выберите или загрузите учебный план", type="warning")
                                return
                            if not upload_state["selected_code"]:
                                ui.notify("Выберите дисциплину из списка", type="warning")
                                return

                            dest_plan = inp / upload_state["plan_filename"]
                            shutil.copy(upload_state["plan_path"], str(dest_plan))

                            pid = create_project(
                                user_id=user["user_id"],
                                name=safe_name,
                                course_code=upload_state["selected_code"],
                                course_name=upload_state["selected_name"],
                                plan_filename=upload_state["plan_filename"],
                                department=dept_select.value or "Кафедра экологии",
                                institute=inst_select.value or ""
                            )
                            update_project_files(pid, plan_path=str(dest_plan))
                            update_project_status(pid, "rpd_wizard")

                            new_dlg.close()
                            ui.navigate.to(f"/project/{pid}/rpd")

                        else:
                            if not upload_state["legacy_pdf_path"]:
                                ui.notify("Загрузите PDF файл РПД", type="warning")
                                return

                            dest_pdf = inp / upload_state["legacy_filename"]
                            shutil.move(upload_state["legacy_pdf_path"], str(dest_pdf))

                            pid = create_project(
                                user_id=user["user_id"],
                                name=safe_name,
                                plan_filename=upload_state["legacy_filename"],
                                department=dept_select.value or "",
                                institute=inst_select.value or ""
                            )
                            update_project_files(pid, syllabus_path=str(dest_pdf))

                            new_dlg.close()
                            ui.navigate.to(f"/project/{pid}/parameters")

                    ui.button(
                        "Создать проект →", on_click=do_create
                    ).classes("primary-btn")

            ui.button("+ Новый проект", on_click=new_dlg.open).classes("primary-btn")

        def open_delete_dialog(proj: dict):
            with ui.dialog() as dlg, ui.card().classes("app-card p-6 min-w-[380px] max-w-md"):
                ui.label("Удаление проекта").classes("text-lg font-bold text-white mb-2")
                disp_title = proj.get("course_name") or proj["name"]
                ui.label(
                    f"Вы действительно хотите удалить проект «{disp_title}»?\n\n"
                    "Все связанные файлы (учебный план, контекст, сгенерированные РПД и ОМД) будут безвозвратно удалены из файловой системы и базы данных."
                ).classes("text-sm text-gray-300 mb-6 whitespace-pre-line")
                with ui.row().classes("w-full justify-end gap-3"):
                    ui.button("Отмена", on_click=dlg.close).props("flat")
                    def confirm_delete():
                        safe_name = proj["name"]
                        delete_project(proj["id"])
                        # Clean filesystem
                        shutil.rmtree(input_dir(safe_name), ignore_errors=True)
                        shutil.rmtree(processing_dir(safe_name), ignore_errors=True)
                        shutil.rmtree(results_dir(safe_name), ignore_errors=True)
                        dlg.close()
                        ui.notify(f"Проект «{safe_name}» успешно удален", type="positive")
                        ui.navigate.to("/")
                    ui.button("Удалить", on_click=confirm_delete).props("color=negative")
            dlg.open()

        # ── Projects list ─────────────────────────────────────────────────────
        if not projects:
            with ui.column().classes("w-full items-center justify-center gap-4").style(
                "padding: 80px 0;"
            ):
                ui.icon("folder_open", size="4rem").style(
                    "color: rgba(99,102,241,0.3);"
                )
                ui.label("Нет проектов").classes("text-xl font-semibold text-gray-500")
                ui.label("Нажмите «+ Новый проект» чтобы начать").classes(
                    "text-sm text-gray-600"
                )
        else:
            with ui.column().classes("w-full gap-3"):
                for p in projects:
                    status = p.get("status", "new")
                    badge_cls = f"badge badge-{status}"
                    step_route = STATUS_STEP.get(status, "/rpd" if p.get("course_code") else "/parameters")

                    with ui.card().classes(
                        "app-card w-full cursor-pointer project-card"
                    ).style("padding: 20px 24px;").on(
                        "click",
                        lambda _, pid=p["id"], r=step_route: ui.navigate.to(
                            f"/project/{pid}{r}"
                        ),
                    ):
                        with ui.row().classes("w-full items-center gap-4"):
                            icon_name = "school" if p.get("course_code") else "description"
                            ui.icon(icon_name, size="1.8rem").style(
                                "color: #6366f1;"
                            )
                            with ui.column().classes("flex-1 gap-1"):
                                title_text = p["name"]
                                if p.get("course_name"):
                                    title_text = f"{p.get('course_code', '')} {p['course_name']}".strip()
                                ui.label(title_text).classes(
                                    "text-base font-semibold text-white"
                                )
                                subtitle = f"Проект: {p['name']} • Создан: {p['created_at'][:10] if p['created_at'] else '—'}"
                                ui.label(subtitle).classes("text-xs text-gray-500")

                            ui.label(STATUS_LABELS.get(status, status)).classes(
                                badge_cls
                            )
                            if status == "error":
                                ui.icon("error_outline", size="1.2rem").style(
                                    "color: #ef4444;"
                                ).tooltip(p.get("error_message", ""))

                            # Delete button with click.stop so it doesn't trigger card navigation
                            del_btn = ui.button(icon="delete").props("flat round dense color=negative").tooltip("Удалить проект")
                            del_btn.on("click.stop", lambda _, proj=p: open_delete_dialog(proj))

                            ui.icon("chevron_right", size="1.2rem").style(
                                "color: #6366f1;"
                            )

        ui.add_head_html("""
        <style>
          .project-card { transition: all 0.2s ease; }
          .project-card:hover {
            border-color: rgba(99,102,241,0.5) !important;
            transform: translateY(-1px);
          }
        </style>""")
