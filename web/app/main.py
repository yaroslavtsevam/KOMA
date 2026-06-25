"""
main.py – NiceGUI application entrypoint.

All pages are registered by importing their modules here.
The app is started with `python -m app.main` from the Docker WORKDIR (/app).
"""

import os
import logging
from nicegui import app, ui
from starlette.formparsers import MultiPartParser
from starlette.requests import ClientDisconnect
from fastapi import Request
from fastapi.responses import Response

# Set spool max size to 50MB to buffer uploads in memory.
# This prevents slow disk I/O from blocking the asyncio event loop
# in WSL2/Docker environments, which causes WebSocket timeouts and ClientDisconnects.
MultiPartParser.spool_max_size = 50 * 1024 * 1024

@app.exception_handler(ClientDisconnect)
async def client_disconnect_handler(request: Request, exc: ClientDisconnect):
    # Quietly handle ClientDisconnect when the browser closes/aborts the upload request
    # after receiving the response or on page navigation.
    return Response(status_code=204)

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
