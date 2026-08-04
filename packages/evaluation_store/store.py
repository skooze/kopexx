"""Durable evaluation storage: what a review session needs to survive a page reload.

WHAT THIS IS NOT. It is not the product database, and building it is not permission to design
one. roadmap.md Phase 4 designs persistence FROM measured model artifacts; this store exists so
that measuring them is possible at all. It holds no schema, no relational model, no index, no
query language and no notion of what a filing contains — a run directory, a job directory, some
exact bytes and two small manifests.

WHY EVERY WRITE GOES THROUGH packages/storage. rules.md section 5 makes that package the single
home for byte-exact preservation. Its `put_bytes` writes to a temporary path, flushes, fsyncs and
renames, and refuses a key that escapes the store root. A store that opened files itself would
reimplement all three and would eventually get one of them wrong.

WHY ONE OBJECT PER EVENT. An append to a shared log is not atomic across a crash, and a torn last
line is indistinguishable from an event that never happened. One immutable object per event makes
every write atomic, makes `Last-Event-ID` resumption a matter of listing keys, and removes the
reader/writer race entirely. Runs carry tens of events, not millions.

RESTART BEHAVIOUR IS EXPLICIT AND COSTS NOTHING. `mark_interrupted_jobs` moves every job that was
mid-flight into INTERRUPTED and stops. It never re-invokes anything. A process that came back up
is not a user who asked to spend money again.
"""

from __future__ import annotations

import re
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

from packages.llm_gateway import parse_yaml, require_mapping, to_yaml
from packages.sec_identity import accession_dashed, cik_padded
from packages.storage import FilesystemObjectStore, ObjectStore

from .errors import (
    BenchmarkTruthVersionExistsError,
    IllegalTransitionError,
    JobNotFoundError,
    RunNotFoundError,
    TaskNotFoundError,
)
from .identity import (
    require_comment_id,
    require_job_id,
    require_run_id,
    require_task_id,
)
from .queue_states import (
    CANCELLABLE_TASK_STATES,
    RESUMABLE_TASK_STATES,
    DependencyPolicy,
    TaskState,
    assert_task_transition,
    dependencies_satisfied,
)
from .records import (
    Comment,
    JobRecord,
    ReviewTransition,
    RunEvent,
    RunRecord,
    utc_now,
)
from .states import (
    RESUMABLE_EXECUTION_STATES,
    ExecutionState,
    ReviewState,
    assert_execution_transition,
    assert_review_transition,
)
from .tasks import MultipartTask

#: Evidence file names are written by this repository, never by a request. The pattern is still
#: enforced: an evidence name reaches a storage key, and a guard that only exists because "no
#: caller would do that" is a guard that stops holding the first time a caller does.
_EVIDENCE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

_RUNS = "runs"

#: Human benchmark-truth documents, keyed by FILING rather than by run.
#:
#: WHY NOT UNDER A RUN. A reviewer's classification of Apple's inventory is evidence about ONE
#: FILING at one source hash. It outlives every run against it, it is what a second run is measured
#: against, and filing it under the first run that happened to exist would make the denominator of
#: a benchmark depend on which run was created first.
_BENCHMARKS = "benchmarks"

#: `truth-0007.yaml`. Four digits is a display width, not a limit: the pattern accepts more, and
#: sorting is done on the parsed integer so a five-digit version never sorts below a four-digit one.
_TRUTH_VERSION = re.compile(r"^truth-(\d+)\.yaml$")


class EvaluationStore:
    """Parent runs, child jobs, exact model evidence, events, comments and review state."""

    def __init__(self, objects: ObjectStore) -> None:
        self._objects = objects
        # One lock per store instance, held only while a sequence number is allocated. The
        # background worker is bounded to one billable invocation at a time, but the HTTP server
        # is threaded, so two requests can append an event concurrently.
        self._sequence_lock = threading.Lock()
        # Parsed task manifests, keyed by storage key, each validated against the object store's
        # fingerprint on every read. See `load_task` for why this exists and why it cannot serve a
        # stale record.
        self._task_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}

    @classmethod
    def at_path(cls, root: str | Path) -> EvaluationStore:
        """A store rooted at a local directory. `var/evaluation-runs` is gitignored."""
        return cls(FilesystemObjectStore(root))

    # --- keys ----------------------------------------------------------------------------------

    @staticmethod
    def _run_key(run_id: str) -> str:
        return f"{_RUNS}/{require_run_id(run_id)}/run.yaml"

    @staticmethod
    def _job_key(run_id: str, job_id: str) -> str:
        return f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}/job.yaml"

    @staticmethod
    def _evidence_key(run_id: str, job_id: str, name: str) -> str:
        if not _EVIDENCE_NAME.match(name):
            raise ValueError(f"evidence name {name!r} is not a permitted evidence file name")
        return f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}/evidence/{name}"

    @staticmethod
    def _task_key(run_id: str, job_id: str, task_id: str) -> str:
        return (
            f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}"
            f"/tasks/{require_task_id(task_id)}/task.yaml"
        )

    @staticmethod
    def _task_evidence_key(run_id: str, job_id: str, task_id: str, name: str) -> str:
        """SECURITY-INVARIANT: three issued identifiers and one checked name, and nothing else.

        A multipart task carries a MODEL-CHOSEN part identifier. It never appears in a key. The
        path is built from identifiers this store minted and validated, so the worst a model can do
        by choosing a hostile part identifier is have it displayed, escaped, as text.
        """
        if not _EVIDENCE_NAME.match(name):
            raise ValueError(f"evidence name {name!r} is not a permitted evidence file name")
        return (
            f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}"
            f"/tasks/{require_task_id(task_id)}/evidence/{name}"
        )

    @staticmethod
    def _assembly_key(run_id: str, job_id: str) -> str:
        return f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}/assembly.yaml"

    @staticmethod
    def _benchmark_prefix(cik: str, accession: str) -> str:
        """SECURITY-INVARIANT: the two path segments are NORMALISED SEC identities, not free text.

        `cik_padded` and `accession_dashed` accept a ten-digit CIK and a dashed accession and refuse
        everything else, so `..` and `/` never reach a storage key. They are also the single home
        for that normalisation — rules.md section 5 — which is why this does not pad or hyphenate
        anything itself.
        """
        return f"{_BENCHMARKS}/{cik_padded(cik)}/{accession_dashed(accession)}/"

    @classmethod
    def _benchmark_truth_key(cls, cik: str, accession: str, version: int) -> str:
        if version < 1:
            raise ValueError(
                f"benchmark truth version {version} is not storable. Version 0 is the derived "
                "document a filing starts from — mechanical suggestions and nothing accepted — and "
                "writing it would make an unreviewed filing indistinguishable from a reviewed one."
            )
        return f"{cls._benchmark_prefix(cik, accession)}truth-{version:04d}.yaml"

    # --- parent runs ---------------------------------------------------------------------------

    def save_run(self, run: RunRecord) -> None:
        """Write the parent run manifest. Atomic; a reader never sees a half-written run."""
        self._objects.put_text(
            self._run_key(run.run_id), to_yaml(run.to_mapping()), content_type="application/yaml"
        )

    def load_run(self, run_id: str) -> RunRecord:
        key = self._run_key(run_id)
        if not self._objects.exists(key):
            raise RunNotFoundError(f"no evaluation run is stored under {run_id!r}")
        return RunRecord.from_mapping(require_mapping(parse_yaml(self._objects.get_text(key))))

    def run_exists(self, run_id: str) -> bool:
        return self._objects.exists(self._run_key(run_id))

    def list_run_ids(self) -> list[str]:
        """Every stored run, newest first by creation time.

        Sorted by the manifest's timestamp rather than by identifier: the identifier is random by
        design, so sorting by it would present runs in an order with no meaning.
        """
        found = []
        for key in self._objects.list_keys(f"{_RUNS}/"):
            parts = key.split("/")
            if len(parts) == 3 and parts[2] == "run.yaml":
                found.append(parts[1])
        runs = []
        for run_id in found:
            try:
                runs.append(self.load_run(run_id))
            except Exception:  # noqa: BLE001 - a corrupt run must not hide every other run
                continue
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return [r.run_id for r in runs]

    # --- child jobs ----------------------------------------------------------------------------

    def save_job(self, job: JobRecord) -> None:
        job.updated_at = utc_now()
        self._objects.put_text(
            self._job_key(job.parent_run_id, job.job_id),
            to_yaml(job.to_mapping()),
            content_type="application/yaml",
        )

    def load_job(self, run_id: str, job_id: str) -> JobRecord:
        key = self._job_key(run_id, job_id)
        if not self._objects.exists(key):
            raise JobNotFoundError(f"no child job {job_id!r} is stored under run {run_id!r}")
        return JobRecord.from_mapping(require_mapping(parse_yaml(self._objects.get_text(key))))

    def list_job_ids(self, run_id: str) -> list[str]:
        """Child job identifiers in creation order."""
        prefix = f"{_RUNS}/{require_run_id(run_id)}/jobs/"
        found = []
        for key in self._objects.list_keys(prefix):
            parts = key[len(prefix) :].split("/")
            if len(parts) == 2 and parts[1] == "job.yaml":
                found.append(parts[0])
        jobs = []
        for job_id in found:
            try:
                jobs.append(self.load_job(run_id, job_id))
            except Exception:  # noqa: BLE001
                continue
        jobs.sort(key=lambda j: j.created_at)
        return [j.job_id for j in jobs]

    def load_jobs(self, run_id: str) -> list[JobRecord]:
        return [self.load_job(run_id, job_id) for job_id in self.list_job_ids(run_id)]

    # --- multipart tasks -------------------------------------------------------------------------

    def save_task(self, task: MultipartTask) -> None:
        """Write one task manifest. Atomic; a reader never sees a half-written task."""
        task.updated_at = utc_now()
        self._objects.put_text(
            self._task_key(task.run_id, task.root_job_id, task.task_id),
            to_yaml(task.to_mapping()),
            content_type="application/yaml",
        )

    def load_task(self, run_id: str, job_id: str, task_id: str) -> MultipartTask:
        """One task manifest, parsed, with a FINGERPRINTED read cache in front of it.

        WHY A CACHE IS HERE AT ALL. Scheduling reads every task of a filing to decide which one may
        run next, and a multipart parse of a dozen tasks makes that decision a dozen times. Measured
        on the integration suite: 460 manifest parses in one 41-second run, 27 seconds of it inside
        the YAML parser, over documents of two kilobytes. The parser is a pure-Python YAML 1.2 safe
        loader by deliberate choice, and it is not going to get faster.

        WHY IT CANNOT GO STALE. The entry is keyed by the object store's own fingerprint — the
        modification time in nanoseconds and the size — so any write, by this process or another,
        misses. A backend that cannot answer cheaply returns None and every read goes to disk, which
        is the same behaviour this method had before the cache existed.
        """
        key = self._task_key(run_id, job_id, task_id)
        fingerprint = self._objects.fingerprint(key)
        if fingerprint is not None:
            cached = self._task_cache.get(key)
            if cached is not None and cached[0] == fingerprint:
                # A fresh record per read: callers mutate what they are given and save it back,
                # and handing out the cached instance would let one caller's half-finished edits
                # appear in another's read.
                return MultipartTask.from_mapping(cached[1])
        if not self._objects.exists(key):
            raise TaskNotFoundError(
                f"no multipart task {task_id!r} is stored under child job {job_id!r} of run "
                f"{run_id!r}"
            )
        document = require_mapping(parse_yaml(self._objects.get_text(key)))
        if fingerprint is not None:
            self._task_cache[key] = (fingerprint, document)
        return MultipartTask.from_mapping(document)

    def list_task_ids(self, run_id: str, job_id: str) -> list[str]:
        prefix = f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}/tasks/"
        found = []
        for key in self._objects.list_keys(prefix):
            parts = key[len(prefix) :].split("/")
            if len(parts) == 2 and parts[1] == "task.yaml":
                found.append(parts[0])
        return found

    def load_tasks(self, run_id: str, job_id: str) -> list[MultipartTask]:
        """Every task of one child job, in creation order then declared order.

        Sorted by (created_at, order) rather than by identifier: identifiers are random by design,
        and the model's own `order` is what the hierarchy view has to respect.
        """
        tasks = []
        for task_id in self.list_task_ids(run_id, job_id):
            try:
                tasks.append(self.load_task(run_id, job_id, task_id))
            except Exception:  # noqa: BLE001 - one corrupt task must not hide every other task
                continue
        tasks.sort(key=lambda t: (t.created_at, t.order))
        return tasks

    def set_task_state(
        self, task: MultipartTask, requested: TaskState, *, message: str = ""
    ) -> MultipartTask:
        """Move a task's queue state, refusing an illegal move, and record the event."""
        assert_task_transition(task.state, requested)
        task.state = requested
        if requested is TaskState.RUNNING and task.started_at is None:
            task.started_at = utc_now()
        if requested in {
            TaskState.SUCCEEDED,
            TaskState.TRUNCATED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }:
            task.finished_at = utc_now()
        self.save_task(task)
        self.append_event(
            task.run_id,
            kind=f"task.{requested.value.lower()}",
            job_id=task.root_job_id,
            task_id=task.task_id,
            message=message or f"{task.task_type.value} {requested.value}",
        )
        return task

    def runnable_tasks(self, run_id: str, job_id: str) -> list[MultipartTask]:
        """Every task whose durable dependencies are satisfied and which is not yet running.

        DEPENDENCIES ARE READ FROM RECORDS, NOT WATCHED ON THE FILESYSTEM. A scheduler that polled
        for the appearance of a file would race the writer that is creating it, and the race would
        show up as a part occasionally starting before its plan existed.
        """
        tasks = self.load_tasks(run_id, job_id)
        by_id = {t.task_id: t for t in tasks}
        runnable = []
        for task in tasks:
            if task.state not in {TaskState.CREATED, TaskState.BLOCKED, TaskState.READY}:
                continue
            states = [by_id[d].state for d in task.depends_on if d in by_id]
            missing = [d for d in task.depends_on if d not in by_id]
            if missing:
                continue
            policy = task.dependency_policy or DependencyPolicy.ALL_SUCCEEDED
            if dependencies_satisfied(states, policy):
                runnable.append(task)
        return runnable

    def cancel_task(self, task: MultipartTask, *, reason: str) -> MultipartTask:
        """Cancel a task that has not been reserved. A reserved or running one is never cancelled.

        The provider call is billable from the moment it is issued, so a cancelled label on a
        running task would hide a charge the journal still has to settle.
        """
        if task.state not in CANCELLABLE_TASK_STATES:
            raise IllegalTransitionError(
                f"a task in {task.state.value} cannot be cancelled; a reserved or issued "
                "invocation is billable and is recorded rather than hidden",
                current=task.state.value,
                requested=TaskState.CANCELLED.value,
            )
        task.note = reason
        return self.set_task_state(task, TaskState.CANCELLED, message=reason)

    def resume_task(self, task: MultipartTask, *, author: str) -> MultipartTask:
        """Reopen an INTERRUPTED or FAILED task, by an EXPLICIT user action only.

        This is the only path back from either state, and nothing calls it automatically. A restart
        marks work interrupted and stops; a person decides whether to spend again.
        """
        task.error = None
        task.blocked_reason = None
        return self.set_task_state(
            task, TaskState.READY, message=f"reopened by {author}; a new attempt will be reserved"
        )

    def mark_interrupted_tasks(self) -> list[tuple[str, str, str]]:
        """Move every mid-flight multipart task to INTERRUPTED. Returns (run, job, task) triples.

        Called once at server start, beside `mark_interrupted_jobs`. NOTHING IS RE-INVOKED and
        NOTHING COMPLETED IS TOUCHED: a parse whose plan and four parts succeeded keeps all five,
        and only the branch that was in flight waits for a person.
        """
        touched: list[tuple[str, str, str]] = []
        for run_id in self.list_run_ids():
            for job in self.load_jobs(run_id):
                for task in self.load_tasks(run_id, job.job_id):
                    if task.state not in RESUMABLE_TASK_STATES:
                        continue
                    task.state = TaskState.INTERRUPTED
                    task.error = (
                        "the server restarted while this task was in flight. It was NOT rerun: a "
                        "rerun is billable and is only ever started by an explicit user action."
                    )
                    self.save_task(task)
                    self.append_event(
                        run_id,
                        kind="task.interrupted",
                        job_id=job.job_id,
                        task_id=task.task_id,
                        message="interrupted by a server restart; not rerun automatically",
                    )
                    touched.append((run_id, job.job_id, task.task_id))
        return touched

    def find_successful_task(
        self, run_id: str, job_id: str, *, idempotency: str
    ) -> MultipartTask | None:
        """An already-SUCCEEDED task with the same billable identity, or None.

        This is duplicate-scheduling protection and nothing more. It claims no provider-level
        exactly-once semantics: it says that THIS repository already paid for exactly these inputs
        and holds the response.
        """
        if not idempotency:
            return None
        for task in self.load_tasks(run_id, job_id):
            if task.idempotency == idempotency and task.state is TaskState.SUCCEEDED:
                return task
        return None

    # --- the mechanically assembled parse --------------------------------------------------------

    def save_assembly(self, run_id: str, job_id: str, assembly: dict[str, Any]) -> None:
        """Write the mechanical assembly index for one filing's multipart parse."""
        self._objects.put_text(
            self._assembly_key(run_id, job_id),
            to_yaml(assembly),
            content_type="application/yaml",
        )

    def load_assembly(self, run_id: str, job_id: str) -> dict[str, Any] | None:
        key = self._assembly_key(run_id, job_id)
        if not self._objects.exists(key):
            return None
        return require_mapping(parse_yaml(self._objects.get_text(key)))

    # --- the human benchmark truth for one filing ------------------------------------------------

    def save_benchmark_truth(self, document: dict[str, Any]) -> str:
        """Write one benchmark-truth version and return its key. Never overwrites a stored one.

        The document is an opaque mapping, exactly like a source set or a validation result: this
        store does not import `packages/completeness` and holds no opinion about what a
        classification means. It knows that the record belongs to one filing, that it carries a
        version, and that a version already on disk is not writable.
        """
        version = int(document.get("version") or 0)
        key = self._benchmark_truth_key(
            str(document.get("cik") or ""), str(document.get("accession") or ""), version
        )
        if self._objects.exists(key):
            raise BenchmarkTruthVersionExistsError(
                f"benchmark truth version {version} is already stored for this filing. It is "
                "superseded, never overwritten: reload the current version and record the "
                "judgement against it."
            )
        self._objects.put_text(key, to_yaml(document), content_type="application/yaml")
        return key

    def benchmark_truth_versions(self, cik: str, accession: str) -> list[int]:
        """Every stored version for one filing, ascending. Superseded documents stay readable."""
        prefix = self._benchmark_prefix(cik, accession)
        versions = []
        for key in self._objects.list_keys(prefix):
            found = _TRUTH_VERSION.match(key[len(prefix) :])
            if found:
                versions.append(int(found.group(1)))
        return sorted(versions)

    def load_benchmark_truth(
        self, cik: str, accession: str, *, version: int | None = None
    ) -> dict[str, Any] | None:
        """One stored truth document — the newest by default — or None when none exists.

        None means "no person has classified this filing yet", which is a real and common state
        and is NOT an error. The caller derives the mechanical suggestions instead.
        """
        if version is None:
            stored = self.benchmark_truth_versions(cik, accession)
            if not stored:
                return None
            version = stored[-1]
        key = self._benchmark_truth_key(cik, accession, version)
        if not self._objects.exists(key):
            return None
        return require_mapping(parse_yaml(self._objects.get_text(key)))

    # --- state transitions ---------------------------------------------------------------------

    def set_execution_state(
        self, job: JobRecord, requested: ExecutionState, *, message: str = ""
    ) -> JobRecord:
        """Move a child job's execution state, refusing an illegal move, and record the event."""
        assert_execution_transition(job.execution_state, requested)
        job.execution_state = requested
        self.save_job(job)
        self.append_event(
            job.parent_run_id,
            kind=f"execution.{requested.value.lower()}",
            job_id=job.job_id,
            message=message or requested.value,
        )
        return job

    def set_review_state(
        self,
        run_id: str,
        job_id: str,
        requested: ReviewState,
        *,
        author: str,
        note: str | None = None,
    ) -> JobRecord:
        """Move an artifact's review state and APPEND to its history.

        The history is appended to, never rewritten. rules.md invariant 7 forbids overwriting an
        accepted decision, and a review trail that can be edited is not a trail.
        """
        job = self.load_job(run_id, job_id)
        assert_review_transition(job.review_state, requested)
        previous = job.review_state
        job.review_state = requested
        job.review_history.append(
            ReviewTransition(
                at=utc_now(),
                author=author,
                from_state=previous.value,
                to_state=requested.value,
                note=note,
            )
        )
        self.save_job(job)
        self.append_event(
            run_id,
            kind=f"review.{requested.value.lower()}",
            job_id=job_id,
            message=f"{previous.value} -> {requested.value}",
        )
        return job

    def mark_interrupted_jobs(self) -> list[tuple[str, str]]:
        """Move every mid-flight job to INTERRUPTED. Returns the (run_id, job_id) pairs touched.

        Called once at server start. NOTHING IS RE-INVOKED. A job that was RUNNING when the
        process died may or may not have been billed; the only honest thing to do is say so and
        wait for a person to decide whether to spend again.
        """
        touched: list[tuple[str, str]] = []
        for run_id in self.list_run_ids():
            for job in self.load_jobs(run_id):
                if job.execution_state in RESUMABLE_EXECUTION_STATES:
                    job.execution_state = ExecutionState.INTERRUPTED
                    job.failure = (
                        "the server restarted while this job was in flight. It was NOT rerun: a "
                        "rerun is billable and is only ever started by an explicit user action."
                    )
                    self.save_job(job)
                    self.append_event(
                        run_id,
                        kind="execution.interrupted",
                        job_id=job.job_id,
                        message="interrupted by a server restart; not rerun automatically",
                    )
                    touched.append((run_id, job.job_id))
        return touched

    # --- events --------------------------------------------------------------------------------

    def append_event(
        self,
        run_id: str,
        *,
        kind: str,
        job_id: str | None,
        message: str,
        task_id: str | None = None,
    ) -> RunEvent:
        """Append one progress event and return it.

        The sequence number is allocated under a lock and the object is written under a key that
        embeds it, so two concurrent appends cannot collide on a number and neither can overwrite
        the other.
        """
        require_run_id(run_id)
        with self._sequence_lock:
            sequence = self._next_sequence(run_id)
            event = RunEvent(
                sequence=sequence,
                at=utc_now(),
                kind=kind,
                job_id=job_id,
                message=message,
                task_id=task_id,
            )
            self._objects.put_text(
                f"{_RUNS}/{run_id}/events/{sequence:08d}.txt",
                _encode_event(event),
                content_type="text/plain",
            )
        return event

    def _next_sequence(self, run_id: str) -> int:
        keys = self._objects.list_keys(f"{_RUNS}/{run_id}/events/")
        if not keys:
            return 1
        return max(int(Path(k).stem) for k in keys) + 1

    def read_events(self, run_id: str, *, after: int = 0) -> list[RunEvent]:
        """Every event with a sequence greater than ``after``, in order.

        ``after`` is the `Last-Event-ID` a reconnecting browser sent. Replaying from there is what
        makes the stream resumable without re-running any work.
        """
        require_run_id(run_id)
        events = []
        for key in self._objects.list_keys(f"{_RUNS}/{run_id}/events/"):
            sequence = int(Path(key).stem)
            if sequence <= after:
                continue
            events.append(_decode_event(sequence, self._objects.get_text(key)))
        events.sort(key=lambda e: e.sequence)
        return events

    # --- comments ------------------------------------------------------------------------------

    def add_comment(self, comment: Comment) -> Comment:
        """Store one evaluation comment. Comments are data and are never sent to a model."""
        require_run_id(comment.parent_run_id)
        require_comment_id(comment.comment_id)
        self._objects.put_text(
            f"{_RUNS}/{comment.parent_run_id}/comments/{comment.comment_id}.yaml",
            to_yaml(comment.to_mapping()),
            content_type="application/yaml",
        )
        self.append_event(
            comment.parent_run_id,
            kind="comment.added",
            job_id=comment.child_job_id,
            message=f"comment on {comment.target_type} {comment.target_id}",
        )
        return comment

    def list_comments(self, run_id: str, *, job_id: str | None = None) -> list[Comment]:
        """Comments for a run, oldest first, optionally narrowed to one child job."""
        require_run_id(run_id)
        comments = []
        for key in self._objects.list_keys(f"{_RUNS}/{run_id}/comments/"):
            comments.append(
                Comment.from_mapping(require_mapping(parse_yaml(self._objects.get_text(key))))
            )
        if job_id is not None:
            comments = [c for c in comments if c.child_job_id == job_id]
        comments.sort(key=lambda c: c.created_at)
        return comments

    # --- exact evidence ------------------------------------------------------------------------

    def put_evidence(
        self, run_id: str, job_id: str, name: str, data: bytes, *, content_type: str | None = None
    ) -> str:
        """Store exact bytes — a request, a response, a prompt, a transport envelope.

        Returns the storage key. Bytes are stored EXACTLY: nothing here decodes, re-encodes,
        pretty-prints or normalises. The whole value of this evidence is that it is what actually
        crossed the wire.
        """
        key = self._evidence_key(run_id, job_id, name)
        self._objects.put_bytes(key, data, content_type=content_type)
        return key

    def put_evidence_text(
        self, run_id: str, job_id: str, name: str, text: str, *, content_type: str = "text/plain"
    ) -> str:
        return self.put_evidence(
            run_id, job_id, name, text.encode("utf-8"), content_type=content_type
        )

    def get_evidence(self, run_id: str, job_id: str, name: str) -> bytes:
        return self._objects.get_bytes(self._evidence_key(run_id, job_id, name))

    def get_evidence_text(self, run_id: str, job_id: str, name: str) -> str:
        return self.get_evidence(run_id, job_id, name).decode("utf-8", errors="replace")

    def has_evidence(self, run_id: str, job_id: str, name: str) -> bool:
        return self._objects.exists(self._evidence_key(run_id, job_id, name))

    def list_evidence(self, run_id: str, job_id: str) -> list[str]:
        prefix = f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}/evidence/"
        return [key[len(prefix) :] for key in self._objects.list_keys(prefix)]

    def evidence_uri(self, run_id: str, job_id: str, name: str) -> str:
        return self._objects.uri_for(self._evidence_key(run_id, job_id, name))

    # --- exact evidence, one multipart task at a time ---------------------------------------------
    #
    # THE SOURCE SET IS NOT DUPLICATED PER TASK. Every semantic invocation in one filing's parse
    # receives the SAME intact source set, and that set is preserved once at the CHILD JOB level.
    # A ten-task parse of a 146 KB filing would otherwise store the filing ten times, and five
    # candidates' worth of that is a copy of the corpus per benchmark. What is stored per task is
    # what differs per task: the instruction, the transport envelopes, the exact response, the
    # reasoning content and the validation.

    def put_task_evidence(
        self,
        run_id: str,
        job_id: str,
        task_id: str,
        name: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> str:
        key = self._task_evidence_key(run_id, job_id, task_id, name)
        self._objects.put_bytes(key, data, content_type=content_type)
        return key

    def put_task_evidence_text(
        self,
        run_id: str,
        job_id: str,
        task_id: str,
        name: str,
        text: str,
        *,
        content_type: str = "text/plain",
    ) -> str:
        return self.put_task_evidence(
            run_id, job_id, task_id, name, text.encode("utf-8"), content_type=content_type
        )

    def get_task_evidence(self, run_id: str, job_id: str, task_id: str, name: str) -> bytes:
        return self._objects.get_bytes(self._task_evidence_key(run_id, job_id, task_id, name))

    def get_task_evidence_text(self, run_id: str, job_id: str, task_id: str, name: str) -> str:
        return self.get_task_evidence(run_id, job_id, task_id, name).decode(
            "utf-8", errors="replace"
        )

    def has_task_evidence(self, run_id: str, job_id: str, task_id: str, name: str) -> bool:
        return self._objects.exists(self._task_evidence_key(run_id, job_id, task_id, name))

    def list_task_evidence(self, run_id: str, job_id: str, task_id: str) -> list[str]:
        prefix = (
            f"{_RUNS}/{require_run_id(run_id)}/jobs/{require_job_id(job_id)}"
            f"/tasks/{require_task_id(task_id)}/evidence/"
        )
        return [key[len(prefix) :] for key in self._objects.list_keys(prefix)]


# --- the event wire format -----------------------------------------------------------------------
#
# Tab-separated, one event per object, with the three separators escaped. Deliberately not YAML:
# an event is read by a server-sent-events handler on every reconnect, and a format that needs a
# parser with an alias budget to read five fields is the wrong tool. Deliberately not JSON either
# — nothing here is model-visible, but the repository has one browser-facing serialisation and one
# model-facing one, and a third would be a third thing to keep honest.

_ESCAPES = ((chr(92), r"\\"), ("\t", r"\t"), ("\n", r"\n"))


def _escape(value: str) -> str:
    for raw, encoded in _ESCAPES:
        value = value.replace(raw, encoded)
    return value


def _unescape(value: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == chr(92) and index + 1 < len(value):
            nxt = value[index + 1]
            if nxt == "t":
                out.append("\t")
                index += 2
                continue
            if nxt == "n":
                out.append("\n")
                index += 2
                continue
            if nxt == chr(92):
                out.append(chr(92))
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _encode_event(event: RunEvent) -> str:
    return "\t".join(
        (
            _escape(event.at),
            _escape(event.kind),
            _escape(event.job_id or ""),
            _escape(event.message),
            _escape(event.task_id or ""),
        )
    )


def _decode_event(sequence: int, raw: str) -> RunEvent:
    """Decode one stored event.

    THE FIFTH FIELD IS PADDED, NOT REQUIRED. Thirty stored Phase 2 runs wrote four-field events
    before multipart tasks existed, and every one of them still has to open. A missing task
    identifier reads back as None, which is exactly what those events mean.
    """
    fields = raw.rstrip("\n").split("\t")
    while len(fields) < 5:
        fields.append("")
    return RunEvent(
        sequence=sequence,
        at=_unescape(fields[0]),
        kind=_unescape(fields[1]),
        job_id=_unescape(fields[2]) or None,
        message=_unescape(fields[3]),
        task_id=_unescape(fields[4]) or None,
    )


def summarise_run(run: RunRecord, jobs: list[JobRecord]) -> dict[str, Any]:
    """A small, browser-safe summary of a run and its children.

    Nothing provider-specific appears here: no request identifier, no endpoint, no credential, no
    filing text. The browser sees model LABELS, states, counts and money.
    """
    states = [j.execution_state.value for j in jobs]
    strategies = sorted({j.strategy for j in jobs}) or ["single_response"]
    return {
        "run_id": run.run_id,
        "created_at": run.created_at,
        "cik": run.cik,
        "entity_label": run.entity_label,
        "selected_roles": list(run.selected_roles),
        "parsing_label": run.parsing_label,
        "job_count": len(jobs),
        "ready_for_review": states.count(ExecutionState.READY_FOR_REVIEW.value),
        "failed": states.count(ExecutionState.FAILED.value),
        "incompatible": states.count(ExecutionState.INCOMPATIBLE.value),
        "interrupted": states.count(ExecutionState.INTERRUPTED.value),
        "actual_cost_usd": str(sum((j.actual_cost_usd or 0) for j in jobs)),
        # RECORDED PER RUN SO THE THIRTY HISTORICAL RUNS STAY LEGIBLE. A run listing that showed
        # only counts would make a single-response run and a multipart run look identical, and the
        # comparison this phase exists to enable starts with telling them apart.
        "strategies": strategies,
    }


def summarise_tasks(tasks: list[MultipartTask]) -> dict[str, Any]:
    """Counts a reviewer needs before opening the hierarchy. Mechanical, never a verdict.

    Nothing here says a parse is good, complete or better than another. It says how many tasks of
    each kind ran, how many truncated, how many replanning branches exist and what it cost.
    """
    by_state: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for task in tasks:
        by_state[task.state.value] = by_state.get(task.state.value, 0) + 1
        by_type[task.task_type.value] = by_type.get(task.task_type.value, 0) + 1
    return {
        "task_count": len(tasks),
        "by_state": dict(sorted(by_state.items())),
        "by_type": dict(sorted(by_type.items())),
        "truncated": by_state.get(TaskState.TRUNCATED.value, 0),
        "failed": by_state.get(TaskState.FAILED.value, 0),
        "interrupted": by_state.get(TaskState.INTERRUPTED.value, 0),
        "blocked": by_state.get(TaskState.BLOCKED.value, 0),
        "attempts": sum(t.attempt_count for t in tasks),
        "input_tokens": sum(a.input_tokens for t in tasks for a in t.attempts),
        "output_tokens": sum(a.output_tokens for t in tasks for a in t.attempts),
        "latency_ms": sum(a.latency_ms for t in tasks for a in t.attempts),
        "actual_cost_usd": str(sum((t.actual_cost_usd or Decimal(0)) for t in tasks)),
        "reserved_cost_usd": str(sum((t.reserved_cost_usd or Decimal(0)) for t in tasks)),
    }
