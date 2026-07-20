from app.models.enums import RbacRoleCode
from tests.factories import make_tenant, make_user_with_role


def test_me_returns_role_grants_with_tenant_scope(client, db_session) -> None:
    tenant = make_tenant(db_session)
    make_user_with_role(
        db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant, email="me-test@test.lawfocus", password="Pass123!"
    )
    resp = client.post("/api/v1/auth/login", json={"email": "me-test@test.lawfocus", "password": "Pass123!"})
    token = resp.json()["access_token"]

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["email"] == "me-test@test.lawfocus"
    assert body["grants"] == [{"role_code": "COMPLIANCE_USER", "tenant_id": str(tenant.id)}]


def test_me_requires_authentication(client) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_login_rejects_wrong_password(client, db_session) -> None:
    make_user_with_role(db_session, RbacRoleCode.READER, email="wrongpw@test.lawfocus", password="Correct123!")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@test.lawfocus", "password": "WrongPassword!"}
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "INVALID_CREDENTIALS"
    assert "trace_id" in body


def test_login_rejects_unknown_email(client) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": "nobody@test.lawfocus", "password": "x"})
    assert resp.status_code == 401


def test_audit_events_requires_authentication(client) -> None:
    resp = client.get("/api/v1/audit-events")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHENTICATED"


def test_audit_events_rejects_insufficient_role(client, db_session) -> None:
    user = make_user_with_role(
        db_session, RbacRoleCode.READER, email="reader@test.lawfocus", password="Pass123!"
    )
    token = _login(client, "reader@test.lawfocus", "Pass123!")

    resp = client.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    from app.models import AuditEvent

    denial = (
        db_session.query(AuditEvent)
        .filter_by(actor_id=user.id, decision="DENIED", reason_code="INSUFFICIENT_ROLE")
        .one_or_none()
    )
    assert denial is not None, "the 403 must leave an audit trail, not just a status code"


def test_audit_events_allows_global_auditor_role(client, db_session) -> None:
    make_user_with_role(db_session, RbacRoleCode.AUDITOR, email="auditor@test.lawfocus", password="Pass123!")
    token = _login(client, "auditor@test.lawfocus", "Pass123!")

    resp = client.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json()["items"], list)


def test_tenant_scoped_auditor_cannot_read_a_different_tenant(client, db_session) -> None:
    tenant_a = make_tenant(db_session, code="tenant-a")
    tenant_b = make_tenant(db_session, code="tenant-b")
    make_user_with_role(
        db_session,
        RbacRoleCode.AUDITOR,
        tenant=tenant_a,
        email="scoped-auditor@test.lawfocus",
        password="Pass123!",
    )
    token = _login(client, "scoped-auditor@test.lawfocus", "Pass123!")

    own_tenant = client.get(
        f"/api/v1/audit-events?tenant_id={tenant_a.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert own_tenant.status_code == 200

    other_tenant = client.get(
        f"/api/v1/audit-events?tenant_id={tenant_b.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert other_tenant.status_code == 403
    assert other_tenant.json()["code"] == "TENANT_FORBIDDEN"


def test_invalid_token_is_rejected(client) -> None:
    resp = client.get("/api/v1/audit-events", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_TOKEN"
