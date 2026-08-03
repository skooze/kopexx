"""What a resolved source set is made of, and how it serialises into the evaluation store.

EVERY RECORD IS TRANSPORT. A member carries bytes, a hash, a size, an encoding, a declared type
the filer typed, and a disposition with the evidence behind it. None of it says what the member
means. That is the selected parsing model's job.

THE SOURCE-SET IDENTITY IS A HASH OF HASHES. Reuse identity eventually has to include "the same
source set" (roadmap.md Phase 4), and "the same accession" is not the same thing: a member fetched
later, a member that failed to fetch, or a differently dispositioned member all produce a
different set from the same accession. Hashing the ordered (filename, sha256) pairs of the
SUBMITTED members makes that difference visible in one value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.storage import sha256_text

from .dispositions import COVERED_DISPOSITIONS, SUBMITTED_DISPOSITIONS, MemberDisposition


@dataclass(frozen=True)
class PreservedObject:
    """One byte-exact original artifact this project already holds, or has just fetched."""

    filename: str
    sha256: str
    byte_count: int
    source_url: str
    locator: str
    acquired_at: str
    acquisition_method: str
    reused: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "source_url": self.source_url,
            "locator": self.locator,
            "acquired_at": self.acquired_at,
            "acquisition_method": self.acquisition_method,
            "reused": self.reused,
        }


@dataclass(frozen=True)
class SourceMember:
    """One filed member with its transport disposition and its provenance.

    `text` and `image_bytes` hold the member's content when it is going to the model, and are
    absent otherwise. They are NOT serialised: the bytes live in the object store under their own
    hash, and a manifest that inlined a 4 MB filing would be a second copy that can drift from
    the first.
    """

    sequence: int | None
    declared_type: str
    description: str
    filename: str
    disposition: MemberDisposition
    disposition_evidence: str
    sha256: str
    byte_count: int
    source_url: str
    separately_addressable: bool
    reused: bool
    encoding: str | None = None
    image_format: str | None = None
    text: str | None = field(default=None, repr=False, compare=False)
    image_bytes: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def submitted(self) -> bool:
        """Whether this member is sent as its own content block, and its bytes counted."""
        return self.disposition in SUBMITTED_DISPOSITIONS

    @property
    def covered(self) -> bool:
        """Whether this member's content reaches the model at all, however it travels."""
        return self.disposition in COVERED_DISPOSITIONS

    def to_mapping(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "declared_type": self.declared_type,
            "description": self.description,
            "filename": self.filename,
            "disposition": self.disposition.value,
            "disposition_evidence": self.disposition_evidence,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "source_url": self.source_url,
            "separately_addressable": self.separately_addressable,
            "reused": self.reused,
            "encoding": self.encoding,
            "image_format": self.image_format,
            "submitted": self.submitted,
            "covered": self.covered,
        }


@dataclass(frozen=True)
class SourceSet:
    """Every filed member of one accession, dispositioned, with the subset actually submitted."""

    cik: str
    accession: str
    form_as_filed: str
    filing_date: str
    report_period: str | None
    issuer_label: str
    transport_era: str
    members: tuple[SourceMember, ...]
    declared_document_count: int | None
    listed_document_count: int
    members_separately_addressable: bool

    @property
    def submitted_members(self) -> tuple[SourceMember, ...]:
        return tuple(m for m in self.members if m.submitted)

    @property
    def text_members(self) -> tuple[SourceMember, ...]:
        return tuple(
            m for m in self.members if m.disposition is MemberDisposition.PARSER_INPUT_TEXT
        )

    @property
    def image_members(self) -> tuple[SourceMember, ...]:
        return tuple(
            m for m in self.members if m.disposition is MemberDisposition.PARSER_INPUT_IMAGE
        )

    @property
    def unknown_members(self) -> tuple[SourceMember, ...]:
        return tuple(
            m for m in self.members if m.disposition is MemberDisposition.UNKNOWN_REQUIRES_REVIEW
        )

    @property
    def uncovered_members(self) -> tuple[SourceMember, ...]:
        """Filed members whose content does NOT reach the model.

        This is the honest answer to "what was left out". It is shown in the run plan and in the
        parsed view; a run never reports complete coverage while it is non-empty.
        """
        return tuple(m for m in self.members if not m.covered)

    @property
    def submitted_bytes(self) -> int:
        return sum(m.byte_count for m in self.submitted_members)

    @property
    def total_bytes(self) -> int:
        return sum(m.byte_count for m in self.members)

    @property
    def reused_count(self) -> int:
        return sum(1 for m in self.members if m.reused)

    @property
    def fetched_count(self) -> int:
        return sum(1 for m in self.members if not m.reused)

    @property
    def source_set_id(self) -> str:
        """A stable identity for exactly this submitted set of bytes, in this order."""
        joined = "\n".join(f"{m.filename}:{m.sha256}" for m in self.submitted_members)
        return sha256_text(joined)

    def counts_by_disposition(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for member in self.members:
            counts[member.disposition.value] = counts.get(member.disposition.value, 0) + 1
        return counts

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "source-set-v1",
            "cik": self.cik,
            "accession": self.accession,
            "form_as_filed": self.form_as_filed,
            "filing_date": self.filing_date,
            "report_period": self.report_period,
            "issuer_label": self.issuer_label,
            "transport_era": self.transport_era,
            "source_set_id": self.source_set_id,
            "members_separately_addressable": self.members_separately_addressable,
            "declared_document_count": self.declared_document_count,
            "listed_document_count": self.listed_document_count,
            "counts_by_disposition": self.counts_by_disposition(),
            "submitted_member_count": len(self.submitted_members),
            "submitted_bytes": self.submitted_bytes,
            "total_bytes": self.total_bytes,
            "reused_members": self.reused_count,
            "fetched_members": self.fetched_count,
            "members": [m.to_mapping() for m in self.members],
        }
