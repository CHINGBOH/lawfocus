from datetime import date

from app.models import (
    Article,
    ArticleVersion,
    Concept,
    ConceptVersion,
    GraphEdge,
    GraphNode,
    LegalDocument,
    LegalVersion,
)
from app.models.enums import RbacRoleCode
from tests.factories import make_user_with_role


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(client, db_session) -> dict[str, str]:
    make_user_with_role(db_session, RbacRoleCode.READER, email="reader-rl@test.lawfocus", password="Pass123!")
    token = _login(client, "reader-rl@test.lawfocus", "Pass123!")
    return {"Authorization": f"Bearer {token}"}


def _seed_reading_fixture(db_session):
    document = LegalDocument(code="RL-LAW", name="阅读闭环测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()

    v1 = LegalVersion(
        document_id=document.id,
        version_name="v1",
        effective_from=date(2020, 1, 1),
        effective_to=date(2024, 7, 1),
        status="SUPERSEDED",
    )
    v2 = LegalVersion(
        document_id=document.id,
        version_name="v2",
        effective_from=date(2024, 7, 1),
        effective_to=None,
        status="ACTIVE",
    )
    db_session.add_all([v1, v2])
    db_session.flush()

    article = Article(document_id=document.id, article_no="1")
    db_session.add(article)
    db_session.flush()

    av1 = ArticleVersion(
        article_id=article.id,
        legal_version_id=v1.id,
        article_text="旧文本：上市公司应当设置董事会。",
        valid_from=date(2020, 1, 1),
        valid_to=date(2024, 7, 1),
    )
    av2 = ArticleVersion(
        article_id=article.id,
        legal_version_id=v2.id,
        article_text="上市公司应当设置董事会。",
        valid_from=date(2024, 7, 1),
        valid_to=None,
    )
    db_session.add_all([av1, av2])
    db_session.flush()

    concept = Concept(code="RL-CONCEPT-BOARD", name="董事会", concept_type="ORGAN")
    db_session.add(concept)
    db_session.flush()
    concept_version = ConceptVersion(
        concept_id=concept.id,
        definition="公司的常设决策机构。（测试定义）",
        review_status="UNVERIFIED",
        valid_from=date(2024, 7, 1),
        valid_to=None,
    )
    db_session.add(concept_version)
    db_session.flush()

    concept_node = GraphNode(
        node_type="CONCEPT",
        code=concept.code,
        name=concept.name,
        properties={"ref_table": "concept", "ref_id": str(concept.id)},
    )
    article_node = GraphNode(
        node_type="ARTICLE_VERSION",
        code=f"RL-LAW:1:{v2.id}",
        name="第1条（v2）",
        properties={"ref_table": "article_version", "ref_id": str(av2.id)},
    )
    db_session.add_all([concept_node, article_node])
    db_session.flush()
    db_session.add(
        GraphEdge(source_id=concept_node.id, relation_type="DEFINED_BY", target_id=article_node.id)
    )
    db_session.flush()

    return document, v1, v2, article, av1, av2, concept


def test_list_laws_includes_seeded_document(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    resp = client.get("/api/v1/laws", headers=headers)
    assert resp.status_code == 200
    codes = [law["code"] for law in resp.json()]
    assert "RL-LAW" in codes


def test_get_article_version_by_exact_version(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    old = client.get("/api/v1/laws/RL-LAW/versions/v1/articles/1", headers=headers)
    assert old.status_code == 200
    assert old.json()["article_text"] == "旧文本：上市公司应当设置董事会。"

    new = client.get("/api/v1/laws/RL-LAW/versions/v2/articles/1", headers=headers)
    assert new.status_code == 200
    assert new.json()["article_text"] == "上市公司应当设置董事会。"


def test_get_effective_article_version_by_date(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    resp = client.get(
        "/api/v1/laws/RL-LAW/articles/1/effective", params={"at": "2022-06-01"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["article_text"] == "旧文本：上市公司应当设置董事会。"


def test_article_not_found_returns_404_with_unified_error_shape(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    resp = client.get("/api/v1/laws/NO-SUCH-LAW/versions/v1/articles/1", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "ARTICLE_NOT_FOUND"
    assert "trace_id" in body


def test_list_law_versions_returns_both_versions_in_effective_order(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    resp = client.get("/api/v1/laws/RL-LAW/versions", headers=headers)
    assert resp.status_code == 200
    assert [v["version_name"] for v in resp.json()] == ["v1", "v2"]


def test_list_law_versions_for_unknown_law_returns_404(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    resp = client.get("/api/v1/laws/NO-SUCH-LAW/versions", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "LAW_NOT_FOUND"


def test_list_law_version_articles_returns_directory_with_summary(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    resp = client.get("/api/v1/laws/RL-LAW/versions/v2/articles", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["article_no"] == "1"
    assert body[0]["summary"].startswith("上市公司应当设置董事会")


def test_get_article_navigation_returns_current_and_neighbors(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    resp = client.get("/api/v1/laws/RL-LAW/versions/v2/articles/1/navigation", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"]["article_no"] == "1"
    assert body["current"]["article_text"] == "上市公司应当设置董事会。"
    assert body["previous_article_no"] is None
    assert body["next_article_no"] is None


def test_get_article_navigation_for_unknown_article_returns_404(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    _seed_reading_fixture(db_session)

    resp = client.get("/api/v1/laws/RL-LAW/versions/v2/articles/999/navigation", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "ARTICLE_NOT_FOUND"


def test_concept_detail_includes_definition_source(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    *_rest, av2, concept = _seed_reading_fixture(db_session)

    resp = client.get(f"/api/v1/concepts/{concept.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["definition"] == "公司的常设决策机构。（测试定义）"
    assert body["review_status"] == "UNVERIFIED"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["article_version"]["id"] == str(av2.id)


def test_concept_preview_truncates_definition(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    *_rest, concept = _seed_reading_fixture(db_session)

    resp = client.get(f"/api/v1/concepts/{concept.id}/preview", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "董事会"


def test_synthesis_tags_concept_mentions_with_concept_id(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    *_rest, av2, concept = _seed_reading_fixture(db_session)

    resp = client.get(f"/api/v1/articles/{av2.id}/synthesis", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated_by"] == "deterministic_template"
    matched = [seg for seg in body["text_segments"] if seg["concept_id"] == str(concept.id)]
    assert len(matched) == 1
    assert matched[0]["text"] == "董事会"


def test_synthesis_for_unknown_article_version_returns_404(client, db_session) -> None:
    headers = _auth_headers(client, db_session)
    import uuid

    resp = client.get(f"/api/v1/articles/{uuid.uuid4()}/synthesis", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "ARTICLE_VERSION_NOT_FOUND"
