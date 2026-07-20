import pytest

from app.domain.truth import TruthValue as T
from app.domain.truth import truth_and, truth_and_all, truth_or, truth_or_all

AND_CASES = [
    (T.TRUE, T.TRUE, T.TRUE),
    (T.FALSE, T.TRUE, T.FALSE),
    (T.FALSE, T.FALSE, T.FALSE),
    (T.FALSE, T.UNKNOWN, T.FALSE),
    (T.FALSE, T.CONFLICT, T.FALSE),
    (T.FALSE, T.NOT_APPLICABLE, T.NOT_APPLICABLE),
    (T.UNKNOWN, T.TRUE, T.UNKNOWN),
    (T.UNKNOWN, T.UNKNOWN, T.UNKNOWN),
    (T.UNKNOWN, T.CONFLICT, T.CONFLICT),
    (T.CONFLICT, T.TRUE, T.CONFLICT),
    (T.CONFLICT, T.CONFLICT, T.CONFLICT),
    (T.NOT_APPLICABLE, T.TRUE, T.NOT_APPLICABLE),
    (T.NOT_APPLICABLE, T.FALSE, T.NOT_APPLICABLE),
    (T.NOT_APPLICABLE, T.CONFLICT, T.NOT_APPLICABLE),
    (T.NOT_APPLICABLE, T.NOT_APPLICABLE, T.NOT_APPLICABLE),
]

OR_CASES = [
    (T.TRUE, T.TRUE, T.TRUE),
    (T.TRUE, T.FALSE, T.TRUE),
    (T.TRUE, T.CONFLICT, T.TRUE),
    (T.TRUE, T.NOT_APPLICABLE, T.NOT_APPLICABLE),
    (T.FALSE, T.FALSE, T.FALSE),
    (T.FALSE, T.UNKNOWN, T.UNKNOWN),
    (T.UNKNOWN, T.UNKNOWN, T.UNKNOWN),
    (T.CONFLICT, T.FALSE, T.CONFLICT),
    (T.CONFLICT, T.UNKNOWN, T.CONFLICT),
    (T.CONFLICT, T.CONFLICT, T.CONFLICT),
    (T.NOT_APPLICABLE, T.FALSE, T.NOT_APPLICABLE),
    (T.NOT_APPLICABLE, T.NOT_APPLICABLE, T.NOT_APPLICABLE),
]


@pytest.mark.parametrize("a,b,expected", AND_CASES)
def test_truth_and(a: T, b: T, expected: T) -> None:
    assert truth_and(a, b) == expected
    assert truth_and(b, a) == expected  # AND must be commutative


@pytest.mark.parametrize("a,b,expected", OR_CASES)
def test_truth_or(a: T, b: T, expected: T) -> None:
    assert truth_or(a, b) == expected
    assert truth_or(b, a) == expected  # OR must be commutative


def test_truth_and_all_short_circuits_to_most_dominant() -> None:
    assert truth_and_all([T.TRUE, T.UNKNOWN, T.CONFLICT]) == T.CONFLICT
    assert truth_and_all([T.TRUE, T.TRUE, T.TRUE]) == T.TRUE
    assert truth_and_all([T.TRUE, T.NOT_APPLICABLE, T.FALSE]) == T.NOT_APPLICABLE


def test_truth_or_all_short_circuits_to_most_dominant() -> None:
    assert truth_or_all([T.FALSE, T.UNKNOWN, T.CONFLICT]) == T.CONFLICT
    assert truth_or_all([T.FALSE, T.FALSE, T.FALSE]) == T.FALSE
    assert truth_or_all([T.FALSE, T.NOT_APPLICABLE, T.TRUE]) == T.NOT_APPLICABLE


def test_and_all_and_or_all_reject_empty() -> None:
    with pytest.raises(ValueError):
        truth_and_all([])
    with pytest.raises(ValueError):
        truth_or_all([])
