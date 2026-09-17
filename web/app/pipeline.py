"""
pipeline.py – Simplified async wrappers that execute the root CLI commands
in the background and update the SQLite project status.
"""

import asyncio
import logging
import os
import sys
import json
import yaml
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


MAX_TASK_TIMEOUT_SECONDS = 600.0  # 10 minutes maximum per task step


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
        try:
            return load_env_defaults()
        except Exception:
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


async def _run_subprocess_step(
    project_name: str,
    step: str,
    params: dict = None,
    regenerate: bool = False,
    extra_args: list = None
) -> bool:
    """Executes main.py CLI step as an async subprocess with a 10-minute timeout and logs to pipeline.log."""
    params = params or {}
    proc_dir = processing_dir(project_name)
    log_file_path = proc_dir / "pipeline.log"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(_PROJECT_ROOT / "main.py"),
        "--project", project_name,
        "--step", step,
    ]
    if regenerate:
        cmd.append("--regenerate")
    if extra_args:
        cmd.extend(extra_args)
    for k, v in params.items():
        cmd.extend([f"--{k}", str(v)])

    logger.info(f"Running pipeline subprocess (timeout {MAX_TASK_TIMEOUT_SECONDS}s): {' '.join(cmd)}")

    with open(log_file_path, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n==================================================\n")
        log_f.write(f"STARTING STEP: {step.upper()} (timeout: {int(MAX_TASK_TIMEOUT_SECONDS // 60)} min)\n")
        log_f.write(f"==================================================\n\n")
        log_f.flush()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=str(_PROJECT_ROOT)
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=MAX_TASK_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                msg = f"\n[TIMEOUT] Превышен лимит времени выполнения задачи ({int(MAX_TASK_TIMEOUT_SECONDS // 60)} минут). Процесс принудительно остановлен.\n"
                log_f.write(msg)
                log_f.flush()
                logger.error("Subprocess for step '%s' timed out after %s seconds. Terminating...", step, MAX_TASK_TIMEOUT_SECONDS)
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    process.kill()
                return False

            return process.returncode == 0
        except Exception as exc:
            log_f.write(f"\nFailed to launch subprocess: {exc}\n")
            logger.exception("Failed to launch CLI subprocess for step %s", step)
            return False


# ── STEP RPD: Generate RPD ───────────────────────────────────────────────────

async def run_rpd_generation(
    project_id: int,
    username: str,
    project_name: str,
    plan_path: str,
    course_name: str,
    custom_context: dict = None
) -> None:
    """Generates RPD document from curriculum plan and saves context."""
    update_project_status(project_id, "generating_rpd")
    try:
        from tools.rpd_generator_tool import generate_rpd_for_project
        from .db import update_project_meta

        res_dir = results_dir(project_name)
        proc_dir = processing_dir(project_name)

        # Run generator with 10-minute timeout
        loop = asyncio.get_running_loop()
        try:
            res = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: generate_rpd_for_project(
                        project_name=project_name,
                        plan_pdf_path=plan_path,
                        course_name_or_code=course_name,
                        output_dir=str(res_dir),
                        custom_context=custom_context
                    )
                ),
                timeout=MAX_TASK_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error("RPD generation timed out after %s seconds for project %s", MAX_TASK_TIMEOUT_SECONDS, project_id)
            update_project_status(project_id, "error", f"Превышен лимит времени генерации РПД ({int(MAX_TASK_TIMEOUT_SECONDS // 60)} минут)")
            return

        rpd_docx_path = res["docx_path"]
        context_path = res["context_path"]

        # Copy context to processing_dir
        proc_context_path = proc_dir / "rpd_context.json"
        with open(proc_context_path, "w", encoding="utf-8") as f:
            import json
            json.dump(res["context"], f, indent=2, ensure_ascii=False)

        update_project_files(
            project_id,
            plan_path=str(plan_path),
            rpd_path=str(rpd_docx_path)
        )
        update_project_meta(
            project_id,
            rpd_path=str(rpd_docx_path),
            course_name=course_name
        )
        update_project_status(project_id, "rpd_ready")
        logger.info("Project %s: RPD generated at %s", project_id, rpd_docx_path)

    except Exception as exc:
        logger.exception("RPD generation failed for project %s", project_id)
        update_project_status(project_id, "error", str(exc))


# ── STEP RPD -> OMD: Bridge RPD context to variables.yml ─────────────────────

async def run_rpd_to_omd_bridge(
    project_id: int,
    username: str,
    project_name: str,
    params: dict = None
) -> None:
    """Converts verified RPD context into OMD variables.yml, preserving any existing AI questions."""
    update_project_status(project_id, "processing_structure")
    try:
        from tools.rpd_to_omd_adapter import rpd_context_to_omd_variables
        import json
        import yaml

        proc_dir = processing_dir(project_name)
        rpd_context_path = proc_dir / "rpd_context.json"
        if not rpd_context_path.exists():
            rpd_context_path = results_dir(project_name) / "teach_plan" / "rpd_context.json"

        if not rpd_context_path.exists():
            raise FileNotFoundError(f"rpd_context.json not found for project {project_name}")

        with open(rpd_context_path, "r", encoding="utf-8") as f:
            rpd_ctx = json.load(f)

        variables_path = proc_dir / "variables.yml"
        existing_vars = None
        if variables_path.exists():
            try:
                with open(variables_path, "r", encoding="utf-8") as vf:
                    existing_vars = yaml.safe_load(vf)
            except Exception:
                pass

        omd_data = rpd_context_to_omd_variables(rpd_ctx, existing_variables=existing_vars)
        with open(variables_path, "w", encoding="utf-8") as f:
            yaml.dump(omd_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        update_project_files(
            project_id,
            variables_path=str(variables_path)
        )
        update_project_status(project_id, "variables")
        logger.info("Project %s: Successfully bridged RPD to variables.yml", project_id)

    except Exception as exc:
        logger.exception("RPD to OMD bridge failed for project %s", project_id)
        update_project_status(project_id, "error", str(exc))



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

        update_project_files(project_id, result_path=str(result_docx), omd_path=str(result_docx))
        from .db import update_project_meta
        update_project_meta(project_id, omd_path=str(result_docx))
        update_project_status(project_id, "done")

    except Exception as exc:
        logger.exception("Docx generation failed for project %s", project_id)
        update_project_status(project_id, "error", str(exc))
