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

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from packages.llm_gateway import parse_yaml, require_mapping, to_yaml
from packages.model_catalog import CostCeilingExceededError, PriceInputs
from packages.storage import ObjectStore

_JOURNAL_KEY = "spend-journal.yaml"


@dataclass(frozen=True)
class SpendEntry:
    """One reservation or settlement, with everything needed to re-derive the total."""

    at: str
    kind: str
    run_id: str
    job_id: str
    model_label: str
    amount_usd: Decimal
    released_usd: Decimal
    note: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "kind": self.kind,
            "run_id": self.run_id,
            "job_id": self.job_id,
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
        )


class SpendJournal:
    """Cumulative authorized spend, durable across restarts."""

    def __init__(self, objects: ObjectStore, *, ceiling_usd: Decimal | str) -> None:
        self._objects = objects
        self._ceiling = Decimal(str(ceiling_usd))
        if self._ceiling <= 0:
            raise ValueError("a cost ceiling must be positive; use zero invocations instead")
        self._entries: list[SpendEntry] = self._load()

    def _load(self) -> list[SpendEntry]:
        if not self._objects.exists(_JOURNAL_KEY):
            return []
        document = require_mapping(parse_yaml(self._objects.get_text(_JOURNAL_KEY)))
        return [SpendEntry.from_mapping(e) for e in (document.get("entries") or ())]

    def _save(self) -> None:
        self._objects.put_text(
            _JOURNAL_KEY,
            to_yaml(
                {
                    "schema_version": "spend-journal-v1",
                    "ceiling_usd": str(self._ceiling),
                    "spent_usd": str(self.spent_usd),
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
    ) -> Decimal:
        """Reserve the worst case against the cumulative ceiling, or refuse."""
        estimate = self.bound(
            price, max_input_tokens=max_input_tokens, max_output_tokens=max_output_tokens
        )
        if self.spent_usd + estimate > self._ceiling:
            raise CostCeilingExceededError(
                "invocation refused: the conservative bound would push CUMULATIVE spend past the "
                "authorized ceiling. Nothing is shrunk, dropped or downgraded to fit.",
                ceiling_usd=str(self._ceiling),
                spent_usd=str(self.spent_usd),
                estimate_usd=str(estimate),
            )
        self._entries.append(
            SpendEntry(
                at=at,
                kind="RESERVATION",
                run_id=run_id,
                job_id=job_id,
                model_label=model_label,
                amount_usd=estimate,
                released_usd=Decimal(0),
                note=f"worst case at {max_input_tokens} input and {max_output_tokens} output tokens",
            )
        )
        self._save()
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
    ) -> Decimal:
        """Replace a reservation with the measured cost, recording both halves."""
        actual = price.cost(input_tokens, output_tokens)
        self._entries.append(
            SpendEntry(
                at=at,
                kind="SETTLEMENT",
                run_id=run_id,
                job_id=job_id,
                model_label=model_label,
                amount_usd=actual,
                released_usd=reserved,
                note=f"measured {input_tokens} input and {output_tokens} output tokens",
            )
        )
        self._save()
        return actual
