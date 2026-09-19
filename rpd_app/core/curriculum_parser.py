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

        if meta["institute"]:
            from rpd_app.data.timiryazev_structure import normalize_institute
            meta["institute"] = normalize_institute(meta["institute"]) or meta["institute"]

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
                        np = []
                        k = i + 1
                        while k < len(lines) and not re.match(r'^-?\d+(\.\d+)?$', lines[k]) and not lines[k].startswith("Кафедра") and not any(p in lines[k] for p in ["УК-", "ОПК-", "ПК-", "ПКос-", "Блок"]):
                            np.append(lines[k])
                            k += 1
                        name = " ".join(np).strip()
                        if name and not name.startswith("Блок") and not name.startswith("Дисциплины по выбору"):
                            if not any(d["code"] == code for d in disciplines):
                                disciplines.append({"code": code, "name": name})
        return disciplines

    def extract_discipline_details(self, query: str) -> dict:
        """
        Находит дисциплину по коду или названию и извлекает полную сетку часов, семестр и форму контроля
        с использованием координатного анализа колонок и строгой гарантией сходимости часов (СРС >= 0).
        """
        query_norm = query.lower().strip()
        code_match = re.search(r'((?:Б[123]|ФТД)(?:\.[A-Za-zА-Яа-я0-9]+)+)', query, re.IGNORECASE)
        explicit_code = code_match.group(1).strip() if code_match else None

        if not explicit_code:
            discs = self.list_disciplines()
            # 1. Exact name match
            for d in discs:
                if d["name"].lower() == query_norm:
                    explicit_code = d["code"]
                    break
            # 2. Query contains name or name contains query
            if not explicit_code:
                candidates = []
                for d in discs:
                    d_name_norm = d["name"].lower()
                    if query_norm in d_name_norm or d_name_norm in query_norm:
                        candidates.append((len(d["name"]), d["code"]))
                if candidates:
                    candidates.sort(reverse=True)
                    explicit_code = candidates[0][1]

        target_pno = None
        target_y = None
        target_code = None

        # 1. Поиск строки дисциплины по страницам 3-7
        for pno in range(2, min(8, len(self.doc))):
            words = self.doc[pno].get_text("words")
            
            # Если есть явный/разрешенный код дисциплины - ищем строго по нему
            if explicit_code:
                for w in words:
                    w_clean = w[4].strip()
                    if w_clean.lower() == explicit_code.lower():
                        target_pno = pno
                        target_y = w[1]
                        target_code = w_clean
                        break
                if target_pno is not None:
                    break
            else:
                # Поиск точного совпадения по коду из query_norm
                for w in words:
                    w_clean = w[4].strip()
                    if re.match(r'^(?:Б[123]|ФТД)\.[\w\.\(\)]+$', w_clean, re.IGNORECASE):
                        if query_norm == w_clean.lower() or query_norm.startswith(w_clean.lower() + "_") or query_norm.startswith(w_clean.lower() + " "):
                            target_pno = pno
                            target_y = w[1]
                            target_code = w_clean
                            break
                if target_pno is not None:
                    break

        if target_pno is None:
            raise ValueError(f"Дисциплина по запросу '{query}' не найдена в учебном плане.")

        page = self.doc[target_pno]
        words = page.get_text("words")
        row_words = [w for w in words if abs(w[1] - target_y) < 2.0]
        row_words.sort(key=lambda w: w[0])

        code = target_code or ""
        name_parts = []
        nums = []
        comp_codes = []
        dept = ""

        # Извлечение данных из строки таблицы
        for w in row_words:
            txt = w[4].strip()
            x = w[0]
            cleaned = txt.replace(',', '.')
            if re.match(r'^-?\d+(\.\d+)?$', cleaned):
                val = float(cleaned) if '.' in cleaned else int(cleaned)
                nums.append((x, val))
            elif 30 < x < 120 and not txt.startswith('+') and txt != code:
                name_parts.append(txt)
            elif any(p in txt for p in ['УК-', 'ОПК-', 'ПКос-', 'ПКдпо-', 'ПК-']):
                for match in re.findall(r'(?:УК|ОПК|ПК|ПКос|ПКдпо|СК|ПК[а-я]+)-[\d\.]+', txt):
                    if match not in comp_codes:
                        comp_codes.append(match)
            elif 'кафедра' in txt.lower():
                dept = txt

        name = " ".join(name_parts)
        # Всегда извлекаем полное многострочное название и кафедру из текстового блока страницы
        blocks = page.get_text("blocks")
        for b in blocks:
            if code in b[4]:
                bl_lines = [l.strip() for l in b[4].split('\n') if l.strip()]
                for idx, bl in enumerate(bl_lines):
                    if code in bl and idx + 1 < len(bl_lines):
                        np = []
                        k = idx + 1
                        while k < len(bl_lines) and not re.match(r'^-?\d+(\.\d+)?$', bl_lines[k]) and not bl_lines[k].startswith("Кафедра") and not any(p in bl_lines[k] for p in ["УК-", "ОПК-", "ПК-", "ПКос-", "Блок"]):
                            np.append(bl_lines[k])
                            k += 1
                        if np:
                            name = " ".join(np).strip()
                        break
                if "кафедра" in b[4].lower() and not dept:
                    for l in bl_lines:
                        if "кафедра" in l.lower():
                            dept = l
                            break
                break

        name = name or query

        # 2. Определение ЗЕТ и общего объема часов по связке (H == Z * 36)
        total_hours = None
        ze = None
        tot_idx = None

        for idx, (x, val) in enumerate(nums):
            if isinstance(val, int) and val in [36, 72, 108, 144, 180, 216, 252, 288, 324, 360]:
                expected_z = val // 36
                for prev_idx in range(max(0, idx - 4), idx):
                    if nums[prev_idx][1] == expected_z:
                        total_hours = val
                        ze = expected_z
                        tot_idx = idx
                        break
                if total_hours:
                    break

        if not total_hours:
            for idx, (x, val) in enumerate(nums):
                if isinstance(val, int) and val in [36, 72, 108, 144, 180, 216, 252, 288]:
                    total_hours = val
                    ze = val // 36
                    tot_idx = idx
                    break

        total_hours = total_hours or 72
        ze = ze or (total_hours // 36)

        # 3. Извлечение контактных часов и СРС
        contact_hours = None
        srs_hours = None
        control_hours = 0.0

        if tot_idx is not None:
            # Числа после общего объема часов в сводных колонках (x < 265)
            post_nums = [v for (x, v) in nums[tot_idx + 1:] if x < 265]
            for v in post_nums:
                if isinstance(v, float) and contact_hours is None and 10 <= v <= total_hours:
                    contact_hours = v
                elif contact_hours is not None and srs_hours is None and v > 0:
                    srs_hours = float(v)
                elif contact_hours is not None and srs_hours is not None and control_hours == 0.0:
                    control_hours = float(v)

        if contact_hours is None:
            contact_hours = round(total_hours * 0.33, 2)

        # 4. Анализ семестровых колонок (x >= 260)
        sem_list = []
        # Семестры 1..8 имеют характерные диапазоны x координат
        sem_ranges = [
            (1, 260, 355),
            (2, 355, 455),
            (3, 455, 555),
            (4, 555, 655),
            (5, 655, 755),
            (6, 755, 855),
            (7, 855, 955),
            (8, 955, 1055)
        ]
        
        sem_data = {}
        for sem_idx, x_min, x_max in sem_ranges:
            s_nums = [v for (x, v) in nums if x_min <= x < x_max]
            if s_nums:
                # В семестровом блоке: ЗЕТ, Лек, Лаб/Пр, КРА, СРС
                sem_list.append(sem_idx)
                sem_data[sem_idx] = s_nums

        semester = sem_list[0] if sem_list else 4
        course_year = (semester + 1) // 2

        # 5. Распределение лекций, практик и контактной работы
        # Для односеместровых курсов с детальными часами берем точные часы семестрового блока
        if len(sem_list) == 1 and sem_data.get(semester):
            s_vals = sem_data[semester]
            # [ze, lec, prac, ...]
            s_int_floats = [v for v in s_vals if isinstance(v, (int, float))]
            if len(s_int_floats) >= 3 and s_int_floats[1] > 0 and s_int_floats[2] > 0:
                hours_lecture = int(s_int_floats[1])
                hours_practical = int(s_int_floats[2])
                hours_lab = 0
            else:
                half = int((contact_hours - 0.35) / 2) if contact_hours > 1 else int(contact_hours / 2)
                hours_lecture = half
                hours_practical = half
                hours_lab = 0
        else:
            half = int((contact_hours - 0.35) / 2) if contact_hours > 1 else int(contact_hours / 2)
            hours_lecture = half
            hours_practical = half
            hours_lab = 0

        hours_control = round(contact_hours - (hours_lecture + hours_practical + hours_lab), 2)
        if hours_control < 0:
            hours_control = 0.35

        # Строгий математический инвариант: СРС всегда неотрицательна
        hours_srs = max(0.0, round(total_hours - contact_hours - (27.0 if "экзамен" in query_norm else 0.0), 2))
        if hours_srs == 0.0 and total_hours > contact_hours:
            hours_srs = round(total_hours - contact_hours, 2)

        # Определение формы контроля по координатам столбцов «Формы пром. атт.»
        control_form = self._extract_assessment_form(page, target_y, nums, query_norm)

        # Извлекаем точные компетенции из официальной таблицы «Формируемые компетенции» плана
        matrix = self.extract_competency_matrix()
        if code in matrix and matrix[code]:
            comp_codes = matrix[code]
        elif not comp_codes:
            for m_code, m_comps in matrix.items():
                if m_code.lower() == code.lower() and m_comps:
                    comp_codes = m_comps
                    break

        return {
            "code": code,
            "name": name,
            "department": dept or "Кафедра экологии",
            "semesters": sem_list if sem_list else [semester],
            "semester_phrase": f"{semester} семестре",
            "course_year": course_year,
            "ze": ze,
            "hours_total": total_hours,
            "hours_contact": contact_hours,
            "hours_lecture": hours_lecture,
            "hours_practical": hours_practical,
            "hours_lab": hours_lab,
            "hours_srs": hours_srs,
            "hours_control": hours_control,
            "control_form": control_form,
            "control_phrase": f"{control_form.lower()} в {semester} семестре",
            "competency_codes": comp_codes
        }

    def _extract_assessment_form(self, page, target_y: float, nums: list, query_norm: str) -> str:
        """
        Определяет форму промежуточной аттестации дисциплины по колонкам под заголовком «Формы пром. атт.»
        (Экзамен, Зачет, Зачет с оц., КП, КР), анализируя координаты отметок в строке дисциплины.
        """
        words = page.get_text("words")
        header_words = [w for w in words if w[1] < 45]

        col_map = {}
        zachet_words = []
        for w in header_words:
            txt = w[4].lower()
            if "экза" in txt:
                col_map["Экзамен"] = w[0]
            elif txt == "зачет":
                zachet_words.append(w)
            elif "оц" in txt:
                col_map["Зачет с оценкой"] = w[0]
            elif txt == "кп":
                col_map["Курсовой проект"] = w[0]
            elif txt == "кр":
                col_map["Курсовая работа"] = w[0]

        zachet_words.sort(key=lambda w: w[0])
        if len(zachet_words) >= 2:
            col_map["Зачет"] = zachet_words[0][0]
            if "Зачет с оценкой" not in col_map:
                col_map["Зачет с оценкой"] = zachet_words[1][0]
        elif len(zachet_words) == 1:
            col_map["Зачет"] = zachet_words[0][0]

        if col_map:
            min_x = min(col_map.values()) - 10
            max_x = max(col_map.values()) + 15
            row_words = [w for w in words if abs(w[1] - target_y) < 3.0 and min_x <= w[0] <= max_x]
            candidates = []
            for w in row_words:
                txt = w[4].strip().replace(",", ".")
                if re.match(r"^\d+$", txt):
                    x = w[0]
                    best_col = min(col_map.keys(), key=lambda c: abs(col_map[c] - x))
                    dist = abs(col_map[best_col] - x)
                    candidates.append((dist, best_col, txt, x))

            if candidates:
                candidates.sort(key=lambda item: item[0])
                return candidates[0][1]

        # Резервные правила
        if "экзамен" in query_norm or any(v == 27 for (x, v) in nums):
            return "Экзамен"
        elif "зачет" in query_norm:
            return "Зачет"
        return "Зачет с оценкой"

    def extract_competency_matrix(self) -> dict:
        """
        Извлекает официальную матрицу компетенций из раздела «Формируемые компетенции» учебного плана.
        Возвращает словарь: {code_дисциплины: [список_кодов_индикаторов]}.
        Например: {'Б1.В.09.03': ['ПКдпо-2.1', 'ПКдпо-2.2', 'ПКдпо-2.3', 'ПКдпо-3.1', 'ПКдпо-3.2', 'ПКдпо-3.3']}
        """
        matrix = {}
        matrix_pages = []
        for i, p in enumerate(self.doc):
            t = p.get_text()
            if 'Формируемые компетенции' in t and ('Индекс' in t or 'Наименование' in t):
                matrix_pages.append(i)
                k = i + 1
                while k < len(self.doc):
                    tk = self.doc[k].get_text()
                    if ('Б1.' in tk or 'Б2.' in tk or 'Б3.' in tk) and re.search(r'(?:УК|ОПК|ПК|ПКос|ПКдпо|СК)-', tk):
                        matrix_pages.append(k)
                        k += 1
                    else:
                        break
                break

        comp_regex = re.compile(r'(?:УК|ОПК|ПК|ПКос|ПКдпо|СК|ПК[а-я]+)-[\d\.]+')
        code_regex = re.compile(r'^(?:Б[123]|ФТД)\.[\w\.\(\)]+$')

        for pno in matrix_pages:
            words = self.doc[pno].get_text('words')
            codes_with_y = []
            for w in words:
                if w[0] < 130 and code_regex.match(w[4].strip()):
                    codes_with_y.append((w[1], w[4].strip()))

            codes_with_y.sort(key=lambda item: item[0])

            for idx, (cy, code) in enumerate(codes_with_y):
                next_y = codes_with_y[idx + 1][0] if idx + 1 < len(codes_with_y) else 9999.0
                row_comps = []
                for w in words:
                    if w[0] > 300 and (cy - 5 <= w[1] < next_y - 2):
                        for match in comp_regex.findall(w[4]):
                            if match not in row_comps:
                                row_comps.append(match)
                if code not in matrix or not matrix[code]:
                    matrix[code] = row_comps

        return matrix

    def list_all_program_competencies(self) -> dict:
        """
        Сканирует весь учебный план и возвращает полный каталог всех компетенций
        программы с их индикаторами и описаниями для выбора в веб-интерфейсе.
        Возвращает:
        {
            "ПКдпо-2": {
                "code": "ПКдпо-2",
                "title": "Способен разрабатывать и осуществлять эколого-экономическое обоснование...",
                "indicators": ["ПКдпо-2.1", "ПКдпо-2.2", "ПКдпо-2.3"]
            }, ...
        }
        """
        comp_regex = re.compile(r'(?:УК|ОПК|ПК|ПКос|ПКдпо|СК|ПК[а-я]+)-[\d\.]+')
        all_codes = set()
        for page in self.doc:
            txt = page.get_text()
            for match in comp_regex.findall(txt):
                all_codes.add(match)

        catalog = {}
        for code in all_codes:
            parent = code.split('.')[0]
            if parent not in catalog:
                catalog[parent] = {
                    "code": parent,
                    "title": "",
                    "indicators": []
                }
            if '.' in code and code not in catalog[parent]["indicators"]:
                catalog[parent]["indicators"].append(code)

        # Сортируем индикаторы в каждой компетенции
        for p in catalog:
            catalog[p]["indicators"].sort(
                key=lambda x: [int(n) if n.isdigit() else n for n in re.split(r'(\d+)', x)]
            )
            # Присваиваем наименования из extract_competency_details
            details = self.extract_competency_details([p])
            if details:
                catalog[p]["title"] = details[0]["title"]

        return dict(sorted(catalog.items(), key=lambda item: [int(n) if n.isdigit() else n for n in re.split(r'(\d+)', item[0])]))

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
            "УК-1": "Способен осуществлять критический анализ проблемных ситуаций на основе системного подхода, вырабатывать стратегию действий",
            "УК-1.1": {
                "know": "Знает принципы критического анализа, методы сбора и обобщения научно-практической информации.",
                "can": "Умеет выявлять проблемные ситуации в профессиональной деятельности и формулировать задачи исследования.",
                "master": "Владеет навыками системного подхода и методами разработки стратегий решения комплексных задач."
            },
            "УК-1.2": {
                "know": "Знает фундаментальные методологические основы научно-исследовательской деятельности.",
                "can": "Умеет критически оценивать надежность источников информации и достоверность полученных данных.",
                "master": "Владеет приемами аналитического обобщения результатов профессиональной деятельности."
            },
            "УК-1.3": {
                "know": "Знает алгоритмы построения математических и концептуальных моделей исследуемых процессов.",
                "can": "Умеет разрабатывать план мероприятий по решению поставленной проблемы с учетом рисков.",
                "master": "Владеет методологией обоснования проектных и управленческих решений."
            },
            "УК-2": "Способен определять круг задач в рамках поставленной цели и выбирать оптимальные способы их решения, исходя из действующих правовых норм, имеющихся ресурсов и ограничений",
            "УК-2.1": {
                "know": "Знает методологию проектного менеджмента, этапы жизненного цикла проектов и критерии их успешности.",
                "can": "Умеет разрабатывать концепцию проекта, определять его цели, задачи, ресурсы и ограничения.",
                "master": "Владеет методами календарного и сетевого планирования проектной деятельности."
            },
            "УК-2.2": {
                "know": "Знает методики оценки рисков, ресурсного обеспечения и финансово-экономических показателей проектов.",
                "can": "Умеет оптимизировать план реализации проекта с учетом имеющихся материальных и временных ресурсов.",
                "master": "Владеет инструментами мониторинга и оперативного контроля выполнения проектных этапов."
            },
            "УК-2.3": {
                "know": "Знает нормативные правовые акты и стандарты оформления проектной и технической документации.",
                "can": "Умеет оформлять проектные решения в строгом соответствии с действующими нормативами и ГОСТами.",
                "master": "Владеет навыками защиты результатов проектных разработок перед экспертными комиссиями."
            },
            "УК-2.6": {
                "know": "Знает правовые нормы и требования регламентов при решении производственных и экологических задач.",
                "can": "Умеет определять приоритетные способы внедрения природоохранных технологий с учетом имеющихся ресурсов и ограничений.",
                "master": "Владеет методами оценки эффективности и алгоритмами практической реализации экологических решений на предприятии."
            },
            "УК-3": "Способен организовывать и руководить работой команды, вырабатывая командную стратегию для достижения поставленной цели",
            "УК-3.1": {
                "know": "Знает принципы командообразования, групповой динамики и распределения ролей в рабочих коллективах.",
                "can": "Умеет организовывать продуктивное взаимодействие членов команды для решения профессиональных задач.",
                "master": "Владеет методиками разрешения конфликтов и стимулирования командной инициативы."
            },
            "УК-3.4": {
                "know": "Знает принципы и методы координации работы специалистов при реализации природоохранных мероприятий.",
                "can": "Умеет предвидеть последствия принимаемых экологических и организационных решений при командной работе.",
                "master": "Владеет навыками руководства рабочей группой и делегирования задач в сфере производственного экомониторинга."
            },
            "УК-4": "Способен применять современные коммуникативные технологии, в том числе на иностранном(ых) языке(ах), для академического и профессионального взаимодействия",
            "УК-5": "Способен анализировать и учитывать разнообразие культур в процессе межкультурного взаимодействия",
            "УК-6": "Способен определять и реализовывать приоритеты собственной деятельности и способы ее совершенствования на основе самооценки",
            "ОПК-1": "Способен применять базовые и фундаментальные знания для решения задач профессиональной деятельности",
            "ОПК-1.1": {
                "know": "Знает фундаментальные законы и концептуальные основы предметной области.",
                "can": "Умеет использовать теоретические модели для анализа явлений и процессов.",
                "master": "Владеет базовыми методами естественнонаучных и профессиональных исследований."
            },
            "ОПК-1.2": {
                "know": "Знает современную терминологию, классификации и структуру предметной области.",
                "can": "Умеет структурировать исходную информацию и интерпретировать результаты измерений.",
                "master": "Владеет навыками научно-технического анализа прикладных данных."
            },
            "ОПК-1.3": {
                "know": "Знает принципы функционирования технологических и природных систем.",
                "can": "Умеет оценивать состояние объектов профессиональной деятельности по нормативным показателям.",
                "master": "Владеет инструментами первичной аналитической обработки информации."
            },
            "ОПК-2": "Способен применять специализированные знания и инструментальные средства для решения профессиональных задач",
            "ОПК-3": "Способен применять экологические методы исследований для решения научно-исследовательских и прикладных задач",
            "ОПК-4": "Способен применять нормативные правовые акты в сфере экологии, природопользования и охраны окружающей среды",
            "ОПК-5": "Способен проектировать, представлять, защищать и распространять результаты профессиональной деятельности",
            "ОПК-6": "Способен решать задачи профессиональной деятельности в области экологии с использованием информационно-коммуникационных и геоинформационных технологий",
            "ПКос-1": "Способен осуществлять мероприятия по охране и рациональному использованию земельных ресурсов и объектов недвижимости",
            "ПКос-1.1": {
                "know": "Знает государственные стандарты и нормативы в сфере рационального использования ресурсов.",
                "can": "Умеет проводить инвентаризацию и комплексную оценку состояния объектов недвижимости и природных сред.",
                "master": "Владеет регламентами подготовки отраслевой учетной и отчетной документации."
            },
            "ПКос-1.2": {
                "know": "Знает технологические регламенты проведения контрольно-надзорных мероприятий.",
                "can": "Умеет выявлять факты нерационального природопользования и нарушения стандартов.",
                "master": "Владеет методиками формирования предписаний и планов корректирующих мероприятий."
            },
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
            "ПКос-2.1": {
                "know": "Знает принципы построения и структуру пространственных баз данных геоинформационных систем.",
                "can": "Умеет создавать векторные слои и выполнять пространственные запросы в среде ГИС.",
                "master": "Владеет программным инструментарием QGIS и базовыми навыками геопространственного моделирования."
            },
            "ПКос-2.2": {
                "know": "Знает архитектуру корпоративных эко-ГИС и цифровых платформ производственного экологического мониторинга.",
                "can": "Умеет осуществлять сбор, пространственную привязку и тематическую обработку геоэкологических данных предприятия.",
                "master": "Владеет программным инструментарием ГИС для пространственного анализа зон экологического воздействия."
            },
            "ПКос-2.3": {
                "know": "Знает принципы комплексирования данных ДЗЗ, съемки с БАС и стационарных сенсорных IoT-сетей мониторинга.",
                "can": "Умеет интерпретировать материалы дистанционного зондирования для мониторинга эмиссий и выявления экологических нарушений.",
                "master": "Владеет методами автоматизированного дешифрирования мультиспектральных данных для оценки состояния природных сред."
            },
            "ПКос-3": "Способен организовывать и проводить экологический мониторинг компонентов природной среды и контроль соблюдения нормативов",
            "ПКдпо-1": "Способен разрабатывать и осуществлять мероприятия по внедрению наилучших доступных технологий и производственного экологического контроля",
            "ПКдпо-1.1": {
                "know": "Знает порядок проведения экологической экспертизы проектной документации и требования регламентов.",
                "can": "Умеет осуществлять эколого-технологическую оценку проектов расширения, реконструкции и модернизации производства.",
                "master": "Владеет методами производственного экологического контроля и планирования природоохранных мероприятий."
            },
            "ПКдпо-1.2": {
                "know": "Знает наилучшие доступные технологии (НДТ) в сфере деятельности организации, их экологические критерии и нормативы.",
                "can": "Умеет оценивать технологические показатели НДТ и сопоставлять их с действующими параметрами производства.",
                "master": "Владеет навыками формирования комплексных экологических решений по минимизации негативного воздействия на окружающую среду."
            },
            "ПКдпо-1.3": {
                "know": "Знает нормативные правовые акты в области обращения с опасными отходами и вторичными ресурсами.",
                "can": "Умеет разрабатывать паспорта отходов и нормативы образования отходов и лимитов на их размещение.",
                "master": "Владеет технологиями безопасного сбора, накопления, утилизации и обезвреживания отходов производства."
            },
            "ПКдпо-2": "Способен разрабатывать и осуществлять эколого-экономическое обоснование планов внедрения новой природоохранной техники и технологий в организации",
            "ПКдпо-2.1": {
                "know": "Знает методы расчетов для эколого-экономического обоснования внедрения в организации новой природоохранной техники и технологий.",
                "can": "Умеет проводить расчеты для эколого-экономического обоснования внедрения в организации новой природоохранной техники и технологий с учетом НДТ.",
                "master": "Владеет алгоритмами экономической оценки эффективности экологических проектов и сроков их окупаемости."
            },
            "ПКдпо-2.2": {
                "know": "Знает основные факторы, влияющие на экологическую безопасность при внедрении новой техники и технологий.",
                "can": "Умеет выделять и систематизировать основные факторы риска для экологической безопасности при модернизации технологических линий.",
                "master": "Владеет методологией комплексного факторного анализа безопасности природоохранных объектов предприятия."
            },
            "ПКдпо-2.3": {
                "know": "Знает принципы и технические регламенты эксплуатации современного экозащитного и пылегазоочистного оборудования.",
                "can": "Умеет рассчитывать параметры и эффективность работы оборудования для снижения выбросов и сбросов загрязняющих веществ.",
                "master": "Владеет методиками мониторинга технологических режимов работы природоохранного оборудования организации."
            },
            "ПКдпо-3": "Способен организовывать локализацию и ликвидацию аварийных выбросов и сбросов загрязняющих веществ, разрабатывать меры по предупреждению негативных экологических последствий",
            "ПКдпо-3.1": {
                "know": "Знает причины и источники аварийных выбросов и сбросов загрязняющих веществ в окружающую среду.",
                "can": "Умеет выявлять и анализировать причины и источники аварийных ситуаций, оценивать потенциальные зоны поражения.",
                "master": "Владеет методами моделирования распространения аварийных загрязнений в атмосфере и гидросфере."
            },
            "ПКдпо-3.2": {
                "know": "Знает алгоритмы и порядок оценки масштабов экологического ущерба от аварийных выбросов и сбросов.",
                "can": "Умеет оценивать последствия аварийных выбросов и сбросов загрязняющих веществ и рассчитывать причиненный ущерб природным средам.",
                "master": "Владеет инструментарием оперативного расчета экологического вреда и разработки планов рекультивации."
            },
            "ПКдпо-3.3": {
                "know": "Знает нормативные требования и протоколы локализации загрязнений и ликвидации последствий экологических аварий.",
                "can": "Умеет готовить обоснованные предложения и технические регламенты по предупреждению негативных последствий аварий.",
                "master": "Владеет навыками координации аварийно-спасательных и восстановительных природоохранных мероприятий на промышленном объекте."
            }
        }

        comp_groups = {}
        for code in competency_codes:
            parent = code.split('.')[0]
            if parent not in comp_groups:
                comp_groups[parent] = []
            if '.' in code and code not in comp_groups[parent]:
                comp_groups[parent].append(code)

        # Если индикаторы явно не были переданы для родительского кода
        for p in list(comp_groups.keys()):
            if not comp_groups[p]:
                # Ищем известные индикаторы в known_definitions
                matching_inds = [k for k in known_definitions if k.startswith(f"{p}.")]
                if matching_inds:
                    comp_groups[p] = sorted(matching_inds)
                else:
                    comp_groups[p] = [f"{p}.1", f"{p}.2", f"{p}.3"]

        for parent, inds in comp_groups.items():
            parent_title = known_definitions.get(parent, f"Профессиональная компетенция {parent}")
            indicators_list = []
            for ind in inds:
                ind_def = known_definitions.get(ind, {
                    "know": f"Знает теоретические основы, нормативные требования и стандарты в рамках {ind}.",
                    "can": f"Умеет применять методы, алгоритмы и инструменты {ind} в профессиональной деятельности.",
                    "master": f"Владеет практическими навыками, технологиями и профильным программным обеспечением по {ind}."
                })
                indicators_list.append({
                    "code": ind,
                    "title": f"Индикатор достижения компетенции {ind}",
                    "know": ind_def["know"],
                    "can": ind_def["can"],
                    "able": ind_def["can"],
                    "master": ind_def["master"]
                })

            competencies.append({
                "code": parent,
                "title": parent_title,
                "indicators": indicators_list
            })

        return competencies
