import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: str
    actor_id: uuid.UUID | None
    tenant_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    resource_version: str | None
    decision: str
    reason_code: str | None
    occurred_at: datetime
