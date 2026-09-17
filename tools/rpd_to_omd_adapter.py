#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rpd_to_omd_adapter.py
Адаптер для бесшовного преобразования проверенной структуры РПД
в формат variables.yml для генератора Оценочных материалов дисциплин (ОМД).
Гарантирует 100% согласованность между РПД и ОМД без повторного парсинга PDF.
"""

import os
import yaml
import copy


def rpd_context_to_omd_variables(rpd_context: dict, existing_variables: dict = None) -> dict:
    """
    Преобразует словарь контекста РПД (из rpd_app) в формат variables.yml для ОМД.
    Если передан existing_variables, сохраняет уже сгенерированные AI вопросы и задания.
    """
    # 1. Метаданные шапки
    institute = rpd_context.get("institute", "Институт мелиорации, водного хозяйства и строительства имени А.Н. Костякова")
    department = rpd_context.get("department", "Кафедра экологии")
    course_code = rpd_context.get("course_code", "")
    course_title = rpd_context.get("course_name", "")
    degree_type = rpd_context.get("qualification_plural", "магистров")
    fgos_vo = rpd_context.get("fgos_standard", "ФГОС ВО")
    major_code = rpd_context.get("direction_code", "")
    major_title = rpd_context.get("direction_name", "")
    profile_title = rpd_context.get("profile", "")
    course_year = str(rpd_context.get("course_year", "2"))
    semester = str(rpd_context.get("semester", "4"))
    study_form = rpd_context.get("study_form", "очная")
    start_year = str(rpd_context.get("start_year", "2026"))
    developers = rpd_context.get("developer_fio_rank", "")
    reviewer = rpd_context.get("reviewer_fio_rank", "")

    # 2. Таблица 1 ОМД (Этапы формирования компетенций)
    table1 = []
    # 3. Таблица 2 ОМД (Индикаторы и дескрипторы Знать/Уметь/Владеть)
    table2 = []

    comp_nested = rpd_context.get("competencies_nested", [])
    row_idx = 1
    for comp in comp_nested:
        comp_code = comp.get("code", "")
        comp_title = comp.get("title", "")

        # Собираем индикаторы
        all_inds = []
        if comp.get("ind_first"):
            all_inds.append(comp["ind_first"])
        all_inds.extend(comp.get("other_indicators", []))

        ind_texts = []
        know_list = []
        able_list = []
        master_list = []

        for ind in all_inds:
            ind_code = ind.get("code", "")
            ind_t = ind.get("title", "")
            ind_texts.append(f"{ind_code} {ind_t}".strip())
            if ind.get("know"): know_list.append(ind["know"])
            if ind.get("able"): able_list.append(ind["able"])
            if ind.get("master"): master_list.append(ind["master"])

            # Добавляем этапы в Таблицу 1
            table1.append({
                "num": f"{row_idx}.",
                "comp_code": ind_code or comp_code,
                "stage": "Знаниевый / Деятельностный",
                "eval_tool": "Устный опрос, Тестирование, Защита работ"
            })
            row_idx += 1

        table2.append({
            "num": f"{len(table2) + 1}.",
            "comp_code": comp_code,
            "content": comp_title,
            "indicators": "; ".join(ind_texts),
            "know": "; ".join(know_list),
            "umeti": "; ".join(able_list),
            "vladeti": "; ".join(master_list)
        })

    # 4. Сетка занятий (activities) из Таблицы 4 РПД
    # Считываем уже существующие сгенерированные вопросы (если они есть)
    existing_act_map = {}
    if existing_variables and isinstance(existing_variables.get("activities"), list):
        for idx, e_act in enumerate(existing_variables["activities"]):
            if isinstance(e_act, dict) and e_act.get("questions"):
                num_k = (e_act.get("num") or "").strip().lower()
                theme_k = (e_act.get("theme") or "").strip().lower()
                if num_k: existing_act_map[num_k] = e_act["questions"]
                if theme_k: existing_act_map[theme_k] = e_act["questions"]
                existing_act_map[f"idx_{idx}"] = e_act["questions"]

    activities = []
    t4_sections = rpd_context.get("t4_sections", [])
    for sec in t4_sections:
        for lesson in sec.get("lessons", []):
            l_num = lesson.get("title", f"Занятие №{len(activities)+1}")
            l_theme = lesson.get("theme", "")
            # Ищем существующие вопросы по номеру, теме или порядковому индексу
            preserved_q = (
                existing_act_map.get(l_num.strip().lower()) or
                existing_act_map.get(l_theme.strip().lower()) or
                existing_act_map.get(f"idx_{len(activities)}") or
                []
            )
            activities.append({
                "num": l_num,
                "theme": l_theme,
                "type": "Лекция" if "Лекция" in l_num else "Практическое занятие",
                "hours": float(lesson.get("hours", 1.5)),
                "comp_code": lesson.get("competencies", ""),
                "eval_tool": lesson.get("control", "Устный опрос"),
                "questions": preserved_q
            })

    # Если t4_sections пуст, формируем базовые activities из sections
    if not activities:
        for i, s in enumerate(rpd_context.get("sections", []), 1):
            s_name = s.get("name", "")
            lec_num = f"Лекция №{i}"
            lec_q = existing_act_map.get(lec_num.lower()) or existing_act_map.get(s_name.lower()) or []
            activities.append({
                "num": lec_num,
                "theme": s_name,
                "type": "Лекция",
                "hours": float(s.get("lec", 2) or 2),
                "comp_code": comp_nested[0]["code"] if comp_nested else "УК-1",
                "eval_tool": "Устный опрос",
                "questions": lec_q
            })
            prac_num = f"Практическое занятие №{i}"
            prac_q = existing_act_map.get(prac_num.lower()) or existing_act_map.get(s_name.lower()) or []
            activities.append({
                "num": prac_num,
                "theme": s_name,
                "type": "Практическое занятие",
                "hours": float(s.get("prac", 2) or 2),
                "comp_code": comp_nested[0]["code"] if comp_nested else "УК-1",
                "eval_tool": "Защита практической работы",
                "questions": prac_q
            })

    # 5. Оценочные средства (переносим уже подготовленные задания из РПД или existing_variables)
    # Коллоквиум
    colloquium = None
    if existing_variables and existing_variables.get("colloquium"):
        colloquium = existing_variables["colloquium"]
    else:
        colloquium_qs = [q.get("text") for q in rpd_context.get("colloquium_questions_list", []) if q.get("text")]
        colloquium = {
            "criteria": "Оценка 5: глубокие знания; Оценка 4: небольшие неточности; Оценка 3: базовый минимум; Оценка 2: ответ не дан.",
            "sections": [
                {
                    "section_title": "Вопросы для коллоквиума по разделам дисциплины",
                    "questions": colloquium_qs if colloquium_qs else ["Основные теоретические концепции дисциплины."]
                }
            ]
        }

    # Практические кейсы
    case_study = None
    if existing_variables and existing_variables.get("case_study"):
        case_study = existing_variables["case_study"]
    else:
        case_tasks = []
        for pw in rpd_context.get("practical_works_list", []):
            t_desc = f"{pw.get('title')}: {pw.get('case_desc')}"
            case_tasks.append(t_desc)
        case_study = {
            "tasks": case_tasks if case_tasks else ["Анализ производственной ситуации и решение прикладного кейса."],
            "criteria": "Оценка 5: верное и обоснованное решение; Оценка 4: незначительные погрешности; Оценка 3: решение с ошибками; Оценка 2: кейс не решен."
        }

    # Контрольные работы / Тесты
    test_paper = None
    if existing_variables and existing_variables.get("test_paper"):
        test_paper = existing_variables["test_paper"]
    else:
        test_qs = []
        for tq in rpd_context.get("test_questions_list", []):
            test_qs.append(f"{tq.get('question')} (Варианты: {tq.get('a')}; {tq.get('b')}; {tq.get('c')}; {tq.get('d')})")
        test_paper = {
            "criteria": "Оценка 5: 85-100% правильных ответов; Оценка 4: 70-84%; Оценка 3: 50-69%; Оценка 2: менее 50%.",
            "topics": [
                {
                    "topic_title": "Тестовые задания текущего контроля",
                    "variants": [
                        {
                            "variant_name": "Вариант 1",
                            "tasks": test_qs if test_qs else ["Тестовое задание 1."]
                        }
                    ]
                }
            ]
        }

    # Творческий / Индивидуальный проект
    creative_project = None
    if existing_variables and existing_variables.get("creative_project"):
        creative_project = existing_variables["creative_project"]
    else:
        ind_tasks = [it.get("text") for it in rpd_context.get("individual_tasks_list", []) if it.get("text")]
        creative_project = {
            "individual_projects": ind_tasks if ind_tasks else ["Индивидуальный проект по профилю курса."],
            "group_projects": ["Групповой междисциплинарный проект."],
            "criteria": "Оценка 5: проект выполнен полностью и защищен; Оценка 4: незначительные замечания; Оценка 3: проект требует доработки; Оценка 2: проект не сдан."
        }

    # Вопросы к зачету / экзамену
    credit = None
    exam = None
    control_form_name = rpd_context.get("control_form", "зачет с оценкой")
    if existing_variables and existing_variables.get("credit"):
        credit = existing_variables["credit"]
    if existing_variables and existing_variables.get("exam"):
        exam = existing_variables["exam"]

    if not credit and not exam:
        exam_qs = [eq.get("text") for eq in rpd_context.get("exam_credit_questions_list", []) if eq.get("text")]
        credit_or_exam = {
            "questions": exam_qs if exam_qs else ["Вопрос 1 к промежуточной аттестации.", "Вопрос 2 к промежуточной аттестации."],
            "criteria": "Отлично (85-100 б.): исчерпывающий ответ; Хорошо (70-84 б.): твердый ответ; Удовлетворительно (50-69 б.): пороговый уровень; Не зачтено (0-49 б.): не освоено."
        }
        if "экзамен" in control_form_name:
            exam = credit_or_exam
        else:
            credit = credit_or_exam

    omd_data = {
        "institute": institute,
        "department": department,
        "course_code": course_code,
        "course_title": course_title,
        "degree_type": degree_type,
        "fgos_vo": fgos_vo,
        "major_code": major_code,
        "major_title": major_title,
        "profile_title": profile_title,
        "course_year": course_year,
        "semester": semester,
        "study_form": study_form,
        "start_year": start_year,
        "developers": developers,
        "reviewer": reviewer,
        "rpd_reference_text": f"направлению подготовки {major_code} {major_title}",
        "table1": table1,
        "table2": table2,
        "activities": activities,
        "case_study": case_study,
        "colloquium": colloquium,
        "test_paper": test_paper,
        "creative_project": creative_project,
        "credit": credit,
        "exam": exam,
        "rgr": None,
        "essay": None,
        "round_table": None,
        "portfolio": None,
        "roleplay": None,
        "multi_level_tasks": None,
        "course_work": None,
        # Дополнительные метки
        "cathedra_name": department,
        "cathedra_meeting_year": start_year,
        "protocol_num": "__",
        "protocol_month": "___________",
        "protocol_year": start_year,
        "degree_qualification": rpd_context.get("qualification", "магистр"),
        "degree_qualification_genitive": "магистра" if "магистр" in rpd_context.get("qualification", "") else "бакалавра",
        "course_type": "профессиональная подготовка",
        "hours": rpd_context.get("total_hours", "108")
    }

    return omd_data


def save_rpd_to_omd_variables(rpd_context: dict, output_yaml_path: str):
    """Конвертирует контекст РПД и сохраняет в файл variables.yml."""
    omd_data = rpd_context_to_omd_variables(rpd_context)
    os.makedirs(os.path.dirname(os.path.abspath(output_yaml_path)), exist_ok=True)
    with open(output_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(omd_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return output_yaml_path
