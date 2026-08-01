"""initial control plane schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-01

Creates the FinTek control plane: issuer identity with temporal validity, filings, canonical
footnotes with their source blocks and tables, the append-only fact lake, curated metric
definitions and derived values, versioned summaries, the ingest ledger, the DERA mirror ledger,
Deep Analysis sessions, and model invocation audit.

Generated deterministically from packages.persistence metadata rather than by --autogenerate,
because the authoring environment had no PostgreSQL available. See docs/sprints/SPRINT-0002.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

# Text and UUID are imported explicitly because postgresql.JSONB and postgresql.ARRAY render
# their repr as JSONB(astext_type=Text()) and ARRAY(UUID()), which the generated code evaluates.
_ = (Text, UUID)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_version",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("version_label", sa.String(length=60), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("row_counts", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("verification", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("version_label", name="uq_dataset_version_version_label"),
    )
    op.create_index(
        "ix_dataset_version_current",
        "dataset_version",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "dera_package",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("cadence", sa.String(length=12), nullable=False),
        sa.Column("period", sa.String(length=12), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("format_version", sa.String(length=20), nullable=False),
        sa.Column("http_last_modified", sa.Text(), nullable=True),
        sa.Column("http_etag", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=80), nullable=True),
        sa.Column("zip_validated", sa.Boolean(), nullable=False),
        sa.Column("hash_validated", sa.Boolean(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "cadence IN ('monthly', 'quarterly')", name="ck_dera_package_cadence_is_known"
        ),
        sa.UniqueConstraint("filename", name="uq_dera_package_filename"),
    )
    op.create_index("ix_dera_package_period", "dera_package", ["cadence", "period"])

    op.create_table(
        "excluded_filer",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("exclusion_reason", sa.String(length=40), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("reconsideration_status", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "exclusion_reason IN ('foreign_private_issuer_20f', 'fund_n_csr', 'bdc_specialized', 'shell', 'never_filed', 'unresolved_identity', 'filing_history_unavailable')",
            name="ck_excluded_filer_exclusion_reason_is_known",
        ),
        sa.UniqueConstraint("cik", name="uq_excluded_filer_cik"),
    )

    op.create_table(
        "issuer",
        sa.Column("issuer_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("sic", sa.String(length=8), nullable=True),
        sa.Column(
            "fiscal_year_end",
            sa.String(length=4),
            nullable=True,
            comment="MMDD; most recent observation only",
        ),
        sa.Column("state_of_incorporation", sa.String(length=8), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("cik ~ '^[0-9]{10}$'", name="ck_issuer_cik_is_ten_digits"),
        sa.UniqueConstraint("cik", name="uq_issuer_cik"),
    )
    op.create_index("ix_issuer_legal_name", "issuer", ["legal_name"])

    op.create_table(
        "listing_observation",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_uri", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("last_modified_header", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_listing_observation_source_observed", "listing_observation", ["source", "observed_at"]
    )

    op.create_table(
        "metric_definition",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("metric_id", sa.String(length=60), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=Text()), nullable=False),
        sa.Column("git_commit", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("metric_id", "version", name="uq_metric_definition_version"),
    )
    op.create_index(
        "ix_metric_definition_active",
        "metric_definition",
        ["metric_id"],
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "prompt_version",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=60), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("evaluation_result", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", "version", name="uq_prompt_version"),
    )
    op.create_index(
        "ix_prompt_version_active",
        "prompt_version",
        ["name"],
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "analysis_session",
        sa.Column("session_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("principal_id", sa.String(length=120), nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("ticker_at_creation", sa.String(length=20), nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("allowed_accessions", postgresql.ARRAY(Text()), nullable=False),
        sa.Column("allowed_footnote_ids", postgresql.ARRAY(UUID()), nullable=True),
        sa.Column("date_start", sa.Date(), nullable=True),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column("model_provider", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=80), nullable=False),
        sa.Column("max_turns", sa.Integer(), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("max_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("spent_turns", sa.Integer(), nullable=False),
        sa.Column("spent_input_tokens", sa.Integer(), nullable=False),
        sa.Column("spent_output_tokens", sa.Integer(), nullable=False),
        sa.Column("spent_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "cardinality(allowed_accessions) > 0",
            name="ck_analysis_session_scope_has_at_least_one_accession",
        ),
        sa.CheckConstraint(
            "scope_type IN ('FOOTNOTE', 'FILING', 'TIMEFRAME')",
            name="ck_analysis_session_scope_type_is_known",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'IDLE', 'EXPIRED', 'BUDGET_EXHAUSTED', 'CLOSED', 'TERMINATED')",
            name="ck_analysis_session_session_status_is_known",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_analysis_session_issuer_id_issuer",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_analysis_session_principal", "analysis_session", ["principal_id", "status"])

    op.create_table(
        "filing",
        sa.Column("filing_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("accession", sa.String(length=20), nullable=False),
        sa.Column("form", sa.String(length=20), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=4), nullable=True),
        sa.Column(
            "fiscal_year_end",
            sa.String(length=4),
            nullable=True,
            comment="MMDD as of THIS filing; issuers change year ends",
        ),
        sa.Column("is_amendment", sa.Boolean(), nullable=False),
        sa.Column("amends_filing_id", sa.UUID(), nullable=True),
        sa.Column(
            "primary_document",
            sa.Text(),
            nullable=True,
            comment="empty string for pre-2001 filings; never concatenate blindly",
        ),
        sa.Column("is_xbrl", sa.Boolean(), nullable=False),
        sa.Column("is_inline_xbrl", sa.Boolean(), nullable=False),
        sa.Column("era", sa.String(length=20), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("processing_state", sa.String(length=32), nullable=False),
        sa.Column("footnote_status", sa.String(length=20), nullable=False),
        sa.Column("toc_expected_note_count", sa.Integer(), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column("completeness_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=20), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'", name="ck_filing_accession_is_dashed_form"
        ),
        sa.CheckConstraint("cik ~ '^[0-9]{10}$'", name="ck_filing_cik_is_ten_digits"),
        sa.CheckConstraint(
            "era IN ('inline_xbrl', 'standalone_xbrl', 'html_no_xbrl', 'plain_text', 'pem_armored')",
            name="ck_filing_era_is_known",
        ),
        sa.CheckConstraint(
            "footnote_status IN ('COMPLETE', 'PARTIAL', 'REQUIRES_REVIEW', 'FAILED', 'NOT_STARTED')",
            name="ck_filing_footnote_status_is_known",
        ),
        sa.CheckConstraint(
            "processing_state IN ('DISCOVERED', 'QUEUED', 'DOWNLOADING', 'DOWNLOADED', 'PARSING', 'PARSED', 'EXTRACTING_FACTS', 'FACTS_EXTRACTED', 'EXTRACTING_SECTIONS', 'SECTIONS_EXTRACTED', 'EXTRACTING_FOOTNOTES', 'FOOTNOTES_EXTRACTED', 'GROUPING_FOOTNOTES', 'FOOTNOTES_GROUPED', 'VALIDATING_FOOTNOTES', 'FOOTNOTES_VALIDATED', 'SUMMARIZING', 'SUMMARIES_GENERATED', 'VALIDATING_SUMMARIES', 'CALCULATING_METRICS', 'PUBLISHING', 'COMPLETE', 'PARTIAL', 'FAILED', 'REQUIRES_REVIEW')",
            name="ck_filing_processing_state_is_known",
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('RECONCILED', 'MISMATCH', 'NOT_ATTEMPTED')",
            name="ck_filing_reconciliation_status_is_known",
        ),
        sa.ForeignKeyConstraint(
            ["amends_filing_id"],
            ["filing.filing_id"],
            name="fk_filing_amends_filing_id_filing",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_filing_issuer_id_issuer",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("accession", name="uq_filing_accession"),
    )
    op.create_index("ix_filing_amends", "filing", ["amends_filing_id"])
    op.create_index("ix_filing_issuer_form_period", "filing", ["issuer_id", "form", "report_date"])
    op.create_index("ix_filing_processing_state", "filing", ["processing_state"])

    op.create_table(
        "issuer_former_name",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=False),
        sa.Column("former_name", sa.Text(), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=True),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_issuer_former_name_issuer_id_issuer",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_issuer_former_name_issuer_id", "issuer_former_name", ["issuer_id"])

    op.create_table(
        "listing",
        sa.Column("listing_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("exchange", sa.String(length=20), nullable=True),
        sa.Column("share_class", sa.String(length=20), nullable=True),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_listing_effective_window_is_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_listing_issuer_id_issuer",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "ticker", "exchange", "effective_start", name="uq_listing_ticker_exchange_start"
        ),
    )
    op.create_index("ix_listing_issuer_id", "listing", ["issuer_id"])
    op.create_index(
        "ix_listing_ticker_window", "listing", ["ticker", "effective_start", "effective_end"]
    )

    op.create_table(
        "analysis_message",
        sa.Column("message_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("scope_decision", sa.String(length=30), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_analysis_message_message_role_is_known"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analysis_session.session_id"],
            name="fk_analysis_message_session_id_analysis_session",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("session_id", "turn", "role", name="uq_analysis_message_turn"),
    )
    op.create_index("ix_analysis_message_session", "analysis_message", ["session_id", "turn"])

    op.create_table(
        "canonical_footnote",
        sa.Column("footnote_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("number_as_displayed", sa.String(length=20), nullable=True),
        sa.Column("normalized_number", sa.Integer(), nullable=True),
        sa.Column("title_as_displayed", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("parent_footnote_id", sa.UUID(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("extraction_method", sa.String(length=40), nullable=True),
        sa.Column("grouping_method", sa.String(length=30), nullable=True),
        sa.Column("grouping_evidence", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("review_state", sa.String(length=20), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "parent_footnote_id <> footnote_id",
            name="ck_canonical_footnote_footnote_is_not_own_parent",
        ),
        sa.CheckConstraint(
            "grouping_method IN ('role_uri', 'toc_reconciliation', 'heading', 'presentation_hierarchy', 'concept_overlap', 'title_similarity', 'filing_order', 'model_adjudication', 'human_review')",
            name="ck_canonical_footnote_grouping_method_is_known",
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_canonical_footnote_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_footnote_id"],
            ["canonical_footnote.footnote_id"],
            name="fk_canonical_footnote_parent_footnote_id_canonical_footnote",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("filing_id", "normalized_number", name="uq_canonical_footnote_number"),
        sa.UniqueConstraint("filing_id", "sequence", name="uq_canonical_footnote_sequence"),
    )
    op.create_index("ix_canonical_footnote_filing_id", "canonical_footnote", ["filing_id"])

    op.create_table(
        "conversation_memory",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("memory", postgresql.JSONB(astext_type=Text()), nullable=False),
        sa.Column("source_references", postgresql.ARRAY(Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analysis_session.session_id"],
            name="fk_conversation_memory_session_id_analysis_session",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("session_id", "version", name="uq_conversation_memory_version"),
    )

    op.create_table(
        "derived_metric",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=True),
        sa.Column("metric_id", sa.String(length=60), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("value", sa.Numeric(precision=38, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("formula_version", sa.String(length=20), nullable=False),
        sa.Column("input_fact_ids", postgresql.ARRAY(UUID()), nullable=True),
        sa.Column("is_derived_q4", sa.Boolean(), nullable=False),
        sa.Column("comparability_status", sa.String(length=30), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("missing_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_derived_metric_filing_id_filing",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_derived_metric_issuer_id_issuer",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "issuer_id",
            "metric_id",
            "period_end",
            "duration_months",
            "formula_version",
            name="uq_derived_metric_period",
        ),
    )
    op.create_index(
        "ix_derived_metric_series", "derived_metric", ["issuer_id", "metric_id", "period_end"]
    )

    op.create_table(
        "filing_amendment",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("amendment_filing_id", sa.UUID(), nullable=False),
        sa.Column("amends_filing_id", sa.UUID(), nullable=False),
        sa.Column("amendment_form", sa.String(length=20), nullable=False),
        sa.Column("is_complete_replacement", sa.Boolean(), nullable=False),
        sa.Column("sections_changed", postgresql.ARRAY(Text()), nullable=True),
        sa.Column("footnotes_changed", postgresql.ARRAY(UUID()), nullable=True),
        sa.Column("facts_changed", postgresql.ARRAY(UUID()), nullable=True),
        sa.Column("patch_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("detected_by", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "amendment_filing_id <> amends_filing_id",
            name="ck_filing_amendment_amendment_is_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["amendment_filing_id"],
            ["filing.filing_id"],
            name="fk_filing_amendment_amendment_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["amends_filing_id"],
            ["filing.filing_id"],
            name="fk_filing_amendment_amends_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "amendment_filing_id", "amends_filing_id", name="uq_filing_amendment_pair"
        ),
    )

    op.create_table(
        "filing_document",
        sa.Column("document_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("acquisition_strategy", sa.String(length=40), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_filing_document_filing_id_filing",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_filing_document_filing_id", "filing_document", ["filing_id"])
    op.create_index("ix_filing_document_sha256", "filing_document", ["sha256"])

    op.create_table(
        "filing_section",
        sa.Column("section_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("section_type", sa.String(length=40), nullable=False),
        sa.Column("item_number", sa.String(length=10), nullable=True),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("extraction_strategy", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_filing_section_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("filing_id", "section_type", "sequence", name="uq_filing_section_seq"),
    )
    op.create_index("ix_filing_section_filing_id", "filing_section", ["filing_id"])

    op.create_table(
        "xbrl_fact",
        sa.Column("fact_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("accession", sa.String(length=20), nullable=False),
        sa.Column("form", sa.String(length=20), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column(
            "fiscal_year",
            sa.Integer(),
            nullable=True,
            comment="describes the FILING, not this fact",
        ),
        sa.Column(
            "fiscal_period",
            sa.String(length=4),
            nullable=True,
            comment="describes the FILING, not this fact",
        ),
        sa.Column("taxonomy", sa.String(length=40), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("value_as_filed", sa.Text(), nullable=False),
        sa.Column("value_numeric", sa.Numeric(precision=38, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("scale", sa.Integer(), nullable=False),
        sa.Column("sign", sa.SmallInteger(), nullable=False),
        sa.Column("context_id", sa.Text(), nullable=True),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("instant_date", sa.Date(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column(
            "duration_months",
            sa.Integer(),
            nullable=True,
            comment="computed at ingest; charts filter on it",
        ),
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=Text()),
            nullable=False,
            server_default=sa.text("{}"),
        ),
        sa.Column("segment", sa.Text(), nullable=True),
        sa.Column("coregistrant", sa.Text(), nullable=True),
        sa.Column("statement_role", sa.Text(), nullable=True),
        sa.Column("disclosure_role", sa.Text(), nullable=True),
        sa.Column("source_dataset", sa.String(length=60), nullable=False),
        sa.Column("source_row_id", sa.Text(), nullable=True),
        sa.Column("source_anchor", sa.Text(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restates_fact_id", sa.UUID(), nullable=True),
        sa.Column("is_latest_selected", sa.Boolean(), nullable=False),
        sa.Column("validation_status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(period_type = 'instant' AND instant_date IS NOT NULL) OR (period_type = 'duration' AND period_start IS NOT NULL AND period_end IS NOT NULL)",
            name="ck_xbrl_fact_period_fields_match_period_type",
        ),
        sa.CheckConstraint(
            "period_type IN ('instant', 'duration')", name="ck_xbrl_fact_period_type_is_known"
        ),
        sa.CheckConstraint("sign IN (-1, 1)", name="ck_xbrl_fact_sign_is_plus_or_minus_one"),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_xbrl_fact_filing_id_filing",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_xbrl_fact_issuer_id_issuer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["restates_fact_id"],
            ["xbrl_fact.fact_id"],
            name="fk_xbrl_fact_restates_fact_id_xbrl_fact",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_xbrl_fact_accession", "xbrl_fact", ["accession"])
    op.create_index(
        "ix_xbrl_fact_cik_concept_period", "xbrl_fact", ["cik", "concept", "period_end"]
    )
    op.create_index(
        "ix_xbrl_fact_consolidated_series",
        "xbrl_fact",
        ["cik", "concept", "duration_months", "period_end"],
        postgresql_where=sa.text("dimensions = '{}'::jsonb"),
    )
    op.create_index("ix_xbrl_fact_dimensions", "xbrl_fact", ["dimensions"], postgresql_using="gin")
    op.create_index("ix_xbrl_fact_filing_id", "xbrl_fact", ["filing_id"])

    op.create_table(
        "footnote_source_block",
        sa.Column("block_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("footnote_id", sa.UUID(), nullable=True),
        sa.Column(
            "external_id", sa.String(length=120), nullable=False, comment="cited by the model"
        ),
        sa.Column("block_type", sa.String(length=30), nullable=False),
        sa.Column("dera_report_number", sa.Integer(), nullable=True),
        sa.Column("menucat", sa.String(length=4), nullable=True),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("long_name", sa.Text(), nullable=True),
        sa.Column("role_uri", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_anchor", sa.Text(), nullable=True),
        sa.Column(
            "grouping_method",
            sa.String(length=30),
            nullable=True,
            comment="which stage produced this attachment",
        ),
        sa.Column("grouping_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "grouping_evidence",
            postgresql.JSONB(astext_type=Text()),
            nullable=True,
            comment="matched role URI, overlap score, or similarity score",
        ),
        sa.Column(
            "competing_candidates",
            postgresql.JSONB(astext_type=Text()),
            nullable=True,
            comment="alternatives considered and their scores; a tie is never broken silently",
        ),
        sa.Column("extraction_run_id", sa.UUID(), nullable=True),
        sa.Column("grouping_parser_version", sa.String(length=40), nullable=True),
        sa.Column("grouping_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "grouping_method IN ('role_uri', 'toc_reconciliation', 'heading', 'presentation_hierarchy', 'concept_overlap', 'title_similarity', 'filing_order', 'model_adjudication', 'human_review')",
            name="ck_footnote_source_block_source_block_grouping_method_is_known",
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_footnote_source_block_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["footnote_id"],
            ["canonical_footnote.footnote_id"],
            name="fk_footnote_source_block_footnote_id_canonical_footnote",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("filing_id", "external_id", name="uq_footnote_source_block_external"),
    )
    op.create_index(
        "ix_footnote_source_block_extraction_run", "footnote_source_block", ["extraction_run_id"]
    )
    op.create_index(
        "ix_footnote_source_block_footnote_id", "footnote_source_block", ["footnote_id"]
    )
    op.create_index(
        "ix_footnote_source_block_orphans",
        "footnote_source_block",
        ["filing_id"],
        postgresql_where=sa.text("footnote_id IS NULL"),
    )
    op.create_index("ix_footnote_source_block_role_uri", "footnote_source_block", ["role_uri"])

    op.create_table(
        "footnote_summary",
        sa.Column("summary_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("footnote_id", sa.UUID(), nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("model_provider", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=60), nullable=False),
        sa.Column("output_schema_version", sa.String(length=60), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("plain_summary", sa.Text(), nullable=True),
        sa.Column("structured", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("classification", sa.String(length=20), nullable=True),
        sa.Column("validation_status", sa.String(length=30), nullable=False),
        sa.Column("validation_detail", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("batch_job_id", sa.String(length=120), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "validation_status IN ('GENERATED', 'VALIDATING', 'VALIDATED', 'VALIDATED_NORMALIZED', 'SOURCE_PRESENT_AMBIGUOUS', 'SOURCE_NOT_FOUND', 'UNIT_MISMATCH', 'SCALE_MISMATCH', 'PERIOD_MISMATCH', 'SIGN_MISMATCH', 'UNSUPPORTED', 'REQUIRES_REVIEW', 'FAILED')",
            name="ck_footnote_summary_summary_validation_status_is_known",
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_footnote_summary_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["footnote_id"],
            ["canonical_footnote.footnote_id"],
            name="fk_footnote_summary_footnote_id_canonical_footnote",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("footnote_id", "version", name="uq_footnote_summary_version"),
    )
    op.create_index(
        "ix_footnote_summary_active",
        "footnote_summary",
        ["footnote_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index("ix_footnote_summary_filing_id", "footnote_summary", ["filing_id"])
    op.create_index(
        "ix_footnote_summary_review",
        "footnote_summary",
        ["requires_review"],
        postgresql_where=sa.text("requires_review"),
    )

    op.create_table(
        "footnote_table",
        sa.Column("table_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("filing_id", sa.UUID(), nullable=False),
        sa.Column("footnote_id", sa.UUID(), nullable=True),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("column_headers", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("row_labels", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("cells", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("scale", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("period_labels", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("footnote_markers", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("original_html_uri", sa.Text(), nullable=True),
        sa.Column("plain_rendering", sa.Text(), nullable=True),
        sa.Column("source_anchor", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("validation_warnings", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_footnote_table_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["footnote_id"],
            ["canonical_footnote.footnote_id"],
            name="fk_footnote_table_footnote_id_canonical_footnote",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("filing_id", "external_id", name="uq_footnote_table_external"),
    )
    op.create_index("ix_footnote_table_footnote_id", "footnote_table", ["footnote_id"])

    op.create_table(
        "processing_job",
        sa.Column("job_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=400), nullable=False),
        sa.Column("issuer_id", sa.UUID(), nullable=True),
        sa.Column("filing_id", sa.UUID(), nullable=True),
        sa.Column("footnote_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=Text()), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filing.filing_id"],
            name="fk_processing_job_filing_id_filing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["footnote_id"],
            ["canonical_footnote.footnote_id"],
            name="fk_processing_job_footnote_id_canonical_footnote",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuer.issuer_id"],
            name="fk_processing_job_issuer_id_issuer",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_processing_job_idempotency_key"),
    )
    op.create_index("ix_processing_job_filing_id", "processing_job", ["filing_id"])
    op.create_index(
        "ix_processing_job_queue", "processing_job", ["state", "priority", "scheduled_at"]
    )

    op.create_table(
        "llm_invocation",
        sa.Column("invocation_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=80), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=80), nullable=False),
        sa.Column("region", sa.String(length=30), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=True),
        sa.Column("prompt_version", sa.String(length=60), nullable=False),
        sa.Column("request_format", sa.String(length=12), nullable=False),
        sa.Column("response_format", sa.String(length=12), nullable=False),
        sa.Column("request_uri", sa.Text(), nullable=True),
        sa.Column("request_sha256", sa.String(length=64), nullable=True),
        sa.Column("response_uri", sa.Text(), nullable=True),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "request_format IN ('plain_text', 'yaml') AND response_format IN ('plain_text', 'yaml')",
            name="ck_llm_invocation_model_content_format_is_permitted",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["processing_job.job_id"],
            name="fk_llm_invocation_job_id_processing_job",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analysis_session.session_id"],
            name="fk_llm_invocation_session_id_analysis_session",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_llm_invocation_correlation", "llm_invocation", ["correlation_id"])
    op.create_index("ix_llm_invocation_created", "llm_invocation", ["created_at"])
    op.create_index("ix_llm_invocation_session", "llm_invocation", ["session_id"])

    # FINANCIAL-INVARIANT: a filed fact is immutable. A restatement appends a new observation and
    # is_latest_selected is recomputed; it never rewrites history. Enforced in the database so the
    # guarantee holds even against a direct SQL session.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fintek_reject_fact_value_update()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.value_as_filed IS DISTINCT FROM OLD.value_as_filed
               OR NEW.unit IS DISTINCT FROM OLD.unit
               OR NEW.scale IS DISTINCT FROM OLD.scale
               OR NEW.concept IS DISTINCT FROM OLD.concept
               OR NEW.period_start IS DISTINCT FROM OLD.period_start
               OR NEW.period_end IS DISTINCT FROM OLD.period_end
               OR NEW.instant_date IS DISTINCT FROM OLD.instant_date THEN
                RAISE EXCEPTION
                    'xbrl_fact is append-only: a filed value, unit, scale, concept, or period '
                    'may never be updated. Append a new observation instead (fact_id=%)',
                    OLD.fact_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_xbrl_fact_append_only
        BEFORE UPDATE ON xbrl_fact
        FOR EACH ROW EXECUTE FUNCTION fintek_reject_fact_value_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_xbrl_fact_append_only ON xbrl_fact;")
    op.execute("DROP FUNCTION IF EXISTS fintek_reject_fact_value_update();")
    op.drop_table("llm_invocation")
    op.drop_table("processing_job")
    op.drop_table("footnote_table")
    op.drop_table("footnote_summary")
    op.drop_table("footnote_source_block")
    op.drop_table("xbrl_fact")
    op.drop_table("filing_section")
    op.drop_table("filing_document")
    op.drop_table("filing_amendment")
    op.drop_table("derived_metric")
    op.drop_table("conversation_memory")
    op.drop_table("canonical_footnote")
    op.drop_table("analysis_message")
    op.drop_table("listing")
    op.drop_table("issuer_former_name")
    op.drop_table("filing")
    op.drop_table("analysis_session")
    op.drop_table("prompt_version")
    op.drop_table("metric_definition")
    op.drop_table("listing_observation")
    op.drop_table("issuer")
    op.drop_table("excluded_filer")
    op.drop_table("dera_package")
    op.drop_table("dataset_version")
