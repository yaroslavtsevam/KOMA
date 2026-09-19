"""
variables_form.py – Step 3: Rich editor for variables.yml (/project/{id}/variables)

Renders the full YAML tree as a multi-section accordion form.
Supports: scalars, null-able fields, string lists (add/remove/edit),
          dicts as expansion panels, and lists of dicts.
"""

import os
import copy
import yaml
from pathlib import Path

# Safe constructor for docxtpl Listing if encountered in legacy files
def _listing_constructor(loader, node):
    fields = loader.construct_mapping(node, deep=True)
    return fields.get('xml', '')

yaml.SafeLoader.add_constructor('tag:yaml.org,2002:python/object:docxtpl.listing.Listing', _listing_constructor)

from nicegui import app, ui, background_tasks
from ..db import get_project, update_project_status, update_project_files, processing_dir
from ..auth import current_user, require_login
from ..pipeline import read_parameters_env, generate_docx, run_questions_generation
from .shared import page_layout, _step_indicator


# ── Russian label overrides for common YAML keys ─────────────────────────────

KEY_LABELS = {
    # Top-level
    "activities":           "Виды занятий",
    "case_study":           "Кейс-задание",
    "cathedra_meeting_year":"Год заседания кафедры",
    "colloquium":           "Коллоквиум",
    "control_form":         "Форма контроля",
    "course_code":          "Код дисциплины",
    "course_title":         "Название дисциплины",
    "course_type":          "Тип курса",
    "course_work":          "Курсовая работа",
    "course_year":          "Курс (год обучения)",
    "creative_project":     "Творческий проект",
    "credit":               "Зачёт",
    "credit_heading_label": "Формулировка заголовка зачёта",
    "degree_qualification": "Квалификация",
    "degree_qualification_genitive": "Квалификация (род. пад.)",
    "degree_type":          "Тип степени",
    "department":           "Кафедра",
    "department_head_fio":  "Заведующий кафедрой (ФИО)",
    "developers":           "Разработчики",
    "discipline_or_module": "Дисциплина или модуль",
    "essay":                "Эссе",
    "exam":                 "Экзамен",
    "faculty":              "Факультет",
    "fgos_vo":              "ФГОС ВО",
    "hours":                "Общая трудоемкость (часов)",
    "indicators":           "Индикаторы достижения компетенций",
    "institute":            "Институт",
    "major_code":           "Код специальности",
    "major_title":          "Направление подготовки (название)",
    "major_type_label":     "Тип специальности",
    "major_type_label_genitive": "Тип специальности (род. пад.)",
    "major_type_label_prepositional": "Тип специальности (пред. пад.)",
    "multi_level_tasks":    "Многоуровневые задания",
    "portfolio":            "Портфолио",
    "profile_title":        "Профиль",
    "profile_type_label":   "Тип профиля",
    "protocol_day":         "День протокола",
    "protocol_month":       "Месяц протокола",
    "protocol_num":         "Номер протокола",
    "protocol_year":        "Год протокола",
    "reviewer":             "Рецензент",
    "rgr":                  "РГР",
    "roleplay":             "Ролевая игра",
    "round_table":          "Круглый стол",
    "rpd_reference_text":   "Справочные данные РПД",
    "semester":             "Семестр",
    "start_year":           "Год начала",
    "study_form":           "Форма обучения",
    "table1":               "Таблица компетенций 1",
    "table2":               "Таблица компетенций 2",
    "test_paper":           "Контрольная работа",
    "year_of_study_start":  "Год начала обучения",
    # Nested common
    "questions":    "Вопросы",
    "criteria":     "Критерии оценки",
    "theme":        "Тема",
    "type":         "Тип",
    "num":          "Номер",
    "comp_code":    "Код компетенции",
    "eval_tool":    "Инструмент оценки",
    "lectures":     "Лекции",
    "topics":       "Темы",
    "variants":     "Варианты",
    "tasks":        "Задания",
    "variant_name": "Название варианта",
    "topic_title":  "Название темы",
    "individual_projects": "Индивидуальные проекты",
    "group_projects":      "Групповые проекты",
    "reproductive":  "Репродуктивные задания",
    "reconstructive":"Реконструктивные задания",
    "creative":      "Творческие задания",
    "section_title": "Раздел",
    "know":  "Знать",
    "umeti": "Уметь",
    "vladeti": "Владеть",
    "content": "Содержание",
    "stage":    "Этап",
}

# Keys to group together in "Основная информация"
_SCALAR_KEYS = {
    "cathedra_meeting_year", "course_code", "course_title",
    "course_type", "course_year", "degree_qualification", "degree_qualification_genitive",
    "degree_type", "department", "department_head_fio", "developers", "discipline_or_module", "fgos_vo",
    "hours", "institute", "major_code", "major_title", "major_type_label",
    "major_type_label_genitive", "major_type_label_prepositional", "profile_title",
    "profile_type_label", "protocol_day", "protocol_month", "protocol_num",
    "protocol_year", "reviewer", "rpd_reference_text", "semester", "start_year",
    "study_form", "year_of_study_start",
}

_RPD_SYNCED_KEYS = [
    "course_title", "course_code", "discipline_or_module",
    "institute", "department", "department_head_fio",
    "major_code", "major_title", "profile_title",
    "degree_type", "degree_qualification", "study_form",
    "course_year", "semester", "hours", "control_form",
    "start_year", "developers", "reviewer", "rpd_reference_text",
]

_PROTOCOL_KEYS = [
    "protocol_num", "protocol_day", "protocol_month", "protocol_year", "cathedra_meeting_year",
]

_NULLABLE_KEYS = {
    "case_study", "course_work", "essay", "exam", "portfolio", "rgr",
    "roleplay", "round_table",
}


def _label(key: str) -> str:
    return KEY_LABELS.get(key, key.replace("_", " ").capitalize())


# ── Recursive form renderer ────────────────────────────────────────────────────

def render_value(data: dict, key: str, depth: int = 0):
    """Dispatch to the appropriate renderer based on value type."""
    value = data.get(key)

    if key in _NULLABLE_KEYS and value is None:
        _render_nullable(data, key)
        return

    if value is None:
        _render_scalar(data, key, "")
    elif isinstance(value, bool):
        _render_bool(data, key, value)
    elif isinstance(value, (int, float)):
        _render_scalar(data, key, str(value))
    elif isinstance(value, str):
        _render_scalar(data, key, value)
    elif isinstance(value, list):
        if not value or isinstance(value[0], str):
            _render_string_list(data, key, value)
        elif isinstance(value[0], dict):
            _render_dict_list(data, key, value, depth)
        else:
            _render_string_list(data, key, [str(v) for v in value])
    elif isinstance(value, dict):
        _render_dict_expansion(data, key, value, depth)


def _render_scalar(data: dict, key: str, value: str):
    lbl = _label(key)
    with ui.row().classes("w-full items-start gap-3 mb-2"):
        ui.label(lbl + ":").classes("text-sm text-gray-400").style("min-width: 220px; padding-top: 8px;")
        is_long = len(value) > 80
        if is_long:
            inp = (
                ui.textarea(value=value)
                .props("outlined dark color=indigo autogrow")
                .classes("flex-1")
            )
        else:
            inp = (
                ui.input(value=value)
                .props("outlined dark color=indigo")
                .classes("flex-1")
            )

        def _upd(e, _inp=inp, _d=data, _k=key, _is_long=is_long):
            val = _inp.value
            _d[_k] = val if val else (None if _d.get(_k) is None else val)

        inp.on("blur", _upd)


def _render_bool(data: dict, key: str, value: bool):
    cb = ui.checkbox(_label(key), value=value).props("dark color=indigo")
    cb.on("change", lambda e, _d=data, _k=key: _d.update({_k: e.value}))


def _render_nullable(data: dict, key: str):
    lbl = _label(key)
    with ui.row().classes("w-full items-center gap-3 mb-2"):
        enabled = ui.checkbox(lbl, value=data.get(key) is not None).props("dark color=indigo")
        ui.label("(не используется)").classes("text-xs text-gray-600")

    def toggle(e, _d=data, _k=key):
        _d[_k] = {} if e.value else None

    enabled.on("change", toggle)


def _render_string_list(data: dict, key: str, items: list):
    lbl = _label(key)
    local_items = list(items)  # local copy for rendering

    with ui.expansion(lbl, icon="list").classes("w-full mb-2").props("dark"):
        container = ui.column().classes("w-full gap-2 pl-4")

        def rebuild():
            container.clear()
            with container:
                for idx in range(len(local_items)):
                    _item_row(idx)
                _add_button()

        def _item_row(idx: int):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(f"{idx + 1}.").classes("text-xs text-gray-600").style("min-width: 24px;")
                inp = (
                    ui.textarea(value=local_items[idx])
                    .props("outlined dark color=indigo autogrow dense")
                    .classes("flex-1")
                )

                def _save_text(e, _inp=inp, i=idx):
                    local_items[i] = _inp.value
                    data[key] = local_items[:]

                inp.on("blur", _save_text)

                def _delete(i=idx):
                    local_items.pop(i)
                    data[key] = local_items[:]
                    rebuild()

                ui.button(icon="remove_circle_outline", on_click=_delete).props(
                    "flat round size=xs color=red"
                )

        def _add_button():
            def _add():
                local_items.append("")
                data[key] = local_items[:]
                rebuild()

            ui.button("+ Добавить вопрос/пункт", icon="add", on_click=_add).props(
                "flat size=sm"
            ).classes("text-indigo-400 mt-1")

        rebuild()


def _render_dict_list(data: dict, key: str, items: list, depth: int):
    lbl = _label(key)
    with ui.expansion(lbl, icon="view_list").classes("w-full mb-2").props("dark"):
        with ui.column().classes("w-full gap-3 pl-2"):
            for idx, item in enumerate(items):
                item_label = (
                    item.get("num") or item.get("variant_name") or item.get("topic_title") or
                    item.get("section_title") or item.get("stage") or f"Элемент {idx + 1}"
                )
                with ui.expansion(str(item_label), icon="edit_note").classes("w-full").props("dark"):
                    with ui.column().classes("w-full gap-1 pl-4"):
                        for sub_key in item:
                            render_value(item, sub_key, depth + 1)


def _render_dict_expansion(data: dict, key: str, value: dict, depth: int):
    lbl = _label(key)
    with ui.expansion(lbl, icon="folder_open").classes("w-full mb-2").props("dark"):
        with ui.column().classes("w-full gap-1 pl-4"):
            for sub_key in value:
                render_value(value, sub_key, depth + 1)


# ── Main page ─────────────────────────────────────────────────────────────────

@ui.page("/project/{project_id}/variables")
async def variables_page(project_id: int):
    if not require_login():
        return

    user = current_user()
    project = get_project(project_id)
    if not project or project["user_id"] != user["user_id"]:
        ui.navigate.to("/dashboard")
        return

    status = project.get("status", "new")
    if status not in ("variables", "questions", "error", "done"):
        from .parameters import _redirect_by_status
        _redirect_by_status(project_id, status)
        return

    proc_dir = processing_dir(project["name"])
    variables_path = proc_dir / "variables.yml"

    if not variables_path.exists():
        with page_layout(f"Переменные: {project['name']}", user):
            with ui.card().classes("app-card w-full").style("padding: 40px; text-align: center;"):
                ui.icon("error_outline", size="4rem").style("color: #ef4444;")
                ui.label("Файл variables.yml не найден").classes("text-xl font-bold text-red-400 mt-4")
                ui.label("Запустите обработку РПД заново.").classes("text-gray-500 mt-2")
                ui.button("← Назад к параметрам", on_click=lambda: ui.navigate.to(
                    f"/project/{project_id}/parameters"
                )).classes("primary-btn mt-6")
        return

    # Load + deep-copy so YAML anchors don't create shared-reference issues
    with open(variables_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    data = copy.deepcopy(raw) if raw else {}

    # Load parameters for docx generation
    env_path = proc_dir / "parameters.env"
    params = read_parameters_env(env_path)

    # Sanitize duplicate / obsolete fields
    data.pop("cathedra_name", None)

    # Auto-heal department if empty or default 'Кафедра'
    if not data.get("department") or data.get("department").strip() == "Кафедра":
        if params and params.get("department"):
            data["department"] = params["department"]
        elif project.get("department"):
            data["department"] = project["department"]
        else:
            data["department"] = "Кафедра экологии"

    # Auto-populate department_head_fio if missing in data but in params
    if not data.get("department_head_fio") and params and params.get("department_head_fio"):
        data["department_head_fio"] = params["department_head_fio"]

    has_plan = bool(project.get("plan_path") or project.get("plan_filename") or project.get("course_code"))
    is_structure_only = (status == "variables")
    active_step = 7

    course_display = project.get("course_name") or project.get("course_code") or project["name"]

    # ── Build the page ────────────────────────────────────────────────────────
    with page_layout(f"Шаг 7: Итог ОМД: {course_display}", user):
        _step_indicator(7, project)

        # ── Action toolbar ────────────────────────────────────────────────────
        with ui.card().classes("app-card w-full mb-4").style("padding: 16px 24px;"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon("edit_note", size="1.4rem").style("color: #6366f1;")
                ui.label("Шаг 7: Итог ОМД — Редактор оценочных материалов и фонда вопросов").classes("text-base font-semibold flex-1")

                async def do_save():
                    with open(variables_path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                    update_project_files(project_id, variables_path=str(variables_path))
                    ui.notify("✓ Изменения сохранены", type="positive")

                async def do_generate_questions():
                    await do_save()
                    app.storage.user[f"return_to_{project_id}"] = f"/project/{project_id}/variables"
                    background_tasks.create(
                        run_questions_generation(project_id, user["username"], project["name"], params, regenerate=True)
                    )
                    ui.navigate.to(f"/project/{project_id}/processing")

                async def do_generate_docx():
                    await do_save()
                    app.storage.user[f"return_to_{project_id}"] = f"/project/{project_id}/download"
                    background_tasks.create(
                        generate_docx(project_id, user["username"], project["name"], params)
                    )
                    ui.navigate.to(f"/project/{project_id}/processing")

                ui.button("← Параметры ОМД (Шаг 5)", icon="arrow_back", on_click=lambda: ui.navigate.to(
                    f"/project/{project_id}/omd_parameters"
                )).props("flat").classes("text-gray-400")

                if has_plan:
                    ui.button("К финалу РПД (Шаг 4)", icon="description", on_click=lambda: ui.navigate.to(
                        f"/project/{project_id}/rpd_final"
                    )).props("flat").classes("text-indigo-400")

                ui.button("Сохранить", icon="save", on_click=do_save).props("flat").classes("text-indigo-300")

                # Check whether activities have questions
                has_questions = False
                acts = data.get("activities", [])
                if acts and any(a.get("questions") for a in acts):
                    has_questions = True

                with ui.row().classes("gap-2 items-center"):
                    if not has_questions:
                        if os.environ.get("GOOGLE_API_KEY"):
                            ui.button("⚡ Сгенерировать вопросы (AI Gemini) →", icon="psychology", on_click=do_generate_questions).classes("success-btn")
                        ui.button("Сгенерировать без вопросов (.docx)", icon="description", on_click=do_generate_docx).props("outline color=grey")
                    else:
                        if os.environ.get("GOOGLE_API_KEY"):
                            ui.button("🔄 Перегенерировать (AI)", icon="refresh", on_click=do_generate_questions).props("outline color=indigo")
                        ui.button("Сформировать итоговый комплект (Шаг 8) →", icon="arrow_forward", on_click=do_generate_docx).classes("success-btn")


        if not has_questions:
            with ui.card().classes("w-full mb-4 bg-amber-950/40 border border-amber-500/50 p-4 rounded-xl"):
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("warning", color="amber", size="1.8rem")
                        with ui.column().classes("gap-0"):
                            ui.label("Вопросы к занятиям и оценочные материалы еще не сгенерированы!").classes("font-semibold text-amber-300 text-sm")
                            ui.label("Нажмите «Сгенерировать вопросы (AI Gemini)», чтобы автоматически заполнить вопросы для всех лекций, практик, тестов и зачета/экзамена.").classes("text-xs text-amber-200/80")
                    if os.environ.get("GOOGLE_API_KEY"):
                        ui.button("Сгенерировать вопросы (AI Gemini) →", icon="psychology", on_click=do_generate_questions).classes("success-btn")
        else:
            with ui.card().classes("w-full mb-4 bg-indigo-950/40 border border-indigo-500/40 p-3 rounded-xl"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle", color="positive", size="1.2rem")
                    ui.label("✓ Оценочные материалы и вопросы сгенерированы с помощью AI Gemini.").classes("text-xs text-indigo-200")

        # ── Tabs for logical grouping ─────────────────────────────────────────
        with ui.tabs().props("dark active-color=indigo indicator-color=indigo").classes("mb-2") as tabs:
            tab_main  = ui.tab("Основная информация", icon="info")
            tab_act   = ui.tab("Список занятий" if is_structure_only else "Виды занятий", icon="class")
            tab_tables = ui.tab("Таблицы компетенций", icon="table_chart")
            if not is_structure_only:
                tab_assess = ui.tab("Контроль", icon="grading")
                tab_tasks = ui.tab("Задания", icon="assignment")

        with ui.tab_panels(tabs, value=tab_main).props("dark").classes("w-full"):

            # ── TAB 1: Scalar fields & general information ─────────────────────
            with ui.tab_panel(tab_main):
                # Group 1: Inherited from RPD (Unified pool)
                with ui.card().classes("app-card w-full mb-4").style("padding: 24px;"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("school", size="1.3rem").style("color: #6366f1;")
                            ui.label("Реквизиты образовательной программы").classes("text-base font-semibold text-gray-200")
                        ui.badge("✓ Синхронизировано с РПД", color="indigo").classes("text-xs px-2 py-1")
                    ui.label("Данные автоматически получены из этапов создания РПД (единый пул переменных).").classes("text-xs text-gray-400 mb-4")
                    
                    with ui.column().classes("w-full gap-0"):
                        for key in _RPD_SYNCED_KEYS:
                            if key in data:
                                render_value(data, key)

                # Group 2: Protocol details
                with ui.card().classes("app-card w-full mb-4").style("padding: 24px;"):
                    with ui.row().classes("items-center gap-2 mb-2"):
                        ui.icon("event_note", size="1.3rem").style("color: #10b981;")
                        ui.label("Реквизиты заседания кафедры").classes("text-base font-semibold text-gray-200")
                    ui.label("Номер и дата протокола заседания кафедры для титульного листа и листа утверждения ОМД.").classes("text-xs text-gray-400 mb-4")
                    
                    with ui.column().classes("w-full gap-0"):
                        for key in _PROTOCOL_KEYS:
                            if key in data:
                                render_value(data, key)

                # Group 3: Additional scalar keys & Nullables if any
                other_scalars = [k for k in sorted(_SCALAR_KEYS) if k not in _RPD_SYNCED_KEYS and k not in _PROTOCOL_KEYS and k in data]
                nullables_present = [k for k in sorted(_NULLABLE_KEYS) if k in data]
                
                known = (
                    _SCALAR_KEYS | _NULLABLE_KEYS | set(_RPD_SYNCED_KEYS) | set(_PROTOCOL_KEYS) |
                    {"activities", "colloquium", "credit", "exam", "test_paper",
                     "multi_level_tasks", "creative_project", "table1", "table2", "cathedra_name"}
                )
                other_keys = [k for k in data if k not in known]

                if other_scalars or nullables_present or other_keys:
                    with ui.card().classes("app-card w-full").style("padding: 24px;"):
                        ui.label("Дополнительные параметры").classes("text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3")
                        with ui.column().classes("w-full gap-0"):
                            for key in other_scalars:
                                render_value(data, key)
                            for key in nullables_present:
                                render_value(data, key)
                            for key in sorted(other_keys):
                                render_value(data, key)

            # ── TAB 2: Activities ─────────────────────────────────────────────
            with ui.tab_panel(tab_act):
                with ui.card().classes("app-card w-full").style("padding: 24px;"):
                    if "activities" in data:
                        activities = data["activities"]
                        for idx, act in enumerate(activities):
                            title = f"{act.get('num', f'Занятие {idx+1}')} — {act.get('theme', '')}"
                            with ui.expansion(title, icon="class").classes("w-full mb-3").props("dark"):
                                with ui.column().classes("w-full gap-2 pl-4"):
                                    for key in ["num", "theme", "type", "comp_code", "eval_tool", "hours"]:
                                        if key in act:
                                            render_value(act, key)
                                    if "questions" in act and not is_structure_only:
                                        _render_string_list(act, "questions", act.get("questions", []))
                    else:
                        ui.label("Виды занятий не найдены в variables.yml").classes("text-gray-500")

            # ── TAB 5: Tables ─────────────────────────────────────────────────
            with ui.tab_panel(tab_tables):
                with ui.card().classes("app-card w-full").style("padding: 24px;"):
                    for key in ["table1", "table2"]:
                        if key in data:
                            render_value(data, key)

            if not is_structure_only:
                # ── TAB 3: Assessment (colloquium, credit, exam, test_paper) ─────
                with ui.tab_panel(tab_assess):
                    with ui.card().classes("app-card w-full").style("padding: 24px;"):
                        for key in ["colloquium", "credit", "exam", "test_paper"]:
                            if key in data and data[key] is not None:
                                render_value(data, key)
                            elif key in data:
                                with ui.row().classes("items-center gap-2 mb-2"):
                                    ui.label(_label(key) + ":").classes("text-sm text-gray-600")
                                    ui.label("не используется").classes("text-xs text-gray-700 italic")

                # ── TAB 4: Tasks ──────────────────────────────────────────────────
                with ui.tab_panel(tab_tasks):
                    with ui.card().classes("app-card w-full").style("padding: 24px;"):
                        for key in ["multi_level_tasks", "creative_project"]:
                            if key in data and data[key] is not None:
                                render_value(data, key)

        # ── Bottom save bar ───────────────────────────────────────────────────
        with ui.card().classes("app-card w-full mt-4").style("padding: 16px 24px;"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("После внесения изменений не забудьте сохранить файл.").classes(
                    "text-sm text-gray-500"
                )
                with ui.row().classes("gap-3"):
                    ui.button("← Параметры ОМД (Шаг 5)", on_click=lambda: ui.navigate.to(
                        f"/project/{project_id}/omd_parameters"
                    )).props("flat").classes("text-gray-400")
                    ui.button("Сохранить", icon="save", on_click=do_save).classes("primary-btn")
                    
                    if not has_questions and os.environ.get("GOOGLE_API_KEY"):
                        ui.button("⚡ Сгенерировать вопросы (AI Gemini) →", icon="psychology", on_click=do_generate_questions).classes("success-btn")
                    else:
                        ui.button("Сформировать итоговый комплект (Шаг 8) →", icon="arrow_forward", on_click=do_generate_docx).classes("success-btn")

