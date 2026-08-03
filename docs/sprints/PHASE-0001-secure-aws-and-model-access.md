# PHASE-0001: Secure AWS access and model-capability verification

STATUS: COMPLETE
DATE: 2026-08-03
DEPENDS ON: Phase 0.5, the cleanup commit (ADR-0017)
AUTHORITATIVE DECISION: `../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`
REPRODUCIBLE BY: `../runbooks/bedrock-capability-discovery.md`

**A MODEL WAS INVOKED FOR THE FIRST TIME IN THIS PROJECT'S HISTORY.** Seven minimal invocations,
total spend USD 0.00023 against an authorized ceiling of USD 1.00.

**NO SEC FILING WAS SENT TO ANY MODEL. NO PARSER EXPERIMENT BEGAN. NO PARSER-REVIEW UI EXISTS.
ORDINARY CI REMAINS AWS-FREE. NO APPLICATION DATABASE EXISTS.**

The project is tracked in PHASES rather than sprints; `roadmap.md` is authoritative for sequencing.
This record uses the sprint-record location because that is where the project's history lives.

---

## Objective

Replace every placeholder about models with measured evidence: map five user-facing candidate LABELS
to real provider identifiers or record them unavailable, verify region, access, modality, limits and
official prices, and obtain one real response from each reachable candidate under a hard cost
ceiling.

## What was verified, and how

Discovery ran under a temporary IAM Identity Center role resolved by the AWS CLI provider chain. No
static credential exists, none was created, nothing under the credential cache was opened, and no
credential value appears in any tracked file, log or evidence artifact.

```
control plane   ListFoundationModels, GetFoundationModel, GetFoundationModelAvailability,
                ListInferenceProfiles, GetInferenceProfile
prices          the AWS Price List API, service code AmazonBedrock, standard on-demand tier,
                effective 2026-07-01
limits          the official AWS model cards, which are the only source that states them
runtime         one nonstreaming Converse call per candidate, max 8 output tokens, temperature 0,
                no system prompt, no history, no tools, no streaming
```

## Candidate mapping — all five resolved uniquely

| Label | Provider model | Text | Image | Context | Output | Notes |
|---|---|---|---|---|---|---|
| GPT OSS 120B | `openai.gpt-oss-120b-1:0` | yes | no | 128K | 16K | emits reasoning before answer text |
| NVIDIA Nemotron 3 Super 120B | `nvidia.nemotron-super-3-120b` | yes | no | 256K | 32K | largest output limit |
| Qwen3 235B A22B | `qwen.qwen3-235b-a22b-2507-v1:0` | yes | no | 256K | 8K | **not offered in us-east-1** |
| Llama 4 Maverick | `meta.llama4-maverick-17b-instruct-v1:0` | yes | yes | 1M | 8K | **inference profile required** |
| Qwen3 VL 235B | `qwen.qwen3-vl-235b-a22b` | yes | yes | 256K | 8K | most expensive of the five |

Every value is in `../llm/bedrock-capability-snapshot.yaml` with its provenance. Nothing is repeated
into `techspecs.md` or `roadmap.md`, because a capability recorded twice drifts.

## The four findings that change something

**Llama 4 Maverick is not invocable by its model id.** Its inference type is `INFERENCE_PROFILE`,
not `ON_DEMAND`; callers use `us.meta.llama4-maverick-17b-instruct-v1:0`, which routes across
us-east-1, us-east-2 and us-west-2. That is a data-residency decision, not only a throughput one.

**Qwen3 235B A22B is not available in us-east-1** although the AWS model card says it is. The
control plane answers `ValidationException: The provided model identifier is invalid`. The live API
is recorded; the discrepancy is written down rather than reconciled away.

**Two candidates are verified multimodal, by invocation rather than by flag.** Qwen3 VL 235B and
Llama 4 Maverick each read the word HELLO out of a 173-byte PNG. `multimodal` is validated against
`image_verified` in the dataclass constructor, so no record can carry the badge without the
evidence.

**GPT OSS 120B passed transport and failed the instruction for a request-sizing reason.** The gate's
mandatory 8-token cap was consumed by a `reasoningContent` block preceding the answer, leaving an
empty text block and stop reason `max_tokens`. A single one-off diagnostic at 64 output tokens
returned reasoning followed by `hello`, stop reason `end_turn` — exact compliance. Recorded as a
compatibility note, not as a defect. Anyone stopping at the gate would have concluded the model
returns nothing.

## Functionality gates

```
gate    candidate                       transport   instruction   in     out   latency
text    GPT OSS 120B                    ACCEPTED    NONCOMPLIANT   78      8    1908 ms
text    NVIDIA Nemotron 3 Super 120B    ACCEPTED    EXACT          27      2    3461 ms
text    Qwen3 235B A22B  (us-west-2)    ACCEPTED    EXACT          19      2    1620 ms
text    Llama 4 Maverick (profile)      ACCEPTED    EXACT          46      2    1667 ms
text    Qwen3 VL 235B                   ACCEPTED    EXACT          19      2    1631 ms
image   Qwen3 VL 235B                   ACCEPTED    EXACT          93      2    2001 ms
image   Llama 4 Maverick (profile)      ACCEPTED    EXACT         337      2    1632 ms
```

Transport and instruction are recorded separately and are never collapsed. A nonempty response
proves Bedrock access whether or not it followed a one-word instruction. No gate was retried: none
failed transiently.

## Cost

```
authorized ceiling                    USD 1.00
conservative bound, 5 text gates      USD 0.00030408
conservative bound, 2 image gates     USD 0.00156904
actual, 7 gates plus 1 diagnostic     USD 0.00023
```

Every invocation was bounded before it was made and the bound was added to a running total that had
to stay under the ceiling. `packages/model_catalog.SpendLedger` is that rule as code, and it charges
the reservation immediately: settling only on success would let a run of billable rejections walk
past the ceiling.

## Files created

```
docs/llm/bedrock-capability-snapshot.yaml     the reviewed contract, dated
packages/model_catalog/                       __init__, capabilities, catalog, errors, spend
tests/unit/test_model_catalog.py              hermetic; 50 tests
tests/architecture/test_phase1_aws_boundary.py  repository guards; 12 tests
docs/adr/ADR-0018-...                         why a snapshot and not an adapter
docs/runbooks/bedrock-capability-discovery.md  how to reproduce all of it
docs/sprints/PHASE-0001-secure-aws-and-model-access.md  this record
```

Gitignored, deliberately: `var/local-tools/phase1_smoke.py`, `var/local-tools/make_hello_png.py`,
`var/phase1-evidence/`. The instrument that spends money is not part of the distribution, and an
architecture test fails if it or its evidence becomes tracked.

## Files modified

```
packages/configuration/settings.py    LlmSettings.region loses its hardcoded default
packages/configuration/errors.py      MissingModelRegionError
packages/configuration/__init__.py    the new error is exported
tests/unit/test_configuration.py      four tests for the corrected region behaviour
tests/architecture/test_architecture.py   model_catalog added to PURE_LOGIC_PACKAGES
Makefile                              model_catalog added to COV_PACKAGES
rules.md, roadmap.md, techspecs.md, README.md, CHANGELOG.md, CLAUDE.md
docs/testing/strategy.md, docs/llm/model-benchmark.md, docs/llm/cost-model.md,
docs/llm/model-abstraction.md, docs/security/aws-identity-and-secrets.md
```

## The defect found in retained code

`LlmSettings.region` defaulted to a hardcoded `"us-east-1"`. That is the form-family defect with a
bill attached: a guessed value in runtime source, no reviewed contract behind it, and a silent
success when the operator sets nothing. Phase 1 made the cost concrete — one of the five approved
candidates is not offered in `us-east-1` at all, so an unset region would have reported a real model
as unavailable with nothing in the code to point at.

The default is removed, `AWS_REGION` has no fallback, and a non-mock provider with no region raises
`MissingModelRegionError` at construction. The mock provider still needs no region, so the suite
keeps its zero environmental preconditions.

## Tests run and results

```
make fmt-check / lint / typecheck     clean
make test-no-skips                    375 passed, 0 skipped
make coverage                         92.14 percent against an 85 percent gate
external import verification          9 packages import from a clean venv; 5 deleted ones do not
pip-audit --skip-editable             no known vulnerabilities
gitleaks, history and committable     no leaks found
```

## Known issues

1. The snapshot goes stale silently. Nothing in the repository can detect that Bedrock changed a
   price. The date is carried onto every record so the staleness is visible where it is used.
2. Discovery ran under an `AdministratorAccess` role, which the security policy permits for a
   one-time manual discovery but not for a durable path. The least-privilege Bedrock policy is
   required before any repeatable or automated invocation. ADR-0018 section 7.
3. Only the standard on-demand price tier is recorded. Flex, priority and batch exist and are
   cheaper or dearer; none is authorized, and recording an unauthorized tier would understate cost.
4. `packages/model_catalog` is half of its eventual self. The four-role router is Phase 2.

## Deferred work

The Bedrock provider adapter, an SDK dependency, provider token counting, and the four-role router
all belong to Phase 2 and are named in `roadmap.md`.

## Documentation updated

`rules.md` section 5 (the single-home table), `roadmap.md` (Phase 1 COMPLETE, Phase 2 NEXT),
`techspecs.md` (the ninth runtime package and the corrected region behaviour), `README.md`,
`CHANGELOG.md`, `CLAUDE.md`, `docs/testing/strategy.md`, `docs/llm/model-benchmark.md`,
`docs/llm/cost-model.md`, `docs/llm/model-abstraction.md`,
`docs/security/aws-identity-and-secrets.md`.

## Roadmap changes

Phase 1 COMPLETE. Phase 2 — intact-filing parser experiments with the review UI built in tandem —
is NEXT and requires explicit user authorization to begin. R-22, the unmapped-candidate risk, is
CLOSED.

## ADRs created

`../adr/ADR-0018-verified-capability-snapshot-over-a-provider-adapter.md`.

## Deployment notes

None. Nothing is deployed and nothing in this phase deploys anything.

## Rollback notes

Reverting the phase removes a document and a reader for it. No data, no schema and no external state
is involved. The AWS account was read from and invoked; no AWS resource was created, modified or
deleted.
