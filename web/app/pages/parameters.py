import os
import json
import asyncio
import zipfile
from pathlib import Path
from nicegui import app, ui, background_tasks
from ..db import (
    get_project,
    update_project_status,
    update_project_files,
    update_project_department,
    processing_dir,
    results_dir,
)
from ..auth import current_user, require_login
from rpd_app.data.timiryazev_structure import get_all_departments, find_institute_for_department
from ..pipeline import (
    load_env_defaults,
    read_parameters_env,
    write_parameters_env,
    run_extraction,
    generate_docx,
    run_rpd_to_omd_bridge,
    run_questions_generation,
)
from .shared import page_layout, STATUS_LABELS, _step_indicator


# ── Parameter labels (Russian translations) ──────────────────────────────────

PARAM_LABELS = {
    "course_type":              "Тип курса",
    "hours":                    "Часы (всего)",
    "year_of_study_start":      "Год начала обучения",
    "seminar_questions_number": "Вопросов на семинарском занятии",
    "control_questions_number": "Вопросов в контрольной работе",
    "test_questions_number":    "Вопросов на зачёте/экзамене",
    "lab_questions_number":     "Вопросов на лабораторном занятии",
    "project_questions_number": "Вопросов по проекту",
    "other_questions_number":   "Вопросов по прочим видам деятельности",
}

PARAM_HINTS = {
    "seminar_questions_number": "количество вопросов для практических занятий",
    "control_questions_number": "вопросы / задачи в вариантах к/р",
    "test_questions_number":    "вопросы к зачёту или экзамену",
}


def _assert_owner(project, user):
    return project and project["user_id"] == user["user_id"]


# ── Step 1: Course & Parameters editor ───────────────────────────────────────

@ui.page("/project/{project_id}/parameters")
async def parameters_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    # Redirect if actively running background pipeline
    status = project.get("status", "new")
    if status in ("processing_structure", "generating_questions", "generating_docx", "generating_rpd_content"):
        ui.navigate.to(f"/project/{project_id}/processing")
        return

    has_plan = bool(project.get("plan_path") or project.get("plan_filename") or project.get("course_code"))
    course_display = project.get("course_name") or project.get("course_code") or project["name"]

    # Load defaults + existing params
    defaults = load_env_defaults()
    proc_dir = processing_dir(project["name"])
    env_path = proc_dir / "parameters.env"
    existing = read_parameters_env(env_path)
    merged = {k: existing.get(k, v) for k, v in defaults.items()}

    with page_layout(f"Шаг 1: Курс {course_display}", user):
        _step_indicator(1, project)

        with ui.card().classes("app-card w-full").style("padding: 32px;"):
            with ui.row().classes("w-full justify-between items-center mb-2"):
                ui.label("Шаг 1: Ввод данных о курсе").classes("text-xl font-bold text-white")
                ui.badge("Базовые параметры", color="indigo-7").classes("text-xs px-3 py-1")

            ui.label(
                "Базовые настройки дисциплины и параметров генерации фонда оценочных средств. "
                "Вы можете изменить параметры или сразу перейти к общим данным РПД."
            ).classes("text-sm text-gray-400 mb-6")

            inputs: dict[str, ui.input] = {}
            with ui.grid(columns=2).classes("w-full gap-4"):
                for key, default_val in defaults.items():
                    label = PARAM_LABELS.get(key, key)
                    hint = PARAM_HINTS.get(key, "")
                    current_val = merged.get(key, default_val)

                    with ui.column().classes("gap-1"):
                        inp = (
                            ui.input(label=label, value=str(current_val))
                            .props("outlined dark color=indigo")
                            .classes("w-full")
                        )
                        if hint:
                            ui.label(hint).classes("text-xs text-gray-600")
                        inputs[key] = inp

            ui.separator().classes("my-6").style("border-color: rgba(99,102,241,0.2);")

            # Check if variables.yml already exists
            variables_path = proc_dir / "variables.yml"
            has_variables = variables_path.exists()

            redo_cb = None
            if has_variables and not has_plan:
                with ui.row().classes("w-full items-center gap-2 mb-4"):
                    redo_cb = ui.checkbox("Запустить AI-обработку заново (сотрет все прошлые ручные правки)").props("dark color=red")

            async def do_save_params() -> dict:
                params = {k: inp.value.strip() for k, inp in inputs.items()}
                env_path.parent.mkdir(parents=True, exist_ok=True)
                write_parameters_env(env_path, project["name"], params)
                update_project_files(project_id, parameters_path=str(env_path))
                return params

            async def do_save_and_to_rpd():
                await do_save_params()
                ui.navigate.to(f"/project/{project_id}/rpd")

            async def do_start_legacy_extraction():
                params = await do_save_params()
                should_redo = redo_cb.value if redo_cb else False
                if has_variables and not should_redo:
                    update_project_status(project_id, "variables")
                    update_project_files(project_id, variables_path=str(variables_path))
                    ui.navigate.to(f"/project/{project_id}/variables")
                else:
                    syllabus = project.get("syllabus_path") or ""
                    background_tasks.create(
                        run_extraction(project_id, user["username"], project["name"], syllabus, params, regenerate=True)
                    )
                    app.storage.user[f"return_to_{project_id}"] = f"/project/{project_id}/variables"
                    ui.navigate.to(f"/project/{project_id}/processing")

            with ui.row().classes("gap-4 items-center justify-between w-full"):
                if has_plan:
                    ui.button(
                        "Далее: Общие данные РПД (Шаг 2) →",
                        icon="arrow_forward",
                        on_click=do_save_and_to_rpd
                    ).classes("primary-btn").props("size=lg")
                else:
                    ui.button(
                        "Запустить обработку →",
                        icon="rocket_launch",
                        on_click=do_start_legacy_extraction
                    ).classes("primary-btn").props("size=lg")

                rpd_file_exists = (proc_dir / "rpd_context.json").exists() or bool(project.get("rpd_path"))
                if rpd_file_exists:
                    ui.button(
                        "К финалу РПД (Шаг 4)",
                        icon="verified",
                        on_click=lambda: ui.navigate.to(f"/project/{project_id}/rpd_final")
                    ).props("flat").classes("text-indigo-400")

                if has_variables:
                    ui.button(
                        "К вопросам ОМД (Шаг 7)",
                        icon="chevron_right",
                        on_click=lambda: ui.navigate.to(f"/project/{project_id}/variables")
                    ).props("flat").classes("text-indigo-400")


# ── Step 3 & 6: Processing / Generating status ───────────────────────────────

@ui.page("/project/{project_id}/processing")
async def processing_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    status = project.get("status", "new")
    if status not in ("processing_structure", "generating_questions", "generating_docx", "generating_rpd_content", "generating_rpd"):
        _redirect_by_status(project_id, status)
        return

    if status in ("generating_rpd_content", "generating_rpd"):
        title = "Шаг 3: Синтез содержания РПД (AI Gemini)..."
        desc = "Интеллектуальный синтез З-У-В компетенций, тем лекций, практик, СРС и оценочных средств…"
        active_step = 3
    elif status in ("processing_structure", "generating_questions"):
        title = "Шаг 6: Синтез оценочных материалов ОМД (AI Gemini)..."
        desc = "Идёт генерация вопросов к лекциям/семинарам, тестов и оценочных средств…"
        active_step = 6
    elif status == "generating_docx":
        title = "Формирование документов Word..."
        desc = "Компиляция документа Word по академическому шаблону…"
        active_step = 6
    else:
        title = "Обработка..."
        desc = "Выполняются фоновые задачи…"
        active_step = 3

    with page_layout(title, user):
        _step_indicator(active_step, project)

        with ui.column().classes("w-full gap-6 items-stretch"):
            with ui.card().classes("app-card items-center justify-center p-8 w-full text-center"):
                ui.spinner(size="4rem").style("color: #6366f1;")
                ui.label(title).classes("text-lg font-semibold mt-6 mb-2 text-white")
                ui.label(desc).classes("text-sm text-gray-400 mb-6")

                status_label = ui.label("Статус: обработка...").classes("text-sm text-indigo-300 font-medium")

                with ui.expansion("Подсказка").classes("w-full mt-4 text-left"):
                    ui.label(
                        "Обработка выполняется в фоновом режиме. Вы можете отслеживать "
                        "терминальный вывод и ход выполнения в консоли ниже."
                    ).classes("text-xs text-gray-500")

            with ui.card().classes("app-card w-full p-6"):
                with ui.expansion("Логи выполнения CLI", icon="terminal").classes("w-full text-base font-semibold text-indigo-300"):
                    log_view = ui.log().classes("w-full font-mono text-xs bg-gray-950 border border-indigo-950 rounded-lg p-4 mt-3 text-white").style("height: 380px;")

        # Set up log file reader
        proc_dir = processing_dir(project["name"])
        log_file = proc_dir / "pipeline.log"
        last_pos = 0

        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8")
                log_view.push(content)
                last_pos = log_file.stat().st_size
            except Exception:
                pass

        timer = None
        async def poll():
            nonlocal timer, last_pos
            try:
                if log_file.exists():
                    current_size = log_file.stat().st_size
                    if current_size > last_pos:
                        with open(log_file, "r", encoding="utf-8") as f:
                            f.seek(last_pos)
                            new_text = f.read()
                            if new_text:
                                log_view.push(new_text)
                        last_pos = current_size
            except Exception:
                pass

            try:
                p = get_project(project_id)
                if not p:
                    return
                s = p.get("status", "new")
                status_label.text = f"Статус: {STATUS_LABELS.get(s, s)}"

                # Check if RPD synthesis finished -> return to return_to or Step 4 (rpd_final)
                if s in ("rpd_wizard", "rpd_ready"):
                    if timer:
                        timer.cancel()
                    target = app.storage.user.get(f"return_to_{project_id}", f"/project/{project_id}/rpd_final")
                    app.storage.user.pop(f"return_to_{project_id}", None)
                    ui.navigate.to(target)

                # Check if OMD synthesis finished -> return to return_to or Step 7 (variables)
                elif s in ("variables", "questions"):
                    if timer:
                        timer.cancel()
                    target = app.storage.user.get(f"return_to_{project_id}", f"/project/{project_id}/variables")
                    app.storage.user.pop(f"return_to_{project_id}", None)
                    ui.navigate.to(target)

                # Check if full compile finished -> Step 8 (download)
                elif s == "done":
                    if timer:
                        timer.cancel()
                    target = app.storage.user.get(f"return_to_{project_id}", f"/project/{project_id}/download")
                    app.storage.user.pop(f"return_to_{project_id}", None)
                    ui.navigate.to(target)

                elif s == "error":
                    if timer:
                        timer.cancel()
                    err = p.get("error_message") or "Ошибка выполнения"
                    ui.notify(f"Ошибка: {err}", type="negative", timeout=10000)
                    target = app.storage.user.get(f"return_to_{project_id}")
                    if target:
                        app.storage.user.pop(f"return_to_{project_id}", None)
                        ui.navigate.to(target)
                    elif p.get("plan_path") or p.get("course_code"):
                        ui.navigate.to(f"/project/{project_id}/rpd")
                    else:
                        ui.navigate.to(f"/project/{project_id}/parameters")
            except Exception:
                if timer:
                    timer.cancel()

        timer = ui.timer(1.5, poll)


# ── Step 5: OMD Parameters ───────────────────────────────────────────────────

@ui.page("/project/{project_id}/omd_parameters")
async def omd_parameters_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    proj_name = project["name"]
    proc_dir = processing_dir(proj_name)
    env_path = proc_dir / "parameters.env"
    existing_params = read_parameters_env(env_path)
    defaults = load_env_defaults()
    merged = {k: existing_params.get(k, v) for k, v in defaults.items()}

    # Also load rpd_context if available for synchronizing course details
    context_file = proc_dir / "rpd_context.json"
    context = {}
    if context_file.exists():
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                context = json.load(f)
        except Exception:
            pass

    course_title = context.get("course_name") or project.get("course_name") or proj_name

    with page_layout(f"Шаг 5: ОМД {course_title}", user):
        _step_indicator(5, project)

        with ui.card().classes("app-card w-full mb-6").style("padding: 24px 32px;"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.column().classes("gap-1"):
                    ui.label("Шаг 5: Общие данные ОМД").classes("text-xl font-bold text-white")
                    ui.label(
                        "Настройте реквизиты оценочных материалов, форму контроля и состав оценочных средств. "
                        "Данные синхронизированы с утвержденной рабочей программой (РПД)."
                    ).classes("text-sm text-gray-400")
                ui.badge("Оценочные материалы (ФОС)", color="indigo-7").classes("text-xs px-3 py-1")

        with ui.card().classes("app-card w-full mb-6").style("padding: 24px 32px;"):
            ui.label("Реквизиты заседания кафедры и форма контроля").classes("text-base font-semibold text-indigo-300 mb-4")
            with ui.grid(columns=3).classes("w-full gap-4 mb-6"):
                ctrl_options = ["зачет с оценкой", "экзамен", "зачет"]
                ctl_val_raw = str(context.get("control_form") or merged.get("course_type") or "зачет с оценкой").strip().lower()
                if "дифф" in ctl_val_raw or "оценк" in ctl_val_raw:
                    ctl_val = "зачет с оценкой"
                elif "экзамен" in ctl_val_raw:
                    ctl_val = "экзамен"
                elif "зачет" in ctl_val_raw:
                    ctl_val = "зачет"
                else:
                    ctl_val = ctl_val_raw
                if ctl_val not in ctrl_options:
                    ctrl_options.insert(0, ctl_val)

                in_control = ui.select(
                    options=ctrl_options,
                    label="Форма контроля",
                    value=ctl_val
                ).props("outlined dark color=indigo")

                in_proto_num = ui.input(
                    label="Номер протокола кафедры",
                    value=str(merged.get("protocol_num") or context.get("protocol_num") or "1")
                ).props("outlined dark color=indigo")

                in_proto_month = ui.input(
                    label="Месяц заседания кафедры",
                    value=str(merged.get("protocol_month") or context.get("protocol_month") or "августа")
                ).props("outlined dark color=indigo")

                in_proto_year = ui.input(
                    label="Год заседания кафедры",
                    value=str(merged.get("cathedra_meeting_year") or context.get("start_year") or "2026")
                ).props("outlined dark color=indigo")

                all_depts_list = get_all_departments()
                dept_val = str(project.get("department") or context.get("department") or merged.get("department") or "Кафедра экологии")
                if dept_val not in all_depts_list:
                    all_depts_list.insert(0, dept_val)

                in_dept = ui.select(
                    label="Кафедра создания РПД и ОМД",
                    options=all_depts_list,
                    value=dept_val,
                    with_input=True
                ).props("outlined dark color=indigo col-span-2")

            ui.separator().classes("my-5").style("border-color: rgba(99,102,241,0.2);")
            ui.label("Параметры генерации фонда вопросов").classes("text-base font-semibold text-indigo-300 mb-4")
            with ui.grid(columns=3).classes("w-full gap-4 mb-4"):
                in_sem_q = ui.number(
                    label="Вопросов на семинаре/практике",
                    value=int(merged.get("seminar_questions_number", 5)),
                    min=1, max=20
                ).props("outlined dark color=indigo")

                in_ctrl_q = ui.number(
                    label="Вопросов в контрольной работе",
                    value=int(merged.get("control_questions_number", 3)),
                    min=1, max=15
                ).props("outlined dark color=indigo")

                in_test_q = ui.number(
                    label="Вопросов к зачёту / экзамену",
                    value=int(merged.get("test_questions_number", 10)),
                    min=1, max=50
                ).props("outlined dark color=indigo")

            def collect_omd_params() -> dict:
                p = dict(merged)
                p["course_type"] = in_control.value
                p["protocol_num"] = in_proto_num.value.strip()
                p["protocol_month"] = in_proto_month.value.strip()
                p["cathedra_meeting_year"] = in_proto_year.value.strip()
                dept_str = in_dept.value.strip() if in_dept.value else ""
                p["department"] = dept_str
                inst_str = find_institute_for_department(dept_str) or ""
                p["institute"] = inst_str
                update_project_department(project_id, dept_str, inst_str)
                p["seminar_questions_number"] = str(int(in_sem_q.value or 5))
                p["control_questions_number"] = str(int(in_ctrl_q.value or 3))
                p["test_questions_number"] = str(int(in_test_q.value or 10))
                write_parameters_env(env_path, proj_name, p)
                update_project_files(project_id, parameters_path=str(env_path))
                return p

            async def do_generate_ai():
                params = collect_omd_params()
                await run_rpd_to_omd_bridge(project_id, user["username"], proj_name, params=params)
                app.storage.user[f"return_to_{project_id}"] = f"/project/{project_id}/variables"
                background_tasks.create(
                    run_questions_generation(project_id, user["username"], proj_name, params, regenerate=True)
                )
                ui.notify("Запущена генерация вопросов и оценочных средств (AI Gemini)...", type="info")
                ui.navigate.to(f"/project/{project_id}/processing")

            async def do_proceed_no_ai():
                params = collect_omd_params()
                await run_rpd_to_omd_bridge(project_id, user["username"], proj_name, params=params)
                ui.navigate.to(f"/project/{project_id}/variables")

            ui.separator().classes("my-6").style("border-color: rgba(99,102,241,0.2);")
            with ui.row().classes("w-full justify-between items-center gap-4"):
                ui.button(
                    "← Назад к финалу РПД (Шаг 4)",
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to(f"/project/{project_id}/rpd_final")
                ).props("flat").classes("text-gray-400")

                with ui.row().classes("gap-3 items-center"):
                    ui.button(
                        "Перейти к итогу ОМД без ИИ (Шаг 7) →",
                        on_click=do_proceed_no_ai
                    ).props("flat").classes("text-indigo-400")

                    if os.environ.get("GOOGLE_API_KEY"):
                        ui.button(
                            "⚡ Начать генерацию для ОМД (Шаг 6: ИИ) →",
                            icon="psychology",
                            on_click=do_generate_ai
                        ).classes("primary-btn").props("size=md")
                    else:
                        ui.button(
                            "Перейти к редактированию ОМД (Шаг 7) →",
                            icon="arrow_forward",
                            on_click=do_proceed_no_ai
                        ).classes("primary-btn").props("size=md")


# ── Step 8: Download / Final Summary ──────────────────────────────────────────

def _build_project_zip(project_name: str) -> str:
    res_dir = results_dir(project_name)
    proc_dir = processing_dir(project_name)
    res_dir.mkdir(parents=True, exist_ok=True)
    zip_path = res_dir / f"{project_name}_Комплект_РПД_ОМД.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in res_dir.glob("*.docx"):
            z.write(f, arcname=f"Документы/{f.name}")
        tp_dir = res_dir / "teach_plan"
        if tp_dir.exists():
            for f in tp_dir.glob("*.*"):
                z.write(f, arcname=f"Данные_учебного_плана/{f.name}")
        v_file = proc_dir / "variables.yml"
        if v_file.exists():
            z.write(v_file, arcname="Данные_учебного_плана/variables.yml")

    return str(zip_path)


@ui.page("/project/{project_id}/download")
async def download_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    status = project.get("status", "new")
    if status != "done" and not project.get("result_path") and not project.get("rpd_path"):
        _redirect_by_status(project_id, status)
        return

    proj_name = project["name"]
    res_dir = results_dir(proj_name)

    # Find RPD and OMD docx files
    rpd_path = project.get("rpd_path")
    if not rpd_path or not Path(rpd_path).exists():
        rpd_matches = [f for f in res_dir.glob("*.docx") if not f.name.startswith("~$") and ("рпд" in f.name.lower() or "rpd" in f.name.lower())]
        if rpd_matches:
            rpd_path = str(max(rpd_matches, key=lambda f: f.stat().st_mtime))
            update_project_files(project_id, rpd_path=rpd_path)
            update_project_meta(project_id, rpd_path=rpd_path)

    omd_path = project.get("result_path") or project.get("omd_path")
    if not omd_path or not Path(omd_path).exists():
        omd_matches = [f for f in res_dir.glob("*.docx") if not f.name.startswith("~$") and ("omd" in f.name.lower() or "омд" in f.name.lower())]
        if not omd_matches:
            omd_matches = [f for f in res_dir.glob("*.docx") if not f.name.startswith("~$") and "рпд" not in f.name.lower() and "rpd" not in f.name.lower()]
        if omd_matches:
            omd_path = str(max(omd_matches, key=lambda f: f.stat().st_mtime))
            update_project_files(project_id, omd_path=omd_path, result_path=omd_path)
            update_project_meta(project_id, omd_path=omd_path)

    with page_layout(f"Шаг 8: Комплект {project['name']}", user):
        _step_indicator(8, project)

        with ui.card().classes("app-card w-full items-center").style("padding: 36px 48px; text-align: center;"):
            ui.icon("check_circle", size="4.5rem").style("color: #10b981;")
            ui.label("Шаг 8: Комплект учебно-методической документации готов!").classes("text-2xl font-bold mt-3 mb-1 text-white")
            ui.label(
                "Рабочая программа дисциплины (РПД) и Оценочные материалы (ОМД) "
                "успешно сгенерированы и соответствуют всем академическим требованиям."
            ).classes("text-sm text-gray-400 mb-8")

            with ui.grid(columns=3).classes("w-full gap-6 mb-8 text-left"):
                # Card 1: RPD
                with ui.card().classes("bg-slate-900/60 border border-slate-700/50 p-5 rounded-xl flex flex-col justify-between"):
                    with ui.column().classes("gap-1"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("description", size="1.6rem").style("color: #10b981;")
                            ui.label("РПД (.docx)").classes("text-lg font-bold text-white")
                        ui.label("Рабочая программа с альбомной Таблицей 1 и 14 правилами верстки.").classes("text-xs text-gray-400 mb-4")
                    if rpd_path and Path(rpd_path).exists():
                        rfname = Path(rpd_path).name
                        ui.button(f"Скачать РПД", icon="download", on_click=lambda p=rpd_path, n=rfname: ui.download(p, filename=n)).classes("success-btn w-full")
                    else:
                        ui.button("Сформировать РПД (Шаг 4)", icon="edit", on_click=lambda: ui.navigate.to(f"/project/{project_id}/rpd_final")).props("flat").classes("w-full text-indigo-400")

                # Card 2: OMD
                with ui.card().classes("bg-slate-900/60 border border-slate-700/50 p-5 rounded-xl flex flex-col justify-between"):
                    with ui.column().classes("gap-1"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("menu_book", size="1.6rem").style("color: #6366f1;")
                            ui.label("ОМД (.docx)").classes("text-lg font-bold text-white")
                        ui.label("Оценочные материалы (ФОС) с вопросами и шкалами оценивания.").classes("text-xs text-gray-400 mb-4")
                    if omd_path and Path(omd_path).exists():
                        ofname = Path(omd_path).name
                        ui.button(f"Скачать ОМД", icon="download", on_click=lambda p=omd_path, n=ofname: ui.download(p, filename=n)).classes("primary-btn w-full")
                    else:
                        proc_dir = processing_dir(proj_name)
                        if (proc_dir / "variables.yml").exists():
                            ui.button("Скомпилировать ОМД (Шаг 7)", icon="rate_review", on_click=lambda: ui.navigate.to(f"/project/{project_id}/variables")).classes("primary-btn w-full")
                        else:
                            ui.button("Настроить ОМД (Шаг 5)", icon="tune", on_click=lambda: ui.navigate.to(f"/project/{project_id}/omd_parameters")).props("flat").classes("w-full text-indigo-400")

                # Card 3: Full ZIP Archive
                with ui.card().classes("bg-slate-900/60 border border-indigo-500/40 p-5 rounded-xl flex flex-col justify-between"):
                    with ui.column().classes("gap-1"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("archive", size="1.6rem").style("color: #8b5cf6;")
                            ui.label("Полный комплект (ZIP)").classes("text-lg font-bold text-white")
                        ui.label("Архив со всеми файлами (РПД, ОМД, teach_plan JSON и variables.yml).").classes("text-xs text-gray-400 mb-4")

                    def do_download_zip():
                        z_path = _build_project_zip(proj_name)
                        ui.download(z_path, filename=Path(z_path).name)

                    ui.button("Скачать ZIP-архив", icon="folder_zip", on_click=do_download_zip).props("outline color=purple size=md").classes("w-full")

            ui.separator().classes("my-6 w-full max-w-md").style("border-color: rgba(99,102,241,0.2);")

            with ui.row().classes("gap-4"):
                ui.button(
                    "← Переделать РПД (Шаг 4)", icon="edit_document", on_click=lambda: ui.navigate.to(f"/project/{project_id}/rpd_final")
                ).props("flat").classes("text-indigo-400")
                ui.button(
                    "← Переделать ОМД (Шаг 7)", icon="rate_review", on_click=lambda: ui.navigate.to(f"/project/{project_id}/variables")
                ).props("flat").classes("text-indigo-400")
                ui.button(
                    "К списку проектов", icon="folder", on_click=lambda: ui.navigate.to("/dashboard")
                ).props("flat").classes("text-gray-400")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _redirect_by_status(project_id: int, status: str):
    routes = {
        "new":                  f"/project/{project_id}/parameters",
        "plan_uploaded":        f"/project/{project_id}/rpd",
        "rpd_wizard":           f"/project/{project_id}/rpd",
        "generating_rpd":       f"/project/{project_id}/rpd",
        "generating_rpd_content": f"/project/{project_id}/processing",
        "rpd_ready":            f"/project/{project_id}/rpd_final",
        "error":                f"/project/{project_id}/parameters",
        "processing_structure": f"/project/{project_id}/processing",
        "generating_questions": f"/project/{project_id}/processing",
        "generating_docx":      f"/project/{project_id}/processing",
        "variables":            f"/project/{project_id}/variables",
        "questions":            f"/project/{project_id}/variables",
        "done":                 f"/project/{project_id}/download",
    }
    ui.navigate.to(routes.get(status, "/dashboard"))



