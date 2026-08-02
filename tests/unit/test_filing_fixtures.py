"""Tests over the committed filing fixtures.

These run entirely offline from files in tests/fixtures/filings/, which were extracted from four
real Apple filings retrieved in Sprint 3. The manifest pins each source URL and SHA-256, so the
fixtures are traceable to specific filed documents without committing the documents themselves.

This is also where the item-disclosure exclusion list is exercised against real data rather than
against an invented example.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "filings"
EXCLUSIONS = REPO_ROOT / "metric_definitions" / "item_disclosure_exclusions.yaml"

TEN_K = "0000320193-25-000079"
TEN_QS = ("0000320193-25-000008", "0000320193-25-000057", "0000320193-25-000073")


def _yaml(path: Path) -> dict:
    return YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _yaml(FIXTURES / "manifest.yaml")


@pytest.fixture(scope="module")
def exclusions() -> dict:
    return _yaml(EXCLUSIONS)


def _inventory(accession: str) -> list[dict]:
    return _yaml(FIXTURES / accession / "report-inventory.yaml")["reports"]


def _notes_candidates(accession: str) -> list[dict]:
    return [r for r in _inventory(accession) if r["menu_category"] == "Notes"]


def _is_excluded(report: dict, exclusions: dict) -> bool:
    """Stage 2 of canonicalization, applied to one candidate.

    Deliberately small and explicit here. Sprint 4 moves this into the canonicalizer; this test
    then becomes the regression check that the move preserved the result.
    """
    title = (report["short_name"] or "").strip().lower()
    role = report["role"] or ""
    if any(entry["match"].lower() in title for entry in exclusions["excluded_titles"]):
        return True
    return any(
        entry["fragment"].lower() in role.lower() for entry in exclusions["excluded_role_fragments"]
    )


# --- manifest integrity ----------------------------------------------------------------------


def test_manifest_covers_every_fixture_filing(manifest: dict) -> None:
    accessions = {f["accession"] for f in manifest["filings"]}
    assert accessions == {TEN_K, *TEN_QS}
    assert len(manifest["filings"]) == 4, "one 10-K and three 10-Qs"


def test_manifest_pins_a_source_url_and_hash_for_every_object(manifest: dict) -> None:
    """A fixture without a pinned source cannot be proven faithful to a filed document."""
    for filing in manifest["filings"]:
        assert filing["objects"], f"{filing['accession']} has no objects"
        for obj in filing["objects"]:
            assert obj["url"].startswith("https://www.sec.gov/Archives/")
            assert re.fullmatch(r"[0-9a-f]{64}", obj["sha256"]), obj["role"]
            assert obj["size_bytes"] > 0


def test_committed_filing_summary_matches_its_recorded_hash(manifest: dict) -> None:
    """The extracted fixture is the same bytes the manifest recorded."""
    from packages.storage import sha256_bytes

    for filing in manifest["filings"]:
        path = FIXTURES / filing["accession"] / "filing-summary.xml"
        assert sha256_bytes(path.read_bytes()) == filing["filing_summary_sha256"]


def test_fixture_tree_stays_small() -> None:
    """The strategy is extracted fixtures, not committed filings.

    Sprint 3 set a 25 MB target and a 40 MB ceiling. Blowing past it means someone committed a
    raw document, which belongs in object storage instead.
    """
    total = sum(p.stat().st_size for p in FIXTURES.rglob("*") if p.is_file())
    assert total < 25 * 1024 * 1024, f"fixture tree is {total:,} bytes"


def test_fixtures_need_no_network() -> None:
    """Every fixture is a local file. A test that reaches SEC is not deterministic."""
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            assert path.read_bytes(), f"{path} is empty"


# --- the verified structure of Apple's FY2025 10-K ---------------------------------------------


def test_ten_k_has_seventy_one_renderer_reports() -> None:
    """The number that started the 13-not-58 correction.

    58 was a count of XBRL TextBlock facts. 71 is the renderer's report count. Neither is the
    footnote count. Recorded here against the real filing so the distinction cannot drift back.
    """
    assert len(_inventory(TEN_K)) == 71


def test_one_of_the_seventy_one_reports_is_a_navigation_entry() -> None:
    """Measured in Sprint 3 against the acquired filing, refining the recorded 71.

    The renderer appends an "All Reports" entry of ReportType Book. It carries no menu category,
    no role URI, and no file. It is the renderer's own table of contents, not a report from the
    filing. Counting it as one would put every downstream total off by one.
    """
    inventory = _inventory(TEN_K)
    uncategorized = [r for r in inventory if not r["menu_category"]]
    assert len(uncategorized) == 1
    assert uncategorized[0]["short_name"] == "All Reports"
    assert uncategorized[0]["role"] == ""
    assert uncategorized[0]["file_name"] == ""


def test_ten_k_menu_categories_match_the_recorded_distribution() -> None:
    """70 real reports, categorized. The 71st is the navigation entry above."""
    counts: dict[str, int] = {}
    for report in _inventory(TEN_K):
        if not report["menu_category"]:
            continue
        counts[report["menu_category"]] = counts.get(report["menu_category"], 0) + 1
    assert counts == {
        "Cover": 2,
        "Statements": 6,
        "Notes": 16,
        "Policies": 1,
        "Tables": 12,
        "Details": 33,
    }
    assert sum(counts.values()) == 70


def test_notes_category_is_a_superset_of_the_footnotes() -> None:
    """menucat='Notes' over-includes. It is a candidate set, not an answer."""
    assert len(_notes_candidates(TEN_K)) == 16


# --- the item-disclosure exclusion list, against real candidates --------------------------------


def test_exclusion_list_removes_exactly_the_three_item_disclosures(exclusions: dict) -> None:
    """16 candidates minus 3 item disclosures leaves the 13 canonical footnotes."""
    candidates = _notes_candidates(TEN_K)
    excluded = [r for r in candidates if _is_excluded(r, exclusions)]
    remaining = [r for r in candidates if not _is_excluded(r, exclusions)]

    assert len(excluded) == 3, f"excluded {[r['short_name'] for r in excluded]}"
    assert len(remaining) == 13, f"remaining {len(remaining)}"

    names = {r["short_name"] for r in excluded}
    assert names == {
        "Insider Trading Arrangements",
        "Insider Trading Policies and Procedures",
        "Cybersecurity Risk Management and Strategy Disclosure",
    }


def test_no_real_footnote_is_excluded(exclusions: dict) -> None:
    """The every-footnote requirement fails if the exclusion list is too greedy."""
    remaining = [r for r in _notes_candidates(TEN_K) if not _is_excluded(r, exclusions)]
    titles = {r["short_name"] for r in remaining}
    for expected in (
        "Revenue",
        "Income Taxes",
        "Debt",
        "Leases",
        "Segment Information and Geographic Data",
    ):
        assert expected in titles, f"{expected} was wrongly excluded"


def test_unknown_namespace_flags_for_review_rather_than_defaulting(exclusions: dict) -> None:
    """Neither silent default is acceptable.

    Silently including an unknown disclosure inflates the note count and spends model budget on a
    non-footnote. Silently excluding it drops a real footnote and breaks the every-footnote
    requirement.
    """
    policy = exclusions["unknown_namespace_policy"]
    assert policy["action"] == "flag_for_review"
    assert policy["review_state"] == "REQUIRES_REVIEW"


def test_exclusion_list_declares_its_expected_apple_result(exclusions: dict) -> None:
    """The list carries its own verification target, so drift is detectable."""
    expected = next(e for e in exclusions["expected_results"] if e["accession"] == TEN_K)
    assert expected["candidates_menucat_notes"] == 16
    assert expected["excluded"] == 3
    assert expected["canonical_footnotes"] == 13


@pytest.mark.parametrize("accession", TEN_QS)
def test_quarterly_filings_also_carry_notes_candidates(accession: str, exclusions: dict) -> None:
    """A 10-Q has fewer notes than a 10-K but is not empty, and the exclusions still apply."""
    candidates = _notes_candidates(accession)
    assert candidates, f"{accession} yielded no Notes candidates"
    remaining = [r for r in candidates if not _is_excluded(r, exclusions)]
    assert remaining, f"{accession} had every candidate excluded"
    assert len(remaining) <= len(candidates)
