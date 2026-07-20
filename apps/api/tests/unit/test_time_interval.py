from datetime import date

import pytest

from app.domain.time_interval import ValidInterval, applicable_at


def test_rejects_end_before_or_equal_to_start() -> None:
    with pytest.raises(ValueError):
        ValidInterval(start=date(2024, 1, 1), end=date(2024, 1, 1))
    with pytest.raises(ValueError):
        ValidInterval(start=date(2024, 1, 1), end=date(2023, 1, 1))


def test_contains_is_half_open() -> None:
    interval = ValidInterval(start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert interval.contains(date(2024, 1, 1))  # start is inclusive
    assert interval.contains(date(2024, 12, 30))
    assert not interval.contains(date(2024, 12, 31))  # end is exclusive
    assert not interval.contains(date(2023, 12, 31))


def test_open_ended_interval_is_still_valid_far_in_future() -> None:
    interval = ValidInterval(start=date(2024, 1, 1), end=None)
    assert interval.contains(date(2099, 1, 1))
    assert not interval.contains(date(2023, 12, 31))


@pytest.mark.parametrize(
    "a_start,a_end,b_start,b_end,expected",
    [
        (date(2024, 1, 1), date(2024, 6, 1), date(2024, 5, 1), date(2024, 8, 1), True),
        (date(2024, 1, 1), date(2024, 6, 1), date(2024, 6, 1), date(2024, 8, 1), False),
        (date(2024, 1, 1), date(2024, 6, 1), date(2024, 7, 1), date(2024, 8, 1), False),
        (date(2024, 1, 1), None, date(2099, 1, 1), None, True),
    ],
)
def test_overlaps(
    a_start: date, a_end: date | None, b_start: date, b_end: date | None, expected: bool
) -> None:
    a = ValidInterval(a_start, a_end)
    b = ValidInterval(b_start, b_end)
    assert a.overlaps(b) is expected
    assert b.overlaps(a) is expected  # overlap must be symmetric


def test_applicable_at_matches_contains() -> None:
    rule_interval = ValidInterval(start=date(2024, 7, 1), end=date(2026, 1, 1))
    assert applicable_at(rule_interval, date(2025, 1, 1))
    assert not applicable_at(rule_interval, date(2026, 1, 1))
