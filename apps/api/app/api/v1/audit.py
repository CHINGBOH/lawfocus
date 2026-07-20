import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.v1.deps import CurrentUser, DbSession, require_roles, require_tenant_access
from app.models import AuditEvent
from app.models.enums import RbacRoleCode
from app.schemas.audit import AuditEventOut
from app.schemas.pagination import Page, paginate_params
from app.services.authorization_service import AuthContext

router = APIRouter(prefix="/audit-events", tags=["audit"])

AuditReaderCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.AUDITOR, RbacRoleCode.SYSTEM_ADMIN))
]


@router.get("", response_model=Page[AuditEventOut])
def list_audit_events(
    request: Request,
    db: DbSession,
    ctx: AuditReaderCtx,
    tenant_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    decision: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[AuditEventOut]:
    """Auditor-only view across all tenants/actors. For a user's own recent
    activity (e.g. a workbench "recently read" card), see `/audit-events/mine`
    instead — that endpoint is open to any authenticated user because it is
    hard-scoped to the caller's own actions and can never leak another
    tenant's or user's audit trail."""
    if tenant_id is not None:
        require_tenant_access(tenant_id, ctx, db, request)
    page, page_size = paginate_params(page, page_size)

    conditions = []
    if tenant_id is not None:
        conditions.append(AuditEvent.tenant_id == tenant_id)
    if actor_id is not None:
        conditions.append(AuditEvent.actor_id == actor_id)
    if action is not None:
        conditions.append(AuditEvent.action == action)
    if resource_type is not None:
        conditions.append(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        conditions.append(AuditEvent.resource_id == resource_id)
    if decision is not None:
        conditions.append(AuditEvent.decision == decision)
    if occurred_from is not None:
        conditions.append(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        conditions.append(AuditEvent.occurred_at <= occurred_to)

    count_stmt = select(AuditEvent)
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
    total = len(db.execute(count_stmt).scalars().all())

    stmt = count_stmt.order_by(AuditEvent.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
    events = db.execute(stmt).scalars().all()
    items = [AuditEventOut.model_validate(e) for e in events]
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/mine", response_model=Page[AuditEventOut])
def list_my_audit_events(
    db: DbSession,
    user: CurrentUser,
    action: str | None = None,
    resource_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[AuditEventOut]:
    """Self-scoped activity feed — always filtered to the caller's own
    `actor_id`, regardless of role. Powers workbench cards like "recently
    read" without granting non-Auditor users visibility into anyone else's
    audit trail."""
    page, page_size = paginate_params(page, page_size)

    stmt = select(AuditEvent).where(AuditEvent.actor_id == user.id)
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if resource_type is not None:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)

    total = len(db.execute(stmt).scalars().all())
    stmt = stmt.order_by(AuditEvent.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
    events = db.execute(stmt).scalars().all()
    items = [AuditEventOut.model_validate(e) for e in events]
    return Page(items=items, page=page, page_size=page_size, total=total)
