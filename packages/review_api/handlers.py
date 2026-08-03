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

from packages.coverage_validation import read as read_parsed
from packages.evaluation_store import (
    ExecutionState,
    JobNotFoundError,
    ReviewState,
    RunNotFoundError,
    permitted_review_transitions,
    summarise_run,
)
from packages.evaluation_store.errors import InvalidIdentifierError
from packages.orchestrator import (
    NoParsingModelError,
    ParserReviewService,
    RunRequest,
    StageNotAuthorizedError,
)
from packages.review_web import (
    SCRIPT,
    STYLESHEET,
    esc,
    home,
    job_page,
    join,
    layout,
    preflight_page,
    run_page,
    search_panel,
    tag,
)

from .router import Request, Response, Router, as_json, html, redirect, text
from .security import CSRF_FIELD, SecurityPolicy, set_cookie

_VIEWS = {"raw", "parsed", "side-by-side"}


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
        except (NoParsingModelError, StageNotAuthorizedError) as error:
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
        except (NoParsingModelError, StageNotAuthorizedError) as error:
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
        except (NoParsingModelError, StageNotAuthorizedError) as error:
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
                    yield (
                        f"id: {event.event_id}\nevent: {event.kind}\ndata: {event.message}\n\n"
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
        except (RunNotFoundError, JobNotFoundError, InvalidIdentifierError) as error:
            return self.policy.decorate(
                as_json({"code": "not_found", "message": str(error)}, status=404)
            )
        except ValueError as error:
            return self.policy.decorate(
                as_json({"code": "bad_request", "message": str(error)}, status=400)
            )


__all__ = ["ReviewApp", "CSRF_FIELD"]
