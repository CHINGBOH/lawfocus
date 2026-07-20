"""Smoke-tier performance check per 04-MVP性能基准与容量验收方案.md §4.1:
'每次提交运行核心接口各 20 次'. This is NOT the official benchmark — that
requires the fixed large dataset and dedicated environment described in
§2/§3 of that document, which this local sandbox cannot stand up. This just
asserts nothing regresses to a pathological order-of-magnitude on a warm
local dev DB, and fails loudly (not silently) if a core endpoint errors.
"""

import time
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

ITERATIONS = 20
# Generous local-dev ceiling — NOT the official §3 SLO (which targets a much
# larger seeded dataset on dedicated hardware). This just catches a handler
# that regresses to doing something pathological (e.g. an N+1 query loop).
LOCAL_SMOKE_CEILING_SECONDS = 1.0


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_smoke_get_laws_20_times(client, db_session) -> None:
    email = f"perf-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, RbacRoleCode.READER, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    headers = {"Authorization": f"Bearer {token}"}

    durations = []
    for _ in range(ITERATIONS):
        start = time.monotonic()
        resp = client.get("/api/v1/laws", headers=headers)
        durations.append(time.monotonic() - start)
        assert resp.status_code == 200

    durations.sort()
    p95 = durations[int(ITERATIONS * 0.95) - 1]
    assert p95 < LOCAL_SMOKE_CEILING_SECONDS, f"GET /laws p95={p95:.3f}s over local smoke ceiling"


def test_smoke_compliance_check_20_times(client, db_session) -> None:
    tenant = make_tenant(db_session)
    email = f"perf-cu-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    headers = {"Authorization": f"Bearer {token}"}

    document = LegalDocument(code=f"PERF-LAW-{uuid.uuid4().hex[:6]}", name="性能烟雾测试法", document_type="LAW")
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
    rule = LegalRule(code="PERF-GOV-ORG-001", name="性能测试规则")
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status="DRAFT", subject_type="ListedCompany", modality="OBLIGATION",
        condition_expression={}, requirement_expression={},
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()

    company = LegalSubject(name="性能测试公司", subject_type=SubjectType.LISTED_COMPANY, listed=True)
    db_session.add(company)
    db_session.flush()
    db_session.add(Organization(company_id=company.id, organization_type="BOARD", name="董事会"))
    db_session.flush()

    # PERF-GOV-ORG-001 isn't in RULE_REGISTRY, so use the real GOV-ORG-001 code instead.
    rule.code = "GOV-ORG-001"
    db_session.flush()

    durations = []
    for i in range(ITERATIONS):
        start = time.monotonic()
        resp = client.post(
            "/api/v1/compliance-checks",
            headers=headers,
            json={
                "tenant_id": str(tenant.id),
                "company_id": str(company.id),
                "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
                "rule_codes": ["GOV-ORG-001"],
                "idempotency_key": f"perf-{i}-{uuid.uuid4().hex}",
            },
        )
        durations.append(time.monotonic() - start)
        assert resp.status_code == 201

    durations.sort()
    p95 = durations[int(ITERATIONS * 0.95) - 1]
    assert p95 < LOCAL_SMOKE_CEILING_SECONDS, f"POST /compliance-checks p95={p95:.3f}s over local smoke ceiling"
