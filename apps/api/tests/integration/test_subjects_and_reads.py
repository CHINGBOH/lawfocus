"""F1: subject/fact/evidence read endpoints per
06-MVP骨架充实与功能闭环计划.md §3.2/§4.2/§4.3.
"""

import uuid
from datetime import date

from app.models import LegalSubject, Organization, RoleAssignment, RoleType
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


def test_list_subjects_filters_by_type_and_listed(client, db_session) -> None:
    headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER)
    listed_co = LegalSubject(
        name=f"上市公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    unlisted_co = LegalSubject(
        name=f"非上市公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.COMPANY, listed=False
    )
    db_session.add_all([listed_co, unlisted_co])
    db_session.flush()

    resp = client.get(
        "/api/v1/subjects",
        headers=headers,
        params={"subject_type": "LISTED_COMPANY", "listed": True, "page_size": 200},
    )
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(listed_co.id) in ids
    assert str(unlisted_co.id) not in ids


def test_subject_detail_and_404(client, db_session) -> None:
    headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER)
    company = LegalSubject(
        name=f"详情公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()

    ok = client.get(f"/api/v1/subjects/{company.id}", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["name"] == company.name

    missing = client.get(f"/api/v1/subjects/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "SUBJECT_NOT_FOUND"


def test_governance_distinguishes_no_organ_from_empty_roster(client, db_session) -> None:
    headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER)
    company = LegalSubject(
        name=f"治理公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    board = Organization(company_id=company.id, organization_type="BOARD", name="董事会")
    db_session.add(board)
    db_session.flush()
    role_type = RoleType(code=f"DIRECTOR-{uuid.uuid4().hex[:6]}", name="董事")
    db_session.add(role_type)
    db_session.flush()
    person = LegalSubject(name="测试董事", subject_type=SubjectType.PERSON)
    db_session.add(person)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            person_id=person.id, role_type_id=role_type.id, company_id=company.id, organization_id=board.id,
            valid_from=date(2020, 1, 1), valid_to=date(2024, 1, 1),  # expired before our query date
        )
    )
    db_session.flush()

    resp = client.get(f"/api/v1/subjects/{company.id}/governance", headers=headers, params={"at": "2025-06-01"})
    assert resp.status_code == 200
    body = resp.json()
    # BOARD organization row exists (recorded), but has no member active at the query time.
    board_entry = next(o for o in body["organizations"] if o["organization"]["organization_type"] == "BOARD")
    assert board_entry["members"][0]["active_at_query_time"] is False
    # AUDIT_COMMITTEE has no Organization row at all -> absent from the list entirely,
    # distinct from "present but empty".
    assert not any(o["organization"]["organization_type"] == "AUDIT_COMMITTEE" for o in body["organizations"])


def test_list_and_get_facts_scoped_to_tenant(client, db_session) -> None:
    tenant = make_tenant(db_session)
    headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    company = LegalSubject(
        name=f"事实公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()

    create_resp = client.post(
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
    fact_id = create_resp.json()["id"]

    list_resp = client.get(
        "/api/v1/facts", headers=headers, params={"tenant_id": str(tenant.id), "subject_id": str(company.id)}
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    detail_resp = client.get(f"/api/v1/facts/{fact_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["evidence"] == []


def test_reader_role_cannot_browse_tenant_private_facts(client, db_session) -> None:
    tenant = make_tenant(db_session)
    reader_headers = _headers(client, db_session, RbacRoleCode.READER)

    resp = client.get("/api/v1/facts", headers=reader_headers, params={"tenant_id": str(tenant.id)})
    assert resp.status_code == 403


def test_evidence_list_filters_by_fact(client, db_session) -> None:
    tenant = make_tenant(db_session)
    headers = _headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    company = LegalSubject(
        name=f"证据公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()

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
    fact_id = fact_resp.json()["id"]
    evidence_resp = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={"tenant_id": str(tenant.id), "evidence_type": "AnnualReport", "title": "测试年报"},
    )
    evidence_id = evidence_resp.json()["id"]
    client.post(
        f"/api/v1/facts/{fact_id}/evidence/{evidence_id}", headers=headers, json={"support_type": "DIRECT"}
    )

    list_resp = client.get(
        "/api/v1/evidence", headers=headers, params={"tenant_id": str(tenant.id), "fact_id": fact_id}
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["id"] == evidence_id

    detail_resp = client.get(f"/api/v1/facts/{fact_id}", headers=headers)
    assert len(detail_resp.json()["evidence"]) == 1
    assert detail_resp.json()["evidence"][0]["evidence"]["id"] == evidence_id
