# ADR-0018: A reviewed capability snapshot, not a provider adapter, is Phase 1's durable output

STATUS: ACCEPTED
DATE: 2026-08-03

SUPERSEDES: nothing. It records the first decision taken after a model was actually reached.

AMENDS: `rules.md` section 5, which reserved `packages/model_catalog` for Phase 2. The
capability-record half of it exists now; the four-role router does not.

**THIS IS THE FIRST ADR IN THIS REPOSITORY WRITTEN AFTER A REAL MODEL RESPONDED.** Every earlier
statement about model availability, identifiers, limits or prices was a placeholder, and several
were wrong.

---

## 1. Context

Phase 1 had one job: stop guessing about models. Five user-facing candidate LABELS had been approved
for the beta — GPT OSS 120B, NVIDIA Nemotron 3 Super 120B, Qwen3 235B A22B, Llama 4 Maverick and
Qwen3 VL 235B — and not one of them had ever been mapped to a real provider identifier, a real
region, a real limit or a real price. `docs/llm/cost-model.md` was placeholders end to end.
`README.md` said none of them was configured or reachable, which was true.

Discovery ran on 2026-08-03 under a temporary IAM Identity Center role, resolved by the AWS CLI
provider chain. No static credential exists, none was created, and nothing under the credential
cache was opened. All five labels mapped uniquely to real models. All five were reached. Total
model spend for the whole phase was **USD 0.00023** against an authorized ceiling of USD 1.00.

The question this ADR answers is what to KEEP from that, in a repository whose last two corrections
were both caused by writing down more than had been measured.

## 2. Decision

**Phase 1's durable output is a dated, reviewed capability SNAPSHOT plus a provider-neutral reader
for it. It is not a provider adapter, and it adds no SDK dependency.**

```
docs/llm/bedrock-capability-snapshot.yaml   the evidence, dated, with its provenance
packages/model_catalog                      reads it, resolves a label, refuses everything else
var/local-tools/phase1_smoke.py             GITIGNORED. the instrument, not the result
```

`packages/model_catalog` contains no AWS import, no ARN, no endpoint, no credential, no region
literal and no model identifier. It never invokes anything. An architecture test parses shipped
source and fails if a provider model id or a region string is written into it — the same guard shape
that now protects the qualifying-form set, for the same reason.

## 3. Why a snapshot rather than live discovery at runtime

Live discovery at runtime would be simpler to write and worse in three specific ways.

**It would make the model catalog an availability oracle rather than a reviewed decision.** The five
candidates are user-approved. A model appearing in `ListFoundationModels` tomorrow is not thereby
approved for this product, and a runtime call that returns it would make it selectable with nobody
having decided that.

**It would put a network dependency inside a capability check.** The suite has no environmental
precondition at all — no database, no network, no credentials — which is precisely why the zero-skip
gate has no legitimate excuse. A live catalog would reintroduce the excuse.

**It would lose the date.** Bedrock moves. A snapshot says what was true on a stated day and can be
compared with what is true now; a live call has no yesterday to disagree with.

## 4. Why no boto3 dependency

The discovery and the gates ran entirely through the AWS CLI, which is official AWS tooling and was
already installed. Nothing in the durable half needs an SDK, so adding one would be a dependency
carried for convenience — and `rules.md` section 5 already names
`packages/llm_gateway/providers/bedrock.py` as the ONLY home for provider SDK usage, in Phase 2.
Adding boto3 now would create a second place where AWS could be reached before the first place
exists.

Runtime dependencies remain exactly two: `ruamel.yaml` and `httpx`.

## 5. What was found, and what it changes

**All five labels mapped uniquely.** Two required care. `Qwen3 235B A22B` is
`qwen.qwen3-235b-a22b-2507-v1:0` — the `2507` is the provider's release qualifier and part of the
identifier — and it is a different model from `Qwen3 VL 235B`, which is the fifth candidate.
`GPT OSS 120B` is `openai.gpt-oss-120b-1:0` and is NOT `GPT OSS Safeguard 120B`, a separately named
and separately priced model in the same account.

**Llama 4 Maverick cannot be invoked by its model id at all.** Its `inferenceTypesSupported` is
`INFERENCE_PROFILE`, not `ON_DEMAND`. Callers use the US geo profile, which routes across three
regions — a data-residency fact, not merely a throughput one. `ModelCapability.invocation_id` is
where that lives, so no caller has to remember it.

**Qwen3 235B A22B is not available in `us-east-1`,** the project's primary region, although the AWS
model card lists it as in-region available there. The control plane answers
`ValidationException: The provided model identifier is invalid`. The live API is recorded and the
documentation is not, with the discrepancy written down rather than reconciled away.

**Two candidates are genuinely multimodal, and both were proved so by invocation.** Qwen3 VL 235B
and Llama 4 Maverick each read the word HELLO out of a 173-byte PNG. The other three are text-only.
`multimodal` is validated against `image_verified` in the dataclass constructor, so a record cannot
claim the badge without the evidence — the instruction is explicit that a model is not labelled
`Multimodal` in the selector until an actual image invocation works.

**GPT OSS 120B passed transport and failed the instruction, for a reason worth keeping.** The gate's
mandatory 8-token output cap was consumed entirely by a `reasoningContent` block that precedes the
answer, so the text block came back empty with stop reason `max_tokens`. A separate one-off
diagnostic at 64 output tokens returned reasoning followed by `hello`, stop reason `end_turn`. That
is a request-sizing fact — `max_output_tokens` must cover reasoning PLUS the answer — and it would
have been recorded as a capability defect by anyone who stopped at the gate.

**Context limits differ by a factor of eight across the five**, from 128K to 1M, and output limits by
a factor of four, from 8K to 32K. Against dated Phase 0 evidence that 44 percent of primary corpus
documents exceed roughly 200,000 estimated tokens, that is the difference between a model that can
take an intact filing and one that cannot. It is measured now instead of assumed.

## 6. What this does NOT authorize

```
sending an SEC filing to any model          designing the parsed-artifact contract
a parser prompt                             the parser-review UI
a product database                          Redis
background population                       an AWS-enabled ordinary CI job
```

Phase 2 remains next, and remains unstarted.

## 7. The administrator-identity disclosure

`docs/llm/model-benchmark.md` and `docs/security/aws-identity-and-secrets.md` both say broad
administrator access to ease model discovery is prohibited, because discovery is a one-time
convenience and the permission outlives it.

**Phase 1 discovery ran under an IAM Identity Center `AdministratorAccess` role**, which is the
identity the user supplied for this task. That is recorded rather than glossed. What the rule
protects against is a DURABLE broad permission, and that requirement is unchanged: the least-
privilege Bedrock policy is required before any repeatable or automated invocation path, no CI job
receives an AWS role, and the discovery was performed once, by hand, and produced a document rather
than a running capability.

## 8. Consequences

Easier: Phase 2 can state a model's real identifier, region, limits and price without reaching AWS,
and can compute a cost bound before spending. A selector can show a disabled state with a concrete
reason instead of a shrug.

Harder: the snapshot goes stale silently. Nothing in the repository can detect that Bedrock changed
a price. Mitigated by the date on the file, the runbook that regenerates it, and the rule that it is
replaced wholesale rather than patched.

Accepted: the catalog trusts the snapshot. That is deliberate — it is a REVIEWED contract, in the
same sense and for the same reason as the form-family adjudication, and the alternative is code that
decides for itself which models exist.

## 9. Risks

1. **A price changes and a cost estimate silently becomes wrong.** The effective date is carried on
   every record so the staleness is visible at the point of use, and Phase 2's first act is a
   measured cost.
2. **The snapshot is edited by hand into an inconsistent state.** The loader rejects a missing
   field rather than defaulting it, and the constructor rejects a contradiction.
3. **A future contributor adds a model identifier to source "just for a test".** An architecture
   test parses shipped source and fails on a provider identifier or region literal.

## Revisit conditions

- When Phase 2 writes `packages/llm_gateway/providers/bedrock.py`, at which point an SDK dependency
  is reconsidered on its merits.
- When the four-role router is built, which completes `packages/model_catalog`.
- Whenever a candidate is added or withdrawn, or a price or region changes.

## Migration impact

None. No database exists, nothing is deployed, and no existing caller changes. One correction ships
with it: `LlmSettings.region` no longer defaults to a hardcoded `us-east-1` and a non-mock provider
without a region now fails closed at startup.
