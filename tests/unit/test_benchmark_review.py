"""The completeness benchmark surface: five pages, one state change, and what each must refuse.

WHAT IS ACTUALLY UNDER TEST. Not that a page renders — that is arithmetic. The subject is the set
of things this surface must get right or be dangerous:

    ESCAPING            every page here exists to display bytes SEC published, and the benchmark
                        filing below carries a script element written as character references. If
                        any page emitted it unescaped, opening the review UI would execute filing
                        content in the reviewer's browser on an origin holding a session that can
                        spend money.
    CSRF                recording a judgement changes the DENOMINATOR of a benchmark. Every control
                        is a form post with a bound token, and a post without one is refused.
    SUPERSESSION        a truth version is written once. A completeness figure computed against
                        version 3 means nothing if version 3 can be edited under its own name.
    SUGGESTIONS         the two byte-level proposals are derived on read and never stored, so a
                        proposal nobody accepted can never become indistinguishable from a decision.
    MISSES              a filing this project does not hold is a 404 on every route, and a judgement
                        about an item the inventory does not contain has nothing to attach to.

HERMETIC AND SOCKETLESS, like the rest of the review suite. Every route is exercised by handing
`ReviewApp.handle` a `Request` and reading the `Response` back. The corpus, the capability snapshot,
the prompt registry and the evaluation store are all synthetic and live under `tmp_path`; nothing
reads a developer's environment, the research corpus, the committed snapshot or any credential.

NO MODEL IS INVOLVED ANYWHERE IN THIS FILE, and that is a property of the surface rather than of the
fixture: the benchmark pages measure preserved bytes and record a person's judgement, and not one of
them can reach a provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from packages.completeness import BenchmarkTruth
from packages.evaluation_store import EvaluationStore
from packages.llm_gateway.providers.mock import MockProvider
from packages.model_catalog import load_snapshot
from packages.orchestrator import (
    CorpusFilingCatalog,
    InlineWorker,
    ParserReviewService,
    SpendJournal,
)
from packages.prompt_registry import PromptRegistry
from packages.review_api import (
    CSRF_FIELD,
    SECURITY_HEADERS,
    SESSION_COOKIE,
    Response,
    ReviewApp,
    SecurityPolicy,
    build_request,
)
from packages.source_transport import ManifestInventory, PreservedObject, RefusingFetcher
from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_text

CIK = "0000000123"
ACCESSION = "0000000123-25-000001"
ABSENT_ACCESSION = "0000000123-25-000099"
ENTITY_NAME = "Synthetic Benchmark Issuer"
REGION = "region-one"
PRIMARY = "primary.htm"
IMAGE = "chart.png"

#: THE HOSTILE PAYLOAD, AS A FILING WOULD CARRY IT. `HTMLParser` is run with `convert_charrefs`,
#: which is what makes this the real case rather than a contrived one: the source carries character
#: references, the inventory's span and cell text carry the DECODED characters, and it is those
#: decoded characters that reach a page. The benchmark filing measured in Phase 2.2 carries 970
#: character references and zero literal non-ASCII characters, so entity-decoded text is what this
#: surface displays for real filings too.
HOSTILE_SOURCE = "&lt;script&gt;alert(&quot;benchmark&quot;)&lt;/script&gt;"
HOSTILE_DECODED = '<script>alert("benchmark")</script>'

#: Repeated verbatim so the second occurrence is marked `duplicate_of` the first, which is what the
#: REPEATED_CONTENT suggestion is derived from.
REPEATED = "Net sales moved over the period."

#: Two byte-identical table elements with an empty one between them. The pair drives the
#: DUPLICATE_RENDERING suggestion; the empty one drives EMPTY. Formatting is identical on purpose:
#: a table's source slice runs to the start of the next construct, so a stray space would make two
#: renderings of the same table stop being byte-identical.
_DATA_TABLE = (
    "<table><tr><th>Period</th><th>Amount</th></tr>"
    f"<tr><td>{HOSTILE_SOURCE}</td><td>1,234</td></tr></table>"
)

PRIMARY_DOCUMENT = (
    "<html><head><title>Synthetic benchmark filing</title></head><body>\n"
    f"<p>{REPEATED}</p>\n"
    f"<p>{HOSTILE_SOURCE}</p>\n"
    f"{_DATA_TABLE}\n"
    "<table></table>\n"
    f"{_DATA_TABLE}\n"
    f'<p><img src="{IMAGE}"></p>\n'
    f"<p>{REPEATED}</p>\n"
    "</body></html>\n"
).encode("ascii")

#: A PNG signature followed by a minimal IHDR, so the image module can read real dimensions from
#: the header rather than reporting them as not mechanically obtainable.
IMAGE_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    + (13).to_bytes(4, "big")
    + b"IHDR"
    + (7).to_bytes(4, "big")
    + (5).to_bytes(4, "big")
    + b"\x08\x06\x00\x00\x00"
    + b"\x00\x00\x00\x00"
)

SUBMISSION = (
    f"<SEC-DOCUMENT>{ACCESSION}.txt : 20250131\n"
    f"<SEC-HEADER>{ACCESSION}.hdr.sgml : 20250131\n"
    f"ACCESSION NUMBER:\t\t{ACCESSION}\n"
    "CONFORMED SUBMISSION TYPE:\tQUARTERLY\n"
    "PUBLIC DOCUMENT COUNT:\t\t2\n"
    "CONFORMED PERIOD OF REPORT:\t20241228\n"
    "FILED AS OF DATE:\t\t20250131\n"
    "</SEC-HEADER>\n"
    "<DOCUMENT>\n"
    "<TYPE>QUARTERLY\n"
    "<SEQUENCE>1\n"
    f"<FILENAME>{PRIMARY}\n"
    "<DESCRIPTION>PRIMARY DOCUMENT\n"
    "<TEXT>\n"
    f"{PRIMARY_DOCUMENT.decode('ascii')}"
    "</TEXT>\n"
    "</DOCUMENT>\n"
    "<DOCUMENT>\n"
    "<TYPE>GRAPHIC\n"
    "<SEQUENCE>2\n"
    f"<FILENAME>{IMAGE}\n"
    "<DESCRIPTION>CHART\n"
    "<TEXT>\n"
    "begin 644 chart.png\n"
    "M(" + "A" * 60 + "\n"
    "end\n"
    "</TEXT>\n"
    "</DOCUMENT>\n"
    "</SEC-DOCUMENT>\n"
).encode("ascii")

SNAPSHOT = """snapshot_version: "1"
verified_on: "2026-01-01"
verified_from_region: region-one
price_source: a published price list
price_effective_date: "2026-01-01"
price_currency: USD
price_unit: per 1000 tokens
candidates:
  - label: Parser One
    provider: Provider
    model_id: "provider.parser-one"
    model_name: Parser One
    version_qualifier: "v1"
    mapping: UNIQUE
    availability: AVAILABLE
    access_status: granted
    verified_regions: ["region-one"]
    inference_profile_required: false
    inference_profile_id: null
    text_input: true
    image_input: false
    multimodal: false
    image_verified: false
    context_tokens: 128000
    max_output_tokens: 8192
    invocation_apis: ["Converse"]
    streaming_supported: true
    price_input_per_1k: 0.001
    price_output_per_1k: 0.004
    smoke_transport: ACCEPTED
    smoke_instruction: EXACT
    blocker: null
    disabled_reason: null
"""

PROMPT_TEXT = (
    "Parse the complete filing in its own vocabulary. Represent every human-readable range or "
    "mark it unresolved.\n"
)

DEV_SECRET = "this-is-not-a-real-secret-only-a-test-value"

# Assembled, never written out: tests/architecture/test_aws_identity.py fails the build when these
# literals appear in a tracked file that is not the policy itself.
_AWS_PREFIX = "AWS_"
CREDENTIAL_VARIABLE_NAMES = tuple(
    _AWS_PREFIX + suffix for suffix in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "SESSION_TOKEN")
)
TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")
PROVIDER_MARKERS = ("arn:aws", "amazonaws.com", "bedrock-runtime", "AKIA", "ASIA")


@dataclass(frozen=True)
class Harness:
    """A review service over one synthetic filing, assembled by hand under `tmp_path`."""

    service: ParserReviewService
    worker: InlineWorker


def _write_corpus(tmp_path: Path) -> tuple[Path, ManifestInventory]:
    """Three preserved objects — the envelope and its two addressable members — and the manifest.

    ADDRESSABLE ON PURPOSE. The envelope declares a `<FILENAME>` per document, which is the branch
    where each member is reused as itself. It is also the only branch that produces a filed IMAGE
    member, and the image page has nothing to show without one.
    """
    corpus = tmp_path / "corpus" / ACCESSION
    corpus.mkdir(parents=True)
    members = {f"{ACCESSION}.txt": SUBMISSION, PRIMARY: PRIMARY_DOCUMENT, IMAGE: IMAGE_BYTES}
    preserved: list[PreservedObject] = []
    files: list[dict[str, Any]] = []
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
                acquisition_method="synthetic_corpus",
                reused=True,
            )
        )
        files.append(
            {
                "filename": filename,
                "sha256": digest,
                "raw_bytes": len(data),
                "local_path": str(path),
                "source_url": "",
            }
        )

    manifest = tmp_path / "corpus-manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "cik": CIK,
                    "accession": ACCESSION,
                    "form_as_filed": "QUARTERLY",
                    "filing_date": "2025-01-31",
                    "report_period": "2024-12-28",
                    "issuer_name_current": ENTITY_NAME,
                    "tickers_current": ["SYNB"],
                    "sic_description": "Synthetic issuers",
                    "transport_era": "addressable-members",
                    "is_amendment": False,
                    "is_annual": False,
                    "form_variant": "QUARTERLY",
                    "package_file_count": len(files),
                    "package_image_count": 1,
                    "primary_est_tokens_at_3_0": 900,
                    "files": files,
                }
            ]
        ),
        encoding="utf-8",
    )
    return manifest, ManifestInventory({(CIK, ACCESSION): preserved})


def _write_prompts(tmp_path: Path) -> Path:
    directory = tmp_path / "prompts"
    directory.mkdir()
    (directory / "parser-v1.txt").write_text(PROMPT_TEXT, encoding="utf-8")
    (directory / "versions.yaml").write_text(
        'schema_version: "prompt-versions-v1"\n'
        "prompts:\n"
        "  - prompt_id: synthetic-parser\n"
        '    version: "1"\n'
        "    file: parser-v1.txt\n"
        f'    sha256: "{sha256_text(PROMPT_TEXT)}"\n'
        '    created: "2026-01-01"\n'
        "    status: ACTIVE\n"
        "    role: parsing\n",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    manifest, inventory = _write_corpus(tmp_path)
    evaluation_root = tmp_path / "evaluation"
    service = ParserReviewService(
        store=EvaluationStore.at_path(evaluation_root),
        catalog=CorpusFilingCatalog.from_manifest(manifest),
        snapshot=load_snapshot(SNAPSHOT),
        prompts=PromptRegistry.from_directory(_write_prompts(tmp_path)),
        inventory=inventory,
        fetcher=RefusingFetcher(),
        provider=MockProvider(),
        journal=SpendJournal(FilesystemObjectStore(evaluation_root), ceiling_usd=Decimal("5.00")),
        preferred_region=REGION,
        author="reviewer",
    )
    return Harness(service=service, worker=InlineWorker(service))


def app_for(
    harness: Harness, *, loopback_only: bool = True, secret: str | None = None
) -> ReviewApp:
    return ReviewApp(
        service=harness.service,
        worker=harness.worker,
        policy=SecurityPolicy(loopback_only=loopback_only, dev_auth_secret=secret),
    )


@pytest.fixture
def app(harness: Harness) -> ReviewApp:
    """The ordinary posture: loopback, no authentication, no session, so no token to bind."""
    return app_for(harness)


@pytest.fixture
def guarded(harness: Harness) -> ReviewApp:
    """Bound beyond loopback, which is every posture where the CSRF check applies."""
    return app_for(harness, loopback_only=False, secret=DEV_SECRET)


def call(
    app: ReviewApp,
    method: str,
    raw_path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> Response:
    return app.handle(
        build_request(
            method=method,
            raw_path=raw_path,
            headers=headers or {},
            body=body,
            client_host="127.0.0.1",
        )
    )


def body_json(response: Response) -> Any:
    return json.loads(response.body.decode("utf-8"))


def page(response: Response) -> str:
    return response.body.decode("utf-8")


def signed_in(app: ReviewApp) -> tuple[dict[str, str], str]:
    session = app.policy.sessions.create()
    return {"Cookie": f"{SESSION_COOKIE}={session.session_id}"}, session.csrf_token


BASE = f"/benchmark/{CIK}/{ACCESSION}"
MISSING = f"/benchmark/{CIK}/{ABSENT_ACCESSION}"

#: The five server-rendered pages. Filing text reaches a MARKUP parser here or it reaches nothing.
HTML_ROUTES = (
    BASE,
    f"{BASE}/inventory",
    f"{BASE}/spans",
    f"{BASE}/tables",
    f"{BASE}/images",
)

#: The two browser-facing JSON reads. Filing text is a JSON STRING VALUE here, not markup, and the
#: response is declared `application/json` with `nosniff` — so a browser never parses it as a
#: document. Holding them to the HTML rule would be the wrong rule: JSON that escaped `<` would
#: still be JSON, and JSON that did not is still not markup.
JSON_ROUTES = (
    f"/api/benchmark/{CIK}/{ACCESSION}/inventory",
    f"/api/benchmark/{CIK}/{ACCESSION}/truth",
)

GET_ROUTES = HTML_ROUTES + JSON_ROUTES


# --- anti-vacuity: the synthetic filing is rich enough for these assertions to mean anything ----


def test_the_synthetic_filing_measures_into_a_real_inventory(harness: Harness) -> None:
    """Every escaping and classification assertion below is worthless over an empty inventory.

    This proves there is a human-readable member, a filed image, more than one table element, a
    byte-identical pair, an element empty of text, a repeated span, and a span carrying the hostile
    payload — before anything looks at a page.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    inventory = found.inventory
    assert [m.member for m in inventory.human_readable_members] == [PRIMARY]
    assert [i.filename for i in inventory.images] == [IMAGE]
    assert len(inventory.tables) == 3
    assert any(t.duplicate_of for t in inventory.tables), "no byte-identical table pair"
    assert any(t.is_empty for t in inventory.tables), "no element empty of text"
    assert any(s.mechanically_duplicate for s in inventory.spans), "no repeated span"
    assert any(HOSTILE_DECODED in s.normalized_text for s in inventory.visible_spans), (
        "the hostile payload never became a visible span, so the escaping tests prove nothing"
    )
    assert any(
        HOSTILE_DECODED in cell.text for table in inventory.tables for cell in table.cells
    ), "the hostile payload never became a table cell"
    assert inventory.images[0].width == 7 and inventory.images[0].height == 5


def test_the_inventory_is_measured_from_preserved_bytes_and_reaches_no_model(
    harness: Harness,
) -> None:
    """Building an inventory issues no provider request and spends nothing.

    The fetcher refuses every request and the journal is untouched, so a page view cannot generate
    SEC traffic and cannot move the cumulative ceiling.
    """
    before = harness.service.journal.spent_usd
    assert harness.service.inventoried_filing(CIK, ACCESSION) is not None
    assert harness.service.journal.spent_usd == before


# --- the five pages -----------------------------------------------------------------------------


def test_every_benchmark_route_answers_and_carries_the_security_headers(app: ReviewApp) -> None:
    """A page that arrived without the headers is one the browser treats unlike every other."""
    for path in GET_ROUTES:
        response = call(app, "GET", path, headers={"Accept": "text/html"})
        assert response.status == 200, f"{path} answered {response.status}"
        for name, value in SECURITY_HEADERS.items():
            assert response.headers.get(name) == value, f"{name} missing from {path}"


def test_the_overview_states_the_truth_version_and_the_unreviewed_counts(app: ReviewApp) -> None:
    """An unreviewed item is neither required nor excused, so the count is shown, not implied."""
    body = page(call(app, "GET", BASE, headers={"Accept": "text/html"}))
    assert "benchmark truth version 0" in body
    assert "unreviewed" in body
    assert "no judgement has been recorded for this filing yet" in body


def test_the_overview_refuses_to_show_a_ledger_when_no_parse_exists(app: ReviewApp) -> None:
    """rules.md section 13: never describe planned behaviour as implemented.

    A ledger measures ONE PARSE against this truth. No model has parsed this filing, so a ledger
    computed here would report every span as silently omitted and would mean nothing. The page says
    so in words rather than rendering an empty table that reads as a measurement.
    """
    body = page(call(app, "GET", BASE, headers={"Accept": "text/html"}))
    assert "No completeness ledger is shown" in body
    assert "No model has parsed this filing" in body


def test_the_inventory_page_lists_every_member_with_its_role_size_hash_and_counts(
    app: ReviewApp, harness: Harness
) -> None:
    """The transport role is a measurement and the SEC-declared type is a claim; both are shown."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    body = page(call(app, "GET", f"{BASE}/inventory", headers={"Accept": "text/html"}))
    for member in found.inventory.members:
        assert member.member in body, f"{member.member} is missing from the inventory page"
        assert member.sha256 in body, f"{member.member} is listed without its hash"
        assert member.transport_role in body
    assert f"{len(found.inventory.members):,} member(s)" in body


def test_the_span_page_defaults_to_a_member_and_shows_offsets_duplication_and_a_control(
    app: ReviewApp, harness: Harness
) -> None:
    """A span row has to carry everything a reviewer needs to classify it without leaving the page."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span = found.inventory.spans_for(PRIMARY)[0]
    body = page(call(app, "GET", f"{BASE}/spans", headers={"Accept": "text/html"}))
    assert f"Spans of {PRIMARY}" in body
    assert span.span_id in body
    assert f"{span.start:,}–{span.end:,}" in body
    assert "MATERIAL_FILING_CONTENT" in body, "the classification control offers no required value"
    assert 'method="post"' in body
    assert f'action="/benchmark/{CIK}/{ACCESSION}/judgements"' in body


def test_a_repeated_span_is_shown_as_repeated_and_the_suggestion_is_marked_unaccepted(
    app: ReviewApp, harness: Harness
) -> None:
    """A byte observation is a proposal, not a judgement, and the page must not blur the two."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    repeated = next(s for s in found.inventory.spans if s.mechanically_duplicate)
    body = page(call(app, "GET", f"{BASE}/spans", headers={"Accept": "text/html"}))
    assert repeated.duplicate_of in body
    assert "mechanical suggestion, NOT APPLIED: REPEATED_CONTENT" in body
    assert "REQUIRES_REVIEW" in body, "an unaccepted suggestion still leaves the item unreviewed"


def test_an_unknown_member_falls_back_rather_than_rendering_an_empty_filing(app: ReviewApp) -> None:
    """A page that answered a nonsense member with nothing would read as a filing with no content.

    It also keeps a browser-supplied string out of the page entirely: the requested member is
    checked against the inventory before it is used, so nothing arbitrary reaches an href or a
    hidden field.
    """
    body = page(
        call(
            app,
            "GET",
            f"{BASE}/spans?member=%3Cscript%3Enope%3C%2Fscript%3E",
            headers={"Accept": "text/html"},
        )
    )
    assert f"Spans of {PRIMARY}" in body
    assert "nope" not in body


def test_the_table_page_shows_the_source_slice_beside_the_extracted_grid(
    app: ReviewApp, harness: Harness
) -> None:
    """The slice is what SEC published; the grid is what the walk read out of it.

    A reviewer deciding whether an element carries data or is page furniture needs both, and a
    disagreement between them is itself the finding.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    body = page(call(app, "GET", f"{BASE}/tables", headers={"Accept": "text/html"}))
    for table in found.inventory.tables:
        assert table.table_id in body
        assert table.sha256 in body
        assert f"{table.row_count:,} row(s)" in body
    assert "&lt;table&gt;" in body, "the raw source slice is not rendered as escaped text"
    assert "<th>Period</th>" in body, "the extracted grid was not rendered"
    assert "empty of text" in body
    assert "byte-identical to" in body
    assert "DATA_BEARING" in body


def test_the_image_page_shows_the_hash_dimensions_media_type_and_reference_sites(
    app: ReviewApp, harness: Harness
) -> None:
    """A dimension that could not be read is reported as unobtainable, never as a plausible number."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    record = found.inventory.images[0]
    body = page(call(app, "GET", f"{BASE}/images", headers={"Accept": "text/html"}))
    assert record.filename in body
    assert record.sha256 in body
    assert "image/png" in body
    assert "7×5 pixels" in body
    assert f"{PRIMARY} at character offset" in body
    assert "DECORATIVE" in body, "the image classification control offers no excluding value"


def test_the_pages_are_reachable_from_one_another(app: ReviewApp) -> None:
    """A page nobody can navigate to is not a surface."""
    body = page(call(app, "GET", BASE, headers={"Accept": "text/html"}))
    for page_name in ("inventory", "spans", "tables", "images"):
        assert f'href="/benchmark/{CIK}/{ACCESSION}/{page_name}"' in body


# --- escaping -----------------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.parametrize("path", HTML_ROUTES)
def test_no_benchmark_page_ever_emits_filing_text_as_markup(app: ReviewApp, path: str) -> None:
    """SECURITY-INVARIANT, and the reason this surface can exist at all.

    Every page here displays bytes SEC published. The benchmark filing carries a script element
    written as character references, so the inventory's span text and cell text carry the DECODED
    characters. Emitting those unescaped would execute filing content on an origin that holds a
    session able to spend money — and the content security policy is only as strict as it is
    because nothing from a filing is ever parsed as markup.
    """
    body = page(call(app, "GET", path, headers={"Accept": "text/html"}))
    assert HOSTILE_DECODED not in body, f"{path} emitted filing text as markup"
    assert "<script>alert" not in body


@pytest.mark.security
@pytest.mark.parametrize("path", JSON_ROUTES)
def test_the_json_reads_are_declared_json_and_are_never_sniffed_into_a_document(
    app: ReviewApp, path: str
) -> None:
    """Filing text is a JSON string value here, and a JSON string value is not markup.

    What makes that safe is not escaping — it is the declared content type plus `nosniff`, which is
    what stops a browser deciding for itself that a body beginning with `{` is a document. The
    inventory genuinely carries the decoded span text, so this is the case that would break if the
    header were ever dropped.
    """
    response = call(app, "GET", path, headers={"Accept": "text/html"})
    assert response.content_type.startswith("application/json")
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.security
def test_the_inventory_json_really_carries_the_hostile_text(app: ReviewApp) -> None:
    """ANTI-VACUITY for the header test above: the body it protects has to contain the payload."""
    payload = body_json(call(app, "GET", JSON_ROUTES[0]))
    assert any(HOSTILE_DECODED in span["normalized_text"] for span in payload["spans"])


@pytest.mark.security
def test_the_hostile_text_is_displayed_rather_than_dropped(app: ReviewApp) -> None:
    """ANTI-VACUITY partner. Escaping proves nothing if the content never reached the page.

    A renderer that silently omitted anything it could not display safely would pass the test above
    and would hide exactly the source range this surface exists to account for.
    """
    for path in (f"{BASE}/spans", f"{BASE}/tables"):
        body = page(call(app, "GET", path, headers={"Accept": "text/html"}))
        assert "&lt;script&gt;alert(&quot;benchmark&quot;)&lt;/script&gt;" in body, (
            f"{path} dropped the filing text instead of escaping it"
        )


@pytest.mark.security
@pytest.mark.parametrize("path", GET_ROUTES)
def test_no_benchmark_route_returns_a_provider_endpoint_or_a_credential(
    app: ReviewApp, path: str, harness: Harness
) -> None:
    """The browser never calls a provider, because no route hands it anything to call one with.

    THE HASHES ARE REMOVED BEFORE THE ACCOUNT-SHAPED SCAN, AND THAT IS NOT A LOOPHOLE. These pages
    show SHA-256 digests in full — the inventory page shows one per member, the table page one per
    element — and a hexadecimal digest contains a run of twelve digits often enough that scanning
    over one would fail for a reason that has nothing to do with an AWS account identifier. Every
    removed string is a value this test computed itself from the fixture's own bytes.
    """
    body = page(call(app, "GET", path, headers={"Accept": "text/html"}))
    for marker in PROVIDER_MARKERS:
        assert marker not in body, f"{path} returned {marker!r}"
    for variable in CREDENTIAL_VARIABLE_NAMES:
        assert variable not in body, f"{path} named a credential variable"

    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    without_hashes = body
    for digest in {m.sha256 for m in found.inventory.members} | {
        t.sha256 for t in found.inventory.tables
    }:
        without_hashes = without_hashes.replace(digest, "")
    assert not TWELVE_DIGITS.search(without_hashes), f"{path} returned an account-shaped identifier"


# --- misses -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    (
        MISSING,
        f"{MISSING}/inventory",
        f"{MISSING}/spans",
        f"{MISSING}/tables",
        f"{MISSING}/images",
        f"/api/benchmark/{CIK}/{ABSENT_ACCESSION}/inventory",
        f"/api/benchmark/{CIK}/{ABSENT_ACCESSION}/truth",
    ),
)
def test_a_filing_this_project_does_not_hold_is_a_404_on_every_route(
    app: ReviewApp, path: str
) -> None:
    """Nothing is fetched to answer a page view, so an unheld filing is a miss and not a fetch."""
    response = call(app, "GET", path, headers={"Accept": "text/html"})
    assert response.status == 404, f"{path} answered {response.status}"
    assert body_json(response)["code"] == "not_found"


def test_a_malformed_identity_is_a_miss_rather_than_an_identity_exception(app: ReviewApp) -> None:
    """The catalog promises `FilingRecord | None`; a browser typing nonsense is a miss."""
    for path in ("/benchmark/not-a-cik/not-an-accession", f"/benchmark/{CIK}/..."):
        assert call(app, "GET", path, headers={"Accept": "text/html"}).status == 404, path


def test_posting_a_judgement_about_an_unheld_filing_is_a_404(app: ReviewApp) -> None:
    response = call(
        app,
        "POST",
        f"{MISSING}/judgements",
        body=b"kind=span&item_id=x&classification=NAVIGATION",
    )
    assert response.status == 404
    assert body_json(response)["code"] == "not_found"


# --- CSRF ---------------------------------------------------------------------------------------


@pytest.mark.security
def test_recording_a_judgement_without_a_token_is_refused_once_a_session_exists(
    guarded: ReviewApp,
) -> None:
    """A browser on another origin can make the request; it cannot read the token.

    Recording a judgement changes the denominator of a benchmark, which is exactly the kind of
    state change a cross-origin form post must not be able to make.
    """
    headers, _ = signed_in(guarded)
    response = call(
        guarded,
        "POST",
        f"{BASE}/judgements",
        headers=headers,
        body=b"kind=span&item_id=x&classification=NAVIGATION",
    )
    assert response.status == 403
    assert body_json(response)["code"] == "csrf_failed"


@pytest.mark.security
def test_a_token_from_another_session_does_not_record_a_judgement(guarded: ReviewApp) -> None:
    """The token is bound to ONE session. A valid-looking token from elsewhere is not a token."""
    headers, _ = signed_in(guarded)
    _, other = signed_in(guarded)
    response = call(
        guarded,
        "POST",
        f"{BASE}/judgements",
        headers={**headers, "X-Csrf-Token": other},
        body=b"kind=span&item_id=x&classification=NAVIGATION",
    )
    assert response.status == 403


@pytest.mark.security
def test_the_bound_token_is_accepted_and_the_refusals_above_are_about_the_token(
    guarded: ReviewApp, harness: Harness
) -> None:
    """ANTI-VACUITY. The two 403s must come from the missing token, not from the route."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span_id = found.inventory.visible_spans[0].span_id
    headers, token = signed_in(guarded)
    response = call(
        guarded,
        "POST",
        f"{BASE}/judgements",
        headers=headers,
        body=(
            f"{CSRF_FIELD}={token}&kind=span&item_id={span_id}"
            "&classification=MATERIAL_FILING_CONTENT"
        ).encode(),
    )
    assert response.status == 201
    assert body_json(response)["version"] == 1


@pytest.mark.security
def test_every_classification_control_is_a_form_post_and_never_a_link(app: ReviewApp) -> None:
    """A link is something a browser can be made to follow; a state change must not be one."""
    for path in (f"{BASE}/spans", f"{BASE}/tables", f"{BASE}/images"):
        body = page(call(app, "GET", path, headers={"Accept": "text/html"}))
        assert 'method="post"' in body, f"{path} carries no post form"
        assert f'href="/benchmark/{CIK}/{ACCESSION}/judgements"' not in body, (
            f"{path} offers a judgement as a link"
        )


# --- recording a judgement ----------------------------------------------------------------------


def _record(app: ReviewApp, **fields: str) -> Response:
    body = "&".join(f"{key}={value}" for key, value in fields.items()).encode()
    return call(app, "POST", f"{BASE}/judgements", body=body)


def test_a_recorded_judgement_lands_at_a_new_version_and_supersedes_nothing(
    app: ReviewApp, harness: Harness
) -> None:
    """rules.md invariant 7: a version is written once and the previous document stays on disk.

    A completeness figure computed against version 3 is meaningless if version 3 can be edited into
    version 4 under the same name, so both versions are asserted to exist afterwards.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    store = harness.service.store
    first, second = (s.span_id for s in found.inventory.visible_spans[:2])

    created = _record(app, kind="span", item_id=first, classification="MATERIAL_FILING_CONTENT")
    assert created.status == 201
    assert body_json(created)["version"] == 1

    again = _record(app, kind="span", item_id=second, classification="NAVIGATION")
    assert body_json(again)["version"] == 2

    assert store.benchmark_truth_versions(CIK, ACCESSION) == [1, 2]
    earlier = store.load_benchmark_truth(CIK, ACCESSION, version=1)
    assert earlier is not None
    assert set(earlier["spans"]) == {first}, "version 1 was rewritten rather than superseded"

    latest = BenchmarkTruth.from_mapping(store.load_benchmark_truth(CIK, ACCESSION) or {})
    assert latest.span(first).value == "MATERIAL_FILING_CONTENT"
    assert latest.span(second).value == "NAVIGATION"


def test_a_recorded_judgement_carries_who_recorded_it_and_when(
    app: ReviewApp, harness: Harness
) -> None:
    """A judgement without provenance is an opinion. The reviewer and the time are on the record."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    element = found.inventory.tables[0]
    _record(
        app,
        kind="table",
        item_id=element.table_id,
        classification="DATA_BEARING",
        note="carries+the+figures",
    )
    stored = harness.service.store.load_benchmark_truth(CIK, ACCESSION)
    assert stored is not None
    judgement = stored["tables"][element.table_id]
    assert judgement["reviewer"] == "reviewer"
    assert judgement["at"]
    assert judgement["note"] == "carries the figures"
    assert judgement["is_unaccepted_suggestion"] is False


def test_the_stored_document_never_acquires_a_mechanical_suggestion(
    app: ReviewApp, harness: Harness
) -> None:
    """A proposal that persisted itself would become indistinguishable from a decision.

    The filing carries repeated spans and two byte-identical table elements, so the derived document
    offered several suggestions before this post. The stored one holds exactly the single judgement
    a person recorded.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span_id = found.inventory.visible_spans[0].span_id
    _record(app, kind="span", item_id=span_id, classification="MATERIAL_FILING_CONTENT")
    stored = harness.service.store.load_benchmark_truth(CIK, ACCESSION)
    assert stored is not None
    assert set(stored["spans"]) == {span_id}
    assert stored["tables"] == {}
    assert stored["suggestion_count"] == 0


def test_a_recorded_judgement_replaces_the_suggestion_shown_on_the_page(
    app: ReviewApp, harness: Harness
) -> None:
    """A decision always wins over a proposal, and exactly one proposal stops being shown.

    Counted rather than merely looked for: this filing carries several repeated spans, so asserting
    that the phrase disappeared entirely would fail, and asserting that it is still present would
    pass over a page that had accepted nothing.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    repeated = next(s for s in found.inventory.spans if s.mechanically_duplicate)
    marker = "mechanical suggestion, NOT APPLIED: REPEATED_CONTENT"

    before = page(call(app, "GET", f"{BASE}/spans", headers={"Accept": "text/html"}))
    assert before.count(marker) >= 2, "too few proposals for this count to mean anything"

    _record(app, kind="span", item_id=repeated.span_id, classification="REPEATED_CONTENT")

    after = page(call(app, "GET", f"{BASE}/spans", headers={"Accept": "text/html"}))
    assert after.count(marker) == before.count(marker) - 1
    assert "recorded by reviewer at" in after


def test_an_unknown_item_kind_is_refused_rather_than_guessed(app: ReviewApp) -> None:
    """A judgement attaches to a span, a table or an image, and to nothing else."""
    response = _record(app, kind="paragraph", item_id="x", classification="NAVIGATION")
    assert response.status == 400
    assert body_json(response)["code"] == "bad_request"


def test_a_judgement_about_an_item_the_filing_does_not_contain_is_refused(app: ReviewApp) -> None:
    """It has nothing to attach to, and storing it would put a phantom item into the denominator."""
    response = _record(app, kind="span", item_id="primary.htm%23s9999", classification="NAVIGATION")
    assert response.status == 404
    assert body_json(response)["code"] == "not_found"


def test_a_classification_outside_the_closed_set_is_refused_rather_than_coerced(
    app: ReviewApp, harness: Harness
) -> None:
    """Silently downgrading it to REQUIRES_REVIEW would look exactly like an unreviewed item.

    The reviewer would have no way to tell that their decision had been discarded.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span_id = found.inventory.visible_spans[0].span_id
    response = _record(app, kind="span", item_id=span_id, classification="PROBABLY_FINE")
    assert response.status == 400
    assert body_json(response)["code"] == "bad_request"
    assert harness.service.store.benchmark_truth_versions(CIK, ACCESSION) == []


def test_a_span_classification_offered_to_a_table_is_refused(
    app: ReviewApp, harness: Harness
) -> None:
    """The three vocabularies are separate. A table is not MATERIAL_FILING_CONTENT."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    response = _record(
        app,
        kind="table",
        item_id=found.inventory.tables[0].table_id,
        classification="MATERIAL_FILING_CONTENT",
    )
    assert response.status == 400


def test_a_browser_is_returned_to_the_page_it_recorded_from_and_a_script_gets_a_body(
    app: ReviewApp, harness: Harness
) -> None:
    """The redirect target is built from the item KIND, never from anything the browser sent.

    A `return_to` field taken from a form would be an open redirect on an origin holding a session.
    """
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span_id = found.inventory.visible_spans[0].span_id
    redirected = call(
        app,
        "POST",
        f"{BASE}/judgements",
        headers={"Accept": "text/html"},
        body=(
            f"kind=span&item_id={span_id}&classification=NAVIGATION&member={PRIMARY}&start=0"
        ).encode(),
    )
    assert redirected.status == 303
    assert redirected.headers["Location"].startswith(f"{BASE}/spans")
    assert PRIMARY in redirected.headers["Location"]

    element = found.inventory.tables[0]
    to_tables = call(
        app,
        "POST",
        f"{BASE}/judgements",
        headers={"Accept": "text/html"},
        body=f"kind=table&item_id={element.table_id}&classification=LAYOUT".encode(),
    )
    assert to_tables.status == 303
    assert to_tables.headers["Location"] == f"{BASE}/tables"


def test_a_member_the_filing_does_not_contain_never_reaches_the_redirect(
    app: ReviewApp, harness: Harness
) -> None:
    """MUTATION GUARD on the redirect above: the member is checked against the inventory first."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span_id = found.inventory.visible_spans[0].span_id
    response = call(
        app,
        "POST",
        f"{BASE}/judgements",
        headers={"Accept": "text/html"},
        body=f"kind=span&item_id={span_id}&classification=NAVIGATION&member=elsewhere".encode(),
    )
    assert response.status == 303
    assert "elsewhere" not in response.headers["Location"]


# --- the JSON reads -----------------------------------------------------------------------------


def test_the_inventory_json_reports_the_measurement_and_says_it_judges_nothing(
    app: ReviewApp, harness: Harness
) -> None:
    """Every value is a transport measurement, and the document says so in its own words."""
    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    payload = body_json(call(app, "GET", f"/api/benchmark/{CIK}/{ACCESSION}/inventory"))
    assert payload["cik"] == CIK
    assert payload["accession"] == ACCESSION
    assert payload["source_set_sha256"] == found.inventory.source_set_sha256
    assert payload["member_count"] == len(found.inventory.members)
    assert payload["table_count"] == len(found.inventory.tables)
    assert "MEANS" in payload["semantic_note"]


def test_the_truth_json_reports_the_stored_document_and_every_stored_version(
    app: ReviewApp, harness: Harness
) -> None:
    """An empty document at version 0 is a state every filing starts in, not an error."""
    empty = body_json(call(app, "GET", f"/api/benchmark/{CIK}/{ACCESSION}/truth"))
    assert empty["version"] == 0
    assert empty["stored_versions"] == []
    assert empty["spans"] == {}

    found = harness.service.inventoried_filing(CIK, ACCESSION)
    assert found is not None
    span_id = found.inventory.visible_spans[0].span_id
    _record(app, kind="span", item_id=span_id, classification="MATERIAL_FILING_CONTENT")

    filled = body_json(call(app, "GET", f"/api/benchmark/{CIK}/{ACCESSION}/truth"))
    assert filled["version"] == 1
    assert filled["stored_versions"] == [1]
    assert filled["spans"][span_id]["classification"] == "MATERIAL_FILING_CONTENT"
    assert "rule about filings" in filled["scope_note"]


def test_writing_a_version_that_is_already_stored_is_refused(harness: Harness) -> None:
    """A lost update is REPORTED rather than accepted in silence.

    Two reviewers in two browser tabs both read version 3 and both try to write version 4. The
    object store offers no compare-and-swap, so the check narrows the window rather than closing
    it; what it guarantees is that the losing write is told to reload.
    """
    from packages.evaluation_store import BenchmarkTruthVersionExistsError

    truth = BenchmarkTruth(cik=CIK, accession=ACCESSION, source_set_sha256="abc", version=1)
    harness.service.store.save_benchmark_truth(truth.to_mapping())
    with pytest.raises(BenchmarkTruthVersionExistsError):
        harness.service.store.save_benchmark_truth(truth.to_mapping())


def test_version_zero_is_not_storable(harness: Harness) -> None:
    """Version 0 is the derived document a filing starts from, carrying nothing anybody accepted."""
    truth = BenchmarkTruth(cik=CIK, accession=ACCESSION, source_set_sha256="abc", version=0)
    with pytest.raises(ValueError, match="not storable"):
        harness.service.store.save_benchmark_truth(truth.to_mapping())


def test_a_truth_recorded_against_other_bytes_is_flagged_on_every_page(
    app: ReviewApp, harness: Harness
) -> None:
    """Coverage of one filing computed against another filing's denominator is confidently wrong.

    `build_ledger` refuses that pairing outright, so a reviewer who cannot see the drift would go
    on classifying items that no longer exist.
    """
    harness.service.store.save_benchmark_truth(
        BenchmarkTruth(
            cik=CIK, accession=ACCESSION, source_set_sha256="a-different-set", version=1
        ).to_mapping()
    )
    body = page(call(app, "GET", BASE, headers={"Accept": "text/html"}))
    assert "a-different-set" in body
    assert "refuses this pairing" in body
