"""The whole parser-only path, end to end, over a synthetic corpus and the in-process mock.

WHY AN INTEGRATION TEST EXISTS AGAIN. `tests/integration/` was emptied when the deterministic
parser and the application database went, and the `integration` marker went with it because every
test in that directory needed a live PostgreSQL. This one needs nothing: a tmp_path corpus, a
tmp_path prompt directory, a tmp_path capability snapshot, an in-process provider that returns a
fixed document, and no network, no AWS, no credential, no database and no listening socket. That is
the whole reason it is allowed to exist — a suite with an environmental precondition is a suite that
skips, and a skip is a guard that quietly stopped being enforced.

WHAT IT PROTECTS THAT NO UNIT TEST CAN. Every property below is a property of the SEQUENCE, and
each one has already been violated somewhere in this project's history by a component that was
individually correct:

    one child job per filing, never a concatenation
    the source set is reused from what is already held, and SEC is not contacted
    a cost bound exists BEFORE the first billable call, not after it
    the bytes preserved as evidence are the bytes the provider actually saw and returned
    a job reaching READY_FOR_REVIEW says nothing at all about what a reviewer decided
    a page reload loses nothing
    a restart re-invokes NOTHING, however far along a job was
    a parser-only run runs the parser and only the parser
    a filing that does not fit is refused with numbers, and never quietly reaches a provider

NO ARTIFACT CONTRACT IS ASSERTED HERE. The mock's document is a well-formed YAML mapping carrying
the provisional envelope and one node with one verbatim quote. It exercises the reader, the
reference resolver and the audit path; it is not a response schema, and nothing below asserts that
a real model would produce anything shaped like it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from packages.coverage_validation import Resolution, ValidationStatus
from packages.evaluation_store import (
    EvaluationStore,
    ExecutionState,
    ReviewState,
    is_job_id,
    is_run_id,
    summarise_run,
)
from packages.llm_gateway.providers.mock import MockProvider
from packages.model_catalog import ModelRole, load_snapshot
from packages.orchestrator import (
    CorpusFilingCatalog,
    InlineWorker,
    ParserReviewService,
    RunRequest,
    SpendJournal,
    StageNotAuthorizedError,
)
from packages.orchestrator.service import (
    INSTRUCTION_EVIDENCE,
    PROMPT_EVIDENCE,
    RESPONSE_EVIDENCE,
    SOURCE_SET_EVIDENCE,
    VALIDATION_EVIDENCE,
)
from packages.prompt_registry import PromptRegistry
from packages.source_transport import (
    ManifestInventory,
    MemberDisposition,
    PreservedObject,
    SourceMemberMissingError,
)
from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_text

pytestmark = pytest.mark.integration

# --- the synthetic world -------------------------------------------------------------------------
#
# Nothing here is real and nothing here is meant to be. A real issuer, a real accession or the
# committed capability snapshot would make this test depend on artifacts that change for reasons
# that have nothing to do with the orchestration path it is about.

REGION = "region-one"
TEXT_PARSER = "Text Parser"
VISION_PARSER = "Vision Parser"
AUTHOR = "evaluator"
CEILING = Decimal("5.00")

CIK = "0000000042"
ISSUER = "Synthetic Issuer Company"
ACCESSION_RECENT = "0001234567-24-000001"
ACCESSION_EARLIER = "0001234567-23-000002"

#: The sentence the mock's single source reference quotes. It is embedded verbatim, once, in each
#: filing's primary document, so a resolved reference proves the resolver searched the PRESERVED
#: bytes rather than the model's own text.
ANCHOR = "Total net sales increased by a measured amount during the period covered by this report."

PROMPT_TEXT = (
    "You are given the complete human-readable source set of one SEC filing.\n"
    "Return exactly one YAML document describing the filing in the filing's own vocabulary.\n"
    "Quote the preserved source verbatim for every node, and record anything you cannot "
    "resolve as unresolved.\n"
)

MOCK_PARSE_RESPONSE = f"""artifact:
  produced_by: a deterministic in-process mock
document:
  - filename: primary.htm
nodes:
  - id: node-1
    order: 1
    type: Results of Operations
    title: Results of Operations
    content: The filing reports a movement in net sales over the period.
    source:
      - filename: primary.htm
        quote: {ANCHOR}
unresolved: []
metadata:
  note: exercises the reader, the reference resolver and the audit path offline
"""


def _primary_document(accession: str) -> bytes:
    """A small, ASCII, HTML-rooted primary document carrying the anchor sentence exactly once.

    Deliberately padded to a few kilobytes: the incompatibility test needs an estimated input that
    genuinely exceeds a small context window, and a two-line document would fit anything.
    """
    filler = "\n".join(
        f"<p>Paragraph {index} of the synthetic primary document for accession {accession}.</p>"
        for index in range(40)
    )
    return (
        "<html><head><title>Synthetic Annual Report</title></head><body>\n"
        f"<p>{ANCHOR}</p>\n"
        f"{filler}\n"
        "</body></html>\n"
    ).encode("ascii")


def _chart_image() -> bytes:
    """Bytes whose PNG signature is what dispositions them as an image. Not a valid picture."""
    return b"\x89PNG\r\n\x1a\n" + bytes(range(64))


def _submission(accession: str, filing_date: str) -> bytes:
    """An EDGAR complete-submission envelope declaring two individually addressable members.

    ADDRESSABLE ON PURPOSE. The envelope declares a <FILENAME> per document, which is the branch
    where members are reused or fetched as themselves and the flat submission becomes the
    duplicate. It is also the branch where a missing member would generate SEC traffic, which is
    exactly what the zero-fetch assertion is watching for.

    The graphic's payload inside the envelope is an ASCII placeholder, as EDGAR uuencodes binaries
    into the flat submission. The real image bytes exist only as the addressable member, which is
    what actually reaches a multimodal parser.
    """
    stamp = filing_date.replace("-", "")
    return (
        f"<SEC-DOCUMENT>{accession}.txt : {stamp}\n"
        f"<SEC-HEADER>{accession}.hdr.sgml : {stamp}\n"
        f"ACCESSION NUMBER:\t\t{accession}\n"
        "CONFORMED SUBMISSION TYPE:\t10-K\n"
        "PUBLIC DOCUMENT COUNT:\t\t2\n"
        f"FILED AS OF DATE:\t\t{stamp}\n"
        "</SEC-HEADER>\n"
        "<DOCUMENT>\n"
        "<TYPE>10-K\n"
        "<SEQUENCE>1\n"
        "<FILENAME>primary.htm\n"
        "<DESCRIPTION>FORM 10-K\n"
        "<TEXT>\n"
        f"{_primary_document(accession).decode('ascii')}"
        "</TEXT>\n"
        "</DOCUMENT>\n"
        "<DOCUMENT>\n"
        "<TYPE>GRAPHIC\n"
        "<SEQUENCE>2\n"
        "<FILENAME>chart.png\n"
        "<DESCRIPTION>CHART\n"
        "<TEXT>\n"
        "begin 644 chart.png\n"
        "M(" + "A" * 60 + "\n"
        "end\n"
        "</TEXT>\n"
        "</DOCUMENT>\n"
        "</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _candidate(
    *,
    label: str,
    multimodal: bool,
    context_tokens: int,
) -> str:
    """One synthetic snapshot candidate. Every field the loader requires, none of them real."""
    flag = "true" if multimodal else "false"
    return (
        f'  - label: "{label}"\n'
        '    provider: "Synthetic"\n'
        f'    model_id: "synthetic.{label.lower().replace(" ", "-")}"\n'
        f'    model_name: "{label}"\n'
        '    version_qualifier: "v1"\n'
        '    mapping: "UNIQUE"\n'
        '    availability: "AVAILABLE"\n'
        '    access_status: "granted"\n'
        f'    verified_regions: ["{REGION}"]\n'
        "    inference_profile_required: false\n"
        "    inference_profile_id: null\n"
        "    text_input: true\n"
        f"    image_input: {flag}\n"
        f"    multimodal: {flag}\n"
        f"    image_verified: {flag}\n"
        f"    context_tokens: {context_tokens}\n"
        "    max_output_tokens: 4096\n"
        '    invocation_apis: ["Converse"]\n'
        "    streaming_supported: true\n"
        "    price_input_per_1k: 0.001\n"
        "    price_output_per_1k: 0.004\n"
        '    smoke_transport: "ACCEPTED"\n'
        '    smoke_instruction: "EXACT"\n'
        "    blocker: null\n"
        "    disabled_reason: null\n"
    )


def _snapshot_text(*, context_tokens: int) -> str:
    """A two-candidate snapshot: one text-only parser and one multimodal parser."""
    return (
        'snapshot_version: "synthetic-1"\n'
        'verified_on: "2026-01-01"\n'
        f"verified_from_region: {REGION}\n"
        "price_source: a synthetic price list that bills nobody\n"
        'price_effective_date: "2026-01-01"\n'
        "price_currency: USD\n"
        "candidates:\n"
        + _candidate(label=TEXT_PARSER, multimodal=False, context_tokens=context_tokens)
        + _candidate(label=VISION_PARSER, multimodal=True, context_tokens=context_tokens)
    )


class RecordingFetcher:
    """A member fetcher that records every request and then refuses it.

    NOT A NO-OP AND NOT A MOCK OF SUCCESS. If assembly ever decides it needs a member this project
    already holds, the call is recorded so the test can name it, and it raises so the run fails
    loudly rather than silently generating SEC traffic in a suite that must never leave the host.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def fetch(self, cik: str, accession: str, filename: str) -> tuple[PreservedObject, bytes]:
        self.calls.append((cik, accession, filename))
        raise SourceMemberMissingError(
            f"{filename!r} for ({cik}, {accession}) is not held locally and this test contacts "
            "nothing"
        )


@dataclass(frozen=True)
class Harness:
    """Everything one parser-only session is made of, all of it under one tmp_path root."""

    root: Path
    store: EvaluationStore
    journal: SpendJournal
    catalog: CorpusFilingCatalog
    provider: MockProvider
    fetcher: RecordingFetcher
    service: ParserReviewService
    worker: InlineWorker


def _write_corpus(root: Path) -> tuple[Path, ManifestInventory]:
    """Write two preserved filings to disk and return the manifest path and a local inventory.

    Rewriting identical bytes on a second call is deliberate: a simulated restart rebuilds the
    harness over the same directory, and the corpus has to look exactly the same to it.
    """
    corpus = root / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    entries: dict[tuple[str, str], list[PreservedObject]] = {}

    for accession, filing_date, period in (
        (ACCESSION_RECENT, "2024-02-01", "2023-12-31"),
        (ACCESSION_EARLIER, "2023-02-01", "2022-12-31"),
    ):
        members = {
            f"{accession}.txt": _submission(accession, filing_date),
            "primary.htm": _primary_document(accession),
            "chart.png": _chart_image(),
        }
        preserved: list[PreservedObject] = []
        files: list[dict[str, object]] = []
        for filename, data in members.items():
            path = corpus / accession / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            digest = sha256_bytes(data)
            preserved.append(
                PreservedObject(
                    filename=filename,
                    sha256=digest,
                    byte_count=len(data),
                    source_url=f"https://example.invalid/{accession}/{filename}",
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
                    "source_url": f"https://example.invalid/{accession}/{filename}",
                    "local_path": str(path),
                }
            )
        entries[(CIK, accession)] = preserved
        records.append(
            {
                "cik": CIK,
                "accession": accession,
                "form_as_filed": "10-K",
                "filing_date": filing_date,
                "report_period": period,
                "issuer_name_current": ISSUER,
                "tickers_current": ["SYN"],
                "former_names": [],
                "sic_description": "Synthetic manufacturing",
                "transport_era": "addressable-members",
                "is_amendment": False,
                "is_annual": True,
                "form_variant": "10-K",
                "package_file_count": len(files),
                "package_image_count": 1,
                "primary_est_tokens_at_3_0": 1000,
                "files": files,
            }
        )

    manifest = root / "corpus-manifest.json"
    manifest.write_text(json.dumps(records), encoding="utf-8")
    return manifest, ManifestInventory(entries)


def _write_prompts(root: Path) -> PromptRegistry:
    """A prompt directory with one ACTIVE parsing prompt, loaded through its real hash gate."""
    directory = root / "prompts"
    directory.mkdir(parents=True, exist_ok=True)
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
        "    role: parsing\n"
        "    supersedes: null\n"
        "    superseded_by: null\n",
        encoding="utf-8",
    )
    return PromptRegistry.from_directory(directory)


def _harness(
    root: Path,
    *,
    context_tokens: int = 200_000,
    provider: MockProvider | None = None,
) -> Harness:
    """Build a complete parser-only session over ``root``. Called twice to simulate a restart."""
    manifest_path, inventory = _write_corpus(root)
    prompts = _write_prompts(root)
    objects = FilesystemObjectStore(root / "evaluation")
    store = EvaluationStore(objects)
    journal = SpendJournal(objects, ceiling_usd=CEILING)
    catalog = CorpusFilingCatalog.from_manifest(manifest_path)
    mock = provider if provider is not None else MockProvider(MOCK_PARSE_RESPONSE)
    fetcher = RecordingFetcher()
    service = ParserReviewService(
        store=store,
        catalog=catalog,
        snapshot=load_snapshot(_snapshot_text(context_tokens=context_tokens)),
        prompts=prompts,
        inventory=inventory,
        fetcher=fetcher,
        provider=mock,
        journal=journal,
        preferred_region=REGION,
        author=AUTHOR,
    )
    return Harness(
        root=root,
        store=store,
        journal=journal,
        catalog=catalog,
        provider=mock,
        fetcher=fetcher,
        service=service,
        worker=InlineWorker(service),
    )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    """A parser-only session whose selected model is text-only and whose context is generous."""
    return _harness(tmp_path)


def _both_filings() -> RunRequest:
    return RunRequest(cik=CIK, parsing_label=TEXT_PARSER)


def _one_filing(*, label: str = TEXT_PARSER) -> RunRequest:
    return RunRequest(cik=CIK, parsing_label=label, accessions=(ACCESSION_RECENT,))


# --- anti-vacuity ---------------------------------------------------------------------------------


def test_the_synthetic_world_is_the_world_these_tests_think_it_is() -> None:
    """Every assertion below is meaningless if the fixtures do not have the shape they assume.

    A corpus with one filing cannot show that two filings produce two jobs; a submission EDGAR
    would not recognise lists no documents and every coverage count then reconciles against
    nothing. This is the guard on the guards.
    """
    submission = _submission(ACCESSION_RECENT, "2024-02-01")
    assert b"<SEC-DOCUMENT>" in submission[:8192]
    assert submission.count(b"<FILENAME>") == 2, "the envelope must declare addressable members"
    assert ANCHOR.encode("ascii") in _primary_document(ACCESSION_RECENT)
    assert _primary_document(ACCESSION_RECENT).count(ANCHOR.encode("ascii")) == 1
    assert len(_primary_document(ACCESSION_RECENT)) > 3000, (
        "the primary document must be large enough that a small context genuinely cannot hold it"
    )
    assert ACCESSION_RECENT != ACCESSION_EARLIER


def test_the_snapshot_offers_one_text_only_and_one_multimodal_candidate(harness: Harness) -> None:
    """The image path and the text-only path are different code paths and both are exercised.

    A snapshot with only text-only candidates would make the image-coverage assertions vacuous:
    `analysed: false` would be the only answer the system could ever give.
    """
    rows = harness.service.selectors()["roles"][ModelRole.PARSING.value]["entries"]
    badges = {row["label"]: row["badge"] for row in rows}
    assert badges == {TEXT_PARSER: "Text only", VISION_PARSER: "Multimodal"}
    assert all(row["available"] for row in rows), "both candidates must be selectable"


# --- one filing, one child job ---------------------------------------------------------------------


def test_two_filings_produce_two_child_jobs_and_never_one_concatenated_request(
    harness: Harness,
) -> None:
    """A multi-filing request is N independent billable units, never one call with N filings in it.

    A concatenated request cannot be reviewed per filing, costed per filing, approved per filing or
    failed per filing, which is why rules.md section 1 point 5 forbids it. The strongest available
    evidence is the provider's own view: two requests, each naming exactly one accession and
    carrying exactly one filing's preserved bytes.
    """
    run = harness.service.create_run(_both_filings())
    harness.worker.submit_run(run.run_id)

    assert len(run.job_ids) == 2
    assert len(set(run.job_ids)) == 2, "two filings must not share one child job identifier"
    assert all(is_job_id(job_id) for job_id in run.job_ids)
    assert is_run_id(run.run_id)

    accessions = {job.accession for job in harness.store.load_jobs(run.run_id)}
    assert accessions == {ACCESSION_RECENT, ACCESSION_EARLIER}

    assert len(harness.provider.invocations) == 2
    for request in harness.provider.invocations:
        named = [a for a in (ACCESSION_RECENT, ACCESSION_EARLIER) if a in request.user_content]
        assert len(named) == 1, f"one request named {named}; a request carries exactly one filing"
        assert len(request.original_source) == 1, "one text artifact per request, not two filings'"


# --- local reuse, no SEC traffic ---------------------------------------------------------------------


def test_the_source_set_is_reused_from_local_storage_and_sec_is_never_contacted(
    harness: Harness,
) -> None:
    """Reuse what is held, hash-verified, and fetch only what is missing. Here nothing is missing.

    The fetcher records and refuses, so a regression that stopped consulting the local inventory
    would appear as a named call rather than as a silent network request in a suite that must have
    no environmental precondition at all.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)

    assert harness.fetcher.calls == [], "a preserved member was fetched instead of reused"

    job = harness.store.load_jobs(run.run_id)[0]
    assert job.source_set is not None
    assert job.source_set["fetched_members"] == 0
    assert job.source_set["reused_members"] == 3, "submission, primary document and image"
    dispositions = job.source_set["counts_by_disposition"]
    assert dispositions[MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION.value] == 1
    assert dispositions[MemberDisposition.PARSER_INPUT_TEXT.value] == 1
    assert dispositions[MemberDisposition.PARSER_INPUT_IMAGE.value] == 1


# --- a cost bound before any spend --------------------------------------------------------------------


def test_preflight_bounds_the_cost_of_every_filing_before_anything_is_invoked(
    harness: Harness,
) -> None:
    """No billable invocation happens without a preview against the ceiling — section 21 rule 11.

    Preflight is also where the answer to `will this fit` is computed, so it deliberately assembles
    real source sets. Assembling them must cost nothing and must reach no provider.
    """
    plan = harness.service.preflight(_both_filings())

    assert harness.provider.invocations == [], "preflight invoked a model"
    assert harness.journal.spent_usd == Decimal(0), "preflight reserved money"
    assert len(plan.items) == 2
    assert all(item.compatible for item in plan.items)
    assert plan.worst_case_total_usd > 0, "a bound of zero is not a bound"
    assert plan.within_ceiling
    assert plan.ceiling_usd == CEILING

    mapping = plan.to_mapping()
    assert mapping["compatible_filings"] == 2
    assert mapping["incompatible_filings"] == 0
    assert "WORST-CASE" in mapping["cost_note"]
    assert mapping["routing"][ModelRole.PARSING.value]["region"] == REGION
    assert set(mapping["routing"]) == {ModelRole.PARSING.value}, "a blank role must not be routed"


def test_the_reserved_bound_is_settled_against_measured_usage_after_the_call(
    harness: Harness,
) -> None:
    """Reserve before, settle after, and record both halves so the arithmetic is auditable.

    A ledger that only recorded the measured figure could not show what was authorized, and one
    that only recorded the reservation would drift from the bill for ever.
    """
    plan = harness.service.preflight(_one_filing())
    run = harness.service.create_run(_one_filing(), plan=plan)
    harness.worker.submit_run(run.run_id)

    kinds = [entry.kind for entry in harness.journal.entries]
    assert kinds == ["RESERVATION", "SETTLEMENT"]
    reservation, settlement = harness.journal.entries
    assert reservation.amount_usd == plan.items[0].worst_case_cost_usd
    assert settlement.released_usd == reservation.amount_usd
    assert settlement.amount_usd <= reservation.amount_usd, (
        "the measured cost must not exceed the worst case that was authorized"
    )

    job = harness.store.load_jobs(run.run_id)[0]
    assert job.reserved_cost_usd == reservation.amount_usd
    assert job.actual_cost_usd == settlement.amount_usd


# --- exact evidence ----------------------------------------------------------------------------------


def test_the_preserved_evidence_is_byte_identical_to_what_the_provider_saw_and_returned(
    harness: Harness,
) -> None:
    """The review UI shows what the model ACTUALLY received; anything else is a reconstruction.

    rules.md section 3 and the gateway's own security invariant both require the exact
    model-visible request and the exact response to be persisted unmodified. This asserts the
    identity in the only way that means anything: against the provider's own record of the call.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)
    job_id = run.job_ids[0]
    request = harness.provider.invocations[0]

    assert harness.store.get_evidence_text(run.run_id, job_id, INSTRUCTION_EVIDENCE) == (
        request.user_content
    )
    assert harness.store.get_evidence_text(run.run_id, job_id, PROMPT_EVIDENCE) == (
        request.system_text
    )
    assert harness.store.get_evidence_text(run.run_id, job_id, PROMPT_EVIDENCE) == PROMPT_TEXT
    assert harness.store.get_evidence(run.run_id, job_id, RESPONSE_EVIDENCE) == (
        MOCK_PARSE_RESPONSE.encode("utf-8")
    )


def test_the_preserved_source_bytes_reach_the_model_intact_and_are_stored_beside_the_run(
    harness: Harness,
) -> None:
    """A filing is admitted by PROVENANCE, and the run keeps its own copy of what it sent.

    Resolving the artifact from a corpus path months later depends on a file nobody promised not to
    move, so `execute_job` writes the exact block bytes into the job's evidence directory. Both
    copies must hash to what the inventory recorded, or the original-source exception does not
    cover them.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)
    job_id = run.job_ids[0]

    expected = _primary_document(ACCESSION_RECENT)
    block = harness.provider.invocations[0].original_source[0]
    assert block.raw_bytes == expected
    assert block.sha256 == sha256_bytes(expected)
    assert block.text is not None and block.text.encode(block.codec or "") == expected

    stored = harness.store.get_evidence(run.run_id, job_id, "source-01.txt")
    assert stored == expected, "the stored source evidence is not the bytes that were sent"
    assert sha256_bytes(stored) == block.sha256

    names = harness.store.list_evidence(run.run_id, job_id)
    assert "source-02.bin" not in names, (
        "a text-only parser received an image block; the image must stay unsent and unanalysed"
    )
    assert {INSTRUCTION_EVIDENCE, PROMPT_EVIDENCE, RESPONSE_EVIDENCE}.issubset(names)
    assert {SOURCE_SET_EVIDENCE, VALIDATION_EVIDENCE}.issubset(names)


# --- validation and the two independent state machines -------------------------------------------------


def test_a_validated_job_reaches_ready_for_review_with_its_review_state_untouched(
    harness: Harness,
) -> None:
    """READY_FOR_REVIEW says a person CAN look at it, and nothing at all about what they decided.

    Deriving a review state from an execution state is how an unreviewed artifact acquires the
    authority of an approved one. The two machines are separate and this is the point at which they
    are most tempting to collapse.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)
    job = harness.store.load_jobs(run.run_id)[0]

    assert job.execution_state is ExecutionState.READY_FOR_REVIEW
    assert job.review_state is ReviewState.EVALUATION
    assert job.review_history == []
    assert job.failure is None
    assert len(job.attempts) == 1
    assert job.attempts[0].input_tokens > 0

    assert job.validation is not None
    assert job.validation["yaml_parsed"] is True
    assert job.validation["boundary_ok"] is True
    assert job.validation["missing_envelope_keys"] == []
    assert job.validation["node_count"] == 1
    assert job.validation["references_resolved"] == 1
    assert job.validation["references"][0]["resolution"] == Resolution.EXACT.value


def test_a_text_only_parser_never_claims_image_coverage_and_the_verdict_is_never_complete(
    harness: Harness,
) -> None:
    """A run that quietly omits images while reporting a complete parse is a false completeness claim.

    Two invariants meet here. The image-bearing member is NAMED as unanalysed rather than dropped
    from the record, and the strongest verdict the validator can issue is PARTIAL or
    REVIEW_REQUIRED — COMPLETE is not a value it owns.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)
    job = harness.store.load_jobs(run.run_id)[0]

    assert job.image_coverage is not None
    assert job.image_coverage["analysed"] is False
    assert job.image_coverage["image_member_count"] == 1
    assert [m["filename"] for m in job.image_coverage["members"]] == ["chart.png"]
    assert job.image_coverage["members"][0]["submitted_to_parser"] is False

    assert job.validation is not None
    assert job.validation["status"] == ValidationStatus.PARTIAL.value
    assert "COMPLETE" in job.validation["status_note"]
    assert any("NOT analysed" in finding for finding in job.validation["findings"])
    assert ValidationStatus.__members__.keys().isdisjoint({"COMPLETE"})


def test_a_multimodal_parser_receives_the_image_and_the_run_does_claim_image_coverage(
    tmp_path: Path,
) -> None:
    """The mutation of the test above: the same filing, a model with a verified image path.

    If image handling silently did nothing, `analysed: false` would be the only answer the system
    could produce and the assertion above would pass for the wrong reason. Selecting the multimodal
    candidate must change the request, the evidence and the verdict.
    """
    session = _harness(tmp_path)
    run = session.service.create_run(_one_filing(label=VISION_PARSER))
    session.worker.submit_run(run.run_id)
    job = session.store.load_jobs(run.run_id)[0]

    blocks = session.provider.invocations[0].original_source
    assert [b.is_image for b in blocks] == [False, True]
    assert blocks[1].raw_bytes == _chart_image()
    assert blocks[1].image_format == "png"

    assert session.store.get_evidence(run.run_id, job.job_id, "source-02.bin") == _chart_image()
    assert job.image_coverage is not None
    assert job.image_coverage["analysed"] is True
    assert job.image_coverage["members"][0]["submitted_to_parser"] is True
    assert job.validation is not None
    assert job.validation["status"] == ValidationStatus.REVIEW_REQUIRED.value


# --- review: comments and decisions ----------------------------------------------------------------------


def test_a_comment_is_bound_to_the_artifact_version_it_was_written_against(
    harness: Harness,
) -> None:
    """A comment written about attempt 1 must not silently become a comment about attempt 2.

    Comments are DATA. They are stored beside the run, they carry the version they targeted, and
    they never enter model-visible content — a reviewer's note beside a filing is untrusted input
    to a model exactly as the filing is.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)
    job = harness.store.load_jobs(run.run_id)[0]

    comment = harness.service.add_comment(
        run.run_id,
        target_type="node",
        target_id="node-1",
        text="the node title reproduces the filing's own heading",
        job_id=job.job_id,
        target_version=str(len(job.attempts)),
        tags=("titles",),
    )

    assert comment.target_version == "1"
    assert comment.child_job_id == job.job_id
    assert comment.author == AUTHOR
    assert comment.status == "OPEN"

    for_job = harness.store.list_comments(run.run_id, job_id=job.job_id)
    assert [c.comment_id for c in for_job] == [comment.comment_id]
    assert harness.store.list_comments(run.run_id, job_id="job_" + "a" * 26) == [], (
        "a comment must be returned only for the child job it was written against"
    )


def test_a_review_decision_is_appended_to_history_and_leaves_the_execution_state_alone(
    harness: Harness,
) -> None:
    """A human judgement records itself and changes no machinery.

    The review trail is appended to, never rewritten, because rules.md invariant 7 forbids
    overwriting an accepted decision and a trail that can be edited is not a trail.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)
    job_id = run.job_ids[0]

    harness.store.set_review_state(
        run.run_id, job_id, ReviewState.UNDER_REVIEW, author=AUTHOR, note="reading it now"
    )
    reviewed = harness.store.set_review_state(
        run.run_id, job_id, ReviewState.APPROVED, author=AUTHOR
    )

    assert reviewed.review_state is ReviewState.APPROVED
    assert reviewed.execution_state is ExecutionState.READY_FOR_REVIEW, (
        "a review decision changed the execution state"
    )
    assert [(t.from_state, t.to_state) for t in reviewed.review_history] == [
        (ReviewState.EVALUATION.value, ReviewState.UNDER_REVIEW.value),
        (ReviewState.UNDER_REVIEW.value, ReviewState.APPROVED.value),
    ]
    assert reviewed.review_history[0].note == "reading it now"


# --- the page-reload requirement ---------------------------------------------------------------------


def test_a_brand_new_store_over_the_same_directory_returns_the_entire_session(
    harness: Harness,
) -> None:
    """A review session that loses its work on a page reload is not a review session.

    The reload is modelled exactly as it happens: a second `EvaluationStore` constructed over the
    same directory, sharing no in-memory state with the first. Everything the reviewer had must
    come back — the run, the jobs, the comments, the event log and the exact evidence bytes.
    """
    run = harness.service.create_run(_both_filings())
    harness.worker.submit_run(run.run_id)
    job_id = run.job_ids[0]
    harness.service.add_comment(
        run.run_id,
        target_type="artifact",
        target_id=job_id,
        text="survives a reload",
        job_id=job_id,
    )
    original_events = harness.store.read_events(run.run_id)

    reloaded = EvaluationStore.at_path(harness.root / "evaluation")

    assert reloaded.list_run_ids() == [run.run_id]
    assert (
        reloaded.load_run(run.run_id).to_mapping()
        == harness.store.load_run(run.run_id).to_mapping()
    )
    assert reloaded.list_job_ids(run.run_id) == harness.store.list_job_ids(run.run_id)
    assert [c.text for c in reloaded.list_comments(run.run_id)] == ["survives a reload"]

    replayed = reloaded.read_events(run.run_id)
    assert [(e.event_id, e.kind, e.message) for e in replayed] == [
        (e.event_id, e.kind, e.message) for e in original_events
    ]
    assert len(replayed) > 5, "an empty event log would make this comparison vacuous"
    assert reloaded.read_events(run.run_id, after=replayed[0].sequence) == replayed[1:], (
        "Last-Event-ID resumption must replay from the event after the one the browser saw"
    )

    assert reloaded.get_evidence(run.run_id, job_id, RESPONSE_EVIDENCE) == (
        MOCK_PARSE_RESPONSE.encode("utf-8")
    )
    assert sorted(reloaded.list_evidence(run.run_id, job_id)) == sorted(
        harness.store.list_evidence(run.run_id, job_id)
    )


# --- restart -------------------------------------------------------------------------------------------


def test_a_restart_marks_an_in_flight_job_interrupted_and_re_invokes_nothing(
    tmp_path: Path,
) -> None:
    """A process that came back up is not a user who asked to spend money again.

    A job that was RUNNING may or may not have been billed, so the only honest thing is to say so
    and wait for a person. The assertion that matters is the negative one: the provider's
    invocation count is identical before and after the restart, and the job that had already
    finished is not swept along with the one that had not.
    """
    session = _harness(tmp_path)
    run = session.service.create_run(_both_filings())
    finished_id, in_flight_id = run.job_ids

    session.worker.submit(run.run_id, finished_id)
    invocations_before = len(session.provider.invocations)
    assert invocations_before == 1, "only the first child job was executed"

    in_flight = session.store.load_job(run.run_id, in_flight_id)
    session.store.set_execution_state(in_flight, ExecutionState.RUNNING)

    restarted = _harness(tmp_path, provider=session.provider)
    touched = restarted.store.mark_interrupted_jobs()

    assert touched == [(run.run_id, in_flight_id)]
    assert len(restarted.provider.invocations) == invocations_before, (
        "a restart re-invoked a model; nothing is ever rerun without an explicit user action"
    )

    swept = restarted.store.load_job(run.run_id, in_flight_id)
    assert swept.execution_state is ExecutionState.INTERRUPTED
    assert swept.failure is not None and "NOT rerun" in swept.failure

    untouched = restarted.store.load_job(run.run_id, finished_id)
    assert untouched.execution_state is ExecutionState.READY_FOR_REVIEW, (
        "a terminal job was swept into INTERRUPTED by a restart"
    )
    assert untouched.failure is None


# --- only the selected stages run -----------------------------------------------------------------------


def test_a_parser_only_run_invokes_exactly_one_model_and_selects_exactly_one_role(
    harness: Harness,
) -> None:
    """Only the parsing model is required, and a parser-only run is a complete, valid run.

    A blank image, summary or analysis selector produces no routing entry and therefore no stage —
    the absence of the entry IS the absence of the stage. One filing must therefore cost exactly
    one invocation, whatever the other three selectors look like.
    """
    run = harness.service.create_run(_one_filing())
    harness.worker.submit_run(run.run_id)

    assert len(harness.provider.invocations) == 1
    assert list(run.selected_roles) == ["parsing"]
    assert (run.image_label, run.summary_label, run.analysis_label) == (None, None, None)

    stored = harness.store.load_run(run.run_id)
    assert list(stored.selected_roles) == ["parsing"]
    assert stored.to_mapping()["selections"] == {
        "parsing": TEXT_PARSER,
        "image": None,
        "summary": None,
        "analysis": None,
    }
    assert summarise_run(stored, harness.store.load_jobs(run.run_id))["selected_roles"] == [
        "parsing"
    ]


@pytest.mark.parametrize("role", ["image", "summary", "analysis"])
def test_selecting_an_unauthorized_stage_refuses_rather_than_quietly_running_it(
    harness: Harness, role: str
) -> None:
    """Phase 2 executes the parsing stage only, and a filled selector is a scope violation.

    The other three selectors exist so the progressive workflow is real. Running one because it was
    filled in would spend money on a stage no one authorized, which is why this raises with the
    role NAMED instead of ignoring the selection.
    """
    request = RunRequest(
        cik=CIK,
        parsing_label=TEXT_PARSER,
        accessions=(ACCESSION_RECENT,),
        **{f"{role}_label": VISION_PARSER},
    )
    with pytest.raises(StageNotAuthorizedError) as error:
        harness.service.create_run(request)

    assert role in str(error.value)
    assert harness.provider.invocations == [], "an unauthorized stage reached a provider"
    assert harness.store.list_run_ids() == [], "a refused run must leave no parent run behind"


def test_a_parsing_only_selection_is_not_refused(harness: Harness) -> None:
    """The mutation guard on the refusal above. A parser-only run must still be accepted.

    A `StageNotAuthorizedError` raised unconditionally would satisfy every assertion in the test
    above while breaking the only workflow this phase has.
    """
    run = harness.service.create_run(_one_filing())
    assert harness.store.run_exists(run.run_id)
    assert list(run.selected_roles) == ["parsing"]


# --- incompatibility ----------------------------------------------------------------------------------


def test_a_filing_that_exceeds_the_model_context_never_reaches_the_provider(
    tmp_path: Path,
) -> None:
    """INTACT_SOURCE_ONLY: it fits or the pairing is refused, with the arithmetic on the record.

    Nothing is truncated, sliced, split or swapped to a cheaper model. The refusal has to carry the
    numbers a person can check, because `incompatible` on its own sends a user to a support channel
    rather than to a different model.
    """
    session = _harness(tmp_path, context_tokens=500)
    run = session.service.create_run(_one_filing())
    queued = session.worker.submit_run(run.run_id)

    assert queued == 0
    assert session.provider.invocations == [], "an incompatible filing reached a provider"
    assert session.journal.spent_usd == Decimal(0), "an incompatible filing reserved money"

    job = session.store.load_jobs(run.run_id)[0]
    assert job.execution_state is ExecutionState.INCOMPATIBLE
    assert job.incompatibility is not None
    assert job.incompatibility.reason == "source_set_exceeds_context"
    assert job.incompatibility.model_context_tokens == 500
    assert job.incompatibility.estimated_input_tokens is not None
    assert job.incompatibility.estimated_input_tokens > 500
    assert job.incompatibility.source_set_bytes is not None
    assert job.incompatibility.source_set_bytes > 0
    assert "INTACT_SOURCE_ONLY" in job.incompatibility.detail
    assert str(job.incompatibility.model_context_tokens) in job.incompatibility.detail.replace(
        ",", ""
    )


def test_the_same_filing_against_a_sufficient_context_is_not_flagged_incompatible(
    harness: Harness,
) -> None:
    """The mutation guard on the refusal above. The compatibility gate must not refuse everything.

    A gate wired to `compatible = False` would pass every assertion in the previous test while
    making the product incapable of parsing anything at all.
    """
    run = harness.service.create_run(_one_filing())
    job = harness.store.load_jobs(run.run_id)[0]

    assert job.execution_state is ExecutionState.QUEUED
    assert job.incompatibility is None
    assert harness.worker.submit_run(run.run_id) == 1
    assert len(harness.provider.invocations) == 1


def test_a_source_set_that_changed_after_preflight_refuses_the_job(harness: Harness) -> None:
    """The set that was COSTED must be the set that is SENT, or nothing is sent.

    Preflight assembles a source set, bounds its cost and records its identity. Execution happens
    later, on a worker, and assembles it again. If a member was re-acquired or a corrected member
    was published in between, the two sets differ — and the run would spend against a bound
    computed for different bytes while recording a `source_set_id` that does not describe what was
    submitted. Both halves of that are wrong, and neither is visible afterwards.

    Simulated by rewriting the recorded identity on the stored job, which is exactly the state a
    changed source set produces.
    """
    run = harness.service.create_run(_one_filing())
    job = harness.store.load_jobs(run.run_id)[0]
    job.source_set_id = "0" * 64
    harness.store.save_job(job)

    before = len(harness.provider.invocations)
    harness.service.execute_job(run.run_id, job.job_id)
    after = harness.store.load_job(run.run_id, job.job_id)

    assert after.execution_state is ExecutionState.FAILED
    assert "source set changed" in (after.failure or "")
    assert len(harness.provider.invocations) == before, (
        "a job whose source set changed must not reach the provider at all"
    )
