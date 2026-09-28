"""Provider-independent records shared by extraction, review and export."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceBlock(Record):
    id: str
    page: int
    label: str
    text: str


class Option(Record):
    label: str
    text: dict[str, str] = Field(default_factory=dict)


class QuestionRecord(Record):
    number: str
    section: str = "Unclassified"
    kind: Literal["mcq", "short_answer", "long_answer", "descriptive", "true_false", "fill_blank", "matching", "unknown"] = "unknown"
    text: dict[str, str] = Field(default_factory=dict)
    options: list[Option] = Field(default_factory=list)
    marks: float | None = Field(default=None, ge=0)
    marks_evidence: str = ""
    source_ids: list[str] = Field(default_factory=list)
    review: list[str] = Field(default_factory=list)

    @property
    def english(self):
        return self.text.get("English", "")

    @property
    def hindi(self):
        return self.text.get("हिंदी", "")

    def option(self, label):
        return next((o.text.get("English") or o.text.get("हिंदी") or " / ".join(o.text.values())
                     for o in self.options if o.label == label), "")


class Extraction(Record):
    questions: list[QuestionRecord] = Field(default_factory=list)


class SectionPlan(Record):
    title: str
    kind: str
    evidence_ids: list[str]


class PaperPlan(Record):
    sections: list[SectionPlan] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Analysis(Record):
    schema_version: int = 1
    method: str = "rules"
    questions: list[QuestionRecord] = Field(default_factory=list)
    sources: list[SourceBlock] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    plan: PaperPlan | None = None


def language_text(text: str) -> dict[str, str]:
    """Preserve mixed-script text intact; never translate or discard symbols."""
    import re
    scripts = [("English", r"[A-Za-z]"), ("हिंदी", r"[\u0900-\u097f]"),
               ("বাংলা", r"[\u0980-\u09ff]"), ("ગુજરાતી", r"[\u0a80-\u0aff]"),
               ("ਪੰਜਾਬੀ", r"[\u0a00-\u0a7f]"), ("தமிழ்", r"[\u0b80-\u0bff]"),
               ("తెలుగు", r"[\u0c00-\u0c7f]"), ("ಕನ್ನಡ", r"[\u0c80-\u0cff]"),
               ("മലയാളം", r"[\u0d00-\u0d7f]"), ("ଓଡ଼ିଆ", r"[\u0b00-\u0b7f]"),
               ("العربية", r"[\u0600-\u06ff]")]
    # Shared punctuation (for example Bengali's danda) is not language evidence.
    counts = [(name, sum(c.isalpha() for c in re.findall(pattern, text))) for name, pattern in scripts]
    found = [name for name, count in counts if count]
    # Embedded Latin symbols/names do not turn a Hindi sentence into a
    # separate language. Preserve the entire sentence under its main script.
    if len(found) > 1:
        dominant, count = max(counts, key=lambda item: item[1])
        return {dominant: text.strip()}
    # A bilingual sentence with math/Latin names cannot safely be split by script.
    return {(found[0] if len(found) == 1 else "Original"): text.strip()} if text.strip() else {}
