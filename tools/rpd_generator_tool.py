"""
rpd_generator_tool.py – Module to generate RPD docx from curriculum plan or context.
Ensures 100% compliance with all 14 established formatting rules.
"""

import os
import json
import shutil
import logging
from pathlib import Path

from rpd_app.core.curriculum_parser import CurriculumParser
from rpd_app.core.course_presets import (
    get_preset_for_environmental_digital_tech,
    build_generic_context_from_parsed
)
from rpd_app.core.docx_generator import generate_rpd, validate_rpd_document

logger = logging.getLogger("RpdGeneratorTool")

DEFAULT_RPD_TEMPLATE = Path(__file__).resolve().parent.parent / "rpd_app" / "data" / "rpd_template_parametrized.docx"

def generate_rpd_for_project(
    project_name: str,
    plan_pdf_path: str,
    course_name_or_code: str,
    output_dir: str,
    custom_context: dict = None,
    template_path: str = None,
) -> dict:
    """
    Parses curriculum plan, builds RPD context (or uses custom_context),
    and generates the final compliant RPD DOCX.
    """
    out_path = Path(output_dir)
    teach_plan_dir = out_path / "teach_plan"
    template_dir = out_path / "template"
    teach_plan_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parse plan if not already fully provided
    meta = {}
    disc = {}
    comps = []
    coreqs = []
    
    if plan_pdf_path and os.path.exists(plan_pdf_path):
        parser = CurriculumParser(plan_pdf_path)
        meta = parser.extract_metadata()
        disc = parser.extract_discipline_details(course_name_or_code)
        sem = disc["semesters"][0] if disc.get("semesters") else 1
        coreqs = parser.extract_corequisites(sem, disc.get("code", ""))
        comps = parser.extract_competency_details(disc.get("competency_codes", []))

    # 2. Build or merge context
    if custom_context:
        context = custom_context
    elif "цифровые технологии" in course_name_or_code.lower() and "природоохран" in course_name_or_code.lower():
        context = get_preset_for_environmental_digital_tech()
    else:
        context = build_generic_context_from_parsed(meta, disc, comps, coreqs)

    # 3. Save teach_plan JSON artifacts
    if meta:
        with open(teach_plan_dir / "01_metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    if disc:
        with open(teach_plan_dir / "02_curriculum_discipline.json", "w", encoding="utf-8") as f:
            json.dump(disc, f, indent=2, ensure_ascii=False)
    if comps:
        with open(teach_plan_dir / "03_competencies_indicators.json", "w", encoding="utf-8") as f:
            json.dump(comps, f, indent=2, ensure_ascii=False)
    
    from rpd_app.core.docx_generator import sanitize_section2_text
    context = sanitize_section2_text(context)

    with open(teach_plan_dir / "rpd_context.json", "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    # 4. Copy template
    tmpl_src = Path(template_path) if template_path else DEFAULT_RPD_TEMPLATE
    tmpl_dest = template_dir / "rpd_template_parametrized.docx"
    shutil.copy(tmpl_src, tmpl_dest)

    # 5. Determine target docx filename
    code_clean = context.get("course_code", "RPD").replace(" ", "_").replace(".", "_")
    name_clean = context.get("course_name", "Дисциплина").replace(" ", "_")
    name_clean = "".join(c for c in name_clean if c.isalnum() or c in "_-")
    year = context.get("current_year", 2026)
    out_docx_name = f"{code_clean}_{name_clean}_РПД_{year}.docx"
    out_docx_path = out_path / out_docx_name

    # 6. Generate DOCX with all 14 rules
    generate_rpd(str(tmpl_dest), context, str(out_docx_path))
    
    # 7. Validate
    val = validate_rpd_document(str(out_docx_path))
    logger.info("Generated RPD DOCX: %s, validation: %s", out_docx_path, val)

    return {
        "status": "success",
        "docx_path": str(out_docx_path),
        "context_path": str(teach_plan_dir / "rpd_context.json"),
        "context": context,
        "validation": val,
    }
