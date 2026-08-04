"""YAML 1.2 serialization for model-visible request payloads.

FINANCIAL-INVARIANT: identifiers must be emitted as quoted strings. YAML 1.2 parses an unquoted
0000320193 as the integer 320193, silently destroying the leading zeros that make it a valid CIK.
The same applies to accession numbers, fiscal periods, zero-prefixed labels a filing or a model
supplies, and version strings such as 1.0.0.

This module never emits Markdown, fences, or explanatory prose. Its output is exactly one
unfenced YAML 1.2 document.
"""

from __future__ import annotations

import io
import re
from typing import Any, Final

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

# Field names whose values are identifiers and must always be quoted, even when they look
# numeric. Matching is on the leaf key name at any depth.
#
# THIS IS A QUOTING RULE, NOT A FILING ONTOLOGY. Every entry names a transport or identity field —
# an SEC identifier, a date, a version, a generic node or artifact id. Nothing here asserts that a
# filing HAS a particular kind of content. The withdrawn entries `footnote_id`,
# `canonical_footnote_id`, `footnote_number` and `parser_version` came from the deterministic
# footnote pipeline that was deleted; the generic `id` and `number` keys already cover whatever
# labels a filing or a parsing model actually produces. Add a key here only when a real payload
# needs it, never in anticipation of one.
IDENTIFIER_KEYS: Final[frozenset[str]] = frozenset(
    {
        "cik",
        "accession",
        "accession_number",
        "source_id",
        "artifact_id",
        "node_id",
        "run_id",
        "job_id",
        "session_id",
        # Added by Phase 2, each because a REAL payload carries it and each because the value can
        # be all digits. A SHA-256 is hexadecimal and is all-digit roughly once in ten trillion
        # documents, which is exactly the frequency at which an unquoted identifier defect is
        # impossible to reproduce and impossible to explain.
        "sha256",
        "comment_id",
        "parent_run_id",
        "child_job_id",
        "source_set_id",
        "prompt_id",
        "target_id",
        "target_version",
        "invocation_id",
        "form_as_filed",
        "sequence_number",
        "id",
        "number",
        # Added by Phase 2.1. Every one of these is an identifier a MODEL chose while reading a
        # filing, and filings number things. A model that names a part `0405` or `12` produces an
        # unquoted YAML integer, and the identifier the next request quotes back is then `405` or
        # `12` — a part the model never named. The same class of defect as the CIK, one layer up.
        "part_id",
        "parse_plan_id",
        "parent_part_id",
        "plan_id",
        "task_id",
        "storage_token",
        "root_job_id",
        "parent_task_id",
        "fiscal_period",
        "fp",
        "fy",
        "period_end",
        "period_start",
        "filing_date",
        "report_date",
        "schema_version",
        "prompt_version",
        "version",
        "model_id",
        "form",
        "form_type",
    }
)

# Prose longer than this is emitted as a literal block scalar so the model sees natural
# paragraph structure instead of a folded single line.
LITERAL_BLOCK_THRESHOLD: Final[int] = 120

# Characters that a literal block scalar CANNOT carry back out unchanged, so a string containing
# any of them is double-quoted instead — where the emitter escapes it (\N, \L, \P, \v, \f, \x1b)
# and the reader restores the exact character.
#
# FOUND IN A REAL FILING, NOT BY INSPECTION. A 1996 10-K405 table quoted by a parsing model
# contained U+0085 NEXT LINE. Forcing style `|` bypasses the emitter's own scalar analysis, which
# would have refused block style; the character was written raw, and the reader — which treats
# U+0085, U+2028 and U+2029 as line breaks — turned it into a newline. In a short scalar that
# silently corrupted a preserved quote, so it no longer matched the bytes it cited. In a block
# scalar it broke the indentation of everything after it and the whole document became
# unreadable: an assembly this repository had just written, that it could no longer load.
#
# The set is every character outside the YAML printable range, plus the two line separators that
# ARE printable but are still read as breaks. Tab and newline are excluded deliberately: a block
# scalar carries both correctly, and EDGAR text tables are made of them.
_BLOCK_UNSAFE: Final[re.Pattern[str]] = re.compile(
    "[^"
    "\\t\\n"  # the break and the separator a block scalar carries correctly
    "\\u0020-\\u007e"  # printable ASCII
    "\\u00a0-\\u2027\\u202a-\\ud7ff"  # the BMP, minus U+2028 LINE and U+2029 PARAGRAPH SEPARATOR
    "\\ue000-\\ufffd"  # the BMP above the surrogate range
    "\\U00010000-\\U0010ffff"  # the astral planes
    "]"
)


def _coerce(value: Any, key: str | None = None) -> Any:
    """Recursively prepare a value for YAML emission."""
    if isinstance(value, dict):
        return {k: _coerce(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce(v, key) for v in value]
    if isinstance(value, str):
        if key is not None and key in IDENTIFIER_KEYS:
            return DoubleQuotedScalarString(value)
        if "\n" in value or len(value) > LITERAL_BLOCK_THRESHOLD:
            # Literal block scalars preserve paragraph boundaries in filing prose.
            normalized = value.replace("\r\n", "\n").replace("\r", "\n")
            if _BLOCK_UNSAFE.search(normalized):
                # FIDELITY BEATS READABILITY. This gives up the paragraph layout for the rare
                # string that carries a control or separator character, and keeps the character.
                return DoubleQuotedScalarString(normalized)
            return LiteralScalarString(normalized)
        if _BLOCK_UNSAFE.search(value):
            return DoubleQuotedScalarString(value)
        return value
    return value


def _represent_double_quoted(representer: Any, data: Any) -> Any:
    return representer.represent_scalar("tag:yaml.org,2002:str", str(data), style='"')


def _represent_literal(representer: Any, data: Any) -> Any:
    return representer.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


def _new_dumper() -> YAML:
    """Return a YAML 1.2 safe dumper that understands our forced-style scalars.

    The safe representer has no built-in handling for ruamel's scalar-string subclasses, so the
    two styles we rely on are registered explicitly. Safe dumping is retained rather than falling
    back to round-trip mode, which would carry comment and formatting machinery we do not need.
    """
    dumper = YAML(typ="safe", pure=True)
    dumper.default_flow_style = False
    dumper.allow_unicode = True
    dumper.width = 100
    dumper.representer.add_representer(DoubleQuotedScalarString, _represent_double_quoted)
    dumper.representer.add_representer(LiteralScalarString, _represent_literal)
    return dumper


def to_yaml(payload: dict[str, Any]) -> str:
    """Serialize a mapping to exactly one unfenced YAML 1.2 document.

    The result carries no document-start marker, no fence, and no surrounding prose, so it can be
    placed directly into model-visible content.
    """
    if not isinstance(payload, dict):
        raise TypeError(f"model payload root must be a mapping, got {type(payload).__name__}")
    buffer = io.StringIO()
    _new_dumper().dump(_coerce(payload), buffer)
    return buffer.getvalue().rstrip("\n") + "\n"
