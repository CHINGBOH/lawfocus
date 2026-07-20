from datetime import date

import pytest

from app.models import Article, ArticleVersion, LegalDocument, LegalVersion
from app.services.legal_repository_service import (
    ArticleNotFoundError,
    LawNotFoundError,
    LegalRepositoryService,
)


@pytest.fixture
def seeded_document(db_session):
    document = LegalDocument(code="TEST-LAW", name="测试法", document_type="LAW")
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

    article = Article(document_id=document.id, article_no="108")
    db_session.add(article)
    db_session.flush()

    db_session.add_all(
        [
            ArticleVersion(
                article_id=article.id,
                legal_version_id=v1.id,
                article_text="旧文本",
                valid_from=date(2020, 1, 1),
                valid_to=date(2024, 7, 1),
            ),
            ArticleVersion(
                article_id=article.id,
                legal_version_id=v2.id,
                article_text="新文本",
                valid_from=date(2024, 7, 1),
                valid_to=None,
            ),
        ]
    )
    db_session.flush()
    return document


def test_selects_the_version_effective_at_the_given_date(db_session, seeded_document) -> None:
    service = LegalRepositoryService(db_session)

    old = service.get_effective_article_version("TEST-LAW", "108", date(2022, 6, 1))
    assert old.article_text == "旧文本"

    new = service.get_effective_article_version("TEST-LAW", "108", date(2025, 1, 1))
    assert new.article_text == "新文本"


def test_boundary_date_selects_the_new_version_half_open(db_session, seeded_document) -> None:
    service = LegalRepositoryService(db_session)
    boundary = service.get_effective_article_version("TEST-LAW", "108", date(2024, 7, 1))
    assert boundary.article_text == "新文本"  # valid_from is inclusive on the new version


def test_raises_when_no_version_covers_the_date(db_session, seeded_document) -> None:
    service = LegalRepositoryService(db_session)
    with pytest.raises(ArticleNotFoundError):
        service.get_effective_article_version("TEST-LAW", "108", date(2019, 1, 1))


def test_raises_for_unknown_article_rather_than_guessing(db_session, seeded_document) -> None:
    service = LegalRepositoryService(db_session)
    with pytest.raises(ArticleNotFoundError):
        service.get_effective_article_version("TEST-LAW", "999", date(2025, 1, 1))


@pytest.fixture
def multi_article_document(db_session):
    """Article numbers '1', '2', '10' — a plain string sort would order these
    '1', '10', '2', which would silently corrupt directory order and
    prev/next chaining for any real law with more than 9 articles."""
    document = LegalDocument(code="MULTI-LAW", name="多条测试法", document_type="LAW")
    db_session.add(document)
    db_session.flush()

    v1 = LegalVersion(
        document_id=document.id,
        version_name="v1",
        effective_from=date(2024, 1, 1),
        effective_to=None,
        status="ACTIVE",
    )
    db_session.add(v1)
    db_session.flush()

    articles = [Article(document_id=document.id, article_no=no) for no in ["10", "1", "2"]]
    db_session.add_all(articles)
    db_session.flush()

    db_session.add_all(
        [
            ArticleVersion(
                article_id=a.id,
                legal_version_id=v1.id,
                chapter_no="第一章",
                article_text=f"第{a.article_no}条正文。",
                valid_from=date(2024, 1, 1),
                valid_to=None,
            )
            for a in articles
        ]
    )
    db_session.flush()
    return document, v1


def test_list_versions_for_document_returns_versions_in_effective_order(
    db_session, seeded_document
) -> None:
    service = LegalRepositoryService(db_session)
    versions = service.list_versions_for_document("TEST-LAW")
    assert [v.version_name for v in versions] == ["v1", "v2"]


def test_list_versions_for_unknown_law_raises(db_session) -> None:
    service = LegalRepositoryService(db_session)
    with pytest.raises(LawNotFoundError):
        service.list_versions_for_document("NO-SUCH-LAW")


def test_article_directory_is_sorted_numerically_not_lexicographically(
    db_session, multi_article_document
) -> None:
    document, v1 = multi_article_document
    service = LegalRepositoryService(db_session)
    directory = service.list_article_directory("MULTI-LAW", "v1")
    assert [av.article_no for av in directory] == ["1", "2", "10"]


def test_article_directory_for_unknown_law_raises(db_session) -> None:
    service = LegalRepositoryService(db_session)
    with pytest.raises(LawNotFoundError):
        service.list_article_directory("NO-SUCH-LAW", "v1")


def test_navigation_returns_numeric_neighbors(db_session, multi_article_document) -> None:
    document, v1 = multi_article_document
    service = LegalRepositoryService(db_session)

    current, previous_no, next_no = service.get_article_navigation("MULTI-LAW", "v1", "2")
    assert current.article_no == "2"
    assert previous_no == "1"
    assert next_no == "10"


def test_navigation_has_no_previous_at_the_first_article(db_session, multi_article_document) -> None:
    service = LegalRepositoryService(db_session)
    _current, previous_no, next_no = service.get_article_navigation("MULTI-LAW", "v1", "1")
    assert previous_no is None
    assert next_no == "2"


def test_navigation_has_no_next_at_the_last_article(db_session, multi_article_document) -> None:
    service = LegalRepositoryService(db_session)
    _current, previous_no, next_no = service.get_article_navigation("MULTI-LAW", "v1", "10")
    assert previous_no == "2"
    assert next_no is None


def test_navigation_raises_for_unknown_article(db_session, multi_article_document) -> None:
    service = LegalRepositoryService(db_session)
    with pytest.raises(ArticleNotFoundError):
        service.get_article_navigation("MULTI-LAW", "v1", "999")


@pytest.fixture
def dotted_hierarchical_document(db_session):
    """Article numbers '4.4.1', '4.4.2', '4.4.10' — exchange listing rules'
    dotted numbering. A sort key that only reads the leading integer would
    put '4.4.10' before '4.4.2' (confirmed against real imported
    SSE-LIST-2026 data, where this ordering bug was first caught)."""
    document = LegalDocument(code="DOTTED-LAW", name="层级编号测试规则", document_type="EXCHANGE_RULE")
    db_session.add(document)
    db_session.flush()

    v1 = LegalVersion(
        document_id=document.id,
        version_name="v1",
        effective_from=date(2024, 1, 1),
        effective_to=None,
        status="ACTIVE",
    )
    db_session.add(v1)
    db_session.flush()

    articles = [
        Article(document_id=document.id, article_no=no) for no in ["4.4.10", "4.4.1", "4.4.2"]
    ]
    db_session.add_all(articles)
    db_session.flush()

    db_session.add_all(
        [
            ArticleVersion(
                article_id=a.id,
                legal_version_id=v1.id,
                chapter_no="第四章",
                article_text=f"{a.article_no} 正文。",
                valid_from=date(2024, 1, 1),
                valid_to=None,
            )
            for a in articles
        ]
    )
    db_session.flush()
    return document, v1


def test_article_directory_sorts_dotted_hierarchical_numbers_numerically(
    db_session, dotted_hierarchical_document
) -> None:
    service = LegalRepositoryService(db_session)
    directory = service.list_article_directory("DOTTED-LAW", "v1")
    assert [av.article_no for av in directory] == ["4.4.1", "4.4.2", "4.4.10"]
