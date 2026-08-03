# Changelog

All notable changes to FinTek are recorded here. This is not a commit dump: it records
user-visible, architecture-level, data-model, and operational changes.

Format follows Keep a Changelog, with two additional sections that matter for this system:
`Data migrations` and `Operational changes`.


## Phase 2 — intact-filing parser experiments and the parser-review UI (2026-08-03)

**AN SEC FILING WAS PARSED BY A REAL MODEL FOR THE FIRST TIME IN THIS PROJECT'S HISTORY.** Phase 1
proved five models were reachable and nothing else. Phase 2 sent them filings, preserved exactly
what crossed the wire in both directions, proved every citation against the preserved bytes, and
built the surface a person needs to look at the result beside the filing it came from. The measured
figures, the benchmark selection evidence and the comparison are in
`docs/sprints/PHASE-0002-parser-experiments-and-review-ui.md`.

**WHAT IS STILL NOT TRUE, AND IT MATTERS.** No application database exists. No Redis exists. No
summary artifact, no image artifact and no chat session exists — the orchestrator ran the PARSING
stage only and raises rather than running another. An APPROVED artifact records a judgement and
activates no reuse: no search consults the evaluation store and no cache is populated. Nothing is
deployed. Breadth across the 22 substantive form strings has not been attempted.

### Added

- **`packages/evaluation_store`** — parent runs, child filing jobs, exact request and response
  evidence, an append-only event log, developer comments, and TWO INDEPENDENT state machines.
  Execution state describes machinery; review state describes a human judgement; neither is ever
  inferred from the other. Every write goes through `packages/storage`, whose `put_bytes` now
  flushes and fsyncs before the atomic rename. **It is not the product database and holds no
  schema** — a source set, a validation result and an image-coverage report all arrive as opaque
  mappings written by the packages that own those concepts.
- **`packages/source_transport`** — mechanical source-set assembly. Local inventory first, byte
  count and SHA-256 re-verified rather than trusted from bookkeeping, only missing members fetched.
  Transport disposition from byte signatures, filename extensions, XML root namespaces and EDGAR's
  own declared renderer marker. **An unrecognised member fails closed into the run plan** rather
  than being dropped or submitted on a guess.
- **`packages/filing_acquisition/documents.py`** — the NON-CLASSIFYING filed-document lister
  reserved by `rules.md` section 5, replacing the classifier ADR-0017 deleted. It reports what the
  filer declared — sequence, type string, filename, description, byte range — and assigns no role,
  class, importance or meaning to any of it.
- **`packages/coverage_validation`** — an elastic reader that preserves unknown model-returned
  fields and requires no node-type vocabulary; source-reference resolution against the preserved
  bytes; generic numeric signals. `ValidationStatus` has **no `COMPLETE` member**, deliberately.
- **`packages/prompt_registry`** — versioned prompts locked by SHA-256. Editing a version that has
  been used fails at load, in the suite and in CI.
- **`packages/model_catalog/routing.py`** — the four-role router, completing the package that
  arrived in Phase 1 carrying half its responsibility. Region is DERIVED from the reviewed snapshot
  and a cross-region route is always disclosed.
- **`packages/llm_gateway/providers/bedrock.py`** — the Bedrock Converse adapter, the only place an
  AWS SDK is imported anywhere in the repository. It separates reasoning content from visible
  answer text, normalises provider failures with an honest retryable flag, and performs no retry of
  its own.
- **`packages/orchestrator`** — preflight, a DURABLE cumulative spend journal that survives a
  restart, parser-only execution, the local filing catalog, and a bounded in-process worker
  defaulting to one billable invocation at a time.
- **`packages/review_api` and `packages/review_web`** — the parser-review application. Raw, Parsed
  and Side-by-side views; the four model selectors with a visible blank option on the three
  optional ones; a viewport-anchored copyable parent run identifier; cost preflight before any
  billable call; review states and developer comments.
- **`prompts/parser/parser-complete-filing-v1.txt`** and its version manifest — the first
  provisional parser prompt. It asks for the complete filing in the filing's OWN vocabulary and
  imposes no section taxonomy.
- **`docs/adr/ADR-0019`** — the six decisions Phase 2 forced, recorded once.
- **`tests/architecture/test_phase2_boundaries.py`** and the OpenAPI route-contract check, which
  compares the specification against the application's real route table in BOTH directions.
- **`tests/integration/`** returned, and the `integration` marker with it. Every test in the old
  directory needed a live PostgreSQL; the new one exercises the whole parser-only path against the
  in-process mock provider with no database, no network, no credential and no listening socket.

### Changed

- **`packages/llm_gateway/providers/base.py`** gained `OriginalSourceBlock`. `model-abstraction.md`
  had recorded that the interface had no representation for a preserved SEC artifact sent intact,
  that it would need one before the first real parsing run, and that its shape would be designed
  against a real adapter rather than guessed. It was.
- **`LlmGateway.invoke`** admits original source by PROVENANCE — the bytes must hash to the SHA-256
  the source store recorded — rather than by syntax, which would reject an inline-XBRL filing for
  containing HTML. It also gained `strict_response=False`, under which a response that fails the
  boundary check is recorded with its exact bytes instead of raising: that response was bought, and
  whether the prompt or the model is at fault is what a reviewer is there to decide.
- **`InvocationRecord.cost_usd` is a `Decimal`**, and the price arithmetic has exactly one home.
- **`ModelCapability.verified_regions` is an ordered tuple, not a frozenset.** The router picks the
  first verified region when the preferred one is absent, and a set would make that choice depend
  on hash ordering — a different region on a different interpreter run, and an unreproducible bill.
- **`packages/storage.ObjectStore` gained `list_keys`**, and the filesystem backend now fsyncs.
- **`docs/api/openapi.yaml`** describes both halves honestly: 27 IMPLEMENTED operations compared
  against the real route table, and 14 that remain PLANNED.
- **`boto3` is an OPTIONAL extra.** "Ordinary CI is AWS-free" now means the SDK is not installed.

### Fixed

- **The content boundary could not tell a YAML scalar QUOTING markup from a markup RESPONSE.** A
  parser response is required to quote filings verbatim, and filings are SGML, HTML or inline
  XBRL — so under the old rule no response quoting a pre-2001 filing could ever pass, which is the
  entire corpus era this product exists to cover. Observed on the first real benchmark. A document
  that PARSES as one YAML 1.2 mapping is now accepted as one unfenced YAML document, and only
  SERIALIZATION violations still apply to it. JSON is a YAML subset, so the JSON detectors stay, as
  do the fence, native-tool and structural checks; mutation tests prove a JSON response, a fenced
  response and a genuinely markup response are all still refused.
- **The AWS SDK retried underneath the cost ceiling.** botocore retries by default and a Converse
  call is billable from the moment it is issued, so an SDK-level retry was a second charge that
  `RetryBudget` never counted and the spend journal never recorded — the ceiling was being enforced
  against a number smaller than the bill. The client is now constructed for one total attempt. The
  same change raised the read timeout from the SDK's 60-second default: the first real parse of a
  preserved filing took 158 seconds, and a candidate with a larger output limit timed out at the
  default on the same filing.
- **An inline-XBRL primary document was dispositioned MACHINE_ONLY and silently dropped from the
  source set.** Inline XBRL is XHTML: the document opens with an XML declaration and carries XBRL
  and XLink namespaces on its `html` root, which matched the machine-artifact rule before the
  HTML-root check. Measured on accession `0000794367-25-000156`, the single most important member
  of a modern filing — the 10-Q/A itself — was excluded while three certification exhibits and an
  image were submitted, coverage counts reconciled against what WAS submitted, and nothing anywhere
  said the filing had not been sent. Found by reading a disposition table, not by an assertion. The
  HTML-root check now runs first and a regression test locks it.
- **Eleven further defects found by the test authors**, each reported rather than silently fixed
  around: every modern filing reported its own complete submission as uncovered content; source
  reference offsets were emitted in three coordinate systems while the UI treated them as one; a
  zero offset was dropped from a URL because `0 == False`; `href` values were HTML-escaped twice
  and never percent-encoded; a JSON run request containing an `=` in any value was parsed as a
  form; `CompositeInventory` did not fall through on `ValueError`, so an absolute local path
  crashed preflight; a hash-invalid held member was never re-acquired although three docstrings
  promised it was; the adapter crashed with `AttributeError` on `metrics: null`, losing an
  already-billed response; an undeclared image format defaulted to PNG and a text block with no
  decoded text was sent as an empty body; `image_coverage_report` contradicted itself for a filing
  with no images; and a null parsing selection loaded as the literal string `"None"`.

### Operational changes

- `make review` starts the parser-review application on `127.0.0.1`. Binding beyond loopback
  requires a development authentication secret from ignored environment state, and
  `ReviewSettings` refuses to construct without one — the unsafe combination is not reachable by
  forgetting a flag.
- `make test-integration` exists again, and CI runs it.
- Evaluation evidence lives in the gitignored `var/evaluation-runs/`, alongside a durable spend
  journal that carries the cumulative cost ceiling across restarts.
- On restart, every mid-flight child job becomes `INTERRUPTED` and **nothing is re-invoked**. A
  rerun is billable, and a process that came back up is not a user who asked to spend money again.

### Data migrations

None. There is still no database.


## Phase 1 — secure AWS access and model-capability verification (2026-08-03)

**A MODEL RESPONDED FOR THE FIRST TIME IN THIS PROJECT'S HISTORY.** Seven minimal invocations, total
spend USD 0.00023 against an authorized USD 1.00 ceiling. Every earlier statement in this repository
about model availability, identifiers, limits or prices was a placeholder, and several were wrong.

**NO SEC FILING WAS SENT TO ANY MODEL. NO PARSER EXPERIMENT BEGAN. ORDINARY CI REMAINS AWS-FREE.**
One authoritative explanation, not repeated elsewhere:
`docs/adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`.

### Added

- **`docs/llm/bedrock-capability-snapshot.yaml`** — the reviewed, dated capability contract. All
  five approved candidate LABELS mapped UNIQUELY to real provider models, each with its availability,
  access status, verified regions, inference-profile requirement, text and image capability, context
  and output limits, invocation APIs, streaming support, official price inputs with their source and
  effective date, and its smoke result. **It is the only place any of those facts is written down**;
  a capability recorded twice drifts.
- **`packages/model_catalog`** — the provider-neutral reader. It resolves a user-facing label to
  something invocable, or raises with the sentence a user should read. It contains no AWS import, no
  ARN, no endpoint, no credential, and **no model identifier, region, limit or price** — every one is
  supplied from the snapshot, exactly as the qualifying-form set is supplied to `filing_discovery`.
  Also carries `SpendLedger`, which bounds the worst-case cost of an invocation BEFORE it is made,
  and `RetryBudget`, which permits one retry and only for a transient reason.
- **`tests/architecture/test_phase1_aws_boundary.py`** — twelve guards: no provider SDK or CLI
  subprocess in a shipped package, no provider identifier or region literal in shipped source, no
  account id, account-bearing ARN, SSO URL or access-key identifier in any tracked file, no
  `id-token` permission or credential step in ordinary CI, no test that reaches AWS, and the smoke
  tooling and its evidence proven untracked and gitignored.
- **`tests/unit/test_model_catalog.py`** — fifty hermetic tests, each building its own synthetic
  snapshot.
- `docs/runbooks/bedrock-capability-discovery.md`, which reproduces the whole phase, and
  `docs/sprints/PHASE-0001-secure-aws-and-model-access.md`.

### Fixed

- **`LlmSettings.region` no longer defaults to a hardcoded `"us-east-1"`.** That is the form-family
  defect with a bill attached: a guessed value in runtime source, no reviewed contract behind it,
  and a silent success when the operator sets nothing. Phase 1 made the cost concrete — one of the
  five approved candidates is **not offered in `us-east-1` at all**, so an unset region would have
  reported a real model as unavailable with nothing in the code to point at. `AWS_REGION` now has no
  fallback and a non-mock provider without a region raises `MissingModelRegionError` at
  construction. The mock still needs none, so the suite keeps its zero environmental preconditions.

### Findings that constrain Phase 2

- **Llama 4 Maverick cannot be invoked by its model id.** Its inference type is `INFERENCE_PROFILE`,
  not `ON_DEMAND`; callers use the US geo profile, which routes across three regions — a
  data-residency fact, not only a throughput one.
- **Qwen3 235B A22B is not available in `us-east-1`,** although the AWS model card lists it as
  in-region available there. The control plane answers `ValidationException`. The live API is
  recorded and the discrepancy is written down rather than reconciled away.
- **Two of the five are genuinely multimodal, and both proved it by invocation** — each read the
  word HELLO out of a 173-byte PNG. `multimodal` is validated against `image_verified` in the
  dataclass constructor, so no record can carry the badge without the evidence.
- **GPT OSS 120B passed transport and failed the instruction for a request-sizing reason.** The
  gate's mandatory 8-token output cap was consumed by a `reasoningContent` block preceding the
  answer, leaving an empty text block. A one-off diagnostic at 64 tokens returned reasoning followed
  by `hello`. `max_output_tokens` must budget for reasoning PLUS the answer.
- **Context limits span 128K to 1M and output limits 8K to 32K** across the five, against dated
  Phase 0 evidence that 44 percent of primary corpus documents exceed ~200,000 estimated tokens.

### Operational changes

- Runtime dependencies are unchanged and remain exactly two: `ruamel.yaml` and `httpx`. **No AWS
  SDK was added.** Discovery and the gates used the AWS CLI, which is official AWS tooling; the
  Bedrock adapter and any SDK dependency are Phase 2, in the single home `rules.md` section 5 names.
- 375 tests, 0 skipped, 92.14 percent coverage. The suite still has **no environmental
  precondition** — no database, no network, no credentials.
- **DISCLOSED:** Phase 1 discovery ran under an IAM Identity Center `AdministratorAccess` role, the
  identity supplied for the task. The security policy permits a one-time manual discovery under a
  broad role but not a durable path; the least-privilege Bedrock policy is required before any
  repeatable or automated invocation, and no CI job holds an AWS role. ADR-0018 section 7.


## Commit 3 — delete the rejected parser and the application persistence layer (2026-08-03, `d093e73`)

Removes the withdrawn architecture from the active repository. ADR-0016 withdrew deterministic
semantic parsing from product authority and DEMOTED the implementation to a benchmark oracle; this
change DELETES it, together with the application database it wrote to, the migrations that
described that database, the DERA mirror and fact loader, and everything that existed only to serve
them. **Git history is the archive. Nothing was moved to `oracle/`, `legacy/`, `deprecated/` or
`tests/support/`.** One authoritative explanation, not repeated elsewhere:
`docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.

### Removed

- **The deterministic semantic parser.** `packages/footnote_extractor`,
  `packages/footnote_canonicalizer`, `packages/table_parser`. The Sprint 4 measurement stands as
  history — 43 canonical footnotes across four Apple filings, 117 of 117 child blocks attached,
  zero orphans — and the code that produced it is gone. It measured one issuer, one filing agent
  and two of six transport eras, and grading a parsing model against a deterministic parse would
  have made the deterministic answer authoritative again through the back door.
- **The application persistence layer and its migrations.** `packages/persistence` (24 ORM
  tables), `migrations/`, `alembic.ini`, `docker-compose.yml`. Ten of the twenty-four tables were
  the rejected ontology directly, including a `filing.processing_state` CHECK constraint that
  enumerated `EXTRACTING_FOOTNOTES` and `GROUPING_FOOTNOTES` as pipeline states. **The
  sealed-migration rule in `rules.md` section 8 was satisfied, not bypassed:** the application
  database `fintek` was verified NOT to exist before anything was removed, so no deployed
  environment is left diverged from a file claiming to describe it.
- **The DERA mirror and fact loader.** `packages/dera_notes` fails three of the seven parts of the
  DERA/XBRL retention test — it writes to deleted tables, cannot work without them, and has no
  near-term use. Its coverage was also structurally inadequate for the role proposed for it: NOTES
  starts at 2009Q1 and covers XBRL filers only, against a corpus of which 281 of 613 filings
  predate HTML-era markup. **The 26 GB mirror itself is untouched** in the gitignored `var/dera/`.
- **The accession document classifier.** `packages/filing_acquisition/inventory.py` assigned a
  nine-term Regulation S-K document ROLE taxonomy and ruled that a courtesy PDF duplicated the
  primary document, suppressing a filed source range on a semantic-equivalence judgement — a direct
  violation of COMPLETE-CONTENT-INVARIANT. It had no production caller.
- All seven `scripts/`, `metric_definitions/`, `artifacts/`, `prompts/footnote-summary/`,
  `docs/footnotes/`, four `docs/financial/` specifications, `docs/sec/dera-notes.md`,
  `docs/architecture/{components,data-flows}.md`, three `docs/llm/` summary specifications and nine
  runbooks.
- From `packages/llm_gateway`: `FootnoteSummaryRequest`, `SourceBlockPayload`, `TablePayload`,
  `compile_footnote_summary_request`, and — as dead code with zero callers and zero tests —
  `ModelCapabilities` and `SerializationComparison`. Four footnote identifiers left the YAML
  quoting rule. The mock provider's canned response was a `footnote-summary-v1.0.0` document with a
  fixed taxonomy, which quietly made the mock the de facto response schema; it is now a minimal
  mapping asserting no contract.
- **346 test functions**, with their subjects. A reduced total is the correct outcome of a
  deletion; nothing was kept for the count.
- Dependencies `sqlalchemy`, `alembic`, `psycopg[binary]` — and `pydantic`, which was declared and
  never imported by a single module. Runtime dependencies are now `ruamel.yaml` and `httpx`.
- Make targets `migration-check`, `db-*` and `test-integration`; the CI PostgreSQL service, both
  disposable-database environment variables and the five database steps; the `integration` pytest
  marker.

### Fixed

- **A guessed form allowlist that contradicted the reviewed contract.**
  `packages/filing_discovery` shipped `ANNUAL_FORMS = ("10-K", "10-K405", "10-KSB")` and
  `QUARTERLY_FORMS = ("10-Q", "10-QSB")`, matching on the part before `/A`. EDGAR files `10KSB` and
  `10QSB` unhyphenated — `10QSB` alone is 120,120 filings and the fourth most common form in the
  family — so the filter matched none of the small-business family and none of the transition
  family, while `tests/fixtures/form_family.yaml`, which adjudicates all 41 observed strings, sat
  beside it saying qualifying logic is generated from the inventory and never hardcoded. **The
  reconciliation designed to catch a discovery gap applied the same filter to the master index, so
  both sides agreed perfectly and reported a complete history.** The qualifying set is now a
  required argument with no default, matched on the exact filed string; an empty set is rejected;
  and an architecture test parses runtime source and fails on a form literal.
- **The pre-spend budget guard mixed two token ratios.** `gateway.invoke` added
  `len(system_text) // 4` to a payload estimate computed at 3.8 characters per token, under-counting
  the system prompt — the unsafe direction for a check that runs before the money is spent. Both
  now use `estimate_tokens`.

### Added

- `docs/adr/ADR-0017`, the single authoritative record of what was deleted and why.
- `tests/architecture/test_openapi_contract.py`, 9 tests: the contract parses, every local `$ref`
  resolves, no reference leaves the document, no component schema is orphaned, **no `servers:`
  entry claims a deployed server**, every operation is marked `PLANNED`, and the browser-facing
  contract names no provider credential or endpoint. Commit 2 recorded that OpenAPI parsing and
  `$ref` validation ran only as local ad hoc checks with no test reading the file.
- `tests/unit/test_observability.py`, 12 tests. The package had none at all while carrying the
  SECURITY-INVARIANT that filing text, model payload bodies and credential material are never
  logged. Redaction is parametrized over **every** entry in `REDACTED_FIELDS`, and one test asserts
  an unlisted field IS emitted so the others cannot pass vacuously.
- An architecture guard that no runtime package hardcodes a filing-form allowlist, parsed from the
  AST so a comment or docstring naming a form stays legal.
- A CI step proving the five deleted packages cannot be imported from an installed distribution.
- Hash verification extended to **every** committed original SEC document. The four Apple primary
  documents are 3.9 MiB of the fixture tree and had no verification of their own — the manifest
  recorded their hashes and no test compared them. A test also fails if derived parser output
  returns to `tests/fixtures/`.

### Changed

- `roadmap.md` is restructured around the delivery order the product actually needs: cleanup →
  **secure AWS and model-access verification** → **parser experiments and the review UI, built
  together** → optional model stages → persistence and the approval gate → background population →
  beta UI → Deep Dive. The review UI moved from Phase 6 to Phase 2 because a parsed artifact cannot
  be evaluated without seeing it beside the filing it came from.
- The roadmap now states, as requirements: only the parsing model is required and the other three
  selectors may be blank; multimodal parsers are visibly labelled and disable the image selector;
  a text-only parser with no image model must REPORT unanalyzed image-bearing content rather than
  claim complete coverage; local durable source storage is checked and hash-verified before EDGAR;
  parsed artifacts are EVALUATION artifacts until explicitly APPROVED; only approved artifacts
  become reusable, cached in Redis with a **24-hour TTL** over an authoritative persistent store;
  background population needs a separate authorization; one visible parent run ID per request with
  one child job per filing; and granular developer comments stored with the run logs.
- `rules.md`: section 1 drops the two product steps whose code is deleted; section 5 loses four
  single-home rows for packages that no longer exist; section 8 records the migration deletion
  additively with the precondition that was verified first, and continues to bind every future
  migration; the data-ownership table becomes a forward constraint and states that Redis is a
  24-hour acceleration layer, never authoritative; TEST-DATABASE-ISOLATION-INVARIANT is marked
  DORMANT and forward-binding rather than deleted. **Section 21 rule 15 is STRENGTHENED**: the
  oracle exception it granted is withdrawn.
- `techspecs.md` is rewritten against the code that exists: eight packages, 40 modules, 3,469
  lines, with the measured dependency graph and a candid list of what the cleanup cost.
- `docs/testing/strategy.md` is rewritten. It described 876 tests across fifteen packages, three
  database identities and a live migration round trip, none of which existed.
- `pyproject.toml` description, dependency list and packaging commentary. The include pattern is
  documented as the rule rather than as a package count, which is what lets a deleted package keep
  appearing to exist.

### Operational changes

- **The suite has no environmental precondition.** No database, no network, no credentials. CI
  needs no service container, and a skip has no legitimate cause.
- `fintek_test` and `fintek_integration_test` remain on the development host as **unused
  leftovers**. Nothing in the repository can reach them. Removing them is host administration and
  requires separate authorization; no PostgreSQL role, database, service or configuration was
  touched by this change.
- 309 tests, 0 skipped, 90.89 percent coverage against an 85 percent gate.

### Data migrations

None. No application database exists, no revision was applied or downgraded, and no replacement
schema was created. Revisions `0001_initial_control_plane_schema` and `0002_table_ownership` remain
in git history.


## Commit 2 — architecture and governance realignment (2026-08-02, not yet committed)

Reconciles the active documentation, governance, architecture, roadmap and sprint plan with the
corpus-first, model-first product direction. **Architecture and governance documentation plus
one hermetic identity-rules test. No production implementation file changed, no package was
added or removed, no migration was touched, and no runtime behavior changed.**

- `rules.md` gains section 21, PRODUCT-DIRECTION-INVARIANT — seventeen mandatory rules written
  after the repository drifted away from the stated product twice. Strengthening only; sections 15
  to 21 may never be weakened.
- ADR-0016 is finalized with corrected corpus evidence, the four model roles, `INTACT_SOURCE_ONLY`,
  the retained / demoted / withdrawn split, risks and rejected alternatives.
- `docs/api/openapi.yaml` is replaced. The previous document was built on the withdrawn
  content-unit ontology and declared production and localhost servers. The replacement is an
  architectural beta contract with no `servers:` block, every operation marked PLANNED, and a
  deliberately loosely-typed parsed artifact.
- The roadmap, product definition, dashboard UX, data dictionary, Deep Analysis, LLM and testing
  specifications are reconciled around the same direction.
- Corpus totals corrected everywhere from 59 issuers / 533 filings to **112 issuers / 613
  filings**, and labelled as dated Phase 1 evidence rather than permanent constants.
- A withdrawn finding is recorded rather than deleted: "190 of 533 filings declare no primary
  document" came from `index.json`, whose `type` field is a UI icon name and whose sizes are often
  zero. Re-measured against filer-declared document tables, all 613 filings resolve a primary
  document.
- Nine references to `docs/filings/complete-content-model.md`, a file that does not exist, are
  removed, along with five references to the superseded ADR filename.
- The entity catalog is split into two scopes so the beta UI is not left waiting on Phase 8: a
  MINIMUM BETA CATALOG required no later than Phase 3 and completed before Phase 6 can be
  complete, and a Phase 8 universe-scale EXPANSION of that same working catalog. Phase 6
  depends on Phase 3, never on Phase 8. No fabricated historical ticker data.

**No model activity. No orchestrator implementation. No final persistence design.**

## Commit 1 correction — CI (`068eceb2`, pushed, CI green)

One unit test asserted that the migration-target resolver reads `TEST_DATABASE_URL` from the
project's `.env`, and relied on the developer's own gitignored `.env` to supply it. It passed
locally and could only ever fail in CI, which it did. It now writes its own `.env` under `tmp_path`
and points the resolver's `REPO_ROOT` at it, so the real parser, resolver and precedence chain all
still run with nothing stubbed. Four regression tests added, including the first coverage of the
cluster-database rejection rule. No production code changed.

## Commit 1 — preservation and reusable infrastructure (`062baafc`, pushed)

28 paths.

- Preserved five original SEC filings that cost rate-limited fetches and cannot be reproduced
  offline — four Apple FY2025 inline-XBRL documents and the 1994 PEM-armored complete submission —
  all pinned in the fixture manifest with their SHA-256.
- Added two small durable fixtures and 25 contract tests making the form-family and identity
  defects unrepeatable.
- Added the accession document inventory, which classifies documents by the filer's own declared
  type rather than by filename.
- **Test-database isolation.** Three identities with no fallback between them: `fintek_test` for
  destructive migration tests, `fintek_integration_test` for persistence integration tests, and an
  application database that deliberately does not exist. Closed defect D-13, in which an Alembic
  `sqlalchemy.url` option was silently overridden by `DATABASE_URL` and `stamp base` reached the
  application database. Ordinary CI now creates no database named `fintek` and does not set
  `DATABASE_URL` at all.

## [Unreleased]

### Changed — the product is a model-first orchestrator, derived from a measured corpus

**2026-08-02. The architecture was re-founded on evidence rather than on one issuer.**

The repository had validated a deterministic semantic parser, a 22-value universal filing ontology
and a PostgreSQL schema against five Apple filings. A representative research corpus was acquired
and measured: 112 issuers, 613 filings, six transport eras, 760,174,532 bytes of preserved
objects, every object SHA-256 verified, zero throttle events. The measurements refuted the design.
These are DATED PHASE 1 FIGURES — a measurement of one sample on one date, not a constant.

```
44 percent of primary documents exceed ~200,000 estimated tokens; 12 percent exceed ~1,000,000
pre-2001 documents are NOT individually addressable: the complete submission is the only artifact
raw-to-visible markup overhead ranges from 1.06x (SGML) to 24.11x (inline XBRL)
filing packages range from 4 to 283 files; table markup from 0 to 1,115 open tags
malformed table markup is normal before 2005 and absent after it
48 of 112 issuers have former names; 68 have no current ticker; 4 report three or more
361 of 613 accession prefixes belong to the FILING AGENT, not the issuer
```

Apple, the issuer the entire previous architecture was validated against, is roughly one eighth
the size of the largest filing in the corpus.

Decision record: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`.

### Removed — the deterministic semantic parser and its schema

`packages/filing_parser` and `packages/filing_content`, `scripts/extract_filing_content.py`, the
complete-content-model document, the earlier uncommitted ADR-0016, and their tests. None had ever
been committed. Migration `0003_filing_content_coverage.py` was deleted without being committed and
no `0004` was created. The local `fintek` application database was dropped after proving that all
36 original SEC source objects it referenced exist byte-exact on the filesystem with matching
hashes; PostgreSQL held no source bytes, only references.

### Demoted — footnote extraction becomes a validation oracle

`packages/footnote_extractor`, `packages/footnote_canonicalizer` and `packages/table_parser` are
retained and unchanged, and are no longer a product requirement. Their measured Apple results — 43
canonical footnotes, 117 of 117 attachments, 174 classified tables — become recall floors for
grading a parsing model.

### Retained — acquisition, preservation and safety

SEC client and rate limiting, filing discovery, accession document inventory by the filer's
declared type, object storage and hashing, byte-exact preservation and provenance, DERA and XBRL
numeric evidence, database-isolation guards, AWS identity governance, the LLM gateway chokepoint,
and token and cost accounting.


### Changed — the product covers complete SEC filings, not footnotes alone

**Sprint 4.1. The product definition was too narrow, and the correction is architectural.**

The repository had encoded "the footnotes are the product" as a scope definition rather than as an
emphasis. That claim reached governance, the MVP definition, the completeness model, the schema,
the API, the dashboard specification, the Deep Analysis scope table, the summarization contract,
the benchmark corpus, and the cost model — twenty-four locations across five layers.

The clarified requirement: **every human-readable part of every processed 10-K and 10-Q** is
acquired, parsed, classified, preserved, represented as canonical filing content, summarized,
searchable, displayed, and available as evidence to filing-scoped Deep Analysis. Financial
statements and their footnotes are critically important content types; they are examples of filing
content, not the whole of it.

Three failures followed structurally, not incidentally, and all three are now fixed:

```
extraction was blind outside one renderer menu category — MD&A, risk factors, controls,
    legal proceedings, signatures and certifications were INVISIBLE, not merely unprocessed
acquisition fetched five objects per filing, never the filed package; filing_document held
    zero rows for four acquired filings
completeness measured the wrong denominator — a filing whose MD&A was never extracted
    computed COMPLETE
```

Decision record: the uncommitted ADR-0016 "complete filing content scope", which was itself
superseded before entering history by
`docs/adr/ADR-0016-corpus-first-model-first-architecture.md`. Sprint record:
`docs/sprints/SPRINT-0004A.md`.

**Sprint 4 is not superseded.** Its 43 canonical footnotes, 117 of 117 attachments, zero orphans
and table ownership stand unchanged and are now referenced by the general model rather than
replaced. Its sprint record is unedited; a dated forward note was appended.

### Added — the COMPLETE-FILING-COVERAGE-INVARIANT

`rules.md` section 3. Every human-readable disclosure is assigned to exactly one canonical
filing-content unit or to an explicit, auditable exclusion. Nothing may be omitted for being
boilerplate, routine, qualitative, non-financial, untagged, outside the financial statements,
outside the footnotes, hard to classify, in an exhibit, in a certification, in a signature block,
incorporated by reference, present only in a historical format, or judged immaterial by code or a
model.

Coverage reconciles against **discovered source material**, never against a count of sections.
Extraction is deterministic or honestly unresolved: no model participates in discovering,
classifying, bounding, or discarding filing content (`rules.md` invariant 13).

### Added — the canonical filing-content model

`packages/filing_content`: hierarchy paths, the source-block coverage ledger, layered completeness,
incorporation-by-reference detection, and idempotent filing-scoped persistence.

`packages/filing_parser`: an era-neutral parser registry. Required fields carry no inline-XBRL
dependency; role URI, TextBlock concept, renderer report, continuation id, `FilingSummary` report
and XBRL context are optional provenance, and an architecture test fails the build if one becomes
required.

`packages/filing_acquisition.inventory`: the authoritative filed-document inventory, classified by
the **filer's declared type** rather than by filename.

Measured across five filings and two eras:

```
2,878 source blocks   238 content units   0 unresolved   0 double-assigned
43 footnotes reached from the DOCUMENT BODY, independently reproducing the Sprint 4
   renderer-inventory total
```

### Added — complete accession document acquisition

55 filed documents inventoried across four accessions, **zero ambiguous classifications**. Seventeen
human-readable filed documents had never been fetched: a description of securities, a subsidiaries
list, an auditor consent, six officer certifications, and two material contracts. 23 downloaded,
4 reused, 4,632,706 bytes, all through the shared rate limiter with hashes and provenance.

### Added — the historical proof

Apple's 1994 10-K (`0000320193-94-000016`), real filed bytes, PEM-armored. Decoded through PEM
armor, an `IMS-HEADER` submission header, and a `DOCUMENT` wrapper into 4 Parts, 14 Items, 4
financial statements, 9 individual footnotes, 5 schedules, 4 exhibit-index pages and a signature
block — **with no inline XBRL, no role URI, no `FilingSummary`, no TextBlock concept and no
continuation identifier**.

### Added — layered completeness

Acquisition, submission content, disclosure, footnote, and summary, tracked separately and never
collapsed. `SUBMISSION_COMPLETE` and `DISCLOSURE_COMPLETE` are distinct: a 10-K whose Part III is
incorporated from a proxy statement is submission-complete and disclosure-partial at the same time,
and marking either one alone would be false.

### Data migrations

`0003_filing_content` — applied to the application database. Adds `filing_content_unit`,
`filing_source_block`, `filing_incorporation_reference`; five columns on `filing_document`; six on
`filing`. `0001_initial` and `0002_table_ownership` are untouched.

Structural guarantees the schema now enforces rather than tests:

```
assigned_block_has_exactly_one_owner    a block cannot be assigned twice — ownership is a
                                        single column, not a join table
excluded_block_states_its_reason        an exclusion without a reason is indistinguishable
                                        from a block nobody looked at
footnote_unit_does_not_copy_text        footnote evidence is referenced, never duplicated
resolved_reference_names_its_evidence   RESOLVED must name the accession it resolved to
```

Backfill: **3,165 rows** across five filings; an identical second pass wrote **zero**. 2,845 XBRL
facts, 43 footnote identities, 160 footnote attachments and 174 table ownership records verified
unchanged. One non-derived insert, disclosed before it ran: the 1994 filing's `filing` row.

### Fixed — twelve defects

```
D-1   footnote prose never persisted: canonical_footnote.text NULL 43/43,
      footnote_source_block.text NULL 160/160
D-2   filing_document never populated by acquisition
D-3   filing.era and filing.primary_document NULL, so parser selection had no stored input
D-4   dead `if False` branch in the era check-constraint expression
D-5   the Part pattern required a bare `PART I`, so every 10-Q matched ZERO parts and all
      eleven Items attached to the filing root — silently
D-6   statement and notes headings required end-of-string, so every `(Unaudited)` heading was
      missed; 10-Qs reported zero statements and zero footnotes while carrying five and ten
D-7   test_migrations read only 0001, so a table created in 0003 looked absent and one created
      but never dropped would have passed the completeness check
D-8   the head revision was asserted against a literal, so any new migration failed the test for
      the one reason that is not a defect
D-9   certifications classified by filename landed in `other_filed_attachment`
D-10  a courtesy PDF carries the SAME declared type as the document it duplicates and was marked
      for extraction, which would have double-counted an entire proxy statement
D-11  the 1994 filing's footnotes are unnumbered and underlined by a typewriter rule; matching
      only `Note N` found ZERO and collapsed all 140 notes-section blocks into the aggregate
D-12  the historical signature unit captured 146 blocks of schedules and exhibit index, because
      nothing terminates a signature block in a pre-2001 flat submission
```

D-5, D-6, D-9, D-10 and D-11 each produced a confident, silent, wrong result on real filings and
were invisible to any test written against author-composed text. That is why the four FY2025
primary documents and the 1994 submission are now committed fixtures.

### Changed — downstream specifications

`docs/api/openapi.yaml` to 0.2.0: content, tree, coverage, documents, summary,
incorporated-references and content-unit endpoints; `Coverage` replaced by five independent layers;
Deep Analysis scopes extended to `CONTENT_UNIT`, `PART` and `ITEM`. Footnote endpoints remain as
specialized convenience views.

`docs/dashboard/ux-specification.md`: the filing view is a rendered canonical hierarchy, not a
footnote index; coverage displays five layers separately.

`docs/deep-analysis/product.md` and `retrieval.md`: `FILING` scope is the complete processed filing
corpus, and retrieval selects from all content units.

`docs/llm/standard-summarization.md`, `summary-validation.md`, `model-benchmark.md`,
`cost-model.md`: summary targets are content units with footnotes keeping their own independent
guarantee; hierarchical chunking for oversized units; the benchmark spans the taxonomy; cost is
measured per unit, per footnote, per Item, per filing — never extrapolated from footnote counts.

Suite: 622 to 794, 0 skipped. Coverage 91.64% across thirteen measured packages.

### Fixed — migration-target routing (defect D-13)

**A test helper ran `alembic stamp base` against the application database.**

`migrations/env.py` resolved its target through `packages.persistence.engine.database_url()`,
which reads `DATABASE_URL`. A helper that set `sqlalchemy.url` on an Alembic `Config` was therefore
silently overridden, and the operation reached `fintek`, emptying its `alembic_version`.

**No data was lost, and that was luck rather than safety.** The subsequent `upgrade head` failed on
`CREATE TABLE dataset_version` because those tables already existed, so the transaction rolled
back. Against an empty application database the same helper would have migrated it.

The row-count preservation gate stayed green throughout: not one row moved. This was never merely
an `alembic_version` reporting problem — the recorded revision and the actual schema disagreed,
and the mechanism that allowed it would equally have allowed a `downgrade base`.

Root cause: **two independent URL resolutions with no defined precedence.**

```
packages.persistence.engine.migration_target_url()   the single authoritative resolver
  1. an explicit argument supplied by the caller
  2. FINTEK_ALEMBIC_URL, the invocation-specific override
  3. TEST_DATABASE_URL, when FINTEK_ALEMBIC_TEST_TARGET selects it
  4. DATABASE_URL, the ordinary application target
  5. the repository-safe local default

An explicitly supplied target is NEVER silently overridden by DATABASE_URL.
```

`assert_safe_destructive_target()` now runs **before** Alembic is invoked, for `downgrade`,
`stamp`, and any `upgrade` that rebuilds a schema. It proves parsed identity, database name, host
or socket, port, the disposable-test token, and difference from the application database, and
raises without opening a connection.

The application-preservation gate additionally watches `alembic_version` alongside row counts.
That is necessary but not sufficient, and is documented as the post-execution backstop rather than
the fix.

24 regression tests in `tests/unit/test_migration_target_routing.py`, covering all ten required
cases. The revision-detection proof uses synthetic snapshots — the application revision is never
mutated again to demonstrate a guard.

### Removed — tests that asserted documentation content

Four tests asserted that specific prose existed. They are deleted. None of them tested the system;
each one made editing a document a build failure.

```
test_the_readme_stays_within_its_length_budget      README is 700-1,200 words
test_the_readme_renders_the_sections_it_promises    README contains six named headings
test_the_policy_document_exists_and_states_the_rule eight phrases appear in the AWS policy doc
test_rules_carries_the_invariant                    two strings appear in rules.md
```

The word budget was a number with no source: not in `rules.md`, not requested, invented when the
test was written. It failed twice during the README rewrite, and both times the README was edited
to satisfy it. The headings test failed when two sections were deliberately removed — the test was
wrong and the change was correct, which is the whole argument against it.

No rule required any of this. `rules.md` section 18 makes documentation truthfulness a commit-time
obligation on the author. That is a judgement about meaning; a string match cannot make it and
should not pretend to.

`tests/architecture/test_documentation.py` is renamed to `test_markdown_lint.py`, which is what the
four surviving checks are: balanced fences, no heading trapped inside a code block, relative links
resolve, no password-bearing database URL in prose. They read structure, never meaning. The two
removed AWS assertions leave the policy document still covered — it is a `POLICY_DOCUMENTS`
allowlist entry, and `test_the_checks_have_something_to_scan` fails if it disappears.

Suite: 626 to 622. Coverage: 93.45%, unchanged — the four tests exercised no package statement.

### Documentation synchronization after Sprint 4

Project memory had drifted behind the code. `rules.md` sections 13 and 18 make synchronization a
commit-time gate, and it had not been applied since Sprint 3 — so the repository, which is supposed
to be the durable memory, described a project two sprints younger than the one on disk.

Nothing in this change touches code, schema, migrations, or a measured result. It is a correction
to the record.

#### Fixed

- **`CLAUDE.md` said "No SEC filing has been retrieved yet."** This file is loaded at the start of
  every session, so it was the most costly stale sentence in the repository: a new agent began with
  a false picture of the project. Sprint 3 retrieved four filings and Sprint 4 extracted their
  footnotes.
- **`README.md` listed canonical footnote extraction under "What does not exist yet."** It is the
  central deliverable of Sprint 4 and has been production code since `468d0f2`.
- **The roadmap's Sprint Breakdown table contradicted the rest of the same file** — Sprint 3 as
  `IN PROGRESS — database blocked`, Sprint 4 as `NOT STARTED`, while the sprint sections above them
  recorded both COMPLETE. The table now carries the commit SHA for every completed sprint.
- **Commit and push results were missing from the sprint records**, which `rules.md` section 20
  step 11 requires. `SPRINT-0003.md` still said `NOT COMMITTED` for work pushed on 2026-08-01, and
  `SPRINT-0004.md` had no record of the hardening commit. Both now carry their SHAs.
- **Six specification documents described implemented behaviour as `PLANNED`** — the canonical
  model, the canonicalization algorithm, completeness, the table model, filing discovery, and
  document acquisition. `rules.md` section 18 names this as a blocking condition in both
  directions.
- **`rules.md` had no sealed-migration entry for `0002_table_ownership`**, which has been applied
  to a live database since Sprint 4. Section 8 seals a migration on application; the record simply
  had not been written. Added, along with the derived-range requirement for `make migration-check`.
- Stale counts across `techspecs.md`, `README.md`, `docs/testing/strategy.md`, and
  `docs/architecture/deployment.md`: 337 tests to **626**, 92.73% to **93.45%** coverage, 65 to
  **82** typed source files, ten to **thirteen** implemented packages.
- Component reference entries added for `footnote_extractor` and `table_parser`, which had none.

Historical sprint records and historical changelog entries keep their original figures. A count
that was true when written is not stale, and section 18 says so explicitly.

### Post-Sprint-4 hardening (committed as `1d05199`, pushed to `origin/main`)

Three gaps found by reading the CI log of the Sprint 4 push, not by a failing test. Sprint 4's
behaviour is unchanged: no canonicalization, ownership, migration, or schema code was touched, and
every measured result stands exactly as recorded.

#### Added

- `tests/unit/test_ten_q_regression.py` — the three FY2025 10-Qs asserted the way the 10-K already
  was: candidates, notes, exclusions, child blocks, attachments, orphans, ambiguity, completeness,
  filed order, filed titles, and the **per-note distribution**. Plus six mutation proofs, including
  the two a total cannot catch — a child attached to the wrong note, and a correct total spread
  wrongly.
- `tests/integration/test_ten_q_persistence.py` — the database half: an identical rerun of each
  quarter inserts 0, updates 0, and leaves a byte-identical persisted digest.
- `tests/architecture/test_ci_workflow.py` — the workflow as an architecture surface, checked by
  parsing the YAML rather than grepping it.
- Four tests in `tests/unit/test_migrations.py` pinning the offline migration range to a derived
  one, including a non-vacuity proof that the range it replaced was insufficient.

#### Fixed

- **`make migration-check` had silently stopped covering the newest migration.** The downgrade was
  generated as `0001_initial:base` — correct while 0001 was the only revision, and wrong from the
  moment 0002 existed. Alembic renders only the revisions inside the range it is given, so the
  target kept exiting 0 while producing 25 statements, none of which dropped an ownership column,
  constraint, or index. Now `upgrade base:head` and `downgrade head:base`: derived, so a future
  migration is covered without editing anything. **A check that reports a property it has stopped
  testing is worse than no check.**
- **CI ran on a deprecated Node runtime.** `actions/checkout@v4` and `actions/setup-python@v5` both
  declare `runs.using: node20`; every run emitted a deprecation notice and nothing failed. Verified
  against the official repositories: checkout is Node 24 from v5, setup-python from v6, and v7 is
  the current major of both. Both moved to `@v7`. Neither v7 change affects this workflow —
  checkout v7 restricts fork checkouts under `pull_request_target`/`workflow_run`, which is not
  used here, and setup-python v7 removed a `pip-install` input never set here.
- **A measured result no test asserted.** CI proved the 10-Qs' table-ownership census while their
  note and attachment counts existed only in the sprint record. The numbers were right; nothing
  would have caught them becoming wrong.

### Sprint 4 — canonical footnote extraction (committed as `468d0f2`)

**The 13-not-58 correction is now production code**, measured against four preserved Apple filings
rather than confirmed by inspection.

#### Added

- `packages/footnote_extractor`: renderer report inventory, candidate discovery, child-block
  extraction, note-heading parsing. Reports what a filing contains and decides nothing.
- `packages/footnote_canonicalizer`: stages 1 through 5, item-disclosure exclusion driven by
  `metric_definitions/item_disclosure_exclusions.yaml`, per-child attachment audit, completeness,
  and persistence. No model participates; every decision is a string comparison or a count.
- `packages/table_parser`: row and column structure, header hierarchy, cell provenance, and exact
  numeric text. No financial interpretation and no float conversion of a filed value.
- `scripts/canonicalize_footnotes.py`, which orchestrates and holds no parsing or SQL of its own.
- 121 tests, including a fixture regression test and mutation proofs that it can fail.

#### Measured

| Filing | Cand. | Notes | Excl. | Children | Attached | Orphans | Status |
|---|---|---|---|---|---|---|---|
| 10-K FY2025 | 16 | **13** | 3 | 46 | **46** | **0** | `COMPLETE` |
| 10-Q Q1 | 12 | 10 | 2 | 23 | 23 | **0** | `COMPLETE` |
| 10-Q Q2 | 12 | 10 | 2 | 23 | 23 | **0** | `COMPLETE` |
| 10-Q Q3 | 12 | 10 | 2 | 25 | 25 | **0** | `COMPLETE` |

Per-note child distribution for the 10-K matches the specification exactly: 1, 4, 3, 4, 3, 3, 6,
4, 5, 3, 4, 2, 4. Persisted: 43 canonical footnotes, 160 source blocks with 0 orphans, 174 tables,
12,620 cells, 9 filing sections. `xbrl_fact` unchanged at 2,845; `llm_invocation` **0**.

**Stage 4 reports `NOT_ATTEMPTED`, not `RECONCILED`.** Apple's filings carry no per-note table of
contents, so there is nothing to reconcile against. Claiming a match would report a confirmation
that never happened; stage 5 supplies the independent count instead, and confidence is 0.950
rather than 1.0 because of it.

#### Fixed

- **A note heading is split across two elements.** The document renders `Note 1 –` and its title
  separately, so a pattern requiring both on one line finds **zero** headings and stage 5 confirms
  nothing while reporting success. All 43 headings across the four filings are joined this way.
- **A closure captured a loop variable and destroyed cell provenance.** Every cell carried down by
  a rowspan was stamped with the last row index rather than its own — corrupting exactly what the
  parser exists to preserve.
- **Spacing rows were reported as malformed tables.** `<tr></tr>` used for vertical space flagged
  46 of 62 tables as ragged when none was, and defeated header detection on all of them.
- **The issuer-specific guard missed the defect it was hunting.** Skipping lines beginning with a
  quote flagged docstring continuation lines; skipping every string token then missed
  `if cik == "0000320193"`, since the issuer is a string literal. Now an AST walk that exempts
  docstrings specifically, proven by mutation.

#### Table ownership, and a wrong first answer

Ownership was initially reported unresolvable: attributing a table to a note appeared to need a
document-offset-to-report map `FilingSummary.xml` does not contain. That assumed the renderer
inventory was the only route. The filing publishes the relationship itself — a table's owner is
the note the FILER wrapped it in:

```
table offset -> innermost ix:nonNumeric span -> TextBlock concept
             -> presentation roles (_pre.xml) -> canonical footnote
```

A child role resolves through the attachment stage 3 already audited, so ownership reuses one
decision rather than deriving a second that could disagree.

**A continuation defect this exposed.** Treating the `ix:nonNumeric` element as the note boundary
classified 23 of the 10-K's tables. Inline XBRL splits non-contiguous content with `continuedAt`;
Apple's 10-K has 24 continued TextBlocks and 35 continuation elements, 11 chained onward. The debt
maturity schedule, the commercial-paper table, and the purchase-obligation table all live in
continuations. Ignoring them classified those as unowned furniture — a false negative that would
have silently narrowed what a Sprint 5 summary could be validated against. Resolving the chain
took footnote-owned tables from 23 to 26.

Statements carry no TextBlock — each figure is tagged individually — so they are identified by the
concepts of the numeric facts inside their own byte range, separating the five primary statements
from the 31 layout tables they had been pooled with.

| Filing | Total | Footnote | Excluded | Statement | Other | Unresolved |
|---|---|---|---|---|---|---|
| 10-K | 62 | 26 | 0 | 5 | 31 | **0** |
| 10-Q ×3 | 37/37/38 | 11/11/12 | 0 | 5 each | 21 each | **0** |
| total | 174 | **60** | 0 | 20 | 94 | **0** |

Zero excluded-section tables is a measurement: the three Item 408 and Item 1C disclosures were
checked directly and contain no table. The classifier handles the case; this filer does not
exercise it.

#### Added: migration `0002_table_ownership`

`footnote_table` gains `ownership_kind`, `ownership_method`, and `ownership_evidence`, a check
constraint restricting the kind, a partial index over unresolved rows, and a constraint requiring
`ownership_kind = 'CANONICAL_FOOTNOTE'` and a non-null `footnote_id` to agree in both directions.
A NULL `footnote_id` alone cannot distinguish a statement from an excluded disclosure from an
unresolved table, and only the last is a defect. `0001_initial` is untouched; the round trip was
tested against `fintek_test`.

#### Fixed: idempotency was a rewrite, not a no-op

A rerun reported `updated 13 footnotes, 59 blocks`. A full-row digest showed no duplicates and no
business-field drift — but every rerun stamped a fresh `extraction_run_id` and
`grouping_decided_at` onto decisions that had not changed, so those fields answered "which run
last touched this" while their names promise "which run decided this, and when".

Every upsert is now conditional on a value genuinely differing, so an identical rerun performs no
write at all and the full-row digest — timestamps and run ids included — is byte-identical.
Correction behaviour is preserved and tested: the condition is on the values, not a flag.

#### Not done, deliberately

- **No migration.** The sealed `0001_initial` already carries every audit column and every
  uniqueness constraint idempotency needs, verified against the live catalog before the
  persistence layer was written.
- **Stages 6 through 11 are not implemented.** Stage 3 left zero children unattached across all
  four filings, so no fallback could be exercised. An architecture test asserts the later grouping
  methods are not produced.
- **`filing_document` registration stays carried forward.** Canonicalization does not need it:
  input is located through the acquisition manifest and each footnote persists the renderer
  position, role URI, and inventory hash.
- **Tables are persisted at filing level, not per note.** Attributing a table to its owning note
  needs a document-offset-to-report mapping the renderer does not provide. A NULL is honest; a
  guess would not be.

Role-URI grouping is measured on one issuer. It is not claimed to be universally sufficient;
breadth validation across 25 issuers and four eras is Stage 2 phase W-3.


### Sprint 3 — filing discovery and acquisition (committed as `2672222`, `1e9f343`, `bc9aeb6`)

**The first SEC filings have been retrieved.** Requirement 1 of fifteen had not started before
this; the repository now holds four real Apple filings with full provenance.

#### Added

- `packages/filing_discovery`: every 10-K and 10-Q for an issuer, from the submissions API plus
  its overflow shards, with era classification and quarterly-index reconciliation. Apple yields
  **134 covered filings, 1994 to 2026**, reconciling **134 = 134** against `master.gz` across 131
  quarters with zero gaps in either direction.
- `packages/filing_acquisition`: inline-XBRL-era acquisition of the primary document, the
  `-xbrl.zip`, SEC's own extracted instance, `FilingSummary.xml`, and the schema. **20 objects,
  8.42 MiB preserved**, idempotent on re-run at zero requests, zero throttle events.
- `scripts/build_fixtures.py` and `tests/fixtures/filings/`: a 188 KiB fixture tree with a
  manifest pinning every source URL and SHA-256. The raw documents stay in gitignored object
  storage, per the strategy decided in SPRINT-0003.
- `SecHttpClient.get_bytes` for small in-memory fetches such as the gzipped quarterly index.
- `.gitleaks.toml`. The scanner flagged four false positives: the `generic-api-key` rule matched
  `aapl-20250927.htm`, a public SEC document filename. The config adds a narrow allowlist for the
  SEC inline-XBRL filename and dashed-accession shapes and **disables no rule**. Verified against
  a fixture that a real credential is still caught, including one placed directly beside a SEC
  filename.
- 58 tests: discovery, acquisition, fixtures, and the item-disclosure exclusion list exercised
  against real acquired data rather than an invented example.

#### Fixed

- **The client rejected a filing's primary document.** `_assert_not_error_page` treated any HTML
  body as an error page, which was correct for the DERA mirror and wrong here: a primary document
  *is* HTML. Added `expect_html`, which keeps the directory-listing check active because a folder
  index is also HTML and is the corruption the guard exists to catch.
- **A gzipped response was misread as truncated.** SEC serves `.htm` and `.xml` gzipped, so
  `Content-Length` reports compressed bytes while httpx yields decompressed ones. The
  completeness check compared the two and rejected a whole 1,520,208-byte document against a
  declared 111,447. It now skips the comparison when `Content-Encoding` is set. The DERA path
  never saw this because SEC does not re-compress a `.zip`.

#### Measured

- `filings.recent` returned exactly its documented 1,000-entry cap. **89 of Apple's 134 covered
  filings came from the overflow shard** — reading only `recent` loses 66 percent of the history,
  and the loss is indistinguishable from a company that files less.
- The 13-not-58 correction confirmed against the acquired `FilingSummary.xml`: 71 `<Report>`
  elements, 16 `menucat='Notes'` candidates, 3 Item 408 / Item 1C disclosures, **13 footnotes**.
- The 71st report is `All Reports`, `ReportType: Book` — the renderer's navigation entry, with no
  category, role, or file. The filing has **70 real reports plus one index entry**.

#### Completed after the initial Sprint 3 entry

- **PostgreSQL 18.4 installed and the migration applied to a live database**, the oldest open
  blocker in the project. `upgrade head` → `downgrade base` → `upgrade head` all succeed; the
  live schema carries 24 domain tables plus `alembic_version`, 25 primary keys, 19 unique and 29
  foreign-key constraints, 23 check constraints, 37 explicit indexes (81 including
  constraint-backing), and the append-only trigger. All counts are `public`-schema only.
- **The two live migration tests now pass rather than skip.** The suite reports **203 passed,
  0 skipped** — the first run in this project where every test executed.
- **No database credential is stored on this development host.** Authentication is `peer` over
  the Unix socket with a `pg_ident` map, so there is no password in `.env`. Verified directly
  rather than assumed: `select rolpassword is null from pg_authid where rolname='fintek'` returns
  true, so no SCRAM verifier exists for the role. `DATABASE_URL` carries a role name and a socket
  path only. This is a local-development arrangement and says nothing about deployment, which is
  undecided; CI deliberately uses a disposable password instead.
- **URGENT-02 discharged.** All twelve monthly DERA packages, 2,145,477,071 bytes, copied to a
  separate filesystem and verified: source hash against the ledger, destination hash after copy,
  and ZIP CRC on every member. A second run copied 0 bytes and re-verified every hash.

#### Fixed by the first live database run

Both were invisible to offline DDL generation, which writes SQL without executing it.

- **The migration could not apply at all.** `xbrl_fact.dimensions` used
  `server_default="{}"`; SQLAlchemy emits a bare string server default as raw SQL, producing
  `DEFAULT {}` — a syntax error. Now `server_default=text("'{}'::jsonb")`, matching the partial
  index that had always spelled the literal correctly.
- **The append-only test was vacuous.** It ran
  `UPDATE xbrl_fact SET value_as_filed = '1' WHERE false`. Zero rows match, and the guard is a
  `FOR EACH ROW` trigger, so it never fired and the statement always succeeded — the test could
  not fail whatever the schema did. Rewritten to insert a real fact and attempt to change its
  filed value. Proven non-vacuous: dropping the trigger makes it fail. The trigger itself was
  always correct.

#### Completed last: the DERA fact load

**The fact lake holds real filed data.** 2,845 facts across Apple's FY2025 10-K and its three
10-Qs, every one reconciled against the package it came from.

- `packages/dera_notes` gained eight modules, one responsibility each: `selection` (which package
  contains a filing, and archive completeness), `tsv` (parsing), `dimensions` (dimh to axis and
  member), `normalize` (row to domain values), `validate` (domain rules), `registration` (the
  issuer and filing rows the fact foreign keys require), `loader` (transaction, insertion, load
  ledger, idempotency), `reconcile`, and `report`.
- `scripts/load_dera_partition.py` orchestrates them and holds no parsing, validation, or SQL of
  its own. It exits non-zero unless every reconciliation check passes.
- `packages/persistence/engine.py`: the single home for resolving `DATABASE_URL`. Three places
  had their own copy.
- 96 tests, including a live-database integration suite proven non-vacuous by removing the
  idempotency guard and watching the rerun test fail.

| Filing | Facts | Consolidated | Package |
|---|---|---|---|
| `0000320193-25-000079` 10-K FY2025 | 967 | 547 | `2025_10_notes.zip` |
| `0000320193-25-000073` 10-Q Q3 | 683 | 317 | `2025_08_notes.zip` |
| `0000320193-25-000057` 10-Q Q2 | 672 | 309 | `2025q2_notes.zip` |
| `0000320193-25-000008` 10-Q Q1 | 523 | 231 | `2025q1_notes.zip` |

Reconciliation is nine checks per load, all passing. The strongest is the numeric total: the sum
of every accepted `value_numeric` computed in Python matched PostgreSQL's own `sum()` exactly —
34,808,176,701,339.3705 for the 10-K, a delta of zero against a rounding tolerance of 0.000967.
A rerun re-reads the whole package, finds every natural key present, and inserts nothing.

#### Fixed by the DERA load

- **A derived quarter start was a day short.** `period_start` is derived, because DERA publishes
  an end date and a quarter count and no start at all. Subtracting whole months and adding a day
  clamps 30 June minus three months to 30 March, because March has 31 days, giving 31 March. The
  error is invisible on annual periods ending 30 September and wrong on every quarter ending in a
  30-day month. Caught by a unit test **after** the first load had already written 136 wrong rows;
  those were deleted and reloaded. Now derived as the first day of the month `months - 1` earlier,
  with a test asserting consecutive quarters tile the year with no gap and no overlap.
- **A credential sat in a tracked file.** `migrations/env.py` defaulted to
  `postgresql+psycopg://<user>:<password>@localhost:5432/<database>`, and `tests/unit/test_migrations.py`
  carried the same string. Both now resolve through `packages/persistence/engine`. The default
  was also actively harmful: against a cluster using peer authentication over a Unix socket it
  made the reachability probe succeed, so the live tests **ran** instead of skipping and then
  failed on authentication — which reads as a broken database rather than a wrong URL.
- **`iter_rows` read whole members into memory.** A monthly `num.tsv` is 261 MB decompressed and
  `txt.tsv` is 210 MB; `archive.read()` cost the bytes plus a decoded copy for data consumed one
  row at a time. Now streamed through `TextIOWrapper`.
- **The test suite destroyed the data it was run against.**
  `test_upgrade_then_downgrade_round_trips` runs `alembic downgrade base`, dropping every
  application table. On a development host holding a real load, `make check` deleted 2,845 facts
  and reported green. Destructive tests now run against a separate disposable database; see the
  new invariant below.
- **An inter-test dependency, exposed by that fix.**
  `test_filed_fact_cannot_be_updated` inserted its fixture using Apple's real CIK and accession,
  both UNIQUE, so it failed as soon as the database held a real load. It had only ever passed
  because the destructive test ran first and emptied every table. It now builds its own schema on
  the disposable database and uses reserved identifiers, so it depends on no other test.
- **Package ordering was accidental.** `locate_filing` sorted ledger periods as raw strings, which
  compares `2025-10` against `2025Q3` by comparing `-` to `Q`. Both forms are now parsed to a year
  and an end month, and a tie prefers the quarterly package — monthlies are deleted upstream, so a
  load citing one becomes unreproducible once SEC consolidates.

#### Measured

- 969 rows in `num.tsv` carry the 10-K's accession; 967 became facts. The two rejections are
  `CommitmentsAndContingencies` rows with no value — the shape DERA uses for a line-item label.
  They are counted and reported, never silently dropped.
- 894 of the 10-K's facts use `us-gaap`, 71 are issuer extensions, 2 are `dei`. 257 distinct
  concepts. 488 instants and 479 durations.
- A full load takes about 30 seconds, almost all of it counting rows in the other five members
  for provenance.

#### Added: TEST-DATABASE-ISOLATION-INVARIANT

`rules.md` section 3 gains an eleventh non-negotiable invariant:

> Destructive database tests must never operate on the configured application database. Migration
> upgrade and downgrade tests run only against a dedicated disposable test database, and must fail
> closed if the test target cannot be proven separate.

- Two variables with no fallback between them: `DATABASE_URL` for the application database,
  `TEST_DATABASE_URL` for destructive tests. A fallback works everywhere, quietly, until the day
  the application database has something in it.
- `packages/persistence/engine.assert_disposable` proves separateness before any destructive test
  body runs. It compares parsed host, port, socket path, and database name — **not the configured
  strings**, because `@localhost/fintek` and `@127.0.0.1:5432/fintek` are different strings and
  the same database — and excludes credentials on purpose, so a destructive run cannot be
  authorized by connecting as a different user. It further requires a `test` token in the name and
  refuses `prod`, `production`, `live`, `master`, and `primary`.
- A session hook in `tests/conftest.py` records `issuer`, `filing`, and `xbrl_fact` row counts
  before the suite and fails the run if they change — from a dropped table or from a fixture row
  left behind. Always on.
- `scripts/create_test_database.py` with `make db-create-test`, `db-verify-isolation`,
  `db-upgrade-test`, and `test-summary`.
- 30 tests in `tests/unit/test_database_isolation.py`, each named after the specific way a weaker
  guard still lets the deletion happen: substring matching designating `latest` disposable, a
  credential difference masking an identical target, `prod_test` passing a naming check.
- `docs/runbooks/test-database.md`, and a gitignored `var/local-tools/setup_test_database.sh` for
  the one privileged local action — the `fintek` role has no CREATEDB and `pg_hba` scopes peer
  authentication to the `fintek` database, both deliberate.

#### Added: Markdown integrity checks

`tests/architecture/test_documentation.py` — fences balanced, no heading trapped inside a code
block, relative links resolve, no password-bearing database URL in prose, README headings render,
README within its 700-to-1,200-word budget. Scans repository-owned files via `git ls-files`.
Each check was proven to fire by introducing the corresponding defect.

It found a pre-existing false positive in its own first form (a `#` shell comment inside a
` ```bash ` block read as a swallowed heading) and a scoping bug (a directory walk pulling in a
dependency's README), both corrected.

#### Operational changes

- CI runs a **PostgreSQL 18 service container** with a fixed, disposable, obviously
  non-production password written openly in the workflow. It protects nothing: the container is
  created and destroyed by one job, is reachable only from that job, and holds public SEC data. A
  repository secret would imply the value is sensitive and add a rotation obligation for something
  that cannot leak anything. It replaces `POSTGRES_HOST_AUTH_METHOD: trust`, which accepted any
  connection with no password and therefore never exercised the authentication path the
  application code takes. It is not a pattern for a deployed database, and how one will
  authenticate remains undecided; the local host still uses peer authentication and stores no
  password at all. The health check authenticates rather than probing the port, so the job waits
  for a server that will actually accept the credential the tests use.
- The job creates `fintek_test` explicitly — `POSTGRES_DB` creates exactly one database — and runs
  `make db-verify-isolation` **before** any test, so a misconfiguration is caught before something
  drops a table rather than after. No step echoes a URL: `db-verify-isolation` prints host, port,
  and database name only.
- `make test-summary` no longer reruns the suite. It reads `.pytest-last-run.log`, written by the
  run that the zero-skip gate just enforced, so the reported counts come from that execution
  rather than a second one.
- `.env.example` no longer carries the former password-bearing localhost database URL. That was a
  credential in a tracked file, which this project prohibits, and wrong for a peer-authenticated
  cluster besides.
- New Makefile targets `db-upgrade` and `test-no-skips`. The second sets `FINTEK_FORBID_SKIPS`,
  which a hook in `tests/conftest.py` reads to fail a run that skipped anything, naming each test
  and its reason. CI runs it. Proven to fire by adding a deliberate skip.
- Test targets now pass `-ra` instead of `-q`. A skip was a bare `s` in a progress line, and
  "203 passed, 2 skipped" read as success for two sprints while the only two tests exercising the
  live schema had never executed.
- `docs/runbooks/dera-backup-mount.md`: the backup device is still not persistent across reboots.
  The runbook carries the exact `fstab` entry, why it must be by UUID and carry `nofail`, and the
  post-reboot check. Applying it needs root and has not been done.

#### Known limitations recorded, not worked around

- **DERA period boundaries are approximations.** `ddate` is rounded to the nearest month end and
  `qtrs` is a whole number of quarters; DERA publishes the residuals separately as `datp` and
  `durp`. Apple's FY2025 ended 2025-09-27 and DERA records 2025-09-30. Every row this loader
  writes is therefore `validation_status = 'UNVALIDATED'` — the exact filed boundaries live in
  the XBRL instance, and because `xbrl_fact` is append-only, that later observation supersedes
  these rows through the ordinary restatement path rather than overwriting them.
- **Only the named filing is loaded, not the whole package.** `xbrl_fact` has foreign keys to
  `issuer` and `filing`, so loading a monthly package outright would first require registering
  thousands of issuers. That is Stage 2 phase W-1 and out of scope by ADR-0015.
- **`filing.era` is left NULL by DERA registration.** DERA does not describe a filing's
  acquisition era; `packages/filing_acquisition` owns that column and does not yet write to the
  database.

---

### Earlier unreleased entries

Two: the Sprint 2 alignment review (committed as `275db19`), and the CI repair that
followed the first GitHub Actions run.

---

### CI repair — committed as `7ebfb82`

The repository's first Actions run failed in both jobs. Neither failure was caused by the commit
that triggered it; both were latent defects that had never executed because the workflow triggers
on push to `main`, the branch was `master`, and no remote existed.

#### Fixed

- **`pip install -e ".[dev]"` could never succeed.** Setuptools flat-layout auto-discovery aborts
  with `Multiple top-level packages discovered` because the repository root holds `prompts`,
  `artifacts`, `migrations`, `metric_definitions`, `docs`, and `tests` alongside `packages`.
  `pyproject.toml` now declares explicit discovery, `include = ["packages*"]`, plus an explicit
  `[build-system]`. Verified: editable install succeeds in a clean virtualenv, all nine
  subpackages import, and none of the six non-package directories is packaged.
- **Three runtime dependencies were undeclared.** `sqlalchemy`, `alembic`, and `psycopg[binary]`
  are imported by `packages/persistence`, `migrations/`, and the migration tests but were absent
  from `[project].dependencies`. The install failure had masked this: fixing discovery alone would
  have moved the failure to the test step with `ModuleNotFoundError: sqlalchemy`. Proven by
  simulating the CI dependency set before declaring them.
- **Gitleaks had never scanned anything.** The action derived a commit range from the push event,
  which on a first push resolved to `<root>^` — the parent of the root commit, which cannot exist.
  It errored having scanned `~0 bytes` and failed the job. Replaced with a pinned CLI binary
  (8.30.1, SHA-256 verified) invoked over **all reachable commits** and **the working tree**,
  never an event-derived range. Checkout now uses `fetch-depth: 0`; it was `1`, which cannot be
  scanned for history at all.
- **CI validated narrower paths than local validation.** CI checked `packages tests` while local
  validation checked `packages tests scripts migrations`. The Makefile is now the single
  definition of every command and CI invokes those targets, so the two cannot drift. `rules.md`
  section 17 required this reconciliation.
- **The dependency scan was silently suppressed.** `pip-audit --strict || true` swallowed every
  result. `--strict` errors on `fintek` itself, which is an editable local install and not on
  PyPI; `--skip-editable` is the correct exclusion. The gate is now enforcing. Verified: exits 0
  on the current dependency set and exits 1 against a deliberately vulnerable pin.

#### Added

- `docs/runbooks/ci-failure.md` — reproducing each failure locally, and what not to do about it.
- `make migration-check` — offline Alembic upgrade and downgrade, now part of `make check`.
- A CI step asserting the installed distribution actually imports.
- `workflow_dispatch` trigger, and an explicit least-privilege `permissions: contents: read`.

#### Changed

- Type checking covers `packages scripts migrations`, 45 source files. `tests` is excluded
  deliberately and the reason is recorded: it reaches into SQLAlchemy internals where
  `Model.__table__` is typed as `FromClause`, and blanket ignores would weaken the check for the
  source that matters.
- `CLAUDE.md`, `techspecs.md`, `README.md`, `docs/testing/strategy.md`, and
  `docs/architecture/deployment.md` updated. The recorded warnings that CI cannot install the
  project, that gitleaks cannot run locally, and that CI omits `scripts` and `migrations` are
  removed **because they are no longer true**. The `master` branch warning is removed because the
  branch is now `main`.

---

### Sprint 2 alignment review — committed as `275db19`

A product-alignment audit against the fifteen core product requirements, a Git governance
amendment, and the resulting planning corrections. No feature code was added.

### Added

- `rules.md` sections 15 to 20: the COMMIT-AUTHORIZATION, PRE-COMMIT-VALIDATION, TEST-DISCOVERY,
  DOCUMENTATION-SYNCHRONIZATION, and GIT-SAFETY invariants, plus Sprint Completion and Git. No
  agent may create or push Git history without explicit per-operation user approval;
  `--dangerously-skip-permissions` and pre-approved tool-permission entries grant no Git
  authority. The former section 15 is renumbered to 21.
- `CLAUDE.md`: loaded automatically each session, requiring `rules.md` to be read and restating
  the commit and push authorization requirement.
- `docs/adr/ADR-0015-thread-first-delivery-sequence.md`: prove one vertical thread through every
  layer before widening any layer.
- `docs/dashboard/ux-specification.md`: the product surface, including the states previously
  unspecified — partial coverage, low confidence, refused out-of-scope requests, budget
  exhaustion, and session restoration.
- `docs/llm/analysis-model-benchmark.md`: the Deep Analysis model benchmark, which did not exist.
  Multi-turn retention, evidence grounding, and an adversarial scope-escape subset with
  zero-tolerance security gates. The deterministic detector is measured separately from the model.
- `docs/footnotes/period-comparison.md`: same-footnote comparison across periods, keyed on a
  stable topic key rather than a note number, which is not stable across filings.
- `metric_definitions/item_disclosure_exclusions.yaml`: the Item 408 and Item 1C exclusion list
  that canonicalization stage 2 reads. It was referenced by the algorithm and did not exist.
- `docs/sprints/SPRINT-0003.md`: the Sprint 3 plan, including a decided fixture strategy.
- `footnote_source_block`: per-attachment grouping audit columns — `grouping_method`,
  `grouping_confidence`, `grouping_evidence`, `competing_candidates`, `extraction_run_id`,
  `grouping_parser_version`, `grouping_decided_at`.
- `filing`: `completeness_confidence` and `reconciliation_status`.
- API: `/issuers/{cik}/footnote-topics` and `/issuers/{cik}/footnote-topics/{topic_key}`.
  Error code `UNSUPPORTED_FILTER`.
- Architecture tests: anti-vacuity guard, no-empty-stub guard, and a single-home guard for
  model-visible prompts. Migration tests for the attachment audit and completeness design.

### Changed

- `roadmap.md` rewritten into the thread-first sequence. Sprints 3 to 7 contain every dependency
  of the vertical slice; breadth work moves to Stage 2. Provider catalog verification, model
  selection, and cost measurement move from Phase 6 to Sprint 5, which is now an explicit
  go/no-go on unit economics. The zero-LLM dashboard test lands with the first read endpoint in
  Sprint 6 rather than at sprint 22.
- `docs/llm/model-benchmark.md` split into a tier-1 smoke benchmark of 15 footnotes in Sprint 5
  and the full tier-2 120-fixture program before backfill. A tier-1 pass is provisional and does
  not select a production model.
- `docs/footnotes/completeness.md`: eleven of thirteen counters documented as derived rather than
  stored, with their derivations. Storing a derivable count creates a second source of truth.
- `docs/footnotes/canonicalization-algorithm.md`: the grouping audit record is recorded on the
  child block, because stages 3 and 6 to 10 decide per child.
- ADR-0008 and ADR-0009 moved from ACCEPTED to PROVISIONAL. Both were decided in Sprint 1 with
  nothing deployable and their implementation phase roughly twenty sprints away.
- `rules.md` section 5: `bedrock.py` and `deep_analysis/scope.py` marked RESERVED rather than
  presented as implemented single-home owners.
- Current test counts corrected to 143 in `README.md`, `docs/testing/strategy.md`,
  `docs/architecture/deployment.md`, and `techspecs.md`. **Historical counts in
  `docs/sprints/SPRINT-0001.md` and the 0.1.0 entry below are left unchanged, because they are
  accurate records of what was true then.**
- `techspecs.md` section 3.6 corrected: it described the DERA download as PLANNED while
  section 2 recorded it as executed.

### Removed

- Eighteen packages containing only a docstring: `deep_analysis`, `domain`, `fact_lake`,
  `filing_acquisition`, `filing_discovery`, `filing_parser`, `financial_metrics`, `fiscal`,
  `footnote_canonicalizer`, `footnote_extractor`, `issuer_registry`, `metric_definitions`,
  `retrieval`, `summarization`, `table_parser`, `testing_support`, `validation`, `xbrl`. They
  reserved names up to twenty sprints ahead of their code and caused two architecture tests to
  pass while scanning nothing. Reserved names now live in `techspecs.md` section 2 with a status
  column, and an architecture test prevents the pattern returning.
- Empty `apps/` and `infrastructure/` directory trees, untracked by Git.
- `docs/deep-analysis/system-prompt.txt`, a byte-identical duplicate of
  `prompts/deep-analysis/v1.0.0/system.txt`. Two homes for one model-visible artifact drift, and
  only `prompts/` was scanned by the architecture tests.

### Data migrations

- `0001_initial_control_plane_schema.py` regenerated in place, adding nine columns. **The
  migration has never been applied to any database** — verified by connection refused on
  `127.0.0.1:5432` — so amending it is safe and avoids applying a known-incomplete schema to the
  live PostgreSQL that Sprint 3 creates. Offline upgrade DDL grew from 653 to 676 lines;
  downgrade remains 66 lines and symmetric.

### Fixed

- The roadmap's central contradiction: Phase 1 promised a vertical slice at sprints 3 to 5 while
  its dependencies were scheduled at sprints 8 to 33, and the sprint breakdown silently dropped
  the dashboard and Deep Analysis deliverables. The slice was described and scheduled nowhere.
- `classification=changed` was exposed by the API with nothing defining or computing it. It is
  now specified, and rejected with `UNSUPPORTED_FILTER` until the backing data exists.

## [0.2.0] — Sprint 2 — 2026-08-01

Discharges URGENT-01 and establishes the database schema.

### Added

- `packages/sec_client.client`: the SEC HTTP client. Built on the Sprint 1 limiter and throttle
  classifier. Streams to disk while hashing, and rejects rather than stores an HTML error page, a
  directory listing, wrong ZIP magic bytes, a body shorter than its declared Content-Length, a ZIP
  with no members, or a ZIP whose member fails CRC. Writes to a temporary path and renames only
  after every assertion passes.
- `scripts/mirror_dera.py`: the live DERA mirror, with size probe, dry run, monthly-only, and full
  modes. Produces a manifest and reconciles discovered against persisted.
- `packages/persistence`: the PostgreSQL control-plane schema. 24 tables, 36 indexes, 93
  constraints.
- `migrations/versions/0001_initial_control_plane_schema.py`: the initial migration, including a
  BEFORE UPDATE trigger on `xbrl_fact` that enforces append-only at the database level.
- `scripts/generate_initial_migration.py`: deterministic migration generation from model metadata,
  used because Alembic autogenerate requires a live database and this environment has none.
- 33 tests: 15 for the HTTP client, 14 for migrations, 4 for YAML library identity and alias
  bounding.

### Changed

- Roadmap URGENT-01 moved to COMPLETE with completion evidence. Risk R-01 CLOSED.
- Phase 0 marked COMPLETE.

### Fixed

- **Unbounded YAML alias expansion.** The Sprint 1 parser enforced size, depth, collection, and
  scalar limits AFTER parsing, which is useless against alias expansion because the allocation
  happens during parsing. Measured: a five-line document with nine anchors each referencing the
  previous nine expanded to 59,049 leaf nodes; two further levels exhaust memory. A pre-parse
  anchor and alias budget now rejects it. Found by the Sprint 2 YAML verification, not by review.

### Security

- YAML alias bomb protection, as above.
- The append-only guarantee on filed facts moved from a code comment to a database trigger, so it
  holds against a direct SQL session rather than only against application code.
- `llm_invocation` carries a check constraint restricting content format to plain_text or yaml,
  putting the LLM serialization invariant in the schema.

### Data migrations

- `0001_initial_control_plane_schema`. Verified by offline DDL generation in both directions.
  **Not yet applied to a live database**; see known issues.

### Operational changes

- **The DERA mirror is complete.** 78 of 78 discoverable packages held locally, 25.36 GiB, zero
  failures. The twelve monthly packages with no quarterly consolidation were secured first.
  `docs/runbooks/dera-mirror.md` records the run and the idempotency proof.

### Documentation

- ADR-0013 now pins the YAML parser (ruamel.yaml 0.19.1, YAML 1.2 core, pure safe mode) and
  documents the alias bound with its measurement.
- `techspecs.md`, `roadmap.md`, `docs/data-dictionary/README.md`, `docs/sec/dera-notes.md`, and
  `docs/runbooks/dera-mirror.md` synchronized with the implementation.

## [0.1.0] — Sprint 1 — 2026-08-01

The foundation sprint. Establishes durable project memory, the SEC-safety-critical primitives,
and the complete LLM content-boundary control set. No ingestion at scale and no real model calls.

### Added

- Repository scaffold: 25 domain packages, application shells, versioned prompt directories,
  test layout, and documentation tree.
- Governance documents: `rules.md`, `roadmap.md`, `techspecs.md`, `CHANGELOG.md`, `README.md`.
- 14 architecture decision records, ADR-0001 through ADR-0014.
- `packages/sec_identity`: CIK normalization, accession normalization, and SEC URL construction.
  The single home for these transforms, enforced by an architecture test.
- `packages/configuration`: eager settings validation, including SEC User-Agent validation that
  fails closed on a missing, generic, or emailless value.
- `packages/sec_client`: token-bucket rate limiting with separate global and full-text-search
  buckets, HTML 403 classification distinguishing a rate block from a configuration defect,
  reference-identifier extraction, directory-listing detection, and a typed error hierarchy
  carrying explicit retry classification.
- `packages/storage`: object-store abstraction with a filesystem backend, atomic writes, path
  traversal rejection, and SHA-256 hashing.
- `packages/observability`: structured logging with correlation identifiers and mandatory
  redaction of payload and secret fields.
- `packages/dera_notes`: package discovery by scraping the authoritative listing, classification
  handling the irregular 2010 filename suffixes, and a resumable mirror ledger.
- `packages/llm_gateway`: the complete model content boundary. Payload compiler, plain-text and
  YAML 1.2 serializers, hardened safe parser, boundary validator covering twenty prohibited
  constructs, token counter with a cross-serialization comparison harness, cost calculator that
  raises on an unpriced model, provider interface, and a deterministic mock provider.
- Six curated metric definitions: revenue, net income, operating cash flow, capital expenditures,
  total debt, and stock-based compensation.
- Production prompt files for footnote summarization and Deep Analysis, in `.txt` and `.yaml`
  only. Model-visible Markdown is prohibited and the prohibition is tested.
- Nine operational runbooks.
- 49 specification documents.
- 104 tests: 81 unit, 2 integration, 8 architecture, plus fixtures capturing real SEC 403 bodies
  and a directory listing.
- Docker Compose stack, Makefile, CI workflow, and environment template.

### Changed

- **The canonical footnote unit was corrected.** An earlier design counted 58 XBRL TextBlock
  facts as Apple's FY2025 footnote count. Direct verification shows 71 renderer reports, 16 in
  the Notes category, and **13 actual footnotes**. The three Notes-category entries that are not
  footnotes are Item 408 and Item 1C disclosures. This is a 4.5-fold correction to the unit of
  work and therefore to summarization cost. Recorded in ADR-0005.
- **The ingest ledger moved from SQLite to PostgreSQL.** The earlier reasoning was correct about
  DuckDB being unsuitable for concurrent upserts but did not follow through: PostgreSQL is
  already present and handles ten writes per second trivially. One fewer datastore. Recorded in
  ADR-0004.
- **The prior cost estimate was withdrawn.** It was computed on the wrong unit of work. Formulas
  and named placeholders replace it until parameters are measured. Recorded in ADR-0006.
- **The model content boundary replaced JSON and native tool calling.** The earlier design used a
  JSON summary schema, JSON Schema validation, and six native tools. All three are prohibited at
  the model boundary. Recorded in ADR-0013.

### Fixed

- Token bucket infinite loop. `tokens >= 1.0` compared exactly; after sleeping the computed delay
  the refill could land a fraction below 1.0 in binary floating point, so `acquire` spun forever
  on ever-smaller deltas. Found by the test suite hanging rather than by review. A nanotoken
  epsilon fixes it.
- Object store silently reinterpreted an absolute key as relative. It now rejects, because a
  caller passing `/etc/passwd` has a defect that should surface.
- YAML serializer could not represent forced-style scalars under the safe dumper. Explicit
  representers registered rather than falling back to round-trip mode.

### Security

- SEC User-Agent validation fails closed, preventing traffic that would certainly be blocked.
- Object keys cannot escape the store root.
- Log records redact payload bodies, prompts, and secrets.
- Model-visible content is validated in both directions against twenty prohibited constructs.
- Native tool calling is refused before any provider work.
- The YAML parser rejects duplicate keys, custom tags, and arbitrary object construction, and
  enforces limits on input size, nesting depth, collection size, scalar length, and document
  count.
- Budgets are enforced before invocation, never after.

### Data migrations

None. No database schema exists yet; it is Sprint 2.

### Operational changes

- `docs/runbooks/dera-mirror.md` records the rolling twelve-month retention window on monthly
  DERA packages. This is the only task in the project with an external deadline.
- Local development requires no model credentials. The mock provider exercises the full gateway
  path offline.

### Documentation

- All 49 specification documents carry an implementation status. Planned behaviour is never
  described as implemented.
