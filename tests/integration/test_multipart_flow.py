"""The model-directed multipart path, end to end, over a synthetic corpus and a scripted provider.

WHAT THIS PROTECTS THAT NO UNIT TEST CAN. Every property below is a property of the SEQUENCE, and
the sequence is the whole point of Phase 2.1:

    a plan is the first billable call, and the parts come from the plan the MODEL wrote
    every semantic call receives the COMPLETE intact source set, not a slice of it
    a part that says it is too large produces subparts the MODEL proposed
    a truncated attempt is preserved, marked, and NEVER continued
    a truncated attempt produces a replanning call that divides the WHOLE original part
    reconciliation may add work, and the work it adds runs
    one failed part does not erase the parts that succeeded
    a restart re-invokes nothing and loses no completed part
    every attempt takes its own reservation, and the totals reconcile in the assembly
    the assembly is an INDEX: model order, model titles, no merging and no renaming

NO ARTIFACT CONTRACT IS ASSERTED. The scripted responses are well-formed YAML documents carrying
the provisional multipart envelopes. They exercise the readers, the scheduler, the reference
resolver and the assembly; they are not a response schema, and nothing here claims a real model
would produce anything shaped like them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from packages.evaluation_store import (
    RESUMABLE_TASK_STATES,
    EvaluationStore,
    ExecutionState,
    TaskState,
    TaskType,
)
from packages.llm_gateway import parse_yaml
from packages.llm_gateway.errors import ProviderError
from packages.llm_gateway.providers.base import ModelProvider, ModelRequest, ModelResponse
from packages.llm_gateway.token_counter import estimate_tokens
from packages.model_catalog import load_snapshot
from packages.multipart import AssemblyStatus
from packages.orchestrator import (
    MULTIPART_STRATEGY,
    CorpusFilingCatalog,
    InlineWorker,
    MultipartSettings,
    ParserReviewService,
    RunRequest,
    SpendJournal,
)
from packages.orchestrator.multipart_service import RESPONSE_EVIDENCE
from packages.orchestrator.sizing import part_sizing
from packages.prompt_registry import PromptRegistry
from packages.source_transport import (
    ManifestInventory,
    PreservedObject,
    SourceMemberMissingError,
)
from packages.storage import FilesystemObjectStore, sha256_bytes, sha256_text

pytestmark = pytest.mark.integration

REGION = "region-one"
PARSER = "Text Parser"
AUTHOR = "evaluator"
CEILING = Decimal("5.00")
CIK = "0000000042"
ISSUER = "Synthetic Issuer Company"
ACCESSION = "0001234567-24-000001"

#: Sentences embedded verbatim, once each, in the preserved primary document. A resolved reference
#: proves the resolver searched the PRESERVED bytes rather than the model's own text.
ANCHOR_ONE = "The first anchor sentence appears exactly once in the preserved primary document."
ANCHOR_TWO = "The second anchor sentence also appears exactly once in the preserved document."

PLAN_RESPONSE = """parse_plan_id: "plan-alpha"
parts:
  - part_id: "front"
    order: 1
    title: A Heading The Filing Uses
    type: whatever the model calls it
    purpose: the opening material
    expected_output_tokens: 2000
  - part_id: "middle"
    order: 2
    title: Another Heading The Filing Uses
    type: a different model-chosen kind
    purpose: the material after the opening
    may_require_subparts: true
    expected_output_tokens: 9000
  - part_id: "back"
    order: 3
    title: A Third Heading
    type: a third model-chosen kind
    purpose: the closing material
    depends_on:
      - "front"
    expected_output_tokens: 1500
unassigned: []
uncertainty: []
metadata:
  note: a scripted plan, not a real one
"""

PART_FRONT = f"""parse_plan_id: "plan-alpha"
part_id: "front"
status: complete
title: A Heading The Filing Uses
type: whatever the model calls it
nodes:
  - id: "n1"
    order: 1
    type: a model-chosen node kind
    title: A Heading The Filing Uses
    content: what the opening material says
    source:
      - filename: primary.htm
        quote: "{ANCHOR_ONE}"
unresolved: []
coverage_summary: the opening material, in full
metadata: {{}}
"""

PART_MIDDLE_NEEDS_SUBPARTS = """parse_plan_id: "plan-alpha"
part_id: "middle"
status: needs_subparts
title: Another Heading The Filing Uses
type: a different model-chosen kind
unresolved: []
coverage_summary: too large for one response
subparts_required: true
proposed_subparts:
  - part_id: "middle-a"
    order: 1
    title: First Half Of Another Heading
    type: a model-chosen kind
    purpose: the first half
  - part_id: "middle-b"
    order: 2
    title: Second Half Of Another Heading
    type: a model-chosen kind
    purpose: the second half
metadata: {}
"""

PART_MIDDLE_A = f"""parse_plan_id: "plan-alpha"
part_id: "middle-a"
parent_part_id: "middle"
status: complete
title: First Half Of Another Heading
type: a model-chosen kind
nodes:
  - id: "n2"
    order: 1
    type: a model-chosen node kind
    title: First Half Of Another Heading
    content: what the first half says
    source:
      - filename: primary.htm
        quote: "{ANCHOR_TWO}"
unresolved: []
coverage_summary: the first half
metadata: {{}}
"""

#: The response the scripted provider TRUNCATES. It is deliberately a valid prefix that would parse
#: on its own, so the test proves truncation is detected from the provider's STOP REASON rather than
#: from the text looking broken.
PART_MIDDLE_B_TRUNCATED = """parse_plan_id: "plan-alpha"
part_id: "middle-b"
parent_part_id: "middle"
status: complete
title: Second Half Of Another Heading
type: a model-chosen kind
nodes:
  - id: "n3"
    order: 1
    type: a model-chosen node kind
    title: Second Half Of Another Heading
    content: what the second half says, cut off in the middle of
"""

REPLAN_RESPONSE = """parse_plan_id: "plan-alpha"
part_id: "middle-b"
covered_before_truncation:
  - what: the opening of the second half
remaining:
  - what: everything after that
proposed_subparts:
  - part_id: "middle-b-1"
    order: 1
    title: Second Half, First Portion
    type: a model-chosen kind
    purpose: covers the whole of the original second half, first portion
  - part_id: "middle-b-2"
    order: 2
    title: Second Half, Second Portion
    type: a model-chosen kind
    purpose: covers the whole of the original second half, second portion
overlap_risk: the two portions are divided at a boundary the filing itself uses
uncertainty: []
metadata: {}
"""

RECONCILE_ADDS_WORK = """parse_plan_id: "plan-alpha"
cycle: 1
plan_complete: false
missing:
  - where: after the closing material
    what: something no part covered
    why: the plan did not assign it
duplicated: []
conflicting: []
additional_parts:
  - part_id: "appendix"
    order: 9
    title: A Heading Reconciliation Named
    type: a model-chosen kind
    purpose: the material no part covered
replacement_parts: []
unresolvable: []
model_declared_coverage: one piece of material was not covered and one more part is required
metadata: {}
"""

RECONCILE_COMPLETE = """parse_plan_id: "plan-alpha"
cycle: 2
plan_complete: true
missing: []
duplicated: []
conflicting: []
additional_parts: []
replacement_parts: []
unresolvable: []
model_declared_coverage: every part of the plan is now covered
metadata: {}
"""


def _generic_part(part_id: str, title: str) -> str:
    return f"""parse_plan_id: "plan-alpha"
part_id: "{part_id}"
status: complete
title: {title}
type: a model-chosen kind
nodes:
  - id: "node-{part_id}"
    order: 1
    type: a model-chosen node kind
    title: {title}
    content: what this material says
unresolved: []
coverage_summary: this material, in full
metadata: {{}}
"""


class ScriptedProvider(ModelProvider):
    """Returns a response chosen by the BRIEF KIND and the requested part identifier.

    It reads the compiled brief rather than being handed a script index, so the test also proves
    that the orchestrator actually asked for the part it thinks it asked for. A provider driven by
    a counter would pass even if every request named the wrong part.
    """

    name = "scripted"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self.truncate_once: set[str] = {"middle-b"}
        self.fail_once: set[str] = set()
        self.reconcile_calls = 0

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        brief = parse_yaml(request.user_content)
        kind = brief.get("brief")
        stop_reason = "end_turn"

        if kind == "planning":
            text = PLAN_RESPONSE
        elif kind == "part":
            part_id = str(brief["requested_part"]["part_id"])
            if part_id in self.fail_once:
                self.fail_once.discard(part_id)
                # A NON-RETRYABLE provider failure, which is what a permanent refusal looks like.
                # A retryable one would consume the retry budget and succeed on the second call,
                # which is a different test.
                raise ProviderError(
                    f"scripted permanent failure for part {part_id}",
                    retryable=False,
                    provider=self.name,
                )
            if part_id == "front":
                text = PART_FRONT
            elif part_id == "middle":
                text = PART_MIDDLE_NEEDS_SUBPARTS
            elif part_id == "middle-a":
                text = PART_MIDDLE_A
            elif part_id == "middle-b" and part_id in self.truncate_once:
                self.truncate_once.discard(part_id)
                text = PART_MIDDLE_B_TRUNCATED
                stop_reason = "max_tokens"
            else:
                text = _generic_part(part_id, f"Title For {part_id}")
        elif kind == "replan":
            text = REPLAN_RESPONSE
        elif kind == "reconcile":
            self.reconcile_calls += 1
            text = RECONCILE_ADDS_WORK if self.reconcile_calls == 1 else RECONCILE_COMPLETE
        elif kind == "gap":
            text = RECONCILE_COMPLETE
        else:
            text = "repaired: true\n"

        return ModelResponse(
            text=text,
            input_tokens=estimate_tokens(request.user_content)
            + sum(estimate_tokens(b.text or "") for b in request.original_source),
            output_tokens=estimate_tokens(text),
            model_id=request.model_id,
            provider=self.name,
            stop_reason=stop_reason,
            truncated=stop_reason == "max_tokens",
        )


# --- the synthetic world ---------------------------------------------------------------------------


def _primary_document() -> bytes:
    filler = "\n".join(
        f"<p>Paragraph {index} of the synthetic document.</p>" for index in range(60)
    )
    return (
        "<html><head><title>Synthetic Annual Report</title></head><body>\n"
        f"<p>{ANCHOR_ONE}</p>\n<p>{ANCHOR_TWO}</p>\n{filler}\n</body></html>\n"
    ).encode("ascii")


def _submission() -> bytes:
    return (
        f"<SEC-DOCUMENT>{ACCESSION}.txt : 20240201\n"
        f"<SEC-HEADER>{ACCESSION}.hdr.sgml : 20240201\n"
        f"ACCESSION NUMBER:\t\t{ACCESSION}\n"
        "CONFORMED SUBMISSION TYPE:\t10-K\n"
        "PUBLIC DOCUMENT COUNT:\t\t1\n"
        "FILED AS OF DATE:\t\t20240201\n"
        "</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>10-K\n<SEQUENCE>1\n<FILENAME>primary.htm\n"
        "<DESCRIPTION>FORM 10-K\n<TEXT>\n"
        f"{_primary_document().decode('ascii')}"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _snapshot_text() -> str:
    return (
        'snapshot_version: "synthetic-1"\n'
        'verified_on: "2026-01-01"\n'
        f"verified_from_region: {REGION}\n"
        "price_source: a synthetic price list that bills nobody\n"
        'price_effective_date: "2026-01-01"\n'
        "price_currency: USD\n"
        "candidates:\n"
        f'  - label: "{PARSER}"\n'
        '    provider: "Synthetic"\n'
        '    model_id: "synthetic.text-parser"\n'
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


#: One synthetic prompt per multipart role, plus the single-response role the registry still needs.
_ROLES = (
    ("parsing", "single"),
    ("parsing_multipart_plan", "plan"),
    ("parsing_multipart_part", "part"),
    ("parsing_multipart_replan", "replan"),
    ("parsing_multipart_reconcile", "reconcile"),
    ("parsing_multipart_gap", "gap"),
    ("parsing_multipart_format_repair", "repair"),
)


class RecordingFetcher:
    """Records any attempt to contact SEC and then refuses it. This suite reaches nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def fetch(self, cik: str, accession: str, filename: str) -> tuple[PreservedObject, bytes]:
        self.calls.append((cik, accession, filename))
        raise SourceMemberMissingError(
            f"{filename!r} is not held locally and this test fetches none"
        )


@dataclass(frozen=True)
class Harness:
    root: Path
    store: EvaluationStore
    journal: SpendJournal
    provider: ScriptedProvider
    fetcher: RecordingFetcher
    service: ParserReviewService
    worker: InlineWorker


def _write_corpus(root: Path) -> tuple[Path, ManifestInventory]:
    corpus = root / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    members = {f"{ACCESSION}.txt": _submission(), "primary.htm": _primary_document()}
    preserved: list[PreservedObject] = []
    files: list[dict[str, object]] = []
    for filename, data in members.items():
        path = corpus / ACCESSION / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digest = sha256_bytes(data)
        preserved.append(
            PreservedObject(
                filename=filename,
                sha256=digest,
                byte_count=len(data),
                source_url=f"https://example.invalid/{ACCESSION}/{filename}",
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
                "source_url": f"https://example.invalid/{ACCESSION}/{filename}",
                "local_path": str(path),
            }
        )
    manifest = root / "corpus-manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "cik": CIK,
                    "accession": ACCESSION,
                    "form_as_filed": "10-K",
                    "filing_date": "2024-02-01",
                    "report_period": "2023-12-31",
                    "issuer_name_current": ISSUER,
                    "tickers_current": ["SYN"],
                    "former_names": [],
                    "sic_description": "Synthetic manufacturing",
                    "transport_era": "addressable-members",
                    "is_amendment": False,
                    "is_annual": True,
                    "form_variant": "10-K",
                    "package_file_count": len(files),
                    "package_image_count": 0,
                    "primary_est_tokens_at_3_0": 1000,
                    "files": files,
                }
            ]
        ),
        encoding="utf-8",
    )
    return manifest, ManifestInventory({(CIK, ACCESSION): preserved})


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


def _harness(
    root: Path,
    *,
    provider: ScriptedProvider | None = None,
    settings: MultipartSettings | None = None,
) -> Harness:
    manifest_path, inventory = _write_corpus(root)
    prompts = _write_prompts(root)
    objects = FilesystemObjectStore(root / "evaluation")
    store = EvaluationStore(objects)
    journal = SpendJournal(objects, ceiling_usd=CEILING, phase="test", phase_ceiling_usd=CEILING)
    scripted = provider if provider is not None else ScriptedProvider()
    fetcher = RecordingFetcher()
    service = ParserReviewService(
        store=store,
        catalog=CorpusFilingCatalog.from_manifest(manifest_path),
        snapshot=load_snapshot(_snapshot_text()),
        prompts=prompts,
        inventory=inventory,
        fetcher=fetcher,
        provider=scripted,
        journal=journal,
        preferred_region=REGION,
        author=AUTHOR,
        multipart_settings=settings or MultipartSettings(filing_budget_usd=Decimal("4.00")),
    )
    return Harness(
        root=root,
        store=store,
        journal=journal,
        provider=scripted,
        fetcher=fetcher,
        service=service,
        worker=InlineWorker(service),
    )


class Completed(NamedTuple):
    """One finished multipart parse, shared by every test that only READS it.

    WHY SHARED. Driving the scripted sequence end to end is twelve billable-shaped steps over a
    real object store, and twenty assertions about the SAME finished parse do not each need their
    own. Rebuilding it per test cost about ten seconds a test and produced twenty identical runs.

    WHY IT IS SAFE. Every test taking this fixture is read-only. The ones that mutate state —
    resume, retry, duplicate scheduling — build their own harness, and so does every test that
    changes the settings or the scripted provider. That split is enforced by which fixture a test
    asks for, which is visible in its signature.
    """

    harness: Harness
    run_id: str
    job_id: str


@pytest.fixture(scope="module")
def completed(tmp_path_factory: pytest.TempPathFactory) -> Completed:
    harness = _harness(tmp_path_factory.mktemp("shared-multipart-run"))
    run_id, job_id = _run(harness)
    return Completed(harness, run_id, job_id)


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return _harness(tmp_path)


def _request() -> RunRequest:
    return RunRequest(
        cik=CIK,
        parsing_label=PARSER,
        accessions=(ACCESSION,),
        strategy=MULTIPART_STRATEGY,
    )


def _run(harness: Harness) -> tuple[str, str]:
    run = harness.service.create_run(_request())
    harness.worker.submit_run(run.run_id)
    return run.run_id, run.job_ids[0]


# --- anti-vacuity ----------------------------------------------------------------------------------


def test_the_scripted_world_is_real_enough_to_enforce_anything(completed: Completed) -> None:
    """A harness that produced no tasks would make every assertion below vacuous."""
    harness, run_id, job_id = completed
    tasks = harness.store.load_tasks(run_id, job_id)
    assert len(tasks) >= 8, f"only {len(tasks)} task(s) ran; the sequence is not being exercised"
    assert harness.provider.requests, "the provider was never invoked"
    assert not harness.fetcher.calls, f"this suite contacted SEC: {harness.fetcher.calls}"


# --- the plan is the model's ------------------------------------------------------------------------


def test_the_first_billable_call_is_a_plan_and_the_parts_come_from_it(completed: Completed) -> None:
    harness, run_id, job_id = completed
    tasks = harness.store.load_tasks(run_id, job_id)
    first = tasks[0]
    assert first.task_type is TaskType.PLAN_PARSE
    assert first.state is TaskState.SUCCEEDED

    part_ids = {t.part_id for t in tasks if t.task_type is TaskType.PARSE_PART}
    # Exactly the identifiers the scripted PLAN named, plus the one reconciliation asked for.
    assert {"front", "middle", "back"} <= part_ids
    assert "appendix" in part_ids, "reconciliation asked for a part and it was never queued"


def test_every_part_identifier_in_the_queue_came_from_a_model_response(
    completed: Completed,
) -> None:
    """No backend-invented identifier reaches a task. The set is exactly what was returned."""
    harness, run_id, job_id = completed
    produced = {
        t.part_id
        for t in harness.store.load_tasks(run_id, job_id)
        if t.part_id and t.task_type in {TaskType.PARSE_PART, TaskType.PARSE_SUBPART}
    }
    assert produced == {
        "front",
        "middle",
        "back",
        "middle-a",
        "middle-b",
        "middle-b-1",
        "middle-b-2",
        "appendix",
    }


# --- intact source on every semantic call ------------------------------------------------------------


def test_every_semantic_invocation_received_the_complete_source_set(completed: Completed) -> None:
    """The whole filing goes to the model on the plan call, every part call and reconciliation.

    THE ONE EXCEPTION IS DELIBERATE AND IS ASSERTED SEPARATELY: a format repair carries no filing,
    because it is forbidden to change meaning and is given nothing to change it with.
    """
    harness, run_id, job_id = completed
    job = harness.store.load_job(run_id, job_id)
    assert job.source_set is not None
    submitted = {m["filename"] for m in job.source_set["members"] if m["submitted"]}
    assert submitted, "the job recorded no submitted member"
    for request in harness.provider.requests:
        labels = {block.label for block in request.original_source}
        assert labels == submitted, (
            f"an invocation received {labels} and the submitted source set is {submitted}"
        )


def test_no_invocation_carried_a_slice_of_a_source_artifact(completed: Completed) -> None:
    """Each block is the WHOLE preserved artifact, admitted by its recorded hash."""
    harness, run_id, job_id = completed
    job = harness.store.load_job(run_id, job_id)
    hashes = {
        m["filename"]: m["sha256"]
        for m in job.source_set["members"]
        if m["submitted"]  # type: ignore[index]
    }
    for request in harness.provider.requests:
        for block in request.original_source:
            assert block.sha256 == hashes[block.label]
            assert sha256_bytes(block.raw_bytes) == block.sha256


# --- model-directed subparts ------------------------------------------------------------------------


def test_a_part_that_declares_itself_too_large_produces_the_subparts_the_model_proposed(
    completed: Completed,
) -> None:
    harness, run_id, job_id = completed
    tasks = harness.store.load_tasks(run_id, job_id)
    subparts = [t for t in tasks if t.task_type is TaskType.PARSE_SUBPART]
    identifiers = {t.part_id for t in subparts}
    assert {"middle-a", "middle-b"} <= identifiers
    for task in subparts:
        if task.part_id in {"middle-a", "middle-b"}:
            assert task.parent_part_id == "middle"
            assert task.depth == 2, "a subpart must be recorded one level below its parent"


def test_the_recursion_depth_limit_pauses_a_branch_instead_of_dividing_again(
    tmp_path: Path,
) -> None:
    """An OPERATIONAL limit. It records a reason and stops spending; it says nothing about filings."""
    harness = _harness(
        tmp_path, settings=MultipartSettings(max_depth=1, filing_budget_usd=Decimal("4.00"))
    )
    run_id, job_id = _run(harness)
    tasks = harness.store.load_tasks(run_id, job_id)
    assert not [t for t in tasks if t.task_type is TaskType.PARSE_SUBPART], (
        "a subpart was queued past the configured depth limit"
    )
    kinds = [e.kind for e in harness.store.read_events(run_id)]
    assert "depth.limit" in kinds, "the branch was dropped without recording why"


# --- truncation -------------------------------------------------------------------------------------


def test_a_truncated_attempt_is_preserved_marked_and_never_continued(completed: Completed) -> None:
    harness, run_id, job_id = completed
    truncated = [
        t for t in harness.store.load_tasks(run_id, job_id) if t.state is TaskState.TRUNCATED
    ]
    assert len(truncated) == 1, "the scripted max_tokens response was not detected as truncation"
    task = truncated[0]
    assert task.part_id == "middle-b"
    assert task.truncation is not None
    assert task.truncation["stop_reason"] == "max_tokens"

    stored = harness.store.get_task_evidence_text(run_id, job_id, task.task_id, RESPONSE_EVIDENCE)
    assert stored == PART_MIDDLE_B_TRUNCATED, "the exact partial response was not preserved"
    assert task.envelope is None, "a truncated attempt must not be read as a finished part"


def test_a_truncation_creates_a_replanning_task_and_the_subparts_cover_the_whole_part(
    completed: Completed,
) -> None:
    harness, run_id, job_id = completed
    tasks = harness.store.load_tasks(run_id, job_id)
    replans = [t for t in tasks if t.task_type is TaskType.REPLAN_TRUNCATED_PART]
    assert len(replans) == 1
    assert replans[0].state is TaskState.SUCCEEDED

    produced = {t.part_id for t in tasks if t.task_type is TaskType.PARSE_SUBPART}
    assert {"middle-b-1", "middle-b-2"} <= produced


def test_no_request_ever_asked_a_model_to_continue_a_response(completed: Completed) -> None:
    """The protocol prohibition, asserted against every byte actually sent.

    A replanning request DOES carry the truncated text — as labelled evidence. What must not appear
    anywhere is an instruction to resume it.
    """
    harness = completed.harness
    for request in harness.provider.requests:
        content = request.user_content.lower()
        for forbidden in ("continue from", "resume from", "carry on from", "pick up where"):
            assert forbidden not in content, f"a request asked the model to {forbidden!r}"

    replans = [
        r for r in harness.provider.requests if parse_yaml(r.user_content).get("brief") == "replan"
    ]
    assert len(replans) == 1
    brief = parse_yaml(replans[0].user_content)
    assert brief["truncated_attempt"]["exact_partial_response"] == PART_MIDDLE_B_TRUNCATED
    assert "EVIDENCE ONLY" in brief["truncated_attempt"]["status"]


def test_the_truncated_text_is_not_merged_into_the_assembled_parse(completed: Completed) -> None:
    harness, run_id, job_id = completed
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    truncated = [p for p in assembly["parts"] if p["truncated"]]
    assert len(truncated) == 1
    assert truncated[0]["node_count"] == 0, "content from a truncated attempt reached the assembly"
    assert truncated[0]["terminal"] is False


# --- reconciliation ----------------------------------------------------------------------------------


def test_reconciliation_adds_work_and_the_work_it_adds_actually_runs(completed: Completed) -> None:
    harness, run_id, job_id = completed
    tasks = harness.store.load_tasks(run_id, job_id)
    reconciles = [t for t in tasks if t.task_type is TaskType.RECONCILE_PARSE]
    assert len(reconciles) >= 2, "a second cycle was not queued after the first added work"
    appendix = [t for t in tasks if t.part_id == "appendix"]
    assert appendix and appendix[0].state is TaskState.SUCCEEDED
    kinds = [e.kind for e in harness.store.read_events(run_id)]
    assert "reconcile.added_work" in kinds


def test_reconciliation_waits_for_terminal_parts_not_for_successful_ones(
    completed: Completed,
) -> None:
    """A truncated part is exactly what reconciliation exists to notice."""
    harness, run_id, job_id = completed
    reconciles = [
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.task_type is TaskType.RECONCILE_PARSE
    ]
    assert reconciles[0].dependency_policy.value == "ALL_TERMINAL"
    assert reconciles[0].state is TaskState.SUCCEEDED


def test_the_reconciliation_cycle_limit_stops_the_run_and_preserves_everything(
    tmp_path: Path,
) -> None:
    class AlwaysAddsWork(ScriptedProvider):
        def invoke(self, request: ModelRequest) -> ModelResponse:
            response = super().invoke(request)
            if parse_yaml(request.user_content).get("brief") == "reconcile":
                return ModelResponse(
                    text=RECONCILE_ADDS_WORK.replace(
                        '"appendix"', f'"extra-{self.reconcile_calls}"'
                    ),
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    model_id=response.model_id,
                    provider=response.provider,
                )
            return response

    harness = _harness(
        tmp_path,
        provider=AlwaysAddsWork(),
        settings=MultipartSettings(max_reconciliation_cycles=2, filing_budget_usd=Decimal("4.00")),
    )
    run_id, job_id = _run(harness)
    reconciles = [
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.task_type is TaskType.RECONCILE_PARSE
    ]
    assert len(reconciles) == 2, f"the cycle limit was not enforced: {len(reconciles)} cycles ran"
    assert "reconcile.cycle_limit" in [e.kind for e in harness.store.read_events(run_id)]
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    assert (
        assembly["status"] != AssemblyStatus.MECHANICALLY_ASSEMBLED.value
        or not assembly["model_declared_complete"]
    )


# --- cost --------------------------------------------------------------------------------------------


def test_every_attempt_takes_its_own_reservation_and_the_totals_reconcile(
    completed: Completed,
) -> None:
    harness, run_id, job_id = completed
    tasks = harness.store.load_tasks(run_id, job_id)
    billable = [t for t in tasks if t.attempts]
    assert billable
    for task in billable:
        assert task.reserved_cost_usd is not None and task.reserved_cost_usd > 0
    reservations = [e for e in harness.journal.entries if e.kind == "RESERVATION"]
    assert len(reservations) == sum(len(t.attempts) for t in billable)

    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    assert assembly["validation"]["cost_reconciles"] is True
    assert Decimal(assembly["total_cost_usd"]) == harness.journal.spent_for_job(job_id)


def test_the_filing_budget_pauses_the_queue_before_it_overspends(tmp_path: Path) -> None:
    """A ceiling refusal PAUSES a branch with the reason visible. It never fails the parse.

    The budget is derived from a full run rather than guessed, so the test asserts a PARTIAL run:
    enough for the plan and some parts, not enough for all of them. A budget small enough to refuse
    the very first call would prove only that zero is less than one.
    """
    reference = _harness(tmp_path / "reference")
    reference_run, reference_job = _run(reference)
    reservations = [e.amount_usd for e in reference.journal.entries if e.kind == "RESERVATION"]
    settlements = [e.amount_usd for e in reference.journal.entries if e.kind == "SETTLEMENT"]
    assert len(reservations) > 4 and settlements and reference_run and reference_job
    # ONE WORST-CASE RESERVATION PLUS THREE SETTLED CALLS, DERIVED FROM THE REFERENCE RUN.
    #
    # The arithmetic matters and is easy to get wrong. A reservation is the CONSERVATIVE BOUND and
    # is an order of magnitude larger than what the call settles at; it occupies the budget only
    # until the measured cost replaces it. So the budget that binds is "enough for a few settled
    # calls, plus headroom for one more reservation" — a budget derived from the settled TOTAL
    # would refuse the very first call, and a multiple of the reservation alone would never bind at
    # all, because each reservation is released as it settles.
    budget = max(reservations) + max(settlements) * 3

    harness = _harness(
        tmp_path / "constrained", settings=MultipartSettings(filing_budget_usd=budget)
    )
    run_id, job_id = _run(harness)
    tasks = harness.store.load_tasks(run_id, job_id)
    blocked = [t for t in tasks if t.state is TaskState.BLOCKED]
    assert blocked, "a budget of three worst-case reservations did not pause anything"
    assert all(t.blocked_reason for t in blocked), "a task was blocked with no reason recorded"
    assert "budget.paused" in [e.kind for e in harness.store.read_events(run_id)]
    assert [t for t in tasks if t.state is TaskState.SUCCEEDED], (
        "the pause discarded work that had already been paid for"
    )
    assert harness.journal.spent_for_job(job_id) <= budget, "the pause let the budget be exceeded"


def test_a_budget_too_small_for_the_first_call_refuses_gracefully(tmp_path: Path) -> None:
    """Nothing is invoked, nothing is failed, and the reason is on the record."""
    harness = _harness(tmp_path, settings=MultipartSettings(filing_budget_usd=Decimal("0.0000001")))
    run_id, job_id = _run(harness)
    assert not harness.provider.requests, "a refused budget still reached a provider"
    tasks = harness.store.load_tasks(run_id, job_id)
    assert [t for t in tasks if t.state is TaskState.BLOCKED and t.blocked_reason]
    assert harness.journal.spent_for_job(job_id) == 0


def test_the_phase_ceiling_is_tracked_separately_from_the_cumulative_one(
    completed: Completed,
) -> None:
    harness, run_id, job_id = completed
    assert harness.journal.phase == "test"
    assert harness.journal.phase_spent_usd == harness.journal.spent_usd
    assert harness.journal.spent_for_job(job_id) > 0
    assert all(e.phase == "test" for e in harness.journal.entries)
    assert run_id


# --- restart and partial retry -------------------------------------------------------------------------


def restarted_targets(tasks: list[Any]) -> list[Any]:
    """The tasks a crashed process would have left mid-flight."""
    return [t for t in tasks if t.state in RESUMABLE_TASK_STATES]


def test_a_restart_marks_in_flight_tasks_interrupted_and_reruns_nothing(tmp_path: Path) -> None:
    class StopsAfterPlan(ScriptedProvider):
        def invoke(self, request: ModelRequest) -> ModelResponse:
            if parse_yaml(request.user_content).get("brief") == "part":
                raise RuntimeError("scripted crash mid-parse")
            return super().invoke(request)

    harness = _harness(tmp_path, provider=StopsAfterPlan())
    run = harness.service.create_run(_request())
    run_id, job_id = run.run_id, run.job_ids[0]
    harness.service.multipart.start(run_id, job_id)
    with pytest.raises(RuntimeError):
        harness.service.multipart.drive(run_id, job_id)

    before = harness.store.load_tasks(run_id, job_id)
    succeeded_before = {t.task_id for t in before if t.state is TaskState.SUCCEEDED}
    assert succeeded_before, "nothing succeeded before the crash; the test proves nothing"

    # A CRASH MEANS THE PROCESS IS GONE, and the test has to say so because it is still running.
    # `mark_interrupted_tasks` now parks only work whose owning process is dead — that is what lets
    # several parses share one store — so a restart test that leaves a LIVE lease on its tasks is
    # simulating a restart nobody had. The dead pid stands in for the process that crashed.
    for stranded in restarted_targets(before):
        stranded.owner = "crashed-host:999999999"
        stranded.heartbeat = "2000-01-01T00:00:00+00:00"
        harness.store.save_task(stranded)

    restarted = _harness(tmp_path, provider=ScriptedProvider())
    restarted.store.mark_interrupted_tasks()
    after = restarted.store.load_tasks(run_id, job_id)
    assert {t.task_id for t in after if t.state is TaskState.SUCCEEDED} == succeeded_before, (
        "a restart lost or reran a completed task"
    )
    assert any(t.state is TaskState.INTERRUPTED for t in after)
    assert not restarted.provider.requests, "a restart invoked a model without being asked to"


def test_resume_reopens_only_the_interrupted_branch(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    run_id, job_id = _run(harness)
    tasks = harness.store.load_tasks(run_id, job_id)
    victim = next(t for t in tasks if t.task_type is TaskType.PARSE_PART)
    victim.state = TaskState.INTERRUPTED
    harness.store.save_task(victim)

    reopened = harness.service.multipart.resume(run_id, job_id)
    assert reopened == [victim.task_id]
    others = [
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.task_id != victim.task_id and t.task_type is TaskType.PARSE_PART
    ]
    assert all(t.state is TaskState.SUCCEEDED for t in others), "resume disturbed a completed part"


def test_a_resumed_parse_finishes_and_actually_reaches_review(tmp_path: Path) -> None:
    """FOUND ON A REAL RUN, NOT IN THIS FILE. A restart marks BOTH the tasks and the child job
    INTERRUPTED. Reopening only the tasks left the job in a terminal state, so a parse that then
    ran to completion had nowhere to go: 47 of 47 parts terminal, 214 nodes produced, and a job
    still reporting INTERRUPTED with no way for a reviewer to see any of it.

    The whole point of paying for half a parse and resuming it is that the finished parse becomes
    reviewable. A resume that cannot end in READY_FOR_REVIEW has bought nothing.
    """

    class StopsAfterPlan(ScriptedProvider):
        def invoke(self, request: ModelRequest) -> ModelResponse:
            if parse_yaml(request.user_content).get("brief") == "part":
                raise RuntimeError("scripted crash mid-parse")
            return super().invoke(request)

    harness = _harness(tmp_path, provider=StopsAfterPlan())
    run = harness.service.create_run(_request())
    run_id, job_id = run.run_id, run.job_ids[0]
    harness.service.multipart.start(run_id, job_id)
    with pytest.raises(RuntimeError):
        harness.service.multipart.drive(run_id, job_id)

    restarted = _harness(tmp_path, provider=ScriptedProvider())
    restarted.store.mark_interrupted_tasks()
    restarted.store.mark_interrupted_jobs()
    assert restarted.store.load_job(run_id, job_id).execution_state is ExecutionState.INTERRUPTED, (
        "the restart did not park the job, so this test would pass for the wrong reason"
    )

    restarted.service.multipart.resume(run_id, job_id)
    job = restarted.service.multipart.drive(run_id, job_id)
    assert job.execution_state is ExecutionState.READY_FOR_REVIEW, (
        f"a resumed parse finished in {job.execution_state.value} and no reviewer can reach it"
    )
    assembly = restarted.store.load_assembly(run_id, job_id)
    assert assembly is not None and assembly["part_count"] > 0


def test_resuming_a_job_whose_tasks_all_finished_still_reopens_it(tmp_path: Path) -> None:
    """THE SHAPE THE GUARD USED TO MISS. A process can die between the last task and assembly.
    There is then nothing to re-arm, and a resume conditioned on having re-armed something would
    be a no-op on exactly the case that most needs fixing.
    """
    harness = _harness(tmp_path)
    run = harness.service.create_run(_request())
    run_id, job_id = run.run_id, run.job_ids[0]
    harness.service.multipart.start(run_id, job_id)
    # Every task, and then a death before assembly: `run_next` is driven directly so `_finish` is
    # never reached, which is the state a process that died at that moment would leave behind.
    while harness.service.multipart.run_next(run_id, job_id):
        pass
    harness.store.mark_interrupted_jobs()
    assert not harness.store.runnable_tasks(run_id, job_id)

    assert harness.service.multipart.resume(run_id, job_id) == [], (
        "a task was re-armed; this test no longer covers the empty case"
    )
    assert harness.store.load_job(run_id, job_id).execution_state is ExecutionState.RUNNING, (
        "resume left a finished parse parked in INTERRUPTED"
    )
    assert (
        harness.service.multipart.drive(run_id, job_id).execution_state
        is ExecutionState.READY_FOR_REVIEW
    )


def test_resuming_reopens_nothing_else_and_invokes_nothing(tmp_path: Path) -> None:
    """ANTI-VACUITY. Reopening the job must not be a licence to reopen a job that ended properly,
    and resume itself still spends nothing — driving the queue is a separate, explicit act.
    """
    harness = _harness(tmp_path)
    run_id, job_id = _run(harness)
    before = harness.store.load_job(run_id, job_id).execution_state
    assert before is ExecutionState.READY_FOR_REVIEW

    calls = len(harness.provider.requests)
    assert harness.service.multipart.resume(run_id, job_id) == []
    assert harness.store.load_job(run_id, job_id).execution_state is before, (
        "resume dragged a reviewable parse back out of its terminal state"
    )
    assert len(harness.provider.requests) == calls, "resume invoked a model"


def test_one_failed_part_does_not_erase_the_parts_that_succeeded(tmp_path: Path) -> None:
    provider = ScriptedProvider()
    provider.fail_once = {"back"}
    harness = _harness(tmp_path, provider=provider)
    run_id, job_id = _run(harness)
    tasks = harness.store.load_tasks(run_id, job_id)
    failed = [t for t in tasks if t.state is TaskState.FAILED]
    assert failed and failed[0].part_id == "back"
    assert [t for t in tasks if t.part_id == "front"][0].state is TaskState.SUCCEEDED
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    assert any(p["part_id"] == "front" and p["terminal"] for p in assembly["parts"])


def test_an_explicit_retry_mints_a_new_billable_identity(tmp_path: Path) -> None:
    provider = ScriptedProvider()
    provider.fail_once = {"back"}
    harness = _harness(tmp_path, provider=provider)
    run_id, job_id = _run(harness)
    failed = next(
        t for t in harness.store.load_tasks(run_id, job_id) if t.state is TaskState.FAILED
    )
    before = failed.idempotency
    retried = harness.service.multipart.retry(run_id, job_id, failed.task_id)
    assert retried.state is TaskState.READY
    assert retried.idempotency != before, (
        "a rerun kept its old identity and would have been skipped as a duplicate"
    )


def test_duplicate_scheduling_of_identical_inputs_does_not_invoke_twice(
    harness: Harness,
) -> None:
    """Accidental duplicate scheduling is refused. This is NOT a provider exactly-once claim.

    The clone is created exactly as the scheduler would create it — same plan, same part, same
    parent artifact, same settings — so the identity it computes is the identity the original
    already holds.
    """
    run_id, job_id = _run(harness)
    multipart = harness.service.multipart
    job = harness.store.load_job(run_id, job_id)
    done = next(
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.task_type is TaskType.PARSE_PART and t.state is TaskState.SUCCEEDED
    )
    calls_before = len(harness.provider.requests)
    context = multipart._context(job)  # noqa: SLF001 - exercising the guard directly
    clone = multipart._create_task(  # noqa: SLF001
        job,
        task_type=TaskType.PARSE_PART,
        sizing=part_sizing(
            context.capability, estimated_input_tokens=job.estimated_input_tokens or 0
        ),
        depends_on=(),
        order=done.order,
        parent_task_id=done.parent_task_id,
        plan_id=done.plan_id,
        part=done.part_spec,
    )
    harness.store.set_task_state(clone, TaskState.READY)
    multipart.run_next(run_id, job_id)

    settled = harness.store.load_task(run_id, job_id, clone.task_id)
    assert settled.idempotency == done.idempotency, (
        "the clone computed a different identity at execution, so this test would prove nothing"
    )
    assert len(harness.provider.requests) == calls_before, (
        "an identical set of inputs was invoked a second time"
    )
    assert settled.state is TaskState.CANCELLED, (
        "a duplicate schedule must be cancelled, not recorded as a failure"
    )
    assert "already holds a successful response" in settled.note


# --- assembly ------------------------------------------------------------------------------------------


def test_the_assembly_preserves_model_order_titles_and_types(completed: Completed) -> None:
    harness, run_id, job_id = completed
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    by_id = {p["part_id"]: p for p in assembly["parts"]}
    assert by_id["front"]["title"] == "A Heading The Filing Uses"
    assert by_id["front"]["type"] == "whatever the model calls it"
    assert by_id["middle-a"]["parent_part_id"] == "middle"
    assert by_id["middle-a"]["depth"] == 1, "a subpart is nested under its parent in the index"
    ordered = [p["part_id"] for p in assembly["parts"]]
    assert ordered.index("front") < ordered.index("middle") < ordered.index("back")


def test_the_assembly_merges_nothing_and_renames_nothing(completed: Completed) -> None:
    harness, run_id, job_id = completed
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    identifiers = [p["part_id"] for p in assembly["parts"]]
    assert len(identifiers) == len(set(identifiers)), "the index collapsed two parts into one"
    # Every node in the index is the model's own node mapping, untouched.
    front = next(p for p in assembly["parts"] if p["part_id"] == "front")
    assert front["nodes"][0]["id"] == "n1"
    assert front["nodes"][0]["title"] == "A Heading The Filing Uses"


def test_the_assembly_never_claims_completeness(completed: Completed) -> None:
    harness, run_id, job_id = completed
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    assert assembly["status"] in {s.value for s in AssemblyStatus}
    assert "COMPLETE" not in assembly["status"] or assembly["status"] == "INCOMPLETE_WORK"
    assert assembly["human_review_required"] is True
    # Four distinct claims, never one boolean.
    for key in (
        "mechanically_assembled",
        "model_declared_complete",
        "reconciliation_unresolved",
        "human_review_required",
    ):
        assert key in assembly


def test_the_job_reaches_ready_for_review_and_says_nothing_about_a_reviewer(
    completed: Completed,
) -> None:
    harness, run_id, job_id = completed
    job = harness.store.load_job(run_id, job_id)
    assert job.execution_state is ExecutionState.READY_FOR_REVIEW
    assert job.review_state.value == "EVALUATION"
    assert job.strategy == MULTIPART_STRATEGY
    assert job.multipart is not None
    assert job.multipart["parse_plan_id"] == "plan-alpha"


def test_source_references_are_resolved_against_the_preserved_bytes(completed: Completed) -> None:
    harness, run_id, job_id = completed
    front = next(
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.part_id == "front" and t.task_type is TaskType.PARSE_PART
    )
    coverage = (front.validation or {})["coverage"]
    assert coverage["reference_count"] == 1
    assert coverage["references_resolved"] == 1
    assert coverage["references"][0]["resolution"] in {
        "EXACT",
        "WHITESPACE_NORMALISED",
        "TEXT_ONLY",
    }


def test_a_part_is_not_penalised_for_citing_only_its_own_material(completed: Completed) -> None:
    """A part cites the artifacts IT was asked about. The whole-filing question is the assembly's."""
    harness, run_id, job_id = completed
    back = next(
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.part_id == "back" and t.task_type is TaskType.PARSE_PART
    )
    findings = " ".join((back.validation or {})["coverage"]["findings"])
    assert "carry no resolved reference" not in findings


# --- the source set a reviewer actually sees ------------------------------------------------------
#
# BOTH OF THESE WERE FOUND BY OPENING THE UI AGAINST A REAL RUN, not by an assertion. The multipart
# path preserved every request and every response and did NOT preserve the source set, so a part's
# review page had no filing to show beside it — no raw view, no side-by-side. And the session
# summary was written once at start and once at finish, so an interrupted run showed "plan not yet
# produced" in its header beside twenty-four parts the plan had created.


def test_the_source_set_is_preserved_once_at_the_child_job_level(completed: Completed) -> None:
    """A part cannot be reviewed beside a filing the store does not hold."""
    harness, run_id, job_id = completed
    job = harness.store.load_job(run_id, job_id)
    assert job.source_set is not None
    submitted = [m for m in job.source_set["members"] if m["submitted"]]
    assert submitted, "the job recorded no submitted member"
    for member in submitted:
        name = member["evidence_name"]
        assert name, f"{member['filename']} carries no evidence name, so no page can resolve it"
        assert harness.store.has_evidence(run_id, job_id, name)
        stored = harness.store.get_evidence(run_id, job_id, name)
        assert sha256_bytes(stored) == member["sha256"], (
            "the preserved bytes are not the sent bytes"
        )


def test_the_source_set_is_stored_once_and_not_once_per_task(completed: Completed) -> None:
    """A ten-task parse of a 146 KB filing would otherwise store the filing ten times."""
    harness, run_id, job_id = completed
    job_level = [n for n in harness.store.list_evidence(run_id, job_id) if n.startswith("source-")]
    assert job_level, "no source evidence at the child-job level"
    for task in harness.store.load_tasks(run_id, job_id):
        per_task = [
            n
            for n in harness.store.list_task_evidence(run_id, job_id, task.task_id)
            if n.startswith("source-")
        ]
        assert not per_task, f"task {task.task_id} duplicated the source set: {per_task}"


def test_the_session_summary_carries_the_plan_as_soon_as_the_plan_exists(
    completed: Completed,
) -> None:
    harness, run_id, job_id = completed
    session = harness.store.load_job(run_id, job_id).multipart
    assert session is not None
    assert session["parse_plan_id"] == "plan-alpha"
    assert session["planned_part_count"] == 3


# --- a repaired part must reach the index -----------------------------------------------------------
#
# FOUND IN A REAL RUN, NOT HERE. A model returned a part response that would not parse; the format
# repair then succeeded and produced a readable envelope with two nodes. The index carried the
# ORIGINAL row — `node_count: 0`, empty title type and coverage summary — and reported the part as
# terminal. A FALSE EMPTY: content that exists, reported as absent. That is the inverse of the
# failure mode this project guards against and exactly as untrue.


class MalformsOnePart(ScriptedProvider):
    """Returns unparseable YAML for one part, then a good envelope when asked to repair it."""

    def __init__(self, victim: str) -> None:
        super().__init__()
        self.victim = victim
        self.malformed_once = True

    def invoke(self, request: ModelRequest) -> ModelResponse:
        brief = parse_yaml(request.user_content)
        if brief.get("brief") == "part":
            part_id = str(brief["requested_part"]["part_id"])
            if part_id == self.victim and self.malformed_once:
                self.malformed_once = False
                self.requests.append(request)
                # A colon-space inside an unquoted plain scalar: the exact defect measured on a
                # real run, eight times in one parse.
                text = (
                    f'parse_plan_id: "plan-alpha"\n'
                    f'part_id: "{part_id}"\n'
                    "status: complete\n"
                    "nodes:\n"
                    "  - id: n9\n"
                    "    content: State of Incorporation: Delaware\n"
                )
                return ModelResponse(
                    text=text,
                    input_tokens=estimate_tokens(request.user_content),
                    output_tokens=estimate_tokens(text),
                    model_id=request.model_id,
                    provider=self.name,
                    stop_reason="end_turn",
                    truncated=False,
                )
        if brief.get("brief") == "format_repair":
            self.requests.append(request)
            text = _generic_part(self.victim, "Repaired Title")
            return ModelResponse(
                text=text,
                input_tokens=estimate_tokens(request.user_content),
                output_tokens=estimate_tokens(text),
                model_id=request.model_id,
                provider=self.name,
                stop_reason="end_turn",
                truncated=False,
            )
        return super().invoke(request)


def _repaired_harness(tmp_path: Path) -> tuple[Harness, str, str]:
    harness = _harness(tmp_path, provider=MalformsOnePart("front"))
    run_id, job_id = _run(harness)
    return harness, run_id, job_id


def test_the_scripted_malformed_response_really_is_unreadable(tmp_path: Path) -> None:
    """ANTI-VACUITY. If the scripted response parsed, every assertion below would be about nothing."""
    harness, run_id, job_id = _repaired_harness(tmp_path)
    original = next(
        t
        for t in harness.store.load_tasks(run_id, job_id)
        if t.task_type is TaskType.PARSE_PART
        and t.part_id == "front"
        and (t.envelope or {}).get("readable") is False
    )
    assert "not one YAML" in (original.error or ""), original.error


def test_a_successful_repair_supplies_the_part_the_index_shows(tmp_path: Path) -> None:
    harness, run_id, job_id = _repaired_harness(tmp_path)
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    row = next(p for p in assembly["parts"] if p["part_id"] == "front")
    assert row["node_count"] > 0, "the repaired nodes never reached the index"
    assert row["title"] == "Repaired Title"
    assert row["nodes"], "the row carries counts but not the model's own nodes"


def test_the_row_names_both_artifacts_so_neither_is_lost(tmp_path: Path) -> None:
    """The malformed original is preserved and still reachable; it is not replaced or rewritten."""
    harness, run_id, job_id = _repaired_harness(tmp_path)
    tasks = harness.store.load_tasks(run_id, job_id)
    original = next(
        t
        for t in tasks
        if t.task_type is TaskType.PARSE_PART
        and t.part_id == "front"
        and (t.envelope or {}).get("readable") is False
    )
    repair = next(t for t in tasks if t.task_type is TaskType.FORMAT_REPAIR)
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    row = next(p for p in assembly["parts"] if p["part_id"] == "front")
    assert row["task_id"] == repair.task_id, "the row does not point at the artifact it displays"
    assert row["repaired_from_task_id"] == original.task_id
    assert harness.store.load_task(run_id, job_id, original.task_id).envelope == original.envelope


def test_a_repaired_part_appears_exactly_once(tmp_path: Path) -> None:
    """A duplicate part identifier is a defect validate_assembly reports. One row, not two."""
    harness, run_id, job_id = _repaired_harness(tmp_path)
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    ids = [p["part_id"] for p in assembly["parts"]]
    assert ids.count("front") == 1, ids
    assert assembly["validation"]["consistent"], assembly["validation"]


def test_the_row_carries_what_both_calls_cost(tmp_path: Path) -> None:
    """The malformed response was bought too. A row showing only the repair understates the part."""
    harness, run_id, job_id = _repaired_harness(tmp_path)
    tasks = harness.store.load_tasks(run_id, job_id)
    original = next(
        t
        for t in tasks
        if t.task_type is TaskType.PARSE_PART
        and t.part_id == "front"
        and (t.envelope or {}).get("readable") is False
    )
    repair = next(t for t in tasks if t.task_type is TaskType.FORMAT_REPAIR)
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    row = next(p for p in assembly["parts"] if p["part_id"] == "front")
    expected = (original.actual_cost_usd or Decimal(0)) + (repair.actual_cost_usd or Decimal(0))
    assert Decimal(row["actual_cost_usd"]) == expected
    assert expected > Decimal(0), "both calls were free; this test proves nothing"


def test_an_unrepaired_part_is_untouched_by_any_of_this(tmp_path: Path) -> None:
    """MUTATION PROOF. Substitution must happen only where a readable repair actually exists."""
    harness, run_id, job_id = _repaired_harness(tmp_path)
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    others = [p for p in assembly["parts"] if p["part_id"] != "front"]
    assert others, "no other parts exist; the mutation proof is vacuous"
    assert all(p["repaired_from_task_id"] is None for p in others)


def test_a_repair_that_is_itself_unreadable_does_not_displace_the_original(
    tmp_path: Path,
) -> None:
    """Swapping one unreadable artifact for another loses the original's place and gains nothing."""

    class RepairAlsoMalforms(MalformsOnePart):
        def invoke(self, request: ModelRequest) -> ModelResponse:
            if parse_yaml(request.user_content).get("brief") == "format_repair":
                self.requests.append(request)
                text = "nodes:\n  - id: n9\n    content: still broken: yes\n"
                return ModelResponse(
                    text=text,
                    input_tokens=estimate_tokens(request.user_content),
                    output_tokens=estimate_tokens(text),
                    model_id=request.model_id,
                    provider=self.name,
                    stop_reason="end_turn",
                    truncated=False,
                )
            return super().invoke(request)

    harness = _harness(tmp_path, provider=RepairAlsoMalforms("front"))
    run_id, job_id = _run(harness)
    tasks = harness.store.load_tasks(run_id, job_id)
    original = next(
        t
        for t in tasks
        if t.task_type is TaskType.PARSE_PART
        and t.part_id == "front"
        and (t.envelope or {}).get("readable") is False
    )
    assembly = harness.store.load_assembly(run_id, job_id)
    assert assembly is not None
    row = next(p for p in assembly["parts"] if p["part_id"] == "front")
    assert row["task_id"] == original.task_id
    assert row["repaired_from_task_id"] is None


def test_a_format_repair_is_never_itself_repaired(tmp_path: Path) -> None:
    """FOUND IN A REAL RUN: a FORMAT_REPAIR whose parent was a FORMAT_REPAIR.

    `max_format_repairs_per_artifact` counts repairs of a GIVEN task, so an unreadable repair
    became a new artifact with its own allowance. One repair per artifact has to mean one repair,
    not one per link.
    """

    class RepairAlsoMalforms(MalformsOnePart):
        def invoke(self, request: ModelRequest) -> ModelResponse:
            if parse_yaml(request.user_content).get("brief") == "format_repair":
                self.requests.append(request)
                text = "nodes:\n  - id: n9\n    content: still broken: yes\n"
                return ModelResponse(
                    text=text,
                    input_tokens=estimate_tokens(request.user_content),
                    output_tokens=estimate_tokens(text),
                    model_id=request.model_id,
                    provider=self.name,
                    stop_reason="end_turn",
                    truncated=False,
                )
            return super().invoke(request)

    harness = _harness(tmp_path, provider=RepairAlsoMalforms("front"))
    run_id, job_id = _run(harness)
    tasks = harness.store.load_tasks(run_id, job_id)
    repairs = [t for t in tasks if t.task_type is TaskType.FORMAT_REPAIR]
    assert len(repairs) == 1, f"a repair chain formed: {[t.task_id for t in repairs]}"
    assert repairs[0].parent_task_id is not None
    parent = harness.store.load_task(run_id, job_id, repairs[0].parent_task_id)
    assert parent.task_type is TaskType.PARSE_PART
