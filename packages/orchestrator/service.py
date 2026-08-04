"""Parent runs, child filing jobs, and the parser-only workflow that executes them.

ONE PARENT RUN PER REQUEST, ONE CHILD JOB PER FILING, NEVER CONCATENATED. A five-year request is
five independent billable units under one visible identifier. rules.md section 1 point 5 and the
Phase 2 brief both say so, and the reason is not tidiness: a multi-year request concatenated into
one invocation cannot be reviewed, cannot be costed per filing, cannot be approved per filing, and
cannot fail per filing.

ONLY THE SELECTED STAGES RUN, AND ONLY THE PARSER IS SELECTED IN THIS PHASE. `route_selection`
returns one entry per SELECTED role, and this service iterates that mapping. A blank image, summary
or analysis selector produces no entry and therefore no stage — there is no `if summary_enabled`
anywhere, because the absence of the entry IS the absence of the stage. Phase 2 additionally
refuses to execute anything but parsing, so a selector that was filled in by mistake fails loudly
rather than spending money on an unauthorized stage.

THE ORDER OF ONE CHILD JOB.

    CREATED            the job exists and knows its filing and its model
    SOURCE_READY       the source set is assembled: local first, hash-verified, missing fetched
    PREFLIGHT          compatibility and a worst-case cost bound are computed and recorded
    QUEUED             the bound was authorized against the CUMULATIVE ceiling
    RUNNING            the provider has been called
    RESPONSE_RECEIVED  exact bytes are durable BEFORE anything is claimed about them
    VALIDATING         references are resolved against the preserved source
    READY_FOR_REVIEW   a person can look at it

    A validation VERDICT never produces FAILED. An unparseable response still reaches review: it
    was bought, it cannot be regenerated for free, and whether the prompt or the model is at fault
    is exactly what a reviewer is there to decide.

NOTHING IS EVER SUBSTITUTED. No fallback model, no fallback region, no fallback prompt, no
fallback output format, no automatic parser substitution. A failure stays attached to the model the
user selected — rules.md section 21 rule 9.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from packages.coverage_validation import validate_response
from packages.evaluation_store import (
    Comment,
    EvaluationStore,
    ExecutionState,
    Incompatibility,
    InvocationAttempt,
    JobRecord,
    ModelRouting,
    ParserSettings,
    PromptIdentity,
    RunRecord,
    new_comment_id,
    new_job_id,
    new_run_id,
    utc_now,
)
from packages.llm_gateway import LlmGateway, ProviderError, compile_plain_text
from packages.llm_gateway import to_yaml as _yaml
from packages.llm_gateway.providers.base import (
    MEDIA_IMAGE,
    MEDIA_TEXT,
    ModelProvider,
    OriginalSourceBlock,
)
from packages.model_catalog import (
    CapabilitySnapshot,
    ModelRole,
    RetryBudget,
    RoleSelection,
    route_selection,
    selector_entries,
)
from packages.prompt_registry import PromptRegistry
from packages.source_inventory import FilingInventory, build_inventory
from packages.source_transport import (
    MemberDisposition,
    SourceSet,
    assemble_source_set,
    assess,
    image_coverage_report,
)

from .catalog import FilingCatalog, FilingRecord
from .errors import (
    FilingNotInCatalogError,
    NoParsingModelError,
    StageNotAuthorizedError,
    UnknownStrategyError,
)
from .multipart_service import MultipartParseService, MultipartSettings
from .sizing import compact_sizing
from .spend_journal import SpendJournal

#: OUTPUT SIZING POLICY, documented because section 24.2 requires one rather than a habit.
#:
#: The request asks for roughly this fraction of the estimated input, floored so that a model which
#: emits reasoning before its answer always has room for both, and capped by the model's verified
#: output limit and by what the context has left after the input.
#:
#: The floor is the important half. Phase 1 measured a candidate whose entire 8-token output budget
#: went to a reasoning block, leaving an empty answer with stop reason `max_tokens` — a well-formed
#: response with nothing in it. Sizing an output budget for the visible answer alone reproduces
#: that at any scale.
#:
#: Every number here is a STARTING POINT chosen before any filing had been parsed. The measured
#: output lengths from the first benchmark are what replace it.
OUTPUT_RATIO_OF_INPUT: Final[float] = 0.6
MINIMUM_PARSE_OUTPUT_TOKENS: Final[int] = 8000

#: The two parsing protocols a user may choose between, and the reason both remain runnable.
#:
#: `single_response` is the Phase 2 protocol. It is not deprecated and is not removed: thirty
#: preserved runs used it, and section 26 of the Phase 2.1 brief asks for a factual comparison
#: between the two, which is impossible if one of them can no longer be run.
#:
#: THE DEFAULT IS `single_response`, AND THAT IS BACKWARD COMPATIBILITY RATHER THAN A PREFERENCE.
#: A stored job with no `strategy` field is a Phase 2 job, and an API request that names no
#: strategy predates the choice existing. The UI form always sends one explicitly.
SINGLE_RESPONSE_STRATEGY: Final[str] = "single_response"
MULTIPART_STRATEGY: Final[str] = "multipart"
STRATEGIES: Final[tuple[str, ...]] = (SINGLE_RESPONSE_STRATEGY, MULTIPART_STRATEGY)

#: Evidence file names. Fixed, lowercase and hyphenated so they satisfy the evaluation store's
#: name guard and so a reviewer opening a job directory finds the same names every time.
PROMPT_EVIDENCE: Final[str] = "prompt.txt"
INSTRUCTION_EVIDENCE: Final[str] = "request-instruction.txt"
REQUEST_TRANSPORT_EVIDENCE: Final[str] = "request-transport.json"
RESPONSE_EVIDENCE: Final[str] = "response-visible.txt"
REASONING_EVIDENCE: Final[str] = "response-reasoning.txt"
RESPONSE_TRANSPORT_EVIDENCE: Final[str] = "response-transport.json"
SOURCE_SET_EVIDENCE: Final[str] = "source-set.yaml"
VALIDATION_EVIDENCE: Final[str] = "validation.yaml"


def sized_output_tokens(
    *, estimated_input_tokens: int, model_max_output: int, model_context: int
) -> int:
    """How many output tokens to request for one parse. See OUTPUT_RATIO_OF_INPUT."""
    wanted = max(
        MINIMUM_PARSE_OUTPUT_TOKENS,
        int(math.ceil(estimated_input_tokens * OUTPUT_RATIO_OF_INPUT)),
    )
    headroom = model_context - estimated_input_tokens
    return max(1, min(wanted, model_max_output, headroom))


@dataclass(frozen=True)
class RunRequest:
    """One user request. `parsing_label` is required; the other three roles may be blank."""

    cik: str
    parsing_label: str
    accessions: tuple[str, ...] = ()
    from_date: str | None = None
    to_date: str | None = None
    image_label: str | None = None
    summary_label: str | None = None
    analysis_label: str | None = None
    temperature: float = 0.0
    strategy: str = SINGLE_RESPONSE_STRATEGY

    def __post_init__(self) -> None:
        if self.strategy not in STRATEGIES:
            raise UnknownStrategyError(
                f"{self.strategy!r} is not a parsing strategy this repository implements. "
                f"Choose one of: {', '.join(STRATEGIES)}. There is no default beyond the "
                "backward-compatible one and no silent fallback."
            )

    def selection(self) -> RoleSelection:
        # `.strip()` matters: a UI that sends a space for an unfilled field would otherwise slip
        # past this typed refusal and surface as the bare ValueError from RoleSelection, losing
        # both the error type an API layer catches and the sentence a user reads.
        if not self.parsing_label.strip():
            raise NoParsingModelError(
                "a run requires a parsing model. The image, summary and analysis selectors may be "
                "left blank, and a blank one runs NO stage rather than borrowing this model."
            )
        return RoleSelection(
            parsing=self.parsing_label,
            image=self.image_label or None,
            summary=self.summary_label or None,
            analysis=self.analysis_label or None,
        )


@dataclass(frozen=True)
class InventoriedFiling:
    """One preserved filing, its assembled source set, and the mechanical inventory of its bytes.

    The three travel together because the completeness review surface needs all three at once: the
    catalog record names the filing, the source set holds the decoded member text a source slice is
    cut from, and the inventory is the DENOMINATOR every classification is recorded against.

    NOTHING HERE WAS SENT TO A MODEL. Building an inventory issues no provider request and costs
    nothing. It is a measurement of the preserved bytes, taken before any parse exists.
    """

    filing: FilingRecord
    source_set: SourceSet
    inventory: FilingInventory


@dataclass
class PreflightItem:
    """One filing's preflight: what would be sent, whether it fits, and what it could cost."""

    filing: FilingRecord
    source_set: SourceSet
    compatibility: dict[str, Any]
    requested_output_tokens: int
    worst_case_cost_usd: Decimal
    compatible: bool
    reason: str
    detail: str
    strategy: str = SINGLE_RESPONSE_STRATEGY
    first_call_worst_case_usd: Decimal | None = None

    def to_mapping(self) -> dict[str, Any]:
        mapping = {
            "filing": self.filing.to_mapping(),
            "source_set_id": self.source_set.source_set_id,
            "submitted_members": len(self.source_set.submitted_members),
            "submitted_bytes": self.source_set.submitted_bytes,
            "reused_members": self.source_set.reused_count,
            "fetched_members": self.source_set.fetched_count,
            "compatibility": self.compatibility,
            "requested_output_tokens": self.requested_output_tokens,
            "worst_case_cost_usd": str(self.worst_case_cost_usd),
            "compatible": self.compatible,
            "reason": self.reason,
            "detail": self.detail,
            "strategy": self.strategy,
        }
        if self.strategy == MULTIPART_STRATEGY:
            # A MULTIPART BOUND IS THE FILING'S OWN BUDGET, NOT A GUESS AT THE CALL COUNT. How many
            # parts a filing has is exactly what the model decides in the first call, so any number
            # this backend put here before that call would be an invented fact about the filing.
            # What CAN be stated honestly before spending is the hard limit the parse cannot pass,
            # and the cost of the one call that is certain to happen. The revised worst case
            # arrives after the plan, when the part count is a measured thing.
            mapping["first_call_worst_case_usd"] = str(self.first_call_worst_case_usd or 0)
            mapping["bound_basis"] = (
                "this filing's own budget ceiling. The number of part calls is decided by the "
                "planning response and is not projected here; a revised worst case is computed "
                "from the plan before any part is invoked."
            )
        return mapping


@dataclass
class RunPlan:
    """Everything a user should see BEFORE authorizing a billable run."""

    items: list[PreflightItem] = field(default_factory=list)
    routing: dict[str, Any] = field(default_factory=dict)
    prompt: dict[str, Any] = field(default_factory=dict)
    ceiling_usd: Decimal = Decimal(0)
    already_spent_usd: Decimal = Decimal(0)
    strategy: str = SINGLE_RESPONSE_STRATEGY

    @property
    def worst_case_total_usd(self) -> Decimal:
        return sum((i.worst_case_cost_usd for i in self.items if i.compatible), Decimal(0))

    @property
    def within_ceiling(self) -> bool:
        return self.already_spent_usd + self.worst_case_total_usd <= self.ceiling_usd

    def to_mapping(self) -> dict[str, Any]:
        return {
            "routing": self.routing,
            "prompt": self.prompt,
            "strategy": self.strategy,
            "strategy_note": (
                "a model-directed multipart parse: a compact plan the model writes, one call per "
                "part it names, subparts where it asks for them, and reconciliation. The complete "
                "filing goes to the model intact on every one of those calls."
                if self.strategy == MULTIPART_STRATEGY
                else "one filing, one response. The Phase 2 protocol, kept runnable for comparison."
            ),
            "filings": [i.to_mapping() for i in self.items],
            "compatible_filings": sum(1 for i in self.items if i.compatible),
            "incompatible_filings": sum(1 for i in self.items if not i.compatible),
            "worst_case_total_usd": str(self.worst_case_total_usd),
            "ceiling_usd": str(self.ceiling_usd),
            "already_spent_usd": str(self.already_spent_usd),
            "within_ceiling": self.within_ceiling,
            "cost_note": (
                "a WORST-CASE bound from a character-ratio token estimate and the reviewed price "
                "inputs, not a prediction. It is reserved before the call and settled against "
                "measured usage after it."
            ),
        }


class ParserReviewService:
    """The parser-only orchestration path, and everything the review API calls."""

    def __init__(
        self,
        *,
        store: EvaluationStore,
        catalog: FilingCatalog,
        snapshot: CapabilitySnapshot,
        prompts: PromptRegistry,
        inventory: Any,
        fetcher: Any,
        provider: ModelProvider,
        journal: SpendJournal,
        preferred_region: str,
        author: str,
        multipart_settings: MultipartSettings | None = None,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._snapshot = snapshot
        self._prompts = prompts
        self._inventory = inventory
        self._fetcher = fetcher
        self._provider = provider
        self._journal = journal
        self._region = preferred_region
        self._author = author
        self._multipart_settings = multipart_settings or MultipartSettings()
        #: (cik, accession) -> (source set identity, inventory). Keyed on the identity rather than
        #: on the accession alone: a member acquired between two page loads produces a different
        #: source set from the same accession, and serving the earlier inventory would give the
        #: review surface a denominator that no longer describes the bytes on disk.
        self._inventories: dict[tuple[str, str], tuple[str, FilingInventory]] = {}
        self._multipart = MultipartParseService(
            store=store,
            snapshot=snapshot,
            prompts=prompts,
            inventory=inventory,
            fetcher=fetcher,
            provider=provider,
            journal=journal,
            settings=self._multipart_settings,
            author=author,
        )

    # --- read paths ------------------------------------------------------------------------------

    @property
    def store(self) -> EvaluationStore:
        return self._store

    @property
    def catalog(self) -> FilingCatalog:
        return self._catalog

    @property
    def journal(self) -> SpendJournal:
        return self._journal

    @property
    def multipart(self) -> MultipartParseService:
        """The model-directed multipart workflow, sharing this service's store and journal."""
        return self._multipart

    @property
    def multipart_settings(self) -> MultipartSettings:
        return self._multipart_settings

    def prompt_for_strategy(self, strategy: str) -> Any:
        """The prompt a run of this strategy STARTS from.

        A multipart run starts from the planning family and goes on to use four more; a
        single-response run uses exactly one. The child job records the first, and every task
        records its own, so the assembly can name all of them.
        """
        if strategy == MULTIPART_STRATEGY:
            return self._prompts.active_for("parsing_multipart_plan")
        return self._prompts.active_for(ModelRole.PARSING.value)

    @property
    def preferred_region(self) -> str:
        return self._region

    @property
    def author(self) -> str:
        """The configured reviewer identity.

        A LABEL, never a personal email or name in tracked code. It is supplied from ignored
        environment state and defaults to a generic string, because a comment record that
        carried a real identity would put it into evaluation artifacts nobody reviewed for it.
        """
        return self._author

    def selectors(self) -> dict[str, Any]:
        """Every model selector, with every field the UX specification requires on each row.

        The three optional roles carry an explicit blank option. It is a VISIBLE choice with a
        label, not a hidden default: `None — skip this stage` is what the user selects when they
        mean it, and nothing is preselected for them.
        """
        return {
            "preferred_region": self._region,
            "roles": {
                role.value: {
                    "required": role is ModelRole.PARSING,
                    "blank_option": (
                        None
                        if role is ModelRole.PARSING
                        else {"label": "", "display": "None — skip this stage"}
                    ),
                    "executed_in_this_phase": role is ModelRole.PARSING,
                    "entries": [
                        entry.to_mapping()
                        for entry in selector_entries(
                            self._snapshot, role=role, preferred_region=self._region
                        )
                    ],
                }
                for role in ModelRole
            },
        }

    # --- the mechanical inventory of one preserved filing -----------------------------------------

    def inventoried_filing(self, cik: str, accession: str) -> InventoriedFiling | None:
        """Assemble one filing's source set and measure it. None when the catalog does not hold it.

        NO MODEL IS INVOLVED AND NOTHING IS SPENT. `packages/source_inventory` counts members,
        visible text spans, table elements and images from the preserved bytes; that is the
        denominator Phase 2.1 lacked, and it is available before any parse exists.

        THE WALK IS MEMOISED AND THE ASSEMBLY IS NOT. Measured on Apple's 10-Q, walking 915,890
        characters of markup takes roughly 0.4 seconds and a review surface re-renders it on every
        page load, per member, per pagination step. Re-assembling the source set each time is what
        makes the memo safe: the assembly is what notices that a member moved, and its identity is
        the cache key.
        """
        filing = self._catalog.filing(cik, accession)
        if filing is None:
            return None
        source_set = assemble_source_set(
            self._inventory,
            self._fetcher,
            cik=filing.cik,
            accession=filing.accession,
            form_as_filed=filing.form_as_filed,
            filing_date=filing.filing_date,
            issuer_label=filing.issuer_label,
            transport_era=filing.transport_era,
            report_period=filing.report_period,
        )
        key = (filing.cik, filing.accession)
        cached = self._inventories.get(key)
        if cached is not None and cached[0] == source_set.source_set_id:
            return InventoriedFiling(filing=filing, source_set=source_set, inventory=cached[1])
        inventory = build_inventory(source_set)
        self._inventories[key] = (source_set.source_set_id, inventory)
        return InventoriedFiling(filing=filing, source_set=source_set, inventory=inventory)

    # --- preflight -------------------------------------------------------------------------------

    def _resolve_filings(self, request: RunRequest) -> list[FilingRecord]:
        if request.accessions:
            found = []
            for accession in request.accessions:
                try:
                    record = self._catalog.filing(request.cik, accession)
                except ValueError as error:
                    # `sec_identity` refuses a malformed CIK or accession with its own typed
                    # error. The catalog protocol promises None for "not held", not an identity
                    # exception, so it is translated here rather than escaping untyped.
                    raise FilingNotInCatalogError(
                        f"({request.cik}, {accession}) is not a well-formed filing identity: "
                        f"{error}"
                    ) from error
                if record is None:
                    raise FilingNotInCatalogError(
                        f"no preserved filing ({request.cik}, {accession}) is in the catalog"
                    )
                found.append(record)
            return found
        return self._catalog.filings(
            request.cik, from_date=request.from_date, to_date=request.to_date
        )

    def preflight(self, request: RunRequest) -> RunPlan:
        """Assemble every source set, assess compatibility, and bound the cost. No spend."""
        selection = request.selection()
        routed = route_selection(self._snapshot, selection, preferred_region=self._region)
        parsing = routed[ModelRole.PARSING]
        prompt = self.prompt_for_strategy(request.strategy)
        capability = parsing.capability
        multipart = request.strategy == MULTIPART_STRATEGY

        plan = RunPlan(
            routing={role.value: decision.to_mapping() for role, decision in routed.items()},
            prompt=prompt.to_mapping(),
            ceiling_usd=self._journal.ceiling_usd,
            already_spent_usd=self._journal.spent_usd,
            strategy=request.strategy,
        )

        for filing in self._resolve_filings(request):
            source_set = assemble_source_set(
                self._inventory,
                self._fetcher,
                cik=filing.cik,
                accession=filing.accession,
                form_as_filed=filing.form_as_filed,
                filing_date=filing.filing_date,
                issuer_label=filing.issuer_label,
                transport_era=filing.transport_era,
                report_period=filing.report_period,
            )
            instruction = self._instruction_text(filing, source_set, capability.multimodal)
            probe = assess(
                source_set,
                prompt_text=prompt.text + instruction,
                model_context_tokens=capability.effective_context_tokens(
                    images_submitted=capability.multimodal
                ),
                requested_output_tokens=0,
                model_accepts_images=capability.multimodal,
            )
            if multipart:
                requested_output = compact_sizing(
                    capability,
                    estimated_input_tokens=probe.estimated_input_tokens,
                    kind="plan",
                ).requested_output_tokens
            else:
                requested_output = sized_output_tokens(
                    estimated_input_tokens=probe.estimated_input_tokens,
                    model_max_output=capability.max_output_tokens,
                    model_context=capability.effective_context_tokens(
                        images_submitted=capability.multimodal
                    ),
                )
            report = assess(
                source_set,
                prompt_text=prompt.text + instruction,
                model_context_tokens=capability.effective_context_tokens(
                    images_submitted=capability.multimodal
                ),
                requested_output_tokens=requested_output,
                model_accepts_images=capability.multimodal,
            )
            first_call = self._journal.bound(
                capability.price,
                max_input_tokens=report.estimated_input_tokens,
                max_output_tokens=requested_output,
            )
            plan.items.append(
                PreflightItem(
                    filing=filing,
                    source_set=source_set,
                    compatibility=report.to_mapping(),
                    requested_output_tokens=requested_output,
                    worst_case_cost_usd=(
                        self._multipart_settings.filing_budget_usd if multipart else first_call
                    ),
                    compatible=report.compatible,
                    reason=report.reason,
                    detail=report.detail,
                    strategy=request.strategy,
                    first_call_worst_case_usd=first_call,
                )
            )
        return plan

    # --- run creation ----------------------------------------------------------------------------

    def create_run(self, request: RunRequest, *, plan: RunPlan | None = None) -> RunRecord:
        """Create the parent run and one child job per filing. Nothing is invoked here."""
        selection = request.selection()
        routed = route_selection(self._snapshot, selection, preferred_region=self._region)
        unauthorized = [role.value for role in routed if role is not ModelRole.PARSING]
        if unauthorized:
            raise StageNotAuthorizedError(
                f"Phase 2 executes the parsing stage only; {', '.join(unauthorized)} was selected. "
                "The other selectors exist so the progressive workflow is real, and running one "
                "here would be a scope violation rather than a missing feature."
            )

        plan = plan or self.preflight(request)
        parsing = routed[ModelRole.PARSING]
        prompt = self.prompt_for_strategy(request.strategy)
        entity = self._catalog.entity(request.cik)

        run = RunRecord(
            run_id=new_run_id(),
            created_at=utc_now(),
            author=self._author,
            cik=request.cik,
            entity_label=entity.name if entity else request.cik,
            parsing_label=selection.parsing,
            image_label=selection.image,
            summary_label=selection.summary,
            analysis_label=selection.analysis,
            from_date=request.from_date,
            to_date=request.to_date,
            preferred_region=self._region,
            cost_ceiling_usd=self._journal.ceiling_usd,
        )
        self._store.save_run(run)
        self._store.append_event(
            run.run_id,
            kind="run.created",
            job_id=None,
            message=(
                f"{len(plan.items)} filing(s); parsing model {selection.parsing} in "
                f"{parsing.region}; stages: {', '.join(r.value for r in selection.selected_roles)}"
            ),
        )
        if parsing.cross_region_reason:
            self._store.append_event(
                run.run_id,
                kind="run.cross_region",
                job_id=None,
                message=parsing.cross_region_reason,
            )

        for item in plan.items:
            job = JobRecord(
                job_id=new_job_id(),
                parent_run_id=run.run_id,
                created_at=utc_now(),
                updated_at=utc_now(),
                cik=item.filing.cik,
                accession=item.filing.accession,
                form_as_filed=item.filing.form_as_filed,
                filing_date=item.filing.filing_date,
                issuer_label=item.filing.issuer_label,
                transport_era=item.filing.transport_era,
                report_period=item.filing.report_period,
                routing=ModelRouting.from_mapping(parsing.to_mapping()),
                prompt=PromptIdentity(
                    prompt_id=prompt.prompt_id, version=prompt.version, sha256=prompt.sha256
                ),
                settings=ParserSettings(
                    max_output_tokens=item.requested_output_tokens,
                    temperature=request.temperature,
                ),
                strategy=request.strategy,
                budget_ceiling_usd=(
                    self._multipart_settings.filing_budget_usd
                    if request.strategy == MULTIPART_STRATEGY
                    else None
                ),
                source_set_id=item.source_set.source_set_id,
                source_set=item.source_set.to_mapping(),
                image_coverage=image_coverage_report(
                    item.source_set, model_accepts_images=parsing.capability.multimodal
                ),
                estimated_input_tokens=item.compatibility["estimated_input_tokens"],
            )
            self._store.save_job(job)
            run.job_ids.append(job.job_id)
            self._store.put_evidence_text(run.run_id, job.job_id, PROMPT_EVIDENCE, prompt.text)
            self._store.append_event(
                run.run_id,
                kind="filing.resolved",
                job_id=job.job_id,
                message=f"{item.filing.form_as_filed} {item.filing.accession}",
            )
            self._store.append_event(
                run.run_id,
                kind="source.ready",
                job_id=job.job_id,
                message=(
                    f"{len(item.source_set.submitted_members)} member(s), "
                    f"{item.source_set.reused_count} reused, "
                    f"{item.source_set.fetched_count} fetched from SEC"
                ),
            )
            self._store.set_execution_state(job, ExecutionState.SOURCE_READY)
            self._store.set_execution_state(
                job, ExecutionState.PREFLIGHT, message=item.compatibility["detail"]
            )
            if not item.compatible:
                job.incompatibility = Incompatibility(
                    reason=item.reason,
                    detail=item.detail,
                    source_set_bytes=item.source_set.submitted_bytes,
                    estimated_input_tokens=item.compatibility["estimated_input_tokens"],
                    model_context_tokens=item.compatibility["model_context_tokens"],
                )
                self._store.set_execution_state(
                    job, ExecutionState.INCOMPATIBLE, message=item.detail
                )
                continue
            self._store.set_execution_state(job, ExecutionState.QUEUED)

        self._store.save_run(run)
        return run

    # --- execution -------------------------------------------------------------------------------

    def _instruction_text(
        self, filing: FilingRecord, source_set: SourceSet, multimodal: bool
    ) -> str:
        """The SYNTHETIC part of the request: plain prose naming the filing and its artifacts.

        Mechanical labelling only, which rules.md section 11 permits explicitly. It states which
        accession this is, which artifacts follow and in what order, and — when the parser is
        text-only — that image-bearing members exist and were not sent. It says nothing about what
        any of them contains.
        """
        labels = ", ".join(
            m.filename or "complete submission" for m in source_set.submitted_members
        )
        lines = [
            f"This is SEC accession {filing.accession}, filed by CIK {filing.cik} on "
            f"{filing.filing_date} as form {filing.form_as_filed}.",
            f"{len(source_set.submitted_members)} source artifact(s) follow in filed order: {labels}.",
        ]
        images = source_set.image_members
        if images and not multimodal:
            names = ", ".join(m.filename for m in images)
            lines.append(
                f"{len(images)} image-bearing member(s) were filed and are NOT included in this "
                f"request because the selected model has no verified image path: {names}. "
                "Record anything that depends on them as unresolved."
            )
        return "\n\n".join(lines)

    def _blocks(
        self, source_set: SourceSet, *, multimodal: bool
    ) -> tuple[OriginalSourceBlock, ...]:
        """One provider block per submitted member, in filed order, admitted by provenance."""
        blocks = []
        for member in source_set.submitted_members:
            if member.disposition is MemberDisposition.PARSER_INPUT_IMAGE:
                if not multimodal or member.image_bytes is None:
                    continue
                blocks.append(
                    OriginalSourceBlock(
                        label=member.filename,
                        sha256=member.sha256,
                        byte_count=member.byte_count,
                        media_kind=MEDIA_IMAGE,
                        raw_bytes=member.image_bytes,
                        image_format=member.image_format,
                    )
                )
                continue
            if member.text is None:
                continue
            blocks.append(
                OriginalSourceBlock(
                    label=member.filename or f"{source_set.accession}.txt",
                    sha256=member.sha256,
                    byte_count=member.byte_count,
                    media_kind=MEDIA_TEXT,
                    raw_bytes=member.text.encode(member.encoding or "utf-8"),
                    text=member.text,
                    codec=member.encoding or "utf-8",
                )
            )
        return tuple(blocks)

    def execute_job(self, run_id: str, job_id: str) -> JobRecord:
        """Invoke the parser for one child job, preserve everything, validate, and stop.

        DISPATCHES ON THE RECORDED STRATEGY, NOT ON A FLAG PASSED IN. The strategy is durable on
        the job, so a worker that picks the job up minutes later, or after a restart, runs the
        protocol the run was created with rather than whatever is configured now.
        """
        job = self._store.load_job(run_id, job_id)
        if job.execution_state is not ExecutionState.QUEUED:
            return job
        if job.strategy == MULTIPART_STRATEGY:
            self._multipart.start(run_id, job_id)
            return self._multipart.drive(run_id, job_id)

        filing = self._catalog.filing(job.cik, job.accession)
        assert filing is not None  # a job is never created for a filing the catalog lacks
        capability = self._snapshot.get(job.routing.label)
        prompt = self._prompts.get(job.prompt.prompt_id, job.prompt.version)

        source_set = assemble_source_set(
            self._inventory,
            self._fetcher,
            cik=job.cik,
            accession=job.accession,
            form_as_filed=job.form_as_filed,
            filing_date=job.filing_date,
            issuer_label=job.issuer_label,
            transport_era=job.transport_era,
            report_period=job.report_period,
        )
        # THE SET THAT WAS COSTED MUST BE THE SET THAT IS SENT. Preflight assembles a source set,
        # measures it, bounds its cost and records its identity; execution assembles it again,
        # because a job is executed by a worker that may start minutes later. If a member was
        # re-acquired, a hash moved, or EDGAR published a corrected member in between, the two
        # sets differ — and the run would then spend against a bound computed for different bytes
        # and record a source_set_id that does not describe what was submitted. That is refused
        # rather than reconciled: the user reruns, and the rerun costs what the rerun costs.
        if job.source_set_id and source_set.source_set_id != job.source_set_id:
            job.failure = (
                f"the source set changed between preflight and execution: {job.source_set_id} "
                f"became {source_set.source_set_id}. The cost bound and the recorded identity "
                "describe different bytes, so this job is refused rather than reconciled."
            )
            self._store.set_execution_state(
                job, ExecutionState.FAILED, message="source set changed after preflight"
            )
            return job

        blocks = self._blocks(source_set, multimodal=capability.multimodal)
        instruction = self._instruction_text(filing, source_set, capability.multimodal)
        payload = compile_plain_text(instruction, origin="parser.request")

        self._store.put_evidence_text(run_id, job_id, INSTRUCTION_EVIDENCE, payload.content)

        # THE EXACT BYTES THAT WERE SENT ARE PRESERVED WITH THE RUN, not merely referenced.
        # The review UI has to show the reviewer what the model actually received, and resolving
        # that from a corpus path months later depends on a file nobody promised not to move. It
        # also makes the raw view work with no network and no re-assembly.
        manifest = source_set.to_mapping()
        evidence_names: dict[str, str] = {}
        for index, block in enumerate(blocks, start=1):
            suffix = "bin" if block.is_image else "txt"
            name = f"source-{index:02d}.{suffix}"
            self._store.put_evidence(run_id, job_id, name, block.raw_bytes)
            evidence_names[block.label] = name
        for member in manifest["members"]:
            member["evidence_name"] = evidence_names.get(
                member["filename"] or f"{source_set.accession}.txt"
            )
        self._store.put_evidence_text(
            run_id,
            job_id,
            SOURCE_SET_EVIDENCE,
            _yaml(manifest),
            content_type="application/yaml",
        )
        job.source_set = manifest
        self._store.save_job(job)

        gateway = LlmGateway(self._provider)
        budget = RetryBudget(max_retries=1)
        attempt_number = 0
        result = None
        reserved = Decimal(0)
        last_error: ProviderError | None = None

        self._store.set_execution_state(job, ExecutionState.RUNNING)
        while result is None:
            attempt_number += 1
            # EVERY ATTEMPT IS RESERVED SEPARATELY, BECAUSE EVERY ATTEMPT IS BILLABLE. A retry is a
            # second provider call and a second charge; reserving once and retrying would spend
            # twice against a ceiling that had been checked once. The RESERVATION FOR A FAILED
            # ATTEMPT IS NOT RELEASED — that request was issued and cost money, and only the
            # attempt that actually returns usage is settled against a measurement.
            reserved = self._journal.authorize(
                capability.price,
                max_input_tokens=job.estimated_input_tokens or 0,
                max_output_tokens=job.settings.max_output_tokens,
                at=utc_now(),
                run_id=run_id,
                job_id=job_id,
                model_label=job.routing.label,
            )
            job.reserved_cost_usd = reserved
            self._store.save_job(job)
            self._store.append_event(
                run_id,
                kind="preflight.authorized",
                job_id=job_id,
                message=(
                    f"attempt {attempt_number}: worst case USD {reserved} reserved against the "
                    "cumulative ceiling"
                ),
            )
            started = utc_now()
            try:
                result = gateway.invoke(
                    model_id=job.routing.invocation_id,
                    system_text=prompt.text,
                    payload=payload,
                    prompt_version=f"{prompt.prompt_id}@{prompt.version}",
                    expect_structured=True,
                    max_output_tokens=job.settings.max_output_tokens,
                    original_source=blocks,
                    temperature=job.settings.temperature,
                    region=job.routing.region,
                    cost=capability.price.cost,
                    strict_response=False,
                )
            except ProviderError as error:
                last_error = error
                job.attempts.append(
                    InvocationAttempt(
                        attempt=attempt_number,
                        started_at=started,
                        finished_at=utc_now(),
                        latency_ms=0,
                        stop_reason="provider_error",
                        input_tokens=0,
                        output_tokens=0,
                        visible_characters=0,
                        reasoning_characters=0,
                        error=str(error),
                        retryable=error.retryable,
                    )
                )
                self._store.save_job(job)
                try:
                    budget.consume(retryable=error.retryable)
                except Exception:
                    job.failure = str(error)
                    self._store.set_execution_state(
                        job, ExecutionState.FAILED, message=str(error)[:400]
                    )
                    return job
                self._store.append_event(
                    run_id,
                    kind="invocation.retry",
                    job_id=job_id,
                    message="one retry, for a transient provider condition",
                )

        record = result.record
        actual = self._journal.settle(
            capability.price,
            reserved=reserved,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            at=utc_now(),
            run_id=run_id,
            job_id=job_id,
            model_label=job.routing.label,
        )
        job.actual_cost_usd = actual
        job.attempts.append(
            InvocationAttempt(
                attempt=attempt_number,
                started_at=record.started_at.isoformat(),
                finished_at=record.finished_at.isoformat(),
                latency_ms=int(record.latency_seconds * 1000),
                stop_reason=record.stop_reason,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                visible_characters=len(record.response_body),
                reasoning_characters=len(record.reasoning_body),
                provider_request_id=record.provider_request_id,
                error=record.error,
                retryable=None,
            )
        )

        # EXACT BYTES BECOME DURABLE BEFORE ANY CLAIM IS MADE ABOUT THEM. Validation, parsing and
        # the state change all happen after this point, so a crash between them leaves evidence
        # that was bought rather than a job that spent money and recorded nothing.
        self._store.put_evidence_text(run_id, job_id, RESPONSE_EVIDENCE, record.response_body)
        if record.reasoning_body:
            self._store.put_evidence_text(run_id, job_id, REASONING_EVIDENCE, record.reasoning_body)
        if record.transport_request:
            self._store.put_evidence_text(
                run_id,
                job_id,
                REQUEST_TRANSPORT_EVIDENCE,
                record.transport_request,
                content_type="application/json",
            )
        if record.transport_response:
            self._store.put_evidence_text(
                run_id,
                job_id,
                RESPONSE_TRANSPORT_EVIDENCE,
                record.transport_response,
                content_type="application/json",
            )
        self._store.save_job(job)
        self._store.set_execution_state(
            job,
            ExecutionState.RESPONSE_RECEIVED,
            message=(
                f"{record.input_tokens} input and {record.output_tokens} output tokens, "
                f"stop reason {record.stop_reason or 'unreported'}, USD {actual}"
            ),
        )

        self._store.set_execution_state(job, ExecutionState.VALIDATING)
        artifact_texts = {b.label: (b.text or "") for b in blocks if not b.is_image}
        validation, _ = validate_response(
            record.response_body,
            artifact_texts=artifact_texts,
            image_filenames=tuple(m.filename for m in source_set.image_members),
            images_analysed=capability.multimodal and bool(source_set.image_members),
        )
        job.validation = validation.to_mapping()
        self._store.put_evidence_text(
            run_id,
            job_id,
            VALIDATION_EVIDENCE,
            _yaml(job.validation),
            content_type="application/yaml",
        )
        self._store.save_job(job)
        self._store.set_execution_state(
            job,
            ExecutionState.READY_FOR_REVIEW,
            message=(
                f"{validation.status.value}: {validation.node_count} node(s), "
                f"{validation.references_resolved}/{validation.reference_count} references resolved"
            ),
        )
        if last_error is not None:
            self._store.append_event(
                run_id,
                kind="invocation.recovered",
                job_id=job_id,
                message="the first attempt failed transiently and the retry succeeded",
            )
        return job

    # --- review ----------------------------------------------------------------------------------

    def add_comment(
        self,
        run_id: str,
        *,
        target_type: str,
        target_id: str,
        text: str,
        job_id: str | None = None,
        target_version: str = "",
        tags: tuple[str, ...] = (),
    ) -> Comment:
        """Record one evaluation comment against the artifact VERSION it targets."""
        comment = Comment(
            comment_id=new_comment_id(),
            parent_run_id=run_id,
            child_job_id=job_id,
            target_type=target_type,
            target_id=target_id,
            target_version=target_version or "1",
            author=self._author,
            created_at=utc_now(),
            text=text,
            tags=tags,
        )
        return self._store.add_comment(comment)
