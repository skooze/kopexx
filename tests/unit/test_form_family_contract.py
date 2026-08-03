"""The SEC 10-K / 10-Q form-family contract, enforced in ordinary CI.

WHY THIS EXISTS. A hand-written allowlist filtered EDGAR for the hyphenated strings `10-KSB` and
`10-QSB`. EDGAR writes `10KSB` and `10QSB`. The filter matched almost nothing and the project
concluded that the small-business family was "effectively absent" from EDGAR. It is roughly
190,000 filings, and `10QSB` alone is the fourth most common form in the entire family.

These tests make that failure unrepeatable. The qualifying set is DERIVED from a reviewed fixture
in which every included form carries an authoritative SEC description and a verified accession,
and any unreviewed candidate fails closed.

They read a small committed fixture. They never call the SEC and never touch the ignored research
corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "form_family.yaml"

DIRECT_ANNUAL = "direct_annual_report"
DIRECT_QUARTERLY = "direct_quarterly_report"
UNADJUDICATED = "UNADJUDICATED_REQUIRES_REVIEW"


@pytest.fixture(scope="module")
def family() -> dict:
    yaml = YAML(typ="safe", pure=True)
    return yaml.load(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def forms(family: dict) -> list[dict]:
    return family["forms"]


def qualifying_set(forms: list[dict]) -> set[str]:
    """The qualifying family, GENERATED from the reviewed inventory. Never hardcoded."""
    return {f["form"] for f in forms if f["included"]}


def adjudicate(forms: list[dict], candidate: str) -> str:
    """Classify an exact filed form string, or fail closed."""
    for f in forms:
        if f["form"] == candidate:
            return f["classification"] if f["included"] else f["exclusion_class"]
    return UNADJUDICATED


# --- 1 to 3: the inventory is complete and correctly partitioned ------------------------------


def test_every_fixture_entry_is_adjudicated(forms: list[dict]) -> None:
    for f in forms:
        assert isinstance(f["included"], bool), f"{f['form']} has no include decision"
        if f["included"]:
            assert f["classification"] in (DIRECT_ANNUAL, DIRECT_QUARTERLY)
        else:
            assert f["exclusion_class"], f"{f['form']} excluded with no class"
            assert f["exclusion_reason"], f"{f['form']} excluded with no reason"
        assert f["sec_description"], f"{f['form']} has no authoritative SEC description"
        assert f["representative_accession"], f"{f['form']} has no verified accession"
        assert f["representative_cik"], f"{f['form']} has no representative CIK"


def test_exactly_twenty_two_direct_report_forms_are_included(forms: list[dict]) -> None:
    assert sum(1 for f in forms if f["included"]) == 22


def test_exactly_nineteen_near_matches_are_excluded(forms: list[dict]) -> None:
    assert sum(1 for f in forms if not f["included"]) == 19


# --- 4 to 6: the qualifying set is derived, exact, and closed ---------------------------------


def test_qualifying_set_is_generated_from_the_reviewed_inventory(forms: list[dict]) -> None:
    q = qualifying_set(forms)
    assert len(q) == 22
    assert q == {f["form"] for f in forms if f["included"]}


def test_exact_sec_form_strings_are_preserved_unnormalized(forms: list[dict]) -> None:
    """Unhyphenated small-business strings must survive verbatim.

    Normalising `10KSB` to `10-KSB` is precisely the defect this contract exists to prevent.
    """
    q = qualifying_set(forms)
    for exact in ("10KSB", "10KSB/A", "10KSB40", "10KSB40/A", "10QSB", "10QSB/A", "10KT405"):
        assert exact in q, f"{exact} missing; the inventory has been normalised"
    # The rare hyphenated spellings are real EDGAR data-entry anomalies and are also included.
    for exact in ("10-KSB", "10-KSB/A", "10-QSB", "10-QSB/A"):
        assert exact in q
    for f in forms:
        assert f["form"] == f["form"].strip(), "leading or trailing whitespace was introduced"


def test_no_excluded_near_match_enters_the_qualifying_set(forms: list[dict]) -> None:
    q = qualifying_set(forms)
    for f in forms:
        if not f["included"]:
            assert f["form"] not in q, f"{f['form']} is excluded yet qualifies"
    for near in (
        "NT 10-K",
        "NT 10-Q",
        "NT 10-D",
        "10-12B",
        "10-12G",
        "10SB12G",
        "10-D",
        "10-C",
        "10-M",
    ):
        assert near not in q, f"{near} must never qualify"


# --- 7: an unreviewed candidate fails closed --------------------------------------------------


@pytest.mark.parametrize("candidate", ["10-KZZ", "10ZZZ", "10-K999", "NT 10-ZZ", "10QSB99"])
def test_an_unreviewed_candidate_fails_closed(forms: list[dict], candidate: str) -> None:
    assert candidate not in qualifying_set(forms)
    assert adjudicate(forms, candidate) == UNADJUDICATED


# --- 8: every known direct-report family is represented ---------------------------------------


def test_every_direct_report_family_is_represented(forms: list[dict]) -> None:
    included = [f for f in forms if f["included"]]
    variants = {f["variant"] for f in included}
    assert {"standard", "transition", "small_business", "item_405"} <= variants
    periods = {f["period"] for f in included}
    assert periods == {"annual", "quarterly"}
    assert any(f["is_amendment"] for f in included), "no amendment form included"
    assert any(not f["is_amendment"] for f in included), "no base form included"
    # each variant must carry both a base form and an amendment
    for variant in ("standard", "transition", "small_business", "item_405"):
        sub = [f for f in included if f["variant"] == variant]
        assert any(f["is_amendment"] for f in sub), f"{variant} has no amendment"
        assert any(not f["is_amendment"] for f in sub), f"{variant} has no base form"


# --- 9: guessed variants that do not exist are not admitted -----------------------------------


def test_nonexistent_guessed_variants_are_not_admitted(family: dict, forms: list[dict]) -> None:
    q = qualifying_set(forms)
    recorded = set(family["nonexistent_guessed_variants"])
    assert recorded == {"10KSB405", "10KSB405/A"}
    for ghost in recorded:
        assert ghost not in q, f"{ghost} does not occur in EDGAR and must not qualify"
        assert adjudicate(forms, ghost) == UNADJUDICATED


# --- 10: prefix matching alone can never classify ---------------------------------------------


def test_prefix_matching_alone_can_never_classify_a_form(forms: list[dict]) -> None:
    """Every one of these begins with '10' and is NOT a substantive periodic report.

    Classification must come from the SEC's description of the filing's purpose. A prefix test
    would sweep registrations, notifications and asset-backed distribution reports into the
    qualifying family.
    """
    q = qualifying_set(forms)
    prefix_traps = [f["form"] for f in forms if not f["included"] and f["form"].startswith("10")]
    assert len(prefix_traps) >= 10, "the fixture no longer exercises the prefix trap"
    for trap in prefix_traps:
        assert trap.startswith("10")
        assert trap not in q


def test_scan_provenance_is_recorded(family: dict) -> None:
    """The inventory must state what it was derived from, including the empty future quarter."""
    scan = family["scan"]
    assert scan["first_quarter"] == "1993Q1"
    assert scan["last_time_eligible_quarter"] == "2026Q3"
    assert scan["time_eligible_quarters_scanned"] == 135
    assert scan["quarters_unavailable"] == 0
    assert scan["pre_created_future_directory_data_rows"] == 0
    assert scan["distinct_ten_family_strings"] == len(family["forms"]) == 41
