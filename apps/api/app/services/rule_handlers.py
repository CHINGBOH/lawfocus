"""Handlers for the 10 P0 rules in 02-上市公司治理MVP十条规则清单.md.

Two data sources are used deliberately for different rules, matching the
Fact/Evidence-vs-formal-role-registry separation in the meta-model:

- `Organization` / `RoleAssignment` are treated as an authoritative, curated
  governance registry (like `Article`/`LegalVersion` — authoritative once
  entered), so their absence is a genuine FALSE, not UNKNOWN. This is what
  existence/composition/convenor/appointment-validity rules read.
- `Fact` (+ its `FactEvidence` links) is the evidentiary layer for
  propositions not yet formalized into that registry — this is where
  UNKNOWN (no fact recorded) and CONFLICT (contradictory unretracted facts)
  genuinely arise. Director-count/ratio rules read from here on purpose, so
  the demo data's conflicting company-B facts actually exercise CONFLICT.

Every handler returns a real RuleResult computed from the DB — none of this
is hardcoded per company; swap the seed data and results change accordingly.

Parameterization (07-剩余工作执行与验收指南.md R1): handlers contain comparison
*algorithms* only. Concrete legal thresholds (独立董事 2 人、1/3 比例、审计委员会
3 人、过半数) are read from the executed rule version's `requirement_expression`
via the immutable `RuleExecutionContext`; a missing/illegal expression raises
`InvalidRequirementExpressionError` — there is no fallback to a code default.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rule_requirement import (
    RuleExecutionContext,
    parse_ratio,
    parse_threshold,
)
from app.domain.rule_result import ProofStepData, RuleResult
from app.domain.time_interval import ValidInterval, applicable_at
from app.domain.truth import TruthValue
from app.models import Fact, LegalSubject, Organization, RoleAssignment, RoleType
from app.models.enums import SubjectType

_NOT_LISTED_REASON = "主体不是上市公司，本规则不适用"


def _not_applicable_if_not_listed(rule_code: str, company: LegalSubject) -> RuleResult | None:
    if company.subject_type != SubjectType.LISTED_COMPANY or not company.listed:
        return RuleResult(
            rule_code=rule_code,
            status=TruthValue.NOT_APPLICABLE,
            excluded_reason=_NOT_LISTED_REASON,
            proof_steps=[
                ProofStepData(
                    step_type="SCOPE_CHECK",
                    calculation={"listed": company.listed, "subject_type": str(company.subject_type)},
                )
            ],
        )
    return None


def _active_role_assignments(
    session: Session, company_id, role_type_code: str, at: datetime, organization_id=None
) -> list[RoleAssignment]:
    stmt = (
        select(RoleAssignment)
        .join(RoleType, RoleAssignment.role_type_id == RoleType.id)
        .where(RoleAssignment.company_id == company_id, RoleType.code == role_type_code)
    )
    if organization_id is not None:
        stmt = stmt.where(RoleAssignment.organization_id == organization_id)
    candidates = session.execute(stmt).scalars().all()
    at_date = at.date() if isinstance(at, datetime) else at
    return [
        ra
        for ra in candidates
        if applicable_at(ValidInterval(ra.valid_from, ra.valid_to), at_date)
    ]


def _get_organization(session: Session, company_id, organization_type: str) -> Organization | None:
    stmt = select(Organization).where(
        Organization.company_id == company_id, Organization.organization_type == organization_type
    )
    return session.execute(stmt).scalar_one_or_none()


def evaluate_gov_org_001(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-ORG-001: 上市公司董事会存在性。"""
    guard = _not_applicable_if_not_listed("GOV-ORG-001", company)
    if guard:
        return guard

    board = _get_organization(session, company.id, "BOARD")
    status = TruthValue.TRUE if board is not None else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-ORG-001",
        status=status,
        applicable_reason="上市公司必须设置董事会",
        variable_bindings={"board_exists": board is not None},
        proof_steps=[
            ProofStepData(
                step_type="ORGAN_LOOKUP",
                calculation={"organization_type": "BOARD", "found": board is not None},
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_aud_001(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-AUD-001: 审计委员会设置。"""
    guard = _not_applicable_if_not_listed("GOV-AUD-001", company)
    if guard:
        return guard

    committee = _get_organization(session, company.id, "AUDIT_COMMITTEE")
    status = TruthValue.TRUE if committee is not None else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-AUD-001",
        status=status,
        applicable_reason="上市公司必须设置审计委员会",
        variable_bindings={"audit_committee_exists": committee is not None},
        proof_steps=[
            ProofStepData(
                step_type="ORGAN_LOOKUP",
                calculation={"organization_type": "AUDIT_COMMITTEE", "found": committee is not None},
                output_state={"status": status.value},
            )
        ],
    )


def _latest_board_composition_facts(session: Session, company_id, at: datetime) -> list[Fact]:
    at_date = at.date() if isinstance(at, datetime) else at
    stmt = select(Fact).where(
        Fact.company_id == company_id,
        Fact.fact_type == "BOARD_COMPOSITION",
        Fact.predicate == "independent_director_count",
        Fact.valid_from <= at_date,
    ).where((Fact.valid_to.is_(None)) | (Fact.valid_to > at_date))
    return list(session.execute(stmt).scalars().all())


def _board_composition_result(rule_code: str, facts: list[Fact]) -> RuleResult | None:
    """Shared UNKNOWN/CONFLICT handling for the two count/ratio rules that
    both read the same BOARD_COMPOSITION facts. Returns None (meaning: "here
    is exactly one usable fact, proceed with the rule-specific comparison")
    when there's a single, unambiguous fact to work with.
    """
    if not facts:
        return RuleResult(
            rule_code=rule_code,
            status=TruthValue.UNKNOWN,
            missing_facts=["BOARD_COMPOSITION.independent_director_count"],
            proof_steps=[ProofStepData(step_type="FACT_LOOKUP", calculation={"facts_found": 0})],
        )

    distinct_values = {(f.object_value.get("total"), f.object_value.get("independent")) for f in facts}
    if len(distinct_values) > 1:
        return RuleResult(
            rule_code=rule_code,
            status=TruthValue.CONFLICT,
            variable_bindings={"conflicting_values": [list(v) for v in distinct_values]},
            proof_steps=[
                ProofStepData(
                    step_type="FACT_CONFLICT",
                    calculation={"fact_ids": [str(f.id) for f in facts], "values": list(distinct_values)},
                )
            ],
        )
    return None


def evaluate_gov_id_001(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-ID-001: 独立董事最低人数（阈值来自规则版本，如不少于二人）。"""
    guard = _not_applicable_if_not_listed("GOV-ID-001", company)
    if guard:
        return guard

    req = parse_threshold(ctx.requirement_expression, rule_code="GOV-ID-001")

    facts = _latest_board_composition_facts(session, company.id, ctx.evaluation_time)
    shared = _board_composition_result("GOV-ID-001", facts)
    if shared:
        return shared

    independent = facts[0].object_value["independent"]
    status = TruthValue.TRUE if req.holds(independent) else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-ID-001",
        status=status,
        applicable_reason="独立董事人数不得低于规则版本规定的最低人数",
        variable_bindings={"independent_director_count": independent, "threshold": req.value},
        proof_steps=[
            ProofStepData(
                step_type="THRESHOLD_COMPARISON",
                calculation={
                    "fact_id": str(facts[0].id),
                    "independent": independent,
                    "threshold": req.value,
                    "op": ">=",
                    "requirement": dict(ctx.requirement_expression),
                },
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_id_002(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-ID-002: 独立董事最低比例（比例来自规则版本，整数交叉相乘避免浮点误差）。"""
    guard = _not_applicable_if_not_listed("GOV-ID-002", company)
    if guard:
        return guard

    req = parse_ratio(ctx.requirement_expression, rule_code="GOV-ID-002")

    facts = _latest_board_composition_facts(session, company.id, ctx.evaluation_time)
    shared = _board_composition_result("GOV-ID-002", facts)
    if shared:
        return shared

    independent = facts[0].object_value["independent"]
    total = facts[0].object_value["total"]
    holds, lhs, rhs = req.evaluate(independent, total)
    status = TruthValue.TRUE if holds else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-ID-002",
        status=status,
        applicable_reason="独立董事比例不得低于规则版本规定的最低比例",
        variable_bindings={"independent": independent, "total": total},
        proof_steps=[
            ProofStepData(
                step_type="RATIO_CROSS_MULTIPLY",
                calculation={
                    "fact_id": str(facts[0].id),
                    "independent": independent,
                    "total": total,
                    "lhs": lhs,
                    "rhs": rhs,
                    "requirement": dict(ctx.requirement_expression),
                },
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_aud_002(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-AUD-002: 审计委员会成员构成（阈值来自规则版本，如不少于三人）。"""
    guard = _not_applicable_if_not_listed("GOV-AUD-002", company)
    if guard:
        return guard

    req = parse_threshold(ctx.requirement_expression, rule_code="GOV-AUD-002")

    committee = _get_organization(session, company.id, "AUDIT_COMMITTEE")
    if committee is None:
        return RuleResult(
            rule_code="GOV-AUD-002",
            status=TruthValue.NOT_APPLICABLE,
            excluded_reason="公司未设置审计委员会，成员构成规则不适用",
            proof_steps=[ProofStepData(step_type="ORGAN_LOOKUP", calculation={"found": False})],
        )

    members = _active_role_assignments(
        session, company.id, "AUDIT_COMMITTEE_MEMBER", ctx.evaluation_time, committee.id
    )
    status = TruthValue.TRUE if req.holds(len(members)) else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-AUD-002",
        status=status,
        applicable_reason="审计委员会成员人数不得低于规则版本规定的最低人数",
        variable_bindings={"member_count": len(members), "threshold": req.value},
        proof_steps=[
            ProofStepData(
                step_type="THRESHOLD_COMPARISON",
                calculation={
                    "member_count": len(members),
                    "threshold": req.value,
                    "op": ">=",
                    "requirement": dict(ctx.requirement_expression),
                },
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_aud_003(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-AUD-003: 审计委员会独立董事占比（比例来自规则版本，如过半数）。"""
    guard = _not_applicable_if_not_listed("GOV-AUD-003", company)
    if guard:
        return guard

    req = parse_ratio(ctx.requirement_expression, rule_code="GOV-AUD-003")

    committee = _get_organization(session, company.id, "AUDIT_COMMITTEE")
    if committee is None:
        return RuleResult(
            rule_code="GOV-AUD-003",
            status=TruthValue.NOT_APPLICABLE,
            excluded_reason="公司未设置审计委员会，独立董事占比规则不适用",
            proof_steps=[ProofStepData(step_type="ORGAN_LOOKUP", calculation={"found": False})],
        )

    members = _active_role_assignments(
        session, company.id, "AUDIT_COMMITTEE_MEMBER", ctx.evaluation_time, committee.id
    )
    independent_directors = {
        ra.person_id
        for ra in _active_role_assignments(session, company.id, "INDEPENDENT_DIRECTOR", ctx.evaluation_time)
    }
    independent_members = [m for m in members if m.person_id in independent_directors]
    total = len(members)
    independent_count = len(independent_members)
    holds, lhs, rhs = req.evaluate(independent_count, total)
    status = TruthValue.TRUE if holds else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-AUD-003",
        status=status,
        applicable_reason="审计委员会中独立董事占比必须满足规则版本规定的比例",
        variable_bindings={"independent_count": independent_count, "total": total},
        proof_steps=[
            ProofStepData(
                step_type="RATIO_CROSS_MULTIPLY",
                calculation={
                    "independent_count": independent_count,
                    "total": total,
                    "lhs": lhs,
                    "rhs": rhs,
                    "requirement": dict(ctx.requirement_expression),
                },
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_aud_004(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-AUD-004: 审计委员会召集人资格（须为独立董事）。"""
    guard = _not_applicable_if_not_listed("GOV-AUD-004", company)
    if guard:
        return guard

    committee = _get_organization(session, company.id, "AUDIT_COMMITTEE")
    if committee is None:
        return RuleResult(
            rule_code="GOV-AUD-004",
            status=TruthValue.NOT_APPLICABLE,
            excluded_reason="公司未设置审计委员会，召集人资格规则不适用",
            proof_steps=[ProofStepData(step_type="ORGAN_LOOKUP", calculation={"found": False})],
        )

    convenors = _active_role_assignments(
        session, company.id, "AUDIT_COMMITTEE_CONVENOR", ctx.evaluation_time, committee.id
    )
    if not convenors:
        return RuleResult(
            rule_code="GOV-AUD-004",
            status=TruthValue.UNKNOWN,
            missing_facts=["RoleAssignment(AUDIT_COMMITTEE_CONVENOR)"],
            proof_steps=[ProofStepData(step_type="ROLE_LOOKUP", calculation={"convenors_found": 0})],
        )

    independent_directors = {
        ra.person_id
        for ra in _active_role_assignments(session, company.id, "INDEPENDENT_DIRECTOR", ctx.evaluation_time)
    }
    convenor = convenors[0]
    is_independent = convenor.person_id in independent_directors
    status = TruthValue.TRUE if is_independent else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-AUD-004",
        status=status,
        applicable_reason="审计委员会召集人应当由独立董事担任",
        variable_bindings={"convenor_person_id": str(convenor.person_id), "is_independent_director": is_independent},
        proof_steps=[
            ProofStepData(
                step_type="ROLE_CROSS_CHECK",
                calculation={"convenor_person_id": str(convenor.person_id), "is_independent": is_independent},
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_role_001(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-ROLE-001: 董事任职有效性 — every DIRECTOR/INDEPENDENT_DIRECTOR
    role assignment for the company must be valid (interval covers `at`)."""
    at = ctx.evaluation_time
    at_date = at.date() if isinstance(at, datetime) else at
    stmt = (
        select(RoleAssignment)
        .join(RoleType, RoleAssignment.role_type_id == RoleType.id)
        .where(
            RoleAssignment.company_id == company.id,
            RoleType.code.in_(["DIRECTOR", "INDEPENDENT_DIRECTOR"]),
        )
    )
    assignments = session.execute(stmt).scalars().all()
    if not assignments:
        return RuleResult(
            rule_code="GOV-ROLE-001",
            status=TruthValue.UNKNOWN,
            missing_facts=["RoleAssignment(DIRECTOR|INDEPENDENT_DIRECTOR)"],
            proof_steps=[ProofStepData(step_type="ROLE_LOOKUP", calculation={"assignments_found": 0})],
        )

    expired = [
        ra for ra in assignments if not applicable_at(ValidInterval(ra.valid_from, ra.valid_to), at_date)
    ]
    status = TruthValue.FALSE if expired else TruthValue.TRUE
    return RuleResult(
        rule_code="GOV-ROLE-001",
        status=status,
        applicable_reason="董事任职必须在评价时点有效",
        variable_bindings={"total_assignments": len(assignments), "expired_count": len(expired)},
        proof_steps=[
            ProofStepData(
                step_type="INTERVAL_CHECK",
                calculation={"evaluated_at": at_date.isoformat(), "expired_ids": [str(ra.id) for ra in expired]},
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_time_001(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-TIME-001: 任职评价时点有效性 — the general [valid_from,valid_to)
    applicability primitive, evaluated here over the company's own role
    assignments (shared logic with GOV-ROLE-001, framed as a standalone
    time-applicability check per the rules list)."""
    at = ctx.evaluation_time
    at_date = at.date() if isinstance(at, datetime) else at
    stmt = select(RoleAssignment).where(RoleAssignment.company_id == company.id)
    assignments = session.execute(stmt).scalars().all()
    if not assignments:
        return RuleResult(
            rule_code="GOV-TIME-001",
            status=TruthValue.UNKNOWN,
            missing_facts=["RoleAssignment(*)"],
            proof_steps=[ProofStepData(step_type="ROLE_LOOKUP", calculation={"assignments_found": 0})],
        )

    applicable_count = sum(
        1 for ra in assignments if applicable_at(ValidInterval(ra.valid_from, ra.valid_to), at_date)
    )
    status = TruthValue.TRUE if applicable_count > 0 else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-TIME-001",
        status=status,
        applicable_reason="至少一项任职在评价时点处于有效区间内",
        variable_bindings={"total": len(assignments), "applicable_at_evaluation_time": applicable_count},
        proof_steps=[
            ProofStepData(
                step_type="INTERVAL_CHECK",
                calculation={"evaluated_at": at_date.isoformat(), "applicable_count": applicable_count},
                output_state={"status": status.value},
            )
        ],
    )


def evaluate_gov_ctrl_001(session: Session, ctx: RuleExecutionContext, company: LegalSubject) -> RuleResult:
    """GOV-CTRL-001: 控股股东/实际控制人关系认定 — reads a CONTROL_RELATIONSHIP
    Fact; genuinely UNKNOWN when none has been entered (none is seeded by
    default), never guessed from indirect signals."""
    at = ctx.evaluation_time
    at_date = at.date() if isinstance(at, datetime) else at
    stmt = select(Fact).where(
        Fact.company_id == company.id,
        Fact.fact_type == "CONTROL_RELATIONSHIP",
        Fact.valid_from <= at_date,
    ).where((Fact.valid_to.is_(None)) | (Fact.valid_to > at_date))
    facts = list(session.execute(stmt).scalars().all())
    if not facts:
        return RuleResult(
            rule_code="GOV-CTRL-001",
            status=TruthValue.UNKNOWN,
            missing_facts=["CONTROL_RELATIONSHIP"],
            proof_steps=[ProofStepData(step_type="FACT_LOOKUP", calculation={"facts_found": 0})],
        )

    distinct = {f.object_value.get("controls") for f in facts}
    if len(distinct) > 1:
        return RuleResult(
            rule_code="GOV-CTRL-001",
            status=TruthValue.CONFLICT,
            variable_bindings={"conflicting_values": list(distinct)},
            proof_steps=[
                ProofStepData(
                    step_type="FACT_CONFLICT",
                    calculation={"fact_ids": [str(f.id) for f in facts], "values": list(distinct)},
                )
            ],
        )

    controls = facts[0].object_value.get("controls", False)
    status = TruthValue.TRUE if controls else TruthValue.FALSE
    return RuleResult(
        rule_code="GOV-CTRL-001",
        status=status,
        variable_bindings={"controls": controls},
        proof_steps=[
            ProofStepData(step_type="FACT_LOOKUP", calculation={"fact_id": str(facts[0].id), "controls": controls})
        ],
    )


RuleHandler = Callable[[Session, RuleExecutionContext, LegalSubject], RuleResult]

RULE_REGISTRY: dict[str, RuleHandler] = {
    "GOV-ORG-001": evaluate_gov_org_001,
    "GOV-AUD-001": evaluate_gov_aud_001,
    "GOV-ID-001": evaluate_gov_id_001,
    "GOV-ID-002": evaluate_gov_id_002,
    "GOV-AUD-002": evaluate_gov_aud_002,
    "GOV-AUD-003": evaluate_gov_aud_003,
    "GOV-AUD-004": evaluate_gov_aud_004,
    "GOV-ROLE-001": evaluate_gov_role_001,
    "GOV-TIME-001": evaluate_gov_time_001,
    "GOV-CTRL-001": evaluate_gov_ctrl_001,
}
