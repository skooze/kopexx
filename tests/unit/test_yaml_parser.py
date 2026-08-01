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


# --- Sprint 2 additions: library identity and alias bounding -----------------------------------


def test_yaml_library_is_ruamel_with_yaml_12_semantics() -> None:
    """Pin the parser choice. ADR-0013 depends on YAML 1.2 core-schema behaviour.

    PyYAML implements YAML 1.1 and would silently convert the bare scalar "no" to False, which in
    a footnote summary field is a correctness failure, not a formatting one.
    """
    import ruamel.yaml

    assert ruamel.yaml.version_info >= (0, 18), (
        f"ruamel.yaml {ruamel.yaml.version_info} is older than the pinned floor"
    )
    # The core-schema behaviour that motivated the choice.
    assert parse_yaml("v: yes\n")["v"] == "yes"


def test_yaml_parser_preserves_quoted_dates() -> None:
    """Quoted dates must remain strings, not become date objects.

    A period_end that arrives as a date object has lost its exact filed representation, and the
    application compares period boundaries as strings.
    """
    parsed = parse_yaml('period_end: "2025-09-27"\nperiod_start: "2024-09-29"\n')
    assert parsed["period_end"] == "2025-09-27"
    assert isinstance(parsed["period_end"], str)
    assert isinstance(parsed["period_start"], str)


def test_yaml_parser_preserves_quoted_fiscal_period_and_version() -> None:
    """Values that look numeric but are identifiers stay strings when quoted."""
    parsed = parse_yaml('fp: "Q2"\nfootnote_number: "01"\nschema_version: "1.0.0"\n')
    assert parsed["footnote_number"] == "01", "leading zero must survive"
    assert parsed["schema_version"] == "1.0.0"
    assert require_string(parsed, "fp") == "Q2"


def test_yaml_parser_rejects_excessive_aliases() -> None:
    """SECURITY: alias expansion is multiplicative and must be bounded before parsing.

    Measured during Sprint 2: this five-line document expanded to 59,049 leaf nodes before the
    guard existed. Two more levels exhaust memory. Post-parse size limits cannot help, because the
    allocation has already happened by the time they run.
    """
    bomb = (
        'a: &a ["x","x","x","x","x","x","x","x","x"]\n'
        "b: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
        "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]\n"
        "d: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c]\n"
        "e: [*d,*d,*d,*d,*d,*d,*d,*d,*d]\n"
    )
    with pytest.raises(YamlSafetyError, match="alias"):
        parse_yaml(bomb)


def test_yaml_parser_rejects_excessive_anchors() -> None:
    from packages.llm_gateway.yaml_parser import MAX_ANCHORS

    doc = "".join(f"k{i}: &anchor{i} value{i}\n" for i in range(MAX_ANCHORS + 5))
    with pytest.raises(YamlSafetyError, match="anchor"):
        parse_yaml(doc)


def test_yaml_parser_allows_a_small_number_of_aliases() -> None:
    """The bound must not break legitimate reuse."""
    parsed = parse_yaml("base: &b\n  unit: USD\nfirst: *b\nsecond: *b\n")
    assert parsed["first"] == {"unit": "USD"}
    assert parsed["second"] == {"unit": "USD"}
