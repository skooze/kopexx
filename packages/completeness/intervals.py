"""Interval algebra over one source member's character offsets.

WHY INTERVALS AT ALL. Phase 2.1 counted model-emitted references and could not answer "what
fraction of the filing did this parse represent". A reference count has no denominator: a region a
model never mentioned never entered it. An interval does. Two resolved anchors bound a region of
the preserved bytes, and the union of every bounded region, measured against the mechanical
inventory of every visible span, is a fraction with a real denominator underneath it.

WHAT AN INTERVAL PROVES AND WHAT IT DOES NOT. It proves that a model claimed a stretch of source
and that both ends of the claim resolve in the preserved bytes. It does NOT prove the model
represented what is inside the stretch, understood it, or got it right. `rules.md` section 21 rule
4 requires coverage to be PROVED against the preserved bytes rather than asserted by the model, and
this proves exactly one thing: the boundaries are real. Everything between them is still a human
judgement, which is why nothing here issues a completeness verdict.

    A MODEL CAN CLAIM A HUGE INTERVAL AND SAY NOTHING ABOUT IT. That is why the ledger reports
    interval coverage BESIDE the span-level accounting rather than instead of it, and why the
    mechanical gate requires both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Interval:
    """A half-open character range `[start, end)` in one member's decoded text."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"interval {self.start}:{self.end} ends before it begins")

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, position: int) -> bool:
        return self.start <= position < self.end

    def intersection(self, other: Interval) -> Interval | None:
        start, end = max(self.start, other.start), min(self.end, other.end)
        return Interval(start, end) if end > start else None

    def to_mapping(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "length": self.length}


def merge(intervals: list[Interval]) -> tuple[Interval, ...]:
    """The union of a set of intervals, as a minimal ordered set of disjoint intervals.

    ADJACENT INTERVALS ARE JOINED, TOUCHING ONES ARE NOT DOUBLE-COUNTED. `[0,10)` and `[10,20)`
    become `[0,20)`; `[0,10)` and `[5,20)` also become `[0,20)` and the shared five characters are
    counted once. Summing lengths without merging first is how a parse that covers one paragraph
    three times reports three hundred percent coverage.
    """
    if not intervals:
        return ()
    ordered = sorted(intervals, key=lambda i: (i.start, i.end))
    merged = [ordered[0]]
    for current in ordered[1:]:
        last = merged[-1]
        if current.start <= last.end:
            if current.end > last.end:
                merged[-1] = Interval(last.start, current.end)
            continue
        merged.append(current)
    return tuple(merged)


def gaps(covered: tuple[Interval, ...], *, within: Interval) -> tuple[Interval, ...]:
    """Every part of `within` that no interval in `covered` reaches."""
    found: list[Interval] = []
    cursor = within.start
    for interval in merge(list(covered)):
        clipped = interval.intersection(within)
        if clipped is None:
            continue
        if clipped.start > cursor:
            found.append(Interval(cursor, clipped.start))
        cursor = max(cursor, clipped.end)
    if cursor < within.end:
        found.append(Interval(cursor, within.end))
    return tuple(found)


def overlaps(intervals: list[Interval]) -> tuple[Interval, ...]:
    """Every region claimed by more than one interval.

    Reported rather than resolved. Two parts covering the same paragraph may be a duplication
    defect or may be two models' honest reading of a passage that belongs to both; deciding which
    is a semantic judgement, and `rules.md` section 21 rule 1 puts it outside backend code.
    """
    ordered = sorted(intervals, key=lambda i: (i.start, i.end))
    found: list[Interval] = []
    for position, current in enumerate(ordered):
        for other in ordered[position + 1 :]:
            if other.start >= current.end:
                break
            shared = current.intersection(other)
            if shared is not None and shared.length > 0:
                found.append(shared)
    return merge(found)


def covered_length(intervals: tuple[Interval, ...]) -> int:
    """Total characters covered, counting a region claimed twice exactly once."""
    return sum(interval.length for interval in merge(list(intervals)))
