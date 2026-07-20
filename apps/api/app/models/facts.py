import uuid
from datetime import date

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk, valid_interval_check


class Fact(Base, UUIDPk, CreatedAtMixin):
    """A timestamped proposition — never a static field. Kept structurally
    separate from Evidence (Supports(Evidence, Fact))."""

    __tablename__ = "fact"
    __table_args__ = (
        Index("idx_fact_tenant_company", "tenant_id", "company_id"),
        valid_interval_check(),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_subject.id"), nullable=False
    )
    fact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    predicate: Mapped[str] = mapped_column(String(80), nullable=False)
    object_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[date] = mapped_column(nullable=False)
    valid_to: Mapped[date | None] = mapped_column(nullable=True)

    evidence_links: Mapped[list["FactEvidence"]] = relationship(back_populates="fact")


class Evidence(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "evidence"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(Text)
    page_no: Mapped[int | None] = mapped_column(Integer)
    quote_text: Mapped[str | None] = mapped_column(Text)
    source_hash: Mapped[str | None] = mapped_column(String(128))
    published_at: Mapped[date | None] = mapped_column()

    fact_links: Mapped[list["FactEvidence"]] = relationship(back_populates="evidence")


class FactEvidence(Base, CreatedAtMixin):
    __tablename__ = "fact_evidence"

    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fact.id"), primary_key=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), primary_key=True
    )
    support_type: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))

    fact: Mapped[Fact] = relationship(back_populates="evidence_links")
    evidence: Mapped[Evidence] = relationship(back_populates="fact_links")
