"""R1: strict parsing & deterministic evaluation of requirement_expression.

Pure domain tests — no DB. Covers the 07 指南 R1 §3.4 rejection list and the
ratio boundary cases (1/3, 2/5, strict >1/2) with integer cross-multiplication.
"""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.rule_requirement import (
    InvalidRequirementExpressionError,
    RatioRequirement,
    RuleExecutionContext,
    ThresholdRequirement,
    parse_ratio,
    parse_requirement,
    parse_threshold,
)


def test_parse_person_threshold() -> None:
    req = parse_requirement({"operator": "gte", "value": 2, "unit": "person"})
    assert isinstance(req, ThresholdRequirement)
    assert req.value == 2
    assert req.unit == "person"


def test_parse_gte_ratio() -> None:
    req = parse_requirement({"operator": "gte_ratio", "numerator": 1, "denominator": 3})
    assert isinstance(req, RatioRequirement)
    assert (req.numerator, req.denominator, req.operator) == (1, 3, "gte_ratio")


def test_parse_gt_ratio() -> None:
    req = parse_requirement({"operator": "gt_ratio", "numerator": 1, "denominator": 2})
    assert isinstance(req, RatioRequirement)
    assert req.operator == "gt_ratio"


@pytest.mark.parametrize(
    ("actual", "expected"),
    [(1, False), (2, True), (5, True)],
)
def test_threshold_holds_boundary(actual: int, expected: bool) -> None:
    req = ThresholdRequirement(value=2, unit="person")
    assert req.holds(actual) is expected


@pytest.mark.parametrize(
    ("numerator", "denominator", "part", "whole", "expected"),
    [
        (1, 3, 1, 3, True),  # exactly 1/3
        (1, 3, 3, 9, True),  # exactly 1/3 again
        (1, 3, 0, 3, False),  # 0/3 < 1/3
        (1, 3, 1, 4, False),  # 1/4 < 1/3
        (1, 3, 2, 5, True),  # 2/5 > 1/3
        (2, 5, 2, 5, True),  # exactly 2/5
        (2, 5, 4, 10, True),  # exactly 2/5 scaled
        (2, 5, 1, 3, False),  # 1/3 < 2/5
        (2, 5, 3, 7, True),  # 3/7 > 2/5
    ],
)
def test_gte_ratio_boundaries(numerator: int, denominator: int, part: int, whole: int, expected: bool) -> None:
    req = RatioRequirement(numerator=numerator, denominator=denominator, operator="gte_ratio")
    holds, lhs, rhs = req.evaluate(part, whole)
    assert holds is expected
    assert lhs == part * denominator
    assert rhs == whole * numerator


@pytest.mark.parametrize(
    ("part", "whole", "expected"),
    [
        (1, 2, False),  # exactly 1/2 is NOT strictly over half
        (2, 4, False),  # exactly 1/2 scaled
        (2, 3, True),  # 2/3 > 1/2
        (3, 5, True),  # 3/5 > 1/2
        (1, 0, False),  # zero denominator on the measured side can never satisfy ">"
        (0, 0, False),
    ],
)
def test_gt_ratio_strict_majority(part: int, whole: int, expected: bool) -> None:
    req = RatioRequirement(numerator=1, denominator=2, operator="gt_ratio")
    holds, _, _ = req.evaluate(part, whole)
    assert holds is expected


@pytest.mark.parametrize(
    "expr",
    [
        {"operator": "gte_ratio", "numerator": 1, "denominator": 0},  # zero denominator
        {"operator": "gte_ratio", "numerator": 1, "denominator": -3},
        {"operator": "gte_ratio", "numerator": 0, "denominator": 3},  # degenerate numerator
        {"operator": "gte", "value": -1, "unit": "person"},  # negative person count
        {"operator": "eq", "value": 2, "unit": "person"},  # unknown operator
        {"operator": "gte", "value": "2", "unit": "person"},  # string number
        {"operator": "gte_ratio", "numerator": "1", "denominator": 3},
        {"operator": "gte", "value": 2.0, "unit": "person"},  # float
        {"operator": "gte", "value": True, "unit": "person"},  # bool is not an int
        {"operator": "gte", "value": 2, "unit": "person", "note": "x"},  # extra field
        {"operator": "gte", "value": 2},  # missing unit
        {"operator": "gte", "value": 2, "unit": "percent"},  # unknown unit
        {"operator": "gte_ratio", "numerator": 1},  # missing denominator
        {"value": 2, "unit": "person"},  # missing operator
        {},  # empty
        [],  # not an object
        "gte:2",  # not an object
        None,
    ],
)
def test_invalid_expressions_rejected(expr) -> None:
    with pytest.raises(InvalidRequirementExpressionError):
        parse_requirement(expr)


def test_parse_threshold_rejects_ratio_shape() -> None:
    with pytest.raises(InvalidRequirementExpressionError):
        parse_threshold({"operator": "gte_ratio", "numerator": 1, "denominator": 3}, rule_code="GOV-ID-001")


def test_parse_ratio_rejects_threshold_shape() -> None:
    with pytest.raises(InvalidRequirementExpressionError):
        parse_ratio({"operator": "gte", "value": 2, "unit": "person"}, rule_code="GOV-ID-002")


def test_rule_execution_context_is_immutable() -> None:
    ctx = RuleExecutionContext(
        rule_version_id=uuid.uuid4(),
        rule_code="GOV-ID-001",
        requirement_expression={"operator": "gte", "value": 2, "unit": "person"},
        evaluation_time=datetime(2025, 6, 1, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        ctx.requirement_expression = {}  # type: ignore[misc]
