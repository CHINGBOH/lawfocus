import uuid

from pydantic import BaseModel


class TextSegmentOut(BaseModel):
    text: str
    concept_id: uuid.UUID | None


class SynthesisOut(BaseModel):
    article_version_id: uuid.UUID
    text_segments: list[TextSegmentOut]
    generated_by: str = "deterministic_template"


class RuleSynthesisOut(BaseModel):
    article_version_id: uuid.UUID
    rule_id: uuid.UUID
    rule_code: str
    rule_name: str
    text_segments: list[TextSegmentOut]
    generated_by: str = "deterministic_rule_template"
