"""A bounded, in-process background worker. Deliberately the smallest thing that works.

WHY NOT A QUEUE. roadmap.md and the Phase 2 brief both rule out a distributed queue, Redis and
Celery for this phase, and the reason is the same one that deleted a 24-table schema: designing
durable infrastructure before there is a measured workload is how you get infrastructure shaped
like a guess. What is actually needed here is that the browser does not block for two minutes while
a filing is parsed, and one worker thread does that.

ONE BILLABLE INVOCATION AT A TIME, BY DEFAULT. `max_concurrency` defaults to 1. Five expensive
filing requests launched concurrently is a fivefold multiplication of the worst case against a
five-dollar ceiling, and the comparative benchmark is explicitly allowed to run sequentially. The
bound is configurable so a later phase can raise it deliberately rather than discover it.

DURABILITY LIVES IN THE STORE, NOT HERE. This class holds no state a restart would need. Every
transition it causes is written by `EvaluationStore` before the next one begins, and on restart
`mark_interrupted_jobs` moves anything mid-flight to INTERRUPTED. NOTHING IS RESUMED
AUTOMATICALLY: a rerun is billable, and money is never spent by a process that merely came back up.

A FAILING JOB NEVER KILLS THE WORKER. An exception inside one job is recorded against that job and
the next one still runs. A worker thread that died silently would leave every subsequent job QUEUED
for ever with nothing to say why.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from packages.evaluation_store import ExecutionState

from .service import ParserReviewService


class BoundedWorker:
    """Runs child filing jobs off the request thread, one at a time by default."""

    def __init__(self, service: ParserReviewService, *, max_concurrency: int = 1) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._service = service
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency, thread_name_prefix="parser-job"
        )
        self._lock = threading.Lock()
        self._pending: dict[str, Future[Any]] = {}
        self.max_concurrency = max_concurrency

    def submit(self, run_id: str, job_id: str) -> None:
        """Queue one child job. Returns immediately."""
        with self._lock:
            if job_id in self._pending and not self._pending[job_id].done():
                return
            self._pending[job_id] = self._executor.submit(self._run, run_id, job_id)

    def submit_run(self, run_id: str) -> int:
        """Queue every QUEUED child job of one run. Returns how many were queued."""
        queued = 0
        for job in self._service.store.load_jobs(run_id):
            if job.execution_state is ExecutionState.QUEUED:
                self.submit(run_id, job.job_id)
                queued += 1
        return queued

    def _run(self, run_id: str, job_id: str) -> None:
        try:
            self._service.execute_job(run_id, job_id)
        except Exception as error:  # noqa: BLE001 - one job's failure must not stop the worker
            store = self._service.store
            try:
                job = store.load_job(run_id, job_id)
                job.failure = f"{type(error).__name__}: {error}"
                store.save_job(job)
                if job.execution_state not in {
                    ExecutionState.FAILED,
                    ExecutionState.READY_FOR_REVIEW,
                    ExecutionState.INCOMPATIBLE,
                    ExecutionState.CANCELLED,
                    ExecutionState.INTERRUPTED,
                }:
                    store.set_execution_state(job, ExecutionState.FAILED, message=str(error)[:400])
            except Exception:  # noqa: BLE001 - the store itself is unreachable; nothing to record
                pass

    def wait(self, timeout: float | None = None) -> None:
        """Block until every queued job has finished. Test and benchmark support."""
        with self._lock:
            futures = list(self._pending.values())
        for future in futures:
            future.result(timeout=timeout)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class InlineWorker:
    """Runs each job on the calling thread, immediately.

    Used by tests and by the benchmark tool, where the sequencing has to be deterministic and a
    background thread would make an assertion race the work it is asserting about.
    """

    max_concurrency = 1

    def __init__(self, service: ParserReviewService) -> None:
        self._service = service

    def submit(self, run_id: str, job_id: str) -> None:
        self._service.execute_job(run_id, job_id)

    def submit_run(self, run_id: str) -> int:
        queued = 0
        for job in self._service.store.load_jobs(run_id):
            if job.execution_state is ExecutionState.QUEUED:
                self.submit(run_id, job.job_id)
                queued += 1
        return queued

    def wait(self, timeout: float | None = None) -> None:
        return None

    def shutdown(self) -> None:
        return None
