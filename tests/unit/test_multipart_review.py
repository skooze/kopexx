"""The multipart review surface: every new route, and every value it must escape or refuse.

HERMETIC AND SOCKETLESS, for the same reason the Phase 2 surface is. Every route below is exercised
by handing `ReviewApp.handle` a `Request` and reading the `Response`. No port, no timeout, no flake.

WHAT IS ACTUALLY UNDER TEST. Not that a page renders; that is arithmetic. The subject is what this
surface must REFUSE and what it must never lose:

    a MODEL-CHOSEN part identifier is escaped, never interpreted, and never reaches a storage key
    a queue action with no CSRF token is refused
    an unrecognised queue action is refused rather than becoming the nearest thing that spends
    a truncated call is shown as a branch with its cap, its partial output and its replanning
    the assembled view says it is an INDEX and claims no completeness
    the thirty historical single-response jobs still open, and report having no tasks
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from packages.evaluation_store import EvaluationStore, TaskState, TaskType
from packages.llm_gateway import parse_yaml
from packages.llm_gateway.providers.base import ModelProvider, ModelRequest, ModelResponse
from packages.llm_gateway.token_counter import estimate_tokens
from packages.model_catalog import load_snapshot
from packages.orchestrator import (
    MULTIPART_STRATEGY,
    SINGLE_RESPONSE_STRATEGY,
    CorpusFilingCatalog,
    InlineWorker,
    MultipartSettings,
    ParserReviewService,
    RunRequest,
    SpendJournal,
)
from packages.prompt_registry import PromptRegistry
from packages.review_api import (
    CSRF_FIELD,
    Response,
    ReviewApp,
    SecurityPolicy,
    build_request,
)
from packages.source_transport import ManifestInventory, PreservedObject, RefusingFetcher
from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_text

CIK = "0000000001"
ACCESSION = "0000000001-24-000001"
REGION = "region-one"
PARSER = "Parser One"
DEV_SECRET = "a-sufficiently-long-development-secret"

#: A model-chosen part identifier carrying characters that would be markup if a renderer ever
#: stopped escaping. It is deliberately not a "safe" identifier: the model names its own parts.
HOSTILE_PART_ID = 'Item <script>alert("x")</script> & more'
ANCHOR = "The anchor sentence appears exactly once in the preserved primary document."

SUBMISSION = (
    f"<SEC-DOCUMENT>{ACCESSION}.txt : 20240102\n"
    f"<SEC-HEADER>{ACCESSION}.hdr.sgml : 20240102\n"
    f"ACCESSION NUMBER:\t\t{ACCESSION}\n"
    "CONFORMED SUBMISSION TYPE:\t10-K\n"
    "PUBLIC DOCUMENT COUNT:\t\t1\n"
    "FILED AS OF DATE:\t\t20240102\n"
    "</SEC-HEADER>\n"
    "<DOCUMENT>\n<TYPE>10-K\n<SEQUENCE>1\n<DESCRIPTION>ANNUAL REPORT\n<TEXT>\n"
    f"SYNTHETIC ANNUAL REPORT BODY. {ANCHOR}\n"
    "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
).encode("ascii")

PLAN = f"""parse_plan_id: "plan-1"
parts:
  - part_id: {json.dumps(HOSTILE_PART_ID)}
    order: 1
    title: A Title The Filing Uses
    type: a model-chosen kind
    purpose: the whole thing
  - part_id: "second"
    order: 2
    title: Another Title
    type: another model-chosen kind
    purpose: the rest
unassigned: []
uncertainty: []
metadata: {{}}
"""

PART = f"""parse_plan_id: "plan-1"
part_id: {json.dumps(HOSTILE_PART_ID)}
status: complete
title: A Title The Filing Uses
type: a model-chosen kind
nodes:
  - id: "n1"
    order: 1
    type: a model-chosen node kind
    title: A Title The Filing Uses
    content: what it says
    source:
      - filename: {ACCESSION}.txt
        quote: "{ANCHOR}"
unresolved: []
coverage_summary: all of it
metadata: {{}}
"""

TRUNCATED = """parse_plan_id: "plan-1"
part_id: "second"
status: complete
title: Another Title
type: another model-chosen kind
nodes:
  - id: "n2"
    order: 1
    type: a kind
    title: Another Title
    content: cut off in the middle of
"""

REPLAN = """parse_plan_id: "plan-1"
part_id: "second"
covered_before_truncation: []
remaining:
  - what: all of it
proposed_subparts:
  - part_id: "second-a"
    order: 1
    title: A Portion
    type: a kind
    purpose: covers the whole of the original part
overlap_risk: none
uncertainty: []
metadata: {}
"""

#: The Phase 2 envelope, for the single-response job that runs beside the multipart one.
SINGLE_RESPONSE_PARSE = f"""artifact:
  produced_by: a scripted provider
document:
  - filename: {ACCESSION}.txt
nodes:
  - id: "s1"
    order: 1
    type: a model-chosen kind
    title: The Whole Filing
    content: what it says
    source:
      - filename: {ACCESSION}.txt
        quote: "{ANCHOR}"
unresolved: []
metadata: {{}}
"""

RECONCILE = """parse_plan_id: "plan-1"
cycle: 1
plan_complete: true
missing: []
duplicated: []
conflicting: []
additional_parts: []
replacement_parts: []
unresolvable: []
model_declared_coverage: everything is covered
metadata: {}
"""

SNAPSHOT = (
    'snapshot_version: "synthetic-1"\n'
    'verified_on: "2026-01-01"\n'
    f"verified_from_region: {REGION}\n"
    "price_source: a synthetic price list that bills nobody\n"
    'price_effective_date: "2026-01-01"\n'
    "price_currency: USD\n"
    "candidates:\n"
    f'  - label: "{PARSER}"\n'
    '    provider: "Synthetic"\n'
    '    model_id: "synthetic.parser"\n'
    f'    model_name: "{PARSER}"\n'
    '    version_qualifier: "v1"\n'
    '    mapping: "UNIQUE"\n'
    '    availability: "AVAILABLE"\n'
    '    access_status: "granted"\n'
    f'    verified_regions: ["{REGION}"]\n'
    "    inference_profile_required: false\n"
    "    inference_profile_id: null\n"
    "    text_input: true\n"
    "    image_input: false\n"
    "    multimodal: false\n"
    "    image_verified: false\n"
    "    context_tokens: 200000\n"
    "    max_output_tokens: 8000\n"
    "    emits_reasoning_before_answer: false\n"
    '    invocation_apis: ["Converse"]\n'
    "    streaming_supported: true\n"
    "    price_input_per_1k: 0.001\n"
    "    price_output_per_1k: 0.004\n"
    '    smoke_transport: "ACCEPTED"\n'
    '    smoke_instruction: "EXACT"\n'
    "    blocker: null\n"
    "    disabled_reason: null\n"
)

_ROLES = (
    ("parsing", "single"),
    ("parsing_multipart_plan", "plan"),
    ("parsing_multipart_part", "part"),
    ("parsing_multipart_replan", "replan"),
    ("parsing_multipart_reconcile", "reconcile"),
    ("parsing_multipart_gap", "gap"),
    ("parsing_multipart_format_repair", "repair"),
)


class ScriptedProvider(ModelProvider):
    """Answers by brief kind, so the test also proves the right part was asked for."""

    name = "scripted"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self._truncate = {"second"}

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        # A SINGLE-RESPONSE REQUEST IS PLAIN PROSE, NOT A YAML BRIEF, and that is the difference
        # this branch exists to notice. Both protocols run against the same store in this file so
        # the historical shape stays exercised beside the new one.
        try:
            brief = parse_yaml(request.user_content)
        except Exception:  # noqa: BLE001 - not a brief means the Phase 2 protocol
            brief = {}
        kind = brief.get("brief") if isinstance(brief, dict) else None
        if kind is None:
            return ModelResponse(
                text=SINGLE_RESPONSE_PARSE,
                input_tokens=estimate_tokens(request.user_content),
                output_tokens=estimate_tokens(SINGLE_RESPONSE_PARSE),
                model_id=request.model_id,
                provider=self.name,
            )
        stop = "end_turn"
        if kind == "planning":
            text = PLAN
        elif kind == "part":
            part_id = str(brief["requested_part"]["part_id"])
            if part_id in self._truncate:
                self._truncate.discard(part_id)
                text, stop = TRUNCATED, "max_tokens"
            elif part_id == HOSTILE_PART_ID:
                text = PART
            else:
                text = PART.replace(json.dumps(HOSTILE_PART_ID), json.dumps(part_id))
        elif kind == "replan":
            text = REPLAN
        else:
            text = RECONCILE
        return ModelResponse(
            text=text,
            input_tokens=estimate_tokens(request.user_content),
            output_tokens=estimate_tokens(text),
            model_id=request.model_id,
            provider=self.name,
            stop_reason=stop,
            truncated=stop == "max_tokens",
        )


@dataclass(frozen=True)
class Harness:
    store: EvaluationStore
    service: ParserReviewService
    worker: InlineWorker
    provider: ScriptedProvider


def _write_corpus(root: Path) -> tuple[Path, ManifestInventory]:
    path = root / "corpus" / f"{ACCESSION}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SUBMISSION)
    manifest = root / "corpus-manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "cik": CIK,
                    "accession": ACCESSION,
                    "form_as_filed": "10-K",
                    "filing_date": "2024-01-02",
                    "report_period": "2023-12-31",
                    "issuer_name_current": "Synthetic Issuer Company",
                    "tickers_current": ["SYN"],
                    "former_names": [],
                    "sic_description": "Synthetic",
                    "transport_era": "era",
                    "is_amendment": False,
                    "is_annual": True,
                    "form_variant": "10-K",
                    "package_file_count": 1,
                    "package_image_count": 0,
                    "primary_est_tokens_at_3_0": 500,
                    "files": [
                        {
                            "filename": f"{ACCESSION}.txt",
                            "sha256": sha256_bytes(SUBMISSION),
                            "raw_bytes": len(SUBMISSION),
                            "source_url": "",
                            "local_path": str(path),
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return manifest, ManifestInventory(
        {
            (CIK, ACCESSION): [
                PreservedObject(
                    filename=f"{ACCESSION}.txt",
                    sha256=sha256_bytes(SUBMISSION),
                    byte_count=len(SUBMISSION),
                    source_url="",
                    locator=str(path),
                    acquired_at="2026-01-01T00:00:00+00:00",
                    acquisition_method="synthetic",
                    reused=True,
                )
            ]
        }
    )


def _write_prompts(root: Path) -> PromptRegistry:
    directory = root / "prompts"
    directory.mkdir(parents=True, exist_ok=True)
    lines = ['schema_version: "prompt-versions-v1"', "prompts:"]
    for role, stem in _ROLES:
        text = f"A synthetic {stem} prompt. Return one YAML document.\n"
        (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
        lines.extend(
            [
                f"  - prompt_id: synthetic-{stem}",
                '    version: "1"',
                f"    file: {stem}.txt",
                f'    sha256: "{sha256_text(text)}"',
                '    created: "2026-01-01"',
                "    status: ACTIVE",
                f"    role: {role}",
                "    supersedes: null",
                "    superseded_by: null",
            ]
        )
    (directory / "versions.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return PromptRegistry.from_directory(directory)


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory) -> Harness:
    root = tmp_path_factory.mktemp("multipart-review")
    manifest, inventory = _write_corpus(root)
    objects = FilesystemObjectStore(root / "evaluation")
    store = EvaluationStore(objects)
    provider = ScriptedProvider()
    service = ParserReviewService(
        store=store,
        catalog=CorpusFilingCatalog.from_manifest(manifest),
        snapshot=load_snapshot(SNAPSHOT),
        prompts=_write_prompts(root),
        inventory=inventory,
        fetcher=RefusingFetcher(),
        provider=provider,
        journal=SpendJournal(
            objects, ceiling_usd=Decimal("5.00"), phase="test", phase_ceiling_usd=Decimal("5.00")
        ),
        preferred_region=REGION,
        author="evaluator",
        multipart_settings=MultipartSettings(filing_budget_usd=Decimal("4.00")),
    )
    return Harness(store=store, service=service, worker=InlineWorker(service), provider=provider)


@pytest.fixture(scope="module")
def app(harness: Harness) -> ReviewApp:
    return ReviewApp(
        service=harness.service,
        worker=harness.worker,
        policy=SecurityPolicy(loopback_only=True, dev_auth_secret=None),
    )


@pytest.fixture(scope="module")
def run(harness: Harness) -> tuple[str, str]:
    request = RunRequest(
        cik=CIK, parsing_label=PARSER, accessions=(ACCESSION,), strategy=MULTIPART_STRATEGY
    )
    created = harness.service.create_run(request)
    harness.worker.submit_run(created.run_id)
    return created.run_id, created.job_ids[0]


@pytest.fixture(scope="module")
def single_run(harness: Harness) -> tuple[str, str]:
    """A single-response job in the SAME store, so the historical shape stays exercised."""
    request = RunRequest(
        cik=CIK,
        parsing_label=PARSER,
        accessions=(ACCESSION,),
        strategy=SINGLE_RESPONSE_STRATEGY,
    )
    created = harness.service.create_run(request)
    harness.worker.submit_run(created.run_id)
    return created.run_id, created.job_ids[0]


def call(app: ReviewApp, method: str, path: str, *, body: bytes = b"") -> Response:
    return app.handle(
        build_request(
            method=method,
            raw_path=path,
            headers={"accept": "application/json"},
            body=body,
            client_host="127.0.0.1",
        )
    )


def html_call(app: ReviewApp, path: str) -> str:
    response = app.handle(
        build_request(
            method="GET",
            raw_path=path,
            headers={"accept": "text/html"},
            body=b"",
            client_host="127.0.0.1",
        )
    )
    assert response.status == 200, response.body[:400]
    return response.body.decode("utf-8")


# --- anti-vacuity --------------------------------------------------------------------------------


def test_the_fixture_really_ran_a_multipart_parse(harness: Harness, run: tuple[str, str]) -> None:
    tasks = harness.store.load_tasks(*run)
    assert len(tasks) >= 5, f"only {len(tasks)} task(s); every assertion below would be vacuous"
    assert any(t.state is TaskState.TRUNCATED for t in tasks), "no truncation branch to render"
    assert harness.store.load_assembly(*run) is not None


# --- the hierarchy page ---------------------------------------------------------------------------


def test_the_hierarchy_page_lists_every_call_in_the_models_own_order(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/multipart")
    assert "Multipart model-directed parse" in page
    assert "PLAN_PARSE" in page and "PARSE_PART" in page and "RECONCILE_PARSE" in page
    assert "plan-1" in page


def test_a_model_chosen_identifier_is_escaped_and_never_rendered_as_markup(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    """SECURITY-INVARIANT. A part identifier is a string a model wrote after reading a filing."""
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/multipart")
    assert "<script>alert" not in page, "a model-chosen identifier reached the browser as markup"
    assert "&lt;script&gt;alert" in page, "the identifier was dropped instead of escaped"


def test_a_truncated_call_is_shown_as_a_branch_with_its_cap_and_its_replanning(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/multipart")
    assert "reached the output limit" in page
    assert "is NOT merged into the parse" in page
    assert "REPLAN_TRUNCATED_PART" in page


def test_the_hierarchy_page_shows_all_three_ceilings(app: ReviewApp, run: tuple[str, str]) -> None:
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/multipart")
    assert "budget" in page and "Phase" in page and "remains" in page


def test_the_queue_controls_are_posts_and_carry_a_token_field(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    """A control that spends money must not be a link a browser can be made to follow."""
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/multipart")
    assert page.count('method="post"') >= 4
    assert f'name="{CSRF_FIELD}"' in page
    assert 'action="/runs/' in page and "/queue" in page


# --- one task ---------------------------------------------------------------------------------------


def test_a_task_page_shows_the_exact_request_and_the_exact_response(
    app: ReviewApp, harness: Harness, run: tuple[str, str]
) -> None:
    task = next(t for t in harness.store.load_tasks(*run) if t.task_type is TaskType.PARSE_PART)
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/tasks/{task.task_id}")
    assert "Exact request brief" in page
    assert "Exact model response" in page
    assert "brief: part" in page, "the compiled brief was not shown"


def test_a_truncated_task_page_states_the_cap_and_that_it_is_evidence(
    app: ReviewApp, harness: Harness, run: tuple[str, str]
) -> None:
    task = next(t for t in harness.store.load_tasks(*run) if t.state is TaskState.TRUNCATED)
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/tasks/{task.task_id}")
    assert "Output limit reached" in page
    assert "EVIDENCE ONLY" in page
    assert "cut off in the middle of" in page, "the exact partial response was not shown"


def test_a_task_page_offers_the_same_raw_parsed_and_side_by_side_views(
    app: ReviewApp, harness: Harness, run: tuple[str, str]
) -> None:
    task = next(t for t in harness.store.load_tasks(*run) if t.task_type is TaskType.PARSE_PART)
    base = f"/runs/{run[0]}/jobs/{run[1]}/tasks/{task.task_id}"
    for view in ("raw", "parsed", "side-by-side"):
        page = html_call(app, f"{base}?view={view}")
        assert "Raw source" in page or "Parsed" in page
    assert ANCHOR in html_call(app, f"{base}?view=raw"), "the preserved filing was not shown"


# --- the assembled view -------------------------------------------------------------------------------


def test_the_assembled_view_says_it_is_an_index_and_claims_no_completeness(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/assembled")
    assert "an INDEX over the exact model responses" in page
    assert "NOT a completeness verdict" in page
    assert "No title was renamed" in page


def test_the_assembled_view_uses_the_models_titles_and_links_back_to_its_responses(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    page = html_call(app, f"/runs/{run[0]}/jobs/{run[1]}/assembled")
    assert "A Title The Filing Uses" in page
    assert "open the exact response that produced this part" in page


# --- the JSON surface ----------------------------------------------------------------------------------


def test_the_task_list_route_returns_every_task_and_a_mechanical_summary(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    payload = json.loads(call(app, "GET", f"/api/runs/{run[0]}/jobs/{run[1]}/tasks").body)
    assert payload["summary"]["task_count"] == len(payload["results"])
    assert payload["summary"]["truncated"] == 1


def test_the_exact_response_route_serves_a_truncated_call_too(
    app: ReviewApp, harness: Harness, run: tuple[str, str]
) -> None:
    task = next(t for t in harness.store.load_tasks(*run) if t.state is TaskState.TRUNCATED)
    response = call(app, "GET", f"/api/runs/{run[0]}/jobs/{run[1]}/tasks/{task.task_id}/response")
    assert response.status == 200
    assert response.body.decode("utf-8") == TRUNCATED


def test_the_assembly_route_returns_four_separate_claims(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    payload = json.loads(call(app, "GET", f"/api/runs/{run[0]}/jobs/{run[1]}/assembly").body)
    for key in (
        "mechanically_assembled",
        "model_declared_complete",
        "reconciliation_unresolved",
        "human_review_required",
    ):
        assert key in payload
    assert payload["human_review_required"] is True


def test_an_unknown_task_identifier_is_a_not_found_and_not_a_stack_trace(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    response = call(app, "GET", f"/api/runs/{run[0]}/jobs/{run[1]}/tasks/tsk_{'z' * 26}")
    assert response.status == 404
    response = call(app, "GET", f"/api/runs/{run[0]}/jobs/{run[1]}/tasks/not-an-identifier")
    assert response.status == 404


# --- queue control --------------------------------------------------------------------------------------


def test_an_unrecognised_queue_action_is_refused_rather_than_becoming_one_that_spends(
    app: ReviewApp, run: tuple[str, str]
) -> None:
    response = call(
        app, "POST", f"/runs/{run[0]}/jobs/{run[1]}/queue", body=b"action=make_it_better"
    )
    assert response.status == 400
    assert b"no default" in response.body


def test_a_queue_action_without_a_token_is_refused_when_a_session_exists(
    harness: Harness, run: tuple[str, str]
) -> None:
    """CSRF applies wherever a session exists, which is every configuration beyond loopback."""
    guarded = ReviewApp(
        service=harness.service,
        worker=harness.worker,
        policy=SecurityPolicy(loopback_only=False, dev_auth_secret=DEV_SECRET),
    )
    session = guarded.policy.sessions.create()
    response = guarded.handle(
        build_request(
            method="POST",
            raw_path=f"/runs/{run[0]}/jobs/{run[1]}/queue",
            headers={
                "accept": "application/json",
                "cookie": f"kopexx_review_session={session.session_id}",
            },
            body=b"action=resume",
            client_host="10.0.0.5",
        )
    )
    assert response.status == 403
    assert b"csrf_failed" in response.body


def test_resume_and_unblock_report_what_they_reopened(app: ReviewApp, run: tuple[str, str]) -> None:
    for action in (b"action=resume", b"action=unblock"):
        response = call(app, "POST", f"/runs/{run[0]}/jobs/{run[1]}/queue", body=action)
        assert response.status == 200
        assert json.loads(response.body)


# --- the historical single-response shape ------------------------------------------------------------------


def test_a_single_response_job_still_opens_and_reports_having_no_multipart_work(
    app: ReviewApp, single_run: tuple[str, str]
) -> None:
    """The thirty preserved Phase 2 runs are exactly this shape and must keep working."""
    page = html_call(app, f"/runs/{single_run[0]}/jobs/{single_run[1]}")
    assert "Exact model response" in page
    assert "call hierarchy" not in page, (
        "a single-response job advertised a hierarchy it has none of"
    )

    hierarchy = html_call(app, f"/runs/{single_run[0]}/jobs/{single_run[1]}/multipart")
    assert "not yet produced" in hierarchy
    assert "No assembly has been written" in hierarchy

    assembly = call(app, "GET", f"/api/runs/{single_run[0]}/jobs/{single_run[1]}/assembly")
    assert assembly.status == 404


def test_the_run_page_names_the_protocol_of_each_child_job(
    app: ReviewApp, run: tuple[str, str], single_run: tuple[str, str]
) -> None:
    assert "multipart" in html_call(app, f"/runs/{run[0]}")
    assert "single_response" in html_call(app, f"/runs/{single_run[0]}")


def test_the_search_panel_offers_both_protocols_with_multipart_preselected(
    app: ReviewApp,
) -> None:
    page = html_call(app, "/")
    assert 'name="strategy"' in page
    assert 'value="multipart" selected' in page
    assert 'value="single_response"' in page


def test_an_unknown_strategy_is_refused_at_the_api_rather_than_silently_substituted(
    app: ReviewApp,
) -> None:
    response = app.handle(
        build_request(
            method="POST",
            raw_path="/api/preflight",
            headers={"accept": "application/json", "content-type": "application/json"},
            body=json.dumps(
                {"cik": CIK, "parsing_label": PARSER, "strategy": "multi-part"}
            ).encode(),
            client_host="127.0.0.1",
        )
    )
    assert response.status == 400
    assert b"no default" in response.body or b"not a parsing strategy" in response.body
