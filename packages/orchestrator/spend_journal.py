"""A DURABLE cumulative spend ceiling. It does not reset when the process does.

WHY THE LEDGER ALONE IS NOT ENOUGH. `packages/model_catalog.SpendLedger` bounds the worst case of
one invocation against a ceiling and reserves before the call — which is exactly right, and which
lives entirely in memory. A ceiling that starts again at zero every time the server restarts is
not a ceiling; it is a per-process suggestion. The authorized Phase 2 ceiling is CUMULATIVE, so
the total has to outlive the process that spent it.

HOW IT WORKS. Every reservation and every settlement is appended to a durable journal in the
evaluation store, and the running total is recomputed from the journal at construction. The
journal is append-only: a settlement records both the reservation it replaces and the measured
amount, so the arithmetic is auditable rather than merely stated.

RESERVE BEFORE, SETTLE AFTER, AND CHARGE FAILURES. A reservation is charged immediately. A
billable request that fails still cost money, and a ledger that only charged successes would let a
run of rejections walk straight past the ceiling.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import IO, Any

from packages.llm_gateway import parse_yaml, require_mapping, to_yaml
from packages.model_catalog import CostCeilingExceededError, PriceInputs
from packages.storage import ObjectStore

_JOURNAL_KEY = "spend-journal.yaml"
_LOCK_KEY = "spend-journal.lock"


@dataclass(frozen=True)
class UnsettledReservation:
    """One task holding ceiling with no settlement and no release behind it.

    HELD IS NOT SPENT AND THE TWO ARE NEVER SHOWN AS ONE NUMBER. A held reservation is money the
    ceiling has committed and the provider may never have charged. Reporting it inside `spent_usd`
    was the honest conservative choice while nothing could tell the two apart; reporting it
    SEPARATELY is the honest precise one now that something can.
    """

    task_id: str
    run_id: str
    job_id: str
    model_label: str
    held_usd: Decimal

    def to_mapping(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "model_label": self.model_label,
            "held_usd": str(self.held_usd),
        }


@dataclass(frozen=True)
class SpendEntry:
    """One reservation or settlement, with everything needed to re-derive the total.

    `task_id` and `phase` were added in Phase 2.1 and both default to empty, which is exactly what
    the 30 Phase 2 entries already in the journal mean: no multipart task, and a phase that was not
    being tracked separately. Neither changes what an existing entry contributes to the cumulative
    total.
    """

    at: str
    kind: str
    run_id: str
    job_id: str
    model_label: str
    amount_usd: Decimal
    released_usd: Decimal
    note: str = ""
    task_id: str = ""
    phase: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "kind": self.kind,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "task_id": self.task_id,
            "phase": self.phase,
            "model_label": self.model_label,
            "amount_usd": str(self.amount_usd),
            "released_usd": str(self.released_usd),
            "note": self.note,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> SpendEntry:
        return cls(
            at=str(raw["at"]),
            kind=str(raw["kind"]),
            run_id=str(raw.get("run_id") or ""),
            job_id=str(raw.get("job_id") or ""),
            model_label=str(raw.get("model_label") or ""),
            amount_usd=Decimal(str(raw["amount_usd"])),
            released_usd=Decimal(str(raw.get("released_usd") or "0")),
            note=str(raw.get("note") or ""),
            task_id=str(raw.get("task_id") or ""),
            phase=str(raw.get("phase") or ""),
        )


class SpendJournal:
    """Cumulative authorized spend, durable across restarts.

    THREE CEILINGS, EACH ANSWERING A DIFFERENT QUESTION, AND THE TIGHTEST ONE ALWAYS WINS.

        cumulative      everything this repository has ever authorized. Never resets.
        phase           what the CURRENT authorized task may spend. Phase 2 spent USD 0.40711113
                        against the same journal, and Phase 2.1 carries its own authorization; a
                        phase total is what makes "this task's ceiling" a computable fact rather
                        than an arithmetic note in a report.
        filing run      what ONE filing's parse may spend across every task it queues. A multipart
                        parse can queue a dozen billable calls off one plan, and without this a
                        single filing that planned ambitiously could consume the whole phase.

    A reservation must fit under all three or it is refused. Nothing is shrunk, dropped, downgraded
    or deferred to make it fit.
    """

    def __init__(
        self,
        objects: ObjectStore,
        *,
        ceiling_usd: Decimal | str,
        phase: str = "",
        phase_ceiling_usd: Decimal | str | None = None,
    ) -> None:
        self._objects = objects
        self._ceiling = Decimal(str(ceiling_usd))
        if self._ceiling <= 0:
            raise ValueError("a cost ceiling must be positive; use zero invocations instead")
        self._phase = phase
        self._phase_ceiling = None if phase_ceiling_usd is None else Decimal(str(phase_ceiling_usd))
        if self._phase_ceiling is not None and self._phase_ceiling <= 0:
            raise ValueError("a phase cost ceiling must be positive")
        if self._phase_ceiling is not None and not phase:
            raise ValueError(
                "a phase cost ceiling needs a phase label to attribute spend to; an unlabelled "
                "phase ceiling would be enforced against entries that belong to no phase"
            )
        self._entries: list[SpendEntry] = self._load()

    def _load(self) -> list[SpendEntry]:
        if not self._objects.exists(_JOURNAL_KEY):
            return []
        document = require_mapping(parse_yaml(self._objects.get_text(_JOURNAL_KEY)))
        return [SpendEntry.from_mapping(e) for e in (document.get("entries") or ())]

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Hold the journal lock for one read-modify-write.

        THE CEILING IS A MONEY GUARD AND IT WAS NOT CONCURRENCY-SAFE. Every entry was appended to
        an in-memory list loaded at construction, and `_save` wrote that whole list back. Two
        processes reserving at once each wrote their own view, and whichever finished second
        silently erased the other's entries — so the cumulative total under-reported real spend and
        the ceiling could be walked straight past by running two parses.

        AN ADVISORY FILE LOCK, AND ADVISORY IS ENOUGH. Every writer of this file is this class.
        The lock is held across re-read, append and write, so an entry can never be lost to a
        stale read; it is not held while a provider call is in flight, so one parse never blocks
        another for the length of a request.
        """
        import fcntl  # noqa: PLC0415 - POSIX only, and this application is POSIX only

        path = Path(getattr(self._objects, "root", ".")) / _LOCK_KEY
        path.parent.mkdir(parents=True, exist_ok=True)
        handle: IO[str] = path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _append(self, entry: SpendEntry) -> None:
        """Add one entry under the lock, re-reading first so no concurrent write is lost."""
        with self._exclusive():
            self._entries = self._load()
            self._entries.append(entry)
            self._save()

    def _save(self) -> None:
        self._objects.put_text(
            _JOURNAL_KEY,
            to_yaml(
                {
                    "schema_version": "spend-journal-v2",
                    "ceiling_usd": str(self._ceiling),
                    "spent_usd": str(self.spent_usd),
                    "phase": self._phase,
                    "phase_ceiling_usd": (
                        None if self._phase_ceiling is None else str(self._phase_ceiling)
                    ),
                    "phase_spent_usd": str(self.phase_spent_usd),
                    "entries": [e.to_mapping() for e in self._entries],
                }
            ),
            content_type="application/yaml",
        )

    @property
    def ceiling_usd(self) -> Decimal:
        return self._ceiling

    @property
    def spent_usd(self) -> Decimal:
        return sum((e.amount_usd - e.released_usd for e in self._entries), Decimal(0))

    @property
    def remaining_usd(self) -> Decimal:
        return self._ceiling - self.spent_usd

    @property
    def entries(self) -> tuple[SpendEntry, ...]:
        return tuple(self._entries)

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def phase_ceiling_usd(self) -> Decimal | None:
        return self._phase_ceiling

    @property
    def phase_spent_usd(self) -> Decimal:
        """What the current phase has spent. Zero when no phase is configured."""
        if not self._phase:
            return Decimal(0)
        return sum(
            (e.amount_usd - e.released_usd for e in self._entries if e.phase == self._phase),
            Decimal(0),
        )

    @property
    def phase_remaining_usd(self) -> Decimal | None:
        if self._phase_ceiling is None:
            return None
        return self._phase_ceiling - self.phase_spent_usd

    def spent_for_job(self, job_id: str) -> Decimal:
        """What ONE filing's parse has spent across every task it queued.

        Derived from the journal rather than summed from task records on purpose: the journal is
        the thing that was actually enforced against, and a second running total kept elsewhere is
        the one that drifts.
        """
        return sum(
            (e.amount_usd - e.released_usd for e in self._entries if e.job_id == job_id),
            Decimal(0),
        )

    def remaining_for_job(self, job_id: str, *, budget_usd: Decimal | None) -> Decimal:
        """How much this filing may still spend, under the tightest applicable ceiling."""
        limits = [self.remaining_usd]
        phase_left = self.phase_remaining_usd
        if phase_left is not None:
            limits.append(phase_left)
        if budget_usd is not None:
            limits.append(budget_usd - self.spent_for_job(job_id))
        return min(limits)

    def can_afford(
        self, amount_usd: Decimal, *, job_id: str, budget_usd: Decimal | None
    ) -> tuple[bool, str]:
        """Whether one conservative reservation fits, and which ceiling refuses it if not.

        Returned rather than raised, because the scheduler's correct response to "this does not
        fit" is to PAUSE the branch with the reason visible, not to fail the parse. The parts that
        already succeeded are kept and a person decides what to do next.
        """
        if self.spent_usd + amount_usd > self._ceiling:
            return False, (
                f"the cumulative authorized ceiling of USD {self._ceiling} would be exceeded: "
                f"USD {self.spent_usd} is already spent and this attempt reserves USD {amount_usd}"
            )
        if (
            self._phase_ceiling is not None
            and self.phase_spent_usd + amount_usd > self._phase_ceiling
        ):
            return False, (
                f"the phase {self._phase} ceiling of USD {self._phase_ceiling} would be exceeded: "
                f"USD {self.phase_spent_usd} is already spent in this phase and this attempt "
                f"reserves USD {amount_usd}"
            )
        if budget_usd is not None and self.spent_for_job(job_id) + amount_usd > budget_usd:
            return False, (
                f"this filing's own budget of USD {budget_usd} would be exceeded: USD "
                f"{self.spent_for_job(job_id)} is already spent on it and this attempt reserves "
                f"USD {amount_usd}"
            )
        return True, ""

    @staticmethod
    def bound(price: PriceInputs, *, max_input_tokens: int, max_output_tokens: int) -> Decimal:
        """The worst-case cost of one invocation. No side effect; safe to show a user."""
        return price.cost(max_input_tokens, max_output_tokens)

    def authorize(
        self,
        price: PriceInputs,
        *,
        max_input_tokens: int,
        max_output_tokens: int,
        at: str,
        run_id: str,
        job_id: str,
        model_label: str,
        task_id: str = "",
        filing_budget_usd: Decimal | None = None,
    ) -> Decimal:
        """Reserve the worst case against every applicable ceiling, or refuse."""
        estimate = self.bound(
            price, max_input_tokens=max_input_tokens, max_output_tokens=max_output_tokens
        )
        affordable, reason = self.can_afford(estimate, job_id=job_id, budget_usd=filing_budget_usd)
        if not affordable:
            raise CostCeilingExceededError(
                f"invocation refused: {reason}. Nothing is shrunk, dropped or downgraded to fit.",
                ceiling_usd=str(self._ceiling),
                spent_usd=str(self.spent_usd),
                estimate_usd=str(estimate),
            )
        self._append(
            SpendEntry(
                at=at,
                kind="RESERVATION",
                run_id=run_id,
                job_id=job_id,
                model_label=model_label,
                amount_usd=estimate,
                released_usd=Decimal(0),
                note=f"worst case at {max_input_tokens} input and {max_output_tokens} output tokens",
                task_id=task_id,
                phase=self._phase,
            )
        )
        return estimate

    def settle(
        self,
        price: PriceInputs,
        *,
        reserved: Decimal,
        input_tokens: int,
        output_tokens: int,
        at: str,
        run_id: str,
        job_id: str,
        model_label: str,
        task_id: str = "",
    ) -> Decimal:
        """Replace a reservation with the measured cost, recording both halves."""
        actual = price.cost(input_tokens, output_tokens)
        self._append(
            SpendEntry(
                at=at,
                kind="SETTLEMENT",
                run_id=run_id,
                job_id=job_id,
                model_label=model_label,
                amount_usd=actual,
                released_usd=reserved,
                note=f"measured {input_tokens} input and {output_tokens} output tokens",
                task_id=task_id,
                phase=self._phase,
            )
        )
        return actual

    def release(
        self,
        *,
        reserved: Decimal,
        at: str,
        run_id: str,
        job_id: str,
        model_label: str,
        task_id: str,
        evidence: str,
    ) -> Decimal:
        """Return a reservation to the ceiling because NO PROVIDER TRANSPORT OCCURRED.

        THE MECHANISM AND ITS JUSTIFICATION WERE NOT THE SAME SIZE, AND THIS IS WHERE THEY MEET.
        This module has always said "a billable request that failed still cost money, and a ledger
        that only charged successes would let a run of rejections walk straight past the ceiling".
        That is true of a request that REACHED a provider. It is false of one that never left this
        machine, and Phase 2.1 held real ceiling for eleven of those.

            MEASURED IN THE DURABLE JOURNAL. Twelve task ids held unsettled reservations totalling
            USD 0.24197085. Eleven were `TokenRetrievalError: Token has expired and refresh failed`,
            every one with zero input tokens, zero output tokens, zero latency and no provider
            request id — USD 0.22590990 of ceiling held for calls no provider ever saw. The twelfth,
            USD 0.01606095, is a different defect: a task interrupted after reserving, resumed, and
            reserved a second time, with only the later reservation settled.

        WHAT THIS IS NOT. It is not a way to un-charge a failure. A request that reached a provider
        is charged whatever it returned, and it stays charged. Releasing requires POSITIVE evidence
        that transport did not occur, `evidence` records what that evidence was, and a caller who
        cannot supply it must not call this.

        THE JOURNAL STAYS APPEND-ONLY. A RELEASE entry carries `amount_usd = 0` and
        `released_usd = reserved`, so it contributes exactly the negative of the reservation to
        `sum(amount - released)` and no total needs different arithmetic. Nothing is edited, nothing
        is deleted, and the original reservation stays visible with its timestamp.
        """
        if reserved <= 0:
            raise ValueError("a release must name the positive amount it returns to the ceiling")
        if not evidence.strip():
            raise ValueError(
                "a release must record the evidence that no provider transport occurred; a "
                "release with no evidence is indistinguishable from un-charging a real failure"
            )
        self._append(
            SpendEntry(
                at=at,
                kind="RELEASE",
                run_id=run_id,
                job_id=job_id,
                model_label=model_label,
                amount_usd=Decimal(0),
                released_usd=reserved,
                note=evidence,
                task_id=task_id,
                phase=self._phase,
            )
        )
        return reserved

    def unsettled(self) -> tuple[UnsettledReservation, ...]:
        """Every reservation with no matching settlement or release, by task.

        REPORTED RATHER THAN RESOLVED. This is the input to a decision, not the decision: whether a
        given unsettled reservation may be released depends on whether transport can be proved not
        to have occurred, and only the attempt record knows that.
        """
        # HELD IS NOT NET SPEND, AND CONFUSING THE TWO REPORTS EVERY HEALTHY TASK AS UNSETTLED.
        # A settled task's entries sum to `reserved + (actual - reserved)`, which is `actual` — a
        # positive number, and exactly the money it really cost. What is HELD is the reservation
        # side alone, minus whatever a settlement or a release gave back.
        held: dict[str, Decimal] = {}
        labels: dict[str, str] = {}
        runs: dict[str, str] = {}
        jobs: dict[str, str] = {}
        for entry in self._entries:
            if not entry.task_id:
                continue
            delta = entry.amount_usd if entry.kind == "RESERVATION" else -entry.released_usd
            held[entry.task_id] = held.get(entry.task_id, Decimal(0)) + delta
            labels.setdefault(entry.task_id, entry.model_label)
            runs.setdefault(entry.task_id, entry.run_id)
            jobs.setdefault(entry.task_id, entry.job_id)
        return tuple(
            UnsettledReservation(
                task_id=task_id,
                run_id=runs[task_id],
                job_id=jobs[task_id],
                model_label=labels[task_id],
                held_usd=amount,
            )
            for task_id, amount in sorted(held.items())
            if amount > 0
        )
