"""Source-transport tests: what the filed bytes ARE, never what they mean.

HERMETIC. Every EDGAR envelope below is built inline from the transport tags EDGAR actually writes
— `<SEC-DOCUMENT>`, `<DOCUMENT>`, `<TYPE>`, `<SEQUENCE>`, `<FILENAME>`, `<DESCRIPTION>`, `<TEXT>` —
and every retrieval goes through a fake holding a dict. Nothing reaches SEC, nothing resolves a
credential, nothing opens a socket, and the only files read are the preserved SEC artifacts
committed under `tests/fixtures/filings/`.

WHAT IS ACTUALLY BEING TESTED. Not that a dispatcher returns an enum; that is arithmetic. The
subject is the set of ways a filed source range can vanish while the run still looks healthy:

    an inline-XBRL primary document ruled a machine artifact and dropped
    a member a fetcher declined to retrieve, quietly
    an unrecognised member guessed in either direction instead of failing closed
    a filing that does not fit the selected model sent anyway
    images omitted from a run that goes on claiming a complete parse

The first of those is not hypothetical. `packages/source_transport/dispositions.py` documents it as
a measured defect: the `xlink` namespace on an XHTML root matched the XBRL rule, the primary
document of a modern filing was dispositioned MACHINE_ONLY, and coverage still reconciled because
it reconciled against what was submitted. The real preserved document that triggered it is a
committed fixture and is asserted on directly below.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.filing_acquisition import storage_key
from packages.llm_gateway import estimate_tokens
from packages.sec_identity import cik_padded
from packages.source_transport import (
    COVERED_DISPOSITIONS,
    SUBMITTED_DISPOSITIONS,
    UNVERIFIED_TOKENS_PER_IMAGE,
    CompositeInventory,
    ManifestInventory,
    MemberDisposition,
    ObjectStoreInventory,
    PreservedObject,
    RefusingFetcher,
    SourceIntegrityError,
    SourceMember,
    SourceMemberMissingError,
    SourceSet,
    assemble_source_set,
    assess,
    declared_encoding,
    decode_source,
    disposition_for,
    image_coverage_report,
    image_format,
    load_complete_submission,
    verify,
)
from packages.storage import FilesystemObjectStore, sha256_bytes

ACCESSION = "0000794367-25-000156"
CIK = "0000794367"

# --- byte specimens ---------------------------------------------------------------------------
#
# THE TRAP, SYNTHESISED. An XML declaration, an XHTML root, and both the inline-XBRL and the XLink
# namespaces on that root — the exact shape that used to be dispositioned MACHINE_ONLY.
INLINE_XBRL_PRIMARY = (
    b"<?xml version='1.0' encoding='ASCII'?>\n"
    b'<html xmlns="http://www.w3.org/1999/xhtml" '
    b'xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
    b'xmlns:xlink="http://www.w3.org/1999/xlink" '
    b'xmlns:xbrli="http://www.xbrl.org/2003/instance">\n'
    b"<body>\n"
    b"<div><span>Item 2. Management's Discussion and Analysis</span></div>\n"
    b"<table><tr><td>Total net sales</td><td>94,036</td></tr></table>\n"
    b"</body>\n</html>\n"
)

# A genuine machine artifact: XML root, XBRL and XLink namespaces, and NO html element anywhere.
XBRL_LINKBASE = (
    b"<?xml version='1.0' encoding='UTF-8'?>\n"
    b'<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" '
    b'xmlns:xlink="http://www.w3.org/1999/xlink">\n'
    b'<link:labelLink xlink:type="extended"/>\n'
    b"</link:linkbase>\n"
)

CERTIFICATION_HTML = b"<html><body><p>I, the officer, certify that ...</p></body></html>\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + bytes(range(64))
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(range(64))
GIF_BYTES = b"GIF89a" + bytes(range(64))
ZIP_BYTES = b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + bytes(range(64))
RENDERED_R1 = b"<html><body><table><tr><td>rendered by IDEA</td></tr></table></body></html>\n"

PRE_2001_FIXTURE = Path("0000320193-94-000016") / "0000320193-94-000016.txt"
INLINE_XBRL_FIXTURE = Path("0000320193-25-000073") / "aapl-20250628.htm"
FILING_SUMMARY_FIXTURE = Path("0000320193-25-000073") / "filing-summary.xml"


# --- envelope builders ------------------------------------------------------------------------


def _document(
    *,
    declared_type: str,
    sequence: int,
    text: bytes,
    filename: str = "",
    description: str = "",
) -> bytes:
    """One `<DOCUMENT>` block. `filename` is omitted entirely for the pre-2001 shape."""
    lines = [
        b"<DOCUMENT>",
        b"<TYPE>" + declared_type.encode(),
        b"<SEQUENCE>" + str(sequence).encode(),
    ]
    if filename:
        lines.append(b"<FILENAME>" + filename.encode())
    if description:
        lines.append(b"<DESCRIPTION>" + description.encode())
    lines += [b"<TEXT>", text, b"</TEXT>", b"</DOCUMENT>"]
    return b"\n".join(lines) + b"\n"


def _submission(
    *documents: bytes, accession: str = ACCESSION, declared_count: int | None = None
) -> bytes:
    """An EDGAR complete-submission envelope wrapping the given documents."""
    count = len(documents) if declared_count is None else declared_count
    header = (
        f"<SEC-DOCUMENT>{accession}.txt : 20250801\n"
        f"<SEC-HEADER>{accession}.hdr.sgml : 20250801\n"
        f"ACCESSION NUMBER:\t\t{accession}\n"
        "CONFORMED SUBMISSION TYPE:\t10-Q\n"
        f"PUBLIC DOCUMENT COUNT:\t\t{count}\n"
        "FILED AS OF DATE:\t\t20250801\n"
        "</SEC-HEADER>\n"
    )
    return header.encode() + b"".join(documents)


ADDRESSABLE_MEMBERS: dict[str, bytes] = {
    "issuer-20250630.htm": INLINE_XBRL_PRIMARY,
    "ex31-1.htm": CERTIFICATION_HTML,
    "logo.png": PNG_BYTES,
    "issuer-20250630_lab.xml": XBRL_LINKBASE,
    "R1.htm": RENDERED_R1,
}

ADDRESSABLE_SUBMISSION = _submission(
    _document(
        declared_type="10-Q",
        sequence=1,
        filename="issuer-20250630.htm",
        text=INLINE_XBRL_PRIMARY,
    ),
    _document(declared_type="EX-31.1", sequence=2, filename="ex31-1.htm", text=CERTIFICATION_HTML),
    _document(declared_type="GRAPHIC", sequence=3, filename="logo.png", text=PNG_BYTES),
    _document(
        declared_type="EX-101.LAB",
        sequence=4,
        filename="issuer-20250630_lab.xml",
        text=XBRL_LINKBASE,
    ),
    _document(
        declared_type="XML",
        sequence=5,
        filename="R1.htm",
        description="IDEA: XBRL DOCUMENT",
        text=RENDERED_R1,
    ),
)

NON_ADDRESSABLE_SUBMISSION = _submission(
    _document(
        declared_type="10-K",
        sequence=1,
        text=b"UNITED STATES SECURITIES AND EXCHANGE COMMISSION\nForm 10-K\n",
    ),
    _document(declared_type="EX-11", sequence=2, text=b"Computation of earnings per share\n"),
    _document(declared_type="EX-27", sequence=3, text=b"<ARTICLE> 5\n<PERIOD-TYPE> YEAR\n"),
)


# --- fakes ---------------------------------------------------------------------------------


class _FakeInventory:
    """An inventory over a dict of bytes. No disk, no object store, no network."""

    def __init__(self, held: dict[str, bytes]) -> None:
        self.held = dict(held)
        self.reads: list[str] = []

    def find(self, cik: str, accession: str, filename: str) -> PreservedObject | None:
        data = self.held.get(filename)
        if data is None:
            return None
        return PreservedObject(
            filename=filename,
            sha256=sha256_bytes(data),
            byte_count=len(data),
            source_url=f"https://example.invalid/held/{filename}",
            locator=filename,
            acquired_at="2026-08-03T00:00:00Z",
            acquisition_method="test_inventory",
            reused=True,
        )

    def read(self, obj: PreservedObject) -> bytes:
        self.reads.append(obj.filename)
        return self.held[obj.filename]

    def filenames(self, cik: str, accession: str) -> tuple[str, ...]:
        return tuple(self.held)


class _StaleInventory(_FakeInventory):
    """An inventory whose RECORD no longer describes the bytes on disk."""

    def find(self, cik: str, accession: str, filename: str) -> PreservedObject | None:
        found = super().find(cik, accession, filename)
        if found is None:
            return None
        return PreservedObject(
            filename=found.filename,
            sha256="0" * 64,
            byte_count=found.byte_count,
            source_url=found.source_url,
            locator=found.locator,
            acquired_at=found.acquired_at,
            acquisition_method=found.acquisition_method,
            reused=True,
        )


class _RecordingFetcher:
    """A fetcher that serves from a dict and records exactly which members it was asked for."""

    def __init__(self, available: dict[str, bytes]) -> None:
        self.available = dict(available)
        self.calls: list[str] = []

    def fetch(self, cik: str, accession: str, filename: str) -> tuple[PreservedObject, bytes]:
        self.calls.append(filename)
        data = self.available[filename]
        return (
            PreservedObject(
                filename=filename,
                sha256=sha256_bytes(data),
                byte_count=len(data),
                source_url=f"https://example.invalid/fetched/{filename}",
                locator=filename,
                acquired_at="2026-08-03T00:00:00Z",
                acquisition_method="test_fetch",
                reused=False,
            ),
            data,
        )


def _member(
    *,
    filename: str,
    disposition: MemberDisposition,
    text: str | None = None,
    byte_count: int | None = None,
    sha256: str = "a" * 64,
    sequence: int | None = 1,
    image_kind: str | None = None,
) -> SourceMember:
    return SourceMember(
        sequence=sequence,
        declared_type="10-Q",
        description="",
        filename=filename,
        disposition=disposition,
        disposition_evidence="supplied by the test",
        sha256=sha256,
        byte_count=len(text.encode()) if byte_count is None and text else (byte_count or 100),
        source_url=f"https://example.invalid/{filename}",
        separately_addressable=True,
        reused=False,
        encoding="utf-8" if text is not None else None,
        image_format=image_kind,
        text=text,
    )


def _set(*members: SourceMember, addressable: bool = True) -> SourceSet:
    return SourceSet(
        cik=CIK,
        accession=ACCESSION,
        form_as_filed="10-Q",
        filing_date="2025-08-01",
        report_period="2025-06-30",
        issuer_label="Issuer Inc.",
        transport_era="inline_xbrl",
        members=members,
        declared_document_count=len(members),
        listed_document_count=len(members),
        members_separately_addressable=addressable,
    )


def _assemble(inventory: _FakeInventory, fetcher: object, **overrides: str) -> SourceSet:
    arguments: dict[str, str] = {
        "cik": CIK,
        "accession": ACCESSION,
        "form_as_filed": "10-Q",
        "filing_date": "2025-08-01",
        "issuer_label": "Issuer Inc.",
        "transport_era": "inline_xbrl",
    }
    arguments.update(overrides)
    return assemble_source_set(inventory, fetcher, **arguments)  # type: ignore[arg-type]


# --- anti-vacuity: the specimens really are the traps they claim to be -------------------------


def test_the_inline_xbrl_specimen_actually_carries_the_namespaces_that_used_to_trap_it() -> None:
    """ANTI-VACUITY. The disposition test below is worthless if the trap bytes are absent.

    The defect was that `xmlns:xlink` and the XBRL namespace on an XHTML root matched the XBRL
    rule. If a future edit tidies those namespaces out of the specimen, the regression test would
    keep passing while testing nothing at all, which is exactly how the original defect survived.
    """
    head = INLINE_XBRL_PRIMARY[:4096]
    assert head.lstrip().startswith(b"<?xml"), "the specimen must open with an XML declaration"
    assert b"http://www.w3.org/1999/xlink" in head, "the XLink namespace is the trap"
    assert b"http://www.xbrl.org/2013/inlineXBRL" in head, "the inline-XBRL namespace is the trap"
    assert b"<html" in head and b"<div" in head and b"<table" in head


def test_the_committed_inline_xbrl_fixture_is_the_real_preserved_shape(fixtures_dir: Path) -> None:
    """ANTI-VACUITY. The real-document test must be reading a real inline-XBRL primary document."""
    data = (fixtures_dir / "filings" / INLINE_XBRL_FIXTURE).read_bytes()
    head = data[:4096]
    assert head.lstrip().startswith(b"<?xml")
    assert b"http://www.w3.org/1999/xlink" in head
    assert b"http://www.xbrl.org/2013/inlineXBRL" in head
    assert len(data) > 500_000, "a primary document this small is not the one that was preserved"


# --- dispositions: the inline-XBRL regression --------------------------------------------------


def test_an_inline_xbrl_primary_document_is_parser_input_text_and_not_machine_only() -> None:
    """THE REGRESSION THIS PACKAGE EXISTS FOR. Inline XBRL is XHTML, and XHTML is prose.

    An XML declaration plus XBRL and XLink namespaces on an `<html>` root is what every modern
    primary document looks like. Ruling it MACHINE_ONLY dropped the 10-Q itself from the source
    set while the run still reported reconciled coverage, because coverage was reconciled against
    what had been submitted rather than against what had been filed.
    """
    disposition, evidence = disposition_for(
        filename="issuer-20250630.htm",
        declared_type="10-Q",
        description="",
        data=INLINE_XBRL_PRIMARY,
    )
    assert disposition is MemberDisposition.PARSER_INPUT_TEXT
    assert disposition is not MemberDisposition.MACHINE_ONLY
    assert "HTML" in evidence or "XHTML" in evidence


def test_the_real_preserved_inline_xbrl_primary_document_survives_disposition(
    fixtures_dir: Path,
) -> None:
    """The same rule, against the actual bytes SEC published rather than a specimen.

    A synthetic specimen proves the ordering; the preserved artifact proves the ordering holds for
    the eighteen namespaces a real filer agent emits, in the order it emits them.
    """
    data = (fixtures_dir / "filings" / INLINE_XBRL_FIXTURE).read_bytes()
    disposition, _ = disposition_for(
        filename=INLINE_XBRL_FIXTURE.name, declared_type="10-Q", description="", data=data
    )
    assert disposition is MemberDisposition.PARSER_INPUT_TEXT


def test_a_genuine_xbrl_linkbase_with_no_html_root_is_machine_only() -> None:
    """MUTATION. The inline-XBRL fix must not have disabled the XBRL rule outright.

    The same namespaces, minus the `<html>` root, are a label linkbase: no prose, nothing a
    language model can read. If this returned PARSER_INPUT_TEXT the fix would have been a deletion
    rather than a reordering, and every filing would ship its linkbases as billed input tokens.
    """
    disposition, evidence = disposition_for(
        filename="issuer-20250630_lab.xml",
        declared_type="EX-101.LAB",
        description="",
        data=XBRL_LINKBASE,
    )
    assert disposition is MemberDisposition.MACHINE_ONLY
    assert "no" in evidence.lower() and "HTML" in evidence


# --- dispositions: byte signatures -------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected_format"),
    [(PNG_BYTES, "png"), (JPEG_BYTES, "jpeg"), (GIF_BYTES, "gif")],
)
def test_a_raster_image_is_identified_by_magic_bytes_not_by_its_name(
    data: bytes, expected_format: str
) -> None:
    """A magic number is what the bytes ARE; an extension is what someone called them.

    The filename here is deliberately wrong. A GRAPHIC member misnamed `.txt` must still reach a
    multimodal parser as an image rather than being decoded into mojibake and charged as text.
    """
    disposition, evidence = disposition_for(
        filename="misnamed.txt", declared_type="GRAPHIC", description="", data=data
    )
    assert disposition is MemberDisposition.PARSER_INPUT_IMAGE
    assert image_format(data) == expected_format
    assert expected_format in evidence


def test_a_zip_archive_is_machine_only_by_signature() -> None:
    """No language model reads a central directory. Submitting one spends tokens on nothing."""
    disposition, evidence = disposition_for(
        filename="issuer-20250630-xbrl.zip",
        declared_type="EX-101.INS",
        description="",
        data=ZIP_BYTES,
    )
    assert disposition is MemberDisposition.MACHINE_ONLY
    assert "signature" in evidence


def test_text_is_not_mistaken_for_an_image_or_an_archive() -> None:
    """MUTATION. `image_format` must answer None for the overwhelmingly common case.

    A signature test that matched too eagerly would route filed prose to an image block, where it
    is unreadable, and nothing downstream would notice because the member would still be counted.
    """
    assert image_format(CERTIFICATION_HTML) is None
    assert image_format(INLINE_XBRL_PRIMARY) is None
    assert image_format(b"") is None
    assert (
        disposition_for(
            filename="ex31-1.htm", declared_type="EX-31.1", description="", data=CERTIFICATION_HTML
        )[0]
        is MemberDisposition.PARSER_INPUT_TEXT
    )


@pytest.mark.parametrize("extension", [".zip", ".xlsx", ".xls", ".css", ".js", ".json", ".xsd"])
def test_a_machine_only_extension_is_refused_without_reading_the_bytes(extension: str) -> None:
    """A stylesheet full of readable ASCII is still not prose a parser can use."""
    disposition, evidence = disposition_for(
        filename=f"artifact{extension}",
        declared_type="EX-101.SCH",
        description="",
        data=b"body { font-size: 10pt; }\n",
    )
    assert disposition is MemberDisposition.MACHINE_ONLY
    assert extension in evidence


# --- dispositions: EDGAR's own declared fields --------------------------------------------------


def test_an_idea_description_marks_secs_own_renderer_output() -> None:
    """SEC-INVARIANT: EDGAR labels its Interactive Data renderer artifacts in `<DESCRIPTION>`.

    The evidence is a field EDGAR itself wrote, in the same class as `<TYPE>` — a transport label,
    not a judgement this code formed about what the document contains. That distinction is the
    whole reason the check reads a declared string instead of sniffing for renderer markup.
    """
    disposition, evidence = disposition_for(
        filename="R1.htm", declared_type="XML", description="IDEA: XBRL DOCUMENT", data=RENDERED_R1
    )
    assert disposition is MemberDisposition.SEC_GENERATED_RENDERING
    assert "IDEA: XBRL DOCUMENT" in evidence


def test_the_same_bytes_without_the_idea_marker_are_filer_content() -> None:
    """MUTATION. The renderer rule must key on the DECLARED marker, not on the markup.

    `R1.htm` is ordinary HTML. If the rule matched anything table-shaped it would suppress filed
    documents, which is precisely the class of judgement ADR-0017 deleted a module for making.
    """
    disposition, _ = disposition_for(
        filename="R1.htm", declared_type="XML", description="", data=RENDERED_R1
    )
    assert disposition is MemberDisposition.PARSER_INPUT_TEXT


def test_the_flat_submission_is_a_duplicate_only_when_members_are_addressable() -> None:
    """Sending both the flat submission and its addressable members submits content twice.

    The opposite case is asserted in the same test: with no addressable members the flat artifact
    is the only thing EDGAR publishes and must NOT be marked a duplicate, or a pre-2001 filing
    would have every one of its bytes dropped.
    """
    duplicate, _ = disposition_for(
        filename=f"{ACCESSION}.txt",
        declared_type="",
        description="",
        data=ADDRESSABLE_SUBMISSION,
        is_complete_submission=True,
        members_separately_addressable=True,
    )
    assert duplicate is MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION

    only_artifact, _ = disposition_for(
        filename=f"{ACCESSION}.txt",
        declared_type="",
        description="",
        data=NON_ADDRESSABLE_SUBMISSION,
        is_complete_submission=True,
        members_separately_addressable=False,
    )
    assert only_artifact is not MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION
    assert only_artifact is MemberDisposition.PARSER_INPUT_TEXT


# --- dispositions: failing closed --------------------------------------------------------------


def test_an_unrecognised_extension_carrying_text_fails_closed() -> None:
    """FAILING CLOSED IS THE DESIGN. An unknown role is neither dropped nor guessed.

    Dropping it loses filed content; submitting it may spend a context window on bytes no model
    can use. Neither is a decision code is allowed to make on a hunch, so it goes to the run plan
    and a person decides.
    """
    disposition, evidence = disposition_for(
        filename="exhibit.dat",
        declared_type="EX-99",
        description="",
        data=b"a filed exhibit in some format nobody has catalogued\n",
    )
    assert disposition is MemberDisposition.UNKNOWN_REQUIRES_REVIEW
    assert ".dat" in evidence
    assert "fails closed" in evidence


def test_a_real_preserved_xml_with_no_xbrl_namespace_fails_closed(fixtures_dir: Path) -> None:
    """The fail-closed path, on bytes SEC really published rather than an invented specimen.

    `FilingSummary.xml` is well-formed XML with no XBRL namespace, no HTML root and an extension
    that is on neither the machine list nor the text list. Guessing MACHINE_ONLY from `.xml` would
    have suppressed it; guessing text would have submitted it. It fails closed instead.
    """
    data = (fixtures_dir / "filings" / FILING_SUMMARY_FIXTURE).read_bytes()
    disposition, _ = disposition_for(
        filename=FILING_SUMMARY_FIXTURE.name, declared_type="XML", description="", data=data
    )
    assert disposition is MemberDisposition.UNKNOWN_REQUIRES_REVIEW


def test_binary_bytes_matching_no_known_signature_fail_closed() -> None:
    """A NUL byte in the first block is the discriminator; no filed text document contains one."""
    disposition, evidence = disposition_for(
        filename="opaque.bin", declared_type="EX-99", description="", data=bytes(range(32)) * 8
    )
    assert disposition is MemberDisposition.UNKNOWN_REQUIRES_REVIEW
    assert "not text" in evidence


def test_an_extensionless_text_member_is_parser_input_text() -> None:
    """HISTORICAL-FORMAT: pre-2001 documents have no filename at all, therefore no extension."""
    disposition, _ = disposition_for(
        filename="", declared_type="10-K", description="", data=b"ANNUAL REPORT ON FORM 10-K\n"
    )
    assert disposition is MemberDisposition.PARSER_INPUT_TEXT


def test_the_declared_type_never_changes_the_disposition() -> None:
    """rules.md invariant 14: backend code never decides what a member MEANS.

    `EX-27` is a financial data schedule and the offline corpus tool called it "preserved numeric
    evidence" — a judgement about what it is FOR. Identical bytes must produce identical transport
    answers whatever the filer typed in `<TYPE>`, or this module has an opinion it is not allowed
    to have.
    """
    body = b"<ARTICLE> 5\n<PERIOD-TYPE> YEAR\n<TOTAL-ASSETS> 5303\n"
    answers = {
        disposition_for(filename="filed.txt", declared_type=declared, description="", data=body)[0]
        for declared in ("EX-27", "10-K", "EX-13", "GRAPHIC", "")
    }
    assert answers == {MemberDisposition.PARSER_INPUT_TEXT}


# --- disposition sets ---------------------------------------------------------------------------


def test_submitted_and_covered_are_different_questions() -> None:
    """Request SIZE is measured against one set, CONTENT COVERAGE against the other.

    Collapsing them makes a pre-2001 filing either double-count its own bytes — the envelope plus
    every document inside it — or report its exhibits as uncovered content. Both were observed
    before the two sets were separated.
    """
    assert set(COVERED_DISPOSITIONS) == set(SUBMITTED_DISPOSITIONS) | {
        MemberDisposition.INSIDE_COMPLETE_SUBMISSION,
        MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION,
    }
    for not_sent in (
        MemberDisposition.INSIDE_COMPLETE_SUBMISSION,
        MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION,
    ):
        assert not_sent not in SUBMITTED_DISPOSITIONS, (
            f"{not_sent} content reaches the model without being sent as its own block; counting "
            "it toward request size would double-count the bytes"
        )
    # CORRECTED. DUPLICATE_COMPLETE_SUBMISSION used to be asserted as UNCOVERED, and that was the
    # defect: in addressable mode the flat submission is a byte-for-byte duplicate of members that
    # ARE sent, so its content reaches the model in full. Calling it uncovered made every modern
    # filing report its own complete submission — usually its largest member — as content that did
    # not reach the model, which put complete coverage permanently out of reach for the whole
    # post-2001 era.
    for never in (
        MemberDisposition.MACHINE_ONLY,
        MemberDisposition.SEC_GENERATED_RENDERING,
        MemberDisposition.UNKNOWN_REQUIRES_REVIEW,
    ):
        assert never not in COVERED_DISPOSITIONS, f"{never} must not count as covered content"


# --- decoding -----------------------------------------------------------------------------------


def test_decoding_round_trips_losslessly_and_records_the_codec() -> None:
    """Every decode is re-encoded and compared. A lossy decode is recorded, never shipped.

    The intact-source rule permits transport adaptation only where the complete compatible source
    survives it. Recording the codec is what makes that claim checkable afterwards instead of
    assumed.
    """
    data = "Curaçao — naïve résumé\n".encode()
    decoded = decode_source(data)
    assert decoded.codec == "utf-8"
    assert decoded.lossless
    assert decoded.text.encode("utf-8") == data
    assert decoded.characters == len(decoded.text)


def test_utf8_is_preferred_over_the_latin1_reading_that_would_also_have_succeeded() -> None:
    """MUTATION. latin-1 round-trips every byte sequence, so ordering is the only protection.

    Every one of the 256 byte values maps to a code point under latin-1, so a latin-1-first chain
    would report `lossless=True` on a UTF-8 filing and hand the model mojibake for every non-ASCII
    character in it. This asserts the mojibake reading is exactly what did NOT happen.
    """
    data = "Total: €1,234 — Zürich\n".encode()
    decoded = decode_source(data)
    assert decoded.codec == "utf-8"
    assert "€" in decoded.text and "Zürich" in decoded.text
    assert decoded.text != data.decode("latin-1"), "the latin-1 reading is mojibake"
    assert "Â" not in decoded.text and "Ã" not in decoded.text


def test_bytes_no_earlier_codec_accepts_fall_back_to_latin1_without_losing_one() -> None:
    """HISTORICAL-FORMAT: pre-2005 filings carry bytes that are valid in no declared encoding.

    `0x81` is undefined in cp1252 and illegal in UTF-8. Decoding must still not fail and must not
    drop the byte: a filing that cannot be read is a refusal, but a filing read with a hole in it
    is a false complete.
    """
    data = b"Registrant\x81s address\n"
    decoded = decode_source(data)
    assert decoded.codec == "latin-1"
    assert decoded.lossless
    assert len(decoded.text) == len(data)
    assert decoded.text.encode("latin-1") == data


def test_the_declared_encoding_is_recorded_as_a_declaration_and_not_obeyed() -> None:
    """A declared encoding is what the filer claimed; the codec is what actually worked.

    Modern filer agents emit `encoding='ASCII'` on documents containing UTF-8 punctuation. Obeying
    the declaration would either fail or corrupt; reporting both keeps the discrepancy visible.
    """
    data = (
        b"<?xml version='1.0' encoding='ASCII'?>\n<html><body><p>"
        + "net sales — up 9%".encode()
        + b"</p></body></html>\n"
    )
    decoded = decode_source(data)
    assert decoded.declared_encoding == "ASCII"
    assert decoded.codec == "utf-8"
    assert "—" in decoded.text


def test_a_meta_charset_is_read_when_there_is_no_xml_declaration() -> None:
    data = b'<html><head><meta content="text/html; charset=iso-8859-1"></head></html>'
    assert declared_encoding(data) == "iso-8859-1"


def test_a_document_declaring_nothing_reports_none_rather_than_a_guess() -> None:
    """MUTATION. Inventing a default declaration would make the recorded evidence a fiction."""
    assert declared_encoding(b"ANNUAL REPORT ON FORM 10-K\n") is None
    assert decode_source(b"plain ascii\n").declared_encoding is None


def test_the_real_pre_2001_filing_decodes_without_losing_a_byte(fixtures_dir: Path) -> None:
    """The lossless claim, against 240 KB of preserved 1994 dissemination rather than a specimen."""
    data = (fixtures_dir / "filings" / PRE_2001_FIXTURE).read_bytes()
    decoded = decode_source(data)
    assert decoded.lossless
    assert decoded.text.encode(decoded.codec) == data


# --- records ------------------------------------------------------------------------------------


def test_source_set_identity_is_stable_for_the_same_submitted_bytes() -> None:
    """Reuse identity is 'the same source set', which is not 'the same accession'.

    Two independent assemblies of identical submitted bytes must be recognisable as the same work,
    or every reuse decision downstream degrades into re-running everything.
    """
    first = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="1" * 64)
    )
    second = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="1" * 64)
    )
    assert first.source_set_id == second.source_set_id


def test_source_set_identity_changes_when_the_submitted_set_changes() -> None:
    """MUTATION. An identity that never moves is worse than none: it authorises stale reuse.

    A member fetched later, a member that failed to fetch, and a differently dispositioned member
    all produce a different source set from the same accession, and each must be visible in one
    value.
    """
    base = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="1" * 64)
    )
    changed_bytes = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="2" * 64)
    )
    added_member = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="1" * 64),
        _member(
            filename="b.png", disposition=MemberDisposition.PARSER_INPUT_IMAGE, sha256="3" * 64
        ),
    )
    reordered = _set(
        _member(
            filename="b.png", disposition=MemberDisposition.PARSER_INPUT_IMAGE, sha256="3" * 64
        ),
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="1" * 64),
    )
    identities = {
        base.source_set_id,
        changed_bytes.source_set_id,
        added_member.source_set_id,
        reordered.source_set_id,
    }
    assert len(identities) == 4, "each difference must produce a distinct identity"


def test_source_set_identity_covers_the_submitted_members_only() -> None:
    """Identity is over the bytes that were SENT, as the docstring states.

    A machine-only member is recorded but never submitted, so changing it cannot change what any
    model saw. Asserting the documented scope keeps a later widening from being made silently.
    """
    text = _member(
        filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, sha256="1" * 64
    )
    with_linkbase = _set(
        text,
        _member(filename="lab.xml", disposition=MemberDisposition.MACHINE_ONLY, sha256="9" * 64),
    )
    other_linkbase = _set(
        text,
        _member(filename="lab.xml", disposition=MemberDisposition.MACHINE_ONLY, sha256="8" * 64),
    )
    assert with_linkbase.source_set_id == other_linkbase.source_set_id


def test_uncovered_members_name_what_was_left_out() -> None:
    """A run never reports complete coverage while this is non-empty.

    The counts are asserted in both directions: the machine artifact and the unknown are reported
    as left out, and the text and image members are NOT — an 'everything is uncovered' answer would
    be as useless as an empty one.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose"),
        _member(filename="logo.png", disposition=MemberDisposition.PARSER_INPUT_IMAGE),
        _member(filename="lab.xml", disposition=MemberDisposition.MACHINE_ONLY),
        _member(filename="odd.dat", disposition=MemberDisposition.UNKNOWN_REQUIRES_REVIEW),
    )
    assert [m.filename for m in source_set.uncovered_members] == ["lab.xml", "odd.dat"]
    assert [m.filename for m in source_set.submitted_members] == ["a.htm", "logo.png"]
    assert [m.filename for m in source_set.unknown_members] == ["odd.dat"]
    assert [m.filename for m in source_set.text_members] == ["a.htm"]
    assert [m.filename for m in source_set.image_members] == ["logo.png"]


def test_a_member_inside_the_complete_submission_is_covered_but_not_submitted() -> None:
    """The pre-2001 case. Its content reaches the model; its bytes are not counted a second time."""
    inside = _member(
        filename="", disposition=MemberDisposition.INSIDE_COMPLETE_SUBMISSION, byte_count=2000
    )
    assert inside.covered
    assert not inside.submitted
    assert _set(inside).submitted_bytes == 0
    assert _set(inside).uncovered_members == ()


def test_the_manifest_never_inlines_the_bytes_it_describes() -> None:
    """A manifest that inlined a filing would be a second copy, free to drift from the first.

    The bytes live in the object store under their own hash. What serialises is the hash, the
    size, the disposition and the evidence — enough to prove what was sent, not a duplicate of it.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose"),
        _member(filename="logo.png", disposition=MemberDisposition.PARSER_INPUT_IMAGE),
    )
    mapping = source_set.to_mapping()
    round_tripped = json.loads(json.dumps(mapping))
    assert round_tripped["schema_version"] == "source-set-v1"
    assert round_tripped["source_set_id"] == source_set.source_set_id
    for member in round_tripped["members"]:
        assert "text" not in member
        assert "image_bytes" not in member
        assert member["sha256"] and member["disposition_evidence"]


def test_counts_by_disposition_reports_every_member_exactly_once() -> None:
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="x"),
        _member(filename="b.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="y"),
        _member(filename="lab.xml", disposition=MemberDisposition.MACHINE_ONLY),
    )
    assert source_set.counts_by_disposition() == {"PARSER_INPUT_TEXT": 2, "MACHINE_ONLY": 1}
    assert sum(source_set.counts_by_disposition().values()) == len(source_set.members)


def test_preserved_object_serialises_its_whole_provenance() -> None:
    obj = PreservedObject(
        filename="a.htm",
        sha256=sha256_bytes(b"x"),
        byte_count=1,
        source_url="https://example.invalid/a.htm",
        locator="filings/x/a.htm",
        acquired_at="2026-08-03T00:00:00Z",
        acquisition_method="test",
        reused=True,
    )
    assert json.loads(json.dumps(obj.to_mapping()))["acquisition_method"] == "test"


# --- inventory verification ----------------------------------------------------------------------


def test_verify_accepts_bytes_that_match_the_record() -> None:
    """ANTI-VACUITY. A verifier that rejected everything would pass both refusal tests below."""
    data = b"the preserved bytes\n"
    verify(_preserved(data), data)


def _preserved(data: bytes, *, filename: str = "a.htm") -> PreservedObject:
    return PreservedObject(
        filename=filename,
        sha256=sha256_bytes(data),
        byte_count=len(data),
        source_url="https://example.invalid/a.htm",
        locator=filename,
        acquired_at="2026-08-03T00:00:00Z",
        acquisition_method="test",
        reused=True,
    )


def test_verify_refuses_a_byte_count_that_moved() -> None:
    """A truncated object is the dangerous case: it still parses, and it is missing content.

    The recorded count proves what a previous run saw. Measuring the bytes in hand proves what
    this run would send. They differ exactly when something has gone wrong.
    """
    obj = _preserved(b"the preserved bytes\n")
    with pytest.raises(SourceIntegrityError) as error:
        verify(obj, b"the preserved by")
    assert "20" in str(error.value) and "16" in str(error.value)
    assert "a.htm" in str(error.value)


def test_verify_refuses_a_hash_that_moved_at_the_same_length() -> None:
    """MUTATION. A same-length edit is invisible to the byte count and must not slip through.

    Verification is RE-COMPUTED rather than trusted from bookkeeping precisely so a silently
    rewritten object cannot pass by keeping its size.
    """
    original = b"total net sales 94,036\n"
    tampered = b"total net sales 94,037\n"
    assert len(original) == len(tampered)
    with pytest.raises(SourceIntegrityError) as error:
        verify(_preserved(original), tampered)
    assert sha256_bytes(tampered) in str(error.value)
    assert sha256_bytes(original) in str(error.value)


def test_the_object_store_inventory_finds_what_the_acquirer_preserved(tmp_path: Path) -> None:
    """CROSS-PACKAGE CONTRACT: one key convention, owned by `filing_acquisition.storage_key`.

    A second naming convention here would mean objects this project preserved are invisible to the
    inventory that looks for them, and every member would be re-fetched from SEC as though it had
    never been acquired.
    """
    store = FilesystemObjectStore(tmp_path / "objects")
    key = storage_key(cik_padded(CIK), ACCESSION, "issuer-20250630.htm")
    store.put_bytes(key, INLINE_XBRL_PRIMARY)
    inventory = ObjectStoreInventory(store)

    found = inventory.find(CIK, ACCESSION, "issuer-20250630.htm")
    assert found is not None
    assert found.sha256 == sha256_bytes(INLINE_XBRL_PRIMARY)
    assert found.reused
    assert inventory.read(found) == INLINE_XBRL_PRIMARY
    assert inventory.filenames(CIK, ACCESSION) == ("issuer-20250630.htm",)


def test_the_object_store_inventory_normalises_identity_before_looking(tmp_path: Path) -> None:
    """`(CIK, accession)` is resolved through `sec_identity`, which owns both normalisations.

    An unpadded CIK and an undashed accession are the same filing. Re-implementing the padding
    here is how two spellings of one identity end up holding two copies of the same bytes.
    """
    store = FilesystemObjectStore(tmp_path / "objects")
    store.put_bytes(
        storage_key(cik_padded(CIK), ACCESSION, "a.htm"), b"<html><body>x</body></html>"
    )
    inventory = ObjectStoreInventory(store)
    assert inventory.find("794367", "000079436725000156", "a.htm") is not None
    assert inventory.find(CIK, ACCESSION, "absent.htm") is None


def test_the_manifest_inventory_verifies_the_file_it_reads(tmp_path: Path) -> None:
    """A research corpus is read-only and elsewhere; nothing guarantees it has not moved.

    The record is checked against the bytes at read time rather than at registration time, because
    a corpus file can be replaced between the two.
    """
    path = tmp_path / "0000320193-94-000016.txt"
    path.write_bytes(NON_ADDRESSABLE_SUBMISSION)
    obj = PreservedObject(
        filename=f"{ACCESSION}.txt",
        sha256=sha256_bytes(NON_ADDRESSABLE_SUBMISSION),
        byte_count=len(NON_ADDRESSABLE_SUBMISSION),
        source_url="",
        locator=str(path),
        acquired_at="",
        acquisition_method="corpus",
        reused=True,
    )
    inventory = ManifestInventory({("794367", "000079436725000156"): [obj]})
    assert inventory.filenames(CIK, ACCESSION) == (f"{ACCESSION}.txt",)
    assert inventory.read(obj) == NON_ADDRESSABLE_SUBMISSION

    path.write_bytes(NON_ADDRESSABLE_SUBMISSION + b"appended\n")
    with pytest.raises(SourceIntegrityError):
        inventory.read(obj)


def test_the_manifest_inventory_answers_nothing_for_a_member_it_does_not_hold() -> None:
    """The corpus preserved one object per filing; the rest must be FETCHED, not invented."""
    inventory = ManifestInventory({})
    assert inventory.find(CIK, ACCESSION, "issuer-20250630.htm") is None
    assert inventory.filenames(CIK, ACCESSION) == ()


def test_the_composite_inventory_takes_the_first_holder_in_order(tmp_path: Path) -> None:
    """Order is the caller's choice: a run's own preserved object beats a corpus duplicate."""
    store = FilesystemObjectStore(tmp_path / "objects")
    store.put_bytes(storage_key(cik_padded(CIK), ACCESSION, "a.htm"), b"the run's own copy")
    corpus = _FakeInventory({"a.htm": b"the corpus copy", "b.htm": b"corpus only"})
    composite = CompositeInventory(ObjectStoreInventory(store), corpus)

    found = composite.find(CIK, ACCESSION, "a.htm")
    assert found is not None
    assert composite.read(found) == b"the run's own copy"
    assert composite.filenames(CIK, ACCESSION) == ("a.htm", "b.htm"), "merged, without duplicates"


def test_the_composite_inventory_raises_when_nothing_can_read_the_object() -> None:
    """MUTATION. Returning empty bytes here would assemble a source set with a hole in it."""
    composite = CompositeInventory(_FakeInventory({}))
    with pytest.raises(SourceIntegrityError, match="missing.htm"):
        composite.read(_preserved(b"x", filename="missing.htm"))


# --- assembly: the non-addressable era ------------------------------------------------------------


def test_non_addressable_assembly_sends_the_complete_submission_and_covers_everything() -> None:
    """HISTORICAL-FORMAT: before roughly 2001 EDGAR publishes no per-document URL.

    The complete submission IS the source set and is sent intact. Every declared document is still
    listed so the run plan shows what that one artifact contains — marked INSIDE_COMPLETE_SUBMISSION
    so its bytes are not counted a second time and its exhibits are not reported as left out.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": NON_ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, RefusingFetcher(), transport_era="pem_armored")

    assert not source_set.members_separately_addressable
    assert len(source_set.submitted_members) == 1
    envelope = source_set.submitted_members[0]
    assert envelope.disposition is MemberDisposition.PARSER_INPUT_TEXT
    assert envelope.filename == f"{ACCESSION}.txt"
    assert envelope.text == decode_source(NON_ADDRESSABLE_SUBMISSION).text
    assert envelope.encoding == decode_source(NON_ADDRESSABLE_SUBMISSION).codec

    inside = source_set.members[1:]
    assert len(inside) == 3
    assert {m.disposition for m in inside} == {MemberDisposition.INSIDE_COMPLETE_SUBMISSION}
    assert [m.declared_type for m in inside] == ["10-K", "EX-11", "EX-27"]
    assert source_set.uncovered_members == ()
    assert source_set.submitted_bytes == len(NON_ADDRESSABLE_SUBMISSION), "no double counting"
    assert source_set.declared_document_count == source_set.listed_document_count == 3


def test_non_addressable_assembly_hashes_each_document_range_it_reports() -> None:
    """Each inner document's recorded hash must be the hash of its actual byte range.

    A listing whose hashes do not correspond to real ranges is bookkeeping, not provenance: it
    could not later prove which bytes of the envelope a given document occupied.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": NON_ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, RefusingFetcher())
    for member in source_set.members[1:]:
        assert member.byte_count > 0
        assert len(member.sha256) == 64
        assert member.sha256 != sha256_bytes(NON_ADDRESSABLE_SUBMISSION)


def test_the_real_1994_filing_assembles_with_every_exhibit_accounted_for(
    fixtures_dir: Path,
) -> None:
    """COMPLETE-CONTENT-INVARIANT, on a real 1994 dissemination with PEM armor.

    Five declared documents, one retrievable artifact, no per-document URL. The 10-K and all four
    exhibits — including the EX-27 the deleted corpus tool wanted to reclassify — must appear, and
    nothing may be reported as uncovered.
    """
    data = (fixtures_dir / "filings" / PRE_2001_FIXTURE).read_bytes()
    accession = "0000320193-94-000016"
    inventory = _FakeInventory({f"{accession}.txt": data})
    source_set = _assemble(
        inventory,
        RefusingFetcher(),
        cik="0000320193",
        accession=accession,
        form_as_filed="10-K",
        filing_date="1994-12-13",
        transport_era="pem_armored",
    )

    assert source_set.listed_document_count == 5
    assert source_set.declared_document_count == 5
    assert [m.declared_type for m in source_set.members[1:]] == [
        "10-K",
        "EX-10",
        "EX-11",
        "EX-21",
        "EX-27",
    ]
    assert source_set.uncovered_members == ()
    assert source_set.submitted_bytes == len(data)
    assert source_set.submitted_members[0].sha256 == sha256_bytes(data)


# --- assembly: the addressable era ---------------------------------------------------------------


def test_addressable_assembly_marks_the_flat_submission_a_duplicate_and_resolves_each_member() -> (
    None
):
    """The flat `.txt` is recorded with its hash but never submitted alongside its own members.

    It is kept in the record because the document listing was read from it and the provenance has
    to be traceable; it is not sent because doing so submits identical content twice. Its members
    are FETCHED rather than sliced out of it: the dissemination wraps each in an `<XBRL>` element,
    so the inner bytes are not byte-identical to the addressable object and admission by
    provenance would fail.
    """
    inventory = _FakeInventory(
        {f"{ACCESSION}.txt": ADDRESSABLE_SUBMISSION, "ex31-1.htm": CERTIFICATION_HTML}
    )
    fetcher = _RecordingFetcher(ADDRESSABLE_MEMBERS)
    source_set = _assemble(inventory, fetcher)

    assert source_set.members_separately_addressable
    flat = source_set.members[0]
    assert flat.disposition is MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION
    assert flat.filename == f"{ACCESSION}.txt"
    assert flat.sha256 == sha256_bytes(ADDRESSABLE_SUBMISSION)
    assert not flat.submitted

    assert [m.filename for m in source_set.members[1:]] == list(ADDRESSABLE_MEMBERS)
    assert fetcher.calls == [
        "issuer-20250630.htm",
        "logo.png",
        "issuer-20250630_lab.xml",
        "R1.htm",
    ], "the held member must be reused, and every other member fetched exactly once"
    reused = {m.filename for m in source_set.members if m.reused}
    assert reused == {f"{ACCESSION}.txt", "ex31-1.htm"}
    assert source_set.fetched_count == 4
    assert source_set.reused_count == 2


def test_addressable_assembly_submits_the_inline_xbrl_primary_document() -> None:
    """THE REGRESSION, END TO END. The most important member of a modern filing must be SENT.

    When it was dispositioned MACHINE_ONLY the run still looked healthy — three certifications and
    an image were submitted and the counts reconciled — and nothing anywhere said the 10-Q itself
    had not been sent. This asserts the primary document is submitted, decoded and carrying text.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, _RecordingFetcher(ADDRESSABLE_MEMBERS))

    primary = next(m for m in source_set.members if m.filename == "issuer-20250630.htm")
    assert primary.disposition is MemberDisposition.PARSER_INPUT_TEXT
    assert primary.submitted and primary.covered
    assert primary.text is not None and "Management's Discussion" in primary.text
    assert primary.encoding == "utf-8"
    assert "issuer-20250630.htm" in [m.filename for m in source_set.submitted_members]


def test_addressable_assembly_keeps_images_as_bytes_and_machine_artifacts_unsubmitted() -> None:
    """Each disposition carries the content it needs and no content it must not have.

    An image is never decoded, described or transcribed by backend code — it travels as bytes to a
    multimodal model or it is reported unanalysed. A linkbase and a renderer artifact carry
    neither text nor bytes, because neither is sent.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, _RecordingFetcher(ADDRESSABLE_MEMBERS))
    by_name = {m.filename: m for m in source_set.members}

    image = by_name["logo.png"]
    assert image.disposition is MemberDisposition.PARSER_INPUT_IMAGE
    assert image.image_bytes == PNG_BYTES
    assert image.image_format == "png"
    assert image.text is None

    assert by_name["issuer-20250630_lab.xml"].disposition is MemberDisposition.MACHINE_ONLY
    assert by_name["R1.htm"].disposition is MemberDisposition.SEC_GENERATED_RENDERING
    for suppressed in ("issuer-20250630_lab.xml", "R1.htm"):
        assert by_name[suppressed].text is None
        assert by_name[suppressed].image_bytes is None
        assert not by_name[suppressed].submitted


def test_every_declared_document_appears_in_the_assembled_set_exactly_once() -> None:
    """COMPLETE-CONTENT-INVARIANT: nothing filed is dropped, merged away or silently deduplicated.

    A member may be dispositioned as unusable, but it may never be absent. This counts the members
    against the envelope's own listing so a future filter cannot remove one quietly.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, _RecordingFetcher(ADDRESSABLE_MEMBERS))
    declared = [m for m in source_set.members if m.sequence is not None]
    assert len(declared) == source_set.listed_document_count == 5
    assert [m.sequence for m in declared] == [1, 2, 3, 4, 5]


# --- assembly: refusals ---------------------------------------------------------------------------


def test_the_refusing_fetcher_names_the_member_it_will_not_retrieve() -> None:
    """A silent skip produces an incomplete source set that looks complete.

    That is the failure this whole package exists to prevent, so the offline fetcher is not a
    no-op: it raises, and it names the member and the filing so the gap is attributable.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": ADDRESSABLE_SUBMISSION})
    with pytest.raises(SourceMemberMissingError) as error:
        _assemble(inventory, RefusingFetcher())
    message = str(error.value)
    assert "issuer-20250630.htm" in message
    assert CIK in message and ACCESSION in message
    assert "configured not to contact SEC" in message


def test_a_missing_complete_submission_is_refused_by_name() -> None:
    """Nothing is held and nothing may be fetched, so the run stops rather than assembling less."""
    with pytest.raises(SourceMemberMissingError, match=f"{ACCESSION}.txt"):
        _assemble(_FakeInventory({}), RefusingFetcher())


def test_an_artifact_that_is_not_an_envelope_is_refused_before_it_is_listed() -> None:
    """SEC-INVARIANT: a bare folder URL answers HTTP 200 with a directory listing.

    A throttle refusal is an HTML page and a directory listing is an HTML page; both would list
    zero documents, which is indistinguishable from a submission that legitimately contains none.
    The shape is checked rather than assumed.
    """
    listing = b"<html><head><title>Index of /Archives</title></head><body><p>x</p></body></html>"
    inventory = _FakeInventory({f"{ACCESSION}.txt": listing})
    with pytest.raises(SourceMemberMissingError, match="not an EDGAR"):
        load_complete_submission(inventory, RefusingFetcher(), cik=CIK, accession=ACCESSION)


def test_a_preserved_object_whose_hash_moved_is_re_acquired(tmp_path: Path) -> None:
    """The preserved original is authoritative; a stored copy that no longer matches is replaced.

    CORRECTED. This test used to assert that a hash mismatch STOPPED the assembly. That was the
    defect: step 7 of the raw-first sequence is "fetch only what is missing, incomplete OR
    HASH-INVALID", and `SourceIntegrityError`'s own docstring says the safe response is to refuse
    the bytes and re-acquire. The code refused and never re-acquired, so one corrupted local object
    killed the whole run instead of being repaired from SEC.

    Trusting the bytes and updating the recorded hash remains the one response that is never
    available: it converts a detected corruption into a silently different source set.
    """
    inventory = _StaleInventory({f"{ACCESSION}.txt": NON_ADDRESSABLE_SUBMISSION})
    fetcher = _RecordingFetcher({f"{ACCESSION}.txt": NON_ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, fetcher)
    assert f"{ACCESSION}.txt" in fetcher.calls, (
        "a hash-invalid held member must be re-acquired, not merely refused"
    )
    assert source_set.submitted_members, "the re-acquired member produced no source set"

    # And when acquisition is refused, the run says so with the member named rather than
    # pretending the source set is complete.
    with pytest.raises(SourceMemberMissingError, match=f"{ACCESSION}.txt"):
        _assemble(
            _StaleInventory({f"{ACCESSION}.txt": NON_ADDRESSABLE_SUBMISSION}), RefusingFetcher()
        )


def test_assembly_normalises_the_filing_identity_it_records() -> None:
    """`(CIK, accession)` is one identity with several spellings, normalised in exactly one place."""
    inventory = _FakeInventory({f"{ACCESSION}.txt": NON_ADDRESSABLE_SUBMISSION})
    source_set = _assemble(
        inventory, RefusingFetcher(), cik="794367", accession="000079436725000156"
    )
    assert source_set.cik == CIK
    assert source_set.accession == ACCESSION


# --- compatibility --------------------------------------------------------------------------------


def test_a_source_set_that_fits_is_reported_as_fitting() -> None:
    """ANTI-VACUITY. A guard that refused everything would satisfy every refusal test below."""
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="x" * 3800)
    )
    report = assess(
        source_set,
        prompt_text="parse this filing",
        model_context_tokens=128_000,
        requested_output_tokens=8_000,
        model_accepts_images=False,
    )
    assert report.compatible
    assert report.reason == "fits"
    assert report.text_tokens == estimate_tokens("x" * 3800)
    assert report.headroom_tokens > 0
    assert "ESTIMATES" in report.detail


def test_a_source_set_that_exceeds_the_context_is_refused_with_the_overage_named() -> None:
    """INTACT_SOURCE_ONLY. Not fitting is a RESULT, and the arithmetic is shown rather than a verdict.

    Output shares the context window with input on the Converse path, so the guard reserves room
    for both. Sizing only the input is how a request is accepted and then truncated at max_tokens
    with the parse half finished — a false complete produced by a guard that thought it had passed.
    """
    body = "x" * 40_000
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text=body)
    )
    prompt = "parse this filing"
    report = assess(
        source_set,
        prompt_text=prompt,
        model_context_tokens=8_000,
        requested_output_tokens=4_000,
        model_accepts_images=False,
    )
    expected_input = estimate_tokens(prompt) + estimate_tokens(body)
    overage = expected_input + 4_000 - 8_000

    assert not report.compatible
    assert report.reason == "source_set_exceeds_context"
    assert report.estimated_input_tokens == expected_input
    assert f"over by {overage:,}" in report.detail
    assert report.headroom_tokens == -overage
    assert "no other model is substituted" in report.detail
    assert "truncated" in report.detail


def test_an_unknown_member_refuses_the_pairing_and_names_the_member() -> None:
    """FAILING CLOSED reaches the compatibility answer too, not just the disposition table.

    A member whose role nobody recognised must not be dropped from the source set to make a run
    fit, and must not be submitted as bytes no model can use. The run stops and names it.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose"),
        _member(filename="exhibit.dat", disposition=MemberDisposition.UNKNOWN_REQUIRES_REVIEW),
    )
    report = assess(
        source_set,
        prompt_text="parse this filing",
        model_context_tokens=128_000,
        requested_output_tokens=8_000,
        model_accepts_images=False,
    )
    assert not report.compatible
    assert report.reason == "unknown_member_role"
    assert report.unknown_member_count == 1
    assert "exhibit.dat" in report.detail
    assert "fails closed" in report.detail


def test_an_unknown_member_with_no_filename_is_named_by_its_sequence() -> None:
    """MUTATION. An unnamed member must still be identifiable, or the refusal is unactionable.

    Pre-2001 members have no filename at all. Reporting `1 member(s) have an unknown role` with
    nothing to look up is the kind of message that sends a user to a support channel.
    """
    source_set = _set(
        _member(
            filename="",
            disposition=MemberDisposition.UNKNOWN_REQUIRES_REVIEW,
            sequence=4,
        )
    )
    report = assess(
        source_set,
        prompt_text="parse",
        model_context_tokens=128_000,
        requested_output_tokens=1_000,
        model_accepts_images=False,
    )
    assert "sequence 4" in report.detail


def test_a_text_only_model_reports_images_unprocessed_without_dropping_them() -> None:
    """A run that quietly omits images while reporting a complete parse is a false completeness claim.

    The images stay in the source set, they are excluded from the request bytes and from the token
    estimate, and the flag says so. Both halves matter: charging for images a text model never
    receives inflates the pre-spend bound, and hiding them inflates the coverage claim.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose"),
        _member(
            filename="logo.png",
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            byte_count=54_000,
            image_kind="png",
        ),
    )
    report = assess(
        source_set,
        prompt_text="parse this filing",
        model_context_tokens=128_000,
        requested_output_tokens=8_000,
        model_accepts_images=False,
    )
    assert report.images_unprocessed
    assert report.image_count == 0
    assert report.image_tokens == 0
    assert report.submitted_bytes == 5, "the image bytes are not part of a text-only request"
    assert len(source_set.image_members) == 1, "the image is still in the record"


def test_a_multimodal_model_charges_the_unverified_image_bound_and_flags_nothing() -> None:
    """MUTATION. `images_unprocessed` must be a real signal, not a constant.

    The image cost is a deliberately generous UNVERIFIED constant, labelled as such, because a
    guard that runs before money is spent must round in the safe direction. Too large refuses a
    run that would have fitted; too small approves one that will not.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose"),
        _member(
            filename="logo.png",
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            byte_count=54_000,
            image_kind="png",
        ),
    )
    report = assess(
        source_set,
        prompt_text="parse this filing",
        model_context_tokens=128_000,
        requested_output_tokens=8_000,
        model_accepts_images=True,
    )
    assert not report.images_unprocessed
    assert report.image_count == 1
    assert report.image_tokens == UNVERIFIED_TOKENS_PER_IMAGE
    assert report.submitted_bytes == 54_005
    assert report.to_mapping()["image_tokens_are_verified"] is False


def test_a_filing_with_no_images_never_reports_images_unprocessed() -> None:
    """MUTATION. The flag must be false for the case it does not describe.

    A flag that is true on every text-only run would be noise, and a reviewer who learns to ignore
    it stops seeing the runs where images really were left out.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose")
    )
    report = assess(
        source_set,
        prompt_text="parse",
        model_context_tokens=128_000,
        requested_output_tokens=1_000,
        model_accepts_images=False,
    )
    assert not report.images_unprocessed
    assert report.image_count == 0


def test_the_image_coverage_report_says_not_analysed_and_names_the_members() -> None:
    """The Phase 2 brief requires the affected documents NAMED, not a count.

    `analysed: false` with no names is a claim a reviewer cannot check. The hash and the byte count
    are carried too, so the unanalysed content can be found in the object store afterwards.
    """
    source_set = _set(
        _member(
            filename="logo.png",
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            byte_count=54_000,
            sha256="c" * 64,
            image_kind="png",
        ),
        _member(
            filename="chart.jpg",
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            byte_count=12_000,
            sha256="d" * 64,
            image_kind="jpeg",
        ),
    )
    report = image_coverage_report(source_set, model_accepts_images=False)
    assert report["image_member_count"] == 2
    assert report["analysed"] is False
    assert "NOT analysed" in report["reason"]
    assert [m["filename"] for m in report["members"]] == ["logo.png", "chart.jpg"]
    assert [m["submitted_to_parser"] for m in report["members"]] == [False, False]
    assert [m["sha256"] for m in report["members"]] == ["c" * 64, "d" * 64]
    assert json.loads(json.dumps(report))["image_member_count"] == 2


def test_the_image_coverage_report_claims_analysis_only_for_a_multimodal_model() -> None:
    """MUTATION. `analysed` must move with the model, or the field asserts nothing."""
    source_set = _set(
        _member(
            filename="logo.png",
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            image_kind="png",
        )
    )
    assert image_coverage_report(source_set, model_accepts_images=True)["analysed"] is True
    assert image_coverage_report(source_set, model_accepts_images=False)["analysed"] is False


def test_the_compatibility_report_labels_every_token_figure_an_estimate() -> None:
    """R-24 IS OPEN: a character ratio is an upper bound, not a count.

    Every published token figure in this project comes from that ratio. The serialised report has
    to say so beside the numbers, so a reader cannot mistake a pre-spend bound for a measurement.
    """
    source_set = _set(
        _member(filename="a.htm", disposition=MemberDisposition.PARSER_INPUT_TEXT, text="prose")
    )
    mapping = assess(
        source_set,
        prompt_text="parse",
        model_context_tokens=128_000,
        requested_output_tokens=1_000,
        model_accepts_images=False,
    ).to_mapping()
    assert "ESTIMATES" in mapping["token_values_are"]
    assert mapping["image_tokens_are_verified"] is False
    assert mapping["headroom_tokens"] == (
        128_000 - mapping["estimated_input_tokens"] - mapping["requested_output_tokens"]
    )
    assert json.loads(json.dumps(mapping))["compatible"] is True


def test_the_whole_path_from_preserved_bytes_to_a_compatibility_answer_holds_together() -> None:
    """END TO END, still hermetic: preserved bytes in, a defensible yes-or-no out.

    The inline-XBRL primary document survives disposition, is decoded, is submitted, is estimated,
    and the machine artifacts it travels with are reported as uncovered rather than as content the
    model saw. Each of those has its own test; this one proves they compose.
    """
    inventory = _FakeInventory({f"{ACCESSION}.txt": ADDRESSABLE_SUBMISSION})
    source_set = _assemble(inventory, _RecordingFetcher(ADDRESSABLE_MEMBERS))
    report = assess(
        source_set,
        prompt_text="Return the filing's native semantic structure.",
        model_context_tokens=128_000,
        requested_output_tokens=8_000,
        model_accepts_images=False,
    )
    assert report.compatible
    assert report.unknown_member_count == 0
    assert report.images_unprocessed, "the GRAPHIC member cannot reach a text-only parser"
    assert report.text_tokens > 0
    # The flat submission is NOT uncovered: it is a byte-for-byte duplicate of members that ARE
    # sent, so its content reaches the model in full. Only the machine artifact and SEC's own
    # renderer output are genuinely content the model never saw.
    assert {m.filename for m in source_set.uncovered_members} == {
        "issuer-20250630_lab.xml",
        "R1.htm",
    }
