# Product Definition

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 0 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
>
> **UPDATED 2026-08-03.** The deterministic semantic parser, the application persistence layer and
> its migrations, the DERA mirror and the accession document classifier are no longer merely
> withdrawn — they are DELETED from the active tree, and no application database exists. The
> surviving runtime is transport, identity, boundary and generic infrastructure only.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`,
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md` and `roadmap.md`.

IMPLEMENTATION STATUS: PLANNED. The acquisition, preservation and boundary foundation is
IMPLEMENTED; the orchestrator, the model roles, coverage validation and the artifacts are not.

## What the beta is

**An orchestrator-driven, model-first SEC filing product.**

The user picks a company, a timeframe, and **a parsing model — the only required selection**. The
backend checks its own durable source storage first, acquires anything missing from EDGAR,
preserves the original SEC artifacts byte-for-byte, sends each filing intact to the chosen parsing
model, proves the returned parse against the preserved bytes, and shows the result for review.
Image analysis, summarization and Deep Dive are optional stages that run only when the user selects
a model for them. Ordinary browsing of a completed result invokes no model at all.

**A parser-only run is a complete, valid run.** It is the first functional workflow this project
builds, and the orchestrator never turns it into a fuller pipeline on its own initiative.

**The backend orchestrates and validates. It is not the authoritative semantic parser.** No backend
code decides what is MD&A, a risk factor, a footnote, an exhibit, a certification or a signature
block. That is the parsing model's job, and giving it away to a regular expression is the mistake
this document exists to prevent recurring.

## The four model roles

The user chooses each **independently**, for every job. No role inherits another's model, there is
no automatic substitution, and there is no silent fallback. **Only parsing is required**; the other
three selectors may be left blank, and a blank selector means that stage does not run, produces no
artifact, and shows no placeholder.

| Role | Required | What it does |
|---|---|---|
| **Parsing** | **YES** | Determines the filing's native semantic structure and returns a clean parsed artifact |
| **Image** | optional | Analyzes image-bearing source objects when the parsing model is text-only |
| **Summary** | optional | Turns an accepted parse into a separate summary and explanation artifact |
| **Analysis / chat** | optional | Deep Dive, follow-up questions and comparisons inside an immutable scope |

The orchestrator executes only the stages the user selected, in order, and stops after the last one.
It never silently selects a blank model, substitutes another, adds a stage, skips a selected stage,
invokes an extra model, or retries through a different model.

If the parsing model is multimodal it handles images itself; the image selector stays visible but
disabled for that job and no image model is invoked redundantly. If the parsing model is text-only,
the backend inventories image-bearing objects **mechanically** — location, dimensions, hash,
containing document, never meaning — and the selected image model analyzes them into separate,
linked artifacts.

**Approved beta candidates:** GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4
Maverick, Qwen3 VL 235B. **None is currently configured or accessible.** These are LABELS, not
verified provider identifiers. Availability, model IDs, regional support, modality, limits and
prices are subject to live discovery in Phase 1, which has not run.

## The workflow

Steps 1 to 9 are the required path. Steps 10 to 13 run only when the user selected a model for that
stage.

```
discover -> check local source storage -> acquire byte-exact -> preserve
         -> assemble the intact human-readable source set -> parsing model
         -> validate against preserved bytes -> review / approve
         -> optional image / summary / chat stages
```

1. Search a locally maintained catalog of entities that have qualifying 10-K/10-Q-family filings.
2. Select an entity by ticker, historical ticker, current or historical name, SEC filer name, or
   alias.
3. Select a timeframe, bounded below by the entity's earliest known qualifying filing.
4. Select a parsing model. Optionally select an image, summary or analysis/chat model.
5. Open ONE visible, copyable parent run ID, with one child job per filing.
6. **Check durable local source storage BEFORE contacting SEC** — verify object presence, byte count
   and SHA-256, and reuse a valid preserved original. Fetch from EDGAR only what is missing,
   incomplete or hash-invalid, and preserve what is fetched byte-for-byte.
7. Determine the complete relevant human-readable source set **mechanically**.
8. Send that set **intact** to the selected parsing model, one filing per invocation, when the
   pairing is compatible. Refuse and explain when it is not.
9. Receive a clean parsed filing artifact, prove its coverage, citations and numbers against the
   preserved bytes, and store it **separately from** the original source as an EVALUATION artifact
   for review.
10. Send the accepted parse and its supporting evidence to the selected summary model, and store a
    separate summary and explanation artifact.
11. Use the image model only when the selected parser is text-only and an image model was selected.
12. Use the selected analysis/chat model for Deep Dive and conversation.
13. Render original source, clean parse, and summary as distinct views, with source-reference
    navigation between them.
14. Reuse only APPROVED artifacts, on an exact reuse key.
15. Stream processing progress, validation warnings, cost and timing to the frontend.
16. Serve completed results with no further model calls.

## Evaluation, approval and reuse

**A parsed artifact is an EVALUATION artifact until a human explicitly approves it.** It is
reviewable immediately and it does not satisfy a user search as a trusted result before approval.
Approval is per filing and needs no other model: a parser-only artifact may be approved on its own.

Only an approved artifact becomes reusable. The **authoritative** copy lives in persistent storage;
Redis holds a reusable cache entry with a **24-hour TTL** and is an acceleration layer, never the
source of truth. Reuse requires an exact match on filing identity, source hash, model identity and
version, prompt version, settings and validation-policy version — two versions of a model are never
interchangeable, and neither are two prompts.

Every run carries a visible parent run ID, and granular developer comments attach to the run, a
filing, a child job, any node of a parsed artifact, a summary, a chat message, a validation warning
or an error.

## Intact-source-only

`INTACT_SOURCE_ONLY` is the current authorized input mode, and the only one.

For each filing and model pairing the backend determines the complete relevant human-readable
source set and verifies real compatibility **before** invocation. If the set fits, the model may be
used. If it does not, that model is **incompatible with that filing** — the pairing is refused,
explained, and the user may choose a different compatible model.

```
no truncation                    no semantic slicing
no automatic model substitution  no silent fallback
no mechanical multipart          no visible-content projection
```

Mechanical multipart and lossless reversible projection remain **possible future research options
requiring separate user approval**. They are not accepted architecture and must not be presented as
such.

## The four non-negotiable properties

```
EVERY human-readable source range in every processed filing is represented in the accepted parsed
artifact or explicitly marked unresolved. Every financial-statement footnote the accepted parse
identifies stays an independent content node and an independent required summary target. Nothing is
merged away. Uncertainty produces PARTIAL or REVIEW_REQUIRED, never a false complete.

THE SELECTED PARSING MODEL determines the filing's native semantic structure. The backend performs
transport handling and then PROVES coverage, citations and numbers against the preserved bytes.
Backend code never decides what any part of a filing means.

ORDINARY dashboard access never invokes a language model.

DEEP ANALYSIS is a deliberate, scoped, metered, auditable feature bound to one issuer and
timeframe. It is not a general-purpose financial chatbot.
```

Interpretation is the model's. **Proof is the backend's.** Coverage validation is what makes
model-first parsing safe, and it is the reason model-first is not the same thing as trusting the
model.

## What a filing is not required to look like

There is **no universal semantic filing taxonomy**. The parsed artifact carries filing-native
labels, unknown structures, free-form model descriptions, ordered content, parent/child
relationships, paragraphs, lists, tables, images, source references, confidence, ambiguity,
unresolved content, and content types nobody has anticipated yet.

Names like MD&A, Risk Factors, Item 7, Footnote, Part I, Certification, Signature or a fixed proxy
topic may appear as filing-native labels, model annotations, optional derived indexes, search
facets, benchmarks or validation hints. **They are not required database ontology** and no filing
is obliged to use them.

## Primary users

The retail or semi-professional investor who can read a financial statement but will not read a
hundred pages of disclosure. The analyst who will read them but wants to find the three sections
that matter first. Neither wants to touch raw SEC HTML.

## Product boundaries

The system reads SEC filings and explains them. It does not price securities, execute trades,
manage portfolios, recommend actions, or predict prices.

**Non-goals for the beta.** Real-time market pricing, brokerage integration, trade execution,
personalized recommendations, portfolio management, news scraping, social sentiment, earnings-call
transcription, options analytics, non-US filing systems, mobile applications, full valuation
modeling, and SEC form types beyond the 10-K/10-Q family.

## Entity and filing identity

Corpus-proven, and every rule below exists because getting it wrong produced a real defect.

| Rule | Why |
|---|---|
| CIK is the stable issuer identity | Names and tickers both change; the CIK does not |
| Filing identity is `(CIK, accession)` | Co-registration puts one submission under two filer CIKs |
| The accession prefix may be the FILING AGENT's CIK | 361 of 613 corpus filings; ownership comes from the archive path |
| A current ticker is not identity | 68 of 112 corpus issuers have no current ticker at all |
| Historical ticker data is never fabricated | Absent is recorded as absent |
| A sampling label never overwrites EDGAR identity | CIK 0001736946 was labelled "Astera Labs"; it is Arlo Technologies |
| Exact filed form strings are preserved | EDGAR writes `10KSB`, not `10-KSB` |
| Family membership comes from the reviewed inventory | 22 included and 19 excluded, each adjudicated |
| An unreviewed form candidate fails closed | A guess produced a confidently inverted conclusion once already |

A ticker that has never filed a qualifying form does not appear in search. Showing a symbol the
product cannot serve is worse than not showing it.

## The entity catalog — two scopes, deliberately

The beta needs a working local catalog long before it needs the whole of EDGAR, and the roadmap
says so explicitly so the UI is never left waiting on Phase 8.

**MINIMUM BETA CATALOG — complete before Phase 6, the functional beta UI, can be complete.**

```
stable CIK identity                    current authoritative filer name
observed aliases                       current ticker where known
historical ticker observations WHERE AUTHORITATIVE EVIDENCE EXISTS
qualifying filing identities           exact filed forms, never normalized
earliest known qualifying filing       latest known qualifying filing
filing dates and report periods        local entity search
filing-bounded timeframe selection
incremental additions for the beta corpus and actively used entities
```

**No fabricated historical ticker data.** Absent evidence is recorded as absent.

This is not the EDGAR universe, and the parser experiment does not wait for one.

**PHASE 8 CATALOG EXPANSION.** Complete EDGAR-wide entity population, complete historical
qualifying filing acquisition, universe-scale alias and name-history reconciliation, scheduled
incremental synchronization, durable checkpoints, amendment monitoring, newly qualifying issuer
discovery, performance and search-index optimization, large-scale backfill, and long-term
operational scheduling. Phase 8 expands the working catalog; it does not create it.

## Timeframe

"Year" always means the **issuer's** fiscal year, never the calendar year — Apple's fiscal 2025 ends
in September. A selectable timeframe is bounded below by the entity's earliest known qualifying
filing, so the UI cannot offer a range the product cannot serve.

## Corpus evidence — dated Phase 0, measured 2026-08-02, reverified 2026-08-03

These are measurements of one sample on one date. They are evidence, not permanent constants.

```
112 issuers                    613 filings
6 transport eras               22 direct substantive form strings
19 adjudicated exclusions      75 distinct SIC industries
138 amendments                 313 annual, 300 quarterly
187 filings carry images       11 carry PDFs
median package 11 files        largest package 283 files
44 percent of primary documents exceed ~200,000 estimated tokens
```

Standard, transition, small-business and Item-405 variants are all represented, as are base reports
and amendments, modern inline-XBRL filings, historical SGML and plain-text filings, HTML filings,
image-bearing and PDF-bearing packages, and filings too large for some context windows.

## Future expansion

Additional form types (20-F, 8-K, DEF 14A, S-1), delisted-issuer backfill, pre-2009 numeric
extraction, and cross-issuer comparison as a distinct scope type. The ingestion layer is
form-extensible, so these are additions rather than rewrites.
