#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_parser_tool.py
Высокопроизводительный парсер PDF-документов на базе PyMuPDF (fitz).
Полностью заменяет IBM Docling, исключая зависимость от Docker-сервиса docling-serve и OCR.
Поддерживает как учебные планы (.plx.pdf / .pdf), так и силлабусы/РПД.
"""

import os
import re
import json
import logging
import pymupdf

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    try:
        from google.adk.tools import ToolContext
    except ImportError:
        class ToolContext:
            def __init__(self, state=None):
                self.state = state or {}

logger = logging.getLogger(__name__)


def extract_pdf_to_markdown(pdf_path: str) -> str:
    """
    Преобразует произвольный PDF-документ (РПД, ОПОП, силлабус)
    в структурированный Markdown с сохранением заголовков и таблиц
    через нативный векторный парсинг PyMuPDF.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF файл не найден: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    md_pages = []

    for page_num, page in enumerate(doc, 1):
        page_lines = []
        page_lines.append(f"\n<!-- Page {page_num} -->\n")

        # 1. Попытка извлечь структурированные таблицы
        try:
            tabs = page.find_tables()
            table_bboxes = [t.bbox for t in tabs] if tabs else []
        except Exception:
            tabs = []
            table_bboxes = []

        # 2. Извлечение текстовых блоков
        blocks = page.get_text("blocks")
        # blocks: (x0, y0, x1, y1, text, block_no, block_type)
        blocks.sort(key=lambda b: (b[1], b[0]))

        for b in blocks:
            b_text = b[4].strip()
            if not b_text:
                continue

            # Проверяем, не перекрывается ли блок распознанной таблицей
            in_table = False
            bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
            for tbox in table_bboxes:
                if (bx0 >= tbox[0] - 5 and by0 >= tbox[1] - 5 and
                    bx1 <= tbox[2] + 5 and by1 <= tbox[3] + 5):
                    in_table = True
                    break

            if in_table:
                continue

            # Определение уровня заголовка по содержанию и регистру
            first_line = b_text.split('\n')[0].strip()
            if re.match(r'^\d+\.\s+[А-ЯЁ\s]{3,}', first_line):
                page_lines.append(f"\n## {b_text}\n")
            elif re.match(r'^\d+\.\d+\.?\s+', first_line):
                page_lines.append(f"\n### {b_text}\n")
            elif first_line.isupper() and len(first_line) > 4 and len(first_line) < 80:
                page_lines.append(f"\n## {b_text}\n")
            else:
                page_lines.append(f"\n{b_text}\n")

        # 3. Добавление форматированных таблиц
        if tabs:
            for tab in tabs:
                df = tab.extract()
                if not df or len(df) < 1:
                    continue
                header = df[0]
                md_table = []
                clean_hdr = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in header]
                md_table.append("| " + " | ".join(clean_hdr) + " |")
                md_table.append("| " + " | ".join(["---"] * len(clean_hdr)) + " |")
                for row in df[1:]:
                    clean_row = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in row]
                    md_table.append("| " + " | ".join(clean_row) + " |")
                page_lines.append("\n" + "\n".join(md_table) + "\n")

        md_pages.append("\n".join(page_lines))

    doc.close()
    return "\n".join(md_pages)


def pdf_parser_tool(tool_context: ToolContext, pdf_path: str = None) -> dict:
    """
    Основной инструмент парсинга силлабуса/РПД в Markdown для агентов KOMA.
    Использует PyMuPDF для прямого векторного чтения за ~40 мс без обращения к Docker.
    """
    if pdf_path is None:
        pdf_path = tool_context.state.get("pdf_path", "FTD.01_R_RPD_2022.pdf")

    output_markdown_path = tool_context.state.get("output_markdown_path")
    regenerate = tool_context.state.get("regenerate", False)

    if output_markdown_path and os.path.exists(output_markdown_path) and not regenerate:
        logger.info(f"Используем готовый Markdown: {output_markdown_path}")
        try:
            with open(output_markdown_path, "r", encoding="utf-8") as f:
                content = f.read()
            tool_context.state["rpd_content"] = content
            return {
                "status": "success",
                "message": "Loaded parsed markdown from existing file",
                "char_count": len(content),
                "parsed_markdown": content
            }
        except Exception as e:
            logger.warning(f"Не удалось прочитать {output_markdown_path}: {e}")

    logger.info(f"Запуск PyMuPDF парсера для файла: {pdf_path}")

    if not os.path.exists(pdf_path):
        workspace_path = os.path.join(os.getcwd(), pdf_path)
        if os.path.exists(workspace_path):
            pdf_path = workspace_path
        else:
            msg = f"PDF файл не найден: {pdf_path}"
            logger.error(msg)
            return {"status": "error", "message": msg}

    try:
        markdown_content = extract_pdf_to_markdown(pdf_path)
        tool_context.state["rpd_content"] = markdown_content

        if output_markdown_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_markdown_path)), exist_ok=True)
            with open(output_markdown_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            logger.info(f"Сохранен Markdown в: {output_markdown_path}")

        logger.info(f"PyMuPDF успешно обработал {pdf_path} (символов: {len(markdown_content)}).")
        return {
            "status": "success",
            "message": "Successfully parsed PDF using PyMuPDF",
            "char_count": len(markdown_content),
            "parsed_markdown": markdown_content
        }
    except Exception as e:
        msg = f"Ошибка парсинга PDF через PyMuPDF: {e}"
        logger.exception(msg)
        return {"status": "error", "message": msg}


# Обратная совместимость для существующего кода
docling_parser_tool = pdf_parser_tool
