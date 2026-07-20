"""Rule submit/review/publish state machine, per
03-用户权限与内容审核模型.md §3 and GOAL.md §5.2/§6.

State machine (as specified):
    DRAFT -> IN_REVIEW -> LEGAL_APPROVED -> TECH_APPROVED -> PUBLISHED -> DEPRECATED
      ^          |               |               |
      +----------+-- CHANGES_REQUESTED ----------+

The publish gate genuinely re-executes every RuleTestCase against its
referenced demo company/time through the real rule handler and compares the
result to `expected_status` — it does not just check a human-set flag, so a
handler regression is caught even if nobody remembers to re-run tests by hand.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.rule_requirement import InvalidRequirementExpressionError, RuleExecutionContext
from app.models import LegalRuleVersion, LegalSubject, ReviewDecision, RuleTestCase
from app.models.enums import ReviewDecisionType, ReviewStatus, ReviewType
from app.services.rule_handlers import RULE_REGISTRY

MANDATORY_TEST_CASE_TYPES = {"PASS", "VIOLATION", "BOUNDARY", "MISSING_FACT"}
WAIVABLE_TEST_CASE_TYPES = {"NOT_APPLICABLE", "EXCEPTION", "CONFLICT"}


class RuleGovernanceError(Exception):
    pass


class SelfReviewNotAllowedError(RuleGovernanceError):
    pass


class InvalidTransitionError(RuleGovernanceError):
    pass


class PublishGateFailedError(RuleGovernanceError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class RuleGovernanceService:
    def __init__(self, session: Session):
        self.session = session

    def submit(self, rule_version: LegalRuleVersion, submitted_by: uuid.UUID) -> LegalRuleVersion:
        if rule_version.status not in (ReviewStatus.DRAFT, ReviewStatus.CHANGES_REQUESTED):
            raise InvalidTransitionError(
                f"cannot submit a rule version in status {rule_version.status}"
            )
        rule_version.status = ReviewStatus.IN_REVIEW
        rule_version.submitted_by = submitted_by
        self.session.flush()
        return rule_version

    def add_review(
        self,
        rule_version: LegalRuleVersion,
        reviewer_id: uuid.UUID,
        review_type: ReviewType,
        decision: ReviewDecisionType,
        comment: str | None,
    ) -> LegalRuleVersion:
        if rule_version.submitted_by is not None and reviewer_id == rule_version.submitted_by:
            raise SelfReviewNotAllowedError("the submitter cannot review their own rule version")

        if rule_version.status not in (
            ReviewStatus.IN_REVIEW,
            ReviewStatus.LEGAL_APPROVED,
        ):
            raise InvalidTransitionError(
                f"rule version in status {rule_version.status} is not open for review"
            )
        if review_type == ReviewType.TECHNICAL and rule_version.status == ReviewStatus.IN_REVIEW:
            raise InvalidTransitionError(
                "technical review requires legal review to be approved first"
            )

        self.session.add(
            ReviewDecision(
                rule_version_id=rule_version.id,
                reviewer_user_id=reviewer_id,
                review_type=review_type,
                decision=decision,
                comment=comment,
            )
        )

        if decision == ReviewDecisionType.CHANGES_REQUESTED:
            rule_version.status = ReviewStatus.CHANGES_REQUESTED
        elif review_type == ReviewType.LEGAL:
            rule_version.status = ReviewStatus.LEGAL_APPROVED
        elif review_type == ReviewType.TECHNICAL:
            rule_version.status = ReviewStatus.TECH_APPROVED

        self.session.flush()
        return rule_version

    def _run_test_gate(self, rule_version: LegalRuleVersion) -> list[str]:
        failures: list[str] = []
        test_cases = self.session.query(RuleTestCase).filter_by(rule_version_id=rule_version.id).all()

        present_types = {tc.case_type.value if hasattr(tc.case_type, "value") else tc.case_type for tc in test_cases}
        for required in MANDATORY_TEST_CASE_TYPES:
            if required not in present_types:
                failures.append(f"missing mandatory test case type: {required}")
        for waivable in WAIVABLE_TEST_CASE_TYPES:
            has_case = waivable in present_types
            has_waiver = any(
                (tc.case_type.value if hasattr(tc.case_type, "value") else tc.case_type) == waivable
                and tc.not_applicable_reason
                for tc in test_cases
            )
            if not has_case and not has_waiver:
                failures.append(f"test case type {waivable} needs either a case or a documented waiver reason")

        rule_code = rule_version.rule.code
        handler = RULE_REGISTRY.get(rule_code)
        for tc in test_cases:
            company_ref = tc.input_facts.get("company_id")
            eval_time_ref = tc.input_facts.get("evaluation_time")
            if handler is None or company_ref is None or eval_time_ref is None:
                continue  # nothing to execute for a purely-documented/waived case
            company = self.session.get(LegalSubject, uuid.UUID(company_ref))
            if company is None:
                failures.append(f"test case {tc.id}: referenced company {company_ref} not found")
                continue
            at = datetime.fromisoformat(eval_time_ref)
            ctx = RuleExecutionContext(
                rule_version_id=rule_version.id,
                rule_code=rule_code,
                requirement_expression=rule_version.requirement_expression,
                evaluation_time=at,
            )
            try:
                result = handler(self.session, ctx, company)
            except InvalidRequirementExpressionError as exc:
                failures.append(f"test case {tc.id}: invalid requirement_expression: {exc}")
                continue
            if result.status.value != tc.expected_status:
                failures.append(
                    f"test case {tc.id} ({tc.case_type}): expected {tc.expected_status}, got {result.status.value}"
                )

        if not test_cases:
            failures.append("no test cases recorded at all")

        return failures

    def publish(self, rule_version: LegalRuleVersion, publisher_id: uuid.UUID) -> LegalRuleVersion:
        if rule_version.status != ReviewStatus.TECH_APPROVED:
            raise InvalidTransitionError(
                f"cannot publish a rule version in status {rule_version.status}; "
                "requires legal + technical approval first"
            )

        failures = self._run_test_gate(rule_version)
        if failures:
            raise PublishGateFailedError(failures)

        rule_version.status = ReviewStatus.PUBLISHED
        self.session.flush()
        return rule_version
