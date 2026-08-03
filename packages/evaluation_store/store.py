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
from pathlib import Path
from typing import Any

from packages.llm_gateway import parse_yaml, require_mapping, to_yaml
from packages.storage import FilesystemObjectStore, ObjectStore

from .errors import JobNotFoundError, RunNotFoundError
from .identity import require_comment_id, require_job_id, require_run_id
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

#: Evidence file names are written by this repository, never by a request. The pattern is still
#: enforced: an evidence name reaches a storage key, and a guard that only exists because "no
#: caller would do that" is a guard that stops holding the first time a caller does.
_EVIDENCE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

_RUNS = "runs"


class EvaluationStore:
    """Parent runs, child jobs, exact model evidence, events, comments and review state."""

    def __init__(self, objects: ObjectStore) -> None:
        self._objects = objects
        # One lock per store instance, held only while a sequence number is allocated. The
        # background worker is bounded to one billable invocation at a time, but the HTTP server
        # is threaded, so two requests can append an event concurrently.
        self._sequence_lock = threading.Lock()

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

    def append_event(self, run_id: str, *, kind: str, job_id: str | None, message: str) -> RunEvent:
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
        )
    )


def _decode_event(sequence: int, raw: str) -> RunEvent:
    fields = raw.rstrip("\n").split("\t")
    while len(fields) < 4:
        fields.append("")
    return RunEvent(
        sequence=sequence,
        at=_unescape(fields[0]),
        kind=_unescape(fields[1]),
        job_id=_unescape(fields[2]) or None,
        message=_unescape(fields[3]),
    )


def summarise_run(run: RunRecord, jobs: list[JobRecord]) -> dict[str, Any]:
    """A small, browser-safe summary of a run and its children.

    Nothing provider-specific appears here: no request identifier, no endpoint, no credential, no
    filing text. The browser sees model LABELS, states, counts and money.
    """
    states = [j.execution_state.value for j in jobs]
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
    }
