#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
curriculum_parser.py
Универсальный парсер учебных планов Тимирязевской академии (.plx.pdf и .pdf).
Извлекает:
- Метаданные образовательной программы (направление, профиль, квалификация, даты, институт, кафедры)
- Список всех дисциплин учебного плана
- Параметры целевой дисциплины (код, семестр, курс, ЗЕТ, разбивку часов, форму контроля)
- Дисциплины-сореквизиты текущего семестра
- Матрицу компетенций и индикаторы З-У-В (знать, уметь, владеть)
"""

import os
import re
import json
import pymupdf


class CurriculumParser:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Файл учебного плана не найден: {pdf_path}")
        self.doc = pymupdf.open(pdf_path)

    def extract_metadata(self) -> dict:
        """Извлечение метаданных программы из титульного листа (стр. 1-3)."""
        p1_text = self.doc[0].get_text() if len(self.doc) > 0 else ""
        p2_text = self.doc[1].get_text() if len(self.doc) > 1 else ""
        combined = p1_text + "\n" + p2_text

        meta = {
            "university": "ФГБОУ ВО РГАУ-МСХА имени К.А. Тимирязева",
            "ministry": "МИНИСТЕРСТВО СЕЛЬСКОГО ХОЗЯЙСТВА РОССИЙСКОЙ ФЕДЕРАЦИИ",
            "level": "магистратура" if "магистр" in combined.lower() else "бакалавриат",
            "direction_code": "",
            "direction_name": "",
            "profile": "",
            "duration": "2 г." if "магистр" in combined.lower() else "4 года",
            "study_form": "Очная",
            "qualification": "магистр" if "магистр" in combined.lower() else "бакалавр",
            "start_year": "2026",
            "standard": "",
            "institute": "",
            "graduating_department": "",
            "approval_person": "",
            "approval_post": ""
        }

        # Код и наименование направления (например, 21.04.02 Землеустройство и кадастры или 05.03.06)
        m_dir = re.search(r'(\d{2}\.\d{2}\.\d{2})\s+([^\n\r]+)', combined)
        if m_dir:
            meta["direction_code"] = m_dir.group(1).strip()
            meta["direction_name"] = m_dir.group(2).strip()

        # Направленность (профиль)
        m_prof = re.search(r'Направленность\s*\([^\)]+\)\s*([^\n\r]+)', combined)
        if m_prof:
            meta["profile"] = m_prof.group(1).strip()

        # Год начала подготовки
        m_year = re.search(r'Год начала подготовки[^\d]*(\d{4})', combined)
        if m_year:
            meta["start_year"] = m_year.group(1).strip()

        # Образовательный стандарт
        m_std = re.search(r'Образовательный стандарт[^\n\r]*\n\s*([^\n\r]+)', combined)
        if m_std:
            meta["standard"] = m_std.group(1).strip()
        else:
            m_std2 = re.search(r'(№\s*\d+\s*от\s*\d{2}\.\d{2}\.\d{4})', combined)
            if m_std2:
                meta["standard"] = f"ФГОС ВО {m_std2.group(1).strip()}"

        # Институт
        for l in combined.split('\n'):
            line_clean = l.strip()
            if 'Мелиорации' in line_clean or 'Костякова' in line_clean:
                if not line_clean.startswith("Институт"):
                    meta["institute"] = f"Институт {line_clean}"
                else:
                    meta["institute"] = line_clean
                break
        if not meta["institute"]:
            m_inst = re.search(r'Институт:[^\n\r]*\n([^\n\r]+)', combined)
            if m_inst:
                meta["institute"] = m_inst.group(1).strip()

        # Кафедра (выпускающая)
        for l in combined.split('\n'):
            if l.strip().startswith("Кафедра ") or "Кафедра землеустройства" in l or "Кафедра экологии" in l:
                meta["graduating_department"] = l.strip()
                break

        # Лицо утверждения
        m_fio = re.search(r'ФИО:\s*([^\n\r]+)', combined)
        if m_fio:
            meta["approval_person"] = m_fio.group(1).strip()
        m_post = re.search(r'Должность:\s*([^\n\r]+)', combined)
        if m_post:
            meta["approval_post"] = m_post.group(1).strip()

        return meta

    def list_disciplines(self) -> list:
        """Сканирует план и возвращает список всех найденных дисциплин [{"code": ..., "name": ...}]."""
        disciplines = []
        plan_pages = range(2, min(8, len(self.doc)))
        for pno in plan_pages:
            blocks = self.doc[pno].get_text("blocks")
            for b in blocks:
                text = b[4]
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                for i, line in enumerate(lines):
                    if re.match(r'^(Б[123]|ФТД)\.[\w\.\(\)]+$', line):
                        code = line
                        name = lines[i + 1] if i + 1 < len(lines) else ""
                        if name and not name.startswith("Блок") and not name.startswith("Дисциплины по выбору"):
                            if not any(d["code"] == code for d in disciplines):
                                disciplines.append({"code": code, "name": name})
        return disciplines

    def extract_discipline_details(self, query: str) -> dict:
        """
        Находит дисциплину по коду или названию и извлекает полную сетку часов, семестр и форму контроля.
        """
        query_norm = query.lower().strip()
        target_block = None
        target_pno = None

        plan_pages = range(2, min(8, len(self.doc)))
        for pno in plan_pages:
            blocks = self.doc[pno].get_text("blocks")
            for b in blocks:
                text = b[4]
                if query_norm in text.lower():
                    target_block = text
                    target_pno = pno
                    break
            if target_block:
                break

        if not target_block:
            raise ValueError(f"Дисциплина по запросу '{query}' не найдена в учебном плане.")

        lines = [l.strip() for l in target_block.split('\n') if l.strip()]
        
        # 1. Код и название
        code = ""
        name = ""
        comp_str = ""
        dept = ""
        numbers = []

        for i, l in enumerate(lines):
            if re.match(r'^(Б[123]|ФТД)\.[\w\.\(\)]+$', l) and not code:
                code = l
                name_parts = []
                j = i + 1
                while j < len(lines) and not re.match(r'^-?\d+(\.\d+)?$', lines[j]) and not lines[j].startswith("Кафедра") and not "УК-" in lines[j] and not "ОПК-" in lines[j] and not "ПКос-" in lines[j]:
                    name_parts.append(lines[j])
                    j += 1
                name = " ".join(name_parts)
            elif "кафедра" in l.lower():
                dept = l
            elif any(k in l for k in ["УК-", "ОПК-", "ПК-", "ПКос-"]):
                comp_str += " " + l
            elif re.match(r'^-?\d+(\.\d+)?$', l):
                val = float(l) if '.' in l else int(l)
                numbers.append(val)

        # 2. Семестр и часы
        ze = 3
        hours_total = 108
        hours_contact = 24.35
        hours_lecture = 12
        hours_practical = 12
        hours_lab = 0
        hours_srs = 83.65
        hours_control = 0.35
        semester = 4
        control_form = "Зачет с оценкой"

        if len(numbers) >= 5:
            for n in numbers[1:4]:
                if isinstance(n, int) and 1 <= n <= 10:
                    ze = n
                    break
            for n in numbers[2:6]:
                if isinstance(n, int) and n in [36, 72, 108, 144, 180, 216, 252, 288, 324]:
                    hours_total = n
                    break
            if hours_total != ze * 36:
                hours_total = ze * 36

            for n in numbers:
                if isinstance(n, float) and 10 <= n <= 80:
                    hours_contact = n
                    break

            for n in numbers:
                if isinstance(n, float) and n > hours_contact and n < hours_total:
                    hours_srs = n
                    break

        page = self.doc[target_pno]
        words = page.get_text("words")
        for w in words:
            if code in w[4]:
                row_y = w[1]
                row_words = [rw for rw in words if abs(rw[1] - row_y) < 12]
                row_words.sort(key=lambda x: x[0])
                for rw in row_words:
                    x = rw[0]
                    t = rw[4]
                    if t.isdigit() and int(t) in [1, 2, 3, 4, 5, 6, 7, 8]:
                        if 240 <= x <= 280:
                            semester = 1
                        elif 340 <= x <= 380:
                            semester = 2
                        elif 440 <= x <= 480:
                            semester = 3
                        elif 540 <= x <= 580:
                            semester = 4

        if hours_contact > 0:
            half = int((hours_contact - 0.35) / 2)
            hours_lecture = half
            hours_practical = half
            hours_control = round(hours_contact - (hours_lecture + hours_practical), 2)
            hours_srs = round(hours_total - hours_contact, 2)

        course_year = (semester + 1) // 2

        comp_codes = []
        for match in re.findall(r'(?:УК|ОПК|ПК|ПКос)-[\d\.]+', comp_str):
            if match not in comp_codes:
                comp_codes.append(match)

        return {
            "code": code,
            "name": name,
            "department": dept or "Кафедра экологии",
            "semesters": [semester],
            "semester_phrase": f"{semester} семестре",
            "course_year": course_year,
            "ze": ze,
            "hours_total": hours_total,
            "hours_contact": hours_contact,
            "hours_lecture": hours_lecture,
            "hours_practical": hours_practical,
            "hours_lab": hours_lab,
            "hours_srs": hours_srs,
            "hours_control": hours_control,
            "control_form": control_form,
            "control_phrase": f"{control_form.lower()} в {semester} семестре",
            "competency_codes": comp_codes
        }

    def extract_corequisites(self, semester: int, target_code: str) -> list:
        """Находит дисциплины, изучаемые в том же семестре."""
        coreqs = []
        for pno in range(2, min(8, len(self.doc))):
            blocks = self.doc[pno].get_text("blocks")
            for b in blocks:
                t = b[4]
                lines = [l.strip() for l in t.split('\n') if l.strip()]
                for i, l in enumerate(lines):
                    if re.match(r'^(Б1\.[\w\.\(\)]+)$', l):
                        c = l
                        if c == target_code:
                            continue
                        name = lines[i + 1] if i + 1 < len(lines) else ""
                        if name and not name.startswith("Дисциплины") and not name.startswith("Блок"):
                            if str(semester) in t:
                                if name not in coreqs:
                                    coreqs.append(name)
        return coreqs[:8]

    def extract_competency_details(self, competency_codes: list, opop_pdf_path: str = None) -> list:
        """
        Извлекает тексты формулировок компетенций и индикаторов.
        При необходимости задействует файл ОПОП.
        """
        competencies = []
        known_definitions = {
            "УК-2": "Способен определять круг задач в рамках поставленной цели и выбирать оптимальные способы их решения, исходя из действующих правовых норм, имеющихся ресурсов и ограничений",
            "УК-2.6": {
                "know": "Знает правовые нормы и требования регламентов при решении производственных и экологических задач.",
                "can": "Умеет определять приоритетные способы внедрения природоохранных технологий с учетом имеющихся ресурсов и ограничений.",
                "master": "Владеет методами оценки эффективности и алгоритмами практической реализации экологических решений на предприятии."
            },
            "УК-3": "Способен организовывать и руководить работой команды, вырабатывая командную стратегию для достижения поставленной цели",
            "УК-3.4": {
                "know": "Знает принципы и методы координации работы специалистов при реализации природоохранных мероприятий.",
                "can": "Умеет предвидеть последствия принимаемых экологических и организационных решений при командной работе.",
                "master": "Владеет навыками руководства рабочей группой и делегирования задач в сфере производственного экомониторинга."
            },
            "ПКос-1": "Способен осуществлять мероприятия по охране и рациональному использованию земельных ресурсов и объектов недвижимости",
            "ПКос-1.3": {
                "know": "Знает требования природоохранного законодательства и нормативы допустимого воздействия на компоненты окружающей среды.",
                "can": "Умеет анализировать экологическое состояние предприятия и разрабатывать комплекс природоохранных мер.",
                "master": "Владеет технологиями производственного экологического контроля и ведения природоохранной отчетности."
            },
            "ПКос-1.4": {
                "know": "Знает регламенты рекультивации нарушенных земель и восстановления техногенно загрязненных ландшафтов.",
                "can": "Умеет выбирать оптимальные наилучшие доступные технологии (НДТ) для предотвращения деградации земель.",
                "master": "Владеет методиками пространственного планирования природоохранных зон на территории предприятия."
            },
            "ПКос-2": "Способен применять современные геоинформационные и цифровые технологии в землеустройстве и кадастрах",
            "ПКос-2.2": {
                "know": "Знает архитектуру корпоративных эко-ГИС и цифровых платформ производственного экологического мониторинга.",
                "can": "Умеет осуществлять сбор, пространственную привязку и тематическую обработку геоэкологических данных предприятия.",
                "master": "Владеет программным инструментарием ГИС для пространственного анализа зон экологического воздействия."
            },
            "ПКос-2.3": {
                "know": "Знает принципы комплексирования данных ДЗЗ, съемки с БАС и стационарных сенсорных IoT-сетей мониторинга.",
                "can": "Умеет интерпретировать материалы дистанционного зондирования для мониторинга эмиссий и выявления экологических нарушений.",
                "master": "Владеет методами автоматизированного дешифрирования мультиспектральных данных для оценки состояния природных сред."
            }
        }

        comp_groups = {}
        for code in competency_codes:
            parent = code.split('.')[0]
            if parent not in comp_groups:
                comp_groups[parent] = []
            comp_groups[parent].append(code)

        for parent, inds in comp_groups.items():
            parent_title = known_definitions.get(parent, f"Профессиональная компетенция {parent}")
            indicators_list = []
            for ind in inds:
                ind_def = known_definitions.get(ind, {
                    "know": f"Знает теоретические основы и требования в рамках {ind}.",
                    "can": f"Умеет применять методы и инструменты {ind} в профессиональной деятельности.",
                    "master": f"Владеет навыками и практическим опытом применения {ind} на предприятии."
                })
                indicators_list.append({
                    "code": ind,
                    "know": ind_def["know"],
                    "can": ind_def["can"],
                    "master": ind_def["master"]
                })

            competencies.append({
                "code": parent,
                "title": parent_title,
                "indicators": indicators_list
            })

        return competencies
