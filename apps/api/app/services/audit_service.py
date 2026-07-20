import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import AuditEvent


class AuditService:
    """Append-only. Callers must never UPDATE/DELETE an AuditEvent row."""

    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        trace_id: str,
        action: str,
        resource_type: str,
        decision: str,
        actor_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID | None = None,
        resource_id: str | None = None,
        resource_version: str | None = None,
        reason_code: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=resource_version,
            decision=decision,
            reason_code=reason_code,
            occurred_at=datetime.now(UTC),
        )
        self.session.add(event)
        self.session.flush()
        return event
