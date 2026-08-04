"""Model-visible content boundary enforcement.

LLM-SERIALIZATION-INVARIANT (see rules.md, section 3):

    Model-visible content may be ONLY unmarked normalized plain text, or exactly one unfenced
    YAML 1.2 document. Markdown, JSON, JSON Lines, JSON Schema, XML, XBRL, inline XBRL, HTML,
    XHTML, native tool schemas, and native tool arguments are prohibited in both directions.

This validator is a defence-in-depth backstop, not the primary control. The primary control is
that model-visible content can only be produced by ``payload_compiler``, which builds from typed
domain objects and never passes through an internal serialization. This module exists to catch
the case where someone bypasses the compiler.

Detection is deliberately conservative in one direction: it may reject content that a human would
consider acceptable prose (for example a sentence that begins with a hash character), because a
false rejection is a loud, cheap, fixable failure, whereas a false acceptance silently ships a
prohibited format to a paid model and corrupts the audit record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from .errors import BoundaryViolationError


class ContentFormat(StrEnum):
    """The only two permitted model-visible formats."""

    PLAIN_TEXT = "plain_text"
    YAML = "yaml"


class Violation(StrEnum):
    """Every prohibited construct the validator can identify."""

    JSON_OBJECT = "json_object"
    JSON_ARRAY = "json_array"
    JSON_LINES = "json_lines"
    JSON_SCHEMA = "json_schema"
    XML_DECLARATION = "xml_declaration"
    XML_TAG = "xml_tag"
    XBRL_TAG = "xbrl_tag"
    HTML_MARKUP = "html_markup"
    MARKDOWN_FENCE = "markdown_fence"
    MARKDOWN_HEADING = "markdown_heading"
    MARKDOWN_TABLE = "markdown_table"
    MARKDOWN_LINK = "markdown_link"
    MARKDOWN_BLOCKQUOTE = "markdown_blockquote"
    MARKDOWN_EMPHASIS = "markdown_emphasis"
    INLINE_BACKTICK = "inline_backtick"
    NATIVE_TOOL_SCHEMA = "native_tool_schema"
    YAML_PREAMBLE = "yaml_preamble"
    YAML_POSTAMBLE = "yaml_postamble"
    YAML_MULTIPLE_DOCUMENTS = "yaml_multiple_documents"
    EMPTY_CONTENT = "empty_content"


@dataclass(frozen=True)
class BoundaryReport:
    """The outcome of validating one piece of model-visible content."""

    ok: bool
    declared_format: ContentFormat
    violations: tuple[Violation, ...] = field(default_factory=tuple)
    detail: str = ""

    def raise_if_violated(self, *, origin: str) -> None:
        """Raise BoundaryViolationError when the content is not permitted."""
        if self.ok:
            return
        raise BoundaryViolationError(
            origin=origin,
            declared_format=self.declared_format.value,
            violations=[v.value for v in self.violations],
            detail=self.detail,
        )


# --- detectors -------------------------------------------------------------------------------
# Each detector answers one question and is tested independently.

_JSON_OBJECT = re.compile(r'^\s*\{\s*"', re.MULTILINE)
_JSON_ARRAY = re.compile(r'^\s*\[\s*[\{"]', re.MULTILINE)
_JSON_SCHEMA_HINT = re.compile(
    r'"\$schema"|"additionalProperties"\s*:|"type"\s*:\s*"object"|"input_schema"',
)
_XML_DECLARATION = re.compile(r"<\?xml\b", re.IGNORECASE)
# An XML/HTML tag: an angle bracket, an optional slash, a name character, then eventually '>'.
_XML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9._:-]*(\s[^<>]*)?/?>")
_XBRL_TAG = re.compile(r"</?(ix|xbrl[il]?|link|xlink|us-gaap|dei)\s*:", re.IGNORECASE)
_HTML_MARKUP = re.compile(
    r"<!DOCTYPE\b|</?(html|head|body|div|span|table|tr|td|th|p|br|script|style)\b",
    re.IGNORECASE,
)
_MD_FENCE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_MD_TABLE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_MD_TABLE_RULE = re.compile(r"^\s*\|?[\s:-]*-{3,}[\s:|-]*$", re.MULTILINE)
_MD_LINK = re.compile(r"\[[^\]\n]+\]\([^)\n]+\)")
_MD_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s+\S", re.MULTILINE)
_MD_EMPHASIS = re.compile(r"(\*\*[^*\n]+\*\*)|(__[^_\n]+__)")
_INLINE_BACKTICK = re.compile(r"`")
_NATIVE_TOOL = re.compile(
    r'"(tool_use|tool_result|toolSpec|input_schema|function_call|tool_choice)"',
)
_YAML_DOC_SEP = re.compile(r"^---\s*$", re.MULTILINE)


def _json_lines(text: str) -> bool:
    """True when two or more consecutive lines each parse as a JSON object."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    jsonish = sum(1 for ln in lines if ln.startswith("{") and ln.endswith("}"))
    return jsonish >= 2


def _shared_violations(text: str) -> list[Violation]:
    """Detect constructs prohibited in BOTH plain-text and YAML content."""
    found: list[Violation] = []
    if _JSON_OBJECT.search(text):
        found.append(Violation.JSON_OBJECT)
    if _JSON_ARRAY.search(text):
        found.append(Violation.JSON_ARRAY)
    if _json_lines(text):
        found.append(Violation.JSON_LINES)
    if _JSON_SCHEMA_HINT.search(text):
        found.append(Violation.JSON_SCHEMA)
    if _NATIVE_TOOL.search(text):
        found.append(Violation.NATIVE_TOOL_SCHEMA)
    if _XML_DECLARATION.search(text):
        found.append(Violation.XML_DECLARATION)
    if _XBRL_TAG.search(text):
        found.append(Violation.XBRL_TAG)
    if _HTML_MARKUP.search(text):
        found.append(Violation.HTML_MARKUP)
    elif _XML_TAG.search(text):
        # Only report a generic XML tag when it is not already reported as HTML or XBRL,
        # so the violation list names the most specific cause.
        found.append(Violation.XML_TAG)
    if _MD_FENCE.search(text):
        found.append(Violation.MARKDOWN_FENCE)
    if _INLINE_BACKTICK.search(text):
        found.append(Violation.INLINE_BACKTICK)
    if _MD_LINK.search(text):
        found.append(Violation.MARKDOWN_LINK)
    return found


def validate_plain_text(text: str) -> BoundaryReport:
    """Validate unmarked normalized plain text.

    Plain text carries no structural markup at all. In addition to the shared prohibitions it
    must contain no Markdown headings, tables, blockquotes, or emphasis runs.
    """
    if not text or not text.strip():
        return BoundaryReport(
            ok=False,
            declared_format=ContentFormat.PLAIN_TEXT,
            violations=(Violation.EMPTY_CONTENT,),
            detail="plain-text payload is empty",
        )
    found = _shared_violations(text)
    if _MD_HEADING.search(text):
        found.append(Violation.MARKDOWN_HEADING)
    if _MD_TABLE.search(text) or _MD_TABLE_RULE.search(text):
        found.append(Violation.MARKDOWN_TABLE)
    if _MD_BLOCKQUOTE.search(text):
        found.append(Violation.MARKDOWN_BLOCKQUOTE)
    if _MD_EMPHASIS.search(text):
        found.append(Violation.MARKDOWN_EMPHASIS)
    ordered = tuple(dict.fromkeys(found))
    return BoundaryReport(
        ok=not ordered,
        declared_format=ContentFormat.PLAIN_TEXT,
        violations=ordered,
        detail="" if not ordered else f"{len(ordered)} prohibited construct(s) in plain text",
    )


#: Violations that describe the SERIALIZATION rather than a value inside it.
#:
#: These are the ones that still apply to a document that parses as YAML. A response that starts
#: `{"` is JSON whatever else is true of it, because JSON is a YAML subset and therefore parses;
#: a native tool schema is a native tool schema. Neither can be a quoted scalar the way markup can.
#:
#: MARKDOWN_FENCE WAS REMOVED FROM THIS SET IN PHASE 2.1, AND THE REMOVAL IS DEMONSTRATED RATHER
#: THAN ARGUED. It was here on the stated ground that "a fenced document is fenced" — true of a
#: document that IS fenced, and not true of the check, which is a textual search for three
#: backticks at the start of any line. A YAML literal block scalar can contain such a line, and two
#: real request shapes must:
#:
#:     the REPLANNING call carries the exact truncated response as evidence
#:     the FORMAT-REPAIR call carries the exact malformed response, which is very often malformed
#:     BECAUSE it is fenced — five of fifteen Phase 2 responses failed on serialisation alone
#:
#: Under the old rule those two requests could never be constructed, so the protocol that recovers
#: a paid-for response would have been unbuildable. The narrowing is safe because a fenced document
#: CANNOT reach this branch: `parse_yaml` raises on both "```yaml\nkey: value\n```" and
#: "```\nkey: value\n```", so a document that parses as one mapping is not fence-wrapped. That is
#: asserted directly in `tests/unit/test_llm_boundary.py`, together with mutation proofs that a
#: fenced document and a JSON document are both still refused.
_SERIALIZATION_VIOLATIONS: frozenset[Violation] = frozenset(
    {
        Violation.JSON_OBJECT,
        Violation.JSON_ARRAY,
        Violation.JSON_LINES,
        Violation.JSON_SCHEMA,
        Violation.NATIVE_TOOL_SCHEMA,
    }
)


def _parses_as_one_yaml_mapping(text: str) -> bool:
    """Whether the text really is one YAML 1.2 document with a mapping at its root.

    Imported here rather than at module scope so the validator stays usable as a pure textual
    check by anything that does not want the parser's resource limits.
    """
    from .yaml_parser import parse_yaml  # noqa: PLC0415 - see above

    try:
        return isinstance(parse_yaml(text), dict)
    except Exception:  # noqa: BLE001 - any parse failure means "not one YAML mapping"
        return False


def validate_yaml_text(text: str) -> BoundaryReport:
    """Validate that the content is exactly one unfenced YAML 1.2 document.

    A YAML payload must not be wrapped in a Markdown fence, must not carry explanatory prose
    before or after the document, and must not contain multiple documents. A leading ``---``
    document-start marker is permitted; a second one is not.

    MARKUP INSIDE A QUOTED SCALAR IS NOT A MARKUP RESPONSE, AND CONFLATING THE TWO BROKE THE
    PRODUCT. The textual detectors cannot tell `<TYPE>EX-27` appearing as the serialization from
    the same characters appearing inside a YAML string — and a parser response is REQUIRED to carry
    verbatim quotes from filings that are SGML, HTML or inline XBRL. Under the old rule, no
    response quoting a pre-2001 filing could ever pass, which is the entire corpus era this product
    exists to cover. Measured on the first real benchmark: a model returned a well-formed YAML
    document whose source quotes contained the filing's own tags, and it was rejected for
    `html_markup`.

    So when the text PARSES as exactly one YAML 1.2 document with a mapping at its root, that is
    the proof it is one unfenced YAML document, and only the SERIALIZATION violations still apply.
    This is not a relaxation: JSON is a YAML subset, so the JSON detectors stay, and so do the
    fence, native-tool and structural checks. What is dropped is only the claim that a filing may
    not be quoted accurately.
    """
    if not text or not text.strip():
        return BoundaryReport(
            ok=False,
            declared_format=ContentFormat.YAML,
            violations=(Violation.EMPTY_CONTENT,),
            detail="yaml payload is empty",
        )
    found = _shared_violations(text)
    if _parses_as_one_yaml_mapping(text):
        found = [v for v in found if v in _SERIALIZATION_VIOLATIONS]

    stripped = text.strip()
    lines = stripped.splitlines()

    # A leading document-start marker is allowed; a second separator means multiple documents.
    separators = _YAML_DOC_SEP.findall(stripped)
    leading_marker = bool(lines) and lines[0].strip() == "---"
    allowed_separators = 1 if leading_marker else 0
    if len(separators) > allowed_separators:
        found.append(Violation.YAML_MULTIPLE_DOCUMENTS)

    body = lines[1:] if leading_marker else lines
    if body:
        first = body[0].strip()
        # A YAML document begins with a mapping key, a sequence entry, or a comment.
        looks_like_yaml = (
            first.startswith("#")
            or first.startswith("- ")
            or re.match(r"^[A-Za-z_][\w.-]*\s*:(\s|$)", first) is not None
            or re.match(r'^"[^"]+"\s*:(\s|$)', first) is not None
        )
        if not looks_like_yaml:
            found.append(Violation.YAML_PREAMBLE)

        last = body[-1].strip()
        if last and not last.startswith("#"):
            # Postamble prose is a line that carries no YAML structure: no colon-space, not a
            # sequence entry, not a continuation of a block scalar (indented).
            structural = (
                ": " in last
                or last.endswith(":")
                or last.startswith("- ")
                or body[-1].startswith((" ", "\t"))
            )
            if not structural:
                found.append(Violation.YAML_POSTAMBLE)

    ordered = tuple(dict.fromkeys(found))
    return BoundaryReport(
        ok=not ordered,
        declared_format=ContentFormat.YAML,
        violations=ordered,
        detail="" if not ordered else f"{len(ordered)} prohibited construct(s) in yaml",
    )


def validate(text: str, declared_format: ContentFormat) -> BoundaryReport:
    """Validate model-visible content against its declared format."""
    if declared_format is ContentFormat.PLAIN_TEXT:
        return validate_plain_text(text)
    if declared_format is ContentFormat.YAML:
        return validate_yaml_text(text)
    raise ValueError(f"unsupported content format: {declared_format!r}")


def enforce(text: str, declared_format: ContentFormat, *, origin: str) -> None:
    """Validate and raise on violation.

    ``origin`` names the subsystem that produced the content so a violation is attributable
    without logging the content itself, which may be large and may carry filing text.
    """
    validate(text, declared_format).raise_if_violated(origin=origin)
