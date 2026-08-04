"""Every route the parser-review application serves.

WHAT THE BROWSER GETS AND WHAT IT NEVER GETS. Model LABELS, regions, states, counts, money, the
preserved bytes of a filing, and the exact bytes a model returned. It never receives an AWS access
key, an SSO token, a session credential, a profile name, an authorization header, a provider
endpoint or a filesystem path. There is no browser-to-Bedrock route because there is no route that
returns anything a browser could call Bedrock with — the whole model path is server-side through
`packages/llm_gateway`.

EVERY HANDLER IS A FUNCTION FROM `Request` TO `Response`, so the entire API is exercised in the
test suite with no socket, no port and no timeout. That is what keeps `test-no-skips` honest.

`Router.implemented()` IS THE CONTRACT. `tests/architecture/test_openapi_contract.py` compares it
against `docs/api/openapi.yaml` in BOTH directions: an endpoint marked IMPLEMENTED that no route
serves fails, and a route the specification does not describe fails too.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from packages.completeness import (
    BenchmarkTruth,
    BenchmarkTruthError,
    Judgement,
    suggest,
)
from packages.coverage_validation import read as read_parsed
from packages.evaluation_store import (
    BenchmarkTruthVersionExistsError,
    ExecutionState,
    IllegalTransitionError,
    JobNotFoundError,
    ReviewState,
    RunNotFoundError,
    TaskNotFoundError,
    TaskType,
    permitted_review_transitions,
    summarise_run,
    summarise_tasks,
    utc_now,
)
from packages.evaluation_store.errors import InvalidIdentifierError
from packages.multipart import PART_ENVELOPE_KEYS
from packages.orchestrator import (
    STRATEGIES,
    FilingNotInCatalogError,
    InventoriedFiling,
    NoParsingModelError,
    ParserReviewService,
    RunRequest,
    StageNotAuthorizedError,
    UnknownStrategyError,
)
from packages.orchestrator.multipart_service import (
    REASONING_EVIDENCE as TASK_REASONING_EVIDENCE,
)
from packages.orchestrator.multipart_service import (
    REQUEST_BRIEF_EVIDENCE as TASK_REQUEST_EVIDENCE,
)
from packages.orchestrator.multipart_service import (
    RESPONSE_EVIDENCE as TASK_RESPONSE_EVIDENCE,
)
from packages.review_web import (
    KIND_CLASSIFICATIONS,
    SCRIPT,
    STYLESHEET,
    assembled_page,
    base_path,
    benchmark_index,
    esc,
    home,
    images_page,
    inventory_page,
    job_page,
    join,
    layout,
    multipart_page,
    preflight_page,
    run_page,
    search_panel,
    spans_page,
    tables_page,
    tag,
    task_page,
    url,
)
from packages.source_transport import SourceTransportError

from .router import Request, Response, Router, as_json, html, redirect, text
from .security import CSRF_FIELD, SecurityPolicy, set_cookie

_VIEWS = {"raw", "parsed", "side-by-side"}

#: The `at` a MECHANICAL SUGGESTION carries when it is derived for one page render.
#:
#: A suggestion is never stored: the durable truth document holds what people decided, and the two
#: byte-level proposals are recomputed from the inventory on every read. There is therefore no
#: moment at which one was recorded, and stamping the current clock onto it would manufacture a
#: provenance for a judgement nobody made.
_DERIVED_ON_READ: str = ""


class ReviewApp:
    """The route table and the handlers behind it."""

    def __init__(
        self,
        *,
        service: ParserReviewService,
        worker: Any,
        policy: SecurityPolicy,
    ) -> None:
        self.service = service
        self.worker = worker
        self.policy = policy
        self.router = Router()
        self._register()

    # --- shared helpers ---------------------------------------------------------------------

    def _csrf(self, request: Request) -> str:
        session = self.policy.session_for(request)
        return session.csrf_token if session else ""

    def _page(
        self, request: Request, *, title: str, panel: str, main: str, run_id: str | None
    ) -> Response:
        return html(
            layout(
                title=title,
                panel=panel,
                main=main,
                run_id=run_id,
                collapsed=request.q("panel") == "closed",
                https=self.policy.https,
            )
        )

    def _panel(self, request: Request) -> str:
        """The left search panel, rebuilt from the query string so state survives a reload."""
        query = request.q("q")
        cik = request.q("cik")
        entity = self.service.catalog.entity(cik) if cik else None
        matches = self.service.catalog.search_entities(query) if query else []
        filings = self.service.catalog.filings(cik) if entity else []
        return search_panel(
            selectors=self.service.selectors(),
            csrf=self._csrf(request),
            query=query,
            entity=entity.to_mapping() if entity else None,
            matches=[m.to_mapping() for m in matches],
            filings=[f.to_mapping() for f in filings],
            chosen={
                "parsing_label": request.q("parsing_label"),
                "image_label": request.q("image_label"),
                "summary_label": request.q("summary_label"),
                "analysis_label": request.q("analysis_label"),
                "from_date": request.q("from_date"),
                "to_date": request.q("to_date"),
                "accession": request.q("accession"),
                "strategy": request.q("strategy"),
            },
            spend={
                "spent_usd": str(self.service.journal.spent_usd),
                "ceiling_usd": str(self.service.journal.ceiling_usd),
            },
        )

    @staticmethod
    def _request_from_form(form: dict[str, str]) -> RunRequest:
        accession = form.get("accession", "").strip()
        return RunRequest(
            cik=form.get("cik", "").strip(),
            parsing_label=form.get("parsing_label", "").strip(),
            accessions=(accession,) if accession else (),
            from_date=form.get("from_date") or None,
            to_date=form.get("to_date") or None,
            image_label=form.get("image_label") or None,
            summary_label=form.get("summary_label") or None,
            analysis_label=form.get("analysis_label") or None,
            # ABSENT MEANS THE PHASE 2 PROTOCOL, AND THAT IS BACKWARD COMPATIBILITY RATHER THAN A
            # PREFERENCE. A request that names no strategy predates the choice existing; the UI
            # form always sends one. `RunRequest` refuses anything it does not implement, so a
            # misspelled value fails loudly instead of silently running the other protocol.
            strategy=form.get("strategy") or STRATEGIES[0],
        )

    # --- registration -----------------------------------------------------------------------

    def _register(self) -> None:
        r = self.router
        r.add("GET", "/health", self.health, name="health")
        r.add("GET", "/", self.index, name="index")
        r.add("GET", "/sign-in", self.sign_in_page, name="signInPage")
        r.add("POST", "/sign-in", self.sign_in, name="signIn")
        r.add("GET", "/static/app.css", self.stylesheet, name="stylesheet")
        r.add("GET", "/static/app.js", self.script, name="script")
        r.add("GET", "/api/models", self.models, name="listModels")
        r.add("GET", "/api/entities", self.entities, name="searchEntities")
        r.add("GET", "/api/entities/{cik}", self.entity, name="getEntity")
        r.add("GET", "/api/entities/{cik}/filings", self.entity_filings, name="listEntityFilings")
        r.add("POST", "/preflight", self.preflight_html, name="preflightPage")
        r.add("POST", "/api/preflight", self.preflight_json, name="previewRunCost")
        r.add("POST", "/runs", self.create_run, name="createRun")
        r.add("GET", "/api/runs", self.list_runs, name="listRuns")
        r.add("GET", "/runs/{run_id}", self.run_html, name="runPage")
        r.add("GET", "/api/runs/{run_id}", self.run_json, name="getRun")
        r.add("GET", "/runs/{run_id}/events", self.run_events, name="streamRunEvents")
        r.add("POST", "/runs/{run_id}/cancel", self.cancel_run, name="cancelRun")
        r.add("GET", "/api/runs/{run_id}/comments", self.list_comments, name="listComments")
        r.add("GET", "/runs/{run_id}/jobs/{job_id}", self.job_html, name="jobPage")
        r.add("GET", "/api/runs/{run_id}/jobs/{job_id}", self.job_json, name="getChildJob")
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/source",
            self.job_source,
            name="getJobSourceArtifact",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/response",
            self.job_response,
            name="getExactModelResponse",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/parsed",
            self.job_parsed,
            name="getParsedArtifact",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/validation",
            self.job_validation,
            name="getValidation",
        )
        r.add("POST", "/runs/{run_id}/jobs/{job_id}/review", self.set_review, name="setReviewState")
        r.add("POST", "/runs/{run_id}/jobs/{job_id}/comments", self.add_comment, name="addComment")
        # --- the model-directed multipart surface, added in Phase 2.1 -----------------------
        r.add(
            "GET",
            "/runs/{run_id}/jobs/{job_id}/multipart",
            self.multipart_html,
            name="multipartPage",
        )
        r.add(
            "GET",
            "/runs/{run_id}/jobs/{job_id}/assembled",
            self.assembled_html,
            name="assembledPage",
        )
        r.add(
            "GET",
            "/runs/{run_id}/jobs/{job_id}/tasks/{task_id}",
            self.task_html,
            name="multipartTaskPage",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/tasks",
            self.tasks_json,
            name="listMultipartTasks",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/tasks/{task_id}",
            self.task_json,
            name="getMultipartTask",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/tasks/{task_id}/request",
            self.task_request,
            name="getExactTaskRequest",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/tasks/{task_id}/response",
            self.task_response,
            name="getExactTaskResponse",
        )
        r.add(
            "GET",
            "/api/runs/{run_id}/jobs/{job_id}/assembly",
            self.assembly_json,
            name="getAssembledParse",
        )
        r.add(
            "POST",
            "/runs/{run_id}/jobs/{job_id}/queue",
            self.queue_control,
            name="controlMultipartQueue",
        )
        # --- the completeness benchmark surface, added in Phase 2.2 --------------------------
        #
        # SCOPED TO A FILING RATHER THAN TO A RUN, AND THAT IS THE WHOLE POINT. A reviewer's
        # classification of one filing's inventory is the DENOMINATOR every parse of that filing is
        # measured against. It outlives every run, it is what a second run is compared with, and
        # hanging it off whichever run happened to exist first would make the denominator depend on
        # scheduling.
        r.add("GET", "/benchmark/{cik}/{accession}", self.benchmark_html, name="benchmarkPage")
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/inventory",
            self.benchmark_inventory_html,
            name="benchmarkInventoryPage",
        )
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/spans",
            self.benchmark_spans_html,
            name="benchmarkSpansPage",
        )
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/tables",
            self.benchmark_tables_html,
            name="benchmarkTablesPage",
        )
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/images",
            self.benchmark_images_html,
            name="benchmarkImagesPage",
        )
        r.add(
            "POST",
            "/benchmark/{cik}/{accession}/judgements",
            self.record_judgement,
            name="recordBenchmarkJudgement",
        )
        r.add(
            "GET",
            "/api/benchmark/{cik}/{accession}/inventory",
            self.benchmark_inventory_json,
            name="getBenchmarkInventory",
        )
        r.add(
            "GET",
            "/api/benchmark/{cik}/{accession}/truth",
            self.benchmark_truth_json,
            name="getBenchmarkTruth",
        )

    # --- health and assets ------------------------------------------------------------------

    def health(self, request: Request) -> Response:
        """Liveness plus the facts an operator needs, and nothing account-specific."""
        return as_json(
            {
                "status": "ok",
                "bind_mode": "loopback" if self.policy.loopback_only else "network interface",
                "authentication_required": self.policy.authentication_required,
                "https": self.policy.https,
                "preferred_region": self.service.preferred_region,
                "catalog_entities": getattr(self.service.catalog, "entity_count", None),
                "catalog_filings": getattr(self.service.catalog, "filing_count", None),
                "cost_ceiling_usd": str(self.service.journal.ceiling_usd),
                "cumulative_spend_usd": str(self.service.journal.spent_usd),
                "max_concurrent_invocations": getattr(self.worker, "max_concurrency", 1),
                "stages_executed_in_this_phase": ["parsing"],
            }
        )

    def stylesheet(self, request: Request) -> Response:
        return text(STYLESHEET, content_type="text/css; charset=utf-8")

    def script(self, request: Request) -> Response:
        return text(SCRIPT, content_type="text/javascript; charset=utf-8")

    # --- authentication ---------------------------------------------------------------------

    def sign_in_page(self, request: Request) -> Response:
        body = tag(
            "div",
            join(
                tag("h1", "Development sign-in"),
                tag(
                    "p",
                    esc(
                        "This instance is bound beyond the loopback interface, so it requires the "
                        "development authentication secret. The secret is read from ignored "
                        "environment state and is never stored in this repository."
                    ),
                ),
                tag(
                    "form",
                    join(
                        tag("input", "", type="password", name="secret", aria_label="secret"),
                        tag("button", "Sign in", type="submit"),
                    ),
                    method="post",
                    action="/sign-in",
                    class_="inline",
                ),
            ),
            class_="card",
        )
        return html(
            layout(
                title="Sign in",
                panel="",
                main=body,
                run_id=None,
                collapsed=True,
                https=self.policy.https,
            )
        )

    def sign_in(self, request: Request) -> Response:
        if not self.policy.check_secret(request.form().get("secret", "")):
            return as_json({"code": "invalid_secret", "message": "sign-in refused"}, status=401)
        session = self.policy.sessions.create()
        response = redirect("/")
        response.headers["Set-Cookie"] = set_cookie(session.session_id, https=self.policy.https)
        return response

    # --- catalog and models -----------------------------------------------------------------

    def models(self, request: Request) -> Response:
        return as_json(self.service.selectors())

    def entities(self, request: Request) -> Response:
        found = self.service.catalog.search_entities(
            request.q("q"), limit=int(request.q("limit", "20"))
        )
        return as_json({"results": [e.to_mapping() for e in found]})

    def entity(self, request: Request) -> Response:
        found = self.service.catalog.entity(request.params["cik"])
        if found is None:
            return as_json({"code": "not_found", "message": "no such entity"}, status=404)
        return as_json(found.to_mapping())

    def entity_filings(self, request: Request) -> Response:
        found = self.service.catalog.filings(
            request.params["cik"],
            from_date=request.q("from") or None,
            to_date=request.q("to") or None,
        )
        return as_json({"results": [f.to_mapping() for f in found]})

    # --- preflight and run creation ---------------------------------------------------------

    def _plan(self, form: dict[str, str]) -> Any:
        return self.service.preflight(self._request_from_form(form))

    def preflight_html(self, request: Request) -> Response:
        form = request.form()
        try:
            plan = self._plan(form)
        except (NoParsingModelError, StageNotAuthorizedError, UnknownStrategyError) as error:
            return html(
                layout(
                    title="Preflight refused",
                    panel=self._panel(request),
                    main=tag("div", tag("p", esc(str(error)), class_="warning"), class_="card"),
                    run_id=None,
                    collapsed=False,
                    https=self.policy.https,
                ),
                status=400,
            )
        return self._page(
            request,
            title="Cost preflight",
            panel=self._panel(request),
            main=preflight_page(plan=plan.to_mapping(), csrf=self._csrf(request), form=form),
            run_id=None,
        )

    def preflight_json(self, request: Request) -> Response:
        payload = request.json_body() or {}
        try:
            plan = self._plan({k: str(v) for k, v in payload.items()})
        except (NoParsingModelError, StageNotAuthorizedError, UnknownStrategyError) as error:
            return as_json({"code": "refused", "message": str(error)}, status=400)
        return as_json(plan.to_mapping())

    def create_run(self, request: Request) -> Response:
        # THE CONTENT TYPE DECIDES, NOT A SUBSTRING SEARCH. This used to sniff for an `=` anywhere
        # in the body, so a JSON document containing one in any VALUE — a note, a URL, a base64
        # fragment — was parsed as a form, produced one nonsense key, and the request was refused
        # 400 with "a run requires a parsing model" while carrying a perfectly good one. The
        # sibling preflight route parsed the same document correctly, so the two disagreed about
        # one payload. The header was present the whole time and unused.
        content_type = request.header("content-type").split(";")[0].strip().lower()
        body = request.body.lstrip()
        is_json = content_type == "application/json" or (not content_type and body.startswith(b"{"))
        if is_json:
            payload = request.json_body() or {}
            form = {k: str(v) for k, v in payload.items()}
        else:
            form = request.form()
        try:
            run_request = self._request_from_form(form)
            plan = self.service.preflight(run_request)
            run = self.service.create_run(run_request, plan=plan)
        except (NoParsingModelError, StageNotAuthorizedError, UnknownStrategyError) as error:
            return as_json({"code": "refused", "message": str(error)}, status=400)
        self.worker.submit_run(run.run_id)
        if request.wants_html():
            return redirect(f"/runs/{run.run_id}")
        return as_json({"run_id": run.run_id, "job_ids": run.job_ids}, status=202)

    # --- runs -------------------------------------------------------------------------------

    def list_runs(self, request: Request) -> Response:
        runs = []
        for run_id in self.service.store.list_run_ids():
            run = self.service.store.load_run(run_id)
            runs.append(summarise_run(run, self.service.store.load_jobs(run_id)))
        return as_json({"results": runs})

    def index(self, request: Request) -> Response:
        runs = []
        for run_id in self.service.store.list_run_ids():
            run = self.service.store.load_run(run_id)
            runs.append(summarise_run(run, self.service.store.load_jobs(run_id)))
        return self._page(
            request,
            title="Kopexx parser review",
            panel=self._panel(request),
            main=home(
                runs=runs,
                catalog={
                    "entity_count": getattr(self.service.catalog, "entity_count", 0),
                    "filing_count": getattr(self.service.catalog, "filing_count", 0),
                },
            ),
            run_id=None,
        )

    def _job_summaries(self, run_id: str) -> list[dict[str, Any]]:
        summaries = []
        for job in self.service.store.load_jobs(run_id):
            mapping = job.to_mapping()
            mapping["validation_status"] = (job.validation or {}).get("status")
            summaries.append(mapping)
        return summaries

    def run_html(self, request: Request) -> Response:
        run_id = request.params["run_id"]
        run = self.service.store.load_run(run_id)
        return self._page(
            request,
            title=f"Run {run_id}",
            panel=self._panel(request),
            main=run_page(
                run={**run.to_mapping(), "selected_roles": list(run.selected_roles)},
                jobs=self._job_summaries(run_id),
                events=[
                    {"event_id": e.event_id, "at": e.at, "kind": e.kind, "message": e.message}
                    for e in self.service.store.read_events(run_id)
                ],
            ),
            run_id=run_id,
        )

    def run_json(self, request: Request) -> Response:
        run_id = request.params["run_id"]
        run = self.service.store.load_run(run_id)
        jobs = self.service.store.load_jobs(run_id)
        return as_json(
            {
                "run": run.to_mapping(),
                "summary": summarise_run(run, jobs),
                "jobs": [j.to_mapping() for j in jobs],
            }
        )

    def run_events(self, request: Request) -> Response:
        """A server-sent-event stream, resumable through `Last-Event-ID`.

        NO PROVIDER DATA AND NO FILING TEXT CROSSES THIS STREAM. Events carry a kind, a child job
        identifier and a short message. Bodies live in the evaluation store and are referenced.

        The stream terminates once every child job reaches a terminal state, so a completed run
        replays its stored events and closes rather than holding a connection for ever.
        """
        run_id = request.params["run_id"]
        last = request.header("last-event-id") or request.q("last_event_id", "0")
        after = int(last) if last.isdigit() else 0
        store = self.service.store

        def stream() -> Iterator[bytes]:
            cursor = after
            for _ in range(600):  # a bounded watch, not an eternal one
                events = store.read_events(run_id, after=cursor)
                for event in events:
                    cursor = event.sequence
                    # THE TASK IDENTIFIER IS THE ONLY THING PHASE 2.1 ADDED TO THE WIRE, and it is
                    # an identifier this store issued. A multipart run emits many events per child
                    # job — a plan, N parts, a truncation, a reconciliation — and a stream that
                    # could name only the filing would leave a reviewer unable to tell which part
                    # truncated. Still no provider payload, no credential and no filing text.
                    attribution = f" [{event.task_id}]" if event.task_id else ""
                    yield (
                        f"id: {event.event_id}\nevent: {event.kind}\n"
                        f"data: {event.message}{attribution}\n\n"
                    ).encode()
                jobs = store.load_jobs(run_id)
                if jobs and all(
                    j.execution_state
                    in {
                        ExecutionState.READY_FOR_REVIEW,
                        ExecutionState.FAILED,
                        ExecutionState.INCOMPATIBLE,
                        ExecutionState.CANCELLED,
                        ExecutionState.INTERRUPTED,
                    }
                    for j in jobs
                ):
                    yield b"event: terminal\ndata: every child job has reached a terminal state\n\n"
                    return
                if not events:
                    yield b": keep-alive\n\n"
                    return

        return Response(
            status=200,
            stream=stream(),
            content_type="text/event-stream; charset=utf-8",
            headers={"Connection": "close", "X-Accel-Buffering": "no"},
        )

    def cancel_run(self, request: Request) -> Response:
        """Cancel every child job that has not yet been invoked.

        A RUNNING job is NOT cancelled. The provider call is billable from the moment it is issued,
        and marking it cancelled would hide a charge the ledger still has to settle.
        """
        run_id = request.params["run_id"]
        cancelled = []
        for job in self.service.store.load_jobs(run_id):
            if job.execution_state in {
                ExecutionState.CREATED,
                ExecutionState.SOURCE_READY,
                ExecutionState.PREFLIGHT,
                ExecutionState.QUEUED,
            }:
                self.service.store.set_execution_state(
                    job, ExecutionState.CANCELLED, message="cancelled by the user before invocation"
                )
                cancelled.append(job.job_id)
        if request.wants_html():
            return redirect(f"/runs/{run_id}")
        return as_json({"cancelled": cancelled})

    # --- one child job ----------------------------------------------------------------------

    def _artifact_names(self, job: Any) -> list[str]:
        members = (job.source_set or {}).get("members", [])
        return [m["filename"] for m in members if m.get("evidence_name")]

    def _artifact_text(self, run_id: str, job: Any, filename: str) -> str:
        for member in (job.source_set or {}).get("members", []):
            if member["filename"] == filename and member.get("evidence_name"):
                return self.service.store.get_evidence_text(
                    run_id, job.job_id, member["evidence_name"]
                )
        return ""

    def job_html(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        run = self.service.store.load_run(run_id)
        job = self.service.store.load_job(run_id, job_id)
        view = request.q("view", "side-by-side")
        if view not in _VIEWS:
            view = "side-by-side"
        artifacts = self._artifact_names(job)
        artifact = request.q("artifact") or (artifacts[0] if artifacts else "")
        offset = request.q("offset")
        length = request.q("length")

        raw_response = (
            self.service.store.get_evidence_text(run_id, job_id, "response-visible.txt")
            if self.service.store.has_evidence(run_id, job_id, "response-visible.txt")
            else ""
        )
        reasoning = (
            self.service.store.get_evidence_text(run_id, job_id, "response-reasoning.txt")
            if self.service.store.has_evidence(run_id, job_id, "response-reasoning.txt")
            else ""
        )
        parsed = None
        if raw_response:
            try:
                parsed = read_parsed(raw_response).raw
            except Exception:  # noqa: BLE001 - an unparseable response is shown raw, not hidden
                parsed = None

        return self._page(
            request,
            title=f"{job.form_as_filed} {job.accession}",
            panel=self._panel(request),
            main=job_page(
                run=run.to_mapping(),
                job=job.to_mapping(),
                view=view,
                artifacts=artifacts,
                artifact=artifact,
                artifact_text=self._artifact_text(run_id, job, artifact),
                focus=int(offset) if offset.isdigit() else None,
                focus_length=int(length) if length.isdigit() else 1,
                parsed=parsed,
                raw_response=raw_response,
                reasoning=reasoning,
                validation=job.validation,
                comments=[
                    c.to_mapping() for c in self.service.store.list_comments(run_id, job_id=job_id)
                ],
                csrf=self._csrf(request),
                permitted_reviews=sorted(
                    s.value for s in permitted_review_transitions(job.review_state)
                ),
            ),
            run_id=run_id,
        )

    def job_json(self, request: Request) -> Response:
        job = self.service.store.load_job(request.params["run_id"], request.params["job_id"])
        return as_json(job.to_mapping())

    def job_source(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        job = self.service.store.load_job(run_id, job_id)
        name = request.q("artifact") or (self._artifact_names(job) or [""])[0]
        body = self._artifact_text(run_id, job, name)
        if not body:
            return as_json({"code": "not_found", "message": "no such source artifact"}, status=404)
        return text(body)

    def job_response(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        if not self.service.store.has_evidence(run_id, job_id, "response-visible.txt"):
            return as_json({"code": "not_found", "message": "no response is stored"}, status=404)
        return text(self.service.store.get_evidence_text(run_id, job_id, "response-visible.txt"))

    def job_parsed(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        if not self.service.store.has_evidence(run_id, job_id, "response-visible.txt"):
            return as_json({"code": "not_found", "message": "no response is stored"}, status=404)
        raw = self.service.store.get_evidence_text(run_id, job_id, "response-visible.txt")
        try:
            document = read_parsed(raw)
        except Exception as error:  # noqa: BLE001
            return as_json(
                {
                    "code": "unparseable",
                    "message": str(error),
                    "note": "the exact response is preserved and is served by the response route",
                },
                status=409,
            )
        return as_json(document.raw)

    def job_validation(self, request: Request) -> Response:
        job = self.service.store.load_job(request.params["run_id"], request.params["job_id"])
        if job.validation is None:
            return as_json({"code": "not_found", "message": "no validation is stored"}, status=404)
        return as_json(job.validation)

    def set_review(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        form = request.form()
        try:
            requested = ReviewState(form.get("review_state", ""))
        except ValueError:
            return as_json({"code": "bad_request", "message": "unknown review state"}, status=400)
        self.service.store.set_review_state(
            run_id,
            job_id,
            requested,
            author=form.get("author") or self.service.author,
            note=form.get("note") or None,
        )
        if request.wants_html():
            return redirect(f"/runs/{run_id}/jobs/{job_id}")
        return as_json({"review_state": requested.value})

    def add_comment(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        form = request.form()
        if not form.get("text", "").strip():
            return as_json({"code": "bad_request", "message": "a comment needs text"}, status=400)
        comment = self.service.add_comment(
            run_id,
            job_id=job_id,
            target_type=form.get("target_type", "child_job"),
            target_id=form.get("target_id", "") or job_id,
            text=form["text"],
            target_version=str(len((self.service.store.load_job(run_id, job_id)).attempts) or 1),
        )
        if request.wants_html():
            return redirect(f"/runs/{run_id}/jobs/{job_id}")
        return as_json(comment.to_mapping(), status=201)

    def list_comments(self, request: Request) -> Response:
        comments = self.service.store.list_comments(request.params["run_id"])
        return as_json({"results": [c.to_mapping() for c in comments]})

    # --- one multipart parse ----------------------------------------------------------------
    #
    # THE THIRTY HISTORICAL SINGLE-RESPONSE RUNS ARE UNAFFECTED BY EVERY ROUTE BELOW. A job that
    # ran the Phase 2 protocol has no tasks and no assembly, so these pages report that plainly
    # rather than failing — and the job page it already had is untouched.

    def _tasks(self, run_id: str, job_id: str) -> list[dict[str, Any]]:
        return [t.to_mapping() for t in self.service.store.load_tasks(run_id, job_id)]

    def multipart_html(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        run = self.service.store.load_run(run_id)
        job = self.service.store.load_job(run_id, job_id)
        return self._page(
            request,
            title=f"Multipart parse {job.accession}",
            panel=self._panel(request),
            main=multipart_page(
                run=run.to_mapping(),
                job=job.to_mapping(),
                tasks=self._tasks(run_id, job_id),
                assembly=self.service.store.load_assembly(run_id, job_id),
                csrf=self._csrf(request),
            ),
            run_id=run_id,
        )

    def assembled_html(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        assembly = self.service.store.load_assembly(run_id, job_id)
        if assembly is None:
            return as_json(
                {"code": "not_found", "message": "no assembled parse is stored for this job"},
                status=404,
            )
        return self._page(
            request,
            title=f"Assembled parse {request.params['job_id']}",
            panel=self._panel(request),
            main=assembled_page(
                run=self.service.store.load_run(run_id).to_mapping(),
                job=self.service.store.load_job(run_id, job_id).to_mapping(),
                assembly=assembly,
            ),
            run_id=run_id,
        )

    def task_html(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        task_id = request.params["task_id"]
        store = self.service.store
        run = store.load_run(run_id)
        job = store.load_job(run_id, job_id)
        task = store.load_task(run_id, job_id, task_id)

        view = request.q("view", "side-by-side")
        if view not in _VIEWS:
            view = "side-by-side"
        artifacts = self._artifact_names(job)
        artifact = request.q("artifact") or (artifacts[0] if artifacts else "")
        offset, length = request.q("offset"), request.q("length")

        def evidence(name: str) -> str:
            return (
                store.get_task_evidence_text(run_id, job_id, task_id, name)
                if store.has_task_evidence(run_id, job_id, task_id, name)
                else ""
            )

        raw_response = evidence(TASK_RESPONSE_EVIDENCE)
        parsed = None
        if raw_response:
            try:
                parsed = read_parsed(raw_response, envelope_keys=PART_ENVELOPE_KEYS).raw
            except Exception:  # noqa: BLE001 - an unreadable response is shown raw, not hidden
                parsed = None

        return self._page(
            request,
            title=f"{task.task_type.value} {task.part_id or job.accession}",
            panel=self._panel(request),
            main=task_page(
                run=run.to_mapping(),
                job=job.to_mapping(),
                task=task.to_mapping(),
                view=view,
                artifacts=artifacts,
                artifact=artifact,
                artifact_text=self._artifact_text(run_id, job, artifact),
                focus=int(offset) if offset.isdigit() else None,
                focus_length=int(length) if length.isdigit() else 1,
                parsed=parsed if isinstance(parsed, dict) else None,
                request_brief=evidence(TASK_REQUEST_EVIDENCE),
                raw_response=raw_response,
                reasoning=evidence(TASK_REASONING_EVIDENCE),
                comments=[
                    c.to_mapping()
                    for c in store.list_comments(run_id, job_id=job_id)
                    if c.target_id == task_id or c.target_type != "multipart_task"
                ],
                csrf=self._csrf(request),
                permitted_reviews=sorted(
                    s.value for s in permitted_review_transitions(job.review_state)
                ),
            ),
            run_id=run_id,
        )

    def tasks_json(self, request: Request) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        tasks = self.service.store.load_tasks(run_id, job_id)
        return as_json(
            {
                "results": [t.to_mapping() for t in tasks],
                "summary": summarise_tasks(tasks),
            }
        )

    def task_json(self, request: Request) -> Response:
        task = self.service.store.load_task(
            request.params["run_id"], request.params["job_id"], request.params["task_id"]
        )
        return as_json(task.to_mapping())

    def _task_evidence(self, request: Request, name: str) -> Response:
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        task_id = request.params["task_id"]
        if not self.service.store.has_task_evidence(run_id, job_id, task_id, name):
            return as_json({"code": "not_found", "message": f"no {name} is stored"}, status=404)
        return text(self.service.store.get_task_evidence_text(run_id, job_id, task_id, name))

    def task_request(self, request: Request) -> Response:
        return self._task_evidence(request, TASK_REQUEST_EVIDENCE)

    def task_response(self, request: Request) -> Response:
        return self._task_evidence(request, TASK_RESPONSE_EVIDENCE)

    def assembly_json(self, request: Request) -> Response:
        assembly = self.service.store.load_assembly(
            request.params["run_id"], request.params["job_id"]
        )
        if assembly is None:
            return as_json(
                {"code": "not_found", "message": "no assembled parse is stored for this job"},
                status=404,
            )
        return as_json(assembly)

    def queue_control(self, request: Request) -> Response:
        """Every control that resumes, retries, cancels or advances a multipart parse.

        ONE ROUTE AND AN EXPLICIT ACTION NAME, rather than five routes. Each of these spends money
        or unblocks something that will; keeping them together makes the CSRF requirement and the
        authorization check impossible to apply to four of five by accident.
        """
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        form = request.form()
        action = form.get("action", "")
        multipart = self.service.multipart
        try:
            if action == "resume":
                result: Any = {"resumed": multipart.resume(run_id, job_id)}
            elif action == "unblock":
                result = {"unblocked": multipart.unblock(run_id, job_id)}
            elif action == "retry":
                task = multipart.retry(run_id, job_id, form.get("task_id", ""))
                result = {"retried": task.task_id}
            elif action == "cancel_branch":
                result = {
                    "cancelled": multipart.cancel_branch(run_id, job_id, form.get("task_id", ""))
                }
            elif action == "advance":
                result = {"ran": multipart.run_next(run_id, job_id)}
            elif action == "reconcile":
                # NARROWED TO RECONCILIATION, AND STILL SUBJECT TO THE DEPENDENCY RECORD. A
                # reconciliation whose parts have not reached a terminal state does not run because
                # a button was pressed; it reports that nothing was runnable.
                result = {"ran": multipart.run_next(run_id, job_id, only=TaskType.RECONCILE_PARSE)}
            else:
                return as_json(
                    {
                        "code": "bad_request",
                        "message": (
                            "unknown queue action. There is no default: an unrecognised action "
                            "must not quietly become one that spends money."
                        ),
                    },
                    status=400,
                )
        except (TaskNotFoundError, IllegalTransitionError) as error:
            return as_json({"code": "refused", "message": str(error)}, status=409)
        if request.wants_html():
            return redirect(f"/runs/{run_id}/jobs/{job_id}/multipart")
        return as_json(result)

    # --- the completeness benchmark for one filing --------------------------------------------
    #
    # NOTHING ON THIS SURFACE INVOKES A MODEL OR SPENDS ANYTHING. The inventory is measured from
    # the preserved bytes; the classification is a person's. The one state-changing route records
    # a judgement, and it is a POST with a CSRF token like every other one.

    def _stored_truth(self, found: InventoriedFiling) -> tuple[BenchmarkTruth, list[int]]:
        """The newest stored truth for this filing and every version on disk.

        An absent document is `BenchmarkTruth.empty` rather than an error: "nobody has classified
        this filing yet" is the state every filing starts in.

        THE VERSION LIST IS RESOLVED ONCE AND HANDED DOWN. `load_benchmark_truth` enumerates the
        stored keys itself when it is not told which version to read, so asking it for the newest
        after listing them would scan the store twice on every page load.
        """
        store = self.service.store
        cik, accession = found.filing.cik, found.filing.accession
        versions = store.benchmark_truth_versions(cik, accession)
        document = (
            store.load_benchmark_truth(cik, accession, version=versions[-1]) if versions else None
        )
        if document is None:
            return (
                BenchmarkTruth.empty(
                    cik=cik,
                    accession=accession,
                    source_set_sha256=found.inventory.source_set_sha256,
                ),
                versions,
            )
        return BenchmarkTruth.from_mapping(document), versions

    @staticmethod
    def _displayed_truth(found: InventoriedFiling, stored: BenchmarkTruth) -> BenchmarkTruth:
        """The stored judgements, with the two mechanical proposals filled in behind them.

        THE PROPOSALS ARE NEVER STORED AND NEVER WIN. `completeness.suggest` observes that a table
        element carries no non-whitespace character, or that its source slice is byte-identical to
        an earlier one, and proposes a classification with that evidence attached. A recorded
        judgement always takes precedence, and a proposal counts as neither reviewed nor excluded —
        it is displayed as an unaccepted suggestion and it still blocks the gate.
        """
        proposals = suggest(found.inventory, at=_DERIVED_ON_READ)
        return BenchmarkTruth(
            cik=stored.cik,
            accession=stored.accession,
            source_set_sha256=stored.source_set_sha256,
            version=stored.version,
            spans={**proposals.spans, **stored.spans},
            tables={**proposals.tables, **stored.tables},
            images={**proposals.images, **stored.images},
        )

    def _for_display(self, request: Request) -> tuple[InventoriedFiling, BenchmarkTruth, list[int]]:
        """Everything all five pages open with: the measurement, the merged truth, the versions.

        RESOLVED IN ONE PLACE SO EVERY PAGE SHOWS THE SAME TRUTH. Repeating the four steps per page
        is four chances for one of them to render the STORED document instead of the merged one —
        and a page that did would call an item unreviewed while the page beside it showed the
        mechanical proposal for it.

        A filing this project does not hold raises `FilingNotInCatalogError`, which `handle` turns
        into an ordinary 404. A malformed CIK or accession lands there too: the catalog's own
        contract promises `FilingRecord | None`, and a browser typing nonsense into a path is a miss
        rather than a fault.
        """
        found = self.service.inventoried_filing(request.params["cik"], request.params["accession"])
        if found is None:
            raise FilingNotInCatalogError(
                "no preserved filing with that identity is in the catalog. A completeness "
                "benchmark is measured from bytes this project actually holds; nothing is fetched "
                "to answer a page view."
            )
        stored, versions = self._stored_truth(found)
        return found, self._displayed_truth(found, stored), versions

    @staticmethod
    def _readable_member(found: InventoriedFiling, requested: str) -> str:
        """The requested member if this filing has it, otherwise the first human-readable one.

        CHECKED AGAINST THE INVENTORY BEFORE IT IS USED, which keeps an arbitrary browser-supplied
        string out of every href and hidden field the span page renders. Falling back rather than
        rendering nothing also matters: a page that answered a nonsense member with an empty table
        would read as a filing that contains no text.
        """
        readable = found.inventory.human_readable_members
        if any(record.member == requested for record in readable):
            return requested
        return readable[0].member if readable else ""

    def _benchmark_page(self, request: Request, *, title: str, main: str) -> Response:
        """A benchmark page carries NO run identifier, because it belongs to no run.

        `_page` anchors the parent run bar to the viewport, and a filing-scoped page showing the
        identifier of whichever run was last opened would invite exactly the wrong reading: that
        this classification describes that run.
        """
        return html(
            layout(
                title=title,
                panel=self._panel(request),
                main=main,
                run_id=None,
                collapsed=request.q("panel") == "closed",
                https=self.policy.https,
            )
        )

    def benchmark_html(self, request: Request) -> Response:
        found, truth, versions = self._for_display(request)
        return self._benchmark_page(
            request,
            title=f"Completeness benchmark {found.filing.accession}",
            main=benchmark_index(
                inventory=found.inventory,
                truth=truth,
                truth_versions=versions,
                issuer_label=found.filing.issuer_label,
            ),
        )

    def benchmark_inventory_html(self, request: Request) -> Response:
        found, truth, _ = self._for_display(request)
        return self._benchmark_page(
            request,
            title=f"Source inventory {found.filing.accession}",
            main=inventory_page(inventory=found.inventory, truth=truth),
        )

    def benchmark_spans_html(self, request: Request) -> Response:
        found, truth, _ = self._for_display(request)
        offset = request.q("start")
        return self._benchmark_page(
            request,
            title=f"Spans {found.filing.accession}",
            main=spans_page(
                inventory=found.inventory,
                truth=truth,
                member=self._readable_member(found, request.q("member")),
                start=int(offset) if offset.isdigit() else 0,
                csrf=self._csrf(request),
            ),
        )

    def benchmark_tables_html(self, request: Request) -> Response:
        found, truth, _ = self._for_display(request)
        # THE SLICE IS CUT FROM THE DECODED MEMBER, WHICH IS THE SAME COORDINATE SYSTEM THE
        # ELEMENT'S OFFSETS ARE IN. Cutting it from the raw bytes instead would be off by however
        # much the decoding changed, and a table's source slice would drift further into the
        # document the further down the filing it sits.
        texts = {m.filename: (m.text or "") for m in found.source_set.members if m.text}
        return self._benchmark_page(
            request,
            title=f"Tables {found.filing.accession}",
            main=tables_page(
                inventory=found.inventory,
                truth=truth,
                slices={
                    table.table_id: texts.get(table.member, "")[table.start : table.end]
                    for table in found.inventory.tables
                },
                csrf=self._csrf(request),
            ),
        )

    def benchmark_images_html(self, request: Request) -> Response:
        found, truth, _ = self._for_display(request)
        return self._benchmark_page(
            request,
            title=f"Images {found.filing.accession}",
            main=images_page(inventory=found.inventory, truth=truth, csrf=self._csrf(request)),
        )

    def benchmark_inventory_json(self, request: Request) -> Response:
        found, _, _ = self._for_display(request)
        return as_json(found.inventory.to_mapping())

    def benchmark_truth_json(self, request: Request) -> Response:
        found, _, versions = self._for_display(request)
        stored, _ = self._stored_truth(found)
        return as_json({**stored.to_mapping(), "stored_versions": versions})

    @staticmethod
    def _item_exists(found: InventoriedFiling, kind: str, item_id: str) -> bool:
        """Whether this filing's inventory contains the item a judgement names.

        EVERY KIND IS NAMED AND AN UNKNOWN ONE IS FALSE. Letting the image branch be the fall-
        through would mean that a fourth kind added to `KIND_CLASSIFICATIONS` was silently looked
        up among the images — and would be reported as absent for a reason having nothing to do
        with the filing.
        """
        inventory = found.inventory
        if kind == "span":
            return inventory.span(item_id) is not None
        if kind == "table":
            return inventory.table(item_id) is not None
        if kind == "image":
            return any(image.filename == item_id for image in inventory.images)
        return False

    def record_judgement(self, request: Request) -> Response:
        """Record ONE human classification of ONE inventory item, at a NEW truth version.

        THE STORED DOCUMENT NEVER CARRIES A SUGGESTION. The new version is built from the stored
        one, so the two mechanical proposals stay derived — a suggestion that persisted itself the
        first time anybody classified anything would become indistinguishable from a judgement.
        """
        found, _, _ = self._for_display(request)
        form = request.form()
        kind = form.get("kind", "")
        if kind not in KIND_CLASSIFICATIONS:
            return as_json(
                {
                    "code": "bad_request",
                    "message": (
                        f"{kind!r} is not an inventory item kind. A judgement attaches to a span, "
                        "a table or an image, and to nothing else."
                    ),
                },
                status=400,
            )
        item_id = form.get("item_id", "").strip()
        if not self._item_exists(found, kind, item_id):
            return as_json(
                {
                    "code": "not_found",
                    "message": (
                        f"no {kind} {item_id!r} is in this filing's mechanical inventory. A "
                        "judgement about an item the filing does not contain has nothing to "
                        "attach to and is refused rather than stored."
                    ),
                },
                status=404,
            )
        classification = form.get("classification", "")
        stored, _ = self._stored_truth(found)
        try:
            updated = stored.with_judgement(
                kind,
                Judgement(
                    item_id=item_id,
                    classification=classification,
                    reviewer=form.get("author") or self.service.author,
                    at=utc_now(),
                    note=form.get("note", ""),
                    suggested=False,
                ),
            )
        except BenchmarkTruthError as error:
            return as_json({"code": "bad_request", "message": str(error)}, status=400)
        try:
            self.service.store.save_benchmark_truth(updated.to_mapping())
        except BenchmarkTruthVersionExistsError as error:
            return as_json({"code": "conflict", "message": str(error)}, status=409)

        if request.wants_html():
            return redirect(self._judgement_location(found, kind, form))
        return as_json(
            {
                "kind": kind,
                "item_id": item_id,
                "classification": classification,
                "version": updated.version,
                "note": (
                    "the previous version is unchanged on disk. A truth version is superseded, "
                    "never overwritten."
                ),
            },
            status=201,
        )

    def _judgement_location(self, found: InventoriedFiling, kind: str, form: dict[str, str]) -> str:
        """Where a browser goes after recording a judgement.

        BUILT FROM THE ITEM KIND, NEVER FROM ANYTHING THE BROWSER SENT. A `return_to` field taken
        from a form would be an open redirect on an origin that holds a session able to spend
        money. The two values that DO come from the form — which member and which page of it the
        reviewer was reading — are checked against the inventory and against `str.isdigit` before
        they are used, so the worst a hostile post achieves is being returned to the first member.
        """
        base = base_path(found.filing.cik, found.filing.accession)
        if kind != "span":
            return url(*base, "tables" if kind == "table" else "images")
        start = form.get("start", "")
        return url(
            *base,
            "spans",
            member=self._readable_member(found, form.get("member", "")),
            start=start if start.isdigit() else "",
        )

    # --- dispatch ---------------------------------------------------------------------------

    def handle(self, request: Request) -> Response:
        """Route, authorize, check CSRF, and turn a known failure into an honest status."""
        if request.path.startswith("/static/") or request.path in {"/health", "/sign-in"}:
            refusal = None
        else:
            refusal = self.policy.authorize(request)
        if refusal is not None:
            return self.policy.decorate(refusal)

        resolved = self.router.resolve(request.method, request.path)
        if resolved is None:
            return self.policy.decorate(
                as_json(
                    {"code": "not_found", "message": f"no route for {request.path}"}, status=404
                )
            )
        handler, params = resolved

        if request.method == "POST" and request.path != "/sign-in":
            csrf_failure = self.policy.check_csrf(request)
            if csrf_failure is not None:
                return self.policy.decorate(csrf_failure)

        bound = Request(
            method=request.method,
            path=request.path,
            query=request.query,
            headers=request.headers,
            body=request.body,
            params=params,
            client_host=request.client_host,
        )
        try:
            return self.policy.decorate(handler(bound))
        except (
            RunNotFoundError,
            JobNotFoundError,
            TaskNotFoundError,
            InvalidIdentifierError,
            FilingNotInCatalogError,
        ) as error:
            return self.policy.decorate(
                as_json({"code": "not_found", "message": str(error)}, status=404)
            )
        except SourceTransportError as error:
            # A SOURCE SET THAT CANNOT BE ASSEMBLED IS A 409, NOT A 500 AND NOT A 404. The filing
            # is in the catalog; a member of it is missing, its hash has moved, or its transport
            # role could not be justified from its bytes. Every one of those is a state of this
            # host's preserved objects that a person has to resolve, and answering 404 would say
            # the filing does not exist while it sits in the manifest.
            return self.policy.decorate(
                as_json({"code": "source_unavailable", "message": str(error)}, status=409)
            )
        except ValueError as error:
            return self.policy.decorate(
                as_json({"code": "bad_request", "message": str(error)}, status=400)
            )


__all__ = ["ReviewApp", "CSRF_FIELD"]
