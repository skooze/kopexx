"""Transport disposition of one filed member — what the BYTES are, never what they mean.

THE LINE THIS MODULE MUST NOT CROSS. rules.md invariant 14 and section 21 rule 1 forbid backend
code from deciding what filing content MEANS. Nothing here asks whether a member is important,
whether it is MD&A, whether it is a footnote, whether it belongs to the financial statements, or
whether one member covers the same ground as another. The deleted classifier asked exactly those
questions, ruled that a courtesy PDF duplicated the primary document, and suppressed a filed
source range on that judgement (ADR-0017).

WHAT IT ASKS INSTEAD, AND THE ONLY EVIDENCE IT MAY USE:

    is this an image?                   byte signature
    is this a machine-only artifact?    byte signature, filename extension, XML root namespace
    is this SEC's renderer output?      the DECLARED description EDGAR itself writes
    is this the flat duplicate?         whether individually addressable members exist
    anything else                       UNKNOWN_REQUIRES_REVIEW — it fails closed

FAILING CLOSED IS THE WHOLE DESIGN. An unrecognised member is not quietly dropped and not quietly
submitted. It appears in the run plan with its bytes and its declared type, and a person decides.
A dropped member is lost content; a submitted one may be an unusable binary charged as input
tokens. Neither is something code should choose on a hunch.

    EX-27 IS A WORKED EXAMPLE. A financial data schedule is filed text and is dispositioned
    PARSER_INPUT_TEXT here, exactly like every other filed text member. The offline corpus tool
    called it "preserved numeric evidence", which is a judgement about what it is FOR. This module
    is not allowed to have that opinion, and the difference is the whole point.

HISTORICAL-FORMAT, DATED OBSERVATION, MEASURED 2026-08-03. EDGAR's dissemination of a modern
filing interleaves SEC's own renderer output with the filer's documents inside the same envelope.
Measured on accession 0000794367-25-000156: documents 1 through 8 are the filer's (types 10-Q/A,
EX-31.1, EX-31.2, EX-32.2, EX-101.SCH, EX-101.LAB, EX-101.PRE, GRAPHIC); documents 10 through 18
are SEC's renderer artifacts (R1.htm, Show.js, report.css, FilingSummary.xml, MetaLinks.json, the
XBRL zip and the extracted instance), every one of them carrying the DECLARED description
`IDEA: XBRL DOCUMENT` — IDEA being SEC's own Interactive Data Electronic Applications renderer.
That declared marker is what this module reads. It is a transport label EDGAR writes, in the same
sense as `<TYPE>`, and it is recorded here as an observation with a date rather than as a
permanent constant.

Two further facts from the same measurement, both reported rather than reconciled: the envelope's
own `PUBLIC DOCUMENT COUNT` header said 16 while the envelope contained 15 `<DOCUMENT>` blocks,
and the sequence numbers were non-contiguous, skipping 9, 13 and 15.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final


class MemberDisposition(StrEnum):
    """What is done with one filed member, and why, in one word."""

    #: Human-readable filed text. Goes to the parsing model intact.
    PARSER_INPUT_TEXT = "PARSER_INPUT_TEXT"
    #: A filed raster image. Goes to a MULTIMODAL parsing model intact; reported unanalysed
    #: otherwise. It is never described, summarised or transcribed by backend code.
    PARSER_INPUT_IMAGE = "PARSER_INPUT_IMAGE"
    #: An artifact no language model can read as prose: an archive, a spreadsheet, a stylesheet,
    #: a script, a schema, or an XBRL linkbase or instance.
    MACHINE_ONLY = "MACHINE_ONLY"
    #: SEC's own renderer output, declared as such by EDGAR.
    SEC_GENERATED_RENDERING = "SEC_GENERATED_RENDERING"
    #: The flat complete submission, when its members are individually addressable and are being
    #: sent as themselves. Sending both would submit identical content twice.
    DUPLICATE_COMPLETE_SUBMISSION = "DUPLICATE_COMPLETE_SUBMISSION"
    #: The member has no individual URL on EDGAR and reaches the model INSIDE the complete
    #: submission, which is submitted intact. Its content is covered; its bytes are not counted a
    #: second time. Pre-2001 filings are entirely this case.
    INSIDE_COMPLETE_SUBMISSION = "INSIDE_COMPLETE_SUBMISSION"
    #: Nothing above matched. Fails closed and appears in the run plan.
    UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"


#: Dispositions whose members are sent to the model as their own content block, and whose bytes
#: are therefore counted toward the request.
SUBMITTED_DISPOSITIONS: Final[frozenset[MemberDisposition]] = frozenset(
    {MemberDisposition.PARSER_INPUT_TEXT, MemberDisposition.PARSER_INPUT_IMAGE}
)

#: Dispositions whose content REACHES the model, whether as its own block, inside one, or as the
#: same bytes travelling under another name. Coverage is measured against this set; request size is
#: measured against SUBMITTED_DISPOSITIONS. Keeping them apart is what stops a pre-2001 filing from
#: either double-counting its own bytes or reporting its exhibits as uncovered.
#:
#: DUPLICATE_COMPLETE_SUBMISSION IS COVERED, AND LEAVING IT OUT WAS A DEFECT. In addressable mode
#: the flat submission is a byte-for-byte duplicate of members that ARE sent, so its content
#: reaches the model in full — it is simply not sent twice. Counting it as uncovered made every
#: modern filing report its own complete submission as "content that did not reach the model", and
#: since it is usually the largest member in the set, it made complete coverage unreachable for the
#: entire post-2001 era. A false claim that something was left out is the same class of defect as a
#: false claim that nothing was.
COVERED_DISPOSITIONS: Final[frozenset[MemberDisposition]] = SUBMITTED_DISPOSITIONS | {
    MemberDisposition.INSIDE_COMPLETE_SUBMISSION,
    MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION,
}

#: EDGAR's declared marker for its own Interactive Data renderer output. Read verbatim from the
#: `<DESCRIPTION>` field; see the module docstring for the measurement behind it.
SEC_RENDERER_DESCRIPTION_PREFIX: Final[str] = "IDEA:"

# Byte signatures. A magic number is what the bytes ARE; an extension is what someone called them.
_IMAGE_SIGNATURES: Final[tuple[tuple[bytes, str], ...]] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)

_ARCHIVE_SIGNATURES: Final[tuple[bytes, ...]] = (
    b"PK\x03\x04",  # zip, and therefore xlsx and docx
    b"\x1f\x8b",  # gzip
    b"%PDF-",  # a PDF is filed content but is not text a text-only path can carry
)

_MACHINE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".zip", ".xlsx", ".xls", ".css", ".js", ".json", ".xsd"}
)

_TEXT_EXTENSIONS: Final[frozenset[str]] = frozenset({".htm", ".html", ".txt", ".sgml", ".text"})

# An XML document whose root carries one of these is a machine artifact regardless of who filed it.
_XBRL_ROOT_MARKERS: Final[tuple[bytes, ...]] = (
    b"http://www.xbrl.org/",
    b"http://www.w3.org/1999/xlink",
    b"<xbrl",
    b"<link:linkbase",
    b"<xsd:schema",
    b"<schema",
)

_XML_DECLARATION = re.compile(rb"^\s*<\?xml\b", re.IGNORECASE)
_HTML_MARKER = re.compile(rb"<(html|head|body|p|div|table|font)\b", re.IGNORECASE)


def image_format(data: bytes) -> str | None:
    """The image format these bytes actually are, or None.

    WEBP is deliberately absent: it is `RIFF....WEBP`, no filer in the measured corpus has filed
    one, and adding a format nothing has ever produced would be an untested branch pretending to
    be coverage. Add it when a filing produces one.
    """
    for signature, name in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return name
    return None


def _looks_like_xbrl_xml(data: bytes) -> bool:
    head = data[:4096]
    if not _XML_DECLARATION.match(head) and not head.lstrip().startswith(b"<"):
        return False
    return any(marker in head for marker in _XBRL_ROOT_MARKERS)


def _looks_like_text(data: bytes) -> bool:
    """Whether the bytes are plain text or markup rather than a binary blob.

    A NUL byte in the first block is the practical discriminator: no SEC-filed text document
    contains one, and every binary format in the corpus does.
    """
    head = data[:8192]
    if b"\x00" in head:
        return False
    return not any(head.startswith(signature) for signature in _ARCHIVE_SIGNATURES)


def disposition_for(
    *,
    filename: str,
    declared_type: str,
    description: str,
    data: bytes,
    is_complete_submission: bool = False,
    members_separately_addressable: bool = False,
) -> tuple[MemberDisposition, str]:
    """The disposition of one member, and the transport evidence for it.

    Returns (disposition, evidence). The evidence string is shown in the run plan, so a person can
    see exactly which byte signature, extension or declared field produced the answer instead of
    being told a category.
    """
    lowered = filename.lower()
    extension = lowered[lowered.rfind(".") :] if "." in lowered else ""

    if is_complete_submission and members_separately_addressable:
        return (
            MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION,
            "the complete submission is the flat concatenation of members that are individually "
            "addressable and are being sent as themselves; sending both submits identical "
            "content twice",
        )

    if description.strip().upper().startswith(SEC_RENDERER_DESCRIPTION_PREFIX):
        return (
            MemberDisposition.SEC_GENERATED_RENDERING,
            f"EDGAR declared this document's description as {description.strip()!r}, its own "
            "Interactive Data renderer marker; it was generated by SEC, not filed by the filer",
        )

    found_image = image_format(data)
    if found_image is not None:
        return (
            MemberDisposition.PARSER_INPUT_IMAGE,
            f"byte signature identifies a {found_image} image",
        )

    if any(data.startswith(signature) for signature in _ARCHIVE_SIGNATURES):
        return (
            MemberDisposition.MACHINE_ONLY,
            "byte signature identifies an archive or a binary document container",
        )

    if extension in _MACHINE_EXTENSIONS:
        return (
            MemberDisposition.MACHINE_ONLY,
            f"filename extension {extension!r} names a machine-only artifact",
        )

    # THE HTML ROOT IS CHECKED BEFORE THE XBRL ROOT, AND THIS ORDERING IS THE WHOLE RULE.
    #
    # An inline-XBRL primary document IS XHTML. Measured on accession 0000794367-25-000156, the
    # primary document opens with `<?xml version='1.0' encoding='ASCII'?>` and then
    # `<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" ... xmlns:xlink=...>`, and it carries
    # 87 div, 110 span and 10 table elements of ordinary human-readable prose and tables.
    #
    # With the XBRL test first, that document — the single most important member of a modern
    # filing — was dispositioned MACHINE_ONLY and silently dropped from the source set. The run
    # still looked healthy: three certification exhibits and an image were submitted, coverage
    # counts reconciled against what was submitted, and nothing anywhere said the 10-Q itself had
    # not been sent. That is the exact failure mode the complete-content invariant exists to
    # prevent, and it was caught by reading a disposition table rather than by any assertion.
    if _HTML_MARKER.search(data[:16384]):
        return (
            MemberDisposition.PARSER_INPUT_TEXT,
            "the document carries an HTML or XHTML root, so it is human-readable markup. Inline "
            "XBRL is XHTML: an XML declaration and XBRL namespaces on the root do NOT make it a "
            "machine artifact, and treating them that way drops the primary document",
        )

    if _looks_like_xbrl_xml(data):
        return (
            MemberDisposition.MACHINE_ONLY,
            "the XML root carries an XBRL, XLink or XML-Schema namespace and the document has no "
            "HTML root, so it is a machine rendering rather than prose",
        )

    if not _looks_like_text(data):
        return (
            MemberDisposition.UNKNOWN_REQUIRES_REVIEW,
            "the bytes are not text and match no known image or archive signature",
        )

    if extension in _TEXT_EXTENSIONS or _HTML_MARKER.search(data[:8192]) or not extension:
        return (
            MemberDisposition.PARSER_INPUT_TEXT,
            f"the bytes decode as text; declared type {declared_type or 'none'!r}, "
            f"extension {extension or 'none'!r}",
        )

    return (
        MemberDisposition.UNKNOWN_REQUIRES_REVIEW,
        f"the bytes are text but the extension {extension!r} matches no known transport role; "
        "an unknown role fails closed rather than being guessed in either direction",
    )
