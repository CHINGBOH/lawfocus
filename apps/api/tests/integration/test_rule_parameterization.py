"""R1: rule handlers take business parameters from the executed rule version.

Covers 07 指南 R1 §3.4:
- the same handler bound to different rule-version params yields different results;
- missing/illegal params refuse execution with a stable error (API 422 +
  publish-gate failure), never a fallback to code defaults;
- check history keeps referencing the rule version used at execution time.
"""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.domain.rule_requirement import RuleExecutionContext
from app.models import (
    Article,
    ArticleVersion,
    Conclusion,
    Fact,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    LegalVersion,
    Proof,
    ProofStep,
    RuleSource,
    RuleTestCase,
)
from app.models.enums import RbacRoleCode, ReviewDecisionType, ReviewStatus, ReviewType, SubjectType
from app.services.rule_governance_service import PublishGateFailedError, RuleGovernanceService
from app.services.rule_handlers import evaluate_gov_id_001, evaluate_gov_id_002
from tests.factories import make_tenant, make_user_with_role

EVAL_TIME = datetime(2025, 6, 1, tzinfo=UTC)


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(client, db_session, role: RbacRoleCode, tenant=None) -> dict:
    email = f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, role, tenant=tenant, email=email, password="Pass123!")
    return {"Authorization": f"Bearer {_login(client, email, 'Pass123!')}"}


def _make_article_version(db_session) -> ArticleVersion:
    document = LegalDocument(code=f"RP-LAW-{uuid.uuid4().hex[:6]}", name="参数化测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()
    version = LegalVersion(
        document_id=document.id, version_name="v1", effective_from=date(2024, 1, 1), status="ACTIVE"
    )
    db_session.add(version)
    db_session.flush()
    article = Article(document_id=document.id, article_no="1")
    db_session.add(article)
    db_session.flush()
    article_version = ArticleVersion(
        article_id=article.id, legal_version_id=version.id, article_text="测试条文", valid_from=date(2024, 1, 1)
    )
    db_session.add(article_version)
    db_session.flush()
    return article_version


def _make_rule_version(
    db_session, code: str, requirement_expression: dict, *, status: str = "DRAFT", version_no: int = 1
) -> LegalRuleVersion:
    article_version = _make_article_version(db_session)
    rule = LegalRule(code=code, name=code)
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id,
        version_no=version_no,
        status=status,
        subject_type="ListedCompany",
        modality="OBLIGATION",
        condition_expression={},
        requirement_expression=requirement_expression,
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()
    return rule_version


def _make_company_with_board_fact(db_session, tenant, *, independent: int, total: int) -> LegalSubject:
    company = LegalSubject(
        name=f"参数化测试公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(
        Fact(
            tenant_id=tenant.id,
            company_id=company.id,
            fact_type="BOARD_COMPOSITION",
            predicate="independent_director_count",
            object_value={"total": total, "independent": independent},
            valid_from=date(2025, 1, 1),
            valid_to=None,
        )
    )
    db_session.flush()
    return company


def _ctx(rule_version_id, rule_code: str, requirement_expression: dict) -> RuleExecutionContext:
    return RuleExecutionContext(
        rule_version_id=rule_version_id,
        rule_code=rule_code,
        requirement_expression=requirement_expression,
        evaluation_time=EVAL_TIME,
    )


def test_same_handler_different_params_different_results(db_session) -> None:
    """One handler, two rule-version parameter sets -> opposite outcomes on the
    very same facts (independent=2, total=9)."""
    tenant = make_tenant(db_session)
    company = _make_company_with_board_fact(db_session, tenant, independent=2, total=9)

    threshold_2 = evaluate_gov_id_001(
        db_session, _ctx(uuid.uuid4(), "GOV-ID-001", {"operator": "gte", "value": 2, "unit": "person"}), company
    )
    threshold_5 = evaluate_gov_id_001(
        db_session, _ctx(uuid.uuid4(), "GOV-ID-001", {"operator": "gte", "value": 5, "unit": "person"}), company
    )
    assert threshold_2.status.value == "TRUE"  # 2 >= 2
    assert threshold_5.status.value == "FALSE"  # 2 < 5

    ratio_one_third = evaluate_gov_id_002(
        db_session,
        _ctx(uuid.uuid4(), "GOV-ID-002", {"operator": "gte_ratio", "numerator": 1, "denominator": 3}),
        company,
    )
    ratio_one_fifth = evaluate_gov_id_002(
        db_session,
        _ctx(uuid.uuid4(), "GOV-ID-002", {"operator": "gte_ratio", "numerator": 1, "denominator": 5}),
        company,
    )
    assert ratio_one_third.status.value == "FALSE"  # 2*3 < 9*1
    assert ratio_one_fifth.status.value == "TRUE"  # 2*5 >= 9*1
    # Proof records the parameters actually used (lhs/rhs cross-multiplied integers).
    calc = ratio_one_fifth.proof_steps[0].calculation
    assert calc["lhs"] == 10 and calc["rhs"] == 9
    assert calc["requirement"] == {"operator": "gte_ratio", "numerator": 1, "denominator": 5}


def test_invalid_requirement_expression_rejected_via_api(client, db_session) -> None:
    """A rule version with a string number is refused with a stable 422 code —
    no silent fallback to any default threshold."""
    tenant = make_tenant(db_session)
    headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    _make_rule_version(db_session, "GOV-ID-001", {"operator": "gte", "value": "2", "unit": "person"})
    company = _make_company_with_board_fact(db_session, tenant, independent=2, total=9)

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "evaluation_time": EVAL_TIME.isoformat(),
            "rule_codes": ["GOV-ID-001"],
            "idempotency_key": f"bad-param-{uuid.uuid4().hex}",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_RULE_REQUIREMENT"


def test_check_history_keeps_execution_time_rule_version(client, db_session) -> None:
    """Publishing a new rule version must not rewrite old conclusions: the old
    check still references v1 and its stored proof payload is unchanged."""
    tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)

    v1 = _make_rule_version(
        db_session, "GOV-ID-001", {"operator": "gte", "value": 2, "unit": "person"}, status="PUBLISHED"
    )

    def _publish_ruleset(rule_version: LegalRuleVersion) -> str:
        resp = client.post(
            "/api/v1/rulesets",
            headers=editor_headers,
            json={"code": f"RP-{uuid.uuid4().hex[:6]}", "name": "参数化规则集", "effective_from": "2025-01-01"},
        )
        assert resp.status_code == 201, resp.text
        rule_set_id = resp.json()["id"]
        client.post(
            f"/api/v1/rulesets/{rule_set_id}/members",
            headers=editor_headers,
            json={"rule_version_id": str(rule_version.id)},
        )
        pub = client.post(f"/api/v1/rulesets/{rule_set_id}/publish", headers=publisher_headers)
        assert pub.status_code == 200, pub.text
        return rule_set_id

    def _run_formal_check(rule_set_id: str) -> dict:
        resp = client.post(
            "/api/v1/compliance-checks",
            headers={**compliance_headers, "Idempotency-Key": f"rp-{uuid.uuid4().hex}"},
            json={
                "tenant_id": str(tenant.id),
                "subject_id": str(company.id),
                "evaluation_time": EVAL_TIME.isoformat(),
                "ruleset_id": rule_set_id,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    company = _make_company_with_board_fact(db_session, tenant, independent=2, total=9)

    check_v1 = _run_formal_check(_publish_ruleset(v1))
    assert check_v1["conclusions"][0]["result_status"] == "TRUE"  # 2 >= 2

    # A new version of the same rule with a stricter threshold, and a new check.
    v2 = LegalRuleVersion(
        rule_id=v1.rule_id,
        version_no=2,
        status="PUBLISHED",
        subject_type="ListedCompany",
        modality="OBLIGATION",
        condition_expression={},
        requirement_expression={"operator": "gte", "value": 5, "unit": "person"},
    )
    db_session.add(v2)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=v2.id, article_version_id=_make_article_version(db_session).id))
    db_session.flush()

    check_v2 = _run_formal_check(_publish_ruleset(v2))
    assert check_v2["conclusions"][0]["result_status"] == "FALSE"  # 2 < 5

    # The old check is untouched: still v1, still TRUE, still threshold=2 in the proof.
    old_conclusion = (
        db_session.query(Conclusion).filter_by(compliance_check_id=uuid.UUID(check_v1["id"])).one()
    )
    assert str(old_conclusion.rule_version_id) == str(v1.id)
    assert old_conclusion.result_status.value == "TRUE"
    threshold_step = (
        db_session.query(ProofStep)
        .join(Proof, ProofStep.proof_id == Proof.id)
        .filter(Proof.conclusion_id == old_conclusion.id, ProofStep.step_type == "THRESHOLD_COMPARISON")
        .one()
    )
    assert threshold_step.calculation["threshold"] == 2
    assert threshold_step.calculation["requirement"] == {"operator": "gte", "value": 2, "unit": "person"}
    assert str(threshold_step.rule_version_id) == str(v1.id)


def test_publish_gate_records_invalid_requirement_as_failure(db_session) -> None:
    """The publish gate really executes handlers: an illegal expression surfaces
    as gate failure reasons, not as a crash or a silent pass."""
    tenant = make_tenant(db_session)
    company = _make_company_with_board_fact(db_session, tenant, independent=2, total=9)
    rule_version = _make_rule_version(db_session, "GOV-ID-001", {"operator": "gte", "value": "two", "unit": "person"})

    editor = make_user_with_role(db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal = make_user_with_role(db_session, RbacRoleCode.LEGAL_REVIEWER)
    tech = make_user_with_role(db_session, RbacRoleCode.TECHNICAL_REVIEWER)
    publisher = make_user_with_role(db_session, RbacRoleCode.PUBLISHER)

    eval_time = EVAL_TIME.isoformat()
    for case_type in ("PASS", "VIOLATION", "BOUNDARY", "MISSING_FACT"):
        db_session.add(
            RuleTestCase(
                rule_version_id=rule_version.id,
                case_type=case_type,
                expected_status="TRUE",
                input_facts={"company_id": str(company.id), "evaluation_time": eval_time},
            )
        )
    for waivable in ("NOT_APPLICABLE", "EXCEPTION", "CONFLICT"):
        db_session.add(
            RuleTestCase(
                rule_version_id=rule_version.id,
                case_type=waivable,
                expected_status="TRUE",
                input_facts={},
                not_applicable_reason="参数化门禁测试：仅验证非法表达式被拒绝",
            )
        )
    db_session.flush()

    governance = RuleGovernanceService(db_session)
    governance.submit(rule_version, submitted_by=editor.id)
    governance.add_review(rule_version, legal.id, ReviewType.LEGAL, ReviewDecisionType.APPROVED, "ok")
    governance.add_review(rule_version, tech.id, ReviewType.TECHNICAL, ReviewDecisionType.APPROVED, "ok")

    with pytest.raises(PublishGateFailedError) as exc_info:
        governance.publish(rule_version, publisher.id)
    assert exc_info.value.reasons
    assert all("invalid requirement_expression" in reason for reason in exc_info.value.reasons)
    assert rule_version.status == ReviewStatus.TECH_APPROVED  # not silently published
