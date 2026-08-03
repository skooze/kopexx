"""Integrity of the committed original-SEC-source fixtures.

These run entirely offline. Everything under `tests/fixtures/filings/` is ORIGINAL SEC SOURCE —
four inline-XBRL primary documents, one pre-2001 complete submission, and four `FilingSummary.xml`
renderer artifacts — pinned by the manifest to a source URL, a SHA-256 and a byte count. Nothing
derived is committed there any more.

WHAT THIS FILE USED TO ALSO DO. It carried nine tests that reimplemented canonicalization stage 2
inline and asserted a semantic conclusion about Apple: that 16 `menucat='Notes'` candidates minus 3
Regulation S-K item disclosures leaves 13 canonical footnotes. Those tests, their
`report-inventory.yaml` inputs, and the `item_disclosure_exclusions.yaml` taxonomy they consulted
were deleted with the deterministic parser. The backend does not decide which disclosures are
footnotes; the selected parsing model does.

WHAT THIS FILE NOW DOES THAT IT DID NOT BEFORE. It hash-verifies EVERY committed source object, not
only the four `FilingSummary.xml` files. The four primary documents are 3.9 MiB of the fixture tree
and had no verification of their own — the manifest recorded their hashes and no test ever compared
them. Preserved source that nothing checks is preserved source that can rot silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "filings"

TEN_K = "0000320193-25-000079"
TEN_QS = ("0000320193-25-000008", "0000320193-25-000057", "0000320193-25-000073")
PRE_2001 = "0000320193-94-000016"

# Roles whose bytes are committed. The XBRL package, the SEC-extracted instance and the schema are
# pinned by the manifest but deliberately NOT committed: they are large machine evidence and live
# in the gitignored object store.
COMMITTED_ROLES = frozenset({"primary_document", "complete_submission"})


def _yaml(path: Path) -> dict:
    return YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _yaml(FIXTURES / "manifest.yaml")


def _committed_path(filing: dict, obj: dict) -> Path:
    """Where a manifest object's bytes live on disk, by SEC's own filename."""
    return FIXTURES / filing["accession"] / obj["url"].rsplit("/", 1)[-1]


# --- manifest integrity ----------------------------------------------------------------------


def test_manifest_covers_every_fixture_filing(manifest: dict) -> None:
    """Every accession directory on disk is described by the manifest, and vice versa.

    Derived from the fixture tree rather than compared against a hardcoded set, so it also catches
    a fixture committed WITHOUT a manifest entry.
    """
    accessions = {f["accession"] for f in manifest["filings"]}
    on_disk = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
    assert accessions == on_disk, "manifest and fixture tree disagree"
    assert {TEN_K, *TEN_QS, PRE_2001} <= accessions, "the five source fixtures must remain"


def test_manifest_pins_a_source_url_and_hash_for_every_object(manifest: dict) -> None:
    """A fixture without a pinned source cannot be proven faithful to a filed document."""
    for filing in manifest["filings"]:
        assert filing["objects"], f"{filing['accession']} has no objects"
        for obj in filing["objects"]:
            assert obj["url"].startswith("https://www.sec.gov/Archives/")
            assert re.fullmatch(r"[0-9a-f]{64}", obj["sha256"]), obj["role"]
            assert obj["size_bytes"] > 0


def test_every_committed_source_object_matches_its_recorded_hash(manifest: dict) -> None:
    """SOURCE-PRESERVATION: the committed bytes are the bytes SEC served.

    Covers the four inline-XBRL primary documents and the 1994 complete submission. The count is
    asserted so a fixture cannot quietly stop being verified by being renamed out of the check.
    """
    from packages.storage import sha256_bytes

    checked = 0
    for filing in manifest["filings"]:
        for obj in filing["objects"]:
            if obj["role"] not in COMMITTED_ROLES:
                continue
            path = _committed_path(filing, obj)
            assert path.exists(), f"{filing['accession']}: {obj['role']} is pinned but absent"
            raw = path.read_bytes()
            assert sha256_bytes(raw) == obj["sha256"], f"{path.name} does not match the manifest"
            assert len(raw) == obj["size_bytes"], f"{path.name} byte count differs"
            checked += 1
    assert checked == 5, f"expected 5 committed source objects, verified {checked}"


def test_committed_filing_summary_matches_its_recorded_hash(manifest: dict) -> None:
    """The renderer artifact is the same bytes the manifest recorded.

    A `FilingSummary.xml` exists only from the XBRL era onward. A pre-2001 submission has none, so
    the manifest records no hash for one — and the ABSENCE of a declaration is itself asserted
    against the tree, so a filing cannot quietly lose its recorded hash and pass.
    """
    from packages.storage import sha256_bytes

    checked = 0
    for filing in manifest["filings"]:
        path = FIXTURES / filing["accession"] / "filing-summary.xml"
        recorded = filing.get("filing_summary_sha256")
        if recorded is None:
            assert not path.exists(), (
                f"{filing['accession']} has a filing-summary.xml on disk but records no hash"
            )
            continue
        assert sha256_bytes(path.read_bytes()) == recorded
        checked += 1
    assert checked == 4, "the four inline-XBRL fixtures must each still be hash-checked"


def test_no_derived_parser_output_remains_in_the_fixture_tree() -> None:
    """The deterministic parser's outputs were deleted; only original SEC source is committed.

    `report-inventory.yaml` was a re-encoding of the renderer's report list and the documented
    input to canonicalization stage 1. `table-ownership.json` was the table-to-footnote ownership
    census. Both are backend decisions about what a filing means, and neither may return.
    """
    derived = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in FIXTURES.rglob("*")
        if p.is_file() and p.name in {"report-inventory.yaml", "table-ownership.json"}
    )
    assert not derived, f"derived parser output committed as a fixture: {derived}"


def test_fixture_tree_stays_small() -> None:
    """The strategy is a small pinned source set, not a filing archive.

    Blowing past the ceiling means someone committed an XBRL package or an extracted instance,
    which belongs in object storage instead.
    """
    total = sum(p.stat().st_size for p in FIXTURES.rglob("*") if p.is_file())
    assert total < 25 * 1024 * 1024, f"fixture tree is {total:,} bytes"


def test_fixtures_need_no_network() -> None:
    """Every fixture is a local file. A test that reaches SEC is not deterministic."""
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            assert path.read_bytes(), f"{path} is empty"


def test_the_pre_2001_submission_declares_why_it_has_no_primary_document(manifest: dict) -> None:
    """HISTORICAL-FORMAT: an entire era exposes no individually addressable documents.

    EDGAR does not serve the filed components of a pre-2001 submission as separate objects. The
    complete submission text file IS the artifact, and every exhibit lives inside it. A pipeline
    whose input contract assumes a per-document URL is blind to 125 filings of the research corpus.
    """
    filing = next(f for f in manifest["filings"] if f["accession"] == PRE_2001)
    roles = {o["role"] for o in filing["objects"]}
    assert roles == {"complete_submission"}, f"unexpected roles for a pre-2001 filing: {roles}"
    assert "filing_summary_sha256" not in filing
