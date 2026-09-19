from pydantic import BaseModel, Field
from typing import List, Optional

class RpdIndicatorZUV(BaseModel):
    code: str = Field(..., description="Код индикатора, например: УК-1.1, ОПК-1.2")
    title: str = Field(..., description="Формулировка индикатора достижения компетенции")
    know: str = Field(..., description="Дескриптор 'Знать' (глубокие теоретические знания)")
    able: str = Field(..., description="Дескриптор 'Уметь' (прикладные умения и расчеты)")
    master: str = Field(..., description="Дескриптор 'Владеть' (методики, технологии, инструментарий)")

class RpdCompetencyZUV(BaseModel):
    num: str = Field(..., description="Порядковый номер компетенции, например: '1', '2'")
    code: str = Field(..., description="Код компетенции, например: УК-1, ОПК-6")
    title: str = Field(..., description="Формулировка компетенции")
    ind_first: RpdIndicatorZUV = Field(..., description="Первый индикатор компетенции")
    other_indicators: List[RpdIndicatorZUV] = Field(default_factory=list, description="Остальные индикаторы компетенции")

class RpdLessonItem(BaseModel):
    theme: str = Field(..., description="Код темы, например: 'Тема 1.1'")
    title: str = Field(..., description="Полное наименование занятия: 'Лекция № 1. Название' или 'Практическое занятие № 1. Название'")
    competencies: str = Field(..., description="Коды формируемых компетенций, например: 'УК-1, ОПК-1'")
    control: str = Field(..., description="Форма текущего контроля, например: 'Устный опрос', 'Защита практической работы', 'Тестирование'")
    hours: str = Field(..., description="Количество академических часов, например: '2' или '4'")

class RpdT4Section(BaseModel):
    num: str = Field(..., description="Номер раздела, например: '1'")
    title: str = Field(..., description="Наименование раздела дисциплины")
    lessons: List[RpdLessonItem] = Field(default_factory=list, description="Список лекций и практических занятий раздела")

class RpdDetailedTheme(BaseModel):
    title: str = Field(..., description="Название темы лекции с номером, например: 'Тема 1.1. Введение...'")
    text: str = Field(..., description="Краткое содержание / аннотация лекции (3-5 предложений)")

class RpdDetailedSection(BaseModel):
    title: str = Field(..., description="Наименование раздела")
    themes: List[RpdDetailedTheme] = Field(default_factory=list, description="Темы лекций данного раздела с аннотациями")

class RpdT5Theme(BaseModel):
    name: str = Field(..., description="Название темы СРС, например: 'Тема 1.1. ...'")
    questions: str = Field(..., description="Вопросы для самостоятельного изучения и подготовки к занятиям")

class RpdT5Section(BaseModel):
    num: str = Field(..., description="Номер раздела")
    title: str = Field(..., description="Наименование раздела")
    themes: List[RpdT5Theme] = Field(default_factory=list, description="Темы самостоятельной работы по разделу")

class RpdSectionOverview(BaseModel):
    name: str = Field(..., description="Наименование раздела, например: 'Раздел 1. Наименование'")
    lec: str = Field(..., description="Часы лекций по разделу")
    prac: str = Field(..., description="Часы практических занятий по разделу")
    srs: str = Field(..., description="Часы самостоятельной работы по разделу")
    total: str = Field(..., description="Всего часов по разделу")

class RpdCaseQuestion(BaseModel):
    label_num: str = Field(..., description="Номер вопроса, например: '1. '")
    text: str = Field(..., description="Текст аналитического или расчетного вопроса по кейсу")

class RpdCaseTask(BaseModel):
    num: str = Field(..., description="Номер кейса, например: '1'")
    title: str = Field(..., description="Название практического ситуационного кейса")
    case_desc: str = Field(..., description="Описание производственной/исследовательской ситуации с вводными параметрами")
    questions: List[RpdCaseQuestion] = Field(default_factory=list, description="Вопросы и расчетные задания к кейсу")

class RpdTestQuestion(BaseModel):
    label_num: str = Field(..., description="Номер вопроса, например: '1. '")
    question: str = Field(..., description="Текст тестового вопроса")
    a: str = Field(..., description="Вариант ответа А (с пометкой (+) если правильный)")
    b: str = Field(..., description="Вариант ответа Б (с пометкой (+) если правильный)")
    c: str = Field(..., description="Вариант ответа В (с пометкой (+) если правильный)")
    d: str = Field(..., description="Вариант ответа Г (с пометкой (+) если правильный)")

class RpdNumberedItem(BaseModel):
    label_num: str = Field(..., description="Номер, например: '1. '")
    text: str = Field(..., description="Текст вопроса или темы")

class RpdInteractiveItem(BaseModel):
    num: str = Field(..., description="Порядковый номер занятия в интерактивной форме, например: '1', '2'")
    theme: str = Field(..., description="Раздел и тема занятия (например: 'Раздел 1. Тема 1.1...')")
    form: str = Field(..., description="Форма проведения: 'Лекция' или 'Практикум' или 'Семинар'")
    tech: str = Field(..., description="Наименование используемых активных и интерактивных образовательных технологий (например: Проблемная лекция-дискуссия, Деловая игра, Мастер-класс и командный хакатон в QGIS, Питч-сессия проектов)")

class RpdSoftwareItem(BaseModel):
    num: str = Field(..., description="Номер, например: '1'")
    section: str = Field("Все разделы", description="Наименование раздела учебной дисциплины (модуля)")
    name: str = Field(..., description="Наименование программы (например: QGIS Desktop 3.28 LTR)")
    type: str = Field("Специализированное ПО", description="Тип программы (например: Геоинформационная система, Офисный пакет, СУБД)")
    author: str = Field("Разработчик ПО", description="Автор или организация-разработчик")
    year: str = Field("2024", description="Год разработки / релиза версии")
    license: Optional[str] = Field(None, description="Тип лицензии (Свободное ПО / Академическая лицензия / Включено в Единый реестр российских программ)")

class RpdContentSchema(BaseModel):
    course_purpose: str = Field(..., description="Цель освоения дисциплины (академическая формулировка уровня РГАУ-МСХА)")
    course_tasks: str = Field(..., description="Задачи дисциплины (4-5 нумерованных пунктов)")
    course_features_text: str = Field(..., description="Особенности дисциплины, продолжающие фразу 'Особенностью дисциплины является...' (например: 'ее практико-ориентированный характер...') строго БЕЗ слов 'Особенностью дисциплины является' или 'Дисциплина носит'")
    course_annotation_content: str = Field(..., description="Краткое содержание курса для аннотации (1-2 абзаца)")
    prerequisites_text: str = Field(..., description="Перечень предшествующих дисциплин через запятую строго БЕЗ вводных фраз 'Освоение дисциплины базируется на...' или 'Предшествующими курсами являются...'")
    postrequisites_text: str = Field(..., description="Перечень последующих дисциплин и практик через запятую строго БЕЗ вводных фраз 'Освоение дисциплины необходимо для...' или 'Последующими дисциплинами являются...'")
    corequisites_text: str = Field(..., description="Перечень параллельных дисциплин через запятую строго БЕЗ вводных фраз 'Параллельно изучаются...'")
    
    competencies_nested: List[RpdCompetencyZUV] = Field(..., description="Глубокая декомпозиция всех закрепленных компетенций на З-У-В: для каждого индикатора формулировать развернутые дескрипторы не менее 3 предложений с указанием нормативной базы, алгоритмов и ПО")
    
    sections: List[RpdSectionOverview] = Field(..., description="Динамический перечень N разделов дисциплины с распределением часов")
    detailed_sections: List[RpdDetailedSection] = Field(..., description="Содержание тем лекций по разделам (в каждом разделе 2-3 темы с развернутыми аннотациями по 4-6 предложений)")
    t4_sections: List[RpdT4Section] = Field(..., description="Таблица календарно-тематического плана (Таблица 4): в каждом разделе должно быть по 2-4 детальных лекционных и 2-4 практических занятия с академическими названиями, компетенциями, формами контроля и часами, сумма часов которых строго равна лекциям и практикам раздела")
    t5_sections: List[RpdT5Section] = Field(..., description="Самостоятельная работа студентов (Таблица 5): для каждого раздела 2-3 темы с развернутым перечнем 3-5 конкретных вопросов для самоподготовки и аналитических задач")
    interactive_items: List[RpdInteractiveItem] = Field(..., description="Перечень занятий в активной и интерактивной форме (Таблица 6): 4-6 разноплановых образовательных технологий (деловая игра, командный хакатон, проблемная дискуссия, питч-сессия проектов)")
    
    practical_works_list: List[RpdCaseTask] = Field(..., description="Ситуационные расчетные кейсы для практических работ (3-5 развернутых кейсов с реальным производственным контекстом предприятия, исходными параметрами и 3-4 расчетно-аналитическими подзадачами)")
    test_questions_list: List[RpdTestQuestion] = Field(..., description="Тестовые вопросы закрытого типа (12-15 вопросов с 4 вариантами ответов и маркером (+) у правильного)")
    oral_questions_list: List[RpdNumberedItem] = Field(..., description="Вопросы для устного опроса/собеседования (12-15 глубоких вопросов)")
    colloquium_questions_list: List[RpdNumberedItem] = Field(..., description="Темы для коллоквиумов/дискуссий (6-8 тем)")
    exam_credit_questions_list: List[RpdNumberedItem] = Field(..., description="Вопросы к промежуточной аттестации (зачет/экзамен, 20-25 вопросов)")
    individual_tasks_list: List[RpdNumberedItem] = Field(..., description="Темы индивидуальных заданий / расчетно-графических проектов (4-6 тем)")
    
    main_literature_list: List[str] = Field(..., description="Основная учебная литература строго из ЭБС 'Лань' (e.lanbook.com) и 'Юрайт' (urait.ru) 2020-2025 гг. со ссылками (3-4 учебника)")
    additional_literature_list: List[str] = Field(..., description="Дополнительная литература (монографии, статьи в профильных журналах, 3-4 наименования)")
    regulatory_acts_list: List[str] = Field(..., description="Нормативно-правовые акты РФ (ФЗ, профильные ГОСТы, СанПиНы, 5-7 актов)")
    software_items: List[RpdSoftwareItem] = Field(..., description="Специализированное профильное ПО (5-7 программ: ГИС, СУБД, языки геоанализа, офисные пакеты)")
    
    teacher_guidelines: str = Field(..., description="Развернутые методические указания преподавателю (2-3 абзаца)")
    student_guidelines: str = Field(..., description="Развернутые методические указания обучающимся (2-3 абзаца)")
    missed_classes_text: str = Field(..., description="Подробный регламент отработки пропущенных занятий")

