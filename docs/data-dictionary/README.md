# Data Dictionary

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 1 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The product is an orchestrator-driven, model-first SEC filing product: the backend acquires,
> preserves, transports, orchestrates and VALIDATES; a user-selected parsing model determines what
> a filing means. The user selects four models independently — parsing, image, summary, and
> analysis/chat. The current authorized input mode is `INTACT_SOURCE_ONLY`. The deterministic
> content ontology, migration `0003` and the local application database are withdrawn. Sections
> below that describe the withdrawn design are historical.
>
> **UPDATED 2026-08-03 — the withdrawal is now complete (ADR-0017).** `packages/persistence`, the
> 24-table ORM schema, revisions `0001_initial` and `0002_table_ownership`, and the DERA fact
> loader were DELETED from the active tree. **No application database exists and nothing in this
> file describes a table, column, index, constraint or migration that exists anywhere.**
> Authoritative: `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.
>
> **FORWARD NOTE, 2026-08-03 (Phase 2) — the line immediately above is superseded in exactly one
> respect.** Phase 1 reached the approved candidates through a live provider API, and Phase 2
> IMPLEMENTED the Bedrock adapter, the four-role router, the orchestrator, the coverage validator
> and the parser-review UI, so "no model has been invoked and AWS is not configured" no longer
> describes this repository. **Nothing else in that paragraph changes. There is still no
> application database, no ORM, no migration, no index and no product schema.** Phase 2 writes
> EVALUATION records into a gitignored local directory instead; they have their own section below,
> and rules.md invariant 15 is the reason the two are not the same thing.

---

# ARCHITECTURAL VOCABULARY — AUTHORITATIVE. This section, and only this section, is current.

**THIS IS NOT A SCHEMA.** No table definition here is current, and the persistence representation
is **DEFERRED to Phase 4**, after real parsed artifacts from real models over materially different
corpus samples exist. Designing tables before seeing model output is exactly what produced the
withdrawn migration `0003`.

**Rigid semantic categories are removed from the mandatory vocabulary.** There is no required
content-unit type, no required hierarchy, and no enum of filing sections. Terms like MD&A, Item 7,
Part I, Footnote, Certification or Signature may appear as filing-native labels, model annotations,
optional derived indexes or search facets. They are not vocabulary the system requires.

## The terms

| Term | Meaning |
|---|---|
| **Entity** | An SEC filer. Identity is the CIK. Names and tickers are temporal aliases. |
| **Filing** | One submission. Identity is `(CIK, accession)` — never the accession alone, because co-registration puts one submission under two filer CIKs. |
| **Source artifact** | An original SEC document, preserved byte-for-byte with its SHA-256 and provenance. Authoritative. Never replaced by anything derived. |
| **Processing job** | One authorized unit of work over an entity, a timeframe and four model selections. Durable and resumable. |
| **Model role** | One of exactly four: parsing, image, summary, analysis/chat. **Only parsing is required**; the other three may be left blank and the run is still complete. |
| **Model selection** | The user's explicit choice of a model for one role on one job. No role inherits another's, and an unselected role is never silently filled. |
| **Model invocation** | One call to one provider. Records tokens, cost, latency, prompt version, model id, and the object-storage URIs of the exact request and response bodies. |
| **Artifact** | Anything a model produced that the system keeps. Never confused with the source. |
| **Artifact version** | Artifacts are superseded, never overwritten. |
| **Artifact lineage** | What produced this artifact, from what, with which prompt, superseding what. |
| **Parsed artifact** | The accepted output of the parsing model. Deliberately loosely typed. |
| **Summary artifact** | A separate artifact grounded in an accepted parse. Regenerating it does not require reparsing. |
| **Image-analysis artifact** | Produced by the image model, only when the parsing model is text-only. Linked to its source object. |
| **Chat artifact** | A Deep Dive turn: question, answer, citations, cost, bound to an immutable scope. |
| **Source reference** | A byte range in a preserved original artifact. Validation resolves it there, not in the parse. |
| **Validation result** | The backend's independent proof of coverage, citations and numbers against preserved bytes. `COMPLETE`, `PARTIAL` or `REVIEW_REQUIRED`. |
| **Cost record** | Tokens, amount, currency, latency, and whether the figures are measured or estimated. |
| **Cache record** | A reusable accepted result, keyed by what actually determines it. |

## What the vocabulary deliberately omits

No content-unit type. No section kind. No universal hierarchy. No proxy-topic mapping. No
disposition enum describing one interpretation of every filing.

A parsed node carries: an id, an order, an optional parent, an optional filing-native label, an
optional open-ended content type, text, source references, confidence, ambiguity, and an explicit
unresolved flag. Its shape is in `docs/api/openapi.yaml` as `ParsedNode`, and it is
`additionalProperties: true` on purpose.

## The one semantic guarantee that survives

Every financial-statement footnote **the accepted parse identifies** remains an independent node
and an independent required summary target. That is a completeness guarantee about not merging
content away. It is not a taxonomy, and the backend does not decide what a footnote is.

---

# PHASE 2 EVALUATION-RUN RECORDS — IMPLEMENTED 2026-08-03. Ignored local storage, NOT a product schema.

**READ THIS BEFORE ANY TABLE IN THIS SECTION.** Everything described here is an EVALUATION record
written into the gitignored directory `var/evaluation-runs/`, so that the first parser experiments
can be started, watched, reviewed and re-read after a page reload. **It is not the product
database, and the fact that it exists is not permission to design one.** There is no schema, no
ORM, no migration, no index, no query language, no Redis and no relational model anywhere in it —
a run directory, a job directory, some exact bytes and a few small manifests.

rules.md invariant 15 is the reason: **never design persistence ahead of measured model output.**
Schema follows accepted artifacts and artifacts follow real experiments, so `roadmap.md` Phase 4
designs the product's persistence FROM measured artifacts that will by then exist. Designing tables
before seeing model output is exactly what produced the withdrawn migration `0003` recorded further
down this file. The ARCHITECTURAL VOCABULARY section above remains the authoritative vocabulary;
what follows is the shape the evaluation harness writes TODAY, and no field below is a forward
commitment to a column.

**No measurement is reproduced in this document.** These records are where the first measured token
counts, latencies, stop reasons, resolution rates and dollar amounts land. Reading a figure out of
them and copying it here would create a second, staler home for it. Every per-model capability fact
— identifier, region, context limit, output limit, price — lives in exactly one file,
`docs/llm/bedrock-capability-snapshot.yaml`, and only `packages/model_catalog` reads it. A
capability recorded twice drifts.

**The store carries no opinion about what a filing contains.** `packages/evaluation_store` holds a
source set, a validation result and an image-coverage report as OPAQUE mappings produced by the
packages that own those concepts, and never reads inside them. That is rules.md invariant 14
applied to storage: a store that understood source sets would eventually start deciding which
members mattered.

## Where the records live

The root defaults to `./var/evaluation-runs` and is supplied by `packages/configuration`
(`EVALUATION_ROOT`). Every write goes through `packages/storage`, which writes to a temporary path,
flushes, fsyncs, renames, and refuses a key that escapes the store root — so a reader never sees a
half-written manifest.

| Key | Record |
|---|---|
| `spend-journal.yaml` | The cumulative spend journal for the whole store, not for one run |
| `runs/<run_id>/run.yaml` | The parent run manifest |
| `runs/<run_id>/events/<00000001>.txt` | One immutable object per progress event |
| `runs/<run_id>/comments/<comment_id>.yaml` | One developer evaluation comment |
| `runs/<run_id>/jobs/<job_id>/job.yaml` | One child filing job |
| `runs/<run_id>/jobs/<job_id>/evidence/<name>` | Exact bytes: request, response, prompt, source |

**One object per event, rather than appended lines.** An append to a shared log is not atomic
across a crash, and a torn last line is indistinguishable from an event that never happened. One
object per event makes every write atomic and makes `Last-Event-ID` resumption a matter of listing
keys. Runs carry tens of events, not millions.

### Evidence file names, fixed so a reviewer finds the same names every time

```
prompt.txt                the exact prompt text, by version, from packages/prompt_registry
request-instruction.txt   the compiled model-visible instruction
request-transport.json    the provider request envelope, written only when the adapter returns one
response-visible.txt      the model's visible answer text, exactly as returned
response-reasoning.txt    reasoning content, separated from the answer; written only when present
response-transport.json   the provider response envelope
source-NN.txt / .bin      the exact bytes of each submitted member, in submission order
source-set.yaml           the source-set manifest
validation.yaml           the validation result
```

Bytes are stored EXACTLY. Nothing decodes, re-encodes, pretty-prints or normalises evidence; its
whole value is that it is what actually crossed the wire. The two `.json` files are the
provider-required API transport envelope, which `docs/llm/content-boundary.md` permits for that one
purpose; nothing model-visible is JSON in either direction.

## Identifiers

| Identifier | Format | Notes |
|---|---|---|
| Run id | `run_` + 26 lowercase base32 characters | 16 random bytes, 128 bits |
| Job id | `job_` + 26 lowercase base32 characters | |
| Comment id | `cmt_` + 26 lowercase base32 characters | |
| Event id | 8-digit zero-padded sequence, e.g. `00000007` | Per run; `Last-Event-ID` replays after it |
| Source-set id | SHA-256 of the ordered `filename:sha256` lines of the SUBMITTED members | |

An identifier carries **no** account id, CIK, ticker, model id, email, username, timestamp or
counter. A run id is quoted in a bug report and pasted into a chat window, and anything encoded in
it is disclosed with it. `packages/evaluation_store.identity` validates every identifier before it
reaches a storage key, so `..` and `/` fail there rather than relying on the object store's
traversal guard as the only line of defence.

The source-set id is a hash of hashes because "the same accession" is not "the same source set": a
member fetched later, a member that failed to fetch, or a differently dispositioned member all
produce a different set from the same accession, and one value has to make that visible.

## Serialisation conventions

| Convention | Rule |
|---|---|
| Record format | One unfenced YAML 1.2 document per record, written by `packages/llm_gateway.to_yaml` |
| Money | Exact decimal TEXT, read back through `Decimal`. A float round-trip through YAML turns `0.00015` into `0.000149999999999999993145` |
| Identifiers | Always quoted on the way out. YAML 1.2 parses an unquoted `0000320193` as the integer `320193` and destroys a CIK |
| Timestamps | ISO-8601 UTC strings, so every record is comparable as text |
| Versioning | A `schema_version` string on each manifest: `evaluation-run-v1`, `evaluation-job-v1`, `source-set-v1`, `validation-v1`, `spend-journal-v1` |
| Events | Tab-separated, four fields, with backslash, tab and newline escaped — deliberately neither YAML nor JSON |

The event wire format is not YAML because an event is re-read by a server-sent-events handler on
every reconnect and a format needing a parser with an alias budget to read four fields is the wrong
tool. It is not JSON because the repository has one browser-facing serialisation and one
model-facing one, and a third would be a third thing to keep honest.

## Parent run — `run.yaml`, `evaluation-run-v1`

One user request, one visible identifier, N child filing jobs. `packages/evaluation_store.records.RunRecord`.

| Field | Meaning |
|---|---|
| `schema_version` | `evaluation-run-v1` |
| `run_id` | The opaque parent identifier |
| `created_at` | ISO-8601 UTC |
| `author` | Who asked for the run |
| `cik` | The issuer, quoted |
| `entity_label` | The issuer name as displayed. A temporal alias, never identity |
| `selections.parsing` | The user's parsing-model LABEL. Always present |
| `selections.image` | The image-model label, or null |
| `selections.summary` | The summary-model label, or null |
| `selections.analysis` | The analysis/chat-model label, or null |
| `timeframe.from` / `.to` | The requested filing window, either may be null |
| `preferred_region` | The region the user preferred, supplied by configuration; routing may DISCLOSE a different one per role |
| `cost_ceiling_usd` | Decimal text. The authorized ceiling for this run |
| `job_ids` | The child filing jobs this run created |
| `closed_at` | Set when the run is closed, else null |
| `note` | Free text from the author |

**A blank role is a value, not an absent key.** `selections` always carries all four roles, with
null for a role the user left blank. Writing the parsing model into an empty summary slot is the
silent substitution rules.md section 21 rule 8 forbids, and it would be invisible afterwards if the
record could not represent "the user chose nothing". A parser-only run is complete and valid.
`selected_roles` is DERIVED from which labels are non-null, never stored.

**Phase 2 executes the parsing stage only.** All four roles are routed, and invoking the image,
summary or analysis stage raises `StageNotAuthorizedError`. No summary model, no analysis/chat
model and no separate image model has been invoked. That is a status, not a design: those stages
are PLANNED for the optional-model phases in `roadmap.md`.

## Child filing job — `job.yaml`, `evaluation-job-v1`

One filing, one parsing model, one independent unit of billable work. A multi-year request never
becomes one invocation. `packages/evaluation_store.records.JobRecord`.

| Field | Meaning |
|---|---|
| `schema_version` | `evaluation-job-v1` |
| `job_id` / `parent_run_id` | Identity, and the run it belongs to |
| `created_at` / `updated_at` | `updated_at` is rewritten on every save |
| `filing.cik` | Quoted CIK. Filing identity is `(CIK, accession)`, never the accession alone |
| `filing.accession` | Dashed accession |
| `filing.form_as_filed` | The filer's own form string, verbatim and never normalised |
| `filing.filing_date` | As filed |
| `filing.report_period` | The period the filing reports on, or null |
| `filing.issuer_label` | Display name at the time of the run |
| `filing.transport_era` | Which of the measured transport eras this filing belongs to |
| `model_routing` | The routing sub-record below |
| `prompt` | The prompt-identity sub-record below |
| `settings` | The parser-settings sub-record below |
| `execution_state` | One of the twelve execution states |
| `review_state` | One of the six review states |
| `source_set_id` | The hash-of-hashes identity of exactly these submitted bytes |
| `source_set` | The source-set manifest, stored OPAQUELY. Owned by `packages/source_transport` |
| `validation` | The validation result, stored OPAQUELY. Owned by `packages/coverage_validation` |
| `image_coverage` | The image-coverage report, stored OPAQUELY |
| `incompatibility` | Why this filing and this model cannot be paired, or null |
| `attempts` | Every billable attempt, in order, successes and failures alike |
| `review_history` | Appended review transitions, never rewritten |
| `reserved_cost_usd` | Decimal text. The worst-case bound charged BEFORE the call |
| `actual_cost_usd` | Decimal text. The measured cost, once usage came back |
| `estimated_input_tokens` | The pre-spend character-ratio ESTIMATE, not a tokenizer count |
| `failure` | Why the job failed, or null |

### `model_routing`

Exactly which model was invoked, where, and whether that was the preferred region.

| Field | Meaning |
|---|---|
| `label` | The user-facing model label |
| `role` | `parsing`, `image`, `summary` or `analysis` |
| `model_id` | The provider model identifier, resolved from the reviewed capability snapshot |
| `invocation_id` | What is actually invoked — the model id, or its inference profile |
| `region` | The region this invocation ran in |
| `preferred_region` | The region the run asked for |
| `in_preferred_region` | Whether the two agree |
| `inference_profile_id` | Set when the model requires an inference profile, else null |
| `cross_region_reason` | A sentence explaining a cross-region route, else null |
| `multimodal` | Whether this model has a verified image path |

**A cross-region route is DISCLOSED, never silent.** The product is explicitly allowed to run
different models in different regions; it is not allowed to do so quietly. `in_preferred_region`
and `cross_region_reason` carry that fact into the run plan, the child job, the request evidence,
the response evidence, the cost record and the artifact lineage. Every value these fields can hold
is DERIVED from `docs/llm/bedrock-capability-snapshot.yaml`; none is written here, and none is
written in `packages/model_catalog/routing.py` either.

### `prompt`

| Field | Meaning |
|---|---|
| `prompt_id` | The registered prompt |
| `version` | The exact version invoked |
| `sha256` | The hash of the prompt bytes |

The hash rather than the text: the text is also written beside the request evidence, and a second
copy is the one that drifts. `packages/prompt_registry` re-hashes the file on load and refuses it
when the bytes have moved from what its manifest recorded, so editing an in-use prompt version
fails at load, in the test suite and in CI — rather than quietly changing what stored invocations
claim to have asked.

### `settings`

| Field | Meaning |
|---|---|
| `max_output_tokens` | The output budget requested for this parse |
| `temperature` | The sampling temperature requested |

These are the request settings that change what comes back, and therefore change reuse identity.

### `incompatibility`

| Field | Meaning |
|---|---|
| `reason` | A short machine-readable reason, e.g. `unknown_member_role`, `source_set_exceeds_context` |
| `detail` | The full sentence a user reads, with the arithmetic in it |
| `source_set_bytes` | Bytes in the submitted set, or null |
| `estimated_input_tokens` | The pre-spend estimate, or null |
| `model_context_tokens` | The verified context limit this was measured against, or null |

"Incompatible" on its own sends a user to a support channel. Every field exists so the UI can say
which limit was exceeded and by how much, and so the USER — never the backend — picks a different
model. `INTACT_SOURCE_ONLY` is the authorized mode: nothing is truncated, sliced, projected, split
into parts or swapped to another model, so incompatibility is a RESULT.

## Execution and review — two independent state machines

They are never collapsed. An execution state describes machinery; a review state describes a human
judgement. Deriving one from the other is how an unreviewed artifact acquires the authority of an
approved one. A job reaching `READY_FOR_REVIEW` says only that a person can now look at it.

```
execution   CREATED  SOURCE_READY  PREFLIGHT  QUEUED  RUNNING  RESPONSE_RECEIVED  VALIDATING
            READY_FOR_REVIEW  FAILED  INCOMPATIBLE  INTERRUPTED  CANCELLED

review      EVALUATION  UNDER_REVIEW  APPROVED  REJECTED  SUPERSEDED  INVALIDATED
```

Transitions are enumerated in one table in `packages/evaluation_store/states.py` rather than
checked ad hoc, because a table can be read, tested exhaustively and extended in one place. Four
consequences are worth stating here, each of which the table makes unrepresentable rather than
merely tested for:

| Rule | Why |
|---|---|
| `RUNNING` may not go to `CANCELLED` | A provider call already issued is billable whatever the browser does next. It becomes `INTERRUPTED` or it completes |
| `VALIDATING` never goes to `FAILED` for a validation VERDICT | A parse that fails coverage or returns unparseable YAML still reaches `READY_FOR_REVIEW` carrying that verdict; the response was bought and a person has to see it. `FAILED` here means validation itself broke |
| `APPROVED` is never edited back to unapproved | It is `SUPERSEDED` by a newer artifact or `INVALIDATED`, both of which leave the original readable — rules.md invariant 7 |
| Every mid-flight state becomes `INTERRUPTED` on restart | Nothing is re-invoked. A rerun spends money, and money is never spent by a process that merely came back up |

`EVALUATION` is the state every artifact starts in and stays in until someone acts. **Nothing in
this project treats an `EVALUATION` artifact as a reusable result.** `APPROVED` starts to mean
something operational at `roadmap.md` Phase 4; that gate is PLANNED and is not switched on.

## Source set and member disposition — `source-set.yaml`, `source-set-v1`

Every filed member of one accession, dispositioned, with the subset actually submitted.
`packages/source_transport.records.SourceSet`. Every record here is TRANSPORT: bytes, a hash, a
size, an encoding, a declared type the filer typed, and a disposition with the evidence behind it.
None of it says what a member MEANS.

| Field | Meaning |
|---|---|
| `schema_version` | `source-set-v1` |
| `cik`, `accession`, `form_as_filed`, `filing_date`, `report_period`, `issuer_label`, `transport_era` | Filing identity and era, carried verbatim |
| `source_set_id` | SHA-256 over the ordered `filename:sha256` lines of the submitted members |
| `members_separately_addressable` | Whether EDGAR publishes a per-document URL for this accession's members. Decided by EDGAR, not by this system |
| `declared_document_count` | What the envelope's own `PUBLIC DOCUMENT COUNT` header claimed, or null |
| `listed_document_count` | How many `<DOCUMENT>` blocks were actually found |
| `counts_by_disposition` | A census of dispositions across all members |
| `submitted_member_count` | Members sent as their own content block |
| `submitted_bytes` | Bytes counted toward the request |
| `total_bytes` | Bytes across all members, submitted or not |
| `reused_members` / `fetched_members` | Local-first reuse versus a fetch from SEC |
| `members` | Every filed member, below |

`declared_document_count` and `listed_document_count` are REPORTED, never reconciled. A dated
Phase 2 measurement found an envelope whose header said one number while the envelope contained
another, with non-contiguous sequence numbers; picking a winner in code would hide the disagreement
that a reviewer needs to see.

### One member

| Field | Meaning |
|---|---|
| `sequence` | The filer's declared document sequence, or null when the era published none |
| `declared_type` | The filer's own string, verbatim and never normalised, mapped or interpreted |
| `description` | EDGAR's declared description, read verbatim |
| `filename` | Empty when the era published none, which means the member has no individual EDGAR URL |
| `disposition` | One of the seven below |
| `disposition_evidence` | The exact byte signature, extension or declared field that produced the disposition — shown so a person sees the evidence rather than a category |
| `sha256` | Of the preserved bytes |
| `byte_count` | Of the preserved bytes |
| `source_url` | Where it came from |
| `separately_addressable` | Whether EDGAR publishes a URL for this member |
| `reused` | Whether it was already preserved locally and verified, rather than fetched |
| `encoding` | The encoding it losslessly decoded from, or null |
| `image_format` | `png`, `jpeg`, `gif` — from the BYTE SIGNATURE, or null |
| `submitted` | DERIVED: sent as its own content block, and its bytes counted |
| `covered` | DERIVED: its content reaches the model at all, however it travels |
| `evidence_name` | Added by the orchestrator when it writes the manifest onto a job: which `source-NN` evidence file holds these exact bytes |

Member content is deliberately NOT serialised into the manifest. The bytes live in evidence under
their own hash; a manifest that inlined a multi-megabyte filing would be a second copy that can
drift from the first.

### The seven dispositions

| Disposition | Submitted | Covered | Meaning |
|---|---|---|---|
| `PARSER_INPUT_TEXT` | yes | yes | Human-readable filed text; goes to the parsing model intact |
| `PARSER_INPUT_IMAGE` | yes | yes | A filed raster image; goes to a MULTIMODAL parser intact, reported unanalysed otherwise. Never described, summarised or transcribed by backend code |
| `INSIDE_COMPLETE_SUBMISSION` | no | **yes** | The member has no individual EDGAR URL and reaches the model inside the complete submission, which is submitted intact. Its content is covered; its bytes are not counted twice |
| `MACHINE_ONLY` | no | no | An archive, spreadsheet, stylesheet, script, schema, or XBRL linkbase or instance — nothing a language model reads as prose |
| `SEC_GENERATED_RENDERING` | no | no | SEC's own renderer output, declared as such by EDGAR's `IDEA:` description marker |
| `DUPLICATE_COMPLETE_SUBMISSION` | no | no | The flat complete submission when its members are individually addressable and are being sent as themselves; sending both submits identical content twice |
| `UNKNOWN_REQUIRES_REVIEW` | no | no | Nothing matched. **Fails closed** into the run plan |

**Submitted and covered are kept apart deliberately.** Coverage is measured against the covered
set; request size is measured against the submitted set. Collapsing them makes a pre-2001 filing
either double-count its own bytes or report its own exhibits as uncovered.

**`uncovered_members` is the honest answer to "what was left out".** It is DERIVED, shown in the
run plan and in the parsed view, and a run never reports complete coverage while it is non-empty.

**An unknown role is not guessed in either direction.** A dropped member is lost content; a
submitted one may be an unusable binary charged as input tokens. The deleted accession classifier
(ADR-0017) chose in exactly this position, ruled that a courtesy PDF duplicated the primary
document, and suppressed a filed source range on that judgement.

### The acquisition record behind a member

`PreservedObject` is the result of finding or fetching one artifact. It is an in-memory record used
during assembly and is NOT serialised into the manifest; its durable half is the member row above.

| Field | Meaning |
|---|---|
| `filename`, `sha256`, `byte_count` | Identity of the exact bytes |
| `source_url` | Where it was fetched from; empty for a local hit |
| `locator` | Where the preserved copy lives |
| `acquired_at` | When, or empty for a local hit |
| `acquisition_method` | How it was obtained, e.g. `object_store` |
| `reused` | Whether it came from local preservation rather than SEC |

A reused object is verified before it is trusted: byte count and SHA-256 must both match the
record, or it is re-acquired rather than believed.

### `image_coverage`

| Field | Meaning |
|---|---|
| `image_member_count` | Image-bearing members in the source set |
| `analysed` | True only when images exist AND the parsing model is multimodal |
| `reason` | The sentence explaining which of those two it was |
| `members[]` | `filename`, `sha256`, `byte_count`, `image_format`, `submitted_to_parser` |

A text-only parser produces `analysed: false` with the affected documents NAMED. A run that quietly
omitted images while reporting a complete parse would have made a false completeness claim.

## Invocation attempt

One billable attempt against one model, whatever its outcome, appended to `attempts`.

| Field | Meaning |
|---|---|
| `attempt` | 1-based attempt number |
| `started_at` / `finished_at` | ISO-8601 UTC |
| `latency_ms` | Wall-clock milliseconds |
| `stop_reason` | The provider's stop reason, verbatim |
| `input_tokens` / `output_tokens` | The provider's MEASURED usage, not an estimate |
| `visible_characters` | Length of the visible answer text |
| `reasoning_characters` | Length of the separated reasoning content |
| `provider_request_id` | The provider's request identifier, or null |
| `error` | The failure, or null |
| `retryable` | Whether the failure was transient, or null |

**A FAILED attempt is recorded exactly as carefully as a successful one.** It was billable, it
consumed the retry budget, and a benchmark that quietly dropped failures would report a success
rate it never measured.

**Reasoning length is separate from visible length on purpose.** One candidate emits reasoning
content before its answer through the Converse path, and an output budget sized for the answer
alone returns a well-formed response with no text in it. Recording only the visible length would
make an exhausted budget look like an empty answer.

**`estimated_input_tokens` beside measured `input_tokens` is a measurement, not redundancy.** The
pre-spend guard is a character ratio and is an upper bound, not a count (risk R-24, OPEN). Keeping
both is how the size of that gap stops being a guess. **The first such comparisons live in these
records; no figure from them is reproduced in this document.**

## Validation result — `validation.yaml`, `validation-v1`

The backend's independent proof against the PRESERVED BYTES. Interpretation is the model's; proof
is the backend's. `packages/coverage_validation.validator`.

| Field | Meaning |
|---|---|
| `schema_version` | `validation-v1` |
| `status` | `REVIEW_REQUIRED`, `PARTIAL`, `UNPARSEABLE` or `EMPTY` |
| `status_note` | A carried sentence stating that COMPLETE is not a value this validator can issue |
| `findings` | The ordered sentences a reviewer should see first |
| `response_characters` / `source_characters` | Sizes of the response and of the concatenated submitted text |
| `source_to_response_ratio` | DERIVED, rounded to two places |
| `yaml_parsed` | Whether the response read as one YAML document |
| `boundary_ok` / `boundary_violations` | Whether the response honoured the LLM content boundary, and which rules it broke |
| `missing_envelope_keys` | Which PROVISIONAL envelope keys the response omitted |
| `node_count` / `table_count` | What the parse contains, counted generically |
| `reference_count` | Source references the model supplied |
| `references_resolved` / `references_ambiguous` / `references_unresolved` | How they landed against the preserved bytes |
| `resolution_breakdown` | A census keyed by resolution outcome |
| `artifacts_submitted` / `artifacts_referenced` | How many submitted artifacts carry a resolved reference |
| `artifacts_unreferenced` | The ones that carry none, by name |
| `declared_unresolved` | How many items the MODEL itself declared unresolved |
| `image_dependent_nodes` | Nodes the model marked as depending on an image |
| `model_selected_types` | A CENSUS of the `type` strings the model chose. Never a vocabulary |
| `numeric` | The numeric signals below |
| `references` | One row per reference, below |

**`ValidationStatus` has no `COMPLETE` member, deliberately.** The complete-content invariant asks
whether every human-readable source RANGE is represented. What this module can measure today is
whether every submitted ARTIFACT is cited, how many references resolve, and what the model itself
declared unresolved. Those are coverage SIGNALS, and rounding a set of signals up to a completeness
claim is precisely the false complete the invariant forbids. A status value that exists is a status
value something eventually sets, so it does not exist. Note that this differs from the `COMPLETE |
PARTIAL | REVIEW_REQUIRED` triple in the vocabulary table above: the vocabulary describes the
eventual product concept; this enum describes what is IMPLEMENTED and provable today.

**A failure here is a result, not an exception.** A response that will not parse still produces a
validation record, still reaches the review UI, and still shows its exact bytes. It was bought and
it cannot be regenerated for free.

**Validation never grades a parse against a second parse.** rules.md section 21 rule 15 withdrew
the deterministic Apple oracle for exactly that reason: grading a model against a deterministic
interpretation makes the deterministic interpretation authoritative again through the back door.
Everything compares the response to the SOURCE.

### One reference outcome

| Field | Meaning |
|---|---|
| `node_id` | The node whose claim this reference supports |
| `filename` | The artifact the quote was located in — not necessarily the one the model named |
| `quote` | Truncated to 200 characters FOR THE MANIFEST ONLY; the exact response beside it is authoritative |
| `resolution` | One of the seven below |
| `occurrences` | How many times the quote occurs |
| `offset` | Where it was found, or null |

```
EXACT                  character for character in the preserved bytes
WHITESPACE_NORMALISED  found once runs of whitespace collapse on both sides
TEXT_ONLY              found in the same bytes with markup tags removed
AMBIGUOUS              occurs too many times to locate anything in particular
UNRESOLVED             not found by any of the three searches
NO_SUCH_ARTIFACT       there were no artifacts to search
EMPTY_QUOTE            the model supplied no quote
```

The first three count as resolved. **Quotes, not offsets:** a model handed an artifact as text
cannot count bytes in it, and a fabricated offset resolves to the wrong place while looking exactly
like a real one. A quote either occurs in the preserved bytes or it does not.

**`AMBIGUOUS` is its own outcome, not a resolution.** A quote occurring everywhere locates nothing;
counting it as resolved would inflate the citation rate with references that point everywhere at
once.

The three searches are a SEARCH STRATEGY over preserved bytes, not a projection of the input.
Nothing about what is sent to a model changes; visible-content projection remains an unapproved
research option.

### `numeric` — signals, never verdicts

| Field | Meaning |
|---|---|
| `numbers_checked` | Numeric literals in the reported text, above a four-digit noise floor |
| `numbers_verbatim_in_source` | How many occur in the source, compared bare so `1,234` matches `1234` |
| `verbatim_rate` | DERIVED, rounded to four places |
| `formatted_numbers_checked` / `formatted_numbers_preserved` | Currency and percentage formatting carried through |
| `tables_checked` | Tables with rows |
| `tables_with_a_coherent_column` | Tables where one value equals the sum of the others in some column |
| `note` | A carried sentence stating that these are arithmetic observations only |

A coherent column is an ARITHMETIC OBSERVATION. This does not conclude that the row is a total,
does not look at row labels, and does not report an incoherent table as wrong — plenty of
legitimate tables have no total row. The count is a comparison signal between models on the same
filing, nothing more. Anything richer runs into rules.md invariant 14.

## Comment — `comments/<comment_id>.yaml`

One developer evaluation comment, bound to the artifact VERSION it targeted.

| Field | Meaning |
|---|---|
| `comment_id` | `cmt_` identifier |
| `parent_run_id` | The run it belongs to |
| `child_job_id` | The filing job, or null for a run-level comment |
| `target_type` | What kind of thing is being commented on |
| `target_id` | Which one |
| `target_version` | Which VERSION of it |
| `author` | Who wrote it |
| `created_at` | ISO-8601 UTC |
| `text` | The comment |
| `status` | Defaults to `OPEN` |
| `tags` | Free-form labels |

`target_version` matters: a comment written against attempt 1 does not silently become a comment
about attempt 2.

**Comments are DATA.** They are rendered as text and are never placed into any model-visible
content. A filing, and anything a reviewer writes beside it, is untrusted input to a model.

## Review transition — inside `job.yaml`

| Field | Meaning |
|---|---|
| `at` | ISO-8601 UTC |
| `author` | Who decided |
| `from_state` / `to_state` | The move, with the illegal ones already refused |
| `note` | Why, or null |

Appended, never rewritten. rules.md invariant 7 forbids overwriting an accepted decision, and a
review trail that can be edited is not a trail.

## Run event — `events/<sequence>.txt`

| Field | Meaning |
|---|---|
| `sequence` | Monotonic within the run; the filename carries it zero-padded to eight digits |
| `at` | ISO-8601 UTC |
| `kind` | e.g. `execution.running`, `review.approved`, `comment.added`, `invocation.recovered` |
| `job_id` | The child job, or empty for a run-level event |
| `message` | A short human sentence |

**No provider data and no filing text.** Filing text may be very large and may carry an instruction
a prompt injection placed inside a filing; provider payloads may carry request identifiers a
browser has no business seeing. Both go to the evaluation store and are REFERENCED from an event,
never streamed through one.

## Spend-journal entry — `spend-journal.yaml`, `spend-journal-v1`

Cumulative authorized spend, durable across restarts. `packages/orchestrator.spend_journal`.

| Document field | Meaning |
|---|---|
| `schema_version` | `spend-journal-v1` |
| `ceiling_usd` | Decimal text. The authorized CUMULATIVE ceiling |
| `spent_usd` | Decimal text. DERIVED as the sum of `amount_usd - released_usd`, rewritten on save |
| `entries` | Every reservation and settlement, in order |

| Entry field | Meaning |
|---|---|
| `at` | ISO-8601 UTC |
| `kind` | `RESERVATION` or `SETTLEMENT` |
| `run_id` / `job_id` | What the money was spent on |
| `model_label` | Which model, by LABEL |
| `amount_usd` | Decimal text. The worst-case bound on a reservation; the measured cost on a settlement |
| `released_usd` | Decimal text. Zero on a reservation; the reservation being replaced on a settlement |
| `note` | The token counts behind the amount, stated as bound or as measured |

**Why the in-memory ledger is not enough.** `packages/model_catalog.SpendLedger` bounds the worst
case of one invocation and reserves before the call, which is right and lives entirely in memory. A
ceiling that starts again at zero when the server restarts is not a ceiling; it is a per-process
suggestion. The authorized Phase 2 ceiling is CUMULATIVE, so the total has to outlive the process
that spent it. The journal is append-only and the total is recomputed from it at construction.

**Reserve before, settle after, and charge failures.** A reservation is charged immediately. A
billable request that fails still cost money, and a ledger that only charged successes would let a
run of rejections walk straight past the ceiling. A settlement records both the reservation it
replaces and the measured amount, so the arithmetic is auditable rather than merely stated.

**Refusal is refusal.** When the bound would push cumulative spend past the ceiling the invocation
is refused with the numbers in the message. Nothing is shrunk, dropped or downgraded to fit.

## What these records deliberately do not carry

No content-unit type. No section kind. No universal hierarchy. No filing taxonomy. No enum of
filing sections anywhere in `packages/coverage_validation` — `model_selected_types` is a census of
strings the model chose, and the elastic reader preserves every key it does not recognise in
`extra` rather than dropping it. The whole point of the first experiments is to find out what
models actually emit, and a reader that silently discarded the surprising half would guarantee the
surprise was never seen.

No table, column, index, constraint, foreign key or migration. No Redis. **No final persistence:**
it is PLANNED for `roadmap.md` Phase 4 and is DEFERRED until measured artifacts exist to design it
from.

---

# HISTORICAL — describes the withdrawn application schema, which was DELETED on 2026-08-03. No table below exists.

> **FORWARD NOTE, 2026-08-03 (Phase 2).** Phase 2 revived none of what follows. It built no
> database, no ORM, no migration, no index and no table; the evaluation records described in the
> section above are YAML manifests in a gitignored local directory and are explicitly not a schema.
> The record below stands unchanged as the reasoning behind a withdrawn design.

Everything from here to the end of the file is a **record of a design that was withdrawn**. It is
kept, not deleted, so the reasoning survives and is not re-derived — the mistake ADR-0016 and
ADR-0017 exist to stop repeating. Every table, column, constraint, index, migration, enum, status
value and file path below was deleted with `packages/persistence`, `migrations/` and
`packages/dera_notes` (ADR-0017). None of it exists, none of it is planned in this shape, and no
path named below is in the active tree.

IMPLEMENTATION STATUS: SUPERSEDED (by ADR-0017; the schema described below was deleted on
2026-08-03). Previously recorded as IMPLEMENTED in Sprint 2, with table-ownership columns in
Sprint 4.

24 domain tables were defined in `packages/persistence/models.py` with migrations `0001_initial`
and `0002_table_ownership`. A third revision, `0003_filing_content`, was designed and described
below but never committed.

---

## Complete filing content — migration `0003` (Sprint 4.1)

Decision: ADR-0016. WITHDRAWN — see the vocabulary section above. Retained here only as the
record of what migration `0003` would have encoded; it was never committed.

### `filing_content_unit`

One node in a filing's canonical content hierarchy: cover page through signatures and filed
exhibits.

| Column | Type | Null | Notes |
|---|---|---|---|
| `content_unit_id` | uuid | no | Primary key |
| `filing_id` | uuid | no | FK `filing`, cascade |
| `document_id` | uuid | yes | FK `filing_document`. Which filed document this came from |
| `parent_content_unit_id` | uuid | yes | FK self, cascade. NULL only on the filing root |
| `canonical_footnote_id` | uuid | yes | FK `canonical_footnote`. **Reference, never a copy** |
| `filing_section_id` | uuid | yes | FK `filing_section`, retained link to Sprint 4 sections |
| `unit_type` | text | no | Taxonomy below; check-constrained |
| `part_number` | text | yes | Roman numeral, e.g. `II` |
| `item_number` | text | yes | e.g. `1A`, `7A` |
| `title_as_displayed` | text | yes | Exactly as filed |
| `normalized_title` | text | yes | Lowercased, for comparison only |
| `sequence` | integer | no | Filed order among siblings |
| `hierarchy_path` | text | no | **Materialized path**; see semantics below |
| `text` | text | yes | Normalized prose. NULL on aggregates and footnote references |
| `source_char_start` / `_end` | integer | yes | Span in the filed document |
| `source_anchor` | text | yes | |
| `source_sha256` | text | yes | Hash of the RAW source span |
| `content_sha256` | text | yes | Hash of the NORMALIZED text. Two hashes distinguish a parser change from a filing change |
| `extraction_method` | text | yes | |
| `parser_version` | text | yes | |
| `confidence` | numeric(5,4) | yes | |
| `coverage_status` | text | no | `COVERED` \| `PARTIAL` \| `UNRESOLVED` \| `EXCLUDED` |
| `summary_required` | boolean | no | Set from unit TYPE and filed position, **never from materiality** |
| `incorporated_by_reference` | boolean | no | |
| `unit_metadata` | jsonb | yes | |

**Idempotency key**: `UNIQUE (filing_id, hierarchy_path)`.

**Constraints.** `content_unit_type_is_known`; `content_coverage_status_is_known`;
`content_unit_is_not_own_parent`; `footnote_reference_requires_footnote_type` — a
`canonical_footnote_id` is only valid on a `FINANCIAL_STATEMENT_FOOTNOTE` unit, so there is no
second path to footnote evidence; `footnote_unit_does_not_copy_text` — a footnote unit stores NULL
text, because two editable copies of one fact diverge and nothing notices.

### `hierarchy_path` — materialization semantics

Dotted zero-padded ordinals from the root: `001.002.007`. **Derived** from
`(parent_content_unit_id, sequence)` and rewritten by the same transaction that writes them.

Stored, rather than computed on read, for two reasons stated so it is not mistaken for a second
source of truth: `(parent_content_unit_id, sequence)` cannot serve as a unique constraint, because
a NULL parent never conflicts in one and two content roots would insert silently; and a stored path
turns a subtree read into a prefix scan rather than a recursive CTE on every dashboard request.
Zero-padding makes lexical order equal filed order past nine siblings.

### `filing_source_block` — the coverage ledger

One discovered human-visible leaf block and its single disposition.

| Column | Type | Null | Notes |
|---|---|---|---|
| `source_block_id` | uuid | no | Primary key |
| `filing_id` | uuid | no | FK `filing`, cascade |
| `document_id` | uuid | yes | FK `filing_document` |
| `content_unit_id` | uuid | yes | **The single owner.** Non-NULL if and only if `ASSIGNED` |
| `block_key` | text | no | `{document_tag}:{ordinal}` over an immutable filed document |
| `sequence` | integer | no | Discovery order |
| `block_kind` | text | no | `heading` \| `text` \| `table` \| `list` \| `graphic` \| `signature` \| `other` |
| `disposition` | text | no | The six below |
| `disposition_reason` | text | yes | Required for every exclusion |
| `normalized_text` | text | yes | |
| `text_sha256` | text | yes | |
| `char_length` | integer | yes | |
| `source_char_start` / `_end` | integer | yes | |
| `parser_version` | text | yes | |
| `evidence` | jsonb | yes | |

**Idempotency key**: `UNIQUE (filing_id, block_key)`. Stable because it derives from position in an
immutable filed document, never from a runtime DOM identity — which would change between runs and
make rerun reconciliation meaningless.

**Dispositions.** Five count as accounted; one does not.

| Disposition | Accounted |
|---|---|
| `ASSIGNED` | yes |
| `REPEATED_LAYOUT` | yes |
| `NAVIGATION_DUPLICATE` | yes |
| `DECORATIVE` | yes |
| `MACHINE_ONLY` | yes |
| `UNRESOLVED` | **no — blocks completion, and is never a reason to discard the block** |

**Constraints.** `assigned_block_has_exactly_one_owner` makes `ASSIGNED` equivalent to a non-NULL
`content_unit_id`, so **double assignment is unrepresentable** rather than merely tested for.
`excluded_block_states_its_reason` — an exclusion without a reason is indistinguishable from a
block nobody looked at.

### `filing_incorporation_reference`

A statement that this filing incorporates material filed elsewhere.

| Column | Type | Null | Notes |
|---|---|---|---|
| `reference_id` | uuid | no | Primary key |
| `filing_id` | uuid | no | FK `filing`, cascade |
| `content_unit_id` | uuid | yes | The unit containing the statement |
| `reference_key` | text | no | Stable digest of accession, unit, and source text |
| `item_number` | text | yes | The Item whose disclosure is incorporated |
| `referenced_form` | text | yes | e.g. `DEF 14A` |
| `referenced_document` | text | yes | |
| `referenced_accession` | text | yes | Set when deterministically resolved |
| `referenced_filing_date` | date | yes | |
| `referenced_deadline` | text | yes | e.g. "within 120 days after September 27, 2025" |
| `resolution_status` | text | no | `UNRESOLVED` \| `IDENTIFIED` \| `RESOLVED` \| `OUT_OF_SCOPE` |
| `acquisition_status` | text | no | `NOT_ATTEMPTED` \| `ACQUIRED` \| `UNAVAILABLE` \| `OUT_OF_SCOPE` |
| `source_text` | text | yes | The exact filed sentence, so a reviewer can check the detector |
| `coverage_consequence` | text | yes | |
| `detected_by`, `parser_version` | text | yes | |

**Idempotency key**: `UNIQUE (filing_id, reference_key)`.

**Constraint.** `resolved_reference_names_its_evidence` — `RESOLVED` requires a
`referenced_accession` and `acquisition_status = 'ACQUIRED'`. Marking a dependency resolved without
evidence is the specific dishonesty this table exists to prevent.

### `filing_document` — columns added by `0003`

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_class` | text | no | `HUMAN_READABLE` \| `MACHINE_ARTIFACT` \| `GRAPHIC` \| `UNKNOWN` |
| `inventory_sequence` | integer | yes | Position in the authoritative accession inventory |
| `is_primary` | boolean | no | |
| `classification_method` | text | yes | `declared_type` where possible; filename only as fallback |
| `classification_evidence` | jsonb | yes | Declared type, role, extraction requirement, reason |

**Idempotency key added**: `UNIQUE (filing_id, filename)`.

### `filing` — columns added by `0003`

| Column | Type | Null | Notes |
|---|---|---|---|
| `content_status` | text | no | `COMPLETE` \| `PARTIAL` \| `REQUIRES_REVIEW` \| `FAILED` \| `NOT_STARTED` |
| `submission_completeness` | text | no | `SUBMISSION_COMPLETE` \| `SUBMISSION_PARTIAL` \| `NOT_ASSESSED` |
| `disclosure_completeness` | text | no | `DISCLOSURE_COMPLETE` \| `DISCLOSURE_PARTIAL` \| `NOT_ASSESSED` |
| `content_coverage_confidence` | numeric(4,3) | yes | A judgement, not a count |
| `documents_listed` | integer | yes | What the AUTHORITATIVE inventory claimed |
| `content_parser_version` | text | yes | |

`footnote_status` is unchanged and remains the **footnote layer**. It must never be read as filing
completeness.

### Content-unit taxonomy

```
FILING_ROOT   COVER_PAGE   PART   ITEM   SUBSECTION   NARRATIVE
FINANCIAL_STATEMENT_SET   FINANCIAL_STATEMENT
FINANCIAL_STATEMENT_FOOTNOTE_SET   FINANCIAL_STATEMENT_FOOTNOTE   FINANCIAL_SCHEDULE
TABLE   LIST   GRAPHIC   EXHIBIT_INDEX   EXHIBIT   CERTIFICATION   SIGNATURE   CONSENT
INCORPORATED_REFERENCE   OTHER_DISCLOSURE   UNRESOLVED
```

There is deliberately **no** disposition or status meaning "skipped because it looked unimportant".

### Derived, deliberately not stored

Every count the coverage report shows — blocks discovered, assigned, excluded, unresolved, content
units, duplicate assignments, required summary units — is a `COUNT()` over
`filing_source_block` and `filing_content_unit`. Only judgements are stored, for the same reason
the eleven footnote counters are not stored: a stored copy of a derivable count is a second source
of truth that goes stale the moment a block is re-dispositioned.

---

## Conventions

| Convention | Rule |
|---|---|
| Primary keys | `uuid`, generated application-side so a record has identity before insert |
| Timestamps | `timestamptz`, always UTC |
| Identifiers from SEC | `text`, never integer. `0000320193` is not the number 320193 |
| Money | `numeric`, never float. Never a currency-scaled integer without a `scale` column |
| Enums | `text` with a check constraint, so a new value is a migration not a deploy |
| Soft delete | Not used. Supersession columns instead |
| `created_at` | On every table |

## Identifier formats

| Identifier | Format | Example | Notes |
|---|---|---|---|
| CIK | 10-digit zero-padded text | `"0000320193"` | Unpadded for Archives URLs only |
| Accession | dashed text | `"0000320193-25-000079"` | Undashed only as a folder segment |
| Ticker | uppercase text | `"AAPL"` | Never unique on its own; temporal |
| Footnote id | uuid | | |
| Source block id | text | `"debt-narrative-01"` | Stable within a filing; cited by the model |
| Dataset version | text | `"2026-08-01T04:38Z-r3"` | Names an immutable Parquet directory |

## Unit conventions

```
USD, USD_thousands, USD_millions, USD_billions, shares, percent, years, count, ratio
```

Unit and `scale` are stored separately and always together. A value without both is not
interpretable. A unit is never inferred at display time from magnitude.

## Period conventions

```
period_type      instant | duration
instant_date     set for instants, null for durations
period_start     null for instants
period_end       always set
duration_months  computed at ingest; charts filter on it
is_derived       true for a computed Q4
```

The database enforces this: `ck_xbrl_fact_period_fields_match_period_type` requires an
`instant_date` for an instant and both boundaries for a duration.

### Period fidelity depends on the source, and the source is recorded

`xbrl_fact.source_dataset` is not decoration. Period precision differs by source, and a chart that
mixed them without knowing would be quietly wrong.

**`source_dataset = 'dera_notes'` periods are normalized approximations.** DERA rounds `ddate` to
the nearest month end, states `qtrs` as a whole number of quarters, and publishes the residuals
separately as `datp` and `durp`. It publishes no period start at all, so `period_start` is
DERIVED: the first day of the month `duration_months - 1` before `period_end`.

The consequence is concrete. Apple's FY2025 ended 2025-09-27, a 52/53-week fiscal year end; DERA
records 2025-09-30, and the derived start is 2024-10-01 where the filed context begins 2024-09-29.
Days differ; the quarter does not.

Every row loaded this way carries `validation_status = 'UNVALIDATED'`, because nothing has
validated it and the exact filed boundaries live in the XBRL instance document. When the instance
is parsed, its facts are APPENDED — `xbrl_fact` is append-only — and supersede the DERA
observations through the ordinary restatement path. The DERA rows are never edited in place; the
trigger would reject it.

**Do not use a DERA `period_start` as a filed date.** Use it to bucket a period. Anything that
must cite an exact boundary reads from a source that publishes one.

## Footnote extraction conventions — Sprint 4

```
canonical_footnote.sequence          filed order, 1..N; the idempotency key
canonical_footnote.normalized_number displayed note number, NULL when the filing shows none
footnote_source_block.external_id    the renderer position, R9, matching its own file naming
footnote_source_block.block_type     parent_narrative | details | tables | policies
footnote_source_block.footnote_id    NULL means ORPHAN, which is a reportable state, not an error
filing_section.section_type          item_disclosure for an excluded Regulation S-K item
footnote_table.footnote_id           the owning note; NULL for every non-footnote kind
footnote_table.ownership_kind        CANONICAL_FOOTNOTE | EXCLUDED_FILING_SECTION
                                     | FINANCIAL_STATEMENT | OTHER_FILING_REPORT | UNRESOLVED
footnote_table.ownership_evidence    tagged concept, candidate roles, deterministic reason
```

`sequence` rather than `normalized_number` is the upsert key. `normalized_number` is nullable, and
a NULL never conflicts in a unique constraint, so two unnumbered notes would duplicate silently.

`ownership_kind` and `footnote_id` must agree, enforced by a check constraint: a NULL
`footnote_id` alone cannot distinguish a statement from an excluded disclosure from an unresolved
table, and only the last is a defect.

Numeric text inside `footnote_table.cells` is the string the filer wrote — `(1,234)`, `$`, commas
intact. It is never converted to a number at extraction time.

## State enums

Filing processing: `DISCOVERED`, `QUEUED`, `DOWNLOADING`, `DOWNLOADED`, `PARSING`, `PARSED`,
`EXTRACTING_FACTS`, `FACTS_EXTRACTED`, `EXTRACTING_SECTIONS`, `SECTIONS_EXTRACTED`,
`EXTRACTING_FOOTNOTES`, `FOOTNOTES_EXTRACTED`, `GROUPING_FOOTNOTES`, `FOOTNOTES_GROUPED`,
`VALIDATING_FOOTNOTES`, `FOOTNOTES_VALIDATED`, `SUMMARIZING`, `SUMMARIES_GENERATED`,
`VALIDATING_SUMMARIES`, `CALCULATING_METRICS`, `PUBLISHING`, `COMPLETE`, `PARTIAL`, `FAILED`,
`REQUIRES_REVIEW`.

Footnote status: `COMPLETE`, `PARTIAL`, `REQUIRES_REVIEW`, `FAILED`.

Summary validation: the eleven states in `docs/llm/summary-validation.md`.

Grouping method: `role_uri`, `toc_reconciliation`, `heading`, `presentation_hierarchy`,
`concept_overlap`, `title_similarity`, `filing_order`, `model_adjudication`, `human_review`.

Exclusion reason: `foreign_private_issuer_20f`, `fund_n_csr`, `bdc_specialized`, `shell`,
`never_filed`, `unresolved_identity`, `filing_history_unavailable`.

Analysis scope: `FOOTNOTE`, `FILING`, `TIMEFRAME`.

## Source types

```
footnote_narrative   footnote_policy      footnote_detail      footnote_table
filing_section       xbrl_fact            derived_metric       summary
```

Every citation names one of these plus an identifier, so a claim's provenance is typed.

## Tables

24 domain tables. Full column definitions in `packages/persistence/models.py` and the initial
migration.

### Counting the schema

Two methods, both useful, not interchangeable. They agree once `alembic_version` is accounted for.

| Object | Model metadata | Live catalog (`public`) |
|---|---|---|
| Tables | 24 | 24 domain, 25 including `alembic_version` |
| Explicit indexes | 37 | 37 |
| of which partial | 7 | 7 |
| Check constraints | 23 | 23 |
| Unique constraints | 19 | 19 |
| Foreign-key constraints | 29 | 29 |
| Primary-key constraints | 24 | 25 (`alembic_version` has one) |
| Indexes including constraint-backing | not modelled | 81 = 25 PK + 19 unique + 37 explicit |

*Model metadata* is `Base.metadata` — what the code declares. The structural tests assert against
it, and it is available with no database.

*Live catalog* is `pg_class`, `pg_constraint`, `pg_indexes` restricted to `public`. It is what
actually exists, including objects PostgreSQL creates on its own behalf. Migration verification
uses it.

Two traps when reading these numbers. SQLAlchemy reflection omits primary-key-backing indexes, so
`inspect().get_indexes()` sums to 56, not 81 — the difference is exactly the 25 PK indexes. And a
`pg_constraint` query without a schema filter picks up `cardinal_number_domain_check` and
`yes_or_no_check` from `information_schema`, reporting 25 check constraints where the application
has 23. Always filter on `nspname='public'`.
Summary of ownership:

| Table | Owns | Key invariant |
|---|---|---|
| `issuer` | Issuer identity | CIK unique |
| `issuer_former_name` | Name history | Needed because delisted issuers are renamed |
| `listing` | Ticker history | Unique on `(ticker, exchange, effective_start)`, never on ticker |
| `listing_observation` | Raw snapshots | Append only; never overwritten |
| `excluded_filer` | Exclusions | Reason always populated |
| `filing` | Filing metadata | Accession unique; carries `completeness_confidence` and `reconciliation_status`, the two completeness values that cannot be derived from child rows |
| `filing_document` | Acquired objects | Every row has a sha256 |
| `filing_section` | Item sections | Carries extraction strategy and confidence |
| `canonical_footnote` | Footnotes | Unique on `(filing_id, normalized_number)` |
| `footnote_source_block` | Source blocks | Parent nullable so orphans are visible; carries the per-attachment grouping audit (method, confidence, evidence, competing candidates, run id) |
| `footnote_table` | Tables | Structure preserved; original HTML retained |
| `xbrl_fact` | Filed facts | `value_as_filed` append-only, enforced by trigger |
| `metric_definition` | Curated mappings | Versioned; git commit recorded |
| `derived_metric` | Computed values | Records formula version and input fact ids |
| `footnote_summary` | Summaries | One active version per footnote, partial unique index |
| `processing_job` | Job state | Idempotency key unique |
| `analysis_session` | Deep Analysis scope | Immutable after creation |
| `analysis_message` | Turns | Carries citations and cost |
| `conversation_memory` | Structured memory | Only evidenced findings |
| `llm_invocation` | Model audit | Exact request and response URIs and hashes |
| `prompt_version` | Prompt registry | Content hash recorded |
| `dera_package` | DERA mirror ledger | Monthly rows retained after quarterly consolidation |
| `dataset_version` | Published Parquet pointer | Partial unique index: at most one current |
| `filing_amendment` | Amendment relationships | Amendment is never its own target |

### Enforcement highlights

    xbrl_fact               BEFORE UPDATE trigger rejects any change to a filed value, unit,
                            scale, concept, or period. Append a new observation instead.
    listing                 unique on (ticker, exchange, effective_start), never on ticker
    footnote_summary        partial unique index gives exactly one active version per footnote
    footnote_source_block   footnote_id nullable, with a partial index over orphans
    llm_invocation          check constraint restricts content format to plain_text or yaml
    dataset_version         partial unique index over is_current
    filing                  reconciliation_status constrained to RECONCILED | MISMATCH |
                            NOT_ATTEMPTED, so "no TOC found" is distinguishable from "reconciled"

### Derived, deliberately not stored

Eleven of the thirteen completeness counters in docs/footnotes/completeness.md are COUNT()
queries over canonical_footnote, footnote_source_block, footnote_table, and footnote_summary.
They are not columns. A stored copy of a derivable count is a second source of truth that goes
stale the moment a summary is superseded or a block is re-attached.

## Retention

Filing data and facts: indefinite; public data with provenance value.
Summaries: indefinite, including superseded versions.
Model invocation records: indefinite; principal anonymized on user deletion rather than the row
removed, so cost accounting stays reconcilable.
Analysis sessions and messages: user-deletable.
Dataset versions: last N retained plus one per quarter as an archive.
