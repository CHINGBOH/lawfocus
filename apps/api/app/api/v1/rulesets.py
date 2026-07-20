import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.v1.deps import CurrentUser, DbSession, get_trace_id, require_roles
from app.models import LegalRuleVersion, RuleSet
from app.models.enums import RbacRoleCode, RuleSetStatus
from app.schemas.rule_set import (
    RuleSetCreate,
    RuleSetDetailOut,
    RuleSetMemberAdd,
    RuleSetOut,
    RuleVersionSummaryOut,
)
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthContext
from app.services.rule_set_service import (
    MemberNotPublishedError,
    RuleSetError,
    RuleSetNotEditableError,
    RuleSetService,
)

router = APIRouter(prefix="/rulesets", tags=["rulesets"])

EditorCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.KNOWLEDGE_EDITOR, RbacRoleCode.SYSTEM_ADMIN))
]
PublisherCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.PUBLISHER, RbacRoleCode.SYSTEM_ADMIN))
]


def _to_detail_out(db: DbSession, rule_set: RuleSet) -> RuleSetDetailOut:
    members = RuleSetService(db).member_rule_versions(rule_set)
    return RuleSetDetailOut(
        id=rule_set.id,
        code=rule_set.code,
        version_no=rule_set.version_no,
        name=rule_set.name,
        status=rule_set.status,
        effective_from=rule_set.effective_from,
        effective_to=rule_set.effective_to,
        members=[
            RuleVersionSummaryOut(id=rv.id, rule_code=rv.rule.code, version_no=rv.version_no, status=rv.status)
            for rv in members
        ],
    )


@router.get("", response_model=list[RuleSetOut])
def list_rulesets(
    db: DbSession,
    _user: CurrentUser,
    status_filter: RuleSetStatus | None = None,
    at: date | None = None,
) -> list[RuleSet]:
    stmt = select(RuleSet).order_by(RuleSet.code, RuleSet.version_no.desc())
    if status_filter is not None:
        stmt = stmt.where(RuleSet.status == status_filter)
    if at is not None:
        stmt = stmt.where(
            RuleSet.effective_from <= at,
        ).where((RuleSet.effective_to.is_(None)) | (RuleSet.effective_to > at))
    return list(db.execute(stmt).scalars().all())


@router.get("/{rule_set_id}", response_model=RuleSetDetailOut)
def get_ruleset(rule_set_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> RuleSetDetailOut:
    rule_set = db.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_SET_NOT_FOUND", "message": f"no rule_set {rule_set_id}"},
        )
    return _to_detail_out(db, rule_set)


@router.post("", response_model=RuleSetOut, status_code=201)
def create_ruleset(payload: RuleSetCreate, db: DbSession, _ctx: EditorCtx) -> RuleSet:
    rule_set = RuleSetService(db).create_draft(
        code=payload.code, name=payload.name, effective_from=payload.effective_from, effective_to=payload.effective_to
    )
    db.commit()
    return rule_set


@router.post("/{rule_set_id}/members", response_model=RuleSetDetailOut, status_code=201)
def add_ruleset_member(
    rule_set_id: uuid.UUID, payload: RuleSetMemberAdd, db: DbSession, _ctx: EditorCtx
) -> RuleSetDetailOut:
    rule_set = db.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_SET_NOT_FOUND", "message": f"no rule_set {rule_set_id}"},
        )
    rule_version = db.get(LegalRuleVersion, payload.rule_version_id)
    if rule_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_VERSION_NOT_FOUND", "message": f"no rule_version {payload.rule_version_id}"},
        )
    try:
        RuleSetService(db).add_member(rule_set, rule_version)
    except RuleSetNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "RULE_SET_NOT_EDITABLE", "message": str(exc)}
        ) from exc
    except MemberNotPublishedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "MEMBER_NOT_PUBLISHED", "message": str(exc)},
        ) from exc
    db.commit()
    return _to_detail_out(db, rule_set)


@router.post("/{rule_set_id}/publish", response_model=RuleSetOut)
def publish_ruleset(rule_set_id: uuid.UUID, request: Request, db: DbSession, ctx: PublisherCtx) -> RuleSet:
    rule_set = db.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_SET_NOT_FOUND", "message": f"no rule_set {rule_set_id}"},
        )
    try:
        RuleSetService(db).publish(rule_set)
    except RuleSetNotEditableError as exc:
        AuditService(db).record(
            trace_id=get_trace_id(request), actor_id=ctx.user_id, action="PUBLISH",
            resource_type="rule_set", resource_id=str(rule_set.id), resource_version=str(rule_set.version_no),
            decision="DENIED", reason_code="RULE_SET_NOT_EDITABLE",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "RULE_SET_NOT_EDITABLE", "message": str(exc)}
        ) from exc
    except RuleSetError as exc:
        AuditService(db).record(
            trace_id=get_trace_id(request), actor_id=ctx.user_id, action="PUBLISH",
            resource_type="rule_set", resource_id=str(rule_set.id), resource_version=str(rule_set.version_no),
            decision="DENIED", reason_code="RULE_SET_EMPTY",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "RULE_SET_EMPTY", "message": str(exc)},
        ) from exc
    AuditService(db).record(
        trace_id=get_trace_id(request), actor_id=ctx.user_id, action="PUBLISH",
        resource_type="rule_set", resource_id=str(rule_set.id), resource_version=str(rule_set.version_no),
        decision="ALLOWED",
    )
    db.commit()
    return rule_set
