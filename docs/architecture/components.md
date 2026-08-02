# Component Reference

Each entry states responsibility, inputs, outputs, public interface, dependencies, prohibited
dependencies, data owned, data explicitly not owned, invariants, failure modes, retry behaviour,
security, observability, scaling, and test approach.

For the seven IMPLEMENTED components, full detail is in `techspecs.md` section 3. This document
covers the planned components so the specification is complete before the code exists.

---

## issuer_registry — PLANNED (Stage 2 phase W-1)

RESPONSIBILITY. Maintain the temporal issuer registry and compute the active universe.
INPUTS. Ticker snapshots, submissions metadata, quarterly indexes.
OUTPUTS. Issuer records, listings with validity windows, exclusions with reasons.
PUBLIC INTERFACE. `resolve_ticker(ticker, as_of)`, `get_issuer(cik)`, `active_universe()`,
`record_observation(snapshot)`.
DEPENDENCIES. `sec_identity`, `storage`, PostgreSQL.
PROHIBITED. Must not fetch from SEC directly; acquisition belongs to `sec_client`.
DATA OWNED. Issuers, listings, listing observations, exclusions, relationships.
NOT OWNED. Filings, facts.
INVARIANTS. Ticker resolution is always as-of a date. A ticker is never unique on its own. A
delisted former filer stays in the universe. Every exclusion carries a reason.
FAILURE MODES. Ambiguous ticker returns candidates rather than picking one. A snapshot that
disagrees with the previous one is recorded, not overwritten.
RETRY. Snapshot fetch is retryable; resolution is pure.
SECURITY. None beyond standard access control.
OBSERVABILITY. Universe size, exclusions by reason, ambiguous resolutions, snapshot drift.
SCALING. Read-heavy, cacheable.
TESTS. Ticker reuse resolution, former-name reconciliation, snapshot union, exclusion
classification.

## filing_discovery — IMPLEMENTED (Sprint 3), one issuer

RESPONSIBILITY. Enumerate every 10-K and 10-Q for covered issuers, across all history.
INPUTS. `submissions.zip`, per-issuer submissions JSON, `filings.files[]` shards, `master.gz`.
OUTPUTS. Filing records with accession, form, dates, primary document, XBRL flags, era.
PUBLIC INTERFACE. `discover_all()`, `discover_issuer(cik)`, `reconcile(cik)`.
INVARIANTS. `filings.recent` is never the only source. `submissions.zip` is streamed, never
expanded. Accessions deduplicate. Discovery reconciles against the independent quarterly index.
FAILURE MODES. Missing shard is a hard error, not a silent truncation.
OBSERVABILITY. Filings discovered per issuer, reconciliation discrepancies, watermark age.
TESTS. Overflow shard handling, `25-NSE` duplicate rows, reconciliation mismatch.

## filing_acquisition — IMPLEMENTED (Sprint 3), inline-XBRL era only

RESPONSIBILITY. Fetch and preserve source objects using the era decision table.
INVARIANTS. Era branch chosen from the filing record. Rejection assertions run before persistence.
Every object records URL, hash, size, headers, strategy, and time.
FAILURE MODES. Directory listing, empty primary document, missing ZIP member, error-page hash
match, accession mismatch. All are permanent, none retried.
SCALING. Bounded by the SEC rate limit, not by workers.
TESTS. One golden fixture per era; resumability under `kill -9`.

## filing_parser — PLANNED (Sprint 5; other eras Stage 2 W-2)

RESPONSIBILITY. Turn a preserved source object into sections, footnote blocks, tables, and facts.
PUBLIC INTERFACE. The `FilingParser` protocol; five era implementations.
INVARIANTS. Every result reports parser id, version, source hash, era, warnings, confidence, and
counts. A failure is never downgraded to a warning.
FAILURE MODES. Encoding failure, unresolved continuation chain, malformed table, missing heading.
TESTS. Golden fixtures per era; the short-block assertion catching silent continuation failure.

## fact_lake — PLANNED (Sprint 6)

RESPONSIBILITY. Store filed facts immutably and compute selection separately.
INVARIANTS. `value_as_filed` is append-only, enforced by trigger. `duration_months` computed at
ingest. Restatements append.
TESTS. Update rejection, selection recomputation idempotency, dimensional preservation.

## footnote_extractor — IMPLEMENTED (Sprint 4)

RESPONSIBILITY. Report what a filing contains and decide nothing: renderer report inventory,
candidate discovery, child-block extraction, and `Note N —` heading parsing.
PUBLIC INTERFACE. `inventory()`, `candidates()`, `child_blocks()`, `note_headings()`.
INVARIANTS. No classification, no grouping, no exclusion. Every block keeps its own identity,
role URI, `menucat`, and hash so grouping can only ever add an edge, never destroy a source.
FAILURE MODES. Missing `FilingSummary.xml`, unparseable report entry, absent heading block — each
reported, never inferred around.
TESTS. 25, against the preserved bytes of all four Apple filings.

## footnote_canonicalizer — IMPLEMENTED (Sprint 4), stages 1-5; fallback stages Stage 2 W-3

RESPONSIBILITY. Produce canonical footnotes and attach every source block and table.
FULL SPECIFICATION. `docs/footnotes/canonicalization-algorithm.md`.
PUBLIC INTERFACE. `canonicalize()`, `persist()`, `resolve_table_ownership()`.
INVARIANTS. Source identity survives grouping. Every decision records stage, confidence, and
evidence. An unattachable block keeps a null parent and enters review; it is never force-attached.
No model participates: every decision is a string comparison or a count, enforced by an AST guard.
MEASURED. 43 canonical footnotes across four filings, 117 of 117 child blocks attached by role-URI
prefix at confidence 1.0, zero orphans, zero ambiguous multi-parent matches, zero unresolved
tables. Persistence is idempotent — a rerun inserts 0 and leaves a byte-identical digest.
FAILURE MODES. TOC or heading count mismatch produces `PARTIAL`, never a silent `COMPLETE`.
TESTS. 36 unit, plus offline fixture regressions for the 10-K and each 10-Q with mutation proofs,
and live persistence tests for idempotency.

## table_parser — IMPLEMENTED (Sprint 4)

RESPONSIBILITY. Row and column structure, header hierarchy, cell provenance, and exact numeric
text for the tables inside footnotes.
INVARIANTS. No financial interpretation. **No float conversion of a filed value** — the filed text
is preserved exactly, because a parse that rounds is a parse that has altered a filed number.
TESTS. 28, plus the ownership census that assigns every table to its owning footnote.

## summarization — PLANNED (Sprint 5)

RESPONSIBILITY. One summary per canonical footnote, batched offline.
INVARIANTS. One canonical footnote per model request. Every source block and table supplied.
Never invoked on the dashboard path.
DEPENDENCIES. `llm_gateway` only; never a provider SDK.
TESTS. Coverage property test; batch expiry re-queue.

## validation — PLANNED (Sprint 5)

RESPONSIBILITY. Schema, identity, source, citation, numeric, period, unit, scale, sign, and
coverage validation of every summary.
INVARIANT. An unvalidated summary is never published or displayed.

## retrieval — PLANNED (Sprint 7)

RESPONSIBILITY. Scope-filtered hybrid search over summaries and source content.
INVARIANT. Scope predicates are applied in the query builder, never as a post-filter.

## deep_analysis — PLANNED (Sprint 7)

RESPONSIBILITY. Session lifecycle, scope enforcement, retrieval orchestration, memory, budgets.
INVARIANT. Scope is immutable and server-side. Tools re-derive the allowlist per call.
