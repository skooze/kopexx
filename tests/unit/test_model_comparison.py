"""The model-comparison surface: what it must show, what it must escape, and what it must NOT do.

WHAT IS ACTUALLY UNDER TEST. Not that two pages render — that is arithmetic. The subject is the set
of properties this surface must hold or be actively harmful:

    NO SELECTION       `rules.md` section 21 rule 14 forbids choosing a parser, and a table ordered
                       by a computed figure IS that choice: whatever the caption says, the reader
                       takes the top row as the answer. The mutation proof below rewrites the
                       measured figures of every run and asserts the page's row order does not
                       move — so a future `sorted(runs, key=...)` fails the build rather than
                       quietly recommending a model.

    NO FALSE EMPTY     a run that failed at preflight or at the provider with zero parts is a row
                       stating what happened. Reporting `0 of N covered` for it would read as a
                       measurement of a model that never answered; hiding it would be worse.

    ESCAPING           every figure on these pages is derived from bytes SEC published or from what
                       a model wrote after reading them. The fixture filing carries a script
                       element written as character references, and it reaches the page as a
                       silently omitted span, as a table cell and as a coverage anchor.

    HONEST MISSES      an unknown run is a 404, and a filing with no recorded run says so rather
                       than rendering an empty table that reads as a measurement.

HERMETIC AND SOCKETLESS, like the rest of the review suite. Every route is exercised by handing
`ReviewApp.handle` a `Request` and reading the `Response` back. The corpus, the capability snapshot,
the prompt registry and the evaluation store are synthetic and live under `tmp_path`; the provider
is a scripted in-process object. Nothing reads a developer's environment, the research corpus, the
committed snapshot or any credential, and no model is invoked anywhere in this file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import pytest

from packages.completeness import BenchmarkTruth, SerializationState
from packages.evaluation_store import EvaluationStore
from packages.llm_gateway import ProviderError, parse_yaml
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
from packages.review_api import Response, ReviewApp, SecurityPolicy, build_request
from packages.review_web import model_comparison_page
from packages.source_transport import ManifestInventory, PreservedObject, RefusingFetcher
from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_text

CIK = "0000000042"
ACCESSION = "0000000042-24-000001"
UNPARSED_ACCESSION = "0000000042-24-000002"
ABSENT_ACCESSION = "0000000042-24-000099"
REGION = "region-one"
PARSER = "Parser One"
REFUSER = "Parser Two"
PRIMARY = "primary.htm"

#: THE HOSTILE PAYLOAD, AS A FILING WOULD CARRY IT. The source writes it as character references;
#: `HTMLParser` runs with `convert_charrefs`, so the inventory's span and cell text carry the
#: DECODED characters — and it is those that reach a page. A model quoting the filing back reaches
#: the page the same way, through a coverage anchor and a table cell.
HOSTILE_SOURCE = "&lt;script&gt;alert(&quot;omitted&quot;)&lt;/script&gt;"
HOSTILE_DECODED = '<script>alert("omitted")</script>'

#: Quoted by the scripted parse, so it becomes a COVERED span and the omission list is not the
#: whole filing. Present exactly once.
COVERED_SENTENCE = "The covered sentence occurs exactly once in the preserved primary document."

#: Never quoted by anything, so it is SILENTLY OMITTED and carries the hostile payload with it.
OMITTED_SENTENCE = f"An omitted disclosure carrying {HOSTILE_SOURCE} and nothing else."

PRIMARY_DOCUMENT = (
    "<html><head><title>Synthetic comparison filing</title></head><body>\n"
    f"<p>{COVERED_SENTENCE}</p>\n"
    f"<p>{OMITTED_SENTENCE}</p>\n"
    "<table><tr><th>Period</th><th>Amount</th></tr>"
    f"<tr><td>{HOSTILE_SOURCE}</td><td>1,234</td></tr></table>\n"
    "</body></html>\n"
).encode("ascii")

SUBMISSION = (
    f"<SEC-DOCUMENT>{ACCESSION}.txt : 20240102\n"
    f"<SEC-HEADER>{ACCESSION}.hdr.sgml : 20240102\n"
    f"ACCESSION NUMBER:\t\t{ACCESSION}\n"
    "CONFORMED SUBMISSION TYPE:\tANNUAL\n"
    "PUBLIC DOCUMENT COUNT:\t\t1\n"
    "FILED AS OF DATE:\t\t20240102\n"
    "</SEC-HEADER>\n"
    "<DOCUMENT>\n<TYPE>ANNUAL\n<SEQUENCE>1\n"
    f"<FILENAME>{PRIMARY}\n<DESCRIPTION>PRIMARY DOCUMENT\n<TEXT>\n"
    f"{PRIMARY_DOCUMENT.decode('ascii')}"
    "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
).encode("ascii")

#: The mechanical inventory's identifier for the one table element of the primary document, and
#: the span identifier of the disclosure nothing cites. Both are asserted against the measured
#: inventory below rather than trusted: an identifier scheme that moved would otherwise turn the
#: fabricated-cell and omitted-span assertions into assertions about nothing.
SOURCE_TABLE_ID = f"{PRIMARY}#t1"
OMITTED_SPAN_ID = f"{PRIMARY}#s3"

PLAN = """parse_plan_id: "plan-1"
parts:
  - part_id: "the-only-part"
    order: 1
    title: A Title The Model Chose
    type: a model-chosen kind
    purpose: the whole thing
unassigned: []
uncertainty: []
metadata: {}
"""

#: A part that covers ONE sentence, cites it, emits ONE structured table, and declares one item
#: unresolved. Every figure the comparison page shows has a non-zero source in here, so an
#: assertion about any of them means something.
PART = f"""parse_plan_id: "plan-1"
part_id: "the-only-part"
status: complete
title: A Title The Model Chose
type: a model-chosen kind
nodes:
  - id: "n1"
    order: 1
    type: a model-chosen node kind
    title: A Title The Model Chose
    content: what it says
    source:
      - filename: {PRIMARY}
        quote: "{COVERED_SENTENCE}"
coverage_claims:
  - member: {PRIMARY}
    start_anchor: "{COVERED_SENTENCE}"
    end_anchor: "{COVERED_SENTENCE}"
    purpose: the covered region
    unresolved: false
tables:
  - table_id: "t-1"
    title: A Table The Model Named
    type: a model-chosen table kind
    source_member: {PRIMARY}
    source_table_id: "{SOURCE_TABLE_ID}"
    rows:
      - - text: "Period"
          is_header: true
        - text: {json.dumps(HOSTILE_DECODED)}
      - - text: "1,234"
        - text: "a figure that is nowhere in the source"
unresolved:
  - where: "{PRIMARY}#s9999"
    why: the model said it could not resolve this
coverage_summary: one region of it
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
model_declared_coverage: what was asked for
metadata: {}
"""

SINGLE_RESPONSE_PARSE = f"""artifact:
  produced_by: a scripted provider
document:
  - filename: {PRIMARY}
nodes:
  - id: "s1"
    order: 1
    type: a model-chosen kind
    title: The Whole Filing
    content: what it says
    source:
      - filename: {PRIMARY}
        quote: "{COVERED_SENTENCE}"
unresolved: []
metadata: {{}}
"""


def _candidate(label: str, model_id: str) -> str:
    return (
        f'  - label: "{label}"\n'
        '    provider: "Synthetic"\n'
        f'    model_id: "{model_id}"\n'
        f'    model_name: "{label}"\n'
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
        '    invocation_apis: ["Converse"]\n'
        "    streaming_supported: true\n"
        "    price_input_per_1k: 0.001\n"
        "    price_output_per_1k: 0.004\n"
        '    smoke_transport: "ACCEPTED"\n'
        '    smoke_instruction: "EXACT"\n'
        "    blocker: null\n"
        "    disabled_reason: null\n"
    )


SNAPSHOT = (
    'snapshot_version: "synthetic-1"\n'
    'verified_on: "2026-01-01"\n'
    f"verified_from_region: {REGION}\n"
    "price_source: a synthetic price list that bills nobody\n"
    'price_effective_date: "2026-01-01"\n'
    "price_currency: USD\n"
    "candidates:\n"
    + _candidate(PARSER, "synthetic.parser-one")
    + _candidate(REFUSER, "synthetic.parser-two")
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
    """Answers by brief kind, and refuses outright for one of the two candidates.

    THE REFUSAL IS THE POINT OF THE SECOND CANDIDATE. Most preserved runs in this repository failed
    at the provider with zero parts, and a comparison page that crashed or silently hid them would
    be worse than useless. One model here always fails, so the "row that states what happened" is
    exercised beside a row that carries real figures.
    """

    name = "scripted"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if request.model_id == "synthetic.parser-two":
            raise ProviderError(
                "the scripted provider refused this invocation",
                retryable=False,
                provider=self.name,
            )
        try:
            brief = parse_yaml(request.user_content)
        except Exception:  # noqa: BLE001 - not a brief means the Phase 2 protocol
            brief = {}
        kind = brief.get("brief") if isinstance(brief, dict) else None
        if kind is None:
            text = SINGLE_RESPONSE_PARSE
        elif kind == "planning":
            text = PLAN
        elif kind == "part":
            text = PART
        else:
            text = RECONCILE
        return ModelResponse(
            text=text,
            input_tokens=estimate_tokens(request.user_content),
            output_tokens=estimate_tokens(text),
            model_id=request.model_id,
            provider=self.name,
            stop_reason="end_turn",
        )

    def count_tokens(self, text: str) -> int:
        return estimate_tokens(text)


@dataclass(frozen=True)
class Harness:
    store: EvaluationStore
    service: ParserReviewService
    worker: InlineWorker


def _filing(root: Path, accession: str) -> tuple[dict[str, object], list[PreservedObject]]:
    corpus = root / "corpus" / accession
    corpus.mkdir(parents=True, exist_ok=True)
    submission = SUBMISSION.replace(ACCESSION.encode(), accession.encode())
    members = {f"{accession}.txt": submission, PRIMARY: PRIMARY_DOCUMENT}
    preserved: list[PreservedObject] = []
    files: list[dict[str, object]] = []
    for filename, data in members.items():
        path = corpus / filename
        path.write_bytes(data)
        digest = sha256_bytes(data)
        preserved.append(
            PreservedObject(
                filename=filename,
                sha256=digest,
                byte_count=len(data),
                source_url="",
                locator=str(path),
                acquired_at="2026-01-01T00:00:00+00:00",
                acquisition_method="synthetic",
                reused=True,
            )
        )
        files.append(
            {
                "filename": filename,
                "sha256": digest,
                "raw_bytes": len(data),
                "source_url": "",
                "local_path": str(path),
            }
        )
    record: dict[str, object] = {
        "cik": CIK,
        "accession": accession,
        "form_as_filed": "ANNUAL",
        "filing_date": "2024-01-02",
        "report_period": "2023-12-31",
        "issuer_name_current": "Synthetic Comparison Issuer",
        "tickers_current": ["SYNC"],
        "former_names": [],
        "sic_description": "Synthetic",
        "transport_era": "addressable-members",
        "is_amendment": False,
        "is_annual": True,
        "form_variant": "ANNUAL",
        "package_file_count": len(files),
        "package_image_count": 0,
        "primary_est_tokens_at_3_0": 500,
        "files": files,
    }
    return record, preserved


def _write_corpus(root: Path) -> tuple[Path, ManifestInventory]:
    """Two filings: one that runs are recorded against, and one that nothing has ever parsed."""
    parsed, parsed_objects = _filing(root, ACCESSION)
    unparsed, unparsed_objects = _filing(root, UNPARSED_ACCESSION)
    manifest = root / "corpus-manifest.json"
    manifest.write_text(json.dumps([parsed, unparsed]), encoding="utf-8")
    return manifest, ManifestInventory(
        {(CIK, ACCESSION): parsed_objects, (CIK, UNPARSED_ACCESSION): unparsed_objects}
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
    root = tmp_path_factory.mktemp("model-comparison")
    manifest, inventory = _write_corpus(root)
    objects = FilesystemObjectStore(root / "evaluation")
    store = EvaluationStore(objects)
    service = ParserReviewService(
        store=store,
        catalog=CorpusFilingCatalog.from_manifest(manifest),
        snapshot=load_snapshot(SNAPSHOT),
        prompts=_write_prompts(root),
        inventory=inventory,
        fetcher=RefusingFetcher(),
        provider=ScriptedProvider(),
        journal=SpendJournal(
            objects, ceiling_usd=Decimal("5.00"), phase="test", phase_ceiling_usd=Decimal("5.00")
        ),
        preferred_region=REGION,
        author="evaluator",
        multipart_settings=MultipartSettings(filing_budget_usd=Decimal("4.00")),
    )
    return Harness(store=store, service=service, worker=InlineWorker(service))


@pytest.fixture(scope="module")
def runs(harness: Harness) -> tuple[str, str, str]:
    """Three recorded runs against one filing: multipart, single-response, and one that fails.

    Created in this order on purpose. The mutation proof below asserts the page keeps it whatever
    the figures say, and the failing run is created LAST so a page that quietly floated failures to
    the bottom would still pass — it has to be a genuine recorded order, not a coincidence.
    """
    created = []
    for label, strategy in (
        (PARSER, MULTIPART_STRATEGY),
        (PARSER, SINGLE_RESPONSE_STRATEGY),
        (REFUSER, MULTIPART_STRATEGY),
    ):
        run = harness.service.create_run(
            RunRequest(cik=CIK, parsing_label=label, accessions=(ACCESSION,), strategy=strategy)
        )
        harness.worker.submit_run(run.run_id)
        created.append(run.run_id)
    return created[0], created[1], created[2]


@pytest.fixture(scope="module")
def app(harness: Harness) -> ReviewApp:
    return ReviewApp(
        service=harness.service,
        worker=harness.worker,
        policy=SecurityPolicy(loopback_only=True, dev_auth_secret=None),
    )


def call(app: ReviewApp, path: str) -> Response:
    return app.handle(
        build_request(
            method="GET",
            raw_path=path,
            headers={"accept": "text/html"},
            body=b"",
            client_host="127.0.0.1",
        )
    )


def page(response: Response) -> str:
    return response.body.decode("utf-8")


MODELS = f"/benchmark/{CIK}/{ACCESSION}/models"
UNPARSED_MODELS = f"/benchmark/{CIK}/{UNPARSED_ACCESSION}/models"


# --- anti-vacuity: the fixture measures into something worth asserting about ---------------------


def test_the_three_runs_measure_into_figures_these_assertions_can_mean_anything_about(
    harness: Harness, runs: tuple[str, str, str]
) -> None:
    """Every assertion below is worthless over three empty ledgers.

    This proves there are three recorded runs; that two of them produced a readable parse and one
    produced none; that the parse covers some spans and silently omits others; that it emitted a
    structured table with a cell that is nowhere in the source; and that it declared something
    unresolved.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    truth = BenchmarkTruth.empty(
        cik=CIK, accession=ACCESSION, source_set_sha256=found.inventory.source_set_sha256
    )
    measured = harness.service.measured_runs(found, truth)
    assert [m.run_id for m in measured] == list(runs), "the runs are not in recorded order"

    multipart, single, refused = measured
    assert multipart.parse_exists and single.parse_exists
    assert not refused.parse_exists, "the refusing candidate produced a parse after all"

    assert multipart.ledger is not None and multipart.gate is not None
    coverage = multipart.ledger.coverage
    assert coverage.spans_covered > 0, "nothing was covered, so the covered column proves nothing"
    assert coverage.spans_silently_omitted > 0, "nothing was omitted; the key figure is vacuous"
    assert multipart.ledger.table_state.structured_emitted == 1
    assert multipart.cells_missing_from_source > 0, "no fabricated cell to mark"
    assert multipart.unresolved_items, "nothing was declared unresolved"
    assert Decimal(multipart.cost_usd) > 0, "the run recorded no spend"


def test_the_omitted_span_really_carries_the_hostile_payload(harness: Harness) -> None:
    """ANTI-VACUITY for the escaping tests: the payload must reach the page to be escaped on it.

    The two identifiers the scripted parse and the assertions below name are checked against the
    measured inventory here. If the inventory's identifier scheme moved, the model's table would
    name no source element, every cell of it would be unclassifiable rather than fabricated, and
    the assertions that prove a fabricated cell is marked would pass over a page proving nothing.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    assert [t.table_id for t in found.inventory.tables] == [SOURCE_TABLE_ID]
    omitted = found.inventory.span(OMITTED_SPAN_ID)
    assert omitted is not None and HOSTILE_DECODED in omitted.normalized_text
    assert any(
        HOSTILE_DECODED in cell.text for table in found.inventory.tables for cell in table.cells
    )


# --- both routes render --------------------------------------------------------------------------


def test_the_comparison_page_lists_every_recorded_run_with_every_required_figure(
    app: ReviewApp, harness: Harness, runs: tuple[str, str, str]
) -> None:
    """One row per run, carrying the identity, the four states and the nine measured figures."""
    body = page(call(app, MODELS))
    assert "3 recorded run(s)" in body
    for run_id in runs:
        assert run_id in body, f"{run_id} is missing from the comparison page"
        assert f'href="{MODELS}/{run_id}"' in body, f"{run_id} has no detail link"
    assert PARSER in body and REFUSER in body
    assert REGION in body
    assert "intact" in body, "the source input mode is not shown"
    for header in (
        "visible spans covered",
        "silently omitted",
        "structured tables",
        "table validations",
        "cells not in source",
        "members accounted",
        "images accounted",
        "measured cost",
        "gate",
    ):
        assert f"<th>{header}</th>" in body, f"the {header!r} column is missing"


def test_the_comparison_page_shows_the_silently_omitted_count_prominently(app: ReviewApp) -> None:
    """The most important figure on the page, and never carried by colour alone.

    A span in this count is filing content the model never mentioned in any form. The cell says
    SILENTLY OMITTED in words as well as carrying the marker class, because a reviewer reading
    without colour has to see it too.
    """
    body = page(call(app, MODELS))
    assert 'class="omitted"' in body
    assert "SILENTLY OMITTED" in body
    assert re.search(r"[0-9,]+ SILENTLY OMITTED", body), "the count is not beside the words"


def test_the_comparison_page_says_what_it_is_not(app: ReviewApp) -> None:
    """rules.md section 21 rule 14. The page must not read as a recommendation."""
    body = page(call(app, MODELS))
    assert "no run is recommended" in body
    assert "Ordered by creation time and by nothing else" in body
    assert "MECHANICAL_COMPLETENESS_CANDIDATE" in body
    assert "enough evidence to undergo human completeness review" in body


def test_the_detail_page_shows_the_gate_the_claims_the_omissions_and_the_tables(
    app: ReviewApp, harness: Harness, runs: tuple[str, str, str]
) -> None:
    """Everything a reviewer needs in one place, and each part of it identifiable."""
    multipart = runs[0]
    body = page(call(app, f"{MODELS}/{multipart}"))

    assert "The fourteen conditions" in body
    for number in range(1, 15):
        assert f"<td>{number}</td>" in body, f"gate condition {number} is missing"
    assert "no source region is silently omitted" in body

    assert "Coverage claims" in body
    assert "start anchor" in body and "end anchor" in body
    assert "interval bounded" in body
    assert re.search(r"level [0-9]", body), "no ladder level is reported for any anchor"

    assert "Silently omitted source spans" in body
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    omitted = found.inventory.span(OMITTED_SPAN_ID)
    assert omitted is not None
    assert omitted.span_id in body, "the omitted span is not listed"
    assert f"{omitted.start:,}–{omitted.end:,}" in body, "the omitted span has no source offsets"

    assert "Structured tables" in body
    assert "What the model returned" in body
    assert "The mechanical source element" in body
    assert "NOT IN SOURCE" in body, "the fabricated cell is not marked"

    assert "Model-declared unresolved items" in body
    assert "the model said it could not resolve this" in body


def test_the_detail_page_of_a_run_that_produced_nothing_still_renders(
    app: ReviewApp, runs: tuple[str, str, str]
) -> None:
    """A refused run has a detail page too, and it says what happened rather than nothing."""
    response = call(app, f"{MODELS}/{runs[2]}")
    assert response.status == 200
    body = page(response)
    assert REFUSER in body
    assert "The fourteen conditions" in body
    assert "the scripted provider refused this invocation" in body
    assert "0 readable part artifact(s)" in body


def test_the_comparison_page_is_reachable_from_the_rest_of_the_benchmark_surface(
    app: ReviewApp,
) -> None:
    """A page nobody can navigate to is not a surface."""
    body = page(call(app, f"/benchmark/{CIK}/{ACCESSION}"))
    assert f'href="{MODELS}"' in body
    assert "Model runs" in body


# --- a run that never produced a parse -----------------------------------------------------------


def test_a_run_that_failed_at_the_provider_is_a_row_stating_what_happened(
    app: ReviewApp, runs: tuple[str, str, str]
) -> None:
    """Not hidden, not crashed, and not reported as a model that covered nothing.

    Printing `0 of N covered` for a run that never answered would put an accusation against a model
    into the column a reader scans for exactly that. The row withholds the figures it does not have
    and says why.
    """
    body = page(call(app, MODELS))
    assert runs[2] in body, "the failed run was hidden"
    assert "no parse" in body, "the failed run's coverage columns were not withheld"
    assert "the scripted provider refused this invocation" in body


def test_a_filing_with_no_recorded_run_renders_an_empty_state_rather_than_an_error(
    app: ReviewApp,
) -> None:
    """An empty table would read as a measurement. The page says there is nothing to compare."""
    response = call(app, UNPARSED_MODELS)
    assert response.status == 200
    body = page(response)
    assert "No run has been recorded against this filing" in body
    assert "SILENTLY OMITTED" not in body, "an empty state reported an omission figure"


# --- misses ---------------------------------------------------------------------------------------


def test_an_unknown_run_is_a_404(app: ReviewApp) -> None:
    """A run identifier naming no job against THIS filing names nothing this page can measure."""
    response = call(app, f"{MODELS}/run_aaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert response.status == 404
    assert json.loads(response.body.decode("utf-8"))["code"] == "not_found"


def test_a_run_that_parsed_another_filing_is_not_shown_under_this_one(
    app: ReviewApp, runs: tuple[str, str, str]
) -> None:
    """Its ledger would be computed against another filing's denominator, which is meaningless."""
    response = call(app, f"{UNPARSED_MODELS}/{runs[0]}")
    assert response.status == 404


def test_a_filing_this_project_does_not_hold_is_a_404_on_both_routes(app: ReviewApp) -> None:
    """Nothing is fetched to answer a page view, so an unheld filing is a miss and not a fetch."""
    base = f"/benchmark/{CIK}/{ABSENT_ACCESSION}/models"
    for path in (base, f"{base}/run_aaaaaaaaaaaaaaaaaaaaaaaaaa"):
        assert call(app, path).status == 404, path


# --- escaping ------------------------------------------------------------------------------------


@pytest.mark.security
def test_neither_page_ever_emits_filing_text_as_markup(
    app: ReviewApp, runs: tuple[str, str, str]
) -> None:
    """SECURITY-INVARIANT, and the reason this surface can exist at all.

    The fixture filing carries a script element written as character references. It reaches these
    pages as a silently omitted span, as a cell of the model's own table and as a cell of the
    mechanical source element. Emitting any of them unescaped would execute filing content on an
    origin that holds a session able to spend money.
    """
    for path in (MODELS, f"{MODELS}/{runs[0]}", f"{MODELS}/{runs[1]}", f"{MODELS}/{runs[2]}"):
        body = page(call(app, path))
        assert HOSTILE_DECODED not in body, f"{path} emitted filing text as markup"
        assert "<script>alert" not in body


@pytest.mark.security
def test_the_hostile_text_is_displayed_rather_than_dropped(
    app: ReviewApp, runs: tuple[str, str, str]
) -> None:
    """ANTI-VACUITY partner. Escaping proves nothing if the content never reached the page.

    A renderer that silently omitted anything it could not display safely would pass the test above
    and would hide exactly the source range this surface exists to account for.
    """
    body = page(call(app, f"{MODELS}/{runs[0]}"))
    assert "&lt;script&gt;alert(&quot;omitted&quot;)&lt;/script&gt;" in body, (
        "the detail page dropped the filing text instead of escaping it"
    )


@pytest.mark.security
def test_a_provider_error_message_is_escaped_like_everything_else(harness: Harness) -> None:
    """A failure message is a string a provider wrote, and it is rendered as text.

    Proved by rendering the page from a run whose situation sentence carries markup, rather than by
    trusting that provider messages happen to be tame today.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    truth = BenchmarkTruth.empty(
        cik=CIK, accession=ACCESSION, source_set_sha256=found.inventory.source_set_sha256
    )
    measured = harness.service.measured_runs(found, truth)
    hostile = replace(measured[0], situation=HOSTILE_DECODED, model_label=HOSTILE_DECODED)
    body = model_comparison_page(
        inventory=found.inventory,
        truth=truth,
        runs=[hostile],
        issuer_label=HOSTILE_DECODED,
    )
    assert HOSTILE_DECODED not in body
    assert "&lt;script&gt;" in body


# --- THE MUTATION PROOF ---------------------------------------------------------------------------


def _row_order(body: str) -> list[str]:
    """The run identifiers in the order the rendered table puts them."""
    return re.findall(r"/models/(run_[a-z2-7]{26})", body)


@pytest.mark.security
def test_the_comparison_page_does_not_order_rows_by_any_coverage_figure(
    harness: Harness, runs: tuple[str, str, str]
) -> None:
    """MUTATION PROOF for `rules.md` section 21 rule 14: nothing here selects a parser.

    Every figure a reader might expect a page to sort by is rewritten — coverage, omissions, cost,
    gate conditions, table validations — and the rendered row order must not move. A future
    `sorted(runs, key=...)` on any of them fails here, which is the only way this prohibition stays
    enforced rather than remembered: the page would otherwise go on rendering correctly while
    quietly recommending whichever model the sort key favoured.

    The states are rewritten too, because ordering by "worked" before "failed" is the same
    selection wearing a different key.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    truth = BenchmarkTruth.empty(
        cik=CIK, accession=ACCESSION, source_set_sha256=found.inventory.source_set_sha256
    )
    measured = harness.service.measured_runs(found, truth)
    assert len(measured) >= 3, "too few runs for an ordering proof to mean anything"

    def render(entries: list) -> list[str]:
        return _row_order(
            model_comparison_page(
                inventory=found.inventory,
                truth=truth,
                runs=entries,
                issuer_label="Synthetic Comparison Issuer",
            )
        )

    baseline = render(measured)
    assert baseline == list(runs), "the unmutated page already disagrees with recorded order"

    # Reverse every measurable quantity: the run with the best figures becomes the one with the
    # worst. Costs, serialization states and part counts are inverted along with them.
    mutated = [
        replace(
            run,
            cost_usd=str(Decimal(len(measured) - position)),
            part_documents=len(measured) - position,
            serialization=(
                SerializationState.UNPARSEABLE
                if position == 0
                else SerializationState.RAW_PARSEABLE
            ),
        )
        for position, run in enumerate(measured)
    ]
    assert render(mutated) == baseline, "the page reordered its rows when the figures changed"

    # And the ordering must not be a property of the input list either: a caller handing the runs
    # over in another order gets that order back, because the page applies none of its own.
    assert render(list(reversed(measured))) == list(reversed(baseline)), (
        "the page imposed an order of its own rather than rendering what it was given"
    )


@pytest.mark.security
def test_no_measured_figure_appears_in_a_sort_key_anywhere_in_the_surface() -> None:
    """The same prohibition read off the source, so an ordering added elsewhere is caught too.

    The renderer test above proves the page as it is; this proves nothing in either module has
    acquired a `sorted`, `max`, `min` or `key=` over a measured value. `jobs_for` sorts by creation
    time and identifier, which is the one ordering that carries no opinion, and it is the only sort
    either module is allowed to contain.
    """
    from packages.orchestrator import comparison_service
    from packages.review_web import model_comparison_view

    figures = re.compile(
        r"(sorted|max|min)\([^)]*"
        r"(spans_|characters_|coverage|cells_|structured_|conditions_|cost|passing)",
        re.IGNORECASE,
    )
    for module in (comparison_service, model_comparison_view):
        source = Path(module.__file__ or "").read_text(encoding="utf-8")
        stripped = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        offenders = figures.findall(stripped)
        assert not offenders, (
            f"{module.__name__} orders or aggregates a measured figure: {offenders}"
        )
