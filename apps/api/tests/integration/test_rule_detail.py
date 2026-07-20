"""F3: GET /rules/{rule_id} detail — needed so the proof-chain page can jump
from a conclusion's rule_version_id to the rule and, from there, to its
cited article version (06-MVP骨架充实与功能闭环计划.md §4.5)."""

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
    RuleTestCase,
)
from app.models.enums import RbacRoleCode
from tests.factories import make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_get_rule_detail_includes_source_article(client, db_session) -> None:
    email = f"reader-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, RbacRoleCode.READER, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")
    headers = {"Authorization": f"Bearer {token}"}

    document = LegalDocument(code=f"RD-LAW-{uuid.uuid4().hex[:6]}", name="规则详情测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()
    version = LegalVersion(document_id=document.id, version_name="v1", effective_from=date(2024, 1, 1), status="ACTIVE")
    db_session.add(version)
    db_session.flush()
    article = Article(document_id=document.id, article_no="1")
    db_session.add(article)
    db_session.flush()
    article_version = ArticleVersion(
        article_id=article.id, legal_version_id=version.id, article_text="测试条文内容", valid_from=date(2024, 1, 1)
    )
    db_session.add(article_version)
    db_session.flush()

    rule = LegalRule(code=f"RD-RULE-{uuid.uuid4().hex[:6]}", name="规则详情测试规则")
    db_session.add(rule)
    db_session.flush()
    rule_version = LegalRuleVersion(
        rule_id=rule.id, version_no=1, status="DRAFT", subject_type="ListedCompany", modality="OBLIGATION",
        condition_expression={}, requirement_expression={},
    )
    db_session.add(rule_version)
    db_session.flush()
    db_session.add(RuleSource(rule_version_id=rule_version.id, article_version_id=article_version.id))
    db_session.add(
        RuleTestCase(
            rule_version_id=rule_version.id, case_type="PASS", expected_status="TRUE", input_facts={}
        )
    )
    db_session.flush()

    resp = client.get(f"/api/v1/rules/{rule.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == rule.code
    assert body["latest_version"]["status"] == "DRAFT"
    assert len(body["latest_version"]["sources"]) == 1
    assert body["latest_version"]["sources"][0]["article_version"]["article_text"] == "测试条文内容"
    assert len(body["latest_version"]["test_cases"]) == 1
    assert body["latest_version"]["test_cases"][0]["case_type"] == "PASS"
    assert body["latest_version"]["review_decisions"] == []


def test_get_rule_detail_404_for_unknown_rule(client, db_session) -> None:
    email = f"reader-{uuid.uuid4().hex[:6]}@test.lawfocus"
    make_user_with_role(db_session, RbacRoleCode.READER, email=email, password="Pass123!")
    token = _login(client, email, "Pass123!")

    resp = client.get(f"/api/v1/rules/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "RULE_NOT_FOUND"
