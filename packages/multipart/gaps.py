"""A STABLE IDENTITY for one gap, so a repeated gap can be recognised as repeated.

THE DEFECT THIS CLOSES, AS PHASE 2.1 OBSERVED IT. Reconciliation cycles 2 and 3 of the GPT OSS run
were re-shown the ORIGINAL part's unresolved counts, because an earlier result is never overwritten,
so the model kept re-reporting items whose replacements had already run. Cycle 1 named five missing
items and asked for four replacement parts; cycle 2 asked for four more; cycle 3 asked for ten and
recorded `cycle_limit_reached` in its own metadata. The model never declared satisfaction.

    IT WAS RECORDED AS AN OBSERVED COST OF THE BRIEF RATHER THAN A DEFECT CLAIM, and that was the
    right call at the time: the reconcile prompt gives the model an explicit exit, so the loop was
    not structurally non-terminating. But nothing could tell cycle 3's ten requests from cycle 1's
    five, because a gap was an opaque mapping with no key, never persisted, never diffed and never
    deduplicated. A loop nobody can measure is a loop nobody can stop early.

WHAT A FINGERPRINT IS, AND WHAT IT IS CAREFULLY NOT. It is a digest over the STRUCTURAL identity of
a gap: the kind of finding, and the model-created identifier or filename it names. It is NOT a
digest over the prose, because two cycles describing the same missing material in different words
are the same gap, and a hash of the sentence would say they are different.

    THE FREE-TEXT FIELDS ARE DELIBERATELY EXCLUDED. `evidence`, `why`, `what` and `where` are the
    model's or the backend's description of a gap, not its identity. Including them would let a
    rephrasing defeat deduplication — which is precisely the "duplicate gaps under new free-text
    labels" this phase is asked to prevent.

NOTHING IS DISCARDED. A repeated gap is still recorded, still shown to a reviewer and still carried
in the evidence. It simply stops creating new billable work, and the repeat is counted so the
no-progress rule can see it.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

#: Keys that carry a gap's IDENTITY. Everything else on a gap mapping is description.
#:
#: `part_id` and `artifact` are the two the mechanical findings key on; `filename`, `id`, `part` and
#: `table_id` are the shapes a MODEL has been observed to use for the same thing. A gap naming none
#: of them fingerprints on its kind alone, which is the honest answer: two findings of one kind
#: naming nothing are indistinguishable, and treating them as distinct would defeat the whole point.
_IDENTITY_KEYS: tuple[str, ...] = (
    "part_id",
    "artifact",
    "filename",
    "table_id",
    "span_id",
    "id",
    "part",
)


@dataclass(frozen=True)
class GapFingerprint:
    """One gap's stable identity, and the cycle it was first seen in."""

    fingerprint: str
    kind: str
    subject: str
    first_seen_cycle: int
    times_seen: int = 1

    @property
    def repeated(self) -> bool:
        return self.times_seen > 1

    def to_mapping(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "kind": self.kind,
            "subject": self.subject,
            "first_seen_cycle": self.first_seen_cycle,
            "times_seen": self.times_seen,
            "repeated": self.repeated,
        }


def _subject(gap: dict[str, Any]) -> str:
    for key in _IDENTITY_KEYS:
        value = gap.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def fingerprint(gap: dict[str, Any], *, kind: str = "") -> GapFingerprint:
    """The stable identity of one gap mapping, at cycle 0 until a caller says otherwise."""
    resolved_kind = (kind or str(gap.get("finding") or gap.get("kind") or "")).strip()
    subject = _subject(gap)
    digest = sha256(f"{resolved_kind}\n{subject}".encode()).hexdigest()[:32]
    return GapFingerprint(
        fingerprint=digest, kind=resolved_kind, subject=subject, first_seen_cycle=0
    )


def fold(
    gaps: list[dict[str, Any]], *, cycle: int, seen: dict[str, GapFingerprint] | None = None
) -> tuple[dict[str, GapFingerprint], tuple[GapFingerprint, ...], tuple[GapFingerprint, ...]]:
    """Fold this cycle's gaps into the running set.

    Returns the updated set, the gaps that are NEW this cycle, and the gaps that REPEAT one already
    seen. A reconciliation cycle may create work only for the first list — that is what "require
    measurable progress" means mechanically, and it is why the second list is returned rather than
    silently dropped: a repeat is evidence about the loop, and the no-progress rule reads it.
    """
    running = dict(seen or {})
    fresh: list[GapFingerprint] = []
    repeated: list[GapFingerprint] = []
    for gap in gaps:
        found = fingerprint(gap)
        existing = running.get(found.fingerprint)
        if existing is None:
            entry = GapFingerprint(
                fingerprint=found.fingerprint,
                kind=found.kind,
                subject=found.subject,
                first_seen_cycle=cycle,
                times_seen=1,
            )
            running[found.fingerprint] = entry
            fresh.append(entry)
            continue
        entry = GapFingerprint(
            fingerprint=existing.fingerprint,
            kind=existing.kind,
            subject=existing.subject,
            first_seen_cycle=existing.first_seen_cycle,
            times_seen=existing.times_seen + 1,
        )
        running[entry.fingerprint] = entry
        repeated.append(entry)
    return running, tuple(fresh), tuple(repeated)
