"""Corpus-integrity rules, proven hermetically.

These encode identity lessons that were learned by getting them WRONG against real SEC data. They
use synthetic fixtures on purpose, so they run in every environment and do not depend on the
research corpus, which lives under var/ and is not committed.

Each rule cites the real filing that taught it.
"""

from __future__ import annotations

import re

import pytest

# The SEC archive path carries the ISSUER's CIK. The accession prefix carries the FILING AGENT's.
ARCHIVE_CIK = re.compile(r"/Archives/edgar/data/(\d+)/")


def owner_cik_from_url(url: str) -> str | None:
    """Return the issuer CIK from an SEC archive URL, or None when the URL is not one."""
    match = ARCHIVE_CIK.search(url)
    return match.group(1) if match else None


def accession_prefix(accession: str) -> str:
    """Return the accession's leading ten digits. This is the FILING AGENT, never the issuer."""
    return accession.split("-")[0]


def corpus_key(cik: str, accession: str) -> tuple[str, str]:
    """The uniqueness key for a corpus filing record."""
    return (cik, accession)


class TestAccessionPrefixIsNotIdentity:
    """SEC-INVARIANT: the accession prefix belongs to whoever transmitted the filing.

    Measured on the research corpus: 361 of 613 filings carry an accession prefix that differs
    from the issuer CIK. Treating the prefix as identity would have produced 361 false mismatches.
    """

    def test_archive_path_yields_the_issuer_not_the_agent(self) -> None:
        # Apple's FY2025 10-K, transmitted under Apple's own filer id.
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
        assert owner_cik_from_url(url) == "320193"

    def test_a_filing_agent_prefix_does_not_match_the_issuer(self) -> None:
        # Apple's 2026 proxy was transmitted by a filing agent, CIK 1308179, not by Apple.
        accession = "0001308179-26-000008"
        url = f"https://www.sec.gov/Archives/edgar/data/320193/{accession.replace('-', '')}/x.htm"
        assert accession_prefix(accession) == "0001308179"
        assert owner_cik_from_url(url) == "320193"
        assert accession_prefix(accession).lstrip("0") != owner_cik_from_url(url)

    def test_ownership_is_verified_from_the_path_not_the_prefix(self) -> None:
        recorded_issuer = "0000320193"
        accession = "0001308179-26-000008"
        url = f"https://www.sec.gov/Archives/edgar/data/320193/{accession.replace('-', '')}/x.htm"
        # The correct check passes.
        assert owner_cik_from_url(url) == recorded_issuer.lstrip("0")
        # The naive check would have raised a false mismatch.
        assert accession_prefix(accession) != recorded_issuer

    def test_a_non_archive_url_yields_no_owner_rather_than_a_guess(self) -> None:
        assert owner_cik_from_url("https://data.sec.gov/submissions/CIK0000320193.json") is None


class TestCoRegistrationIsValid:
    """One accession may legitimately belong to more than one CIK.

    Measured: 10-K/A 0001193125-16-520367 was co-registered by Alphabet Inc. (0001652044) and
    GOOGLE INC. (0001288776) with byte-identical content. A uniqueness rule keyed on the accession
    alone would reject valid SEC data.
    """

    ACCESSION = "0001193125-16-520367"
    ALPHABET = "0001652044"
    GOOGLE = "0001288776"

    def test_the_same_accession_under_two_ciks_is_not_a_duplicate(self) -> None:
        records = [
            corpus_key(self.ALPHABET, self.ACCESSION),
            corpus_key(self.GOOGLE, self.ACCESSION),
        ]
        assert len(set(records)) == 2, "co-registration must survive de-duplication"

    def test_the_same_accession_under_one_cik_twice_is_a_duplicate(self) -> None:
        records = [
            corpus_key(self.ALPHABET, self.ACCESSION),
            corpus_key(self.ALPHABET, self.ACCESSION),
        ]
        assert len(set(records)) == 1, "a true duplicate must collapse"

    def test_keying_on_accession_alone_would_reject_valid_sec_data(self) -> None:
        by_accession = {self.ACCESSION}
        assert len(by_accession) == 1
        by_correct_key = {
            corpus_key(self.ALPHABET, self.ACCESSION),
            corpus_key(self.GOOGLE, self.ACCESSION),
        }
        assert len(by_correct_key) == 2

    def test_identical_bytes_across_co_registrants_are_expected(self) -> None:
        digest = "f74262703ff479537d2107188b06f0bb" + "0" * 32
        seen = {digest: [self.ALPHABET, self.GOOGLE]}
        reused = {h: v for h, v in seen.items() if len(v) > 1}
        assert reused, "a co-registered filing shares its bytes; this is not corruption"


class TestSamplingLabelNeverOverridesIdentity:
    """A hand-written sampling label is an INTENT. EDGAR is the AUTHORITY.

    Measured: CIK 0001736946 was sampled as "Astera Labs" and is Arlo Technologies, Inc. The
    sampling intent additionally called it young; its first qualifying filing is 2018-08-27.
    """

    CIK = "0001736946"
    AUTHORITATIVE = "Arlo Technologies, Inc."
    SAMPLING_LABEL = "Astera Labs"

    @staticmethod
    def resolve_identity(record: dict[str, str]) -> str:
        """Authoritative name wins. A caller cannot substitute the sampling label."""
        return record["name_current"]

    def test_authoritative_name_wins_over_the_sampling_label(self) -> None:
        record = {
            "cik": self.CIK,
            "name_current": self.AUTHORITATIVE,
            "sampling_label_original": self.SAMPLING_LABEL,
        }
        assert self.resolve_identity(record) == self.AUTHORITATIVE

    def test_the_sampling_intent_is_preserved_not_erased(self) -> None:
        record = {
            "cik": self.CIK,
            "name_current": self.AUTHORITATIVE,
            "sampling_label_original": self.SAMPLING_LABEL,
        }
        assert record["sampling_label_original"] == self.SAMPLING_LABEL, (
            "a wrong intent is evidence about the sampling process and must stay visible"
        )

    def test_one_cik_may_not_carry_two_authoritative_names(self) -> None:
        records = [
            {"cik": self.CIK, "name_current": self.AUTHORITATIVE},
            {"cik": self.CIK, "name_current": "Astera Labs, Inc."},
        ]
        by_cik: dict[str, set[str]] = {}
        for r in records:
            by_cik.setdefault(r["cik"], set()).add(r["name_current"])
        conflicting = {c: n for c, n in by_cik.items() if len(n) > 1}
        assert conflicting, "two authoritative names for one CIK must be detected, not merged"

    def test_maturity_is_derived_from_filing_history_not_from_intent(self) -> None:
        record = {"category_intent": "young", "earliest_qualifying": "2018-08-27"}
        derived_young = record["earliest_qualifying"] >= "2020-01-01"
        assert derived_young is False
        assert (record["category_intent"] == "young") != derived_young, (
            "intent and authority disagree here, and the disagreement must be detectable"
        )


class TestFormStringsAreNeverNormalized:
    """Filed form strings are recorded exactly as filed.

    A discovery scan that searched for the hyphenated `10-KSB` could not match EDGAR's actual
    submission type, and produced a false 'this family is absent' conclusion. Exact strings only.
    """

    @pytest.mark.parametrize(
        "filed,normalized",
        [("10KSB", "10-KSB"), ("10QSB", "10-QSB"), ("10KSB40", "10-KSB40")],
    )
    def test_a_normalized_form_does_not_match_the_filed_form(
        self, filed: str, normalized: str
    ) -> None:
        assert filed != normalized
        assert filed not in {normalized}, "normalizing during discovery loses the family"

    def test_historical_forms_are_not_relabelled_as_modern_ones(self) -> None:
        for filed in ("10-K405", "10KSB", "10-KT"):
            assert filed != "10-K", "a historical form must never be displayed as a modern 10-K"

    def test_prefix_matching_alone_would_admit_non_report_forms(self) -> None:
        not_reports = ("10-12B", "10-12G", "10-D", "NT 10-K", "10SB12G")
        for form in not_reports:
            assert form.startswith("10") or form.startswith("NT 10")
        # Membership must come from an adjudicated set, never from the prefix.
        adjudicated_direct_reports = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10KSB", "10QSB"}
        for form in not_reports:
            assert form not in adjudicated_direct_reports
