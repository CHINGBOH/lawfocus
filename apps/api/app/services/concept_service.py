import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArticleVersion, Concept, ConceptVersion, GraphEdge, GraphNode


class ConceptNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ConceptDetail:
    concept: Concept
    active_version: ConceptVersion
    source_article_versions: list[ArticleVersion]


class ConceptService:
    """Resolves a concept's current definition and, via graph_node/graph_edge
    DEFINED_BY edges, the article version(s) it traces back to — the backend
    half of the UI's 'definition source' provenance requirement (UI doc §2.3,
    §7.3). Never fabricates a source: a concept with no DEFINED_BY edge simply
    returns an empty source list rather than guessing one.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_concept_detail(self, concept_id: uuid.UUID, at: date) -> ConceptDetail:
        """Looks up by Concept.id (UUID) — matching the id every other
        endpoint uses, and matching what SynthesisService puts in a
        text_segment's `concept_id` for a matched mention."""
        concept = self.session.get(Concept, concept_id)
        if concept is None:
            raise ConceptNotFoundError(f"no concept with id {concept_id}")

        version_stmt = (
            select(ConceptVersion)
            .where(
                ConceptVersion.concept_id == concept.id,
                ConceptVersion.valid_from <= at,
            )
            .where((ConceptVersion.valid_to.is_(None)) | (ConceptVersion.valid_to > at))
        )
        active_version = self.session.execute(version_stmt).scalar_one_or_none()
        if active_version is None:
            raise ConceptNotFoundError(f"no version of concept {concept_id} effective at {at.isoformat()}")

        sources = self._resolve_defined_by_sources(concept.code)
        return ConceptDetail(concept=concept, active_version=active_version, source_article_versions=sources)

    def _resolve_defined_by_sources(self, concept_code: str) -> list[ArticleVersion]:
        concept_node = self.session.execute(
            select(GraphNode).where(GraphNode.node_type == "CONCEPT", GraphNode.code == concept_code)
        ).scalar_one_or_none()
        if concept_node is None:
            return []

        edge_stmt = select(GraphEdge).where(
            GraphEdge.source_id == concept_node.id, GraphEdge.relation_type == "DEFINED_BY"
        )
        edges = self.session.execute(edge_stmt).scalars().all()

        article_versions: list[ArticleVersion] = []
        for edge in edges:
            target_node = self.session.get(GraphNode, edge.target_id)
            if target_node is None or target_node.properties.get("ref_table") != "article_version":
                continue
            article_version = self.session.get(
                ArticleVersion, uuid.UUID(target_node.properties["ref_id"])
            )
            if article_version is not None:
                article_versions.append(article_version)
        return article_versions
