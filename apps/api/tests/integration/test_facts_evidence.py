import uuid

from app.models import LegalSubject
from app.models.enums import RbacRoleCode, SubjectType
from tests.factories import make_tenant, make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _compliance_user_headers(client, db_session, tenant) -> dict[str, str]:
    email = f"cu-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(
        db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant, email=email, password="Pass123!"
    )
    token = _login(client, email, "Pass123!")
    return {"Authorization": f"Bearer {token}"}


def _make_company(db_session) -> LegalSubject:
    company = LegalSubject(
        name=f"证据测试公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    return company


def test_create_fact_requires_compliance_user_role(client, db_session) -> None:
    tenant = make_tenant(db_session)
    email = f"reader-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, RbacRoleCode.READER, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    company = _make_company(db_session)

    resp = client.post(
        "/api/v1/facts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "fact_type": "BOARD_COMPOSITION",
            "predicate": "independent_director_count",
            "object_value": {"total": 9, "independent": 3},
            "valid_from": "2025-01-01",
        },
    )
    assert resp.status_code == 403


def test_create_fact_and_evidence_and_link_them(client, db_session) -> None:
    tenant = make_tenant(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)

    fact_resp = client.post(
        "/api/v1/facts",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "fact_type": "BOARD_COMPOSITION",
            "predicate": "independent_director_count",
            "object_value": {"total": 9, "independent": 3},
            "valid_from": "2025-01-01",
        },
    )
    assert fact_resp.status_code == 201, fact_resp.text
    fact_id = fact_resp.json()["id"]

    evidence_resp = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "evidence_type": "AnnualReport",
            "title": "测试年报",
            "quote_text": "独立董事3人",
        },
    )
    assert evidence_resp.status_code == 201, evidence_resp.text
    evidence_id = evidence_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/facts/{fact_id}/evidence/{evidence_id}",
        headers=headers,
        json={"support_type": "DIRECT", "confidence": 0.95},
    )
    assert link_resp.status_code == 201, link_resp.text
    assert link_resp.json()["fact_id"] == fact_id
    assert link_resp.json()["evidence_id"] == evidence_id


def test_link_rejects_evidence_from_a_different_tenant(client, db_session) -> None:
    tenant_a = make_tenant(db_session)
    tenant_b = make_tenant(db_session)
    headers = _compliance_user_headers(client, db_session, tenant_a)
    company = _make_company(db_session)

    fact_resp = client.post(
        "/api/v1/facts",
        headers=headers,
        json={
            "tenant_id": str(tenant_a.id),
            "company_id": str(company.id),
            "fact_type": "BOARD_COMPOSITION",
            "predicate": "independent_director_count",
            "object_value": {"total": 9, "independent": 3},
            "valid_from": "2025-01-01",
        },
    )
    fact_id = fact_resp.json()["id"]

    from app.models import Evidence

    other_evidence = Evidence(tenant_id=tenant_b.id, evidence_type="AnnualReport", title="其他租户证据")
    db_session.add(other_evidence)
    db_session.flush()

    link_resp = client.post(
        f"/api/v1/facts/{fact_id}/evidence/{other_evidence.id}",
        headers=headers,
        json={"support_type": "DIRECT"},
    )
    assert link_resp.status_code == 400
    assert link_resp.json()["code"] == "TENANT_MISMATCH"


def test_link_returns_404_for_unknown_fact(client, db_session) -> None:
    tenant = make_tenant(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)

    resp = client.post(
        f"/api/v1/facts/{uuid.uuid4()}/evidence/{uuid.uuid4()}",
        headers=headers,
        json={"support_type": "DIRECT"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "FACT_NOT_FOUND"
