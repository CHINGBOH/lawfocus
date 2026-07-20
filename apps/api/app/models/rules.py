import uuid
from datetime import date

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk, valid_interval_check
from app.models.enums import ReviewDecisionType, ReviewStatus, ReviewType, RuleSetStatus, RuleTestCaseType
from app.models.legal import ArticleVersion


class LegalRule(Base, UUIDPk, CreatedAtMixin):
    """A stable rule identity, e.g. GOV-ID-002 — versions carry the actual logic."""

    __tablename__ = "legal_rule"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    versions: Mapped[list["LegalRuleVersion"]] = relationship(back_populates="rule")


class LegalRuleVersion(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "legal_rule_version"
    __table_args__ = (
        UniqueConstraint("rule_id", "version_no", name="uq_rule_version_no"),
        valid_interval_check("effective_from", "effective_to"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="rule_review_status"), nullable=False, default=ReviewStatus.DRAFT
    )
    subject_type: Mapped[str | None] = mapped_column(String(100))
    modality: Mapped[str] = mapped_column(String(30), nullable=False)
    condition_expression: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    requirement_expression: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    exception_expression: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    consequence_expression: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    effective_from: Mapped[date | None] = mapped_column()
    effective_to: Mapped[date | None] = mapped_column()
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )

    rule: Mapped[LegalRule] = relationship(back_populates="versions")
    sources: Mapped[list["RuleSource"]] = relationship(back_populates="rule_version")
    test_cases: Mapped[list["RuleTestCase"]] = relationship(back_populates="rule_version")
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="rule_version")


class RuleSource(Base, CreatedAtMixin):
    """Every published rule version must trace back to at least one ArticleVersion
    (Norm(n) => exists a: FORMALIZED_FROM(n,a))."""

    __tablename__ = "rule_source"

    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule_version.id"), primary_key=True
    )
    article_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("article_version.id"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False, default="FORMALIZED_FROM")

    rule_version: Mapped[LegalRuleVersion] = relationship(back_populates="sources")
    article_version: Mapped[ArticleVersion] = relationship()


class RuleTestCase(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "rule_test_case"

    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule_version.id"), nullable=False
    )
    case_type: Mapped[RuleTestCaseType] = mapped_column(
        Enum(RuleTestCaseType, name="rule_test_case_type"), nullable=False
    )
    input_facts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expected_status: Mapped[str] = mapped_column(String(30), nullable=False)
    not_applicable_reason: Mapped[str | None] = mapped_column(Text)

    rule_version: Mapped[LegalRuleVersion] = relationship(back_populates="test_cases")


class ReviewDecision(Base, UUIDPk, CreatedAtMixin):
    """Legal and technical review are both required before PUBLISHED; the
    submitter of a rule_version may never be its own final legal reviewer —
    enforced in AuthorizationService, not by a DB constraint alone."""

    __tablename__ = "review_decision"

    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule_version.id"), nullable=False
    )
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    review_type: Mapped[ReviewType] = mapped_column(Enum(ReviewType, name="review_type"), nullable=False)
    decision: Mapped[ReviewDecisionType] = mapped_column(
        Enum(ReviewDecisionType, name="review_decision_type"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)

    rule_version: Mapped[LegalRuleVersion] = relationship(back_populates="review_decisions")


class RuleSet(Base, UUIDPk, CreatedAtMixin):
    """A versioned, named bundle of PUBLISHED rule versions. A formal
    compliance check must reference a PUBLISHED RuleSet by id — the backend
    resolves its pinned member rule_version_ids itself; callers can never
    assemble an ad-hoc rule list for a real (non-demo) check.

    Members are only mutable while status=DRAFT (enforced in
    RuleSetService, not by a DB trigger) — once PUBLISHED, changing the
    rule mix requires creating a new (code, version_no)."""

    __tablename__ = "rule_set"
    __table_args__ = (
        UniqueConstraint("code", "version_no", name="uq_rule_set_code_version"),
        valid_interval_check("effective_from", "effective_to"),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RuleSetStatus] = mapped_column(
        Enum(RuleSetStatus, name="rule_set_status"), nullable=False, default=RuleSetStatus.DRAFT
    )
    effective_from: Mapped[date | None] = mapped_column()
    effective_to: Mapped[date | None] = mapped_column()

    members: Mapped[list["RuleSetMember"]] = relationship(back_populates="rule_set")


class RuleSetMember(Base, CreatedAtMixin):
    __tablename__ = "rule_set_member"

    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_set.id"), primary_key=True
    )
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule_version.id"), primary_key=True
    )

    rule_set: Mapped[RuleSet] = relationship(back_populates="members")
    rule_version: Mapped[LegalRuleVersion] = relationship()
