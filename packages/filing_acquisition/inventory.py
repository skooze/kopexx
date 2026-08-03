"""The authoritative accession document inventory, and classification of every filed document.

WHY THIS EXISTS. `plan_inline_xbrl` acquires five objects: the primary document, the XBRL package,
the SEC-extracted instance, `FilingSummary.xml`, and the schema. That is not the filed submission.
Apple's FY2025 10-K accession lists **seventeen filed documents**, including a description of
securities, a subsidiaries list, an auditor consent, three officer certifications, and two
graphics — none of which was ever fetched. And `filing_document`, the table whose entire purpose
is to inventory acquired objects, held zero rows for four acquired filings.

THE FILER'S OWN DECLARED TYPE IS THE CLASSIFICATION, NOT THE FILENAME. The accession index page
carries a document table whose `Type` column is what the filer declared: `EX-31.1`, `EX-23.1`,
`GRAPHIC`, `EX-101.SCH`. Classifying by filename instead is guesswork — Apple names its
certification `a10-kexhibit31109272025.htm`, from which "exhibit 31.1" is recoverable only by
assuming where the digits split. A filename heuristic remains as a documented fallback for the
case where a row carries no type at all.

TWO LISTINGS, TWO DIFFERENT THINGS, AND CONFLATING THEM IS THE TRAP:

    the index document table   the documents the ISSUER FILED. 17 for Apple's FY2025 10-K.
                               This is what an accession inventory means and what coverage
                               reconciles against.

    index.json                 every file in the folder, 93 for the same accession, because it
                               also contains the R*.htm reports, MetaLinks.json, and the XLSX
                               that SEC's own VIEWER generated. Those were never filed by anyone
                               and carry no disclosure.

Reconciling filed content against the 93 would demand extraction of 76 renderer artifacts;
reconciling the folder against the 17 would report files missing that were never filed.

DOCUMENTED SEC TRAPS, all previously verified in `docs/sec/document-acquisition.md`:

    `index.json`'s `type` is the renderer's SPRITE ICON FILENAME — `text.gif`, `image2.gif` — and
    never a MIME type.

    `size` is an EMPTY STRING for some entries, so `int(item["size"])` raises and any folder total
    computed from it under-counts.

    The complete submission `.txt` concatenates every other document in the accession. Registering
    it as human-readable would double-count every disclosure in the filing.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any

from packages.sec_identity import cik_archive, filing_folder_url

# --- document classes ------------------------------------------------------------------------
# Mirrors `packages.persistence.models.DOCUMENT_CLASSES`, the storage vocabulary. A finer ROLE is
# recorded alongside, because "human-readable" does not distinguish a certification from a
# subsidiaries list and the coverage report needs to.

HUMAN_READABLE = "HUMAN_READABLE"
MACHINE_ARTIFACT = "MACHINE_ARTIFACT"
GRAPHIC = "GRAPHIC"
UNKNOWN = "UNKNOWN"

ROLE_PRIMARY = "primary_document"
ROLE_EXHIBIT = "human_readable_exhibit"
ROLE_CERTIFICATION = "certification"
ROLE_CONSENT = "consent"
ROLE_SCHEDULE = "financial_schedule"
ROLE_GRAPHIC = "graphic"
ROLE_MACHINE = "machine_evidence"
ROLE_COMPLETE_SUBMISSION = "complete_submission_text"
ROLE_OTHER = "other_filed_attachment"

# Declared types, from Item 601 of Regulation S-K and the EDGAR document-type list.
PRIMARY_TYPES = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A", "DEF 14A", "DEFA14A"})
CERTIFICATION_TYPE = re.compile(r"^EX-3[12](\.\d+)?$", re.IGNORECASE)
CONSENT_TYPE = re.compile(r"^EX-23(\.\d+)?$", re.IGNORECASE)
SCHEDULE_TYPE = re.compile(r"^EX-99(\.\d+)?$", re.IGNORECASE)
# EX-101.* and EX-100.* are the XBRL taxonomy exhibits: schema and the four linkbases.
XBRL_EXHIBIT_TYPE = re.compile(r"^EX-10[01]\.", re.IGNORECASE)
EXHIBIT_TYPE = re.compile(r"^EX-", re.IGNORECASE)

COMPLETE_SUBMISSION = re.compile(r"^\d{10}-\d{2}-\d{6}\.txt$")
GRAPHIC_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg")
HUMAN_SUFFIXES = (".htm", ".html", ".txt")
MACHINE_SUFFIXES = (".xsd", ".xml", ".zip", ".json", ".xlsx")

# The index document table. Two tables appear on the page — filed documents, then data files —
# and both are parsed, because the XBRL exhibits in the second are filed documents too.
TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")
# The Document cell carries the filename plus renderer annotations such as a trailing `iXBRL`.
FILENAME_IN_CELL = re.compile(r"([A-Za-z0-9._-]+\.[A-Za-z0-9]{2,5})")


@dataclass(frozen=True)
class InventoryEntry:
    """One document the issuer filed, with its classification and the reason for it."""

    filename: str
    sequence: int
    declared_type: str
    description: str | None
    document_class: str
    role: str
    requires_content_extraction: bool
    listed_size: int | None
    classification_method: str
    classification_reason: str

    @property
    def is_human_readable(self) -> bool:
        return self.document_class == HUMAN_READABLE

    def as_record(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "sequence": self.sequence,
            "declared_type": self.declared_type,
            "description": self.description,
            "document_class": self.document_class,
            "role": self.role,
            "requires_content_extraction": self.requires_content_extraction,
            "listed_size": self.listed_size,
            "classification_method": self.classification_method,
            "classification_reason": self.classification_reason,
        }


@dataclass
class AccessionInventory:
    """Every document the issuer filed in one accession."""

    accession: str
    cik: str
    source_url: str
    entries: list[InventoryEntry] = field(default_factory=list)
    # Files present in the folder listing but not filed by the issuer: SEC viewer output.
    renderer_artifacts: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)

    def by_class(self, document_class: str) -> list[InventoryEntry]:
        return [e for e in self.entries if e.document_class == document_class]

    def by_role(self, role: str) -> list[InventoryEntry]:
        return [e for e in self.entries if e.role == role]

    @property
    def requiring_extraction(self) -> list[InventoryEntry]:
        return [e for e in self.entries if e.requires_content_extraction]

    def census(self) -> dict[str, int]:
        counts: dict[str, int] = {
            "filed_documents": len(self.entries),
            "renderer_artifacts": len(self.renderer_artifacts),
            "requires_extraction": len(self.requiring_extraction),
            "ambiguous": len(self.ambiguities),
        }
        for entry in self.entries:
            counts[entry.document_class] = counts.get(entry.document_class, 0) + 1
            counts[f"role:{entry.role}"] = counts.get(f"role:{entry.role}", 0) + 1
        return counts


def _text(cell: str) -> str:
    return html.unescape(TAG.sub("", cell)).replace("\xa0", " ").strip()


def _listed_size(raw: str) -> int | None:
    """SEC writes an empty string for some entries; `int("")` raises and a total silently drops."""
    stripped = raw.strip().replace(",", "")
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def classify(
    filename: str, declared_type: str, *, primary_document: str | None
) -> tuple[str, str, bool, str, str]:
    """Return `(document_class, role, requires_extraction, method, reason)`.

    Deterministic. Where neither the declared type nor the filename determines a class, the result
    is UNKNOWN and the ambiguity is recorded rather than guessed. No model participates.
    """
    lowered = filename.lower()
    upper_type = declared_type.strip().upper()

    if COMPLETE_SUBMISSION.match(filename):
        return (
            MACHINE_ARTIFACT,
            ROLE_COMPLETE_SUBMISSION,
            False,
            "complete_submission_filename",
            "concatenates every other document in this accession; extracting it would "
            "double-count every disclosure in the filing",
        )

    if upper_type in PRIMARY_TYPES or (primary_document and lowered == primary_document.lower()):
        # A courtesy PDF carries the SAME declared type as the primary document it duplicates.
        # Apple files `aapl_courtesy-pdf.pdf` alongside its DEF 14A; extracting both would
        # double-count the entire proxy. The suffix is what separates the filed text from an
        # alternate rendering of it.
        if not lowered.endswith(HUMAN_SUFFIXES):
            return (
                HUMAN_READABLE,
                ROLE_OTHER,
                False,
                "declared_type_and_suffix",
                f"declared type {declared_type!r} on a non-text file: a courtesy or alternate "
                "rendering of the primary document. Inventoried, not extracted, because its "
                "content is already covered by the filed text version",
            )
        return (
            HUMAN_READABLE,
            ROLE_PRIMARY,
            True,
            "declared_type",
            f"declared type {declared_type!r}: the filing's primary document",
        )

    if upper_type == "GRAPHIC" or lowered.endswith(GRAPHIC_SUFFIXES):
        return (
            GRAPHIC,
            ROLE_GRAPHIC,
            False,
            "declared_type" if upper_type == "GRAPHIC" else "filename_suffix",
            "image; inventoried here, and its meaning assessed where it appears in content. "
            "Absence of alt text is never treated as proof of decoration",
        )

    if XBRL_EXHIBIT_TYPE.match(upper_type):
        return (
            MACHINE_ARTIFACT,
            ROLE_MACHINE,
            False,
            "declared_type",
            f"declared type {declared_type!r}: an XBRL taxonomy exhibit. Machine evidence, "
            "preserved and registered, never model-visible",
        )

    if CERTIFICATION_TYPE.match(upper_type):
        return (
            HUMAN_READABLE,
            ROLE_CERTIFICATION,
            True,
            "declared_type",
            f"declared type {declared_type!r}: an officer certification under Item 601",
        )

    if CONSENT_TYPE.match(upper_type):
        return (
            HUMAN_READABLE,
            ROLE_CONSENT,
            True,
            "declared_type",
            f"declared type {declared_type!r}: an auditor consent under Item 601",
        )

    if SCHEDULE_TYPE.match(upper_type):
        return (
            HUMAN_READABLE,
            ROLE_SCHEDULE,
            True,
            "declared_type",
            f"declared type {declared_type!r}: an additional exhibit, commonly a schedule",
        )

    if EXHIBIT_TYPE.match(upper_type):
        if lowered.endswith(HUMAN_SUFFIXES):
            return (
                HUMAN_READABLE,
                ROLE_EXHIBIT,
                True,
                "declared_type",
                f"declared type {declared_type!r}: a human-readable Item 601 exhibit",
            )
        return (
            MACHINE_ARTIFACT,
            ROLE_MACHINE,
            False,
            "declared_type_and_suffix",
            f"declared type {declared_type!r} on a non-text file",
        )

    # No usable declared type. Fall back to the filename, and say so.
    if lowered.endswith(MACHINE_SUFFIXES):
        return (
            MACHINE_ARTIFACT,
            ROLE_MACHINE,
            False,
            "filename_suffix_fallback",
            "no declared type; suffix indicates a schema, linkbase, instance, or package",
        )
    if lowered.endswith(HUMAN_SUFFIXES):
        return (
            HUMAN_READABLE,
            ROLE_OTHER,
            True,
            "filename_suffix_fallback",
            "no declared type; suffix indicates a human-readable document",
        )

    return (
        UNKNOWN,
        ROLE_OTHER,
        False,
        "unclassified",
        f"neither the declared type {declared_type!r} nor the filename {filename!r} determines a "
        "document class; recorded as ambiguous rather than guessed",
    )


def parse_filing_index(
    payload: str, *, accession: str, cik: str, primary_document: str | None
) -> AccessionInventory:
    """Build the filed-document inventory from the accession index page."""
    inventory = AccessionInventory(
        accession=accession,
        cik=cik,
        source_url=filing_index_url(cik, accession),
    )
    seen: set[str] = set()

    for row in TABLE_ROW.findall(payload):
        cells = [_text(cell) for cell in TABLE_CELL.findall(row)]
        if len(cells) < 4:
            continue
        if cells[0].strip().lower() == "seq":
            continue

        sequence_text, description, document_cell, declared_type = (
            cells[0],
            cells[1],
            cells[2],
            cells[3],
        )
        size_text = cells[4] if len(cells) > 4 else ""

        match = FILENAME_IN_CELL.search(document_cell)
        if not match:
            continue
        filename = match.group(1)
        if filename in seen:
            continue
        seen.add(filename)

        document_class, role, extract, method, reason = classify(
            filename, declared_type, primary_document=primary_document
        )
        if document_class == UNKNOWN:
            inventory.ambiguities.append(f"{filename}: {reason}")

        inventory.entries.append(
            InventoryEntry(
                filename=filename,
                sequence=int(sequence_text) if sequence_text.strip().isdigit() else 0,
                declared_type=declared_type,
                description=description or None,
                document_class=document_class,
                role=role,
                requires_content_extraction=extract,
                listed_size=_listed_size(size_text),
                classification_method=method,
                classification_reason=reason,
            )
        )

    return inventory


def folder_filenames(payload: str) -> list[str]:
    """Every file in the accession folder, from `index.json`.

    A superset of the filed documents: it also holds the R*.htm reports, `MetaLinks.json`, and the
    XLSX that SEC's viewer generated, none of which anyone filed.
    """
    data = json.loads(payload)
    return [item["name"] for item in data.get("directory", {}).get("item", []) if item.get("name")]


def filing_index_url(cik: str, accession: str) -> str:
    return f"{filing_folder_url(str(cik_archive(cik)), accession)}/{accession}-index.html"


def folder_index_url(cik: str, accession: str) -> str:
    return f"{filing_folder_url(str(cik_archive(cik)), accession)}/index.json"


def fetch_inventory(
    client: Any, cik: str, accession: str, primary_document: str | None
) -> AccessionInventory:
    """Retrieve and classify the authoritative filed-document inventory.

    Two requests through the shared limiter: the index page for what was filed, and the folder
    listing so renderer artifacts are distinguishable from filed documents rather than merely
    absent from one of the two views.
    """
    inventory = parse_filing_index(
        client.get_text(filing_index_url(cik, accession)),
        accession=accession,
        cik=cik,
        primary_document=primary_document,
    )
    filed = {e.filename for e in inventory.entries}
    inventory.renderer_artifacts = [
        name
        for name in folder_filenames(client.get_text(folder_index_url(cik, accession)))
        if name not in filed
    ]
    return inventory
