"""
variables_form.py – Step 3: Rich editor for variables.yml (/project/{id}/variables)

Renders the full YAML tree as a multi-section accordion form.
Supports: scalars, null-able fields, string lists (add/remove/edit),
          dicts as expansion panels, and lists of dicts.
"""

import copy
import yaml
from pathlib import Path
from nicegui import ui, background_tasks
from ..db import get_project, update_project_status, update_project_files, processing_dir
from ..auth import current_user, require_login
from ..pipeline import read_parameters_env, generate_docx, run_questions_generation
from .shared import page_layout


# ── Russian label overrides for common YAML keys ─────────────────────────────

KEY_LABELS = {
    # Top-level
    "activities":           "Виды занятий",
    "case_study":           "Кейс-задание",
    "cathedra_meeting_year":"Год заседания кафедры",
    "cathedra_name":        "Название кафедры",
    "colloquium":           "Коллоквиум",
    "course_type":          "Тип курса",
    "course_work":          "Курсовая работа",
    "course_year":          "Курс (год обучения)",
    "creative_project":     "Творческий проект",
    "credit":               "Зачёт",
    "degree_qualification": "Квалификация",
    "degree_qualification_genitive": "Квалификация (род. пад.)",
    "degree_type":          "Тип степени",
    "department":           "Кафедра",
    "developers":           "Разработчики",
    "discipline_or_module": "Дисциплина или модуль",
    "essay":                "Эссе",
    "exam":                 "Экзамен",
    "fgos_vo":              "ФГОС ВО",
    "major_code":           "Код специальности",
    "major_type_label":     "Тип специальности",
    "major_type_label_genitive": "Тип специальности (род. пад.)",
    "major_type_label_prepositional": "Тип специальности (пред. пад.)",
    "multi_level_tasks":    "Многоуровневые задания",
    "portfolio":            "Портфолио",
    "profile_title":        "Профиль",
    "profile_type_label":   "Тип профиля",
    "protocol_month":       "Месяц протокола",
    "protocol_num":         "Номер протокола",
    "protocol_year":        "Год протокола",
    "reviewer":             "Рецензент",
    "rgr":                  "РГР",
    "roleplay":             "Ролевая игра",
    "round_table":          "Круглый стол",
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
    "hours":        "Часы",
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
    "num":      "Номер",
}

# Keys to group together in "Основная информация"
_SCALAR_KEYS = {
    "cathedra_meeting_year", "cathedra_name", "course_type", "course_year",
    "degree_qualification", "degree_qualification_genitive", "degree_type",
    "department", "developers", "discipline_or_module", "fgos_vo",
    "major_code", "major_type_label", "major_type_label_genitive",
    "major_type_label_prepositional", "profile_title", "profile_type_label",
    "protocol_month", "protocol_num", "protocol_year", "reviewer",
    "semester", "start_year", "study_form", "year_of_study_start",
}

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

        def _upd(e, _d=data, _k=key, _is_long=is_long):
            _d[_k] = e.value if e.value else None if _d.get(_k) is None else e.value

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

                def _save_text(e, i=idx):
                    local_items[i] = e.value
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

    is_structure_only = (status == "variables")
    active_step = 3 if is_structure_only else 5

    # ── Build the page ────────────────────────────────────────────────────────
    with page_layout(f"Переменные: {project['name']}", user):
        from .shared import _step_indicator
        _step_indicator(active_step, project)

        # ── Action toolbar ────────────────────────────────────────────────────
        with ui.card().classes("app-card w-full mb-4").style("padding: 16px 24px;"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon("edit_note", size="1.4rem").style("color: #6366f1;")
                ui.label("Редактор переменных документа" if not is_structure_only else "Проверка структуры документа").classes("text-base font-semibold flex-1")

                async def do_save():
                    with open(variables_path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                    update_project_files(project_id, variables_path=str(variables_path))
                    ui.notify("✓ Изменения сохранены", type="positive")

                async def do_generate_questions():
                    await do_save()
                    background_tasks.create(
                        run_questions_generation(project_id, user["username"], project["name"], params)
                    )
                    ui.navigate.to(f"/project/{project_id}/processing")

                async def do_generate_docx():
                    await do_save()
                    background_tasks.create(
                        generate_docx(project_id, user["username"], project["name"], params)
                    )
                    ui.navigate.to(f"/project/{project_id}/processing")

                ui.button("← Назад к параметрам", icon="arrow_back", on_click=lambda: ui.navigate.to(
                    f"/project/{project_id}/parameters"
                )).props("flat").classes("text-gray-400")

                ui.button("Сохранить", icon="save", on_click=do_save).props("flat").classes("text-indigo-300")

                if is_structure_only:
                    ui.button("Генерация вопросов →", icon="psychology", on_click=do_generate_questions).classes("success-btn")
                else:
                    ui.button("Сгенерировать Word документ →", icon="description", on_click=do_generate_docx).classes("success-btn")

        # ── Tabs for logical grouping ─────────────────────────────────────────
        with ui.tabs().props("dark active-color=indigo indicator-color=indigo").classes("mb-2") as tabs:
            tab_main  = ui.tab("Основная информация", icon="info")
            tab_act   = ui.tab("Список занятий" if is_structure_only else "Виды занятий", icon="class")
            tab_tables = ui.tab("Таблицы компетенций", icon="table_chart")
            if not is_structure_only:
                tab_assess = ui.tab("Контроль", icon="grading")
                tab_tasks = ui.tab("Задания", icon="assignment")
                tab_other = ui.tab("Прочее", icon="more_horiz")

        with ui.tab_panels(tabs, value=tab_main).props("dark").classes("w-full"):

            # ── TAB 1: Scalar fields ──────────────────────────────────────────
            with ui.tab_panel(tab_main):
                with ui.card().classes("app-card w-full").style("padding: 24px;"):
                    with ui.column().classes("w-full gap-0"):
                        for key in sorted(_SCALAR_KEYS):
                            if key in data:
                                render_value(data, key)
                        # Nullable simple keys
                        for key in sorted(_NULLABLE_KEYS):
                            if key in data:
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

                # ── TAB 6: Other remaining top-level keys ─────────────────────────
                with ui.tab_panel(tab_other):
                    with ui.card().classes("app-card w-full").style("padding: 24px;"):
                        known = (
                            _SCALAR_KEYS | _NULLABLE_KEYS |
                            {"activities", "colloquium", "credit", "exam", "test_paper",
                             "multi_level_tasks", "creative_project", "table1", "table2"}
                        )
                        other_keys = [k for k in data if k not in known]
                        if other_keys:
                            for key in other_keys:
                                render_value(data, key)
                        else:
                            ui.label("Все поля распределены по вкладкам выше.").classes("text-gray-500")

        # ── Bottom save bar ───────────────────────────────────────────────────
        with ui.card().classes("app-card w-full mt-4").style("padding: 16px 24px;"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("После внесения изменений не забудьте сохранить файл.").classes(
                    "text-sm text-gray-500"
                )
                with ui.row().classes("gap-3"):
                    ui.button("← Назад к параметрам", on_click=lambda: ui.navigate.to(
                        f"/project/{project_id}/parameters"
                    )).props("flat").classes("text-gray-400")
                    ui.button("Сохранить", icon="save", on_click=do_save).classes("primary-btn")
                    
                    if is_structure_only:
                        ui.button("Генерация вопросов →", icon="psychology", on_click=do_generate_questions).classes("success-btn")
                    else:
                        ui.button("Сгенерировать Word документ →", icon="description", on_click=do_generate_docx).classes("success-btn")
