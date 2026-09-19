import os
import sys
import asyncio
import logging
import json
import yaml
import copy
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import SequentialAgent, LoopAgent, LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google import genai
from schemas.omd_schema import OmdDataSchema, OmdQuestionsPatchSchema, ActivityQuestionsItem

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("PipelineCore")

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

# Validate the API key setup
if not os.environ.get("GOOGLE_API_KEY"):
    logger.warning("GOOGLE_API_KEY environment variable is not set. Gemini API calls will fail.")

# Imports of tools
from tools.pdf_parser_tool import pdf_parser_tool, docling_parser_tool
from tools.docx_generator_tool import (
    docx_generator_tool,
    clean_dict_hyphenations,
    clean_question_prefixes
)
from tools.rpd_generator_tool import generate_rpd_for_project
from tools.rpd_to_omd_adapter import rpd_context_to_omd_variables
from tools.rpd_ai_generator import generate_rpd_content_via_ai, dump_rpd_variables_to_cli
from rpd_app.core.curriculum_parser import CurriculumParser
from agents.analyzer_agent import analyzer_agent
from agents.critic_agent import critic_agent

# Mock context for running tools directly
class MockToolContext:
    def __init__(self, state):
        self.state = state

# Exit helper for loops
def exit_loop(tool_context) -> dict:
    tool_context.actions.escalate = True
    return {"status": "success", "message": "Critic approved the verification."}

# Helper to load Defaults and Parameters
def load_env_defaults():
    default_path = ".env.default"
    defaults = {}
    if os.path.exists(default_path):
        with open(default_path, "r", encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if line_s and not line_s.startswith("#") and "=" in line_s:
                    k, v = line_s.split("=", 1)
                    defaults[k.strip()] = v.strip()
    return defaults

def load_project_parameters(project_name, processing_dir, cli_args=None, extra_cli_params=None):
    defaults = load_env_defaults()
    project_env_path = os.path.join(processing_dir, "parameters.env")
    
    # Read existing parameter file
    project_params = {}
    if os.path.exists(project_env_path):
        with open(project_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line_s = line.strip()
                if line_s and not line_s.startswith("#") and "=" in line_s:
                    k, v = line_s.split("=", 1)
                    project_params[k.strip()] = v.strip()
                    
    # Overlay CLI args if passed
    if cli_args:
        for k in defaults.keys():
            val = getattr(cli_args, k, None)
            if val is not None:
                project_params[k] = str(val)

    if extra_cli_params:
        for k, val in extra_cli_params.items():
            if val is not None:
                project_params[k] = str(val)
                
    # Save the updated parameters to parameters.env
    os.makedirs(processing_dir, exist_ok=True)
    with open(project_env_path, "w", encoding="utf-8") as f:
        f.write("# ==========================================================\n")
        f.write(f"# PROJECT PARAMETERS FOR: {project_name}\n")
        f.write("# ==========================================================\n\n")
        f.write("# === DEFAULT VALUES ===\n")
        for k, v in defaults.items():
            f.write(f"# {k}={v}\n")
        f.write("\n# === ACTIVE VALUES (User set) ===\n")
        for k, v in project_params.items():
            f.write(f"{k}={v}\n")
            
    # Merge and return all active parameters
    merged = dict(defaults)
    merged.update(project_params)
    return merged


# ── STEP 1: Parse PDF ─────────────────────────────────────────────────────────
def run_parse_step(project_name: str, regenerate: bool = False) -> dict:
    logger.info(f"--- Running Step 1: Parse PDF for project {project_name} ---")
    input_base_dir = "input"
    project_input_dir = os.path.join(input_base_dir, project_name)
    if not os.path.exists(project_input_dir):
        raise FileNotFoundError(f"Input directory '{project_input_dir}' not found.")
        
    pdf_files = [f for f in os.listdir(project_input_dir) if f.endswith(".pdf")]
    if not pdf_files:
        raise FileNotFoundError(f"No PDF file found in {project_input_dir}")
        
    pdf_path = os.path.join(project_input_dir, pdf_files[0])
    processing_dir = os.path.join("processing", project_name)
    os.makedirs(processing_dir, exist_ok=True)
    output_markdown_path = os.path.join(processing_dir, f"{project_name}_parsed.md")
    
    state = {
        "project_name": project_name,
        "pdf_path": pdf_path,
        "output_markdown_path": output_markdown_path,
        "regenerate": regenerate,
    }
    
    res = docling_parser_tool(MockToolContext(state))
    logger.info(f"Step 1 Complete: {res}")
    return res


# ── STEP 2: Extract Structure ────────────────────────────────────────────────
async def run_extract_structure_step(project_name: str, params: dict, regenerate: bool = False) -> dict:
    logger.info(f"--- Running Step 2: Extract Structure for project {project_name} ---")
    processing_dir = os.path.join("processing", project_name)
    output_markdown_path = os.path.join(processing_dir, f"{project_name}_parsed.md")
    variables_path = os.path.join(processing_dir, "variables.yml")
    
    if not os.path.exists(output_markdown_path):
        raise FileNotFoundError(f"Parsed Markdown not found at {output_markdown_path}. Run step 'parse' first.")
        
    # Check if variables.yml already exists and regenerate is False
    if os.path.exists(variables_path) and not regenerate:
        logger.info(f"variables.yml already exists for '{project_name}' and regenerate=False. Skipping extraction.")
        return {"status": "success", "message": "variables.yml already exists"}
        
    with open(output_markdown_path, "r", encoding="utf-8") as f:
        rpd_content = f.read()
        
    # Build structural analyzer agent
    structural_analyzer = LlmAgent(
        name="StructuralAnalyzer",
        model=DEFAULT_GEMINI_MODEL,
        output_schema=OmdDataSchema,
        output_key="omd_json_data",
        instruction="""
        You are the StructuralAnalyzerAgent. Your job is to read the raw syllabus Markdown content provided in the user input message
        and extract and structure all educational header metadata, department, course code, competency tables, and the lesson schedule.
        
        Format the output strictly according to the OmdDataSchema Pydantic model.
        Instructions for extraction:
        1. Metadata:
           - Extract 'institute', 'department', 'course_code', 'course_title', 'degree_type', 'fgos_vo', 'major_code', 'major_title', 'profile_title', 'course_year', 'semester', 'study_form', 'start_year', 'developers', 'reviewer', 'rpd_reference_text'.
        2. Table 1 & Table 2:
           - Extract Table 1 (stages of competency formation) and Table 2 (competencies indicators know/umeti/vladeti).
        3. Table 4 Activities Outline:
           - Populate 'activities' list with all individual lessons/activities (Lectures / Лекции and Practical classes / Практические занятия).
           - For each activity, extract its 'num' (e.g. 'Лекция №1'), 'theme', 'type', 'hours', 'comp_code', and 'eval_tool'.
           - CRITICAL: Do NOT generate or extract any questions for activities. Set 'questions' to an empty list [] for all activities.
        4. Evaluation Tasks:
           - Set all evaluation task fields (case_study, colloquium, test_paper, round_table, portfolio, roleplay, creative_project, multi_level_tasks, rgr, essay, course_work, credit, exam) to null (None).
        """
    )
    
    structural_critic = LlmAgent(
        name="StructuralCritic",
        model=DEFAULT_GEMINI_MODEL,
        instruction="""
        You are the StructuralCriticAgent. Your job is to validate the structured JSON data stored in 'omd_json_data'
        against the raw syllabus content in 'rpd_content'.
        
        Validation Checklist:
        1. Metadata: Are all header fields (institute, department, course year, developers, profile, etc.) fully and accurately extracted?
        2. Competency Tables: Are Table 1 and Table 2 fully extracted? Are all competencies from the syllabus present?
        3. Activities List: Does the 'activities' list contain all the lectures and practical lessons from the syllabus Table 4? Are their details (num, theme, hours, type, comp_code, eval_tool) fully populated?
        4. CRITICAL: Make sure NO questions or evaluation tasks are generated yet. All 'questions' lists in activities must be empty.
        
        If the structure is 100% complete and correct, CALL the 'exit_loop' tool immediately.
        If there are errors or missing structure, provide a critique so the analyzer agent can fix it.
        """,
        tools=[exit_loop]
    )
    
    struct_loop = LoopAgent(
        name="StructuralAnalysisLoop",
        sub_agents=[structural_analyzer, structural_critic],
        max_iterations=5,
    )
    
    runner = InMemoryRunner(agent=struct_loop)
    runner.auto_create_session = True
    session_id = f"struct_session_{project_name}"
    
    query = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Parse syllabus structure for '{project_name}' from the provided markdown context:\n\n{rpd_content}"
        ))],
    )
    
    state_delta = {
        "project_name": project_name,
        "rpd_content": rpd_content,
        "omd_json_data": {},
        **{k: (int(v) if k.endswith("_number") else v) for k, v in params.items()},
    }
    
    async def _run_extract_loop():
        async for event in runner.run_async(
            user_id="system_user",
            session_id=session_id,
            new_message=query,
            state_delta=state_delta,
        ):
            source = getattr(event, 'source', 'System')
            print(f"\n>>> [{source} Event]")
            if hasattr(event, 'content') and event.content:
                parts = getattr(event.content, 'parts', []) or []
                for part in parts:
                    text = getattr(part, 'text', '')
                    if text:
                        print(text)
            elif hasattr(event, 'tool_call') and event.tool_call:
                print(f"Calling Tool: {getattr(event.tool_call, 'name')}")

    try:
        await asyncio.wait_for(_run_extract_loop(), timeout=600.0)
    except asyncio.TimeoutError:
        logger.error("AI structural extraction timed out after 10 minutes (600s).")
        raise TimeoutError("Structural extraction timed out after 10 minutes.")
            
    # Fetch final state and write variables.yml
    session = await runner.session_service.get_session(app_name=runner.app_name, user_id="system_user", session_id=session_id)
    omd_json_data = session.state.get("omd_json_data", {})
    if not omd_json_data:
        raise RuntimeError("AI structural extraction failed: omd_json_data is empty.")
        
    data = clean_dict_hyphenations(omd_json_data)
    data = clean_question_prefixes(data)
    
    with open(variables_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
    logger.info(f"Saved structural variables.yml to {variables_path}")
    return {"status": "success", "message": f"Saved structure to {variables_path}"}


# ── STEP 3: Generate Questions ───────────────────────────────────────────────
async def run_generate_questions_step(project_name: str, params: dict, regenerate: bool = False) -> dict:
    logger.info(f"--- Running Step 3: Generate Questions for project {project_name} ---")
    processing_dir = os.path.join("processing", project_name)
    output_markdown_path = os.path.join(processing_dir, f"{project_name}_parsed.md")
    variables_path = os.path.join(processing_dir, "variables.yml")
    rpd_ctx_file = os.path.join(processing_dir, "rpd_context.json")
    
    # 1. Load existing variables.yml
    omd_json_data = {}
    if os.path.exists(variables_path):
        try:
            with open(variables_path, "r", encoding="utf-8") as f:
                omd_json_data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Error loading {variables_path}: {e}")

    # 2. If rpd_context.json exists, harmonize structure & import assessment tasks
    if os.path.exists(rpd_ctx_file):
        try:
            with open(rpd_ctx_file, "r", encoding="utf-8") as f:
                rpd_ctx = json.load(f)
            omd_json_data = rpd_context_to_omd_variables(rpd_ctx, omd_json_data, params=params)
            logger.info("Harmonized variables.yml with rpd_context.json assessment tools.")
        except Exception as e:
            logger.warning(f"Could not adapt rpd_context.json: {e}")

    if not omd_json_data:
        raise FileNotFoundError(f"Neither variables.yml nor rpd_context.json found at {processing_dir}. Run prior steps first.")

    acts = omd_json_data.get("activities", [])
    has_questions = bool(acts and any(a.get("questions") for a in acts))
    if has_questions and not regenerate:
        logger.info("Questions already exist in variables.yml and regenerate=False. Skipping.")
        return {"status": "success", "message": "Questions already exist in variables.yml"}

    # 3. Generate questions via Google Gemini API (focused patch schema)
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key and acts:
        try:
            client = genai.Client(api_key=api_key)
            model_name = DEFAULT_GEMINI_MODEL

            # Extract activities summary
            acts_summary = [
                {
                    "num": a.get("num", f"Занятие {i+1}"),
                    "theme": a.get("theme", ""),
                    "type": a.get("type", "Лекция"),
                    "comp_code": a.get("comp_code", "")
                }
                for i, a in enumerate(acts)
            ]

            # Determine assessment tools needing generation
            needed_tools = []
            if not omd_json_data.get("colloquium") or regenerate: needed_tools.append("colloquium (коллоквиум)")
            if not omd_json_data.get("test_paper") or regenerate: needed_tools.append("test_paper (тестирование)")
            if not omd_json_data.get("case_study") or regenerate: needed_tools.append("case_study (кейс-задания)")
            if not omd_json_data.get("creative_project") or regenerate: needed_tools.append("creative_project (творческий проект)")
            is_exam = "экзамен" in str(omd_json_data.get("course_type", "")).lower()
            if is_exam:
                if not omd_json_data.get("exam") or regenerate: needed_tools.append("exam (вопросы к экзамену)")
            else:
                if not omd_json_data.get("credit") or regenerate: needed_tools.append("credit (вопросы к зачету)")

            prompt = f"""Ты — ведущий профессор и эксперт-методист РГАУ-МСХА имени К.А. Тимирязева.
Твоя задача — сгенерировать академически глубокие, профессиональные оценочные материалы для фонда оценочных средств (ОМД).

СВЕДЕНИЯ О ДИСЦИПЛИНЕ:
- Наименование дисциплины: «{omd_json_data.get('course_title')}» (код: {omd_json_data.get('course_code')})
- Направление подготовки: {omd_json_data.get('major_code')} {omd_json_data.get('major_title')}
- Направленность (профиль): {omd_json_data.get('profile_title')}
- Уровень образования: {omd_json_data.get('degree_type')}

СЕТКА УЧЕБНЫХ ЗАНЯТИЙ:
{json.dumps(acts_summary, ensure_ascii=False, indent=2)}

ИНСТРУКЦИИ ПО ГЕНЕРАЦИИ:
1. В поле 'activity_questions' для КАЖДОГО занятия сгенерируй от 3 до 5 контрольных вопросов для устного опроса и текущего контроля, строго привязанных к теме занятия и компетенциям.
2. Для оценочных средств:
   - В 'colloquium': 5-8 дискуссионных вопросов по ключевым разделам и критерии оценивания.
   - В 'test_paper': 10-15 тестовых заданий с 4 нумерованными вариантами ответов (1), 2), 3), 4)) и ключом правильного ответа, плюс шкала оценивания. Форматируй каждое задание строго: предложение вопроса с двоеточием или знаком ?, новая строка, варианты ответа 1) ..., 2) ..., 3) ..., 4) ..., строка с ключом (Правильный ответ: [номер]).
   - В 'case_study': 3-5 практических ситуационных кейс-задач с описанием производственной ситуации и критерии решения.
   - В 'creative_project': 5-10 актуальных тем индивидуальных и групповых проектов с критериями защиты.
   - В 'credit' или 'exam': 15-20 вопросов к промежуточной аттестации с критериями оценивания.

Верни результат строго в формате JSON, соответствующем схеме OmdQuestionsPatchSchema.
"""
            print(f">>> [OMD Questions Event] Запуск генерации вопросов через Gemini ({model_name})...", flush=True)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OmdQuestionsPatchSchema,
                    temperature=0.3
                )
            )

            prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            cand_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
            total_tokens = getattr(response.usage_metadata, "total_token_count", 0) or (prompt_tokens + cand_tokens)
            cost_usd = (prompt_tokens * 0.15 + cand_tokens * 0.60) / 1_000_000
            cost_rub = cost_usd * 95.0
            print(f">>> [OMD Questions Event] Вопросы получены! Токены: {total_tokens:,} (вход: {prompt_tokens:,}, выход: {cand_tokens:,}). Стоимость: ~{cost_rub:.2f} ₽ (${cost_usd:.5f})", flush=True)

            patch_data = json.loads(response.text)
            act_qs_map = {}
            for item in patch_data.get("activity_questions", []):
                k = (item.get("num") or "").strip().lower()
                if k and item.get("questions"):
                    act_qs_map[k] = item["questions"]

            # Merge questions into activities
            for idx, a in enumerate(acts):
                num_k = (a.get("num") or "").strip().lower()
                matched_qs = act_qs_map.get(num_k)
                if not matched_qs and idx < len(patch_data.get("activity_questions", [])):
                    matched_qs = patch_data["activity_questions"][idx].get("questions")
                if matched_qs:
                    a["questions"] = matched_qs

            # Merge assessment tools
            for tool_key in ["colloquium", "test_paper", "case_study", "creative_project", "credit", "exam"]:
                if patch_data.get(tool_key):
                    omd_json_data[tool_key] = patch_data[tool_key]

        except Exception as e:
            logger.warning(f"AI question generation failed or hit error: {e}. Falling back to synthesized questions...")

    # 4. Fallback synthesis for any activity that still lacks questions
    for idx, a in enumerate(omd_json_data.get("activities", [])):
        if not a.get("questions"):
            theme = a.get("theme") or a.get("num") or f"Занятие {idx+1}"
            a["questions"] = [
                f"Раскройте теоретические основы и понятийный аппарат темы «{theme}».",
                f"Каковы ключевые методы и алгоритмы, применяемые в рамках темы «{theme}»?",
                f"Приведите практический пример реализации решений по теме «{theme}»."
            ]

    data = clean_dict_hyphenations(omd_json_data)
    data = clean_question_prefixes(data)

    with open(variables_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 5. CLI Output of generated variables summary
    print("\n" + "=" * 80)
    print(f"  ДАМП СГЕНЕРИРОВАННЫХ ОЦЕНОЧНЫХ МАТЕРИАЛОВ (ОМД): {project_name}")
    print("=" * 80)
    print(f"Дисциплина: {data.get('course_title')} ({data.get('course_code')})")
    print(f"Учебных занятий в сетке: {len(data.get('activities', []))}")
    for idx, a in enumerate(data.get("activities", [])[:4], 1):
        print(f"  {idx}. [{a.get('type')}] {a.get('num')}: {len(a.get('questions', []))} вопр.")
        for q in a.get("questions", [])[:2]:
            print(f"     • {q}")
    if len(data.get("activities", [])) > 4:
        rem_count = len(data.get("activities", [])) - 4
        print(f"  ... и еще {rem_count} занятий с вопросами.")

    print("\nФОНД ОЦЕНОЧНЫХ СРЕДСТВ:")
    colloq = data.get("colloquium")
    if colloq:
        q_cnt = sum(len(s.get("questions", [])) for s in colloq.get("sections", []))
        print(f"  - Коллоквиум: {q_cnt} вопросов")
    test_p = data.get("test_paper")
    if test_p:
        t_cnt = sum(len(v.get("tasks", [])) for top in test_p.get("topics", []) for v in top.get("variants", []))
        print(f"  - Тестовые задания: {t_cnt} заданий")
    case_s = data.get("case_study")
    if case_s:
        print(f"  - Практические кейсы: {len(case_s.get('tasks', []))} кейсов")
    creat_p = data.get("creative_project")
    if creat_p:
        print(f"  - Творческие проекты: {len(creat_p.get('individual_projects', []))} инд. / {len(creat_p.get('group_projects', []))} групп.")
    cred = data.get("credit")
    if cred:
        print(f"  - Вопросы к зачету: {len(cred.get('questions', []))} вопросов")
    ex = data.get("exam")
    if ex:
        print(f"  - Вопросы к экзамену: {len(ex.get('questions', []))} вопросов")
    print("=" * 80 + "\n")

    logger.info(f"Saved completed variables.yml with questions to {variables_path}")
    return {"status": "success", "message": f"Saved questions to {variables_path}"}


# ── STEP 4: Generate Docx ────────────────────────────────────────────────────
def run_generate_docx_step(project_name: str, params: dict, regenerate: bool = False) -> dict:
    logger.info(f"--- Running Step 4: Generate Docx for project {project_name} ---")
    processing_dir = os.path.join("processing", project_name)
    results_dir = os.path.join("results", project_name)
    variables_path = os.path.join(processing_dir, "variables.yml")
    output_markdown_path = os.path.join(processing_dir, f"{project_name}_parsed.md")
    
    if not os.path.exists(variables_path):
        raise FileNotFoundError(f"variables.yml not found at {variables_path}")
        
    with open(variables_path, encoding="utf-8") as f:
        omd_data = yaml.safe_load(f)
        
    rpd_content = ""
    if os.path.exists(output_markdown_path):
        with open(output_markdown_path, encoding="utf-8") as f:
            rpd_content = f.read()
            
    template_path = "templates/OMD_template.docx"
    output_path = os.path.join(results_dir, f"{project_name}_OMD_Generated.docx")
    
    state = {
        "project_name": project_name,
        "pdf_path": "",
        "template_path": template_path,
        "output_markdown_path": output_markdown_path,
        "temp_annotated_path": os.path.join(processing_dir, f"{project_name}_annotated.docx"),
        "output_path": output_path,
        "regenerate": regenerate,
        "omd_json_data": omd_data,
        "rpd_content": rpd_content,
        **{k: (int(v) if k.endswith("_number") else v) for k, v in params.items()},
    }
    
    res = docx_generator_tool(MockToolContext(state))
    logger.info(f"Step 4 Complete: {res}")
    if res.get("status") == "error":
        raise RuntimeError(f"Docx generation failed: {res.get('message')}")
    return res


# ── UNIFIED RPD & CURRICULUM STEPS ──────────────────────────────────────────

def _find_plan_file(project_name: str, explicit_path: str = None) -> str:
    """Finds curriculum plan PDF for project."""
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path
        
    input_base_dir = "input"
    project_input_dir = os.path.join(input_base_dir, project_name)
    if os.path.exists(project_input_dir):
        plx_files = [f for f in os.listdir(project_input_dir) if f.endswith(".plx.pdf")]
        if plx_files:
            return os.path.join(project_input_dir, plx_files[0])
        pdf_files = [f for f in os.listdir(project_input_dir) if f.endswith(".pdf")]
        if pdf_files:
            return os.path.join(project_input_dir, pdf_files[0])
            
    # Check default research presets
    preset = Path("RPD-research/цифровые технологии в природоохранной деятельности на предприятии/Учебные_планы/21.04.02_Zemleustroistvo_i_kadastry_(mag.)_CTvZA_2026.plx.pdf")
    if preset.exists():
        return str(preset)
        
    raise FileNotFoundError(f"Curriculum plan not found for project '{project_name}'.")


def run_parse_plan_step(project_name: str, plan_path: str = None) -> dict:
    """Parses curriculum plan with PyMuPDF, extracts metadata and lists disciplines."""
    logger.info(f"--- Running Step: Parse Curriculum Plan for project '{project_name}' ---")
    plan_file = _find_plan_file(project_name, plan_path)
    parser = CurriculumParser(plan_file)
    meta = parser.extract_metadata()
    disciplines = parser.list_disciplines()
    
    proc_dir = os.path.join("processing", project_name)
    os.makedirs(proc_dir, exist_ok=True)
    summary_path = os.path.join(proc_dir, "curriculum_summary.json")
    
    data = {
        "metadata": meta,
        "disciplines_count": len(disciplines),
        "disciplines": disciplines,
        "plan_file": plan_file
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Curriculum parsed: {len(disciplines)} disciplines found. Saved to {summary_path}")
    return data


def run_generate_rpd_content_step(project_name: str, plan_path: str = None, course_query: str = None, params: dict = None, regenerate: bool = False) -> dict:
    """Generates rich AI RPD content (ZUV, dynamic sections, FOS, literature, software) via Gemini API."""
    logger.info(f"--- Running Step: Generate RPD AI Content for project '{project_name}' ---")
    proc_dir = os.path.join("processing", project_name)
    os.makedirs(proc_dir, exist_ok=True)
    proc_context_path = os.path.join(proc_dir, "rpd_context.json")

    if os.path.exists(proc_context_path) and not regenerate:
        try:
            with open(proc_context_path, "r", encoding="utf-8") as f:
                existing_ctx = json.load(f)
            has_substance = bool(
                existing_ctx.get("token_usage") or
                (existing_ctx.get("t4_sections") and sum(len(s.get("lessons", [])) for s in existing_ctx.get("t4_sections", [])) >= 10)
            )
            if has_substance:
                logger.info(f"rpd_context.json already exists for '{project_name}' with substantive content. Skipping AI call.")
                dump_rpd_variables_to_cli(existing_ctx)
                return {"status": "success", "context": existing_ctx}
        except Exception:
            pass

    plan_file = _find_plan_file(project_name, plan_path)
    if not plan_file or not os.path.exists(plan_file):
        raise FileNotFoundError(f"Curriculum plan PDF not found for project '{project_name}'. Provide --plan.")

    query = course_query
    if not query and params:
        query = params.get("course_code") or params.get("course_name")
    if not query and os.path.exists(proc_context_path):
        try:
            with open(proc_context_path, "r", encoding="utf-8") as f:
                old_c = json.load(f)
                query = old_c.get("course_code") or old_c.get("course_name")
        except Exception:
            pass
    if not query:
        query = project_name

    parser = CurriculumParser(plan_file)
    meta = parser.extract_metadata()
    disc = parser.extract_discipline_details(query)
    sem = disc["semesters"][0] if disc.get("semesters") else 1
    coreqs = parser.extract_corequisites(sem, disc.get("code", ""))

    comps = None
    if os.path.exists(proc_context_path):
        try:
            with open(proc_context_path, "r", encoding="utf-8") as f:
                saved_ctx = json.load(f)
            if saved_ctx.get("user_verified_competencies") and saved_ctx.get("competencies_nested"):
                user_codes = saved_ctx.get("competency_codes") or [c["code"] for c in saved_ctx["competencies_nested"]]
                comps = parser.extract_competency_details(user_codes)
        except Exception:
            pass
    if not comps:
        comps = parser.extract_competency_details(disc.get("competency_codes", []))

    context = generate_rpd_content_via_ai(meta, disc, comps, coreqs)

    with open(proc_context_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    results_dir = os.path.join("results", project_name, "teach_plan")
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "rpd_context.json"), "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    logger.info(f"RPD AI content successfully generated and saved to {proc_context_path}")

    # Stream all generated variables to CLI / stdout
    dump_rpd_variables_to_cli(context)

    # Immediately compile fresh DOCX document so it matches the generated AI content
    try:
        logger.info(f"Automatically compiling fresh RPD DOCX document for '{project_name}'...")
        run_generate_rpd_step(project_name, plan_path=plan_file, course_query=query, params=params)
    except Exception as e:
        logger.warning(f"Could not automatically compile DOCX after RPD AI generation: {e}")

    return {"status": "success", "context": context}


def run_generate_rpd_step(project_name: str, plan_path: str = None, course_query: str = None, params: dict = None) -> dict:
    """Generates 100% compliant RPD DOCX using 14 formatting rules."""
    logger.info(f"--- Running Step: Generate RPD for project '{project_name}' ---")
    proc_dir = os.path.join("processing", project_name)
    proc_context_path = os.path.join(proc_dir, "rpd_context.json")
    
    custom_context = None
    if os.path.exists(proc_context_path):
        try:
            with open(proc_context_path, "r", encoding="utf-8") as f:
                custom_context = json.load(f)
        except Exception:
            custom_context = None

    if not custom_context:
        # Pre-generate rich AI content first
        gen_res = run_generate_rpd_content_step(project_name, plan_path, course_query, params)
        custom_context = gen_res.get("context")

    plan_file = _find_plan_file(project_name, plan_path)
    query = course_query or (params.get("course_code") or params.get("course_name") if params else None) or project_name
        
    results_dir = os.path.join("results", project_name)
    os.makedirs(results_dir, exist_ok=True)
    
    res = generate_rpd_for_project(
        project_name=project_name,
        plan_pdf_path=plan_file,
        course_name_or_code=query,
        output_dir=results_dir,
        custom_context=custom_context
    )
    
    # Save context copy to processing dir
    os.makedirs(proc_dir, exist_ok=True)
    with open(proc_context_path, "w", encoding="utf-8") as f:
        json.dump(res["context"], f, indent=2, ensure_ascii=False)
        
    logger.info(f"RPD generated successfully: {res['docx_path']}")
    return res


def run_rpd_to_omd_step(project_name: str, params: dict = None) -> dict:
    """Converts verified RPD context into OMD variables.yml data."""
    logger.info(f"--- Running Step: Convert RPD to OMD for project '{project_name}' ---")
    proc_dir = os.path.join("processing", project_name)
    rpd_ctx_candidates = [
        os.path.join(proc_dir, "rpd_context.json"),
        os.path.join("results", project_name, "teach_plan", "rpd_context.json"),
    ]
    rpd_ctx_file = None
    for c in rpd_ctx_candidates:
        if os.path.exists(c):
            rpd_ctx_file = c
            break
            
    if not rpd_ctx_file:
        raise FileNotFoundError(f"rpd_context.json not found in processing/ or results/ for project '{project_name}'. Run 'generate_rpd' first.")
        
    with open(rpd_ctx_file, "r", encoding="utf-8") as f:
        rpd_ctx = json.load(f)
        
    variables_path = os.path.join(proc_dir, "variables.yml")
    existing_vars = None
    if os.path.exists(variables_path):
        try:
            with open(variables_path, "r", encoding="utf-8") as vf:
                existing_vars = yaml.safe_load(vf)
        except Exception:
            pass

    omd_data = rpd_context_to_omd_variables(rpd_ctx, existing_variables=existing_vars)
    with open(variables_path, "w", encoding="utf-8") as f:
        yaml.dump(omd_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
    logger.info(f"Successfully converted RPD context to OMD variables.yml at {variables_path}")
    return {"status": "success", "variables_path": variables_path, "data": omd_data}


# ── CLI & Main ────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="TimPlan & KOMA Unified Syllabus Processing CLI")
    parser.add_argument("--project", required=True, help="Project name (subdirectory in input/)")
    parser.add_argument(
        "--step",
        choices=[
            "parse",
            "parse_plan",
            "generate_rpd_content",
            "generate_rpd",
            "rpd_to_omd",
            "extract_structure",
            "generate_questions",
            "generate_docx",
            "generate_omd",
            "all"
        ],
        default="all",
        help="Pipeline step to execute"
    )
    parser.add_argument("--plan", help="Path to curriculum plan PDF (.plx.pdf or .pdf)")
    parser.add_argument("--course", help="Target course name or code (e.g. 'Цифровые технологии...')")
    parser.add_argument("--regenerate", action="store_true", help="Force regenerate files")
    
    # Parameters overrides
    defaults = load_env_defaults()
    for k in defaults.keys():
        parser.add_argument(f"--{k}", help=f"Override for parameter {k}")
        
    args, unknown = parser.parse_known_args()
    project_name = args.project
    step = args.step
    regenerate = args.regenerate
    
    extra_cli_params = {}
    i = 0
    while i < len(unknown):
        arg = unknown[i]
        if arg.startswith("--"):
            key = arg[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                extra_cli_params[k] = v
                i += 1
            elif i + 1 < len(unknown) and not unknown[i+1].startswith("--"):
                extra_cli_params[key] = unknown[i+1]
                i += 2
            else:
                extra_cli_params[key] = "true"
                i += 1
        else:
            i += 1

    proc_dir = os.path.join("processing", project_name)
    params = load_project_parameters(project_name, proc_dir, args, extra_cli_params=extra_cli_params)
    if args.course:
        params["course_name"] = args.course
    
    try:
        if step == "parse":
            run_parse_step(project_name, regenerate)
        elif step == "parse_plan":
            run_parse_plan_step(project_name, args.plan)
        elif step == "generate_rpd_content":
            run_generate_rpd_content_step(project_name, args.plan, args.course, params, regenerate)
        elif step == "generate_rpd":
            run_generate_rpd_step(project_name, args.plan, args.course, params)
        elif step == "rpd_to_omd":
            run_rpd_to_omd_step(project_name, params)
        elif step == "extract_structure":
            await run_extract_structure_step(project_name, params, regenerate)
        elif step == "generate_questions":
            await run_generate_questions_step(project_name, params, regenerate)
        elif step in ("generate_docx", "generate_omd"):
            run_generate_docx_step(project_name, params, regenerate)
        elif step == "all":
            # Check if this is a curriculum-first project
            has_plan = bool(args.plan)
            if not has_plan:
                inp_dir = os.path.join("input", project_name)
                if os.path.exists(inp_dir):
                    has_plan = any(f.endswith(".plx.pdf") or "plan" in f.lower() for f in os.listdir(inp_dir))
                    
            if has_plan:
                logger.info("=== Running Unified Curriculum -> RPD -> OMD Pipeline ===")
                run_parse_plan_step(project_name, args.plan)
                run_generate_rpd_content_step(project_name, args.plan, args.course, params, regenerate)
                run_generate_rpd_step(project_name, args.plan, args.course, params)
                run_rpd_to_omd_step(project_name, params)
                # Questions are populated via bridge; if AI questions requested, run questions step
                if os.environ.get("GOOGLE_API_KEY"):
                    try:
                        await run_generate_questions_step(project_name, params, regenerate)
                    except Exception as err:
                        logger.warning(f"AI questions step skipped or failed: {err}. Proceeding with template questions.")
                run_generate_docx_step(project_name, params, regenerate)
            else:
                logger.info("=== Running Standard Syllabus -> OMD Pipeline ===")
                run_parse_step(project_name, regenerate)
                await run_extract_structure_step(project_name, params, regenerate)
                await run_generate_questions_step(project_name, params, regenerate)
                run_generate_docx_step(project_name, params, regenerate)
            
        logger.info(f"SUCCESS: Pipeline execution for step '{step}' completed.")
    except Exception as ex:
        logger.exception(f"ERROR: Pipeline execution failed for step '{step}'")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

