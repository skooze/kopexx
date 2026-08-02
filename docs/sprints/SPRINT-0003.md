# SPRINT-0003: Acquire One Issuer's Filings and Establish Reproducible Fixtures

STATUS: COMPLETE — all thirteen acceptance criteria met; see the audit at the end
DATE: 2026-08-01
SEQUENCING DECISION: `docs/adr/ADR-0015-thread-first-delivery-sequence.md`

COMMITTED as three separately approved commits, each pushed to `origin/main` on 2026-08-01:

```
2672222   Retrieve and preserve one issuer's filings
1e9f343   Verify the control-plane schema and secure the DERA monthly archive
bc9aeb6   Load one issuer's DERA facts and reconcile them
```

Sprint completion and committing are separate events; `rules.md` section 15 requires explicit
approval for each commit and section 20 requires each SHA to be recorded here. The work was
approved and committed in three stages, which is why there are three SHAs rather than one.

---

## Outcome

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
| DERA facts loaded and reconciled | **2,845** across those four filings |
| Tests | 143 → **337 passing**, 0 skipped |

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

### PostgreSQL — done

Installed locally rather than via Docker, whose containerd shim cannot start containers on this
host. **PostgreSQL 18.4**, cluster at `/var/lib/postgres/data`, service `postgresql` active,
`listen_addresses = localhost`.

**On this development host, no database credential is stored.** Authentication is `peer` over
the Unix socket with a `pg_ident` map from the local OS user to the `fintek` role, so there is no
password in a file. `DATABASE_URL` carries a role name and a socket path, neither of which is a
secret.

Verified against the catalog rather than assumed:

```
select rolname, rolpassword is null as no_verifier from pg_authid where rolname='fintek'
fintek|t
```

`no_verifier` is true, so no SCRAM verifier exists for the role. `pg_authid` is superuser-only, so
this required one privileged read; an unprivileged session cannot answer it — `pg_roles` masks
`rolpassword` as `********` for every role whether or not one is set, and a rejected TCP login is
consistent with either state.

**This scoping matters.** It describes the local host only. CI deliberately uses a disposable
password, and deployment authentication is undecided.

**This is a local-development arrangement and says nothing about deployment.** Peer
authentication works because the client and the server share a host and a kernel that can vouch
for the connecting UID. A deployed database will not have that property and will need its own
mechanism — managed credentials, IAM authentication, or client certificates. That decision has
not been made and must not be inferred from this configuration.

| Operation | Result |
|---|---|
| `alembic upgrade head` | exit 0, 24 domain tables created |
| `alembic downgrade base` | exit 0, 0 domain tables; only `alembic_version` remains |
| `alembic upgrade head` | exit 0, 24 domain tables, revision `0001_initial (head)` |
| Live schema | see the catalog table below |
| **Full suite at that point** | **203 passed, 0 skipped** — the first run in this project where every test executed |

The two tests that had never executed in this project now pass:
`test_upgrade_then_downgrade_round_trips` and `test_filed_fact_cannot_be_updated`.

#### Live schema, counted from the PostgreSQL catalog

Every figure below is restricted to the `public` schema. System schemas are excluded.

| Object | Count | Counting method |
|---|---|---|
| Domain tables | **24** | `pg_class` `relkind='r'`, excluding `alembic_version` |
| User tables total | **25** | the same, including `alembic_version` |
| Primary-key constraints | 25 | `pg_constraint` `contype='p'` |
| Unique constraints | 19 | `contype='u'` |
| Foreign-key constraints | 29 | `contype='f'` |
| Check constraints | **23** | `contype='c'` |
| Explicit indexes | **37** | indexes not backing a PK or UNIQUE constraint |
| Indexes total | **81** | `pg_indexes`; 25 PK-backing + 19 unique-backing + 37 explicit |
| Partial indexes | 7 | `pg_index.indpred IS NOT NULL` |
| User triggers | 1 | `pg_trigger`, non-internal |

**Two counting methods exist and they are not interchangeable.**

*Model metadata* comes from SQLAlchemy reflection or `Base.metadata`. It answers "what does the
code declare?" and is what the structural tests assert against. Its index count omits
primary-key-backing indexes, which is why reflection reports 56 where the catalog reports 81:
`81 − 25 PK-backing = 56`.

*Catalog counts* come from `pg_class`, `pg_constraint`, `pg_indexes`. They answer "what actually
exists in this database?" and include objects PostgreSQL creates on its own behalf. Migration
verification uses these.

The 24-versus-25 table difference is **`alembic_version`**, which Alembic creates and the
application does not model.

An earlier draft of this record reported 25 check constraints. That figure came from a
`pg_constraint` query with no schema filter, which swept in `cardinal_number_domain_check` and
`yes_or_no_check` from `information_schema`. The application schema has **23**.

### Two defects the live database exposed

Both were invisible to offline DDL generation, which writes SQL text without ever sending it to
a server.

**1. The migration could not apply at all.** `xbrl_fact.dimensions` declared
`server_default="{}"`. SQLAlchemy emits a bare string server default as *raw SQL*, so the DDL
read `DEFAULT {}` — a syntax error. Corrected to `server_default=text("'{}'::jsonb")`, which
matches the partial index below it that had always spelled the literal correctly.

**2. The append-only test was vacuous.** It attempted
`UPDATE xbrl_fact SET value_as_filed = '1' WHERE false`. `WHERE false` matches zero rows and the
guard is a `FOR EACH ROW` trigger, so it never fired and the statement always succeeded. The test
could not fail regardless of what the schema did. Rewritten to insert a real fact and attempt to
change its filed value. Proven non-vacuous: dropping the trigger makes it fail, restoring it
makes it pass.

The trigger itself was always correct. Verified directly: an `UPDATE` of a filed value is
rejected with *"xbrl_fact is append-only: a filed value, unit, scale, concept, or period may
never be updated"*, the stored value is unchanged, and non-filed columns such as
`is_latest_selected` remain updatable — which restatement handling requires.

### URGENT-02 — discharged

All twelve monthly DERA packages copied to a second, genuinely separate filesystem.

| Item | Value |
|---|---|
| Packages | **12 of 12 verified** |
| Bytes | 2,145,477,071 |
| Source device / destination device | different, confirmed by `stat` |
| Verification | source SHA-256 against the ledger, destination SHA-256 after copy, ZIP CRC on every member |
| Second run | **0 bytes copied**, 2,145,477,071 reused, every hash re-verified |
| Source files | neither modified nor deleted |

A manifest and a plain-text verification report sit beside the copy.

**The destination mount is not persistent.** The backup lives on a second block device mounted at
a path outside the repository, but `/etc/fstab` has no entry for it and there is no systemd mount
unit — the unit systemd reports is a runtime object synthesised from the live mount table. After a
reboot the device will not remount on its own and the path will be empty until someone mounts it.

The copied data is unaffected: it is on the device, verified, and independent of the source disk.
But **do not treat the backup path as automatically available.** Re-run the verification after any
reboot before relying on it. Making the mount persistent is a one-line `fstab` change and has not
been made, because modifying `/etc/fstab` was outside what was authorised. The exact entry, the
reasoning for `UUID=` and `nofail`, the pre-reboot validation, and the post-reboot check are now
recorded in `docs/runbooks/dera-backup-mount.md`. Persistence is **not** an exit criterion:
criterion 12 asks that a second durable copy exists, and it does.

---

## The DERA fact load — done

**The fact lake holds real filed data for the first time.** 2,845 facts across the four target
filings, every one reconciled against the package it came from.

| Filing | Facts | Consolidated | Dimensional | Package | Cadence |
|---|---|---|---|---|---|
| `…-25-000079` 10-K FY2025 | 967 | 547 | 420 | `2025_10_notes.zip` | monthly |
| `…-25-000073` 10-Q Q3 | 683 | 317 | 366 | `2025_08_notes.zip` | monthly |
| `…-25-000057` 10-Q Q2 | 672 | 309 | 363 | `2025q2_notes.zip` | quarterly |
| `…-25-000008` 10-Q Q1 | 523 | 231 | 292 | `2025q1_notes.zip` | quarterly |

### The package is chosen by reading, not by arithmetic

The sprint plan guessed `2025q3`. That is wrong for three of the four filings, and the reason is
a rule worth stating plainly:

**A filing belongs to the DERA package for the period it was SUBMITTED in, not the period it
reports on.** The FY2025 10-K covers a year ending 2025-09-27 and was filed 2025-10-31, so it
lives in `2025_10`. `locate_filing` reads each package's `sub.tsv` and answers from the data.
Deriving a period from a report date is exactly the kind of off-by-one-quarter error that produces
a confident, wrong, silent result — the load would simply find nothing and report a filing with no
facts, which is indistinguishable from a filing that has none.

### Ten modules, one responsibility each

| Module | Owns |
|---|---|
| `selection` | which package holds a filing; archive completeness; period ordering |
| `tsv` | parsing, with quoting DISABLED, streaming |
| `dimensions` | `dimh` to axis and member, from `dim.tsv` |
| `normalize` | row to domain values, including the derived period start |
| `validate` | domain rules mirroring the database constraints |
| `registration` | the `issuer` and `filing` rows the fact foreign keys require |
| `loader` | one transaction: insert, load ledger, idempotency, advisory lock |
| `reconcile` | nine checks against the source and the database |
| `report` | plain text for a person |
| `scripts/load_dera_partition.py` | orchestration only — no parsing, no validation, no SQL |

### Reconciliation

Nine checks per load, all passing on all four filings. The strongest is the numeric total: the sum
of every accepted `value_numeric` computed in Python against PostgreSQL's own `sum()`.

```
every_matched_row_is_accounted_for   969 = 967 accepted + 2 rejected
database_row_count_matches_accepted  967 = 967
natural_key_is_unique_in_database    967 distinct keys in 967 rows
distinct_concepts_match              257 = 257
numeric_total_matches                34,808,176,701,339.3705
                                     delta 0.000000, tolerance 0.000967
consolidated_split_matches           547 = 547
period_type_split_matches            488 instant / 479 duration, both sides
every_dimension_hash_resolved        0 unknown
no_duplicate_natural_keys_in_source  0
```

The two rejections are `CommitmentsAndContingencies` rows with no value — the shape DERA uses for
a line-item label. They are counted and named in the report, never silently dropped.

### Idempotency, demonstrated rather than asserted

```
run 1 (cold)   inserted 967, already present 0,   in database 967
run 2          inserted 0,   already present 967, in database 967, RECONCILED
```

Run 2 re-reads the whole 97 MB package and re-derives every natural key. It does not consult
`loaded_at` to decide whether to work: a bookkeeping flag set by a run that half-failed would make
the gap permanent and invisible. The flag records what happened; it never authorises a skip.

Proven non-vacuous by mutation. Removing the existing-key filter from the loader makes
`test_a_rerun_inserts_nothing` fail with 8 rows in the database where 4 belong.

### Four defects the load exposed

**1. A derived quarter start was a day short.** DERA publishes an end date and a quarter count and
no start at all, so `period_start` is derived. Subtracting whole months and adding a day clamps
30 June minus three months to 30 March — March has 31 days — giving 31 March. The error is
invisible on Apple's annual periods, which end 30 September and land on 1 October either way, and
wrong on every quarter ending in a 30-day month.

It was caught by a unit test **after** the first load had already written 136 wrong rows. Those
were deleted and all four filings reloaded. The derivation is now the first day of the month
`months - 1` earlier, with a test asserting consecutive quarters tile the year with no gap and no
overlap.

**2. The test suite destroyed the data it ran against.**
`test_upgrade_then_downgrade_round_trips` runs `alembic downgrade base`, which drops every
application table. That is correct against CI's ephemeral container and destructive here:
`make check` deleted all 2,845 loaded facts, silently, and reported green.

The first fix skipped the test when the target held data. That stopped the deletion and left the
test unrun — the other half of the same failure. **The final design is two databases**, and a new
invariant: see the section below.

**3. An inter-test dependency, exposed by fixing that.**
`test_filed_fact_cannot_be_updated` inserted its fixture row using Apple's real CIK and accession,
both UNIQUE columns, so it failed the moment the database held a real load. It had only ever
passed because the destructive test ran first and left every table empty. It now builds its own
schema on the disposable database and uses reserved identifiers, so it depends on no other test.

Both are one lesson: a test that has only ever run against an empty database has not been tested
against a database.

**4. A credential sat in two tracked files.** `migrations/env.py` and
`tests/unit/test_migrations.py` both defaulted to
`postgresql+psycopg://<user>:<password>@localhost:5432/<database>`. Both now resolve through
`packages/persistence/engine`, which is the single home for the URL.

The default was not merely untidy. Against a cluster using peer authentication over a Unix socket
it pointed at `localhost:5432`, where a server does answer, so the reachability probe succeeded
and the live tests **ran** instead of skipping — then failed on authentication, which reads as a
broken database rather than a wrong URL.

### What the loader deliberately does not claim

**Every row is written `validation_status = 'UNVALIDATED'`.** Nothing has validated these facts;
the validation pipeline is Sprint 5. Writing `VALID` would be a claim no code in this repository
has earned.

**`is_latest_selected` is false on every row.** Selecting the latest observation is a pure
function over the observation set and belongs to the fact lake in Sprint 6. Asserting it now, with
one source loaded, would be wrong the moment a second arrives.

**DERA period boundaries are approximations by design.** `ddate` is rounded to the nearest month
end and `qtrs` is a whole number of quarters; DERA publishes the residuals separately as `datp`
and `durp`. Apple's FY2025 ended 2025-09-27 and DERA records 2025-09-30. The exact filed
boundaries are in the XBRL instance, which Sprint 6 reads. Because `xbrl_fact` is append-only,
that later and better observation supersedes these rows through the ordinary restatement path
rather than overwriting them.

**Only the named filing is loaded, not the whole package.** `xbrl_fact` has foreign keys to
`issuer` and `filing`, so loading a monthly package outright would first require registering the
7,098 submissions in it as issuers and filings. That is the issuer universe, Stage 2 phase W-1,
and out of scope by ADR-0015.

### Destructive tests are isolated — TEST-DATABASE-ISOLATION-INVARIANT

`rules.md` section 3 gains an eleventh non-negotiable invariant:

> Destructive database tests must never operate on the configured application database. Migration
> upgrade and downgrade tests run only against a dedicated disposable test database, and must fail
> closed if the test target cannot be proven separate.

```
DATABASE_URL       fintek        the application database; NON-DESTRUCTIVE use only
TEST_DATABASE_URL  fintek_test   disposable; destructive tests drop every table in it
```

**No fallback between them.** `TEST_DATABASE_URL` never defaults to, derives from, or falls back
to `DATABASE_URL`. A fallback works everywhere, quietly, until the day the application database
has something in it. Absent configuration fails; it is never a silent substitution and never a
skip.

**Separateness is proven, not named.** `assert_disposable` parses both URLs to a
`DatabaseIdentity` — host, port, socket path, database name, and deliberately no credentials — and
refuses equality. Comparing the configured strings is not enough: `@localhost/fintek` and
`@127.0.0.1:5432/fintek` are different strings and the same database. Credentials are excluded on
purpose, so a destructive run cannot be authorized merely by connecting as a different user. The
name must additionally carry `test` as a whole underscore-delimited token and must not contain
`prod`, `production`, `live`, `master`, or `primary`.

**The application database is watched from the other side.** A session hook records `issuer`,
`filing`, and `xbrl_fact` row counts before the suite and fails the run if they change — from a
dropped table or from a fixture row a test left behind. Always on.

Failure modes are distinguished rather than blurred into one skip:

| Situation | Behaviour |
|---|---|
| server unreachable | SKIP — the machine cannot run database tests at all |
| `TEST_DATABASE_URL` unset | FAIL — configuration error, not an environment limitation |
| server up, test database missing | FAIL, naming `make db-create-test` |
| test URL equals application URL | FAIL before anything is dropped |

30 tests in `tests/unit/test_database_isolation.py` cover the guard, each named after the specific
way a weaker one still permits the deletion.

**Local setup needed one privileged action.** The `fintek` role has no CREATEDB, and `pg_hba`
scopes peer authentication to the `fintek` database — both deliberate, and granting CREATEDB to
make tests convenient would be a broader privilege than the problem requires. A gitignored helper
under `var/local-tools/` creates `fintek_test` owned by the existing role and widens that one
`pg_hba` line. Procedure in `docs/runbooks/test-database.md`.

**CI declares both databases** against one service container, creates `fintek_test` explicitly
because `POSTGRES_DB` creates exactly one, and runs `make db-verify-isolation` before any test.

The service uses a fixed, disposable, obviously non-production password written openly in the
workflow, replacing `POSTGRES_HOST_AUTH_METHOD: trust`. `trust` accepts any connection with no
password, so the workflow never exercised the authentication path the application code takes. The
replacement protects nothing — the container lives for one job, is reachable only from it, and
holds public SEC data — and a repository secret would imply sensitivity and a rotation obligation
for a value that cannot leak anything. The health check authenticates rather than probing the
port. None of this bears on deployment, which remains undecided; the local host still uses peer
authentication and stores no password at all.

### The database was empty until now

Sprint 3's acquisition wrote objects to the store and provenance to a manifest, never to
PostgreSQL, so `issuer` and `filing` both held zero rows. `packages/dera_notes/registration.py`
creates the two rows a fact must attach to, sourced from the package's own `sub.tsv`. `era` and
`primary_document` are left NULL: DERA does not describe them, and `packages/filing_acquisition`
owns those columns.

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

## Acceptance criteria (as planned)

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

## Acceptance criteria — audit

Every criterion, checked against what actually exists. Evidence is a command that was run or a
figure counted, not a recollection.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | `upgrade head` and `downgrade base` both succeed against a real PostgreSQL | **MET** | Both run; `alembic current` reports `0001_initial (head)` |
| 2 | The two previously skipped live migration tests pass; zero skips for database reasons | **MET** | `337 passed, 0 skipped`, `make test-no-skips` exits 0. Both run against `fintek_test`; the application database's counts are identical before and after |
| 3 | One DERA partition is loaded and its row counts reconcile against the package | **MET, exceeded** | Four filings from four packages; nine reconciliation checks each, all passing |
| 4 | Filing discovery for CIK `0000320193` returns the complete history and reconciles gap-free against `master.gz` | **MET** | 134 covered filings, `134 = 134` across 131 quarters, zero gaps either direction |
| 5 | The `filings.files[]` overflow path is exercised, not merely coded | **MET** | `recent` returned its 1,000 cap; 89 of 134 came from the overflow shard |
| 6 | Four filings preserved with SHA-256, provenance, and acquisition strategy recorded | **MET** | 20 objects, 8.42 MiB, in `var/acquisition.json` and the fixture manifest |
| 7 | Re-running acquisition downloads nothing and re-verifies by content address | **MET** | 0 downloaded, 20 reused, 0 requests |
| 8 | Committed fixtures reproduce the four filings' structure offline | **MET** | `tests/unit/test_filing_fixtures.py` passes with no network |
| 9 | `pytest` passes on a fresh clone with no network access | **MET, with one qualification** | No test performs network I/O. Tests needing a database skip with a reason; on a clone without one the suite is green and reports those skips |
| 10 | Repository growth under 25 MB, measured and reported | **MET** | Fixture tree 188.4 KiB. No binary added since |
| 11 | The exclusion list resolves Apple's three item disclosures and flags unknown namespaces | **MET** | `tests/unit/test_filing_acquisition.py`, exercised against acquired data |
| 12 | URGENT-02: a second durable copy of the twelve monthly packages exists | **MET** | 12 of 12, 2,145,477,071 bytes, separate device confirmed by `stat`, hashes and ZIP CRCs verified both sides |
| 13 | Zero SEC throttle events | **MET** | 0 across every run in this sprint |

Criterion 9 is qualified rather than claimed outright. "Passes with no network" is true; "passes
with no database" means the database tests skip, which is the designed behaviour and is now
visible in the output because the targets pass `-ra`. CI provides a database so they run there,
and `make test-no-skips` fails if anything skips in an environment that should run everything.

---

## Validation

```
337 passed, 0 skipped
92.73% coverage on the implemented packages (85% gate)
mypy clean across 65 source files in packages, scripts, migrations
ruff format and lint clean across packages, tests, scripts, migrations
alembic upgrade head --sql and downgrade --sql both succeed offline
```

---

## Known issues carried into Sprint 4

1. **The backup mount is not persistent.** `/etc/fstab` has no entry for the backup device, so
   after a reboot `/mnt/backup` is an empty directory on the root filesystem. The copied data is
   safe; the risk is a future backup writing into that empty directory and reporting success.
   `docs/runbooks/dera-backup-mount.md` carries the exact entry and the validation sequence.
   Applying it needs root and has not been done.

2. **Only the inline-XBRL era is implemented.** `standalone_xbrl`, `html_no_xbrl`, and
   `pem_armored` raise `UnsupportedEraError` rather than guessing. That covers the four target
   filings and everything from roughly 2019; the other 104 of Apple's 134 filings need Stage 2
   phase W-2.

3. **DERA period boundaries are month-end approximations**, and every loaded row is
   `UNVALIDATED` because of it. Superseded by the XBRL instance in Sprint 6 through the
   append-only restatement path. Not a defect; a recorded property of the source.

4. **Acquired objects are not registered in `filing_document`.** Provenance for the 20 acquired
   objects lives in `var/acquisition.json` and the fixture manifest, not in PostgreSQL. The
   `filing` rows that do exist were created by DERA registration and therefore carry NULL `era`
   and `primary_document`. `packages/filing_acquisition` owns that gap.

5. **Idempotency relies on a read-then-insert inside one transaction**, serialized by a
   transaction-scoped advisory lock on the accession, rather than on a unique index over
   `(accession, source_dataset, source_row_id)`. Migration `0001_initial` is SEALED, so adding
   that index is a second migration. The advisory lock is correct for the single-writer ingest
   this project has today; the index is the right answer once ingest is concurrent.

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
