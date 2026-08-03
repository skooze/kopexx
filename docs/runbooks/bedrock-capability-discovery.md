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
