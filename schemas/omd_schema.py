from pydantic import BaseModel, Field
from typing import List, Optional

class CompetencyTable1Row(BaseModel):
    num: str = Field(..., description="Row index, e.g., '1.'")
    comp_code: str = Field(..., description="Code of the competency, e.g., 'ОПК-1'")
    stage: str = Field(..., description="Stage of competency formation in the course")
    eval_tool: str = Field(..., description="Evaluation tool name(s)")

class CompetencyTable2Row(BaseModel):
    num: str = Field(..., description="Row index, e.g., '1.'")
    comp_code: str = Field(..., description="Code of the competency, e.g., 'ОПК-1'")
    content: str = Field(..., description="Description of the competency content")
    indicators: str = Field(..., description="Indicators of the competency")
    know: str = Field(..., description="Knowledge descriptors ('знать')")
    umeti: str = Field(..., description="Skills descriptors ('уметь')")
    vladeti: str = Field(..., description="Abilities descriptors ('владеть')")

class CaseStudyTask(BaseModel):
    tasks: List[str] = Field(default_factory=list, description="List of case study tasks/questions")
    criteria: str = Field("", description="Grading criteria for case studies")

class ColloquiumSection(BaseModel):
    section_title: str = Field(..., description="Title of the topic/section")
    questions: List[str] = Field(default_factory=list, description="List of questions for this section")

class ColloquiumTask(BaseModel):
    sections: List[ColloquiumSection] = Field(default_factory=list, description="Colloquium sections and their questions")
    criteria: str = Field("", description="Grading criteria for colloquiums")

class TestPaperVariant(BaseModel):
    variant_name: str = Field(..., description="Variant name, e.g., 'Вариант 1'")
    tasks: List[str] = Field(default_factory=list, description="Tasks/questions for this variant")

class TestPaperTopic(BaseModel):
    topic_title: str = Field(..., description="Topic of the test paper")
    variants: List[TestPaperVariant] = Field(default_factory=list, description="Variants for this test paper")

class TestPaperTask(BaseModel):
    topics: List[TestPaperTopic] = Field(default_factory=list, description="Test paper topics and variants")
    criteria: str = Field("", description="Grading criteria for test papers")

class RoundTableTask(BaseModel):
    topics: List[str] = Field(default_factory=list, description="List of discussion topics")
    criteria: str = Field("", description="Grading criteria for round table discussions")

class PortfolioTask(BaseModel):
    portfolio_title: str = Field("", description="Title of the portfolio")
    structure: List[str] = Field(default_factory=list, description="Structure parts of the portfolio")
    criteria: str = Field("", description="Grading criteria for portfolio")

class RoleplayGame(BaseModel):
    title: str = Field(..., description="Title or topic of the roleplay game")
    concept: str = Field(..., description="Concept/scenario of the game")
    roles: List[str] = Field(default_factory=list, description="List of roles")
    expected_results: str = Field(..., description="Expected outcomes/results")

class RoleplayGameTask(BaseModel):
    games: List[RoleplayGame] = Field(default_factory=list, description="List of roleplay games")
    criteria: str = Field("", description="Grading criteria for roleplay games")

class CreativeProjectTask(BaseModel):
    group_projects: List[str] = Field(default_factory=list, description="Group creative tasks or projects")
    individual_projects: List[str] = Field(default_factory=list, description="Individual creative tasks or projects")
    criteria: str = Field("", description="Grading criteria for creative projects")

class MultiLevelTasks(BaseModel):
    reproductive: List[str] = Field(default_factory=list, description="Reproductive level tasks/questions")
    reconstructive: List[str] = Field(default_factory=list, description="Reconstructive level tasks/questions")
    creative: List[str] = Field(default_factory=list, description="Creative level tasks/questions")
    criteria: str = Field("", description="Grading criteria for multi-level tasks")

class RGRTask(BaseModel):
    tasks: List[str] = Field(default_factory=list, description="Calculation and graphic tasks (РГР)")
    criteria: str = Field("", description="Grading criteria for RGR")

class EssayTask(BaseModel):
    topics: List[str] = Field(default_factory=list, description="List of essay/report topics")
    criteria: str = Field("", description="Grading criteria for essays/reports")

class CourseWorkTask(BaseModel):
    topics: List[str] = Field(default_factory=list, description="List of coursework/project topics")
    criteria: str = Field("", description="Grading criteria for coursework")

class ExamCreditTask(BaseModel):
    questions: List[str] = Field(default_factory=list, description="Questions for credit or exam")
    criteria: str = Field("", description="Grading criteria for credit/exam")

class SyllabusActivity(BaseModel):
    num: str = Field(..., description="Lesson/activity number/identifier, e.g., 'Лекция №1', 'Практическое занятие №1'")
    theme: str = Field(..., description="Theme/topic of the lesson/activity")
    type: str = Field(..., description="Type of activity, e.g., 'Лекция' or 'Практическое занятие'")
    hours: int = Field(..., description="Number of academic hours for this activity")
    comp_code: str = Field(..., description="Codes of competencies developed during this activity, separated by semicolon")
    eval_tool: str = Field(..., description="Name of the evaluation tool used, e.g., 'Устный опрос', 'Решение задач'")
    questions: List[str] = Field(default_factory=list, description="Possible questions or tasks the teacher can use/ask during this activity")

class OmdDataSchema(BaseModel):
    # Header Metadata
    institute: str = Field(..., description="Name of the institute/department, e.g., 'Институт механики и энергетики'")
    department: str = Field(..., description="Name of the department, e.g., 'Кафедра тракторов и автомобилей'")
    course_code: str = Field(..., description="Course code, e.g., 'ФТД.01'")
    course_title: str = Field(..., description="Course title, e.g., 'Основы научных исследований'")
    degree_type: str = Field(..., description="Degree type, e.g., 'бакалавров' or 'магистров'")
    fgos_vo: str = Field(..., description="FGOS VO version/reference, e.g., 'ФГОС ВО 3++'")
    major_code: str = Field(..., description="Major code, e.g., '35.03.06'")
    major_title: str = Field(..., description="Major title, e.g., 'Экология и природопользование'")
    profile_title: str = Field(..., description="Profile/specialization title, e.g., 'Экология и устойчивое развитие'")
    course_year: str = Field(..., description="Course year number, e.g., '4' or '2'")
    semester: str = Field(..., description="Semester number, e.g., '7' or '8'")
    study_form: str = Field(..., description="Study form, e.g., 'очная' or 'заочная'")
    start_year: str = Field(..., description="Year of start of training, e.g., '2023'")
    developers: str = Field(..., description="Names and titles of developers, e.g., 'Морев Д.В., кандидат биол. наук'")
    reviewer: str = Field(..., description="Name and title of the reviewer, e.g., 'Иванов И.И., доктор наук'")
    
    # Target standard reference phrase
    rpd_reference_text: str = Field(..., description="Reference path/text for RPD matching, e.g., 'направлению подготовки 35.03.06 Экология и природопользование'")
    
    # Table 1, 2, 4
    table1: List[CompetencyTable1Row] = Field(default_factory=list, description="Table 1 rows mapping competencies to stages and tools")
    table2: List[CompetencyTable2Row] = Field(default_factory=list, description="Table 2 rows with competency requirements")
    activities: List[SyllabusActivity] = Field(default_factory=list, description="Table 4 activities/lessons list from the syllabus with their mapped questions")
    
    # Evaluation Tasks
    case_study: Optional[CaseStudyTask] = Field(None, description="Case study tasks and criteria")
    colloquium: Optional[ColloquiumTask] = Field(None, description="Colloquium questions and criteria")
    test_paper: Optional[TestPaperTask] = Field(None, description="Test paper variants and criteria")
    round_table: Optional[RoundTableTask] = Field(None, description="Round table topics and criteria")
    portfolio: Optional[PortfolioTask] = Field(None, description="Portfolio structure and criteria")
    roleplay: Optional[RoleplayGameTask] = Field(None, description="Roleplay games, roles and criteria")
    creative_project: Optional[CreativeProjectTask] = Field(None, description="Group/individual projects and criteria")
    multi_level_tasks: Optional[MultiLevelTasks] = Field(None, description="Reproductive, reconstructive and creative tasks and criteria")
    rgr: Optional[RGRTask] = Field(None, description="Calculation and graphic tasks (РГР) and criteria")
    essay: Optional[EssayTask] = Field(None, description="Essay topics and criteria")
    course_work: Optional[CourseWorkTask] = Field(None, description="Course work/project topics and criteria")
    credit: Optional[ExamCreditTask] = Field(None, description="Questions and criteria for credit (зачёт)")
    exam: Optional[ExamCreditTask] = Field(None, description="Questions and criteria for exam (экзамен)")
