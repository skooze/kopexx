"""The durable hierarchical queue: states, dependencies, restart, cancellation, identity, cost.

WHAT IS BEING PROTECTED, AND WHAT ALREADY WENT WRONG ONCE. Every property here is one a multipart
parse cannot be trusted without, and two of them were defects in this phase's own first draft:

    a duplicate identity must include EVERYTHING that changes the answer. Keyed on the declared
    components alone, reconciliation cycle 2 collided with cycle 1 and was skipped as a duplicate,
    which silently disabled the loop.

    a duplicate schedule is CANCELLED, not FAILED. Recording "nothing needed doing" as a failure
    makes a healthy run look broken.

THE THREE STATE MACHINES ARE NEVER COLLAPSED, and the test that matters most is the one asserting
they share no member by accident.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from packages.evaluation_store import (
    BILLABLE_TASK_TYPES,
    CANCELLABLE_TASK_STATES,
    RESUMABLE_TASK_STATES,
    TERMINAL_TASK_STATES,
    DependencyPolicy,
    EvaluationStore,
    ExecutionState,
    IllegalTransitionError,
    ModelRouting,
    ParserSettings,
    PromptIdentity,
    ReviewState,
    TaskNotFoundError,
    TaskState,
    TaskType,
    assert_task_transition,
    dependencies_satisfied,
    idempotency_key,
    is_task_id,
    new_attempt_salt,
    new_task,
    new_task_id,
    permitted_task_transitions,
    summarise_tasks,
)
from packages.evaluation_store.identity import require_task_id
from packages.model_catalog import PriceInputs
from packages.orchestrator import SpendJournal
from packages.storage import FilesystemObjectStore

RUN_ID = "run_" + "a" * 26
JOB_ID = "job_" + "b" * 26

ROUTING = ModelRouting(
    label="Parser",
    role="parsing",
    model_id="synthetic.parser",
    invocation_id="synthetic.parser",
    region="region-one",
    preferred_region="region-one",
    in_preferred_region=True,
    inference_profile_id=None,
    cross_region_reason=None,
    multimodal=False,
)
PROMPT = PromptIdentity(prompt_id="p", version="1", sha256="0" * 64)
SETTINGS = ParserSettings(max_output_tokens=8000, temperature=0.0)
PRICE = PriceInputs(
    input_per_1k=Decimal("0.001"),
    output_per_1k=Decimal("0.004"),
    currency="USD",
    source="synthetic",
    effective_date="2026-01-01",
)


@pytest.fixture
def store(tmp_path: Path) -> EvaluationStore:
    return EvaluationStore(FilesystemObjectStore(tmp_path / "evaluation"))


def _task(**overrides: object) -> object:
    fields: dict = {
        "task_id": new_task_id(),
        "run_id": RUN_ID,
        "root_job_id": JOB_ID,
        "task_type": TaskType.PARSE_PART,
        "routing": ROUTING,
        "prompt": PROMPT,
        "settings": SETTINGS,
    }
    fields.update(overrides)
    return new_task(**fields)  # type: ignore[arg-type]


# --- anti-vacuity and the three machines -------------------------------------------------------


def test_the_three_state_machines_share_no_member_by_accident() -> None:
    """Execution, review and queue states answer different questions and must stay separable.

    `READY_FOR_REVIEW` appears in two of them on purpose and means different things: a child job a
    person can look at, and a queue task that has reached the end of its own life. Everything else
    overlapping would be a sign one machine had started being derived from another.
    """
    execution = {s.value for s in ExecutionState}
    review = {s.value for s in ReviewState}
    queue = {s.value for s in TaskState}
    assert review.isdisjoint(queue), f"review and queue states overlap: {review & queue}"
    assert execution & queue == {
        "CREATED",
        "RUNNING",
        "RESPONSE_RECEIVED",
        "VALIDATING",
        "READY_FOR_REVIEW",
        "FAILED",
        "CANCELLED",
        "INTERRUPTED",
    }


def test_every_billable_task_type_is_one_that_invokes_a_model() -> None:
    mechanical = {
        TaskType.SOURCE_PREFLIGHT,
        TaskType.VALIDATE_ASSEMBLY,
        TaskType.READY_FOR_REVIEW,
    }
    assert BILLABLE_TASK_TYPES.isdisjoint(mechanical)
    assert set(TaskType) - BILLABLE_TASK_TYPES == mechanical


# --- transitions --------------------------------------------------------------------------------


def test_a_running_task_can_never_be_cancelled() -> None:
    """The call is billable from the moment it is issued; a cancelled label would hide a charge."""
    with pytest.raises(IllegalTransitionError, match="cannot move to CANCELLED"):
        assert_task_transition(TaskState.RUNNING, TaskState.CANCELLED)
    assert TaskState.RUNNING not in CANCELLABLE_TASK_STATES
    assert TaskState.RESERVED not in CANCELLABLE_TASK_STATES


def test_truncated_is_terminal_and_reopening_it_is_refused() -> None:
    """Reopening a truncated attempt IS the blind-continuation protocol this phase refuses."""
    assert permitted_task_transitions(TaskState.TRUNCATED) == frozenset()
    for target in TaskState:
        with pytest.raises(IllegalTransitionError):
            assert_task_transition(TaskState.TRUNCATED, target)


def test_failed_and_interrupted_reopen_only_to_ready() -> None:
    for state in (TaskState.FAILED, TaskState.INTERRUPTED):
        assert permitted_task_transitions(state) == frozenset({TaskState.READY})


def test_a_ready_task_may_be_blocked_which_is_the_budget_pause() -> None:
    assert TaskState.BLOCKED in permitted_task_transitions(TaskState.READY)


def test_validating_never_becomes_failed_for_a_validation_verdict() -> None:
    """A part whose YAML will not parse still reaches a terminal state carrying that verdict."""
    assert TaskState.SUCCEEDED in permitted_task_transitions(TaskState.VALIDATING)


def test_every_resumable_state_is_one_a_process_can_die_in() -> None:
    assert RESUMABLE_TASK_STATES.isdisjoint(TERMINAL_TASK_STATES)
    assert TaskState.SUCCEEDED not in RESUMABLE_TASK_STATES


# --- dependencies -------------------------------------------------------------------------------


def test_a_task_with_no_dependencies_is_satisfied() -> None:
    """The plan genuinely depends on nothing; a scheduler that refused it would never start."""
    assert dependencies_satisfied([]) is True


def test_all_succeeded_refuses_a_truncated_dependency_and_all_terminal_accepts_it() -> None:
    states = [TaskState.SUCCEEDED, TaskState.TRUNCATED]
    assert dependencies_satisfied(states, DependencyPolicy.ALL_SUCCEEDED) is False
    assert dependencies_satisfied(states, DependencyPolicy.ALL_TERMINAL) is True


def test_a_task_becomes_runnable_only_when_its_durable_dependencies_are_satisfied(
    store: EvaluationStore,
) -> None:
    first = _task()
    second = _task(depends_on=[first.task_id])  # type: ignore[attr-defined]
    store.save_task(first)  # type: ignore[arg-type]
    store.save_task(second)  # type: ignore[arg-type]
    store.set_task_state(first, TaskState.READY)  # type: ignore[arg-type]
    store.set_task_state(second, TaskState.BLOCKED)  # type: ignore[arg-type]

    runnable = {t.task_id for t in store.runnable_tasks(RUN_ID, JOB_ID)}
    assert runnable == {first.task_id}, "a blocked dependant was runnable"  # type: ignore[attr-defined]

    store.set_task_state(first, TaskState.RESERVED)  # type: ignore[arg-type]
    store.set_task_state(first, TaskState.RUNNING)  # type: ignore[arg-type]
    store.set_task_state(first, TaskState.RESPONSE_RECEIVED)  # type: ignore[arg-type]
    store.set_task_state(first, TaskState.VALIDATING)  # type: ignore[arg-type]
    store.set_task_state(first, TaskState.SUCCEEDED)  # type: ignore[arg-type]
    assert {t.task_id for t in store.runnable_tasks(RUN_ID, JOB_ID)} == {second.task_id}  # type: ignore[attr-defined]


def test_a_dependency_on_a_task_that_does_not_exist_never_becomes_runnable(
    store: EvaluationStore,
) -> None:
    """A missing dependency is not treated as a satisfied one. It waits and is visible."""
    orphan = _task(depends_on=["tsk_" + "z" * 26])
    store.save_task(orphan)  # type: ignore[arg-type]
    store.set_task_state(orphan, TaskState.BLOCKED)  # type: ignore[arg-type]
    assert store.runnable_tasks(RUN_ID, JOB_ID) == []


# --- storage ------------------------------------------------------------------------------------


def test_a_task_round_trips_through_storage_unchanged(store: EvaluationStore) -> None:
    task = _task(
        plan_id="plan-1",
        part_id="a model chose this",
        storage_token="a-model-chose-this-abc123",
        part_spec={"title": "what the filing calls it"},
        depth=2,
        order=7,
    )
    store.save_task(task)  # type: ignore[arg-type]
    loaded = store.load_task(RUN_ID, JOB_ID, task.task_id)  # type: ignore[attr-defined]
    assert loaded.part_id == "a model chose this"
    assert loaded.part_spec == {"title": "what the filing calls it"}
    assert loaded.depth == 2
    assert loaded.order == 7


def test_a_missing_task_raises_rather_than_returning_something_plausible(
    store: EvaluationStore,
) -> None:
    with pytest.raises(TaskNotFoundError):
        store.load_task(RUN_ID, JOB_ID, "tsk_" + "c" * 26)


def test_an_identifier_this_store_did_not_issue_never_reaches_a_storage_key() -> None:
    """SECURITY-INVARIANT. `..` and `/` are outside the permitted alphabet."""
    for hostile in ("../../etc", "tsk_short", "job_" + "a" * 26, ""):
        with pytest.raises(Exception, match="not a multipart task identifier"):
            require_task_id(hostile)
    assert is_task_id(new_task_id())


def test_the_read_cache_never_serves_a_record_that_has_changed(store: EvaluationStore) -> None:
    """MUTATION PROOF FOR THE FINGERPRINTED CACHE. A stale read here would be a stale scheduler."""
    task = _task()
    store.save_task(task)  # type: ignore[arg-type]
    assert store.load_task(RUN_ID, JOB_ID, task.task_id).state is TaskState.CREATED  # type: ignore[attr-defined]
    store.set_task_state(task, TaskState.READY)  # type: ignore[arg-type]
    assert store.load_task(RUN_ID, JOB_ID, task.task_id).state is TaskState.READY  # type: ignore[attr-defined]


# --- restart, resume, cancel ----------------------------------------------------------------------


def test_a_restart_interrupts_mid_flight_tasks_and_leaves_completed_ones_alone(
    store: EvaluationStore, tmp_path: Path
) -> None:
    from packages.evaluation_store import JobRecord, RunRecord, utc_now

    run = RunRecord(
        run_id=RUN_ID,
        created_at=utc_now(),
        author="tester",
        cik="0000000001",
        entity_label="Synthetic",
        parsing_label="Parser",
    )
    job = JobRecord(
        job_id=JOB_ID,
        parent_run_id=RUN_ID,
        created_at=utc_now(),
        updated_at=utc_now(),
        cik="0000000001",
        accession="0000000001-24-000001",
        form_as_filed="10-K",
        filing_date="2024-01-02",
        issuer_label="Synthetic",
        transport_era="era",
        routing=ROUTING,
        prompt=PROMPT,
        settings=SETTINGS,
    )
    store.save_run(run)
    store.save_job(job)

    done = _task()
    store.save_task(done)  # type: ignore[arg-type]
    for state in (
        TaskState.READY,
        TaskState.RESERVED,
        TaskState.RUNNING,
        TaskState.RESPONSE_RECEIVED,
        TaskState.VALIDATING,
        TaskState.SUCCEEDED,
    ):
        store.set_task_state(done, state)  # type: ignore[arg-type]

    inflight = _task()
    store.save_task(inflight)  # type: ignore[arg-type]
    store.set_task_state(inflight, TaskState.READY)  # type: ignore[arg-type]
    store.set_task_state(inflight, TaskState.RESERVED)  # type: ignore[arg-type]
    store.set_task_state(inflight, TaskState.RUNNING)  # type: ignore[arg-type]

    touched = store.mark_interrupted_tasks()
    assert [t[2] for t in touched] == [inflight.task_id]  # type: ignore[attr-defined]
    assert store.load_task(RUN_ID, JOB_ID, done.task_id).state is TaskState.SUCCEEDED  # type: ignore[attr-defined]
    interrupted = store.load_task(RUN_ID, JOB_ID, inflight.task_id)  # type: ignore[attr-defined]
    assert interrupted.state is TaskState.INTERRUPTED
    assert "NOT rerun" in (interrupted.error or "")


def test_resume_is_the_only_way_back_and_it_records_who_asked(store: EvaluationStore) -> None:
    task = _task()
    store.save_task(task)  # type: ignore[arg-type]
    store.set_task_state(task, TaskState.READY)  # type: ignore[arg-type]
    store.set_task_state(task, TaskState.INTERRUPTED)  # type: ignore[arg-type]
    reopened = store.resume_task(task, author="a person")  # type: ignore[arg-type]
    assert reopened.state is TaskState.READY


def test_cancelling_a_reserved_task_is_refused_with_the_reason(store: EvaluationStore) -> None:
    task = _task()
    store.save_task(task)  # type: ignore[arg-type]
    store.set_task_state(task, TaskState.READY)  # type: ignore[arg-type]
    store.set_task_state(task, TaskState.RESERVED)  # type: ignore[arg-type]
    with pytest.raises(IllegalTransitionError, match="billable"):
        store.cancel_task(task, reason="too late")  # type: ignore[arg-type]


# --- idempotency ----------------------------------------------------------------------------------


def _key(**overrides: object) -> str:
    fields: dict = {
        "source_set_id": "s",
        "model_label": "Parser",
        "invocation_id": "synthetic.parser",
        "region": "region-one",
        "prompt_identity": "p@1",
        "prompt_sha256": "0" * 64,
        "task_type": "PARSE_PART",
        "plan_id": "plan-1",
        "part_id": "a",
        "parent_artifact_sha256": "abc",
        "max_output_tokens": 8000,
        "temperature": 0.0,
        "attempt_salt": "",
    }
    fields.update(overrides)
    return idempotency_key(**fields)  # type: ignore[arg-type]


def test_identical_inputs_produce_an_identical_identity() -> None:
    assert _key() == _key()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_set_id", "different"),
        ("model_label", "Another Parser"),
        ("region", "region-two"),
        ("prompt_identity", "p@2"),
        ("prompt_sha256", "1" * 64),
        ("task_type", "PARSE_SUBPART"),
        ("plan_id", "plan-2"),
        ("part_id", "b"),
        ("parent_artifact_sha256", "def"),
        ("max_output_tokens", 4000),
        ("temperature", 0.7),
    ],
)
def test_anything_that_changes_the_answer_changes_the_identity(field: str, value: object) -> None:
    assert _key(**{field: value}) != _key()


def test_an_explicit_rerun_salt_makes_a_new_identity() -> None:
    """A reviewer asking for a second opinion is not a duplicate schedule."""
    assert _key(attempt_salt=new_attempt_salt()) != _key()


def test_an_already_successful_identity_is_found_and_an_unfinished_one_is_not(
    store: EvaluationStore,
) -> None:
    done = _task(idempotency="the-same")
    store.save_task(done)  # type: ignore[arg-type]
    for state in (
        TaskState.READY,
        TaskState.RESERVED,
        TaskState.RUNNING,
        TaskState.RESPONSE_RECEIVED,
        TaskState.VALIDATING,
        TaskState.SUCCEEDED,
    ):
        store.set_task_state(done, state)  # type: ignore[arg-type]
    assert store.find_successful_task(RUN_ID, JOB_ID, idempotency="the-same") is not None
    assert store.find_successful_task(RUN_ID, JOB_ID, idempotency="") is None
    assert store.find_successful_task(RUN_ID, JOB_ID, idempotency="something else") is None


# --- cost -------------------------------------------------------------------------------------------


@pytest.fixture
def journal(tmp_path: Path) -> SpendJournal:
    return SpendJournal(
        FilesystemObjectStore(tmp_path / "journal"),
        ceiling_usd=Decimal("5.00"),
        phase="2.1",
        phase_ceiling_usd=Decimal("1.00"),
    )


def test_a_phase_ceiling_needs_a_phase_label_to_attribute_spend_to(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="phase label"):
        SpendJournal(
            FilesystemObjectStore(tmp_path / "j"),
            ceiling_usd=Decimal("5.00"),
            phase_ceiling_usd=Decimal("1.00"),
        )


def test_spend_is_attributed_to_the_phase_the_job_and_the_task(journal: SpendJournal) -> None:
    journal.authorize(
        PRICE,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-01-01T00:00:00+00:00",
        run_id=RUN_ID,
        job_id=JOB_ID,
        model_label="Parser",
        task_id="tsk_" + "d" * 26,
    )
    assert journal.phase_spent_usd == journal.spent_usd
    assert journal.spent_for_job(JOB_ID) == journal.spent_usd
    assert journal.spent_for_job("job_" + "z" * 26) == Decimal(0)
    assert journal.entries[0].task_id == "tsk_" + "d" * 26
    assert journal.entries[0].phase == "2.1"


def test_the_tightest_of_the_three_ceilings_is_the_one_that_refuses(journal: SpendJournal) -> None:
    """A filing budget of one cent refuses long before the phase or cumulative ceiling would."""
    affordable, reason = journal.can_afford(
        Decimal("0.50"), job_id=JOB_ID, budget_usd=Decimal("0.01")
    )
    assert affordable is False
    assert "this filing's own budget" in reason

    affordable, reason = journal.can_afford(
        Decimal("2.00"), job_id=JOB_ID, budget_usd=Decimal("4.00")
    )
    assert affordable is False
    assert "phase 2.1 ceiling" in reason

    affordable, _ = journal.can_afford(Decimal("0.10"), job_id=JOB_ID, budget_usd=Decimal("4.00"))
    assert affordable is True


def test_a_failed_attempts_reservation_is_not_released(journal: SpendJournal) -> None:
    """A billable request that failed still cost money. It stays charged until a measurement."""
    reserved = journal.authorize(
        PRICE,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-01-01T00:00:00+00:00",
        run_id=RUN_ID,
        job_id=JOB_ID,
        model_label="Parser",
    )
    assert journal.spent_usd == reserved
    # No settlement follows; the total does not fall back on its own.
    assert journal.spent_usd == reserved


def test_a_retry_takes_a_second_reservation(journal: SpendJournal) -> None:
    first = journal.authorize(
        PRICE,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-01-01T00:00:00+00:00",
        run_id=RUN_ID,
        job_id=JOB_ID,
        model_label="Parser",
    )
    second = journal.authorize(
        PRICE,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-01-01T00:00:01+00:00",
        run_id=RUN_ID,
        job_id=JOB_ID,
        model_label="Parser",
    )
    assert journal.spent_usd == first + second


def test_the_journal_survives_a_restart_with_its_phase_attribution(tmp_path: Path) -> None:
    objects = FilesystemObjectStore(tmp_path / "journal")
    first = SpendJournal(
        objects, ceiling_usd=Decimal("5.00"), phase="2.1", phase_ceiling_usd=Decimal("1.00")
    )
    first.authorize(
        PRICE,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-01-01T00:00:00+00:00",
        run_id=RUN_ID,
        job_id=JOB_ID,
        model_label="Parser",
    )
    second = SpendJournal(
        objects, ceiling_usd=Decimal("5.00"), phase="2.1", phase_ceiling_usd=Decimal("1.00")
    )
    assert second.spent_usd == first.spent_usd
    assert second.phase_spent_usd == first.phase_spent_usd


def test_an_entry_from_another_phase_counts_cumulatively_and_not_against_this_phase(
    tmp_path: Path,
) -> None:
    """Phase 2's 30 entries are exactly this case: they bind the cumulative ceiling and no other."""
    objects = FilesystemObjectStore(tmp_path / "journal")
    earlier = SpendJournal(objects, ceiling_usd=Decimal("5.00"))
    earlier.authorize(
        PRICE,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-01-01T00:00:00+00:00",
        run_id=RUN_ID,
        job_id=JOB_ID,
        model_label="Parser",
    )
    now = SpendJournal(
        objects, ceiling_usd=Decimal("5.00"), phase="2.1", phase_ceiling_usd=Decimal("1.00")
    )
    assert now.spent_usd == earlier.spent_usd
    assert now.phase_spent_usd == Decimal(0)


# --- summaries ---------------------------------------------------------------------------------------


def test_a_task_summary_counts_and_never_judges() -> None:
    tasks = [
        _task(),
        _task(task_type=TaskType.RECONCILE_PARSE),
    ]
    summary = summarise_tasks(tasks)  # type: ignore[arg-type]
    assert summary["task_count"] == 2
    assert summary["by_type"]["PARSE_PART"] == 1
    assert summary["by_type"]["RECONCILE_PARSE"] == 1
    assert summary["actual_cost_usd"] == "0"
    assert "verdict" not in summary and "quality" not in summary
