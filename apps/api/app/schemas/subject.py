import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_type: str
    name: str
    unified_credit_code: str | None
    listed: bool
    exchange: str | None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_type: str
    name: str


class RoleAssignmentOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID
    person_name: str
    role_type_code: str
    role_type_name: str
    valid_from: date
    valid_to: date | None
    active_at_query_time: bool


class OrganizationGovernanceOut(BaseModel):
    organization: OrganizationOut
    members: list[RoleAssignmentOut]


class SubjectGovernanceOut(BaseModel):
    subject: SubjectOut
    at: date
    organizations: list[OrganizationGovernanceOut]
