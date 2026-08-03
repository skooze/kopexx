# roadmap.md — Kopexx Delivery Roadmap

STATUS OF THIS DOCUMENT: IMPLEMENTED (accurate as of Phase 1, 2026-08-03)
LAST UPDATED: 2026-08-03, after Phase 1 completed against published baseline `d093e73`.
ARCHITECTURE DECISIONS: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`,
`docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md` and
`docs/adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`
SEQUENCING PRINCIPLE: evidence before architecture; architecture before schema; a working parser
review loop before anything that depends on parsed data.

---

## Product Vision

An investor selects a company, a timeframe, and models — a parsing model, and optionally an image
model, a summary model and an analysis/chat model. The backend discovers and acquires the filings,
preserves the original SEC artifacts byte-for-byte, and sends the complete relevant human-readable
source set **intact** to the selected parsing model. It validates what comes back against the
preserved bytes and streams the results. Browsing a completed result invokes no model.

**The backend orchestrates, transports, preserves and PROVES. It never decides what a filing
means.**

**ONLY THE PARSING MODEL IS REQUIRED.** A parser-only run is a complete, valid run and it is the
first functional workflow this project builds:

```
raw SEC filing  ->  parsing model  ->  parsed artifact  ->  UI review  ->  approve / reject
```

The image, summary and analysis/chat selectors may be left blank. The orchestrator executes only
the stages the user selected, in order, and stops after the last one. It never silently selects a
blank model, substitutes another, adds a stage, skips a selected stage, invokes an extra model,
retries through a different model, or turns a parser-only run into a full pipeline.

---

## Where the project is

```
PHASE 0    Corpus evidence                            COMPLETE
PHASE 0.5  Repository cleanup and corpus reverify     COMPLETE
PHASE 1    Secure AWS and model-access verification   COMPLETE  2026-08-03
PHASE 2    Parser experiments + review UI, together   NEXT — needs explicit authorization
PHASE 3    Optional model stages: image, summary, chat
PHASE 4    Persistence, approval gate and reuse
PHASE 5    Background population
PHASE 6    Functional beta UI
PHASE 7    Deep Dive
PHASE 8    Breadth and optimization
```

**AWS IS CONFIGURED AND FIVE MODELS HAVE ANSWERED.** Seven minimal invocations on 2026-08-03, total
spend USD 0.00023 under an authorized USD 1.00 ceiling, proving reachability and nothing else. The
verified identifiers, regions, modalities, limits and prices are in
`docs/llm/bedrock-capability-snapshot.yaml` and are not repeated anywhere else.

**NOTHING IS DEPLOYED. NO SUMMARY EXISTS. NO APPLICATION DATABASE EXISTS. NO SEC FILING HAS BEEN
SENT TO ANY MODEL.** Every cost figure in `docs/llm/cost-model.md` remains a placeholder — official
price INPUTS are now known, but the token counts they multiply are not, and the first measured cost
per filing is Phase 2.

| Area | Status |
|---|---|
| Repository scaffold, governance | IMPLEMENTED |
| SEC identity library | IMPLEMENTED |
| SEC client, rate limiting, throttle classification | IMPLEMENTED |
| Object storage abstraction and hashing | IMPLEMENTED (filesystem); S3 PLANNED |
| Configuration and User-Agent validation | IMPLEMENTED |
| Observability: structured logging, redaction, correlation | IMPLEMENTED |
| Filing discovery against a supplied qualifying-form set | IMPLEMENTED |
| Filing acquisition, byte-exact, inline-XBRL era | IMPLEMENTED |
| LLM gateway: boundary, YAML 1.2, budget, audit, mock provider | IMPLEMENTED |
| Representative research corpus (112 issuers, 613 filings) | COMPLETE — Phase 0 |
| Corpus integrity, identity and form-family contracts | IMPLEMENTED and REVERIFIED 2026-08-03 |
| Verified model capability catalog and cost ceiling | IMPLEMENTED — Phase 1, `packages/model_catalog` |
| Deterministic semantic parser, canonical footnotes, table ownership | **DELETED** (ADR-0017) |
| DERA mirror and fact loader | **DELETED** (ADR-0017); the mirrored data is untouched |
| Application PostgreSQL schema, ORM, Alembic migrations | **DELETED** (ADR-0017) |
| Filed-document lister, non-classifying | NOT STARTED — Phase 2 |
| Secure AWS access, Bedrock capability discovery | COMPLETE — Phase 1, 2026-08-03 |
| Four-role model router | NOT STARTED — Phase 2, completes `packages/model_catalog` |
| Real provider adapter | NOT STARTED — Phase 2 |
| Parser-review UI | NOT STARTED — Phase 2, built WITH the parser experiments |
| Parsed / image / summary / chat artifacts | NOT STARTED — Phases 2, 3 |
| Persistence, approval gate, Redis cache | NOT STARTED — Phase 4 |
| Background population | NOT STARTED — Phase 5, needs separate authorization |
| Functional beta UI | NOT STARTED — Phase 6 |
| Deep Dive | NOT STARTED — Phase 7 |

---

# PHASE 0 — Representative filing corpus (COMPLETE)

Acquire and measure real filings across the COMPLETE SEC 10-K/10-Q reporting family before
designing anything.

Every time-eligible EDGAR quarterly master index from 1993Q1 through 2026Q3 — 135 quarters, zero
unavailable. 41 distinct 10-family form strings enumerated and adjudicated: **22 direct substantive
reports included, 19 near-matches excluded** with a recorded reason. Every included form carries an
authoritative SEC description read from a real filing-detail page and a verified accession.
Qualifying-family logic is GENERATED from that inventory; an unreviewed candidate fails the gate.

```
MEASURED 2026-08-02, REVERIFIED 2026-08-03
112 issuers   613 filings   760,174,532 bytes   613/613 hash-verified   0 throttle events
22 of 22 forms present   6 of 6 transport eras   75 SIC industries
313 annual / 300 quarterly     475 base / 138 amendments
510 standard / 42 small-business / 36 transition / 25 Item-405
187 image-bearing   11 PDF-bearing   113 inline XBRL   281 plain-text or SGML
44% of primary documents exceed ~200,000 estimated tokens; 12% exceed ~1,000,000
largest: JPMorgan Chase 10-K, 12.9 MB, ~4.3M estimated tokens
```

**EVERY TOKEN FIGURE IS A CHARACTER-RATIO ESTIMATE** at 3.0 characters per token, never a provider
tokenizer count. These totals describe one sample on one date. They are dated evidence, not
permanent constants.

THE DEFECT THIS PHASE EXISTED TO CATCH. The first pass filtered on guessed hyphenated strings
`10-KSB` and `10-QSB`, matched almost nothing, and concluded the small-business family was
"effectively absent". EDGAR uses `10KSB` and `10QSB`. `10QSB` alone is 120,120 filings by 9,771
issuers — the FOURTH most common form in the entire family. A guessed allowlist produced a
confident, precise, inverted conclusion.

# PHASE 0.5 — Repository cleanup and corpus reverification (COMPLETE, `d093e73`)

The cleanup gate that had to close before any AWS work.

```
complete code audit                          DONE — every active path classified
programmatic semantic parser deleted         DONE — footnote_extractor, footnote_canonicalizer,
                                                    table_parser, the accession classifier
parser-specific tests deleted                DONE — 346 test functions
obsolete persistence deleted                 DONE — 24 ORM tables, engine, isolation machinery
active obsolete migrations deleted           DONE — 0001, 0002, alembic wiring
DERA mirror and fact loader deleted          DONE — fails the seven-part test on 3 of 7 parts
unused database dependencies removed         DONE — sqlalchemy, alembic, psycopg, pydantic
clean distribution proven                    DONE — wheel and sdist inspected, external import test
corpus reverified                            DONE — see PHASE 0
```

Authoritative explanation: `docs/adr/ADR-0017`. It is not repeated elsewhere.

---

# PHASE 1 — SECURE AWS AND MODEL-ACCESS VERIFICATION (COMPLETE, 2026-08-03)

Full record: `docs/sprints/PHASE-0001-secure-aws-and-model-access.md`.
Decision: `docs/adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`.
Reproduce: `docs/runbooks/bedrock-capability-discovery.md`.
Evidence: `docs/llm/bedrock-capability-snapshot.yaml`, which is the ONLY place the verified
identifiers, regions, modalities, limits and prices are written down. A capability recorded twice
drifts.

```
identity            IAM Identity Center, temporary credentials through the SDK provider chain.
                    No static key exists and none was created.
control plane       all five candidate LABELS mapped UNIQUELY to real provider models
runtime             5 text gates and 2 image gates, all ACCEPTED
multimodal          2 of 5 verified BY INVOCATION — each read a word out of a 173-byte PNG
spend               USD 0.00023 against an authorized USD 1.00 ceiling
ordinary CI         still AWS-free: contents:read only, no id-token, no credential, no SDK
```

**Four findings that constrain Phase 2.** Llama 4 Maverick cannot be invoked by its model id and
requires a cross-region inference profile that routes across three regions. Qwen3 235B A22B is not
available in `us-east-1` although its model card says it is. Context limits span 128K to 1M and
output limits 8K to 32K across the five, against dated Phase 0 evidence that 44 percent of primary
corpus documents exceed ~200,000 estimated tokens. One candidate emits reasoning content before its
answer, so an output budget sized for the answer alone returns nothing.

## Credentials

```
IAM Identity Center / SSO, Isengard identity, assumed IAM roles, workload or service roles,
OIDC role assumption in CI — any short-lived mechanism appropriate to the environment,
resolved through the AWS SDK default provider chain.
```

**NEVER: a static access key in Git, in source, or in `.env`; a credential in a prompt, in
model-visible content, or in a browser; any browser-to-Bedrock path.** AWS Secrets Manager holds
workload secrets that IAM cannot replace — it is not where AWS keys live, and it is not a
substitute for a role when calling an AWS service. `rules.md` section 3,
AWS-IDENTITY-AND-SECRETS-INVARIANT, and `docs/security/aws-identity-and-secrets.md`.

**Ordinary CI remains AWS-free** unless a separately authorized integration workflow is later
created. No `id-token` permission, no credential configuration, no provider SDK.

## Capability discovery

For each of the five user-approved beta candidate LABELS — GPT OSS 120B, NVIDIA Nemotron 3 Super
120B, Qwen3 235B A22B, Llama 4 Maverick, Qwen3 VL 235B — discover and record, or record
unavailability:

```
actual availability          the exact provider model ID and version
region                       modality: text, image, both
context limit                output limit
supported request formats    official price inputs
```

**These were labels, not verified Bedrock model identifiers.** Discovery returned all of it on
2026-08-03 and the results live in `docs/llm/bedrock-capability-snapshot.yaml`. **The rule survives
the phase:** no availability, modality, limit, region or price may be recorded anywhere as settled
until discovery returns it, and re-running discovery replaces that file wholesale rather than
patching one field into a document still carrying an older date.

## Exit criteria — all met 2026-08-03

- Secure credential resolution works with no static key anywhere. **MET.**
- Bedrock control-plane and runtime access verified. **MET.**
- Every candidate label mapped to a real model ID, or recorded unavailable with the reason.
  **MET — five of five mapped uniquely.**
- **One real response obtained from every required available model. MET** — five text gates and two
  image gates, all accepted, under an authorized ceiling, for USD 0.00023.

---

# PHASE 2 — PARSER EXPERIMENTS AND THE REVIEW UI, BUILT TOGETHER (NEXT)

The previous roadmap placed the UI at Phase 6, after images, summaries and chat. That is too late:
**a parsed artifact cannot be evaluated without looking at it beside the filing it came from.**
Reading a YAML document in a terminal is not evaluation.

This does not mean building the polished beta before model testing. It means the first useful
frontend exists early enough to compare raw filings and parsed responses visually.

## 2a — The parser path

- Provisional flexible parser request and response contracts: raw text or exactly one unfenced
  YAML 1.2 document, with the ORIGINAL-SOURCE EXCEPTION for the intact artifact.
- A real provider adapter, in `packages/llm_gateway/providers/`, the only place a provider SDK may
  be imported.
- A non-classifying **filed-document lister**: filename, sequence, filer-declared type,
  description, size, from the accession index. No document class, no role, no extraction verdict.
  This replaces the classifier deleted in ADR-0017 and is what determines the complete relevant
  human-readable source set mechanically.
- Intact-source compatibility check against the verified Phase 1 catalog.
- Real parsing runs across corpus samples differing by era, industry, size, package shape and
  markup quality.

## 2b — The minimum review UI, in tandem

```
entity / filing selection  ->  model selection  ->  run  ->  raw / parsed review  ->  approve
```

Required from the first experiment:

```
entity selection                     filing or timeframe selection
parsing-model selector (REQUIRED)    image / summary / analysis selectors, may be left BLANK
model capability labels              Multimodal badge where applicable
run button                           streaming status
visible parent run ID                child filing-job status
RAW view    PARSED view    toggle    SIDE-BY-SIDE view
source-reference navigation          validation warnings
model metadata, prompt version, cost, token counts, latency
review status, approve, reject, comments
```

**Raw/parsed display controls.** A `Raw` view, a `Parsed` view, a toggle between them, and a
`Side by side` button. Source-reference links from parsed nodes to raw evidence. A visible warning
when a source reference cannot be resolved, when image-bearing content was not analyzed, and when
the parse contains unresolved content. Side-by-side gains synchronized navigation where practical;
perfect visual synchronization is NOT required before the first experiments.

## 2c — The elastic response requirement

The parsing model determines filing-native section names, subsection names, titles, labels,
groupings, relationships, table labels, footnote labels, display hints, metadata and explanations.

**The backend must not require any filing to use a fixed label.** `Part I`, `Item 7`, `MD&A`,
`Risk Factors`, `Footnote 1`, `Revenue Table`, `Certification`, `Signature` and any fixed
proxy-topic name may APPEAR when the filing or the model uses them. They are not a mandatory
backend ontology.

A minimal extensible envelope may eventually carry: artifact identity, filing identity, source
identities, ordered nodes, model-selected node type, model-selected title, content, tables, source
references, metadata, confidence, ambiguity, unresolved content, parent/child relationships, prompt
identity, model identity, validation status. **This is not authorization to finalize it.** The
response format stays provisional until real models are tested, and the final contract is DERIVED
from what they return.

## 2d — Evaluation storage, before the final database

Review work must survive a page reload. That does not authorize designing the final relational
schema before real model output exists, and it must not recreate the rejected semantic PostgreSQL
schema in another form.

Permitted during experiments: durable filesystem artifacts, object-store-like local directories,
plain append-only run manifests, plain YAML metadata, or other minimal non-semantic storage.
Evaluation artifacts must remain exportable and migratable.

## 2e — Measurement

Whether the provider accepts the intact artifact; input and output tokens; context compatibility;
omissions; source coverage; citation fidelity; numeric fidelity; cost; latency; and response
variability across models and across reruns of the same model.

**Level 1, BREADTH.** At least one compatible model processes intact filings covering all six
transport eras, standard annual and quarterly reports, transition forms, small-business forms,
Item-405 variants, at least one amendment, young and mature issuers, at least one image-bearing
filing, and at least one large filing near a discovered context limit. Attempt at least one trial
for **every one of the 22 exact substantive form strings** where compatibility and the cost ceiling
permit. Any untested form carries an explicit compatibility, availability or cost blocker recorded
against that exact string. Another form is never silently treated as equivalent.

**Level 2, CROSS-MODEL COMPARISON.** All available approved candidates against a smaller shared
benchmark set. Neither level substitutes for the other.

EXPLICITLY OUT OF SCOPE. Any rigid database schema. Any universal semantic taxonomy.

---

# PHASE 3 — THE OPTIONAL MODEL STAGES

Image, summary and analysis/chat may be built as separate subphases. They must compose into ONE
optional progressive workflow. **No stage is a hard prerequisite except parsing.**

The orchestrator must eventually support at least: parser only; parser+image; parser+summary;
parser+chat; parser+image+summary; parser+image+chat; parser+summary+chat; and all four.

## Image

**If the parsing model is MULTIMODAL:**
- the parsing-model dropdown labels it clearly as `Multimodal`;
- the parser handles supported filing images itself;
- the separate image-model selector stays VISIBLE but DISABLED for that run;
- the UI explains that image analysis is handled by the selected parsing model;
- no redundant image-model invocation occurs.

**If the parsing model is TEXT-ONLY and no image model is selected:**
- the parser-only workflow still proceeds;
- the backend identifies image-bearing artifacts or pages MECHANICALLY;
- the run reports which image-bearing content was NOT analyzed;
- **the run must not claim complete image coverage.**

**If a separate image model IS selected:** only mechanically identified image-bearing inputs are
sent; image analysis stays a separate linked artifact; results may be reconciled with the parse;
the original image bytes remain authoritative and preserved.

Corpus evidence, dated Phase 0: 187 of 613 filings carry at least one image, none before 1996 and
80 of 108 in the current era; 11 carry PDFs; the largest package carries 108 images.

## Summary

Optional. **If blank: no summary call occurs, the parsed artifact stays fully reviewable, and the
UI must not show a fabricated or placeholder summary.** If selected, it receives the accepted parse
and supporting source evidence and produces a separate summary artifact. It does not replace the
parsed artifact and does not replace the original filing. Regenerating a summary must not require
reparsing an unchanged filing.

## Analysis / chat

Optional. **If blank: no analysis session is created and no chat model is invoked.** If selected it
may operate on the original source, the accepted parse, the image artifact and the summary artifact
that exist for the run. **A summary is not required, and the summary must never be the sole
evidence source.** Responses are separate versioned artifacts with message-level lineage.

## Model dropdown requirements

Every model selector must eventually show: user-facing label; provider; exact verified model
version when known; availability status; region; text capability; image capability; a visible
`Multimodal` badge when applicable; context limit when verified; output limit when verified;
compatibility with the currently selected filing set; estimated or known cost when verified; and a
disabled state with a concrete reason when incompatible.

**No model capability may be claimed until Phase 1 verified it.**

---

# PHASE 4 — PERSISTENCE, THE APPROVAL GATE, AND REUSE

Designed AFTER real model outputs are understood, and BEFORE the functional UI depends on reusable
parsed artifacts, summaries, chat history, run logs, run IDs, comments, approval, cost history or
artifact lineage.

## Raw-first source storage — active from the beginning, not gated on approval

For every filing, before EDGAR is contacted:

```
1  resolve stable filing identity, at least (CIK, accession)
2  query the local source-artifact inventory
3  verify expected object presence
4  verify stored byte count
5  verify SHA-256
6  reuse the stored original when valid
7  fetch from SEC ONLY when the source is missing, incomplete, hash-invalid, a required member is
   absent, or the SEC package has a verified newer authoritative member
8  preserve the fetched source byte-for-byte
9  record provenance and acquisition metadata
10 never overwrite a valid original artifact silently
```

**Source identity** must account for at least: CIK; accession; exact filed form; filing date;
report period when available; SEC-declared document type; original filename; source URL; source
byte count; SHA-256; acquisition timestamp; acquisition method; package member identity.
**Accession alone is not globally sufficient — filing identity is `(CIK, accession)`.** One
accession legitimately belongs to more than one CIK: Alphabet and GOOGLE INC co-registered 10-K/A
`0001193125-16-520367`, one submission, identical bytes, two filer CIKs. Separately, 361 of 613
corpus filings carry an accession whose prefix is the FILING AGENT's CIK, so ownership is resolved
from the SEC archive path and never from the prefix.

## Parsed artifacts are evaluation artifacts until explicitly approved

A parsed response must be reviewable in the UI immediately. **It must not satisfy a user search as
a trusted result until it is explicitly approved.**

States, semantics fixed, exact naming refinable:

```
EVALUATION   UNDER_REVIEW   APPROVED   REJECTED   SUPERSEDED   INVALIDATED
```

**Approval is per filing and needs no other model.** A parser-only artifact may be approved
independently — no image model, no summary model, no analysis model, no completed four-model
pipeline.

Approval records at least: artifact identity; filing identity; source hash; parser model identity
and version; prompt version; processing settings; reviewer identity; review timestamp; approval
status; review comments; known limitations; validation results.

## Durable storage and the 24-hour cache

Only after explicit approval may an artifact become eligible for reusable product storage:

```
persistent      the approved durable artifact store — AUTHORITATIVE for derived product results
object storage  for large exact responses
Redis           a reusable cache entry with a 24-HOUR TTL
```

**Redis is not the authoritative store. It is a 24-hour acceleration layer.** The persistent
artifact remains authoritative. `rules.md` invariant 8: never store authoritative data only in
Redis.

## Lookup order, once the user enables reuse

```
1  check Redis for an exact approved reusable artifact
2  if absent, check persistent approved-artifact storage
3  validate the reuse key
4  serve the approved artifact when valid
5  populate Redis with a 24-hour TTL
6  invoke the parser only when no valid approved artifact exists, or the user explicitly reruns
```

**Before the gate is switched on:** searches do not treat evaluation responses as reusable trusted
results; evaluation responses may still be opened by run ID for review; a new search creates new
evaluation work unless the user explicitly reopens an existing run.

## Reuse identity

A reusable artifact must match at least: filing identity; exact source hash; parsing model
identity; parsing model version; prompt version; parser settings; input-source-set identity;
multimodal or text-only path; image-workflow settings where relevant; status `APPROVED`; validation
policy version.

**Do not reuse when any required identity differs. Do not treat two versions of a model as
interchangeable. Do not treat two prompts as interchangeable.** Never reuse an evaluation,
rejected, superseded, invalidated or partially written artifact, one based on a different source
hash, or one created with incompatible processing settings.

## Run IDs and developer comments

**Every new search or session receives a visible, copyable PARENT RUN ID.** It stays visible in the
lower-left area of the UI, does not disappear when the left search panel collapses, and has a copy
control.

The parent run ID links: user request; entity; timeframe; child filing jobs; model selections;
prompt versions; source identities; raw artifacts; parsed artifacts; image artifacts; summary
artifacts; analysis/chat artifacts; validation results; costs; timing; errors; retries; review
states; developer comments; chat history. Each child filing job may also carry its own job ID; the
parent remains the main human-facing reference.

**Granular developer comments**, stored with the run logs, on: the whole run; an individual filing;
a child filing job; a parsed section; a parsed subsection; a table; a footnote; a source reference;
the full parser response; the image-analysis response; a summary; a summary section; a complete
analysis/chat response; an individual chat message; a validation warning; an error or retry event.

Each comment records: comment ID; parent run ID; child job ID when applicable; target artifact or
message identity; target artifact VERSION; author identity; timestamp; comment text; resolution
status; optional tags, severity and reviewer assignment.

Comments stay associated with run logs for prompt refinement, model comparison, accuracy
evaluation, UI improvement, failure analysis, fine-tuning research and approval-policy design.

---

# PHASE 5 — BACKGROUND POPULATION (needs separate authorization)

**Not started in cleanup, and not started in Phase 4.** Long-running population becomes available
only after ALL of:

```
1  one or more parser configurations have demonstrated acceptable accuracy
2  the user explicitly authorizes keeping and reusing approved responses
3  the relevant prompt / model / settings combination is identified
4  the persistence system exists
5  retry, cost, rate, status and invalidation controls exist
6  a SEPARATE authorization is given for the backfill
```

The background process must work incrementally; resume safely; avoid duplicate work; check raw
source storage first and approved parsed storage second; record parent batch and child filing jobs;
respect cost ceilings and concurrency limits; preserve exact request and response artifacts; and
**never promote a failed or unreviewed response automatically** unless a later, separately
approved, automated-validation policy allows it.

**One approved filing does not approve every filing from that parser. A parser model is never
approved without its prompt and its settings.** The bulk-approval policy is a later user decision.

---

# PHASE 6 — FUNCTIONAL BETA UI

## End-to-end behaviour

For `Analyze AAPL for the past five years` the system must:

```
 1 resolve the entity using stable SEC identity
 2 determine the requested date boundaries
 3 query the local filing catalog
 4 identify every qualifying substantive 10-K/10-Q-family filing in range
 5 apply the approved amendment-selection policy
 6 create ONE parent run ID
 7 create ONE child filing job per filing
 8 check local durable source storage BEFORE contacting SEC
 9 reuse valid byte-exact originals already stored
10 fetch only missing, incomplete or hash-invalid source
11 preserve newly fetched source byte-for-byte
12 hash and provenance-stamp every original
13 determine the complete relevant human-readable source set MECHANICALLY
14 determine selected-model compatibility
15 send EACH FILING INDIVIDUALLY to the parsing model
16 receive an elastic parsed response
17 optionally execute image analysis
18 optionally execute summary generation
19 optionally create analysis/chat capability
20 show filing-level results
21 show a consolidated parent-run experience
22 reuse eligible approved artifacts when exact reuse conditions match
23 process only missing, rejected, invalidated, superseded or incompatible artifacts
```

**A multi-year request never concatenates filings into one parser invocation.** Each filing is a
separate parser job under one parent run.

## The entity catalog

Search suggestions come from the product's OWN catalog of entities with qualifying
10-K/10-Q-family filings. **An entity with no qualifying substantive filing never appears.**

Search supports: current ticker; historical ticker where authoritative evidence exists; current
company name; historical company name; SEC filer name; known aliases.

**NO FABRICATED HISTORICAL TICKER DATA.** Absent evidence is recorded as absent; a plausible
reconstruction is not an observation. Corpus evidence: 48 of 112 issuers have recorded former
names, 68 have no current ticker in the submissions API at all, and four report three or more
concurrent tickers.

**The catalog is ADDITIVE.** Scheduled synchronization adds newly qualifying entities and filings
without replacing or deleting the existing catalog wholesale.

## Timeframe

Bounded below by the entity's earliest known qualifying filing — the control cannot offer a range
the product cannot serve. It resolves qualifying filings in the selected range, clearly shows how
many filings will be processed, and handles annual, quarterly, transition, small-business, Item-405
and amendment forms per the approved selection policy.

## Layout

A persistent vertical **left search panel**: entity/ticker search; timeframe; parsing-model
selector; image-model selector; summary-model selector; analysis/chat-model selector; Search/Run
button. It can collapse, has a visible collapse arrow, reopens with a hamburger control, and
**does not destroy the current run state when collapsed.**

The **Search/Run button** is opaque-ish or semi-transparent light blue, never a harsh solid block;
disabled until the required parsing model and entity/timeframe inputs are valid; and accompanied by
a cost or compatibility warning when known.

**Visual style:** light mode; light and dark grey primary surfaces; dark grey menus and tables; soft
translucent blue and green accents; no fully saturated large colour blocks; the dashboard filling
the viewport to the right of the search panel.

## Minimum authentication — a prerequisite to binding beyond loopback

```
localhost-only operation until authentication is enabled    NO unauthenticated LAN exposure
server-side sessions                                        secure cookie behaviour where applicable
CSRF protection for state-changing browser requests         no provider credentials in the browser
no browser-to-Bedrock path                                  configurable bind address
```

Full multi-user identity management may remain deferred. Binding beyond loopback without the list
above may not.

---

# PHASE 7 — DEEP DIVE

The analysis/chat workflow uses the selected analysis model; works with or without a summary;
accesses original evidence, the accepted parse, image artifacts and the summary when present;
preserves message-level lineage; and supports comments on individual responses. Scope is immutable
after creation and loaded server-side from an immutable session record, never from the request
body.

# PHASE 8 — BREADTH AND OPTIMIZATION

Final persistence tuning; derived indexes and search facets; optional deterministic fast paths
where the corpus shows they are safe; complete EDGAR-wide entity population; universe-scale alias
and name-history reconciliation; scheduled incremental synchronization with durable checkpoints;
amendment monitoring; newly qualifying issuer discovery; large-scale backfill.

---

## Intact-source policy — current authorized mode

CURRENT AUTHORIZED MODE: `INTACT_SOURCE_ONLY`.

The complete relevant human-readable source set goes to the model intact in one invocation, or the
filing/model pairing is INCOMPATIBLE and is refused with an explanation showing bytes, tokens, the
limit and the alternatives. Another model may be selected ONLY by the user.

```
no truncation                    no semantic slicing
no automatic model substitution  no silent fallback
no mechanical multipart          no visible-content projection
```

Lossless mechanical multipart, lossless reversible visible-content projection, and any hybrid are
**unapproved research options requiring separate explicit user approval**. A lower token cost is not
authorization. They must be revisited if Phase 2 shows intact submission is unaffordable at useful
breadth.

---

## Risks Register

| ID | Risk | Severity | Status |
|---|---|---|---|
| R-20 | Intact submission is unaffordable or impossible for a large fraction of filings. Dated Phase 0 evidence: 44% of primary documents exceed ~200k estimated tokens, 12% exceed ~1M | HIGH | OPEN. Phase 1 measures real limits; Phase 2 measures cost. The no-slicing policy makes it a visible failure, not a silent truncation |
| R-21 | No candidate model accepts a materially sized modern filing intact | HIGH | OPEN. Phase 2 |
| R-22 | The five candidate LABELS have not been mapped to verified model IDs, versions, regions, modalities, limits or prices | HIGH | CLOSED 2026-08-03. All five mapped uniquely, reached, and recorded in `docs/llm/bedrock-capability-snapshot.yaml`. The snapshot goes stale silently, which is R-33 |
| R-23 | Model parse output varies between reruns, weakening the completeness guarantee | HIGH | OPEN. Repeat-run variability is a measured Phase 2 output; artifacts are versioned and superseded, never overwritten |
| R-24 | Token estimates are a character ratio, unfit for a compatibility gate | MEDIUM | OPEN. Bedrock returns exact usage per invocation, so Phase 2 measures rather than estimates; the pre-spend guard is still a character ratio and remains an upper bound, not a count |
| R-33 | The capability snapshot goes stale silently. Nothing in the repository can detect that a provider changed a price, moved a model between regions or retired a version | MEDIUM | OPEN. Mitigated by the date carried onto every record, the runbook that regenerates it, and the rule that it is replaced wholesale. Re-run before any Phase 2 cost commitment |
| R-34 | Phase 1 discovery ran under a broad administrator role, which the security policy permits for one-time manual discovery but not for a durable path | MEDIUM | OPEN. A least-privilege Bedrock policy is required before any repeatable or automated invocation. No CI job holds an AWS role. ADR-0018 section 7 |
| R-25 | Pre-2001 filing components are not individually addressable through EDGAR; the complete-submission text may be the only retrievable artifact, so the input contract must not assume a per-document URL | MEDIUM | Measured. Design constraint, not a defect |
| R-26 | Malformed markup is normal before 2005 | MEDIUM | Measured. Transport tolerance required |
| R-27 | Corpus form-family coverage | HIGH | CLOSED. All 22 reviewed direct substantive form strings represented and reverified 2026-08-03 |
| R-28 | SEC identification must be validated before every acquisition run. The monitored contact stays outside tracked source | MEDIUM | OPEN, operational. Enforced at startup by configuration validation |
| R-30 | Uniqueness rules keyed on accession alone reject valid EDGAR co-registrations | MEDIUM | CLOSED. Key is `(cik, accession)`; ownership verified from the archive path |
| R-31 | A guessed form allowlist in runtime code contradicts the reviewed contract, and a reconciliation sharing the same filter cannot see it | HIGH | CLOSED 2026-08-03. The qualifying set is a required argument with no default; an architecture test fails on a form literal in runtime source. ADR-0017 section 8 |
| R-32 | Capability lost to the cleanup — no local numeric evidence, no filed-document lister — is not rebuilt because nothing tracks it | MEDIUM | OPEN. The lister is Phase 2a; numeric cross-checking is reconsidered on measured need |
| R-09 | Unit economics unknown | HIGH | OPEN. Phase 2 produces the first measured figure |

---

## Deferred Work

| ID | Item | Revisit |
|---|---|---|
| D-20 | Final persistent artifact schema | Phase 4, from measured artifacts |
| D-21 | Redis data model, 24-hour approved-artifact cache | Phase 4 |
| D-22 | Entity-catalog scheduler and universe-scale expansion | Phase 8. The working catalog is Phase 6 |
| D-23 | Parquet and DuckDB serving (ADR-0002) | Phase 8, reconsidered rather than assumed |
| D-24 | pgvector retrieval (ADR-0007) | Phase 8, reconsidered rather than assumed |
| D-25 | Terraform and ECS (ADR-0008, ADR-0009) | after the beta runs on LAN |
| D-26 | Local numeric cross-checking of model-returned values | on measured need. ADR-0017 section 6 |
| D-01 | Form types beyond the 10-K and 10-Q families | after the beta |
| D-05 | FULL multi-user identity management (ADR-0014) | after the beta. The MINIMUM authentication before binding beyond loopback is Phase 6 work |

---

## Known Limitations

1. No model has ever been invoked by this project. Every cost figure is a placeholder.
2. The corpus is 613 filings out of millions. It is representative by construction, not complete.
3. Token counts throughout are character-ratio estimates, explicitly labelled as such.
4. Structured numeric history remains XBRL-bound and effectively complete only from 2011 — and
   there is now no local numeric evidence at all, by decision.
5. No application database, no persistence and no migration exist. PostgreSQL remains installed on
   the development host with two unused disposable databases, `fintek_test` and
   `fintek_integration_test`. Nothing in this repository can reach them.
6. `packages/configuration` and `packages/observability` have no non-test caller. They are the
   designated homes for startup validation and structured logging and are wired in Phase 2.
7. Filing acquisition is implemented for the inline-XBRL era only. The other five transport eras
   have no acquisition path.
8. `packages/model_catalog` is half of its eventual self. The capability record, label mapping,
   price inputs and cost ceiling exist; the four-role router is Phase 2.
9. The capability snapshot is dated evidence and goes stale silently. Nothing in the repository can
   detect that a provider changed a price or moved a model. R-33.
10. Only the standard on-demand price tier is recorded. Flex, priority and batch tiers exist and are
    not authorized; recording an unauthorized cheaper tier would understate cost.

---

## Completed History

Sprints 1 through 4 and Phase 1 are recorded in `docs/sprints/`. They remain historically accurate
and are not rewritten. What they built and what became of it:

- **Sprint 1** delivered the scaffold, governance, the SEC identity library, the SEC client
  foundation with rate limiting and throttle classification, configuration and User-Agent
  validation, object storage with hashing, the observability foundation, and the LLM content
  boundary. **All retained.** Its DERA link discovery and mirror ledger are deleted.
- **Sprint 2** mirrored all 78 DERA packages, built the SEC HTTP client, added the 24-table
  PostgreSQL control-plane schema, and fixed an unbounded YAML alias expansion vulnerability. **The
  HTTP client and the YAML fix are retained; the schema and the DERA code are deleted.** The
  mirrored data is untouched on disk.
- **Sprint 3** discovered 134 Apple filings back to 1994 and preserved five with SHA-256
  provenance. **The preserved fixtures are retained and hash-verified.**
- **Sprint 4** built the deterministic footnote pipeline: 43 canonical footnotes across four Apple
  filings, 117 of 117 child blocks attached, zero orphans. **The measurement stands. The
  implementation is deleted** — see ADR-0016 for why it was withdrawn and ADR-0017 for why it was
  not preserved as an oracle.
- **Phase 1** verified secure AWS identity and mapped all five approved candidate LABELS to real
  provider models, reaching every one of them for the first time in the project's history — seven
  minimal invocations, USD 0.00023, no SEC content. **The evidence is
  `docs/llm/bedrock-capability-snapshot.yaml`; the reader is `packages/model_catalog`.** See
  ADR-0018 for why the durable output is a dated snapshot rather than a provider adapter.
