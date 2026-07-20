import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class LegalVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_name: str
    promulgated_at: date | None
    effective_from: date
    effective_to: date | None
    status: str


class LawOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    document_type: str
    issuer: str | None
    jurisdiction: str | None
    versions: list[LegalVersionOut]


class ArticleVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    article_id: uuid.UUID
    article_no: str
    legal_version_id: uuid.UUID
    chapter_no: str | None
    section_no: str | None
    article_text: str
    valid_from: date
    valid_to: date | None
    created_at: datetime


class ArticleSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    article_no: str
    chapter_no: str | None
    section_no: str | None
    summary: str


class ArticleNavigationOut(BaseModel):
    current: ArticleVersionOut
    previous_article_no: str | None
    next_article_no: str | None
