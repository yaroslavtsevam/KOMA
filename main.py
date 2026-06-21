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
from schemas.omd_schema import OmdDataSchema

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("PipelineCore")

# Validate the API key setup
if not os.environ.get("GOOGLE_API_KEY"):
    logger.warning("GOOGLE_API_KEY environment variable is not set. Gemini API calls will fail.")

# Imports of tools
from tools.docling_parser_tool import docling_parser_tool
from tools.docx_generator_tool import (
    docx_generator_tool,
    clean_dict_hyphenations,
    clean_question_prefixes
)
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

def load_project_parameters(project_name, processing_dir, cli_args=None):
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
            
    # Merge and return
    merged = {}
    for k, default_val in defaults.items():
        user_val = project_params.get(k)
        merged[k] = user_val if user_val is not None else default_val
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
        model="gemini-2.5-flash",
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
        model="gemini-2.5-flash",
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
    
    async for event in runner.run_async(
        user_id="system_user",
        session_id=session_id,
        new_message=query,
        state_delta=state_delta,
    ):
        # Print events verbosely to stdout so the web tail-logger can capture them
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
    
    if not os.path.exists(output_markdown_path):
        raise FileNotFoundError(f"Parsed Markdown not found at {output_markdown_path}. Run step 'parse' first.")
    if not os.path.exists(variables_path):
        raise FileNotFoundError(f"variables.yml not found at {variables_path}. Run step 'extract_structure' first.")
        
    with open(output_markdown_path, "r", encoding="utf-8") as f:
        rpd_content = f.read()
    with open(variables_path, "r", encoding="utf-8") as f:
        omd_json_data = yaml.safe_load(f)
        
    # If variables already have questions and regenerate is False, skip
    has_questions = False
    if omd_json_data:
        acts = omd_json_data.get("activities", [])
        if acts and any(a.get("questions") for a in acts):
            has_questions = True
            
    if has_questions and not regenerate:
        logger.info(f"Questions already generated in variables.yml and regenerate=False. Skipping.")
        return {"status": "success", "message": "Questions already exist in variables.yml"}
        
    # Build questions generator agent
    questions_generator = LlmAgent(
        name="QuestionsGenerator",
        model="gemini-2.5-flash",
        output_schema=OmdDataSchema,
        output_key="omd_json_data",
        instruction="""
        You are the QuestionsGeneratorAgent. Your job is to take the existing course structure (metadata, competency tables, and activities schedule) provided in 'omd_json_data', read the raw syllabus text in 'rpd_content', and generate/populate all evaluation questions and tasks.
        
        Do NOT change the course structure (e.g. metadata, competency lists, activity names/hours) that is already in 'omd_json_data'. Keep them exactly as they are.
        
        Your task is to:
        1. Lesson Questions:
           - For each activity in the 'activities' list: generate a list of relevant, high-quality, academic questions in Russian that match the topic and competencies.
           - The number of questions for seminars/practical lessons should match 'seminar_questions_number' parameter.
           - The number of questions for lab classes should match 'lab_questions_number'.
           - Populate these under the activity's 'questions' field.
        2. Colloquium sections:
           - Populate 'colloquium.sections' to match the activities list (each section corresponding to a lesson and its generated questions).
           - Populate 'colloquium.criteria' with standard grading criteria (grades 5, 4, 3, 2).
        3. Evaluation Tasks & Active Tools:
           - Identify active evaluation tools from the syllabus (e.g., test paper, credit, exam, case study).
           - For each active tool: generate questions, variants, or tasks that test the indicators of the competencies.
           - The number of questions per variant/exam must match the parameters (e.g., 'control_questions_number' for test papers, 'test_questions_number' for exam/credit questions).
           - Populate them in the respective fields: 'test_paper', 'exam', 'credit', 'case_study', etc.
           - For unused/missing tools, set them to null (None).
        4. Format the final output strictly according to the OmdDataSchema.
        """
    )
    
    questions_critic = LlmAgent(
        name="QuestionsCritic",
        model="gemini-2.5-flash",
        instruction="""
        You are the QuestionsCriticAgent. Your job is to validate the generated questions in 'omd_json_data' against the parameters and the raw syllabus.
        
        Validation Checklist:
        1. Lesson Questions: Are questions generated for all activities? Do the counts match the requested numbers (seminar_questions_number, lab_questions_number)?
        2. Evaluation Tools: Are tasks and questions generated for all active evaluation tools (test_paper, exam, credit, case_study) and do their counts match the requested numbers?
        3. Criteria: Are the grading criteria populated?
        4. Preservation: Check that the original structural metadata (course name, code, competencies tables) was NOT altered or damaged.
        
        If everything is complete, correct, and matches parameters, CALL the 'exit_loop' tool.
        If there are missing questions, incorrect counts, or errors, provide a detailed critique.
        """,
        tools=[exit_loop]
    )
    
    questions_loop = LoopAgent(
        name="QuestionsGenerationLoop",
        sub_agents=[questions_generator, questions_critic],
        max_iterations=5,
    )
    
    runner = InMemoryRunner(agent=questions_loop)
    runner.auto_create_session = True
    session_id = f"questions_session_{project_name}"
    
    query = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Generate questions for project '{project_name}' based on the provided structure and parameters.\n\n"
            f"--- Parameters ---\n"
            f"{json.dumps(params, indent=2, ensure_ascii=False)}\n\n"
            f"--- Existing Structure (omd_json_data) ---\n"
            f"{json.dumps(omd_json_data, indent=2, ensure_ascii=False)}\n\n"
            f"--- Raw Syllabus Markdown Context (rpd_content) ---\n"
            f"{rpd_content}"
        ))],
    )
    
    state_delta = {
        "project_name": project_name,
        "rpd_content": rpd_content,
        "omd_json_data": omd_json_data,
        **{k: (int(v) if k.endswith("_number") else v) for k, v in params.items()},
    }
    
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
            
    # Fetch final state and update variables.yml
    session = await runner.session_service.get_session(app_name=runner.app_name, user_id="system_user", session_id=session_id)
    omd_json_data = session.state.get("omd_json_data", {})
    if not omd_json_data:
        raise RuntimeError("AI questions generation failed: omd_json_data is empty.")
        
    data = clean_dict_hyphenations(omd_json_data)
    data = clean_question_prefixes(data)
    
    with open(variables_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
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
    return res


# ── CLI & Main ────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="TimPlan Syllabus Processing CLI")
    parser.add_argument("--project", required=True, help="Project name (subdirectory in input/)")
    parser.add_argument("--step", choices=["parse", "extract_structure", "generate_questions", "generate_docx", "all"], default="all", help="Pipeline step to execute")
    parser.add_argument("--regenerate", action="store_true", help="Force regenerate files")
    
    # Parameters overrides
    defaults = load_env_defaults()
    for k in defaults.keys():
        parser.add_argument(f"--{k}", help=f"Override for parameter {k}")
        
    args = parser.parse_args()
    project_name = args.project
    step = args.step
    regenerate = args.regenerate
    
    proc_dir = os.path.join("processing", project_name)
    params = load_project_parameters(project_name, proc_dir, args)
    
    try:
        if step == "parse":
            run_parse_step(project_name, regenerate)
        elif step == "extract_structure":
            await run_extract_structure_step(project_name, params, regenerate)
        elif step == "generate_questions":
            await run_generate_questions_step(project_name, params, regenerate)
        elif step == "generate_docx":
            run_generate_docx_step(project_name, params, regenerate)
        elif step == "all":
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
