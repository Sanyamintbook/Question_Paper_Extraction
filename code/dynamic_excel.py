"""Excel generation driven by question records, with original OCR always available."""
from __future__ import annotations
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from excel_math import readable_math
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.views import Selection
import math
import re


MATCH_COLUMN_A = re.compile(r"^(?:column|col\.?|स्तम्भ|स्तंभ|कॉलम)\s*(?:a|1|अ)\s*[:.-]?$", re.I)
MATCH_COLUMN_B = re.compile(r"^(?:column|col\.?|स्तम्भ|स्तंभ|कॉलम)\s*(?:b|2|ब)\s*[:.-]?$", re.I)
MATCH_PAIR = re.compile(r"^(.+?)\s+(?:—|–|->|→|=>)\s+(.+)$")
MATCH_RIGHT_ITEM = re.compile(r"\s+(\([A-Za-z]\)|[A-Za-z][.)])\s+(.+)$")


def split_matching_text(text):
    """Return instruction, Column A and Column B without guessing content.

    Explicit column headings and visible pair separators are safe structural
    evidence. If OCR does not preserve that evidence, retain the full text in
    the instruction column rather than placing items in the wrong column.
    """
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    instruction = []
    left, right = [], []
    active = None
    saw_heading = False
    for line in lines:
        if MATCH_COLUMN_A.match(line):
            active, saw_heading = "left", True
            continue
        if MATCH_COLUMN_B.match(line):
            active, saw_heading = "right", True
            continue
        if saw_heading:
            (left if active == "left" else right).append(line)
            continue
        pair = MATCH_PAIR.match(line)
        if pair:
            left.append(pair.group(1).strip())
            right.append(pair.group(2).strip())
            continue
        # OCR sometimes emits both printed columns on one line, for example
        # "(i) Apple   (a) Fruit". Require distinct marker families so an
        # ordinary sentence containing parentheses is never split.
        paired_items = MATCH_RIGHT_ITEM.search(line)
        if paired_items and re.match(r"^\s*(?:\([ivxlcdm]+\)|[ivxlcdm]+[.)]|\(\d+\)|\d+[.)])\s+", line, re.I):
            left.append(line[:paired_items.start()].strip())
            right.append((paired_items.group(1) + " " + paired_items.group(2)).strip())
            continue
        instruction.append(line)
    if not left and not right:
        return "\n".join(lines), "", ""
    # A leading task line belongs in the instruction field, while any
    # unmatched OCR text remains visible there for correction.
    return "\n".join(instruction), "\n".join(left), "\n".join(right)


def readable_rows(ws, start, widths):
    """Size wrapped rows for their content instead of clipping every row at 42pt."""
    for row in ws.iter_rows(min_row=start):
        lines = 1
        for cell, width in zip(row, widths):
            text = str(cell.value or "")
            lines = max(lines, sum(max(1, math.ceil(len(line) / max(1, width * .8))) for line in text.split("\n")))
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.font = Font(name="Calibri", size=11)
        ws.row_dimensions[row[0].row].height = min(409, max(42, lines * 18 + 10))


def append_row(ws, values):
    ws.append([ILLEGAL_CHARACTERS_RE.sub("", v)[:32767] if isinstance(v, str) else v for v in values])
    # OCR/model text must remain text, including strings starting with '='.
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def build_dynamic_excel(analysis, destination, pages=None):
    from export_documents import safe_sheet_name, style_sheet, add_cover_sheet, add_intro
    from html import escape
    wb = Workbook()
    wb.remove(wb.active)
    if pages is None:
        first_page = analysis.sources[0].page if analysis.sources else 1
        pages = [{"blocks": [{"html": escape(s.text), "label": s.label} for s in analysis.sources if s.page == first_page]}]
    add_cover_sheet(wb, pages)
    grouped = defaultdict(list)
    for question in analysis.questions:
        grouped[question.kind].append(question)
    names = {"Cover Page", "Needs Review", "Source OCR"}
    kinds = {"mcq": "MCQ", "short_answer": "Short Ans", "long_answer": "Long Ans", "true_false": "True-False", "fill_blank": "Fill Blanks", "matching": "Matching", "descriptive": "Descriptive", "unknown": "Questions"}
    for index, (kind, items) in enumerate(grouped.items(), 1):
        section = kinds[kind]
        texts = [text for q in items for text in [q.text] + [o.text for o in q.options]]
        known = list(dict.fromkeys(lang for text in texts for lang in text if lang != "Original"))
        def display_text(text):
            values = dict(text)
            # Numbers and punctuation belong in the single language column of
            # a monolingual section; genuine mixed-language text stays intact.
            if "Original" in values:
                original = values.pop("Original")
                target = known[0] if known else "Text"
                values[target] = (values.get(target, "") + "\n" + original).strip()
            return values
        languages = list(dict.fromkeys(lang for text in texts for lang in display_text(text))) or ["Original"]
        labels = list(dict.fromkeys(o.label for q in items for o in q.options))
        ws = wb.create_sheet(safe_sheet_name(f"{index} - {kinds[kind]} ({len(items)} Ques)", names))
        headers = ["Q.No"] + [f"Question ({lang})" for lang in languages]
        if kind == "matching":
            headers += [f"Column A ({lang})" for lang in languages]
            headers += [f"Column B ({lang})" for lang in languages]
        else:
            headers += [f"Option {label} ({lang})" for label in labels for lang in languages]
        headers += ["Marks", "Answer"]
        section = kinds[kind] if section == "Unclassified" else section
        header_row = add_intro(ws, [section, f"{kinds[kind]} — {len(items)} questions"], len(headers))
        append_row(ws, headers)
        detail_columns = 2 * len(languages) if kind == "matching" else len(labels) * len(languages)
        widths = [9] + [46] * len(languages) + [30] * detail_columns + [10, 34]
        for q in items:
            options = {o.label: display_text(o.text) for o in q.options}
            question_text = display_text(q.text)
            matching = {lang: split_matching_text(question_text.get(lang, "")) for lang in languages}
            values = [q.number] + [readable_math(matching[lang][0] if kind == "matching" else question_text.get(lang, "")) for lang in languages]
            if kind == "matching":
                values += [readable_math(matching[lang][1]) for lang in languages]
                values += [readable_math(matching[lang][2]) for lang in languages]
            else:
                values += [readable_math(options.get(label, {}).get(lang, "")) for label in labels for lang in languages]
            values += [q.marks, ""]
            append_row(ws, values)
        style_sheet(ws, header_row, widths)
        ws.freeze_panes = None
        ws.sheet_view.pane = None
        ws.sheet_view.selection = [Selection(activeCell="A1", sqref="A1")]
        readable_rows(ws, header_row + 1, widths)
        ws.sheet_view.showGridLines = False
        ws.print_title_rows = f"1:{header_row}"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
    for sheet in wb:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)
