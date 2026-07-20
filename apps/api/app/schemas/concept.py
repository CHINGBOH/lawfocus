import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.legal import ArticleVersionOut


class ConceptSourceOut(BaseModel):
    article_version: ArticleVersionOut
    relation_type: str = "DEFINED_BY"


class ConceptDetailOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    concept_type: str
    status: str
    definition: str
    review_status: str
    valid_from: date
    valid_to: date | None
    sources: list[ConceptSourceOut]


class ConceptPreviewOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    concept_type: str
    review_status: str
    short_definition: str
