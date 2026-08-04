"""Model content-boundary enforcement tests.

LLM-SERIALIZATION-INVARIANT (rules.md section 3): model-visible content may be only unmarked
normalized plain text or exactly one unfenced YAML 1.2 document.
"""

from __future__ import annotations

import pytest

from packages.llm_gateway import (
    Budget,
    BudgetExceededError,
    CompiledPayload,
    ContentFormat,
    LlmGateway,
    NativeToolUseProhibitedError,
    Violation,
    compile_plain_text,
    compile_yaml,
    parse_yaml,
    to_yaml,
    validate,
    validate_plain_text,
    validate_yaml_text,
)
from packages.llm_gateway.providers.mock import MockProvider

# --- plain text -----------------------------------------------------------------------------


def test_plain_text_payload_accepts_unmarked_text() -> None:
    report = validate_plain_text(
        "The Company issues unsecured short-term promissory notes under a commercial paper "
        "program.\n\nOutstanding balances are reported at amortized cost."
    )
    assert report.ok, report.violations


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# Heading\n\nbody text", Violation.MARKDOWN_HEADING),
        ("| year | amount |\n| --- | --- |\n| 2026 | 1250 |", Violation.MARKDOWN_TABLE),
        ("> quoted disclosure text", Violation.MARKDOWN_BLOCKQUOTE),
        ("This is **important** disclosure", Violation.MARKDOWN_EMPHASIS),
        ("Use the `LongTermDebt` concept", Violation.INLINE_BACKTICK),
        ("See [the filing](https://example.com/x)", Violation.MARKDOWN_LINK),
        ("```\nfenced\n```", Violation.MARKDOWN_FENCE),
    ],
)
def test_plain_text_payload_rejects_markdown(text: str, expected: Violation) -> None:
    report = validate_plain_text(text)
    assert not report.ok
    assert expected in report.violations


def test_plain_text_payload_rejects_json() -> None:
    report = validate_plain_text('{"node": {"number": "9"}}')
    assert not report.ok
    assert Violation.JSON_OBJECT in report.violations

    lines = validate_plain_text('{"a": 1}\n{"b": 2}\n{"c": 3}')
    assert not lines.ok
    assert Violation.JSON_LINES in lines.violations

    schema = validate_plain_text('"type": "object", "additionalProperties": false')
    assert not schema.ok
    assert Violation.JSON_SCHEMA in schema.violations


def test_plain_text_payload_rejects_xml() -> None:
    report = validate_plain_text('<?xml version="1.0"?><root><a>1</a></root>')
    assert not report.ok
    assert Violation.XML_DECLARATION in report.violations


def test_plain_text_payload_rejects_html() -> None:
    report = validate_plain_text("<html><body><p>Item 1A. Risk Factors</p></body></html>")
    assert not report.ok
    assert Violation.HTML_MARKUP in report.violations


def test_model_visible_payload_contains_no_xbrl() -> None:
    report = validate_plain_text(
        '<ix:nonNumeric name="us-gaap:DebtDisclosureTextBlock">Debt</ix:nonNumeric>'
    )
    assert not report.ok
    assert Violation.XBRL_TAG in report.violations


def test_empty_payload_rejected() -> None:
    assert not validate_plain_text("").ok
    assert not validate_yaml_text("   ").ok


# --- YAML -----------------------------------------------------------------------------------

VALID_YAML = 'node:\n  id: "n-0009"\n  title: A model-chosen label\nlabels:\n  - alpha\n  - beta\n'


def test_yaml_payload_accepts_unfenced_yaml() -> None:
    report = validate_yaml_text(VALID_YAML)
    assert report.ok, report.violations


def test_yaml_payload_accepts_leading_document_marker() -> None:
    assert validate_yaml_text("---\n" + VALID_YAML).ok


def test_yaml_payload_rejects_markdown_fence() -> None:
    report = validate_yaml_text("```yaml\n" + VALID_YAML + "```\n")
    assert not report.ok
    assert Violation.MARKDOWN_FENCE in report.violations


def test_yaml_payload_rejects_preamble() -> None:
    report = validate_yaml_text("Here is the summary you asked for:\n" + VALID_YAML)
    assert not report.ok
    assert Violation.YAML_PREAMBLE in report.violations


def test_yaml_payload_rejects_postamble() -> None:
    report = validate_yaml_text(VALID_YAML + "Let me know if you need anything else\n")
    assert not report.ok
    assert Violation.YAML_POSTAMBLE in report.violations


def test_yaml_payload_rejects_multiple_documents() -> None:
    report = validate_yaml_text(VALID_YAML + "---\n" + VALID_YAML)
    assert not report.ok
    assert Violation.YAML_MULTIPLE_DOCUMENTS in report.violations


# --- compiler -------------------------------------------------------------------------------


def _sample_payload() -> CompiledPayload:
    """A generic model-visible request, compiled through the only permitted path.

    DELIBERATELY CARRIES NO FILING ONTOLOGY. This helper used to build a `FootnoteSummaryRequest`
    with a footnote id, number and title, a typed source block and a typed table — the
    deterministic parser's output shape. That contract is deleted and no model has been invoked, so
    no request shape can honestly be asserted. What these tests actually check is the FORMAT
    boundary, and the format boundary is a property of the compiler, not of any payload schema. The
    mapping below therefore exercises exactly the things that can go wrong: identifiers that YAML
    1.2 would destroy if left unquoted, prose long enough to become a literal block scalar, and a
    nested sequence of records.
    """
    return compile_yaml(
        {
            "request": {"task": "boundary_probe", "prompt_version": "test-v1"},
            "filing": {
                "cik": "0000320193",
                "accession": "0000320193-25-000079",
                "form": "10-K",
                "period_end": "2025-09-27",
            },
            "nodes": [
                {
                    "id": "node-0001",
                    "title": "A node label the model chose",
                    "text": (
                        "A paragraph long enough to be emitted as a literal block scalar so the "
                        "model sees natural paragraph structure rather than one folded line."
                    ),
                },
            ],
            "rows": [
                {"period": "2026", "amount": 1250},
                {"period": "2027", "amount": 1800},
            ],
        },
        origin="test.boundary_probe",
    )


def test_model_visible_payload_contains_no_markdown() -> None:
    payload = _sample_payload()
    assert "```" not in payload.content
    assert "|" not in payload.content.replace("|-", "")  # block scalars use |- , not tables
    assert "**" not in payload.content
    assert "`" not in payload.content


def test_model_visible_payload_contains_no_json() -> None:
    payload = _sample_payload()
    assert not payload.content.lstrip().startswith("{")
    assert '":' not in payload.content


def test_model_visible_payload_contains_no_xml() -> None:
    payload = _sample_payload()
    assert "<?xml" not in payload.content
    assert "</" not in payload.content


def test_model_visible_payload_contains_no_html() -> None:
    payload = _sample_payload()
    for tag in ("<html", "<body", "<div", "<table", "<p>"):
        assert tag not in payload.content.lower()


def test_compiled_payload_quotes_identifiers() -> None:
    """FINANCIAL-INVARIANT: an unquoted CIK loses its leading zeros in YAML 1.2."""
    payload = _sample_payload()
    assert '"0000320193"' in payload.content
    assert '"0000320193-25-000079"' in payload.content


def test_identifier_quoting_covers_generic_node_ids_not_a_filing_ontology() -> None:
    """The quoting rule keys on transport and identity names, never on filing content kinds.

    `footnote_id`, `canonical_footnote_id`, `footnote_number` and `parser_version` were removed
    from IDENTIFIER_KEYS with the parser that produced them. A model-chosen label lands under the
    generic `id` and `number` keys, which are quoted, so a zero-prefixed label a filing actually
    uses still survives the round trip.
    """
    from packages.llm_gateway.yaml_serializer import IDENTIFIER_KEYS

    assert {"id", "number", "cik", "accession"} <= IDENTIFIER_KEYS
    assert not (
        {"footnote_id", "canonical_footnote_id", "footnote_number", "parser_version"}
        & IDENTIFIER_KEYS
    ), "the deleted parser's identifiers must not reappear in the quoting rule"

    payload = compile_yaml({"node": {"id": "0009", "number": "007"}}, origin="test.quoting")
    assert '"0009"' in payload.content
    assert '"007"' in payload.content


def test_compile_yaml_rejects_prohibited_content() -> None:
    from packages.llm_gateway.errors import BoundaryViolationError

    with pytest.raises(BoundaryViolationError):
        compile_plain_text("# a markdown heading", origin="test")


def test_compile_plain_text_normalizes_whitespace() -> None:
    payload = compile_plain_text("a   b\n\n\n  c   d  ", origin="test")
    assert payload.content == "a b\n\nc d"
    assert payload.content_format is ContentFormat.PLAIN_TEXT


# --- gateway --------------------------------------------------------------------------------


def test_model_gateway_rejects_native_tool_schema() -> None:
    """Native tool calling requires JSON Schema definitions and yields JSON arguments."""
    gateway = LlmGateway(MockProvider())
    payload = _sample_payload()
    with pytest.raises(NativeToolUseProhibitedError):
        gateway.invoke(
            model_id="mock-model-v1",
            system_text="You return one unfenced YAML 1.2 document.",
            payload=payload,
            prompt_version="test-v1",
            tools=[{"name": "search", "input_schema": {"type": "object"}}],
        )


def test_gateway_records_exact_request_and_response_bodies() -> None:
    """SECURITY-INVARIANT: the original model-visible content is preserved unmodified."""
    provider = MockProvider()
    gateway = LlmGateway(provider)
    payload = _sample_payload()
    result = gateway.invoke(
        model_id="mock-model-v1",
        system_text="You return one unfenced YAML 1.2 document.",
        payload=payload,
        prompt_version="test-v1",
    )
    record = result.record
    assert record.request_body == payload.content
    assert record.response_body == provider.invoke.__self__._response_text  # type: ignore[attr-defined]
    assert record.request_format == "yaml"
    assert record.response_format == "yaml"
    assert record.status == "SUCCEEDED"
    assert record.latency_seconds >= 0


def test_gateway_parses_yaml_response() -> None:
    gateway = LlmGateway(MockProvider())
    payload = _sample_payload()
    result = gateway.invoke(
        model_id="mock-model-v1",
        system_text="You return one unfenced YAML 1.2 document.",
        payload=payload,
        prompt_version="test-v1",
    )
    assert result.parsed["schema_version"] == "mock-response-v1"
    assert "text" in result.parsed["response"]


def test_gateway_rejects_json_model_response() -> None:
    """A provider returning JSON must be caught at the boundary, not parsed."""
    gateway = LlmGateway(MockProvider('{"response": {"text": "json is not permitted"}}'))
    payload = _sample_payload()
    with pytest.raises(RuntimeError, match="rejected at the boundary"):
        gateway.invoke(
            model_id="mock-model-v1",
            system_text="You return one unfenced YAML 1.2 document.",
            payload=payload,
            prompt_version="test-v1",
        )
    assert gateway.audit[-1].status == "BOUNDARY_REJECTED"


def test_gateway_enforces_budget_before_invocation() -> None:
    provider = MockProvider()
    gateway = LlmGateway(provider)
    payload = _sample_payload()
    with pytest.raises(BudgetExceededError):
        gateway.invoke(
            model_id="mock-model-v1",
            system_text="You return one unfenced YAML 1.2 document.",
            payload=payload,
            prompt_version="test-v1",
            budget=Budget(max_input_tokens=1),
        )
    assert provider.invocations == [], "budget must be enforced before spend"


# --- the Phase 2.1 narrowing, and the mutation proofs that make it safe --------------------------
#
# `MARKDOWN_FENCE` was removed from the SERIALIZATION set — the violations that still apply to a
# document that PARSES as one YAML 1.2 mapping. It was there on the ground that "a fenced document
# is fenced", which is true of a fenced document and not true of the CHECK, which is a textual
# search for three backticks at the start of any line.
#
# Two real request shapes must carry such a line inside a block scalar: the replanning call carries
# the exact truncated response as evidence, and the format-repair call carries the exact malformed
# response — which is very often malformed BECAUSE it is fenced. Under the old rule neither request
# could be constructed, so the protocol that recovers a paid-for response would have been
# unbuildable.
#
# The narrowing is safe because a fenced document CANNOT reach that branch, and the three tests
# below are the proof rather than the argument.


def test_a_fence_wrapped_document_cannot_parse_as_a_yaml_mapping() -> None:
    """THE LOAD-BEARING FACT. If this stopped holding, the narrowing below would be unsafe."""
    from packages.llm_gateway.errors import YamlParseError

    for wrapped in ("```yaml\nkey: value\n```", "```\nkey: value\n```"):
        with pytest.raises(YamlParseError):
            parse_yaml(wrapped)


def test_a_fenced_document_is_still_refused() -> None:
    """MUTATION PROOF. The narrowing must not have made a fenced response acceptable."""
    report = validate("```yaml\nkey: value\n```", ContentFormat.YAML)
    assert not report.ok
    assert Violation.MARKDOWN_FENCE in report.violations


def test_a_json_document_is_still_refused_although_it_parses_as_yaml() -> None:
    """MUTATION PROOF. JSON is a YAML subset, so it DOES reach the narrowed branch."""
    report = validate('{"a": 1}', ContentFormat.YAML)
    assert not report.ok
    assert Violation.JSON_OBJECT in report.violations


def test_a_yaml_document_carrying_a_fence_inside_a_block_scalar_is_accepted() -> None:
    """The shape a replanning or format-repair request must be able to take.

    The document is one YAML 1.2 mapping. The backticks are DATA — the exact bytes a model returned
    — and a request that could not carry them could not ask a model to repair its own output.
    """
    document = to_yaml(
        {
            "brief": "format_repair",
            "malformed_response": "```yaml\nartifact: x\nnodes: []\n```",
        }
    )
    report = validate(document, ContentFormat.YAML)
    assert report.ok, f"a compiled repair brief was refused: {report.violations}"
    assert isinstance(parse_yaml(document), dict)


def test_a_yaml_document_carrying_filing_markup_in_a_scalar_is_still_accepted() -> None:
    """The Phase 2 narrowing, re-asserted so the two cannot drift apart."""
    document = to_yaml({"quote": "<TYPE>EX-27</TYPE> and <ix:nonFraction> in one sentence"})
    assert validate(document, ContentFormat.YAML).ok
