# Footnote Table Model

IMPLEMENTATION STATUS: PLANNED (Phase 5)
OWNER PACKAGE: `packages/table_parser`

Footnote tables are first-class evidence. A maturity schedule, a tax rate reconciliation, or a
fair-value hierarchy carries the substance of its footnote. Collapsing one into unstructured text
destroys the units, periods, and hierarchy that make it meaningful.

## Schema

```
footnote_table
  table_id              uuid primary key
  canonical_footnote_id uuid references canonical_footnote
  filing_id             uuid not null references filing
  title                 text
  subtitle              text
  sequence              integer not null
  column_headers        jsonb not null      -- ordered, may be multi-level
  row_labels            jsonb not null      -- ordered, may be hierarchical
  cells                 jsonb not null      -- [{row, col, value, raw, colspan, rowspan}]
  unit                  text                -- USD, USD_millions, percent, shares, years
  scale                 integer             -- 1, 1000, 1000000
  currency              text
  period_labels         jsonb               -- per column
  footnote_markers      jsonb               -- superscript markers and their text
  original_html_uri     text not null       -- object storage, never discarded
  normalized_json       jsonb not null
  plain_rendering       text not null       -- for model consumption and search
  source_anchor         text
  parser_version        text not null
  confidence            numeric not null
  validation_warnings   jsonb
```

## Structural cases that must not be flattened

| Case | Handling |
|---|---|
| Multi-level column headers | `column_headers` is a nested list; the leaf carries the period |
| Hierarchical row labels | `row_labels` carries depth so indentation survives |
| Cell spans | `colspan` and `rowspan` retained; a spanned cell is not duplicated |
| Repeated headers mid-table | Detected and collapsed; recorded in warnings |
| Blank cells | Null, never zero. The distinction is material |
| Footnote markers in cells | Extracted to `footnote_markers`, not left in the value |
| Multi-table footnotes | Each table is its own row; `sequence` preserves order |
| Unit in the caption | Parsed to `unit` and `scale`; not re-applied to values that already carry it |
| Negative in parentheses | Normalized to a negative number; the raw string is retained |

## Domain-specific tables

Maturity schedules, fair-value hierarchies, tax rate reconciliations, segment tables, lease
maturity tables, debt schedules, pension roll-forwards, and acquisition purchase-price
allocations each have a recognizer that asserts expected shape and emits a warning when the table
does not match, rather than silently mis-parsing.

## Two renderings

The model receives **both**:

```
a compact structured representation   columns and rows, or records when sparser
a readable rendering                  aligned text preserving row and column relationships
```

Both are YAML or plain text. Neither is Markdown, neither is HTML. The payload compiler chooses
the row-oriented or record-oriented form by measured token count, and never sends the same table
twice in one request.

## Validation

Row and column counts consistent with the cell set. Every cell resolvable to a row and a column.
Units present or explicitly unknown. Numeric cells parseable. A table failing validation is stored
with warnings and its footnote routed to review, never silently dropped.
