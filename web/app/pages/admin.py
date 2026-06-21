"""
admin.py – Admin panel for user management (/admin)
"""

from nicegui import ui, app
from ..db import list_users, create_user, delete_user, change_password
from ..auth import current_user, require_admin, logout_user
from .shared import page_layout


@ui.page("/admin")
async def admin_page():
    if not require_admin():
        return

    user = current_user()

    def refresh():
        ui.navigate.to("/admin")

    with page_layout("Управление пользователями", user):
        with ui.column().classes("w-full gap-6"):

            # ── Create user form ─────────────────────────────────────────────
            with ui.card().classes("app-card w-full"):
                ui.label("Создать пользователя").classes("text-lg font-semibold text-indigo-300 mb-4")
                with ui.row().classes("w-full gap-3 flex-wrap items-end"):
                    new_username = (
                        ui.input(label="Имя пользователя")
                        .props("outlined dark color=indigo")
                        .classes("flex-1 min-w-48")
                    )
                    new_password = (
                        ui.input(label="Пароль", password=True, password_toggle_button=True)
                        .props("outlined dark color=indigo")
                        .classes("flex-1 min-w-48")
                    )
                    is_admin_cb = ui.checkbox("Администратор").props("dark color=indigo")

                    def do_create():
                        uname = new_username.value.strip()
                        pwd = new_password.value.strip()
                        if not uname or not pwd:
                            ui.notify("Заполните все поля", type="warning")
                            return
                        if len(uname) < 3:
                            ui.notify("Имя пользователя должно быть не менее 3 символов", type="warning")
                            return
                        ok = create_user(uname, pwd, is_admin_cb.value)
                        if ok:
                            ui.notify(f"Пользователь «{uname}» создан", type="positive")
                            new_username.value = ""
                            new_password.value = ""
                            is_admin_cb.value = False
                            refresh()
                        else:
                            ui.notify(f"Пользователь «{uname}» уже существует", type="negative")

                    ui.button("Создать", icon="person_add", on_click=do_create).classes("primary-btn")

            # ── Users table ──────────────────────────────────────────────────
            with ui.card().classes("app-card w-full"):
                ui.label("Список пользователей").classes("text-lg font-semibold text-indigo-300 mb-4")
                users = list_users()

                with ui.column().classes("w-full gap-2"):
                    # Header
                    with ui.row().classes("w-full px-4 py-2").style(
                        "background: rgba(99,102,241,0.1); border-radius: 8px;"
                    ):
                        ui.label("Имя пользователя").classes("flex-1 text-sm font-semibold text-gray-300")
                        ui.label("Роль").classes("w-28 text-sm font-semibold text-gray-300")
                        ui.label("Создан").classes("w-40 text-sm font-semibold text-gray-300")
                        ui.label("Действия").classes("w-32 text-sm font-semibold text-gray-300")

                    for u in users:
                        is_self = u["username"] == user["username"]
                        with ui.row().classes("w-full px-4 py-3 items-center user-row"):
                            ui.label(u["username"]).classes("flex-1 font-medium")
                            role_label = "Администратор" if u["is_admin"] else "Пользователь"
                            role_color = "text-indigo-400" if u["is_admin"] else "text-gray-400"
                            ui.label(role_label).classes(f"w-28 text-sm {role_color}")
                            ui.label(u["created_at"][:10] if u["created_at"] else "—").classes(
                                "w-40 text-sm text-gray-500"
                            )
                            with ui.row().classes("w-32 gap-1"):
                                # Change password dialog
                                with ui.dialog() as pwd_dialog, ui.card().classes("app-card").style("min-width:320px"):
                                    ui.label(f"Смена пароля: {u['username']}").classes(
                                        "text-base font-semibold mb-4"
                                    )
                                    new_pwd = (
                                        ui.input("Новый пароль", password=True, password_toggle_button=True)
                                        .props("outlined dark color=indigo")
                                        .classes("w-full mb-4")
                                    )
                                    with ui.row().classes("gap-2 justify-end"):
                                        ui.button("Отмена", on_click=pwd_dialog.close).props("flat")
                                        def do_change_pwd(uid=u["id"], dlg=pwd_dialog, inp=new_pwd):
                                            if inp.value.strip():
                                                change_password(uid, inp.value.strip())
                                                ui.notify("Пароль изменён", type="positive")
                                                dlg.close()
                                            else:
                                                ui.notify("Введите пароль", type="warning")
                                        ui.button("Сохранить", on_click=do_change_pwd).classes("primary-btn")

                                ui.button(
                                    icon="lock", on_click=pwd_dialog.open
                                ).props("flat round size=sm").tooltip("Сменить пароль")

                                if not is_self:
                                    def do_delete(uid=u["id"], uname=u["username"]):
                                        delete_user(uid)
                                        ui.notify(f"Пользователь «{uname}» удалён", type="positive")
                                        refresh()

                                    ui.button(
                                        icon="delete", on_click=do_delete
                                    ).props("flat round size=sm color=red").tooltip("Удалить пользователя")
                                else:
                                    ui.label("(Вы)").classes("text-xs text-gray-500 mt-1")
