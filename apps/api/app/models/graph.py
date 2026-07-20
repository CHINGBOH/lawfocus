import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk, valid_interval_check


class Concept(Base, UUIDPk, CreatedAtMixin):
    """A legal concept — never bound to a fixed article number (Concept != Article)."""

    __tablename__ = "concept"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    concept_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")

    versions: Mapped[list["ConceptVersion"]] = relationship(back_populates="concept")


class ConceptVersion(Base, UUIDPk, CreatedAtMixin):
    """A versioned definition of a Concept, carrying its own review status so an
    UNVERIFIED definition can exist without being usable as synthesis input."""

    __tablename__ = "concept_version"
    __table_args__ = (valid_interval_check(),)

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concept.id"), nullable=False
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNVERIFIED")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)

    concept: Mapped[Concept] = relationship(back_populates="versions")


class GraphNode(Base, UUIDPk, CreatedAtMixin):
    """A pointer into the graph layer for a relational entity — `properties` carries
    `{"ref_table": ..., "ref_id": ...}` back to the authoritative row rather than a
    typed FK, since node_type varies (Concept, ArticleVersion, LegalSubject, ...)."""

    __tablename__ = "graph_node"
    __table_args__ = (valid_interval_check(),)

    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class GraphEdge(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "graph_edge"
    __table_args__ = (
        Index("idx_graph_edge_source", "source_id"),
        Index("idx_graph_edge_target", "target_id"),
        Index("idx_graph_edge_relation", "relation_type"),
        valid_interval_check(),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("graph_node.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("graph_node.id"), nullable=False
    )
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
