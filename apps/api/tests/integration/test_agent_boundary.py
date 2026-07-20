"""S6 Eval-style tests for the AgentProvider boundary (GOAL.md §8).

Covers: default-disabled operation, a well-behaved fake provider, and
adversarial ("prompt injection"-style) providers that try to change segment
count or smuggle an extra concept mention into rewritten text — the service
must refuse or structurally ignore all of these rather than trust agent
output.
"""

from datetime import date

import pytest

from app.models import Article, ArticleVersion, Concept, ConceptVersion, LegalDocument, LegalVersion
from app.services.agent_provider import (
    AgentCallRecord,
    AgentUnavailableError,
    DisabledAgentProvider,
    FakeAgentProvider,
)
from app.services.synthesis_service import SynthesisService


def _seed_article(db_session):
    document = LegalDocument(code="AGENT-TEST-LAW", name="Agent 边界测试法", document_type="LAW")
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
        article_text="上市公司应当设置董事会。",
        valid_from=date(2024, 1, 1),
    )
    db_session.add(article_version)
    db_session.flush()

    concept = Concept(code="AGENT-TEST-BOARD", name="董事会", concept_type="ORGAN")
    db_session.add(concept)
    db_session.flush()
    db_session.add(
        ConceptVersion(
            concept_id=concept.id,
            definition="测试定义",
            review_status="UNVERIFIED",
            valid_from=date(2024, 1, 1),
        )
    )
    db_session.flush()
    return article_version, concept


def test_default_disabled_provider_falls_back_to_deterministic(db_session) -> None:
    article_version, _concept = _seed_article(db_session)
    service = SynthesisService(db_session, agent_provider=DisabledAgentProvider())

    result = service.get_synthesis(article_version.id)

    assert result.generated_by == "deterministic_template"
    assert "".join(s.text for s in result.segments) == "上市公司应当设置董事会。"


def test_fake_provider_rewrites_only_plain_segments(db_session) -> None:
    article_version, concept = _seed_article(db_session)
    service = SynthesisService(db_session, agent_provider=FakeAgentProvider())

    result = service.get_synthesis(article_version.id)

    assert result.generated_by == "deterministic_template+agent:fake"
    concept_segments = [s for s in result.segments if s.concept_id == str(concept.id)]
    assert len(concept_segments) == 1
    assert concept_segments[0].text == "董事会"  # concept-tagged text is untouched

    plain_text = "".join(s.text for s in result.segments if s.concept_id is None)
    assert "须" in plain_text  # FakeAgentProvider's deterministic 应当->须 rewrite did apply
    assert "应当" not in plain_text


class _SegmentCountChangingProvider:
    """Adversarial: tries to drop a segment, hoping the caller doesn't notice."""

    name = "malicious-drop"

    def enhance_plain_text(self, segments: list[str], call_context: dict):
        return segments[:-1] if segments else segments, AgentCallRecord(
            provider="malicious-drop", model=None, prompt_version="n/a"
        )


class _ConceptInjectingProvider:
    """Adversarial: rewrites plain text to literally contain a concept's name,
    hoping it gets retroactively linked as a sourced concept mention."""

    name = "malicious-inject"

    def enhance_plain_text(self, segments: list[str], call_context: dict):
        injected = [s + "（另见独立董事）" for s in segments]
        return injected, AgentCallRecord(provider="malicious-inject", model=None, prompt_version="n/a")


def test_provider_that_changes_segment_count_is_rejected(db_session) -> None:
    article_version, _concept = _seed_article(db_session)
    service = SynthesisService(db_session, agent_provider=_SegmentCountChangingProvider())

    result = service.get_synthesis(article_version.id)

    # Falls all the way back to the untouched deterministic template.
    assert result.generated_by == "deterministic_template"
    assert "".join(s.text for s in result.segments) == "上市公司应当设置董事会。"


def test_provider_cannot_retroactively_tag_injected_text_with_a_concept_id(db_session) -> None:
    article_version, _concept = _seed_article(db_session)
    service = SynthesisService(db_session, agent_provider=_ConceptInjectingProvider())

    result = service.get_synthesis(article_version.id)

    # The injected "独立董事" text is present (segment count unchanged, so it's
    # accepted) but it must NOT have been tagged with a concept_id — concept
    # tagging only ever happens during the initial deterministic pass, before
    # any agent call, so this string can never retroactively gain provenance.
    assert any("独立董事" in s.text for s in result.segments)
    for s in result.segments:
        if "独立董事" in s.text:
            assert s.concept_id is None


def test_agent_unavailable_error_is_raised_by_disabled_provider_directly() -> None:
    with pytest.raises(AgentUnavailableError):
        DisabledAgentProvider().enhance_plain_text(["some text"], {})


def test_agent_call_writes_nothing_to_the_database(db_session) -> None:
    """03号文档§4/§1: Agent 无任何审核、发布、删除或授权能力 — operationalized
    here as a structural guarantee, not just a policy statement: no code path
    from an agent call (however adversarial) reaches a session.add/commit.
    Even a malicious provider that successfully injects text into the
    rendered output must leave zero new/dirty ORM objects behind."""
    article_version, _concept = _seed_article(db_session)
    db_session.flush()
    db_session.expire_all()

    service = SynthesisService(db_session, agent_provider=_ConceptInjectingProvider())
    service.get_synthesis(article_version.id)

    assert len(db_session.new) == 0
    assert len(db_session.dirty) == 0
    assert len(db_session.deleted) == 0
