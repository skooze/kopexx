"""The SUPPLIED benchmark-filing contract, and the composite that reaches it.

WHY THIS FILE EXISTS. The fixed completeness benchmark — Apple's 10-Q `0000320193-25-000008` — is a
preserved Sprint 3 fixture and is NOT one of the 613 filings the Phase 0 sampling run drew. The
review surface resolves a filing's IDENTITY through the catalog, so before the benchmark contract
existed every benchmark route answered 404 for the one filing the whole phase is about. That was
found by opening the page, not by an assertion, which is why there is an assertion now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.orchestrator import (
    BenchmarkFilingCatalog,
    CompositeFilingCatalog,
    CorpusFilingCatalog,
)

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "benchmark" / "benchmark-filings.yaml"


@pytest.fixture
def benchmark() -> BenchmarkFilingCatalog:
    return BenchmarkFilingCatalog.from_manifest(CONTRACT)


def test_the_tracked_contract_loads_and_holds_the_fixed_benchmark_filing(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    """The contract is tracked source, so this passes on a fresh checkout with no var/ at all."""
    filing = benchmark.filing("0000320193", "0000320193-25-000008")
    assert filing is not None
    assert filing.form_as_filed == "10-Q"
    assert filing.filing_date == "2025-01-31"
    # THE PERIOD IS NOT THE FILING DATE. Getting these two the wrong way round is a
    # financial-accuracy defect rather than a cosmetic one, so it is asserted apart.
    assert filing.report_period == "2024-12-28"
    assert filing.issuer_label == "Apple Inc."
    assert filing.transport_era == "inline_xbrl"
    assert filing.is_annual is False
    assert filing.is_amendment is False


def test_identity_is_normalised_so_either_accession_form_resolves(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    """`sec_identity` owns both normalisations and this catalog must not reimplement either."""
    dashed = benchmark.filing("0000320193", "0000320193-25-000008")
    undashed = benchmark.filing("320193", "000032019325000008")
    assert dashed is not None
    assert undashed is not None
    assert dashed.accession == undashed.accession == "0000320193-25-000008"
    assert dashed.cik == undashed.cik == "0000320193"


def test_an_unknown_filing_returns_none_rather_than_a_substitute(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    """No fallback, no nearest match. rules.md section 21 rule 9."""
    assert benchmark.filing("0000320193", "0000320193-99-999999") is None
    assert benchmark.filing("0000000001", "0000000001-25-000001") is None


def test_a_benchmark_filing_is_opened_by_identity_and_never_found_by_browsing(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    """Search is deliberately empty: a benchmark is chosen, not discovered."""
    assert benchmark.search_entities("Apple") == []
    assert benchmark.entity("0000320193") is None


def test_a_contract_declaring_no_filings_is_refused(tmp_path: Path) -> None:
    """An empty contract is a configuration error, never a catalog that quietly holds nothing."""
    empty = tmp_path / "empty.yaml"
    empty.write_text('schema_version: "benchmark-filings-v1"\nfilings: []\n', encoding="utf-8")
    with pytest.raises(ValueError, match="declares no benchmark filings"):
        BenchmarkFilingCatalog.from_manifest(empty)


def test_the_corpus_answers_first_and_the_benchmark_answers_only_for_what_it_lacks(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    """Order is the caller's choice and it decides which record a shared filing keeps.

    A filing genuinely in the sampled corpus keeps the RICHER record that run measured — package
    counts, image counts, the primary document's estimated size. The benchmark contract carries
    identity only, so letting it answer first would silently zero three measured fields.
    """
    corpus = CorpusFilingCatalog(
        [
            {
                "cik": "0000320193",
                "accession": "0000320193-25-000008",
                "form_as_filed": "10-Q",
                "filing_date": "2025-01-31",
                "report_period": "2024-12-28",
                "issuer_label": "Apple Inc.",
                "transport_era": "inline_xbrl",
                "is_amendment": False,
                "is_annual": False,
                "form_variant": "standard",
                "package_file_count": 63,
                "package_image_count": 2,
                "primary_est_tokens_at_3_0": 244196,
                "files": [],
            }
        ]
    )
    composite = CompositeFilingCatalog(corpus, benchmark)
    found = composite.filing("0000320193", "0000320193-25-000008")
    assert found is not None
    # The corpus record won, and its measured fields survived.
    assert found.package_file_count == 63
    assert found.primary_estimated_tokens == 244196

    # MUTATION PROOF: with the corpus EMPTY the benchmark answers, and its identity-only record
    # carries zeroes rather than a fabricated package count.
    fallback = CompositeFilingCatalog(CorpusFilingCatalog([]), benchmark)
    only = fallback.filing("0000320193", "0000320193-25-000008")
    assert only is not None
    assert only.package_file_count == 0
    assert only.form_as_filed == "10-Q"


def test_the_composite_never_invents_a_filing_neither_catalog_holds(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    composite = CompositeFilingCatalog(CorpusFilingCatalog([]), benchmark)
    assert composite.filing("0000000009", "0000000009-25-000001") is None
    assert composite.entity("0000000009") is None
    assert composite.filings("0000000009") == []


def test_the_composite_deduplicates_a_filing_both_catalogs_hold(
    benchmark: BenchmarkFilingCatalog,
) -> None:
    """One filing, one row. A duplicate would double a benchmark's denominator in every listing."""
    composite = CompositeFilingCatalog(benchmark, benchmark)
    rows = composite.filings("0000320193")
    assert len(rows) == 1


def test_no_accession_or_form_literal_leaks_into_runtime_source() -> None:
    """The contract is SUPPLIED, exactly as the capability snapshot and the form family are.

    A guessed allowlist in runtime source produced a confident, precise and inverted conclusion
    once already — ADR-0017 section 8 — and this asserts the same mistake was not repeated for a
    benchmark identity.
    """
    source = (
        Path(__file__).resolve().parents[2] / "packages" / "orchestrator" / "catalog.py"
    ).read_text(encoding="utf-8")
    assert "0000320193-25-000008" not in source
    assert "aapl" not in source.lower()
