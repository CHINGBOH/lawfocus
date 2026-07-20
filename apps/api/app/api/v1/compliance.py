import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.v1.deps import DbSession, get_trace_id, require_roles, require_tenant_access
from app.domain.rule_requirement import InvalidRequirementExpressionError
from app.models import ComplianceCheck, Conclusion
from app.models.enums import ComplianceCheckStatus, RbacRoleCode
from app.schemas.compliance import (
    ComplianceCheckCreate,
    ComplianceCheckOut,
    PrecheckItemOut,
    PrecheckOut,
    ProofOut,
)
from app.schemas.pagination import Page, paginate_params
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthContext
from app.services.rule_engine import (
    RuleEngine,
    RuleVersionNotRegisteredError,
    SubjectNotFoundError,
    UnknownRuleCodeError,
)
from app.services.rule_set_service import RuleSetNotFoundError

router = APIRouter(tags=["compliance"])

ComplianceExecutorCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.COMPLIANCE_USER, RbacRoleCode.SYSTEM_ADMIN))
]
ComplianceReaderCtx = Annotated[
    AuthContext,
    Depends(
        require_roles(
            RbacRoleCode.READER,
            RbacRoleCode.COMPLIANCE_USER,
            RbacRoleCode.AUDITOR,
            RbacRoleCode.SYSTEM_ADMIN,
        )
    ),
]


@router.get("/compliance-checks/precheck", response_model=PrecheckOut)
def precheck_compliance_check(
    db: DbSession,
    ctx: ComplianceExecutorCtx,
    request: Request,
    tenant_id: uuid.UUID,
    subject_id: uuid.UUID,
    evaluation_time: datetime,
    ruleset_id: uuid.UUID,
) -> PrecheckOut:
    """Read-only dry run — no ComplianceCheck is created, no audit event is
    recorded, no Idempotency-Key is required. Lets the wizard show which
    rules are applicable and which facts are missing before the user
    commits to a real, audited check."""
    require_tenant_access(tenant_id, ctx, db, request)

    engine = RuleEngine(db)
    try:
        previews = engine.preview_compliance_check(
            company_id=subject_id, evaluation_time=evaluation_time, rule_set_id=ruleset_id
        )
    except SubjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except RuleSetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_SET_NOT_FOUND", "message": str(exc)},
        ) from exc
    except UnknownRuleCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "UNKNOWN_RULE_CODE", "message": str(exc)},
        ) from exc
    except InvalidRequirementExpressionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_RULE_REQUIREMENT", "message": str(exc)},
        ) from exc

    return PrecheckOut(items=[PrecheckItemOut.from_preview(p) for p in previews])


@router.post("/compliance-checks", response_model=ComplianceCheckOut, status_code=201)
def create_compliance_check(
    payload: ComplianceCheckCreate,
    request: Request,
    db: DbSession,
    ctx: ComplianceExecutorCtx,
    idempotency_key_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ComplianceCheckOut:
    require_tenant_access(payload.tenant_id, ctx, db, request)

    deprecations: list[str] = []
    subject_id = payload.resolved_subject_id
    if payload.company_id is not None and payload.subject_id is None:
        deprecations.append("company_id is deprecated; use subject_id")

    idempotency_key = idempotency_key_header or payload.idempotency_key
    if idempotency_key_header is None and payload.idempotency_key is not None:
        deprecations.append("body idempotency_key is deprecated; use the Idempotency-Key header")
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "MISSING_IDEMPOTENCY_KEY",
                "message": "Idempotency-Key header (or deprecated body field) is required",
            },
        )

    engine = RuleEngine(db)
    try:
        if payload.ruleset_id is not None:
            check = engine.run_compliance_check(
                tenant_id=payload.tenant_id,
                company_id=subject_id,
                evaluation_time=payload.evaluation_time,
                rule_set_id=payload.ruleset_id,
                idempotency_key=idempotency_key,
                requested_by=ctx.user_id,
            )
        else:
            deprecations.append("rule_codes is deprecated; use ruleset_id with a PUBLISHED RuleSet")
            check = engine.run_compliance_check_legacy(
                tenant_id=payload.tenant_id,
                company_id=subject_id,
                evaluation_time=payload.evaluation_time,
                rule_codes=payload.rule_codes or [],
                idempotency_key=idempotency_key,
                requested_by=ctx.user_id,
            )
    except SubjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBJECT_NOT_FOUND", "message": str(exc)},
        ) from exc
    except RuleSetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_SET_NOT_FOUND", "message": str(exc)},
        ) from exc
    except UnknownRuleCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "UNKNOWN_RULE_CODE", "message": str(exc)},
        ) from exc
    except InvalidRequirementExpressionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_RULE_REQUIREMENT", "message": str(exc)},
        ) from exc
    except RuleVersionNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RULE_VERSION_NOT_REGISTERED", "message": str(exc)},
        ) from exc

    AuditService(db).record(
        trace_id=get_trace_id(request),
        actor_id=ctx.user_id,
        tenant_id=payload.tenant_id,
        action="CREATE",
        resource_type="compliance_check",
        resource_id=str(check.id),
        decision="ALLOWED",
    )
    db.commit()
    db.refresh(check)
    return ComplianceCheckOut.from_check(check, deprecations)


@router.get("/compliance-checks", response_model=Page[ComplianceCheckOut])
def list_compliance_checks(
    db: DbSession,
    ctx: ComplianceReaderCtx,
    request: Request,
    tenant_id: uuid.UUID,
    subject_id: uuid.UUID | None = None,
    status_filter: ComplianceCheckStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[ComplianceCheckOut]:
    require_tenant_access(tenant_id, ctx, db, request)
    page, page_size = paginate_params(page, page_size)

    stmt = select(ComplianceCheck).where(ComplianceCheck.tenant_id == tenant_id)
    if subject_id is not None:
        stmt = stmt.where(ComplianceCheck.company_id == subject_id)
    if status_filter is not None:
        stmt = stmt.where(ComplianceCheck.status == status_filter)

    total = len(db.execute(stmt).scalars().all())
    stmt = stmt.order_by(ComplianceCheck.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    checks = db.execute(stmt).scalars().all()
    return Page(items=[ComplianceCheckOut.from_check(c) for c in checks], page=page, page_size=page_size, total=total)


@router.get("/compliance-checks/{check_id}", response_model=ComplianceCheckOut)
def get_compliance_check(
    check_id: uuid.UUID, request: Request, db: DbSession, ctx: ComplianceReaderCtx
) -> ComplianceCheckOut:
    check = db.get(ComplianceCheck, check_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPLIANCE_CHECK_NOT_FOUND", "message": f"no compliance_check {check_id}"},
        )
    require_tenant_access(check.tenant_id, ctx, db, request)
    return ComplianceCheckOut.from_check(check)


@router.get("/conclusions/{conclusion_id}/proof", response_model=ProofOut)
def get_conclusion_proof(
    conclusion_id: uuid.UUID, request: Request, db: DbSession, ctx: ComplianceReaderCtx
) -> ProofOut:
    conclusion = db.get(Conclusion, conclusion_id)
    if conclusion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONCLUSION_NOT_FOUND", "message": f"no conclusion {conclusion_id}"},
        )
    check = db.get(ComplianceCheck, conclusion.compliance_check_id)
    assert check is not None, "conclusion.compliance_check_id is a NOT NULL FK"
    require_tenant_access(check.tenant_id, ctx, db, request)

    proof = conclusion.proof
    if proof is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROOF_NOT_FOUND", "message": f"no proof for conclusion {conclusion_id}"},
        )
    return ProofOut.from_proof(proof)
