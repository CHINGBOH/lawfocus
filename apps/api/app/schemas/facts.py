import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class FactCreate(BaseModel):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    fact_type: str
    predicate: str
    object_value: dict
    valid_from: date
    valid_to: date | None = None
    subject_ref: uuid.UUID | None = None


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    fact_type: str
    predicate: str
    object_value: dict
    valid_from: date
    valid_to: date | None
    created_at: datetime


class EvidenceCreate(BaseModel):
    tenant_id: uuid.UUID
    evidence_type: str
    title: str
    source_url: str | None = None
    source_file: str | None = None
    page_no: int | None = None
    quote_text: str | None = None
    published_at: date | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    evidence_type: str
    title: str
    source_url: str | None
    source_file: str | None
    page_no: int | None
    quote_text: str | None
    published_at: date | None
    created_at: datetime


class FactEvidenceLinkCreate(BaseModel):
    support_type: str = "DIRECT"
    confidence: float | None = None


class FactEvidenceLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_id: uuid.UUID
    evidence_id: uuid.UUID
    support_type: str
    confidence: float | None


class EvidenceLinkSummary(BaseModel):
    evidence: EvidenceOut
    support_type: str
    confidence: float | None


class FactDetailOut(FactOut):
    evidence: list[EvidenceLinkSummary]
