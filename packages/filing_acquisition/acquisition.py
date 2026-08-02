"""Acquire the source objects for one filing and preserve them with provenance.

Only the inline-XBRL era is implemented. That covers every filing from roughly 2019 onward and is
what Sprint 4 needs. The other three eras raise rather than guess, because the difference between
them is not cosmetic: a pre-2001 filing has no primary document name, and a URL built from the
empty string returns HTTP 200 with a directory listing.

What is acquired per filing, and why each one is needed:

    primary document    the narrative, and the source of note headings
    -xbrl.zip           the instance plus every linkbase, about a third the size of the
                        complete submission text file
    extracted instance  SEC publishes its own inline-XBRL extraction, so we never implement
                        iXBRL transformation ourselves
    FilingSummary.xml   the renderer report inventory: menu categories, role URIs, report
                        names. This is what canonical footnote grouping reads.
    schema (.xsd)       carries the statement and disclosure role classification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packages.sec_identity import (
    accession_undashed,
    cik_archive,
    extracted_instance_url,
    filing_folder_url,
    filing_xbrl_zip_url,
    primary_document_url,
)
from packages.storage import sha256_bytes

from .errors import MissingPrimaryDocumentError, UnsupportedEraError

SUPPORTED_ERAS = ("inline_xbrl",)


@dataclass(frozen=True)
class AcquiredObject:
    """One preserved file with everything needed to prove where it came from."""

    role: str
    url: str
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str
    retrieved_at: str
    reused: bool = False

    def as_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "url": self.url,
            "storage_key": self.storage_key,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "retrieved_at": self.retrieved_at,
            "reused": self.reused,
        }


@dataclass
class AcquisitionResult:
    """Every object preserved for one filing."""

    accession: str
    cik: str
    form: str
    era: str
    strategy: str
    objects: list[AcquiredObject] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(o.size_bytes for o in self.objects)

    @property
    def downloaded(self) -> int:
        return sum(1 for o in self.objects if not o.reused)

    @property
    def reused(self) -> int:
        return sum(1 for o in self.objects if o.reused)

    def key_for(self, role: str) -> str | None:
        for obj in self.objects:
            if obj.role == role:
                return obj.storage_key
        return None

    def as_record(self) -> dict[str, object]:
        return {
            "accession": self.accession,
            "cik": self.cik,
            "form": self.form,
            "era": self.era,
            "strategy": self.strategy,
            "object_count": len(self.objects),
            "total_bytes": self.total_bytes,
            "objects": [o.as_record() for o in self.objects],
        }


def storage_key(cik: str, accession: str, filename: str) -> str:
    """Where a filing object lives in the object store.

    Keyed on the ISSUER's CIK, never the accession prefix. The prefix belongs to whichever filing
    agent transmitted the document and is frequently a different company.
    """
    return f"filings/{cik}/{accession_undashed(accession)}/{filename}"


def _content_type(filename: str) -> str:
    if filename.endswith(".zip"):
        return "application/zip"
    if filename.endswith((".xml", ".xsd")):
        return "application/xml"
    if filename.endswith((".htm", ".html")):
        return "text/html"
    return "application/octet-stream"


def plan_inline_xbrl(cik: str, accession: str, primary_document: str) -> list[tuple[str, str, str]]:
    """(role, url, filename) for each object an inline-XBRL filing needs."""
    if not primary_document:
        raise MissingPrimaryDocumentError(accession)

    stem = primary_document.rsplit(".", 1)[0]
    folder = filing_folder_url(cik, accession)
    return [
        (
            "primary_document",
            primary_document_url(cik, accession, primary_document),
            primary_document,
        ),
        (
            "xbrl_package",
            filing_xbrl_zip_url(cik, accession),
            f"{accession}-xbrl.zip",
        ),
        (
            "extracted_instance",
            extracted_instance_url(cik, accession, primary_document),
            f"{stem}_htm.xml",
        ),
        ("filing_summary", f"{folder}/FilingSummary.xml", "FilingSummary.xml"),
        ("schema", f"{folder}/{stem}.xsd", f"{stem}.xsd"),
    ]


def acquire_filing(
    client,
    store,
    filing,
    *,
    workspace: str | Path,
    force: bool = False,
) -> AcquisitionResult:
    """Download and preserve every source object for one filing.

    Idempotent by content address: an object already in the store with the same key is reused
    without a request, and its hash is recomputed from what is stored rather than trusted from a
    previous run's bookkeeping.
    """
    if filing.era not in SUPPORTED_ERAS:
        raise UnsupportedEraError(filing.accession, filing.era)

    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    archive_cik = str(cik_archive(filing.cik))

    result = AcquisitionResult(
        accession=filing.accession,
        cik=filing.cik,
        form=filing.form,
        era=filing.era,
        strategy="inline_xbrl_bundle",
    )

    for role, url, filename in plan_inline_xbrl(
        archive_cik, filing.accession, filing.primary_document
    ):
        key = storage_key(filing.cik, filing.accession, filename)

        if not force and store.exists(key):
            data = store.get_bytes(key)
            result.objects.append(
                AcquiredObject(
                    role=role,
                    url=url,
                    storage_key=key,
                    sha256=sha256_bytes(data),
                    size_bytes=len(data),
                    content_type=_content_type(filename),
                    retrieved_at=datetime.now(UTC).isoformat(),
                    reused=True,
                )
            )
            continue

        destination = workspace / filename
        fetched = client.download(
            url,
            destination,
            expect_zip=filename.endswith(".zip"),
            # A filing's primary document IS HTML. The client's blanket HTML rejection exists to
            # catch error pages and folder indexes; the directory-listing check still runs here,
            # which is the part that actually matters for this URL shape.
            expect_html=filename.endswith((".htm", ".html")),
        )
        payload = destination.read_bytes()
        store.put_bytes(key, payload, content_type=_content_type(filename))
        destination.unlink(missing_ok=True)

        result.objects.append(
            AcquiredObject(
                role=role,
                url=url,
                storage_key=key,
                sha256=fetched.sha256,
                size_bytes=fetched.size_bytes,
                content_type=fetched.content_type or _content_type(filename),
                retrieved_at=fetched.retrieved_at,
                reused=False,
            )
        )

    return result
