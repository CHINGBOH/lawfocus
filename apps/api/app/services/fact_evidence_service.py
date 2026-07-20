import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Evidence, Fact, FactEvidence


class FactNotFoundError(Exception):
    pass


class EvidenceNotFoundError(Exception):
    pass


class FactEvidenceService:
    """Facts and evidence are written through separate calls and only linked
    explicitly afterwards — Supports(Evidence, Fact) is a relation, not a
    merge of the two records into one row."""

    def __init__(self, session: Session):
        self.session = session

    def create_fact(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        fact_type: str,
        predicate: str,
        object_value: dict,
        valid_from: date,
        valid_to: date | None,
        subject_ref: uuid.UUID | None = None,
    ) -> Fact:
        fact = Fact(
            tenant_id=tenant_id,
            company_id=company_id,
            fact_type=fact_type,
            predicate=predicate,
            object_value=object_value,
            valid_from=valid_from,
            valid_to=valid_to,
            subject_ref=subject_ref,
        )
        self.session.add(fact)
        self.session.flush()
        return fact

    def create_evidence(
        self,
        *,
        tenant_id: uuid.UUID,
        evidence_type: str,
        title: str,
        source_url: str | None = None,
        source_file: str | None = None,
        page_no: int | None = None,
        quote_text: str | None = None,
        published_at: date | None = None,
    ) -> Evidence:
        evidence = Evidence(
            tenant_id=tenant_id,
            evidence_type=evidence_type,
            title=title,
            source_url=source_url,
            source_file=source_file,
            page_no=page_no,
            quote_text=quote_text,
            published_at=published_at,
        )
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def link_fact_to_evidence(
        self,
        *,
        fact_id: uuid.UUID,
        evidence_id: uuid.UUID,
        support_type: str = "DIRECT",
        confidence: float | None = None,
    ) -> FactEvidence:
        link = FactEvidence(
            fact_id=fact_id, evidence_id=evidence_id, support_type=support_type, confidence=confidence
        )
        self.session.add(link)
        self.session.flush()
        return link

    def list_facts(
        self,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID | None = None,
        at: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Fact], int]:
        stmt = select(Fact).where(Fact.tenant_id == tenant_id)
        if subject_id is not None:
            stmt = stmt.where(Fact.company_id == subject_id)
        if at is not None:
            stmt = stmt.where(Fact.valid_from <= at).where(
                (Fact.valid_to.is_(None)) | (Fact.valid_to > at)
            )

        total = len(self.session.execute(stmt).scalars().all())
        stmt = stmt.order_by(Fact.valid_from.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.session.execute(stmt).scalars().all())
        return items, total

    def get_fact(self, fact_id: uuid.UUID) -> Fact:
        fact = self.session.get(Fact, fact_id)
        if fact is None:
            raise FactNotFoundError(f"no fact {fact_id}")
        return fact

    def list_evidence(
        self,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID | None = None,
        fact_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Evidence], int]:
        stmt = select(Evidence).where(Evidence.tenant_id == tenant_id)
        if fact_id is not None:
            stmt = stmt.join(FactEvidence, FactEvidence.evidence_id == Evidence.id).where(
                FactEvidence.fact_id == fact_id
            )
        elif subject_id is not None:
            stmt = (
                stmt.join(FactEvidence, FactEvidence.evidence_id == Evidence.id)
                .join(Fact, Fact.id == FactEvidence.fact_id)
                .where(Fact.company_id == subject_id)
            )

        total = len(self.session.execute(stmt).scalars().all())
        stmt = stmt.order_by(Evidence.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.session.execute(stmt).scalars().all())
        return items, total

    def get_evidence(self, evidence_id: uuid.UUID) -> Evidence:
        evidence = self.session.get(Evidence, evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(f"no evidence {evidence_id}")
        return evidence
