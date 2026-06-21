"""
shared.py – Common page layout (header + sidebar) used by all inner pages.
"""

from contextlib import contextmanager
from nicegui import ui
from ..auth import logout_user, current_user


_GLOBAL_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body, input, textarea, select, button, label, p, h1, h2, h3, h4, h5, h6, span:not(.material-icons):not(.material-icons-outlined):not(.material-icons-round), div:not(.q-icon) {
    font-family: 'Inter', sans-serif;
  }
  /* Restore Quasar/Material icon fonts that the wildcard selector would otherwise clobber */
  .material-icons,
  .material-icons-outlined,
  .material-icons-round,
  .material-icons-sharp,
  .q-icon {
    font-family: 'Material Icons', 'Material Icons Outlined', 'Material Icons Round' !important;
  }

  body {
    background: linear-gradient(135deg, #0a0e1a 0%, #0f1827 60%, #0a1020 100%) !important;
    min-height: 100vh;
  }

  /* Cards */
  .app-card {
    background: rgba(17,24,39,0.85) !important;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(99,102,241,0.2) !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3) !important;
  }

  /* Primary buttons */
  .primary-btn {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
  }
  .primary-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 24px rgba(99,102,241,0.4) !important;
  }

  /* Success button */
  .success-btn {
    background: linear-gradient(135deg, #10b981, #059669) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
  }

  /* Inputs */
  .q-field .q-field__control { border-radius: 10px !important; background: rgba(255,255,255,0.04) !important; }
  .q-field.q-field--focused .q-field__control { border-color: #6366f1 !important; }
  .q-field--outlined .q-field__control { border-color: rgba(99,102,241,0.3) !important; }

  /* Sidebar nav item */
  .nav-item { border-radius: 10px; transition: all 0.15s ease; cursor: pointer; padding: 10px 14px; }
  .nav-item:hover { background: rgba(99,102,241,0.15); }
  .nav-item.active { background: rgba(99,102,241,0.25); border-left: 3px solid #6366f1; }

  /* User row in admin */
  .user-row { border-bottom: 1px solid rgba(255,255,255,0.05); }
  .user-row:last-child { border-bottom: none; }

  /* Status badges */
  .badge { border-radius: 20px; padding: 2px 10px; font-size: 0.78rem; font-weight: 600; }
  .badge-new      { background: rgba(156,163,175,0.2); color: #9ca3af; }
  .badge-processing { background: rgba(251,191,36,0.2); color: #fbbf24; }
  .badge-generating { background: rgba(251,191,36,0.2); color: #fbbf24; }
  .badge-variables  { background: rgba(99,102,241,0.2); color: #818cf8; }
  .badge-done     { background: rgba(16,185,129,0.2); color: #10b981; }
  .badge-error    { background: rgba(239,68,68,0.2);  color: #ef4444; }

  /* Logo gradient */
  .logo-gradient {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  /* Expansion panel overrides */
  .q-expansion-item .q-expansion-item__container {
    background: rgba(255,255,255,0.02) !important;
    border: 1px solid rgba(99,102,241,0.15);
    border-radius: 10px;
    margin-bottom: 8px;
  }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); }
  ::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.4); border-radius: 4px; }
</style>
"""


STATUS_LABELS = {
    "new":                  "Новый",
    "processing_structure": "Сбор структуры...",
    "variables":            "Проверка структуры",
    "generating_questions": "Генерация вопросов...",
    "questions":            "Проверка вопросов",
    "generating_docx":      "Генерация Word...",
    "done":                 "Готов",
    "error":                "Ошибка",
}


@contextmanager
def page_layout(title: str, user: dict):
    """
    Context manager that renders the app shell (sidebar + header) and
    yields inside the main content column.
    """
    ui.add_head_html(_GLOBAL_CSS)

    with ui.row().classes("w-full").style("min-height: 100vh; gap: 0;"):
        # ── Sidebar ──────────────────────────────────────────────────────────
        with ui.column().style(
            "width: 220px; min-height: 100vh; padding: 24px 16px; "
            "background: rgba(10,14,26,0.7); backdrop-filter: blur(8px); "
            "border-right: 1px solid rgba(99,102,241,0.15); flex-shrink: 0;"
        ):
            with ui.row().classes("items-center gap-2 mb-8 px-2"):
                ui.icon("school", size="1.6rem").style("color:#6366f1;")
                ui.label("Комплексный Оптимизатор Методических Актов").classes("text-xl font-bold logo-gradient")

            with ui.column().classes("gap-1 w-full"):
                ui.label("НАВИГАЦИЯ").classes("text-xs text-gray-600 font-semibold px-2 mb-1")

                def nav(label, icon, route, active=False):
                    cls = "nav-item w-full flex items-center gap-3"
                    if active:
                        cls += " active"
                    with ui.row().classes(cls).on("click", lambda _, r=route: ui.navigate.to(r)):
                        ui.icon(icon, size="1.1rem").style("color: #818cf8;")
                        ui.label(label).classes("text-sm text-gray-200")

                nav("Мои проекты", "folder", "/dashboard")
                if user.get("is_admin"):
                    nav("Пользователи", "people", "/admin")

            # Spacer
            ui.space()

            # Bottom: user info + logout
            with ui.column().classes("gap-2 w-full mt-4"):
                ui.separator().style("border-color: rgba(99,102,241,0.2);")
                with ui.row().classes("items-center gap-2 px-2 py-2"):
                    ui.icon("account_circle", size="1.2rem").style("color:#6366f1;")
                    ui.label(user.get("username", "")).classes("text-sm text-gray-300 flex-1")
                with ui.row().classes("w-full"):
                    def do_logout():
                        logout_user()
                        ui.navigate.to("/login")
                    ui.button("Выйти", icon="logout", on_click=do_logout).props(
                        "flat size=sm"
                    ).classes("w-full text-gray-400")

        # ── Main content ─────────────────────────────────────────────────────
        with ui.column().classes("flex-1 p-8 gap-0").style("min-width: 0; overflow: auto;"):
            # Page title
            ui.label(title).classes("text-2xl font-bold text-white mb-6")
            yield


def _step_indicator(active: int, project: dict):
    from pathlib import Path
    project_id = project["id"]
    status = project.get("status", "new")

    # Check accessibility for each step
    is_running = status in ("processing_structure", "generating_questions", "generating_docx")

    step1_avail = not is_running
    step2_avail = status != "new" and not is_running

    variables_path = project.get("variables_path")
    step3_avail = bool(variables_path and Path(variables_path).exists() and not is_running)

    step4_avail = status in ("generating_questions", "questions", "generating_docx", "done")
    step5_avail = bool(variables_path and Path(variables_path).exists() and status in ("questions", "generating_docx", "done") and not is_running)
    step6_avail = status in ("generating_docx", "done")
    step7_avail = bool(project.get("result_path") and Path(project["result_path"]).exists() and status == "done")

    steps = [
        (1, "Параметры", "settings", f"/project/{project_id}/parameters", step1_avail),
        (2, "Структура AI", "auto_awesome", f"/project/{project_id}/processing", step2_avail),
        (3, "Проверка структуры", "edit_note", f"/project/{project_id}/variables", step3_avail),
        (4, "Вопросы AI", "psychology", f"/project/{project_id}/processing", step4_avail),
        (5, "Проверка вопросов", "rate_review", f"/project/{project_id}/variables", step5_avail),
        (6, "Генерация Word", "build", f"/project/{project_id}/processing", step6_avail),
        (7, "Готово", "download", f"/project/{project_id}/download", step7_avail),
    ]

    with ui.row().classes("w-full gap-0 mb-8 items-center"):
        for i, (num, label, icon, route, avail) in enumerate(steps):
            is_active = num == active
            is_done = num < active

            # Colors
            if is_done:
                color = "#10b981"  # Green for completed
            elif is_active:
                color = "#6366f1"  # Indigo for active
            else:
                color = "rgba(255,255,255,0.15)"  # Gray for future

            if is_done:
                text_color = "#10b981"
            elif is_active:
                text_color = "#c4b5fd"
            elif avail:
                text_color = "#9ca3af"  # readable gray for available steps
            else:
                text_color = "#4b5563"  # dark gray for disabled

            with ui.column().classes("items-center gap-1").style("flex: 1; position: relative;"):
                # Make interactive if available and not currently active
                circle_classes = "items-center justify-center transition-all"
                if avail and not is_active:
                    circle_classes += " cursor-pointer hover:scale-110"

                circle_style = f"width: 36px; height: 36px; border-radius: 50%; background: {color}; margin: 0 auto; display: flex;"

                circle = ui.row().classes(circle_classes).style(circle_style)
                with circle:
                    if is_done:
                        ui.icon("check", size="1rem").style("color: white;")
                    else:
                        ui.icon(icon, size="1rem").style(f"color: {'white' if is_active else '#6b7280'};")

                # Navigation event
                if avail and not is_active:
                    circle.on("click", lambda _, r=route: ui.navigate.to(r))

                ui.label(label).classes("text-xs font-medium").style(f"color: {text_color};")

            if i < len(steps) - 1:
                line_color = "#10b981" if num < active else "rgba(255,255,255,0.1)"
                ui.separator().style(
                    f"flex: 2; height: 2px; background: {line_color}; "
                    f"margin-top: -20px; border: none; align-self: flex-start;"
                )

