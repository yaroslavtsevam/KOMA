Act as a Senior Python and AI Solutions Architect. Build a production-ready automated reporting system that extracts data from source documents (PDF/DOCX) and generates a structured Word report (.docx) based on a pre-defined .docx template while preserving 100% of the template's original styling, fonts, and formatting.

### 1. Core Tech Stack Requirements:
- Orchestration & Agents: `google-adk` (Google Agent Development Kit). Do NOT use CrewAI, LangChain, or LangGraph.
- Parsing Engine: `docling` (by IBM) to convert input PDF/DOCX files into clean, structured Markdown.
- LLM Core: Google Gemini (via `google-genai` / Google AI Studio API), utilizing Structured Outputs (Pydantic schemas).
- Document Generation: `docxtpl` (Python Docx Template) to render data into an existing .docx template using Jinja2-like syntax. Do NOT use Typst or Pandoc.

### 2. Architecture & Workflow to Implement (Google ADK):
The system must be built using an ADK `SequentialAgent` containing a `LoopAgent` for quality control. Implement the following agent pipeline:

1. ParserAgent (LlmAgent):
   - Tool: `docling_parser_tool`. 
   - Function: Takes input files, runs them through Docling, extracts text and tables as Markdown, and saves the output to `session.state["raw_content"]`.

2. AnalysisQualityLoop (LoopAgent):
   - Sub-agent A: `AnalyzerAgent`. Reads `session.state["raw_content"]`. Uses Gemini with a Pydantic schema to extract key metrics, summaries, and tabular data into a strictly structured JSON object. Saves it to `session.state["extracted_json"]`.
   - Sub-agent B: `CriticAgent`. Validates `session.state["extracted_json"]` against the raw content. If fields are missing, hallucinated, or malformed, it requests a retry. If the data is 100% correct, it triggers `exit_loop`.

3. PublisherAgent (LlmAgent):
   - Tool: `docx_generator_tool`.
   - Function: Takes `session.state["extracted_json"]`, opens the provided `template.docx`, uses `docxtpl` to render the data into the placeholders, and saves the final file as `final_report.docx`.

### 3. Code Quality & Project Structure:
- Provide a clean, modular directory structure (e.g., `agents/`, `tools/`, `schemas/`, `main.py`).
- Implement robust error handling, especially for file I/O, Docling parsing, and JSON validation.
- Use environment variables for configuration (`GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI=FALSE`).
- Provide a clear `requirements.txt` file.
- Include a sample Pydantic schema for the data extraction step to demonstrate how Gemini should format the output.
- Write clean, self-documented Python code following PEP 8.

Generate the complete project implementation now.




Act as a Senior Python and AI Solutions Architect. Build a production-ready automated reporting system that extracts data from a Course Syllabus/Work Program (РПД) and generates a structured "Evaluation Materials" document (Оценочные материалы дисциплины - ОМД) in .docx format based on a pre-defined template, preserving 100% of the template's original styling.

### 1. Context & Files:
- Input File: `FTD.01_R_RPD_2022.pdf` (Contains course description, structural units, required competencies, themes, and examples of evaluation tasks).
- Template File: `ШАБЛОН ОМД.docx` (The master Word template with styles, tables, and headers that must be preserved).
- Output File: `FTD.01_R_OMD_Generated.docx`

### 2. Core Tech Stack Requirements:
- Orchestration & Agents: `google-adk` (Google Agent Development Kit). Do NOT use CrewAI, LangChain, or LangGraph.
- Parsing Engine: `docling` (by IBM) to convert the input PDF into clean, structured Markdown, accurately capturing complex educational tables (competency matrices, theme breakdowns).
- LLM Core: Google Gemini (via `google-genai` / Google AI Studio API), utilizing Structured Outputs (Pydantic schemas).
- Document Generation: `docxtpl` (Python Docx Template) to render data into `ШАБЛОН ОМД.docx` using Jinja2-like syntax. Do NOT use Typst or Pandoc.

### 3. Data Schema Specifications (Pydantic):
The system must extract and structure the following data from `FTD.01_R_RPD_2022.pdf` to match typical academic assessment standards:
- Course Metadata: Course title, department, code, competencies (ОК, ОПК, ПК codes and indicators).
- Course Structure: List of modules/topics mapped to assessment types.
- Assessment Content: Test questions, practical tasks, case studies, exam/credit questions (вопросы к зачету/экзамену), and evaluation criteria (критерии оценивания).

### 4. Architecture & Workflow to Implement (Google ADK):
Implement a sequential pipeline with an active quality-control loop:

1. ParserAgent (LlmAgent):
   - Tool: `docling_parser_tool`. 
   - Function: Parses `FTD.01_R_RPD_2022.pdf` via Docling, extracts text and tables as Markdown, and saves it to `session.state["rpd_content"]`.

2. AnalysisQualityLoop (LoopAgent):
   - Sub-agent A (AnalyzerAgent): Reads `session.state["rpd_content"]`. Uses Gemini with the defined Pydantic schema to extract course structure and evaluation tasks into a strict JSON object. Saves it to `session.state["omd_json_data"]`.
   - Sub-agent B (CriticAgent): Validates `session.state["omd_json_data"]`. Ensures all evaluation materials, questions, and criteria from the PDF are fully extracted without omissions or hallucinations. Triggers `exit_loop` only when data is 100% complete.

3. PublisherAgent (LlmAgent):
   - Tool: `docx_generator_tool`.
   - Function: Takes `session.state["omd_json_data"]`, loads `ШАБЛОН ОМД.docx`, runs `docxtpl` to populate the template fields and dynamic tables, and exports the final file as `FTD.01_R_OMD_Generated.docx`.

### 5. Project Deliverables:
- Modular project structure (`agents/`, `tools/`, `schemas/`, `main.py`).
- Robust error handling for complex PDF parsing and JSON validation.
- `requirements.txt` with exact dependencies.
- A draft of the Pydantic schema representing the OMD educational data structure.

Generate the complete project implementation now.



Result can not be accepted. Implementation plan should be updated according to foloowing comments:

I want more control on all stages of processing. For that make "input" folder, where sources should be placed in subfolder. Name of this subfolder will be "project name" for all further steps. Results of all further steps will be stored in "processing" folder in subfolder named after "project name". This intermediate results should include markdown files produced by docling parsing and processed templates for docx generation. Final result should be stored in folder "results" in subfolder named according to "project name".
Also in given template all colored text (including background color)are comments and example, it should be removed or used as palceholder for generated content.

Generated assesment should carefully follow the curiculum structure and requirements, including competency-based questions.

That mean that LLM should not only extract the text but also understand the structure and requirements of the curriculum and build assesment materials accordingly. If any info is missing in PDF it should be clearly stated in the final document as not provided.



Result is still absent. Lets focus on generating proper docx template [FTD.01_R_RPD_2022_annotated.docx](file;file:///Users/godfreyspencer/Downloads/TimPlanningDocling/processing/FTD.01_R_RPD_2022/FTD.01_R_RPD_2022_annotated.docx). For you proper understanding I have added file with proper filled assesment [OMD_example.docx](file;file:///Users/godfreyspencer/Downloads/TimPlanningDocling/OMD_example.docx). Task is more complicated than your approach. First of all syllabus have clear list of "Компетенции" which student should develop during the course. It is clear stated in text and it should be extracted [FTD.01_R_RPD_2022_parsed.md](file;file:///Users/godfreyspencer/Downloads/TimPlanningDocling/processing/FTD.01_R_RPD_2022/FTD.01_R_RPD_2022_parsed.md) and saved as separate table for further use. All of this "Компетенции" should be listed in Table 1. Besides that the logic of Table 1 forming is based on syllabys topic, so each row generated according to topic and {{ item.comp_code }} added acording to what "Компетенции" can be developed by student with this topic, there could be more than one, for each topic



Great we have a big progress, but first we should again fix  some issues. I gave you [OMD_example.docx](file;file:///Users/godfreyspencer/Downloads/TimPlanningDocling/OMD_example.docx)  as example, but now you rewrited this file and it is content lost. Now I dont understand what file are you using as template. Lets make it more clear final product should produce assesment document accorrding to just syllabys file. So template for assessment should be universal and project independent and kept in "templates" folder. All templates from input and processing folders should be removed. Next I want more transparency and in progress folder should be more functional parts from parsed syllabus. Besides competencies you should extract with docling table 4 where you have full list of activities(lessons) and their type - for each lesson full list of possible question which teacher can use druing should be listed in OMD doucument. Finally styling - it is horrible use given    template( ШАБЛОН) file only as  structural example, all docx styling should be taken from example. Also I added new copy of example [OMD_example_readonly.docx](file;file:///Users/godfreyspencer/Downloads/TimPlanningDocling/OMD_example_readonly.docx) , use it, but please dont ruin


Great we have some progress. Lets focus on assessment criteria. First, for each project, subfolder "criteria_tables" should be created where tables with assesment criterias should be stored in separate .md files. Assessment criteria tables should be made according to example tables 3 & 13 in [OMD_example_readonly.docx](file;file:///Users/godfreyspencer/Downloads/TimPlanningDocling/OMD_example_readonly.docx). Assessment criteria tables should be created for each activity/lesson type and added to resulting document after all questions of this typeWS

Code for generating tables (especially competetncies) should be updated to fix problems with hyphenation of words by syllables and also other formatting problems.For example "Вла- деть основными методами гео- информацион- ных исследова- ний, геостати- стической и ста- тистической обработки дан- ных в экологии и природополь- зовании с при- менением циф- ровых инстру- ментов и техно- логий " should be written as "Владеть основными методами геоинформационных исследований, геостатистической и статистической обработки данных в экологии и природопользовании с применением цифровых инструментов и технологий"

For each project parameters.env should be generated, where user can set parameters for project. User can use default parameters or create their own. Default parameters are stored in .env.default file. Variables in .env file should be used by the program to set parameters for the project. Only parameters which user explicitly changed in .env file should be different from default ones. It should be clearly stated in .env file which parameters are default and which are user set. If .env file is missing, it should be generated from .env.default file. Variables in .env file should not be overriden when regenerating. When generating a new project with the same name, the user's .env file should be preserved. The program should check for the presence of .env file at the beginning of the program and if it is missing, generate it from .env.default file. List of variables in parameters.env:
  - course_type: "профессиональное обучение" or "дополнительное профессиональное образование"
  - hours: number of hours
  - year_of_study_start: starting year of education, format 2023
  - seminar_questions_number: number of questions for each type of seminar activity
  - control_questions_number: number of questions for each type of control activity
  - test_questions_number: number of questions for each type of test activity
  - lab_questions_number: number of questions for each type of lab activity
  - project_questions_number: number of questions for each type of project activity
  - other_questions_number: number of questions for each type of other activity

Template should be updated:
  - On title page - "Направление/специальность" only one should be left according to type of course in syllabus
  - On title page - "Направленность/специализация" only one should be left according to type of course in syllabus
  - On title page - "Год начала подготовки: [YEAR]" should be updated according to year_of_study_start parameter
  - On second page - Оценочные материалы обсуждены на заседании кафедры Кафедра Экологии should be updated according to syllabus  in the proper fields. Оценочные материалы обсуждены на заседании кафедры: {cathedra_name} "
  - On second page - "протокол № __ от «__» ___________ 2020__г." should be change to  "протокол № __ от «__» ___________ {cathedra_meeting_year}г."
  - All activities which is not present in syllabus should be presented in document. But the possibility to produce them should be left in code, so it will be generated if presented in syllabus. Example there is no project activity in syllabus, but it is present in document. So it should be removed from document, but the possibility to produce it should be left in code.
  - "Вопросы к зачёту/зачёту с оценкой" only one should be left according to type of test in syllabus: "зачёт" or "зачёт с оценкой"
  - In review part("РЕЦЕНЗИЯ"), "квалификация  выпускника – бакалавр/специалист/магистр" should be updated according to syllabus: "бакалавр", "специалист" or "магистр"
  - In review part("РЕЦЕНЗИЯ"), subpbart - "ОБЩИЕ ВЫВОДЫ" should be updated according to syllabus, proper course id, course name and specialisation   

Update to overall functioning:
  - If in processing folder there are already folder with name of current project and it has some files, script should check what files are already generated and generate only the ones wheach left. But if in folder .env file is present and it has parameter "regenerate" set to true, script should regenerate all files. Documents in "results" folder always regenerated.
  
Template still needs some updates:
 - On title page - "ДИСЦИПЛИНЫ (МОДУЛЯ)" should be "ДИСЦИПЛИНЫ" or "МОДУЛЯ" depending on syllabus
 - Every type of activity (for example - "Вопросы к лекционным занятиям (устный опрос):") should be bold and aligned left
 - Every activity in each type of activity (for example - "Лекция №1. Введение базовые понятия языка R.") should be bold and aligned left
 - List of questions in each type of activity should formated as simple numbered list. The text of the question should not have any numbering. 
