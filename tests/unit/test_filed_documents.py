"""The filed-document listing of one accession, and the classification it must never perform.

HERMETIC. Two kinds of input are used and no other. The first is
`tests/fixtures/filings/0000320193-94-000016/0000320193-94-000016.txt` — 240,556 preserved bytes of
a real 1994 dissemination, PEM-armored, `<IMS-DOCUMENT>`-wrapped, five filed documents, not one of
them carrying a filename. Its SHA-256 is pinned by the fixture manifest and verified by
`test_filing_fixtures.py`, so the byte offsets asserted below are measurements of a fixed artifact
rather than numbers that happen to hold today. The second input is synthetic envelope built in this
file: tag structure and placeholder bodies, nothing anybody has to interpret. Nothing here reaches
SEC, and nothing here needs a credential, a database or a socket.

WHAT IS ACTUALLY BEING TESTED. Not that a regex finds five `<DOCUMENT>` blocks; that is arithmetic.
The subject is the set of things this module replaced `packages/filing_acquisition/inventory.py` in
order to STOP doing: sorting declared types into a Regulation S-K role taxonomy, deciding which
member is "the filing", ruling that a courtesy copy duplicates another member, and normalising the
filer's own string into the one a reader expects. That module suppressed a filed source range on a
semantic judgement and was deleted for it (ADR-0017). `EX-27` and `10-K` must come back as two
strings the filer typed, and every test below that touches one of them asserts the module treated
the two identically.

THE SECOND SUBJECT IS THE REFUSAL. SEC answers a bare folder URL with HTTP 200 and a directory
listing, and answers a throttle with an HTML page. Both are bytes, both contain zero `<DOCUMENT>`
blocks, and "zero documents" is an answer a caller would believe. The committed 403 and
directory-listing fixtures are fed to the lister here to prove it raises instead — and an envelope
that legitimately contains nothing is fed to it too, to prove the guard did not quietly become
"raise on everything".
"""

from __future__ import annotations

import ast
import re
from dataclasses import fields
from pathlib import Path

import pytest

from packages.filing_acquisition import (
    FiledDocument,
    SubmissionFormatError,
    declared_document_count,
    list_filed_documents,
    looks_like_complete_submission,
    submission_header,
)
from packages.filing_acquisition import documents as documents_module

PRE_2001 = "0000320193-94-000016"

# Measured against the hash-pinned fixture. The five documents Apple filed in December 1994, in the
# order they appear, with the filer's own type strings and the byte length of each `<TEXT>` body.
PRE_2001_TYPES = ("10-K", "EX-10", "EX-11", "EX-21", "EX-27")
PRE_2001_BYTE_COUNTS = (209340, 22191, 3453, 1175, 2812)
EX_27_RANGE = (237669, 240481)


@pytest.fixture
def pre_2001_submission(fixtures_dir: Path) -> bytes:
    """The preserved 1994 complete submission, exactly as SEC disseminated it."""
    return (fixtures_dir / "filings" / PRE_2001 / f"{PRE_2001}.txt").read_bytes()


def _document(
    declared_type: bytes,
    sequence: bytes = b"1",
    body: bytes = b"BODY\n",
    filename: bytes = b"",
    description: bytes = b"",
    with_text: bool = True,
) -> bytes:
    """One synthetic `<DOCUMENT>` block. `body` must end with a newline, as EDGAR's always do."""
    lines = [b"<DOCUMENT>", b"<TYPE>" + declared_type, b"<SEQUENCE>" + sequence]
    if filename:
        lines.append(b"<FILENAME>" + filename)
    if description:
        lines.append(b"<DESCRIPTION>" + description)
    block = b"\n".join(lines) + b"\n"
    if with_text:
        block += b"<TEXT>\n" + body + b"</TEXT>\n"
    return block + b"</DOCUMENT>\n"


def _submission(
    *documents: bytes,
    envelope: bytes = b"SEC",
    declared_count: bytes | None = None,
    extra_header: tuple[bytes, ...] = (),
) -> bytes:
    """One synthetic complete submission wrapped in the named envelope variant.

    `SEC` and `IMS` are the same length, so a submission built one way and the same submission
    built the other way are byte-for-byte parallel — which is what makes the envelope-equivalence
    test below able to compare offsets directly.
    """
    header = [
        b"<" + envelope + b"-DOCUMENT>0000000000-00-000000.txt : 20200101",
        b"<" + envelope + b"-HEADER>0000000000-00-000000.hdr.sgml : 20200101",
        b"ACCESSION NUMBER:\t\t0000000000-00-000000",
        b"CONFORMED SUBMISSION TYPE:\t10-K",
    ]
    if declared_count is not None:
        header.append(b"PUBLIC DOCUMENT COUNT:\t\t" + declared_count)
    header.extend(extra_header)
    header.append(b"</" + envelope + b"-HEADER>")
    return b"\n".join(header) + b"\n" + b"".join(documents) + b"</" + envelope + b"-DOCUMENT>\n"


# --- the preserved 1994 submission: the <IMS-DOCUMENT> variant ----------------------------------


def test_the_1995_era_envelope_variant_is_recognised_under_its_pem_armor(
    pre_2001_submission: bytes,
) -> None:
    """HISTORICAL-FORMAT: the oldest dissemination names its envelope `<IMS-DOCUMENT>`.

    It is also wrapped in PEM armor, so the envelope marker is several hundred bytes into the file
    rather than on line one. A recogniser that looked only at the first line, or only for
    `<SEC-DOCUMENT>`, would reject an entire era of the corpus as "not a submission".
    """
    assert looks_like_complete_submission(pre_2001_submission)
    assert pre_2001_submission.startswith(b"-----BEGIN PRIVACY-ENHANCED MESSAGE-----")
    assert b"<IMS-DOCUMENT>" in pre_2001_submission
    assert b"<SEC-DOCUMENT>" not in pre_2001_submission, "this fixture is the IMS variant"


def test_every_document_the_1994_filer_submitted_is_listed_in_filed_order(
    pre_2001_submission: bytes,
) -> None:
    """COMPLETE-CONTENT-INVARIANT: a member the envelope declares and the listing omits is loss.

    Five documents, in the sequence the filer numbered them. The count and the sequence are both
    asserted because a lister that dropped the last exhibit and a lister that reordered the set
    would each still return "some documents".
    """
    documents = list_filed_documents(pre_2001_submission)
    assert len(documents) == 5
    assert tuple(d.sequence for d in documents) == (1, 2, 3, 4, 5)


def test_the_declared_type_is_carried_exactly_as_the_filer_typed_it(
    pre_2001_submission: bytes,
) -> None:
    """The filer's string, verbatim — no case folding, no hyphen removal, no mapping to a role.

    `EX-27` is the Article 5 Financial Data Schedule, and knowing that is precisely what this
    module is forbidden to encode. It comes back as the five characters the filer typed, beside
    `10-K`, with nothing to distinguish them but their content.
    """
    documents = list_filed_documents(pre_2001_submission)
    assert tuple(d.declared_type for d in documents) == PRE_2001_TYPES

    exhibit = documents[-1]
    assert exhibit.declared_type == "EX-27"
    assert exhibit.declared_type in pre_2001_submission.decode("ascii"), "not a reconstruction"
    # The opposite case, asserted so this is not merely a spelling check: the record carries the
    # string and nothing derived from it.
    assert "EX-27" not in {key for key in exhibit.as_record() if key != "declared_type"}
    assert exhibit.as_record()["declared_type"] == "EX-27"


def test_a_pre_2001_document_has_no_filename_and_is_not_separately_addressable(
    pre_2001_submission: bytes,
) -> None:
    """HISTORICAL-FORMAT: an entire era publishes no per-document URL, and that must be visible.

    EDGAR does not serve the filed components of this submission as separate objects. A caller that
    assumed a filename could be derived would build a URL that returns a directory listing with
    HTTP 200 — a corruption that looks like success. The empty filename is reported rather than
    invented, and `separately_addressable` says so in one boolean.
    """
    documents = list_filed_documents(pre_2001_submission)
    assert [d.filename for d in documents] == ["", "", "", "", ""]
    assert not any(d.separately_addressable for d in documents)


def test_a_description_is_reported_only_when_the_filer_declared_one(
    pre_2001_submission: bytes,
) -> None:
    """A description is a filer courtesy, present on one of these five documents and absent on four.

    Absent stays absent. Synthesising a description from the declared type would be the smallest
    possible version of the semantic decision this module refuses to make.
    """
    documents = list_filed_documents(pre_2001_submission)
    assert documents[-1].description == "ART. 5 FDS FOR FY94 FORM 10-K"
    assert [d.description for d in documents[:-1]] == ["", "", "", ""]


def test_the_byte_range_of_a_document_is_the_exact_span_between_its_text_tags(
    pre_2001_submission: bytes,
) -> None:
    """SOURCE-PRESERVATION: the reported range must reproduce the filed bytes, not approximate them.

    Checked from both ends. The byte before `start_offset` closes the `<TEXT>` line that opens the
    body, the bytes at `end_offset` open the `</TEXT>` line that closes it, and the extracted span
    is the exhibit's own first and last lines. An offset off by one line would still extract
    something that reads like an exhibit.
    """
    submission = pre_2001_submission
    exhibit = list_filed_documents(submission)[-1]
    start, end = EX_27_RANGE

    assert (exhibit.start_offset, exhibit.end_offset) == (start, end)
    assert exhibit.byte_count == end - start == 2812
    assert submission[start - 7 : start] == b"<TEXT>\n"
    assert submission[end : end + 7] == b"</TEXT>"
    assert exhibit.extract(submission) == submission[start:end]
    assert exhibit.extract(submission).startswith(b"\n<TABLE> <S> <C>\n")
    assert exhibit.extract(submission).endswith(b"</TABLE>\n")


def test_no_document_body_carries_the_envelope_that_delimits_it(
    pre_2001_submission: bytes,
) -> None:
    """A range that swallowed its own closing tag would corrupt every downstream byte count."""
    submission = pre_2001_submission
    documents = list_filed_documents(submission)
    assert [d.byte_count for d in documents] == list(PRE_2001_BYTE_COUNTS)
    for document in documents:
        extracted = document.extract(submission)
        assert b"</TEXT>" not in extracted
        assert b"<DOCUMENT>" not in extracted
        assert b"</IMS-DOCUMENT>" not in extracted


def test_document_ranges_are_disjoint_and_strictly_increasing(
    pre_2001_submission: bytes,
) -> None:
    """Overlapping ranges would double-count source bytes when coverage is later proved.

    The whole point of reporting exact ranges is that a coverage proof can add them up. Ranges that
    overlapped, or that ran backwards, would let a proof report more source covered than exists.
    """
    submission = pre_2001_submission
    documents = list_filed_documents(submission)
    previous_end = 0
    for document in documents:
        assert 0 <= document.start_offset <= document.end_offset <= len(submission)
        assert document.start_offset >= previous_end, "document ranges overlap"
        previous_end = document.end_offset
    assert sum(d.byte_count for d in documents) < len(submission), "ranges exceed the artifact"


# --- the <SEC-DOCUMENT> variant and the filename era ---------------------------------------------


def test_the_modern_envelope_variant_is_recognised() -> None:
    """1996 onward names the envelope `<SEC-DOCUMENT>`; both spellings are the same transport."""
    submission = _submission(_document(b"10-K", filename=b"aapl-20250927.htm"))
    assert looks_like_complete_submission(submission)
    assert len(list_filed_documents(submission)) == 1


def test_a_document_that_declares_a_filename_is_separately_addressable() -> None:
    """Roughly 2001 onward, EDGAR publishes a per-document URL, and the filename is the evidence.

    This is the opposite of the pre-2001 case above, asserted separately so `separately_addressable`
    cannot be a constant. One era says False, the other says True, and the acquirer routes on it.
    """
    submission = _submission(
        _document(b"10-K", sequence=b"1", filename=b"aapl-20250927.htm"),
        _document(b"EX-27", sequence=b"2", filename=b"ex-27.txt"),
    )
    documents = list_filed_documents(submission)
    assert [d.filename for d in documents] == ["aapl-20250927.htm", "ex-27.txt"]
    assert all(d.separately_addressable for d in documents)


def test_the_envelope_name_changes_nothing_about_the_listing() -> None:
    """Transport syntax is not content. The 1995 and 1996 spellings must list identically.

    Both markers are fourteen bytes, so the two submissions are byte-for-byte parallel and the
    records — offsets included — have to match exactly. A variant handled by a separate code path
    would drift, and the older path is the one nobody looks at.
    """
    body = (_document(b"10-K", sequence=b"1"), _document(b"EX-27", sequence=b"2"))
    modern = _submission(*body, envelope=b"SEC")
    historical = _submission(*body, envelope=b"IMS")

    assert len(modern) == len(historical), "the two variants are not byte-parallel"
    assert looks_like_complete_submission(modern)
    assert looks_like_complete_submission(historical)
    assert [d.as_record() for d in list_filed_documents(modern)] == [
        d.as_record() for d in list_filed_documents(historical)
    ]


def test_a_declared_document_with_no_text_body_is_listed_with_an_empty_range() -> None:
    """COMPLETE-CONTENT-INVARIANT: a member with no content is reported, never dropped.

    Dropping it would make the listing disagree with the envelope silently, which is the exact
    class of loss this module exists to prevent. It is reported with a zero-length range so a
    caller can see both that it was declared and that it carries nothing.
    """
    submission = _submission(
        _document(b"GRAPHIC", sequence=b"1", filename=b"logo.gif", with_text=False),
        _document(b"EX-27", sequence=b"2"),
    )
    documents = list_filed_documents(submission)
    assert len(documents) == 2
    assert documents[0].declared_type == "GRAPHIC"
    assert documents[0].byte_count == 0
    assert documents[0].extract(submission) == b""
    assert documents[1].byte_count > 0, "the empty member must not swallow the next one"


def test_an_unparsable_sequence_is_reported_as_unknown_rather_than_as_a_number() -> None:
    """`None` and `0` are different claims, and only one of them is honest.

    A filer's sequence is a declaration like any other. When it is absent or not a number, the
    listing says it does not know instead of substituting a plausible integer that a later ordering
    would trust.
    """
    submission = _submission(
        _document(b"EX-10", sequence=b"", body=b"FIRST\n"),
        _document(b"EX-11", sequence=b"1.1", body=b"SECOND\n"),
        _document(b"EX-21", sequence=b"3", body=b"THIRD\n"),
    )
    documents = list_filed_documents(submission)
    assert [d.sequence for d in documents] == [None, None, 3]
    assert 0 not in [d.sequence for d in documents], "an unknown sequence was coerced to a number"


def test_offsets_index_bytes_not_decoded_characters() -> None:
    """A decode-then-index round trip loses byte fidelity on any submission that is not pure ASCII.

    The 1994 fixture is pure ASCII and cannot demonstrate this, so the case is built: forty
    two-byte characters in the first document put every later character index forty behind its byte
    index. The reported offsets must still cut the second document out of the RAW bytes exactly.
    """
    submission = _submission(
        # b"\xc2\xa9" is UTF-8 for the copyright sign: two bytes, one character.
        _document(b"EX-10", sequence=b"1", body=b"\xc2\xa9" * 40 + b"\n"),
        _document(b"EX-11", sequence=b"2", body=b"SECOND-BODY\n"),
    )
    second = list_filed_documents(submission)[1]

    assert second.extract(submission) == b"SECOND-BODY\n"
    decoded = submission.decode("utf-8")
    assert decoded[second.start_offset : second.end_offset] != "SECOND-BODY\n", (
        "the offsets happen to be character offsets, so this case proves nothing"
    )


# --- the declared count and the listed count, reported separately --------------------------------


def test_the_declared_count_and_the_listed_count_are_reported_separately() -> None:
    """The envelope can disagree with its own header, and the caller must see both numbers.

    This is not hypothetical: one measured accession declared sixteen public documents and
    contained fifteen. Reconciling the two here would mean this module deciding which of the filer
    and the envelope to believe, and then reporting a single number that hides the conflict.
    """
    listed = [_document(b"EX-10", sequence=str(n).encode()) for n in range(1, 16)]
    submission = _submission(*listed, declared_count=b"16")

    assert declared_document_count(submission) == 16
    assert len(list_filed_documents(submission)) == 15
    # Neither number was adjusted toward the other, and neither call raised over the disagreement.
    assert declared_document_count(submission) != len(list_filed_documents(submission))


def test_the_two_counts_agree_on_the_preserved_1994_submission(
    pre_2001_submission: bytes,
) -> None:
    """Anti-vacuity for the test above: a lister that always undercounted would also pass it.

    On a real, hash-pinned submission the header's declared count and the listing agree exactly.
    The disagreement case is therefore a property of that envelope, not of this module.
    """
    assert declared_document_count(pre_2001_submission) == 5
    assert len(list_filed_documents(pre_2001_submission)) == 5


def test_a_submission_declaring_no_document_count_reports_unknown_not_zero() -> None:
    """ "The header did not say" and "the header said none" are different facts.

    Returning 0 for a missing declaration would make an absent field look like a filer's assertion,
    and a reconciliation against it would then report a discrepancy nobody created.
    """
    submission = _submission(_document(b"10-K"), declared_count=None)
    assert declared_document_count(submission) is None
    assert list_filed_documents(submission), "the documents themselves are still listed"


# --- the submission header -----------------------------------------------------------------------


def test_the_header_reports_what_the_1994_filer_declared(pre_2001_submission: bytes) -> None:
    """The declared submission type, accession, period and filing date, as flat strings.

    Read out of the envelope rather than out of a filename or a directory path, both of which are
    conventions rather than declarations.
    """
    header = submission_header(pre_2001_submission)
    assert header["ACCESSION NUMBER"] == PRE_2001
    assert header["CONFORMED SUBMISSION TYPE"] == "10-K"
    assert header["CONFORMED PERIOD OF REPORT"] == "19940930"
    assert header["FILED AS OF DATE"] == "19941213"
    assert header["PUBLIC DOCUMENT COUNT"] == "5"


def test_only_the_first_occurrence_of_a_repeated_header_field_is_kept() -> None:
    """A repeated field collapses to its first value rather than growing a structure.

    The header repeats `SROS:` and repeats an address block per filer. Turning those into lists
    would invent a shape the envelope does not have; keeping the first occurrence is a documented,
    checkable rule, and this test is what stops it from silently becoming "keep the last".
    """
    submission = _submission(
        _document(b"10-K"),
        extra_header=(b"SROS:\t\t\tNASD", b"SROS:\t\t\tNYSE"),
    )
    assert submission_header(submission)["SROS"] == "NASD"


def test_the_header_stops_at_the_first_document() -> None:
    """A header-shaped line inside a filed document is content, not a declaration.

    Filings quote correspondence, cover pages and tables of contents, any of which can contain a
    line that looks exactly like an EDGAR header field. Scanning the whole submission would let a
    document's own text overwrite — or invent — the accession the envelope declared.
    """
    submission = _submission(
        _document(
            b"10-K",
            body=b"ACCESSION NUMBER:\t\t9999999999-99-999999\nINVENTED FIELD:\t\tnot a header\n",
        )
    )
    header = submission_header(submission)
    assert header["ACCESSION NUMBER"] == "0000000000-00-000000"
    assert "INVENTED FIELD" not in header


# --- what SEC serves when it is not serving a submission -----------------------------------------


@pytest.mark.parametrize(
    "relative_path",
    [
        "sec_directory_listing.html",
        "sec_403_rate_limit.html",
        "sec_403_undeclared_automation.html",
        "filings/0000320193-25-000079/aapl-20250927.htm",
    ],
)
def test_bytes_sec_serves_instead_of_a_submission_are_not_mistaken_for_one(
    fixtures_dir: Path, relative_path: str
) -> None:
    """Every one of these is HTTP 200 with a body, and none of them is a complete submission.

    A bare folder URL returns a directory listing; a throttle and an undeclared-automation refusal
    each return an HTML page; and a filing's primary document handed here by mistake is a real
    filing that is nonetheless not an envelope. All four contain zero `<DOCUMENT>` blocks.
    """
    assert not looks_like_complete_submission((fixtures_dir / relative_path).read_bytes())


@pytest.mark.parametrize(
    "relative_path",
    [
        "sec_directory_listing.html",
        "sec_403_rate_limit.html",
        "sec_403_undeclared_automation.html",
    ],
)
def test_listing_a_non_submission_raises_rather_than_returning_an_empty_tuple(
    fixtures_dir: Path, relative_path: str
) -> None:
    """An empty tuple would be indistinguishable from a submission that legitimately holds nothing.

    That is the whole reason the check exists. A caller handed `()` has no way to tell "SEC threw a
    403 page at me" from "this accession really has no documents", and the first case is a retry
    while the second is a finding. The error names both envelope markers so the reader knows what
    was looked for.
    """
    with pytest.raises(SubmissionFormatError) as error:
        list_filed_documents((fixtures_dir / relative_path).read_bytes())
    assert "<SEC-DOCUMENT>" in str(error.value)
    assert "<IMS-DOCUMENT>" in str(error.value)


def test_an_envelope_that_contains_nothing_returns_empty_rather_than_raising() -> None:
    """Anti-vacuity, and the other half of the refusal above.

    A guard that raised on everything would pass every test in the section above while destroying
    the distinction it exists to draw. A real envelope holding no `<DOCUMENT>` block is a valid
    answer, and it returns an empty tuple without raising.
    """
    empty = _submission(declared_count=b"0")
    assert looks_like_complete_submission(empty)
    assert list_filed_documents(empty) == ()
    assert declared_document_count(empty) == 0


# --- the classification this module must never perform -------------------------------------------


def test_two_documents_differing_only_in_declared_type_are_treated_identically() -> None:
    """MUTATION: the declared type must change the string reported and nothing else at all.

    Two documents, same sequence-adjacent position, same body, same absent filename, same absent
    description — differing only in whether the filer typed `10-K` or `EX-27`. The deleted
    `inventory.py` would have called the first one "the filing" and the second an exhibit, and
    would have ruled a third member a duplicate. Here every derived field is equal, so any future
    role, importance or duplication verdict makes this test fail.
    """
    submission = _submission(
        _document(b"10-K", sequence=b"1", body=b"IDENTICAL-BODY\n"),
        _document(b"EX-27", sequence=b"2", body=b"IDENTICAL-BODY\n"),
    )
    primary, exhibit = list_filed_documents(submission)

    assert (primary.declared_type, exhibit.declared_type) == ("10-K", "EX-27")
    assert primary.byte_count == exhibit.byte_count
    assert primary.extract(submission) == exhibit.extract(submission) == b"IDENTICAL-BODY\n"
    assert primary.filename == exhibit.filename == ""
    assert primary.description == exhibit.description == ""
    assert primary.separately_addressable is exhibit.separately_addressable is False

    derived = {"declared_type", "sequence", "start_offset", "end_offset"}
    assert {k: v for k, v in primary.as_record().items() if k not in derived} == {
        k: v for k, v in exhibit.as_record().items() if k not in derived
    }


def test_the_record_exposes_no_role_class_or_importance_field() -> None:
    """The record's shape is the contract, and the contract has no place to put a verdict.

    Asserted as an exact field set rather than a subset: a role, a category or an `is_primary` flag
    added later would fail here before it could reach a caller who might believe it.
    """
    assert {f.name for f in fields(FiledDocument)} == {
        "sequence",
        "declared_type",
        "filename",
        "description",
        "start_offset",
        "end_offset",
    }

    document = FiledDocument(
        sequence=1,
        declared_type="EX-27",
        filename="",
        description="",
        start_offset=0,
        end_offset=0,
    )
    assert set(document.as_record()) == {
        "sequence",
        "declared_type",
        "filename",
        "description",
        "start_offset",
        "end_offset",
        "byte_count",
        "separately_addressable",
    }

    forbidden = re.compile(
        r"role|class|kind|categor|primary|exhibit|graphic|import|duplicat|canonical|footnote"
    )
    offenders = [name for name in dir(FiledDocument) if not name.startswith("_")]
    assert not [name for name in offenders if forbidden.search(name)], (
        f"a classification-shaped member appeared on the record: {offenders}"
    )


def test_the_module_evaluates_no_filing_type_or_role_literal() -> None:
    """MUTATION: no declared type may exist as a value the interpreter can match against.

    Parsed rather than grepped, so only string literals the code EVALUATES are inspected — the
    module's own docstring names `EX-27`, `EX-13`, `10-K` and `GRAPHIC` while explaining why it
    refuses to interpret them, and that explanation must stay legal. This is the same technique
    `tests/architecture/test_architecture.py` uses for the filing-form allowlist, narrowed to this
    module and widened to exhibit types and role vocabulary.
    """
    tree = ast.parse(Path(documents_module.__file__).read_text(encoding="utf-8"))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    role_literal = re.compile(
        r"(EX-[\w.]+|10-?[KQ][\w./]*|GRAPHIC|COVER|PDF|primary|exhibit|annual[ _]report"
        r"|financial[ _]data[ _]schedule|duplicate|courtesy)",
        re.IGNORECASE,
    )

    inspected: list[str] = []
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or node in docstrings:
            continue
        if isinstance(node.value, bytes):
            value = node.value.decode("latin-1")
        elif isinstance(node.value, str):
            value = node.value
        else:
            continue
        inspected.append(value)
        if role_literal.search(value):
            offenders.append(f"line {node.lineno}: {value!r}")

    assert len(inspected) >= 10, "the scan found almost no literals and is not measuring the module"
    assert not offenders, (
        "a filing type or role vocabulary is written into evaluated source; deciding what a "
        f"declared type MEANS is the selected parsing model's job: {offenders}"
    )


def test_the_module_holds_no_lookup_table_keyed_by_a_declared_type() -> None:
    """MUTATION: a taxonomy needs somewhere to live, and this asserts there is nowhere.

    Any mapping from a filer's string to a role, and any membership test against a fixed set of
    them, requires a literal container in the source. The module builds dictionaries at runtime
    from what it read — `declared`, `fields` — and neither is ever populated from a literal, so a
    dict with a constant value, a set literal, or an `in` against a literal container is enough
    evidence on its own.
    """
    tree = ast.parse(Path(documents_module.__file__).read_text(encoding="utf-8"))
    tables: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and any(
            isinstance(value, ast.Constant) for value in node.values if value is not None
        ):
            tables.append(f"line {node.lineno}: a dict literal holding constant values")
        if isinstance(node, ast.Set):
            tables.append(f"line {node.lineno}: a set literal")
        if isinstance(node, ast.Compare) and any(
            isinstance(op, ast.In | ast.NotIn) for op in node.ops
        ):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Tuple | ast.List | ast.Set | ast.Dict):
                    tables.append(f"line {node.lineno}: a membership test against a literal set")
    assert not tables, f"a classification table appeared in the filed-document lister: {tables}"
