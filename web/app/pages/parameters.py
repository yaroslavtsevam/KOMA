"""
parameters.py – Step 1: Edit processing parameters (/project/{id}/parameters)
              + Step: Processing status page (/project/{id}/processing)
              + Step: Download page (/project/{id}/download)
"""

import asyncio
from pathlib import Path
from nicegui import ui, background_tasks
from ..db import get_project, update_project_status, update_project_files, processing_dir
from ..auth import current_user, require_login
from ..pipeline import (
    load_env_defaults,
    read_parameters_env,
    write_parameters_env,
    run_extraction,
    generate_docx,
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


# ── Parameters editor ────────────────────────────────────────────────────────

@ui.page("/project/{project_id}/parameters")
async def parameters_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not _assert_owner(project, user):
        ui.navigate.to("/dashboard")
        return

    # Redirect if already past this step
    status = project.get("status", "new")
    if status in ("processing_structure", "generating_questions", "generating_docx"):
        ui.navigate.to(f"/project/{project_id}/processing")
        return

    # Load defaults + existing params
    defaults = load_env_defaults()
    proc_dir = processing_dir(project["name"])
    env_path = proc_dir / "parameters.env"
    existing = read_parameters_env(env_path)
    merged = {k: existing.get(k, v) for k, v in defaults.items()}

    with page_layout(f"Параметры: {project['name']}", user):
        # ── Step indicator ────────────────────────────────────────────────────
        _step_indicator(1, project)

        with ui.card().classes("app-card w-full").style("padding: 32px;"):
            ui.label("Настройка параметров обработки").classes("text-lg font-semibold text-indigo-300 mb-2")
            ui.label(
                "Параметры берутся из .env.default. Измените значения при необходимости. "
                "После сохранения запустится обработка РПД."
            ).classes("text-sm text-gray-500 mb-6")

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

            with ui.row().classes("gap-3 items-center mb-4"):
                ui.icon("info_outline", size="1rem").style("color: #6366f1;")
                ui.label(
                    "После нажатия «Запустить» AI-агент обработает РПД "
                    "и извлечет его структуру. Это займёт несколько минут."
                ).classes("text-sm text-gray-400 flex-1")

            # Check if variables.yml already exists
            variables_path = proc_dir / "variables.yml"
            has_variables = variables_path.exists()

            redo_cb = None
            if has_variables:
                with ui.row().classes("w-full items-center gap-2 mb-4"):
                    redo_cb = ui.checkbox("Запустить AI-обработку заново (сотрет все прошлые ручные правки)").props("dark color=red")

            ui.separator().classes("my-4").style("border-color: rgba(99,102,241,0.1);")

            async def do_start():
                params = {k: inp.value.strip() for k, inp in inputs.items()}
                # Save parameters.env
                env_path.parent.mkdir(parents=True, exist_ok=True)
                write_parameters_env(env_path, project["name"], params)
                update_project_files(project_id, parameters_path=str(env_path))

                should_redo = redo_cb.value if redo_cb else False
                if has_variables and not should_redo:
                    update_project_status(project_id, "variables")
                    update_project_files(project_id, variables_path=str(variables_path))
                    ui.navigate.to(f"/project/{project_id}/variables")
                else:
                    # Launch background extraction pipeline with force regenerate
                    syllabus = project.get("syllabus_path") or ""
                    background_tasks.create(
                        run_extraction(project_id, user["username"], project["name"], syllabus, params, regenerate=True)
                    )
                    ui.navigate.to(f"/project/{project_id}/processing")

            with ui.row().classes("gap-4 items-center"):
                ui.button(
                    "Запустить обработку →", icon="rocket_launch", on_click=do_start
                ).classes("primary-btn").props("size=lg")

                if has_variables:
                    ui.button(
                        "Назад к переменным", icon="chevron_right", on_click=lambda: ui.navigate.to(f"/project/{project_id}/variables")
                    ).props("flat").classes("text-indigo-400")


# ── Processing / generating status ───────────────────────────────────────────

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
    if status not in ("processing_structure", "generating_questions", "generating_docx"):
        _redirect_by_status(project_id, status)
        return

    if status == "processing_structure":
        title = "Сбор структуры РПД..."
        desc = "Идёт извлечение структуры РПД и таблиц с помощью AI…"
        active_step = 2
    elif status == "generating_questions":
        title = "Генерация вопросов..."
        desc = "Идёт генерация вопросов к лекциям/семинарам и оценочных средств…"
        active_step = 4
    else:
        title = "Генерация документа..."
        desc = "Формирование документа Word по шаблону…"
        active_step = 6

    with page_layout(title, user):
        _step_indicator(active_step, project)

        with ui.column().classes("w-full gap-6 items-stretch"):
            # First Row: Status details
            with ui.card().classes("app-card items-center justify-center p-8 w-full text-center"):
                ui.spinner(size="4rem").style("color: #6366f1;")
                ui.label(title).classes("text-lg font-semibold mt-6 mb-2 text-white")
                ui.label(desc).classes("text-sm text-gray-500 mb-6")

                status_label = ui.label("Статус: обработка...").classes("text-sm text-indigo-300")

                with ui.expansion("Подсказка").classes("w-full mt-4 text-left"):
                    ui.label(
                        "Обработка выполняется в фоновом режиме. Вы можете отслеживать "
                        "терминальный вывод и ход выполнения в консоли ниже."
                    ).classes("text-xs text-gray-500")

            # Second Row: Collapsible Live log console
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
                # 1. Read new lines from log file
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
                if s == "variables" or s == "questions":
                    if timer:
                        timer.cancel()
                    ui.navigate.to(f"/project/{project_id}/variables")
                elif s == "done":
                    if timer:
                        timer.cancel()
                    ui.navigate.to(f"/project/{project_id}/download")
                elif s == "error":
                    if timer:
                        timer.cancel()
                    ui.navigate.to(f"/project/{project_id}/parameters")
            except Exception:
                if timer:
                    timer.cancel()

        timer = ui.timer(2.0, poll)


# ── Download page ─────────────────────────────────────────────────────────────

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
    if status != "done":
        _redirect_by_status(project_id, status)
        return

    result_path = project.get("result_path") or ""

    with page_layout(f"Готово: {project['name']}", user):
        _step_indicator(7, project)

        with ui.card().classes("app-card w-full items-center").style("padding: 48px; text-align: center;"):
            ui.icon("check_circle", size="5rem").style("color: #10b981;")
            ui.label("Документ сформирован!").classes("text-2xl font-bold mt-4 mb-2")
            ui.label("Нажмите кнопку ниже, чтобы скачать результирующий файл .docx").classes(
                "text-sm text-gray-400 mb-8"
            )

            if result_path and Path(result_path).exists():
                filename = Path(result_path).name

                def do_download():
                    ui.download(result_path, filename=filename)

                ui.button(
                    f"Скачать {filename}", icon="download", on_click=do_download
                ).classes("success-btn").props("size=lg")
            else:
                ui.label("Файл не найден на сервере.").classes("text-red-400")

            ui.separator().classes("my-8 w-full max-w-sm").style("border-color: rgba(99,102,241,0.2);")

            with ui.row().classes("gap-3"):
                ui.button(
                    "Вернуться к форме переменных", icon="edit", on_click=lambda: ui.navigate.to(f"/project/{project_id}/variables")
                ).props("flat").classes("text-indigo-400")
                ui.button(
                    "К списку проектов", icon="folder", on_click=lambda: ui.navigate.to("/dashboard")
                ).props("flat").classes("text-gray-400")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _redirect_by_status(project_id: int, status: str):
    routes = {
        "new":                  f"/project/{project_id}/parameters",
        "error":                f"/project/{project_id}/parameters",
        "processing_structure": f"/project/{project_id}/processing",
        "generating_questions": f"/project/{project_id}/processing",
        "generating_docx":      f"/project/{project_id}/processing",
        "variables":            f"/project/{project_id}/variables",
        "questions":            f"/project/{project_id}/variables",
        "done":                 f"/project/{project_id}/download",
    }
    ui.navigate.to(routes.get(status, "/dashboard"))

