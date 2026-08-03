"""The filed-document listing of one accession, read from the bytes SEC disseminated.

THIS REPLACES A MODULE THAT WAS DELETED FOR CLASSIFYING. `packages/filing_acquisition/inventory.py`
listed an accession's documents and then sorted them into a Regulation S-K role taxonomy, decided
which of them were "the filing" and ruled that a courtesy PDF duplicated the primary document —
which suppressed a filed source range on a semantic judgement. It was deleted (ADR-0017) and
rules.md section 5 reserves this module's name for a NON-CLASSIFYING replacement.

WHAT THIS MODULE DOES. It reads the EDGAR dissemination envelope and reports what the FILER
declared: for each filed document, its sequence, its declared type string, its filename when the
era publishes one, its description, and its exact byte range inside the submission.

WHAT THIS MODULE WILL NEVER DO. It assigns no role, no importance, no class and no meaning. It
does not decide that `EX-27` is numeric evidence, that `EX-13` is the annual report, that a
graphic is decorative, or that anything duplicates anything else. `EX-27` and `10-K` come back as
two strings the filer typed. Deciding what they MEAN is the selected parsing model's job —
rules.md invariant 14 and section 21 rule 1.

WHY PARSING SGML HERE IS NOT SEMANTIC PARSING. `<DOCUMENT>`, `<TYPE>`, `<SEQUENCE>`, `<FILENAME>`
and `<TEXT>` are EDGAR's transport envelope, in the same sense that a ZIP central directory is a
transport envelope. Reading them tells you which byte ranges the filer submitted as separate
documents and what the filer called them. It tells you nothing about what any of them says.

HISTORICAL-FORMAT. Three envelope variants appear in the preserved corpus and all three are
handled: 1995 dissemination wraps the submission in PEM armor and names the envelope
`<IMS-DOCUMENT>`; 1996 onward names it `<SEC-DOCUMENT>`; and only filings from roughly 2001
declare a `<FILENAME>` at all. A document with no filename is NOT individually addressable on
EDGAR — there is no per-document URL for it — and the complete submission is the only artifact
that can be retrieved. That is a transport fact with a large consequence, and it is reported
rather than smoothed over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import SubmissionFormatError

# Byte-level patterns. Offsets have to be exact byte offsets into the preserved artifact, and a
# decode-then-index round trip does not preserve them for a submission that is not pure ASCII.
_DOCUMENT_OPEN = re.compile(rb"^<DOCUMENT>[^\S\n]*$", re.MULTILINE)
_DOCUMENT_CLOSE = re.compile(rb"^</DOCUMENT>[^\S\n]*$", re.MULTILINE)
_TEXT_OPEN = re.compile(rb"^<TEXT>[^\S\n]*\r?\n", re.MULTILINE)
_TEXT_CLOSE = re.compile(rb"^</TEXT>[^\S\n]*$", re.MULTILINE)
_TAG_VALUE = re.compile(rb"^<(TYPE|SEQUENCE|FILENAME|DESCRIPTION)>(.*)$", re.MULTILINE)
_HEADER_FIELD = re.compile(rb"^([A-Z][A-Z0-9 \-/]*):\s*(.+)$", re.MULTILINE)
_ENVELOPE = re.compile(rb"^<(SEC|IMS)-DOCUMENT>", re.MULTILINE)


@dataclass(frozen=True)
class FiledDocument:
    """One document the filer submitted, exactly as the filer declared it.

    `declared_type` is the filer's own string — `10-K`, `10-K405`, `EX-27`, `EX-10.36`, `GRAPHIC`.
    It is carried verbatim and is never normalised, mapped or interpreted, for the same reason the
    filed form string is carried verbatim: EDGAR's real strings are not the ones a reader expects,
    and a normalisation is a guess that hides its own error.

    `filename` is empty when the era published none. An empty filename means the document has no
    individual URL on EDGAR and exists only inside the complete submission.
    """

    sequence: int | None
    declared_type: str
    filename: str
    description: str
    start_offset: int
    end_offset: int

    @property
    def byte_count(self) -> int:
        return self.end_offset - self.start_offset

    @property
    def separately_addressable(self) -> bool:
        """Whether EDGAR publishes a per-document URL for this member."""
        return bool(self.filename)

    def extract(self, submission: bytes) -> bytes:
        """The exact bytes of this document inside the submission it came from."""
        return submission[self.start_offset : self.end_offset]

    def as_record(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "declared_type": self.declared_type,
            "filename": self.filename,
            "description": self.description,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "byte_count": self.byte_count,
            "separately_addressable": self.separately_addressable,
        }


def looks_like_complete_submission(submission: bytes) -> bool:
    """Whether these bytes are an EDGAR complete-submission envelope.

    Checked before listing rather than assumed. A directory listing, an error page or a primary
    document handed here by mistake would otherwise produce an empty document list, which reads
    identically to a submission that legitimately contains nothing.
    """
    return bool(_ENVELOPE.search(submission[:8192]))


def submission_header(submission: bytes) -> dict[str, str]:
    """The declared header fields of the submission, as flat strings.

    Only the FIRST occurrence of each field is kept. The header repeats `SROS:` and repeats an
    address block per filer, and collapsing those into a list would invent a structure the
    envelope does not have. What callers need from here is the declared submission type, the
    accession, the period and the filing date — all of which appear once.
    """
    boundary = submission.find(b"<DOCUMENT>")
    header_bytes = submission[: boundary if boundary > 0 else len(submission)]
    fields: dict[str, str] = {}
    for match in _HEADER_FIELD.finditer(header_bytes):
        key = match.group(1).decode("ascii", errors="replace").strip()
        if key in fields:
            continue
        fields[key] = match.group(2).decode("utf-8", errors="replace").strip()
    return fields


def list_filed_documents(submission: bytes) -> tuple[FiledDocument, ...]:
    """Every document the filer submitted, in filed order, with exact byte ranges.

    Raises rather than returning an empty tuple when the bytes are not a complete submission.
    "No documents" and "not a submission" are different answers and must not look the same.
    """
    if not looks_like_complete_submission(submission):
        raise SubmissionFormatError(
            "these bytes are not an EDGAR complete-submission envelope: no <SEC-DOCUMENT> or "
            "<IMS-DOCUMENT> marker appears in the first 8 KiB"
        )

    documents: list[FiledDocument] = []
    for open_match in _DOCUMENT_OPEN.finditer(submission):
        block_start = open_match.end()
        close_match = _DOCUMENT_CLOSE.search(submission, block_start)
        block_end = close_match.start() if close_match else len(submission)

        text_open = _TEXT_OPEN.search(submission, block_start, block_end)
        if text_open is None:
            # A <DOCUMENT> with no <TEXT> carries no content. It is reported with a zero-length
            # range rather than dropped, because a member the envelope declares and this listing
            # omits is exactly the silent loss this module exists to prevent.
            start = end = block_start
            header_end = block_end
        else:
            start = text_open.end()
            text_close = _TEXT_CLOSE.search(submission, start, block_end)
            end = text_close.start() if text_close else block_end
            header_end = text_open.start()

        declared: dict[str, str] = {}
        for tag in _TAG_VALUE.finditer(submission, block_start, header_end):
            name = tag.group(1).decode("ascii")
            if name not in declared:
                declared[name] = tag.group(2).decode("utf-8", errors="replace").strip()

        raw_sequence = declared.get("SEQUENCE", "")
        documents.append(
            FiledDocument(
                sequence=int(raw_sequence) if raw_sequence.isdigit() else None,
                declared_type=declared.get("TYPE", ""),
                filename=declared.get("FILENAME", ""),
                description=declared.get("DESCRIPTION", ""),
                start_offset=start,
                end_offset=end,
            )
        )
    return tuple(documents)


def declared_document_count(submission: bytes) -> int | None:
    """The document count the submission header itself declares, or None when it declares none.

    Kept separate from `len(list_filed_documents(...))` deliberately. When the two disagree, the
    envelope and its own header disagree, and a caller should see both numbers rather than a
    reconciliation this module invented.
    """
    raw = submission_header(submission).get("PUBLIC DOCUMENT COUNT", "")
    return int(raw) if raw.isdigit() else None
