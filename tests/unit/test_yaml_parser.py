"""Hardened YAML 1.2 safe parser tests.

Model output is untrusted. These tests prove the parser rejects unsafe constructs and preserves
the identifier semantics that financial correctness depends on.
"""

from __future__ import annotations

import pytest

from packages.llm_gateway import YamlParseError, YamlSafetyError, parse_yaml, require_string
from packages.llm_gateway.yaml_parser import MAX_DEPTH, MAX_INPUT_BYTES


def test_yaml_parser_rejects_duplicate_keys() -> None:
    """A duplicate key silently discards data in most parsers; here it is an error."""
    with pytest.raises(YamlSafetyError, match="duplicate key"):
        parse_yaml("footnote: one\nfootnote: two\n")


def test_yaml_parser_rejects_unsafe_tags() -> None:
    """Arbitrary object construction must be impossible from model output."""
    with pytest.raises((YamlSafetyError, YamlParseError)):
        parse_yaml("value: !!python/object/apply:os.system ['echo pwned']\n")


def test_yaml_parser_enforces_size_limits() -> None:
    oversized = "key: " + ("a" * (MAX_INPUT_BYTES + 1))
    with pytest.raises(YamlSafetyError, match="exceeds"):
        parse_yaml(oversized)


def test_yaml_parser_enforces_max_depth() -> None:
    deep = "".join(f"{'  ' * i}k{i}:\n" for i in range(MAX_DEPTH + 5))
    deep += f"{'  ' * (MAX_DEPTH + 5)}leaf: 1\n"
    with pytest.raises(YamlSafetyError, match="depth"):
        parse_yaml(deep)


def test_yaml_parser_rejects_multiple_documents() -> None:
    with pytest.raises(YamlSafetyError, match="document"):
        parse_yaml("a: 1\n---\nb: 2\n")


def test_yaml_parser_preserves_quoted_cik() -> None:
    """FINANCIAL-INVARIANT: YAML 1.2 turns an unquoted 0000320193 into the integer 320193."""
    quoted = parse_yaml('cik: "0000320193"\n')
    assert quoted["cik"] == "0000320193"
    assert isinstance(quoted["cik"], str)

    unquoted = parse_yaml("cik: 0000320193\n")
    assert unquoted["cik"] == 320193, "demonstrates why identifiers must always be quoted"
    with pytest.raises(YamlParseError, match="must be a quoted string"):
        require_string(unquoted, "cik")


def test_yaml_parser_preserves_accession() -> None:
    parsed = parse_yaml('accession: "0000320193-25-000079"\n')
    assert parsed["accession"] == "0000320193-25-000079"
    assert require_string(parsed, "accession") == "0000320193-25-000079"


def test_yaml_12_does_not_coerce_yes_no_on_off() -> None:
    """YAML 1.1 would turn these bare scalars into booleans; the 1.2 core schema does not.

    A footnote field whose value is the word "no" must not silently become False.
    """
    parsed = parse_yaml("a: yes\nb: no\nc: on\nd: off\n")
    assert parsed == {"a": "yes", "b": "no", "c": "on", "d": "off"}


def test_yaml_parser_rejects_invalid_yaml() -> None:
    with pytest.raises(YamlParseError):
        parse_yaml("key: [unclosed\n")


def test_yaml_parser_rejects_empty_document() -> None:
    with pytest.raises(YamlParseError):
        parse_yaml("\n\n")
