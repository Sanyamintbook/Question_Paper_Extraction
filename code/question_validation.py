"""Evidence checks and explicit review coverage; no invented marks or options."""
from __future__ import annotations
import re
from collections import Counter
from question_schema import Analysis


def normalized(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def validate_analysis(analysis: Analysis) -> Analysis:
    sources = {b.id: b for b in analysis.sources}
    duplicates = Counter((q.section, q.number) for q in analysis.questions)
    for q in analysis.questions:
        evidence = " ".join(sources[s].text for s in q.source_ids if s in sources)
        if not q.source_ids or any(s not in sources for s in q.source_ids):
            q.review.append("Missing or invalid source reference")
        if not q.text or not any(q.text.values()):
            q.review.append("Question text is empty")
        for value in list(q.text.values()) + [t for o in q.options for t in o.text.values()]:
            if normalized(value) not in normalized(evidence):
                q.review.append("Extracted text is not an exact source match; inspect original")
            if len(value) > 30000:
                q.review.append("Long text: see full text in Source OCR and analysis JSON")
        if q.kind == "unknown":
            q.review.append("Question type needs review")
        if q.kind == "mcq" and (len(q.options) < 2 or any(not any(o.text.values()) for o in q.options)):
            q.review.append("MCQ choices may be incomplete")
        if len({o.label for o in q.options}) != len(q.options):
            q.review.append("Duplicate option labels")
        if duplicates[(q.section, q.number)] > 1:
            q.review.append("Repeated question number in this section; retained separately")
        if q.marks is not None:
            # Require a marked numeric phrase, not a bare number elsewhere in the question.
            match = re.search(r"(\d+(?:\.\d+)?)\s*(?:marks?\b|अंक)", q.marks_evidence, re.I)
            if not match:
                match = re.fullmatch(r"\(\s*(\d{1,2})\s*\)", q.marks_evidence)
            if not match and any(re.search(r"(?:right.hand margin.*marks|हाशिये.*अंक)", s.text, re.I) for s in analysis.sources):
                match = re.fullmatch(r"(?:[?।)]?\s*|\(\s*)(\d{1,2})\s*\)?", q.marks_evidence)
            if (not match or float(match.group(1)) != q.marks or
                    normalized(q.marks_evidence) not in normalized(evidence)):
                q.marks = None
                q.review.append("Marks not supported by explicit source evidence; left blank")
        q.review = list(dict.fromkeys(q.review))
    return analysis


def review_rows(analysis):
    rows = []
    sources = {s.id: s for s in analysis.sources}
    assigned = set()
    for q in analysis.questions:
        assigned.update(q.source_ids)
        if q.review:
            rows.append([q.number, q.section, "; ".join(q.review),
                         ", ".join(str(sources[s].page) for s in q.source_ids if s in sources),
                         ", ".join(q.source_ids), "\n".join(sources[s].text for s in q.source_ids if s in sources)])
    for source in analysis.sources:
        if source.id not in assigned:
            rows.append(["", "", "Unassigned OCR text (may be a heading or instruction)",
                         str(source.page), source.id, source.text])
        else:
            remainder = normalized(source.text)
            for q in analysis.questions:
                if source.id not in q.source_ids:
                    continue
                values = list(q.text.values()) + [v for o in q.options for v in o.text.values()]
                for value in sorted(values, key=len, reverse=True):
                    remainder = remainder.replace(normalized(value), " ")
            # Ignore common number/option labels; any substantive remainder needs review.
            remainder = re.sub(r"\b(?:\d+|[a-z])\b|[^\w\s]", " ", remainder)
            if len(re.sub(r"\s", "", remainder)) > 3:
                rows.append(["", "", "Source block may contain additional unassigned text",
                             str(source.page), source.id, source.text])
    for note in analysis.notes:
        rows.append(["", "", note, "", "", ""])
    return rows


def validation_report(analysis):
    sections = {}
    for q in analysis.questions:
        entry = sections.setdefault(q.section, {"questions": 0, "review_questions": [],
                                               "missing_english": [], "missing_hindi": [], "incomplete_options": []})
        entry["questions"] += 1
        if q.review:
            entry["review_questions"].append({"number": q.number, "reasons": q.review})
        if q.kind == "mcq" and (len(q.options) < 2 or any(not any(o.text.values()) for o in q.options)):
            entry["incomplete_options"].append(q.number)
    return {"total_questions": len(analysis.questions), "method": analysis.method,
            "review_items": len(review_rows(analysis)), "notes": analysis.notes, "sections": sections}
