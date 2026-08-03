"""Load a reviewed capability snapshot and resolve a user-facing label to something invocable.

THE SNAPSHOT IS SUPPLIED AND HAS NO DEFAULT PATH. `load_snapshot` takes text. Nothing in this
package knows where the file lives, and there is no fallback to a bundled copy, because a fallback
is how a stale catalog keeps answering after the real one has moved. The reviewed snapshot lives in
docs/llm/bedrock-capability-snapshot.yaml and the caller supplies it.

RESOLUTION FAILS LOUDLY. `resolve` returns the model that was asked for or raises. It never returns
a substitute, never widens the region, never downgrades the role and never picks between ambiguous
matches — rules.md section 21 rules 8, 9 and 10.

YAML PARSING IS NOT REIMPLEMENTED HERE. The hardened YAML 1.2 safe parser in packages/llm_gateway
is the single home for that, alias budget and all, and rules.md section 5 forbids a second copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from packages.llm_gateway import parse_yaml, require_mapping

from .capabilities import (
    Availability,
    Mapping,
    ModelCapability,
    ModelRole,
    PriceInputs,
    SmokeInstruction,
    SmokeTransport,
)
from .errors import (
    AmbiguousModelLabelError,
    ModelUnavailableError,
    SnapshotFormatError,
    UnknownModelLabelError,
)

_REQUIRED_SNAPSHOT_KEYS = (
    "snapshot_version",
    "verified_on",
    "price_source",
    "price_effective_date",
    "price_currency",
    "candidates",
)

_REQUIRED_CANDIDATE_KEYS = (
    "label",
    "provider",
    "model_id",
    "model_name",
    "mapping",
    "availability",
    "verified_regions",
    "inference_profile_required",
    "text_input",
    "image_input",
    "multimodal",
    "image_verified",
    "context_tokens",
    "max_output_tokens",
    "invocation_apis",
    "streaming_supported",
    "price_input_per_1k",
    "price_output_per_1k",
    "smoke_transport",
    "smoke_instruction",
)


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise SnapshotFormatError(f"{where} is missing required field {key!r}")
    return mapping[key]


def _as_bool(value: Any, key: str, where: str) -> bool:
    if not isinstance(value, bool):
        raise SnapshotFormatError(f"{where}.{key} must be a boolean, got {type(value).__name__}")
    return value


def _as_int(value: Any, key: str, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotFormatError(f"{where}.{key} must be an integer, got {type(value).__name__}")
    return value


def _as_decimal(value: Any, key: str, where: str) -> Decimal:
    """Convert through str, never through float.

    `Decimal(0.00015)` is 0.000149999999999999993145... because that is what the binary double
    actually holds. `Decimal(str(0.00015))` is exactly 0.00015. The difference is invisible on one
    invocation and is not invisible over a corpus.
    """
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise SnapshotFormatError(f"{where}.{key} is not a number: {value!r}") from error


def _as_str_tuple(value: Any, key: str, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SnapshotFormatError(f"{where}.{key} must be a list of strings")
    return tuple(value)


def _enum[E: StrEnum](enum_cls: type[E], value: Any, key: str, where: str) -> E:
    """Resolve a snapshot string to an enum member, naming the permitted ones when it does not.

    An error that only says "invalid" makes a reader open the source to find out what was allowed.
    """
    try:
        return enum_cls(str(value))
    except ValueError as error:
        permitted = ", ".join(sorted(member.value for member in enum_cls))
        raise SnapshotFormatError(
            f"{where}.{key} is {value!r}; permitted values are {permitted}"
        ) from error


@dataclass(frozen=True)
class CapabilitySnapshot:
    """Every verified candidate, plus the provenance that makes the numbers checkable."""

    snapshot_version: str
    verified_on: str
    verified_from_region: str
    price_source: str
    price_effective_date: str
    price_currency: str
    candidates: tuple[ModelCapability, ...]

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(c.label for c in self.candidates)

    def get(self, label: str) -> ModelCapability:
        """The record for one user-facing label, or a failure naming what does exist."""
        for candidate in self.candidates:
            if candidate.label == label:
                return candidate
        raise UnknownModelLabelError(
            f"no candidate is labelled {label!r}. Known labels: {', '.join(self.labels)}"
        )

    def resolve(self, label: str, *, role: ModelRole, region: str) -> ResolvedModel:
        """The invocable identity for a label in a role and region, or a raised reason.

        There is deliberately no `default=` and no `fallback=`. A caller that cannot use what the
        user selected reports that; it does not choose something else.
        """
        capability = self.get(label)
        if capability.mapping is Mapping.AMBIGUOUS:
            raise AmbiguousModelLabelError(
                f"{label!r} matches more than one provider model; the choice is a product "
                "decision and is not made here"
            )
        reason = capability.unavailable_reason(role=role, region=region)
        if reason is not None:
            raise ModelUnavailableError(
                f"{label!r} cannot fill the {role.value} role in {region}: {reason}",
                label=label,
                reason=reason,
            )
        return ResolvedModel(
            label=capability.label,
            role=role,
            region=region,
            invocation_id=capability.invocation_id,
            capability=capability,
        )

    def selectable(self, *, role: ModelRole, region: str) -> tuple[str, ...]:
        """Labels a selector may offer enabled, in snapshot order."""
        return tuple(
            c.label
            for c in self.candidates
            if c.unavailable_reason(role=role, region=region) is None
        )

    def disabled(self, *, role: ModelRole, region: str) -> tuple[tuple[str, str], ...]:
        """Labels a selector must show DISABLED, each with the concrete reason.

        Returned rather than filtered away on purpose. A candidate that silently disappears from a
        dropdown is indistinguishable from one that was never approved.
        """
        out = []
        for candidate in self.candidates:
            reason = candidate.unavailable_reason(role=role, region=region)
            if reason is not None:
                out.append((candidate.label, reason))
        return tuple(out)


@dataclass(frozen=True)
class ResolvedModel:
    """Exactly what a caller invokes, and nothing implicit about it."""

    label: str
    role: ModelRole
    region: str
    invocation_id: str
    capability: ModelCapability

    @property
    def multimodal(self) -> bool:
        return self.capability.multimodal


def _candidate(
    raw: Any, index: int, *, currency: str, source: str, effective_date: str
) -> ModelCapability:
    """One candidate record, built once and complete.

    The price PROVENANCE is stated once at the top of the snapshot and is passed in here rather
    than attached afterwards, so a `PriceInputs` never exists in a half-built state where its
    source and date are blank. A price that can be read without knowing when it was true is a
    price that will be quoted after it stops being true.
    """
    where = f"candidates[{index}]"
    mapping = require_mapping(raw) if isinstance(raw, dict) else None
    if mapping is None:
        raise SnapshotFormatError(f"{where} is not a mapping")
    for key in _REQUIRED_CANDIDATE_KEYS:
        _require(mapping, key, where)

    price = PriceInputs(
        input_per_1k=_as_decimal(mapping["price_input_per_1k"], "price_input_per_1k", where),
        output_per_1k=_as_decimal(mapping["price_output_per_1k"], "price_output_per_1k", where),
        currency=currency,
        source=source,
        effective_date=effective_date,
    )

    return ModelCapability(
        label=str(mapping["label"]),
        provider=str(mapping["provider"]),
        model_id=str(mapping["model_id"]),
        model_name=str(mapping["model_name"]),
        version_qualifier=str(mapping.get("version_qualifier") or ""),
        mapping=_enum(Mapping, mapping["mapping"], "mapping", where),
        availability=_enum(Availability, mapping["availability"], "availability", where),
        access_status=str(mapping.get("access_status") or ""),
        verified_regions=_as_str_tuple(mapping["verified_regions"], "verified_regions", where),
        inference_profile_required=_as_bool(
            mapping["inference_profile_required"], "inference_profile_required", where
        ),
        inference_profile_id=(
            str(mapping["inference_profile_id"])
            if mapping.get("inference_profile_id") is not None
            else None
        ),
        text_input=_as_bool(mapping["text_input"], "text_input", where),
        image_input=_as_bool(mapping["image_input"], "image_input", where),
        multimodal=_as_bool(mapping["multimodal"], "multimodal", where),
        image_verified=_as_bool(mapping["image_verified"], "image_verified", where),
        context_tokens=_as_int(mapping["context_tokens"], "context_tokens", where),
        max_output_tokens=_as_int(mapping["max_output_tokens"], "max_output_tokens", where),
        invocation_apis=_as_str_tuple(mapping["invocation_apis"], "invocation_apis", where),
        streaming_supported=_as_bool(mapping["streaming_supported"], "streaming_supported", where),
        price=price,
        smoke_transport=_enum(SmokeTransport, mapping["smoke_transport"], "smoke_transport", where),
        smoke_instruction=_enum(
            SmokeInstruction, mapping["smoke_instruction"], "smoke_instruction", where
        ),
        blocker=str(mapping["blocker"]) if mapping.get("blocker") is not None else None,
        disabled_reason=(
            str(mapping["disabled_reason"]) if mapping.get("disabled_reason") is not None else None
        ),
    )


def load_snapshot(text: str) -> CapabilitySnapshot:
    """Parse a reviewed capability snapshot from unfenced YAML 1.2 text.

    Every required field is checked here rather than defaulted, so a snapshot that lost a price or
    a region list fails at load with the field named, instead of producing a catalog that looks
    complete and quietly understates cost.
    """
    document = require_mapping(parse_yaml(text))
    for key in _REQUIRED_SNAPSHOT_KEYS:
        _require(document, key, "snapshot")

    raw_candidates = document["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise SnapshotFormatError("snapshot.candidates must be a non-empty list")

    currency = str(document["price_currency"])
    source = str(document["price_source"])
    effective = str(document["price_effective_date"])

    candidates: list[ModelCapability] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_candidates):
        candidate = _candidate(
            raw, index, currency=currency, source=source, effective_date=effective
        )
        if candidate.label in seen:
            raise SnapshotFormatError(
                f"duplicate label {candidate.label!r}; a label must resolve to one record"
            )
        seen.add(candidate.label)
        candidates.append(candidate)

    return CapabilitySnapshot(
        snapshot_version=str(document["snapshot_version"]),
        verified_on=str(document["verified_on"]),
        verified_from_region=str(document.get("verified_from_region") or ""),
        price_source=source,
        price_effective_date=effective,
        price_currency=currency,
        candidates=tuple(candidates),
    )
