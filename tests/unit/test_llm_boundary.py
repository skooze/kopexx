"""Model content-boundary enforcement tests.

LLM-SERIALIZATION-INVARIANT (rules.md section 3): model-visible content may be only unmarked
normalized plain text or exactly one unfenced YAML 1.2 document.
"""

from __future__ import annotations

import pytest

from packages.llm_gateway import (
    Budget,
    BudgetExceededError,
    ContentFormat,
    FootnoteSummaryRequest,
    LlmGateway,
    NativeToolUseProhibitedError,
    SourceBlockPayload,
    TablePayload,
    Violation,
    compile_footnote_summary_request,
    compile_plain_text,
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
    report = validate_plain_text('{"footnote": {"number": "9"}}')
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

VALID_YAML = 'footnote:\n  id: "fn-0009"\n  title: Debt\ntopics:\n  - debt\n  - liquidity\n'


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


def _sample_request() -> FootnoteSummaryRequest:
    return FootnoteSummaryRequest(
        cik="0000320193",
        accession="0000320193-25-000079",
        form="10-K",
        period_end="2025-09-27",
        footnote_id="fn-0009",
        footnote_number="9",
        footnote_title="Debt",
        source_blocks=[
            SourceBlockPayload("debt-narr-01", "narrative", "The Company issues unsecured notes."),
        ],
        tables=[
            TablePayload(
                "debt-mat-01",
                "Future Debt Maturities",
                "USD millions",
                ["year", "amount"],
                [["2026", 1250], ["2027", 1800]],
            )
        ],
    )


def test_model_visible_payload_contains_no_markdown() -> None:
    payload = compile_footnote_summary_request(_sample_request())
    assert "```" not in payload.content
    assert "|" not in payload.content.replace("|-", "")  # block scalars use |- , not tables
    assert "**" not in payload.content
    assert "`" not in payload.content


def test_model_visible_payload_contains_no_json() -> None:
    payload = compile_footnote_summary_request(_sample_request())
    assert not payload.content.lstrip().startswith("{")
    assert '":' not in payload.content


def test_model_visible_payload_contains_no_xml() -> None:
    payload = compile_footnote_summary_request(_sample_request())
    assert "<?xml" not in payload.content
    assert "</" not in payload.content


def test_model_visible_payload_contains_no_html() -> None:
    payload = compile_footnote_summary_request(_sample_request())
    for tag in ("<html", "<body", "<div", "<table", "<p>"):
        assert tag not in payload.content.lower()


def test_compiled_payload_quotes_identifiers() -> None:
    """FINANCIAL-INVARIANT: an unquoted CIK loses its leading zeros in YAML 1.2."""
    payload = compile_footnote_summary_request(_sample_request())
    assert '"0000320193"' in payload.content
    assert '"0000320193-25-000079"' in payload.content


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
    payload = compile_footnote_summary_request(_sample_request())
    with pytest.raises(NativeToolUseProhibitedError):
        gateway.invoke(
            model_id="mock-model-v1",
            system_text="You summarize one canonical footnote.",
            payload=payload,
            prompt_version="footnote-summary-v1.0.0",
            tools=[{"name": "search", "input_schema": {"type": "object"}}],
        )


def test_gateway_records_exact_request_and_response_bodies() -> None:
    """SECURITY-INVARIANT: the original model-visible content is preserved unmodified."""
    provider = MockProvider()
    gateway = LlmGateway(provider)
    payload = compile_footnote_summary_request(_sample_request())
    result = gateway.invoke(
        model_id="mock-model-v1",
        system_text="You summarize one canonical footnote.",
        payload=payload,
        prompt_version="footnote-summary-v1.0.0",
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
    payload = compile_footnote_summary_request(_sample_request())
    result = gateway.invoke(
        model_id="mock-model-v1",
        system_text="You summarize one canonical footnote.",
        payload=payload,
        prompt_version="footnote-summary-v1.0.0",
    )
    assert result.parsed["summary"]["classification"] == "routine"
    assert result.parsed["footnote"]["number"] == "1"  # quoted, so still a string


def test_gateway_rejects_json_model_response() -> None:
    """A provider returning JSON must be caught at the boundary, not parsed."""
    gateway = LlmGateway(MockProvider('{"summary": {"classification": "routine"}}'))
    payload = compile_footnote_summary_request(_sample_request())
    with pytest.raises(RuntimeError, match="rejected at the boundary"):
        gateway.invoke(
            model_id="mock-model-v1",
            system_text="You summarize one canonical footnote.",
            payload=payload,
            prompt_version="footnote-summary-v1.0.0",
        )
    assert gateway.audit[-1].status == "BOUNDARY_REJECTED"


def test_gateway_enforces_budget_before_invocation() -> None:
    provider = MockProvider()
    gateway = LlmGateway(provider)
    payload = compile_footnote_summary_request(_sample_request())
    with pytest.raises(BudgetExceededError):
        gateway.invoke(
            model_id="mock-model-v1",
            system_text="You summarize one canonical footnote.",
            payload=payload,
            prompt_version="footnote-summary-v1.0.0",
            budget=Budget(max_input_tokens=1),
        )
    assert provider.invocations == [], "budget must be enforced before spend"
