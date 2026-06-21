"""
auth.py – Session helpers built on top of NiceGUI's app.storage.user.
"""

from nicegui import app, ui


def current_user() -> dict | None:
    """Return the session dict for the logged-in user, or None."""
    u = app.storage.user
    if u.get("logged_in") and u.get("username"):
        return dict(u)
    return None


def login_user(user_row: dict) -> None:
    """Persist a user row into the session storage."""
    app.storage.user.update(
        logged_in=True,
        user_id=user_row["id"],
        username=user_row["username"],
        is_admin=bool(user_row["is_admin"]),
    )


def logout_user() -> None:
    app.storage.user.clear()


def require_login() -> bool:
    """Redirect to /login if not authenticated. Returns True if OK."""
    if not current_user():
        ui.navigate.to("/login")
        return False
    return True


def require_admin() -> bool:
    """Redirect away if not admin. Returns True if OK."""
    if not require_login():
        return False
    if not app.storage.user.get("is_admin"):
        ui.navigate.to("/dashboard")
        return False
    return True
