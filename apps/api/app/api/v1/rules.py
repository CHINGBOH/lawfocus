import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.v1.deps import CurrentUser, DbSession, get_trace_id, require_roles
from app.models import LegalRule, LegalRuleVersion, ReviewDecision, RuleSource, RuleTestCase, User
from app.models.enums import RbacRoleCode, ReviewDecisionType, ReviewType
from app.schemas.legal import ArticleVersionOut
from app.schemas.rules import (
    ReviewCreate,
    ReviewDecisionOut,
    ReviewOut,
    RuleDetailOut,
    RuleOut,
    RuleSourceOut,
    RuleTestCaseOut,
    RuleVersionDetailOut,
    RuleVersionSummary,
)
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthContext
from app.services.rule_governance_service import (
    InvalidTransitionError,
    PublishGateFailedError,
    RuleGovernanceService,
    SelfReviewNotAllowedError,
)

router = APIRouter(prefix="/rules", tags=["rules"])

KnowledgeEditorCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.KNOWLEDGE_EDITOR, RbacRoleCode.SYSTEM_ADMIN))
]
ReviewerCtx = Annotated[
    AuthContext,
    Depends(
        require_roles(
            RbacRoleCode.LEGAL_REVIEWER, RbacRoleCode.TECHNICAL_REVIEWER, RbacRoleCode.SYSTEM_ADMIN
        )
    ),
]
PublisherCtx = Annotated[
    AuthContext, Depends(require_roles(RbacRoleCode.PUBLISHER, RbacRoleCode.SYSTEM_ADMIN))
]


def _latest_version(db: DbSession, rule: LegalRule) -> LegalRuleVersion | None:
    stmt = (
        select(LegalRuleVersion)
        .where(LegalRuleVersion.rule_id == rule.id)
        .order_by(LegalRuleVersion.version_no.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _get_rule_or_404(db: DbSession, rule_id: uuid.UUID) -> LegalRule:
    rule = db.get(LegalRule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_NOT_FOUND", "message": f"no rule {rule_id}"},
        )
    return rule


@router.get("", response_model=list[RuleOut])
def list_rules(db: DbSession, _user: CurrentUser) -> list[RuleOut]:
    rules = db.execute(select(LegalRule).order_by(LegalRule.code)).scalars().all()
    out = []
    for rule in rules:
        version = _latest_version(db, rule)
        out.append(
            RuleOut(
                id=rule.id,
                code=rule.code,
                name=rule.name,
                latest_version=(
                    RuleVersionSummary(id=version.id, version_no=version.version_no, status=version.status)
                    if version
                    else None
                ),
            )
        )
    return out


@router.get("/{rule_id}", response_model=RuleDetailOut)
def get_rule(rule_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> RuleDetailOut:
    rule = _get_rule_or_404(db, rule_id)
    version = _latest_version(db, rule)
    if version is None:
        return RuleDetailOut(id=rule.id, code=rule.code, name=rule.name, latest_version=None)

    sources = db.execute(select(RuleSource).where(RuleSource.rule_version_id == version.id)).scalars().all()
    test_cases = (
        db.execute(select(RuleTestCase).where(RuleTestCase.rule_version_id == version.id)).scalars().all()
    )
    reviews = (
        db.execute(
            select(ReviewDecision, User)
            .join(User, User.id == ReviewDecision.reviewer_user_id)
            .where(ReviewDecision.rule_version_id == version.id)
            .order_by(ReviewDecision.created_at)
        )
        .all()
    )

    return RuleDetailOut(
        id=rule.id,
        code=rule.code,
        name=rule.name,
        latest_version=RuleVersionDetailOut(
            id=version.id,
            version_no=version.version_no,
            status=version.status,
            modality=version.modality,
            subject_type=version.subject_type,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            condition_expression=version.condition_expression,
            requirement_expression=version.requirement_expression,
            submitted_by=version.submitted_by,
            sources=[
                RuleSourceOut(
                    article_version=ArticleVersionOut.model_validate(s.article_version),
                    relation_type=s.relation_type,
                )
                for s in sources
            ],
            test_cases=[
                RuleTestCaseOut(
                    id=tc.id,
                    case_type=tc.case_type,
                    expected_status=tc.expected_status,
                    input_facts=tc.input_facts,
                    not_applicable_reason=tc.not_applicable_reason,
                )
                for tc in test_cases
            ],
            review_decisions=[
                ReviewDecisionOut(
                    id=review.id,
                    reviewer_user_id=review.reviewer_user_id,
                    reviewer_display_name=user.display_name,
                    review_type=review.review_type,
                    decision=review.decision,
                    comment=review.comment,
                    created_at=review.created_at,
                )
                for review, user in reviews
            ],
        ),
    )


def _audit_rule_action(
    request: Request,
    db: DbSession,
    *,
    actor_id: uuid.UUID,
    action: str,
    rule_id: uuid.UUID,
    version_no: int,
    decision: str,
    reason_code: str | None = None,
) -> None:
    AuditService(db).record(
        trace_id=get_trace_id(request),
        actor_id=actor_id,
        action=action,
        resource_type="rule",
        resource_id=str(rule_id),
        resource_version=str(version_no),
        decision=decision,
        reason_code=reason_code,
    )
    db.commit()


@router.post("/{rule_id}/submit", response_model=RuleVersionSummary)
def submit_rule(
    rule_id: uuid.UUID, request: Request, db: DbSession, ctx: KnowledgeEditorCtx
) -> RuleVersionSummary:
    rule = _get_rule_or_404(db, rule_id)
    version = _latest_version(db, rule)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_VERSION_NOT_FOUND", "message": f"rule {rule_id} has no version"},
        )
    try:
        version = RuleGovernanceService(db).submit(version, submitted_by=ctx.user_id)
    except InvalidTransitionError as exc:
        _audit_rule_action(
            request, db, actor_id=ctx.user_id, action="SUBMIT", rule_id=rule.id,
            version_no=version.version_no, decision="DENIED", reason_code="INVALID_TRANSITION",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    _audit_rule_action(
        request, db, actor_id=ctx.user_id, action="SUBMIT", rule_id=rule.id,
        version_no=version.version_no, decision="ALLOWED",
    )
    return RuleVersionSummary(id=version.id, version_no=version.version_no, status=version.status)


@router.post("/{rule_id}/reviews", response_model=ReviewOut, status_code=201)
def review_rule(
    rule_id: uuid.UUID, payload: ReviewCreate, request: Request, db: DbSession, ctx: ReviewerCtx
) -> ReviewDecision:
    rule = _get_rule_or_404(db, rule_id)
    version = _latest_version(db, rule)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_VERSION_NOT_FOUND", "message": f"rule {rule_id} has no version"},
        )
    try:
        review_type = ReviewType(payload.review_type)
        decision_type = ReviewDecisionType(payload.decision)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_REVIEW_VALUE", "message": str(exc)},
        ) from exc

    try:
        RuleGovernanceService(db).add_review(
            version, reviewer_id=ctx.user_id, review_type=review_type, decision=decision_type, comment=payload.comment
        )
    except SelfReviewNotAllowedError as exc:
        _audit_rule_action(
            request, db, actor_id=ctx.user_id, action="REVIEW", rule_id=rule.id,
            version_no=version.version_no, decision="DENIED", reason_code="SELF_REVIEW_NOT_ALLOWED",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "SELF_REVIEW_NOT_ALLOWED", "message": str(exc)},
        ) from exc
    except InvalidTransitionError as exc:
        _audit_rule_action(
            request, db, actor_id=ctx.user_id, action="REVIEW", rule_id=rule.id,
            version_no=version.version_no, decision="DENIED", reason_code="INVALID_TRANSITION",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc

    _audit_rule_action(
        request, db, actor_id=ctx.user_id, action="REVIEW", rule_id=rule.id,
        version_no=version.version_no, decision="ALLOWED",
        reason_code=f"{review_type.value}:{decision_type.value}",
    )
    decision_row = (
        db.query(ReviewDecision)
        .filter_by(rule_version_id=version.id, reviewer_user_id=ctx.user_id, review_type=review_type)
        .order_by(ReviewDecision.created_at.desc())
        .first()
    )
    return decision_row  # type: ignore[return-value]


@router.post("/{rule_id}/publish", response_model=RuleVersionSummary)
def publish_rule(
    rule_id: uuid.UUID, request: Request, db: DbSession, ctx: PublisherCtx
) -> RuleVersionSummary:
    rule = _get_rule_or_404(db, rule_id)
    version = _latest_version(db, rule)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RULE_VERSION_NOT_FOUND", "message": f"rule {rule_id} has no version"},
        )
    try:
        version = RuleGovernanceService(db).publish(version, publisher_id=ctx.user_id)
    except PublishGateFailedError as exc:
        _audit_rule_action(
            request, db, actor_id=ctx.user_id, action="PUBLISH", rule_id=rule.id,
            version_no=version.version_no, decision="DENIED", reason_code="PUBLISH_GATE_FAILED",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "PUBLISH_GATE_FAILED", "message": str(exc), "details": {"reasons": exc.reasons}},
        ) from exc
    except InvalidTransitionError as exc:
        _audit_rule_action(
            request, db, actor_id=ctx.user_id, action="PUBLISH", rule_id=rule.id,
            version_no=version.version_no, decision="DENIED", reason_code="INVALID_TRANSITION",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    _audit_rule_action(
        request, db, actor_id=ctx.user_id, action="PUBLISH", rule_id=rule.id,
        version_no=version.version_no, decision="ALLOWED",
    )
    return RuleVersionSummary(id=version.id, version_no=version.version_no, status=version.status)
