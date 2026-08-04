"""Every recorded parse of ONE filing, each measured against the SAME denominator.

WHAT THIS PRODUCES AND WHAT IT REFUSES TO PRODUCE. It produces one `MeasuredRun` per run recorded
against one accession: the model that was selected, where it ran, how the filing reached it, what
state the work ended in, and the completeness ledger, gate verdict and table validations computed
from its preserved artifacts. It produces them in the order the runs were RECORDED.

    IT PRODUCES NO ORDER, NO RANK AND NO SCORE. There is no sort key derived from a coverage
    figure, no aggregate, no threshold and no comparison operator between two runs anywhere in this
    module. `rules.md` section 21 rule 14 and the phase brief both forbid choosing a parser, and a
    table ordered by a computed figure IS a choice — the reader takes the top row as the answer.
    The denominator is shared so the numbers can be read side by side; that is the whole service.

NOTHING HERE IS A QUALITY MEASUREMENT. `MECHANICAL_COMPLETENESS_CANDIDATE` means a result carries
enough evidence to undergo human completeness review. A parse can pass all fourteen conditions and
be wrong about every number in the filing, because not one condition inspects meaning.

A RUN THAT NEVER REACHED A PROVIDER IS REPORTED, NOT HIDDEN AND NOT SCORED. Many preserved runs
failed at preflight or at the provider with zero parts. Rendering `0 of 1,750 covered` for one of
them would read as a measurement of a model that never answered, which is the false-empty defect in
its most misleading form. `parse_exists` is False for those, the situation sentence says what
happened, and the coverage figures are withheld rather than invented.

THE TWO PROTOCOLS ARE MEASURED THE SAME WAY. A Phase 2 single-response job has no tasks; its one
preserved response is presented to the ledger as one part, because it IS one part — the whole
filing. Measuring it as "no parts, therefore nothing covered" would report thirty preserved runs as
having produced nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from packages.completeness import (
    BenchmarkTruth,
    CompletenessLedger,
    ConvergenceState,
    GateResult,
    LedgerInputError,
    SerializationState,
    TableValidation,
    TransportState,
)
from packages.coverage_validation import ArtifactIndex, ResponseUnreadableError
from packages.coverage_validation import read as read_parsed
from packages.evaluation_store import (
    EvaluationStore,
    ExecutionState,
    JobRecord,
    TaskState,
    TaskType,
)
from packages.multipart import PART_ENVELOPE_KEYS, StructuredTable, read_tables
from packages.source_inventory import FilingInventory

from .completeness_service import effective_parse, measure
from .multipart_service import REQUEST_BRIEF_EVIDENCE
from .multipart_service import RESPONSE_EVIDENCE as TASK_RESPONSE_EVIDENCE

#: The task types whose artifacts carry filing content. A plan, a replanning call and a
#: reconciliation are protocol traffic: they schedule and check work rather than representing a
#: source range, and counting their envelopes as coverage would credit a parse for its bookkeeping.
PART_TYPES: frozenset[TaskType] = frozenset({TaskType.PARSE_PART, TaskType.PARSE_SUBPART})

#: The task types whose preserved response may hold a part's content — the parts themselves and the
#: repairs that supersede them. Only these are read from disk; a comparison page that parsed every
#: plan and reconciliation of every run would read hundreds of documents it never looks at.
_READABLE_TYPES: frozenset[TaskType] = PART_TYPES | {TaskType.FORMAT_REPAIR}

#: Task states from which the scheduler will never act again AND which represent work that ended
#: rather than work that stopped. FAILED and INTERRUPTED are deliberately absent: both are terminal
#: to the scheduler and both mean the parse did not converge, which is exactly what the gate's
#: convergence dimension exists to say.
_SETTLED_TASK_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.CANCELLED,
        TaskState.TRUNCATED,
        TaskState.READY_FOR_REVIEW,
    }
)

#: Execution states in which no provider call was ever issued for this filing.
_NEVER_INVOKED: frozenset[ExecutionState] = frozenset(
    {
        ExecutionState.CREATED,
        ExecutionState.SOURCE_READY,
        ExecutionState.PREFLIGHT,
        ExecutionState.QUEUED,
        ExecutionState.CANCELLED,
    }
)

#: How a PROJECTED run is recognised in its own preserved evidence. In projected mode the request
#: brief carries the lossless YAML projection under a top-level `source` key and the filing's text
#: members do not travel as their own blocks; in intact mode there is no such key.
#:
#: DERIVED FROM THE PRESERVED BYTES RATHER THAN FROM THE CURRENT CONFIGURATION, which is the whole
#: point: `MultipartSettings.source_input_mode` says how a run started TODAY would send its filing,
#: and a page that printed it beside a run recorded last week would be asserting something about
#: that run that nobody measured.
_PROJECTION_BRIEF_KEY = "\nsource:"

SOURCE_INPUT_INTACT = "intact"
SOURCE_INPUT_PROJECTED = "projected"
SOURCE_INPUT_UNRECORDED = "not recorded"


class _LazyIndex:
    """The prepared anchor ladder for one filing, built at most once and only when it is needed.

    BUILT LAZILY BECAUSE THE MEMO IS WORTHLESS OTHERWISE. Preparing the ladder over one filing's
    preserved members takes tens of seconds — it strips markup, decodes character references and
    keeps an index back into the original for every character. Building it eagerly on every page
    load meant a comparison page whose every run was already measured still paid the whole cost,
    which is the entire expense the memo exists to remove.
    """

    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts
        self._index: ArtifactIndex | None = None

    def get(self) -> ArtifactIndex:
        if self._index is None:
            self._index = ArtifactIndex(self._texts)
        return self._index


@dataclass(frozen=True)
class _SingleResponseArtifact:
    """The Phase 2 protocol's ONE response, presented to the ledger as one part.

    A SHIM RATHER THAN A STORED RECORD, because a single-response job never had a task and never
    will: the protocol that produced it does not queue work. What it did have is one preserved
    response covering the whole filing, and the ledger's part walk is exactly the right reader for
    it. The shim carries only the six attributes `resolve_effective` and `measure` read.
    """

    task_id: str
    part_id: str
    task_type: TaskType = TaskType.PARSE_PART
    state: TaskState = TaskState.SUCCEEDED
    parent_task_id: str | None = None
    order: int = 0
    envelope: dict[str, Any] | None = None


@dataclass(frozen=True)
class MeasuredRun:
    """One recorded parse of one filing, and everything a reviewer needs to judge it.

    EVERY FIELD IS A FACT ABOUT THIS RUN. There is no field holding a comparison with another run,
    because there is no such fact — two ledgers computed against one denominator are two
    measurements, and turning them into a verdict is a person's work.
    """

    run_id: str
    job_id: str
    created_at: str
    model_label: str
    region: str
    inference_profile_id: str | None
    strategy: str
    source_input_mode: str
    execution_state: str
    transport: TransportState
    serialization: SerializationState
    convergence: ConvergenceState
    cost_usd: str
    task_count: int
    part_documents: int
    situation: str
    ledger: CompletenessLedger | None = None
    gate: GateResult | None = None
    validations: tuple[TableValidation, ...] = ()
    tables: tuple[StructuredTable, ...] = ()
    unresolved_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    refusal: str = ""

    @property
    def parse_exists(self) -> bool:
        """Whether any readable part artifact was preserved for this run at all."""
        return self.part_documents > 0

    @property
    def measured(self) -> bool:
        """Whether a ledger could be computed. False only when the denominator disagrees."""
        return self.ledger is not None

    @property
    def cells_missing_from_source(self) -> int:
        """Model cell texts that occur nowhere in the source element they name."""
        return sum(v.cells_text_missing for v in self.validations)

    @property
    def validations_passing(self) -> int:
        return sum(1 for v in self.validations if v.passes)


class ModelComparisonService:
    """Measures every recorded parse of one filing, and remembers what it measured.

    THE MEMO IS KEYED ON THE RUN AND VALIDATED BY THE DENOMINATOR. Walking one filing's ledger
    means resolving every anchor of every claim against 900,000 characters of preserved markup, and
    a comparison page re-renders that for every recorded run on every load. The cached entry
    carries the source-set hash and the benchmark-truth version it was computed against, and a
    change in either discards it — a ledger served after a reviewer classified another span would
    report a denominator that no longer exists.
    """

    def __init__(self, *, store: EvaluationStore, job_response_evidence: str) -> None:
        self._store = store
        # SUPPLIED RATHER THAN IMPORTED, so this module does not import the service that owns the
        # single-response workflow — that service constructs this one, and an import back would be
        # a cycle. The task-level evidence names come from `multipart_service`, which depends on
        # neither.
        self._job_response = job_response_evidence
        self._measured: dict[tuple[str, str], tuple[tuple[str, int], MeasuredRun]] = {}

    # --- collection ------------------------------------------------------------------------

    def jobs_for(self, cik: str, accession: str) -> list[tuple[str, JobRecord]]:
        """Every recorded (run, child job) pair for one filing, in the order they were created.

        RECORDED ORDER AND NOTHING ELSE. It is the one ordering that carries no opinion: it is
        what happened, in the sequence it happened. Any ordering derived from a coverage figure
        would put a model at the top of the page, and the top of a page is a recommendation
        whatever the caption says.
        """
        found: list[tuple[str, JobRecord]] = []
        for run_id in self._store.list_run_ids():
            for job in self._store.load_jobs(run_id):
                if job.cik == cik and job.accession == accession:
                    found.append((run_id, job))
        return sorted(found, key=lambda pair: (pair[1].created_at, pair[0]))

    def measured_runs(
        self,
        *,
        inventory: FilingInventory,
        truth: BenchmarkTruth,
        artifact_texts: dict[str, str],
        images_submitted: frozenset[str],
    ) -> list[MeasuredRun]:
        """Measure every recorded parse of one filing against one shared denominator."""
        # ONE ANCHOR LADDER FOR THE WHOLE PAGE. Every run of one filing was sent the same preserved
        # bytes, so the prepared search structure over them is the same structure; building it per
        # run turned a page load into a minute of repeated string transforms.
        index = _LazyIndex(artifact_texts)
        return [
            self.measured_run(
                run_id,
                job,
                inventory=inventory,
                truth=truth,
                artifact_texts=artifact_texts,
                images_submitted=images_submitted,
                index=index,
            )
            for run_id, job in self.jobs_for(inventory.cik, inventory.accession)
        ]

    def measured_run(
        self,
        run_id: str,
        job: JobRecord,
        *,
        inventory: FilingInventory,
        truth: BenchmarkTruth,
        artifact_texts: dict[str, str],
        images_submitted: frozenset[str],
        index: _LazyIndex | None = None,
    ) -> MeasuredRun:
        """Measure ONE recorded parse, reusing the previous measurement when nothing moved."""
        key = (run_id, job.job_id)
        token = (inventory.source_set_sha256, truth.version)
        cached = self._measured.get(key)
        if cached is not None and cached[0] == token:
            return cached[1]
        measured = self._measure(
            run_id,
            job,
            inventory=inventory,
            truth=truth,
            artifact_texts=artifact_texts,
            images_submitted=images_submitted,
            index=_LazyIndex(artifact_texts) if index is None else index,
        )
        self._measured[key] = (token, measured)
        return measured

    # --- one run ---------------------------------------------------------------------------

    def _measure(
        self,
        run_id: str,
        job: JobRecord,
        *,
        inventory: FilingInventory,
        truth: BenchmarkTruth,
        artifact_texts: dict[str, str],
        images_submitted: frozenset[str],
        index: _LazyIndex,
    ) -> MeasuredRun:
        tasks = self._store.load_tasks(run_id, job.job_id)
        artifacts, documents = self._artifacts(run_id, job, tasks)
        parse = effective_parse(
            tasks=artifacts,
            documents=documents,
            part_types=PART_TYPES,
            repair_type=TaskType.FORMAT_REPAIR,
            succeeded_state=TaskState.SUCCEEDED,
        )
        # THE SAME WALK IN THE SAME ORDER AS THE LEDGER'S. `measure` reads its tables from
        # `effective_parse` too, so the tables here and the validations it returns describe the
        # same tables in the same positions. Deriving either from a second, separate pass is how
        # a review page ends up marking the wrong cell.
        tables = tuple(
            table
            for entry in parse.documents
            for table in read_tables(entry.document.get("tables"))
        )
        unresolved = tuple(
            item
            for entry in parse.documents
            for item in (entry.document.get("unresolved") or [])
            if isinstance(item, dict)
        )
        nonterminal = sum(1 for task in tasks if task.state not in _SETTLED_TASK_STATES)
        transport = _transport_state(job, tasks)
        serialization = _serialization_state(parse)
        convergence = _convergence_state(transport, nonterminal)

        common: dict[str, Any] = {
            "run_id": run_id,
            "job_id": job.job_id,
            "created_at": job.created_at,
            "model_label": job.routing.label,
            "region": job.routing.region,
            "inference_profile_id": job.routing.inference_profile_id,
            "strategy": job.strategy,
            "source_input_mode": self._source_input_mode(run_id, job, tasks),
            "execution_state": job.execution_state.value,
            "transport": transport,
            "serialization": serialization,
            "convergence": convergence,
            "cost_usd": str(_measured_cost(job, tasks)),
            "task_count": len(tasks),
            "part_documents": len(parse.documents),
            "situation": _situation(job, tasks, parse.documents),
        }

        try:
            ledger, gate, validations = measure(
                tasks=artifacts,
                documents=documents,
                inventory=inventory,
                truth=truth,
                artifact_texts=artifact_texts,
                part_types=PART_TYPES,
                repair_type=TaskType.FORMAT_REPAIR,
                succeeded_state=TaskState.SUCCEEDED,
                model_accepts_images=job.routing.multimodal,
                images_submitted=images_submitted,
                transport=transport,
                serialization=serialization,
                convergence=convergence,
                nonterminal_required_jobs=nonterminal,
                index=index.get(),
            )
        except LedgerInputError as error:
            # THE ROW STAYS AND SAYS WHY. A stored benchmark truth describing other bytes makes
            # every coverage figure meaningless, and dropping the run would hide a recorded parse
            # behind a configuration problem that has nothing to do with it.
            return MeasuredRun(**common, refusal=str(error))

        return MeasuredRun(
            **common,
            ledger=ledger,
            gate=gate,
            validations=tuple(validations),
            tables=tables,
            unresolved_items=unresolved,
        )

    def _artifacts(
        self, run_id: str, job: JobRecord, tasks: list[Any]
    ) -> tuple[list[Any], dict[str, dict[str, Any]]]:
        """The part-bearing records of one job and the documents they hold.

        A multipart job's parts are its tasks. A single-response job's part is its one preserved
        response, wrapped in the shim above so that both protocols reach the ledger through one
        reader rather than two that can disagree.
        """
        if tasks:
            documents: dict[str, dict[str, Any]] = {}
            for task in tasks:
                if task.task_type not in _READABLE_TYPES:
                    continue
                document = self._task_document(run_id, job.job_id, task.task_id)
                if document is not None:
                    documents[task.task_id] = document
            return list(tasks), documents

        if not self._store.has_evidence(run_id, job.job_id, self._job_response):
            return [], {}
        document = _readable(
            self._store.get_evidence_text(run_id, job.job_id, self._job_response),
            envelope_keys=None,
        )
        artifact = _SingleResponseArtifact(task_id=job.job_id, part_id=job.accession)
        return [artifact], ({} if document is None else {job.job_id: document})

    def _task_document(self, run_id: str, job_id: str, task_id: str) -> dict[str, Any] | None:
        if not self._store.has_task_evidence(run_id, job_id, task_id, TASK_RESPONSE_EVIDENCE):
            return None
        return _readable(
            self._store.get_task_evidence_text(run_id, job_id, task_id, TASK_RESPONSE_EVIDENCE),
            envelope_keys=PART_ENVELOPE_KEYS,
        )

    def _source_input_mode(self, run_id: str, job: JobRecord, tasks: list[Any]) -> str:
        """How the filing reached the model on this run, read from the run's own request brief.

        The single-response protocol has no projection path at all — it sends the preserved
        artifacts as their own blocks — so a job with no tasks is intact by construction. A
        multipart job is decided by whether its first preserved brief carries the projection.
        """
        if not tasks:
            return SOURCE_INPUT_INTACT
        for task in tasks:
            if not self._store.has_task_evidence(
                run_id, job.job_id, task.task_id, REQUEST_BRIEF_EVIDENCE
            ):
                continue
            brief = self._store.get_task_evidence_text(
                run_id, job.job_id, task.task_id, REQUEST_BRIEF_EVIDENCE
            )
            return (
                SOURCE_INPUT_PROJECTED
                if _PROJECTION_BRIEF_KEY in f"\n{brief}"
                else SOURCE_INPUT_INTACT
            )
        return SOURCE_INPUT_UNRECORDED


def _readable(text: str, *, envelope_keys: tuple[str, ...] | None) -> dict[str, Any] | None:
    """Parse one preserved response, or None when it is not one YAML document.

    UNREADABLE IS A RESULT, NOT AN ERROR. The response was bought, it is preserved exactly, and the
    ledger counts the part it failed to supply. Raising here would take a whole comparison page
    down because one model returned malformed output, which is the one thing the page exists to
    show.
    """
    try:
        if envelope_keys is None:
            return read_parsed(text).raw
        return read_parsed(text, envelope_keys=envelope_keys).raw
    except ResponseUnreadableError:
        return None


def _measured_cost(job: JobRecord, tasks: list[Any]) -> Decimal:
    """What this run actually spent on this filing.

    SUMMED FROM THE TASKS WHEN THERE ARE TASKS. The job's own total is written at assembly, so a
    multipart parse interrupted before it assembled carries a real charge that the job record has
    not totalled yet — and reporting USD 0 for a run that spent money is the wrong direction to be
    wrong in.
    """
    if tasks:
        return sum((task.actual_cost_usd or Decimal(0) for task in tasks), Decimal(0))
    return job.actual_cost_usd or Decimal(0)


def _transport_state(job: JobRecord, tasks: list[Any]) -> TransportState:
    """Whether this run reached the provider at all, read from what it recorded.

    CREDENTIAL_BLOCKED is not derived here. Distinguishing it from any other provider failure means
    reading a failure message and deciding what it meant, and a guess about why a call failed is
    exactly the kind of interpretation the backend does not make.
    """
    if job.incompatibility is not None or job.execution_state is ExecutionState.INCOMPATIBLE:
        return TransportState.INCOMPATIBLE
    if job.attempts or any(task.attempts for task in tasks):
        return TransportState.INVOKED
    if job.execution_state in _NEVER_INVOKED:
        return TransportState.NOT_RUN
    return TransportState.PROVIDER_FAILED


def _serialization_state(parse: Any) -> SerializationState:
    """Whether what came back can be read, and whether it took a repair to get there.

    The three are reported separately and never collapsed: a parse that needed a format repair is
    usable AND its model did not serialise correctly, and reporting only one of those either hides
    working evidence or credits a model with a document it did not produce.
    """
    if not parse.part_tasks:
        return SerializationState.NOT_RUN
    if not parse.documents:
        return SerializationState.UNPARSEABLE
    return (
        SerializationState.REPAIR_PARSEABLE if parse.repaired else SerializationState.RAW_PARSEABLE
    )


def _convergence_state(transport: TransportState, nonterminal: int) -> ConvergenceState:
    """Why the scheduler stopped creating work, as far as the preserved records can say.

    Only three of the six values are derivable from a stored run: it never started, it stopped with
    work outstanding, or every scheduled task settled. The three specific stopping reasons —
    a part limit, a cycle limit, a budget — are decisions the scheduler made in memory and did not
    record as a state, and naming one of them here would be a guess dressed as a measurement.
    """
    if transport is TransportState.NOT_RUN:
        return ConvergenceState.NOT_RUN
    return ConvergenceState.INTERRUPTED if nonterminal else ConvergenceState.CONVERGED


def _situation(job: JobRecord, tasks: list[Any], documents: tuple[Any, ...]) -> str:
    """One sentence saying what happened to this run, for a row that carries no coverage figures.

    A run that failed at preflight or at the provider is a row on the comparison page like any
    other. What it is not is a measurement of a model, so the row says what happened instead of
    reporting that a parse which does not exist covered nothing.
    """
    if job.incompatibility is not None:
        return f"refused as incompatible: {job.incompatibility.detail}"
    if job.failure:
        return f"the child job failed: {job.failure}"
    errors = [task.error for task in tasks if task.error]
    blocked = [task.blocked_reason for task in tasks if task.blocked_reason]
    if not documents and errors:
        return f"no part artifact was produced; the first recorded error was: {errors[0]}"
    if not documents and blocked:
        return f"no part artifact was produced; work is paused: {blocked[0]}"
    if not documents and not tasks:
        return "no provider response is preserved for this run"
    if not documents:
        return (
            "no readable part artifact is preserved for this run, so there is nothing to measure "
            "coverage from"
        )
    trailer = f"; {len(errors)} task(s) recorded an error" if errors else ""
    return f"{len(documents)} readable part artifact(s){trailer}"


__all__ = [
    "PART_TYPES",
    "SOURCE_INPUT_INTACT",
    "SOURCE_INPUT_PROJECTED",
    "SOURCE_INPUT_UNRECORDED",
    "MeasuredRun",
    "ModelComparisonService",
]
