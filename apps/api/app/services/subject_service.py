import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.time_interval import ValidInterval, applicable_at
from app.models import LegalSubject, Organization, RoleAssignment, RoleType
from app.models.enums import SubjectType


class SubjectNotFoundError(Exception):
    pass


class SubjectService:
    """Read access to the governance-subject registry (legal_subject /
    organization / role_assignment). This registry is shared reference data,
    not tenant-owned — unlike Fact/Evidence, a `tenant_id` here is used only
    to establish RBAC context, never as a row filter."""

    def __init__(self, session: Session):
        self.session = session

    def list_subjects(
        self,
        *,
        subject_type: SubjectType | None = None,
        listed: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[LegalSubject], int]:
        stmt = select(LegalSubject)
        if subject_type is not None:
            stmt = stmt.where(LegalSubject.subject_type == subject_type)
        if listed is not None:
            stmt = stmt.where(LegalSubject.listed == listed)

        total = len(self.session.execute(stmt).scalars().all())
        stmt = stmt.order_by(LegalSubject.name).offset((page - 1) * page_size).limit(page_size)
        items = list(self.session.execute(stmt).scalars().all())
        return items, total

    def get_subject(self, subject_id: uuid.UUID) -> LegalSubject:
        subject = self.session.get(LegalSubject, subject_id)
        if subject is None:
            raise SubjectNotFoundError(f"no legal_subject {subject_id}")
        return subject

    def get_governance(self, subject_id: uuid.UUID, at: date) -> dict:
        """Returns organizations that actually have a recorded row for this
        company, each with its role assignments annotated with whether they
        are active at `at` — never collapses 'no organization row yet' into
        the same shape as 'organization exists but currently has no active
        members', so the frontend can render '暂无记录' vs an empty roster
        distinctly (06 doc §4.2)."""
        subject = self.get_subject(subject_id)

        org_stmt = (
            select(Organization)
            .where(Organization.company_id == subject_id)
            .order_by(Organization.organization_type)
        )
        organizations = list(self.session.execute(org_stmt).scalars().all())

        result = []
        for org in organizations:
            member_stmt = (
                select(RoleAssignment, RoleType)
                .join(RoleType, RoleAssignment.role_type_id == RoleType.id)
                .where(RoleAssignment.organization_id == org.id)
                .order_by(RoleAssignment.valid_from)
            )
            members = []
            for ra, role_type in self.session.execute(member_stmt).all():
                person = self.session.get(LegalSubject, ra.person_id)
                members.append(
                    {
                        "id": ra.id,
                        "person_id": ra.person_id,
                        "person_name": person.name if person else "(未知主体)",
                        "role_type_code": role_type.code,
                        "role_type_name": role_type.name,
                        "valid_from": ra.valid_from,
                        "valid_to": ra.valid_to,
                        "active_at_query_time": applicable_at(ValidInterval(ra.valid_from, ra.valid_to), at),
                    }
                )
            result.append({"organization": org, "members": members})

        return {"subject": subject, "at": at, "organizations": result}
