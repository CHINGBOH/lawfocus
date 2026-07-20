"""Formal RuleSet/RuleSetMember governance per
06-MVP骨架充实与功能闭环计划.md §5.1.

A RuleSet only becomes usable for a real compliance check once PUBLISHED,
and only ever contains rule versions that are themselves PUBLISHED — a
compliance check can never assemble an ad-hoc rule list at request time.
Once PUBLISHED, a RuleSet's members are immutable (enforced here, not by a
DB trigger): changing the rule mix means creating a new (code, version_no).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LegalRuleVersion, RuleSet, RuleSetMember
from app.models.enums import ReviewStatus, RuleSetStatus


class RuleSetError(Exception):
    pass


class RuleSetNotFoundError(RuleSetError):
    pass


class RuleSetNotEditableError(RuleSetError):
    pass


class MemberNotPublishedError(RuleSetError):
    pass


class RuleSetService:
    def __init__(self, session: Session):
        self.session = session

    def create_draft(
        self, code: str, name: str, effective_from: date, effective_to: date | None = None
    ) -> RuleSet:
        max_version = self.session.execute(
            select(RuleSet.version_no).where(RuleSet.code == code).order_by(RuleSet.version_no.desc()).limit(1)
        ).scalar_one_or_none()
        rule_set = RuleSet(
            code=code,
            version_no=(max_version or 0) + 1,
            name=name,
            status=RuleSetStatus.DRAFT,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        self.session.add(rule_set)
        self.session.flush()
        return rule_set

    def add_member(self, rule_set: RuleSet, rule_version: LegalRuleVersion) -> RuleSetMember:
        if rule_set.status != RuleSetStatus.DRAFT:
            raise RuleSetNotEditableError(f"rule_set {rule_set.id} is {rule_set.status}, not DRAFT")
        if rule_version.status != ReviewStatus.PUBLISHED:
            raise MemberNotPublishedError(
                f"rule_version {rule_version.id} is {rule_version.status}, must be PUBLISHED to join a rule set"
            )
        member = RuleSetMember(rule_set_id=rule_set.id, rule_version_id=rule_version.id)
        self.session.add(member)
        self.session.flush()
        return member

    def publish(self, rule_set: RuleSet) -> RuleSet:
        if rule_set.status != RuleSetStatus.DRAFT:
            raise RuleSetNotEditableError(f"rule_set {rule_set.id} is {rule_set.status}, not DRAFT")
        member_count = self.session.execute(
            select(RuleSetMember).where(RuleSetMember.rule_set_id == rule_set.id)
        ).scalars().all()
        if not member_count:
            raise RuleSetError("cannot publish a rule set with no members")
        rule_set.status = RuleSetStatus.PUBLISHED
        self.session.flush()
        return rule_set

    def get_published_ruleset_at(self, rule_set_id: uuid.UUID, at: date) -> RuleSet:
        rule_set = self.session.get(RuleSet, rule_set_id)
        if rule_set is None:
            raise RuleSetNotFoundError(f"no rule_set {rule_set_id}")
        if rule_set.status != RuleSetStatus.PUBLISHED:
            raise RuleSetNotFoundError(f"rule_set {rule_set_id} is {rule_set.status}, not PUBLISHED")
        if rule_set.effective_from and at < rule_set.effective_from:
            raise RuleSetNotFoundError(f"rule_set {rule_set_id} is not yet effective at {at.isoformat()}")
        if rule_set.effective_to and at >= rule_set.effective_to:
            raise RuleSetNotFoundError(f"rule_set {rule_set_id} is no longer effective at {at.isoformat()}")
        return rule_set

    def member_rule_versions(self, rule_set: RuleSet) -> list[LegalRuleVersion]:
        stmt = (
            select(LegalRuleVersion)
            .join(RuleSetMember, RuleSetMember.rule_version_id == LegalRuleVersion.id)
            .where(RuleSetMember.rule_set_id == rule_set.id)
        )
        return list(self.session.execute(stmt).scalars().all())
