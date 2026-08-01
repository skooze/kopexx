# SPRINT-0003: Acquire One Issuer's Filings and Establish Reproducible Fixtures

STATUS: PLANNED
PLANNED DATE: after the Sprint 2 alignment review
SEQUENCING DECISION: `docs/adr/ADR-0015-thread-first-delivery-sequence.md`

---

## Objective

**Retrieve and preserve one real issuer's current filings, and make the canonical-footnote result
reproducible.**

After two sprints the repository holds 25.36 GiB of DERA statistical data, a verified SEC HTTP
client, a 24-table schema, and a hardened model gateway — and has not retrieved a single SEC
filing. Requirement 1 of fifteen has not started. This sprint ends that.

It is deliberately narrow: one company, four filings, one DERA partition, one filing era.

---

## Scope

**In scope.** Live PostgreSQL. The two skipped live migration tests. DERA TSV loading for one
partition. Filing discovery for CIK `0000320193`. Inline-XBRL-era acquisition. Four Apple
filings preserved with provenance. A documented fixture strategy. The item-disclosure exclusion
list exercised by a test. URGENT-02.

**Out of scope.** Any other issuer. Any other filing era. Any other DERA partition. Footnote
canonicalization (Sprint 4). Summarization (Sprint 5). Any API or UI. S3. Deployment.

---

## Ordered plan

### 1. Live database, first

Nothing else in this sprint is verifiable without it, and it is the oldest open blocker.

```
docker compose up -d postgres
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

**The two currently skipped tests must pass, not skip.** They are the only tests in the suite
that have never executed. If Docker still cannot start containers — Sprint 2 recorded
`unsupported protocol: Yunix` — the fallback order is: a system PostgreSQL package, then a
PostgreSQL binary from the distribution, then Podman. If none works, that is a hard blocker to
report rather than route around, because Sprint 4 onward writes real rows.

The migration regenerated during the alignment review adds the per-attachment grouping audit
columns and the two non-derivable completeness columns. It has never been applied anywhere, so
this is its first real execution.

### 2. Minimum DERA partition

Load only the partition covering the target filings, not all 78 packages.

```
partition          2025q3 if published, otherwise the monthlies covering 2025-07 onward
tables             sub, num, pre, tag, ren, txt
parsing            quoting DISABLED — a quote character inside a footnote is data, not a delimiter
readme.htm         ignored; it is stale inside the archives
```

Reconcile loaded row counts against the package's own `sub.tsv` count. A silent short load is
the failure mode that would poison everything downstream.

### 3. Filing discovery, one CIK

`packages/filing_discovery`, built for one CIK but with no CIK-specific logic.

```
submissions API    data.sec.gov, PADDED CIK
filings.recent     caps at 1,000 entries
filings.files[]    the overflow files; roughly 35 percent of CIKs need them
master.gz          quarterly index, for gap reconciliation
```

Apple has filed since 1994 and will exceed the `recent` cap, so the overflow path is exercised
on the first issuer rather than discovered later. Reconcile the discovered 10-K and 10-Q set
against `master.gz` and assert zero gaps.

### 4. Inline-XBRL-era acquisition

`packages/filing_acquisition`, current era only.

```
-xbrl.zip          narrative plus all linkbases; ~33x smaller than the complete .txt
extracted instance primaryDocument[:-4] + "_htm.xml", published by SEC
                   we never implement iXBRL transformation ourselves
.xsd               carries statement and disclosure role classification
```

Every acquisition records URI, SHA-256, byte size, MIME type, retrieval timestamp, and the
acquisition strategy used. A directory listing is rejected, never stored as filing content — the
client already enforces this and the test already exists.

### 5. Target filings

```
Apple Inc.  CIK 0000320193

FY2025 10-K    0000320193-25-000079    the verified filing: 13 footnotes, 46 child blocks
FY2025 Q3 10-Q
FY2025 Q2 10-Q
FY2025 Q1 10-Q
```

Four filings: one annual and three quarterly, so Sprint 4 exercises both footnote profiles and
Sprint 6 has a real quarterly series with a derivable Q4.

### 6. Exclusion definitions

`metric_definitions/item_disclosure_exclusions.yaml` was added during the alignment review. This
sprint gives it a test asserting that the three Apple Item-408 and Item-1C candidates resolve to
exclusion, and that an unrecognised namespace resolves to `flag_for_review` rather than to either
default.

### 7. URGENT-02

Second durable copy of the twelve irreplaceable monthly packages, 2.00 GiB. They currently exist
in exactly one place and cannot be re-downloaded once SEC publishes the 2025q3 consolidation.

---

## Fixture strategy — DECIDED

**Chosen: small deterministic extracted fixtures committed to Git, plus raw sources in local
object storage, plus committed retrieval manifests carrying hashes.**

Apple's FY2025 10-K is roughly 11 MB as a complete submission. Four filings with linkbases would
add tens of megabytes of binary-like content to every clone, forever, for content the SEC already
hosts authoritatively.

```
COMMITTED TO GIT                                             approximate size
  tests/fixtures/filings/manifest.yaml                       ~4 KB
      accession, form, period, primary document, source URL, SHA-256, byte size,
      retrieval timestamp, acquisition strategy
  tests/fixtures/filings/0000320193-25-000079/
      filing-summary.xml            renderer report inventory                 ~40 KB
      report-inventory.yaml         normalized menucat, role URI, names       ~12 KB
      note-headings.txt             parsed headings for stage 5               ~2 KB
      toc-notes.txt                 TOC notes section for stage 4             ~1 KB
      footnotes/note-01..13.txt     extracted footnote text, normalized       ~180 KB
      tables/*.yaml                 parsed tables from those notes            ~60 KB
      expected-canonicalization.yaml  13 footnotes, 46 attachments, 3 exclusions ~8 KB
  (three 10-Qs, same shape, smaller)

NOT COMMITTED
  the complete -xbrl.zip archives, linkbases, and full primary documents
  -> var/objects/, gitignored, reproducible from the manifest URLs

TOTAL GIT GROWTH: target under 25 MB, hard ceiling 40 MB
```

**Why not Git LFS.** LFS solves storage, not reproducibility: a clone without the LFS objects
fetched has fixture files that are pointer stubs, and the test suite fails in a way that looks
like a code defect. It also adds a bandwidth-metered dependency to a project that currently has
none. Revisit only if a later sprint proves that byte-exact original documents are genuinely
required for a test that extracted fixtures cannot express.

**Why not commit the full filings.** They are large, binary-like, and permanently in history.
The SEC hosts them authoritatively and the manifest hashes prove exactly which bytes were used.

**What makes this reproducible.** The manifest pins accession, URL, and SHA-256. A verification
command re-fetches from SEC and confirms the hashes still match, so the extracted fixtures are
provably faithful to a specific filed document. The extracted fixtures are deterministic text,
so they diff cleanly in review — which the raw archives would not.

**Offline requirement.** `pytest` must pass on a fresh clone with **no network**. Every Sprint 4
test reads only committed fixtures. Re-fetching is a separate opt-in command, never part of the
default suite.

---

## Acceptance criteria

1. `alembic upgrade head` and `alembic downgrade base` both succeed against a real PostgreSQL.
2. The two previously skipped live migration tests **pass**; the suite reports zero skips for
   database reasons.
3. One DERA partition is loaded and its row counts reconcile against the package.
4. Filing discovery for CIK `0000320193` returns the complete 10-K and 10-Q history and
   reconciles gap-free against `master.gz`.
5. The `filings.files[]` overflow path is exercised, not merely coded.
6. Four filings are preserved with SHA-256, provenance, and acquisition strategy recorded.
7. Re-running acquisition downloads nothing and re-verifies by content address.
8. Committed fixtures reproduce the four filings' structure offline.
9. `pytest` passes on a fresh clone with no network access.
10. Repository growth is under 25 MB, measured and reported.
11. The exclusion list resolves Apple's three item disclosures and flags unknown namespaces.
12. URGENT-02 discharged: a second durable copy of the twelve monthly packages exists.
13. Zero SEC throttle events.

---

## Tests to be added

```
tests/unit/test_filing_discovery.py       recent-cap overflow, master.gz reconciliation,
                                          padded vs unpadded CIK by host, dashed vs undashed
                                          accession by URL position, agent-prefix accession
tests/unit/test_filing_acquisition.py     era routing, xbrl.zip strategy, extracted-instance
                                          URL derivation, directory-listing rejection,
                                          idempotent re-acquisition
tests/unit/test_dera_load.py              quoting disabled, row-count reconciliation,
                                          irregular filename handling, stale readme ignored
tests/unit/test_item_exclusions.py        three Apple exclusions, unknown namespace flags
tests/unit/test_fixture_manifest.py       every fixture hash matches its manifest entry;
                                          offline suite touches no network
tests/unit/test_migrations.py             the 2 live tests now RUN
```

---

## Risks

| Risk | Mitigation |
|---|---|
| Docker still cannot start containers | Fallback order documented above; a hard blocker is reported, not routed around |
| 2025q3 DERA partition not yet published | Use the monthly packages already mirrored; they cover the period |
| Apple's filing count exceeds the `recent` cap in an unanticipated shape | This is the point of choosing an issuer with a long history first |
| Fixture extraction bakes in a parser bug | `expected-canonicalization.yaml` is derived from the live filing and reviewed against the source document, not generated by the code it will test |
| Repository bloat | Hard ceiling of 40 MB; measured and reported in the sprint record |

---

## Definition of done

Every acceptance criterion passes. Documentation is synchronized. `techspecs.md` records the new
packages with accurate status. `roadmap.md` marks Sprint 3 complete and Sprint 4 next. The sprint
record reflects actual completed work, including anything that did not work.

**Then stop and request commit approval**, per `rules.md` section 15. Committing is not part of
sprint completion.

---

## Next sprint

**SPRINT-0004: reproduce and validate canonical-footnote extraction.** Stages 1 through 5 only,
against the fixtures this sprint produces. Target: exactly 13 canonical footnotes, 46 of 46 child
blocks attached, zero orphans, three item disclosures routed to `filing_section`.
