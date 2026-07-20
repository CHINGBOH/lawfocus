import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Article, ArticleVersion, LegalDocument, LegalVersion


def _make_document(db_session) -> LegalDocument:
    document = LegalDocument(
        code=f"DOC-{uuid.uuid4().hex[:8]}",
        name="中华人民共和国公司法",
        document_type="LAW",
    )
    db_session.add(document)
    db_session.flush()
    return document


def _make_version(db_session, document: LegalDocument, **overrides) -> LegalVersion:
    defaults = dict(
        document_id=document.id,
        version_name="2023修订",
        effective_from=date(2024, 7, 1),
        effective_to=None,
        status="ACTIVE",
    )
    defaults.update(overrides)
    version = LegalVersion(**defaults)
    db_session.add(version)
    db_session.flush()
    return version


def test_legal_version_rejects_effective_to_before_effective_from(db_session) -> None:
    document = _make_document(db_session)
    with pytest.raises(IntegrityError):
        _make_version(
            db_session,
            document,
            effective_from=date(2024, 7, 1),
            effective_to=date(2024, 1, 1),
        )


def test_legal_version_allows_null_effective_to_as_still_active(db_session) -> None:
    document = _make_document(db_session)
    version = _make_version(db_session, document, effective_to=None)
    assert version.id is not None


def test_article_no_is_unique_per_document(db_session) -> None:
    document = _make_document(db_session)
    db_session.add(Article(document_id=document.id, article_no="108"))
    db_session.flush()
    db_session.add(Article(document_id=document.id, article_no="108"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_article_version_unique_per_article_and_legal_version(db_session) -> None:
    document = _make_document(db_session)
    version = _make_version(db_session, document)
    article = Article(document_id=document.id, article_no="108")
    db_session.add(article)
    db_session.flush()

    db_session.add(
        ArticleVersion(
            article_id=article.id,
            legal_version_id=version.id,
            article_text="董事会成员为九人以上……",
            valid_from=date(2024, 7, 1),
            valid_to=None,
        )
    )
    db_session.flush()

    db_session.add(
        ArticleVersion(
            article_id=article.id,
            legal_version_id=version.id,
            article_text="duplicate binding should be rejected",
            valid_from=date(2024, 7, 1),
            valid_to=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
