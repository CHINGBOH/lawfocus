import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk, valid_interval_check
from app.models.enums import SubjectType


class LegalSubject(Base, UUIDPk, CreatedAtMixin):
    """A person or company. Never directly typed as a role — see RoleAssignment."""

    __tablename__ = "legal_subject"

    subject_type: Mapped[SubjectType] = mapped_column(
        Enum(SubjectType, name="subject_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unified_credit_code: Mapped[str | None] = mapped_column(String(50))
    listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exchange: Mapped[str | None] = mapped_column(String(50))

    organizations: Mapped[list["Organization"]] = relationship(back_populates="company")


class Organization(Base, UUIDPk, CreatedAtMixin):
    """A governance organ (Board, AuditCommittee, ...) — always belongs to a
    company: Board(b) => exists c: OrganOf(b,c)."""

    __tablename__ = "organization"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_subject.id"), nullable=False
    )
    organization_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    company: Mapped[LegalSubject] = relationship(back_populates="organizations")


class RoleType(Base, UUIDPk):
    __tablename__ = "role_type"

    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class RoleAssignment(Base, UUIDPk, CreatedAtMixin):
    """A natural person *holding* a role in a company/organ for a validity interval —
    never `Director(person)`; always person -> RoleAssignment -> RoleType."""

    __tablename__ = "role_assignment"
    __table_args__ = (valid_interval_check(),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_subject.id"), nullable=False
    )
    role_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role_type.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_subject.id"), nullable=False
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True
    )
    valid_from: Mapped[date] = mapped_column(nullable=False)
    valid_to: Mapped[date | None] = mapped_column(nullable=True)

    person: Mapped[LegalSubject] = relationship(foreign_keys=[person_id])
    role_type: Mapped[RoleType] = relationship()
    company: Mapped[LegalSubject] = relationship(foreign_keys=[company_id])
    organization: Mapped[Organization | None] = relationship()


class Event(Base, UUIDPk):
    """Event = (Actor, Action, Object, Time, Context, Result) — complex relations
    are promoted to event nodes rather than modeled as plain graph edges."""

    __tablename__ = "event"

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_subject.id"), nullable=True
    )
    object_type: Mapped[str | None] = mapped_column(String(80))
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
