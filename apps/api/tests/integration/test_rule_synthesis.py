from datetime import date

from app.models import (
    Article,
    ArticleVersion,
    Concept,
    ConceptVersion,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalVersion,
    RuleSource,
)
from app.models.enums import RbacRoleCode, ReviewStatus
from tests.factories import make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(client, db_session) -> dict[str, str]:
    make_user_with_role(db_session, RbacRoleCode.READER, email="reader-rs@test.lawfocus", password="Pass123!")
    token = _login(client, "reader-rs@test.lawfocus", "Pass123!")
    return {"Authorization": f"Bearer {token}"}


def _seed_article(db_session, article_no: str = "1") -> ArticleVersion:
    document = LegalDocument(code="RS-LAW", name="规则综合测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()

    version = LegalVersion(
        document_id=document.id, version_name="v1", effective_from=date(2024, 1, 1), status="ACTIVE"
    )
    db_session.add(version)
    db_session.flush()

    article = Article(document_id=document.id, article_no=article_no)
    db_session.add(article)
    db_session.flush()

    article_version = ArticleVersion(
        article_id=article.id,
        legal_version_id=version.id,
        article_text="审计委员会成员为三名以上。",
        valid_from=date(2024, 1, 1),
    )
    db_session.add(article_version)
    db_session.flush()

    for code, name in [
        ("RS-CONCEPT-AUDIT-COMMITTEE", "审计委员会"),
        ("RS-CONCEPT-LISTED-COMPANY", "上市公司"),
    ]:
        concept = Concept(code=code, name=name, concept_type="ORGAN")
        db_session.add(concept)
        db_session.flush()
        db_session.add(
            ConceptVersion(
                concept_id=concept.id,
                definition="测试定义。",
                review_status="UNVERIFIED",
                valid_from=date(2024, 1, 1),
            )
        )
    db_session.flush()

    return article_version


def _bind_rule(
    db_session,
    article_version: ArticleVersion,
    *,
    requirement_expression: dict,
    status: ReviewStatus = ReviewStatus.PUBLISHED,
    modality: str = "OBLIGATION",
    subject_type: str | None = "ListedCompany",
    exception_expression: dict | None = None,
    rule_code: str = "RS-RULE-001",
) -> LegalRuleVersion:
    rule = LegalRule(code=rule_code, name="审计委员会成员构成测试规则")
    db_session.add(rule)
    db_session.flush()

    rule_version = LegalRuleVersion(
        rule_id=rule.id,
        version_no=1,
        status=status,
        subject_type=subject_type,
        modality=modality,
        requirement_expression=requirement_expression,
        exception_expression=exception_expression or {},
    )
    db_session.add(rule_version)
    db_session.flush()

    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.flush()
    return rule_version


def test_rule_synthesis_404_when_no_rule_bound(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    article_version = _seed_article(db_session)

    resp = client.get(f"/api/v1/articles/{article_version.id}/rule-synthesis", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "RULE_SYNTHESIS_NOT_AVAILABLE"


def test_rule_synthesis_404_when_bound_rule_is_not_published(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    article_version = _seed_article(db_session)
    _bind_rule(
        db_session,
        article_version,
        requirement_expression={"operator": "gte", "value": 3, "unit": "person"},
        status=ReviewStatus.DRAFT,
    )

    resp = client.get(f"/api/v1/articles/{article_version.id}/rule-synthesis", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "RULE_SYNTHESIS_NOT_AVAILABLE"


def test_rule_synthesis_404_when_requirement_expression_is_unrenderable(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    article_version = _seed_article(db_session)
    # A placeholder/demo requirement_expression (not a real gte/ratio shape) must
    # not be guessed into prose — this is the same shape GOV-CTRL-001 and the
    # unbound demo rules use today.
    _bind_rule(db_session, article_version, requirement_expression={"demo": True})

    resp = client.get(f"/api/v1/articles/{article_version.id}/rule-synthesis", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "RULE_SYNTHESIS_NOT_AVAILABLE"


def test_rule_synthesis_renders_threshold_requirement_with_concept_tags(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    article_version = _seed_article(db_session)
    _bind_rule(
        db_session,
        article_version,
        requirement_expression={"operator": "gte", "value": 3, "unit": "person"},
        rule_code="RS-RULE-THRESHOLD",
    )

    resp = client.get(f"/api/v1/articles/{article_version.id}/rule-synthesis", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rule_code"] == "RS-RULE-THRESHOLD"
    assert body["generated_by"] == "deterministic_rule_template"

    full_text = "".join(seg["text"] for seg in body["text_segments"])
    assert "上市公司" in full_text
    assert "义务性规范" in full_text
    assert "不少于3人" in full_text
    assert "RS-RULE-THRESHOLD" in full_text

    concept_segments = [seg for seg in body["text_segments"] if seg["concept_id"] is not None]
    assert any(seg["text"] == "审计委员会" for seg in concept_segments)
    assert any(seg["text"] == "上市公司" for seg in concept_segments)


def test_rule_synthesis_renders_ratio_requirement(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    article_version = _seed_article(db_session)
    _bind_rule(
        db_session,
        article_version,
        requirement_expression={"operator": "gte_ratio", "numerator": 1, "denominator": 2},
        rule_code="RS-RULE-RATIO",
    )

    resp = client.get(f"/api/v1/articles/{article_version.id}/rule-synthesis", headers=headers)
    assert resp.status_code == 200
    full_text = "".join(seg["text"] for seg in resp.json()["text_segments"])
    assert "占比不低于1/2" in full_text


def test_rule_synthesis_notes_recorded_exceptions(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    article_version = _seed_article(db_session)
    _bind_rule(
        db_session,
        article_version,
        requirement_expression={"operator": "gte", "value": 3, "unit": "person"},
        exception_expression={"reason": "test exception"},
        rule_code="RS-RULE-EXCEPTION",
    )

    resp = client.get(f"/api/v1/articles/{article_version.id}/rule-synthesis", headers=headers)
    assert resp.status_code == 200
    full_text = "".join(seg["text"] for seg in resp.json()["text_segments"])
    assert "例外情形" in full_text


def test_rule_synthesis_for_unknown_article_version_returns_404(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    import uuid

    resp = client.get(f"/api/v1/articles/{uuid.uuid4()}/rule-synthesis", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "ARTICLE_VERSION_NOT_FOUND"
