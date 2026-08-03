"""Four-role routing: which model, in which region, for which role — and never a substitute.

THIS COMPLETES `packages/model_catalog`. techspecs.md recorded the package as arriving in Phase 1
carrying half its eventual responsibility: the capability record, the label mapping, the price
inputs and the cost ceiling existed; the four-role router did not, and the single-home row stayed
RESERVED rather than being marked done. This module is that router.

THE FOUR ROLES ARE INDEPENDENT AND ONLY PARSING IS REQUIRED. rules.md section 21 rule 8. A blank
image, summary or analysis selector is a legitimate, complete configuration: the stage does not
run, no model is chosen for it, and the parsing model is never borrowed to fill it. `RoleSelection`
represents a blank role as `None` rather than as an absent key, so "the user chose nothing" is a
value the record can hold and a reviewer can see.

REGION ROUTING IS DERIVED FROM THE REVIEWED SNAPSHOT AND IS NEVER SILENT.

    The product is explicitly NOT restricted to one region. A model is routed to the preferred
    region when the snapshot verified it there, and otherwise to the FIRST region the snapshot
    verified — in snapshot order, which is why `verified_regions` is an ordered tuple rather than
    a set. That derivation introduces no new fact: every region it can produce is one a live API
    already answered in, recorded in exactly one file.

    Every such route is DISCLOSED. `RoutingDecision` carries `in_preferred_region` and a
    `cross_region_reason` sentence, and both travel into the run plan, the child job, the request
    evidence, the response evidence, the cost record and the artifact lineage. Cross-region
    inference and the data movement it implies are shown before the invocation, not discovered in
    a bill afterwards.

    THERE IS NO REGION LITERAL IN THIS FILE, and `tests/architecture/test_phase1_aws_boundary.py`
    fails the build if one appears. The preferred region is supplied by configuration; the
    candidates come from the snapshot. That is the same discipline the qualifying-form set is held
    to, after a guessed allowlist in runtime source produced a confident and inverted conclusion.

WHAT THIS MODULE REFUSES TO DO. Choose a model for a blank role. Substitute another model when the
selected one is unavailable. Widen a region beyond what was verified. Downgrade a role. Pick
between ambiguous matches. Every one of those raises with the reason, because rules.md section 21
rules 9 and 10 say the answer to "it does not fit" is a sentence the user reads, not a quiet
different answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .capabilities import ModelCapability, ModelRole
from .catalog import CapabilitySnapshot, ResolvedModel
from .errors import ModelUnavailableError


@dataclass(frozen=True)
class RoutingDecision:
    """One resolved role: the model, the region, and whether that region was the preferred one."""

    resolved: ResolvedModel
    preferred_region: str
    in_preferred_region: bool
    cross_region_reason: str | None

    @property
    def label(self) -> str:
        return self.resolved.label

    @property
    def role(self) -> ModelRole:
        return self.resolved.role

    @property
    def region(self) -> str:
        return self.resolved.region

    @property
    def invocation_id(self) -> str:
        return self.resolved.invocation_id

    @property
    def capability(self) -> ModelCapability:
        return self.resolved.capability

    @property
    def uses_inference_profile(self) -> bool:
        return self.resolved.capability.inference_profile_required

    def to_mapping(self) -> dict[str, Any]:
        capability = self.resolved.capability
        return {
            "label": self.label,
            "role": self.role.value,
            "model_id": capability.model_id,
            "invocation_id": self.invocation_id,
            "region": self.region,
            "preferred_region": self.preferred_region,
            "in_preferred_region": self.in_preferred_region,
            "inference_profile_id": capability.inference_profile_id,
            "cross_region_reason": self.cross_region_reason,
            "multimodal": capability.multimodal,
        }


@dataclass(frozen=True)
class RoleSelection:
    """What the user selected for each of the four roles. Only `parsing` may not be blank."""

    parsing: str
    image: str | None = None
    summary: str | None = None
    analysis: str | None = None

    def __post_init__(self) -> None:
        if not self.parsing or not self.parsing.strip():
            raise ValueError(
                "a parsing model is required. The other three roles may be left blank, and a "
                "blank role runs NO stage rather than borrowing the parsing model."
            )

    @property
    def selected_roles(self) -> tuple[ModelRole, ...]:
        """The roles that will execute, in order. A blank role is simply absent."""
        roles = [ModelRole.PARSING]
        if self.image:
            roles.append(ModelRole.IMAGE)
        if self.summary:
            roles.append(ModelRole.SUMMARY)
        if self.analysis:
            roles.append(ModelRole.ANALYSIS)
        return tuple(roles)

    def label_for(self, role: ModelRole) -> str | None:
        return {
            ModelRole.PARSING: self.parsing,
            ModelRole.IMAGE: self.image,
            ModelRole.SUMMARY: self.summary,
            ModelRole.ANALYSIS: self.analysis,
        }[role]


def route(
    snapshot: CapabilitySnapshot,
    label: str,
    *,
    role: ModelRole,
    preferred_region: str,
) -> RoutingDecision:
    """Resolve one label to something invocable, disclosing any cross-region route."""
    if not preferred_region:
        raise ModelUnavailableError(
            "no preferred region is configured. There is deliberately no default: a default is "
            "how a guessed region survives review, and one approved candidate is not offered in "
            "the project's preferred region at all.",
            label=label,
            reason="no preferred region configured",
        )

    capability = snapshot.get(label)
    if preferred_region in capability.verified_regions:
        return RoutingDecision(
            resolved=snapshot.resolve(label, role=role, region=preferred_region),
            preferred_region=preferred_region,
            in_preferred_region=True,
            cross_region_reason=None,
        )

    if not capability.verified_regions:
        raise ModelUnavailableError(
            f"{label!r} names no verified region at all, so nothing can invoke it",
            label=label,
            reason="the reviewed snapshot records no verified region for this candidate",
        )

    # The first region the reviewed snapshot verified. Deterministic, recorded, and disclosed.
    chosen = capability.verified_regions[0]
    reason = (
        f"{label} is not verified in {preferred_region}. It is routed to {chosen}, the first "
        f"region the reviewed capability snapshot verified it in (verified: "
        f"{', '.join(capability.verified_regions)}). This is a deliberate cross-region route, "
        "shown before the invocation and recorded with the request, the response, the cost and "
        "the artifact lineage. Cross-region inference moves request content between AWS regions."
    )
    return RoutingDecision(
        resolved=snapshot.resolve(label, role=role, region=chosen),
        preferred_region=preferred_region,
        in_preferred_region=False,
        cross_region_reason=reason,
    )


def route_selection(
    snapshot: CapabilitySnapshot,
    selection: RoleSelection,
    *,
    preferred_region: str,
) -> dict[ModelRole, RoutingDecision]:
    """Route every SELECTED role. A blank role produces no entry and invokes nothing.

    The returned mapping is what the orchestrator iterates. A role absent from it is a role that
    does not run — which is how a parser-only run stays a parser-only run without a flag anywhere
    saying so.
    """
    routed: dict[ModelRole, RoutingDecision] = {}
    for role in selection.selected_roles:
        label = selection.label_for(role)
        assert label is not None  # guaranteed by selected_roles
        routed[role] = route(snapshot, label, role=role, preferred_region=preferred_region)
    return routed


@dataclass(frozen=True)
class SelectorEntry:
    """One row of a model dropdown, with everything the UX specification requires on it.

    AN UNVERIFIED FIELD IS RENDERED AS UNVERIFIED, NEVER AS BLANK AND NEVER AS A GUESS. A missing
    context limit reads `context limit not verified`, which is a different statement from a large
    number. Nothing here is populated from anywhere but the reviewed snapshot.

    A DISABLED ROW ALWAYS CARRIES A CONCRETE REASON. A greyed row with no explanation sends a user
    to a support channel, and `packages/model_catalog` returns disabled candidates rather than
    filtering them away precisely so the reason has somewhere to go.
    """

    label: str
    provider: str
    version: str
    region: str
    in_preferred_region: bool
    inference_profile_id: str | None
    text_input: bool
    image_input: bool
    multimodal: bool
    context_tokens: int
    max_output_tokens: int
    available: bool
    disabled_reason: str | None
    price_input_per_1k: Decimal
    price_output_per_1k: Decimal
    currency: str

    @property
    def capability_badge(self) -> str:
        """The badge the UX specification requires: `Multimodal` or `Text only`."""
        return "Multimodal" if self.multimodal else "Text only"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "provider": self.provider,
            "version": self.version or "unverified",
            "region": self.region,
            "in_preferred_region": self.in_preferred_region,
            "inference_profile_id": self.inference_profile_id,
            "uses_inference_profile": bool(self.inference_profile_id),
            "text_input": self.text_input,
            "image_input": self.image_input,
            "multimodal": self.multimodal,
            "badge": self.capability_badge,
            "context_tokens": self.context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "available": self.available,
            "disabled_reason": self.disabled_reason,
            "price_input_per_1k": str(self.price_input_per_1k),
            "price_output_per_1k": str(self.price_output_per_1k),
            "currency": self.currency,
        }


def selector_entries(
    snapshot: CapabilitySnapshot, *, role: ModelRole, preferred_region: str
) -> tuple[SelectorEntry, ...]:
    """Every candidate as a dropdown row, in snapshot order, enabled and disabled alike.

    A candidate that silently vanishes from a selector is indistinguishable from one that was
    never approved, so nothing is filtered out. A candidate that cannot fill this role in any
    verified region comes back disabled, with the reason on the row.
    """
    entries: list[SelectorEntry] = []
    for capability in snapshot.candidates:
        region = (
            preferred_region
            if preferred_region in capability.verified_regions
            else (capability.verified_regions[0] if capability.verified_regions else "")
        )
        reason = (
            capability.unavailable_reason(role=role, region=region)
            if region
            else f"{capability.label} names no verified region at all."
        )
        entries.append(
            SelectorEntry(
                label=capability.label,
                provider=capability.provider,
                version=capability.version_qualifier,
                region=region,
                in_preferred_region=region == preferred_region,
                inference_profile_id=capability.inference_profile_id,
                text_input=capability.text_input,
                image_input=capability.image_input,
                multimodal=capability.multimodal,
                context_tokens=capability.context_tokens,
                max_output_tokens=capability.max_output_tokens,
                available=reason is None,
                disabled_reason=reason,
                price_input_per_1k=capability.price.input_per_1k,
                price_output_per_1k=capability.price.output_per_1k,
                currency=capability.price.currency,
            )
        )
    return tuple(entries)
