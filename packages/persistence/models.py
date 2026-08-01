"""PostgreSQL schema for the FinTek control plane.

Owns everything transactional: issuer identity with temporal validity, filing metadata, canonical
footnotes, summary versions, the ingest ledger, the DERA mirror ledger, analysis sessions, and
model invocation audit.

Does NOT own the financial fact lake at serving scale. `xbrl_fact` below is the authoritative
append-only record; the columnar copy used for charting lives in Parquet (ADR-0002).

FINANCIAL-INVARIANT: identifiers from SEC are stored as text, never integers. `0000320193` is not
the number 320193, and an integer column would destroy the leading zeros that make it a valid CIK.

FINANCIAL-INVARIANT: `xbrl_fact.value_as_filed` is append-only, enforced by a trigger created in
the migration. A restatement appends a new observation; it never updates an existing one.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid

# --- enumerated values -------------------------------------------------------------------------
# Held as text with a check constraint rather than a PostgreSQL ENUM type, so adding a value is a
# migration rather than a type alteration that locks the table.

PROCESSING_STATES = (
    "DISCOVERED",
    "QUEUED",
    "DOWNLOADING",
    "DOWNLOADED",
    "PARSING",
    "PARSED",
    "EXTRACTING_FACTS",
    "FACTS_EXTRACTED",
    "EXTRACTING_SECTIONS",
    "SECTIONS_EXTRACTED",
    "EXTRACTING_FOOTNOTES",
    "FOOTNOTES_EXTRACTED",
    "GROUPING_FOOTNOTES",
    "FOOTNOTES_GROUPED",
    "VALIDATING_FOOTNOTES",
    "FOOTNOTES_VALIDATED",
    "SUMMARIZING",
    "SUMMARIES_GENERATED",
    "VALIDATING_SUMMARIES",
    "CALCULATING_METRICS",
    "PUBLISHING",
    "COMPLETE",
    "PARTIAL",
    "FAILED",
    "REQUIRES_REVIEW",
)
FOOTNOTE_STATUSES = ("COMPLETE", "PARTIAL", "REQUIRES_REVIEW", "FAILED", "NOT_STARTED")
RECONCILIATION_STATUSES = ("RECONCILED", "MISMATCH", "NOT_ATTEMPTED")
GROUPING_METHODS = (
    "role_uri",
    "toc_reconciliation",
    "heading",
    "presentation_hierarchy",
    "concept_overlap",
    "title_similarity",
    "filing_order",
    "model_adjudication",
    "human_review",
)
SUMMARY_VALIDATION_STATES = (
    "GENERATED",
    "VALIDATING",
    "VALIDATED",
    "VALIDATED_NORMALIZED",
    "SOURCE_PRESENT_AMBIGUOUS",
    "SOURCE_NOT_FOUND",
    "UNIT_MISMATCH",
    "SCALE_MISMATCH",
    "PERIOD_MISMATCH",
    "SIGN_MISMATCH",
    "UNSUPPORTED",
    "REQUIRES_REVIEW",
    "FAILED",
)
EXCLUSION_REASONS = (
    "foreign_private_issuer_20f",
    "fund_n_csr",
    "bdc_specialized",
    "shell",
    "never_filed",
    "unresolved_identity",
    "filing_history_unavailable",
)
FILING_ERAS = ("inline_xbrl", "standalone_xbrl", "html_no_xbrl", "plain_text", "pem_armored")
ANALYSIS_SCOPES = ("FOOTNOTE", "FILING", "TIMEFRAME")
SESSION_STATUSES = ("ACTIVE", "IDLE", "EXPIRED", "BUDGET_EXHAUSTED", "CLOSED", "TERMINATED")
PERIOD_TYPES = ("instant", "duration")
CADENCES = ("monthly", "quarterly")


def _enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    joined = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({joined})", name=name)


# --- issuer identity ---------------------------------------------------------------------------


class Issuer(Base, TimestampMixin):
    """An SEC filer. CIK is identity; ticker is a temporal alias and lives in `listing`."""

    __tablename__ = "issuer"

    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    sic: Mapped[str | None] = mapped_column(String(8))
    fiscal_year_end: Mapped[str | None] = mapped_column(
        String(4), comment="MMDD; most recent observation only"
    )
    state_of_incorporation: Mapped[str | None] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("cik ~ '^[0-9]{10}$'", name="cik_is_ten_digits"),
        Index("ix_issuer_legal_name", "legal_name"),
    )


class IssuerFormerName(Base, TimestampMixin):
    """Former names. Delisted issuers are renamed in EDGAR, so name matching alone is unreliable."""

    __tablename__ = "issuer_former_name"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="CASCADE"), nullable=False
    )
    former_name: Mapped[str] = mapped_column(Text, nullable=False)
    effective_start: Mapped[date | None] = mapped_column(Date)
    effective_end: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_issuer_former_name_issuer_id", "issuer_id"),)


class Listing(Base, TimestampMixin):
    """Ticker history with validity windows.

    FINANCIAL-INVARIANT: uniqueness is on (ticker, exchange, effective_start), NEVER on ticker
    alone. BBBY maps to CIK 886158 for 2019-2023 and to CIK 1130713 from 2024, and a unique
    constraint on ticker would silently merge two unrelated companies.
    """

    __tablename__ = "listing"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(20))
    share_class: Mapped[str | None] = mapped_column(String(20))
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "ticker", "exchange", "effective_start", name="uq_listing_ticker_exchange_start"
        ),
        CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="effective_window_is_ordered",
        ),
        Index("ix_listing_ticker_window", "ticker", "effective_start", "effective_end"),
        Index("ix_listing_issuer_id", "issuer_id"),
    )


class ListingObservation(Base, TimestampMixin):
    """Raw snapshots of a ticker source. Append only; never overwritten.

    The SEC ticker file is unstable across CDN edges: three fetches in one session returned
    10,432, 10,419, and 10,411 rows. Retaining every observation is what makes the union possible
    and what makes historical listing reconstruction possible at all.
    """

    __tablename__ = "listing_observation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_uri: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    last_modified_header: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_listing_observation_source_observed", "source", "observed_at"),)


class ExcludedFiler(Base, TimestampMixin):
    """CIKs deliberately outside the active universe, with the reason preserved.

    Preserved rather than discarded so enabling a category later is a flag change rather than a
    re-derivation.
    """

    __tablename__ = "excluded_filer"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    cik: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    exclusion_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    reconsideration_status: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        _enum_check("exclusion_reason", EXCLUSION_REASONS, "exclusion_reason_is_known"),
    )


# --- filings ------------------------------------------------------------------------------------


class Filing(Base, TimestampMixin):
    """One SEC filing."""

    __tablename__ = "filing"

    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="RESTRICT"), nullable=False
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    accession: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    form: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(4))
    fiscal_year_end: Mapped[str | None] = mapped_column(
        String(4), comment="MMDD as of THIS filing; issuers change year ends"
    )
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    amends_filing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="SET NULL")
    )
    primary_document: Mapped[str | None] = mapped_column(
        Text, comment="empty string for pre-2001 filings; never concatenate blindly"
    )
    is_xbrl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_inline_xbrl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    era: Mapped[str | None] = mapped_column(String(20))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    processing_state: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCOVERED")
    footnote_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_STARTED")
    toc_expected_note_count: Mapped[int | None] = mapped_column(Integer)
    parser_version: Mapped[str | None] = mapped_column(String(40))

    # docs/footnotes/completeness.md tracks thirteen counters. Eleven are COUNT() queries over
    # canonical_footnote, footnote_source_block, footnote_table, and footnote_summary, and are
    # deliberately NOT stored: a stored copy of a derivable count is a second source of truth
    # that goes stale. These two are judgements produced by the extraction run and cannot be
    # recomputed from the child rows, so they are stored. See the completeness document for the
    # full derived-versus-stored table.
    completeness_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    reconciliation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_ATTEMPTED"
    )
    raw_sha256: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'", name="accession_is_dashed_form"
        ),
        CheckConstraint("cik ~ '^[0-9]{10}$'", name="cik_is_ten_digits"),
        _enum_check("processing_state", PROCESSING_STATES, "processing_state_is_known"),
        _enum_check("footnote_status", FOOTNOTE_STATUSES, "footnote_status_is_known"),
        _enum_check(
            "reconciliation_status", RECONCILIATION_STATUSES, "reconciliation_status_is_known"
        ),
        _enum_check("era", FILING_ERAS + (None,) if False else FILING_ERAS, "era_is_known"),
        Index("ix_filing_issuer_form_period", "issuer_id", "form", "report_date"),
        Index("ix_filing_processing_state", "processing_state"),
        Index("ix_filing_amends", "amends_filing_id"),
    )


class FilingDocument(Base, TimestampMixin):
    """One acquired object belonging to a filing, with full provenance."""

    __tablename__ = "filing_document"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    filename: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict | None] = mapped_column(JSONB)
    acquisition_strategy: Mapped[str | None] = mapped_column(String(40))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_filing_document_filing_id", "filing_id"),
        Index("ix_filing_document_sha256", "sha256"),
    )


class FilingSection(Base, TimestampMixin):
    """A narrative item section, such as Item 1A or Item 7.

    Distinct from a canonical footnote. Item 408 and Item 1C disclosures land here, not in the
    footnote model, even though the SEC renderer files them under a Notes menu category.
    """

    __tablename__ = "filing_section"

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    section_type: Mapped[str] = mapped_column(String(40), nullable=False)
    item_number: Mapped[str | None] = mapped_column(String(10))
    heading: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    extraction_strategy: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    candidate_count: Mapped[int | None] = mapped_column(Integer)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("filing_id", "section_type", "sequence", name="uq_filing_section_seq"),
        Index("ix_filing_section_filing_id", "filing_id"),
    )


class FilingAmendment(Base, TimestampMixin):
    """An amendment modelled as a PATCH, never a replacement.

    AMD's 10-K/A is 545,192 bytes against a 14,078,338-byte original, filed the same day with the
    same report date. Treating it as a replacement would blank the dashboard for that filer.
    """

    __tablename__ = "filing_amendment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    amendment_filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    amends_filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    amendment_form: Mapped[str] = mapped_column(String(20), nullable=False)
    is_complete_replacement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sections_changed: Mapped[list | None] = mapped_column(ARRAY(Text))
    footnotes_changed: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    facts_changed: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    patch_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    detected_by: Mapped[str | None] = mapped_column(String(30))

    __table_args__ = (
        UniqueConstraint(
            "amendment_filing_id", "amends_filing_id", name="uq_filing_amendment_pair"
        ),
        CheckConstraint("amendment_filing_id <> amends_filing_id", name="amendment_is_not_self"),
    )


# --- canonical footnotes -------------------------------------------------------------------------


class CanonicalFootnote(Base, TimestampMixin):
    """One ACTUAL financial-statement footnote. The product unit.

    Apple's FY2025 10-K has 13 of these, against 58 XBRL TextBlock facts and 71 renderer reports.
    Counting TextBlocks or renderer reports instead over-counts by roughly 4.5 times and
    fragments each real footnote. See ADR-0005.
    """

    __tablename__ = "canonical_footnote"

    footnote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    number_as_displayed: Mapped[str | None] = mapped_column(String(20))
    normalized_number: Mapped[int | None] = mapped_column(Integer)
    title_as_displayed: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_footnote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_footnote.footnote_id", ondelete="SET NULL")
    )
    text: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    extraction_method: Mapped[str | None] = mapped_column(String(40))
    grouping_method: Mapped[str | None] = mapped_column(String(30))
    grouping_evidence: Mapped[dict | None] = mapped_column(JSONB)
    parser_version: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    review_state: Mapped[str | None] = mapped_column(String(20))
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("filing_id", "normalized_number", name="uq_canonical_footnote_number"),
        UniqueConstraint("filing_id", "sequence", name="uq_canonical_footnote_sequence"),
        _enum_check("grouping_method", GROUPING_METHODS, "grouping_method_is_known"),
        CheckConstraint("parent_footnote_id <> footnote_id", name="footnote_is_not_own_parent"),
        Index("ix_canonical_footnote_filing_id", "filing_id"),
    )


class FootnoteSourceBlock(Base, TimestampMixin):
    """A narrative, policy, or detail block belonging to a canonical footnote.

    `footnote_id` is NULLABLE on purpose. An ungrouped block is a visible defect that enters the
    review queue. It is never silently dropped and never force-attached to an arbitrary parent to
    make a count reconcile.
    """

    __tablename__ = "footnote_source_block"

    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    footnote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_footnote.footnote_id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="cited by the model"
    )
    block_type: Mapped[str] = mapped_column(String(30), nullable=False)
    dera_report_number: Mapped[int | None] = mapped_column(Integer)
    menucat: Mapped[str | None] = mapped_column(String(4))
    short_name: Mapped[str | None] = mapped_column(Text)
    long_name: Mapped[str | None] = mapped_column(Text)
    role_uri: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    source_anchor: Mapped[str | None] = mapped_column(Text)

    # The attachment audit record. docs/footnotes/canonicalization-algorithm.md specifies that
    # every parent-child grouping decision is answerable later: which stage produced it, on what
    # evidence, against which alternatives. That decision is made PER CHILD BLOCK by stages 3 and
    # 6 through 10, so it has to live here. Recording it only on the parent footnote, as the
    # original schema did, cannot answer "why was this block attached to this note".
    grouping_method: Mapped[str | None] = mapped_column(
        String(30), comment="which stage produced this attachment"
    )
    grouping_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    grouping_evidence: Mapped[dict | None] = mapped_column(
        JSONB, comment="matched role URI, overlap score, or similarity score"
    )
    competing_candidates: Mapped[dict | None] = mapped_column(
        JSONB, comment="alternatives considered and their scores; a tie is never broken silently"
    )
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    grouping_parser_version: Mapped[str | None] = mapped_column(String(40))
    grouping_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("filing_id", "external_id", name="uq_footnote_source_block_external"),
        Index("ix_footnote_source_block_footnote_id", "footnote_id"),
        Index("ix_footnote_source_block_role_uri", "role_uri"),
        Index("ix_footnote_source_block_extraction_run", "extraction_run_id"),
        _enum_check("grouping_method", GROUPING_METHODS, "source_block_grouping_method_is_known"),
        # Finding orphans is a routine completeness query, so it gets a partial index.
        Index(
            "ix_footnote_source_block_orphans",
            "filing_id",
            postgresql_where=("footnote_id IS NULL"),
        ),
    )


class FootnoteTable(Base, TimestampMixin):
    """A table belonging to a footnote, with structure preserved.

    Collapsing a maturity schedule or a tax reconciliation into unstructured text destroys the
    units, periods, and hierarchy that make it meaningful.
    """

    __tablename__ = "footnote_table"

    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    footnote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_footnote.footnote_id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    column_headers: Mapped[dict | None] = mapped_column(JSONB)
    row_labels: Mapped[dict | None] = mapped_column(JSONB)
    cells: Mapped[dict | None] = mapped_column(JSONB)
    unit: Mapped[str | None] = mapped_column(String(20))
    scale: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    period_labels: Mapped[dict | None] = mapped_column(JSONB)
    footnote_markers: Mapped[dict | None] = mapped_column(JSONB)
    original_html_uri: Mapped[str | None] = mapped_column(Text)
    plain_rendering: Mapped[str | None] = mapped_column(Text)
    source_anchor: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    validation_warnings: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("filing_id", "external_id", name="uq_footnote_table_external"),
        Index("ix_footnote_table_footnote_id", "footnote_id"),
    )


# --- facts ----------------------------------------------------------------------------------------


class XbrlFact(Base, TimestampMixin):
    """One filed XBRL fact. APPEND ONLY.

    FINANCIAL-INVARIANT: `value_as_filed` is never updated. A restatement appends a new row and
    `is_latest_selected` is recomputed as a pure function over the observation set. A trigger
    created in the migration rejects any UPDATE touching the filed value.
    """

    __tablename__ = "xbrl_fact"

    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="RESTRICT"), nullable=False
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="RESTRICT"), nullable=False
    )
    accession: Mapped[str] = mapped_column(String(20), nullable=False)
    form: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(
        Integer, comment="describes the FILING, not this fact"
    )
    fiscal_period: Mapped[str | None] = mapped_column(
        String(4), comment="describes the FILING, not this fact"
    )
    taxonomy: Mapped[str] = mapped_column(String(40), nullable=False)
    namespace: Mapped[str] = mapped_column(Text, nullable=False)
    concept: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    value_as_filed: Mapped[str] = mapped_column(Text, nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(38, 6))
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    scale: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sign: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    context_id: Mapped[str | None] = mapped_column(Text)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    instant_date: Mapped[date | None] = mapped_column(Date)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    duration_months: Mapped[int | None] = mapped_column(
        Integer, comment="computed at ingest; charts filter on it"
    )
    dimensions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    segment: Mapped[str | None] = mapped_column(Text)
    coregistrant: Mapped[str | None] = mapped_column(Text)
    statement_role: Mapped[str | None] = mapped_column(Text)
    disclosure_role: Mapped[str | None] = mapped_column(Text)
    source_dataset: Mapped[str] = mapped_column(String(60), nullable=False)
    source_row_id: Mapped[str | None] = mapped_column(Text)
    source_anchor: Mapped[str | None] = mapped_column(Text)
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    restates_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("xbrl_fact.fact_id", ondelete="SET NULL")
    )
    is_latest_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="UNVALIDATED"
    )

    __table_args__ = (
        _enum_check("period_type", PERIOD_TYPES, "period_type_is_known"),
        CheckConstraint("sign IN (-1, 1)", name="sign_is_plus_or_minus_one"),
        CheckConstraint(
            "(period_type = 'instant' AND instant_date IS NOT NULL) OR "
            "(period_type = 'duration' AND period_start IS NOT NULL AND period_end IS NOT NULL)",
            name="period_fields_match_period_type",
        ),
        Index("ix_xbrl_fact_cik_concept_period", "cik", "concept", "period_end"),
        Index("ix_xbrl_fact_filing_id", "filing_id"),
        Index("ix_xbrl_fact_accession", "accession"),
        # The consolidated-series path: charts always exclude dimensional facts.
        Index(
            "ix_xbrl_fact_consolidated_series",
            "cik",
            "concept",
            "duration_months",
            "period_end",
            postgresql_where=("dimensions = '{}'::jsonb"),
        ),
        Index("ix_xbrl_fact_dimensions", "dimensions", postgresql_using="gin"),
    )


# --- metrics ---------------------------------------------------------------------------------------


class MetricDefinition(Base, TimestampMixin):
    """Registry mirror of the curated YAML metric definitions.

    The YAML files in metric_definitions/ are the source of truth; this table records which
    version is active so a derived value can name the definition that produced it.
    """

    __tablename__ = "metric_definition"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    metric_id: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    git_commit: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("metric_id", "version", name="uq_metric_definition_version"),
        Index("ix_metric_definition_active", "metric_id", postgresql_where=("is_active")),
    )


class DerivedMetric(Base, TimestampMixin):
    """A deterministically computed value with full provenance."""

    __tablename__ = "derived_metric"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="CASCADE"), nullable=False
    )
    filing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="SET NULL")
    )
    metric_id: Mapped[str] = mapped_column(String(60), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    value: Mapped[Decimal | None] = mapped_column(Numeric(38, 6))
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_fact_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    is_derived_q4: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comparability_status: Mapped[str | None] = mapped_column(String(30))
    warnings: Mapped[dict | None] = mapped_column(JSONB)
    missing_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "issuer_id",
            "metric_id",
            "period_end",
            "duration_months",
            "formula_version",
            name="uq_derived_metric_period",
        ),
        Index("ix_derived_metric_series", "issuer_id", "metric_id", "period_end"),
    )


# --- summaries --------------------------------------------------------------------------------------


class FootnoteSummary(Base, TimestampMixin):
    """A model-generated summary of one canonical footnote.

    Exactly one ACTIVE version per footnote, enforced by a partial unique index. Superseding sets
    `superseded_at`; an accepted historical output is never overwritten or deleted.
    """

    __tablename__ = "footnote_summary"

    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    footnote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_footnote.footnote_id", ondelete="CASCADE"),
        nullable=False,
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(60), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(60), nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(40))
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    plain_summary: Mapped[str | None] = mapped_column(Text)
    structured: Mapped[dict | None] = mapped_column(JSONB)
    classification: Mapped[str | None] = mapped_column(String(20))
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="GENERATED")
    validation_detail: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str | None] = mapped_column(String(20))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    batch_job_id: Mapped[str | None] = mapped_column(String(120))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check(
            "validation_status", SUMMARY_VALIDATION_STATES, "summary_validation_status_is_known"
        ),
        UniqueConstraint("footnote_id", "version", name="uq_footnote_summary_version"),
        # Exactly one active version per footnote.
        Index(
            "ix_footnote_summary_active",
            "footnote_id",
            unique=True,
            postgresql_where=("superseded_at IS NULL"),
        ),
        Index("ix_footnote_summary_filing_id", "filing_id"),
        Index(
            "ix_footnote_summary_review", "requires_review", postgresql_where=("requires_review")
        ),
    )


# --- jobs and ledgers ---------------------------------------------------------------------------------


class ProcessingJob(Base, TimestampMixin):
    """The ingest ledger. PostgreSQL owns this; SQLite is deliberately not introduced (ADR-0004)."""

    __tablename__ = "processing_job"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    issuer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="CASCADE")
    )
    filing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing.filing_id", ondelete="CASCADE")
    )
    footnote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_footnote.footnote_id", ondelete="CASCADE")
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_processing_job_queue", "state", "priority", "scheduled_at"),
        Index("ix_processing_job_filing_id", "filing_id"),
    )


class DeraPackageRecord(Base, TimestampMixin):
    """The DERA mirror ledger.

    TIME-SENSITIVE: monthly packages are deleted upstream after quarterly consolidation, so a
    monthly row here may be the only remaining record that the package existed. Monthly rows are
    retained permanently even after the corresponding quarterly arrives.
    """

    __tablename__ = "dera_package"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    filename: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    cadence: Mapped[str] = mapped_column(String(12), nullable=False)
    period: Mapped[str] = mapped_column(String(12), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    format_version: Mapped[str] = mapped_column(String(20), nullable=False, default="notes-v1")
    http_last_modified: Mapped[str | None] = mapped_column(Text)
    http_etag: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(80))
    zip_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hash_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("cadence", CADENCES, "cadence_is_known"),
        Index("ix_dera_package_period", "cadence", "period"),
    )


# --- deep analysis --------------------------------------------------------------------------------------


class AnalysisSession(Base, TimestampMixin):
    """A Deep Analysis session. Scope is IMMUTABLE after creation.

    SECURITY-INVARIANT: the client sends only a session identifier and a message. CIK, tickers,
    accessions, footnote identifiers, model, and budgets are read from this row, never from the
    request body.
    """

    __tablename__ = "analysis_session"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    principal_id: Mapped[str] = mapped_column(String(120), nullable=False)
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuer.issuer_id", ondelete="RESTRICT"), nullable=False
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    ticker_at_creation: Mapped[str | None] = mapped_column(String(20))
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    allowed_accessions: Mapped[list] = mapped_column(ARRAY(Text), nullable=False)
    allowed_footnote_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    date_start: Mapped[date | None] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    model_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False)
    max_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    spent_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spent_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spent_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spent_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        _enum_check("scope_type", ANALYSIS_SCOPES, "scope_type_is_known"),
        _enum_check("status", SESSION_STATUSES, "session_status_is_known"),
        CheckConstraint(
            "cardinality(allowed_accessions) > 0", name="scope_has_at_least_one_accession"
        ),
        Index("ix_analysis_session_principal", "principal_id", "status"),
    )


class AnalysisMessage(Base, TimestampMixin):
    """One turn in a Deep Analysis session."""

    __tablename__ = "analysis_message"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[dict | None] = mapped_column(JSONB)
    scope_decision: Mapped[str | None] = mapped_column(String(30))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    __table_args__ = (
        UniqueConstraint("session_id", "turn", "role", name="uq_analysis_message_turn"),
        CheckConstraint("role IN ('user', 'assistant')", name="message_role_is_known"),
        Index("ix_analysis_message_session", "session_id", "turn"),
    )


class ConversationMemory(Base, TimestampMixin):
    """Structured memory for a session. Only evidenced findings are promoted here."""

    __tablename__ = "conversation_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    memory: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_references: Mapped[list | None] = mapped_column(ARRAY(Text))

    __table_args__ = (
        UniqueConstraint("session_id", "version", name="uq_conversation_memory_version"),
    )


# --- model audit ----------------------------------------------------------------------------------------


class LlmInvocation(Base, TimestampMixin):
    """Audit record for one model invocation.

    SECURITY-INVARIANT: the exact model-visible request and response bodies are preserved
    unmodified in object storage; this row carries their URIs and hashes. The bodies are never
    rewritten into another serialization and presented as the model's original output.
    """

    __tablename__ = "llm_invocation"

    invocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(80), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_job.job_id", ondelete="SET NULL")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_session.session_id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str | None] = mapped_column(String(30))
    tier: Mapped[str | None] = mapped_column(String(20))
    prompt_version: Mapped[str] = mapped_column(String(60), nullable=False)
    request_format: Mapped[str] = mapped_column(String(12), nullable=False)
    response_format: Mapped[str] = mapped_column(String(12), nullable=False)
    request_uri: Mapped[str | None] = mapped_column(Text)
    request_sha256: Mapped[str | None] = mapped_column(String(64))
    response_uri: Mapped[str | None] = mapped_column(Text)
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "request_format IN ('plain_text', 'yaml') AND response_format IN ('plain_text', 'yaml')",
            name="model_content_format_is_permitted",
        ),
        Index("ix_llm_invocation_correlation", "correlation_id"),
        Index("ix_llm_invocation_session", "session_id"),
        Index("ix_llm_invocation_created", "created_at"),
    )


class PromptVersion(Base, TimestampMixin):
    """Registry of prompt files. The files under prompts/ are the source of truth."""

    __tablename__ = "prompt_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluation_result: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_version"),
        Index("ix_prompt_version_active", "name", postgresql_where=("is_active")),
    )


class DatasetVersion(Base, TimestampMixin):
    """The published Parquet dataset pointer. Publication is an atomic flip of `is_current`."""

    __tablename__ = "dataset_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    version_label: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    row_counts: Mapped[dict | None] = mapped_column(JSONB)
    verification: Mapped[dict | None] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # At most one current dataset version at a time.
        Index(
            "ix_dataset_version_current", "is_current", unique=True, postgresql_where=("is_current")
        ),
    )
