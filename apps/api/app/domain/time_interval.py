"""Half-open validity intervals per 法律形式化元模型与精确语义规约.md §7.

ValidTime(x) = [t_start, t_end); Overlap([a,b),[c,d)) iff a<d and c<b.
An open end (`end is None`) means "still valid" — treat it as +infinity.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ValidInterval:
    start: date
    end: date | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be strictly after start for a half-open interval")

    def contains(self, at: date) -> bool:
        if at < self.start:
            return False
        return self.end is None or at < self.end

    def overlaps(self, other: "ValidInterval") -> bool:
        a, b = self.start, self.end
        c, d = other.start, other.end
        a_before_d = d is None or a < d
        c_before_b = b is None or c < b
        return a_before_d and c_before_b


def applicable_at(rule_interval: ValidInterval, event_time: date) -> bool:
    """ApplicableAt(rule,event) iff OccurredAt(event,t) and t in ValidTime(rule)."""
    return rule_interval.contains(event_time)
