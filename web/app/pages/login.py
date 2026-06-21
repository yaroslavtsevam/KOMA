"""
login.py – Login page (/login and /)
"""

from nicegui import ui, app
from ..db import authenticate
from ..auth import login_user, current_user


def _common_head():
    ui.add_head_html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
      * { box-sizing: border-box; }
      body, input, textarea, select, button, label, p, div:not(.q-icon),
      span:not(.material-icons):not(.material-icons-outlined) {
        font-family: 'Inter', sans-serif;
      }
      .material-icons, .material-icons-outlined, .q-icon {
        font-family: 'Material Icons', 'Material Icons Outlined' !important;
      }
      body { background: linear-gradient(135deg, #0a0e1a 0%, #0f1827 60%, #0a1020 100%) !important;
             min-height: 100vh; }
      .login-card {
        background: rgba(17,24,39,0.85);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(99,102,241,0.25);
        border-radius: 16px;
        box-shadow: 0 25px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,102,241,0.1);
      }
      .logo-gradient {
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
      }
      .q-btn.primary-btn {
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px;
        transition: all 0.2s ease !important;
      }
      .q-btn.primary-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 24px rgba(99,102,241,0.4) !important; }
      .q-field .q-field__control { border-radius: 10px !important; background: rgba(255,255,255,0.05) !important; }
      .q-field.q-field--focused .q-field__control { border-color: #6366f1 !important; }
    </style>
    """)


@ui.page("/")
async def root():
    if current_user():
        ui.navigate.to("/dashboard")
    else:
        ui.navigate.to("/login")


@ui.page("/login")
async def login_page():
    _common_head()

    if current_user():
        ui.navigate.to("/dashboard")
        return

    with ui.column().classes("items-center justify-center w-full").style("min-height:100vh; padding: 24px;"):
        with ui.card().classes("login-card").style("width:100%; max-width:420px; padding: 40px;"):

            # Logo / title
            with ui.column().classes("items-center gap-2 mb-8"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("school", size="2.5rem").style("color: #6366f1;")
                    ui.label("КОМА").classes("text-3xl font-bold logo-gradient")
                ui.label("Комплексный Оптимизатор Методических Актов").classes(
                    "text-sm text-gray-400 text-center"
                )

            username_input = (
                ui.input(label="Имя пользователя", placeholder="admin")
                .props("outlined dark color=indigo")
                .classes("w-full mb-3")
            )
            password_input = (
                ui.input(label="Пароль", password=True, password_toggle_button=True)
                .props("outlined dark color=indigo")
                .classes("w-full mb-5")
            )
            error_label = ui.label("").classes("text-red-400 text-sm mb-2").style("display:none")

            def do_login():
                username = username_input.value.strip()
                password = password_input.value
                if not username or not password:
                    error_label.text = "Введите имя пользователя и пароль"
                    error_label.style("display:block")
                    return
                user = authenticate(username, password)
                if user:
                    login_user(user)
                    ui.navigate.to("/dashboard")
                else:
                    error_label.text = "Неверное имя пользователя или пароль"
                    error_label.style("display:block")
                    password_input.value = ""

            password_input.on("keydown.enter", do_login)
            (
                ui.button("Войти", on_click=do_login)
                .classes("w-full primary-btn")
                .props("size=lg")
            )

            ui.label("По умолчанию: admin / admin").classes(
                "text-gray-500 text-xs text-center mt-4"
            )
