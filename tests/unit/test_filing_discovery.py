"""Filing discovery tests.

Uses httpx MockTransport so the overflow-shard path, form filtering, and era classification are
exercised without touching the network.

THE QUALIFYING FORM SET COMES FROM THE REVIEWED CONTRACT, NOT FROM THIS FILE. `QUALIFYING` below is
read out of `tests/fixtures/form_family.yaml`, the adjudicated inventory of every 10-family string
observed across 135 EDGAR quarterly master indexes. Hardcoding a list here would let the code and
the contract drift apart silently, which is the exact failure this suite now exists to prevent:
discovery shipped `("10-K", "10-K405", "10-KSB")` and `("10-Q", "10-QSB")` for four sprints while
the committed contract said EDGAR's real strings are unhyphenated.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from ruamel.yaml import YAML

from packages.filing_discovery import (
    DiscoveredFiling,
    ReconciliationError,
    SubmissionsShapeError,
    classify_era,
    discover_filings,
    issuer_profile,
    parse_master_index,
    quarters_between,
    raise_if_incomplete,
)
from packages.sec_client import FakeClock, SecHttpClient, SecRateLimiters

UA = "Kopexx Research contact@example.com"

FORM_FAMILY = Path(__file__).resolve().parents[1] / "fixtures" / "form_family.yaml"
QUALIFYING = frozenset(
    entry["form"]
    for entry in YAML(typ="safe", pure=True).load(FORM_FAMILY.read_text(encoding="utf-8"))["forms"]
    if entry["included"]
)


def _client(handler) -> SecHttpClient:
    return SecHttpClient(
        UA,
        limiters=SecRateLimiters(global_rps=1000.0, efts_rps=1000.0, clock=FakeClock()),
        transport=httpx.MockTransport(handler),
        sleeper=lambda seconds: None,
    )


def _block(rows: list[dict]) -> dict:
    """Build a parallel-array block the way SEC returns one."""
    keys = [
        "accessionNumber",
        "filingDate",
        "reportDate",
        "form",
        "primaryDocument",
        "isXBRL",
        "isInlineXBRL",
        "size",
    ]
    return {key: [row.get(key, "") for row in rows] for key in keys}


def _row(accession: str, form: str, filed: str, **extra) -> dict:
    return {
        "accessionNumber": accession,
        "filingDate": filed,
        "reportDate": extra.get("reportDate", filed),
        "form": form,
        "primaryDocument": extra.get("primaryDocument", "doc.htm"),
        "isXBRL": extra.get("isXBRL", 1),
        "isInlineXBRL": extra.get("isInlineXBRL", 1),
        "size": extra.get("size", 1000),
    }


# --- form coverage -------------------------------------------------------------------------


def test_the_qualifying_set_is_the_reviewed_contract() -> None:
    """Anti-vacuity. Every filtering test below is meaningless if this set is wrong or empty."""
    assert len(QUALIFYING) == 22, (
        f"the reviewed contract holds 22 included forms, got {len(QUALIFYING)}"
    )


@pytest.mark.parametrize(
    "form",
    # The unhyphenated small-business and transition strings a guessed allowlist cannot match.
    # `10QSB` alone is 120,120 filings by 9,771 issuers — the fourth most common form in the
    # entire 10-family — and the withdrawn filter matched none of them.
    [
        "10-K",
        "10-Q",
        "10-K/A",
        "10-Q/A",
        "10-K405",
        "10-K405/A",
        "10KSB",
        "10QSB",
        "10KSB40",
        "10KSB40/A",
        "10-KT",
        "10-QT",
        "10KT405",
        "10KT405/A",
    ],
)
def test_the_contract_covers_the_strings_edgar_actually_files(form: str) -> None:
    """HISTORICAL-FORMAT: EDGAR's submission types are exact strings, not a normalizable family."""
    assert form in QUALIFYING


@pytest.mark.parametrize(
    "form",
    [
        "8-K",
        "4",
        "424B2",
        "DEF 14A",
        "S-1",
        "SC 13G/A",
        "20-F",
        "11-K",
        "10-KSB405",
        "10KSB405",
        "NT 10-K",
        "10-D",
    ],
)
def test_non_family_and_guessed_variants_are_excluded(form: str) -> None:
    """A form nobody reviewed fails the gate rather than being admitted by a prefix rule."""
    assert form not in QUALIFYING


def test_discovery_refuses_an_empty_qualifying_set() -> None:
    """Discovering nothing and reporting success is the failure mode this replaced."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"filings": {"recent": _block([]), "files": []}})

    with _client(handler) as client, pytest.raises(SubmissionsShapeError, match="empty"):
        discover_filings(client, "0000320193", qualifying_forms=frozenset())


# --- era classification ---------------------------------------------------------------------


def test_era_classification_covers_every_acquisition_strategy() -> None:
    assert (
        classify_era(filing_date=date(2025, 10, 31), is_xbrl=True, is_inline_xbrl=True)
        == "inline_xbrl"
    )
    assert (
        classify_era(filing_date=date(2013, 1, 1), is_xbrl=True, is_inline_xbrl=False)
        == "standalone_xbrl"
    )
    assert (
        classify_era(filing_date=date(2005, 1, 1), is_xbrl=False, is_inline_xbrl=False)
        == "html_no_xbrl"
    )
    assert (
        classify_era(filing_date=date(1994, 1, 26), is_xbrl=False, is_inline_xbrl=False)
        == "pem_armored"
    )


# --- discovery -----------------------------------------------------------------------------


def test_discovery_reads_the_overflow_shard() -> None:
    """SEC-INVARIANT: filings.recent caps at 1,000 entries.

    Apple hits that cap exactly and keeps 1,238 further filings in an overflow shard. Reading
    only `recent` returned 45 of Apple's 134 covered filings when this was measured live, so the
    truncation is not a corner case.
    """
    recent = _block([_row("0000320193-25-000079", "10-K", "2025-10-31")])
    shard = _block([_row("0000320193-94-000002", "10-Q", "1994-01-26", isXBRL=0, isInlineXBRL=0)])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("CIK0000320193.json"):
            return httpx.Response(
                200,
                json={
                    "name": "Apple Inc.",
                    "filings": {"recent": recent, "files": [{"name": "shard-001.json"}]},
                },
            )
        return httpx.Response(200, json=shard)

    with _client(handler) as client:
        filings = discover_filings(client, "0000320193", qualifying_forms=QUALIFYING)

    assert len(filings) == 2, "the overflow shard was not read"
    assert {f.accession for f in filings} == {
        "0000320193-25-000079",
        "0000320193-94-000002",
    }
    assert filings[0].filing_date > filings[1].filing_date, "newest first"


def test_discovery_filters_to_qualifying_forms_only() -> None:
    recent = _block(
        [
            _row("0000320193-25-000079", "10-K", "2025-10-31"),
            _row("0000320193-25-000060", "8-K", "2025-08-01"),
            _row("0000320193-25-000061", "4", "2025-08-02"),
            _row("0000320193-25-000073", "10-Q", "2025-08-01"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"filings": {"recent": recent, "files": []}})

    with _client(handler) as client:
        filings = discover_filings(client, 320193, qualifying_forms=QUALIFYING)

    assert {f.form for f in filings} == {"10-K", "10-Q"}


def test_discovery_deduplicates_across_a_shard_boundary() -> None:
    """A shard boundary can repeat an entry; a duplicate would inflate the filing count."""
    row = _row("0000320193-15-000068", "10-Q", "2015-04-28")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("CIK0000320193.json"):
            return httpx.Response(
                200,
                json={"filings": {"recent": _block([row]), "files": [{"name": "shard-001.json"}]}},
            )
        return httpx.Response(200, json=_block([row]))

    with _client(handler) as client:
        filings = discover_filings(client, "320193", qualifying_forms=QUALIFYING)

    assert len(filings) == 1


def test_pre_2001_empty_primary_document_is_preserved() -> None:
    """SEC-INVARIANT: pre-2001 filings have no primary document name.

    Building a URL from the empty string returns HTTP 200 with a directory listing, which is a
    silent corruption. The empty value is kept so the acquirer routes on it instead of guessing.
    """
    recent = _block(
        [
            _row(
                "0000320193-94-000002",
                "10-Q",
                "1994-01-26",
                primaryDocument="",
                isXBRL=0,
                isInlineXBRL=0,
            )
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"filings": {"recent": recent, "files": []}})

    with _client(handler) as client:
        filings = discover_filings(client, "0000320193", qualifying_forms=QUALIFYING)

    assert filings[0].primary_document == ""
    assert filings[0].era == "pem_armored"


def test_malformed_submissions_payload_raises_rather_than_returning_less() -> None:
    """A shape change absorbed quietly looks identical to an issuer that filed nothing."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "Apple Inc."})

    with _client(handler) as client, pytest.raises(SubmissionsShapeError):
        discover_filings(client, "0000320193", qualifying_forms=QUALIFYING)


def test_submissions_block_missing_required_keys_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"filings": {"recent": {"accessionNumber": ["x"]}, "files": []}}
        )

    with _client(handler) as client, pytest.raises(SubmissionsShapeError):
        discover_filings(client, "0000320193", qualifying_forms=QUALIFYING)


def test_issuer_profile_returns_identity_without_filing_arrays() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "Apple Inc.",
                "sic": "3571",
                "fiscalYearEnd": "0926",
                "tickers": ["AAPL"],
                "exchanges": ["Nasdaq"],
                "formerNames": [{"name": "APPLE COMPUTER INC"}],
                "filings": {"recent": _block([]), "files": []},
            },
        )

    with _client(handler) as client:
        profile = issuer_profile(client, "0000320193")

    assert profile["legal_name"] == "Apple Inc."
    assert profile["fiscal_year_end"] == "0926"
    assert profile["former_names"] == ("APPLE COMPUTER INC",)
    assert "filings" not in profile


# --- master index reconciliation --------------------------------------------------------------


def test_quarters_between_spans_year_boundaries() -> None:
    assert quarters_between(date(2024, 11, 1), date(2025, 2, 1)) == [(2024, 4), (2025, 1)]
    assert len(quarters_between(date(1994, 1, 1), date(2025, 12, 31))) == 128


def test_master_index_parsing_selects_the_issuer_and_qualifying_forms() -> None:
    body = (
        "Description:           Master Index\n"
        "-------------------------------------------\n"
        "320193|Apple Inc.|10-K|2025-10-31|edgar/data/320193/0000320193-25-000079.txt\n"
        "320193|Apple Inc.|8-K|2025-08-01|edgar/data/320193/0000320193-25-000060.txt\n"
        "789019|Microsoft|10-K|2025-07-30|edgar/data/789019/0000950170-25-000000.txt\n"
    )
    found = parse_master_index(
        gzip.compress(body.encode()), "0000320193", qualifying_forms=QUALIFYING
    )
    assert found == {"0000320193-25-000079"}, "only Apple's qualifying forms belong"


def test_master_index_duplicate_rows_do_not_inflate_the_count() -> None:
    """HISTORICAL-FORMAT: some quarters list a row twice."""
    line = "320193|Apple Inc.|10-Q|2025-08-01|edgar/data/320193/0000320193-25-000073.txt\n"
    body = "header\n---\n" + line + line
    assert len(parse_master_index(body.encode(), "0000320193", qualifying_forms=QUALIFYING)) == 1


def test_reconciliation_raises_when_the_index_knows_a_filing_discovery_missed() -> None:
    report = {
        "cik": "0000320193",
        "missing_from_discovery": ("0000320193-94-000002",),
        "absent_from_index": (),
    }
    with pytest.raises(ReconciliationError, match="0000320193-94-000002"):
        raise_if_incomplete(report)


def test_reconciliation_tolerates_filings_absent_from_the_index() -> None:
    """The index omits some amendments; the submissions API is more complete for those."""
    raise_if_incomplete(
        {"cik": "0000320193", "missing_from_discovery": (), "absent_from_index": ("x",)}
    )


def test_discovered_filing_record_is_serialisable() -> None:
    filing = DiscoveredFiling(
        cik="0000320193",
        accession="0000320193-25-000079",
        form="10-K",
        filing_date=date(2025, 10, 31),
        report_date=date(2025, 9, 27),
        primary_document="aapl-20250927.htm",
        is_xbrl=True,
        is_inline_xbrl=True,
        size_bytes=9392337,
        era="inline_xbrl",
        source="recent",
    )
    record = filing.as_record()
    assert json.loads(json.dumps(record))["accession"] == "0000320193-25-000079"
    assert not filing.is_amendment
