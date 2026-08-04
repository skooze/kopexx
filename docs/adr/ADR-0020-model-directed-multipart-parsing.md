# ADR-0020 — Model-directed multipart parsing, and the seven decisions it forced

STATUS: ACCEPTED
DATE: 2026-08-03
PHASE: 2.1
SUPERSEDES: nothing
BUILDS ON: [ADR-0016](ADR-0016-corpus-first-model-first-architecture.md),
[ADR-0018](ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md),
[ADR-0019](ADR-0019-parser-review-application-over-a-framework.md)

---

## Context

Phase 2 sent a complete filing to a model intact and then expected the complete parsed artifact to
come back in **one provider response**. Thirty preserved invocations measured what that assumption
costs.

```
three of the five candidates cap output at 8,000 tokens
four of the benchmark's five truncation failures were that cap
the DEEPEST parse produced — 73 nodes, 69 of 72 source references resolved — was itself
    truncated at 8,000 tokens, with no way to finish it
```

Every candidate held every benchmark filing comfortably in its CONTEXT. The binding constraint was
never the input; it was the output, and it was a constraint on a **response** rather than on a
**parse**.

That assumption is withdrawn. An output cap applies to one provider response. It does not require
one logical filing parse to use one provider response.

**This ADR is the record of a scope change the user authorized explicitly**, and it is the
authorization `rules.md` section 21 rule 7 requires. That rule says visible-content projection,
mechanical multipart and any hybrid are unapproved research options requiring separate explicit
approval. What was approved is **MODEL-DIRECTED MULTIPART OUTPUT**. Two things it is not:

```
NOT mechanical multipart INPUT.       The complete compatible source set still goes to the model
                                      intact on every semantic invocation. Backend code never
                                      slices a filing, and rule 6 is untouched.
NOT visible-content projection.       Nothing is filtered out of what the model receives. That
                                      remains an unapproved research option.
```

---

## Decision

One logical filing parse may use many provider responses:

```
intact filing
  -> model-created parse plan
  -> model-created parts
  -> model-created subparts when needed
  -> model-created reconciliation
  -> mechanically assembled filing parse
  -> human review
```

The SELECTED PARSING MODEL creates the plan from the intact filing and owns every semantic
decision in it: part boundaries, part identifiers, titles, section names, node types, table labels,
footnote labels, relationships, additional required parts, subparts and unresolved material.

The backend sends intact source, carries model-created identifiers, queues work, preserves
artifacts, validates generic structure, resolves source references against the preserved bytes,
tracks coverage and cost, detects truncation and missing outputs, requests model-directed
reconciliation, and presents the result. **It decides nothing about what a filing means.**

Seven decisions followed that were not obvious in advance. Each is recorded here once.

---

## 1. Blind continuation is prohibited, and a truncated response is evidence

**Decision.** No request ever asks a model to continue an interrupted response, and no code
concatenates response fragments into one document. A response that stops at the provider's output
limit is preserved exactly, marked `TRUNCATED`, and left as **evidence**. Its partial content is
never merged into the assembled parse. The work it did not finish is picked up by a
**model-directed replanning call** that receives the intact filing again and proposes subparts
covering the WHOLE original part.

**Why.** Nothing about a language model guarantees it can resume the exact scalar a cap cut, close
a YAML structure it cannot see, avoid duplicating what it already wrote, remember where generation
stopped, preserve identifiers, or preserve source references. A protocol built on `continue` is a
protocol that produces documents nobody can validate, and validating against the preserved bytes is
the only thing this repository trusts.

**Why the replan covers the WHOLE part rather than the remainder.** The truncated response is not
going to be used as a parse. Dividing only the material it did not reach would leave the first half
covered by nothing.

**Enforcement.** `TaskState.TRUNCATED` has no outgoing transition at all, so reopening a truncated
attempt is structurally impossible rather than discouraged. An architecture test scans every
evaluated string in `packages/` and every prompt file for continuation wording.

---

## 2. The plan is a separate, compact, billable call

**Decision.** The first billable step of a multipart filing job is a PLANNING call. It receives the
complete intact source and returns a compact plan — a division of labour the model chooses for
itself — and nothing else. The prompt forbids returning content three times over.

**Why not infer the plan from the first part response.** Because the model has to see the whole
filing before it can say how the whole filing divides, and a planning call that starts parsing runs
out of room and produces neither a plan nor a parse.

**Why the backend supplies no part names.** `rules.md` section 21 rules 1 and 2. The moment the
backend offers a vocabulary, the vocabulary becomes what the product believes a filing is. There is
no section list, no taxonomy, and no minimum or maximum part count anywhere in the prompt or the
code.

---

## 3. Every semantic invocation receives the complete source set again

**Decision.** Planning, part, subpart, replanning, reconciliation and gap-repair calls each receive
the complete compatible source set, in filed order, with hashes verified — including the complete
image set for a multimodal parser. The source-set identity used for the preflight must equal the
one submitted at execution, and a difference **fails closed**.

**Why this costs what it costs, and why it is still right.** Re-sending a 40,000-token filing on
every one of a dozen calls is the dominant input cost of a multipart parse, and there is no
prompt-caching relief available: see
[the prompt-caching investigation](../llm/prompt-caching-investigation.md), which found that AWS
documents prompt caching for Claude, GPT-5.6 and Amazon Nova, and for **none of the five approved
candidates**.

The alternative — hidden provider session memory — was rejected because every invocation must be
independently reproducible from preserved inputs. A part must be re-runnable on its own. If one
part fails, the system must not regenerate every prior part. A protocol that depended on an
ever-growing conversation would make a late part cost the sum of every earlier one and would make a
single re-run impossible.

---

## 4. Three separate state machines, and a durable hierarchical queue

**Decision.** `TaskState` is a THIRD state machine beside the existing execution and review states,
with its own transitions. A multipart parse is a tree of durable task records under one child
filing job: a plan task, part tasks, subpart tasks, replanning tasks, reconciliation tasks and gap
repairs, each recording its own dependencies, model routing, prompt version, attempts, reservation,
settled cost and evidence.

**Why not overload the existing states.** `READY_FOR_REVIEW` would have meant two different things
depending on which level you were looking at. The Phase 2.1 brief says plainly: do not overload
review states.

**Why durable dependency records rather than filesystem polling.** Two tasks writing files in the
same directory and a third watching for them is a race dressed as a scheduler, and the race shows
up as a part occasionally starting before its plan exists.

**No Redis, no PostgreSQL, no Celery, no distributed queue.** The workload is one filing at a time
on one developer's machine, and `rules.md` invariant 15 and section 21 rule 13 both say persistence
follows measured artifacts. The queue is task manifests in the existing evaluation store.

---

## 5. A cost reservation per provider attempt, under three ceilings

**Decision.** Every provider attempt takes its own reservation before the call and settles against
measured usage after it. A failed attempt's reservation is NOT released. A retry is a second call
and takes a second reservation. Three ceilings apply and the tightest wins:

```
cumulative   everything this repository has ever authorized. Never resets.
phase        what the currently authorized task may spend against the same durable journal.
filing run   what ONE filing's parse may spend across every call it queues.
```

**Why the filing-run ceiling had to exist.** A multipart parse can queue a dozen billable calls off
one plan. Without it, one filing that planned ambitiously could consume the whole authorization
before any other filing ran.

**What happens when a ceiling refuses.** The branch PAUSES with the reason visible in the UI.
Nothing is shrunk, dropped, downgraded or deferred to fit, and nothing already produced is
discarded.

---

## 6. Assembly is a mechanical index, not a rewritten parse

**Decision.** The backend orders parts using the model's own `order`, nests them using the model's
own `parent_part_id`, links stable identifiers, counts, aggregates cost and presents. It may not
rename a part title, rename a node type, merge two parts, rewrite prose, move a table, reassign
anything, drop a part as redundant, or impose a canonical vocabulary.

**The exact individual model responses remain the authoritative artifacts.** The assembly is an
index that says where they are and how they relate, built only from relations the model itself
declared.

**Four claims, never collapsed into one.** Mechanical assembly, model-declared completion,
source-reference coverage and human approval answer different questions. `AssemblyStatus` has no
`COMPLETE` member and never will: the strongest thing it says is `MECHANICALLY_ASSEMBLED`, which
means every planned part reached a terminal result and the index is internally consistent.

---

## 7. A narrowly scoped format repair, because the evidence required one

**Decision.** A response that is semantically useful and syntactically invalid may be repaired by
ONE model call that receives the malformed response and the format rules — and **not the filing**.
The original malformed response, the repair request, the repaired response, its validation and its
cost are all preserved separately. The original is never replaced.

**Why it is justified rather than convenient.** Section 6 of the Phase 2.1 brief permits this
family "only if objectively required", and the Phase 2 record is the evidence: under prompt version
2, five of fifteen responses were UNPARSEABLE on serialisation grounds alone, and one candidate
produced zero readable documents in six attempts while returning structures a reader could see were
well formed. Money already spent that cannot be reviewed is the failure this addresses.

**What it may never do.** Improve semantic quality. Change a model-selected title. Add, remove or
merge a field. The prompt enumerates every one of those prohibitions, and it is given no filing to
improve an answer from.

---

## Alternatives Considered

**Blind continuation (`continue`).** Rejected: see decision 1. It is the obvious implementation and
it produces documents that cannot be validated.

**Provider-side conversation memory.** Rejected: it makes a single part un-rerunnable, makes a late
part cost the sum of every earlier one, and makes reproduction from preserved inputs impossible.

**Backend chunking of the filing by size or by heading.** Rejected outright — it is exactly the
deterministic semantic parser `rules.md` section 21 rule 1 forbids and ADR-0017 deleted, wearing a
transport costume.

**Restricting the candidate set to models with large output limits.** Rejected. It would have
eliminated three of five candidates on a constraint the protocol removes, and `rules.md` section 21
rules 8 and 9 leave model selection to the user. Models with an 8,000-token output limit remain
valid candidates precisely because the parse no longer has to fit one response.

**Prompt caching to avoid re-sending the filing.** Not available. AWS documents prompt caching for
Claude, GPT-5.6 and Amazon Nova; none of the five approved candidates is on the supported list, and
the live control plane exposes no caching capability field for any of the 119 models visible to
this account. Recorded in full rather than assumed.

---

## Consequences

**Easier.** A filing whose parse needs more output than any single candidate's maximum response can
now be parsed at all. A truncated part costs one branch rather than a whole filing. A part can be
reviewed, commented on, re-run and replaced on its own. Candidates are no longer separated by their
output ceilings.

**Harder.** Cost. The intact filing is re-sent on every semantic call and there is no caching
relief, so input cost scales with the number of calls. A parse is now a tree to review rather than
one document, which is more work for a reviewer and is why the hierarchy, the per-call page and the
assembled view all exist.

**Constrained.** The backend can never acquire a semantic opinion about how a filing divides, in
this phase or a later one, without reversing this ADR in writing.

---

## Migration Impact

The single-response protocol is NOT removed. `strategy` is durable on every child job, defaults to
`single_response` for backward compatibility, and both protocols remain runnable — which is what
makes the comparison in the Phase 2.1 sprint record possible at all. The thirty preserved Phase 2
runs are untouched and still open in the review UI.

Reversing this decision would mean deleting `packages/multipart`, the multipart task records, the
multipart prompt families and the multipart review surface. The preserved evidence would remain
readable, because it is exact request and response bytes on disk rather than an interpretation.

---

## Revisit Conditions

```
a candidate acquires prompt caching on a verified route, which would change the cost argument
    in decision 3 materially
measured evidence shows that repeating the image set on every multimodal call is unnecessary,
    which section 5 of the brief deliberately refuses to assume in advance
a measured corpus shows that the operational depth limit of 4 or the reconciliation cycle limit
    of 3 stops real work rather than runaway work
the assembled index proves insufficient for review, and a reviewer needs something the exact
    responses plus this index cannot give them
```
