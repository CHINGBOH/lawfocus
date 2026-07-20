import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.legal import ArticleVersionOut


class RuleVersionSummary(BaseModel):
    id: uuid.UUID
    version_no: int
    status: str


class RuleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    latest_version: RuleVersionSummary | None


class RuleSourceOut(BaseModel):
    article_version: ArticleVersionOut
    relation_type: str


class RuleTestCaseOut(BaseModel):
    id: uuid.UUID
    case_type: str
    expected_status: str
    input_facts: dict
    not_applicable_reason: str | None


class ReviewDecisionOut(BaseModel):
    id: uuid.UUID
    reviewer_user_id: uuid.UUID
    reviewer_display_name: str
    review_type: str
    decision: str
    comment: str | None
    created_at: datetime


class RuleVersionDetailOut(BaseModel):
    id: uuid.UUID
    version_no: int
    status: str
    modality: str
    subject_type: str | None
    effective_from: date | None
    effective_to: date | None
    condition_expression: dict
    requirement_expression: dict
    submitted_by: uuid.UUID | None
    sources: list[RuleSourceOut]
    test_cases: list[RuleTestCaseOut]
    review_decisions: list[ReviewDecisionOut]


class RuleDetailOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    latest_version: RuleVersionDetailOut | None


class ReviewCreate(BaseModel):
    review_type: str
    decision: str
    comment: str | None = None


class ReviewOut(BaseModel):
    id: uuid.UUID
    rule_version_id: uuid.UUID
    review_type: str
    decision: str
    comment: str | None
