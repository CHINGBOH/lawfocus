import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk, valid_interval_check


class LegalDocument(Base, UUIDPk, CreatedAtMixin):
    """A stable legal-source identity, e.g. 中华人民共和国公司法 — spans amendments."""

    __tablename__ = "legal_document"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255))
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_hash: Mapped[str | None] = mapped_column(String(128))

    versions: Mapped[list["LegalVersion"]] = relationship(back_populates="document")
    articles: Mapped[list["Article"]] = relationship(back_populates="document")


class LegalVersion(Base, UUIDPk, CreatedAtMixin):
    """One promulgated/amended version of a LegalDocument. Never overwritten —
    only ever superseded by a new row (法律原文只增新版本，不原位覆盖)."""

    __tablename__ = "legal_version"
    __table_args__ = (valid_interval_check("effective_from", "effective_to"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_document.id"), nullable=False
    )
    version_name: Mapped[str] = mapped_column(String(255), nullable=False)
    promulgated_at: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    version_hash: Mapped[str | None] = mapped_column(String(128))

    document: Mapped[LegalDocument] = relationship(back_populates="versions")
    article_versions: Mapped[list["ArticleVersion"]] = relationship(back_populates="legal_version")


class Article(Base, UUIDPk, CreatedAtMixin):
    """A stable article identity within a document (e.g. '第108条') independent
    of any particular LegalVersion's text — Concept != Article != ArticleVersion."""

    __tablename__ = "article"
    __table_args__ = (UniqueConstraint("document_id", "article_no", name="uq_article_document_no"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_document.id"), nullable=False
    )
    article_no: Mapped[str] = mapped_column(String(50), nullable=False)

    document: Mapped[LegalDocument] = relationship(back_populates="articles")
    versions: Mapped[list["ArticleVersion"]] = relationship(back_populates="article")


class ArticleVersion(Base, UUIDPk, CreatedAtMixin):
    """The versioned text of an Article as it reads within one LegalVersion."""

    __tablename__ = "article_version"
    __table_args__ = (
        UniqueConstraint("article_id", "legal_version_id", name="uq_article_version_unique"),
        valid_interval_check(),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("article.id"), nullable=False
    )
    legal_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_version.id"), nullable=False
    )
    chapter_no: Mapped[str | None] = mapped_column(String(50))
    section_no: Mapped[str | None] = mapped_column(String(50))
    article_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)

    article: Mapped[Article] = relationship(back_populates="versions")
    legal_version: Mapped[LegalVersion] = relationship(back_populates="article_versions")

    @property
    def article_no(self) -> str:
        return self.article.article_no
