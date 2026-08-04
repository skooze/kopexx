"""The model-directed multipart workflow: plan, parts, subparts, replanning, reconciliation.

ONE LOGICAL PARSE, MANY PROVIDER RESPONSES. Phase 2 sent a filing intact and then expected the
whole parsed artifact back in one response. An output cap is per response. It is not a cap on the
parse, and this service is what makes that difference real:

    SOURCE_PREFLIGHT       the source set is assembled once and preserved once
    PLAN_PARSE             the model divides the filing into parts it names itself
    PARSE_PART             one part per call, each a complete standalone document
    PLAN_SUBPARTS          when the model says a part is too large, before writing it
    PARSE_SUBPART          the same, one level down, to a configured depth limit
    REPLAN_TRUNCATED_PART  when a part attempt hits the cap, INSTEAD of continuing it
    RECONCILE_PARSE        the model judges whether its own plan was carried out
    GAP_REPAIR             the model judges mechanical findings the backend produced
    VALIDATE_ASSEMBLY      the index is checked against itself and the source set
    READY_FOR_REVIEW       a person can look at it

FOUR THINGS THIS SERVICE NEVER DOES, EACH OF WHICH WOULD BE EASIER THAN WHAT IT DOES INSTEAD.

    IT NEVER DECIDES WHAT A PART IS. There is no heading detector, no section list, no size-based
    splitter and no rule about where a filing divides. Every part identifier, title, type, order,
    relationship and subpart came out of a model response.

    IT NEVER ASKS A MODEL TO CONTINUE. A truncated attempt is preserved exactly, marked TRUNCATED,
    and left as evidence. What follows is a REPLANNING call that receives the intact filing again
    and proposes subparts covering the WHOLE original part. Nothing is concatenated, ever.

    IT NEVER SENDS A SLICE OF THE FILING. Every semantic invocation — planning, part, subpart,
    replanning, reconciliation, gap repair — receives the complete compatible source set, in filed
    order, with hashes verified. The source-set identity used for the preflight must equal the one
    submitted at execution, and a difference fails closed.

    IT NEVER SPENDS WITHOUT RESERVING FIRST. Every provider attempt takes its own reservation
    against three ceilings, and a failed attempt's reservation is not released. A retry is a second
    call and takes a second reservation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from packages.coverage_validation import validate_response
from packages.evaluation_store import (
    BILLABLE_TASK_TYPES,
    DependencyPolicy,
    EvaluationStore,
    ExecutionState,
    InvocationAttempt,
    JobRecord,
    MultipartTask,
    ParserSettings,
    PromptIdentity,
    TaskState,
    TaskType,
    idempotency_key,
    new_attempt_salt,
    new_task,
    new_task_id,
    summarise_tasks,
    utc_now,
)
from packages.llm_gateway import LlmGateway, ProviderError, compile_yaml, estimate_tokens
from packages.llm_gateway import to_yaml as _yaml
from packages.llm_gateway.providers.base import (
    MEDIA_IMAGE,
    MEDIA_TEXT,
    ModelProvider,
    OriginalSourceBlock,
)
from packages.model_catalog import ModelCapability, RetryBudget
from packages.multipart import (
    PART_ENVELOPE_KEYS,
    AssembledPart,
    AssemblyInputs,
    EnvelopeUnreadableError,
    ParsePlan,
    PartStatus,
    ProposedPart,
    acceptable_new_parts,
    assemble,
    read_amendment,
    read_part,
    read_plan,
    read_replan,
    validate_assembly,
    validate_part,
    validate_plan,
)
from packages.prompt_registry import PromptRegistry, PromptVersion
from packages.source_transport import SourceSet
from packages.storage import sha256_text

from . import briefs
from .errors import MultipartProtocolError
from .sizing import OutputSizing, compact_sizing, part_sizing, repair_sizing
from .spend_journal import SpendJournal

#: Prompt-registry roles, one per immutable multipart family.
ROLE_PLAN: Final[str] = "parsing_multipart_plan"
ROLE_PART: Final[str] = "parsing_multipart_part"
ROLE_REPLAN: Final[str] = "parsing_multipart_replan"
ROLE_RECONCILE: Final[str] = "parsing_multipart_reconcile"
ROLE_GAP: Final[str] = "parsing_multipart_gap"
ROLE_REPAIR: Final[str] = "parsing_multipart_format_repair"

_ROLE_FOR_TYPE: Final[dict[TaskType, str]] = {
    TaskType.PLAN_PARSE: ROLE_PLAN,
    TaskType.PARSE_PART: ROLE_PART,
    TaskType.PARSE_SUBPART: ROLE_PART,
    TaskType.PLAN_SUBPARTS: ROLE_REPLAN,
    TaskType.REPLAN_TRUNCATED_PART: ROLE_REPLAN,
    TaskType.RECONCILE_PARSE: ROLE_RECONCILE,
    TaskType.GAP_REPAIR: ROLE_GAP,
    TaskType.FORMAT_REPAIR: ROLE_REPAIR,
}

#: Evidence file names, per task. Fixed, lowercase and hyphenated so a reviewer opening any task
#: directory finds the same names. The SOURCE SET is deliberately absent: it is identical for every
#: task of one filing and is preserved once, at the child-job level.
REQUEST_BRIEF_EVIDENCE: Final[str] = "request-brief.yaml"
PROMPT_EVIDENCE: Final[str] = "prompt.txt"
REQUEST_TRANSPORT_EVIDENCE: Final[str] = "request-transport.json"
RESPONSE_EVIDENCE: Final[str] = "response-visible.txt"
REASONING_EVIDENCE: Final[str] = "response-reasoning.txt"
RESPONSE_TRANSPORT_EVIDENCE: Final[str] = "response-transport.json"
VALIDATION_EVIDENCE: Final[str] = "validation.yaml"
ENVELOPE_EVIDENCE: Final[str] = "envelope.yaml"

#: The source-set manifest, written ONCE at the CHILD JOB level. Deliberately the same name the
#: single-response path uses, so both protocols' review pages resolve a filename the same way.
SOURCE_SET_EVIDENCE: Final[str] = "source-set.yaml"

#: The provider stop reason that means the output budget ran out. A response carrying it is
#: TRUNCATED whatever its visible text looks like.
OUTPUT_LIMIT_STOP_REASON: Final[str] = "max_tokens"


@dataclass(frozen=True)
class MultipartSettings:
    """Operational limits. Every one is a SAFETY bound, never a statement about filings.

    `max_depth` does not say a filing has at most four levels of structure. It says this system
    stops spending on a branch that keeps asking to go deeper, records why, and asks a person.
    """

    max_depth: int = 4
    max_reconciliation_cycles: int = 3
    max_format_repairs_per_artifact: int = 1
    max_retries_per_attempt: int = 1
    filing_budget_usd: Decimal = Decimal("1.00")
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if self.max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        if self.max_reconciliation_cycles < 0:
            raise ValueError("max_reconciliation_cycles cannot be negative")
        if self.filing_budget_usd <= 0:
            raise ValueError("a filing budget must be positive")


@dataclass
class _Context:
    """Everything one filing's parse needs, resolved once per step rather than per task."""

    job: JobRecord
    capability: ModelCapability
    source_set: SourceSet
    blocks: tuple[OriginalSourceBlock, ...]
    artifact_texts: dict[str, str]
    filing_brief: dict[str, Any]
    plan: ParsePlan | None = None
    prompts_used: list[dict[str, Any]] = field(default_factory=list)


class MultipartParseService:
    """Drives one filing's model-directed multipart parse, one task at a time."""

    def __init__(
        self,
        *,
        store: EvaluationStore,
        snapshot: Any,
        prompts: PromptRegistry,
        inventory: Any,
        fetcher: Any,
        provider: ModelProvider,
        journal: SpendJournal,
        settings: MultipartSettings,
        author: str,
    ) -> None:
        self._store = store
        self._snapshot = snapshot
        self._prompts = prompts
        self._inventory = inventory
        self._fetcher = fetcher
        self._provider = provider
        self._journal = journal
        self._settings = settings
        self._author = author

    @property
    def settings(self) -> MultipartSettings:
        return self._settings

    # --- starting a parse -------------------------------------------------------------------------

    def start(self, run_id: str, job_id: str) -> MultipartTask:
        """Queue the planning task for one filing. Nothing is invoked here.

        Refuses to start twice. A second planning task under the same job would produce a second
        plan, and two plans over one filing is two parses wearing one identifier.
        """
        job = self._store.load_job(run_id, job_id)
        existing = [
            t for t in self._store.load_tasks(run_id, job_id) if t.task_type is TaskType.PLAN_PARSE
        ]
        if existing:
            return existing[0]

        context = self._context(job)
        sizing = compact_sizing(
            context.capability,
            estimated_input_tokens=job.estimated_input_tokens or 0,
            kind="plan",
        )
        task = self._create_task(
            job,
            task_type=TaskType.PLAN_PARSE,
            sizing=sizing,
            depends_on=(),
            order=0,
        )
        self._store.set_task_state(
            task,
            TaskState.READY,
            message="the planning call is the first billable step of a multipart parse",
        )
        job.strategy = "multipart"
        job.budget_ceiling_usd = job.budget_ceiling_usd or self._settings.filing_budget_usd
        job.multipart = self._session_summary(job, plan=None, tasks=[task])
        self._store.save_job(job)
        self._preserve_source_set(context)
        return task

    def _preserve_source_set(self, context: _Context) -> None:
        """Store the exact submitted bytes ONCE, at the child-job level, before any call.

        WITHOUT THIS THERE IS NO RAW VIEW AND NO SIDE-BY-SIDE VIEW. A reviewer opening one part
        needs the preserved filing beside it, and resolving that from a corpus path months later
        depends on a file nobody promised not to move. It is written once rather than per task
        because every semantic call of one filing receives the SAME set — a ten-task parse of a
        146 KB filing would otherwise store the filing ten times.

        The manifest gains an `evidence_name` per member, which is what the review surface
        resolves a filename through. That is the same mapping the single-response path writes, so
        both protocols' review pages read the source the same way.
        """
        job = context.job
        run_id, job_id = job.parent_run_id, job.job_id
        manifest = context.source_set.to_mapping()
        names: dict[str, str] = {}
        for index, block in enumerate(context.blocks, start=1):
            suffix = "bin" if block.is_image else "txt"
            name = f"source-{index:02d}.{suffix}"
            self._store.put_evidence(run_id, job_id, name, block.raw_bytes)
            names[block.label] = name
        for member in manifest["members"]:
            member["evidence_name"] = names.get(
                member["filename"] or f"{context.source_set.accession}.txt"
            )
        self._store.put_evidence_text(
            run_id, job_id, SOURCE_SET_EVIDENCE, _yaml(manifest), content_type="application/yaml"
        )
        job.source_set = manifest
        self._store.save_job(job)

    # --- explicit user actions --------------------------------------------------------------------
    #
    # NOTHING IN THIS SECTION IS EVER CALLED BY THE SYSTEM ITSELF. Each one spends money, and each
    # exists because a restart, a transient failure or a reviewer's judgement produced work that a
    # PERSON has to decide to pay for again.

    def resume(self, run_id: str, job_id: str) -> list[str]:
        """Reopen every INTERRUPTED task of one filing. Completed parts are untouched.

        Returns the task identifiers reopened. A parse whose plan and four parts succeeded keeps
        all five; only the branch that was in flight is re-armed, which is what "do not restart the
        entire filing parse when only one part is incomplete" means in code.
        """
        reopened: list[str] = []
        for task in self._store.load_tasks(run_id, job_id):
            if task.state is TaskState.INTERRUPTED:
                self._store.resume_task(task, author=self._author)
                reopened.append(task.task_id)
        # THE CHILD JOB REOPENS TOO, OR A FINISHED PARSE COULD NEVER REACH REVIEW. A restart marks
        # BOTH levels INTERRUPTED; reopening only the tasks left the job terminal while every task
        # beneath it succeeded, and `_finish` then had nowhere to move it. Measured on a real run:
        # 47 of 47 parts terminal, 214 nodes produced, and a job still reporting INTERRUPTED.
        #
        # UNCONDITIONALLY, NOT ONLY WHEN A TASK WAS RE-ARMED. A process can die between the last
        # task and assembly, and that is precisely the case where `reopened` is empty and the parse
        # needs nothing except to be assembled. Guarding on `reopened` would make resume a no-op on
        # the one shape it most needs to fix. Reopening spends nothing by itself: the caller still
        # has to drive the queue, and an empty queue costs an assembly pass.
        job = self._store.load_job(run_id, job_id)
        if job.execution_state is ExecutionState.INTERRUPTED:
            job.failure = None
            self._store.set_execution_state(
                job,
                ExecutionState.RUNNING,
                message=f"reopened by {self._author}; {len(reopened)} task(s) re-armed",
            )
        return reopened

    def retry(self, run_id: str, job_id: str, task_id: str) -> MultipartTask:
        """Reopen ONE failed or interrupted task under a NEW billable identity.

        The new `attempt_salt` is what makes this a rerun rather than a duplicate: without it the
        identity computed at execution would match the one an earlier successful attempt holds, and
        the scheduler would correctly refuse to pay twice for identical inputs. A reviewer asking
        for a second opinion is not a duplicate schedule, and the two must not be confused.
        """
        task = self._store.load_task(run_id, job_id, task_id)
        task.attempt_salt = new_attempt_salt()
        task.idempotency = ""
        task.error = None
        task.blocked_reason = None
        self._store.save_task(task)
        return self._store.resume_task(task, author=self._author)

    def unblock(self, run_id: str, job_id: str) -> list[str]:
        """Re-arm tasks a budget pause blocked, after a person has raised a ceiling.

        Deliberately separate from `resume`: an INTERRUPTED task was in flight when a process died,
        and a BLOCKED one was refused by a ceiling. Treating them as one action would let a restart
        quietly re-arm work that a spending limit had stopped.
        """
        reopened: list[str] = []
        for task in self._store.load_tasks(run_id, job_id):
            if task.state is TaskState.BLOCKED and task.blocked_reason:
                self._store.set_task_state(
                    task, TaskState.READY, message="unblocked by an explicit user action"
                )
                reopened.append(task.task_id)
        return reopened

    def cancel_branch(self, run_id: str, job_id: str, task_id: str) -> list[str]:
        """Cancel one queued task and every queued task beneath it. Nothing issued is touched."""
        tasks = {t.task_id: t for t in self._store.load_tasks(run_id, job_id)}
        cancelled: list[str] = []
        frontier = [task_id]
        while frontier:
            current = frontier.pop()
            task = tasks.get(current)
            if task is None:
                continue
            frontier.extend(t.task_id for t in tasks.values() if t.parent_task_id == current)
            try:
                self._store.cancel_task(task, reason="cancelled by the user before invocation")
            except Exception:  # noqa: BLE001 - a reserved or issued task is billable; leave it
                continue
            cancelled.append(current)
        return cancelled

    # --- driving ----------------------------------------------------------------------------------

    def run_next(self, run_id: str, job_id: str, *, only: TaskType | None = None) -> bool:
        """Execute exactly one runnable task. Returns whether anything ran.

        ONE AT A TIME AND SYNCHRONOUS. Every step writes its result durably before the next begins,
        so a crash between two tasks leaves the completed ones intact and the rest resumable. The
        alternative — a pool racing over shared budget — would make the ceiling advisory.

        `only` narrows the choice to one task type. It is what the review UI's "run reconciliation
        now" control uses, and it deliberately cannot make an unrunnable task runnable: a
        reconciliation still waits for its parts to reach a terminal state, because the dependency
        is durable and the scheduler reads it rather than being told.
        """
        runnable = self._store.runnable_tasks(run_id, job_id)
        if only is not None:
            runnable = [t for t in runnable if t.task_type is only]
        if not runnable:
            return False
        job = self._store.load_job(run_id, job_id)
        self._execute(self._context(job), runnable[0])
        return True

    def drive(self, run_id: str, job_id: str, *, max_steps: int = 400) -> JobRecord:
        """Run tasks until nothing is runnable, then finish the parse.

        `max_steps` is a runaway guard, not a scheduling policy. A parse that hits it has almost
        certainly created work in a loop, and stopping with everything preserved is the honest
        outcome.

        THE CONTEXT IS BUILT ONCE PER DRIVE, NOT ONCE PER TASK, AND THE SOURCE-SET GUARD IS WHY
        THAT IS SAFE RATHER THAN MERELY FASTER. `_context` re-assembles the source set and refuses
        a set that has moved since the parse was costed. Doing that per task re-verified identical
        bytes a dozen times and re-parsed every task manifest to find the plan — thirty seconds of a
        forty-second run, on documents measured in kilobytes. The guard still runs, once, before
        any task of this pass; a member that changed mid-pass is caught by the next pass, and the
        plan is immutable once written.
        """
        steps = 0
        context = self._context(self._store.load_job(run_id, job_id))
        while steps < max_steps:
            runnable = self._store.runnable_tasks(run_id, job_id)
            if not runnable:
                break
            context.job = self._store.load_job(run_id, job_id)
            if context.plan is None:
                context.plan = self._load_plan(context.job)
            self._execute(context, runnable[0])
            steps += 1
        if steps >= max_steps:
            self._store.append_event(
                run_id,
                kind="run.step_limit",
                job_id=job_id,
                message=(
                    f"the parse reached the {max_steps}-step guard and stopped. Everything "
                    "produced is preserved; nothing was discarded."
                ),
            )
        return self._finish(run_id, job_id)

    # --- context ----------------------------------------------------------------------------------

    def _context(self, job: JobRecord) -> _Context:
        """Rebuild everything a task needs, and refuse a source set that has moved.

        THE SET THAT WAS COSTED MUST BE THE SET THAT IS SENT, and in a multipart parse that has to
        hold across every task rather than once. A member re-acquired between the plan and the
        eighth part would mean eight calls read one filing and one read another, with a single
        source_set_id claiming to describe both.
        """
        from packages.source_transport import assemble_source_set

        capability = self._snapshot.get(job.routing.label)
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
        if job.source_set_id and source_set.source_set_id != job.source_set_id:
            raise MultipartProtocolError(
                f"the source set changed after this parse was costed: {job.source_set_id} became "
                f"{source_set.source_set_id}. Every task of a multipart parse must read the same "
                "bytes, so this is refused rather than reconciled."
            )
        blocks = self._blocks(source_set, multimodal=capability.multimodal)
        return _Context(
            job=job,
            capability=capability,
            source_set=source_set,
            blocks=blocks,
            artifact_texts={b.label: (b.text or "") for b in blocks if not b.is_image},
            filing_brief=briefs.filing_brief(
                cik=job.cik,
                accession=job.accession,
                form_as_filed=job.form_as_filed,
                filing_date=job.filing_date,
                issuer_label=job.issuer_label,
                source_set_id=source_set.source_set_id,
                members=[m.to_mapping() for m in source_set.members],
                images_submitted=capability.multimodal,
            ),
            plan=self._load_plan(job),
        )

    @staticmethod
    def _blocks(source_set: SourceSet, *, multimodal: bool) -> tuple[OriginalSourceBlock, ...]:
        """One provider block per submitted member, in filed order, admitted by provenance.

        IDENTICAL ON EVERY SEMANTIC CALL, INCLUDING THE IMAGES. Section 5 of the Phase 2.1 brief is
        deliberately conservative here: a multimodal parser receives the complete image set on
        every planning, part, subpart, replanning, reconciliation and gap-repair invocation, and no
        optimisation of that repetition happens until measured evidence supports one.
        """
        from packages.source_transport import MemberDisposition

        blocks: list[OriginalSourceBlock] = []
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

    def _load_plan(self, job: JobRecord) -> ParsePlan | None:
        """The plan this parse is working from, read back from its preserved response bytes.

        Read from EVIDENCE rather than from a cached record, so the plan a part is generated
        against is provably the plan the model returned.
        """
        for task in self._store.load_tasks(job.parent_run_id, job.job_id):
            if task.task_type is not TaskType.PLAN_PARSE or task.state is not TaskState.SUCCEEDED:
                continue
            if not self._store.has_task_evidence(
                job.parent_run_id, job.job_id, task.task_id, RESPONSE_EVIDENCE
            ):
                continue
            text = self._store.get_task_evidence_text(
                job.parent_run_id, job.job_id, task.task_id, RESPONSE_EVIDENCE
            )
            try:
                return read_plan(text)
            except EnvelopeUnreadableError:
                return None
        return None

    # --- task creation ----------------------------------------------------------------------------

    def _create_task(
        self,
        job: JobRecord,
        *,
        task_type: TaskType,
        sizing: OutputSizing,
        depends_on: tuple[str, ...],
        order: int,
        parent_task_id: str | None = None,
        plan_id: str = "",
        part: ProposedPart | dict[str, Any] | None = None,
        parent_part_id: str | None = None,
        depth: int = 0,
        dependency_policy: DependencyPolicy = DependencyPolicy.ALL_SUCCEEDED,
        note: str = "",
    ) -> MultipartTask:
        prompt = self._prompt_for(task_type)
        spec = (
            part.to_mapping() if isinstance(part, ProposedPart) else (dict(part) if part else None)
        )
        task = new_task(
            task_id=new_task_id(),
            run_id=job.parent_run_id,
            root_job_id=job.job_id,
            parent_task_id=parent_task_id,
            task_type=task_type,
            routing=job.routing,
            prompt=PromptIdentity(
                prompt_id=prompt.prompt_id, version=prompt.version, sha256=prompt.sha256
            ),
            settings=ParserSettings(
                max_output_tokens=sizing.requested_output_tokens,
                temperature=self._settings.temperature,
            ),
            order=order,
            depth=depth,
            plan_id=plan_id,
            part_id=str((spec or {}).get("part_id") or ""),
            parent_part_id=parent_part_id,
            storage_token=str((spec or {}).get("storage_token") or ""),
            part_spec=spec,
            source_set_id=job.source_set_id or "",
            depends_on=list(depends_on),
            dependency_policy=dependency_policy,
            attempt_salt="",
            estimated_input_tokens=job.estimated_input_tokens,
            output_target_tokens=sizing.visible_target_tokens,
            note=note,
        )
        self._store.save_task(task)
        return task

    def _idempotency(self, job: JobRecord, task: MultipartTask, *, brief_content: str) -> str:
        """The billable identity of one attempt, computed from EVERYTHING that changes the answer.

        COMPUTED AT EXECUTION, NOT AT CREATION, AND THAT IS THE CORRECTION. The declared components
        — source set, model, region, prompt, task type, plan, part, settings — are not sufficient on
        their own, and the gap was not hypothetical: two reconciliation cycles differ ONLY in the
        cycle number and the inventory they carry, both of which live in the brief. Keyed on the
        declared components alone, cycle 2 collided with cycle 1 and was skipped as a duplicate,
        which silently disabled the reconciliation loop.

        Hashing the compiled brief is the faithful reading of "parent artifact identity": the brief
        IS the parent artifact for a reconciliation, a gap repair and a replanning call, and it
        carries the plan response for a part. Two calls with identical bytes get identical keys;
        anything that would come back differently gets a different one.
        """
        return idempotency_key(
            source_set_id=job.source_set_id or "",
            model_label=job.routing.label,
            invocation_id=job.routing.invocation_id,
            region=job.routing.region,
            prompt_identity=f"{task.prompt.prompt_id}@{task.prompt.version}",
            prompt_sha256=task.prompt.sha256,
            task_type=task.task_type.value,
            plan_id=task.plan_id,
            part_id=task.part_id,
            parent_artifact_sha256=sha256_text(brief_content),
            max_output_tokens=task.settings.max_output_tokens,
            temperature=task.settings.temperature,
            attempt_salt=task.attempt_salt,
        )

    def _prompt_for(self, task_type: TaskType) -> PromptVersion:
        role = _ROLE_FOR_TYPE.get(task_type)
        if role is None:
            raise MultipartProtocolError(
                f"{task_type.value} invokes no model and has no prompt; only the billable task "
                "types carry one"
            )
        return self._prompts.active_for(role)

    # --- execution --------------------------------------------------------------------------------

    def _execute(self, context: _Context, task: MultipartTask) -> None:
        """Run one task end to end, or pause it with the reason."""
        job = context.job
        run_id, job_id = job.parent_run_id, job.job_id

        if task.task_type not in BILLABLE_TASK_TYPES:
            self._store.set_task_state(task, TaskState.READY)
            self._store.set_task_state(task, TaskState.SUCCEEDED, message="mechanical task")
            return

        prompt = self._prompts.get(task.prompt.prompt_id, task.prompt.version)
        brief = self._brief_for(context, task)
        payload = compile_yaml(brief, origin=f"multipart.{task.task_type.value.lower()}")
        task.idempotency = self._idempotency(job, task, brief_content=payload.content)
        self._store.save_task(task)

        # DUPLICATE-SCHEDULING PROTECTION, NOT AN EXACTLY-ONCE CLAIM. If this repository already
        # paid for exactly these inputs and holds the response, it does not pay again. The task is
        # CANCELLED rather than failed: nothing went wrong, and a run whose duplicate guard fired
        # should not read as a run with a failure in it.
        already = self._store.find_successful_task(run_id, job_id, idempotency=task.idempotency)
        if already is not None and already.task_id != task.task_id:
            task.note = (
                f"skipped: task {already.task_id} already holds a successful response for exactly "
                "these inputs. An explicit rerun mints a new attempt identity."
            )
            self._store.save_task(task)
            self._store.cancel_task(task, reason=task.note)
            return

        # FORMAT REPAIR IS THE ONE CALL THAT DOES NOT CARRY THE FILING. It is forbidden to change
        # meaning, so it is given nothing to change it with.
        blocks = () if task.task_type is TaskType.FORMAT_REPAIR else context.blocks

        estimated_input = (
            payload.estimated_tokens
            + estimate_tokens(prompt.text)
            + sum(estimate_tokens(b.text or "") for b in blocks if not b.is_image)
        )
        task.estimated_input_tokens = estimated_input

        affordable, reason = self._journal.can_afford(
            self._journal.bound(
                context.capability.price,
                max_input_tokens=estimated_input,
                max_output_tokens=task.settings.max_output_tokens,
            ),
            job_id=job_id,
            budget_usd=job.budget_ceiling_usd,
        )
        if not affordable:
            task.blocked_reason = reason
            self._store.save_task(task)
            if task.state is not TaskState.BLOCKED:
                self._store.set_task_state(task, TaskState.BLOCKED, message=reason)
            self._store.append_event(
                run_id, kind="budget.paused", job_id=job_id, task_id=task.task_id, message=reason
            )
            return

        self._store.put_task_evidence_text(
            run_id, job_id, task.task_id, PROMPT_EVIDENCE, prompt.text
        )
        self._store.put_task_evidence_text(
            run_id,
            job_id,
            task.task_id,
            REQUEST_BRIEF_EVIDENCE,
            payload.content,
            content_type="application/yaml",
        )
        task.input_artifact_ids = [PROMPT_EVIDENCE, REQUEST_BRIEF_EVIDENCE]
        self._store.save_task(task)

        if task.state is not TaskState.READY:
            self._store.set_task_state(task, TaskState.READY)
        record = self._invoke(context, task, prompt=prompt, payload=payload, blocks=blocks)
        if record is None:
            return

        self._preserve(context, task, record)
        self._store.set_task_state(
            task,
            TaskState.RESPONSE_RECEIVED,
            message=(
                f"{record.input_tokens} input and {record.output_tokens} output tokens, stop "
                f"reason {record.stop_reason or 'unreported'}, USD {task.actual_cost_usd}"
            ),
        )

        if record.stop_reason == OUTPUT_LIMIT_STOP_REASON:
            self._on_truncation(context, task, record)
            return

        self._store.set_task_state(task, TaskState.VALIDATING)
        self._interpret(context, task, record.response_body)

    def _invoke(
        self,
        context: _Context,
        task: MultipartTask,
        *,
        prompt: PromptVersion,
        payload: Any,
        blocks: tuple[OriginalSourceBlock, ...],
    ) -> Any:
        """One billable attempt, plus at most one retry for a transient condition.

        A RETRY IS A SECOND RESERVATION. The reservation for a failed attempt is NOT released: that
        request was issued and cost money, and only an attempt that returns usage is settled
        against a measurement.

        `max_tokens` IS NOT RETRYABLE and is not treated as a failure here. It is a result, and the
        result is a replanning task.
        """
        job = context.job
        run_id, job_id = job.parent_run_id, job.job_id
        gateway = LlmGateway(self._provider)
        budget = RetryBudget(max_retries=self._settings.max_retries_per_attempt)
        attempt_number = len(task.attempts)

        while True:
            attempt_number += 1
            try:
                reserved = self._journal.authorize(
                    context.capability.price,
                    max_input_tokens=task.estimated_input_tokens or 0,
                    max_output_tokens=task.settings.max_output_tokens,
                    at=utc_now(),
                    run_id=run_id,
                    job_id=job_id,
                    model_label=job.routing.label,
                    task_id=task.task_id,
                    filing_budget_usd=job.budget_ceiling_usd,
                )
            except Exception as error:  # noqa: BLE001 - a ceiling refusal pauses, never fails
                task.blocked_reason = str(error)
                self._store.save_task(task)
                self._store.set_task_state(task, TaskState.BLOCKED, message=str(error)[:400])
                self._store.append_event(
                    run_id,
                    kind="budget.paused",
                    job_id=job_id,
                    task_id=task.task_id,
                    message=str(error)[:400],
                )
                return None

            task.reserved_cost_usd = (task.reserved_cost_usd or Decimal(0)) + reserved
            self._store.save_task(task)
            if task.state is TaskState.READY:
                self._store.set_task_state(
                    task,
                    TaskState.RESERVED,
                    message=f"attempt {attempt_number}: worst case USD {reserved} reserved",
                )
            self._store.set_task_state(task, TaskState.RUNNING)

            started = utc_now()
            try:
                result = gateway.invoke(
                    model_id=job.routing.invocation_id,
                    system_text=prompt.text,
                    payload=payload,
                    prompt_version=f"{prompt.prompt_id}@{prompt.version}",
                    expect_structured=True,
                    max_output_tokens=task.settings.max_output_tokens,
                    original_source=blocks,
                    temperature=task.settings.temperature,
                    region=job.routing.region,
                    cost=context.capability.price.cost,
                    strict_response=False,
                )
            except ProviderError as error:
                task.attempts.append(
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
                self._store.save_task(task)
                try:
                    budget.consume(retryable=error.retryable)
                except Exception:  # noqa: BLE001 - the refusal message is the useful part
                    task.error = str(error)
                    self._store.save_task(task)
                    self._store.set_task_state(task, TaskState.FAILED, message=str(error)[:400])
                    return None
                self._store.append_event(
                    run_id,
                    kind="invocation.retry",
                    job_id=job_id,
                    task_id=task.task_id,
                    message="one retry, for a transient provider condition",
                )
                # The retry re-enters RUNNING from RUNNING, which the machine does not permit, so
                # the loop reserves again and re-issues without a state change. The attempt record
                # is what makes the second call visible.
                continue

            record = result.record
            actual = self._journal.settle(
                context.capability.price,
                reserved=reserved,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                at=utc_now(),
                run_id=run_id,
                job_id=job_id,
                model_label=job.routing.label,
                task_id=task.task_id,
            )
            task.actual_cost_usd = (task.actual_cost_usd or Decimal(0)) + actual
            task.attempts.append(
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
            self._store.save_task(task)
            return record

    def _preserve(self, context: _Context, task: MultipartTask, record: Any) -> None:
        """Exact bytes become durable BEFORE any claim is made about them."""
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        names = [REQUEST_BRIEF_EVIDENCE, PROMPT_EVIDENCE, RESPONSE_EVIDENCE]
        self._store.put_task_evidence_text(
            run_id, job_id, task.task_id, RESPONSE_EVIDENCE, record.response_body
        )
        if record.reasoning_body:
            self._store.put_task_evidence_text(
                run_id, job_id, task.task_id, REASONING_EVIDENCE, record.reasoning_body
            )
            names.append(REASONING_EVIDENCE)
        if record.transport_request:
            self._store.put_task_evidence_text(
                run_id,
                job_id,
                task.task_id,
                REQUEST_TRANSPORT_EVIDENCE,
                record.transport_request,
                content_type="application/json",
            )
            names.append(REQUEST_TRANSPORT_EVIDENCE)
        if record.transport_response:
            self._store.put_task_evidence_text(
                run_id,
                job_id,
                task.task_id,
                RESPONSE_TRANSPORT_EVIDENCE,
                record.transport_response,
                content_type="application/json",
            )
            names.append(RESPONSE_TRANSPORT_EVIDENCE)
        task.output_artifact_ids = names
        self._store.save_task(task)

    # --- outcomes ---------------------------------------------------------------------------------

    def _on_truncation(self, context: _Context, task: MultipartTask, record: Any) -> None:
        """A response that hit the output cap. Preserved, marked, and NEVER continued."""
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        task.truncation = {
            "stop_reason": record.stop_reason,
            "output_tokens": record.output_tokens,
            "configured_cap": task.settings.max_output_tokens,
            "visible_characters": len(record.response_body),
            "reasoning_characters": len(record.reasoning_body),
            "disposition": (
                "EVIDENCE ONLY. The partial content is not merged into the assembled parse. It is "
                "preserved exactly and shown in the review UI, and the work it did not finish is "
                "picked up by a replanning task — never by asking the model to continue."
            ),
        }
        self._store.save_task(task)
        self._store.set_task_state(
            task,
            TaskState.TRUNCATED,
            message=(
                f"the output limit of {task.settings.max_output_tokens} tokens was reached; this "
                "attempt is evidence and the part is not complete"
            ),
        )
        self._store.append_event(
            run_id,
            kind="part.truncated",
            job_id=job_id,
            task_id=task.task_id,
            message=f"part {task.part_id or '(plan)'} truncated at {record.output_tokens} tokens",
        )

        if task.task_type not in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}:
            # A truncated PLAN, REPLAN, RECONCILE or GAP call has no part to divide. It is left as
            # terminal evidence; the parse continues with what it has and reports the gap.
            return
        if task.depth + 1 > self._settings.max_depth:
            self._store.append_event(
                run_id,
                kind="depth.limit",
                job_id=job_id,
                task_id=task.task_id,
                message=(
                    f"this branch reached the configured depth limit of {self._settings.max_depth} "
                    "and was paused rather than divided again. An operational limit, not a "
                    "statement about the filing."
                ),
            )
            return
        self._queue_replan(context, task)

    def _queue_replan(self, context: _Context, truncated: MultipartTask) -> None:
        """Queue the model-directed replanning task for a truncated part."""
        job = context.job
        sizing = compact_sizing(
            context.capability,
            estimated_input_tokens=job.estimated_input_tokens or 0,
            kind="replan",
        )
        task = self._create_task(
            job,
            task_type=TaskType.REPLAN_TRUNCATED_PART,
            sizing=sizing,
            depends_on=(),
            order=truncated.order,
            parent_task_id=truncated.task_id,
            plan_id=truncated.plan_id,
            part=truncated.part_spec,
            parent_part_id=truncated.parent_part_id,
            depth=truncated.depth,
            note="created because the part attempt reached the output limit",
        )
        self._store.set_task_state(
            task,
            TaskState.READY,
            message="replanning a truncated part; the truncated text is evidence, not a prefix",
        )

    def _interpret(self, context: _Context, task: MultipartTask, text: str) -> None:
        """Read the response for its envelope, validate it, and queue whatever it created."""
        handler = {
            TaskType.PLAN_PARSE: self._interpret_plan,
            TaskType.PARSE_PART: self._interpret_part,
            TaskType.PARSE_SUBPART: self._interpret_part,
            TaskType.REPLAN_TRUNCATED_PART: self._interpret_replan,
            TaskType.PLAN_SUBPARTS: self._interpret_replan,
            TaskType.RECONCILE_PARSE: self._interpret_amendment,
            TaskType.GAP_REPAIR: self._interpret_amendment,
            TaskType.FORMAT_REPAIR: self._interpret_repair,
        }[task.task_type]
        try:
            handler(context, task, text)
        except EnvelopeUnreadableError as error:
            self._on_unreadable(context, task, text, str(error))

    def _on_unreadable(self, context: _Context, task: MultipartTask, text: str, error: str) -> None:
        """A response that will not parse. It is kept, and repaired ONCE by the model, or reported.

        NOT REPAIRED IN BACKEND CODE. No regular expression rewrites a malformed response here, and
        the original is never replaced: the repair is a separate task with its own request, its own
        response, its own validation and its own cost.
        """
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        task.error = error
        task.envelope = {"readable": False, "parse_error": error}
        self._store.save_task(task)
        self._store.set_task_state(
            task, TaskState.SUCCEEDED, message=f"unreadable envelope: {error[:200]}"
        )

        # A REPAIR IS NEVER REPAIRED. The limit is one repair per ARTIFACT, and counting only the
        # repairs of THIS task let a chain evade it: an unreadable repair became a new artifact
        # with its own allowance, and the next one after that. Measured on a real run — a
        # FORMAT_REPAIR whose parent was itself a FORMAT_REPAIR. A model that cannot produce one
        # readable document from an explicit repair brief is not going to produce one from a
        # repair of the repair; it just spends money and buries the original two links back.
        if task.task_type is TaskType.FORMAT_REPAIR:
            self._store.append_event(
                run_id,
                kind="repair.not_repaired",
                job_id=job_id,
                task_id=task.task_id,
                message=(
                    "a format repair returned an unreadable document. It is preserved and "
                    "reported; a repair is never itself repaired."
                ),
            )
            return
        repairs = [
            t
            for t in self._store.load_tasks(run_id, job_id)
            if t.task_type is TaskType.FORMAT_REPAIR and t.parent_task_id == task.task_id
        ]
        if len(repairs) >= self._settings.max_format_repairs_per_artifact:
            return
        sizing = repair_sizing(
            context.capability,
            estimated_input_tokens=estimate_tokens(text),
            malformed_tokens=estimate_tokens(text),
        )
        repair = self._create_task(
            context.job,
            task_type=TaskType.FORMAT_REPAIR,
            sizing=sizing,
            depends_on=(),
            order=task.order,
            parent_task_id=task.task_id,
            plan_id=task.plan_id,
            part=task.part_spec,
            parent_part_id=task.parent_part_id,
            depth=task.depth,
            note="one narrowly scoped format repair; the original response is preserved unchanged",
        )
        self._store.set_task_state(
            repair, TaskState.READY, message="format repair, at most one per artifact"
        )

    def _interpret_plan(self, context: _Context, task: MultipartTask, text: str) -> None:
        plan = read_plan(text)
        validation = validate_plan(plan)
        task.plan_id = plan.plan_id
        task.envelope = plan.to_mapping()
        task.validation = validation.to_mapping()
        self._write_envelope(context, task)
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        self._store.set_task_state(
            task,
            TaskState.SUCCEEDED,
            message=(
                f"plan {plan.plan_id or '(unnamed)'} with {len(plan.parts)} part(s); "
                f"{'schedulable' if validation.schedulable else 'NOT schedulable'}"
            ),
        )
        if not validation.schedulable:
            self._store.append_event(
                run_id,
                kind="plan.unschedulable",
                job_id=job_id,
                task_id=task.task_id,
                message="; ".join(validation.findings)[:400],
            )
            return

        context.plan = plan
        # THE SESSION SUMMARY IS REFRESHED HERE, NOT ONLY WHEN THE PARSE FINISHES. It is what the
        # hierarchy header reads, and a run that is interrupted or paused after planning would
        # otherwise show "plan not yet produced" beside twenty-four parts the plan created. A
        # header that contradicts the table under it is worse than one that says less.
        context.job.multipart = self._session_summary(
            context.job, plan=plan, tasks=self._store.load_tasks(run_id, job_id)
        )
        self._store.save_job(context.job)
        by_part: dict[str, str] = {}
        for index, part in enumerate(plan.ordered()):
            created = self._create_task(
                context.job,
                task_type=TaskType.PARSE_PART,
                sizing=part_sizing(
                    context.capability,
                    estimated_input_tokens=context.job.estimated_input_tokens or 0,
                ),
                depends_on=(),
                order=part.order if part.order is not None else index,
                parent_task_id=task.task_id,
                plan_id=plan.plan_id,
                part=part.to_mapping(),
                depth=1,
            )
            by_part[part.part_id] = created.task_id
        # Declared dependencies become DURABLE dependency records, resolved after every part task
        # exists so a part may legitimately depend on one declared after it.
        for part in plan.parts:
            task_id = by_part.get(part.part_id)
            if task_id is None:
                continue
            depends = [by_part[d] for d in part.depends_on if d in by_part]
            created = self._store.load_task(run_id, job_id, task_id)
            created.depends_on = depends
            self._store.save_task(created)
            self._store.set_task_state(
                created,
                TaskState.READY if not depends else TaskState.BLOCKED,
                message=(
                    f"part {part.part_id}"
                    if not depends
                    else f"part {part.part_id} waits for {len(depends)} declared dependency"
                ),
            )
        self._queue_reconciliation(context, plan, cycle=1)

    def _interpret_part(self, context: _Context, task: MultipartTask, text: str) -> None:
        part = read_part(text)
        plan = context.plan or self._load_plan(context.job)
        known = set(plan.part_ids) if plan else set()
        for other in self._store.load_tasks(context.job.parent_run_id, context.job.job_id):
            if other.part_id:
                known.add(other.part_id)
        envelope_validation = validate_part(
            part,
            expected_plan_id=task.plan_id,
            expected_part_id=task.part_id,
            known_part_ids=known,
        )
        coverage, _ = validate_response(
            text,
            artifact_texts=context.artifact_texts,
            image_filenames=tuple(m.filename for m in context.source_set.image_members),
            images_analysed=context.capability.multimodal
            and bool(context.source_set.image_members),
            envelope_keys=PART_ENVELOPE_KEYS,
            require_every_artifact_referenced=False,
        )
        task.envelope = part.to_mapping()
        task.validation = {
            "envelope": envelope_validation.to_mapping(),
            "coverage": coverage.to_mapping(),
        }
        self._write_envelope(context, task)
        self._store.set_task_state(
            task,
            TaskState.SUCCEEDED,
            message=(
                f"part {part.part_id or task.part_id}: {part.declared_status or 'no status'}, "
                f"{part.node_count} node(s), "
                f"{coverage.references_resolved}/{coverage.reference_count} references resolved"
            ),
        )
        if part.status is PartStatus.NEEDS_SUBPARTS and part.proposed_subparts:
            self._queue_subparts(context, task, part.proposed_subparts, known_part_ids=known)

    def _queue_subparts(
        self,
        context: _Context,
        parent: MultipartTask,
        proposed: tuple[ProposedPart, ...],
        *,
        known_part_ids: set[str],
    ) -> None:
        """Create the subpart tasks a model proposed. The backend invents no boundary."""
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        depth = parent.depth + 1
        if depth > self._settings.max_depth:
            self._store.append_event(
                run_id,
                kind="depth.limit",
                job_id=job_id,
                task_id=parent.task_id,
                message=(
                    f"the model proposed a decomposition at depth {depth} and the configured "
                    f"operational limit is {self._settings.max_depth}. This branch is paused with "
                    "its reason recorded; it is not a statement about the filing's structure."
                ),
            )
            return
        accepted, rejected = acceptable_new_parts(proposed, known_part_ids=known_part_ids)
        if rejected:
            self._store.append_event(
                run_id,
                kind="subplan.rejected",
                job_id=job_id,
                task_id=parent.task_id,
                message=(
                    f"{len(rejected)} proposed subpart identifier(s) already exist and were not "
                    f"queued: {', '.join(rejected)}. They are not renamed."
                ),
            )
        for index, sub in enumerate(accepted):
            task = self._create_task(
                context.job,
                task_type=TaskType.PARSE_SUBPART,
                sizing=part_sizing(
                    context.capability,
                    estimated_input_tokens=context.job.estimated_input_tokens or 0,
                ),
                depends_on=(),
                order=sub.order if sub.order is not None else index,
                parent_task_id=parent.task_id,
                plan_id=parent.plan_id,
                part=sub,
                parent_part_id=parent.part_id or None,
                depth=depth,
                note="proposed by the model when it judged the parent part too large",
            )
            self._store.set_task_state(
                task, TaskState.READY, message=f"subpart {sub.part_id} of {parent.part_id}"
            )
        self._store.append_event(
            run_id,
            kind="subplan.created",
            job_id=job_id,
            task_id=parent.task_id,
            message=f"{len(accepted)} subpart(s) queued at depth {depth}",
        )

    def _interpret_replan(self, context: _Context, task: MultipartTask, text: str) -> None:
        outcome = read_replan(text)
        task.envelope = outcome.to_mapping()
        self._write_envelope(context, task)
        known = {
            t.part_id
            for t in self._store.load_tasks(context.job.parent_run_id, context.job.job_id)
            if t.part_id
        }
        plan = context.plan or self._load_plan(context.job)
        if plan:
            known |= set(plan.part_ids)
        self._store.set_task_state(
            task,
            TaskState.SUCCEEDED,
            message=(
                f"{len(outcome.proposed_subparts)} subpart(s) proposed to cover the whole of part "
                f"{outcome.part_id or task.part_id}"
            ),
        )
        if outcome.proposed_subparts:
            self._queue_subparts(context, task, outcome.proposed_subparts, known_part_ids=known)

    def _interpret_amendment(self, context: _Context, task: MultipartTask, text: str) -> None:
        # THE ORCHESTRATOR'S CYCLE COUNT IS AUTHORITATIVE FOR SCHEDULING; THE MODEL'S IS DATA.
        # `read_amendment` prefers a declared cycle so the reviewer sees what the model believed,
        # and a model that answers every cycle with "cycle: 1" would otherwise reset the limit on
        # every pass and reconcile for ever. The limit is a spending control, so it counts what
        # actually ran.
        cycle = int((task.part_spec or {}).get("cycle") or 1)
        amendment = read_amendment(text, cycle=cycle)
        task.envelope = amendment.to_mapping()
        self._write_envelope(context, task)
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        self._store.set_task_state(
            task,
            TaskState.SUCCEEDED,
            message=(
                f"cycle {amendment.cycle}: model-declared complete "
                f"{amendment.plan_complete}; {len(amendment.additional_parts)} additional and "
                f"{len(amendment.replacement_parts)} replacement part(s) requested"
            ),
        )

        plan = context.plan or self._load_plan(context.job)
        known = {t.part_id for t in self._store.load_tasks(run_id, job_id) if t.part_id}
        if plan:
            known |= set(plan.part_ids)
        proposed = amendment.additional_parts + amendment.replacement_parts
        accepted, rejected = acceptable_new_parts(proposed, known_part_ids=known)
        if rejected:
            self._store.append_event(
                run_id,
                kind="reconcile.rejected",
                job_id=job_id,
                task_id=task.task_id,
                message=(
                    f"{len(rejected)} requested part identifier(s) already exist and were not "
                    f"queued: {', '.join(rejected)}. An earlier result is never overwritten."
                ),
            )
        created_ids: list[str] = []
        for index, part in enumerate(accepted):
            created = self._create_task(
                context.job,
                task_type=TaskType.PARSE_PART,
                sizing=part_sizing(
                    context.capability,
                    estimated_input_tokens=context.job.estimated_input_tokens or 0,
                ),
                depends_on=(),
                order=part.order if part.order is not None else index,
                parent_task_id=task.task_id,
                plan_id=task.plan_id,
                part=part,
                depth=1,
                note=f"requested by {task.task_type.value.lower()} cycle {amendment.cycle}",
            )
            self._store.set_task_state(created, TaskState.READY, message=f"part {part.part_id}")
            created_ids.append(created.task_id)
        if created_ids:
            self._store.append_event(
                run_id,
                kind="reconcile.added_work",
                job_id=job_id,
                task_id=task.task_id,
                message=f"{len(created_ids)} further part(s) queued by cycle {cycle}",
            )
            if plan is not None and cycle < self._settings.max_reconciliation_cycles:
                self._queue_reconciliation(context, plan, cycle=cycle + 1)
            elif plan is not None:
                self._store.append_event(
                    run_id,
                    kind="reconcile.cycle_limit",
                    job_id=job_id,
                    task_id=task.task_id,
                    message=(
                        f"the reconciliation cycle limit of "
                        f"{self._settings.max_reconciliation_cycles} was reached with work still "
                        "outstanding. Everything produced is preserved and the unresolved state is "
                        "carried into review."
                    ),
                )

    def _interpret_repair(self, context: _Context, task: MultipartTask, text: str) -> None:
        """A repaired artifact is a SEPARATE artifact. The original is untouched."""
        parent = self._store.load_task(
            context.job.parent_run_id, context.job.job_id, task.parent_task_id or ""
        )
        task.plan_id = parent.plan_id
        task.part_id = parent.part_id
        task.parent_part_id = parent.parent_part_id
        self._store.save_task(task)
        if parent.task_type in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}:
            self._interpret_part(context, task, text)
            return
        if parent.task_type is TaskType.PLAN_PARSE:
            self._interpret_plan(context, task, text)
            return
        task.envelope = {"repaired": True, "of_task": parent.task_id}
        self._write_envelope(context, task)
        self._store.set_task_state(
            task, TaskState.SUCCEEDED, message=f"repaired serialisation of {parent.task_id}"
        )

    def _queue_reconciliation(self, context: _Context, plan: ParsePlan, *, cycle: int) -> None:
        """Queue one reconciliation cycle, waiting for every current part to reach a terminal state.

        DEPENDENCY POLICY IS `ALL_TERMINAL`, NOT `ALL_SUCCEEDED`, AND THAT IS THE POINT. A part that
        truncated or failed is exactly what reconciliation exists to notice; waiting for it to
        succeed would mean the one case that needs reconciling never reaches it.
        """
        if cycle > self._settings.max_reconciliation_cycles:
            return
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        parts = [
            t.task_id
            for t in self._store.load_tasks(run_id, job_id)
            if t.task_type in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}
        ]
        task = self._create_task(
            context.job,
            task_type=TaskType.RECONCILE_PARSE,
            sizing=compact_sizing(
                context.capability,
                estimated_input_tokens=context.job.estimated_input_tokens or 0,
                kind="reconcile",
            ),
            depends_on=tuple(parts),
            order=10_000 + cycle,
            plan_id=plan.plan_id,
            part={"cycle": cycle},
            depth=0,
            dependency_policy=DependencyPolicy.ALL_TERMINAL,
            note=f"reconciliation cycle {cycle}",
        )
        self._store.set_task_state(
            task,
            TaskState.BLOCKED if parts else TaskState.READY,
            message=f"reconciliation cycle {cycle} waits for {len(parts)} part(s)",
        )

    def _write_envelope(self, context: _Context, task: MultipartTask) -> None:
        run_id, job_id = context.job.parent_run_id, context.job.job_id
        self._store.put_task_evidence_text(
            run_id,
            job_id,
            task.task_id,
            ENVELOPE_EVIDENCE,
            _yaml(task.envelope or {}),
            content_type="application/yaml",
        )
        if task.validation is not None:
            self._store.put_task_evidence_text(
                run_id,
                job_id,
                task.task_id,
                VALIDATION_EVIDENCE,
                _yaml(task.validation),
                content_type="application/yaml",
            )
        self._store.save_task(task)

    # --- briefs -----------------------------------------------------------------------------------

    def _brief_for(self, context: _Context, task: MultipartTask) -> dict[str, Any]:
        """The synthetic YAML brief for one task. Every semantic word in it came from the model."""
        job = context.job
        plan = context.plan or self._load_plan(job)
        estimated = job.estimated_input_tokens or 0

        if task.task_type is TaskType.PLAN_PARSE:
            return briefs.planning_brief(
                filing=context.filing_brief,
                sizing=part_sizing(context.capability, estimated_input_tokens=estimated),
            )

        if task.task_type is TaskType.FORMAT_REPAIR:
            parent = self._store.load_task(job.parent_run_id, job.job_id, task.parent_task_id or "")
            malformed = self._store.get_task_evidence_text(
                job.parent_run_id, job.job_id, parent.task_id, RESPONSE_EVIDENCE
            )
            return briefs.repair_brief(
                malformed_response=malformed,
                parse_error=str((parent.envelope or {}).get("parse_error") or parent.error or ""),
            )

        if plan is None:
            raise MultipartProtocolError(
                f"{task.task_type.value} needs the model's plan and no readable plan is stored for "
                f"child job {job.job_id}"
            )

        if task.task_type in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}:
            return briefs.part_brief(
                filing=context.filing_brief,
                plan=plan,
                requested=task.part_spec or {},
                parent_part_id=task.parent_part_id,
                sizing=part_sizing(context.capability, estimated_input_tokens=estimated),
            )

        if task.task_type in {TaskType.REPLAN_TRUNCATED_PART, TaskType.PLAN_SUBPARTS}:
            parent = self._store.load_task(job.parent_run_id, job.job_id, task.parent_task_id or "")
            truncated_text = (
                self._store.get_task_evidence_text(
                    job.parent_run_id, job.job_id, parent.task_id, RESPONSE_EVIDENCE
                )
                if self._store.has_task_evidence(
                    job.parent_run_id, job.job_id, parent.task_id, RESPONSE_EVIDENCE
                )
                else ""
            )
            truncation = parent.truncation or {}
            return briefs.replan_brief(
                filing=context.filing_brief,
                plan=plan,
                part_id=parent.part_id,
                part_spec=parent.part_spec or {},
                truncated_response=truncated_text,
                truncated_output_tokens=int(truncation.get("output_tokens") or 0),
                truncated_cap=int(truncation.get("configured_cap") or 0),
                stop_reason=str(truncation.get("stop_reason") or ""),
                sizing=part_sizing(context.capability, estimated_input_tokens=estimated),
            )

        inventory = self._inventory_entries(job)
        cycle = int((task.part_spec or {}).get("cycle") or 1)
        if task.task_type is TaskType.RECONCILE_PARSE:
            return briefs.reconcile_brief(
                filing=context.filing_brief,
                plan=plan,
                inventory=inventory,
                cycle=cycle,
                cycle_limit=self._settings.max_reconciliation_cycles,
                sizing=compact_sizing(
                    context.capability, estimated_input_tokens=estimated, kind="reconcile"
                ),
            )
        return briefs.gap_brief(
            filing=context.filing_brief,
            plan=plan,
            inventory=inventory,
            findings=self._mechanical_findings(context, plan, inventory),
            cycle=cycle,
            sizing=compact_sizing(context.capability, estimated_input_tokens=estimated, kind="gap"),
        )

    def _inventory_entries(self, job: JobRecord) -> list[dict[str, Any]]:
        """A compact, deterministic inventory of every part task, derived by counting."""
        entries: list[dict[str, Any]] = []
        for task in self._store.load_tasks(job.parent_run_id, job.job_id):
            if task.task_type not in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}:
                continue
            envelope = task.envelope or {}
            coverage = (task.validation or {}).get("coverage") or {}
            entries.append(
                {
                    "part_id": task.part_id,
                    "parent_part_id": task.parent_part_id,
                    "order": task.order,
                    "title": envelope.get("title") or (task.part_spec or {}).get("title") or "",
                    "type": envelope.get("type") or (task.part_spec or {}).get("type") or "",
                    "declared_status": envelope.get("declared_status") or "",
                    "task_state": task.state.value,
                    "truncated": task.state is TaskState.TRUNCATED,
                    "node_count": envelope.get("node_count") or 0,
                    "table_count": envelope.get("table_count") or 0,
                    "reference_count": coverage.get("reference_count") or 0,
                    "references_resolved": coverage.get("references_resolved") or 0,
                    "unresolved_count": envelope.get("unresolved_count") or 0,
                    "coverage_summary": envelope.get("coverage_summary") or "",
                }
            )
        return entries

    def _mechanical_findings(
        self, context: _Context, plan: ParsePlan, inventory: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Evidence produced by COUNTING AND SEARCHING. It names nothing semantic, ever.

        Each finding says what was measured and where. None of them says what is missing, because
        nothing that produced them knows what a filing contains — that judgement is what the
        gap-repair call is for.
        """
        findings: list[dict[str, Any]] = []
        produced = {entry["part_id"] for entry in inventory}
        for part in plan.ordered():
            if part.part_id not in produced:
                findings.append(
                    {
                        "finding": "planned_part_has_no_result",
                        "part_id": part.part_id,
                        "evidence": "the plan names this part and no task produced a result for it",
                    }
                )
        for entry in inventory:
            missing = int(entry["reference_count"]) - int(entry["references_resolved"])
            if missing > 0:
                findings.append(
                    {
                        "finding": "source_references_not_located",
                        "part_id": entry["part_id"],
                        "count": missing,
                        "evidence": (
                            "this many quotes supplied by the part were searched for in the "
                            "preserved bytes of the filing and not found"
                        ),
                    }
                )
            if entry["truncated"]:
                findings.append(
                    {
                        "finding": "part_attempt_reached_the_output_limit",
                        "part_id": entry["part_id"],
                        "evidence": "the provider reported the output budget was exhausted",
                    }
                )
            if int(entry["unresolved_count"]) > 0:
                findings.append(
                    {
                        "finding": "part_declared_unresolved_material",
                        "part_id": entry["part_id"],
                        "count": entry["unresolved_count"],
                        "evidence": "the part's own response listed this many unresolved items",
                    }
                )
            if int(entry["node_count"]) == 0 and entry["declared_status"] == "complete":
                findings.append(
                    {
                        "finding": "part_declared_complete_with_no_nodes",
                        "part_id": entry["part_id"],
                        "evidence": "the response declared completion and carried no node list",
                    }
                )
        cited = {
            str(reference.get("filename") or "")
            for task in self._store.load_tasks(context.job.parent_run_id, context.job.job_id)
            for reference in ((task.validation or {}).get("coverage") or {}).get("references", [])
            if reference.get("resolution") not in {"UNRESOLVED", "NO_SUCH_ARTIFACT", "EMPTY_QUOTE"}
        }
        for name in context.artifact_texts:
            if name not in cited:
                findings.append(
                    {
                        "finding": "submitted_artifact_carries_no_located_reference",
                        "artifact": name,
                        "evidence": (
                            "this artifact was submitted and no part supplied a quote from it that "
                            "could be located"
                        ),
                    }
                )
        identifiers = [entry["part_id"] for entry in inventory]
        for identifier in sorted({i for i in identifiers if identifiers.count(i) > 1}):
            findings.append(
                {
                    "finding": "duplicate_part_identifier",
                    "part_id": identifier,
                    "evidence": "more than one task produced a result under this identifier",
                }
            )
        return findings

    # --- finishing --------------------------------------------------------------------------------

    def _session_summary(
        self, job: JobRecord, *, plan: ParsePlan | None, tasks: list[MultipartTask]
    ) -> dict[str, Any]:
        remaining = self._journal.remaining_for_job(job.job_id, budget_usd=job.budget_ceiling_usd)
        return {
            "schema_version": "multipart-session-v1",
            "protocol": "model-directed multipart",
            "parse_plan_id": plan.plan_id if plan else "",
            "planned_part_count": len(plan.parts) if plan else 0,
            "recursion_depth_limit": self._settings.max_depth,
            "reconciliation_cycle_limit": self._settings.max_reconciliation_cycles,
            "format_repair_limit_per_artifact": self._settings.max_format_repairs_per_artifact,
            "filing_budget_usd": (
                None if job.budget_ceiling_usd is None else str(job.budget_ceiling_usd)
            ),
            "filing_spent_usd": str(self._journal.spent_for_job(job.job_id)),
            "filing_remaining_usd": str(remaining),
            "phase": self._journal.phase,
            "phase_ceiling_usd": (
                None
                if self._journal.phase_ceiling_usd is None
                else str(self._journal.phase_ceiling_usd)
            ),
            "phase_spent_usd": str(self._journal.phase_spent_usd),
            **summarise_tasks(tasks),
        }

    def _part_of(self, task: MultipartTask) -> Any:
        """The part artifact a SUCCEEDED task returned, re-read from its preserved bytes, or None.

        A TRUNCATED task returns None even though its partial text may parse. That is the rule the
        whole protocol turns on: a truncated attempt is evidence, and its content never becomes
        part of the assembled parse.
        """
        if task.state is not TaskState.SUCCEEDED:
            return None
        if not self._store.has_task_evidence(
            task.run_id, task.root_job_id, task.task_id, RESPONSE_EVIDENCE
        ):
            return None
        try:
            return read_part(
                self._store.get_task_evidence_text(
                    task.run_id, task.root_job_id, task.task_id, RESPONSE_EVIDENCE
                )
            )
        except EnvelopeUnreadableError:
            return None

    def _nodes_of(self, task: MultipartTask) -> tuple[dict[str, Any], ...]:
        part = self._part_of(task)
        return part.nodes if part is not None else ()

    def _unresolved_of(self, task: MultipartTask) -> tuple[dict[str, Any], ...]:
        part = self._part_of(task)
        return part.unresolved if part is not None else ()

    @staticmethod
    def _repairs_by_original(tasks: list[MultipartTask]) -> dict[str, MultipartTask]:
        """Map a part task to the successful format repair that carries its content, if any.

        A REPAIR IS ONLY SUBSTITUTED WHEN IT ACTUALLY PRODUCED A PART. Two ways it may not have.
        A repair whose own response would not parse is recorded with `readable: False` and is no
        improvement on the original; substituting it would swap one unreadable artifact for
        another and lose the first one's place in the index. A repair of something that is not a
        part carries a bookkeeping envelope with no `node_count` at all. Requiring the key that
        `_interpret_part` writes admits only the case that means anything here. Measured on a real
        run: 8 repairs were attempted and exactly ONE returned a readable part envelope.

        CHAINS ARE STILL FOLLOWED, BECAUSE PRESERVED RUNS CONTAIN THEM. `_on_unreadable` now
        refuses to repair a repair, so no new chain can start — but a run recorded before that
        must still resolve to the artifact holding its content rather than to the middle of a
        chain, and the walk costs nothing.
        """
        by_id = {t.task_id: t for t in tasks}
        repairs = [t for t in tasks if t.task_type is TaskType.FORMAT_REPAIR]
        resolved: dict[str, MultipartTask] = {}
        for repair in repairs:
            if repair.state is not TaskState.SUCCEEDED:
                continue
            envelope = repair.envelope or {}
            if envelope.get("readable") is False or "node_count" not in envelope:
                continue
            # Walk back to the PART task this repair ultimately descends from.
            origin = by_id.get(repair.parent_task_id or "")
            seen = {repair.task_id}
            while origin is not None and origin.task_type is TaskType.FORMAT_REPAIR:
                if origin.task_id in seen:  # a cycle cannot happen; refusing to loop is free
                    origin = None
                    break
                seen.add(origin.task_id)
                origin = by_id.get(origin.parent_task_id or "")
            if origin is None or origin.task_type not in {
                TaskType.PARSE_PART,
                TaskType.PARSE_SUBPART,
            }:
                continue
            existing = resolved.get(origin.task_id)
            if existing is None or repair.order >= existing.order:
                resolved[origin.task_id] = repair
        return resolved

    def _finish(self, run_id: str, job_id: str) -> JobRecord:
        """Assemble mechanically, validate the index, and stop at READY_FOR_REVIEW."""
        job = self._store.load_job(run_id, job_id)
        tasks = self._store.load_tasks(run_id, job_id)
        plan = self._load_plan(job)
        context = self._context(job)

        repairs = self._repairs_by_original(tasks)
        parts: list[AssembledPart] = []
        for task in tasks:
            if task.task_type not in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}:
                continue
            # THE ROW CARRIES THE ARTIFACT THAT ACTUALLY HOLDS THE CONTENT. A part whose response
            # would not parse, and whose format repair then succeeded, has TWO preserved artifacts:
            # the malformed original and the readable repair. The original is never replaced or
            # rewritten — but indexing it and ignoring the repair reported a FALSE EMPTY, which is
            # the inverse of the failure mode this project guards against and just as untrue.
            # Measured: part_024 of a real run held 2 nodes in its repair and read `node_count: 0`.
            #
            # ONE ROW PER PART, NOT TWO. A duplicate part_id is a defect `validate_assembly`
            # reports, and the repair carries the same model-created identifier by construction.
            # Both task ids stay on the row so a reviewer can open either artifact.
            source = repairs.get(task.task_id, task)
            repaired_from = task.task_id if source is not task else None
            envelope = source.envelope or {}
            coverage = (source.validation or {}).get("coverage") or {}
            last = source.attempts[-1].to_mapping() if source.attempts else {}
            parts.append(
                AssembledPart(
                    part_id=task.part_id,
                    storage_token=task.storage_token,
                    task_id=source.task_id,
                    repaired_from_task_id=repaired_from,
                    parent_part_id=task.parent_part_id,
                    order=task.order,
                    title=str(envelope.get("title") or (task.part_spec or {}).get("title") or ""),
                    type_label=str(
                        envelope.get("type") or (task.part_spec or {}).get("type") or ""
                    ),
                    declared_status=str(envelope.get("declared_status") or ""),
                    task_state=source.state.value,
                    terminal=source.state is TaskState.SUCCEEDED,
                    # TRUNCATION IS READ FROM THE ORIGINAL, NOT THE REPAIR. A repair is never
                    # queued for a truncated response — a truncated attempt is preserved and
                    # replanned, never repaired or continued — so the two can never disagree here.
                    # Reading the original keeps that true even if the repair path ever widens.
                    truncated=task.state is TaskState.TRUNCATED,
                    node_count=int(envelope.get("node_count") or 0),
                    table_count=int(envelope.get("table_count") or 0),
                    unresolved_count=int(envelope.get("unresolved_count") or 0),
                    reference_count=int(coverage.get("reference_count") or 0),
                    references_resolved=int(coverage.get("references_resolved") or 0),
                    reference_filenames=tuple(
                        sorted(
                            {
                                str(r.get("filename") or "")
                                for r in coverage.get("references", [])
                                if r.get("filename")
                            }
                        )
                    ),
                    image_reference_count=int(envelope.get("image_reference_count") or 0),
                    input_tokens=int(last.get("input_tokens") or 0),
                    output_tokens=int(last.get("output_tokens") or 0),
                    latency_ms=int(last.get("latency_ms") or 0),
                    # BOTH CALLS WERE PAID FOR. A repaired part cost the malformed response AND
                    # the repair, and a row showing only one of them would understate what the
                    # part actually cost. The job total is unaffected either way: it sums tasks.
                    actual_cost_usd=(task.actual_cost_usd or Decimal(0))
                    + (source.actual_cost_usd or Decimal(0) if source is not task else Decimal(0)),
                    stop_reason=str(last.get("stop_reason") or ""),
                    prompt_identity=f"{source.prompt.prompt_id}@{source.prompt.version}",
                    # READ BACK FROM THE PRESERVED RESPONSE, NOT FROM A CACHED COPY. The envelope
                    # record is the compact scheduling view and deliberately carries counts rather
                    # than content; the nodes in the index have to be the model's own mapping,
                    # sourced from the bytes it returned, or the assembled view would be showing a
                    # second-hand rendering of the thing it claims to index.
                    nodes=self._nodes_of(source),
                    unresolved=self._unresolved_of(source),
                    coverage_summary=str(envelope.get("coverage_summary") or ""),
                )
            )

        reconciliations = [
            t.envelope or {}
            for t in tasks
            if t.task_type is TaskType.RECONCILE_PARSE and t.envelope
        ]
        declared_complete = bool(reconciliations) and bool(
            reconciliations[-1].get("model_declared_plan_complete")
        )
        # One entry per DISTINCT prompt version this parse used, in first-use order. A multipart
        # parse invokes four or five immutable families, and the assembly has to name every one:
        # "which prompt produced this" is a per-task question, and "which prompts produced this
        # parse" is a per-filing one.
        prompt_versions = list(
            {
                f"{t.prompt.prompt_id}@{t.prompt.version}": {
                    "prompt_id": t.prompt.prompt_id,
                    "version": t.prompt.version,
                    "sha256": t.prompt.sha256,
                }
                for t in tasks
            }.values()
        )
        assembly = assemble(
            AssemblyInputs(
                filing={
                    "cik": job.cik,
                    "accession": job.accession,
                    "form_as_filed": job.form_as_filed,
                    "filing_date": job.filing_date,
                    "issuer_label": job.issuer_label,
                    "transport_era": job.transport_era,
                },
                source_set={
                    "source_set_id": job.source_set_id or "",
                    "submitted_member_count": len(context.source_set.submitted_members),
                    "submitted_bytes": context.source_set.submitted_bytes,
                },
                routing=job.routing.to_mapping(),
                prompts=prompt_versions,
                plan=plan.to_mapping() if plan else {},
                parts=parts,
                tasks=[
                    {
                        "task_id": t.task_id,
                        "task_type": t.task_type.value,
                        "state": t.state.value,
                        "part_id": t.part_id,
                        "depth": t.depth,
                        "attempts": t.attempt_count,
                        "input_tokens": sum(a.input_tokens for a in t.attempts),
                        "output_tokens": sum(a.output_tokens for a in t.attempts),
                        "latency_ms": sum(a.latency_ms for a in t.attempts),
                        "actual_cost_usd": str(t.actual_cost_usd or Decimal(0)),
                        "reserved_cost_usd": str(t.reserved_cost_usd or Decimal(0)),
                        "surfaced": True,
                        "error": t.error,
                        "blocked_reason": t.blocked_reason,
                    }
                    for t in tasks
                ],
                reconciliations=reconciliations,
                gap_repairs=[t.envelope or {} for t in tasks if t.task_type is TaskType.GAP_REPAIR],
                replans=[
                    t.envelope or {}
                    for t in tasks
                    if t.task_type in {TaskType.REPLAN_TRUNCATED_PART, TaskType.PLAN_SUBPARTS}
                ],
                image_coverage=job.image_coverage or {},
                reconciliation_cycles=len(reconciliations),
                reconciliation_cycle_limit=self._settings.max_reconciliation_cycles,
                recursion_depth_limit=self._settings.max_depth,
                # THE PLAN'S OWN COUNT, NOT THE NUMBER OF TASKS THAT HAPPENED TO EXIST. Taking the
                # task count made "expected" mean "produced", so a parse that never got past the
                # planning call expected nothing and satisfied it. Reconciliation may add parts
                # beyond the plan, so the larger of the two is what a terminal count is measured
                # against.
                parts_expected=max(len(parts), len(plan.parts) if plan else 0),
                model_declared_complete=declared_complete,
                plan_available=plan is not None,
                budget_ceiling_usd=job.budget_ceiling_usd,
            )
        )
        validation = validate_assembly(assembly, source_filenames=set(context.artifact_texts))
        assembly["validation"] = validation.to_mapping()
        self._store.save_assembly(run_id, job_id, assembly)

        job.multipart = self._session_summary(job, plan=plan, tasks=tasks)
        job.multipart["assembly_status"] = assembly["status"]
        job.multipart["assembly_consistent"] = validation.consistent
        job.validation = {
            "schema_version": "multipart-job-validation-v1",
            "assembly": validation.to_mapping(),
            "note": (
                "the multipart index, checked against itself and the submitted source set. Each "
                "part's own coverage validation against the preserved bytes is on its task."
            ),
        }
        job.actual_cost_usd = sum((t.actual_cost_usd or Decimal(0) for t in tasks), Decimal(0))
        job.reserved_cost_usd = sum((t.reserved_cost_usd or Decimal(0) for t in tasks), Decimal(0))
        self._store.save_job(job)

        if job.execution_state is ExecutionState.QUEUED:
            self._store.set_execution_state(job, ExecutionState.RUNNING)
        if job.execution_state is ExecutionState.RUNNING:
            self._store.set_execution_state(
                job, ExecutionState.RESPONSE_RECEIVED, message=assembly["status"]
            )
        if job.execution_state is ExecutionState.RESPONSE_RECEIVED:
            self._store.set_execution_state(job, ExecutionState.VALIDATING)
        if job.execution_state is ExecutionState.VALIDATING:
            self._store.set_execution_state(
                job,
                ExecutionState.READY_FOR_REVIEW,
                message=(
                    f"{assembly['status']}: {assembly['part_count']} part(s), "
                    f"{assembly['references_resolved']}/{assembly['reference_count']} references "
                    f"resolved, USD {assembly['total_cost_usd']}"
                ),
            )
        return self._store.load_job(run_id, job_id)
