# ADR-0005: Group canonical footnotes by XBRL role URI, with an ordered fallback chain

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

The product requires exactly one summary per actual financial-statement footnote. Getting the
unit of work wrong multiplies both cost and confusion.

An earlier version of this architecture asserted that Apple's FY2025 10-K contains 58 note
sections, derived from counting XBRL TextBlock facts. Direct verification against the filing
disproved it.

Measured on accession 0000320193-25-000079:

    XBRL TextBlock facts ................................ 58
    FilingSummary <Report> elements ..................... 71
    Reports with MenuCategory "Notes" ................... 16
    Actual numbered footnotes in the filed document ..... 13

The 71 reports break down as Details 33, Notes 16, Tables 12, Statements 6, Cover 2, Policies 1,
and one uncategorised. The 16 in the Notes category include three that are not financial-statement
footnotes at all: Insider Trading Arrangements and Insider Trading Policies and Procedures, which
are Item 408 disclosures, and Cybersecurity Risk Management and Strategy, which is an Item 1C
disclosure. Removing those leaves 13, matching the 13 `Note N` headings parsed from the primary
document exactly.

Testing role URI as a grouping key: all 46 Tables, Details, and Policies reports matched a parent
note by role URI prefix, with zero unmatched. The distribution is uneven and sensible, with Income
Taxes carrying 6 child blocks and Debt carrying 5.

## Decision

A canonical footnote is one actual numbered or titled financial-statement footnote. It is the
unit of summarization and the unit displayed to a user.

Grouping proceeds through an ordered chain. Stage 3 is the primary mechanism; later stages exist
because Stage 3 is unavailable before 2009 and unverified beyond one filing.

    1. Candidate discovery from the Notes menu category
    2. Exclusion of filing-item disclosures that are not financial-statement footnotes
    3. Attachment of child blocks to parents by XBRL role URI prefix
    4. Reconciliation against the filing table of contents
    5. Reconciliation against parsed note headings
    6. Presentation-hierarchy fallback
    7. Concept-overlap fallback
    8. Title-similarity fallback
    9. Filing-order fallback
    10. Model adjudication for genuinely ambiguous residue
    11. Human review

Every source block retains its own identity, role URI, menu category, and hash after grouping.
Grouping adds an edge; it never destroys a source record. Every grouping decision records the
stage that produced it and a confidence value.

## Alternatives Considered

One summary per TextBlock fact. Rejected: produces 58 records for a 13-footnote filing,
fragmenting each real footnote across its narrative, policy, table, and detail pieces, and
multiplying summarization cost roughly 4.5-fold while making the dashboard incoherent.

One summary per Notes-category report. Rejected: over-counts by including Item 408 and Item 1C
disclosures, which belong in the filing sections model instead.

Model-driven grouping as the primary mechanism. Rejected: grouping determines the unit of work
and therefore the completeness invariant. It must be deterministic and auditable, with the model
used only for residue.

## Consequences

The canonical footnote count is defensible and reconcilable against the filing itself.
Summarization cost is computed on the correct unit. Two additional tables are required, and the
Item-disclosure exclusion list is a maintained artifact that will drift as SEC adds tagging
mandates.

The 100 percent attachment rate is a single-filing result. It must not be presented as a general
guarantee. Stage 2 phase W-3 validates breadth across at least 25 issuers spanning all four eras before
scale-out.

Pre-2009 filings have no role URIs at all, so Stage 3 is unavailable and grouping there depends
on the text-only stages with materially lower confidence.

## Migration Impact

Changing the grouping method requires regrouping affected filings and superseding their summaries,
which the summary versioning model supports without data loss.

## Revisit Conditions

Revisit if breadth validation shows role-URI attachment below roughly 95 percent across the
sample, if a filing agent is found to construct role URIs differently, or if SEC changes the
renderer metadata.
