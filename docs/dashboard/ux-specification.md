# Dashboard UX Specification

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
> **UPDATED 2026-08-03.** The deterministic parser, the application persistence layer, the
> migrations, the DERA mirror and fact lake, and the curated metric-definition set were DELETED
> from the active tree. Every screen this document describes remains NOT IMPLEMENTED. The beta-UI
> section below is authoritative and has been brought up to date; everything under
> `HISTORICAL — describes the withdrawn design` is retained as a record and describes screens,
> fields, tables and files that no longer exist. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`,
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and `roadmap.md`.
>
> **NO MODEL HAS BEEN INVOKED AND AWS IS NOT CONFIGURED.**
>
> **FORWARD NOTE, 2026-08-03 — Phase 2 landed a PARSER-REVIEW UI.** The three notes above are kept
> exactly as written, because each was true when it was written: at that point no frontend code
> existed anywhere in the tree. That is no longer true. `packages/review_web` and
> `packages/review_api` are IMPLEMENTED and serve a working parser-review surface, and
> `packages/llm_gateway/providers/bedrock.py` is an IMPLEMENTED Bedrock Converse adapter. The
> sentence "Every screen this document describes remains NOT IMPLEMENTED" is superseded only to
> that extent.
>
> **The parser-review UI is NOT the beta UI.** It is a developer evaluation surface, specified in
> the new section immediately below. The beta-UI section that follows it remains PLANNED and NOT
> IMPLEMENTED, and nothing in the new section may be read as delivering any part of it. Treating an
> evaluation tool as a shipped product surface is precisely the reporting failure
> `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` was written after. Everything under
> `HISTORICAL — describes the withdrawn design` is untouched by this update.
>
> **No parse-quality, token-count or cost-per-filing measurement appears in this document.** Those
> measurements are PENDING. Model identifiers, regions, context limits, output limits and prices
> are recorded in exactly one place, `docs/llm/bedrock-capability-snapshot.yaml`, and are not
> copied here — a capability recorded twice drifts.
>
> **SUPERSEDED 2026-08-03 BY PHASE 2, ADDITIVELY.** The statement above was true when it was
> written and is kept for that reason (`rules.md` section 21 rule 16). It is no longer true:
> AWS IS configured, a real Bedrock adapter EXISTS in `packages/llm_gateway/providers/bedrock.py`,
> and SEC filings HAVE been sent to real models — three preserved filings across five candidates
> under two prompt versions. See `docs/sprints/PHASE-0002-parser-experiments-and-review-ui.md`.
>
> **WHAT IS STILL TRUE.** No application database exists. No Redis exists. No summary artifact, no
> image artifact and no chat session exists — Phase 2 ran the PARSING stage only, and the
> orchestrator raises rather than running another. Nothing is deployed.


IMPLEMENTATION STATUS: parser-review UI IMPLEMENTED (Phase 2); beta UI PLANNED
PRODUCT DEFINITION: `docs/architecture/product-definition.md`
API: `docs/api/openapi.yaml`
ARCHITECTURE: `docs/adr/ADR-0016-corpus-first-model-first-architecture.md`,
`docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`,
`docs/adr/ADR-0019-parser-review-application-over-a-framework.md`

There is no separate content-model document and no universal filing taxonomy. A parsed node
carries whatever label the filing and the parsing model produced.

---

# THE PHASE 2 PARSER-REVIEW UI — IMPLEMENTED

IMPLEMENTED. `packages/review_web` renders the pages, `packages/review_api` serves them, and both
run today. This section describes what the code does, verified by reading it — not what it should
eventually do.

**What this surface is for.** roadmap.md 2b: a parsed artifact cannot be evaluated without seeing
it beside the filing it came from, and reading a YAML document in a terminal is not evaluation.
Every other Phase 2 package exists so that this one page can show something true.

**What this surface is NOT.** It is not the beta UI, not a product surface, and not for an
investor. It is single-user, loopback-first, developer-facing, and it exposes machinery — exact
response bytes, reasoning content, spend reservations, execution states — that no investor should
ever be shown. The section "What the parser-review UI deliberately does not do" below is part of
the specification, not an apology.

## Construction, and why it is what it is

```
SERVER-RENDERED       every page is HTML built on the server; the browser holds no state
STANDARD LIBRARY      http.server only. No web framework, no ASGI server, no bundler, no npm,
                      no new runtime dependency
ONE SCRIPT            copies the run identifier to the clipboard, and nothing else
```

Everything that matters works with scripting disabled: raw and parsed views, side-by-side,
source-reference navigation, comments and review actions are ordinary links and form posts. That
is not nostalgia. A server-rendered surface has no client-side state that can disagree with what
was stored, and no path by which a preserved SEC filing reaches a JavaScript context at all.
Rationale of record: `docs/adr/ADR-0019-parser-review-application-over-a-framework.md`.

**A filing is never rendered as markup.** Every value reaching a page goes through one escape
function in `packages/review_web/html.py`, and raw source is shown as escaped text inside a
preformatted block. There is no sanitizer to get wrong and no sandboxed iframe to configure,
because nothing from a filing is ever parsed as HTML by the browser.

## The shell: a persistent collapsible left panel

```
+---------------------+--------------------------------------------------+
|  SEARCH PANEL   [<] |  WORKSPACE                                       |
|  persistent,        |  index / preflight / run / child job             |
|  vertical, left     |                                                  |
|  Entity or ticker   |                                                  |
|  Timeframe          |                                                  |
|  Exact filing       |                                                  |
|  Parsing model  *   |                                                  |
|  Image model        |                                                  |
|  Summary model      |                                                  |
|  Analysis model     |                                                  |
|  [Preflight and run]|                                                  |
+---------------------+--------------------------------------------------+
|  run 7f3c… [copy]   |   anchored to the VIEWPORT, not to the panel     |
+---------------------+--------------------------------------------------+
   * required
```

The panel is an `<aside>` that is always present. A `collapse` control in its top-right corner
links to `?panel=closed`; when collapsed the panel is hidden and a `menu` control in the workspace
links back to `?panel=open`. The workspace fills the space either way. The panel is rebuilt on
every request from the query string, so a reload restores the same entity, timeframe and model
selections rather than defaults.

**Known gap, stated rather than hidden.** The collapse control carries only `panel=closed`, so it
replaces the query string that held the entity and model selections. Collapse therefore does not
yet preserve panel state, and the beta acceptance criterion "Collapse preserves state" is NOT met
and stays open below. What IS verified by test is narrower and is the part that matters most for
bug reports: the parent run identifier survives a collapsed panel.

## The four model selectors

Four independent selectors — parsing, image, summary, analysis — built from
`ParserReviewService.selectors()`. Each is populated separately from the reviewed capability
snapshot. None defaults from another and none is inferred.

```
Parsing         REQUIRED. No blank option is offered at all.
Image           OPTIONAL. Carries the blank option "None — skip this stage".
Summary         OPTIONAL. Carries the blank option "None — skip this stage".
Analysis        OPTIONAL. Carries the blank option "None — skip this stage".
```

The blank option is a VISIBLE choice with a label, not a hidden default, and nothing is
preselected. A hidden empty first option and a deliberate "skip this stage" are the same HTML and
completely different products: only one of them lets a user state that they meant it.

Each optional selector renders a note reading that the stage is not executed in Phase 2 and that
the selector exists so the progressive workflow is real. The selectors are routed by
`packages/model_catalog/routing.py` and the three optional stages raise `StageNotAuthorizedError`
if anything tries to execute them, so a blank optional role and a filled one produce the same
result today — no stage.

### What every selector row displays

| Field | Source |
|---|---|
| Label, provider | the reviewed capability snapshot |
| Capability badge | `Multimodal` or `Text only`, on every row |
| Region | the region DERIVED from the snapshot for this role |
| Context limit, output limit | the snapshot's verified values |
| Price per 1k input and output, currency | the snapshot's reviewed price inputs |
| `via inference profile` | present when the route goes through an inference profile |
| `UNAVAILABLE: <reason>` | present on every disabled row, with the concrete reason inline |

None of those values is written into this document. They live in
`docs/llm/bedrock-capability-snapshot.yaml`, and `packages/model_catalog` is the only code that
reads them.

**No candidate is filtered out of a selector.** A candidate that cannot fill the role comes back
disabled with its reason on the row, because a candidate that silently vanishes is
indistinguishable from one that was never approved. A version the snapshot does not carry renders
as the literal `unverified`, never as blank.

**The multimodal badge and the disabled image selector.** When the selected parsing model is
multimodal, the image selector is rendered **visible but disabled**, with the one-line explanation
that the parsing model handles filed images itself and no separate image model is invoked. It is
never hidden: hiding it would make the four-role model look like three.

**Per-filing compatibility is NOT on the selector row.** The beta specification puts a fits / does
not fit verdict on each dropdown entry; the implemented UI computes compatibility per filing on the
preflight page instead, because compatibility is a property of a source set and a model together,
not of a model alone. The selector-row verdict remains PLANNED.

## Entity, timeframe and exact filing

**Entity.** A search box and a submit button. The submitted query is matched against the preserved
corpus catalog — current name, former names, and exact ticker, with an exact ticker ranked above a
name match — and the matches render as a list of links, each resolving to a CIK. There is no
relevance score, because a relevance score nobody specified is a product decision hidden in a sort
key. **It is not a typeahead and it reaches nothing beyond the locally preserved corpus.**

**Timeframe.** Two date inputs whose `min` and `max` are the entity's earliest and latest preserved
filing dates, above a line stating how many qualifying filings exist, the range they span, and
which forms are present. The bound is displayed, not merely enforced. These are FILING DATES, not
fiscal years; the fiscal-year control the beta specification requires is PLANNED.

**Exact filing (developer mode).** An optional selector listing each preserved filing with its
form as filed, filing date, accession and estimated token count, so a single filing can be run
rather than a whole timeframe.

**Cumulative spend.** The panel states authorized spend so far against the ceiling, read from the
durable spend journal.

## The Run button and its exact enablement conditions

One button, labelled `Preflight and run`. It posts to `/preflight`; it does not start a billable
invocation.

**Enablement.** The button is rendered `disabled` unless ALL of the following hold:

```
an entity is resolved to a CIK
a parsing model label is selected
that label matches a row in the parsing selector
that row is available — not disabled by the snapshot for this role and region
```

The three optional roles never affect enablement. When the button is disabled the panel states the
unmet condition in words: select an entity and an available parsing model, and the image, summary
and analysis selectors may stay blank.

**Compatibility is NOT an enablement condition here**, and that is deliberate. Whether a filing's
complete source set fits the model is measured per filing during preflight, on the next page, where
the numbers can be shown. Gating the button on it would refuse a run without ever telling the user
by how much it did not fit.

**Presentation.** Semi-transparent light blue, the single strongest accent on the page; disabled it
falls back to a flat grey with `cursor: not-allowed`.

## The cost preflight page

Posting the panel renders `Cost preflight` — everything a user should see BEFORE authorizing a
billable run, with nothing billable having happened yet.

```
ROUTING      the routed parsing model, its role, the DERIVED region and the preferred region,
             its modality, and the invocation identifier. A cross-region route renders as a
             DISCLOSED warning, never silently. An inference-profile route states that the
             profile may span more than one region.
PROMPT       the prompt identifier, its version, and the leading bytes of its SHA-256 lock
PER FILING   form, accession, transport era, submitted members and bytes, how many members were
             REUSED from local storage versus FETCHED from SEC, estimated input tokens, the
             requested output cap, the worst-case cost, and a fits / reason verdict
TOTALS       worst case for this run, cumulative spend so far, and the ceiling
```

Each incompatible filing renders its full explanation as a warning beneath the table. The cost line
states what it is: a WORST-CASE bound from a character-ratio token estimate and the reviewed price
inputs — **not a prediction** — reserved before the call and settled against measured usage after
it. R-24 in `roadmap.md` is the open risk this wording exists to keep visible.

**The confirm control disappears when it must.** `Run now` is rendered only when the worst case
stays within the cumulative ceiling AND at least one filing is compatible. Otherwise the page
renders a refusal stating that nothing is shrunk, dropped or downgraded to fit — the
`INTACT_SOURCE_ONLY` rule, enforced where the user can see it.

## The parent run identifier

**Anchored to the viewport, not to the panel.** It is a fixed element in the lower-left, rendered
on every page that has a parent run — the run page and every child job page. It shows the
identifier as a link to the run, plus a `copy` button that writes the value to the clipboard and
briefly reports `copied`.

It survives a collapsed panel, which is asserted by test. It is the string a person quotes in a bug
report and an operator uses to find the run, so it matches the identifier in the event log and in
the stored evidence exactly.

The index and preflight pages have no run yet and render no identifier, rather than an empty
placeholder.

## Raw, Parsed, and side by side

Three controls on every child job page — `Raw`, `Parsed`, `Side by side` — as links, with
side-by-side the default. When a job submitted more than one preserved artifact, a second row of
links switches between them by filename.

| View | What it renders |
|---|---|
| Raw | the preserved bytes, escaped, exactly as SEC published them |
| Parsed | the model's structure in the model's own vocabulary |
| Side by side | both panes at once, each scrolling independently |

**The raw pane states its own window.** A filing can be megabytes, so the pane renders a bounded
window of characters around the point of interest and prints which characters it is showing out of
the total, plus the fact that the artifact is complete on disk. A silently truncated view of a
source of truth is the same defect as a silently truncated request.

**The parsed pane applies no taxonomy.** It renders whatever `type` and `title` the model produced,
states the node count and that no backend taxonomy is applied, and displays an unfamiliar label
rather than dropping it. A renderer that quietly omitted an unrecognised node would hide exactly
the finding the first experiments exist to produce.

**When the response will not parse there is no parsed view at all.** The pane says so and shows the
exact bytes the model returned instead, and the run is kept: it was billable and cannot be
regenerated for free.

### Source-reference links, and references that are not links

A resolved reference renders as a resolution badge plus the quoted text, linked to the raw view of
the artifact it was found in, carrying an **offset** and a **length** and anchoring at the
highlight. The raw pane opens its window around that offset and marks the range.

An **unresolved reference is marked and is deliberately NOT a link**. It renders its resolution
badge, its quote, and the words `not located in the preserved bytes`. A link would render it as
cited, and the whole point is that it is not.

The resolution vocabulary carried on each reference is `EXACT`, `WHITESPACE_NORMALISED`,
`TEXT_ONLY`, `AMBIGUOUS`, `UNRESOLVED`, `NO_SUCH_ARTIFACT`, `EMPTY_QUOTE`. Resolution is performed
by `packages/coverage_validation` against the PRESERVED BYTES, never against a re-fetched document
and never on the model's assurance.

## The exact model response and the reasoning content

Four things are shown on a child job page and never conflated:

```
RAW              the preserved bytes, escaped
PARSED           the model's structure — DERIVED
EXACT RESPONSE   the bytes the model returned, preserved before anything read them
VALIDATION       what the backend proved against the preserved bytes
```

The exact response is always rendered, labelled as authoritative wherever it and the parsed view
could disagree. When the provider returned reasoning content, the adapter separated it from the
visible answer and it renders in its own card with its character count reported — so reasoning is
never mistaken for the parse.

## The three warnings the parsed view must display

All three are IMPLEMENTED and all three appear at the point of use, in the same view as the content
they qualify. A warning placed only on an operations dashboard protects nobody.

| Warning | As built |
|---|---|
| `UNRESOLVED SOURCE REFERENCE` | Per reference: a resolution badge, the quote, and no link. Per job: the validation card states how many of the references resolved, how many were ambiguous and how many were unresolved |
| `IMAGE CONTENT NOT ANALYZED` | A job-level warning naming how many image-bearing members were filed, stating that they were NOT analysed and that the run makes no image-coverage claim, with the reason. A node that declares an image dependency also carries its own warning |
| `UNRESOLVED CONTENT` | The parsed pane renders a `Declared unresolved by the model` block listing what, where and why. `ValidationStatus` has NO `COMPLETE` member, so no view can round a parse up to complete |

**What is honest about the third warning, and what is still missing.** What renders today is the
model's own declaration of what it could not resolve, plus generic backend signals. A proven
range-by-range map of every human-readable source range against the accepted artifact is NOT built,
and no view claims one. That proof is PLANNED and is the COMPLETE-CONTENT-INVARIANT obligation in
`rules.md` section 3.

## The validation card

Rendered from `packages/coverage_validation` and never from the model's self-report:

```
STATUS         REVIEW_REQUIRED / PARTIAL / UNPARSEABLE / EMPTY, with its explanatory note.
               COMPLETE IS DELIBERATELY ABSENT — nothing measured here can establish it, and a
               status value that exists is a status value something eventually sets.
STRUCTURE      node count, table count
REFERENCES     resolved, ambiguous and unresolved counts against the reference total
ARTIFACTS      how many of the submitted artifacts were cited at all
RATIO          source characters to response characters
NUMERIC        how many reported numbers occur verbatim in the source, and how many tables have
               an arithmetically coherent column
TYPES          the labels the MODEL selected, with counts — reported, never validated
FINDINGS       each rendered as its own warning
```

## Review states and developer comments

**Two independent state machines**, both surfaced. Execution state and review state render as
separate badges on the child job page and as separate columns on the run page, because an execution
that finished says nothing about whether a human accepted it.

An unapproved artifact carries the marker `EVALUATION — not approved for reuse`, together with the
statement that approval records a judgement and activates nothing: no search consults the artifact
and no cache is populated. Reuse and caching do not exist yet, so the UI says so instead of
implying them.

The review control offers **only the transitions permitted from the current state**, computed by
`packages/evaluation_store`, with an optional note. An invalid transition is not rendered as a
disabled option a user has to guess about — it is not offered.

**Granular comments are IMPLEMENTED.** A comment carries a target type and a target identifier and
is attached to one of `child_job`, `parsed_node`, `table`, `source_reference`, `raw_response`,
`validation_warning` or `parent_run`. Each records its author, timestamp, run and job, and the
attempt version of the target it was written against, so a comment cannot silently migrate onto a
re-run's output. Comments render as escaped text and are never interpreted as instructions to any
model.

The configured reviewer identity is a LABEL supplied from ignored environment state, never a
personal name or address in tracked code.

## Progress, events and the run page

The run page lists every child filing job as its own row — job identifier, form, accession,
execution state, review state, validation status and settled spend — so a run over eleven filings
shows eleven rows and never one aggregate. It states in words that blank image, summary and
analysis selectors ran NO stage and that the parsing model was not borrowed to fill them.

Progress is a server-sent-event stream, resumable through `Last-Event-ID`, and the page also
renders the stored append-only event log as a table. **No provider data and no filing text crosses
the stream** — an event carries a kind, a child job identifier and a short message, and bodies stay
in the evaluation store. The stream terminates once every child job reaches a terminal state rather
than holding a connection for ever.

Cancellation cancels only jobs that have not yet been invoked. A RUNNING job is deliberately not
cancelled: the provider call is billable from the moment it is issued, and marking it cancelled
would hide a charge the ledger still has to settle.

## Visual design, as built

Light mode. Light and dark grey surfaces, a dark grey left panel and dark grey table headers, and
soft translucent blue, green, amber and red accents defined as one small set of custom properties.

**No fully saturated large colour blocks.** Every accent is a translucent fill, a thin rule or a
small badge over grey. The Run button is the strongest accent on the page and is still
semi-transparent. Status is never carried by colour alone: every badge and every warning prints its
own text.

The stylesheet and the one script are Python module constants served from their own routes, not
files on disk. That keeps `packages/` free of non-Python files, puts both assets under the linter
and the coverage measurement, and removes an entire class of defect — there is no static-file route
and therefore no path to traverse. They are not inlined into the page, because inline style and
script would force `unsafe-inline` into the content security policy, and that policy is the reason
a preserved filing can be displayed at all without a sanitizer.

## Security posture, as built

```
LOOPBACK BY DEFAULT   binding beyond loopback REQUIRES a development secret, and the settings
                      refuse to construct the unsafe combination
SESSION               server-side, keyed by an opaque random cookie value carrying no claim a
                      client could forge or replay across a restart
CSRF                  every state-changing request carries a token bound to the session
SAME ORIGIN           no CORS headers are emitted at all; the absence is the policy
CSP                   default-src 'none', with one stylesheet and one script from this origin
CREDENTIALS           nothing AWS-shaped is ever placed in a response, and there is no
                      browser-to-Bedrock path to open by accident
```

Whenever HTTPS is not configured the page prints a local-development-mode note stating that it
makes no production security claim, rather than implying a posture it does not have. This is not
multi-user identity management and does not pretend to be; that stays deferred to Phase 6.

## The multipart surface — IMPLEMENTED 2026-08-03, Phase 2.1

A multipart parse is a dozen calls under one child filing job, and a list of runs is not a review
surface for it. Three views, each answering a different question, and none of them collapsing into
another.

**THE CALL HIERARCHY** — `/runs/{run}/jobs/{job}/multipart`. Every call in the order the MODEL's own
plan put them, indented by the model's own parent relationship, each row showing its kind, queue
state, prompt version, output tokens, configured cap, stop reason, cost and validation. The header
carries the plan identifier, the planned part count, the state counts, the three operational limits
and all three spending ceilings with what remains of each.

**THE PER-CALL REVIEW PAGE** — `/runs/{run}/jobs/{job}/tasks/{task}`. The Phase 2 review page one
level down: raw, parsed and side-by-side over the preserved filing, every citation checked against
the original bytes, plus the exact compiled request brief and the exact response. A truncated call
additionally shows the cap it reached, the tokens it produced, its exact partial output, and that
the partial output is EVIDENCE and is not merged into the parse.

**THE ASSEMBLED VIEW** — `/runs/{run}/jobs/{job}/assembled`. The parts in the model's order, under
the model's titles, each linking back to the response that produced it. **It says on the page that
it is an index**: no title renamed, no content merged, no table moved, no part dropped.

### Rules this surface follows

```
A TRUNCATED CALL IS SHOWN AS A BRANCH, NEVER AS A FAILED MODEL. Phase 2 labelled whole candidates
truncated because one response hit a cap. A truncated call here shows its cap, its partial output,
the replanning call it caused, the subparts that came out of that, and whether the branch finished.

EVERY MODEL-CHOSEN STRING IS ESCAPED, NEVER INTERPRETED. A part identifier and a title are strings
a language model wrote after reading an untrusted filing. They are rendered as text through the
same escaping a filing gets, and a model-chosen identifier never reaches a storage key.

EVERY QUEUE CONTROL IS A FORM POST WITH A TOKEN, NEVER A LINK. Resume, unblock, advance, run
reconciliation, retry one call and cancel a branch each spend money or unblock something that will,
and a link is something a browser can be made to follow.

NOTHING ON THE PAGE SPENDS MONEY BY BEING OPENED. A restart marks interrupted work and stops; the
page shows it and waits for a person.

THE THIRTY HISTORICAL SINGLE-RESPONSE RUNS STILL OPEN, and the multipart pages report honestly
that such a job has no plan and no assembly rather than failing.
```

## What the parser-review UI deliberately does NOT do

Every item here is a beta-UI requirement that the implemented surface does not satisfy. None is a
defect in the parser-review UI; all remain PLANNED and are specified in the beta-UI section below.

```
NO ENTITY TYPEAHEAD BEYOND THE LOCAL CORPUS   search is a submitted form over the preserved
                                              research corpus. No live typeahead, no SEC-wide
                                              catalog, no historical-ticker or alias index.
NO SYNCHRONIZED SCROLLING                     side-by-side renders two independent panes.
                                              Following a source reference is a page load
                                              anchored at the highlight, not a linked scroll.
NO SUMMARY VIEW                               no summary artifact exists. No summary model was
                                              invoked, and the summary stage raises rather than
                                              running.
NO DEEP DIVE                                  no analysis/chat surface, no session, no scope
                                              badge, no budget meter, no transcript.
NO FISCAL-YEAR TIMEFRAME                      filing-date bounds only; no fiscal-year resolution,
                                              no derived-quarter labelling.
NO CHARTS, NO ISSUER OVERVIEW, NO TIMELINE    none of the investor-facing surfaces exist.
NO PER-ROW COMPATIBILITY VERDICT              compatibility is shown per filing at preflight, not
                                              on each selector row.
NO REUSE OR CACHING                           approval records a judgement and activates nothing.
NO PERSISTENCE BEYOND THE EVALUATION STORE    runs live in the gitignored var/evaluation-runs/.
                                              There is no product database, no schema, no ORM,
                                              no migration, no index and no Redis.
```

## Acceptance criteria, current state

| Criterion | State |
|---|---|
| Parsing is the only required role | IMPLEMENTED — a run starts with all three optional selectors blank |
| Blank means skip, visibly | IMPLEMENTED — `None — skip this stage` is a labelled option on all three optional roles |
| No inferred model | IMPLEMENTED — a blank role runs no stage; the parsing model is never borrowed |
| Disabled entries state a reason | IMPLEMENTED — every unavailable row carries its concrete reason inline |
| Multimodal badge on every row | IMPLEMENTED |
| Image selector disabled, not hidden | IMPLEMENTED — with the one-line explanation |
| Button gating | IMPLEMENTED — entity plus an available parsing model; the unmet condition is stated |
| Run ID survives collapse | IMPLEMENTED — asserted by test |
| Collapse preserves selections | NOT MET — the collapse control drops the query string that carries them |
| Broken reference is visible | IMPLEMENTED — marked, and deliberately not a link |
| Unanalyzed images are declared | IMPLEMENTED — with the member count and the reason |
| Unresolved content is listed | PARTIAL — the model's declaration renders; a proven range map is PLANNED |
| Nothing is ever labelled complete | IMPLEMENTED — `ValidationStatus` has no `COMPLETE` member |
| Evaluation is not reuse | IMPLEMENTED — and no reuse path exists to violate it |
| Cost is bounded before spend | IMPLEMENTED — worst case, ceiling and refusal at preflight |
| Side by side stays synchronized | NOT IMPLEMENTED — independent panes |
| Reading invokes no model | IMPLEMENTED — every view is served from stored evidence |
| First measured parse figures | PENDING — no parse-quality, token or cost measurement is recorded |

---

# THE BETA UI — AUTHORITATIVE

NOT IMPLEMENTED. No frontend code exists and none is generated by this document. This section is
specification text only.

> **FORWARD NOTE, 2026-08-03.** The paragraph above is kept as written and its verdict on the beta
> UI still stands: PLANNED, and not one screen of it is built. Its second clause is now narrower
> than it was — frontend code does exist in the repository, but it is the Phase 2 parser-review UI
> specified above, which is a developer evaluation surface and no part of the beta UI. Where a
> requirement below is already satisfied by that surface, the parser-review section says so
> explicitly; everything else here remains PLANNED.

## Layout

```
+---------------------+--------------------------------------------------+
|  SEARCH PANEL   [<] |  DASHBOARD                                       |
|  persistent,        |  fills the remaining viewport                    |
|  vertical, left     |                                                  |
|                     |  [ RAW ] [ PARSED ]  [ SIDE-BY-SIDE ]            |
|  Entity / ticker    |                                                  |
|  Timeframe          |  Models and cost | Deep Dive                     |
|  Parsing model  *   |                                                  |
|  Image model        |  Streaming progress while a run is active        |
|  Summary model      |                                                  |
|  Analysis model     |                                                  |
|  [ Search / Run ]   |                                                  |
|                     |                                                  |
|  run 7f3c… [copy]   |                                                  |
+---------------------+--------------------------------------------------+
   * required                lower-left: parent run ID, always visible
```

The left panel is **persistent** and collapses via an arrow control in its top-right corner. When
collapsed, a hamburger control reopens it. The dashboard expands to fill the space either way.

**Collapsing the panel must not destroy run state.** Selections, an in-flight run, streaming
progress, the parent run identifier and any unsaved developer comment survive collapse, reopen and
repeated toggling. Collapse is a viewport control and nothing else. Re-expanding restores the same
selections, not defaults.

## The search panel

**Entity / ticker search.** A single typeahead matching current name, former names, SEC filer name,
current ticker, historical ticker and alias. Served from the minimum beta catalog delivered in
Phase 3 — this view depends on Phase 3, never on the Phase 8 universe-scale expansion. An entity
with no qualifying filing never appears: showing a symbol the product cannot serve is worse than
showing nothing. Results display the authoritative name resolved from the CIK, and a sampling label
is never displayed as identity. Selecting a result resolves to a CIK; all later navigation is by
CIK.

**Timeframe.** **Bounded below by the entity's earliest known qualifying filing**, which the Phase 3
catalog records, so the control cannot offer a range the product cannot serve. The lower bound is
displayed, not merely enforced — the user sees *why* an earlier year is unavailable. The control
labels the span it actually resolved to. Fiscal years, never calendar years.

**Four independent model selectors** — parsing, image, summary, analysis/chat. Each is populated
from the live-discovered catalog and each is chosen separately. **None defaults from another and
none is inferred.**

```
Parsing         REQUIRED. A run cannot start without it.
Image           OPTIONAL. May be left blank.
Summary         OPTIONAL. May be left blank.
Analysis/chat   OPTIONAL. May be left blank.
```

A blank optional role is a legitimate, complete configuration and the UI states what it means
rather than warning about it: leaving Summary blank produces a parse with no summary artifact;
leaving Image blank means image-bearing content is not analyzed and the parse carries the
corresponding warning; leaving Analysis blank means Deep Dive is unavailable for that run. The
product never silently substitutes a model for an empty role, and never reuses the parsing model to
fill one.

When the selected **parsing model is multimodal**, the image selector stays **visible but disabled**
with a one-line explanation that the parsing model handles images itself. It is not hidden: hiding
it would make the four-role model look like three.

### What every model dropdown entry displays

```
Label                     the model's display name
Provider                  who serves it
Version                   the verified version string, or "unverified"
Availability              available / unavailable, from live discovery
Region                    the region it was discovered in
Text capability           yes / no
Image capability          yes / no
Multimodal badge          a VISIBLE badge on any entry with both text and image capability
Context limit             input tokens, shown ONLY when verified
Output limit              output tokens, shown ONLY when verified
Compatibility             fits / does not fit the selected filing set under INTACT_SOURCE_ONLY
Cost                      per-token or per-run cost, shown ONLY when verified
```

**An unverified field is displayed as unverified, never as blank and never as a guess.** A missing
context limit reads `context limit not verified`, which is a different statement from a large
number.

**A disabled entry always states a concrete reason** on the row itself — `unavailable in this
region`, `no image capability, required by this filing set`, `context limit 128k, this filing set
measures 412k tokens`, `version not verified`. A greyed row with no reason is not an acceptable
state.

Compatibility is evaluated against the **selected entity and timeframe**, so changing the timeframe
re-evaluates every dropdown. A model compatible with one filing set may be incompatible with a
wider one, and the UI must show that transition rather than silently keeping a stale verdict.

## The Search / Run button

One button starts a run. Its presentation and its enablement are both specified.

**Presentation.** Semi-transparent, opaque-ish light blue — never a harsh, fully saturated solid
block. It is the strongest accent on the page and it earns that by contrast with soft surroundings,
not by intensity.

**Enablement.** Disabled until *all* of the following hold:

```
an entity is resolved to a CIK
a timeframe is valid and inside the entity's available range
a PARSING model is selected
the parsing model is compatible with the selected filing set
```

The optional roles never affect enablement. A disabled button states which condition is unmet.

**Warnings before the run, when known.** The button area shows a cost estimate when cost is
verified, and a compatibility warning when a pairing is questionable. When cost is not verified it
says so — an unverified cost is never rendered as a number. A warning does not block a run that
satisfies the enablement conditions; it informs the user who is about to spend.

## The parent run ID and child job status

**A visible, copyable PARENT RUN ID sits in the lower-left of the viewport.** One run over one
entity and timeframe has one parent identifier, and every child filing job carries it.

- It is displayed from the moment the run is created, in full or truncated with the full value on
  hover, with a copy control beside it.
- **It does not disappear when the search panel collapses.** It is anchored to the viewport, not to
  the panel. A collapsed panel still shows it.
- It matches the identifier in the logs and in the artifact records exactly, so a user can quote it
  in a bug report and an operator can find the run.

**Child filing-job status** is listed per filing in the run, each with its own job identifier and
terminal state, so a run over eleven filings shows eleven rows rather than one aggregate. A run is
never displayed as complete while a child job is unfinished.

**Streaming progress.** While a run is active the dashboard streams progress per child job.
Reconnection resumes rather than restarting. **Opening a completed result invokes no model at all**
— it is served from stored artifacts.

## RAW, PARSED, and side by side

Three controls, one reading surface:

| Control | Behaviour |
|---|---|
| **RAW** view | The preserved SEC artifact exactly as filed, with its hash and byte count |
| **PARSED** view | The accepted parse, rendered from its filing-native labels |
| **Toggle** | Switches between RAW and PARSED in place, preserving scroll position where a source reference allows it |
| **SIDE-BY-SIDE** | Opens both panes at once, synchronized by source reference |

**Source-reference links.** Every parsed node links to the raw evidence it came from. Selecting a
parsed node highlights its source range in the RAW pane; in side-by-side, both panes move together.
The link is to the preserved bytes, never to a re-fetched document.

A summary is a third, separate artifact with its own view. **Three distinct artifacts, three
distinct views**: a summary never silently stands in for a parse, and a parse never silently stands
in for the source.

**Rendering the parsed view must not assume a fixed taxonomy.** A node carries whatever label the
filing and the model produced. The renderer displays labels; it does not validate them against an
enum, and an unfamiliar label is displayed, not dropped.

### Warnings the parsed view must display

```
UNRESOLVED SOURCE REFERENCE   a parsed node claims a source range that cannot be resolved
                              against the preserved bytes. The node is shown, marked, and its
                              unresolvable reference is named. It is never rendered as cited.
IMAGE CONTENT NOT ANALYZED    the filing set contains image-bearing content and no image model
                              was selected, or the parsing model has no image capability. States
                              which documents are affected.
UNRESOLVED CONTENT            the parse does not account for every human-readable source range.
                              The filing shows PARTIAL or REVIEW_REQUIRED with the unresolved
                              ranges listed and positioned. It is never rounded up to complete.
```

All three are shown at the point of use, in the same view as the content they qualify. A warning
placed only on an operations dashboard protects nobody.

## Approval, rejection, and developer comments

**A parsed artifact is an EVALUATION artifact until it is explicitly APPROVED.** The dashboard is
where that decision is made, and the UI must never blur the two states.

| Element | Behaviour |
|---|---|
| Evaluation banner | Every unapproved artifact carries a persistent `EVALUATION — not approved for reuse` marker in both RAW-linked and PARSED views |
| Approve | Explicit control. Records the approver, the timestamp and the parent run ID |
| Reject | Explicit control. Requires a reason and keeps the artifact readable |
| Reuse | Only approved artifacts are reusable and cacheable. An evaluation artifact is never served as an accepted parse |
| Re-run | Available from either state, and always creates a new parent run ID rather than overwriting one |

**Granular developer comments are required.** A comment can be attached to the run, to a single
child filing job, to an individual parsed node, or to a specific warning — not to the run alone.
Each comment records its author, timestamp, parent run ID, and the exact target it was attached to,
and it survives panel collapse and view switching. Comments are data: they are displayed as text
and never interpreted as instructions to any model.

## Source acquisition, as the UI shows it

Raw source storage is checked before EDGAR. When a run is served from already-preserved bytes the
UI says so — `source already held, no SEC request` — because a user watching a run should be able
to tell a cache read from a live fetch. A live fetch shows the rate-limited progress it actually
made.

## Visual design

Light mode. Light and dark grey surfaces. Dark grey menus and tables. Soft translucent blue and
green accents.

**No fully saturated large colour blocks.** Accent colour arrives as translucent fills, thin rules
and small badges over grey, never as a solid panel of colour. The Search / Run button is the single
strongest accent on the page and is still semi-transparent. Status is never carried by colour alone:
every marker has a text equivalent.

## Error states the UI must express

```
INTACT-SOURCE INCOMPATIBILITY   this filing's complete source set does not fit the selected
                                parsing model. Shows measured bytes, estimated tokens and the
                                model's limit, and lists compatible alternatives THE USER may
                                pick. The product never substitutes a model silently.
CAPABILITY ERROR                the selected model does not support a required modality
MODEL UNAVAILABLE               live discovery did not return the model
BUDGET EXCEEDED                 the run would exceed the authorized ceiling
PARTIAL / REVIEW_REQUIRED       coverage validation did not prove completeness
RUN FAILED                      names the failing child job, keeps the parent run ID visible,
                                and offers the preserved source and the SEC link regardless
```

## Security

**No executable model-generated UI.** Model output is data and is rendered as text; it is never
evaluated, never injected as markup, and never used to construct a component.

The browser never calls a model provider, never holds a credential, and never learns a provider
endpoint. Filing text is untrusted data: instructions found inside a filing are ignored and
reported.

## Deployment

LAN deployment for the beta. Single user. No public exposure.

## Acceptance criteria for the beta UI

All PLANNED. None is implemented and none has been run.

> **FORWARD NOTE, 2026-08-03.** That sentence is kept and is still correct **for the beta UI** —
> none of these criteria has been graded against a beta screen, because none exists. Several of the
> underlying behaviours are nonetheless already IMPLEMENTED in the Phase 2 parser-review UI, and
> the current state of each is recorded once, in the table at the end of
> `THE PHASE 2 PARSER-REVIEW UI — IMPLEMENTED` above. A criterion satisfied there is not thereby
> satisfied here.

| Criterion | Assertion |
|---|---|
| Collapse preserves state | Collapsing and reopening the panel loses no selection, no in-flight run and no unsaved comment |
| Run ID survives collapse | The parent run ID remains visible and copyable with the panel collapsed |
| Parsing is the only required role | A run starts with all three optional model selectors blank |
| No inferred model | Leaving a role blank never causes another role's model to be used for it |
| Disabled entries state a reason | No dropdown row is disabled without a concrete displayed reason |
| Unverified is not blank | An unverified context limit, version or cost renders as unverified, never as a number |
| Button gating | The Search / Run button is disabled until entity, timeframe and parsing model are all valid |
| Side by side stays synchronized | Selecting a parsed node moves the RAW pane to its source range |
| Broken reference is visible | A parsed node whose source range does not resolve is marked, not rendered as cited |
| Unanalyzed images are declared | A run with image-bearing content and no image role shows the warning and names the documents |
| Unresolved content is listed | An unresolved range appears with its position, and the filing is not labelled complete |
| Evaluation is not reuse | An unapproved artifact is never served as an accepted parse |
| Reading invokes no model | Opening a completed run — every view, both panes, every node — records zero model invocations |
| Timeframe floor is honest | The control cannot select a year earlier than the entity's earliest qualifying filing, and states the bound |

---

# HISTORICAL — describes the withdrawn design

> **Everything below this heading is retained as a record and is NOT authoritative.** It describes
> the footnote-centric dashboard built on the deterministic semantic parser, the five-layer coverage
> model, the XBRL fact lake, the curated metric definitions and the application database — all
> withdrawn by `docs/adr/ADR-0016-corpus-first-model-first-architecture.md` and deleted from the
> active tree on 2026-08-03 by
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`. API fields, schema
> tables, directories and companion specifications named below no longer exist. Nothing here is a
> requirement on the beta UI.

> **Corrected in Sprint 4.1.** An earlier version made the footnote index the filing page, and its
> coverage display counted footnotes alone — so a filing whose MD&A was never extracted would have
> rendered as fully processed. The filing view was then specified as a rendered canonical hierarchy
> covering the whole document, with coverage displayed as five separate layers.

## The governing constraint

```
NO-INFERENCE-ON-READ. Every screen, state, and interaction in this section is served entirely
from stored data. Nothing here invokes a language model. The only entry point that spends model
budget is the explicit Deep Analysis action in section 8.
```

A backend architecture does not define a product. This document defines what the investor sees,
including the states most specifications omit: partial, low-confidence, in-progress, and refused.

---

## 1. Issuer search

**Entry.** A single input accepting a ticker or a company name.

**Rule.** A ticker that has never filed a 10-K or 10-Q does not appear in results or
autocomplete. Showing a symbol the product cannot serve is worse than not showing it.

| State | Presentation |
|---|---|
| Match found | Ticker, legal name, exchange, fiscal year end |
| Multiple issuers share a ticker | Disambiguation list showing each issuer's name and the date range it held the ticker. Never auto-select. `BBBY` is two companies |
| Former name matched | Result shows the current legal name with "formerly *X*" |
| Delisted but previously filed | Shown, labelled "no longer listed", still fully browsable |
| Foreign private issuer | Not shown as a result. If typed exactly, an inline notice states that the issuer files Form 20-F and that coverage is limited to domestic 10-K and 10-Q filers |
| No match | "No SEC filer found for *X*." No suggestions invented |

Selecting a result resolves to a CIK. **All subsequent navigation is by CIK.** The ticker is a
display label from that point on.

---

## 2. Issuer overview

Above the fold: legal name, ticker with exchange, CIK, SIC description, fiscal year end, and a
**coverage badge** (section 6).

Then, in order: the timeframe control, the financial charts, and the filing timeline. Opening a
filing from the timeline leads to the **filing view** in section 6A, which was the withdrawn
design's main reading surface.

---

## 3. Timeframe behaviour

One control, five options, mapping exactly to the `range` API parameter:

```
Current year    Previous year    5 years    10 years    All-time
```

**"Year" always means the issuer's fiscal year.** Apple's fiscal 2025 ends in September;
comparing it to a calendar year would be wrong. The control labels the actual span it resolved
to, for example `FY2021 – FY2025`, so the user never has to guess.

| Case | Behaviour |
|---|---|
| Current year is partial | Renders with the label "FY2026 (in progress, 2 of 4 quarters filed)" |
| Requested range exceeds available history | Renders what exists and states the true first year: "Data begins FY2011" — never silently shortens the axis |
| Numeric history shorter than document history | The chart states its own boundary: "Charts begin FY2011; filings and footnote summaries reach 1994" |

**Annual/quarterly toggle.** Independent of range. Annual is the default.

- Quarterly series label a derived fourth quarter explicitly: `Q4 FY2025 (derived)`, with a
  tooltip stating that no Q4 10-Q exists and Q4 is computed as FY minus Q1 minus Q2 minus Q3.
- A 52/53-week fiscal year is flagged where it distorts comparison: `FY2023 (53 weeks)`.
- Cash-flow metrics are presented as year-to-date or discrete-quarter, labelled, never mixed.

---

## 4. Financial charts

Deterministic, from published datasets. Never a model call. The datasets, the fact lake and the
curated metric-definition set this section depended on were all deleted on 2026-08-03.

| Element | Behaviour |
|---|---|
| Series selection | Curated metrics only, from a stored curated definition set — the definition format and its files are withdrawn |
| Point detail | Value, unit, scale, period start and end, duration in months, and the source accession |
| Click-through | Navigates to the footnote that explains that line item, when one is associated |
| Comparability break | A visible marker on the segment where the concept mapping changed, with the reason on hover. The line is not silently redrawn as if nothing happened |
| Restated period | Shows the current value with an indicator that an earlier filing reported a different figure, and links to both |
| Missing period | A gap. Never interpolated, never zero-filled |
| Derived value | Distinct visual treatment plus the `(derived)` label |

**Every number is traceable.** Point detail always exposes the path to `(accession, concept,
context, unit, period)`.

---

## 5. Filing timeline

Reverse-chronological, grouped by fiscal year.

Each entry shows: form type, fiscal period, filing date, period end date, and a per-filing
processing state.

| Marker | Meaning |
|---|---|
| `10-K` / `10-Q` | Form type |
| `10-K/A` | Amendment. Expands to show what it patches. **Never replaces the original in the list** — AMD's 545 KB amendment against a 14 MB original is not a superseding document |
| Era badge | Only where it changes what the user can expect, for example "pre-XBRL: no charts" |

Every entry links to the original SEC document at its authoritative URL.

---

## 6. Coverage and processing states

The single most important honesty requirement in the product: **partial coverage is never
rendered as complete.**

### Five layers, displayed separately

From `/filings/{accession}/coverage`. **There is no single filing "complete" flag, and the UI must
never synthesize one.** A filing can be acquisition-complete and extraction-partial, or
submission-complete with its Part III disclosures unresolved. Collapsing the layers is how a
dashboard tells an investor a filing was fully processed while a third of it lives elsewhere.

```
Documents        16 of 16 filed documents acquired
Filed content    every human-readable block accounted for
Disclosure       Items 10–14 incorporated from the 2026 proxy statement — not yet processed
Footnotes        13 of 13 extracted · 13 of 13 summarized
Summaries        61 of 67 required units summarized
```

| Layer | Source field | Presentation when short |
|---|---|---|
| Acquisition | `acquisition.status` | "3 of 16 filed documents missing", each named |
| Filed content | `submission_content.status` | "4 blocks unresolved" with a link to them |
| Disclosure | `disclosure.status` | Names the referenced document and what it covers |
| Footnotes | `footnotes.status` | *m* of *n*, missing notes listed by number and title |
| Summaries | `summaries.status` | *m* of *n*, missing units listed by title |

**Unresolved content is shown as unresolved, never as absent.** A block the extractor could not
place appears in the coverage panel with its position in the document. An investor cannot
distinguish content that does not exist from content the pipeline dropped, so the product must.

| State | Presentation |
|---|---|
| `SUBMISSION_COMPLETE` + `DISCLOSURE_PARTIAL` | Both shown. This is a normal, correct state for a 10-K and is never rounded to "complete" |
| `REQUIRES_REVIEW` | Filing is browsable; affected units carry a review marker |
| `FAILED` | Filing listed, marked unprocessed, original SEC link still offered |
| `NOT_STARTED` | "Queued for processing" |

The issuer-level badge summarizes `Coverage: 47 of 51 filings fully processed`. Clicking it lists
the exceptions **by layer**, so "fully processed" cannot hide a filing that is merely
footnote-complete. It is never rounded up.

---

## 6A. The filing view

**The filing page is a rendered canonical hierarchy, not a footnote index.**

### Navigation tree

Rendered from `/filings/{accession}/contents/tree` in **filed order**, at whatever depth the
filing has. The tree is **rendered from stored data, never from a hardcoded list of section
names** — a 1994 10-K, a 10-Q, and a 2025 10-K have different structures, and an issuer that
titles its sections unusually must still render correctly.

A typical 10-K renders as:

```
Cover page
Part I
  Item 1   Business
  Item 1A  Risk Factors
  Item 1B  Unresolved Staff Comments
  Item 1C  Cybersecurity
  Item 2   Properties
  Item 3   Legal Proceedings
  Item 4   Mine Safety Disclosures
Part II
  Item 5   Market for Registrant's Common Equity
  Item 7   Management's Discussion and Analysis
  Item 7A  Quantitative and Qualitative Disclosures About Market Risk
  Item 8   Financial Statements and Supplementary Data
    Consolidated Statements of Operations
    ... every statement ...
    Notes to Consolidated Financial Statements
      Note 1  Summary of Significant Accounting Policies
      ... every footnote, individually ...
  Item 9A  Controls and Procedures
  Item 9B  Other Information
Part III
  Item 10  Directors, Executive Officers and Corporate Governance   [incorporated by reference]
  ... Items 11–14, each marked ...
Part IV
  Item 15  Exhibit and Financial Statement Schedules
Financial schedules
Exhibit index
Exhibits              each filed exhibit, individually
Certifications        each officer certification, individually
Signatures
```

Nothing in that list is hardcoded. It is what the stored hierarchy contained for one measured
filing, and a filing with different structure renders differently.

### What the user can do

| Action | Behaviour |
|---|---|
| Read the filing summary | The aggregate from `/filings/{accession}/summary`, built from validated unit summaries |
| Navigate any unit | Every content unit is addressable and linkable |
| Read a unit summary | Stored; **no model call** |
| Expand source evidence | The extracted source blocks for that unit, with their dispositions |
| Open the authoritative source | The SEC document, anchored where an anchor exists |
| View tables | Rendered from stored structure, original available |
| See coverage | The five layers, per filing and per unit |
| See unresolved content | Listed, with position; never hidden |
| See incorporated references | What is incorporated, from where, and whether it is resolved |
| Open the footnote index | The specialized view in section 7 |
| Start Deep Analysis | From a content unit, a footnote, a Part, an Item, the filing, or a timeframe |

### Unit presentation

```
Item 7  Management's Discussion and Analysis        [ Deep Analysis ]

<plain-language summary>

Key figures      value, unit, scale, period — each linked to its source
Tables           rendered from stored structure, original available
Source           every extracted block, individually addressable
Original         link to the SEC document
Coverage         106 blocks assigned · 0 unresolved
```

An **oversized unit** whose summary was built by hierarchical chunking states so, and its
chunk-level summaries are expandable. An aggregate is never presented as though one pass produced
it.

An **incorporated Item** renders its incorporation statement, the referenced document, and its
resolution status — never a blank section and never a claim that nothing was disclosed:

```
Item 11  Executive Compensation                     [ incorporated by reference ]

This Item is disclosed in Apple Inc.'s definitive proxy statement for the 2026 annual
meeting, filed 2026-01-08 (0001308179-26-000008).

Status   acquired, not yet processed — this filing is not disclosure-complete
Source   <link to the referenced filing>
```

---

## 7. Footnote presentation

**One specialized view over `FINANCIAL_STATEMENT_FOOTNOTE` units.** It survived the Sprint 4.1
correction unchanged, because footnotes kept their own dedicated coverage guarantee. It was no
longer the only content index.

### The index

Every canonical footnote for the selected filing, in filed order, showing number as displayed,
title, a one-line summary, and any status marker. **The every-footnote requirement is a UI
requirement too: the index is never filtered by a model's opinion of materiality.**

Optional user-applied filters (`topic`, `classification`, `deep_dive_recommended`) narrow the
view. When any filter is active the header states `Showing 4 of 13 footnotes`, so a filtered
view is never mistaken for the whole set.

### An expanded footnote

```
Note 9 — Debt                                    [ Deep Analysis ]

<plain-language summary>

Key figures      value, unit, scale, period — each linked to its source
Tables           rendered from footnote_table, with the original HTML available
Source           parent block plus every child block, individually addressable
Original         link to the SEC document, anchored to this note
Compare          this note across periods  →  section 9
```

Citations resolve to a source block, a table cell, or a filed fact. **A summary is never itself
offered as evidence for a number.**

### Low-confidence presentation

Confidence is a product-visible property, not an internal one.

| Condition | Presentation |
|---|---|
| Summary passed every validation | No marker. The default |
| `grouping_method` is a fallback stage (6–9) | Note carries "grouping inferred" with the method and what else was considered, from `competing_candidates` |
| `grouping_method` is `model_adjudication` | "Grouping decided by model adjudication", with the model identifier and prompt version |
| `completeness_confidence` below the configured floor | Filing-level banner: "Some structure in this filing could not be determined with confidence" |
| Summary `validation_status` is `REQUIRES_REVIEW` | Summary is **withheld**; the footnote appears with its title, its source text, and "summary awaiting review". Never shown as accepted |
| `reconciliation_status` is `MISMATCH` | Banner naming both numbers: "Table of contents indicates 24 footnotes; 22 were extracted" |
| Source block orphaned | Listed under "unattached source material" on the filing, not hidden |

The rule behind all of these: **uncertainty is surfaced at the point of use, in the same view as
the content it qualifies.** A confidence figure on an internal dashboard protects nobody.

---

## 8. Deep Analysis entry points

Six, matching the six scope types: from a content unit, a footnote, a Part, an Item, the filing,
or a timeframe selection. Each is an explicit, labelled action. Nothing starts a session
implicitly.

**Before creation** the user sees what they are authorizing. A filing-scoped session covers the
**complete processed filing**, and the disclosure states so rather than naming footnotes alone:

```
Deep Analysis
Scope     Apple Inc. (CIK 0000320193) — FY2025 Form 10-K
Covers    the complete processed filing: 67 content units across 4 Parts and 23 Items,
          5 financial statements, 13 footnotes, exhibits, certifications and signatures,
          plus filed facts and derived metrics
Excludes  Items 10–14, incorporated from the 2026 proxy statement and not yet processed
Limits    20 turns, $2.00 maximum
Cannot    retrieve data for any other issuer
[ Start ]  [ Cancel ]
```

A narrower scope names what it narrowed to:

```
Scope     FY2025 Form 10-K — Item 1A Risk Factors
Covers    106 source blocks in this Item and its subsections
```

**What a session cannot reach is stated, not merely enforced.** A filing whose disclosure is
partial says which Items are out, so a user does not read a confident answer about executive
compensation from a corpus that never contained it.

**During the session:**

| Element | Behaviour |
|---|---|
| Scope badge | Persistent, naming issuer and period. Never collapsed or hidden |
| Budget meter | Turns used and spend against limit, updated per turn |
| Citations | Every material claim links to the original source |
| Selected-evidence disclosure | An all-history session states plainly that it reasoned over selected evidence and which periods it examined |
| Suggested follow-ups | Only questions answerable within the existing scope |

**Out-of-scope request:**

```
That question is about Microsoft. This session is locked to Apple Inc.
Within this session I can compare Apple across FY2021–FY2025.
To analyse Microsoft, start a new session from that company's page.
```

Refused in one sentence, states what *is* possible, and — when the deterministic detector caught
it — **costs nothing.** The budget meter does not move. That is the visible proof of
requirement 13.

**Budget exhaustion:**

```
This session has reached its limit of $2.00.
The transcript remains available. Start a new session to continue.
```

The session ends cleanly. It never silently degrades to a weaker model or a shorter context.

**Session restoration.** An expired or closed session reopens as a **read-only transcript** with
every citation still resolving. Continuing requires a new session, which re-derives scope from
current data. The UI states this rather than appearing broken.

---

## 9. Same-footnote comparison across periods

Journey 3, specified in the withdrawn footnote documentation set. From any footnote: "compare this
note across periods".

Presents the same footnote topic for each period in the selected range, side by side, with:

- the summary for each period
- a `changed` / `unchanged` / `absent` / `new` marker per period, computed deterministically
- for changed periods, what changed, from stored comparison records
- links to each original source

**No model call.** The comparison is precomputed and stored. This is what backs the
`classification=changed` filter in section 7.

---

## 10. Cross-cutting states

| State | Presentation |
|---|---|
| Issuer never filed | Unreachable by design — excluded from search |
| Issuer exists, no filings processed yet | Identity and timeline render; charts and footnotes show "queued for processing" |
| Data being republished | Last published version continues to serve. The pointer flip is atomic; the user sees no partial dataset |
| API error | Plain statement of what failed and what still works. Never a blank chart implying zero |
| Empty filter result | "No footnotes match this filter" with a one-click reset |

---

## 11. Accessibility and presentation floor

Charts are readable without colour alone: markers and labels carry the meaning that colour
reinforces. Every status marker has a text equivalent. Tables are navigable by keyboard and
carry proper headers. Numbers are never conveyed by position alone.

This floor is not withdrawn — it is restated as a requirement on the beta UI in the authoritative
section above.

---

## 12. Acceptance tests

Withdrawn with the design they graded. Every one of them asserts against deleted API fields or
deleted schema tables, and none is implemented.

| Test | Assertion |
|---|---|
| `test_dashboard_session_invokes_no_model` | A full browse — search, overview, chart, timeframe change, filing open, **every content unit expanded**, every footnote expanded, filter applied — records **zero** `llm_invocation` rows |
| `test_filing_view_renders_the_stored_hierarchy` | The tree matches the persisted `filing_content_unit` rows in filed order, at the filing's own depth |
| `test_filing_view_is_not_hardcoded_to_one_structure` | A 10-Q, a 10-K, and a pre-2001 filing each render their own structure |
| `test_coverage_layers_render_separately` | The five layers are individually visible; no synthesized single "complete" appears |
| `test_submission_complete_with_disclosure_partial_renders_both` | A 10-K in that state shows both, and is never labelled complete |
| `test_unresolved_content_is_listed_not_hidden` | An unresolved block appears with its position |
| `test_incorporated_item_states_its_dependency` | Item 11 renders the referenced document and resolution status, not a blank section |
| `test_oversized_unit_discloses_chunked_summary` | An aggregate summary names its leaf chunks |
| `test_partial_filing_renders_honestly` | A filing with 12 of 13 summaries shows *12 of 13* and lists the thirteenth as awaiting review |
| `test_missing_footnote_is_listed_not_omitted` | The unsummarized footnote appears in the index with its title |
| `test_exhibits_and_certifications_are_navigable` | Each filed exhibit and certification is its own addressable unit |
| `test_never_filed_ticker_absent_from_search` | A symbol with no 10-K or 10-Q returns no result |
| `test_reused_ticker_disambiguates` | `BBBY` offers both issuers with date ranges; neither is auto-selected |
| `test_derived_q4_is_labelled` | A quarterly series marks Q4 as derived |
| `test_low_confidence_grouping_is_surfaced` | A fallback-stage grouping shows its method in the UI |
| `test_requires_review_summary_is_withheld` | An unvalidated summary is not rendered as accepted |
| `test_out_of_scope_request_costs_nothing` | The budget meter is unchanged after a refused cross-ticker request |
| `test_expired_session_restores_read_only` | Transcript renders; the input is disabled with an explanation |
