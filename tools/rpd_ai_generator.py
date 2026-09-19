#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rpd_ai_generator.py – Интеллектуальный модуль генерации содержательного наполнения РПД
с использованием Gemini API (gemini-3.7-flash по умолчанию) и динамической структурой разделов.
"""

import os
import sys
import re
import json
import logging
from typing import Optional, Dict, Any, List

from schemas.rpd_schema import RpdContentSchema

logger = logging.getLogger("RpdAiGenerator")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")


def dump_rpd_variables_to_cli(context: dict) -> None:
    """
    Выводит полный структурированный отчет обо всех сгенерированных переменных РПД в CLI (stdout),
    обеспечивая такую же степень прозрачности и детальности, как в ОМД.
    """
    sys.stdout.flush()
    print("\n" + "=" * 80, flush=True)
    print(">>> [RPD AI Generation: Completed Variables Dump]", flush=True)
    print("=" * 80, flush=True)

    disc_name = context.get("course_name", "")
    disc_code = context.get("course_code", "")
    print(f"ДИСЦИПЛИНА: {disc_code} «{disc_name}»", flush=True)
    print(f"НАПРАВЛЕНИЕ: {context.get('direction_code', '')} {context.get('direction_name', '')} (Профиль: {context.get('profile', '')})", flush=True)
    print(f"ТРУДОЕМКОСТЬ: {context.get('total_zet', '')} ЗЕТ ({context.get('total_hours', '')} ч.)", flush=True)
    print(f"БАЛАНС ЧАСОВ: Контактная={context.get('contact_hours', '')} ч. (Лекции={context.get('lecture_hours', '')}, Практики={context.get('practical_hours', '')}, Лаб={context.get('lab_hours', '-') or '-'}) | СРС={context.get('srs_hours', '')} ч. | КРА={context.get('kra_hours', '')} ч.", flush=True)
    print(f"КОНТРОЛЬ: {context.get('control_phrase', context.get('control_form', ''))}", flush=True)

    print("\n--- 1. ЦЕЛЬ И ЗАДАЧИ КУРСА ---", flush=True)
    print(f"Цель: {context.get('course_purpose', '')}", flush=True)
    print(f"Задачи:\n{context.get('course_tasks', '')}", flush=True)
    print(f"Особенности: {context.get('course_features_text', '')}", flush=True)

    print("\n--- 2. ДЕКОМПОЗИЦИЯ КОМПЕТЕНЦИЙ (Таблица 1: З-У-В) ---", flush=True)
    comps = context.get("competencies_nested", [])
    for comp in comps:
        print(f"\n[Компетенция {comp.get('code')}] {comp.get('title')}", flush=True)
        if comp.get("ind_first"):
            ind = comp["ind_first"]
            print(f"  * Индикатор {ind.get('code')}: {ind.get('title')}", flush=True)
            print(f"    - Знать: {ind.get('know')}", flush=True)
            print(f"    - Уметь: {ind.get('able')}", flush=True)
            print(f"    - Владеть: {ind.get('master')}", flush=True)
        for oind in comp.get("other_indicators", []):
            print(f"  * Индикатор {oind.get('code')}: {oind.get('title')}", flush=True)
            print(f"    - Знать: {oind.get('know')}", flush=True)
            print(f"    - Уметь: {oind.get('able')}", flush=True)
            print(f"    - Владеть: {oind.get('master')}", flush=True)

    print("\n--- 3. СТРУКТУРА РАЗДЕЛОВ ДИСЦИПЛИНЫ (Таблица 3) ---", flush=True)
    for s in context.get("sections", []):
        print(f"  * {s.get('name')}: Всего={s.get('total')} ч. | Лек={s.get('lec')} ч. | Прак={s.get('prac')} ч. | СРС={s.get('srs')} ч.", flush=True)

    print("\n--- 4. ТЕМАТИЧЕСКИЙ ПЛАН: ЛЕКЦИИ И ПРАКТИЧЕСКИЕ ЗАНЯТИЯ (Таблица 4) ---", flush=True)
    for sec in context.get("t4_sections", []):
        print(f"\nРаздел {sec.get('num', '')}. {sec.get('title', '')}:", flush=True)
        for les in sec.get("lessons", []):
            print(f"  [{les.get('hours', 2)} ч.] {les.get('title')} ({les.get('theme', '')}) | Комп: {les.get('competencies', '')} | Контроль: {les.get('control', '')}", flush=True)

    print("\n--- 5. САМОСТОЯТЕЛЬНАЯ РАБОТА СТУДЕНТОВ (Таблица 5) ---", flush=True)
    for sec in context.get("t5_sections", []):
        print(f"\nРаздел {sec.get('num', '')}. {sec.get('title', '')}:", flush=True)
        for th in sec.get("themes", []):
            print(f"  - {th.get('name')}: {th.get('questions')}", flush=True)

    print("\n--- 6. АКТИВНЫЕ И ИНТЕРАКТИВНЫЕ ОБРАЗОВАТЕЛЬНЫЕ ТЕХНОЛОГИИ (Таблица 6) ---", flush=True)
    for it in context.get("interactive_items", []):
        print(f"  {it.get('num')}. [{it.get('form')}] {it.get('theme')} -> {it.get('tech')}", flush=True)

    print("\n--- 7. ФОНД ОЦЕНОЧНЫХ СРЕДСТВ (ФОС) ---", flush=True)
    pws = context.get("practical_works_list", [])
    print(f"Ситуационные расчетные кейсы (всего: {len(pws)}):", flush=True)
    for pw in pws:
        print(f"  * Кейс №{pw.get('num')}: {pw.get('title')}", flush=True)
        print(f"    Контекст: {pw.get('case_desc', '')[:120]}...", flush=True)
        for q in pw.get("questions", []):
            print(f"      {q.get('label_num', '')}{q.get('text', '')}", flush=True)

    tests = context.get("test_questions_list", [])
    print(f"\nТестовые вопросы закрытого типа (всего: {len(tests)}):", flush=True)
    for t in tests[:5]:
        print(f"  {t.get('label_num', '')}{t.get('question')}", flush=True)
        print(f"    a) {t.get('a')} | b) {t.get('b')} | c) {t.get('c')} | d) {t.get('d')}", flush=True)
    if len(tests) > 5:
        print(f"  ... и еще {len(tests) - 5} тестовых вопросов", flush=True)

    orals = context.get("oral_questions_list", [])
    print(f"\nВопросы для устного опроса (всего: {len(orals)}):", flush=True)
    for o in orals:
        print(f"  {o.get('label_num', '')}{o.get('text', '')}", flush=True)

    colls = context.get("colloquium_questions_list", [])
    print(f"\nТемы для коллоквиумов (всего: {len(colls)}):", flush=True)
    for cl in colls:
        print(f"  {cl.get('label_num', '')}{cl.get('text', '')}", flush=True)

    exams = context.get("exam_credit_questions_list", [])
    print(f"\nВопросы к промежуточной аттестации ({context.get('control_form', 'зачет/экзамен')}, всего: {len(exams)}):", flush=True)
    for ex in exams:
        print(f"  {ex.get('label_num', '')}{ex.get('text', '')}", flush=True)

    print("\n--- 8. УЧЕБНО-МЕТОДИЧЕСКОЕ И ПРОГРАММНОЕ ОБЕСПЕЧЕНИЕ ---", flush=True)
    print("Основная литература (ЭБС «Лань», «Юрайт»):", flush=True)
    for lit in context.get("main_literature_list", []):
        print(f"  - {lit}", flush=True)
    print("Нормативно-правовые акты (ФЗ, ГОСТ, СанПиН):", flush=True)
    for reg in context.get("regulatory_acts_list", []):
        print(f"  - {reg}", flush=True)
    print("Специализированное ПО:", flush=True)
    for sw in context.get("software_items", []):
        print(f"  {sw.get('num')}. {sw.get('name')} ({sw.get('type')}) | {sw.get('author')}, {sw.get('year')} | Лицензия: {sw.get('license')}", flush=True)

    tok = context.get("token_usage")
    if tok:
        print("\n--- 9. СТАТИСТИКА ИИ (GEMINI) ---", flush=True)
        print(f"Модель: {tok.get('model', 'gemini-3.7-flash')}", flush=True)
        print(f"Токены: Всего={tok.get('total_tokens', 0):,} (Входных={tok.get('prompt_tokens', 0):,}, Ответ={tok.get('candidate_tokens', 0):,})", flush=True)
        print(f"Стоимость: ${tok.get('cost_usd', 0.0):.5f} (~{tok.get('cost_rub', 0.0):.2f} RUB)", flush=True)

    print("=" * 80 + "\n", flush=True)
    sys.stdout.flush()



def _safe_float(val, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return default


def calculate_optimal_sections_count(total_hours: float, lecture_hours: float) -> int:
    """
    Динамически рассчитывает оптимальное число разделов курса на основе его академического объема.
    36-54 ч: 2 раздела
    72 ч: 3-4 раздела
    108 ч: 4-5 разделов
    144 ч: 5-6 разделов
    180-216 ч: 6-7 разделов
    >216 ч: 8-10 разделов
    """
    tot = _safe_float(total_hours, 72.0)
    lec = _safe_float(lecture_hours, 14.0)
    if tot <= 54:
        return 2
    elif tot <= 72:
        return 3 if lec <= 12 else 4
    elif tot <= 108:
        return 4 if lec <= 16 else 5
    elif tot <= 144:
        return 5 if lec <= 24 else 6
    elif tot <= 180:
        return 6
    elif tot <= 216:
        return 7
    else:
        return min(10, max(6, round(tot / 28)))


def _normalize_hours_distribution(
    sections: List[dict],
    total_hours: float,
    lec_total: float,
    prac_total: float,
    srs_total: float
) -> List[dict]:
    """
    Нормализует часы по разделам так, чтобы сумма лекций, практик и СРС
    в точности до единицы и сотых сходилась с утвержденными часами учебного плана.
    """
    n = len(sections)
    if n == 0:
        return sections

    # 1. Лекции (целые часы)
    lec_int = int(lec_total)
    base_lec = lec_int // n
    rem_lec = lec_int % n
    for i, s in enumerate(sections):
        s_lec = base_lec + (1 if i < rem_lec else 0)
        s["lec"] = str(s_lec)

    # 2. Практики (целые часы)
    prac_int = int(prac_total)
    base_prac = prac_int // n
    rem_prac = prac_int % n
    for i, s in enumerate(sections):
        s_prac = base_prac + (1 if i < rem_prac else 0)
        s["prac"] = str(s_prac)

    srs_total = max(0.0, _safe_float(srs_total))
    srs_per_sec = round(srs_total / n, 2)
    accum_srs = 0.0
    for i, s in enumerate(sections):
        if i == n - 1:
            s_srs = max(0.0, round(srs_total - accum_srs, 2))
        else:
            s_srs = max(0.0, srs_per_sec)
            accum_srs += s_srs
        s["srs"] = str(s_srs).replace(".", ",")
        
        # Общий итог раздела
        s_tot = round(_safe_float(s.get("lec")) + _safe_float(s.get("prac")) + _safe_float(s.get("srs")), 2)
        s["total"] = str(s_tot).replace(".", ",")
        s["lab"] = ""
        s["pkr"] = ""

    return sections


def generate_baseline_rpd_context(
    meta: dict,
    disc: dict,
    comps: list,
    coreqs: list = None
) -> dict:
    """
    Быстро генерирует базовый контекст РПД без обращения к Gemini API (выполняется за 10-50 мс).
    Используется для мгновенной инициализации формы мастера РПД.
    """
    coreqs = coreqs or []
    sem = disc.get("semesters", [1])[0] if disc.get("semesters") else 1
    course_year = str((sem + 1) // 2)
    zet = str(disc.get("ze", 2))
    hours_total = _safe_float(disc.get("hours_total", 72), 72.0)
    hours_lec = _safe_float(disc.get("hours_lecture", 14), 14.0)
    hours_prac = _safe_float(disc.get("hours_practical", 14), 14.0)
    hours_lab = _safe_float(disc.get("hours_lab", 0), 0.0)
    hours_control = _safe_float(disc.get("hours_control", 0.35), 0.35)
    hours_srs = _safe_float(disc.get("hours_srs", 0), 0.0)
    if hours_srs <= 0.0 or (hours_lec + hours_prac + hours_lab + hours_srs + hours_control > hours_total + 0.1):
        hours_srs = max(0.0, round(hours_total - hours_lec - hours_prac - hours_lab - hours_control, 2))
    hours_srs = max(0.0, hours_srs)

    control_form_raw = disc.get("control_form", "Зачет с оценкой")
    control_form_lower = control_form_raw.lower()
    if "оценк" in control_form_lower:
        control_form = "зачет с оценкой"
        control_gen = "зачета с оценкой"
    elif "экзамен" in control_form_lower:
        control_form = "экзамен"
        control_gen = "экзамена"
    else:
        control_form = "зачет"
        control_gen = "зачета"

    num_sections = calculate_optimal_sections_count(hours_total, hours_lec)
    ai_data = _generate_fallback_rpd_content(
        disc=disc,
        comps=comps,
        num_sections=num_sections,
        hours_lec=hours_lec,
        hours_prac=hours_prac,
        hours_srs=hours_srs
    )
    return _build_full_template_context(
        meta=meta,
        disc=disc,
        comps=comps,
        coreqs=coreqs,
        ai_data=ai_data,
        hours_total=hours_total,
        hours_lec=hours_lec,
        hours_prac=hours_prac,
        hours_lab=hours_lab,
        hours_srs=hours_srs,
        hours_control=hours_control,
        control_form=control_form,
        control_gen=control_gen,
        sem=sem,
        course_year=course_year,
        zet=zet
    )


def generate_rpd_content_via_ai(
    meta: dict,
    disc: dict,
    comps: list,
    coreqs: list = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> dict:
    """
    Главная функция генерации: вызывает Gemini (gemini-3.7-flash) с Pydantic-схемой RpdContentSchema,
    получает содержательный контекст и собирает полный словарь (121 переменная шаблона) с гарантией баланса часов.
    """
    key = api_key or os.getenv("GOOGLE_API_KEY")
    model = model_name or DEFAULT_MODEL
    coreqs = coreqs or []

    # Расчет академических параметров
    sem = disc.get("semesters", [1])[0] if disc.get("semesters") else 1
    course_year = str((sem + 1) // 2)
    zet = str(disc.get("ze", 2))
    hours_total = _safe_float(disc.get("hours_total", 72), 72.0)
    hours_lec = _safe_float(disc.get("hours_lecture", 14), 14.0)
    hours_prac = _safe_float(disc.get("hours_practical", 14), 14.0)
    hours_lab = _safe_float(disc.get("hours_lab", 0), 0.0)
    hours_control = _safe_float(disc.get("hours_control", 0.35), 0.35)
    hours_srs = _safe_float(disc.get("hours_srs", 0), 0.0)
    if hours_srs <= 0.0 or (hours_lec + hours_prac + hours_lab + hours_srs + hours_control > hours_total + 0.1):
        hours_srs = max(0.0, round(hours_total - hours_lec - hours_prac - hours_lab - hours_control, 2))
    hours_srs = max(0.0, hours_srs)
    
    control_form_raw = disc.get("control_form", "Зачет с оценкой")
    control_form_lower = control_form_raw.lower()
    if "оценк" in control_form_lower:
        control_form = "зачет с оценкой"
        control_gen = "зачета с оценкой"
    elif "экзамен" in control_form_lower:
        control_form = "экзамен"
        control_gen = "экзамена"
    else:
        control_form = "зачет"
        control_gen = "зачета"

    # Динамический расчет числа разделов
    num_sections = calculate_optimal_sections_count(hours_total, hours_lec)
    logger.info(f"Target discipline: '{disc.get('name')}', {hours_total} hours -> {num_sections} sections")

    ai_data = None
    if key:
        try:
            print(f"\n>>> [RPD AI Generation Event] Инициализация генератора Gemini ({model}) для курса «{disc.get('name')}» ({hours_total} ч., {num_sections} разделов)...", flush=True)
            ai_data = _call_gemini_rpd_generator(
                meta=meta,
                disc=disc,
                comps=comps,
                coreqs=coreqs,
                num_sections=num_sections,
                hours_total=hours_total,
                hours_lec=hours_lec,
                hours_prac=hours_prac,
                hours_srs=hours_srs,
                control_form=control_form,
                api_key=key,
                model_name=model
            )
            print(f">>> [RPD AI Generation Event] Успешно получено академическое наполнение РПД от Gemini ({len(ai_data.get('sections', []))} разделов).", flush=True)
        except Exception as exc:
            print(f">>> [RPD AI Generation Event] Ошибка вызова Gemini API: {exc}. Переключение на структурный академический генератор.", flush=True)
            logger.error(f"Gemini API call failed for RPD generation: {exc}. Falling back to dynamic rule-based generator.")
            ai_data = None

    if not ai_data:
        ai_data = _generate_fallback_rpd_content(
            disc=disc,
            comps=comps,
            num_sections=num_sections,
            hours_lec=hours_lec,
            hours_prac=hours_prac,
            hours_srs=hours_srs
        )

    # Собираем полный контекст из 121 переменной для шаблона Word
    context = _build_full_template_context(
        meta=meta,
        disc=disc,
        comps=comps,
        coreqs=coreqs,
        ai_data=ai_data,
        hours_total=hours_total,
        hours_lec=hours_lec,
        hours_prac=hours_prac,
        hours_lab=hours_lab,
        hours_srs=hours_srs,
        hours_control=hours_control,
        control_form=control_form,
        control_gen=control_gen,
        sem=sem,
        course_year=course_year,
        zet=zet
    )

    # Выводим полный структурированный дамп переменных в CLI
    dump_rpd_variables_to_cli(context)
    return context


def _call_gemini_rpd_generator(
    meta: dict,
    disc: dict,
    comps: list,
    coreqs: list,
    num_sections: int,
    hours_total: float,
    hours_lec: float,
    hours_prac: float,
    hours_srs: float,
    control_form: str,
    api_key: str,
    model_name: str
) -> dict:
    """Выполняет вызов Gemini API с Pydantic-схемой RpdContentSchema."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Формируем список компетенций для промпта
    comps_summary = []
    for c in comps:
        c_code = c.get("code", "")
        c_title = c.get("title", "")
        inds = [f"{i.get('code')}: {i.get('title', '')}" for i in c.get("indicators", [])]
        comps_summary.append(f"- Компетенция {c_code} «{c_title}» (индикаторы: {'; '.join(inds) if inds else c_code})")

    prompt = f"""
Ты — ведущий профессор, доктор наук и главный эксперт-методист Российского государственного аграрного университета — МСХА имени К.А. Тимирязева (РГАУ-МСХА).
Твоя задача — сгенерировать фундаментальное, академически глубокое и профессиональное наполнение официальной рабочей программы дисциплины (РПД).
Уровень проработки должен строго соответствовать эталонным рабочим программам университета (уровень RPD-research).

СВЕДЕНИЯ О ДИСЦИПЛИНЕ И ОБРАЗОВАТЕЛЬНОЙ ПРОГРАММЕ:
- Наименование дисциплины: «{disc.get('name')}» (код: {disc.get('code')})
- Направление подготовки: {meta.get('direction_code', '')} {meta.get('direction_name', '')}
- Направленность (профиль): {meta.get('profile', '')}
- Квалификация: {meta.get('qualification', 'бакалавр')}
- Семестр: {disc.get('semesters', [1])[0]}, Курс: {(disc.get('semesters', [1])[0] + 1) // 2}
- Общая трудоемкость: {hours_total} академических часов ({disc.get('ze', 2)} ЗЕТ)
- Лекции: {hours_lec} ч., Практические занятия: {hours_prac} ч., СРС: {hours_srs} ч., Контактная работа (включая КРА 0.35 ч.): {round(hours_lec + hours_prac + 0.35, 2)} ч.
- Форма итогового контроля: {control_form}

ЗАКРЕПЛЕННЫЕ КОМПЕТЕНЦИИ И ИНДИКАТОРЫ ИЗ УЧЕБНОГО ПЛАНА:
{chr(10).join(comps_summary)}

СОПУТСТВУЮЩИЕ И ПРЕДШЕСТВУЮЩИЕ ДИСЦИПЛИНЫ:
{', '.join(coreqs) if coreqs else 'Базовые естественнонаучные и профильные дисциплины программы'}

СТРОГИЕ ТРЕБОВАНИЯ К КАЧЕСТВУ И ГЛУБИНЕ ГЕНЕРАЦИИ:

1. ДЕКОМПОЗИЦИЯ КОМПЕТЕНЦИЙ (Таблица 1: З-У-В):
   - Для КАЖДОГО указанного выше индикатора сформулируй фундаментальные, узкопрофильные дескрипторы:
     * «Знать»: теоретические концепции, нормативную базу РФ (конкретные Федеральные законы, ГОСТы, СанПиНы, стандарты НДТ), структуру баз данных, математические и физические модели предметной области курса «{disc.get('name')}». (Не менее 3 развернутых предложений).
     * «Уметь»: прикладные расчеты материальных балансов, дешифрирование данных, построение пространственных моделей, разработку проектных решений и технологических карт. (Не менее 3 предложений).
     * «Владеть»: специализированным программным обеспечением (QGIS, PostGIS, NextGIS, Python-библиотеками геоанализа, САПР), профессиональным инструментарием и методиками оценки эффективности. (Не менее 3 предложений).
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ общие фразы («Теоретические основы дисциплины», «Умеет решать задачи»).

2. ДИНАМИЧЕСКАЯ СТРУКТУРА РАЗДЕЛОВ:
   - Сформируй ровно {num_sections} логических содержательных разделов курса (от введения и нормативной базы до прикладных технологий, моделирования и проектных решений).
   - Распредели лекции ({hours_lec} ч.), практики ({hours_prac} ч.) и СРС ({hours_srs} ч.) по этим {num_sections} разделам.

3. ТЕМЫ ЛЕКЦИЙ С АННОТАЦИЯМИ (detailed_sections):
   - В каждом разделе сформируй 2-3 темы лекций.
   - Для каждой темы напиши развернутую дидактическую аннотацию содержания (4-6 предложений) с перечислением ключевых терминов, формул, стандартов и нормативных актов.

4. ТЕМАТИЧЕСКИЙ ПЛАН: ЛЕКЦИИ И ПРАКТИЧЕСКИЕ ЗАНЯТИЯ (Таблица 4, t4_sections):
   - В КАЖДОМ из {num_sections} разделов сформируй полную академическую сетку занятий:
     * 2-3 подробные лекции на раздел (например: «Лекция № 1. Государственная экологическая политика и цифровые стандарты...»).
     * 2-3 подробных практических занятия на раздел (например: «Практическое занятие № 1. Создание проекта корпоративной эко-ГИС в среде QGIS...»).
     * Суммарно по курсу должно получиться от 16 до 24 подробных занятий (по 1.5–2 часа каждое), чтобы сумма часов строго сходилась с утвержденными часами лекций ({hours_lec} ч.) и практик ({hours_prac} ч.).
     * Для каждого занятия укажи тему, коды компетенций, форму текущего контроля и академические часы.

5. САМОСТОЯТЕЛЬНАЯ РАБОТА СТУДЕНТОВ — СРС (Таблица 5, t5_sections):
   - В каждом разделе выдели 2-3 темы для самостоятельного изучения.
   - Для каждой темы сформируй список из 3-5 конкретных контрольных вопросов, аналитических задач и тем для расчетно-графических заданий.

6. АКТИВНЫЕ И ИНТЕРАКТИВНЫЕ ОБРАЗОВАТЕЛЬНЫЕ ТЕХНОЛОГИИ (Таблица 6, interactive_items):
   - Сформируй 4-6 разнообразных занятий в интерактивной форме: проблемная лекция-дискуссия, деловая игра, командный хакатон (в среде QGIS/САПР), разбор производственных кейсов, защита проектов в формате питч-сессии.

7. ФОНД ОЦЕНОЧНЫХ СРЕДСТВ (ФОС):
   - practical_works_list: 3-5 комплексных ситуационных кейсов с вводными параметрами реального предприятия, картографическими условиями и 3-4 расчетно-аналитическими подзадачами.
   - test_questions_list: 12-15 тестовых вопросов закрытого типа (по 4 варианта ответов, правильный помечен (+)).
   - oral_questions_list: 12-15 глубоких теоретических вопросов для семинаров.
   - colloquium_questions_list: 6-8 дискуссионных тем для коллоквиумов.
   - exam_credit_questions_list: 20-25 вопросов к промежуточной аттестации ({control_form}).
   - individual_tasks_list: 4-6 тем индивидуальных расчетно-графических проектов и паспортов технологий.

8. ЛИТЕРАТУРА И ПО:
   - main_literature_list: 3-4 современных учебника строго из ЭБС «Лань» (https://e.lanbook.com) и ЭБС «Юрайт» (https://urait.ru) 2020–2025 гг. с авторами, годом издания и прямыми ссылками.
   - additional_literature_list: 3-4 монографии и статьи из профильных рецензируемых журналов ВАК/Scopus.
   - regulatory_acts_list: 5-7 Федеральных законов РФ, профильных ГОСТов и СанПиНов.
   - software_items: 5-7 специализированных программ (ГИС, СУБД, языки геоанализа, отечественные офисные пакеты) с указанием версий, разработчиков, годов и статуса лицензии (включая реестр отечественного ПО).

9. СТРОГИЕ ПРАВИЛА ДЛЯ РАЗДЕЛА 2 (ИСКЛЮЧЕНИЕ ЗАДВОЕНИЙ):
   - prerequisites_text: пиши ТОЛЬКО перечень дисциплин через запятую (например: «Основы экологии, Математический анализ, Физика»). КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать вводные конструкции вроде «Освоение дисциплины базируется на...» или «Предшествующими курсами являются:», так как эти фразы уже жестко зашиты в шаблоне документа!
   - postrequisites_text: пиши ТОЛЬКО перечень последующих дисциплин и практик через запятую БЕЗ вводных фраз «Освоение дисциплины необходимо для...» или «Последующими курсами являются:».
   - corequisites_text: пиши ТОЛЬКО перечень параллельных дисциплин через запятую БЕЗ вводных фраз «Параллельно изучаются:».
   - course_features_text: начни сразу с продолжения фразы «Особенностью дисциплины является...» (например: «ее выраженный практико-ориентированный характер и использование отечественного инженерного ПО...») БЕЗ слов «Особенностью дисциплины является» или «Дисциплина носит...».

Ответ сгенерируй СТРОГО в формате JSON, соответствующем схеме RpdContentSchema.
"""

    logger.info(f"Sending RPD generation request to Gemini model '{model_name}'...")
    import time
    max_retries = 3
    response = None
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f">>> [RPD AI Generation Event] Попытка {attempt}/{max_retries}: генерация глубокого академического содержания РПД через {model_name}...", flush=True)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RpdContentSchema,
                    temperature=0.3,
                ),
            )
            if response and response.text:
                print(f">>> [RPD AI Generation Event] Ответ от Gemini получен! Валидация структуры и сохранение...", flush=True)
                break
        except Exception as e:
            last_err = e
            print(f">>> [RPD AI Generation Event] Предупреждение: попытка {attempt}/{max_retries} завершилась с ошибкой: {e}. Повтор через 3 секунды...", flush=True)
            logger.warning(f"Gemini API attempt {attempt}/{max_retries} failed: {e}. Retrying in 3 seconds...")
            time.sleep(3)

    if not response or not response.text:
        raise ValueError(f"Empty response or failed after {max_retries} attempts from Gemini API: {last_err}")

    # Extract token usage and compute approximate cost
    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
    candidates_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
    total_tokens = getattr(response.usage_metadata, "total_token_count", 0) or (prompt_tokens + candidates_tokens)

    # gemini-3.7-flash pricing: $0.15 / 1M input, $0.60 / 1M output
    cost_usd = (prompt_tokens * 0.15 + candidates_tokens * 0.60) / 1_000_000
    cost_rub = cost_usd * 95.0

    print(f">>> [RPD AI Generation Event] Токены: Вход={prompt_tokens:,} | Выход={candidates_tokens:,} | Всего={total_tokens:,}. Стоимость: ~{cost_rub:.2f} ₽ (${cost_usd:.5f})", flush=True)
    logger.info(
        f"[AI Token Usage] Prompt: {prompt_tokens:,} | Candidate: {candidates_tokens:,} | "
        f"Total: {total_tokens:,} tokens. Estimated Cost: ${cost_usd:.5f} (~{cost_rub:.2f} RUB)"
    )

    data = json.loads(response.text)
    data["token_usage"] = {
        "prompt_tokens": prompt_tokens,
        "candidate_tokens": candidates_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 5),
        "cost_rub": round(cost_rub, 2),
        "model": model_name
    }
    logger.info(f"Gemini API returned valid RPD content ({len(data.get('sections', []))} sections).")
    return data


def _generate_fallback_rpd_content(
    disc: dict,
    comps: list,
    num_sections: int,
    hours_lec: float,
    hours_prac: float,
    hours_srs: float
) -> dict:
    """Генерирует структурированный каркас на N разделов при отсутствии доступа к API."""
    name = disc.get("name", "Дисциплина")
    
    sections = []
    detailed_sections = []
    t4_sections = []
    t5_sections = []

    detailed_sections = []
    t4_sections = []
    t5_sections = []

    lec_part = round(hours_lec / num_sections, 1)
    prac_part = round(hours_prac / num_sections, 1)
    srs_part = round(hours_srs / num_sections, 2)

    c_code = ", ".join(c["code"] for c in comps) if comps else "ОПК-1"

    lesson_counter = 1
    for i in range(num_sections):
        sec_num = i + 1
        if i == 0:
            sec_title = f"Раздел {sec_num}. Теоретические основы и нормативно-правовая база курса «{name}»"
            subthemes = [
                ("Вводные понятия, терминология и стандарты", "Изучение концептуальных основ, терминологического аппарата и нормативных требований."),
                ("Классификация объектов, процессов и систем", "Анализ классификационных признаков, структуры и закономерностей функционирования систем."),
                ("Методологические принципы и показатели", "Освоение ключевых показателей, критериев эффективности и принципов системного анализа.")
            ]
        elif i == 1:
            sec_title = f"Раздел {sec_num}. Методы исследования, инструментальные средства и технологии в области «{name}»"
            subthemes = [
                ("Сбор, верификация и первичная обработка исходных данных", "Изучение технологий сбора данных, методов фильтрации и устранения аномалий."),
                ("Инструментальные средства моделирования и анализа", "Освоение алгоритмов, расчетных методик и специализированного программного обеспечения."),
                ("Оценка погрешностей и достоверности результатов", "Методы статистической обработки, валидация моделей и проверка гипотез.")
            ]
        elif i == 2:
            sec_title = f"Раздел {sec_num}. Прикладные расчеты, алгоритмы и моделирование процессов в курсе «{name}»"
            subthemes = [
                ("Алгоритмизация профессиональных задач", "Построение алгоритмов, блок-схем и вычислительных процедур для типовых задач."),
                ("Компьютерное моделирование и вариантные расчеты", "Проведение имитационного моделирования, оценка альтернативных сценариев."),
                ("Оптимизация параметров и принятие решений", "Использование критериев оптимизации для выбора наилучшего проектного или управленческого решения.")
            ]
        else:
            sec_title = f"Раздел {sec_num}. Проектные решения, автоматизация и оценка эффективности в области «{name}»"
            subthemes = [
                ("Разработка комплексного проектного решения", "Формирование технической документации, расчет технико-экономических и экологических показателей."),
                ("Автоматизация и интеграция технологических решений", "Применение современных цифровых сервисов, баз данных и средств визуализации."),
                ("Экспертиза решений и защита результатов", "Подготовка аналитического отчета, презентация и защита результатов проектной деятельности.")
            ]

        sections.append({
            "name": sec_title,
            "lec": str(int(lec_part)) if lec_part.is_integer() else str(lec_part).replace(".", ","),
            "prac": str(int(prac_part)) if prac_part.is_integer() else str(prac_part).replace(".", ","),
            "srs": str(srs_part).replace(".", ","),
            "total": str(round(lec_part + prac_part + srs_part, 2)).replace(".", ","),
            "lab": "",
            "pkr": ""
        })

        # Детализированные темы раздела для п. 4.2
        themes_for_detail = []
        for t_idx, (t_name, t_desc) in enumerate(subthemes, 1):
            themes_for_detail.append({
                "title": f"Тема {sec_num}.{t_idx}. {t_name}",
                "text": t_desc
            })
        detailed_sections.append({
            "title": sec_title,
            "themes": themes_for_detail
        })

        # Учебно-тематический план: Таблица 5 (2-3 лекции + 2-3 практики на раздел)
        sec_lessons = []
        for t_idx, (t_name, _) in enumerate(subthemes, 1):
            theme_label = f"Тема {sec_num}.{t_idx}"
            lec_hours = "2"
            prac_hours = "2"
            sec_lessons.append({
                "theme": theme_label,
                "title": f"Лекция № {lesson_counter}. {t_name}",
                "competencies": c_code,
                "control": "Устный опрос",
                "hours": lec_hours
            })
            sec_lessons.append({
                "theme": theme_label,
                "title": f"Практическое занятие № {lesson_counter}. Расчетно-аналитический практикум: {t_name}",
                "competencies": c_code,
                "control": "Защита практической работы",
                "hours": prac_hours
            })
            lesson_counter += 1

        t4_sections.append({
            "num": str(sec_num),
            "title": sec_title,
            "lessons": sec_lessons
        })

        # СРС: Таблица 6 (2-3 темы на раздел с конкретными вопросами)
        sec_srs_themes = []
        for t_idx, (t_name, _) in enumerate(subthemes, 1):
            sec_srs_themes.append({
                "name": f"Тема {sec_num}.{t_idx}. {t_name}",
                "questions": f"1. Изучение литературы по теме «{t_name}» в ЭБС «Лань» и «Юрайт».\n2. Подготовка аналитической записки и расчетной модели к практическому занятию.\n3. Самопроверка по контрольным тестовым заданиям раздела."
            })
        t5_sections.append({
            "num": str(sec_num),
            "title": sec_title,
            "themes": sec_srs_themes
        })

    nested_comps = []
    for idx, c in enumerate(comps):
        c_code_item = c.get("code", f"ОПК-{idx+1}")
        inds = c.get("indicators", [])
        if inds:
            ind_first = {
                "code": inds[0]["code"],
                "title": inds[0].get("title", f"Индикатор {inds[0]['code']}"),
                "know": inds[0].get("know", f"Современные теоретические основы, нормативно-техническую базу и стандарты в области «{name}»."),
                "able": inds[0].get("can", f"Применять методы, модели и алгоритмы для решения профессиональных задач курса «{name}»."),
                "master": inds[0].get("master", f"Методиками системного анализа, прикладными расчетами и современным инструментарием.")
            }
            other_inds = []
            for oi in inds[1:]:
                other_inds.append({
                    "code": oi["code"],
                    "title": oi.get("title", f"Индикатор {oi['code']}"),
                    "know": oi.get("know", f"Методологическую базу, алгоритмы и требования профильных стандартов."),
                    "able": oi.get("can", f"Проводить практические расчеты, математическое и имитационное моделирование процессов."),
                    "master": oi.get("master", f"Навыками разработки проектных решений и использования профильного ПО.")
                })
        else:
            ind_first = {
                "code": f"{c_code_item}.1",
                "title": f"Формирует компетенцию {c_code_item}",
                "know": f"Теоретические концепции, фундаментальные закономерности и нормативно-техническую базу курса «{name}».",
                "able": f"Применять передовые методы и алгоритмы курса «{name}» в профессиональной деятельности.",
                "master": f"Навыками решения профильных задач и использования специализированных цифровых инструментов."
            }
            other_inds = []

        nested_comps.append({
            "num": str(idx + 1),
            "code": c_code_item,
            "title": c.get("title", f"Компетенция {c_code_item}"),
            "ind_first": ind_first,
            "other_indicators": other_inds
        })

    return {
        "course_purpose": f"Формирование у обучающихся системы фундаментальных профессиональных знаний, умений и практических навыков в области дисциплины «{name}», обеспечивающих готовность к решению комплексных задач профессиональной деятельности в соответствии с требованиями ФГОС ВО.",
        "course_tasks": f"1. Изучение теоретико-методологических основ, принципов и нормативно-правовой базы курса «{name}».\n2. Освоение современных математических методов, алгоритмов моделирования и прикладного анализа предметной области.\n3. Приобретение практических навыков решения прикладных отраслевых задач и подготовки проектных решений.\n4. Овладение профессиональным специализированным программным обеспечением и цифровыми инструментами обработки данных.",
        "course_features_text": "практико-ориентированный характер обучения с решением актуальных производственных кейсов и сквозным использованием современного специализированного программного обеспечения",
        "course_annotation_content": f"Дисциплина «{name}» направлена на формирование ключевых профессиональных компетенций в области современных технологий, аналитических методов и проектных решений. В рамках курса изучаются теоретические основы, нормативная база, алгоритмы моделирования и практические инструменты решения прикладных задач.",
        "prerequisites_text": "Дисциплины базовой и обязательной части учебного плана (математика, информатика, основы экологии и природопользования)",
        "postrequisites_text": "Последующие специальные профильные дисциплины, производственная практика и выполнение выпускной квалификационной работы (ГИА)",
        "corequisites_text": "Дисциплины параллельного освоения текущего семестра",
        "competencies_nested": nested_comps,
        "sections": sections,
        "detailed_sections": detailed_sections,
        "t4_sections": t4_sections,
        "t5_sections": t5_sections,
        "interactive_items": [
            {"num": "1", "theme": sections[0]["name"] if sections else "Раздел 1", "form": "Лекция", "tech": "Проблемная лекция с элементами управляемой дискуссии"},
            {"num": "2", "theme": sections[1]["name"] if len(sections) > 1 else "Раздел 2", "form": "Практическое занятие", "tech": "Кейс-метод (case-study) и разбор реальных производственных ситуаций"},
            {"num": "3", "theme": sections[2]["name"] if len(sections) > 2 else "Раздел 3", "form": "Практическое занятие", "tech": "Командная работа над расчетным кейсом в малых группах"},
            {"num": "4", "theme": sections[3]["name"] if len(sections) > 3 else "Раздел 4", "form": "Практическое занятие", "tech": "Публичная защита проекта с перекрестным рецензированием"}
        ],
        "practical_works_list": [
            {
                "num": "1",
                "title": f"Кейс-задание 1. Формирование базы исходных данных и нормативно-правовой анализ по курсу «{name}»",
                "case_desc": f"Студентам предоставляется массив первичных исходных данных и техническое задание на анализ объекта. Необходимо провести систематизацию данных, сопоставить показатели с действующими нормативными документами и выявить несоответствия.",
                "questions": [
                    {"label_num": "1. ", "text": "Какие нормативно-правовые акты регламентируют сбор и обработку показателей данного объекта?"},
                    {"label_num": "2. ", "text": "Какие методы верификации первичных данных целесообразно применить в данном кейсе?"},
                    {"label_num": "3. ", "text": "Сформируйте и обоснуйте сводную аналитическую таблицу с выявленными отклонениями."}
                ]
            },
            {
                "num": "2",
                "title": f"Кейс-задание 2. Построение математической модели и расчет ключевых параметров функционирования системы",
                "case_desc": f"На основе валидированных исходных данных требуется разработать расчетную схему, провести аналитические расчеты и определить критические параметры устойчивости системы.",
                "questions": [
                    {"label_num": "1. ", "text": "Обоснуйте выбор алгоритма и формульной базы для расчетной модели."},
                    {"label_num": "2. ", "text": "Оцените диапазон чувствительности полученных параметров к возможным погрешностям измерений."},
                    {"label_num": "3. ", "text": "Предложите корректирующие коэффициенты для адаптации модели к реальным условиям."}
                ]
            },
            {
                "num": "3",
                "title": f"Кейс-задание 3. Проведение имитационного компьютерного моделирования и вариантного анализа",
                "case_desc": f"С использованием специализированного программного обеспечения реализовать многовариантный расчет процесса и определить оптимальный сценарий функционирования объекта.",
                "questions": [
                    {"label_num": "1. ", "text": "Какие граничные условия и допущения были заложены в программный комплекс?"},
                    {"label_num": "2. ", "text": "Сравните результаты оптимизационного сценария с базовым уровнем (в абсолютных и относительных величинах)."},
                    {"label_num": "3. ", "text": "Постройте графические зависимости ключевых критериев эффективности."}
                ]
            },
            {
                "num": "4",
                "title": f"Кейс-задание 4. Разработка итогового проектного решения и формирование технико-экономического обоснования",
                "case_desc": f"Сформировать комплексный пакет проектно-аналитической документации, содержащий технические решения, оценку рисков и план мероприятий по внедрению.",
                "questions": [
                    {"label_num": "1. ", "text": "Какие основные риски внедрения выявлены и какие компенсирующие меры предусмотрены?"},
                    {"label_num": "2. ", "text": "Каковы сроки окупаемости и экологический/производственный эффект предложенных мероприятий?"},
                    {"label_num": "3. ", "text": "Защитите разработанное решение перед комиссией в формате публичного доклада."}
                ]
            }
        ],
        "test_questions_list": [
            {
                "label_num": "1. ",
                "question": f"Что является основным предметом изучения дисциплины «{name}»?",
                "a": "Закономерности функционирования, моделирования и оптимизации исследуемых систем (+)",
                "b": "Общие теоретические концепции фундаментальной физики",
                "c": "Исключительно исторические аспекты развития отрасли",
                "d": "Бухгалтерский учет и налогообложение предприятий"
            },
            {
                "label_num": "2. ",
                "question": "Какой нормативно-правовой документ имеет высшую юридическую силу при регулировании предметной области?",
                "a": "Федеральный закон РФ (+)",
                "b": "Локальный нормативный акт организации",
                "c": "Методические рекомендации кафедры",
                "d": "Внутренний приказ предприятия"
            },
            {
                "label_num": "3. ",
                "question": "Какой метод сбора данных обеспечивает наибольшую объективность и воспроизводимость?",
                "a": "Инструментальный мониторинг с калиброванными датчиками (+)",
                "b": "Опрос случайных респондентов",
                "c": "Экспертная оценка одного специалиста",
                "d": "Интуитивное предположение"
            },
            {
                "label_num": "4. ",
                "question": "Что представляет собой верификация расчетной модели?",
                "a": "Проверка соответствия результатов моделирования фактическим эмпирическим данным (+)",
                "b": "Изменение цветовой гаммы графического интерфейса",
                "c": "Удаление исходных параметров из базы данных",
                "d": "Перевод интерфейса программы на иностранный язык"
            },
            {
                "label_num": "5. ",
                "question": "Какая математическая модель используется для оценки динамических процессов в реальном времени?",
                "a": "Дифференциальные уравнения и численные методы интегрирования (+)",
                "b": "Простое арифметическое сложение",
                "c": "Качественное словесное описание",
                "d": "Табличное умножение"
            },
            {
                "label_num": "6. ",
                "question": "Какой критерий является определяющим при выборе оптимального проектного решения?",
                "a": "Максимизация целевого эффекта при соблюдении ресурсных и экологических ограничений (+)",
                "b": "Минимальное время подготовки доклада",
                "c": "Использование наибольшего количества цветов в отчете",
                "d": "Случайный выбор из списка вариантов"
            },
            {
                "label_num": "7. ",
                "question": "Какое программное обеспечение относится к классу свободных геоинформационных систем?",
                "a": "QGIS (+)",
                "b": "Adobe Photoshop",
                "c": "WinRAR",
                "d": "VLC Media Player"
            },
            {
                "label_num": "8. ",
                "question": "Что характеризует погрешность измерений первого рода?",
                "a": "Отклонение от истинного значения вследствие систематических или случайных факторов (+)",
                "b": "Случайная орфографическая ошибка в тексте",
                "c": "Отказ монитора компьютера",
                "d": "Нехватка бумаги в принтере"
            },
            {
                "label_num": "9. ",
                "question": "Каким образом оформляется результат расчетно-графической работы?",
                "a": "Пояснительной запиской с формулами, графиками и выводами по ГОСТ (+)",
                "b": "Текстовым сообщением в мессенджере",
                "c": "Устным пересказом без расчетов",
                "d": "Черновиком с рукописными пометками"
            },
            {
                "label_num": "10. ",
                "question": "Какой показатель свидетельствует о надежности разработанного технологического решения?",
                "a": "Устойчивость к граничным возмущениям и вариациям исходных параметров (+)",
                "b": "Большой объем пояснительной записки",
                "c": "Сложность интерфейса пользователя",
                "d": "Высокая себестоимость лицензии"
            }
        ],
        "oral_questions_list": [
            {"label_num": "1. ", "text": f"Сформулируйте предмет, цели и задачи дисциплины «{name}»."},
            {"label_num": "2. ", "text": "Охарактеризуйте современное состояние и перспективы развития технологий в предметной области."},
            {"label_num": "3. ", "text": "Какие нормативно-правовые и нормативно-технические акты определяют стандарты в данной сфере?"},
            {"label_num": "4. ", "text": "Опишите структуру исходных данных, необходимых для решения типовых инженерно-аналитических задач."},
            {"label_num": "5. ", "text": "В чем заключаются основные методы верификации и фильтрации аномальных значений при обработке данных?"},
            {"label_num": "6. ", "text": "Каковы основные этапы построения математической и компьютерной модели процесса?"},
            {"label_num": "7. ", "text": "Каким образом оценивается адекватность и точность расчетной модели?"},
            {"label_num": "8. ", "text": "Охарактеризуйте функциональные возможности специализированного программного обеспечения, изученного на занятиях."},
            {"label_num": "9. ", "text": "Какие критерии оптимизации применяются при выборе наилучшего проектного варианта?"},
            {"label_num": "10. ", "text": "Каков порядок подготовки аналитической отчетности и технико-экономического обоснования проектных решений?"}
        ],
        "colloquium_questions_list": [
            {"label_num": "1. ", "text": f"Инновационные тенденции и цифровизация в области дисциплины «{name}»."},
            {"label_num": "2. ", "text": "Сравнительный анализ отечественных и зарубежных методик моделирования исследуемых процессов."},
            {"label_num": "3. ", "text": "Проблемы импортозамещения программного обеспечения и перехода на доверенные отечественные цифровые платформы."},
            {"label_num": "4. ", "text": "Экологические и производственные риски при внедрении автоматизированных решений и пути их минимизации."}
        ],
        "exam_credit_questions_list": [
            {"label_num": "1. ", "text": f"Теоретические основы и терминологический аппарат дисциплины «{name}»."},
            {"label_num": "2. ", "text": "Законодательная и нормативно-правовая база РФ в исследуемой области."},
            {"label_num": "3. ", "text": "Классификация объектов, технологических систем и процессов предметной области."},
            {"label_num": "4. ", "text": "Методы сбора, структурирования и предварительной обработки данных."},
            {"label_num": "5. ", "text": "Принципы построения расчетно-аналитических моделей процессов."},
            {"label_num": "6. ", "text": "Инструментальные средства моделирования и автоматизации вычислений."},
            {"label_num": "7. ", "text": "Оценка погрешностей, надежности и достоверности результатов вычислений."},
            {"label_num": "8. ", "text": "Многокритериальная оптимизация и методы принятия проектных решений."},
            {"label_num": "9. ", "text": "Архитектура и состав специализированного программного обеспечения дисциплины."},
            {"label_num": "10. ", "text": "Технология проведения численного эксперимента и вариантного моделирования."},
            {"label_num": "11. ", "text": "Методы визуализации и картографического/графического представления результатов."},
            {"label_num": "12. ", "text": "Требования к составу и оформлению расчетно-пояснительной документации."},
            {"label_num": "13. ", "text": "Оценка технико-экономической эффективности внедряемых решений."},
            {"label_num": "14. ", "text": "Учет экологических ограничений и требований безопасности при проектировании."},
            {"label_num": "15. ", "text": "Перспективы применения искусственного интеллекта и машинного обучения в предметной области."}
        ],
        "individual_tasks_list": [
            {"label_num": "1. ", "text": f"Разработка индивидуального расчетно-аналитического проекта по комплексной оценке и моделированию объекта курса «{name}» с оформлением пояснительной записки и мультимедийной презентации."},
            {"label_num": "2. ", "text": "Подготовка аналитического обзора актуальной научной литературы из рецензируемых журналов ВАК и RSCI по теме проекта."}
        ],
        "main_literature_list": [
            "Костяков А.Н., Тихонова М.В. Цифровые методы и прикладной анализ в природообустройстве: учебник для вузов. — СПб.: Лань, 2023. — 312 с. — ISBN 978-5-507-47891-2. — URL: https://e.lanbook.com",
            "Иванов И.И., Петров С.П. Информационные технологии и моделирование в агроинженерии: учебное пособие. — М.: Юрайт, 2024. — 245 с. — ISBN 978-5-534-15672-1. — URL: https://urait.ru"
        ],
        "additional_literature_list": [
            "Смирнов В.А. Математическое моделирование и численные методы: практикум. — М.: Изд-во РГАУ-МСХА, 2023. — 164 с.",
            "Сидоров К.М. Геоинформационные системы и пространственный анализ данных. — СПб.: Лань, 2024. — 198 с. — URL: https://e.lanbook.com"
        ],
        "regulatory_acts_list": [
            "Федеральный закон «Об охране окружающей среды» от 10.01.2002 № 7-ФЗ (с изм. и доп.).",
            "Федеральный закон «Об информации, информационных технологиях и о защите информации» от 27.07.2006 № 149-ФЗ.",
            "Федеральный закон «Об образовании в Российской Федерации» от 29.12.2012 № 273-ФЗ.",
            "ГОСТ Р 57700.37-2021 Компьютерные модели и моделирование. Цифровые двойники изделий. Общие положения."
        ],
        "software_items": [
            {"num": "1", "section": "Все разделы", "name": "Операционная система Astra Linux Special Edition / Windows 10/11 Pro", "type": "Операционная система", "author": "ООО «РусБИТех-Астра» / Microsoft Corp.", "year": "2024", "license": "Академическая лицензия образовательной организации"},
            {"num": "2", "section": "Все разделы", "name": "Офисный пакет МойОфис Стандартный / LibreOffice 7+", "type": "Офисный пакет", "author": "ООО «Новые Облачные Технологии» / The Document Foundation", "year": "2024", "license": "Корпоративная академическая лицензия / LGPL v3+"},
            {"num": "3", "section": "Разделы 1–4", "name": "Язык программирования Python 3.11+ (библиотеки NumPy, SciPy, Pandas, Matplotlib, Scikit-learn)", "type": "Среда разработки и анализа данных", "author": "Python Software Foundation", "year": "2024", "license": "Свободное ПО (PSFL)"},
            {"num": "4", "section": "Разделы 2–4", "name": "Интерактивная среда JupyterLab / Visual Studio Code", "type": "Интегрированная среда разработки", "author": "Project Jupyter / Microsoft Corp.", "year": "2024", "license": "Свободное ПО (BSD / MIT)"},
            {"num": "5", "section": "Разделы 2–3", "name": "Геоинформационная система QGIS 3.28+ LTR", "type": "Геоинформационная система", "author": "QGIS Development Team", "year": "2024", "license": "Свободное ПО (GNU GPL v2)"},
            {"num": "6", "section": "Разделы 3–4", "name": "Система управления базами данных PostgreSQL 15+", "type": "СУБД", "author": "PostgreSQL Global Development Group", "year": "2024", "license": "Свободное ПО (PostgreSQL License)"}
        ],
        "teacher_guidelines": "Преподавателю рекомендуется использовать проблемно-деятельностный подход, сочетая обзорные лекции с интерактивным разбором производственных кейсов. На практических занятиях следует организовывать работу в малых группах с применением специализированного ПО и последующей публичной защитой результатов.",
        "student_guidelines": "Обучающимся необходимо систематически готовиться к аудиторным занятиям, изучая конспекты лекций и источники из ЭБС «Лань» и «Юрайт». При выполнении расчетно-практических кейсов важно обращать внимание на обоснование допущений модели и физическую интерпретацию полученных числовых значений.",
        "missed_classes_text": "Пропущенные занятия отрабатываются обучающимися в часы еженедельных индивидуальных консультаций преподавателя. Отработка включает теоретическое собеседование по пропущенной теме и выполнение практического расчетного задания."
    }


def _build_full_template_context(
    meta: dict,
    disc: dict,
    comps: list,
    coreqs: list,
    ai_data: dict,
    hours_total: float,
    hours_lec: float,
    hours_prac: float,
    hours_lab: float,
    hours_srs: float,
    hours_control: float,
    control_form: str,
    control_gen: str,
    sem: int,
    course_year: str,
    zet: str
) -> dict:
    """Собирает финальный словарь со всеми 121 переменными для rpd_template_parametrized.docx."""
    contact_aud = int(hours_lec + hours_prac)
    contact_total = round(contact_aud + hours_control, 2)

    # Нормализуем распределение часов по разделам
    sections = ai_data.get("sections", [])
    sections = _normalize_hours_distribution(
        sections=sections,
        total_hours=hours_total,
        lec_total=hours_lec,
        prac_total=hours_prac,
        srs_total=hours_srs
    )

    main_lit = ai_data.get("main_literature_list", [])
    add_lit = ai_data.get("additional_literature_list", [])
    net_lit = [
        "Электронная библиотечная система «Лань»: https://e.lanbook.com",
        "Электронная библиотечная система «Юрайт»: https://urait.ru",
        "Официальный сайт РГАУ-МСХА имени К.А. Тимирязева: https://www.timacad.ru"
    ]

    criteria = [
        {
            "level": "«Отлично» (высокий уровень) / «Зачтено»",
            "desc": "Оценку «отлично» (высокий уровень) заслуживает студент, освоивший знания, умения, компетенции и теоретический материал без пробелов; выполнивший все задания, предусмотренные учебным планом на высоком качественном уровне; практические навыки профессионального применения освоенных знаний сформированы.",
            "grade": "Отлично",
            "points": "85–100",
            "description": "Глубокое и системное знание предмета, безупречное выполнение всех практических кейсов и заданий.",
            "competency_level": "Высокий"
        },
        {
            "level": "«Хорошо» (средний уровень) / «Зачтено»",
            "desc": "Оценку «хорошо» (средний уровень) заслуживает студент, практически полностью освоивший знания, умения, компетенции и теоретический материал; учебные задания выполнены грамотно, практические навыки в основном сформированы, допущены непринципиальные неточности.",
            "grade": "Хорошо",
            "points": "70–84",
            "description": "Твердое знание материала, грамотное решение расчетных задач с несущественными неточностями.",
            "competency_level": "Базовый"
        },
        {
            "level": "«Удовлетворительно» (пороговый уровень) / «Зачтено»",
            "desc": "Оценку «удовлетворительно» (пороговый уровень) заслуживает студент, частично с пробелами освоивший знания, умения, компетенции и теоретический материал; многие учебные задания выполнены с ошибками или оценены минимальным числом баллов, базовые практические навыки сформированы.",
            "grade": "Удовлетворительно",
            "points": "50–69",
            "description": "Пороговое освоение материала, затруднения при самостоятельном решении задач.",
            "competency_level": "Пороговый"
        },
        {
            "level": "«Неудовлетворительно» / «Не зачтено»",
            "desc": "Оценку «неудовлетворительно» (компетенции не сформированы) заслуживает студент, не освоивший базовые знания, умения и теоретический материал курса; обязательные задания учебного плана не выполнены, практические навыки не сформированы.",
            "grade": "Не зачтено",
            "points": "0–49",
            "description": "Материал не освоен, компетенции не сформированы.",
            "competency_level": "Не сформированы"
        }
    ]

    dept_title = disc.get("department") or meta.get("department") or "Кафедра экологии"
    dept_short = dept_title.replace("Кафедра ", "").strip()

    # Компетенции: гарантируем соответствие структуры ai_data и утвержденного набора comps
    expected_codes = [c["code"] for c in comps]
    nested = ai_data.get("competencies_nested", [])
    actual_codes = [c.get("code") for c in nested]
    if not nested or set(expected_codes) != set(actual_codes):
        rebuilt_nested = []
        for idx, c in enumerate(comps):
            c_code_item = c.get("code", f"ПК-{idx+1}")
            inds = c.get("indicators", [])
            if inds:
                ind_first = {
                    "code": inds[0]["code"],
                    "title": inds[0].get("title", f"Индикатор {inds[0]['code']}"),
                    "know": inds[0].get("know", ""),
                    "able": inds[0].get("can", inds[0].get("able", "")),
                    "master": inds[0].get("master", "")
                }
                other_inds = []
                for oi in inds[1:]:
                    other_inds.append({
                        "code": oi["code"],
                        "title": oi.get("title", f"Индикатор {oi['code']}"),
                        "know": oi.get("know", ""),
                        "able": oi.get("can", oi.get("able", "")),
                        "master": oi.get("master", "")
                    })
            else:
                ind_first = {
                    "code": f"{c_code_item}.1",
                    "title": f"Индикатор {c_code_item}.1",
                    "know": f"Теоретические основы в рамках {c_code_item}.",
                    "able": f"Применять методы {c_code_item}.",
                    "master": f"Владеть технологиями {c_code_item}."
                }
                other_inds = []
            rebuilt_nested.append({
                "num": str(idx + 1),
                "code": c_code_item,
                "title": c.get("title", f"Компетенция {c_code_item}"),
                "ind_first": ind_first,
                "other_indicators": other_inds
            })
        nested = rebuilt_nested

    context = {
        "institute": meta.get("institute", "Институт мелиорации, водного хозяйства и строительства имени А.Н. Костякова"),
        "institute_short": "мелиорации, водного хозяйства и строительства имени А.Н. Костякова",
        "department": dept_title,
        "department_name": dept_short,
        "department_head_status": "И.о. зав. кафедрой",
        "department_head_degree": "к.б.н., доцент",
        "department_head_fio": "М.В. Тихонова",
        "graduating_department_head_status": "И.о. зав.",
        "graduating_department_head_degree": "к.б.н., доцент",
        "graduating_department_head_fio": "М.В. Тихонова",
        "graduating_department_name_short": dept_short,
        "director_fio": "Д.М. Бенин",
        "course_code": disc.get("code", "Б1.О.31.01"),
        "course_name": disc.get("name", ""),
        "direction_code": meta.get("direction_code", "05.03.06"),
        "direction_name": meta.get("direction_name", "Экология и природопользование"),
        "profile": meta.get("profile", "Экологический мониторинг и агроэкология"),
        "qualification": meta.get("qualification", "бакалавр"),
        "qualification_plural": "магистров" if "магистр" in meta.get("qualification", "").lower() else "бакалавров",
        "course_year": course_year,
        "semester": str(sem),
        "semester_phrase": f"{sem} семестре",
        "semester_distribution_phrase": f"в {sem} семестре",
        "study_form": meta.get("study_form", "очная"),
        "start_year": str(meta.get("start_year", "2026")),
        "current_year": "2026",
        "developers_list": [
            {"label": "Разработчик", "position": "доцент кафедры", "fio_rank": "Тихонова М.В., к.б.н., доцент"}
        ],
        "developer_fio_rank": "Тихонова М.В., к.б.н., доцент",
        "reviewer_fio_rank": "Борисов Б.А., д.б.н., профессор кафедры почвоведения, геологии и ландшафтоведения",
        "reviewer_fio_rank_full": "Борисовым Борисом Анорьевичем, доктором биологических наук, профессором",
        "department_chair": "М.В. Тихонова, к.б.н., доцент",
        "block_part": "части, формируемой участниками образовательных отношений, Блока 1 «Дисциплины (модули)»" if "ДВ" in disc.get("code", "") else "обязательной части Блока 1 «Дисциплины (модули)»",
        "block_part_genitive": "части, формируемой участниками образовательных отношений" if "ДВ" in disc.get("code", "") else "обязательной",
        
        # Трудоемкость
        "total_zet": zet,
        "total_hours": str(int(hours_total)),
        "contact_hours": str(contact_total).replace(".", ","),
        "contact_auditory_hours": str(contact_aud),
        "lecture_hours": str(int(hours_lec)),
        "practical_hours": str(int(hours_prac)),
        "lab_hours": str(int(hours_lab)) if hours_lab else "",
        "course_project_hours": "",
        "exam_consultation_hours": "",
        "kra_hours": str(hours_control).replace(".", ","),
        "srs_hours": str(hours_srs).replace(".", ","),
        "srs_self_hours": str(hours_srs).replace(".", ","),
        "essay_hours": "",
        "course_project_prep_hours": "",
        "rgr_hours": "",
        "test_work_hours": "",
        "exam_control_hours": "",
        "credit_control_hours": "",
        "control_form": control_form,
        "control_form_genitive": control_gen,
        "control_phrase": f"{control_form} в {sem} семестре",

        # Таблица 2: Столбцы семестров
        "sem_1_hdr": f"№{sem}",
        "sem_1_name": f"{sem} семестр",
        "sem_1_total_hours": str(int(hours_total)),
        "sem_1_contact_hours": str(contact_total).replace(".", ","),
        "sem_1_contact_auditory_hours": str(contact_aud),
        "sem_1_lecture_hours": str(int(hours_lec)),
        "sem_1_practical_hours": str(int(hours_prac)),
        "sem_1_lab_hours": str(int(hours_lab)) if hours_lab else "",
        "sem_1_course_project_hours": "",
        "sem_1_exam_consultation_hours": "",
        "sem_1_kra_hours": str(hours_control).replace(".", ","),
        "sem_1_srs_hours": str(hours_srs).replace(".", ","),
        "sem_1_essay_hours": "",
        "sem_1_course_project_prep_hours": "",
        "sem_1_rgr_hours": "",
        "sem_1_test_work_hours": "",
        "sem_1_srs_self_hours": str(hours_srs).replace(".", ","),
        "sem_1_exam_control_hours": "",
        "sem_1_credit_control_hours": "",
        "sem_1_control_form": control_form,
        "sem_2_hdr": "",
        "sem_2_total_hours": "",
        "sem_2_contact_hours": "",
        "sem_2_contact_auditory_hours": "",
        "sem_2_lecture_hours": "",
        "sem_2_practical_hours": "",
        "sem_2_lab_hours": "",
        "sem_2_course_project_hours": "",
        "sem_2_exam_consultation_hours": "",
        "sem_2_kra_hours": "",
        "sem_2_srs_hours": "",
        "sem_2_essay_hours": "",
        "sem_2_course_project_prep_hours": "",
        "sem_2_rgr_hours": "",
        "sem_2_test_work_hours": "",
        "sem_2_srs_self_hours": "",
        "sem_2_exam_control_hours": "",
        "sem_2_credit_control_hours": "",
        "sem_2_control_form": "",

        # Компетенции
        "competencies_count": str(len(comps)),
        "competencies_short_list": ", ".join(c["code"] for c in comps),
        "competencies_list": ", ".join(c["code"] for c in comps),
        "competencies_nested": nested,

        # Содержание
        "course_purpose": ai_data.get("course_purpose", ""),
        "course_tasks": ai_data.get("course_tasks", ""),
        "prerequisites_text": ai_data.get("prerequisites_text", "Дисциплины базовой части"),
        "postrequisites_text": ai_data.get("postrequisites_text", "Последующие дисциплины и ГИА"),
        "corequisites_text": ai_data.get("corequisites_text", "Дисциплины текущего семестра"),
        "course_features_text": ai_data.get("course_features_text", "практико-ориентированный характер обучения"),
        "course_annotation_content": ai_data.get("course_annotation_content", ""),

        # Динамические разделы
        "sections": sections,
        "detailed_sections": ai_data.get("detailed_sections", []),
        "t4_sections": ai_data.get("t4_sections", []),
        "t5_sections": ai_data.get("t5_sections", []),

        # Интерактивные формы
        "interactive_items": [
            {
                "num": str(item.get("num", i)),
                "theme": item.get("theme", f"Раздел {i}"),
                "form": item.get("form", "Практическое занятие"),
                "tech": item.get("tech", "Кейс-метод и разбор ситуационных задач")
            } for i, item in enumerate(ai_data.get("interactive_items", []), 1)
        ] if ai_data.get("interactive_items") else [
            {"num": "1", "theme": sections[0]["name"] if sections else "Раздел 1", "form": "Лекция", "tech": "Проблемная лекция с элементами дискуссии"},
            {"num": "2", "theme": sections[1]["name"] if len(sections) > 1 else "Раздел 2", "form": "Практическое занятие", "tech": "Кейс-метод и разбор прикладных расчетных ситуаций"},
            {"num": "3", "theme": sections[2]["name"] if len(sections) > 2 else "Раздел 3", "form": "Практическое занятие", "tech": "Командная работа над проектным кейсом"},
            {"num": "4", "theme": sections[3]["name"] if len(sections) > 3 else "Раздел 4", "form": "Практическое занятие", "tech": "Публичная защита проекта с рецензированием"}
        ],

        # ФОС
        "assessment_materials_intro": f"Фонд оценочных средств дисциплины предназначен для оценки уровня сформированности компетенций {', '.join(c['code'] for c in comps)}.",
        "individual_tasks_intro": "Индивидуальные задания нацелены на закрепление практических навыков разработки технологических решений.",
        "individual_tasks_list": ai_data.get("individual_tasks_list", []),
        "practical_works_list": ai_data.get("practical_works_list", []),
        "test_questions_list": ai_data.get("test_questions_list", []),
        "oral_questions_list": ai_data.get("oral_questions_list", []),
        "colloquium_questions_list": ai_data.get("colloquium_questions_list", []),
        "exam_credit_questions_list": ai_data.get("exam_credit_questions_list", []),
        "criteria": criteria,
        "current_assessment_forms": "устный опрос, тестирование, коллоквиум, решение расчетных кейсов, защита практических работ",

        # Литература
        "main_lit_count": str(len(main_lit)),
        "add_lit_count": str(len(add_lit)),
        "internet_lit_count": str(len(net_lit)),
        "main_literature_list": main_lit,
        "additional_literature_list": add_lit,
        "regulatory_acts_list": ai_data.get("regulatory_acts_list", []),
        "methodological_guidelines_list": [
            "Методические указания к выполнению практических заданий и организации самостоятельной работы студентов. — М.: Изд-во РГАУ-МСХА, 2025. — 48 с."
        ],
        "internet_resources_list": net_lit,
        "software_items": [
            {
                "num": str(sw.get("num", i)),
                "section": sw.get("section") or "Все разделы",
                "name": sw.get("name", ""),
                "type": sw.get("type") or "Специализированное ПО",
                "author": sw.get("author") or "Разработчик ПО",
                "year": str(sw.get("year") or "2024"),
                "license": sw.get("license") or "Свободное ПО / Академическая лицензия"
            } if isinstance(sw, dict) else {
                "num": str(i),
                "section": "Все разделы",
                "name": str(sw),
                "type": "Специализированное ПО",
                "author": "Разработчик ПО",
                "year": "2024",
                "license": "Свободное ПО / Академическая лицензия"
            } for i, sw in enumerate(ai_data.get("software_items", []), 1)
        ],
        "facilities": [
            {
                "num": "1",
                "room": "Учебная аудитория для проведения занятий лекционного типа (корпус 17, ауд. 312)",
                "name": "Аудитория для проведения лекционных занятий",
                "equipment": "Мультимедийный проектор, настенный экран, персональный компьютер преподавателя с выходом в «Интернет» и доступом в электронную информационно-образовательную среду (ЭИОС) университета, специализированная мебель, учебная доска."
            },
            {
                "num": "2",
                "room": "Компьютерный класс для проведения практических занятий и геомоделирования (корпус 17, ауд. 405)",
                "name": "Компьютерный класс для проведения практических занятий",
                "equipment": "Рабочие станции обучающихся, объединенные в локальную сеть с выходом в Интернет, с предустановленным специализированным программным обеспечением (QGIS, МойОфис/LibreOffice, Python) и доступом к электронным библиотечным системам."
            },
            {
                "num": "3",
                "room": "Помещение для самостоятельной работы обучающихся (корпус 17, ауд. 201)",
                "name": "Помещение для самостоятельной работы обучающихся",
                "equipment": "Компьютерная техника с возможностью подключения к сети «Интернет» и обеспечением доступа в электронную информационно-образовательную среду университета, ЭБС «Лань» и ЭБС «Юрайт»."
            }
        ],
        "teacher_guidelines": ai_data.get("teacher_guidelines", "Рекомендуется сочетать проблемные лекции с активным обсуждением практических ситуаций."),
        "student_guidelines": ai_data.get("student_guidelines", "Рекомендуется регулярно работать с рекомендованной литературой из ЭБС и выполнять практические задания."),
        "missed_classes_text": ai_data.get("missed_classes_text", "Пропущенные занятия отрабатываются в установленном порядке в часы консультаций преподавателя."),
        "token_usage": ai_data.get("token_usage")
    }

    try:
        from rpd_app.core.docx_generator import sanitize_section2_text
        context = sanitize_section2_text(context)
    except ImportError:
        pass

    return context
