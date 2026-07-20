import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk
from app.models.enums import ComplianceCheckStatus, TruthValueEnum
from app.models.rules import LegalRuleVersion


class ComplianceCheck(Base, UUIDPk, CreatedAtMixin):
    """One execution of rule(s) against one subject at a fixed evaluation
    time. `ruleset_snapshot` freezes the resolved rule_code -> rule_version_id
    pins as a human-readable record regardless of which path created the
    check.

    `rule_set_id` is the load-bearing reference for checks created through
    the formal path (a RuleSet's members are immutable once published) — it
    is nullable ONLY to support the deprecated ad-hoc `rule_codes` request
    path kept for one dev cycle (06-MVP骨架充实与功能闭环计划.md §3.1); a
    legacy check genuinely has no formal RuleSet backing it, and that
    absence is recorded honestly rather than papered over with a synthetic
    RuleSet row. Remove the nullability once the deprecated path is retired.
    """

    __tablename__ = "compliance_check"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_compliance_check_idem"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_subject.id"), nullable=False
    )
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rule_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_set.id"), nullable=True
    )
    ruleset_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ComplianceCheckStatus] = mapped_column(
        Enum(ComplianceCheckStatus, name="compliance_check_status"),
        nullable=False,
        default=ComplianceCheckStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conclusions: Mapped[list["Conclusion"]] = relationship(back_populates="compliance_check")


class Conclusion(Base, UUIDPk, CreatedAtMixin):
    """Conclusion(c) => exists p: Proves(p,c) — every conclusion must have a Proof."""

    __tablename__ = "conclusion"

    compliance_check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_check.id"), nullable=False
    )
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule_version.id"), nullable=False
    )
    result_status: Mapped[TruthValueEnum] = mapped_column(
        Enum(TruthValueEnum, name="truth_value"), nullable=False
    )
    missing_facts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    applicable_reason: Mapped[str | None] = mapped_column(Text)
    excluded_reason: Mapped[str | None] = mapped_column(Text)

    compliance_check: Mapped[ComplianceCheck] = relationship(back_populates="conclusions")
    proof: Mapped["Proof"] = relationship(back_populates="conclusion", uselist=False)
    rule_version: Mapped[LegalRuleVersion] = relationship()


class Proof(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "proof"

    conclusion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conclusion.id"), unique=True, nullable=False
    )
    root_step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    conclusion: Mapped[Conclusion] = relationship(back_populates="proof")
    steps: Mapped[list["ProofStep"]] = relationship(back_populates="proof", order_by="ProofStep.sequence_no")


class ProofStep(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "proof_step"
    __table_args__ = (UniqueConstraint("proof_id", "sequence_no", name="uq_proof_step_sequence"),)

    proof_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proof.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_rule_version.id"), nullable=True
    )
    input_facts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    calculation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    proof: Mapped[Proof] = relationship(back_populates="steps")
    rule_version: Mapped[LegalRuleVersion | None] = relationship()
