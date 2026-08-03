"""Provider-neutral model capability catalog: what a model can do, where, and at what price.

WHAT THIS PACKAGE IS. The durable half of Phase 1. Live discovery produced a dated, reviewed
capability snapshot; this package reads it and answers three questions without guessing at any of
them — does the label the user selected resolve to exactly one real model, may it fill the role in
the region asked for, and what would an invocation cost at worst before it is made.

WHAT THIS PACKAGE IS NOT. It is not a provider adapter and it holds no AWS import, no ARN, no
endpoint, no credential and no region literal. It never invokes anything. The Bedrock adapter is
Phase 2 work and lives in packages/llm_gateway/providers/bedrock.py, which rules.md section 5
names as the only home for provider SDK usage.

THE RULE IT EXISTS TO ENFORCE. rules.md section 21 rules 8, 9, 10 and 11: the four model roles are
selected independently, an unavailable model is REPORTED rather than replaced, nothing is silently
truncated or re-routed, and no billable invocation happens without a preview against a ceiling. All
four are things code has to refuse to do, so every failure here is a raised, named error carrying
the sentence a user should read.

NO MODEL IDENTIFIER, REGION, LIMIT OR PRICE APPEARS IN THIS SOURCE. Every one is supplied from the
reviewed snapshot in docs/llm/bedrock-capability-snapshot.yaml — the same discipline the
form-family contract established after a hardcoded allowlist in runtime source produced a
confident, precise and completely inverted conclusion.
"""

from .capabilities import (
    Availability,
    Mapping,
    ModelCapability,
    ModelRole,
    PriceInputs,
    SmokeInstruction,
    SmokeTransport,
)
from .catalog import CapabilitySnapshot, ResolvedModel, load_snapshot
from .errors import (
    AmbiguousModelLabelError,
    CapabilityContradictionError,
    CostCeilingExceededError,
    ModelCatalogError,
    ModelUnavailableError,
    RetryBudgetExceededError,
    SnapshotFormatError,
    UnknownModelLabelError,
)
from .routing import (
    RoleSelection,
    RoutingDecision,
    SelectorEntry,
    route,
    route_selection,
    selector_entries,
)
from .spend import RetryBudget, SpendLedger

__all__ = [
    "AmbiguousModelLabelError",
    "Availability",
    "CapabilityContradictionError",
    "CapabilitySnapshot",
    "CostCeilingExceededError",
    "Mapping",
    "ModelCapability",
    "ModelCatalogError",
    "ModelRole",
    "ModelUnavailableError",
    "PriceInputs",
    "ResolvedModel",
    "RetryBudget",
    "RoleSelection",
    "RoutingDecision",
    "RetryBudgetExceededError",
    "SelectorEntry",
    "SmokeInstruction",
    "SmokeTransport",
    "SnapshotFormatError",
    "SpendLedger",
    "UnknownModelLabelError",
    "load_snapshot",
    "route",
    "route_selection",
    "selector_entries",
]
