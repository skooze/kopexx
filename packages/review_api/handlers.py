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

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
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
    TaskState,
    TaskType,
    attention,
    permitted_review_transitions,
    summarise_run,
    summarise_tasks,
    utc_now,
)
from packages.evaluation_store.errors import InvalidIdentifierError
from packages.multipart import PART_ENVELOPE_KEYS, resolve_effective
from packages.orchestrator import (
    PART_TYPES,
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
    BENCHMARK_TAB,
    FILING_TAB,
    KIND_CLASSIFICATIONS,
    SCRIPT,
    STYLESHEET,
    Crumb,
    PanelContext,
    TaskRow,
    active_section,
    assembled_page,
    assembled_pane,
    base_path,
    benchmark_index,
    comparison_panes,
    counts,
    counts_sentence,
    esc,
    filings_index,
    home,
    hub,
    images_page,
    inventory_page,
    job_page,
    join,
    judgements_page,
    layout,
    model_comparison_page,
    model_run_page,
    multipart_page,
    panel_mode,
    panel_shell,
    parsed_pane,
    preflight_page,
    review_menu,
    run_page,
    search_panel,
    spans_page,
    tables_page,
    tabs,
    tag,
    task_page,
    url,
    with_query,
)
from packages.source_transport import SourceTransportError

from .router import Request, Response, Router, as_json, html, redirect, text
from .security import CSRF_FIELD, SecurityPolicy, cookie_value, set_cookie

_VIEWS = {"raw", "parsed", "side-by-side"}

#: How the run-event stream watches: how many times it looks, and how long it waits between looks.
#:
#: THE PAIR IS THE BOUND, AND IT USED TO BE THE COUNT ALONE. 600 polls with no wait is not a watch
#: of any duration — it is a spin that ends whenever the disk stops producing new events, holding a
#: core for as long as a parse is emitting them. 600 polls one second apart is a ten-minute watch,
#: which is a duration a reviewer can reason about and a browser reconnects past.
#:
#: ONE SECOND IS CHOSEN AGAINST WHAT A POLL COSTS, NOT AGAINST WHAT FEELS RESPONSIVE. Each one
#: lists a run's event directory and loads every child job; on this store a full replay of 1,280
#: events already costs 2.5 seconds, so a poll interval shorter than the work is a queue rather
#: than a watch.
EVENT_STREAM_POLLS: int = 600
EVENT_STREAM_POLL_SECONDS: float = 1.0

#: The `at` a MECHANICAL SUGGESTION carries when it is derived for one page render.
#:
#: A suggestion is never stored: the durable truth document holds what people decided, and the two
#: byte-level proposals are recomputed from the inventory on every read. There is therefore no
#: moment at which one was recorded, and stamping the current clock onto it would manufacture a
#: provenance for a judgement nobody made.
_DERIVED_ON_READ: str = ""


@dataclass(frozen=True)
class OpenedTarget:
    """One destination whose opening may be recorded, and the version it was opened at.

    `prefix` is a validated attention prefix; `item` and `fingerprint` are validated by
    `packages.evaluation_store.attention`. Nothing here reaches an evidence file: every input is a
    value already present in a durable record, so recording an open reads nothing extra.
    """

    prefix: str
    item: str
    fingerprint: str


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

    # --- attention: what this reader has already opened -------------------------------------
    #
    # DISPOSABLE BY DESIGN. Everything below writes under `attention/`, a sibling of `runs/` and
    # `benchmarks/` and never inside them. Deleting `var/evaluation-runs/attention/` resets every
    # mark and loses not one byte that was paid for, which is the property that makes recording on
    # a GET acceptable at all.

    def _reviewer_token(self) -> str:
        return attention.reviewer_token(self.service.author)

    def _job_prefix(self, run_id: str, job_id: str) -> str:
        return attention.job_prefix(self._reviewer_token(), run_id, job_id)

    def _filing_prefix(self, cik: str, accession: str) -> str:
        return attention.filing_prefix(self._reviewer_token(), cik, accession)

    def _opened(self, prefix: str) -> dict[str, frozenset[str]]:
        """Every item opened under one prefix. One key listing, no file read, no YAML parse."""
        try:
            return self.service.store.opened_items(prefix)
        except Exception:  # noqa: BLE001 - attention is scratch; a page never fails to render for it
            return {}

    @staticmethod
    def _is_prefetch(request: Request) -> bool:
        """Whether a browser fetched this speculatively rather than a person opening it.

        A PREFETCHED PAGE MARKS NOTHING. Recording it would tell the reader they had opened pages
        they never saw, which is the over-counting failure this vocabulary exists to prevent.
        """
        for header in ("sec-purpose", "purpose", "x-moz"):
            if "prefetch" in request.header(header).lower():
                return True
        return False

    def _record_opened(self, request: Request, target: OpenedTarget | None) -> None:
        """Record that this page was rendered. NEVER a failure path for the page.

        A SIDE EFFECT ON A SAFE METHOD, STATED RATHER THAN HIDDEN. What makes it acceptable is that
        the record is not evidence: it is disposable scratch under `attention/`. What makes it
        NECESSARY is that a marker a reader has to click to produce is a marker nobody produces —
        and an indicator that ignores thirty pages you just read is worse than no indicator, for
        exactly the reason an over-counting one is.
        """
        if target is None or request.method != "GET" or self._is_prefetch(request):
            return
        try:
            self.service.store.record_opened(
                target.prefix, item=target.item, fingerprint=target.fingerprint
            )
        except Exception:  # noqa: BLE001 - a page must never fail to render for a progress marker
            return

    # --- attention fingerprints ---------------------------------------------------------------
    #
    # EVERY INPUT IS ALREADY IN A DURABLE RECORD. No evidence file is read and nothing is hashed
    # over response bytes: a fingerprint that cost a file read would put that cost on every page
    # load, to answer a question about a checkmark.

    def _opened_target_for_job(self, job: Any, *, item: str) -> OpenedTarget:
        """A job-scoped destination, stamped with what would make it a different page."""
        return OpenedTarget(
            prefix=self._job_prefix(job.parent_run_id, job.job_id),
            item=item,
            fingerprint=attention.fingerprint(
                job.updated_at, job.execution_state.value, job.review_state.value
            ),
        )

    def _opened_target_for_task(self, job: Any, task: Any) -> OpenedTarget:
        """One call, stamped with its idempotency — which already covers everything that matters.

        `task.idempotency` is a stored hash of the source set, the model, the region, the prompt
        bytes, the task type, the plan and part identity, the parent artifact, the settings and the
        attempt salt. A retry mints a new salt, so a retried call reads `opened at an earlier
        version` without this having to enumerate why.
        """
        return OpenedTarget(
            prefix=self._job_prefix(job.parent_run_id, job.job_id),
            item=task.task_id,
            fingerprint=attention.fingerprint(
                task.idempotency, task.state.value, len(task.attempts or ())
            ),
        )

    def _opened_target_for_filing(
        self, cik: str, accession: str, *, item: str, stamp: str
    ) -> OpenedTarget:
        return OpenedTarget(
            prefix=self._filing_prefix(cik, accession),
            item=item,
            fingerprint=attention.fingerprint(stamp),
        )

    # --- crumb trails ---------------------------------------------------------------------------
    #
    # SUPPLIED, NEVER DERIVED FROM THE PATH. Splitting `request.path` would render an accession as
    # its own label and could not reach the issuer name or the form string, which only the handler
    # has already loaded. Every crumb names its SCOPE rather than an identifier — except the run,
    # whose identifier IS what a person quotes in a bug report.
    #
    # A FILING REACHED UNDER `Home` AND THE SAME FILING REACHED UNDER `Filings` SHOW DIFFERENT
    # TRAILS ON PURPOSE. Which route you took is what the parent crumb should undo.
    #
    # THE RUN TRAIL HAS NO `Runs` CRUMB BETWEEN `Home` AND THE RUN. It had one, pointing at `/` —
    # the same destination `Home` already points at, two crumbs from one trail landing on one page.
    # That is the `Reviews` defect in miniature, and it goes for the same reason: the run list IS
    # the home page, so naming it twice tells a reader the trail does not mean anything.

    @staticmethod
    def _home_crumbs(*rest: Crumb) -> list[Crumb]:
        return [Crumb("Home", "/"), *rest]

    @staticmethod
    def _run_crumbs(run_id: str, *rest: Crumb) -> list[Crumb]:
        trail = [Crumb("Home", "/"), Crumb(run_id, url("runs", run_id))]
        if not rest:
            trail[-1] = Crumb(run_id)
        return [*trail, *rest]

    @staticmethod
    def _attempt_providers(job: Any, assembly: dict[str, Any] | None, task_count: int) -> list[str]:
        """The adapter that answered every attempt of this parse, the job's own and its calls'.

        ONE LIST ACROSS BOTH LEVELS BECAUSE A PARSE IS ONE THING TO A REVIEWER. A single-response
        run records its attempts on the job; a multipart run records every one of them on a task
        and leaves `job.attempts` empty. A card that read only the job could not tell a Bedrock
        call from a mock one on the runs that make the most calls.

        THE MULTIPART SIDE IS READ FROM THE ASSEMBLY, NOT FROM THE TASK RECORDS. The assembly is a
        rollup of every task and this page loads it anyway; opening the 123 task documents of one
        filing's parse to read a provider string cost 2.5 seconds, against 0.02 to list them.

        AN UNRECORDED PROVIDER STAYS IN THE LIST AS AN EMPTY STRING, one per attempt that recorded
        none. Dropping it would make an attempt nobody wrote a provider for indistinguishable from
        no attempt at all, and those two need different sentences on the page. `task_count` is what
        keeps that true for a parse stored before the field existed: its tasks are real, its
        providers are unknown, and the page says exactly that.
        """
        found = [str(a.get("provider") or "") for a in (job.to_mapping().get("attempts") or [])]
        summaries = (assembly or {}).get("tasks") or []
        for summary in summaries:
            named = [str(p) for p in (summary.get("providers") or []) if p]
            found.extend(named or [""] * max(int(summary.get("attempts") or 0), 1))
        if not summaries:
            found.extend([""] * task_count)
        return found

    @staticmethod
    def _filing_label(job: Any) -> str:
        return f"{job.form_as_filed} {job.accession}"

    def _job_crumbs(self, job: Any, *rest: Crumb) -> list[Crumb]:
        hub = url("runs", job.parent_run_id, "jobs", job.job_id, "review")
        label = self._filing_label(job)
        return self._run_crumbs(
            job.parent_run_id,
            Crumb(label, hub if rest else ""),
            *rest,
        )

    @staticmethod
    def _filing_crumbs(cik: str, accession: str, form: str, *rest: Crumb) -> list[Crumb]:
        label = f"{form} {accession}".strip()
        overview = url("benchmark", cik, accession)
        return [
            Crumb("Filings", "/filings"),
            Crumb(label, overview if rest else ""),
            *rest,
        ]

    def _page(
        self,
        request: Request,
        *,
        title: str,
        panel: str,
        main: str,
        run_id: str | None,
        crumbs: Sequence[Crumb],
        tab: str = "",
        filing_href: str = "",
        benchmark_href: str = "",
        opened: OpenedTarget | None = None,
    ) -> Response:
        """Wrap one view in the shell, with the dashboard's tab strip when the page has one.

        A PAGE THAT BELONGS TO NEITHER VIEW GETS NO TAB STRIP AT ALL. The home page and the
        preflight page are not the dashboard; showing them a strip with both tabs inactive would
        say a person is somewhere they are not.
        """
        self._record_opened(request, opened)
        return html(
            layout(
                title=title,
                panel=panel,
                main=main,
                run_id=run_id,
                collapsed=self._panel_collapsed(request),
                https=self.policy.https,
                crumbs=crumbs,
                tab_strip=(
                    tabs(tab, filing_href=filing_href, benchmark_href=benchmark_href) if tab else ""
                ),
            )
        )

    def _benchmark_href(self, cik: str, accession: str) -> str:
        """The benchmark view of one filing, or empty when that filing has no benchmark truth.

        CHECKED RATHER THAN ASSUMED. Only filings named in the supplied benchmark contract have an
        inventory and a truth document, and a tab that 404s is worse than one that is visibly
        unavailable.
        """
        return (
            url("benchmark", cik, accession, "models")
            if self.service.catalog.filing(cik, accession) is not None
            else ""
        )

    def _panel(self, request: Request, *, subject: PanelContext | None = None) -> str:
        """The left panel: global nav, a mode strip, and either search or the review menu.

        THE MODE IS A FUNCTION OF THE ROUTE, NEVER OF A COOKIE. `nav.panel_mode` reads the
        parameters the router already matched, so a panel showing a review menu is on a page that
        named a parse. A shared URL reproduces the same panel and the whole thing renders with
        scripting disabled.

        `?panel_mode=search` FORCES SEARCH AND IS THE ONLY OVERRIDE. It does not claim to preserve
        the entity and model selections: this panel is rebuilt from the query string, and a job URL
        carries none of those keys, so the form comes back empty and says so. Pretending otherwise
        would be the more confusing failure.

        THE KEY IS `panel_mode`, NOT `panel`. `panel` is the collapse state and has been since
        before this existed; one key doing both would force a reader to choose between collapsing
        the panel and choosing what it shows.
        """
        mode = panel_mode(request.path, request.params, request.q("panel_mode"))
        collapse_href = with_query(request.path, request.query, panel="closed")
        search_href = with_query(request.path, request.query, panel_mode="search")
        review_href = with_query(request.path, request.query, panel_mode="review")
        body = (
            review_menu(
                subject,
                csrf=self._csrf(request),
                path=request.path,
                query=request.query,
            )
            if subject is not None and mode != "search"
            else self._search_body(request)
        )
        return panel_shell(
            active=active_section(request.path),
            # SUPPLIED ON EVERY PAGE, NOT ONLY THE ONES WITH A SEARCH FORM. Reading it costs one
            # already-open journal; the figure bounds every billable control in this application.
            spend={
                "spent_usd": str(self.service.journal.spent_usd),
                "ceiling_usd": str(self.service.journal.ceiling_usd),
            },
            collapse_href=collapse_href,
            mode=mode,
            search_href=search_href,
            review_href=review_href,
            review_reason=(
                "" if subject is not None else "no parse or filing is open on this page"
            ),
            body=body,
        )

    def _search_body(self, request: Request) -> str:
        """The search form, rebuilt from the query string so state survives a reload."""
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
        # THE HUB SHARES ITS URL WITH THE VERDICT IT LEADS TO. `Router.resolve` is method-aware and
        # answers 405 with an Allow header on a mismatch, so one path carrying both a GET and a
        # POST is exactly what it is built for.
        r.add("GET", "/runs/{run_id}/jobs/{job_id}/review", self.parse_hub_html, name="parseHub")
        # THE READ VIEW THE PANEL LINKS TO. `POST .../judgements` records a classification and
        # already existed; without a GET beside it, every menu entry pointing here was a 405.
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/judgements",
            self.benchmark_judgements_html,
            name="benchmarkJudgementsPage",
        )
        r.add("GET", "/filings", self.filings_html, name="filingsIndexPage")
        # `/runs` is a POST collection. A reader who typed it, or followed the run-id bar's own
        # wording, used to get a bare 405; they now get the list they were looking for.
        r.add("GET", "/runs", self.runs_redirect, name="runsRedirect")
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
        # EVERY RECORDED PARSE OF THIS FILING, IN RECORDED ORDER. Also filing-scoped, and for the
        # same reason: the classification above is the denominator, and these are the parses
        # measured against it. Neither route sorts, ranks or recommends — `rules.md` section 21
        # rule 14 — and neither invokes anything.
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/models",
            self.benchmark_models_html,
            name="benchmarkModelComparisonPage",
        )
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/compare",
            self.benchmark_compare_html,
            name="benchmarkCompareParsesPage",
        )
        r.add(
            "GET",
            "/benchmark/{cik}/{accession}/models/{run_id}",
            self.benchmark_model_run_html,
            name="benchmarkModelRunPage",
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
        # NOTHING TO SIGN IN TO. When this instance is PUBLISHED without authentication there is no
        # secret to present and no session to obtain, so the form would be a control that cannot do
        # anything. Sending the visitor where they were going is the honest answer.
        #
        # SCOPED TO THAT POSTURE AND NOT TO "authentication is not required". A loopback developer
        # instance also requires none, and it has always served this page; turning it into a
        # redirect there would change a working local tool to fix a remote one.
        if self.policy.authentication_disabled:
            return redirect("/")
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
                crumbs=(),
                panel="",
                main=body,
                run_id=None,
                collapsed=True,
                https=self.policy.https,
            )
        )

    def sign_in(self, request: Request) -> Response:
        if self.policy.authentication_disabled:
            return redirect("/")
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
                    crumbs=self._home_crumbs(Crumb("Cost preflight")),
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
            crumbs=self._home_crumbs(Crumb("Cost preflight")),
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
            crumbs=[Crumb("Home")],
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
            crumbs=self._run_crumbs(run_id),
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
            for poll in range(EVENT_STREAM_POLLS):
                # A WATCH SLEEPS BETWEEN LOOKS. WITHOUT THIS IT IS A SPIN, and the bound above is a
                # count rather than a duration — 600 polls of a busy run is 600 directory listings
                # and 600 full job loads as fast as the disk answers, on one core, for as long as
                # events keep arriving. It never showed on this instance because every stored run
                # is terminal and the loop exits on its first pass; it would appear during exactly
                # the parse a reviewer opens this stream to watch. The sleep is FIRST-ITERATION
                # FREE so an idle reconnect still answers immediately.
                if poll:
                    time.sleep(EVENT_STREAM_POLL_SECONDS)
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

        # IDENTIFIERS, NOT RECORDS. This page needs to know whether the parse has calls at all and
        # how many; opening all 123 task documents of one filing's parse to answer that cost 2.5
        # seconds against 0.02 to list them, and nothing on this page reads a task's body.
        task_count = len(self.service.store.list_task_ids(run_id, job_id))
        # AN ASSEMBLY WITH NO PART IS NOT AN ASSEMBLY TO SHOW. A parse whose plan call returned no
        # part still writes an assembly record — `part_count: 0`, `node_count: 0` — and rendering
        # it would put an empty index on the page in place of the sentence explaining why there is
        # nothing. The sentence is the more useful of the two.
        # THE EXACT BYTES OF EACH OPTIONAL STAGE, read from the evidence the stage preserved.
        # A stage that failed has no evidence and renders its error instead; a role the user left
        # blank has no entry at all and renders nothing.
        stage_texts = {
            role: self.service.store.get_evidence_text(run_id, job_id, str(info["evidence"]))
            for role, info in (job.stages or {}).items()
            if info.get("evidence")
            and self.service.store.has_evidence(run_id, job_id, str(info["evidence"]))
        }
        assembled = self.service.store.load_assembly(run_id, job_id)
        if assembled is not None and not (assembled.get("parts") or []):
            assembled = None

        return self._page(
            request,
            title=f"{job.form_as_filed} {job.accession}",
            crumbs=self._job_crumbs(job, Crumb("Response")),
            opened=self._opened_target_for_job(job, item=f"read-{view}"),
            tab=FILING_TAB,
            filing_href=url("runs", run_id, "jobs", job.job_id),
            # The benchmark view of the SAME filing. A job whose filing nobody has benchmarked
            # gets an empty href and the tab renders disabled rather than 404ing on click.
            benchmark_href=self._benchmark_href(job.cik, job.accession),
            panel=self._panel(request, subject=self._parse_context(job, item=f"read-{view}")),
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
                # A MULTIPART PARSE HAS NO JOB-LEVEL RESPONSE, AND THAT IS NOT A FAILURE. Every
                # response belongs to a task, so `response-visible.txt` is absent here by design.
                # The page used to report that absence as an unreadable YAML document and then show
                # an empty block of "exact bytes"; it now says where the responses actually are.
                responses_live_on_tasks=bool(task_count),
                # THE ASSEMBLED PARSE IS THE PARSED HALF OF A MULTIPART JOB'S SIDE-BY-SIDE. It is
                # loaded here rather than inferred in the renderer, and it is None when a parse
                # never reached assembly — a job whose plan produced no part has nothing to show,
                # and `parsed_pane` says so rather than rendering an empty index as content.
                assembly=assembled,
                stage_texts=stage_texts,
                # GATHERED ACROSS THE TASKS FOR THE SAME REASON. A multipart job's own `attempts`
                # is empty, so an invocation card reading only that could not tell a Bedrock call
                # from a mock one — and it was printing a model, a region and a USD figure for
                # both.
                attempt_providers=self._attempt_providers(job, assembled, task_count),
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

    def _superseded(self, tasks: list[Any]) -> dict[str, str]:
        """task_id -> the task whose artifact currently holds its content, when one supersedes it.

        RESOLVED THROUGH `packages/multipart/effective.py` RATHER THAN GUESSED. A part whose
        response would not parse and whose format repair succeeded is READ from the repair; the
        original is preserved, still linked and still reachable. A reader who opened the empty
        original and never opened the repair has not read that part, and the counts say so.
        """
        try:
            effective = resolve_effective(
                list(tasks),
                part_types=PART_TYPES,
                repair_type=TaskType.FORMAT_REPAIR,
                succeeded_state=TaskState.SUCCEEDED,
            )
        except Exception:  # noqa: BLE001 - a display aid never fails the page
            return {}
        found: dict[str, str] = {}
        for task in tasks:
            if task.task_type not in PART_TYPES:
                continue
            source = effective.effective(task)
            if source.task_id != task.task_id:
                found[task.task_id] = source.task_id
        return found

    def _opened_counts(self, tasks: list[Any], opened: dict[str, frozenset[str]]) -> dict[str, str]:
        """The one sentence the hub and the panel both show above a list of calls."""
        items = tuple(t.task_id for t in tasks)
        fingerprints = {
            t.task_id: attention.fingerprint(t.idempotency, t.state.value, len(t.attempts or ()))
            for t in tasks
        }
        return {
            "calls": counts_sentence(
                counts(items=items, fingerprints=fingerprints, opened=opened), noun="calls"
            )
        }

    def _parse_context(self, job: Any, *, tasks: list[Any] | None = None, item: str = "") -> Any:
        """Everything the review menu renders from, as plain values.

        THE HANDLER LOADS; THE PANEL RENDERS. `packages/review_web/panel.py` may not reach a
        service, an inventory or the store, so every figure it shows has to arrive here — and only
        figures that are cheap to obtain arrive at all.
        """
        rows: tuple[Any, ...] = ()
        opened: dict[str, frozenset[str]] = {}
        if tasks is not None:
            superseded = self._superseded(tasks)
            rows = tuple(
                TaskRow(
                    task_id=t.task_id,
                    part_id=t.part_id or "",
                    task_type=t.task_type.value,
                    state=t.state.value,
                    order=t.order,
                    depth=t.depth,
                    attempt_count=len(t.attempts or ()),
                    idempotency=t.idempotency or "",
                    superseded_by=superseded.get(t.task_id, ""),
                    fingerprint=attention.fingerprint(
                        t.idempotency, t.state.value, len(t.attempts or ())
                    ),
                )
                for t in tasks
            )
            opened = self._opened(self._job_prefix(job.parent_run_id, job.job_id))
        return PanelContext(
            subject="parse",
            run_id=job.parent_run_id,
            job_id=job.job_id,
            form_as_filed=job.form_as_filed,
            accession=job.accession,
            cik=job.cik,
            issuer_label=job.issuer_label,
            model_label=job.routing.label,
            strategy=job.strategy or "single_response",
            created_at=job.created_at,
            review_state=job.review_state.value,
            benchmark_held=self.service.catalog.filing(job.cik, job.accession) is not None,
            session=job.multipart or {},
            assembly=self.service.store.load_assembly(job.parent_run_id, job.job_id),
            tasks=rows,
            opened=opened,
            current_item=item,
        )

    def _filing_context(self, cik: str, accession: str, *, item: str = "") -> Any:
        """The filing-scoped review menu's inputs.

        NO PARSE LIST HERE. Resolving every recorded parse of a filing means walking every run's
        job manifests, and the two pages that already do it (the comparison and one model's
        ledger) pass their own. Doing it on the spans page would put that walk behind a link nobody
        followed for it.
        """
        return PanelContext(
            subject="filing",
            cik=cik,
            accession=accession,
            benchmark_held=self.service.catalog.filing(cik, accession) is not None,
            opened=self._opened(self._filing_prefix(cik, accession)),
            current_item=item,
        )

    def _filings_with_evidence(self) -> list[dict[str, Any]]:
        """Every filing some stored job names, newest job first, deduplicated by accession."""
        found: dict[tuple[str, str], dict[str, Any]] = {}
        for run_id in self.service.store.list_run_ids():
            for job in self.service.store.load_jobs(run_id):
                key = (job.cik, job.accession)
                entry = found.setdefault(
                    key,
                    {
                        "cik": job.cik,
                        "accession": job.accession,
                        "form_as_filed": job.form_as_filed,
                        "issuer_label": job.issuer_label,
                        "parses": 0,
                        "benchmark_href": self._benchmark_href(job.cik, job.accession),
                    },
                )
                entry["parses"] = int(entry["parses"]) + 1
        return sorted(found.values(), key=lambda f: (str(f["issuer_label"]), str(f["accession"])))

    # --- the parse hub, and the two index pages the nav points at -----------------------------

    def parse_hub_html(self, request: Request) -> Response:
        """One parse, and every way of examining it. The page the whole review surface is for.

        THE URL WHERE YOU RECORD A VERDICT IS THE URL WHERE YOU DECIDE ONE. `POST` on this same
        path already sets the review state; the `GET` added here is the evidence that should
        precede it.
        """
        run_id, job_id = request.params["run_id"], request.params["job_id"]
        run = self.service.store.load_run(run_id)
        job = self.service.store.load_job(run_id, job_id)
        tasks = self.service.store.load_tasks(run_id, job_id)
        prefix = self._job_prefix(run_id, job_id)
        opened = self._opened(prefix)
        rows = [t.to_mapping() for t in tasks]
        superseded = self._superseded(tasks)
        return self._page(
            request,
            title=f"Is this parse correct? {job.accession}",
            crumbs=self._job_crumbs(job),
            panel=self._panel(request, subject=self._parse_context(job, tasks=tasks, item="hub")),
            main=hub(
                run=run.to_mapping(),
                job=job.to_mapping(),
                session=job.multipart or {},
                assembly=self.service.store.load_assembly(run_id, job_id),
                tasks=rows,
                superseded_by=superseded,
                comments=[c.to_mapping() for c in self.service.store.list_comments(run_id)],
                opened=opened,
                opened_counts=self._opened_counts(tasks, opened),
                benchmark_held=self.service.catalog.filing(job.cik, job.accession) is not None,
                csrf=self._csrf(request),
                permitted_reviews=sorted(
                    s.value for s in permitted_review_transitions(job.review_state)
                ),
                base_query=request.query,
            ),
            run_id=run_id,
            tab=FILING_TAB,
            filing_href=url("runs", run_id, "jobs", job_id, "review"),
            benchmark_href=self._benchmark_href(job.cik, job.accession),
            opened=self._opened_target_for_job(job, item="hub"),
        )

    def filings_html(self, request: Request) -> Response:
        """Every filing this instance holds evidence about."""
        return self._page(
            request,
            title="Filings",
            crumbs=[Crumb("Filings")],
            panel=self._panel(request),
            main=filings_index(filings=self._filings_with_evidence()),
            run_id=None,
        )

    def benchmark_judgements_html(self, request: Request) -> Response:
        """Every human classification recorded for one filing, superseded versions included.

        NOTHING IS OVERWRITTEN, SO THE PAGE SHOWS THE HISTORY. A truth document is superseded by a
        later version and both are kept; a page that showed only the current one would make a
        revised judgement look like the only judgement there had ever been.
        """
        found, truth, versions = self._for_display(request)
        return self._benchmark_page(
            request,
            title=f"Judgements {found.filing.accession}",
            crumbs=self._filing_crumbs(
                found.filing.cik,
                found.filing.accession,
                found.filing.form_as_filed,
                Crumb("Judgements"),
            ),
            main=judgements_page(
                filing=found.filing.to_mapping(),
                versions=versions,
                documents=[truth.to_mapping()],
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="judgements",
                stamp=found.inventory.source_set_sha256,
            ),
        )

    def runs_redirect(self, request: Request) -> Response:
        """`/runs` is a POST collection. A reader who typed it gets the list, not a 405."""
        return Response(status=303, body=b"", headers={"Location": "/"})

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
            crumbs=self._job_crumbs(job, Crumb("Calls")),
            opened=self._opened_target_for_job(job, item="hierarchy"),
            panel=self._panel(
                request,
                subject=self._parse_context(
                    job, tasks=self.service.store.load_tasks(run_id, job_id), item="hierarchy"
                ),
            ),
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
            crumbs=self._job_crumbs(
                self.service.store.load_job(run_id, job_id), Crumb("Assembled")
            ),
            opened=self._opened_target_for_job(
                self.service.store.load_job(run_id, job_id), item="assembled"
            ),
            panel=self._panel(
                request,
                subject=self._parse_context(
                    self.service.store.load_job(run_id, job_id), item="assembled"
                ),
            ),
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
            crumbs=self._job_crumbs(
                job,
                Crumb("Calls", url("runs", run_id, "jobs", job_id, "multipart")),
                Crumb(task.part_id or task.task_id),
            ),
            opened=self._opened_target_for_task(job, task),
            panel=self._panel(
                request,
                subject=self._parse_context(
                    job,
                    tasks=self.service.store.load_tasks(run_id, job_id),
                    item=task.task_id,
                ),
            ),
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

    def _benchmark_page(
        self,
        request: Request,
        *,
        title: str,
        main: str,
        crumbs: Sequence[Crumb],
        opened: OpenedTarget | None = None,
    ) -> Response:
        """A benchmark page carries NO run identifier, because it belongs to no run.

        `_page` anchors the parent run bar to the viewport, and a filing-scoped page showing the
        identifier of whichever run was last opened would invite exactly the wrong reading: that
        this classification describes that run.
        """
        cik = request.params.get("cik", "")
        accession = request.params.get("accession", "")
        self._record_opened(request, opened)
        return html(
            layout(
                title=title,
                panel=self._panel(
                    request,
                    subject=self._filing_context(
                        cik, accession, item=opened.item if opened else ""
                    ),
                ),
                main=main,
                run_id=None,
                collapsed=self._panel_collapsed(request),
                https=self.policy.https,
                crumbs=crumbs,
                # THE TOGGLE WORKS IN BOTH DIRECTIONS OR IT IS NOT A TOGGLE. The filing side points
                # at the most recent run of THIS filing; when nothing has parsed it, the tab is
                # disabled rather than pointing somewhere that will not load.
                tab_strip=tabs(
                    BENCHMARK_TAB,
                    filing_href=self._latest_job_href(cik, accession),
                    benchmark_href=url("benchmark", cik, accession, "models"),
                ),
            )
        )

    def _latest_job_href(self, cik: str, accession: str) -> str:
        """The most recently created child job for one filing, or empty when there is none."""
        newest: tuple[str, str, str] | None = None
        for run_id in self.service.store.list_run_ids():
            for job in self.service.store.load_jobs(run_id):
                if job.cik != cik or job.accession != accession:
                    continue
                stamp = getattr(job, "created_at", "") or ""
                if newest is None or stamp >= newest[0]:
                    newest = (stamp, run_id, job.job_id)
        return url("runs", newest[1], "jobs", newest[2]) if newest else ""

    def benchmark_html(self, request: Request) -> Response:
        found, truth, versions = self._for_display(request)
        return self._benchmark_page(
            request,
            title=f"Completeness benchmark {found.filing.accession}",
            crumbs=self._filing_crumbs(
                found.filing.cik, found.filing.accession, found.filing.form_as_filed
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="overview",
                stamp=found.inventory.source_set_sha256,
            ),
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
            crumbs=self._filing_crumbs(
                found.filing.cik,
                found.filing.accession,
                found.filing.form_as_filed,
                Crumb("Source inventory"),
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="inventory",
                stamp=found.inventory.source_set_sha256,
            ),
            main=inventory_page(inventory=found.inventory, truth=truth),
        )

    def benchmark_spans_html(self, request: Request) -> Response:
        found, truth, _ = self._for_display(request)
        offset = request.q("start")
        return self._benchmark_page(
            request,
            title=f"Spans {found.filing.accession}",
            crumbs=self._filing_crumbs(
                found.filing.cik, found.filing.accession, found.filing.form_as_filed, Crumb("Spans")
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="spans",
                stamp=found.inventory.source_set_sha256,
            ),
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
            crumbs=self._filing_crumbs(
                found.filing.cik,
                found.filing.accession,
                found.filing.form_as_filed,
                Crumb("Tables"),
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="tables",
                stamp=found.inventory.source_set_sha256,
            ),
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
            crumbs=self._filing_crumbs(
                found.filing.cik,
                found.filing.accession,
                found.filing.form_as_filed,
                Crumb("Images"),
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="images",
                stamp=found.inventory.source_set_sha256,
            ),
            main=images_page(inventory=found.inventory, truth=truth, csrf=self._csrf(request)),
        )

    def benchmark_models_html(self, request: Request) -> Response:
        """Every run recorded against this filing, measured against one shared denominator.

        NOTHING HERE IS SORTED, RANKED OR SCORED, and the ordering is not the renderer's choice
        either: the service returns the runs in the order they were created and this handler
        passes them through. `rules.md` section 21 rule 14 forbids selecting a parser, and a page
        that reordered the rows by any figure on them would be making that selection for the
        reader.
        """
        found, truth, _ = self._for_display(request)
        return self._benchmark_page(
            request,
            title=f"Model runs {found.filing.accession}",
            crumbs=self._filing_crumbs(
                found.filing.cik,
                found.filing.accession,
                found.filing.form_as_filed,
                Crumb("Parses"),
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item="models",
                stamp=found.inventory.source_set_sha256,
            ),
            main=model_comparison_page(
                inventory=found.inventory,
                truth=truth,
                runs=self.service.measured_runs(found, truth),
                issuer_label=found.filing.issuer_label,
            ),
        )

    def benchmark_model_run_html(self, request: Request) -> Response:
        """One recorded parse of this filing in full: gate, claims, omissions, tables, unresolved.

        A run identifier naming no job against THIS filing is a 404 rather than a redirect to the
        run itself. The page's every figure is computed against this filing's denominator, and
        answering with a parse of another filing would present a ledger measured against bytes the
        reviewer is not looking at.
        """
        found, truth, _ = self._for_display(request)
        run = self.service.measured_run(found, truth, request.params["run_id"])
        if run is None:
            return as_json(
                {
                    "code": "not_found",
                    "message": (
                        "no run with that identifier is recorded against this filing. A run that "
                        "parsed another filing is measured against another denominator and is not "
                        "shown here."
                    ),
                },
                status=404,
            )
        return self._benchmark_page(
            request,
            title=f"{run.model_label} — {found.filing.accession}",
            crumbs=self._filing_crumbs(
                found.filing.cik,
                found.filing.accession,
                found.filing.form_as_filed,
                Crumb(
                    "Parses", url("benchmark", found.filing.cik, found.filing.accession, "models")
                ),
                Crumb(run.model_label),
            ),
            opened=self._opened_target_for_filing(
                found.filing.cik,
                found.filing.accession,
                item=run.run_id,
                stamp=found.inventory.source_set_sha256,
            ),
            main=model_run_page(inventory=found.inventory, truth=truth, run=run),
        )

    # --- two parses of one filing, side by side --------------------------------------------------

    def _parses_of(self, cik: str, accession: str) -> list[dict[str, Any]]:
        """Every stored parse of one accession, in the order the store lists runs.

        NEVER ORDERED BY A FIGURE. The node count is carried so a reader can see it, not so the
        list can be ranked — `rules.md` section 21 rule 14. A parse that produced nothing stays in
        the list, because "this model returned nothing for this filing" is a comparison result.
        """
        found: list[dict[str, Any]] = []
        for run_id in self.service.store.list_run_ids():
            for job in self.service.store.load_jobs(run_id):
                if job.cik != cik or job.accession != accession:
                    continue
                try:
                    assembly = self.service.store.load_assembly(run_id, job.job_id)
                except Exception:  # noqa: BLE001 - a parse with no assembly is still a parse
                    assembly = None
                found.append(
                    {
                        "run_id": run_id,
                        "job_id": job.job_id,
                        "label": job.routing.label,
                        "nodes": int((assembly or {}).get("node_count") or 0),
                        "assembly": assembly,
                        "job": job,
                    }
                )
        return found

    def _rendered_parse(self, entry: dict[str, Any] | None) -> dict[str, Any]:
        """One side of the comparison, already rendered, or a sentence saying why there is none."""
        if entry is None:
            return {"label": "nothing selected", "parsed": "", "note": "choose a parse above"}
        job = entry["job"]
        base = ("runs", entry["run_id"], "jobs", job.job_id)
        assembly = entry["assembly"]
        if assembly and (assembly.get("parts") or []):
            parsed = assembled_pane(base=base, assembly=assembly)
            note = f"{entry['nodes']} node(s) — run {entry['run_id']}"
        else:
            parsed = parsed_pane(
                base=base,
                view="side-by-side",
                parsed=None,
                outcomes_by_node={},
                raw_response="",
                responses_live_on_tasks=bool(
                    self.service.store.list_task_ids(entry["run_id"], job.job_id)
                ),
            )
            note = f"no parsed content — run {entry['run_id']}"
        return {"label": entry["label"], "parsed": parsed, "note": note, "run_id": entry["run_id"]}

    def benchmark_compare_html(self, request: Request) -> Response:
        """Four panes: the preserved filing beside each of two models' parses of it."""
        found, _, _ = self._for_display(request)
        cik, accession = found.filing.cik, found.filing.accession
        parses = self._parses_of(cik, accession)
        by_run = {p["run_id"]: p for p in parses}
        # A REQUESTED RUN THAT IS NOT A PARSE OF THIS FILING IS IGNORED, never rendered. The two
        # identifiers are query text and the only ones honoured are those this page already listed.
        left = by_run.get(request.q("a")) or (parses[0] if parses else None)
        right = by_run.get(request.q("b")) or (parses[1] if len(parses) > 1 else None)

        filename, source_text = "", ""
        if left is not None:
            names = self._artifact_names(left["job"])
            filename = names[0] if names else ""
            source_text = self._artifact_text(left["run_id"], left["job"], filename)

        return self._page(
            request,
            title=f"Compare parses {accession}",
            crumbs=self._filing_crumbs(
                cik, accession, found.filing.form_as_filed, Crumb("Compare")
            ),
            tab=BENCHMARK_TAB,
            filing_href="",
            benchmark_href=url("benchmark", cik, accession),
            panel=self._panel(request),
            run_id=None,
            main=comparison_panes(
                cik=cik,
                accession=accession,
                issuer_label=found.filing.issuer_label,
                form_as_filed=found.filing.form_as_filed,
                filename=filename,
                source_text=source_text,
                left=self._rendered_parse(left),
                right=self._rendered_parse(right),
                choices=[
                    {"run_id": p["run_id"], "label": p["label"], "nodes": p["nodes"]}
                    for p in parses
                ],
            ),
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

    @staticmethod
    def _panel_collapsed(request: Request) -> bool:
        """Whether the left panel should render collapsed.

        TWO SOURCES, AND THE EXPLICIT ONE WINS. `?panel=` is a deliberate act on this request — a
        no-script reader clicking the link, or a shared URL — so it decides. Absent that, the
        reader's remembered preference is read from the cookie the toggle writes.

        WHY A COOKIE AND NOT THE QUERY PARAMETER ALONE. The parameter belonged to one URL, so
        collapsing the panel and then following any link brought it straight back. That read as the
        collapse not working at all, which is what it amounted to.
        """
        asked = request.q("panel")
        if asked:
            return asked == "closed"
        return cookie_value(request, "kopexx_panel") == "closed"

    def handle(self, request: Request) -> Response:
        """Check the host, route, authorize, check CSRF, and turn a failure into an honest status.

        THE HOST CHECK COMES FIRST AND HAS NO EXEMPTIONS. `/health` and `/sign-in` skip
        AUTHENTICATION because one must answer a probe and the other is how you authenticate; that
        is not a reason to answer a request that reached this process by an address it was never
        published under. A sign-in form served to an unrecognised Host is precisely the request a
        rebinding attack needs.
        """
        wrong_host = self.policy.check_host(request)
        if wrong_host is not None:
            return self.policy.decorate(wrong_host)
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
