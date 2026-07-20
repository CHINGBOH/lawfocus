import uuid
from datetime import date

from app.models import (
    Article,
    ArticleVersion,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalVersion,
    RuleSource,
)
from app.models.enums import RbacRoleCode
from tests.factories import make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(client, db_session, role: RbacRoleCode, **kwargs) -> tuple[dict[str, str], uuid.UUID]:
    email = f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@test.lawfocus"
    user = make_user_with_role(db_session, role, email=email, password="Pass123!", **kwargs)
    token = _login(client, email, "Pass123!")
    return {"Authorization": f"Bearer {token}"}, user.id


def _make_rule_with_source(db_session) -> tuple[LegalRule, LegalRuleVersion]:
    document = LegalDocument(code=f"AU-LAW-{uuid.uuid4().hex[:6]}", name="审计测试法", document_type="LAW")
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

    rule = LegalRule(code=f"GOV-AUDIT-{uuid.uuid4().hex[:6]}", name="审计测试规则")
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


def test_rule_submit_creates_an_allowed_audit_event(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, editor_id = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    auditor_headers, _ = _headers(client, db_session, RbacRoleCode.AUDITOR)

    submit_resp = client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    assert submit_resp.status_code == 200

    list_resp = client.get(
        "/api/v1/audit-events",
        params={"action": "SUBMIT", "resource_type": "rule", "resource_id": str(rule.id)},
        headers=auditor_headers,
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    event = body["items"][0]
    assert event["actor_id"] == str(editor_id)
    assert event["decision"] == "ALLOWED"
    assert event["resource_version"] == "1"


def test_publish_gate_failure_creates_a_denied_audit_event(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal_headers, _ = _headers(client, db_session, RbacRoleCode.LEGAL_REVIEWER)
    tech_headers, _ = _headers(client, db_session, RbacRoleCode.TECHNICAL_REVIEWER)
    publisher_headers, publisher_id = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    auditor_headers, _ = _headers(client, db_session, RbacRoleCode.AUDITOR)

    client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=legal_headers,
        json={"review_type": "LEGAL", "decision": "APPROVED"},
    )
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=tech_headers,
        json={"review_type": "TECHNICAL", "decision": "APPROVED"},
    )
    publish_resp = client.post(f"/api/v1/rules/{rule.id}/publish", headers=publisher_headers)
    assert publish_resp.status_code == 422

    list_resp = client.get(
        "/api/v1/audit-events",
        params={"action": "PUBLISH", "decision": "DENIED", "resource_id": str(rule.id)},
        headers=auditor_headers,
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    assert body["items"][0]["actor_id"] == str(publisher_id)
    assert body["items"][0]["reason_code"] == "PUBLISH_GATE_FAILED"


def test_review_decision_is_recorded_in_reason_code(client, db_session) -> None:
    rule, _version = _make_rule_with_source(db_session)
    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    legal_headers, _ = _headers(client, db_session, RbacRoleCode.LEGAL_REVIEWER)
    auditor_headers, _ = _headers(client, db_session, RbacRoleCode.AUDITOR)

    client.post(f"/api/v1/rules/{rule.id}/submit", headers=editor_headers)
    client.post(
        f"/api/v1/rules/{rule.id}/reviews", headers=legal_headers,
        json={"review_type": "LEGAL", "decision": "CHANGES_REQUESTED", "comment": "需要修改"},
    )

    list_resp = client.get(
        "/api/v1/audit-events",
        params={"action": "REVIEW", "resource_id": str(rule.id)},
        headers=auditor_headers,
    )
    assert list_resp.json()["items"][0]["reason_code"] == "LEGAL:CHANGES_REQUESTED"


def test_audit_events_endpoint_is_forbidden_to_non_auditors(client, db_session) -> None:
    reader_headers, _ = _headers(client, db_session, RbacRoleCode.READER)
    resp = client.get("/api/v1/audit-events", headers=reader_headers)
    assert resp.status_code == 403


def test_my_audit_events_is_self_scoped_for_any_role(client, db_session) -> None:
    reader_a_headers, reader_a_id = _headers(client, db_session, RbacRoleCode.READER)
    reader_b_headers, reader_b_id = _headers(client, db_session, RbacRoleCode.READER)

    document = LegalDocument(code=f"AU-MINE-{uuid.uuid4().hex[:6]}", name="自读测试法", document_type="LAW")
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
    db_session.add(
        ArticleVersion(
            article_id=article.id, legal_version_id=version.id, article_text="测试条文", valid_from=date(2024, 1, 1)
        )
    )
    db_session.flush()

    view_resp = client.get(
        f"/api/v1/laws/{document.code}/versions/v1/articles/1", headers=reader_a_headers
    )
    assert view_resp.status_code == 200

    mine_a = client.get(
        "/api/v1/audit-events/mine",
        params={"action": "VIEW", "resource_type": "article_version"},
        headers=reader_a_headers,
    )
    assert mine_a.status_code == 200
    assert mine_a.json()["total"] >= 1
    assert all(item["actor_id"] == str(reader_a_id) for item in mine_a.json()["items"])

    # Reader B never viewed anything — their own feed must stay empty, and a
    # READER (no Auditor role) must never be able to see reader A's events by
    # querying /mine (there is no actor_id parameter to spoof on this route).
    mine_b = client.get(
        "/api/v1/audit-events/mine",
        params={"action": "VIEW", "resource_type": "article_version"},
        headers=reader_b_headers,
    )
    assert mine_b.status_code == 200
    assert mine_b.json()["total"] == 0
    assert str(reader_a_id) != str(reader_b_id)


def test_compliance_check_creation_creates_an_audit_event(client, db_session) -> None:
    from tests.integration.test_compliance_check import (
        _base_fixture,
        _compliance_user_headers,
        _make_company,
        _run_check,
    )

    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)
    auditor_headers, _ = _headers(client, db_session, RbacRoleCode.AUDITOR)

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001"])
    assert resp.status_code == 201
    check_id = resp.json()["id"]

    list_resp = client.get(
        "/api/v1/audit-events",
        params={"action": "CREATE", "resource_type": "compliance_check", "resource_id": check_id},
        headers=auditor_headers,
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    assert body["items"][0]["decision"] == "ALLOWED"
    assert body["items"][0]["tenant_id"] == str(tenant.id)


def test_ruleset_publish_of_empty_set_creates_denied_audit_event(client, db_session) -> None:
    editor_headers, _ = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers, publisher_id = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    auditor_headers, _ = _headers(client, db_session, RbacRoleCode.AUDITOR)

    create_resp = client.post(
        "/api/v1/rulesets",
        headers=editor_headers,
        json={"code": f"AU-RS-{uuid.uuid4().hex[:6]}", "name": "空规则集", "effective_from": "2025-01-01"},
    )
    assert create_resp.status_code == 201
    rule_set_id = create_resp.json()["id"]

    publish_resp = client.post(f"/api/v1/rulesets/{rule_set_id}/publish", headers=publisher_headers)
    assert publish_resp.status_code == 422

    list_resp = client.get(
        "/api/v1/audit-events",
        params={"action": "PUBLISH", "resource_type": "rule_set", "resource_id": rule_set_id},
        headers=auditor_headers,
    )
    body = list_resp.json()
    assert body["total"] == 1
    assert body["items"][0]["decision"] == "DENIED"
    assert body["items"][0]["actor_id"] == str(publisher_id)
