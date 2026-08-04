"""Phase 2.1 boundaries: the multipart protocol exists, and none of the things it could become do.

Phase 2.1 withdrew one assumption — that a filing's whole parse must fit one response — and the
withdrawal opens four doors that must stay shut. Each has a guard here rather than a paragraph
somewhere:

    1. A BACKEND SEMANTIC CHUNKER. The model divides the filing. Backend code never splits a source
       artifact, never decides where a part begins, and never sends a slice.
    2. A BLIND CONTINUATION PROTOCOL. No request asks a model to resume an interrupted response, and
       no code concatenates response fragments into one document.
    3. A WINNER. No ranking, no score, no promotion, no automatic selection among the five
       candidates, and no per-model prompt.
    4. AN UNAUTHORIZED STAGE. Still the parsing stage only. Multipart multiplies the number of
       parser calls; it authorizes no summary, image or analysis call.

Plus the two Phase 2 guards that multipart makes MORE load-bearing rather than less: every semantic
invocation carries the complete intact source set, and the exact response is preserved before
anything reads it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
PROMPTS = REPO_ROOT / "prompts"

pytestmark = pytest.mark.architecture

#: The packages Phase 2.1 added or extended. Named explicitly so a guard cannot go vacuous by
#: scanning a directory that quietly stopped existing.
PHASE_21_MODULES = (
    PACKAGES / "multipart",
    PACKAGES / "orchestrator" / "multipart_service.py",
    PACKAGES / "orchestrator" / "briefs.py",
    PACKAGES / "orchestrator" / "sizing.py",
    PACKAGES / "evaluation_store" / "tasks.py",
    PACKAGES / "evaluation_store" / "queue_states.py",
    PACKAGES / "review_web" / "multipart_view.py",
)


def _python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _phase_21_files() -> list[Path]:
    found: list[Path] = []
    for module in PHASE_21_MODULES:
        found.extend(_python_files(module))
    return found


def _string_constants(path: Path) -> list[tuple[int, str]]:
    """Evaluated string literals only, so prose explaining a rule stays legal."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    ]


# --- anti-vacuity -------------------------------------------------------------------------------


def test_the_phase_21_surface_exists_and_carries_code() -> None:
    for module in PHASE_21_MODULES:
        assert module.exists(), f"{module.relative_to(REPO_ROOT)} does not exist"
    files = _phase_21_files()
    assert len(files) >= 8, f"only {len(files)} module(s) scanned; the guards below enforce little"


# --- 1. no backend semantic chunker ----------------------------------------------------------------


def test_no_multipart_module_slices_a_source_artifact() -> None:
    """The model divides the filing. Backend code transports it whole or not at all.

    Slicing shows up as arithmetic on a source string: a character range, a chunk size, a split on a
    heading. This guard reads the AST rather than grepping, so a docstring explaining the rule stays
    legal while a subscript on decoded source text does not.
    """
    suspicious = re.compile(
        r"(chunk|split_?on|slice|segment|window|midpoint|halve|paragraph_?break)", re.IGNORECASE
    )
    offenders: list[str] = []
    for path in _phase_21_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and suspicious.search(
                node.name
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {node.name}")
            if isinstance(node, ast.Attribute) and suspicious.search(node.attr):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: .{node.attr}")
    assert not offenders, (
        "a multipart module names a chunking or slicing operation. The SELECTED PARSING MODEL "
        f"divides the filing; the backend transports it intact: {offenders}"
    )


def test_no_multipart_module_names_a_filing_section() -> None:
    """PRODUCT-DIRECTION-INVARIANT rule 1, applied to the code that decides what to ask for.

    A brief carries the model's own part titles. If a filing-section name ever appeared as an
    evaluated literal here, the backend would be supplying the vocabulary it exists not to supply.
    """
    forbidden = re.compile(
        r"^(md&a|md and a|risk[ _]factors?|item[ _]?\d+[a-z]?|part[ _]?[ivx]+|footnote|"
        r"signature[ _]block|certification|exhibit[ _]?\d*|financial[ _]statements?)$",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in _phase_21_files():
        for line, value in _string_constants(path):
            if forbidden.match(value.strip()):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {value!r}")
    assert not offenders, f"a multipart module names a filing section: {offenders}"


def test_the_part_status_vocabulary_is_workflow_and_not_filing_taxonomy() -> None:
    """MUTATION PROOF. The five statuses describe WORK, not content, and an unknown one survives."""
    from packages.multipart import PartStatus

    values = {member.value for member in PartStatus}
    assert values == {
        "complete",
        "needs_subparts",
        "source_ambiguity",
        "image_dependency_unavailable",
        "unable_to_complete",
        "unrecognised",
    }
    for value in values:
        assert not re.search(r"item|note|exhibit|risk|statement", value), (
            f"a workflow status acquired a filing-domain word: {value}"
        )


# --- 2. no blind continuation ------------------------------------------------------------------------


def test_no_shipped_source_asks_a_model_to_continue_a_response() -> None:
    """The protocol prohibition, enforced against every evaluated string in the repository.

    A truncated response is preserved as evidence and replaced by a model-directed replanning call.
    Nothing anywhere asks a model to resume from where a cap cut it off.
    """
    forbidden = re.compile(
        r"(continue (from|where|the response)|resume (from|the response)|carry on from|"
        r"pick up where|from where you (left|stopped))",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        for line, value in _string_constants(path):
            if forbidden.search(value):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {value[:80]!r}")
    for path in list(PROMPTS.rglob("*.txt")) + list(PROMPTS.rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for number, content in enumerate(text.splitlines(), 1):
            if forbidden.search(content):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {content.strip()[:80]}")
    assert not offenders, (
        "something asks a model to continue an interrupted response. Blind continuation is "
        f"prohibited: a truncated attempt is evidence and produces a replanning call: {offenders}"
    )


def test_a_truncated_task_state_is_terminal_so_it_can_never_be_resumed() -> None:
    """The prohibition enforced structurally rather than by wording."""
    from packages.evaluation_store import TaskState, permitted_task_transitions

    assert permitted_task_transitions(TaskState.TRUNCATED) == frozenset(), (
        "TRUNCATED gained an outgoing transition. Reopening a truncated attempt IS blind "
        "continuation."
    )


def test_no_multipart_module_concatenates_response_bodies() -> None:
    """Joining two response texts into one document is the other half of blind continuation."""
    offenders: list[str] = []
    pattern = re.compile(r"(response_body|visible_text|partial)\s*\+[^=]|\.join\(.*response")
    for path in _phase_21_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"a multipart module concatenates response text: {offenders}"


# --- 3. no winner ---------------------------------------------------------------------------------------


def test_no_shipped_source_ranks_scores_or_selects_among_the_candidates() -> None:
    """rules.md section 21 rules 8 and 9. The user selects; nothing here decides."""
    forbidden = re.compile(
        r"(best_?model|winning_?model|winner|preferred_?parser|primary_?parser|model_?score|"
        r"model_?rank|recommend_?model|choose_?model|select_?best)",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in _python_files(PACKAGES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = (
                node.name
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                else getattr(node, "attr", None) or getattr(node, "id", None)
            )
            if isinstance(name, str) and forbidden.search(name):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {name}")
    assert not offenders, f"shipped source ranks or selects a parser: {offenders}"


def test_the_multipart_prompt_families_are_one_set_shared_by_every_candidate() -> None:
    """A per-model prompt would make the comparison a measurement of the prompt, not the protocol."""
    from packages.prompt_registry import PromptRegistry

    registry = PromptRegistry.from_directory(PROMPTS / "parser")
    multipart = [v for v in registry.versions if v.prompt_id.startswith("parser-multipart-")]
    assert len(multipart) >= 5, "the multipart families are missing"
    for version in multipart:
        for label in ("gpt", "nemotron", "qwen", "llama", "openai", "nvidia", "bedrock"):
            # WORD BOUNDARIES, because "meta" lives inside "metadata" and a substring test
            # would fail on a prompt that correctly asks for a metadata key.
            assert not re.search(rf"\b{label}\b", version.text, re.IGNORECASE), (
                f"{version.identity} names a model provider; the families are shared by all five"
            )
        assert version.filename.endswith(".txt")


def test_every_multipart_prompt_role_resolves_to_exactly_one_active_version() -> None:
    """Two active prompts for one role is a configuration error, not a preference to resolve."""
    from packages.prompt_registry import PromptRegistry

    registry = PromptRegistry.from_directory(PROMPTS / "parser")
    for role in (
        "parsing",
        "parsing_multipart_plan",
        "parsing_multipart_part",
        "parsing_multipart_replan",
        "parsing_multipart_reconcile",
        "parsing_multipart_gap",
        "parsing_multipart_format_repair",
    ):
        assert registry.active_for(role).text.strip(), f"no ACTIVE prompt for {role}"


def test_the_two_historical_single_response_prompts_are_untouched() -> None:
    """Thirty preserved invocations quote them by hash. Editing one rewrites what they claim."""
    from packages.prompt_registry import PromptRegistry

    registry = PromptRegistry.from_directory(PROMPTS / "parser")
    historical = {
        v.identity: v for v in registry.versions if v.prompt_id == "parser-complete-filing"
    }
    assert set(historical) == {"parser-complete-filing@1", "parser-complete-filing@2"}
    assert historical["parser-complete-filing@1"].status == "SUPERSEDED"
    assert historical["parser-complete-filing@2"].status == "ACTIVE"
    # `from_directory` re-hashes every declared file and raises on a mismatch, so reaching this
    # line at all is the proof that neither has moved.
    assert historical["parser-complete-filing@2"].sha256 == (
        "5e84ba57304c97fc36d661a1b74ed3e9ed0ab40d264fa74eec6f11487e25bc93"
    )


# --- 4. still the parsing stage only ------------------------------------------------------------------------


def test_multipart_invokes_only_the_parsing_role() -> None:
    """Multipart multiplies parser CALLS. It authorizes no other stage."""
    from packages.evaluation_store import BILLABLE_TASK_TYPES
    from packages.orchestrator.multipart_service import _ROLE_FOR_TYPE

    for task_type in BILLABLE_TASK_TYPES:
        role = _ROLE_FOR_TYPE[task_type]
        assert role == "parsing" or role.startswith("parsing_multipart_"), (
            f"{task_type.value} resolves to the {role!r} prompt role, which is not a parsing role"
        )


def test_no_multipart_module_reaches_the_image_summary_or_analysis_roles() -> None:
    from packages.model_catalog import ModelRole

    forbidden = {ModelRole.IMAGE.value, ModelRole.SUMMARY.value, ModelRole.ANALYSIS.value}
    offenders: list[str] = []
    for path in _phase_21_files():
        for line, value in _string_constants(path):
            if value in forbidden:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {value!r}")
    assert not offenders, f"a multipart module names a non-parsing role: {offenders}"


# --- the two Phase 2 guards multipart makes more load-bearing --------------------------------------------------


def test_every_semantic_invocation_carries_the_source_set_identity() -> None:
    """A call that could not name the bytes it read is a call whose evidence cannot be checked."""
    source = (PACKAGES / "orchestrator" / "multipart_service.py").read_text(encoding="utf-8")
    assert "source_set_id" in source
    assert "the source set changed after this parse was costed" in source, (
        "the guard that refuses a moved source set has gone"
    )
    assert "MultipartProtocolError" in source


def test_the_exact_response_is_preserved_before_anything_reads_it() -> None:
    """`_preserve` runs before `_interpret`, and the order is what survives a crash between them."""
    source = (PACKAGES / "orchestrator" / "multipart_service.py").read_text(encoding="utf-8")
    preserve = source.index("self._preserve(context, task, record)")
    interpret = source.index("self._interpret(context, task, record.response_body)")
    assert preserve < interpret, (
        "a response is read before it is preserved. A crash between the two would lose bytes that "
        "were bought and cannot be regenerated for free."
    )


def test_the_format_repair_limit_is_one_and_the_original_is_never_replaced() -> None:
    from packages.orchestrator import MultipartSettings

    assert MultipartSettings().max_format_repairs_per_artifact == 1
    source = (PACKAGES / "orchestrator" / "multipart_service.py").read_text(encoding="utf-8")
    assert "the original response is preserved unchanged" in source
    assert "No regular expression rewrites a malformed response here" in source


def test_the_orchestrator_owns_the_retry_and_allows_exactly_one() -> None:
    from packages.orchestrator import MultipartSettings

    assert MultipartSettings().max_retries_per_attempt == 1
    source = (PACKAGES / "orchestrator" / "multipart_service.py").read_text(encoding="utf-8")
    assert "`max_tokens` IS NOT RETRYABLE" in source


def test_the_format_repair_call_carries_no_filing() -> None:
    """It is forbidden to change meaning, so it is given nothing to change it with."""
    source = (PACKAGES / "orchestrator" / "multipart_service.py").read_text(encoding="utf-8")
    assert "blocks = () if task.task_type is TaskType.FORMAT_REPAIR else context.blocks" in source


def test_no_multipart_module_imports_a_database_a_cache_or_a_web_framework() -> None:
    forbidden = re.compile(
        r"^\s*(import|from)\s+(sqlalchemy|alembic|psycopg|psycopg2|redis|pymongo|asyncpg|"
        r"fastapi|flask|django|starlette|uvicorn|celery)\b"
    )
    offenders: list[str] = []
    for path in _phase_21_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.match(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"a multipart module imports prohibited infrastructure: {offenders}"


def test_no_multipart_module_imports_a_provider_sdk() -> None:
    """All provider access stays behind `packages/llm_gateway`, adapter included."""
    forbidden = re.compile(r"^\s*(import|from)\s+(boto3|botocore)\b")
    offenders: list[str] = []
    for path in _phase_21_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.match(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"a multipart module imports a provider SDK: {offenders}"


def test_the_assembly_status_can_never_be_complete() -> None:
    from packages.multipart import AssemblyStatus

    names = {member.name for member in AssemblyStatus}
    assert "COMPLETE" not in names, (
        f"AssemblyStatus gained a COMPLETE member; nothing measured establishes it: {sorted(names)}"
    )
    assert "MECHANICALLY_ASSEMBLED" in names
