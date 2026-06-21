"""
pipeline.py – Simplified async wrappers that execute the root CLI commands
in the background and update the SQLite project status.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from .db import (
    get_project,
    update_project_status,
    update_project_files,
    input_dir,
    processing_dir,
    results_dir,
)

logger = logging.getLogger("pipeline")

# Locate PROJECT_ROOT dynamically by searching upward for main.py
def _find_project_root() -> Path:
    curr = Path(__file__).resolve().parent
    for _ in range(5):
        if (curr / "main.py").exists() and not (curr / "db.py").exists():
            return curr
        curr = curr.parent
    return Path("/app")

_PROJECT_ROOT = _find_project_root()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _env_default_path() -> Path:
    candidates = [
        Path("/app/.env.default"),
        _PROJECT_ROOT / ".env.default",
        Path(".env.default"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(".env.default not found")


def _template_path() -> Path:
    candidates = [
        Path("/app/templates/OMD_template.docx"),
        _PROJECT_ROOT / "templates/OMD_template.docx",
        Path("templates/OMD_template.docx"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("OMD_template.docx not found")


def load_env_defaults() -> dict:
    path = _env_default_path()
    params: dict = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                params[k.strip()] = v.strip()
    return params


def read_parameters_env(env_path: Path) -> dict:
    params: dict = {}
    if not env_path.exists():
        return params
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                params[k.strip()] = v.strip()
    return params


def write_parameters_env(env_path: Path, project_name: str, params: dict) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    defaults = load_env_defaults()
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"# ==========================================================\n")
        f.write(f"# PROJECT PARAMETERS FOR: {project_name}\n")
        f.write(f"# ==========================================================\n\n")
        f.write("# === DEFAULT VALUES ===\n")
        for k, v in defaults.items():
            f.write(f"# {k}={v}\n")
        f.write("\n# === ACTIVE VALUES ===\n")
        for k, v in params.items():
            f.write(f"{k}={v}\n")


async def _run_subprocess_step(project_name: str, step: str, params: dict, regenerate: bool = False) -> bool:
    """Executes main.py CLI step as an async subprocess and logs to pipeline.log."""
    proc_dir = processing_dir(project_name)
    log_file_path = proc_dir / "pipeline.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3",
        str(_PROJECT_ROOT / "main.py"),
        "--project", project_name,
        "--step", step,
    ]
    if regenerate:
        cmd.append("--regenerate")
    for k, v in params.items():
        cmd.extend([f"--{k}", str(v)])

    logger.info(f"Running pipeline subprocess: {' '.join(cmd)}")

    with open(log_file_path, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n==================================================\n")
        log_f.write(f"STARTING STEP: {step.upper()}\n")
        log_f.write(f"==================================================\n\n")
        log_f.flush()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=str(_PROJECT_ROOT)
            )
            await process.wait()
            return process.returncode == 0
        except Exception as exc:
            log_f.write(f"\nFailed to launch subprocess: {exc}\n")
            logger.exception("Failed to launch CLI subprocess for step %s", step)
            return False


# ── STEP 1 & 2: Parse PDF & Extract Structure ────────────────────────────────

async def run_extraction(
    project_id: int,
    username: str,
    project_name: str,
    pdf_path: str,
    params: dict,
    regenerate: bool = False,
) -> None:
    """Runs PDF-to-MD parsing, followed by AI structural extraction."""
    update_project_status(project_id, "processing_structure")
    try:
        proc_dir = processing_dir(project_name)

        # 1. Parse PDF step
        success = await _run_subprocess_step(project_name, "parse", params, regenerate)
        if not success:
            raise RuntimeError("CLI parse step failed.")

        # 2. Extract structure step
        success = await _run_subprocess_step(project_name, "extract_structure", params, regenerate)
        if not success:
            raise RuntimeError("CLI extract_structure step failed.")

        variables_path = proc_dir / "variables.yml"
        update_project_files(
            project_id,
            variables_path=str(variables_path),
        )
        update_project_status(project_id, "variables")

    except Exception as exc:
        logger.exception("Structural extraction pipeline failed for project %s", project_id)
        update_project_status(project_id, "error", str(exc))


# ── STEP 4: Generate Questions ────────────────────────────────────────────────

async def run_questions_generation(
    project_id: int,
    username: str,
    project_name: str,
    params: dict,
    regenerate: bool = False,
) -> None:
    """Runs AI question generation based on variables.yml structure."""
    update_project_status(project_id, "generating_questions")
    try:
        success = await _run_subprocess_step(project_name, "generate_questions", params, regenerate)
        if not success:
            raise RuntimeError("CLI generate_questions step failed.")

        update_project_status(project_id, "questions")

    except Exception as exc:
        logger.exception("AI questions generation failed for project %s", project_id)
        update_project_status(project_id, "error", str(exc))


# ── STEP 6: Generate Word Document ───────────────────────────────────────────

async def generate_docx(
    project_id: int,
    username: str,
    project_name: str,
    params: dict,
) -> None:
    """Compiles variables.yml into the styled Word template."""
    update_project_status(project_id, "generating_docx")
    try:
        res_dir = results_dir(project_name)
        result_docx = res_dir / f"{project_name}_OMD_Generated.docx"

        success = await _run_subprocess_step(project_name, "generate_docx", params)
        if not success:
            raise RuntimeError("CLI generate_docx step failed.")

        update_project_files(project_id, result_path=str(result_docx))
        update_project_status(project_id, "done")

    except Exception as exc:
        logger.exception("Docx generation failed for project %s", project_id)
        update_project_status(project_id, "error", str(exc))
