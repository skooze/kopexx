# SPRINT-0003: Acquire One Issuer's Filings and Establish Reproducible Fixtures

STATUS: IN PROGRESS — acquisition complete, database work blocked
DATE: 2026-08-01
SEQUENCING DECISION: `docs/adr/ADR-0015-thread-first-delivery-sequence.md`

---

## Outcome so far

**Apple's filings are retrieved.** After three sprints in which nothing had been fetched from
EDGAR, the repository now holds four real filings with full provenance.

| Item | Result |
|---|---|
| Filings discovered for CIK 0000320193 | **134** covered filings, 1994-01-26 to 2026-07-31 |
| Reconciliation against `master.gz` | **134 = 134**, zero gaps, zero discrepancies, 131 quarters |
| Filings acquired | FY2025 10-K plus the three FY2025 10-Qs |
| Objects preserved | **20**, 8,827,567 bytes (8.42 MiB) |
| Re-acquisition | 0 downloaded, 20 reused, **0 requests** |
| Throttle events | **0** across every run |
| Fixture tree committed | 188.4 KiB, well under the 25 MB target |
| Tests | 143 → **201 passing**, 2 skipped |

**The overflow path was not optional.** `filings.recent` returned exactly 1,000 entries, its
documented cap, of which 45 were covered forms. The remaining **89 came from the overflow shard**.
Reading only `recent` would have silently lost 66 percent of Apple's history, and the loss would
have looked identical to a company that simply files less.

**The 13-not-58 correction is now confirmed against data we hold.** The acquired
`FilingSummary.xml` contains 71 `<Report>` elements: 2 Cover, 6 Statements, 16 Notes, 1 Policies,
12 Tables, 33 Details, plus one navigation entry. Of the 16 `menucat='Notes'` candidates, exactly
three are the Item 408 and Item 1C disclosures. 16 − 3 = 13.

### Two defects found by real data

1. **The client rejected the primary document.** `_assert_not_error_page` treated any HTML body as
   an error page. That was right for the DERA mirror, where HTML meant a failure, and wrong here:
   a filing's primary document *is* HTML. Fixed with an `expect_html` flag that keeps the
   directory-listing check active, because a folder index is also HTML and is the corruption the
   guard exists to catch.

2. **Gzip was misread as truncation.** SEC serves `.htm` and `.xml` gzipped, so `Content-Length`
   is the *compressed* size while httpx yields decompressed bytes. The completeness check compared
   the two and reported a truncated download of a file that arrived whole: 1,520,208 bytes
   received against a declared 111,447. The DERA path never saw this because SEC does not
   re-compress a `.zip`. The check now skips the comparison when `Content-Encoding` is set.

Both are covered by regression tests.

### A refinement to the recorded report count

The 71st `<Report>` is `All Reports`, `ReportType: Book` — the renderer's own table of contents,
with no menu category, role, or file. So the filing has **70 real reports plus one navigation
entry**. Counting it would put every downstream total off by one.

### Blocked

**PostgreSQL is unavailable, so step 1 did not run.** The two live migration tests still skip, and
the DERA TSV load is deferred with them. See "Known issues" below for the exact commands.

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

## Known issues

1. **PostgreSQL is unavailable on this machine, so the two live migration tests still skip.**
   Every fallback in the plan was tried:

   ```
   $ docker run --rm hello-world
   docker: Error response from daemon: failed to create task for container:
   failed to start shim: start failed: failed to create TTRPC connection:
   unsupported protocol: Yunix

   $ docker compose version
   docker: unknown command: docker compose      # plugin absent

   $ sudo -n true
   sudo: a password is required                  # cannot install a system package

   $ pip index versions pgserver
   ERROR: No matching distribution found         # no rootless PostgreSQL from PyPI

   $ command -v podman
   (not installed)
   ```

   The Docker daemon runs (server 29.4.1) but cannot start containers; the shim failure is the
   same one Sprint 2 recorded. **This needs an action outside the agent's reach.** Either:

   ```
   sudo pacman -S postgresql
   sudo -u postgres initdb -D /var/lib/postgres/data
   sudo systemctl start postgresql
   sudo -u postgres createuser -s fintek && sudo -u postgres createdb -O fintek fintek
   ```

   or repair the Docker containerd shim so `make up` works.

   Once a server answers on 5432, `pytest tests/unit/test_migrations.py` runs the two tests that
   have never executed, and the DERA TSV load can follow.

2. **DERA TSV loading is deferred with the database.** The parser can be written against the
   mirrored packages without a server, but the acceptance criterion is a row-count reconciliation
   after loading, which cannot be met yet.

3. **URGENT-02 is still open.** The twelve monthly DERA packages, 2.00 GiB, exist in exactly one
   place and cannot be re-downloaded once SEC publishes the 2025q3 consolidation. A second copy on
   the same disk is not a second copy. This needs a destination decision.

4. **Only the inline-XBRL era is implemented.** `standalone_xbrl`, `html_no_xbrl`, and
   `pem_armored` raise `UnsupportedEraError` rather than guessing. That covers the four target
   filings and everything from roughly 2019; the other 104 of Apple's 134 filings need Stage 2
   phase W-2.

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
