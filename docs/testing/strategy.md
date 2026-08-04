# Testing Strategy

> **REWRITTEN 2026-08-03 AFTER THE CLEANUP.** The deterministic semantic parser, the application
> PostgreSQL persistence layer, its Alembic migrations, the DERA mirror and fact loader, and the
> accession document classifier were DELETED — and with them 346 test functions. This document
> previously described 876 tests across fifteen packages, three database identities and a live
> migration round trip. None of that exists. Every number below was measured on 2026-08-03.
>
> Authoritative for what was deleted and why:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`.
>
> **UPDATED 2026-08-03 BY PHASE 1.** Two modules were added — `tests/unit/test_model_catalog.py` and
> `tests/architecture/test_phase1_aws_boundary.py` — and the suite went from 309 to 375 tests at
> 92.14 percent coverage. **The suite still has NO environmental precondition.** Phase 1 reached a
> real provider, and not one test does: the catalog tests build their own synthetic snapshots, and
> the architecture tests assert that no test, no package and no CI job can reach AWS at all.
>
> **UPDATED 2026-08-03 BY PHASE 2.1.** Six modules were added — five unit modules for the
> multipart envelopes, their validation, the queue, the sizing policy and the review surface,
> plus `tests/architecture/test_phase21_boundaries.py` — and one integration module for the
> multipart sequence. The suite went from 1,049 to **1,253 tests at 91.64 percent coverage**,
> still with ZERO skips and still with no environmental precondition: the multipart integration
> test drives a scripted provider that answers by BRIEF KIND, so it also proves the orchestrator
> asked for the part it thinks it asked for.
>
> **NO DATABASE EXISTS.** Filings HAVE now been sent to models — thirty single-response
> invocations in Phase 2 and a multipart run in Phase 2.1 — and not one test reaches a provider.
>
> **UPDATED 2026-08-03 BY PHASE 2. HALF OF THE LINE ABOVE IS SUPERSEDED AND HALF OF IT STANDS.**
> `roadmap.md` records that filings have now been parsed by real models. That happened OUTSIDE this
> suite: every model call inside the suite goes to the in-process mock provider or to an injected
> fake client, and `tests/architecture/test_phase1_aws_boundary.py` still fails the build if a test
> imports a provider SDK, shells out to the AWS CLI, or names an account. **No application database
> exists, and that half stands** — Phase 2 stores evaluation evidence as exact bytes under the
> gitignored `var/evaluation-runs/`, and `tests/architecture/test_phase2_boundaries.py` fails the
> build if a database driver, an ORM or a cache client is imported by shipped source.
>
> Twelve test modules were added — ten unit, one architecture, and one in `tests/integration/`,
> which returned with a marker that now means something — and the suite was measured on 2026-08-03
> at **1048 tests, 0 skipped, 92.19 percent coverage** over sixteen packages.
>
> **UPDATED 2026-08-04 BY PHASE 2.2.** Four unit modules were added — `test_source_inventory.py`,
> `test_completeness.py`, `test_anchor_ladder.py` and `test_multipart_tables.py` — and the suite
> was measured at **1,564 tests, 0 skipped, 0 failed**, with `ruff format`, `ruff check` and `mypy`
> over 118 source files all clean. **Phase 2.2 INVOKED NO MODEL AT ALL**, so the usual sentence is
> stronger than usual this time: not only does no test reach a provider, no part of the phase did.
> The two largest new modules are the two whose subject is a DENOMINATOR, and both are hermetic —
> no network, no AWS, no clock, no filesystem. Detail:
> [The Phase 2.2 suites](#the-phase-22-suites).

IMPLEMENTATION STATUS: unit, integration, architecture and security layers IMPLEMENTED. Golden,
property and performance layers PLANNED.

---

## The suite as it stands

```
1048 tests collected, 1048 passed, 0 skipped        measured 2026-08-03
92.19 percent coverage against an 85 percent gate   16 packages measured, all of them
33 test modules: 25 unit, 7 architecture, 1 integration
48 of those tests also carry the `security` marker and are selected by `make test-security`
```

**The suite has NO environmental precondition.** No database, no network, no credentials, no
container, no fixture generation step. That is why `make test-no-skips` is the same suite as
`make test`, and why a skip in CI has no legitimate cause at all. Before the cleanup, "no reachable
PostgreSQL" was an available excuse for a skip; it is gone.

**PHASE 2 ADDED THREE COMPONENTS THAT COULD EACH HAVE REINTRODUCED ONE, AND NONE OF THEM DID.** The
provider adapter takes its `client_factory` as an injected callable, so `test_bedrock_adapter.py`
exercises the whole Converse path with a fake and never resolves an identity. The review API is a
set of functions from a `Request` to a `Response`, so `test_review_api.py` exercises every route
without binding a port — a test that waits on a socket is a test that eventually flakes and then
skips. The evaluation store is a directory of exact bytes, so `tmp_path` is the entire environment
it needs. `make review` binds a socket; the suite never does.

| Module | Tests | Subject |
|---|---|---|
| `tests/unit/test_evaluation_store.py` | 157 | identifiers, two independent state machines, events, comments, exact evidence, the restart sweep |
| `tests/unit/test_review_web.py` | 75 | rendering: escaping paired with mutation proofs, visible refusals, no taxonomy |
| `tests/unit/test_source_transport.py` | 73 | dispositions, decoding, inventory verification, assembly across eras, compatibility |
| `tests/unit/test_review_api.py` | 63 | router, security headers, sessions, CSRF, `/health`, the event stream, run and review routes |
| `tests/unit/test_bedrock_adapter.py` | 57 | request construction, image blocks, reasoning versus answer, failure classification |
| `tests/unit/test_model_catalog.py` | 50 | label mapping, availability, multimodal proof, cost ceiling, retry ceiling |
| `tests/unit/test_prompt_registry.py` | 49 | hash-locked versions, the immutability guard, one ACTIVE prompt per role |
| `tests/unit/test_coverage_validation.py` | 48 | the elastic reader, resolution against preserved bytes, numeric signals, the verdict |
| `tests/unit/test_orchestrator_units.py` | 44 | output sizing, the durable spend journal, the corpus filing catalog |
| `tests/unit/test_filing_discovery.py` | 42 | overflow shard, `master.gz` reconciliation, era routing, the supplied qualifying-form set |
| `tests/unit/test_observability.py` | 38 | redaction, correlation scope, structured output |
| `tests/unit/test_filed_documents.py` | 32 | the SGML dissemination envelope listed, and the classification it must never perform |
| `tests/unit/test_llm_boundary.py` | 32 | model content boundary, compiler, gateway, budget |
| `tests/unit/test_model_routing.py` | 31 | four-role routing, disclosed cross-region routes, blank roles, disabled-with-a-reason |
| `tests/unit/test_sec_identity.py` | 25 | CIK, accession, URL construction, the filing-agent prefix trap |
| `tests/integration/test_parser_review_flow.py` | 23 | the whole parser-only path, against the in-process mock |
| `tests/architecture/test_aws_identity.py` | 18 | credential variables, SDK arguments, credentials in URLs |
| `tests/architecture/test_phase2_boundaries.py` | 18 | the six things the parser path must not become |
| `tests/unit/test_corpus_identity_rules.py` | 17 | the five identity rules, against real EDGAR cases |
| `tests/unit/test_yaml_parser.py` | 16 | hardened YAML 1.2 safe parser, alias and depth budgets |
| `tests/architecture/test_ci_workflow.py` | 15 | the workflow parsed, not grepped |
| `tests/unit/test_form_family_contract.py` | 15 | the 22-in/19-out adjudicated inventory |
| `tests/unit/test_sec_http_client.py` | 15 | retries, cooldown, content assertions, download safety |
| `tests/architecture/test_architecture.py` | 12 | dependency direction, single homes, prompt boundary, no form allowlist |
| `tests/architecture/test_phase1_aws_boundary.py` | 12 | no AWS in the product, no account in the repository, no spend in CI |
| `tests/unit/test_filing_acquisition.py` | 12 | byte-exact acquisition, provenance, storage keys |
| `tests/architecture/test_openapi_contract.py` | 11 | the contract parsed, refs resolved, no server claimed, routes reconciled both ways |
| `tests/unit/test_configuration.py` | 10 | User-Agent gate, rate bounds, cooldown floor |
| `tests/unit/test_corpus_identity_contract.py` | 10 | issuer and co-registration identity |
| `tests/unit/test_sec_client.py` | 9 | token bucket and throttle classification, on a fake clock |
| `tests/unit/test_filing_fixtures.py` | 8 | original-source hash verification, no derived output committed |
| `tests/unit/test_storage.py` | 6 | atomic writes, path traversal, hashing |
| `tests/architecture/test_markdown_lint.py` | 5 | fences, swallowed headings, relative links |

**THESE ARE COLLECTED TESTS, WHICH THE PREVIOUS TABLE WAS NOT.** A parametrized function
contributes one row per case, and this column now counts cases the way the reported total always
did — the Phase 1 table counted test FUNCTIONS and its own total did not, which is why the rows
summed to 297 against a stated 375. The correction is arithmetic and not growth: eighteen of these
modules have not been touched since Phase 1, and `tests/unit/test_observability.py` is the clearest
of them at 12 functions and 38 collected cases, listed as 12 in the Phase 1 table and as 38 here
while being the same file.

## What the suite covers

```
SEC identity                 CIK, accession, URL construction, the filing-agent prefix trap
filing identity              (CIK, accession); co-registration; ownership from the archive path
exact form-family contract   22 included, 19 excluded, GENERATED from the reviewed inventory
SEC request identity         User-Agent validation failing closed
rate limiting                one shared bucket, a fake clock, no wall-clock dependence
retry and throttle           a rate-threshold 403 is one 600-second pause, never backoff
filing discovery             the overflow shard, deduplication, master-index reconciliation
source acquisition           byte-exact, with provenance
source-byte fidelity         every committed original SEC document hash-verified on every run
transport classification     era routing, directory-listing rejection, ZIP and CRC assertions
filed-document listing       the EDGAR SGML envelope enumerated with NO role, class or importance
transport disposition        byte signature, extension, XML root namespace, EDGAR's own IDEA marker
failing closed               an unrecognised member reaches the run plan as unknown, never guessed
lossless decoding            a declared codec round-trips, and an undecodable member says so
source-set assembly          local-first reuse, hash-verified, the fetcher consulted only for gaps
intact-source fit            a filing exceeding the selected model's context is refused WITH numbers
configuration                startup validation
generic storage              atomic writes, path traversal, SHA-256
raw / YAML boundary          both directions, plus native-tool refusal
safe YAML                    alias budget, depth budget, identifier quoting
generic provider interface   and the mock provider
provider adapter             Converse request order and labelling, image bytes carried not
                             re-encoded, reasoning separated from the visible answer, one call per
                             invocation, provider exceptions normalized at the boundary
request/response metadata    exact bodies preserved, budget enforced before spend
evaluation storage           identifiers, two INDEPENDENT state machines, an append-only event log,
                             developer comments, exact request and response evidence
restart behaviour            an in-flight job becomes INTERRUPTED and NOTHING is re-invoked
durable spend                a cumulative ceiling that outlives the process, reserved then settled
versioned prompts            hash-locked; a used version cannot be edited; one ACTIVE prompt a role
four-role routing            region DERIVED from the snapshot, cross-region DISCLOSED, blank roles
elastic parse reading        unknown keys preserved, no node-type vocabulary owned by the backend
reference resolution         against the PRESERVED bytes, including reflowed and XBRL-split quotes
numeric signals              arithmetic only; a figure absent from the source is not counted
no false completeness        ValidationStatus has no COMPLETE member and no path can name one
review HTTP surface          router, security headers, loopback posture, sessions, CSRF, /health,
                             the event stream and its Last-Event-ID resumption
review rendering             a filing is escaped text and never markup; refusals stay visible;
                             a model-chosen label is displayed verbatim
the whole parser path        one integration module across every package, on the mock provider
security                     credential variables, SDK arguments, log redaction
observability                redaction parametrized over every redacted field
architecture                 dependency direction, single homes, no empty stubs, no form allowlist
CI reconciliation            the workflow parsed and asserted against the Makefile
API contract                 OpenAPI parse, every local ref resolved, no server declared, and
                             every route reconciled against the application in BOTH directions
documentation                fences, swallowed headings, relative links resolve on disk
corpus integrity             identity and form-family contracts over the research corpus
model capability             label mapping, unique/ambiguous/missing, availability, region
multimodal claims            a Multimodal badge requires a VERIFIED image invocation, not a flag
no silent substitution       no default model, no fallback, no widened region, no downgraded role
cost ceiling                 a worst-case bound authorized BEFORE the call, reserved then settled
retry ceiling                one retry, and never because the wording was disliked
AWS boundary                 no provider SDK outside the adapter, no CLI subprocess, no model id or
                             region literal in shipped source; no account id, ARN or SSO URL in any
                             tracked file; no id-token, no credential and no model call in ordinary CI
```

## tests/integration/ returned, and the marker now means something

`tests/integration/` was emptied by the cleanup and the `integration` marker was deleted with it,
because `--strict-markers` makes an unused marker a promise the suite does not keep. Every test that
had lived there needed a live PostgreSQL, and that is exactly the shape of precondition this suite
is not allowed to have.

`tests/integration/test_parser_review_flow.py` is IMPLEMENTED and exercises the whole parser-only
path — catalog, source assembly, routing, preflight, invocation, validation, storage and review —
**with no database, no network, no credential and no listening socket.** Everything it runs against
is built inside the test: a `tmp_path` corpus of two synthetic filings, a `tmp_path` prompt
directory loaded through the registry's real hash gate, a `tmp_path` capability snapshot of two
invented candidates, and `MockProvider`. Not one identifier, region, limit or price from
`docs/llm/bedrock-capability-snapshot.yaml` appears in it, so a snapshot regenerated tomorrow
cannot break it.

The properties it protects are properties of the SEQUENCE, and no unit test can hold them:

```
one child job per filing, and two filings are two requests, never one concatenation
the source set is REUSED from what is already held, and a recording fetcher proves SEC was not
    contacted — it records the call and then raises, so a regression is named rather than silent
a cost bound exists BEFORE the first billable call, and the reservation is settled after it
the preserved evidence is byte-identical to what the provider actually saw and returned
a job reaching READY_FOR_REVIEW says NOTHING about what a reviewer decided
a page reload loses nothing: a second store over the same directory returns the whole session
a restart re-invokes NOTHING, and does not sweep a job that had already finished
a parser-only run invokes exactly one model, and a filled image, summary or analysis selector is
    refused BY NAME rather than quietly run
a filing that does not fit is refused with the arithmetic on the record and never reaches a provider
```

Each of those has a MUTATION PARTNER in the same file. The text-only parser must report the image
member as unanalysed; the multimodal parser must actually receive it. The undersized context must
refuse; the sufficient one must not. The unauthorized stage must raise; the parser-only run must
not. A gate wired to refuse everything passes half of these and breaks the product.

**NO ARTIFACT CONTRACT IS ASSERTED THERE, DELIBERATELY.** The mock returns a well-formed YAML
mapping with one node and one verbatim quote. It exercises the reader, the resolver and the audit
path. It is not a response schema, and nothing in it claims a real model would produce that shape.

## The Phase 2.2 suites

Measured 2026-08-04: **1,564 collected, 1,564 passed, 0 skipped, 0 failed.** `ruff format --check`
clean, `ruff check` clean, `mypy` clean over 118 source files. **The table under
[The suite as it stands](#the-suite-as-it-stands) is dated 2026-08-03 and has not been
regenerated**; it is kept as the record of that measurement, and the four modules below are the
Phase 2.2 addition rather than a replacement for it.

| Module | Tests | Subject |
|---|---:|---|
| `tests/unit/test_completeness.py` | 112 | interval algebra, the four dispositions, versioned human truth, the ledger, the fourteen-condition gate |
| `tests/unit/test_source_inventory.py` | 89 | spans, offsets, hiding reasons, the rendered table grid, image headers read and never decoded |
| `tests/unit/test_anchor_ladder.py` | 24 | six levels, the line between a PROOF and a CANDIDATE, and composed index maps |
| `tests/unit/test_multipart_tables.py` | 22 | reading a model-returned structured table: shape carried, meaning never inferred |

### What each one exists to stop

```
test_completeness.py       THAT SILENCE IS COUNTED. A source range no part of the parse ever
                           mentioned must come out SILENTLY_OMITTED and must fail the gate. That
                           is the omission a reference rate cannot see, because a region a model
                           never cited never enters a reference rate's denominator — which is
                           exactly what "352 of 364 references resolved" did NOT measure in Phase
                           2.1. Its single most important test is
                           `test_prose_about_a_table_does_not_discharge_the_table`: real numbers,
                           real citations and no table is the combination this package must refuse
                           to call coverage, and it is the combination all seven proof runs
                           produced.

test_source_inventory.py   THE DENOMINATOR ITSELF, AND NOT ONE WORD ABOUT MEANING. A span ends at
                           a block boundary and survives an inline one; `text[start:end]` is the
                           filed bytes INCLUDING every escape; markup that hides content marks it
                           hidden and never deletes it; a grid position is the position a browser
                           would render after rowspan and colspan; malformed markup is a filing
                           rather than a failure and nothing raises over it; an image header is
                           READ, never decoded, and an unreadable one answers None rather than a
                           plausible default. No test claims a span is a risk factor, a table is a
                           financial statement, or an image is a chart —
                           `packages/filing_acquisition/inventory.py` was DELETED for judgements
                           of exactly that kind, and a test asking for them would put the
                           judgement back one green run at a time.

test_anchor_ladder.py      WHICH NEAR-MISSES MAY BE CALLED `resolved`. Levels 1 to 4 fold away a
                           defect of TRANSCRIPTION and still demand the same characters in the
                           same order; levels 5 and 6 fold away a defect of JUDGEMENT and
                           therefore produce a CANDIDATE. Counting either of the last two as proof
                           would be a citation rate flattering the model that produced it, so it
                           is asserted explicitly rather than implied by enum membership. Every
                           offset assertion slices the ORIGINAL and reads it back: a ladder with
                           wrong index maps returns the right verdict while highlighting bytes
                           that are merely nearby, and it gets worse the more markup a filing
                           carries — which is precisely where a reviewer most needs the highlight.

test_multipart_tables.py   A CONTRACT WRITTEN AGAINST IGNORANCE. `table_count` was ZERO in all
                           seven Phase 2.1 runs and no prompt asked for one, so what a model will
                           emit is unmeasured. Two row shapes are accepted, a bare scalar is
                           accepted, an unknown key survives, and a missing envelope key is a
                           FINDING rather than a refusal — because a reader that rejected an
                           unexpected shape would measure which shape the prompt happened to
                           suggest. What these tests may never start asserting is named in the
                           module docstring: that a table has a header row, that its type is one
                           of a list, that a unit string is well formed.
```

### The mutation-proof discipline these suites follow

**A REGRESSION TEST WHOSE FAILURE HAS NEVER BEEN OBSERVED IS A CLAIM, NOT A GUARD.** The rule
already stated under [Three guards that exist because something got
past](#three-guards-that-exist-because-something-got-past) is applied here in a stricter form,
because every one of these modules computes a number that a person will later believe:

```
EVERY REFUSAL HAS AN ACCEPTANCE PARTNER   a cell absent from the source fails the table AND a cell
                                          drawn from its source element passes; a table naming no
                                          such element fails AND one naming a real element
                                          discharges it; an incompatible pairing fails condition
                                          eight AND a parse accounting for every item passes the
                                          whole gate. A gate wired to refuse everything satisfies
                                          half of these and destroys the product.

ONE INPUT FLIPPED AT A TIME               `test_flipping_one_gate_input_fails_exactly_the
                                          _conditions_it_should` and its ledger twin are
                                          parametrized over the gate's inputs and assert EXACTLY
                                          which conditions go red. A gate that failed everything
                                          whenever anything was wrong would pass a coarser test
                                          and would tell a reviewer nothing about what to look at.

THE SUGGESTER ACCEPTS NONE OF ITS OWN     `test_suggest_accepts_none_of_its_own_proposals_and
  PROPOSALS                               _derives_the_same_document_twice`. A mechanical
                                          suggestion is evidence for a human, and a suggester that
                                          could enact its own proposal is a backend acquiring a
                                          semantic opinion.

A COUNT NEVER GOES NEGATIVE               three separate tests assert that spans, table elements
                                          and images silently omitted never go below zero, and one
                                          asserts every percentage is zero when its denominator is
                                          zero. An omission count that can go negative reports a
                                          filing as MORE than covered.

THE DOCUMENT SAYS WHAT IT IS NOT          the ledger mapping and the gate mapping each assert IN
                                          THEIR OWN OUTPUT that passing is not completeness, and
                                          a test reads that back. Prose in a doc file is not
                                          carried to the person reading a result.
```

**HERMETIC, AND DELIBERATELY SMALL FIXTURES.** `test_completeness.py` measures four lines of
synthetic prose, one table element and one image — a filing small enough to count by hand — rather
than the 41 table elements of somebody's real 10-Q. A test whose denominator is a real filing
proves that a number came out, not that the arithmetic is right. Inventories are built from
`packages.source_inventory` records directly rather than by walking markup, so a ledger test cannot
go red for a markup-walker reason; the walker has its own 89.

## The Phase 2.1 architecture guards

`tests/architecture/test_phase21_boundaries.py` guards the four doors the multipart protocol opens.
Each is a door that would be EASIER to walk through than to keep shut, which is why each has a test
rather than a paragraph.

```
1  NO BACKEND SEMANTIC CHUNKER   no function or attribute in the multipart surface names a
                                 chunking, slicing, splitting or windowing operation; no
                                 filing-section name appears as an evaluated literal
2  NO BLIND CONTINUATION         no evaluated string in packages/ and no line in any prompt file
                                 asks a model to continue, resume or carry on a response; the
                                 TRUNCATED state has no outgoing transition; no module
                                 concatenates response bodies
3  NO WINNER                     no function, class or attribute anywhere in packages/ names a
                                 best, winning, preferred, primary, scored or ranked model; no
                                 multipart prompt names a model provider as a whole word; the
                                 two historical single-response prompts are hash-verified untouched
4  STILL PARSING ONLY            every billable task type resolves to a parsing prompt role, and
                                 no multipart module names the image, summary or analysis role
```

Plus the two Phase 2 guards multipart makes MORE load-bearing: every semantic invocation carries
the source-set identity and refuses a set that moved, and `_preserve` provably runs before
`_interpret` so a crash between them cannot lose bytes that were bought.

**THE ANTI-VACUITY GUARD NAMES ITS SCAN SET.** Seven modules must exist and carry code, or the guards
above would be scanning nothing and passing.

## The Phase 2 architecture guards

`tests/architecture/test_phase2_boundaries.py` is IMPLEMENTED and names the six things the parser
path must not become. Each is a guard rather than a paragraph, because a paragraph has never once
stopped this repository from drifting:

```
1  no programmatic semantic parser   a filing section name — Item, Part, footnote, exhibit, MD&A,
                                     signature block — may not return as an EVALUATED string
                                     constant in any runtime package. Prose explaining the rule
                                     stays legal, and a mutation test asserts the prose is there,
                                     so the guard is provably matching literals and not text
2  no universal filing taxonomy      ValidationStatus has no COMPLETE member; an unfamiliar
                                     model-chosen label and an unknown key both survive the reader
3  no database and no cache          no driver, ORM or cache client imported; none declared as a
                                     runtime dependency; evaluation evidence is gitignored
4  no hardcoded model fact           the router names no region of its own and is asserted to
                                     derive it from the snapshot; the parser prompt is hash-locked
                                     and is not Markdown
5  no browser-to-provider path       the browser-facing packages mention no credential variable and
                                     no provider endpoint, import no SDK and no HTTP client, and
                                     serve a default-src 'none' policy with no unsafe-inline
6  only the authorized stage runs    the orchestrator refuses an unauthorized stage, and a blank
                                     optional role borrows no model
```

The anti-vacuity guard for the file asserts the seven Phase 2 packages exist, each carries a module
beyond `__init__.py`, and `packages/` holds at least 60 Python modules — because every check above
scans a directory, and a scan of a directory that quietly stopped existing passes.

**THE OPENAPI CONTRACT IS NOW RECONCILED AGAINST THE APPLICATION IN BOTH DIRECTIONS.**
`tests/architecture/test_openapi_contract.py` gained the check that `x-implementation-status:
IMPLEMENTED` can only be claimed by an operation a real route answers — and, the harder half, that
a route the application serves must be described in the contract. A one-directional check catches
a specification that over-claims and misses one that has fallen behind, and the second is more
dangerous here because nothing else in the repository would ever notice. The application is
constructed for that test with no service, no worker and no policy: registration binds methods to
paths and invokes nothing, so the guard needs no store, no snapshot and no network. `PLANNED`
operations are asserted NOT to be served, so an unlabelled implementation cannot hide behind the
status it outgrew.

## Frontend tests are Python tests over server-rendered HTML

There is no JavaScript test runner in this repository, no headless browser, no snapshot fixture and
no `npm`. `tests/unit/test_review_web.py` calls the render functions directly and reads their output
back with `html.parser` from the standard library, asserting over the parsed element tree —
ancestry chains, attributes, the options of a named select — rather than over substrings.

That is the LIGHTEST MAINTAINABLE approach for this particular UI, and it is a consequence of
ADR-0019 rather than a preference. The review application has no build step: pages are rendered in
Python and the stylesheet and single script are module constants served from their own routes. A
browser-driver suite would add a runtime, a binary, a wait strategy and a class of flake, to test a
surface that has no client-side state worth exercising. When the beta UI in Phase 6 has real
client-side behaviour, this decision is revisited then and not before.

What is actually asserted there is not that a function returns a string containing a word:

```
ESCAPING, PAIRED WITH MUTATION      Two of the three things this UI displays are untrusted in the
                                    strongest sense — the preserved bytes of a filing, and whatever
                                    a model returned after reading one. Every test that asserts the
                                    dangerous string is absent ALSO asserts the escaped form is
                                    present, because "absent" also passes when a renderer silently
                                    dropped the content, and a renderer that drops content is the
                                    other defect this page exists to catch
VISIBLE REFUSALS                    a disabled candidate keeps its concrete reason; a Run button
                                    with nothing to run is disabled rather than hopeful; an
                                    unresolved source reference is marked and is deliberately NOT a
                                    link, because a link renders it as though it were cited
NO TAXONOMY                         `type` and `title` are strings the model produced and are shown
                                    verbatim. A renderer that normalised an unfamiliar label would
                                    hide exactly the finding the first experiments exist to produce
```

## Three guards that exist because something got past

**The zero-skip gate.** `make test-no-skips` fails the run if anything skips. `"203 passed, 2
skipped"` is what this suite reported for two sprints while the only two tests exercising a live
schema had never once executed. The hook records skips raised during `setup` AND during `call`;
watching only `setup` misses a `pytest.skip()` inside a test body, which is how the first version
of this gate passed a suite containing a deliberate skip.

**Anti-vacuity assertions.** Sprint 1 created eighteen packages holding only a docstring, and
several architecture tests scanned those empty directories and passed while enforcing nothing.
Every scanning guard now asserts its own surface is non-trivial: at least 5 substantive packages
and 20 modules; at least 100 tracked files and 40 Python files; at least 20 Markdown files; at
least 10 API operations and 20 references; and, added in Phase 2, at least 60 Python modules under
`packages/` plus a named list of the seven Phase 2 packages that must each carry real code. **These
floors were re-checked after the deletion and none had to be lowered** — which is the outcome that
matters, because lowering one to accommodate a deletion is how a guard quietly stops guarding.

**Mutation proofs.** A regression test whose failure has never been observed is a claim, not a
guard. The deleted parser suites carried explicit mutation proofs, and that discipline carries
forward: `test_observability.py` asserts that an UNLISTED field IS emitted, so the redaction tests
cannot pass vacuously; `test_filing_fixtures.py` asserts derived parser output is ABSENT, so the
fixture tree cannot silently reacquire it; `test_filing_discovery.py` asserts an empty qualifying
set is REJECTED, so discovery cannot return nothing and report success. Phase 2 added more of them
than any other kind of test: the compatibility gate must accept as well as refuse, the stage guard
must admit a parser-only run, the multimodal path must actually change the request, the resumed
event stream must be strictly shorter than the full one, and the non-loopback bind that is refused
without a secret must be accepted with one.

## Rules that apply to every layer

**A skip is not a pass.** See above.

**A test may not depend on a network, a credential or a cloud account.** Phase 1 reached Bedrock and
Phase 2 parsed filings with real models; no test does either. `test_the_suite_needs_no_aws_identity`
fails the build if a test imports a provider SDK or shells out to the AWS CLI, and the smoke tool
that CAN spend money lives under the gitignored `var/local-tools/`, refuses to run without an
explicit opt-in flag, and is asserted to be untracked. The Phase 2 provider adapter is testable only
because it takes its client factory as an argument; `boto3` is an OPTIONAL extra that ordinary CI
does not install, so "the suite is AWS-free" means the SDK is not even present.

**A test may not bind a socket.** A test that waits on a port is a test that flakes on a slow runner
and is then marked skip, and a skip is a guard that quietly stopped being enforced. The review API
is exercised by handing handlers a request object; the review UI is exercised by calling render
functions. Nothing in `tests/` listens.

**A test may not depend on an untracked file.** One did — it read the developer's gitignored
`.env` — and it passed locally while being incapable of passing in CI. Fixtures come from the
repository or from `tmp_path`.

**A test may not depend on the capability snapshot naming a particular model.** Every routing,
orchestration and integration test builds its own synthetic snapshot out of invented labels and
invented region names. `docs/llm/bedrock-capability-snapshot.yaml` is held to its own contract in
exactly one place, `tests/unit/test_model_catalog.py`, and a capability asserted twice drifts
exactly as a capability recorded twice does.

**A gate is never weakened to make a commit pass.** Correcting a demonstrably wrong test is
permitted and must be disclosed in the commit report, with what changed and why the replacement
still protects the behaviour. During this cleanup the AWS-identity guard failed twice on new test
code in `test_observability.py`; both times the TEST was rewritten, and the guard's allowlist was
made narrower rather than wider. Phase 2 hit the same guard again in `test_review_api.py` and
`test_phase2_boundaries.py`, and both files assemble credential variable names from parts rather
than joining the allowlist.

**Coverage measures surviving product code and is never raised by exclusion.** All sixteen runtime
packages are named in `COV_PACKAGES`, which is every directory under `packages/`. A package absent
from that list is unmeasured, so its gap is invisible and the gate passes without it — the same
vacuity trap as an architecture test scanning an empty directory. Add a package there in the change
that creates it; Phase 2 added seven.

**Deleted behaviour gets deleted tests.** 346 test functions went with their subjects and none was
kept for the count. A reduced total is the correct outcome of a deletion, and comparing it
unfavourably to the previous 717 would be comparing coverage of a product that no longer exists.

## Tests deleted on 2026-08-03

```
151  the deterministic parser        footnote extraction 22, canonicalization 36, footnote
                                     regression 11, table parser 27, table ownership 24,
                                     ownership regression 15, 10-Q regression 16
 82  DERA                            notes 7, tsv 11, normalize 24, selection 16, validate 16,
                                     report 8
 66  obsolete persistence            migrations 23, migration-target routing 23, database
                                     isolation 20
 38  integration, all database-bound canonicalization persistence 19, DERA load 13, DERA mirror 2,
                                     10-Q persistence 4
  9  architecture                    test_deterministic_extraction.py — not one of its invariants
                                     protected anything other than the deleted parser
```

`tests/unit/test_accession_inventory.py` (16) went with the document classifier. Its subject
returned in Phase 2 as `tests/unit/test_filed_documents.py`, and the new module's own docstring
records what it exists to STOP doing: sorting declared types into a role taxonomy, deciding which
member is "the filing", ruling a courtesy copy a duplicate, and normalising the filer's own string.
`EX-27` and `10-K` come back as two strings the filer typed.

`tests/unit/test_filing_fixtures.py` lost 9 of 14 functions: they reimplemented canonicalization
stage 2 inline to assert that 16 candidates minus 3 item disclosures leaves 13 canonical
footnotes — a semantic conclusion about Apple, asserted by a test.

## Moved out of the planned list by Phase 2

Every line here was listed as PLANNED on 2026-08-03 and is now IMPLEMENTED. The record of what was
planned is kept rather than deleted, so a later reader can see which predictions held.

```
source-set completeness       test_source_transport.py assembly, plus the integration path
intact-input compatibility    refused BEFORE invocation, with measured bytes, the estimated input
                              and the model's verified limit on the record
elastic artifact acceptance   test_coverage_validation.py: an unfamiliar label and an unknown key
                              are both represented, neither rejected nor dropped
source-reference validation   resolved against the PRESERVED bytes, including a quote the model
                              reflowed and a quote inline-XBRL markup cut into six pieces
numeric validation            LANDED WEAKER THAN WRITTEN, and honestly so. What exists is generic
                              numeric SIGNALS with a noise floor, not a proof that every reported
                              number appears verbatim. A figure absent from the source is not
                              counted as verbatim; no number is read for meaning
unresolved-content handling   a model-declared unresolved item forces PARTIAL
no false completeness         ValidationStatus has no COMPLETE member, and a guard asserts no code
                              path in the package can name one
prompt-version testing        test_prompt_registry.py: a used version cannot be edited, a manifest
                              is mandatory, and "the latest" is not a thing a caller may ask for
optional-stage composition    a parser-only run is complete and creates one job per filing; a
                              filled image, summary or analysis selector is refused by name
no silent substitution        test_model_routing.py and test_bedrock_adapter.py: no role inherits
                              another's model, no region is widened, no retry crosses to a model
                              the caller did not choose
multimodal routing            both directions in one file: the text-only parser NAMES the image
                              member as unanalysed and the verdict is PARTIAL; the multimodal
                              parser receives the bytes and the evidence records them
cost authorization            preflight bounds every filing before anything is invoked; the
                              reservation is settled against measured usage afterwards
parent run and child jobs     two filings, two job identifiers, two provider requests, each naming
                              exactly one accession
raw-first source lookup       a recording fetcher proves local durable storage was consulted,
                              hash-verified and reused, and that SEC was never contacted
comment lineage               a comment carries the artifact version it targeted and is returned
                              only for the child job it was written against
```

## PLANNED — none of these exists

For the model experiments:

```
model-output fixture testing    recorded real responses replayed offline. The integration test's
                                response is a synthetic mapping that asserts no artifact contract
A/B model comparison            the same filing through different parsing models, IN THE SUITE.
                                Cross-model figures were produced by hand in Phase 2; no test
                                reproduces them, and no test may, without reaching a provider
repeat-run variability          the same filing through the same model twice
breadth across form strings     Phase 2.5, BLOCKED on a user decision about which parser and prompt
                                version advance
```

For persistence, the approval gate and reuse:

```
approval gating                 that an EVALUATION artifact never satisfies a search as a trusted
                                result, and that only APPROVED artifacts become reusable. The two
                                state machines are tested; nothing consults an approved artifact,
                                because no search and no reuse path exists to consult it
reuse identity                  that a differing source hash, model version, prompt version or
                                setting defeats reuse
cache correctness               that Redis holds only approved artifacts, with a 24-hour TTL, and
                                is never the authoritative read. Redis is not implemented
reviewer stream isolation       Last-Event-ID resumption is tested, and the stream is asserted to
                                carry no filing text. There is one reviewer on loopback, so
                                isolation BETWEEN reviewers is neither built nor tested
```

Whole layers not yet started: golden, property and performance. None of the three has a subject
stable enough to be worth writing against — a golden file over model output would pin a shape no
model has promised, and a performance test would measure the standard library's `http.server`
serving one developer.
