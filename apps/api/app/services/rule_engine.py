import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rule_requirement import RuleExecutionContext
from app.models import (
    ComplianceCheck,
    Conclusion,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    Proof,
    ProofStep,
)
from app.models.enums import ComplianceCheckStatus, TruthValueEnum
from app.services.rule_handlers import RULE_REGISTRY
from app.services.rule_set_service import RuleSetService


@dataclass(frozen=True)
class RulePreview:
    """One rule's result if the check were run right now — no ComplianceCheck,
    Conclusion, Proof, or ProofStep rows are created; nothing is persisted."""

    rule_code: str
    rule_name: str
    status: str
    missing_facts: list
    applicable_reason: str | None
    excluded_reason: str | None


class UnknownRuleCodeError(Exception):
    pass


class RuleVersionNotRegisteredError(Exception):
    pass


class SubjectNotFoundError(Exception):
    pass


class RuleEngine:
    """Executes rule versions and persists the full result -> proof chain
    (Conclusion -> Proof -> ProofStep), matching §11 of the DB design doc's
    execution pipeline.

    `run_compliance_check` is the formal path (06-MVP骨架充实与功能闭环计划.md
    §3.1): the rule set to run is resolved server-side from `rule_set_id` —
    the caller never supplies an ad-hoc rule-code list. `run_compliance_check_legacy`
    is the deprecated pre-F0 path, kept for one dev cycle: it looks up each
    code's *latest* version regardless of publish status, which is why it
    still works against DRAFT demo/test rules.
    """

    def __init__(self, session: Session):
        self.session = session

    def _find_existing(self, tenant_id: uuid.UUID, idempotency_key: str) -> ComplianceCheck | None:
        return self.session.execute(
            select(ComplianceCheck).where(
                ComplianceCheck.tenant_id == tenant_id,
                ComplianceCheck.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()

    def _get_company(self, company_id: uuid.UUID) -> LegalSubject:
        company = self.session.get(LegalSubject, company_id)
        if company is None:
            raise SubjectNotFoundError(f"no LegalSubject {company_id}")
        return company

    def _persist(
        self,
        check: ComplianceCheck,
        rule_versions: list[LegalRuleVersion],
        company: LegalSubject,
        evaluation_time: datetime,
    ) -> None:
        for rule_version in rule_versions:
            handler = RULE_REGISTRY[rule_version.rule.code]
            ctx = RuleExecutionContext(
                rule_version_id=rule_version.id,
                rule_code=rule_version.rule.code,
                requirement_expression=rule_version.requirement_expression,
                evaluation_time=evaluation_time,
            )
            result = handler(self.session, ctx, company)

            conclusion = Conclusion(
                compliance_check_id=check.id,
                rule_version_id=rule_version.id,
                result_status=TruthValueEnum(result.status.value),
                missing_facts=result.missing_facts,
                applicable_reason=result.applicable_reason,
                excluded_reason=result.excluded_reason,
            )
            self.session.add(conclusion)
            self.session.flush()

            proof = Proof(conclusion_id=conclusion.id)
            self.session.add(proof)
            self.session.flush()

            root_step_id = None
            for seq, step in enumerate(result.proof_steps, start=1):
                proof_step = ProofStep(
                    proof_id=proof.id,
                    sequence_no=seq,
                    step_type=step.step_type,
                    rule_version_id=rule_version.id,
                    input_facts=step.input_facts,
                    calculation=step.calculation,
                    output_state=step.output_state,
                )
                self.session.add(proof_step)
                self.session.flush()
                if seq == 1:
                    root_step_id = proof_step.id
            proof.root_step_id = root_step_id

        check.status = ComplianceCheckStatus.COMPLETED
        check.completed_at = datetime.now(evaluation_time.tzinfo)
        self.session.flush()

    def run_compliance_check(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        evaluation_time: datetime,
        rule_set_id: uuid.UUID,
        idempotency_key: str,
        requested_by: uuid.UUID | None,
    ) -> ComplianceCheck:
        existing = self._find_existing(tenant_id, idempotency_key)
        if existing is not None:
            return existing

        company = self._get_company(company_id)

        rule_set_service = RuleSetService(self.session)
        rule_set = rule_set_service.get_published_ruleset_at(rule_set_id, evaluation_time.date())
        rule_versions = rule_set_service.member_rule_versions(rule_set)

        for rule_version in rule_versions:
            if rule_version.rule.code not in RULE_REGISTRY:
                raise UnknownRuleCodeError(rule_version.rule.code)

        check = ComplianceCheck(
            tenant_id=tenant_id,
            company_id=company_id,
            evaluation_time=evaluation_time,
            rule_set_id=rule_set.id,
            ruleset_snapshot=[
                {"rule_code": rv.rule.code, "rule_version_id": str(rv.id)} for rv in rule_versions
            ],
            status=ComplianceCheckStatus.PENDING,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
        )
        self.session.add(check)
        self.session.flush()

        self._persist(check, rule_versions, company, evaluation_time)
        return check

    def preview_compliance_check(
        self,
        *,
        company_id: uuid.UUID,
        evaluation_time: datetime,
        rule_set_id: uuid.UUID,
    ) -> list[RulePreview]:
        """Dry run: same rule resolution and execution as `run_compliance_check`,
        but no ComplianceCheck/Conclusion/Proof/ProofStep row is created and
        nothing is committed — lets the wizard show which rules would be
        UNKNOWN and what facts are missing before the user commits to a real,
        audited check (06号文档§4.4 step 4 / 11号文档 E5)."""
        company = self._get_company(company_id)

        rule_set_service = RuleSetService(self.session)
        rule_set = rule_set_service.get_published_ruleset_at(rule_set_id, evaluation_time.date())
        rule_versions = rule_set_service.member_rule_versions(rule_set)

        for rule_version in rule_versions:
            if rule_version.rule.code not in RULE_REGISTRY:
                raise UnknownRuleCodeError(rule_version.rule.code)

        previews = []
        for rule_version in rule_versions:
            handler = RULE_REGISTRY[rule_version.rule.code]
            ctx = RuleExecutionContext(
                rule_version_id=rule_version.id,
                rule_code=rule_version.rule.code,
                requirement_expression=rule_version.requirement_expression,
                evaluation_time=evaluation_time,
            )
            result = handler(self.session, ctx, company)
            previews.append(RulePreview(
                rule_code=rule_version.rule.code,
                rule_name=rule_version.rule.name,
                status=result.status.value,
                missing_facts=result.missing_facts,
                applicable_reason=result.applicable_reason,
                excluded_reason=result.excluded_reason,
            ))
        return previews

    def run_compliance_check_legacy(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        evaluation_time: datetime,
        rule_codes: list[str],
        idempotency_key: str,
        requested_by: uuid.UUID | None,
    ) -> ComplianceCheck:
        """Deprecated: pre-F0 ad-hoc rule-code list, no RuleSet involved.
        Kept for one dev cycle per 06-MVP骨架充实与功能闭环计划.md §3.1.
        """
        existing = self._find_existing(tenant_id, idempotency_key)
        if existing is not None:
            return existing

        company = self._get_company(company_id)

        for code in rule_codes:
            if code not in RULE_REGISTRY:
                raise UnknownRuleCodeError(code)

        rule_versions = [self._latest_rule_version(code) for code in rule_codes]

        check = ComplianceCheck(
            tenant_id=tenant_id,
            company_id=company_id,
            evaluation_time=evaluation_time,
            rule_set_id=None,
            ruleset_snapshot=[
                {"rule_code": rv.rule.code, "rule_version_id": str(rv.id)} for rv in rule_versions
            ],
            status=ComplianceCheckStatus.PENDING,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
        )
        self.session.add(check)
        self.session.flush()

        self._persist(check, rule_versions, company, evaluation_time)
        return check

    def _latest_rule_version(self, rule_code: str) -> LegalRuleVersion:
        stmt = (
            select(LegalRuleVersion)
            .join(LegalRule, LegalRuleVersion.rule_id == LegalRule.id)
            .where(LegalRule.code == rule_code)
            .order_by(LegalRuleVersion.version_no.desc())
            .limit(1)
        )
        version = self.session.execute(stmt).scalar_one_or_none()
        if version is None:
            raise RuleVersionNotRegisteredError(f"no LegalRuleVersion registered for {rule_code}")
        return version
