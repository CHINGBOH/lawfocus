"""F0: formal RuleSet governance + the new compliance-check contract
(subject_id / ruleset_id / Idempotency-Key header), per
06-MVP骨架充实与功能闭环计划.md §3.1/§5.1.
"""

import uuid
from datetime import UTC, date, datetime

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
)
from app.models.enums import RbacRoleCode, SubjectType
from tests.factories import make_tenant, make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(client, db_session, role: RbacRoleCode, tenant=None) -> dict:
    email = f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, role, tenant=tenant, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    return {"Authorization": f"Bearer {token}"}


def _make_published_rule(db_session, code: str = "GOV-ORG-001") -> LegalRuleVersion:
    document = LegalDocument(code=f"RS-LAW-{uuid.uuid4().hex[:6]}", name="规则集测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()
    version = LegalVersion(document_id=document.id, version_name="v1", effective_from=date(2024, 1, 1), status="ACTIVE")
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

    rule = LegalRule(code=code, name="董事会存在性")
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status="PUBLISHED", subject_type="ListedCompany", modality="OBLIGATION",
        condition_expression={}, requirement_expression={},
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()
    return rule_version


def _make_company_with_board(db_session) -> LegalSubject:
    company = LegalSubject(
        name=f"规则集测试公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(Organization(company_id=company.id, organization_type="BOARD", name="董事会"))
    db_session.flush()
    return company


def test_ruleset_lifecycle_draft_add_member_publish(client, db_session) -> None:
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    rule_version = _make_published_rule(db_session)

    create_resp = client.post(
        "/api/v1/rulesets",
        headers=editor_headers,
        json={"code": f"MVP-P0-{uuid.uuid4().hex[:6]}", "name": "MVP P0 规则集", "effective_from": "2025-01-01"},
    )
    assert create_resp.status_code == 201, create_resp.text
    rule_set_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "DRAFT"

    add_resp = client.post(
        f"/api/v1/rulesets/{rule_set_id}/members",
        headers=editor_headers,
        json={"rule_version_id": str(rule_version.id)},
    )
    assert add_resp.status_code == 201, add_resp.text
    assert len(add_resp.json()["members"]) == 1

    publish_resp = client.post(f"/api/v1/rulesets/{rule_set_id}/publish", headers=publisher_headers)
    assert publish_resp.status_code == 200
    assert publish_resp.json()["status"] == "PUBLISHED"

    # Can no longer add members once published.
    second_rule_version = _make_published_rule(db_session, code=f"GOV-EXTRA-{uuid.uuid4().hex[:6]}")
    reject_resp = client.post(
        f"/api/v1/rulesets/{rule_set_id}/members",
        headers=editor_headers,
        json={"rule_version_id": str(second_rule_version.id)},
    )
    assert reject_resp.status_code == 409
    assert reject_resp.json()["code"] == "RULE_SET_NOT_EDITABLE"


def test_ruleset_rejects_unpublished_member(client, db_session) -> None:
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    rule = LegalRule(code=f"DRAFT-RULE-{uuid.uuid4().hex[:6]}", name="草稿规则")
    db_session.add(rule)
    db_session.flush()
    draft_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status="DRAFT", subject_type="ListedCompany", modality="OBLIGATION",
        condition_expression={}, requirement_expression={},
    )
    db_session.add(draft_version)
    db_session.flush()

    create_resp = client.post(
        "/api/v1/rulesets",
        headers=editor_headers,
        json={"code": f"RS-{uuid.uuid4().hex[:6]}", "name": "测试规则集", "effective_from": "2025-01-01"},
    )
    rule_set_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/v1/rulesets/{rule_set_id}/members",
        headers=editor_headers,
        json={"rule_version_id": str(draft_version.id)},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MEMBER_NOT_PUBLISHED"


def test_publish_rejects_empty_ruleset(client, db_session) -> None:
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)

    create_resp = client.post(
        "/api/v1/rulesets",
        headers=editor_headers,
        json={"code": f"EMPTY-{uuid.uuid4().hex[:6]}", "name": "空规则集", "effective_from": "2025-01-01"},
    )
    rule_set_id = create_resp.json()["id"]

    resp = client.post(f"/api/v1/rulesets/{rule_set_id}/publish", headers=publisher_headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "RULE_SET_EMPTY"


def test_formal_compliance_check_with_ruleset_id_and_header_idempotency(client, db_session) -> None:
    tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    publisher_headers = _headers(client, db_session, RbacRoleCode.PUBLISHER)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)

    rule_version = _make_published_rule(db_session)
    rule_set_resp = client.post(
        "/api/v1/rulesets",
        headers=editor_headers,
        json={"code": f"FORMAL-{uuid.uuid4().hex[:6]}", "name": "正式规则集", "effective_from": "2025-01-01"},
    )
    rule_set_id = rule_set_resp.json()["id"]
    client.post(
        f"/api/v1/rulesets/{rule_set_id}/members", headers=editor_headers,
        json={"rule_version_id": str(rule_version.id)},
    )
    client.post(f"/api/v1/rulesets/{rule_set_id}/publish", headers=publisher_headers)

    company = _make_company_with_board(db_session)

    resp = client.post(
        "/api/v1/compliance-checks",
        headers={**compliance_headers, "Idempotency-Key": f"formal-{uuid.uuid4().hex}"},
        json={
            "tenant_id": str(tenant.id),
            "subject_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "ruleset_id": rule_set_id,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["subject_id"] == str(company.id)
    assert body["rule_set_id"] == rule_set_id
    assert body["deprecations"] == []
    assert body["conclusions"][0]["result_status"] == "TRUE"
    # rule_code/rule_name must be present so the frontend never has to show a raw UUID.
    assert body["conclusions"][0]["rule_code"] == "GOV-ORG-001"
    assert body["conclusions"][0]["rule_name"]


def test_unpublished_ruleset_is_rejected_for_a_real_check(client, db_session) -> None:
    tenant = make_tenant(db_session)
    editor_headers = _headers(client, db_session, RbacRoleCode.KNOWLEDGE_EDITOR)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)

    create_resp = client.post(
        "/api/v1/rulesets",
        headers=editor_headers,
        json={"code": f"DRAFT-RS-{uuid.uuid4().hex[:6]}", "name": "未发布规则集", "effective_from": "2025-01-01"},
    )
    rule_set_id = create_resp.json()["id"]
    company = _make_company_with_board(db_session)

    resp = client.post(
        "/api/v1/compliance-checks",
        headers={**compliance_headers, "Idempotency-Key": f"unpub-{uuid.uuid4().hex}"},
        json={
            "tenant_id": str(tenant.id),
            "subject_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "ruleset_id": rule_set_id,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "RULE_SET_NOT_FOUND"


def test_deprecated_fields_are_reported_and_still_work(client, db_session) -> None:
    tenant = make_tenant(db_session)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    company = _make_company_with_board(db_session)
    _make_published_rule(db_session)

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=compliance_headers,  # no Idempotency-Key header
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),  # deprecated alias
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ORG-001"],  # deprecated ad-hoc list
            "idempotency_key": f"legacy-{uuid.uuid4().hex}",  # deprecated body field
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["rule_set_id"] is None  # legacy path has no formal RuleSet backing it
    assert set(body["deprecations"]) == {
        "company_id is deprecated; use subject_id",
        "body idempotency_key is deprecated; use the Idempotency-Key header",
        "rule_codes is deprecated; use ruleset_id with a PUBLISHED RuleSet",
    }


def test_missing_idempotency_key_entirely_is_rejected(client, db_session) -> None:
    tenant = make_tenant(db_session)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    company = _make_company_with_board(db_session)

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=compliance_headers,
        json={
            "tenant_id": str(tenant.id),
            "subject_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ORG-001"],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_list_compliance_checks_is_paginated_and_tenant_scoped(client, db_session) -> None:
    tenant = make_tenant(db_session)
    compliance_headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    company = _make_company_with_board(db_session)
    _make_published_rule(db_session)

    for i in range(3):
        client.post(
            "/api/v1/compliance-checks",
            headers={**compliance_headers, "Idempotency-Key": f"list-{i}-{uuid.uuid4().hex}"},
            json={
                "tenant_id": str(tenant.id),
                "subject_id": str(company.id),
                "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
                "rule_codes": ["GOV-ORG-001"],
            },
        )

    resp = client.get(
        "/api/v1/compliance-checks",
        headers=compliance_headers,
        params={"tenant_id": str(tenant.id), "page": 1, "page_size": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
