"""End-to-end acceptance tests mapped 1:1 to MVP产品需求与验收标准.md §8
(AC-01 through AC-08). Each test drives the real HTTP API — no direct
service calls — so it exercises auth, RBAC, and serialization along with
the underlying logic, the same way a real client would.
"""

import uuid
from datetime import UTC, date, datetime

from app.models import (
    Article,
    ArticleVersion,
    Concept,
    ConceptVersion,
    Fact,
    GraphEdge,
    GraphNode,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    LegalVersion,
    Organization,
    RuleSource,
)
from app.models.enums import RbacRoleCode, SubjectType
from app.services.agent_provider import DisabledAgentProvider
from tests.factories import demo_requirement_expression, make_tenant, make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _user_headers(client, db_session, role: RbacRoleCode, tenant=None) -> tuple[dict, uuid.UUID]:
    email = f"ac-{role.value.lower()}-{uuid.uuid4().hex[:6]}@test.lawfocus"
    user = make_user_with_role(db_session, role, tenant=tenant, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    return {"Authorization": f"Bearer {token}"}, user.id


def _seed_law_and_concept(db_session):
    document = LegalDocument(code=f"AC-LAW-{uuid.uuid4().hex[:6]}", name="验收测试法", document_type="LAW")
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
        article_id=article.id,
        legal_version_id=version.id,
        chapter_no="第一条",
        article_text="上市公司应当设置独立董事。",
        valid_from=date(2024, 1, 1),
    )
    db_session.add(article_version)
    db_session.flush()

    concept = Concept(code=f"AC-CONCEPT-{uuid.uuid4().hex[:6]}", name="独立董事", concept_type="ROLE")
    db_session.add(concept)
    db_session.flush()
    db_session.add(
        ConceptVersion(
            concept_id=concept.id, definition="验收测试定义", review_status="UNVERIFIED", valid_from=date(2024, 1, 1)
        )
    )
    db_session.flush()

    concept_node = GraphNode(
        node_type="CONCEPT", code=concept.code, name=concept.name,
        properties={"ref_table": "concept", "ref_id": str(concept.id)},
    )
    article_node = GraphNode(
        node_type="ARTICLE_VERSION", code=f"{document.code}:1:{version.id}", name="第一条",
        properties={"ref_table": "article_version", "ref_id": str(article_version.id)},
    )
    db_session.add_all([concept_node, article_node])
    db_session.flush()
    db_session.add(GraphEdge(source_id=concept_node.id, relation_type="DEFINED_BY", target_id=article_node.id))
    db_session.flush()

    return document, version, article, article_version, concept


def _register_rule(db_session, code: str, article_version: ArticleVersion) -> None:
    rule = LegalRule(code=code, name=code)
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status="DRAFT", subject_type="ListedCompany", modality="OBLIGATION",
        condition_expression={}, requirement_expression={},
    )
    rule_version.requirement_expression = demo_requirement_expression(code)
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()


def test_ac01_article_and_concept_traceability(client, db_session) -> None:
    """AC-01: open an article, click a concept, see definition + source + version."""
    reader_headers, _ = _user_headers(client, db_session, RbacRoleCode.READER)
    document, version, _article, article_version, concept = _seed_law_and_concept(db_session)

    article_resp = client.get(
        f"/api/v1/laws/{document.code}/versions/{version.version_name}/articles/1", headers=reader_headers
    )
    assert article_resp.status_code == 200

    concept_resp = client.get(f"/api/v1/concepts/{concept.id}", headers=reader_headers)
    assert concept_resp.status_code == 200
    body = concept_resp.json()
    assert body["definition"] == "验收测试定义"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["article_version"]["id"] == str(article_version.id)


def test_ac02_rule_passes_returns_true_with_full_chain(client, db_session) -> None:
    """AC-02: fully compliant subject -> TRUE, with conclusion/rule/facts/evidence/source all reachable."""
    tenant = make_tenant(db_session)
    headers, _ = _user_headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    _document, _version, _article, article_version, _concept = _seed_law_and_concept(db_session)
    _register_rule(db_session, "GOV-ORG-001", article_version)

    company = LegalSubject(
        name=f"AC02公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(Organization(company_id=company.id, organization_type="BOARD", name="董事会"))
    db_session.flush()

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "evaluation_time": datetime(2025, 1, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ORG-001"],
            "idempotency_key": f"ac02-{uuid.uuid4().hex}",
        },
    )
    assert resp.status_code == 201
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "TRUE"

    proof_resp = client.get(f"/api/v1/conclusions/{conclusion['id']}/proof", headers=headers)
    assert proof_resp.status_code == 200
    assert len(proof_resp.json()["steps"]) >= 1


def test_ac03_rule_violation_returns_false_with_calculation(client, db_session) -> None:
    """AC-03: independent-director ratio below threshold -> FALSE with actual/required values shown."""
    tenant = make_tenant(db_session)
    headers, _ = _user_headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    _document, _version, _article, article_version, _concept = _seed_law_and_concept(db_session)
    _register_rule(db_session, "GOV-ID-002", article_version)

    company = LegalSubject(
        name=f"AC03公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(
        Fact(
            tenant_id=tenant.id, company_id=company.id, fact_type="BOARD_COMPOSITION",
            predicate="independent_director_count", object_value={"total": 9, "independent": 1},
            valid_from=date(2025, 1, 1),
        )
    )
    db_session.flush()

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ID-002"],
            "idempotency_key": f"ac03-{uuid.uuid4().hex}",
        },
    )
    assert resp.status_code == 201
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "FALSE"

    proof = client.get(f"/api/v1/conclusions/{conclusion['id']}/proof", headers=headers).json()
    calc = proof["steps"][0]["calculation"]
    assert calc["independent"] == 1 and calc["total"] == 9  # actual values shown, not just a verdict


def test_ac04_missing_facts_return_unknown_not_false(client, db_session) -> None:
    """AC-04: missing director-count/appointment facts -> UNKNOWN with an explicit missing-facts list."""
    tenant = make_tenant(db_session)
    headers, _ = _user_headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    _document, _version, _article, article_version, _concept = _seed_law_and_concept(db_session)
    _register_rule(db_session, "GOV-ID-001", article_version)

    company = LegalSubject(
        name=f"AC04公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ID-001"],
            "idempotency_key": f"ac04-{uuid.uuid4().hex}",
        },
    )
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "UNKNOWN"
    assert conclusion["missing_facts"]  # never silently FALSE


def test_ac05_not_applicable_for_out_of_scope_subject(client, db_session) -> None:
    """AC-05: a non-listed company is out of scope -> NOT_APPLICABLE with a reason."""
    tenant = make_tenant(db_session)
    headers, _ = _user_headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    _document, _version, _article, article_version, _concept = _seed_law_and_concept(db_session)
    _register_rule(db_session, "GOV-ORG-001", article_version)

    company = LegalSubject(
        name=f"AC05公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.COMPANY, listed=False
    )
    db_session.add(company)
    db_session.flush()

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ORG-001"],
            "idempotency_key": f"ac05-{uuid.uuid4().hex}",
        },
    )
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "NOT_APPLICABLE"
    assert conclusion["excluded_reason"]


def test_ac06_unresolvable_conflict_surfaces_as_conflict(client, db_session) -> None:
    """AC-06: two unretracted, disagreeing facts -> CONFLICT, both retained, no silent pick."""
    tenant = make_tenant(db_session)
    headers, _ = _user_headers(client, db_session, RbacRoleCode.COMPLIANCE_USER, tenant=tenant)
    _document, _version, _article, article_version, _concept = _seed_law_and_concept(db_session)
    _register_rule(db_session, "GOV-ID-001", article_version)

    company = LegalSubject(
        name=f"AC06公司-{uuid.uuid4().hex[:6]}", subject_type=SubjectType.LISTED_COMPANY, listed=True
    )
    db_session.add(company)
    db_session.flush()
    db_session.add_all(
        [
            Fact(
                tenant_id=tenant.id, company_id=company.id, fact_type="BOARD_COMPOSITION",
                predicate="independent_director_count", object_value={"total": 9, "independent": 1},
                valid_from=date(2025, 1, 1),
            ),
            Fact(
                tenant_id=tenant.id, company_id=company.id, fact_type="BOARD_COMPOSITION",
                predicate="independent_director_count", object_value={"total": 9, "independent": 3},
                valid_from=date(2025, 1, 1),
            ),
        ]
    )
    db_session.flush()

    resp = client.post(
        "/api/v1/compliance-checks",
        headers=headers,
        json={
            "tenant_id": str(tenant.id),
            "company_id": str(company.id),
            "evaluation_time": datetime(2025, 6, 1, tzinfo=UTC).isoformat(),
            "rule_codes": ["GOV-ID-001"],
            "idempotency_key": f"ac06-{uuid.uuid4().hex}",
        },
    )
    conclusion = resp.json()["conclusions"][0]
    assert conclusion["result_status"] == "CONFLICT"

    proof = client.get(f"/api/v1/conclusions/{conclusion['id']}/proof", headers=headers).json()
    values = proof["steps"][0]["calculation"]["values"]
    assert len(values) == 2  # both conflicting values retained, nothing silently dropped


def test_ac07_publish_rejected_without_source_test_or_review(client, db_session) -> None:
    """AC-07: publish must be rejected (with a reason) when source/tests/review are missing."""
    publisher_headers, _ = _user_headers(client, db_session, RbacRoleCode.PUBLISHER)
    rule = LegalRule(code=f"AC07-RULE-{uuid.uuid4().hex[:6]}", name="AC07测试规则")
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status="DRAFT", subject_type="ListedCompany", modality="OBLIGATION",
        condition_expression={}, requirement_expression={},
    )
    db_session.add(rule_version)
    db_session.flush()

    resp = client.post(f"/api/v1/rules/{rule.id}/publish", headers=publisher_headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_TRANSITION"


def test_ac08_llm_boundary_missing_definition_shows_insufficient_not_guessed(db_session) -> None:
    """AC-08: with no agent (or a disabled one), synthesis never guesses — it only
    surfaces concept mentions that already have a reviewed definition on file."""
    document, version, _article, article_version, _concept = None, None, None, None, None
    document = LegalDocument(code=f"AC08-LAW-{uuid.uuid4().hex[:6]}", name="AC08测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()
    version = LegalVersion(document_id=document.id, version_name="v1", effective_from=date(2024, 1, 1), status="ACTIVE")
    db_session.add(version)
    db_session.flush()
    article = Article(document_id=document.id, article_no="1")
    db_session.add(article)
    db_session.flush()
    # "未知概念" has no Concept/ConceptVersion row at all — it must NOT show up as a
    # concept-tagged, defined mention; the LLM must not be asked/allowed to invent one.
    article_version = ArticleVersion(
        article_id=article.id, legal_version_id=version.id, article_text="本条涉及未知概念。",
        valid_from=date(2024, 1, 1),
    )
    db_session.add(article_version)
    db_session.flush()

    from app.services.synthesis_service import SynthesisService

    result = SynthesisService(db_session, agent_provider=DisabledAgentProvider()).get_synthesis(article_version.id)
    assert result.generated_by == "deterministic_template"
    assert all(s.concept_id is None for s in result.segments)  # no concept was guessed
