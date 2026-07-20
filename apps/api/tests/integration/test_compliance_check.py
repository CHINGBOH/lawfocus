import uuid
from datetime import UTC, date, datetime

from app.models import (
    Article,
    ArticleVersion,
    Fact,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    LegalVersion,
    Organization,
    RoleAssignment,
    RoleType,
    RuleSource,
)
from app.models.enums import RbacRoleCode, SubjectType
from tests.factories import demo_requirement_expression, make_tenant, make_user_with_role


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


def _register_rule(db_session, code: str, article_version: ArticleVersion) -> None:
    rule = LegalRule(code=code, name=code)
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id,
        version_no=1,
        status="DRAFT",
        subject_type="ListedCompany",
        modality="OBLIGATION",
        condition_expression={},
        requirement_expression=demo_requirement_expression(code),
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(
        RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id)
    )
    db_session.flush()


def _base_fixture(db_session):
    tenant = make_tenant(db_session, code=f"cc-tenant-{uuid.uuid4().hex[:6]}")

    document = LegalDocument(code=f"CC-LAW-{uuid.uuid4().hex[:6]}", name="合规检查测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()
    version = LegalVersion(
        document_id=document.id, version_name="v1", effective_from=date(2024, 1, 1), effective_to=None, status="ACTIVE"
    )
    db_session.add(version)
    db_session.flush()
    article = Article(document_id=document.id, article_no="1")
    db_session.add(article)
    db_session.flush()
    article_version = ArticleVersion(
        article_id=article.id,
        legal_version_id=version.id,
        article_text="测试条文",
        valid_from=date(2024, 1, 1),
        valid_to=None,
    )
    db_session.add(article_version)
    db_session.flush()

    for code in [
        "GOV-ORG-001",
        "GOV-AUD-001",
        "GOV-ID-001",
        "GOV-ID-002",
        "GOV-AUD-002",
        "GOV-AUD-003",
        "GOV-AUD-004",
        "GOV-ROLE-001",
        "GOV-TIME-001",
        "GOV-CTRL-001",
    ]:
        _register_rule(db_session, code, article_version)

    role_types = {}
    for code in ["DIRECTOR", "INDEPENDENT_DIRECTOR", "AUDIT_COMMITTEE_MEMBER", "AUDIT_COMMITTEE_CONVENOR"]:
        rt = RoleType(code=code, name=code)
        db_session.add(rt)
        db_session.flush()
        role_types[code] = rt

    return tenant, role_types


def _make_company(db_session, *, listed: bool = True) -> LegalSubject:
    company = LegalSubject(
        name=f"测试公司-{uuid.uuid4().hex[:6]}",
        subject_type=SubjectType.LISTED_COMPANY if listed else SubjectType.COMPANY,
        listed=listed,
    )
    db_session.add(company)
    db_session.flush()
    return company


def _run_check(client, headers, tenant_id, company_id, rule_codes, idem_key=None):
    return client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": rule_codes,
            "idempotency_key": idem_key or f"idem-{uuid.uuid4().hex}",
        },
    )


def test_true_compliant_board_and_director_ratio(client, db_session) -> None:
    tenant, role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)

    board = Organization(company_id=company.id, organization_type="BOARD", name="董事会")
    db_session.add(board)
    db_session.flush()
    for i in range(9):
        role_type = role_types["INDEPENDENT_DIRECTOR"] if i < 3 else role_types["DIRECTOR"]
        person = LegalSubject(name=f"董事{i}", subject_type=SubjectType.PERSON)
        db_session.add(person)
        db_session.flush()
        db_session.add(
            RoleAssignment(
                person_id=person.id,
                role_type_id=role_type.id,
                company_id=company.id,
                organization_id=board.id,
                valid_from=date(2024, 1, 1),
                valid_to=None,
            )
        )
    db_session.flush()

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001", "GOV-ROLE-001", "GOV-TIME-001"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    statuses = {c["rule_version_id"]: c["result_status"] for c in body["conclusions"]}
    assert set(statuses.values()) == {"TRUE"}
    assert body["status"] == "COMPLETED"


def test_false_missing_board(client, db_session) -> None:
    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)  # no Organization rows at all

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001"])
    assert resp.status_code == 201
    assert resp.json()["conclusions"][0]["result_status"] == "FALSE"


def test_unknown_when_no_board_composition_fact(client, db_session) -> None:
    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ID-001"])
    assert resp.status_code == 201
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "UNKNOWN"
    assert "BOARD_COMPOSITION.independent_director_count" in conclusion["missing_facts"]


def test_conflict_when_two_unretracted_facts_disagree(client, db_session) -> None:
    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)

    db_session.add_all(
        [
            Fact(
                tenant_id=tenant.id,
                company_id=company.id,
                fact_type="BOARD_COMPOSITION",
                predicate="independent_director_count",
                object_value={"total": 5, "independent": 1},
                valid_from=date(2025, 1, 1),
                valid_to=None,
            ),
            Fact(
                tenant_id=tenant.id,
                company_id=company.id,
                fact_type="BOARD_COMPOSITION",
                predicate="independent_director_count",
                object_value={"total": 5, "independent": 2},
                valid_from=date(2025, 1, 1),
                valid_to=None,
            ),
        ]
    )
    db_session.flush()

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ID-002"])
    assert resp.status_code == 201
    assert resp.json()["conclusions"][0]["result_status"] == "CONFLICT"


def test_not_applicable_for_non_listed_company(client, db_session) -> None:
    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session, listed=False)

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001"])
    assert resp.status_code == 201
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "NOT_APPLICABLE"
    assert conclusion["excluded_reason"]


def test_compliance_check_is_idempotent(client, db_session) -> None:
    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)
    key = f"idem-fixed-{uuid.uuid4().hex}"

    first = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001"], idem_key=key)
    second = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001"], idem_key=key)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_proof_chain_is_retrievable(client, db_session) -> None:
    tenant, _role_types = _base_fixture(db_session)
    headers = _compliance_user_headers(client, db_session, tenant)
    company = _make_company(db_session)

    resp = _run_check(client, headers, tenant.id, company.id, ["GOV-ORG-001"])
    conclusion_id = resp.json()["conclusions"][0]["id"]

    proof_resp = client.get(f"/api/v1/conclusions/{conclusion_id}/proof", headers=headers)
    assert proof_resp.status_code == 200
    body = proof_resp.json()
    assert len(body["steps"]) >= 1
    assert body["steps"][0]["step_type"] == "ORGAN_LOOKUP"


def test_compliance_check_requires_tenant_access(client, db_session) -> None:
    tenant_a, _role_types = _base_fixture(db_session)
    tenant_b = make_tenant(db_session, code=f"cc-tenant-b-{uuid.uuid4().hex[:6]}")
    headers = _compliance_user_headers(client, db_session, tenant_a)
    company = _make_company(db_session)

    resp = _run_check(client, headers, tenant_b.id, company.id, ["GOV-ORG-001"])
    assert resp.status_code == 403
    assert resp.json()["code"] == "TENANT_FORBIDDEN"
