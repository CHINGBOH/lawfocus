import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, ArticleVersion, LegalDocument, LegalVersion

_NUMERIC_COMPONENT = re.compile(r"\d+|\D+")


def _article_sort_key(article_no: str) -> tuple[int | str, ...]:
    """Numeric-aware ordering for article numbers stored as strings. A plain
    string sort would put '108' before '2' (company law) and, worse, would
    put dotted hierarchical numbers like '4.4.10' before '4.4.2' (exchange
    listing rules — confirmed against real imported SSE-LIST-2026 data,
    where this ordering bug was first caught). Splits on digit/non-digit
    runs and compares each numeric run as an int, so '4.4.2' < '4.4.10'."""
    parts: list[int | str] = []
    for chunk in _NUMERIC_COMPONENT.findall(article_no):
        parts.append(int(chunk) if chunk.isdigit() else chunk)
    return tuple(parts)


class ArticleNotFoundError(Exception):
    pass


class LawNotFoundError(Exception):
    pass


class LegalRepositoryService:
    """Version selection for the reading loop — never guesses: if no version
    covers the requested date, callers get ArticleNotFoundError rather than
    a nearest-match, since a wrong article version would be an invented fact.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_effective_article_version(
        self, document_code: str, article_no: str, at: date
    ) -> ArticleVersion:
        stmt = (
            select(ArticleVersion)
            .join(Article, ArticleVersion.article_id == Article.id)
            .join(LegalDocument, Article.document_id == LegalDocument.id)
            .where(
                LegalDocument.code == document_code,
                Article.article_no == article_no,
                ArticleVersion.valid_from <= at,
            )
            .where((ArticleVersion.valid_to.is_(None)) | (ArticleVersion.valid_to > at))
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result is None:
            raise ArticleNotFoundError(
                f"no effective version of {document_code} {article_no} at {at.isoformat()}"
            )
        return result

    def list_article_versions_for_document(
        self, document_code: str, legal_version_name: str
    ) -> list[ArticleVersion]:
        stmt = (
            select(ArticleVersion)
            .join(Article, ArticleVersion.article_id == Article.id)
            .join(LegalDocument, Article.document_id == LegalDocument.id)
            .join(LegalVersion, ArticleVersion.legal_version_id == LegalVersion.id)
            .where(
                LegalDocument.code == document_code,
                LegalVersion.version_name == legal_version_name,
            )
        )
        results = list(self.session.execute(stmt).scalars().all())
        results.sort(key=lambda av: _article_sort_key(av.article_no))
        return results

    def list_versions_for_document(self, document_code: str) -> list[LegalVersion]:
        stmt = (
            select(LegalVersion)
            .join(LegalDocument, LegalVersion.document_id == LegalDocument.id)
            .where(LegalDocument.code == document_code)
            .order_by(LegalVersion.effective_from)
        )
        results = list(self.session.execute(stmt).scalars().all())
        if not results:
            raise LawNotFoundError(f"no law {document_code}")
        return results

    def list_article_directory(
        self, document_code: str, legal_version_name: str
    ) -> list[ArticleVersion]:
        """Full chapter/article listing for one law version — the reader's
        left-nav tree. Raises if the law/version itself doesn't exist, but an
        empty article list for a real version is returned as-is (not an error)."""
        self.list_versions_for_document(document_code)
        return self.list_article_versions_for_document(document_code, legal_version_name)

    def get_article_navigation(
        self, document_code: str, legal_version_name: str, article_no: str
    ) -> tuple[ArticleVersion, str | None, str | None]:
        """Current article plus its neighbors within the same law version,
        ordered numerically by article_no (not insertion or string order)."""
        directory = self.list_article_versions_for_document(document_code, legal_version_name)
        index = next((i for i, av in enumerate(directory) if av.article_no == article_no), None)
        if index is None:
            raise ArticleNotFoundError(
                f"no article {article_no} in {document_code} version {legal_version_name}"
            )
        previous_no = directory[index - 1].article_no if index > 0 else None
        next_no = directory[index + 1].article_no if index < len(directory) - 1 else None
        return directory[index], previous_no, next_no

    def get_article_version_by_version_name(
        self, document_code: str, legal_version_name: str, article_no: str
    ) -> ArticleVersion:
        """Exact-version addressing (as opposed to `get_effective_article_version`'s
        as-of-date resolution) — for a reader who has already picked a specific
        LegalVersion (e.g. to compare an amendment against its predecessor)."""
        stmt = (
            select(ArticleVersion)
            .join(Article, ArticleVersion.article_id == Article.id)
            .join(LegalDocument, Article.document_id == LegalDocument.id)
            .join(LegalVersion, ArticleVersion.legal_version_id == LegalVersion.id)
            .where(
                LegalDocument.code == document_code,
                LegalVersion.version_name == legal_version_name,
                Article.article_no == article_no,
            )
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        if result is None:
            raise ArticleNotFoundError(
                f"no article {article_no} in {document_code} version {legal_version_name}"
            )
        return result

    def list_laws(self) -> list[LegalDocument]:
        stmt = select(LegalDocument).order_by(LegalDocument.code)
        return list(self.session.execute(stmt).scalars().all())
