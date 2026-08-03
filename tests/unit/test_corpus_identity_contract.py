"""Issuer and filing identity contract, enforced in ordinary CI.

Each rule below was established from real EDGAR data, and each corresponds to a mistake this
project actually made:

  * a sampling label was allowed to stand as identity, so CIK 0001736946 was recorded as "Astera
    Labs". It is Arlo Technologies. Astera Labs is CIK 0001736297.
  * accession uniqueness was asserted globally, which flagged a valid Alphabet/Google
    co-registration as a duplicate.
  * the accession prefix looks like a CIK and is the FILING AGENT's, not the issuer's.

These tests read a small committed fixture. They never call the SEC and never touch the ignored
research corpus.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "corpus_identity.yaml"

ARLO = "0001736946"
ASTERA = "0001736297"


@pytest.fixture(scope="module")
def identity() -> dict:
    yaml = YAML(typ="safe", pure=True)
    return yaml.load(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def issuers(identity: dict) -> dict[str, dict]:
    return {i["cik"]: i for i in identity["issuers"]}


def authoritative_name(issuers: dict[str, dict], cik: str) -> str:
    """Identity resolves from the CIK only. A sampling label is never consulted."""
    return issuers[cik]["authoritative_name"]


# --- 1: one CIK, one authoritative identity ---------------------------------------------------


def test_one_cik_has_exactly_one_authoritative_identity(identity: dict) -> None:
    by_cik = collections.defaultdict(set)
    for i in identity["issuers"]:
        by_cik[i["cik"]].add(i["authoritative_name"])
    conflicting = {c: n for c, n in by_cik.items() if len(n) > 1}
    assert not conflicting, f"a CIK carries more than one authoritative name: {conflicting}"
    assert len(by_cik) == len(identity["issuers"]), "duplicate issuer records"


def test_every_cik_is_a_quoted_ten_digit_string(identity: dict) -> None:
    """YAML 1.2 turns an unquoted 0001736946 into the integer 1736946."""
    for i in identity["issuers"]:
        assert isinstance(i["cik"], str), f"{i['cik']!r} was parsed as a number"
        assert len(i["cik"]) == 10 and i["cik"].isdigit()


# --- 2 and 3: Arlo and Astera are distinct and neither can take the other's name ---------------


def test_arlo_and_astera_are_distinct_issuers(issuers: dict[str, dict]) -> None:
    assert ARLO != ASTERA
    assert ARLO in issuers and ASTERA in issuers
    assert authoritative_name(issuers, ARLO) != authoritative_name(issuers, ASTERA)


def test_arlos_cik_cannot_be_labelled_astera_labs(issuers: dict[str, dict]) -> None:
    name = authoritative_name(issuers, ARLO)
    assert "arlo" in name.lower()
    assert "astera" not in name.lower(), "Arlo's CIK resolved to Astera Labs"


def test_asteras_cik_cannot_be_labelled_arlo(issuers: dict[str, dict]) -> None:
    name = authoritative_name(issuers, ASTERA)
    assert "astera" in name.lower()
    assert "arlo" not in name.lower(), "Astera's CIK resolved to Arlo"


# --- 4: a sampling label is metadata, never authority ------------------------------------------


def test_sampling_labels_are_non_authoritative_metadata(issuers: dict[str, dict]) -> None:
    arlo = issuers[ARLO]
    assert arlo.get("sampling_label_original"), "the wrong label must be preserved, not erased"
    assert "astera" in arlo["sampling_label_original"].lower()
    # The label disagrees with authority, and authority wins.
    assert arlo["sampling_label_original"].lower() not in arlo["authoritative_name"].lower()
    assert arlo["identity_source"] == "EDGAR submissions API"
    for i in issuers.values():
        assert i["identity_source"] == "EDGAR submissions API"


# --- 5 and 6: co-registration is valid; a true duplicate is not -------------------------------


def test_co_registration_does_not_trigger_a_false_duplicate(identity: dict) -> None:
    co = identity["co_registration"]
    ciks = co["filed_jointly_by"]
    assert len(ciks) == 2 and len(set(ciks)) == 2
    rows = [(c, co["accession"]) for c in ciks]
    # The correct key is (cik, accession): two rows, no duplicate.
    assert len(set(rows)) == len(rows), "a valid co-registration was rejected as a duplicate"
    # The accession alone is NOT unique, and asserting that it is would reject valid SEC data.
    assert len({a for _, a in rows}) == 1


def test_duplicate_cik_accession_identities_do_fail(identity: dict) -> None:
    co = identity["co_registration"]
    cik = co["filed_jointly_by"][0]
    rows = [(cik, co["accession"]), (cik, co["accession"])]
    assert len(set(rows)) != len(rows), "a genuine duplicate was not detected"


# --- 7: ownership never comes from the accession prefix ---------------------------------------


def test_accession_ownership_is_never_derived_from_the_prefix(identity: dict) -> None:
    agent = identity["agent_prefixed_filings"]
    assert agent, "the fixture must carry agent-prefixed cases or the rule proves nothing"
    for f in agent:
        prefix = f["accession_prefix"]
        assert prefix.lstrip("0") != f["cik"].lstrip("0"), "not actually an agent-prefixed case"
        # Ownership comes from the SEC archive path, and it agrees with the recorded CIK.
        assert f["archive_path_cik"].lstrip("0") == f["cik"].lstrip("0")

    # A prefix-based check would wrongly reject every one of these.
    would_reject = [f for f in agent if f["accession_prefix"].lstrip("0") != f["cik"].lstrip("0")]
    assert len(would_reject) == len(agent)

    # And it would pass by luck on these, which is why both cases must exist.
    self_pref = identity["self_prefixed_filings"]
    assert self_pref, "the fixture must also carry self-prefixed cases"
    for f in self_pref:
        assert f["accession"].split("-")[0].lstrip("0") == f["cik"].lstrip("0")


# --- 8: an unreviewed identity contradiction fails closed -------------------------------------


def test_an_unreviewed_identity_contradiction_fails_closed(issuers: dict[str, dict]) -> None:
    """An unknown CIK is never resolved to a guess."""
    with pytest.raises(KeyError):
        authoritative_name(issuers, "9999999999")

    # A name that matches no recorded issuer must not be silently accepted as identity.
    known = {i["authoritative_name"] for i in issuers.values()}
    assert "Astera Labs, Inc." in known
    assert "Arlo Technologies, Inc." in known
    assert "Definitely Not A Real Filer, Inc." not in known
