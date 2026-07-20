import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.deps import DbSession, require_roles, require_tenant_access
from app.models import Evidence, Fact
from app.models.enums import RbacRoleCode
from app.schemas.facts import (
    EvidenceCreate,
    EvidenceLinkSummary,
    EvidenceOut,
    FactCreate,
    FactDetailOut,
    FactEvidenceLinkCreate,
    FactEvidenceLinkOut,
    FactOut,
)
from app.schemas.pagination import Page, paginate_params
from app.services.authorization_service import AuthContext
from app.services.fact_evidence_service import (
    EvidenceNotFoundError,
    FactEvidenceService,
    FactNotFoundError,
)

router = APIRouter(tags=["facts"])

ComplianceWriterCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.COMPLIANCE_USER, RbacRoleCode.SYSTEM_ADMIN))
]
# Facts/evidence are tenant-private organizational data (03-用户权限与内容审核模型.md
# §2), not public knowledge — a bare Reader grant does not cover them.
ComplianceReaderCtx = Annotated[
    AuthContext,
    Depends(
        require_roles(RbacRoleCode.COMPLIANCE_USER, RbacRoleCode.AUDITOR, RbacRoleCode.SYSTEM_ADMIN)
    ),
]


@router.post("/facts", response_model=FactOut, status_code=201)
def create_fact(
    payload: FactCreate, request: Request, db: DbSession, ctx: ComplianceWriterCtx
) -> FactOut:
    require_tenant_access(payload.tenant_id, ctx, db, request)
    fact = FactEvidenceService(db).create_fact(
        tenant_id=payload.tenant_id,
        company_id=payload.company_id,
        fact_type=payload.fact_type,
        predicate=payload.predicate,
        object_value=payload.object_value,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        subject_ref=payload.subject_ref,
    )
    db.commit()
    return fact  # type: ignore[return-value]


@router.get("/facts", response_model=Page[FactOut])
def list_facts(
    db: DbSession,
    ctx: ComplianceReaderCtx,
    request: Request,
    tenant_id: uuid.UUID,
    subject_id: uuid.UUID | None = None,
    at: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[FactOut]:
    require_tenant_access(tenant_id, ctx, db, request)
    page, page_size = paginate_params(page, page_size)
    items, total = FactEvidenceService(db).list_facts(
        tenant_id=tenant_id, subject_id=subject_id, at=at, page=page, page_size=page_size
    )
    return Page(items=items, page=page, page_size=page_size, total=total)  # type: ignore[arg-type]


@router.get("/facts/{fact_id}", response_model=FactDetailOut)
def get_fact(fact_id: uuid.UUID, request: Request, db: DbSession, ctx: ComplianceReaderCtx) -> FactDetailOut:
    try:
        fact = FactEvidenceService(db).get_fact(fact_id)
    except FactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "FACT_NOT_FOUND", "message": str(exc)}
        ) from exc
    require_tenant_access(fact.tenant_id, ctx, db, request)

    return FactDetailOut(
        id=fact.id,
        tenant_id=fact.tenant_id,
        company_id=fact.company_id,
        fact_type=fact.fact_type,
        predicate=fact.predicate,
        object_value=fact.object_value,
        valid_from=fact.valid_from,
        valid_to=fact.valid_to,
        created_at=fact.created_at,
        evidence=[
            EvidenceLinkSummary(
                evidence=EvidenceOut.model_validate(link.evidence),
                support_type=link.support_type,
                confidence=link.confidence,
            )
            for link in fact.evidence_links
        ],
    )


@router.post("/evidence", response_model=EvidenceOut, status_code=201)
def create_evidence(
    payload: EvidenceCreate, request: Request, db: DbSession, ctx: ComplianceWriterCtx
) -> EvidenceOut:
    require_tenant_access(payload.tenant_id, ctx, db, request)
    evidence = FactEvidenceService(db).create_evidence(
        tenant_id=payload.tenant_id,
        evidence_type=payload.evidence_type,
        title=payload.title,
        source_url=payload.source_url,
        source_file=payload.source_file,
        page_no=payload.page_no,
        quote_text=payload.quote_text,
        published_at=payload.published_at,
    )
    db.commit()
    return evidence  # type: ignore[return-value]


@router.get("/evidence", response_model=Page[EvidenceOut])
def list_evidence(
    db: DbSession,
    ctx: ComplianceReaderCtx,
    request: Request,
    tenant_id: uuid.UUID,
    subject_id: uuid.UUID | None = None,
    fact_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[EvidenceOut]:
    require_tenant_access(tenant_id, ctx, db, request)
    page, page_size = paginate_params(page, page_size)
    items, total = FactEvidenceService(db).list_evidence(
        tenant_id=tenant_id, subject_id=subject_id, fact_id=fact_id, page=page, page_size=page_size
    )
    return Page(items=items, page=page, page_size=page_size, total=total)  # type: ignore[arg-type]


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: uuid.UUID, request: Request, db: DbSession, ctx: ComplianceReaderCtx) -> EvidenceOut:
    try:
        evidence = FactEvidenceService(db).get_evidence(evidence_id)
    except EvidenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "EVIDENCE_NOT_FOUND", "message": str(exc)}
        ) from exc
    require_tenant_access(evidence.tenant_id, ctx, db, request)
    return evidence  # type: ignore[return-value]


@router.post(
    "/facts/{fact_id}/evidence/{evidence_id}",
    response_model=FactEvidenceLinkOut,
    status_code=201,
)
def link_fact_evidence(
    fact_id: uuid.UUID,
    evidence_id: uuid.UUID,
    payload: FactEvidenceLinkCreate,
    request: Request,
    db: DbSession,
    ctx: ComplianceWriterCtx,
) -> FactEvidenceLinkOut:
    fact = db.get(Fact, fact_id)
    if fact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FACT_NOT_FOUND", "message": f"no fact {fact_id}"},
        )
    evidence = db.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EVIDENCE_NOT_FOUND", "message": f"no evidence {evidence_id}"},
        )
    if fact.tenant_id != evidence.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TENANT_MISMATCH", "message": "fact and evidence belong to different tenants"},
        )
    require_tenant_access(fact.tenant_id, ctx, db, request)

    link = FactEvidenceService(db).link_fact_to_evidence(
        fact_id=fact_id,
        evidence_id=evidence_id,
        support_type=payload.support_type,
        confidence=payload.confidence,
    )
    db.commit()
    return link  # type: ignore[return-value]
