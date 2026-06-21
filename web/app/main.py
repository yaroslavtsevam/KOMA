"""
main.py – NiceGUI application entrypoint.

All pages are registered by importing their modules here.
The app is started with `python -m app.main` from the Docker WORKDIR (/app).
"""

import os
import logging
from nicegui import app, ui

# ── Bootstrap database ────────────────────────────────────────────────────────
from .db import init_db

@app.on_startup
async def startup():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    init_db()
    logging.getLogger("startup").info("Database initialised. Application ready.")


# ── Register all pages by importing them ──────────────────────────────────────
# Each module uses @ui.page decorators to register its routes.
from .pages import login          # noqa: F401  /  /login
from .pages import dashboard      # noqa: F401  /dashboard
from .pages import admin          # noqa: F401  /admin
from .pages import parameters     # noqa: F401  /project/{id}/parameters
                                  #             /project/{id}/processing
                                  #             /project/{id}/download
from .pages import variables_form  # noqa: F401 /project/{id}/variables


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ in {"__main__", "__mp_main__", "app.main"}:
    ui.run(
        title="КОМА — Комплексный Оптимизатор Методических Актов",
        host="0.0.0.0",
        port=8080,
        dark=True,
        storage_secret=os.environ.get("STORAGE_SECRET", "timplan-default-secret"),
        favicon="📚",
        # Reload is off in production; dev can set RELOAD=true externally
        reload=os.environ.get("NICEGUI_RELOAD", "false").lower() == "true",
    )
