"""The model-directed multipart parsing protocol: envelopes, structural validation, assembly.

WHAT PHASE 2.1 WITHDREW. Phase 2 sent a complete filing intact and then expected the complete
parsed artifact to fit inside ONE provider response. An output cap applies to one response. It does
not require one logical filing parse to use one response, and that assumption is withdrawn.

WHAT REPLACED IT. One logical parse composed from a compact model-created plan, independently
complete model-created part responses, model-created subparts where a part is too large, one or
more model-created reconciliation responses, and mechanical orchestration by the backend.

    intact filing
      -> model-created parse plan
      -> model-created parts
      -> model-created subparts when needed
      -> model-created reconciliation
      -> mechanically assembled filing parse
      -> human review

WHAT THIS PACKAGE DOES NOT CONTAIN, AND MUST NEVER. Any decision about what a filing's parts ARE.
The backend does not decide that one section is one part, that tables are separate, that exhibits
are excluded, or that a heading starts a section. The SELECTED PARSING MODEL creates the plan from
the intact filing, and everything here is structure, scheduling and provenance around that.

BLIND CONTINUATION IS NOT THE PROTOCOL AND IS NOT IMPLEMENTED ANYWHERE. There is no function in
this repository that asks a model to continue an interrupted response from where `max_tokens` cut
it off, and none that concatenates response fragments into one document. Every normal part response
is a complete standalone YAML 1.2 document. A truncated response is preserved exactly, marked
TRUNCATED, and handed to a model-directed REPLANNING call that proposes subparts covering the same
part — because nothing about a language model guarantees it can resume a scalar, close a structure
it cannot see, avoid duplicating what it already wrote, or remember where it stopped.
"""

from .assembly import (
    AssembledPart,
    AssemblyInputs,
    AssemblyStatus,
    assemble,
    order_parts,
)
from .envelopes import (
    PART_ENVELOPE_KEYS,
    PLAN_ENVELOPE_KEYS,
    SETTLED_PART_STATUSES,
    ParsePlan,
    PartArtifact,
    PartStatus,
    PlanAmendment,
    PlannedPart,
    ProposedPart,
    ReplanOutcome,
    read_amendment,
    read_part,
    read_plan,
    read_replan,
)
from .errors import (
    EnvelopeUnreadableError,
    MultipartError,
    PlanCycleError,
    RecursionDepthExceededError,
    UnsafePartIdentifierError,
)
from .identity import (
    MAX_PART_IDENTIFIER_CHARACTERS,
    require_part_identifier,
    storage_token,
)
from .validation import (
    AssemblyValidation,
    PartValidation,
    PlanValidation,
    acceptable_new_parts,
    validate_assembly,
    validate_part,
    validate_plan,
)

__all__ = [
    "MAX_PART_IDENTIFIER_CHARACTERS",
    "PART_ENVELOPE_KEYS",
    "PLAN_ENVELOPE_KEYS",
    "SETTLED_PART_STATUSES",
    "AssembledPart",
    "AssemblyInputs",
    "AssemblyStatus",
    "AssemblyValidation",
    "EnvelopeUnreadableError",
    "MultipartError",
    "ParsePlan",
    "PartArtifact",
    "PartStatus",
    "PartValidation",
    "PlanAmendment",
    "PlanCycleError",
    "PlanValidation",
    "PlannedPart",
    "ProposedPart",
    "RecursionDepthExceededError",
    "ReplanOutcome",
    "UnsafePartIdentifierError",
    "acceptable_new_parts",
    "assemble",
    "order_parts",
    "read_amendment",
    "read_part",
    "read_plan",
    "read_replan",
    "require_part_identifier",
    "storage_token",
    "validate_assembly",
    "validate_part",
    "validate_plan",
]
