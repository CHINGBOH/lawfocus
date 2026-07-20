"""C2: GET /compliance-checks/precheck — a read-only dry run of a ruleset
against a subject, with no ComplianceCheck/Conclusion/Proof/ProofStep rows
created and no audit event recorded (06号文档§4.4 step 4 / 11号文档 E5)."""

import uuid
from datetime import UTC, date, datetime

from app.models import (
    Article,
    ArticleVersion,
    ComplianceCheck,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    LegalVersion,
    Organization,
    RuleSource,
)
from app.models.enums import RbacRoleCode, SubjectType
from tests.factories import demo_requirement_expression, make_tenant, make_user_with_role

EVAL_TIME = datetime(2025, 6, 1, tzinfo=UTC)


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(client, db_session, role: RbacRoleCode, tenant=None) -> dict:
    email = f"pc-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, role, tenant=tenant, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    return {"Authorization": f"Bearer {token}"}


def _make_rule_version(db_session, code: str, *, status: str = "PUBLISHED") -> LegalRuleVersion:
    document = LegalDocument(code=f"PC-LAW-{uuid.uuid4().hex[:6]}", name="预检测试法", document_type="LAW")
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
        article_id=article.id, legal_version_id=version.id, article_text="测试条文",
        valid_from=date(2024, 1, 1),
    )
    db_session.add(article_version)
    db_session.flush()

    rule = LegalRule(code=code, name=code)
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status=status, subject_type="ListedCompany",
        modality="OBLIGATION", condition_expression={},
        requirement_expression=demo_requirement_expression(code),
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()
    return rule_version


def _publish_ruleset(client, editor_headers, publisher_headers, rule_version: LegalRuleVersion) -> str:
    resp = client.post(
        "/api/v1/rulesets", headers=editor_headers,
        json={"code": f"PC-{uuid.uuid4().hex[:6]}", "name": "预检测试规则集", "effective_from": "2025-01-01"},
    )
    assert resp.status_code == 201, resp.text
    rule_set_id = resp.json()["id"]
    client.post(
        f"/api/v1/rulesets/{rule_set_id}/members", headers=editor_headers,
        json={"rule_version_id": str(rule_version.id)},
    )
    pub = client.post(f"/api/v1/rulesets/{rule_set_id}/publish", headers=publisher_headers)
    assert pub.status_code == 200, pub.text
    return rule_set_id


def _make_company(db_session, *, listed: bool = True) -> LegalSubject:
    company = LegalSubject(
        name=f"预检测试公司-{uuid.uuid4().hex[:6]}",
        subject_type=SubjectType.LISTED_COMPANY if listed else SubjectType.COMPANY,
        listed=listed,
    )
    db_session.add(company)
    db_session.flush()
    return company


def test_precheck_reports_true_without_creating_a_check(client, db_session) -> None:
    tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)

    rule_version = _make_rule_version(db_session, "GOV-ORG-001")
    rule_set_id = _publish_ruleset(client, editor_headers, publisher_headers, rule_version)

    company = _make_company(db_session)
    db_session.add(Organization(company_id=company.id, organization_type="BOARD", name="董事会"))
    db_session.flush()

    checks_before = db_session.query(ComplianceCheck).count()

    resp = client.get(
        "/api/v1/compliance-checks/precheck", headers=compliance_headers,
        params={
            "tenant_id": str(tenant.id), "subject_id": str(company.id),
            "evaluation_time": EVAL_TIME.isoformat(), "ruleset_id": rule_set_id,
        },
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["rule_code"] == "GOV-ORG-001"
    assert items[0]["status"] == "TRUE"
    assert items[0]["missing_facts"] == []

    db_session.expire_all()
    assert db_session.query(ComplianceCheck).count() == checks_before


def test_precheck_reports_missing_facts_for_unknown_result(client, db_session) -> None:
    tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)

    rule_version = _make_rule_version(db_session, "GOV-ID-002")
    rule_set_id = _publish_ruleset(client, editor_headers, publisher_headers, rule_version)

    company = _make_company(db_session)  # no board composition facts at all

    resp = client.get(
        "/api/v1/compliance-checks/precheck", headers=compliance_headers,
        params={
            "tenant_id": str(tenant.id), "subject_id": str(company.id),
            "evaluation_time": EVAL_TIME.isoformat(), "ruleset_id": rule_set_id,
        },
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["status"] == "UNKNOWN"
    assert len(item["missing_facts"]) > 0


def test_precheck_requires_tenant_access(client, db_session) -> None:
    tenant = make_tenant(db_session)
    other_tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    outsider_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=other_tenant)

    rule_version = _make_rule_version(db_session, "GOV-ORG-001")
    rule_set_id = _publish_ruleset(client, editor_headers, publisher_headers, rule_version)
    company = _make_company(db_session)

    resp = client.get(
        "/api/v1/compliance-checks/precheck", headers=outsider_headers,
        params={
            "tenant_id": str(tenant.id), "subject_id": str(company.id),
            "evaluation_time": EVAL_TIME.isoformat(), "ruleset_id": rule_set_id,
        },
    )
    assert resp.status_code == 403


def test_precheck_for_unpublished_ruleset_is_rejected(client, db_session) -> None:
    tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)

    resp = client.post(
        "/api/v1/rulesets", headers=editor_headers,
        json={"code": f"PC-DRAFT-{uuid.uuid4().hex[:6]}", "name": "未发布规则集", "effective_from": "2025-01-01"},
    )
    assert resp.status_code == 201, resp.text
    rule_set_id = resp.json()["id"]
    company = _make_company(db_session)

    resp = client.get(
        "/api/v1/compliance-checks/precheck", headers=compliance_headers,
        params={
            "tenant_id": str(tenant.id), "subject_id": str(company.id),
            "evaluation_time": EVAL_TIME.isoformat(), "ruleset_id": rule_set_id,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "RULE_SET_NOT_FOUND"
