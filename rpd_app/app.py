#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Веб-приложение генерации рабочих программ дисциплин (РПД)
на базе NiceGUI для РГАУ-МСХА имени К.А. Тимирязева.

Пошаговый мастер (Wizard):
1. Загрузка учебного плана (.plx.pdf / .pdf) и выбор дисциплины
2. Подтверждение метаданных образовательной программы
3. Подтверждение параметров дисциплины и баланса часов
4. Подтверждение матрицы компетенций и дескрипторов (Таблица 1)
5. Подтверждение тематического плана, разработчиков и литературы
6. Генерация комплекта файлов (teach_plan/, template/, DOCX) и прямое скачивание
"""

import os
import sys
import shutil
import json
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nicegui import ui, app, events

from rpd_app.core.curriculum_parser import CurriculumParser
from rpd_app.core.course_presets import (
    get_preset_for_environmental_digital_tech,
    build_generic_context_from_parsed
)
from rpd_app.core.docx_generator import generate_rpd, validate_rpd_document

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_PATH = BASE_DIR / "rpd_app" / "data" / "rpd_template_parametrized.docx"
UPLOAD_DIR = BASE_DIR / "rpd_app" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Предустановленные учебные планы в проекте
PRESET_PLANS = {
    "21.04.02 Землеустройство и кадастры (магистратура, 2026 г.)": str(
        BASE_DIR / "RPD-research" / "цифровые технологии в природоохранной деятельности на предприятии" / "Учебные_планы" / "21.04.02_Zemleustroistvo_i_kadastry_(mag.)_CTvZA_2026.plx.pdf"
    ),
    "05.03.06 Экология и природопользование (бакалавриат, 2026 г.)": str(
        BASE_DIR / "RPD-research" / "инновационные технологии в экологии и агроэкологии" / "Учебные_планы" / "05.03.06_Ekologia_i_prirodopolzovanie_EMiA_2026.plx.pdf"
    )
}


class RpdAppState:
    """Хранилище состояния сессии генератора."""
    def __init__(self):
        self.plan_path = None
        self.parser = None
        self.all_disciplines = []
        self.selected_code = ""
        self.selected_name = ""
        
        # Основные словари данных
        self.meta = {}
        self.disc = {}
        self.comps = []
        self.coreqs = []
        
        # Полный рабочий контекст (все 121 переменная)
        self.context = {}
        
        # Выходные параметры
        self.output_folder = ""
        self.generated_docx = ""
        self.validation_result = {}


@ui.page('/')
def index():
    state = RpdAppState()

    # Стилизация заголовка страницы
    ui.add_head_html("""
    <style>
        body { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif; background-color: #f8fafc; }
        .academic-card { background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }
        .timacad-header { background: linear-gradient(135deg, #104e28 0%, #166534 100%); color: white; }
    </style>
    """)

    with ui.header().classes('timacad-header px-8 py-4 flex justify-between items-center shadow-md'):
        with ui.row().classes('items-center gap-4'):
            ui.icon('school', size='2.5rem').classes('text-white')
            with ui.column().classes('gap-0'):
                ui.label('РГАУ-МСХА имени К.А. Тимирязева').classes('text-xs uppercase tracking-wider text-green-200 font-semibold')
                ui.label('Интеллектуальный генератор РПД').classes('text-xl font-bold text-white')
        ui.badge('Версия 2.0 • 14 правил верстки', color='green-8').classes('text-sm px-3 py-1 font-medium')

    with ui.column().classes('w-full max-w-6xl mx-auto py-6 px-4 gap-6'):

        with ui.stepper().props('vertical animated header-nav').classes('w-full') as stepper:

            # -------------------------------------------------------------
            # ШАГ 1: Загрузка плана и выбор курса
            # -------------------------------------------------------------
            with ui.step('1. Учебный план и дисциплина', icon='folder_open'):
                ui.label('Шаг 1. Загрузка учебного плана и выбор целевой дисциплины').classes('text-lg font-bold text-gray-800')
                ui.label('Загрузите файл учебного плана (.plx.pdf или .pdf) или выберите из готовых образцов:').classes('text-sm text-gray-500 mb-2')

                plan_select = ui.select(
                    label='Готовые учебные планы в проекте',
                    options=list(PRESET_PLANS.keys()),
                    value="21.04.02 Землеустройство и кадастры (магистратура, 2026 г.)"
                ).classes('w-full mb-4')

                def handle_upload(e: events.UploadEventArguments):
                    uploaded_file = UPLOAD_DIR / e.name
                    with open(uploaded_file, 'wb') as f:
                        f.write(e.content.read())
                    state.plan_path = str(uploaded_file)
                    ui.notify(f'Файл {e.name} успешно загружен', color='positive')
                    parse_plan(state.plan_path)

                ui.upload(
                    label='Или перетащите новый файл плана (.plx.pdf / .pdf)',
                    auto_upload=True,
                    on_upload=handle_upload
                ).props('accept=.pdf,.plx.pdf').classes('w-full mb-4')

                disc_select = ui.select(
                    label='Целевая дисциплина учебного плана',
                    options=[],
                    with_input=True
                ).classes('w-full mb-4')

                disc_summary = ui.card().classes('w-full bg-slate-50 p-4 border border-slate-200 hidden')

                def parse_plan(plan_path):
                    try:
                        state.plan_path = plan_path
                        state.parser = CurriculumParser(plan_path)
                        state.meta = state.parser.extract_metadata()
                        state.all_disciplines = state.parser.list_disciplines()

                        options = {d["code"]: f"{d['code']} — {d['name']}" for d in state.all_disciplines}
                        disc_select.options = options
                        
                        # По умолчанию выбираем "Цифровые технологии" или первую
                        default_code = None
                        for code, label in options.items():
                            if "цифров" in label.lower() and "природоохран" in label.lower():
                                default_code = code
                                break
                        if not default_code and options:
                            default_code = list(options.keys())[0]

                        disc_select.value = default_code
                        on_discipline_chosen(default_code)
                        ui.notify(f"План прочитан: найдено дисциплин: {len(state.all_disciplines)}", color='info')
                    except Exception as err:
                        ui.notify(f"Ошибка парсинга плана: {err}", color='negative')

                def on_discipline_chosen(code):
                    if not code or not state.parser:
                        return
                    try:
                        name = ""
                        for d in state.all_disciplines:
                            if d["code"] == code:
                                name = d["name"]
                                break
                        state.selected_code = code
                        state.selected_name = name

                        # Извлечение параметров дисциплины
                        state.disc = state.parser.extract_discipline_details(name or code)
                        state.coreqs = state.parser.extract_corequisites(state.disc["semesters"][0], code)
                        state.comps = state.parser.extract_competency_details(state.disc.get("competency_codes", []))

                        # Проверка: есть ли специализированный готовый пресет
                        if "цифровые технологии" in name.lower() and "природоохран" in name.lower():
                            state.context = get_preset_for_environmental_digital_tech()
                        else:
                            state.context = build_generic_context_from_parsed(state.meta, state.disc, state.comps, state.coreqs)

                        # Обновление сводной карточки
                        disc_summary.clear()
                        disc_summary.classes(remove='hidden')
                        with disc_summary:
                            ui.label(f"Дисциплина: {code} {name}").classes('font-bold text-gray-800')
                            ui.label(f"Семестр: {state.disc['semesters'][0]} (Курс {state.disc['course_year']}) • Трудоемкость: {state.disc['ze']} з.е. ({state.disc['hours_total']} ч.) • Форма контроля: {state.disc['control_form']}").classes('text-sm text-gray-600')
                            ui.label(f"Компетенции: {', '.join(state.disc.get('competency_codes', []))}").classes('text-xs text-green-700 font-semibold')
                    except Exception as err:
                        ui.notify(f"Ошибка загрузки дисциплины: {err}", color='negative')

                disc_select.on_value_change(lambda e: on_discipline_chosen(e.value))

                def on_plan_select_change(e):
                    if e.value in PRESET_PLANS:
                        parse_plan(PRESET_PLANS[e.value])

                plan_select.on_value_change(on_plan_select_change)

                # Инициализация первого плана
                if plan_select.value:
                    parse_plan(PRESET_PLANS[plan_select.value])

                with ui.stepper_navigation():
                    ui.button('Далее: Метаданные программы', on_click=stepper.next).props('color=green-8')

            # -------------------------------------------------------------
            # ШАГ 2: Метаданные образовательной программы
            # -------------------------------------------------------------
            with ui.step('2. Метаданные и титул', icon='badge'):
                ui.label('Шаг 2. Подтверждение метаданных образовательной программы').classes('text-lg font-bold text-gray-800')
                ui.label('Проверьте и при необходимости скорректируйте параметры титульного листа:').classes('text-sm text-gray-500 mb-2')

                with ui.grid(columns=2).classes('w-full gap-4'):
                    in_dir_code = ui.input('Код направления', value='').classes('w-full')
                    in_dir_name = ui.input('Наименование направления', value='').classes('w-full')
                    in_profile = ui.input('Направленность (профиль)', value='').classes('w-full')
                    in_qual = ui.select(options=['магистр', 'бакалавр', 'специалист'], label='Квалификация', value='магистр').classes('w-full')
                    in_inst = ui.input('Институт', value='').classes('w-full')
                    in_dept = ui.input('Кафедра-разработчик', value='').classes('w-full')
                    in_dept_head = ui.input('Заведующий кафедрой (ФИО, статус)', value='').classes('w-full')
                    in_year = ui.input('Год набора / Учебный год', value='2026').classes('w-full')

                def sync_step2_to_ui():
                    in_dir_code.value = state.context.get("direction_code", "")
                    in_dir_name.value = state.context.get("direction_name", "")
                    in_profile.value = state.context.get("profile", "")
                    in_qual.value = state.context.get("qualification", "магистр")
                    in_inst.value = state.context.get("institute", "")
                    in_dept.value = state.context.get("department", "")
                    in_dept_head.value = f"{state.context.get('department_head_status', '')} {state.context.get('department_head_fio', '')}".strip()
                    in_year.value = str(state.context.get("start_year", "2026"))

                def save_step2_to_context():
                    state.context["direction_code"] = in_dir_code.value
                    state.context["direction_name"] = in_dir_name.value
                    state.context["profile"] = in_profile.value
                    state.context["qualification"] = in_qual.value
                    state.context["qualification_plural"] = "магистров" if in_qual.value == "магистр" else "бакалавров"
                    state.context["institute"] = in_inst.value
                    state.context["department"] = in_dept.value
                    state.context["start_year"] = in_year.value
                    state.context["current_year"] = in_year.value
                    stepper.next()

                ui.button('Синхронизировать с извлеченными данными', on_click=sync_step2_to_ui).props('flat color=primary').classes('mb-2')

                with ui.stepper_navigation():
                    ui.button('Назад', on_click=stepper.previous).props('flat')
                    ui.button('Подтвердить и далее', on_click=save_step2_to_context).props('color=green-8')

            # -------------------------------------------------------------
            # ШАГ 3: Параметры дисциплины и баланс часов
            # -------------------------------------------------------------
            with ui.step('3. Трудоемкость и часы', icon='schedule'):
                ui.label('Шаг 3. Подтверждение трудоемкости и распределения часов').classes('text-lg font-bold text-gray-800')
                ui.label('Баланс часов: Лекции + Практика + Лаб + СРС + Контроль = Всего часов').classes('text-sm text-gray-500 mb-2')

                with ui.grid(columns=3).classes('w-full gap-4'):
                    in_code = ui.input('Код дисциплины', value='').classes('w-full')
                    in_name = ui.input('Название дисциплины', value='').classes('w-full col-span-2')
                    in_sem = ui.number('Семестр', value=4, min=1, max=12).classes('w-full')
                    in_year_calc = ui.input('Курс (расчетный)', value='2').props('readonly').classes('w-full')
                    in_control = ui.select(options=['зачет с оценкой', 'экзамен', 'зачет'], label='Форма контроля', value='зачет с оценкой').classes('w-full')
                    in_zet = ui.number('ЗЕТ (зачетных единиц)', value=3, min=1, max=20).classes('w-full')
                    in_total = ui.number('Всего часов', value=108).classes('w-full')
                    in_lec = ui.number('Лекции (час)', value=12).classes('w-full')
                    in_prac = ui.number('Практические (час)', value=12).classes('w-full')
                    in_lab = ui.number('Лабораторные (час)', value=0).classes('w-full')
                    in_srs = ui.number('СРС (час)', value=83.65).classes('w-full')
                    in_kra = ui.number('Контроль / КРА (час)', value=0.35).classes('w-full')

                balance_badge = ui.badge('Баланс часов: 108.0 ч. (100% сходимость)', color='positive').classes('text-sm py-1 px-3 mt-2')

                def check_balance():
                    total = (in_lec.value or 0) + (in_prac.value or 0) + (in_lab.value or 0) + (in_srs.value or 0) + (in_kra.value or 0)
                    target = in_total.value or (in_zet.value * 36 if in_zet.value else 108)
                    diff = round(total - target, 2)
                    if abs(diff) < 0.01:
                        balance_badge.set_text(f'Баланс часов сошелся: {total} ч. из {target} ч.')
                        balance_badge.props('color=positive')
                    else:
                        balance_badge.set_text(f'Внимание: расхождение баланса часов: {total} ч. из {target} ч. (разница: {diff:+} ч.)')
                        balance_badge.props('color=negative')

                for field in [in_lec, in_prac, in_lab, in_srs, in_kra, in_total]:
                    field.on_value_change(lambda e: check_balance())

                def on_sem_change(e):
                    if e.value:
                        in_year_calc.value = str((int(e.value) + 1) // 2)

                in_sem.on_value_change(on_sem_change)

                def sync_step3_to_ui():
                    in_code.value = state.context.get("course_code", "")
                    in_name.value = state.context.get("course_name", "")
                    in_sem.value = int(state.context.get("semester", 4))
                    in_year_calc.value = str(state.context.get("course_year", 2))
                    in_control.value = state.context.get("control_form", "зачет с оценкой")
                    in_zet.value = int(state.context.get("total_zet", 3))
                    in_total.value = float(str(state.context.get("total_hours", 108)).replace(',', '.'))
                    in_lec.value = float(str(state.context.get("lecture_hours", 12)).replace(',', '.'))
                    in_prac.value = float(str(state.context.get("practical_hours", 12)).replace(',', '.'))
                    in_lab.value = float(str(state.context.get("lab_hours", 0) or 0).replace(',', '.'))
                    in_srs.value = float(str(state.context.get("srs_hours", 83.65)).replace(',', '.'))
                    in_kra.value = float(str(state.context.get("kra_hours", 0.35)).replace(',', '.'))
                    check_balance()

                def save_step3_to_context():
                    state.context["course_code"] = in_code.value
                    state.context["course_name"] = in_name.value
                    state.context["semester"] = str(in_sem.value)
                    state.context["course_year"] = str((int(in_sem.value) + 1) // 2)
                    state.context["semester_phrase"] = f"{in_sem.value} семестре"
                    state.context["control_form"] = in_control.value
                    state.context["control_form_genitive"] = "зачета с оценкой" if "оценк" in in_control.value else ("экзамена" if "экзамен" in in_control.value else "зачета")
                    state.context["control_phrase"] = f"{in_control.value} в {in_sem.value} семестре"
                    state.context["total_zet"] = str(in_zet.value)
                    state.context["total_hours"] = str(in_total.value).rstrip('0').rstrip('.')
                    state.context["lecture_hours"] = str(in_lec.value).rstrip('0').rstrip('.')
                    state.context["practical_hours"] = str(in_prac.value).rstrip('0').rstrip('.')
                    state.context["lab_hours"] = str(in_lab.value).rstrip('0').rstrip('.') if in_lab.value else ""
                    state.context["contact_auditory_hours"] = str(int((in_lec.value or 0) + (in_prac.value or 0)))
                    state.context["contact_hours"] = str(round((in_lec.value or 0) + (in_prac.value or 0) + (in_kra.value or 0), 2)).replace('.', ',')
                    state.context["srs_hours"] = str(in_srs.value).replace('.', ',')
                    state.context["srs_self_hours"] = str(in_srs.value).replace('.', ',')
                    state.context["kra_hours"] = str(in_kra.value).replace('.', ',')
                    
                    # Синхронизация столбцов Таблицы 2
                    state.context["sem_1_hdr"] = f"№{in_sem.value}"
                    state.context["sem_1_total_hours"] = state.context["total_hours"]
                    state.context["sem_1_contact_hours"] = state.context["contact_hours"]
                    state.context["sem_1_contact_auditory_hours"] = state.context["contact_auditory_hours"]
                    state.context["sem_1_lecture_hours"] = state.context["lecture_hours"]
                    state.context["sem_1_practical_hours"] = state.context["practical_hours"]
                    state.context["sem_1_lab_hours"] = state.context["lab_hours"]
                    state.context["sem_1_kra_hours"] = state.context["kra_hours"]
                    state.context["sem_1_srs_hours"] = state.context["srs_hours"]
                    state.context["sem_1_srs_self_hours"] = state.context["srs_self_hours"]

                    stepper.next()

                ui.button('Синхронизировать с извлеченными данными', on_click=sync_step3_to_ui).props('flat color=primary').classes('mb-2')

                with ui.stepper_navigation():
                    ui.button('Назад', on_click=stepper.previous).props('flat')
                    ui.button('Подтвердить и далее', on_click=save_step3_to_context).props('color=green-8')

            # -------------------------------------------------------------
            # ШАГ 4: Компетенции и индикаторы (Таблица 1)
            # -------------------------------------------------------------
            with ui.step('4. Компетенции и З-У-В', icon='assignment_turned_in'):
                ui.label('Шаг 4. Матрица компетенций и индикаторы (Таблица 1)').classes('text-lg font-bold text-gray-800')
                ui.label('Декомпозиция индикаторов на дескрипторы Знать, Уметь, Владеть для альбомной Таблицы 1:').classes('text-sm text-gray-500 mb-2')

                comps_container = ui.column().classes('w-full gap-4')

                def render_comps_editor():
                    comps_container.clear()
                    nested = state.context.get("competencies_nested", [])
                    with comps_container:
                        for comp in nested:
                            with ui.expansion(f"{comp['code']}: {comp['title']}", icon='verified').classes('w-full bg-white border border-slate-200 rounded-lg'):
                                ui.label(f"Код: {comp['code']}").classes('font-bold text-green-900')
                                if comp.get("ind_first"):
                                    ind = comp["ind_first"]
                                    with ui.card().classes('w-full bg-slate-50 p-3 mb-2 border border-slate-200'):
                                        ui.label(f"Индикатор: {ind['code']} — {ind.get('title', '')}").classes('font-semibold text-slate-800')
                                        ui.input('Знать', value=ind.get('know', '')).classes('w-full text-xs')
                                        ui.input('Уметь', value=ind.get('able', '')).classes('w-full text-xs')
                                        ui.input('Владеть', value=ind.get('master', '')).classes('w-full text-xs')
                                for oind in comp.get("other_indicators", []):
                                    with ui.card().classes('w-full bg-slate-50 p-3 mb-2 border border-slate-200'):
                                        ui.label(f"Индикатор: {oind['code']} — {oind.get('title', '')}").classes('font-semibold text-slate-800')
                                        ui.input('Знать', value=oind.get('know', '')).classes('w-full text-xs')
                                        ui.input('Уметь', value=oind.get('able', '')).classes('w-full text-xs')
                                        ui.input('Владеть', value=oind.get('master', '')).classes('w-full text-xs')

                ui.button('Обновить список компетенций', on_click=render_comps_editor).props('flat color=primary').classes('mb-2')

                with ui.stepper_navigation():
                    ui.button('Назад', on_click=stepper.previous).props('flat')
                    ui.button('Подтвердить и далее', on_click=stepper.next).props('color=green-8')

            # -------------------------------------------------------------
            # ШАГ 5: Тематический план, разработчики и литература
            # -------------------------------------------------------------
            with ui.step('5. Тематический план и авторы', icon='menu_book'):
                ui.label('Шаг 5. Тематический план, разработчики и обеспечение курса').classes('text-lg font-bold text-gray-800')
                
                with ui.tabs().classes('w-full') as tabs:
                    t_sec = ui.tab('Разделы курса (Таблица 3)')
                    t_dev = ui.tab('Разработчики')
                    t_lit = ui.tab('Литература и ПО')

                with ui.tab_panels(tabs, value=t_sec).classes('w-full'):
                    with ui.tab_panel(t_sec):
                        sections_container = ui.column().classes('w-full gap-2')
                        def render_sections():
                            sections_container.clear()
                            with sections_container:
                                for s in state.context.get("sections", []):
                                    with ui.row().classes('w-full items-center justify-between p-2 bg-slate-50 border rounded'):
                                        ui.label(s["name"]).classes('font-medium text-sm flex-1')
                                        ui.badge(f"Лек: {s.get('lec', 0)} ч.").props('color=blue-7')
                                        ui.badge(f"Прак: {s.get('prac', 0)} ч.").props('color=teal-7')
                                        ui.badge(f"СРС: {s.get('srs', 0)} ч.").props('color=amber-8')
                        render_sections()

                    with ui.tab_panel(t_dev):
                        ui.label('Разработчики рабочей программы:').classes('font-semibold text-gray-700')
                        with ui.column().classes('w-full gap-2'):
                            for dev in state.context.get("developers_list", []):
                                ui.input(f"{dev.get('label', 'Разработчик')}: Должность", value=dev.get('position', '')).classes('w-full')
                                ui.input('ФИО, ученая степень', value=dev.get('fio_rank', '')).classes('w-full')

                    with ui.tab_panel(t_lit):
                        ui.label('Основная литература (из ЭБС Лань / Юрайт):').classes('font-semibold text-gray-700')
                        for lit in state.context.get("main_literature_list", []):
                            ui.label(f"• {lit}").classes('text-xs text-gray-700 mb-1')
                        ui.label('Используемое программное обеспечение:').classes('font-semibold text-gray-700 mt-2')
                        for sw in state.context.get("software_items", []):
                            ui.label(f"• {sw.get('name')} ({sw.get('license')})").classes('text-xs text-gray-600')

                with ui.stepper_navigation():
                    ui.button('Назад', on_click=stepper.previous).props('flat')
                    ui.button('Перейти к финальной генерации', on_click=stepper.next).props('color=green-8')

            # -------------------------------------------------------------
            # ШАГ 6: Генерация и скачивание
            # -------------------------------------------------------------
            with ui.step('6. Генерация РПД', icon='download_for_offline'):
                ui.label('Шаг 6. Финальная проверка, генерация структуры и экспорт').classes('text-lg font-bold text-gray-800')
                ui.label('Все параметры подтверждены. Нажмите кнопку ниже для создания комплекта файлов:').classes('text-sm text-gray-500 mb-4')

                # Карточка параметров
                with ui.card().classes('w-full bg-slate-50 border border-slate-200 p-4 mb-4'):
                    summary_label = ui.markdown('**Готовность к генерации:** Все параметры извлечены и согласованы.')

                folder_input = ui.input(
                    'Папка для сохранения комплекта данных и РПД',
                    value=str(BASE_DIR / "RPD-research" / "цифровые технологии в природоохранной деятельности на предприятии")
                ).classes('w-full mb-4')

                progress_bar = ui.linear_progress(value=0).classes('w-full mb-4 hidden')
                status_label = ui.label('').classes('text-sm font-semibold text-gray-700 mb-4')
                download_btn = ui.button('Скачать итоговый DOCX', icon='download').props('color=green-8 size=lg').classes('hidden mb-4')

                def do_generate():
                    try:
                        progress_bar.classes(remove='hidden')
                        progress_bar.set_value(0.2)
                        status_label.set_text('Создание структуры каталогов...')

                        out_dir = Path(folder_input.value)
                        teach_plan_dir = out_dir / "teach_plan"
                        template_dir = out_dir / "template"
                        teach_plan_dir.mkdir(parents=True, exist_ok=True)
                        template_dir.mkdir(parents=True, exist_ok=True)

                        progress_bar.set_value(0.4)
                        status_label.set_text('Экспорт структурированных JSON данных (teach_plan/)...')

                        with open(teach_plan_dir / "01_metadata.json", "w", encoding="utf-8") as f:
                            json.dump(state.meta, f, indent=2, ensure_ascii=False)
                        with open(teach_plan_dir / "02_curriculum_discipline.json", "w", encoding="utf-8") as f:
                            json.dump(state.disc, f, indent=2, ensure_ascii=False)
                        with open(teach_plan_dir / "03_competencies_indicators.json", "w", encoding="utf-8") as f:
                            json.dump(state.comps, f, indent=2, ensure_ascii=False)

                        rel_dict = {
                            "target_discipline": {
                                "code": state.context.get("course_code"),
                                "name": state.context.get("course_name"),
                                "semester": state.context.get("semester"),
                                "course": state.context.get("course_year")
                            },
                            "co_requisites": [{"code": "", "name": c} for c in state.coreqs]
                        }
                        with open(teach_plan_dir / "04_discipline_relationships.json", "w", encoding="utf-8") as f:
                            json.dump(rel_dict, f, indent=2, ensure_ascii=False)

                        progress_bar.set_value(0.6)
                        status_label.set_text('Копирование параметризованного шаблона (template/)...')
                        dest_template = template_dir / "rpd_template_parametrized.docx"
                        shutil.copy(DEFAULT_TEMPLATE_PATH, dest_template)

                        progress_bar.set_value(0.8)
                        status_label.set_text('Рендеринг и пост-процессинг верстки DOCX (все 14 правил)...')

                        clean_code = state.context.get("course_code", "RPD").replace(" ", "_").replace(".", "_")
                        clean_name = state.context.get("course_name", "Дисциплина").replace(" ", "_")
                        clean_name = "".join(c for c in clean_name if c.isalnum() or c in "_-")
                        year = state.context.get("current_year", 2026)
                        filename = f"{clean_code}_{clean_name}_РПД_{year}.docx"
                        out_docx_path = out_dir / filename

                        generate_rpd(str(dest_template), state.context, str(out_docx_path))

                        progress_bar.set_value(1.0)
                        val = validate_rpd_document(str(out_docx_path))
                        state.validation_result = val
                        state.generated_docx = str(out_docx_path)

                        status_label.set_text(f'Успешно! Документ сгенерирован и проверен (Таблиц: {val["tables_count"]}, Параграфов: {val["paragraphs_count"]}).')
                        ui.notify('РПД успешно сгенерирована!', color='positive')

                        download_btn.classes(remove='hidden')
                        download_btn.on_click(lambda: ui.download(str(out_docx_path), filename))

                    except Exception as err:
                        status_label.set_text(f'Ошибка при генерации: {err}')
                        ui.notify(f'Ошибка: {err}', color='negative')

                ui.button('Сгенерировать РПД и сохранить все данные', icon='auto_fix_high', on_click=do_generate).props('color=green-8 size=lg').classes('w-full')

                with ui.stepper_navigation():
                    ui.button('Назад', on_click=stepper.previous).props('flat')


if __name__ in {"__main__", "__mp_main__"}:
    port = int(os.environ.get("PORT", 8080))
    ui.run(title="Генератор РПД • РГАУ-МСХА", port=port, reload=False, show=False)
