"""AgentProvider boundary per GOAL.md §8 and UI doc §9.4.

An AgentProvider may ONLY rephrase already-reviewed plain-text connective
wording — never concept-tagged spans, never definitions, never introduce a
new proposition/concept relation/rule priority/fact. That boundary is
enforced structurally here: `enhance_plain_text` receives only the plain
segments' text (concept-tagged segments are never passed to it at all), and
the caller (SynthesisService) is responsible for re-inserting the result
1:1 without ever letting a provider add/remove/reorder segments.

`DisabledAgentProvider` is the default — the whole system (including every
compliance-critical code path) must work correctly with it, per GOAL: "无
API 密钥时所有测试和核心业务必须通过".
"""

from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


class AgentUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class AgentCallRecord:
    provider: str
    model: str | None
    prompt_version: str
    redacted: bool = True


class AgentProvider(Protocol):
    name: str

    def enhance_plain_text(
        self, segments: list[str], call_context: dict
    ) -> tuple[list[str], AgentCallRecord]:
        """Must return exactly len(segments) strings, in the same order —
        callers reject any response that changes the segment count."""
        ...


class DisabledAgentProvider:
    name = "disabled"

    def enhance_plain_text(self, segments: list[str], call_context: dict) -> tuple[list[str], AgentCallRecord]:
        raise AgentUnavailableError("no agent provider configured (LAWFOCUS_AGENT_PROVIDER=disabled)")


class FakeAgentProvider:
    """Deterministic, network-free provider for tests and Eval samples —
    never calls a real model. Performs one trivial, reproducible rewrite so
    tests can assert enhancement actually happened without depending on any
    live LLM."""

    name = "fake"

    def enhance_plain_text(self, segments: list[str], call_context: dict) -> tuple[list[str], AgentCallRecord]:
        enhanced = [s.replace("应当", "须") for s in segments]
        record = AgentCallRecord(provider="fake", model="fake-v1", prompt_version="synthesis-v1")
        return enhanced, record


_PROVIDERS: dict[str, type] = {
    "disabled": DisabledAgentProvider,
    "fake": FakeAgentProvider,
}


def get_agent_provider() -> AgentProvider:
    settings = get_settings()
    provider_cls = _PROVIDERS.get(settings.agent_provider, DisabledAgentProvider)
    return provider_cls()
