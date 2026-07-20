import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class RuleSetCreate(BaseModel):
    code: str
    name: str
    effective_from: date
    effective_to: date | None = None


class RuleSetMemberAdd(BaseModel):
    rule_version_id: uuid.UUID


class RuleVersionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_code: str
    version_no: int
    status: str


class RuleSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    version_no: int
    name: str
    status: str
    effective_from: date | None
    effective_to: date | None


class RuleSetDetailOut(RuleSetOut):
    members: list[RuleVersionSummaryOut]
