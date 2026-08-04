# Bedrock prompt caching, and why none of it is available to this project

STATUS: INVESTIGATED, NOT ENABLED
DATE: 2026-08-03
PHASE: 2.1
RE-VERIFIED: 2026-08-04 (Phase 2.2), from the billing side, independently — section 6
DECISION RECORD: [ADR-0020](../adr/ADR-0020-model-directed-multipart-parsing.md), decision 3

---

## Why this was investigated

Model-directed multipart parsing re-sends the **complete intact filing on every semantic
invocation** — the plan, every part, every subpart, every replanning call, reconciliation and gap
repair. On the primary proof filing that is roughly 40,000 input tokens per call, and a parse of a
dozen calls pays for it a dozen times.

Prompt caching, if it were available, would make that repetition close to free. Section 24 of the
Phase 2.1 brief therefore required it to be investigated before the protocol was accepted, and
required the investigation to record what is verified rather than what is plausible.

**It is not available.** The rest of this document is the evidence.

---

## 1. The live control plane

Queried on 2026-08-03 under a temporary IAM Identity Center role, `us-east-1`, no static
credential:

```
bedrock:ListFoundationModels        119 models visible to this account
bedrock:GetFoundationModel          per-candidate
bedrock:ListInferenceProfiles       per-region
```

Every field `ListFoundationModels` returns, for every one of the 119 models:

```
customizationsSupported   inferenceTypesSupported   inputModalities   modelArn
modelId                   modelLifecycle            modelName         outputModalities
providerName              responseStreamingSupported
```

Every field `ListInferenceProfiles` returns:

```
createdAt   description   inferenceProfileArn   inferenceProfileId
inferenceProfileName      models   status   type   updatedAt
```

**No field mentions caching, on any model or any profile.** `GetFoundationModel` on
`openai.gpt-oss-120b-1:0` returns the same shape and adds nothing.

> **This is evidence of NON-EXPOSURE, not evidence of absence.** The control plane does not
> describe caching support for anything, including the models AWS documents as supporting it. It
> cannot be used to conclude that a model does or does not support caching. It is recorded because
> a future reader will otherwise re-run these calls expecting an answer.

---

## 2. The AWS documentation

`https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html`, read 2026-08-03. Its
supported-models table lists, in full:

```
Claude Opus 4.5      Claude Opus 4.6      Claude Sonnet 4.5    Claude Sonnet 4.6
Claude Haiku 4.5     Claude Opus 4        Claude 3.7 Sonnet    Claude 3.5 Sonnet v2
GPT-5.6 Sol          GPT-5.6 Terra        GPT-5.6 Luna
```

The page separately records that Amazon Nova performs automatic prompt caching for text prompts,
and that OpenAI models **prior to GPT-5.6** cache automatically through the Responses API on the
`bedrock-mantle` endpoint.

**None of the five approved candidates appears anywhere on that page.**

```
GPT OSS 120B                    not listed
NVIDIA Nemotron 3 Super 120B    not listed
Qwen3 235B A22B                 not listed
Llama 4 Maverick                not listed
Qwen3 VL 235B                   not listed
```

### The one ambiguity, recorded rather than resolved

The caching page says the table "shows prompt caching for models that are not present in
models-at-a-glance", and directs the reader to each model's own card for the rest. Both the
`gpt-oss-120b` and `Llama 4 Maverick 17B Instruct` cards were read on the same date. **Their
"Capabilities and Features" tables render as an interactive element that the fetched page does not
carry**, so the cards could neither confirm nor deny per-model caching support.

That is a limit of the investigation and is stated as one. What the cards DID confirm, and what is
already in the capability snapshot, is the invocation surface: `gpt-oss-120b` supports Converse,
Invoke, Chat Completions and Responses across `bedrock-runtime` and `bedrock-mantle`; Llama 4
Maverick supports Converse and Invoke on `bedrock-runtime` only, with no `bedrock-mantle` endpoint
and no Responses API.

### Why the `bedrock-mantle` note does not rescue GPT OSS 120B

Automatic caching for OpenAI models is documented for **GPT-5.5 and earlier GPT-5 models** through
the **Responses API**. GPT OSS 120B is a different model family, is not named in that section, and
this project invokes it through **Converse on `bedrock-runtime`**, which is the route the
capability snapshot verified and the route `packages/llm_gateway/providers/bedrock.py` implements.
Nothing in the documentation states that a Converse request to `openai.gpt-oss-120b-1:0` caches.

---

## 3. What was deliberately NOT done

**No live `cachePoint` probe was run.** Section 24 asks for "minimal non-billable discovery where
possible", and a Converse request carrying a `cachePoint` block could not be shown in advance to be
non-billable: a request that is accepted runs inference and is charged, and this project does not
spend money to discover a fact the documentation already answers.

**Prompt caching is not enabled in production code, and no code path constructs a `cachePoint`.**
The Phase 2.1 brief's five preconditions for enabling it — verified support for that exact model
and route, recorded cache boundaries, understood cost behaviour, tests covering the uncached
fallback, and no silent semantic change — are not met, and the first of them fails outright.

---

## 4. What this costs, stated plainly

The multipart workflow re-sends the intact filing on every semantic call and pays the full
uncached input rate for it, every time. That is the dominant input cost of a multipart parse and
there is no relief available.

It is worth being precise about what caching would and would not have changed:

```
WOULD have reduced    the input cost of re-sending an identical filing prefix across the plan
                      call and every part call of one parse
WOULD NOT have changed  the number of calls, the output cost, the latency of generation, or
                      anything about correctness
```

The protocol was designed to work correctly without caching, and it does. Caching is an
optimisation this project cannot currently buy.

---

## 5. Revisit conditions

```
a candidate appears on the AWS prompt-caching supported-models table
AWS documents Converse-path caching for a model this project actually invokes
the control plane begins exposing a caching capability field, which would make the fact
    verifiable the same way every other capability in the snapshot is
the capability snapshot is regenerated for any other reason — re-check this at the same time
```

When any of those holds, the finding is re-verified and recorded here with its date; the
capability snapshot gains the fields the brief requires (supported, applicable invocation API,
minimum cacheable prefix, cache lifetime, pricing, region limitations, image cacheability); and
enabling it remains a separate decision requiring the five preconditions above.

---

## 6. Independent corroboration from the billing side — added 2026-08-04, Phase 2.2

Sections 1 and 2 rested on a control plane that describes caching for nothing and on a
documentation page that could be out of date. **Phase 2.2 asked a third source that has no reason
to agree with either: the AWS Price List offer file, which is what a cache hit would actually be
BILLED against.** A capability with no published rate cannot be charged, so a missing price row is
stronger evidence than a missing documentation row.

Read 2026-08-04, read-only, no invocation:

```
10,995   priced dimensions in the AmazonBedrock offer file
     0   cache price rows for GPT OSS 120B, in any region
     0   cache price rows for NVIDIA Nemotron 3 Super 120B, in any region
     0   cache price rows for Qwen3 235B A22B, in any region
     0   cache price rows for Llama 4 Maverick, in any region
     0   cache price rows for Qwen3 VL 235B, in any region
```

**ZERO FOR ALL FIVE, ACROSS EVERY REGION THE OFFER FILE PRICES.** This does not merely fail to
confirm caching; it removes the mechanism by which a cache hit could be charged differently from an
ordinary input token.

### The six that DO publish a cache rate, which is what makes the zero above meaningful

A scan that found nothing anywhere would be evidence about the scan. This one found rates:

```
Amazon Nova Micro     Amazon Nova Lite      Amazon Nova Pro
Amazon Nova Premier   Amazon Nova 2.0 Lite  Grok 4.3
```

The Claude family publishes cache rates too, under a **different service code**, which is why it
does not appear in an `AmazonBedrock` scan and why its absence there means nothing.

Two of those six are worth naming precisely, because a reader will otherwise re-derive them:
**`Amazon Nova 2 Lite` is the only model relevant to this project's filing sizes that publishes a
cache rate** — `0.000144375` per 1k cache read, alongside 1,000,000 context and 64,000 max output —
and **`Amazon Nova Premier` is LEGACY with an announced end of life of 2026-09-14**, so its rate is
not a route to anything. Neither is an approved candidate; see `model-benchmark.md`, Phase 2.2.

### The request-ordering reasoning is CONFIRMED, and it is the part that would still bite

`cost-model.md` and ADR-0020 both record that FinTek would get no relief from caching even on a
caching-capable model, because of the order in which it builds a request. That reasoning was
re-checked against `packages/llm_gateway/providers/bedrock.py` in this phase and is correct:

```
what the adapter sends    the per-call BRIEF first, then the intact filing after it
why                       the instruction must be readable before the filing it concerns
what caching matches      a strict token PREFIX
the consequence           the brief VARIES per call, so the invariant filing is not a shared
                          prefix at all, and a caching-capable model would recompute the whole
                          filing on every call anyway
```

**THAT MAKES THE ORDERING A SEMANTIC DECISION WITH A PRICE ATTACHED, NOT A BUG.** Reordering the
payload so the invariant filing becomes the cacheable prefix would change what every model sees on
every call, which requires re-benchmarking and, under `rules.md` section 21, explicit approval —
and it buys exactly nothing until a caching-capable model is an approved candidate. It is recorded
as an EXPERIMENT LATER, and nothing in the code was changed.

**NOTHING WAS ENABLED, NOTHING WAS PROBED, AND NO `cachePoint` BLOCK EXISTS ANYWHERE IN THIS
REPOSITORY.** Section 3 still holds in full.
