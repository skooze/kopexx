# Runbook — Bedrock capability discovery and the functionality gates

IMPLEMENTATION STATUS: IMPLEMENTED. Executed once, on 2026-08-03, producing
[the reviewed capability snapshot](../llm/bedrock-capability-snapshot.yaml).

PURPOSE. Reproduce the Phase 1 evidence: map each user-facing candidate label to a real provider
model, verify region, access, modality, limits and price, and obtain one minimal real response from
every candidate that is reachable.

WHEN TO RE-RUN. Whenever a candidate is added or withdrawn, whenever a price or a region changes,
and before any Phase 2 cost commitment. **Replace the snapshot wholesale.** Do not edit one field
and leave the rest carrying a date they no longer earned.

---

## What this runbook is not

It is not a benchmark. The gates prove that identity reaches the runtime, that an identifier is
valid, that the role may invoke it, that the request format is accepted, and that a response comes
back. Quality, reasoning, long context and prompt behaviour are all Phase 2, and running them here
would produce a number before there is anything to compare it against.

**No SEC filing is sent. No user data is sent. No secret is sent.**

---

## Forward note, added 2026-08-03 — Phase 2 built an adapter, and this procedure is unchanged

> **Nothing below this note has been edited.** Steps 1 through 6 remain the whole procedure.

STATUS: IMPLEMENTED. When this runbook was written there was no provider adapter at all — Phase 1
reached Bedrock with the AWS CLI, by hand, and `packages/model_catalog` held no AWS import. Phase 2
built `packages/llm_gateway/providers/bedrock.py`, the Bedrock Converse adapter and the only module
in the repository that imports an AWS SDK. It is reached only through `packages/llm_gateway`, it is
handed an invocation identifier and a region and uses exactly those — no fallback model, no fallback
region, no substitution — and the region is derived by `packages/model_catalog/routing.py` from this
same snapshot, so a cross-region route is disclosed before the call rather than discovered in a bill.
The adapter is constructed with a region and nothing else; temporary credentials stay with the SDK's
default provider chain and never reach this code.

**The snapshot is still regenerated wholesale by the manual discovery below.** The adapter invokes
models; it does not maintain the capability record. It calls `Converse` and nothing else — it never
calls `list-foundation-models`, `get-foundation-model-availability`, `get-inference-profile` or the
Price List API, and it cannot read a context limit or a price from anywhere. Identity, availability,
modality, limits and price are re-established by Steps 1 through 6, by hand, exactly as written. What
has changed is that the INVOCATION half of a re-verification no longer needs bespoke code: a
candidate can now be exercised through the same shipped path the product uses, so what a re-check
proves is what a real run would do.

`boto3` is an OPTIONAL EXTRA, and that is the point:

```bash
pip install -e '.[aws]'
```

Ordinary CI installs `.[dev]`, so "ordinary CI is AWS-free" means the provider SDK is not present at
all rather than merely unused. The adapter imports it lazily inside the client factory and, when it
is absent, raises a named error carrying that exact command — so a host that was never meant to reach
a model fails with an instruction instead of an `ImportError` somebody works around.

The Phase 2 benchmark driver is `var/local-tools/phase2_benchmark.py`, under the same gitignored
directory and for the same reason as `phase1_smoke.py`: it is an instrument that can spend money, and
`tests/architecture/test_phase1_aws_boundary.py` fails the build if such an instrument or the
evidence it produces ever becomes tracked. It implements nothing — source-set assembly, routing,
preflight, the cost ceiling, the gateway, the adapter, validation and the evaluation store are all
shipped packages; the driver chooses the set, orders the runs and prints what happened. Logic living
there would be untested and unshipped. It refuses to run without an explicit opt-in flag,
`--i-authorize-billable-invocations`; `--dry-run` prints the full preflight and spends nothing. Its
results land in the gitignored `var/evaluation-runs/`, and the cumulative ceiling it charges against
is `packages/orchestrator.SpendJournal`, which is durable and does not reset when the process does.

**No measured figure from those runs is recorded here, and none may be copied here.** This document
is the discovery procedure; parse quality, token counts and cost per filing belong to the Phase 2
record, and every model identifier, region, limit and price belongs to
[the reviewed capability snapshot](../llm/bedrock-capability-snapshot.yaml) and to nowhere else.

---

## Forward note, added 2026-08-04 — Phase 2.2 re-ran this read-only, and found zero drift

> **Nothing below this note has been edited either.** Steps 1 through 6 remain the whole procedure,
> exactly as Phase 1 wrote them. What follows is a record of a re-run and of three method details
> worth keeping.

STATUS: IMPLEMENTED. Executed 2026-08-04, `us-east-1`, under a temporary IAM Identity Center role
resolved by the SDK provider chain. No static credential existed, none was created, none is
recorded.

```
RAN        Step 2, control-plane discovery
           Step 3, limits and prices
NOT RUN    Step 4, the functionality gates. NO model was invoked
COST       USD 0.00000000. Nothing in Steps 2 and 3 is billable, which is why a re-verification
           is a routine check and not a project
RESULT     ZERO DRIFT. All ten committed prices match the live Price List API TO THE DIGIT,
           effective 2026-07-01. All five committed context and output limits match the AWS model
           cards read 2026-08-04. The snapshot was NOT rewritten, because nothing in it moved
```

**WHEN NOTHING MOVED, DO NOT REWRITE THE SNAPSHOT.** The standing instruction above — replace it
wholesale, never field by field — is about a snapshot that has to change. Regenerating an unchanged
file so it carries a newer date is the same defect approached from the other side: a date the
evidence did not earn.

### Method detail 1 — a census records ENTITLEMENT, not only presence

`list-foundation-models` returning a model does not mean this account may invoke it. The 2026-08-04
census recorded both, and the two happened to agree:

```
119   foundation models visible in us-east-1
 88   of them emit text
 88   AUTHORIZED, entitlement AVAILABLE — nothing is blocked in this account
 63   system-defined inference profiles, across two geographies, us. and global
```

The five approved candidates were unchanged: present, ACTIVE, same inference types, same
modalities, same access status. `Qwen3 235B A22B` is still absent from `us-east-1` and present in
`us-west-2` exactly as Step 2's "the live API outranks the documentation" note predicts, and
`Llama 4 Maverick` still cannot be invoked by bare model id.

### Method detail 2 — to prove a NEGATIVE about a price, enumerate the offer file

This is the detail most worth keeping, because the obvious approach cannot answer the question.

**Querying `get-products` per model tells you what a model IS priced for. It cannot tell you what
no model is priced for**, and "does any of the five publish a prompt-cache rate, in any region"
is a question of the second kind. Five negative lookups are five chances to have queried the wrong
filter.

Phase 2.2 enumerated **every priced dimension in the `AmazonBedrock` offer file — 10,995 of them —
and scanned the whole set**. That turns five absences into one exhaustive statement, and it also
produces the control the scan needs to be believable:

```
ZERO      cache price rows for any of the five approved candidates, in any region
SIX       models DO publish cache rates under AmazonBedrock: Nova Micro, Nova Lite, Nova Pro,
          Nova Premier, Nova 2.0 Lite, Grok 4.3
NOTE      the Claude family publishes cache rates under a DIFFERENT service code, so its absence
          from an AmazonBedrock scan means nothing at all
```

A scan that found nothing anywhere would be evidence about the scan. Full record:
[the prompt-caching investigation](../llm/prompt-caching-investigation.md), section 6.

The same enumeration re-confirms why **Step 3 records the STANDARD tier only**, with a measurement
rather than a caution: `flex` is published for four of the five at exactly 50 percent of standard
and `batch` for all five, while **`Llama 4 Maverick` publishes no flex and no priority price in any
region under any usagetype** — a property of the whole Llama family. `priority` is 1.75x standard,
so **standard is the MIDDLE of three synchronous prices, not the floor**. Recording a cheaper tier
the code does not request would understate cost, which is the one direction a cost estimate must
never be wrong in.

One asymmetry to know before enabling a tier: the resolved tier IS reported back in the Converse
response as `serviceTier.type`, and a distinct `ResolvedServiceTier` CloudWatch dimension exists.
That is the strongest available evidence that a REQUESTED tier and a SERVED tier can differ. **AWS
never states the conditions under which they do**, so a measurement taken across mixed tiers cannot
be attributed.

### Method detail 3 — a second runtime endpoint now exists, and this project does not use it

`bedrock-mantle` appears on most current model cards alongside `bedrock-runtime`, with AWS
recommending it, and **three models are mantle-only** (`Grok 4.3`, `GPT-5.5`, `GPT-5.4`).

```
IMPLEMENTED           packages/llm_gateway/providers/bedrock.py targets bedrock-runtime, and
                      every measurement this repository holds was taken through it
REQUIRES USER         any use of bedrock-mantle. It is a second transport surface with its own
DECISION              request shape, its own model set and its own caching story, and adopting
                      it would change what a preserved request means
```

This is an architectural fact Phase 1, Phase 2 and Phase 2.1 did not encounter. It is recorded so
that the next person reading a model card and seeing two endpoints knows which one produced the
snapshot.

---

## Preconditions

```
an AWS identity resolved through federation or an assumed role, never a long-lived key
the AWS CLI on PATH
a cost ceiling authorized by the user, in writing, for this run
```

The local profile name and the account identifier are **host state and stay out of Git**.
`docs/security/aws-identity-and-secrets.md` forbids account identifiers in tracked configuration and
this repository is public. Keep them in personal notes or under the gitignored `var/local-tools/`.

Set them process-locally when running the commands below:

```bash
export AWS_PROFILE="<your local profile name>"
export AWS_REGION="us-east-1"
export AWS_DEFAULT_REGION="us-east-1"
```

**Never write those values into a tracked file merely to run a command.**

---

## Step 1 — prove identity, without reading a credential

```bash
aws sts get-caller-identity
```

Record only the account identifier, the principal category, and the region — in your own notes, not
here. Never open, print, copy or commit anything under `~/.aws/sso/cache`, and never record an
access-key id, a secret key, a session token, an authorization header or a full role-session ARN.

If the session has expired, re-authenticate through your federation mechanism. **Do not replace SSO
with a static key**, for any reason, including convenience.

---

## Step 2 — control-plane discovery, which bills nothing

```bash
aws bedrock list-foundation-models --by-provider <Provider>
aws bedrock get-foundation-model --model-identifier <exact-model-id>
aws bedrock get-foundation-model-availability --model-id <exact-model-id>
aws bedrock list-inference-profiles
aws bedrock get-inference-profile --inference-profile-identifier <profile-id>
```

For each candidate LABEL, establish:

```
the exact provider model id           whether the mapping is UNIQUE
availability in this account          agreement, authorization and entitlement status
inferenceTypesSupported               ON_DEMAND, or INFERENCE_PROFILE and therefore a profile id
inputModalities                       whether IMAGE appears at all
responseStreamingSupported            the regions the model actually answers in
```

**`inferenceTypesSupported: [INFERENCE_PROFILE]` means the bare model id is not invocable.** The
profile id is what a caller uses, and `get-inference-profile` lists the regions it routes across —
a data-residency fact, not only a throughput one.

Query only the regions a mapping requires. Enumerating every region to be thorough is a lot of API
calls for a fact a targeted query already answered.

### The live API outranks the documentation

The AWS model card for one candidate lists `us-east-1` as in-region available. In this account the
control plane disagrees: `list-foundation-models` does not return it there, and both
`get-foundation-model` and `get-foundation-model-availability` answer
`ValidationException: The provided model identifier is invalid`.

**Record what the API says.** A documented region an account cannot reach is not a region.

---

## Step 3 — limits and prices, from official sources only

Context and output limits are **not** exposed by any Bedrock API. Read them from the model card
under `https://docs.aws.amazon.com/bedrock/latest/userguide/` — "Models at a glance", then the
individual card — and record the values verbatim.

Prices come from the Price List API, not from a pricing page screenshot:

```bash
aws pricing describe-services --service-code AmazonBedrock --region us-east-1
aws pricing get-attribute-values --service-code AmazonBedrock --attribute-name model \
  --region us-east-1
aws pricing get-products --service-code AmazonBedrock --region us-east-1 \
  --filters Type=TERM_MATCH,Field=model,Value="<model attribute value>" \
            Type=TERM_MATCH,Field=regionCode,Value="<region>"
```

**Record the STANDARD on-demand tier only.** Bedrock also publishes `flex`, `priority` and `batch`
rates for most models, distinguishable by the `usagetype` and `service_tier` attributes. Recording a
cheaper tier the code does not request would understate cost, which is the one direction a cost
estimate must never be wrong in. Carry the `effectiveDate` from the term; a price with no date is a
number somebody typed.

---

## Step 4 — the functionality gates

**Bound the cost before every invocation, not after it.** For each gate compute
`(max_input_tokens / 1000) x input_price + (max_output_tokens / 1000) x output_price`, add it to a
running conservative total, and invoke only while the total stays at or below the authorized
ceiling. `packages/model_catalog.SpendLedger` implements exactly this and is what Phase 2 uses.

The gate parameters are fixed and are recorded in the snapshot's `smoke_protocol` block, where an
architecture test asserts they stayed minimal:

```
one nonstreaming Converse call per candidate     no system prompt
no conversation history                          no tools, no guardrail
temperature 0 where supported                    max output tokens 8, never more
text prompt    hello if you can read this please respond with hello only
image prompt   read the image and respond with hello only
```

The image gate runs **only** for candidates whose actual accessible invocation path accepts images —
verified from `inputModalities`, not from a product page. Generate the image deterministically so
the hash recorded beside a result identifies exactly what was sent:

```bash
python var/local-tools/make_hello_png.py var/phase1-evidence/hello.png
```

Then run the gates. The tool refuses to invoke anything without the explicit opt-in flag:

```bash
python var/local-tools/phase1_smoke.py \
  --profile "$AWS_PROFILE" \
  --plan <plan.json> \
  --ceiling 1.00 \
  --i-understand-this-spends-money
```

### Record two results, never one

```
TRANSPORT     accepted or rejected, request id, latency, input and output tokens, stop reason,
              calculated cost
INSTRUCTION   exact, or noncompliant with the sanitized text that came back
```

They answer different questions and conflating them loses the more important one. **A nonempty
response proves Bedrock access even when it fails the `hello` instruction.**

Permitted normalization before comparison: trim leading and trailing whitespace, remove one trailing
period, compare case-insensitively. Nothing else.

**One automatic retry, maximum**, and only for a clear transient service error, throttling, a
first-use provisioning delay or a retryable network failure — and only while the conservative total
stays under the ceiling. **Never retry because the wording differs.** Retrying until a model says
what you wanted is prompt tuning with the measurement removed.

### A reasoning model can pass transport and fail the instruction for a boring reason

One candidate returned an empty text block with stop reason `max_tokens`, having spent all eight
output tokens on a `reasoningContent` block that precedes the answer. That is a request-sizing fact,
not a capability defect, and it belongs in the snapshot's compatibility note. Budget
`max_output_tokens` for reasoning **plus** the answer, or a caller receives a well-formed response
with no text in it.

---

## Step 5 — evidence

Evidence lands under `var/phase1-evidence/`, which is gitignored, and an architecture test fails if
it ever becomes tracked.

```
PRESERVE   semantic request and response content, model or profile id, region, sanitized
           request and response metadata, usage, cost, latency, image hash
NEVER      access key, secret key, session token, SSO token, authorization header,
           credential cache contents, raw signed request, cookies
```

---

## Step 6 — publish the snapshot

Rewrite `docs/llm/bedrock-capability-snapshot.yaml` from the evidence, then:

```bash
make check
python -m pytest tests/unit/test_model_catalog.py tests/architecture/test_phase1_aws_boundary.py
```

Those two modules enforce what prose cannot: that no candidate claims `multimodal` without a
verified image invocation, that every available candidate was actually reached, that no
account-specific material entered a tracked file, that the gate protocol stayed minimal, and that
the smoke prompts carry no SEC content.

---

## Ordinary CI never does any of this

The `ci` workflow grants `contents: read` and nothing else. It requests no `id-token`, configures no
AWS credential, installs no provider SDK, and cannot invoke a model.
`tests/architecture/test_phase1_aws_boundary.py` fails the build if that changes.

A real-model workflow, if one is ever created, is separate, explicitly gated, budget-limited, unable
to trigger implicitly on a push, and unavailable to a pull request from an untrusted fork — see
`../security/aws-identity-and-secrets.md`.
