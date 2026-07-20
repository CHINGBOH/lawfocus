import uuid
from datetime import date

from app.models import (
    Article,
    ArticleVersion,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    LegalVersion,
    Organization,
    RuleSource,
    RuleTestCase,
)
from app.models.enums import RbacRoleCode, SubjectType
from tests.factories import make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(client, db_session, role: RbacRoleCode) -> tuple[dict[str, str], uuid.UUID]:
    email = f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@test.lawfocus"
    user = make_user_with_role(db_session, role, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    return {"Authorization": f"Bearer {token}"}, user.id


def _make_rule_with_source(db_session) -> tuple[LegalRule, LegalRuleVersion]:
    document = LegalDocument(code=f"RG-LAW-{uuid.uuid4().hex[:6]}", name="规则治理测试法", document_type="LAW")
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

    rule = LegalRule(code=f"GOV-TEST-{uuid.uuid4().hex[:6]}", name="测试规则")
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id,
        version_no=1,
        status="DRAFT",
        subject_type="ListedCompany",
        modality="OBLIGATION",
        condition_expression={},
        requirement_expression={},
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()
    return rule, rule_version


def _make_company_with_board(db_session) -> LegalSubject:
    company = LegalSubject(
        name=f"治理测试公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(Organization(company_id=company.id, organization_type="BOARD", name="董事会"))
    db_session.flush()
    return company


def _make_company_without_board(db_session) -> LegalSubject:
    company = LegalSubject(
        name=f"治理测试公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    return company


def _add_all_mandatory_test_cases(db_session, rule_version_id, pass_company, fail_company):
    eval_time = "2025-06-01T00:00:00+00:00"
    db_session.add_all(
        [
            RuleTestCase(
                rule_version_id=rule_version_id,
                case_type="PASS",
                input_facts={"company_id": str(pass_company.id), "evaluation_time": eval_time},
                expected_status="TRUE",
            ),
            RuleTestCase(
                rule_version_id=rule_version_id,
                case_type="VIOLATION",
                input_facts={"company_id": str(fail_company.id), "evaluation_time": eval_time},
                expected_status="FALSE",
            ),
            RuleTestCase(
                rule_version_id=rule_version_id,
                case_type="BOUNDARY",
                input_facts={},
                expected_status="TRUE",
                not_applicable_reason=None,
            ),
            RuleTestCase(
                rule_version_id=rule_version_id,
                case_type="MISSING_FACT",
                input_facts={},
                expected_status="UNKNOWN",
            ),
            RuleTestCase(
                rule_version_id=rule_version_id,
                case_type="NOT_APPLICABLE",
                input_facts={},
                expected_status="NOT_APPLICABLE",
                not_applicable_reason=None,
            ),
        ]
    )
    db_session.add(
        RuleTestCase(
            rule_version_id=rule_version_id,
            case_type="EXCEPTION",
            input_facts={},
            expected_status="TRUE",
            not_applicable_reason="GOV-ORG-001 无例外分支，规则设计无需例外测试",
        )
    )
    db_session.add(
        RuleTestCase(
            rule_version_id=rule_version_id,
            case_type="CONFLICT",
            input_facts={},
            expected_status="TRUE",
            not_applicable_reason="GOV-ORG-001 基于结构化注册表，不存在冲突来源",
        )
    )
    db_session.flush()


def test_cannot_publish_directly_from_draft(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    publisher_headers, _ = _headers(client, db_session, RbacRoleCode.PUBLISHER)

    resp = client.post(f"/api/v1/rules/{rule.id}/publish", headers=publisher_headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_TRANSITION"


def test_self_review_is_rejected(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, editor_id = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)

    submit_resp = client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    assert submit_resp.status_code == 200, submit_resp.text

    # Grant this same user a LEGAL_REVIEWER role too, then try to review their own submission.
    from tests.factories import make_user_with_role as grant_role

    grant_role(db_session, RbacRoleCode.LEGAL_REVIEWER, tenant=None)  # unrelated user, ensure table has the role
    from app.models import Role, UserRole

    legal_role = db_session.query(Role).filter_by(code=RbacRoleCode.LEGAL_REVIEWER).one()
    db_session.add(UserRole(user_id=editor_id, role_id=legal_role.id, tenant_id=None))
    db_session.flush()

    review_resp = client.post(
        f"/api/v1/rules/{rule.id}/reviews",
        headers=editor_headers,
        json={"review_type": "LEGAL", "decision": "APPROVED"},
    )
    assert review_resp.status_code == 403
    assert review_resp.json()["code"] == "SELF_REVIEW_NOT_ALLOWED"


def test_technical_review_before_legal_approval_is_rejected(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    tech_headers, _ = _headers(client, db_session, RbacRoleCode.TECHNICAL_REVIEWER)

    client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    resp = client.post(
        f"/api/v1/rules/{rule.id}/reviews",
        headers=tech_headers,
        json={"review_type": "TECHNICAL", "decision": "APPROVED"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_TRANSITION"


def test_publish_fails_when_test_cases_are_missing(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal_headers, _ = _headers(client, db_session, RbacRoleCode.LEGAL_REVIEWER)
    tech_headers, _ = _headers(client, db_session, RbacRoleCode.TECHNICAL_REVIEWER)
    publisher_headers, _ = _headers(client, db_session, RbacRoleCode.PUBLISHER)

    client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=legal_headers,
        json={"review_type": "LEGAL", "decision": "APPROVED"},
    )
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=tech_headers,
        json={"review_type": "TECHNICAL", "decision": "APPROVED"},
    )

    resp = client.post(f"/api/v1/rules/{rule.id}/publish", headers=publisher_headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "PUBLISH_GATE_FAILED"
    assert any("missing mandatory test case type" in r for r in resp.json()["details"]["reasons"])


def test_publish_fails_when_a_test_case_result_does_not_match_expectation(client, db_session) -> None:
    rule, version = _make_rule_with_source(db_session)
    # Register this rule's code in the real handler registry by reusing GOV-ORG-001's
    # logic path: point the rule at the actual GOV-ORG-001 code so the gate executes
    # a real handler. (Rule codes must match RULE_REGISTRY keys to be executable.)
    rule.code = "GOV-ORG-001"
    db_session.flush()

    pass_company = _make_company_with_board(db_session)
    fail_company = _make_company_without_board(db_session)
    _add_all_mandatory_test_cases(db_session, version.id, pass_company, fail_company)
    # Corrupt the VIOLATION case's expectation so it disagrees with reality.
    violation_case = (
        db_session.query(RuleTestCase).filter_by(rule_version_id=version.id, case_type="VIOLATION").one()
    )
    violation_case.expected_status = "TRUE"  # wrong: fail_company actually yields FALSE
    db_session.flush()

    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal_headers, _ = _headers(client, db_session, RbacRoleCode.LEGAL_REVIEWER)
    tech_headers, _ = _headers(client, db_session, RbacRoleCode.TECHNICAL_REVIEWER)
    publisher_headers, _ = _headers(client, db_session, RbacRoleCode.PUBLISHER)

    client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=legal_headers,
        json={"review_type": "LEGAL", "decision": "APPROVED"},
    )
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=tech_headers,
        json={"review_type": "TECHNICAL", "decision": "APPROVED"},
    )

    resp = client.post(f"/api/v1/rules/{rule.id}/publish", headers=publisher_headers)
    assert resp.status_code == 422
    reasons = resp.json()["details"]["reasons"]
    assert any("expected TRUE, got FALSE" in r for r in reasons)


def test_full_happy_path_reaches_published(client, db_session) -> None:
    rule, version = _make_rule_with_source(db_session)
    rule.code = "GOV-ORG-001"
    db_session.flush()

    pass_company = _make_company_with_board(db_session)
    fail_company = _make_company_without_board(db_session)
    _add_all_mandatory_test_cases(db_session, version.id, pass_company, fail_company)

    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal_headers, _ = _headers(client, db_session, RbacRoleCode.LEGAL_REVIEWER)
    tech_headers, _ = _headers(client, db_session, RbacRoleCode.TECHNICAL_REVIEWER)
    publisher_headers, _ = _headers(client, db_session, RbacRoleCode.PUBLISHER)

    submit_resp = client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    assert submit_resp.json()["status"] == "IN_REVIEW"

    legal_resp = client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=legal_headers,
        json={"review_type": "LEGAL", "decision": "APPROVED"},
    )
    assert legal_resp.status_code == 201

    tech_resp = client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=tech_headers,
        json={"review_type": "TECHNICAL", "decision": "APPROVED"},
    )
    assert tech_resp.status_code == 201

    publish_resp = client.post(f"/api/v1/rules/{rule.id}/publish", headers=publisher_headers)
    assert publish_resp.status_code == 200, publish_resp.text
    assert publish_resp.json()["status"] == "PUBLISHED"


def test_changes_requested_sends_rule_back_for_resubmission(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal_headers, _ = _headers(client, db_session, RbacRoleCode.LEGAL_REVIEWER)

    client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    resp = client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=legal_headers,
        json={"review_type": "LEGAL", "decision": "CHANGES_REQUESTED", "comment": "阈值需要复核"},
    )
    assert resp.status_code == 201

    resubmit = client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    assert resubmit.status_code == 200
    assert resubmit.json()["status"] == "IN_REVIEW"
