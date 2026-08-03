# Product Definition

> **RE-FOUNDED 2026-08-02 ON MEASURED EVIDENCE.** A representative corpus of **112 SEC issuers and
> 613 filings across six transport eras** was acquired and measured — dated Phase 1 evidence, not a
> permanent constant — and it refuted the assumptions the deterministic semantic parser rested on.
> The deterministic content ontology, migration `0003` and the local application database are
> withdrawn.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.** Authoritative:
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.

IMPLEMENTATION STATUS: PLANNED. The acquisition, preservation and validation foundation is
IMPLEMENTED; the orchestrator, the model roles and the artifacts are not.

## What the beta is

**An orchestrator-driven, model-first SEC filing product.**

The user picks a company, a timeframe, and four models. The backend acquires the filings, preserves
the original SEC artifacts byte-for-byte, sends each filing intact to the user's chosen parsing
model, proves the returned parse against the preserved bytes, sends the accepted parse to the
user's chosen summary model, and serves the results. Ordinary browsing of a completed result
invokes no model at all.

**The backend orchestrates and validates. It is not the authoritative semantic parser.** No backend
code decides what is MD&A, a risk factor, a footnote, an exhibit, a certification or a signature
block. That is the parsing model's job, and giving it away to a regular expression is the mistake
this document exists to prevent recurring.

## The four model roles

The user chooses all four **independently**, for every job. No role inherits another's model, there
is no automatic substitution, and there is no silent fallback.

| Role | What it does |
|---|---|
| **Parsing** | Determines the filing's native semantic structure and returns a clean parsed artifact |
| **Image** | Analyzes image-bearing source objects when the parsing model is text-only |
| **Summary** | Turns an accepted parse into a separate summary and explanation artifact |
| **Analysis / chat** | Deep Dive, follow-up questions and comparisons inside an immutable scope |

If the parsing model is multimodal it handles images itself; the image selector stays visible but
disabled for that job and no image model is invoked redundantly. If the parsing model is text-only,
the backend inventories image-bearing objects **mechanically** — location, dimensions, hash,
containing document, never meaning — and the selected image model analyzes them into separate,
linked artifacts.

**Approved beta candidates:** GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4
Maverick, Qwen3 VL 235B. **None is currently configured or accessible.** Availability, model IDs,
regional support, modality, limits and prices are subject to live discovery in Phase 1.5, which has
not run.

## The workflow

1. Search a locally maintained catalog of entities that have qualifying 10-K/10-Q-family filings.
2. Select an entity by ticker, historical ticker, current or historical name, SEC filer name, or
   alias.
3. Select a timeframe, bounded below by the entity's earliest known qualifying filing.
4. Select the four models independently.
5. Retrieve and preserve the original SEC source artifacts byte-for-byte.
6. Determine the complete relevant human-readable source set.
7. Send that set **intact** to the selected parsing model, when the pairing is compatible.
8. Receive a clean parsed filing artifact.
9. Persist the parsed artifact **separately from** the original source.
10. Send the accepted parse and its supporting evidence to the selected summary model.
11. Persist a separate summary and explanation artifact.
12. Render original source, clean parse, and summary as three distinct views.
13. Use the selected analysis/chat model for Deep Dive and conversation.
14. Use the image model only when the selected parser is text-only.
15. Cache reusable accepted results.
16. Persist durable artifacts and their lineage.
17. Stream processing progress to the frontend.
18. Serve completed results with no further model calls.

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

**MINIMUM BETA CATALOG — required no later than Phase 3, complete before Phase 6 can be complete.**

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

## Corpus evidence — dated Phase 1, 2026-08-02

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
