# PHASE 2.2 — Bedrock research and the single-filing completeness benchmark

STATUS: THE MEASUREMENT INFRASTRUCTURE IS IMPLEMENTED. THE FIVE-MODEL COMPLETENESS BENCHMARK IS
BLOCKED ON A COST-CEILING DECISION AND DID NOT RUN. NO MODEL WAS INVOKED.
DATE: 2026-08-04
BASELINE: `42a0859` (Phase 2.1)
DECISION RECORD: [ADR-0021](../adr/ADR-0021-single-filing-completeness-measurement.md)
BUILDS ON: [ADR-0016](../adr/ADR-0016-corpus-first-model-first-architecture.md),
[ADR-0018](../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md),
[ADR-0020](../adr/ADR-0020-model-directed-multipart-parsing.md)

---

## What this phase was for

Phase 2.1 proved the multipart protocol against real models and published numbers that read like
completeness figures and were not. `352/364 references resolved` counts the model's own citations.
`47/47 parts terminal` counts finished queue work. `214 nodes` has no known correct denominator.
`table_count 0` in all seven runs was measured and unexplained.

This phase was to close that gap: build a MECHANICAL DENOMINATOR from the preserved bytes, harden
the harness against the defects Phase 2.1 exposed, research what Bedrock now offers, and then run
all five candidates against one materially sized modern filing under the new measurement.

**Four of those five things were done. The fifth — the run — did not happen, and section 1 says
exactly why.**

---

## 1. THE BENCHMARK DID NOT RUN, AND CANNOT AT THE AUTHORIZED CEILING

**This is the finding that decides the shape of the phase, so it is stated first and in full.**

```
authorized new-invocation ceiling                                        USD  5.00
cost of running the four runnable candidates at their OWN measured
    Phase 2.1 call counts                                               USD 13.3745
cost at the part-explosion guardrail ceiling of 110 calls each          USD 31.8218
```

**GPT OSS 120B cannot receive this filing at all.** Its 128,000-token context is roughly half the
243,507 estimated input tokens the complete human-readable source set requires — a factor of about
1.9, not a margin. Under INTACT_SOURCE_ONLY that is a RESULT and is recorded as an exact blocker:
nothing was truncated, sliced, projected or swapped to another model. Section 8 carries the table.

**Splitting USD 5.00 equally across the four candidates that CAN receive it lets one of them
finish.**

```
NVIDIA Nemotron 3 Super 120B   USD 1.2500 buys 32 calls;  Phase 2.1 needed 78
Qwen3 235B A22B                USD 1.2500 buys 22 calls;  Phase 2.1 needed 58
Llama 4 Maverick               USD 1.2500 buys 20 calls;  Phase 2.1 needed 14
Qwen3 VL 235B                  USD 1.2500 buys  9 calls;  Phase 2.1 needed 47
```

Three of the four would hit the filing-run budget and PAUSE mid-parse. That is the designed
behaviour under ADR-0020 decision 5 — nothing is shrunk, dropped or downgraded to fit — and it
produces exactly the `INCOMPLETE_WORK` outcome this phase exists to move past. **A paused branch
cannot reach `MECHANICAL_COMPLETENESS_CANDIDATE`, because condition 8 requires that no scheduled
required job remains nonterminal.**

**AND THE HARDENED PROTOCOL MAKES IT WORSE, NOT BETTER.** A mandatory structured-table contract
over 18 substantive table elements, plus two resolvable anchors per coverage claim, increases
output per part, which increases the number of parts, which increases the number of calls, each
re-sending the complete intact source. **Every figure above is a FLOOR.**

**The cumulative ceiling binds first in any case.** The durable spend journal stands at `USD
3.25290926` against `COST_CEILING_USD 5.00`, leaving `USD 1.75` before the configured repository
ceiling refuses. The release performed in section 6 returned `USD 0.22590990` across the ELEVEN
tasks whose every attempt provably failed before transport, bringing settled spend to `USD
3.02699936` and available headroom to `USD 1.97300064`. The twelfth unsettled reservation, `USD
0.01606095`, is HELD and not released: that task reached a provider and settled once, so whether
its orphaned first reservation was ever transported is unknown, and an uncertain reservation is
never called settled spend.

**NO PROVIDER REQUEST WAS ISSUED BY THIS PHASE. Measured Bedrock spend: `USD 0.00000000`.** Every
nonbillable task was completed regardless, and no partial arbitrary subset was run.

---

## 2. The governance bootstrap and the verified starting state

**Every governance file was read in full before any design decision was taken**, not consulted
afterwards:

```
CLAUDE.md                                   rules.md, all 22 sections
roadmap.md                                  techspecs.md
docs/llm/bedrock-capability-snapshot.yaml   docs/llm/cost-model.md
prompts/parser/versions.yaml                prompts/parser/parser-multipart-part-v1.txt
the complete Phase 2.1 working record       Makefile, .gitignore, .env.example
```

Source read directly before design, rather than inferred from documentation:
`packages/source_transport/{assembly,dispositions,compatibility,inventory,records}.py`,
`packages/filing_acquisition/{member_fetch,documents,acquisition}.py`,
`packages/coverage_validation/{references,validator}.py`, `packages/multipart/envelopes.py`,
`packages/orchestrator/{__init__,catalog,spend_journal,multipart_service}.py`,
`packages/model_catalog/capabilities.py`, `packages/prompt_registry/registry.py`,
`packages/llm_gateway/{errors,token_counter}.py`, `packages/llm_gateway/providers/bedrock.py`,
`packages/review_api/app.py`. Two exhaustive read-only subagent surveys produced the code inventory
this phase was written against.

### The starting state, verified rather than assumed

```
repository              /home/rkoasis/FinTek        branch main        remote origin
HEAD at task start      42a08590973b77b214bc4289675e661940f1b5bd
origin/main (fresh)     42a08590973b77b214bc4289675e661940f1b5bd, by git ls-remote
ahead / behind          0 / 0        working tree clean, index empty, no untracked files
CI at start             workflow "ci" green on 42a08590

review server running   NO           worker running   NO           active provider request   NO
durable spend journal   var/evaluation-runs/spend-journal.yaml
configured ceiling      COST_CEILING_USD 5.00
journal spent_usd       3.25290926   of which Phase 2.1 spent 2.84579813
stored run directories  48
```

**AWS identity resolved through an IAM Identity Center profile by the SDK provider chain, as an
assumed role with a live session. No static credential exists, none was created, and none is
recorded anywhere in this repository** — `rules.md` section 3, AWS-IDENTITY-AND-SECRETS-INVARIANT.

---

## 3. Part A — Bedrock research: what was found

A read-only fan-out ran four census agents, four documentation agents and two repository-survey
agents. **No `bedrock-runtime` call was made by any of them, no resource was created, and no
tracked file was modified.**

### 3.1 Census

```
119 foundation models visible in us-east-1
 88 of them emit text, and ALL 88 are AUTHORIZED with entitlement AVAILABLE
 63 system-defined inference profiles, in two geographies: us. and global.
```

Nothing is blocked in this account. **The five current candidates are unchanged** — present,
ACTIVE, same inference types, same modalities, same access status. Qwen3 235B A22B is still absent
from us-east-1 and still present in us-west-2, exactly as the committed snapshot records. Llama 4
Maverick still cannot be invoked by bare model id.

### 3.2 Zero drift in any committed value

```
all TEN committed prices match the live Price List API to the digit, effective 2026-07-01
all FIVE committed context and output limit pairs match the AWS model cards read 2026-08-04
```

**`docs/llm/bedrock-capability-snapshot.yaml` does not need replacing.** The `USD 2.603827`
measured in Phase 2.1 was computed against prices that are still current, so that record needs no
restatement either. R-33 — the snapshot going stale silently — is mitigated for one day by
measurement rather than closed.

### 3.3 The levers, verified against the offer file rather than the marketing pages

```
FLEX          published for FOUR of five at exactly 50 percent of standard. Llama 4 Maverick
              publishes NO flex and NO priority price in any region under any usagetype — a
              property of the whole Llama family, not of one model. The resolved tier IS reported
              back in the Converse response as serviceTier.type, and a distinct ResolvedServiceTier
              CloudWatch dimension exists, which is the strongest available evidence that a
              requested tier and a served tier can differ. AWS never states the conditions.
BATCH         published for all five: at the flex rate for four, at 50 percent for Maverick.
              Asynchronous, S3 JSONL, 24 to 168 hour timeout.
PRIORITY      1.75x standard. STANDARD IS THE MIDDLE OF THREE SYNCHRONOUS PRICES, NOT THE FLOOR.
PROMPT CACHE  NOT published for ANY of the five, in ANY region, in ANY of the 10,995 priced
              dimensions of the offer file. Only Nova Micro, Nova Lite, Nova Pro, Nova Premier,
              Nova 2.0 Lite and Grok 4.3 publish cache rates under AmazonBedrock; Claude publishes
              them under a different service code.
```

**The caching finding independently corroborates `docs/llm/prompt-caching-investigation.md` from
the billing side rather than the documentation side: there is no rate at which a cache hit could be
charged.** The investigation's own reasoning is confirmed correct as well — FinTek places the
varying brief in the prefix and the invariant filing behind it, so even a caching-capable model
would recompute the whole filing on every call.

### 3.4 The long-context and large-output leaderboard

**Context and output limits are NOT returned by any Bedrock control-plane API.** Every figure below
is from an AWS model card fetched 2026-08-04.

| model | context | max output | modalities | profile required |
|---|---|---|---|---|
| Claude Opus 5 / Sonnet 5 / Fable 5 / Opus 4.8 / 4.7 / 4.6 / Sonnet 4.6 | 1M | 128K | text, image | YES |
| GLM 5 | 200K | 128K | text | no |
| Nova 2 Lite | 1M | 64K | text, image, video | YES |
| Claude Haiku 4.5 / Sonnet 4.5 | 200K | 64K | text, image | unverified |
| Nemotron 3 Super 120B | 256K | 32K | text | no |
| Mistral Large 3 | 256K | 32K | text, image | no |
| Llama 4 Scout | 10M | 8K | text, image | YES |
| Llama 4 Maverick | 1M | 8K | text, image | YES |

**The 1M-context / 128K-output combination exists only in the Claude family**, which is priced
under a different service code. Llama 4 Scout at 10M is the only model documented above 1M anywhere
on Bedrock. GLM 5 is the largest output limit outside Claude on an ordinary on-demand path, and its
200K context makes it INCOMPATIBLE with this filing.

### 3.5 A second Bedrock endpoint now exists

`bedrock-mantle` appears on most current model cards alongside `bedrock-runtime`, with AWS
recommending it, and three models are mantle-only: Grok 4.3, GPT-5.5 and GPT-5.4.
**`packages/llm_gateway/providers/bedrock.py` targets `bedrock-runtime`.** This is an architectural
fact Phase 2 and Phase 2.1 did not encounter. It is recorded, not adopted, and it needs its own
investigation before any adoption — it is R-36 below.

---

## 4. The six recommendation buckets

### ADOPT NOW

Nothing that changes semantic behaviour. The capability snapshot needs no replacement: zero drift
on all ten prices and all five limit pairs.

**The entity-decoding level in the anchor ladder is adopted, and it is not a model-facing change at
all.** It corrects a validator that could not find a quote containing an apostrophe in a filing
whose apostrophes are all escape sequences. Section 7.4 has the measurement.

### ADD TO APPLE BENCHMARK — identified, documented, and NOT run

A research-added candidate ranks below completing the current five, and the current five do not
fit. Each is documented so the decision is ready the moment a ceiling exists.

```
1  Amazon Nova 2 Lite     amazon.nova-2-lite-v1:0, via us.amazon.nova-2-lite-v1:0, profile REQUIRED
   price      0.00033 in / 0.00275 out per 1k standard; 0.000165 / 0.001375 flex;
              cache read 0.000144375
   limits     1M context, 64K max output, text + image + video
   advantage  the only model in the account combining a context that fits this filing with room to
              spare AND an output limit 8x that of three of the five candidates. Fewer parts is the
              single largest lever on a protocol whose cost is 80 percent re-sent input. It is also
              the only relevant model that publishes a prompt cache rate at all.
   risk       output is priced at 8.3x its input, so a 64K response costs USD 0.176; an inference
              profile is a data-residency decision
   max cost   one Apple run at 12 calls: USD 1.15 input plus output

2  Llama 4 Scout          meta.llama4-scout-17b-instruct-v1:0,
                          via us.meta.llama4-scout-17b-instruct-v1:0
   price      0.00017 in / 0.00066 out per 1k; no flex, batch at 50 percent
   limits     10M context, 8K max output, text + image
   advantage  removes the INPUT problem entirely for any filing in the 613-filing corpus, including
              the 12.9 MB JPMorgan 10-K that fits nothing else. Cheaper than Maverick in both
              directions, and a known transport path — it is Maverick's sibling.
   risk       8K output, so the part count stays high; against THIS filing it adds little that
              Maverick's 1M does not already give
   max cost   one Apple run at 14 calls: USD 0.58

3  Mistral Large 3        mistral.mistral-large-3-675b-instruct, ON_DEMAND, no profile
   price      0.0005 in / 0.0015 out per 1k; flex at 50 percent
   limits     256K context, 32K max output, text + image
   advantage  the largest parameter count in the account, multimodal, no profile and therefore no
              data-residency decision, and a 32K output limit matching the best of the current five
   risk       256K context means it fits only by shrinking the answer, the same trade as Nemotron;
              3.3x Nemotron's input price
   max cost   one Apple run at 20 calls: USD 2.50
```

### EXPERIMENT LATER

Flex at 50 percent, once a Standard baseline exists to compare against; mixing tiers inside one
comparison is forbidden. Reordering the payload so the invariant filing becomes the cacheable
prefix — a semantic change requiring re-benchmarking and, under `rules.md` section 21, explicit
approval, and one that buys nothing until a caching-capable model is approved. `bedrock-mantle` as
a second endpoint.

### DEFER

Batch, for corpus backfill rather than an interactive benchmark. Bedrock Evaluations, which needs
approved parse data that does not exist. Distillation and customization, for the same reason.

### REJECT FOR THE CURRENT PARSER ARCHITECTURE

```
Prompt routers            the exact parser model must remain known; hidden routing is
                          incompatible with attributing a measurement to a model
GLM 5                     on a measured ground rather than a preference: 200K context against
                          243,507 estimated input tokens
Nova Premier              LEGACY, with EOL 2026-09-14
Guardrails and            they can constrain a response; they cannot prove a filing was fully
Automated Reasoning       represented, and completeness evidence is what this phase is about
```

### REQUIRES USER DECISION

**Strict JSON-Schema structured output.** It would plausibly eliminate the serialization failures
that consumed five of fifteen Phase 2 responses — and the content boundary permits only plain text
or one unfenced YAML document in BOTH directions, so adopting it is a product-rule change and not a
free win. **Bedrock Data Automation in any role**; not created, not invoked. **Any use of the
`bedrock-mantle` endpoint.**

---

## 5. Part B — the harness defects repaired

### 5.1 Effective-artifact supersession — IMPLEMENTED

The survey found that the resolver deciding which artifact currently holds a part's content was a
44-line private static method on `MultipartParseService` with ONE call site, and that six other
consumers read the malformed original instead. **The reconciliation brief was shown `node_count 0`
for a part that had two nodes, and four of the five mechanical findings could not fire for such a
part at all.**

`packages/multipart/effective.py` is new: a named, generic, testable resolver. `_inventory_entries`
and the assembly loop both route through it, and an inventory row now names both the effective task
and the superseded original. **Three facts are reported separately and never collapsed:** raw
parseability, repair parseability, and effective usability. A parse that needed a repair is usable
AND its model did not serialise correctly; reporting only the first hides working evidence, and
reporting only the second credits a model with a document it did not produce.

### 5.2 Pre-transport reservation accounting — IMPLEMENTED

`packages/llm_gateway/errors.py` gains `CredentialResolutionError`, a `ProviderError` subclass
carrying `transport_attempted=False`. `ProviderError` itself gains `transport_attempted`,
defaulting to `True`. **The asymmetry of that default is deliberate: assuming a request was sent
when it was not merely holds ceiling, while assuming it was not sent when it was releases money
that was really spent.**

`packages/llm_gateway/providers/bedrock.py` gains `CREDENTIAL_EXCEPTION_NAMES`, an eleven-name
frozenset covering `TokenRetrievalError`, `UnauthorizedSSOTokenError`, `NoCredentialsError` and the
rest, and raises the new type for them.

`packages/orchestrator/spend_journal.py` gains `release()` and `unsettled()`. A RELEASE entry
carries `amount_usd 0` and `released_usd` equal to the reservation, so it contributes exactly the
negative of the reservation to `sum(amount - released)` and **no total needed different
arithmetic**. The journal stays append-only; nothing is edited or deleted, and a release REFUSES
without evidence text. The executor releases on a failure the adapter PROVES was never transported,
and on nothing else.

### 5.3 Part-explosion guardrails — IMPLEMENTED

The survey found the operational limits that existed: recursion depth 4, reconciliation cycles 3,
format repairs per artifact 1, automatic retries per attempt 1. **THERE WAS NO MAX-PARTS LIMIT AT
ALL.** `packages/orchestrator/multipart_service.py` now carries `soft_part_threshold` 64 and
`hard_part_ceiling` 100. **The soft threshold PAUSES the branch with its reason visible so a person
can look; the hard ceiling stops automatic scheduling.** Neither shrinks, drops or downgrades
anything already produced, which is ADR-0020 decision 5 applied to part count rather than to money.

### 5.4 Stable gap fingerprints — IMPLEMENTED

`packages/multipart/gaps.py` gives a gap a STRUCTURAL identity: a digest over the kind of finding
and the model-created identifier or filename it names, **and deliberately not over the prose**. Two
cycles describing the same missing material in different words are the same gap, and a hash of the
sentence would say they are different.

The defect it closes was observed in Phase 2.1 and recorded then as a cost of the brief rather than
as a defect claim: reconciliation cycles 2 and 3 of the GPT OSS run were re-shown the ORIGINAL
part's unresolved counts, because an earlier result is never overwritten. Cycle 1 named five
missing items and asked for four replacement parts; cycle 3 asked for ten more and recorded
`cycle_limit_reached`. **Nothing could tell cycle 3's ten requests from cycle 1's five, because a
gap was an opaque mapping with no key.** A repeated gap is still recorded and still shown; it
simply stops creating new billable work, and the repeat is counted so the no-progress rule can see
it.

---

## 6. An ADDITIVE correction to the Phase 2.1 reservation figure

**Found by reading the durable spend journal, not by re-reading the record.** `rules.md` section 21
rule 16 forbids rewriting a historical record, so **nothing in the Phase 2.1 record is altered**;
this is the forward correction and it supersedes the earlier figure by reference.

```
Phase 2.1 working record, section 33.14   USD 0.10396815 held across FOUR task ids
the durable journal                       USD 0.24197085 held across TWELVE task ids
```

**ELEVEN are the same credential failure**, and the four named in Phase 2.1 are a subset of them:
`TokenRetrievalError`, token expired and refresh failed, each with `attempts 1`, `input_tokens 0`,
`output_tokens 0`, `latency_ms 0`, `provider_request_id null`, task state `FAILED`, all taken
between `02:19:29` and `02:23:00` on 2026-08-04. They total `USD 0.22590990`. Section 5.2 is the
repair: none of these requests was ever transported, and the adapter can now prove it.

**THE TWELFTH IS A DIFFERENT DEFECT AND IT IS THE ONE WORTH KEEPING.** Task
`tsk_icujnsgypwpkxl6xxthsahrpya` SUCCEEDED, with real usage of 38,361 input and 1,228 output tokens
and a real provider request id, and it carries **TWO reservations of `USD 0.01606095` and ONE
settlement releasing one of them**. The task was interrupted after reserving, resumed, and reserved
again; the journal settled only the later entry. **`USD 0.01606095` leaked**, and it leaked through
the resume path rather than through a failure path — which means it is not addressed by section 5.2
and is carried as R-37 below.

---

## 7. The benchmark filing and its mechanical inventory

### 7.1 Identity, verified, and the package completed

```
issuer          Apple Inc.                 ticker  AAPL        CIK  0000320193
form            10-Q                       accession  0000320193-25-000008
filed           2025-01-31                 report period  2024-12-28
transport era   inline XBRL                package members  63
```

**58 of 63 members were already held.** Five were acquired from SEC this phase: the complete
submission `0000320193-25-000008.txt` at 5,150,277 bytes, and four XBRL linkbases (`_cal`, `_def`,
`_lab`, `_pre`). Approved User-Agent, the project's own shared rate limiter, **zero throttle
events**. 9.9 MB preserved under `var/objects/filings/0000320193/000032019325000008/`. A re-run
makes ZERO SEC requests.

**The envelope self-report disagrees with the envelope.** `PUBLIC DOCUMENT COUNT` declares 63; the
envelope contains 62 `DOCUMENT` blocks. **Recorded, not reconciled** — it is the same class of
discrepancy Phase 2.1 measured on the Macy's filing, and inventing a reconciliation rule for it
would be backend code deciding what a filing contains.

### 7.2 Mechanical disposition of all 63 members

| disposition | count | bytes | reaches the parser |
|---|---:|---:|---|
| `PARSER_INPUT_TEXT` | 6 | 915,890 | YES, intact, as itself |
| `PARSER_INPUT_IMAGE` | 2 | 14,394 | YES, to a multimodal parser |
| `MACHINE_ONLY` | 5 | 1,081,224 | no — XBRL schema and linkbases |
| `SEC_GENERATED_RENDERING` | 49 | 2,459,551 | no — EDGAR's IDEA renderer |
| `DUPLICATE_COMPLETE_SUBMISSION` | 1 | 5,150,277 | its content reaches it as the addressable members |
| `UNKNOWN_REQUIRES_REVIEW` | 0 | 0 | nothing failed closed |

The six human-readable members:

```
seq  filename                        bytes  SEC-declared type
  1  aapl-20241228.htm             732,589  10-Q (inline XBRL primary)
  2  a10-qexhibit10112282024.htm    71,323  EX-10.1
  3  a10-qexhibit10212282024.htm    82,509  EX-10.2
  4  a10-qexhibit31112282024.htm    10,529  EX-31.1
  5  a10-qexhibit31212282024.htm    10,568  EX-31.2
  6  a10-qexhibit32112282024.htm     8,372  EX-32.1
                                   -------
                                   915,890  total decoded characters
```

The two filed images, and one of them is not what it says it is:

```
seq  filename                bytes  declared  actual signature  pixels
 12  aapl-20241228_g1.jpg   10,963  GRAPHIC   jpeg               46x56
 13  image_0.jpg             3,431  GRAPHIC   PNG              294x368
```

**`image_0.jpg` is declared GRAPHIC, named `.jpg`, and is PNG bytes.** The disposition module reads
the byte signature rather than the extension, which is the only reason this was seen at all. It is
recorded as an observation about this filing and is not generalised.

### 7.3 The mechanical inventory — the denominator Phase 2.1 lacked

Built by the new `packages/source_inventory` over the preserved bytes, **in 0.4 seconds, with no
model involved.**

```
members inventoried              63        human-readable members         6
visible text spans            1,750        of 1,757 total
spans hidden by source markup     7        6 DOCUMENT_HEAD, 1 STYLE_SUPPRESSED
spans mechanically duplicate    607
visible source characters   229,410
table elements                   41        images                         2
source_set_sha256   ca1b1f461fb695c5e10c1ac3e16dca0ad216f08fd4e87f8f59350b38cc90e465
```

| member | characters | spans | tables |
|---|---:|---:|---:|
| `aapl-20241228.htm` | 732,589 | 1,486 | 37 |
| `a10-qexhibit10112282024.htm` | 71,323 | 96 | 0 |
| `a10-qexhibit10212282024.htm` | 82,509 | 110 | 0 |
| `a10-qexhibit31112282024.htm` | 10,529 | 21 | 1 |
| `a10-qexhibit31212282024.htm` | 10,568 | 22 | 1 |
| `a10-qexhibit32112282024.htm` | 8,372 | 22 | 2 |

The 41 table elements, classified **by bytes only**:

```
18  carry 20 or more non-empty cells
 8  carry no non-whitespace character at all
 7  are byte-identical to an earlier element
 0  are nested
```

**Only the last three of those are prefilled as suggestions**, and neither suggestion is applied
until a person accepts it. Which of the 18 substantive elements is a financial statement and which
is a layout grid is a human judgement — ADR-0021 decision 4.

**THE 56,644-CHARACTER HIDDEN SPAN.** One span of the primary document is the inline-XBRL hidden
fact block: a `div` carrying `display:none` that holds every tagged-but-not-displayed fact. It is
recorded with its reason and excluded from the visible denominator. That is a transport observation
rather than a judgement, and it is exactly the kind of thing a coverage denominator gets wrong if
it counts characters without reading the markup that governs them.

### 7.4 970 character references, and ZERO literal non-ASCII characters

```
655 of &#160;   116 of &#8217;   53 of &#8212;   51 each of &#8220; and &#8221;
```

**Every non-breaking space, apostrophe, em dash and quotation mark in this filing is an escape
sequence.** A model quoting a sentence back writes the CHARACTER. **Without entity decoding in the
resolution ladder, every quote containing an apostrophe would have failed to resolve — and the
failure would have been indistinguishable from a fabricated citation.** This is the same class of
defect Phase 2.1 saw as "a non-breaking hyphen" among GPT OSS's twelve unresolved references.
Verified fixed: a quote containing a real em dash now resolves against a filing that contains only
`&#8212;`.

---

## 8. Intact-source compatibility — R-21 bites for the first time

Measured with the repository's own compatibility guard, the committed capability snapshot and the
multipart PART prompt. **Token figures are CHARACTER-RATIO ESTIMATES at 3.8 characters per token,
an upper bound and not a tokenizer count** — R-24 is unchanged and still open.

| model | context | estimated input | largest output that fits |
|---|---:|---:|---:|
| GPT OSS 120B | 128,000 | 243,507 | **0 — INCOMPATIBLE** |
| NVIDIA Nemotron 3 Super 120B | 256,000 | 243,507 | 12,493 |
| Qwen3 235B A22B | 256,000 | 243,507 | 8,000 |
| Llama 4 Maverick | 1,000,000 | 251,507 | 8,000 |
| Qwen3 VL 235B | 256,000 | 251,507 | 4,493 |

The estimated input for the two multimodal candidates includes 2 images charged at the UNVERIFIED
4,000-tokens-per-image upper bound the pre-spend guard uses.

**GPT OSS 120B IS INCOMPATIBLE, AND NOT MARGINALLY.** The complete human-readable source set is
roughly 1.9x its entire context window. No output request makes it fit. Under INTACT_SOURCE_ONLY
and `rules.md` section 21 rules 6, 9 and 10, that is a RESULT recorded as an exact blocker: no
truncation, no slicing, no substitution.

**NEMOTRON AND QWEN3 VL FIT ONLY BY SHRINKING THE ANSWER.** Nemotron's own output cap is 32,000 and
it fits at 12,493; Qwen3 VL's is 8,000 and it fits at 4,493, leaving 493 tokens of headroom —
inside the error bar of a character-ratio estimate. **A smaller answer per call means more parts,
which means more calls, each re-sending 243,507 input tokens.**

**THIS IS R-21, AND IT IS NO LONGER HYPOTHETICAL.** R-21 reads "No candidate model accepts a
materially sized modern filing intact", status OPEN. Phase 2 and Phase 2.1 could not touch it,
because by construction the shared benchmark could only contain filings that fit every candidate.
This filing does not.

---

## 9. The dry-run call plan — computed, not assumed

Per-call cost is the estimated intact input at each candidate's own verified price, plus **that
candidate's OWN measured Phase 2.1 mean output per call**. No model's call count, output size or
repair rate is applied to another.

| model | estimated input | USD/call | Phase 2.1 calls | USD at that count |
|---|---:|---:|---:|---:|
| GPT OSS 120B | 243,507 | — | — | INCOMPATIBLE |
| NVIDIA Nemotron 3 Super 120B | 243,507 | 0.03790 | 78 | 2.9564 |
| Qwen3 235B A22B | 243,507 | 0.05556 | 58 | 3.2228 |
| Llama 4 Maverick | 251,507 | 0.06086 | 14 | 0.8520 |
| Qwen3 VL 235B | 251,507 | 0.13496 | 47 | 6.3433 |
| **TOTAL, four runnable candidates** | | | | **13.3745** |

Guardrail-bounded maximum, at the hard ceiling of 100 logical parts plus one plan, three
reconciliation cycles and six repairs — 110 calls each:

```
NVIDIA Nemotron 3 Super 120B    110 calls     4.1693
Qwen3 235B A22B                 110 calls     6.1121
Llama 4 Maverick                110 calls     6.6943
Qwen3 VL 235B                   110 calls    14.8460
                                            --------
TOTAL                                        31.8218
```

**Neither total is a corpus figure and neither extrapolates.** It is one filing, priced at prices
verified on 2026-08-04, using call counts measured on a DIFFERENT filing in Phase 2.1. The Phase
2.1 call counts were produced on a 146,471-byte 1996 10-K405; this filing is 915,890 human-readable
characters. **Whether a candidate needs more calls on a larger filing is exactly the thing that has
not been measured**, which is why section 1 calls every figure a floor.

---

## 10. What was built

Two new packages, four extended, one new prompt role and six new prompt versions, and **no new
runtime dependency**.

```
packages/source_inventory          the mechanical inventory: members, visible text spans, table
                                   elements, images, byte-level duplication. Standard library only.

packages/completeness              the six-dimension status model; interval algebra over one
                                   member's character offsets; the versioned human benchmark truth;
                                   the ledger with four dispositions per item; the
                                   fourteen-condition mechanical candidate gate; structured-table
                                   validation

packages/multipart                 + effective.py, the shared effective-artifact resolver
                                   + tables.py, the structured-table envelope reader
                                   + gaps.py, stable structural gap fingerprints

packages/coverage_validation       + references.py rebuilt: the SIX-LEVEL anchor ladder replacing
                                     three levels, entity decoding, lazy transforms with identity
                                     shortcuts, composed index maps back to original offsets

packages/llm_gateway               + errors.py: CredentialResolutionError and
                                     ProviderError.transport_attempted
                                   + providers/bedrock.py: CREDENTIAL_EXCEPTION_NAMES

packages/orchestrator              + spend_journal.py: release() and unsettled()
                                   + multipart_service.py: part-explosion guardrails, and every
                                     consumer routed through the shared effective-artifact resolver

prompts/parser/                    six v2 families plus parser-multipart-table-v1, all registered
                                   in versions.yaml and hash-locked
```

**The v2 prompt families carry the v1 semantic request word for word where it applies** and add
three things and nothing else: the coverage-claim contract, the structured-table contract, and the
image contract. The v1 families are untouched and every result they produced is preserved —
`prompts/parser/versions.yaml` refuses to load a version whose bytes have moved.

---

## 11. Test and validation state

```
pytest tests                        1,564 passed, 0 skipped, 0 failed
ruff format --check packages tests  clean
ruff check packages tests           clean
mypy packages                       clean over 119 source files
```

**No existing test was weakened, disabled, skipped or deleted.** The suite still has no
environmental precondition of any kind — no database, no network, no credentials — which is why
`make test-no-skips` is the same suite as `make test` and why a skip has no legitimate cause.

---

## 12. What this phase did NOT do

```
no provider request issued                  measured Bedrock spend USD 0.00000000
no model selected, ranked or promoted       no model eliminated on quality grounds
no Phase 2.5 breadth work                   no Phase 3 work
no summary model invoked                    no image model invoked
no analysis/chat model invoked              no Redis
no application database                     nothing deployed
no research-added candidate run             no bedrock-mantle call
no historical record rewritten              nothing staged or committed by this phase
```

**AND, AFTER ALL OF THE ABOVE, THESE REMAIN UNMEASURED:**

```
COMPLETENESS ITSELF     The ledger, the ladder, the table contract and the fourteen-condition gate
                        exist and are tested. NO PARSE HAS BEEN MEASURED THROUGH THEM, because no
                        model was invoked. Section 1 is why.

THE HUMAN BENCHMARK     No span, table or image of the Apple filing has been classified by a
TRUTH                   person. Every item defaults to REQUIRES_REVIEW, so the gate cannot pass for
                        any parse until that work is done — which is the correct pressure and is
                        also real work: 1,750 visible spans, 41 table elements, 2 images.

CORRECTNESS             Unchanged from Phase 2.1. review_history is still empty on all seven runs.

REPEAT-RUN VARIABILITY  Unchanged from Phase 2.1. No filing has been parsed twice by the same
                        model under either protocol.

TABLE STRUCTURE         Whether any candidate CAN emit a structured table is still untested. A
                        prompt now asks; no model has been asked.
```

---

## 13. Risks

| ID | Movement |
|---|---|
| R-09 | Unit economics. **Sharpened, not closed.** A per-call cost now exists for one materially sized modern filing per candidate — from USD 0.03790 to USD 0.13496 across four candidates on the same bytes. The per-FILING cost is still unmeasured, because no run happened. |
| R-20 | Intact submission unaffordable or impossible for a large fraction of filings. **First direct evidence.** One 2025 10-Q at 915,890 human-readable characters is INCOMPATIBLE with one of five approved candidates and costs USD 13.3745 across the other four at Phase 2.1 call counts. One filing is not a fraction of a corpus. |
| R-21 | No candidate model accepts a materially sized modern filing intact. **STILL OPEN, AND NOW EVIDENCED FOR THE FIRST TIME.** GPT OSS 120B is INCOMPATIBLE with this filing by a factor of roughly 1.9; two more fit only by shrinking the answer. |
| R-23 | Repeat-run variability. **UNCHANGED and still OPEN.** No filing has been parsed twice by the same model. |
| R-24 | Character-ratio token estimates. **UNCHANGED and still OPEN.** Every compatibility figure in section 8 is a character-ratio estimate at 3.8 chars/token, an upper bound. Qwen3 VL's 493 tokens of headroom is inside the error bar of that estimate. |
| R-33 | The capability snapshot goes stale silently. **MITIGATED FOR ONE DAY, NOT CLOSED.** Zero drift measured 2026-08-04 across all ten prices and all five limit pairs. Nothing in the repository detects the next change. |
| R-34 | Discovery ran under a broad administrator role. **UNCHANGED and still OPEN.** This phase's research was read-only and created no resource; a least-privilege Bedrock policy is still required. |
| R-35 | An expiring SSO session interrupts a long multipart run. **PARTIALLY MITIGATED.** A credential failure before transport is now provable and its reservation is released — section 5.2 — so the interruption no longer silently holds ceiling. The interruption itself is unchanged. |
| R-36 | **NEW.** A second Bedrock endpoint, `bedrock-mantle`, now exists and AWS recommends it; three models are reachable only through it. `packages/llm_gateway/providers/bedrock.py` targets `bedrock-runtime` and has no knowledge of the other. Adopting it is a REQUIRES USER DECISION item, and not adopting it silently narrows the candidate universe. |
| R-37 | **NEW.** A task interrupted after reserving and then resumed reserves again, and only the later entry settles. Measured once: `tsk_icujnsgypwpkxl6xxthsahrpya`, `USD 0.01606095` leaked. This is the RESUME path, not the failure path, and section 5.2's release mechanism does not address it. |

---

## 14. The decision this phase stops at

Unchanged in substance from Phase 2 and Phase 2.1 — **which parser and prompt version advances to
breadth validation across all 22 substantive form strings** — and blocked one step earlier than
before, on money rather than on evidence.

**ONE DECISION IS REQUIRED AND IT IS THE ONLY THING BLOCKING THE BENCHMARK.**

```
The authorized new-invocation ceiling is USD 5.00.
Four of the five mandatory candidates can receive this filing intact; GPT OSS 120B cannot.
Running those four at their own measured Phase 2.1 call counts costs USD 13.3745, and the
    hardened protocol raises that figure rather than lowering it.
Splitting USD 5.00 equally lets ONE of the four finish and pauses three mid-parse.
```

`rules.md` section 21 rule 11 forbids a billable invocation without explicit authorization and a
cost ceiling, and running a partial arbitrary subset would produce a comparison drawn from one
candidate — which is the reasoning rule 14 forbids. **Nothing billable runs until this is
answered.**

**Nothing in this record selects, ranks, promotes or eliminates a parser.** The five candidates
remain equally available for user-directed testing, the single-response protocol remains runnable,
and the seven preserved Phase 2.1 runs and thirty preserved Phase 2 runs are untouched.
