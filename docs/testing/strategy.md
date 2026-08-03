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
> **NO MODEL HAS BEEN INVOKED. AWS IS NOT CONFIGURED. NO DATABASE EXISTS.**

IMPLEMENTATION STATUS: unit, architecture and security layers IMPLEMENTED. Integration, golden,
property and performance layers PLANNED — there is currently nothing to integrate with.

---

## The suite as it stands

```
309 tests, 0 skipped, 90.89 percent coverage against an 85 percent gate
19 test modules: 14 unit, 5 architecture
```

**The suite has NO environmental precondition.** No database, no network, no credentials, no
container, no fixture generation step. That is why `make test-no-skips` is the same suite as
`make test`, and why a skip in CI has no legitimate cause at all. Before the cleanup, "no reachable
PostgreSQL" was an available excuse for a skip; it is gone.

| Module | Tests | Subject |
|---|---|---|
| `tests/unit/test_llm_boundary.py` | 26 | model content boundary, compiler, gateway, budget |
| `tests/unit/test_filing_discovery.py` | 18 | overflow shard, `master.gz` reconciliation, era routing, the supplied qualifying-form set |
| `tests/unit/test_yaml_parser.py` | 16 | hardened YAML 1.2 safe parser, alias and depth budgets |
| `tests/architecture/test_aws_identity.py` | 16 | credential variables, SDK arguments, credentials in URLs |
| `tests/unit/test_sec_identity.py` | 15 | CIK, accession, URL construction, the filing-agent prefix trap |
| `tests/unit/test_sec_http_client.py` | 15 | retries, cooldown, content assertions, download safety |
| `tests/unit/test_corpus_identity_rules.py` | 15 | the five identity rules, against real EDGAR cases |
| `tests/architecture/test_ci_workflow.py` | 14 | the workflow parsed, not grepped |
| `tests/unit/test_filing_acquisition.py` | 12 | byte-exact acquisition, provenance, storage keys |
| `tests/unit/test_observability.py` | 12 | redaction, correlation scope, structured output |
| `tests/architecture/test_architecture.py` | 12 | dependency direction, single homes, prompt boundary, no form allowlist |
| `tests/unit/test_form_family_contract.py` | 11 | the 22-in/19-out adjudicated inventory |
| `tests/unit/test_corpus_identity_contract.py` | 10 | issuer and co-registration identity |
| `tests/unit/test_sec_client.py` | 9 | token bucket and throttle classification, on a fake clock |
| `tests/architecture/test_openapi_contract.py` | 9 | the API contract parsed, refs resolved, no server claimed |
| `tests/unit/test_filing_fixtures.py` | 8 | original-source hash verification, no derived output committed |
| `tests/unit/test_configuration.py` | 6 | User-Agent gate, rate bounds, cooldown floor |
| `tests/unit/test_storage.py` | 6 | atomic writes, path traversal, hashing |
| `tests/architecture/test_markdown_lint.py` | 5 | fences, swallowed headings, relative links |

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
configuration                startup validation
generic storage              atomic writes, path traversal, SHA-256
raw / YAML boundary          both directions, plus native-tool refusal
safe YAML                    alias budget, depth budget, identifier quoting
generic provider interface   and the mock provider
request/response metadata    exact bodies preserved, budget enforced before spend
security                     credential variables, SDK arguments, log redaction
observability                redaction parametrized over every redacted field
architecture                 dependency direction, single homes, no empty stubs, no form allowlist
CI reconciliation            the workflow parsed and asserted against the Makefile
API contract                 OpenAPI parse, every local ref resolved, no server declared
documentation                fences, swallowed headings, relative links resolve on disk
corpus integrity             identity and form-family contracts over the research corpus
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
least 10 API operations and 20 references. **These floors were re-checked after the deletion and
none had to be lowered** — which is the outcome that matters, because lowering one to accommodate a
deletion is how a guard quietly stops guarding.

**Mutation proofs.** A regression test whose failure has never been observed is a claim, not a
guard. The deleted parser suites carried explicit mutation proofs, and that discipline carries
forward: `test_observability.py` asserts that an UNLISTED field IS emitted, so the redaction tests
cannot pass vacuously; `test_filing_fixtures.py` asserts derived parser output is ABSENT, so the
fixture tree cannot silently reacquire it; `test_filing_discovery.py` asserts an empty qualifying
set is REJECTED, so discovery cannot return nothing and report success.

## Rules that apply to every layer

**A skip is not a pass.** See above.

**A test may not depend on an untracked file.** One did — it read the developer's gitignored
`.env` — and it passed locally while being incapable of passing in CI. Fixtures come from the
repository or from `tmp_path`.

**A gate is never weakened to make a commit pass.** Correcting a demonstrably wrong test is
permitted and must be disclosed in the commit report, with what changed and why the replacement
still protects the behaviour. During this cleanup the AWS-identity guard failed twice on new test
code in `test_observability.py`; both times the TEST was rewritten, and the guard's allowlist was
made narrower rather than wider.

**Coverage measures surviving product code and is never raised by exclusion.** All eight runtime
packages are named in `COV_PACKAGES`. A package absent from that list is unmeasured, so its gap is
invisible and the gate passes without it — the same vacuity trap as an architecture test scanning
an empty directory. Add a package there in the change that creates it.

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

`tests/unit/test_accession_inventory.py` (16) went with the document classifier.
`tests/unit/test_filing_fixtures.py` lost 9 of 14 functions: they reimplemented canonicalization
stage 2 inline to assert that 16 candidates minus 3 item disclosures leaves 13 canonical
footnotes — a semantic conclusion about Apple, asserted by a test.

## PLANNED — none of these exists

For the first model experiments:

```
source-set completeness         that the complete relevant human-readable set was determined
intact-input compatibility      that an incompatible pairing is refused BEFORE invocation, with
                                measured bytes, real token counts and the model's verified limit
elastic artifact acceptance     that an unfamiliar model-chosen label or content type is
                                represented, not rejected and not dropped
source-reference validation     that every cited offset resolves in the preserved source
numeric validation              that every reported number appears verbatim in the source
unresolved-content handling     that unresolved ranges are preserved and block completeness
no false completeness           that PARTIAL and REVIEW_REQUIRED are produced rather than a
                                rounded-up COMPLETE
model-output fixture testing    recorded real responses replayed offline
prompt-version testing          that a prompt change is versioned and attributed
A/B model comparison            the same filing through different parsing models
repeat-run variability          the same filing through the same model twice
```

For the orchestrator and the approval gate:

```
optional-stage composition      that a blank image, summary or analysis selector runs NO stage,
                                and that a parser-only run is complete and approvable on its own
no silent substitution          that a role never inherits another role's model, that no stage is
                                added or skipped, and that no retry crosses to a different model
multimodal routing              that a multimodal parser disables the image selector and no
                                redundant image call occurs, and that a text-only parser without
                                an image model REPORTS unanalyzed image-bearing content rather
                                than claiming complete coverage
cost authorization              that no billable call occurs without an explicit ceiling
parent run and child jobs       one visible run ID, one child job per filing, no concatenation
raw-first source lookup         that local durable storage is checked, hash-verified and reused
                                before EDGAR is contacted
approval gating                 that an EVALUATION artifact never satisfies a search as a trusted
                                result, and that only APPROVED artifacts become reusable
reuse identity                  that a differing source hash, model version, prompt version or
                                setting defeats reuse
cache correctness               that Redis holds only approved artifacts, with a 24-hour TTL, and
                                is never the authoritative read
streaming security              that resumption cannot leak another job's events
comment lineage                 that a comment stays bound to the artifact VERSION it targeted
```
