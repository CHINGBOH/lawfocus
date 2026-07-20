"""Five-valued truth system per 法律形式化元模型与精确语义规约.md §6.

The spec's textual AND/OR rules are partial (they do not state every pairwise
combination, e.g. FALSE AND NOT_APPLICABLE). We resolve the gaps with a single
dominance ordering per operator, chosen so every combination the spec *does*
state literally still holds:

- AND dominance (most to least): NOT_APPLICABLE > FALSE > CONFLICT > UNKNOWN > TRUE
  (NOT_APPLICABLE's rule is stated unconditionally — "任意" — unlike CONFLICT's,
  which explicitly carves out an exception for FALSE, so NOT_APPLICABLE outranks it).
- OR dominance (most to least): NOT_APPLICABLE > TRUE > CONFLICT > UNKNOWN > FALSE
  (mirrors AND: NOT_APPLICABLE unconditional, TRUE explicitly unconditional, CONFLICT
  explicitly carves out an exception for TRUE).

Do not change these orderings without re-checking every example in §6 and any
downstream rule-engine test that encodes a specific pairwise result.
"""

from enum import StrEnum


class TruthValue(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


_AND_DOMINANCE = (
    TruthValue.NOT_APPLICABLE,
    TruthValue.FALSE,
    TruthValue.CONFLICT,
    TruthValue.UNKNOWN,
    TruthValue.TRUE,
)

_OR_DOMINANCE = (
    TruthValue.NOT_APPLICABLE,
    TruthValue.TRUE,
    TruthValue.CONFLICT,
    TruthValue.UNKNOWN,
    TruthValue.FALSE,
)


def _combine(a: TruthValue, b: TruthValue, dominance: tuple[TruthValue, ...]) -> TruthValue:
    rank = {value: index for index, value in enumerate(dominance)}
    return a if rank[a] <= rank[b] else b


def truth_and(a: TruthValue, b: TruthValue) -> TruthValue:
    return _combine(a, b, _AND_DOMINANCE)


def truth_or(a: TruthValue, b: TruthValue) -> TruthValue:
    return _combine(a, b, _OR_DOMINANCE)


def truth_and_all(values: list[TruthValue]) -> TruthValue:
    if not values:
        raise ValueError("truth_and_all requires at least one value")
    result = values[0]
    for value in values[1:]:
        result = truth_and(result, value)
    return result


def truth_or_all(values: list[TruthValue]) -> TruthValue:
    if not values:
        raise ValueError("truth_or_all requires at least one value")
    result = values[0]
    for value in values[1:]:
        result = truth_or(result, value)
    return result
