"""Deterministic parsing & evaluation of `LegalRuleVersion.requirement_expression`.

Pure domain module (no DB). Per 07-剩余工作执行与验收指南.md R1, rule handlers
may contain comparison *algorithms* but never concrete legal thresholds: every
business parameter (person counts, ratios) must come from the rule version
being executed, delivered through the immutable `RuleExecutionContext`.

Supported shapes (strictly validated — unknown operators, extra fields, string
numbers, booleans, negative person counts and zero denominators are all
refused; there is no fallback to a code-default threshold):

    {"operator": "gte", "value": 2, "unit": "person"}
    {"operator": "gte_ratio", "numerator": 1, "denominator": 3}
    {"operator": "gt_ratio", "numerator": 1, "denominator": 2}

Ratio evaluation uses integer cross-multiplication only — never floats.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

PERSON_UNIT = "person"


class InvalidRequirementExpressionError(ValueError):
    """The rule version's requirement_expression is missing or illegal.

    Raised instead of falling back to any default threshold; the API layer
    maps it to a stable 422 code and the publish gate records it as a gate
    failure reason.
    """


@dataclass(frozen=True)
class RuleExecutionContext:
    """Everything a handler needs about the rule version being executed."""

    rule_version_id: uuid.UUID
    rule_code: str
    requirement_expression: Mapping[str, Any]
    evaluation_time: datetime


@dataclass(frozen=True)
class ThresholdRequirement:
    """Person-count comparison, e.g. "at least 2 people" (operator gte)."""

    value: int
    unit: str
    operator: str = "gte"

    def holds(self, actual: int) -> bool:
        return actual >= self.value


@dataclass(frozen=True)
class RatioRequirement:
    """Ratio comparison via integer cross-multiplication.

    gte_ratio n/d: part/whole >= n/d  <=>  part*d >= whole*n
    gt_ratio  n/d: part/whole >  n/d  <=>  part*d >  whole*n (whole must be > 0)
    """

    numerator: int
    denominator: int
    operator: str  # "gte_ratio" | "gt_ratio"

    def evaluate(self, part: int, whole: int) -> tuple[bool, int, int]:
        """Return (holds, lhs, rhs) with lhs/rhs the cross-multiplied integers."""
        lhs = part * self.denominator
        rhs = whole * self.numerator
        if self.operator == "gte_ratio":
            return (lhs >= rhs, lhs, rhs)
        return (whole > 0 and lhs > rhs, lhs, rhs)


def _require_int(expr: Mapping[str, Any], field: str) -> int:
    value = expr[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRequirementExpressionError(f"field '{field}' must be an integer, got {value!r}")
    return value


def _check_keys(expr: Mapping[str, Any], required: set[str]) -> None:
    keys = set(expr.keys())
    missing = required - keys
    extra = keys - required - {"operator"}
    if missing:
        raise InvalidRequirementExpressionError(f"missing fields: {sorted(missing)}")
    if extra:
        raise InvalidRequirementExpressionError(f"unexpected fields: {sorted(extra)}")


def parse_requirement(expr: Any) -> ThresholdRequirement | RatioRequirement:
    """Parse and strictly validate a requirement_expression."""
    if not isinstance(expr, Mapping):
        raise InvalidRequirementExpressionError(
            f"requirement_expression must be an object, got {type(expr).__name__}"
        )
    operator = expr.get("operator")
    if operator == "gte":
        _check_keys(expr, {"operator", "value", "unit"})
        value = _require_int(expr, "value")
        if value < 0:
            raise InvalidRequirementExpressionError(f"field 'value' must be >= 0, got {value}")
        unit = expr["unit"]
        if unit != PERSON_UNIT:
            raise InvalidRequirementExpressionError(f"unknown unit: {unit!r} (expected 'person')")
        return ThresholdRequirement(value=value, unit=unit)
    if operator in ("gte_ratio", "gt_ratio"):
        _check_keys(expr, {"operator", "numerator", "denominator"})
        numerator = _require_int(expr, "numerator")
        denominator = _require_int(expr, "denominator")
        if numerator < 1:
            raise InvalidRequirementExpressionError(f"field 'numerator' must be >= 1, got {numerator}")
        if denominator < 1:
            raise InvalidRequirementExpressionError(
                f"field 'denominator' must be >= 1, got {denominator}"
            )
        return RatioRequirement(numerator=numerator, denominator=denominator, operator=operator)
    raise InvalidRequirementExpressionError(f"unknown operator: {operator!r}")


def parse_threshold(expr: Any, *, rule_code: str) -> ThresholdRequirement:
    """Parse a requirement that must be a person-count threshold."""
    req = parse_requirement(expr)
    if not isinstance(req, ThresholdRequirement):
        raise InvalidRequirementExpressionError(
            f"{rule_code} requires a person-count threshold (operator 'gte')"
        )
    return req


def parse_ratio(expr: Any, *, rule_code: str) -> RatioRequirement:
    """Parse a requirement that must be a ratio comparison."""
    req = parse_requirement(expr)
    if not isinstance(req, RatioRequirement):
        raise InvalidRequirementExpressionError(
            f"{rule_code} requires a ratio (operator 'gte_ratio'/'gt_ratio')"
        )
    return req
