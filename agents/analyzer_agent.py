from google.adk.agents import LlmAgent
from schemas.omd_schema import OmdDataSchema

# AnalyzerAgent parses rpd_content and saves structural JSON to omd_json_data
analyzer_agent = LlmAgent(
    name="AnalyzerAgent",
    model="gemini-2.5-flash",
    output_schema=OmdDataSchema,
    instruction="""
    You are the AnalyzerAgent. Your job is to read the raw syllabus Markdown content provided in the user input message
    and extract and structure all educational structure, course metadata, and evaluation tasks.
    
    Format the output strictly according to the OmdDataSchema Pydantic model.
    Instructions for extraction:
    1. Metadata:
       - Extract 'institute' and 'department' from the syllabus header/context.
       - Extract 'course_code' and 'course_title' from the syllabus text.
       - Extract 'degree_type' (e.g. 'бакалавров', 'специалистов' or 'магистров').
       - Extract 'fgos_vo' (e.g. 'ФГОС ВО' or 'ФГОС ВО 3++').
       - Extract 'major_code' (e.g. '35.03.06') and 'major_title' (e.g. 'Экология и природопользование').
       - Extract 'profile_title' (e.g. 'Экология и устойчивое развитие').
       - Extract 'course_year', 'semester', 'study_form', and 'start_year'.
       - Extract 'developers' and 'reviewer'. If none listed, suggest reasonable academic ones from the context.
       - For 'rpd_reference_text', construct a Russian phrase like: 'направлению подготовки 35.03.06 Экология и природопользование'.
          2. Table 1 & Table 2 & Table 4 Activities:
       - Table 1 MUST be topic-based. Generate one row for each topic in the curriculum schedule (e.g. "Тема 1. Введение базовые понятия языка R", "Тема 2. ...", etc.).
         - For each topic row, set 'num' to the sequential number (e.g., "1.", "2.", "3.").
         - Set 'comp_code' to the competency codes developed by this topic (e.g., "ПКос-1.7; ПКос-3.2"). Extract these exactly from the curriculum table where topics map to competencies. If there is more than one competency developed by a topic, join them with a semicolon.
         - Set 'stage' to the full topic name (e.g., "Тема 1. Введение базовые понятия языка R").
         - Set 'eval_tool' to the names of all assessment tools used for this topic, separated by a comma or semicolon (e.g., "Устный опрос, Решение задач").
       - Table 2 MUST contain the competency requirements. Extract all competencies and indicators (e.g., 'ПКос-1.7', 'ПКос-3.2') that are stated in the syllabus. Map each indicator to its corresponding content, indicator description, and knowledge ('знать'), skills ('уметь'), and abilities ('владеть') descriptors.
       - Extract Table 4 of the syllabus (activities/lessons schedule: Lectures / 'Лекции' and Practical classes / 'Практические занятия'):
         - Populate 'activities' list with all individual lessons/activities.
         - For each activity, extract its 'num' (e.g., 'Лекция №1', 'Практическое занятие №1'), 'theme', 'type' ('Лекция' or 'Практическое занятие'), 'hours', 'comp_code', and 'eval_tool'.
         - Locate the list of questions associated with this specific lesson/activity. If the syllabus contains fewer questions than requested in the user config parameters, generate additional high-quality relevant questions to match the configured number (e.g., seminar_questions_number for seminars/practicals, lab_questions_number for labs, etc.).
         
     3. Assessment Content & Curriculum-based Question Expansion:
        - Map all extracted activities and their questions to the 'colloquium' field:
          - Set 'colloquium.sections' to contain a list where 'section_title' is the full activity name (e.g., 'Лекция №1 Введение базовые понятия языка R' or 'Практическое занятие №1. Основы языка R') and 'questions' is the list of questions for that activity.
          - Set 'colloquium.criteria' to a comprehensive description of the grading criteria for oral questions/interviews (e.g., criteria for grades 5, 4, 3, 2).
        - Carefully understand the structure and requirements of the competencies (e.g. УК-1, ОПК-1, etc.) and their indicators (know, can, master).
        - Identify active/used evaluation task types (e.g. test_paper, credit, exam, case_study, round_table, portfolio, roleplay, creative_project, multi_level_tasks, rgr, essay, course_work, etc.) from the syllabus.
        - If an assessment type is active but the syllabus only provides brief, partial, placeholder, or incomplete examples:
          - You MUST build a complete, high-quality, comprehensive set of competency-based evaluation questions or tasks matching the number of questions requested for that activity type in the user config parameters (e.g. control_questions_number for test paper variants, test_questions_number for exam/credit questions, project_questions_number for projects, other_questions_number for others).
          - Make sure these generated tasks/questions directly test the specific competence indicators.
          - Ensure all generated questions are in professional academic Russian, highly relevant to the course content, and do not contain empty placeholders.
        - If an assessment type is entirely missing/unused in the syllabus, set its value strictly to null (or None). Do NOT generate any questions or tasks for unused assessment types.
        
     4. Text Cleaning and Hyphenation:
        - Crucially, clean up all word hyphenations by syllables (e.g. 'Вла- деть', 'гео- информацион- ных', 'исследова- ний', 'дан- ных') and formatting issues. Always merge syllables separated by hyphens and spaces into a single, clean word (e.g., 'Владеть', 'геоинформационных', 'исследований', 'данных'). Do not leave spaces or hyphens inside these words.
        
     Perform this extraction, cleaning, and expansion with high fidelity, preserving 100% of the educational requirements.
    """,
    output_key="omd_json_data"
)
