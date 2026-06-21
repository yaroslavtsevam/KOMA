"""
dashboard.py – Project list + new-project dialog (/dashboard)

Projects use the same directory layout as the CLI:
  input/<project_name>/          ← uploaded PDF
  processing/<project_name>/     ← parameters.env, variables.yml, etc.
  results/<project_name>/        ← generated docx
"""

import os
import shutil
import logging
from pathlib import Path
from nicegui import ui, events
from ..db import (
    get_user_projects, create_project, update_project_files,
    input_dir, processing_dir, results_dir,
)
from ..auth import current_user, require_login
from .shared import page_layout, STATUS_LABELS

logger = logging.getLogger("dashboard")

STATUS_STEP = {
    "new":                  "/parameters",
    "processing_structure": "/processing",
    "variables":            "/variables",
    "generating_questions": "/processing",
    "questions":            "/variables",
    "generating_docx":      "/processing",
    "done":                 "/download",
    "error":                "/parameters",
}


@ui.page("/dashboard")
async def dashboard_page():
    if not require_login():
        return

    user = current_user()
    projects = get_user_projects(user["user_id"])

    with page_layout("Мои проекты", user):
        # ── New project button ────────────────────────────────────────────────
        with ui.row().classes("w-full justify-end mb-2"):
            with ui.dialog() as new_dlg, ui.card().classes("app-card").style(
                "min-width: 500px; padding: 32px;"
            ):
                ui.label("Новый проект").classes("text-xl font-bold mb-6")

                proj_name = (
                    ui.input(
                        label="Название проекта",
                        placeholder="Например: FTD.01_R_RPD_2024",
                    )
                    .props("outlined dark color=indigo")
                    .classes("w-full mb-5")
                )

                ui.label("РПД (PDF файл)").classes("text-sm text-gray-400 mb-1")

                upload_state: dict = {"tmp_path": None, "filename": None}

                # ── Upload handler (NiceGUI 3.x: e.file.save) ────────────────
                async def handle_upload(e: events.UploadEventArguments):
                    try:
                        f = e.file
                        filename = getattr(f, "name", None) or getattr(f, "filename", None)
                        if not filename:
                            logger.error("No filename on upload event. dir(e.file)=%s", dir(f))
                            ui.notify("Ошибка: имя файла не определено", type="negative")
                            return

                        # Save to a temp location; will be moved on project creation
                        tmp_dir = Path(os.environ.get("DATA_DIR", "/app/data")) / "tmp_uploads"
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        dest = tmp_dir / filename

                        if hasattr(f, "save"):
                            await f.save(str(dest))
                        else:
                            content = await f.read()
                            with open(str(dest), "wb") as fout:
                                fout.write(content)

                        upload_state["tmp_path"] = str(dest)
                        upload_state["filename"] = filename
                        upload_label.set_text(f"✓  {filename}")
                        upload_label.style("color: #10b981; font-weight: 600;")
                        ui.notify(f"Файл «{filename}» загружен", type="positive")
                        logger.info("Upload saved: %s", dest)

                    except Exception as exc:
                        logger.exception("Upload handler failed")
                        ui.notify(f"Ошибка загрузки: {exc}", type="negative")

                ui.upload(
                    label="Выбрать PDF файл",
                    auto_upload=True,
                    on_upload=handle_upload,
                    max_file_size=100_000_000,
                ).props("accept=.pdf flat color=indigo dark").classes("w-full")

                upload_label = ui.label("Файл не выбран").classes(
                    "text-xs text-gray-500 mt-1 mb-5"
                )

                with ui.row().classes("gap-3 justify-end w-full"):
                    ui.button("Отмена", on_click=new_dlg.close).props("flat")

                    def do_create():
                        name = proj_name.value.strip()
                        if not name:
                            ui.notify("Введите название проекта", type="warning")
                            return
                        if not upload_state["tmp_path"]:
                            ui.notify(
                                "Загрузите PDF файл РПД перед созданием проекта",
                                type="warning",
                            )
                            return

                        safe_name = "".join(
                            c if c.isalnum() or c in "-_." else "_" for c in name
                        )

                        # Create directories matching CLI layout:
                        #   input/<safe_name>/   — PDF goes here
                        #   processing/<safe_name>/  — will hold parameters.env, variables.yml
                        inp = input_dir(safe_name)
                        proc = processing_dir(safe_name)
                        results_dir(safe_name)  # ensure exists

                        dest = inp / upload_state["filename"]
                        shutil.move(upload_state["tmp_path"], str(dest))
                        upload_state["tmp_path"] = None

                        pid = create_project(user["user_id"], safe_name)
                        update_project_files(pid, syllabus_path=str(dest))

                        logger.info(
                            "Project '%s' created: input=%s, processing=%s",
                            safe_name, inp, proc,
                        )

                        new_dlg.close()
                        ui.navigate.to(f"/project/{pid}/parameters")

                    ui.button(
                        "Создать и настроить →", on_click=do_create
                    ).classes("primary-btn")

            ui.button("+ Новый проект", on_click=new_dlg.open).classes("primary-btn")

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
                    step_route = STATUS_STEP.get(status, "/parameters")

                    with ui.card().classes(
                        "app-card w-full cursor-pointer project-card"
                    ).style("padding: 20px 24px;").on(
                        "click",
                        lambda _, pid=p["id"], r=step_route: ui.navigate.to(
                            f"/project/{pid}{r}"
                        ),
                    ):
                        with ui.row().classes("w-full items-center gap-4"):
                            ui.icon("description", size="1.8rem").style(
                                "color: #6366f1;"
                            )
                            with ui.column().classes("flex-1 gap-1"):
                                ui.label(p["name"]).classes(
                                    "text-base font-semibold text-white"
                                )
                                ui.label(
                                    f"Создан: {p['created_at'][:10] if p['created_at'] else '—'}"
                                ).classes("text-xs text-gray-500")
                            ui.label(STATUS_LABELS.get(status, status)).classes(
                                badge_cls
                            )
                            if status == "error":
                                ui.icon("error_outline", size="1.2rem").style(
                                    "color: #ef4444;"
                                ).tooltip(p.get("error_message", ""))
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
