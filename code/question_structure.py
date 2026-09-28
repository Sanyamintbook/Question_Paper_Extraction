"""Document-independent cues for question roles, not subject/number templates."""
import re

COMPOSITE_KINDS = {"fill_blank", "matching", "true_false"}
FRONT_MATTER = re.compile(
    r"(?:this\s+question\s+(?:paper|booklet)\s+is\s+divided|"
    r"in\s+section[- ]?[ab].*(?:questions?|marks?)|"
    r"use\s+of\s+(?:any\s+)?electronic\s+appliances?|"
    r"minutes?\s+of\s+extra\s+time|"
    r"questions?\s+nos?\.?\s*\d+\s*(?:to|[-–])\s*\d+\s+are\s+|"
    r"(?:प्रश्नपत्र|प्रश्न पुस्तिका).*(?:खण्ड|खंड)|"
    r"खण्ड[- ]?[अ-बAB].*(?:प्रश्न|अंक)|इलेक्ट्रॉनिक.*(?:वर्जित|प्रतिबंधित))",
    re.I | re.S,
)
SECTION_KIND = re.compile(
    r"(?:section|part|खण्ड|खंड|भाग)[- ]*([A-Zअ-ह0-9]+).*?"
    r"(objective|multiple\s+choice|short\s+answer|long\s+answer|"
    r"वस्तुनिष्ठ|लघु\s+उत्तरीय|दीर्घ\s+उत्तरीय)", re.I | re.S)
DESCRIPTIVE = re.compile(
    r"^(?:read|answer|explain|describe|discuss|define|draw|write|give|state|list|derive|prove|"
    r"calculate|evaluate|differentiate|what\s+(?:is|are|do)|why|how)\b|"
    r"(?:समझाइए|बताइए|लिखिए|वर्णन|व्याख्या|सिद्ध|कीजिए)", re.I)
CHOICE = re.compile(r"\b(?:choose|select|pick|which\s+of|correct\s+(?:answer|option))\b|सही.*(?:उत्तर|विकल्प)", re.I)
PART = re.compile(r"^\s*(?:\(([a-zA-Z]+|\d+|[कखगघকখগঘ])\)|([a-zA-Z]+)[.)])\s+")


def task_kind(body, inherited, detected):
    """Explicit task evidence wins over an inherited section hint."""
    if detected != "unknown":
        return detected
    if CHOICE.search(body):
        return "mcq"
    # Verbs such as explain/define occur naturally inside both short- and
    # long-answer sections. The section supplies the answer-length category;
    # the verb only confirms that the item is descriptive rather than MCQ.
    if inherited in {"short_answer", "long_answer"}:
        return inherited
    if DESCRIPTIVE.search(body):
        return "descriptive"
    if inherited != "unknown":
        return inherited
    return "unknown"


def kind_from_section_instruction(text):
    match = SECTION_KIND.search(text)
    if not match:
        return None
    phrase = match.group(2).casefold()
    if "objective" in phrase or "multiple" in phrase or "वस्तुनिष्ठ" in phrase:
        return "mcq"
    if "short" in phrase or "लघु" in phrase:
        return "short_answer"
    return "long_answer"


def is_subpart(text, kind):
    return kind in COMPOSITE_KINDS | {"descriptive", "short_answer", "long_answer"} and bool(PART.match(text))


def append_text(question, text, source_id, language_text):
    if source_id not in question.source_ids:
        question.source_ids.append(source_id)
    for language, value in language_text(text).items():
        question.text[language] = (question.text.get(language, "") + "\n" + value).strip()


def choice_evidence(lines, question_pattern, option_pattern):
    """Inspect the whole question span, independent of OCR block count.

    A pair of labelled alternatives is evidence for MCQ only when they don't
    themselves look like open-ended subtasks. Numeric top-level questions end
    the span; option numbering in parentheses does not.
    """
    labels = []
    for line in lines:
        if question_pattern.match(line):
            break
        match = option_pattern.match(line)
        if match:
            if DESCRIPTIVE.search(line[match.end():]):
                return False
            labels.append(match.group(1) or match.group(2))
    return len(set(labels)) >= 2
