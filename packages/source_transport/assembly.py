"""Assemble the complete relevant human-readable source set for one filing, mechanically.

THE ORDER OF OPERATIONS IS THE PRODUCT REQUIREMENT, NOT AN OPTIMISATION.

    1  resolve filing identity as (CIK, accession)
    2  ask the local inventory for the complete submission
    3  verify its byte count and its SHA-256 against the record
    4  fetch it from SEC only if it is missing, incomplete or hash-invalid
    5  list the filer's declared documents from the preserved bytes
    6  decide, per member, from TRANSPORT EVIDENCE ONLY, what it is
    7  reuse every valid preserved member; fetch only the rest
    8  preserve whatever is fetched, byte for byte, with provenance
    9  never overwrite a valid original

TWO MODES, DECIDED BY EDGAR AND NOT BY US.

    ADDRESSABLE      the envelope declares a <FILENAME> per document, so each member has its own
                     EDGAR URL. Each is fetched or reused as itself and sent as its own content
                     block. The flat complete submission becomes a DUPLICATE: sending both would
                     submit identical content twice, and its members are not byte-identical to the
                     addressable objects anyway — measured on accession 0000794367-25-000156, the
                     dissemination wraps each member in a `<XBRL>` element, so the primary document
                     is 39,271 bytes inside the submission and 39,256 bytes as its own object.
                     A 15-byte difference defeats admission by provenance, which is exactly why
                     members are fetched rather than sliced out.

    NON-ADDRESSABLE  the envelope declares no filenames, EDGAR publishes no per-document URL, and
                     the complete submission is the only retrievable artifact. It IS the source
                     set and is sent intact. Its declared documents are still listed, each marked
                     INSIDE_COMPLETE_SUBMISSION, so the run plan shows what the one artifact
                     contains without counting its bytes twice.

WHAT THIS MODULE NEVER DOES. It does not decide which members matter, does not drop a member for
being boilerplate, routine, an exhibit, a certification or a signature block, and does not decide
that two members say the same thing. Every filed member appears in the result with a disposition
and the transport evidence for it, and anything unrecognised fails closed.
"""

from __future__ import annotations

from typing import Protocol

from packages.filing_acquisition import (
    declared_document_count,
    list_filed_documents,
    looks_like_complete_submission,
)
from packages.sec_identity import accession_dashed, cik_padded, complete_submission_url
from packages.storage import sha256_bytes

from .decoding import decode_source
from .dispositions import MemberDisposition, disposition_for, image_format
from .errors import SourceIntegrityError, SourceMemberMissingError
from .inventory import SourceInventory, verify
from .records import PreservedObject, SourceMember, SourceSet


class MemberFetcher(Protocol):
    """Whatever can retrieve a filing member from SEC and preserve it byte-exactly.

    Kept as a protocol so this module holds no HTTP client, no rate limiter and no credential.
    That is not decoration: it means the whole assembly path is exercised in tests with no
    network at all, which is why the suite has no environmental precondition.
    """

    def fetch(self, cik: str, accession: str, filename: str) -> tuple[PreservedObject, bytes]:
        """Retrieve and preserve one member, returning its provenance and its exact bytes."""


class RefusingFetcher:
    """A fetcher that refuses, for runs that must not generate SEC traffic.

    Not a no-op: it raises with the member named. A silent skip would produce an incomplete
    source set that looked complete, which is the failure this whole package exists to prevent.
    """

    def fetch(self, cik: str, accession: str, filename: str) -> tuple[PreservedObject, bytes]:
        raise SourceMemberMissingError(
            f"{filename!r} for filing ({cik_padded(cik)}, {accession_dashed(accession)}) is not "
            "held locally and this run is configured not to contact SEC"
        )


def _load_or_fetch(
    inventory: SourceInventory,
    fetcher: MemberFetcher,
    *,
    cik: str,
    accession: str,
    filename: str,
) -> tuple[PreservedObject, bytes]:
    """Reuse a VALID preserved member, or acquire it. Never both, never neither.

    STEP 7 OF THE RAW-FIRST SEQUENCE IS "fetch only what is missing, incomplete OR HASH-INVALID",
    and this function used to implement only the first of the three. A held member whose bytes no
    longer matched its recorded digest raised out of `verify` and killed the whole assembly —
    while `SourceIntegrityError`'s own docstring said the safe response is "to refuse it and
    re-acquire". It refused. It never re-acquired.

    A corrupted local object is now repaired from SEC, and the corruption is still not trusted: the
    stored bytes are discarded rather than adopted, and nothing updates a recorded hash to match
    whatever happens to be on disk.
    """
    held = inventory.find(cik, accession, filename)
    if held is not None:
        try:
            data = inventory.read(held)
            verify(held, data)
            return held, data
        except (SourceIntegrityError, OSError, ValueError):
            # Fall through to acquisition. The preserved original is authoritative, and a stored
            # copy that no longer matches its record is not the original.
            pass
    return fetcher.fetch(cik, accession, filename)


def load_complete_submission(
    inventory: SourceInventory,
    fetcher: MemberFetcher,
    *,
    cik: str,
    accession: str,
) -> tuple[PreservedObject, bytes]:
    """The preserved complete submission for one filing, reused if held and fetched if not."""
    dashed = accession_dashed(accession)
    obj, data = _load_or_fetch(
        inventory, fetcher, cik=cik, accession=accession, filename=f"{dashed}.txt"
    )
    if not looks_like_complete_submission(data):
        raise SourceMemberMissingError(
            f"the artifact preserved as the complete submission for {dashed} is not an EDGAR "
            "submission envelope. SEC answers a bare folder URL with HTTP 200 and a directory "
            "listing, and a throttle refusal is an HTML page — both would list zero documents."
        )
    return obj, data


def assemble_source_set(
    inventory: SourceInventory,
    fetcher: MemberFetcher,
    *,
    cik: str,
    accession: str,
    form_as_filed: str,
    filing_date: str,
    issuer_label: str,
    transport_era: str,
    report_period: str | None = None,
) -> SourceSet:
    """Every filed member of one accession, dispositioned, with content loaded for the submitted."""
    padded = cik_padded(cik)
    dashed = accession_dashed(accession)
    submission_object, submission_bytes = load_complete_submission(
        inventory, fetcher, cik=padded, accession=dashed
    )

    documents = list_filed_documents(submission_bytes)
    addressable = any(document.separately_addressable for document in documents)
    members: list[SourceMember] = []

    # The folder form and the flat root form are both valid SEC URLs for the same object.
    # Whichever one actually retrieved these bytes is the one recorded; the helper is the
    # fallback for a member that came from an inventory with no URL of its own.
    submission_url = submission_object.source_url or complete_submission_url(padded, dashed)
    if addressable:
        # The flat submission is the duplicate. It is still RECORDED, with its hash, because it is
        # the artifact the document listing was read from and the provenance has to be traceable.
        members.append(
            SourceMember(
                sequence=None,
                declared_type="",
                description="",
                filename=f"{dashed}.txt",
                disposition=MemberDisposition.DUPLICATE_COMPLETE_SUBMISSION,
                disposition_evidence=(
                    "members are individually addressable and are sent as themselves; the flat "
                    "submission is the same content a second time"
                ),
                sha256=submission_object.sha256 or sha256_bytes(submission_bytes),
                byte_count=len(submission_bytes),
                source_url=submission_url,
                separately_addressable=True,
                reused=submission_object.reused,
            )
        )

    for document in documents:
        if not addressable:
            # No individual URL exists. The content travels inside the complete submission.
            members.append(
                SourceMember(
                    sequence=document.sequence,
                    declared_type=document.declared_type,
                    description=document.description,
                    filename="",
                    disposition=MemberDisposition.INSIDE_COMPLETE_SUBMISSION,
                    disposition_evidence=(
                        "the envelope declares no filename for this document, so EDGAR publishes "
                        "no per-document URL; it reaches the model inside the complete submission"
                    ),
                    sha256=sha256_bytes(document.extract(submission_bytes)),
                    byte_count=document.byte_count,
                    source_url=submission_url,
                    separately_addressable=False,
                    reused=submission_object.reused,
                )
            )
            continue

        member_object, member_bytes = _load_or_fetch(
            inventory, fetcher, cik=padded, accession=dashed, filename=document.filename
        )
        disposition, evidence = disposition_for(
            filename=document.filename,
            declared_type=document.declared_type,
            description=document.description,
            data=member_bytes,
            is_complete_submission=False,
            members_separately_addressable=True,
        )
        text = None
        encoding = None
        if disposition is MemberDisposition.PARSER_INPUT_TEXT:
            decoded = decode_source(member_bytes)
            text = decoded.text
            encoding = decoded.codec
        members.append(
            SourceMember(
                sequence=document.sequence,
                declared_type=document.declared_type,
                description=document.description,
                filename=document.filename,
                disposition=disposition,
                disposition_evidence=evidence,
                sha256=member_object.sha256 or sha256_bytes(member_bytes),
                byte_count=len(member_bytes),
                source_url=member_object.source_url,
                separately_addressable=True,
                reused=member_object.reused,
                encoding=encoding,
                image_format=image_format(member_bytes),
                text=text,
                image_bytes=(
                    member_bytes if disposition is MemberDisposition.PARSER_INPUT_IMAGE else None
                ),
            )
        )

    if not addressable:
        decoded = decode_source(submission_bytes)
        members.insert(
            0,
            SourceMember(
                sequence=0,
                declared_type=form_as_filed,
                description="complete submission",
                filename=f"{dashed}.txt",
                disposition=MemberDisposition.PARSER_INPUT_TEXT,
                disposition_evidence=(
                    "EDGAR exposes no individually addressable document for this filing, so the "
                    "complete submission IS the complete relevant human-readable source set and "
                    "is sent intact"
                ),
                sha256=submission_object.sha256 or sha256_bytes(submission_bytes),
                byte_count=len(submission_bytes),
                source_url=submission_url,
                separately_addressable=False,
                reused=submission_object.reused,
                encoding=decoded.codec,
                text=decoded.text,
            ),
        )

    return SourceSet(
        cik=padded,
        accession=dashed,
        form_as_filed=form_as_filed,
        filing_date=filing_date,
        report_period=report_period,
        issuer_label=issuer_label,
        transport_era=transport_era,
        members=tuple(members),
        declared_document_count=declared_document_count(submission_bytes),
        listed_document_count=len(documents),
        members_separately_addressable=addressable,
    )
