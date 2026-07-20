import logging
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rule_requirement import (
    InvalidRequirementExpressionError,
    RatioRequirement,
    ThresholdRequirement,
    parse_requirement,
)
from app.models import ArticleVersion, Concept, ConceptVersion, LegalRule, LegalRuleVersion, RuleSource
from app.models.enums import ReviewStatus
from app.services.agent_provider import AgentCallRecord, AgentProvider, AgentUnavailableError, get_agent_provider

logger = logging.getLogger("lawfocus.agent")


class ArticleVersionNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class TextSegment:
    text: str
    concept_id: str | None


@dataclass(frozen=True)
class SynthesisResult:
    segments: list[TextSegment]
    generated_by: str


@dataclass(frozen=True)
class RuleSynthesisResult:
    """A genuine §9.3-style synthesis, built only from a PUBLISHED rule
    version's own structured fields — never from the raw article text."""

    segments: list[TextSegment]
    rule_id: str
    rule_code: str
    rule_name: str


_MODALITY_LABELS = {
    "OBLIGATION": "义务性规范",
    "PROHIBITION": "禁止性规范",
    "PERMISSION": "许可性规范",
    "AUTHORIZATION": "授权性规范",
    "RIGHT": "权利性规范",
}

_SUBJECT_TYPE_LABELS = {
    "LISTEDCOMPANY": "上市公司",
    "COMPANY": "公司",
    "PERSON": "自然人",
    "REGULATOR": "监管机构",
}


class SynthesisService:
    """The article-reader 'synthesis' panel.

    Deterministic concept-tagging always runs first and is always correct on
    its own — the optional AgentProvider step that follows can only touch
    the plain-text (non-concept) segments' wording, per UI doc §9.4 and
    GOAL.md §8. Concept-tagged spans and their definitions never pass
    through the provider at all, so there is no code path by which an agent
    could introduce a new concept relation or unsourced proposition here.
    """

    def __init__(self, session: Session, agent_provider: AgentProvider | None = None):
        self.session = session
        self.agent_provider = agent_provider or get_agent_provider()

    def get_synthesis(self, article_version_id: uuid.UUID) -> SynthesisResult:
        article_version = self.session.get(ArticleVersion, article_version_id)
        if article_version is None:
            raise ArticleVersionNotFoundError(f"no article_version {article_version_id}")

        concepts = self._concepts_effective_at(article_version.valid_from)
        segments = self._segment_text(article_version.article_text, concepts)

        generated_by = "deterministic_template"
        try:
            segments, record = self._apply_agent_enhancement(segments, article_version_id)
            generated_by = f"deterministic_template+agent:{record.provider}"
        except AgentUnavailableError as exc:
            if self.agent_provider.name != "disabled":
                logger.info("agent enhancement unavailable, falling back: %s", exc)

        return SynthesisResult(segments=segments, generated_by=generated_by)

    def get_rule_synthesis(self, article_version_id: uuid.UUID) -> RuleSynthesisResult | None:
        """UI doc §9.3's synthesis template: 主体/法律模态/要求, sourced only from
        a PUBLISHED LegalRuleVersion's own structured fields. Returns None
        (not an empty/placeholder result) when no such rule exists, or when
        the bound rule's requirement can't be mechanically rendered — an
        absent synthesis is honest; a guessed one is not."""
        article_version = self.session.get(ArticleVersion, article_version_id)
        if article_version is None:
            raise ArticleVersionNotFoundError(f"no article_version {article_version_id}")

        stmt = (
            select(LegalRuleVersion)
            .join(RuleSource, RuleSource.rule_version_id == LegalRuleVersion.id)
            .join(LegalRule, LegalRule.id == LegalRuleVersion.rule_id)
            .where(
                RuleSource.article_version_id == article_version_id,
                LegalRuleVersion.status == ReviewStatus.PUBLISHED,
            )
            .order_by(LegalRule.code)
        )
        rule_version = self.session.execute(stmt).scalars().first()
        if rule_version is None:
            return None

        try:
            requirement = parse_requirement(rule_version.requirement_expression)
        except InvalidRequirementExpressionError:
            return None

        sentence = self._render_rule_sentence(rule_version, requirement)
        concepts = self._concepts_effective_at(article_version.valid_from)
        segments = self._segment_text(sentence, concepts)
        return RuleSynthesisResult(
            segments=segments,
            rule_id=str(rule_version.id),
            rule_code=rule_version.rule.code,
            rule_name=rule_version.rule.name,
        )

    @staticmethod
    def _render_rule_sentence(
        rule_version: LegalRuleVersion, requirement: ThresholdRequirement | RatioRequirement
    ) -> str:
        subject_key = (rule_version.subject_type or "").upper().replace("_", "")
        subject = _SUBJECT_TYPE_LABELS.get(subject_key, rule_version.subject_type or "相关主体")
        modality = _MODALITY_LABELS.get(rule_version.modality, rule_version.modality)
        requirement_text = SynthesisService._render_requirement(requirement)
        sentence = (
            f"本条对{subject}设定{modality}：{rule_version.rule.name}{requirement_text}。"
            f"（依据已发布规则 {rule_version.rule.code}）"
        )
        if rule_version.exception_expression:
            sentence += "本规则记录了例外情形，具体范围需结合规则详情判断。"
        return sentence

    @staticmethod
    def _render_requirement(requirement: ThresholdRequirement | RatioRequirement) -> str:
        if isinstance(requirement, ThresholdRequirement):
            unit_label = "人" if requirement.unit == "person" else requirement.unit
            return f"不少于{requirement.value}{unit_label}"
        comparator = "不低于" if requirement.operator == "gte_ratio" else "高于"
        return f"，占比{comparator}{requirement.numerator}/{requirement.denominator}"

    def _apply_agent_enhancement(
        self, segments: list[TextSegment], article_version_id: uuid.UUID
    ) -> tuple[list[TextSegment], AgentCallRecord]:
        plain_indices = [i for i, s in enumerate(segments) if s.concept_id is None]
        plain_texts = [segments[i].text for i in plain_indices]

        enhanced_texts, record = self.agent_provider.enhance_plain_text(
            plain_texts, {"article_version_id": str(article_version_id)}
        )
        if len(enhanced_texts) != len(plain_texts):
            # The provider changed the segment count — refuse the output outright
            # rather than risk misaligning text against concept-tagged spans.
            raise AgentUnavailableError("provider returned a mismatched segment count; ignoring output")

        logger.info(
            "agent call provider=%s model=%s prompt_version=%s redacted=%s",
            record.provider, record.model, record.prompt_version, record.redacted,
        )

        result = list(segments)
        for idx, new_text in zip(plain_indices, enhanced_texts, strict=True):
            result[idx] = TextSegment(text=new_text, concept_id=None)
        return result, record

    def _concepts_effective_at(self, at: date) -> list[tuple[str, str]]:
        stmt = (
            select(Concept.name, Concept.id)
            .join(ConceptVersion, ConceptVersion.concept_id == Concept.id)
            .where(ConceptVersion.valid_from <= at)
            .where((ConceptVersion.valid_to.is_(None)) | (ConceptVersion.valid_to > at))
        )
        rows = self.session.execute(stmt).all()
        # Longest name first so "独立董事" is matched before a shorter substring would be.
        return sorted(((name, str(concept_id)) for name, concept_id in rows), key=lambda p: -len(p[0]))

    @staticmethod
    def _segment_text(text: str, concepts: list[tuple[str, str]]) -> list[TextSegment]:
        segments: list[TextSegment] = []
        cursor = 0
        while cursor < len(text):
            match = None
            for name, concept_id in concepts:
                if text.startswith(name, cursor):
                    match = (name, concept_id)
                    break
            if match:
                name, concept_id = match
                segments.append(TextSegment(text=name, concept_id=concept_id))
                cursor += len(name)
            else:
                # Accumulate plain-text runs into a single segment.
                next_match_at = len(text)
                for i in range(cursor + 1, len(text)):
                    if any(text.startswith(name, i) for name, _ in concepts):
                        next_match_at = i
                        break
                segments.append(TextSegment(text=text[cursor:next_match_at], concept_id=None))
                cursor = next_match_at
        return segments
