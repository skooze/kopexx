# LLM Content Boundary

IMPLEMENTATION STATUS: IMPLEMENTED — the format machinery only
OWNER PACKAGE: `packages/llm_gateway`
DECISION RECORD: `docs/adr/ADR-0013-plain-text-or-yaml-llm-boundary.md`

> **CORRECTED 2026-08-03. THE BANNER THIS REPLACES SAID "NO MODEL HAS EVER BEEN INVOKED", AND THAT
> STOPPED BEING TRUE IN PHASE 2.** Thirty single-response invocations and a model-directed multipart
> run have crossed this boundary against real providers. What has NOT changed is the more important
> half: **no request or response contract is declared here.** The compiler, the validator, the safe
> parser, the budget guard and the audit record specify FORMAT and nothing else. The
> footnote-shaped request contract this document used to list was deleted with the deterministic
> parser whose output it carried, and the real contracts are still derived from observed model
> behaviour rather than declared in advance. Authoritative:
> `docs/adr/ADR-0017-delete-the-rejected-parser-and-application-persistence.md`,
> `docs/adr/ADR-0020-model-directed-multipart-parsing.md` and `roadmap.md`.
>
> **WHAT PHASE 2.1 ADDED TO THIS BOUNDARY.** A multipart brief is compiled as exactly one unfenced
> YAML 1.2 document through `compile_yaml`, and carries filing identity, source-artifact filenames
> and hashes, the model's own plan, the model's own part specification, and measured sizing numbers.
> Every semantic word in one came from a model on an earlier call. The ORIGINAL-SOURCE EXCEPTION is
> unchanged and is what carries the filing itself, intact, beside the brief on every semantic call.
>
> **ONE NARROWING, DEMONSTRATED RATHER THAN ARGUED.** `MARKDOWN_FENCE` no longer applies to a
> document that PARSES as one YAML 1.2 mapping. It was there on the ground that "a fenced document
> is fenced" — true of a fenced document, and not true of the CHECK, which is a textual search for
> three backticks at the start of any line, and a YAML literal block scalar can contain such a line.
> Two real request shapes must: the REPLANNING call carries the exact truncated response as
> evidence, and the FORMAT-REPAIR call carries the exact malformed response, which is very often
> malformed *because* it is fenced. Under the old rule neither request could be constructed at all.
>
> The narrowing is safe because a fence-wrapped document CANNOT reach that branch: `parse_yaml`
> raises on both a language-tagged and a bare fenced document, so anything that parses as one
> mapping is not fence-wrapped. JSON is a YAML subset and therefore DOES reach the branch, which is
> why the JSON detectors stayed. `tests/unit/test_llm_boundary.py` asserts the load-bearing fact
> directly and carries mutation proofs that a fenced document and a JSON document are both still
> refused.

---

## The rule

Model-visible SYNTHETIC content — anything this system composes — is exactly one of two formats.

```
plain_text   unmarked normalized human-readable text, containing no Markdown
yaml         exactly one unfenced YAML 1.2 document, with no prose before or after it
```

Prohibited in model-visible synthetic content, in both directions:

```
markdown                markdown_fences         markdown_tables
markdown_headings       markdown_links          markdown_blockquotes
inline_backtick         json                    json_lines
json_schema             xml                     xbrl
inline_xbrl             html                    xhtml
native_tool_schema      native_tool_arguments
```

Native model tool calling is prohibited, because it requires JSON Schema tool definitions and
produces JSON tool arguments.

---

## The ORIGINAL-SOURCE EXCEPTION

There is exactly one exception, it is narrow, and it is load-bearing: `INTACT_SOURCE_ONLY` requires
that a preserved SEC artifact reach the parsing model unchanged.

```
An untouched original SEC artifact may be sent intact, in whatever syntax SEC published it —
HTML, SGML, XML, XBRL, inline XBRL, PDF, image, plain text.
```

The conditions are cumulative and none of them is waivable.

```
ADMITTED BY PROVENANCE, NEVER BY SYNTAX
    the bytes are identical to a preserved artifact whose SHA-256 is recorded in the source store,
    and were not constructed, normalized, reflowed, re-serialized or repaired by this system

NEVER REWRITTEN INTO YAML OR PLAIN TEXT
    rewriting an original into a permitted format destroys the property the exception exists to
    protect. An artifact that has been rewritten is synthetic content and loses the exception

ONE-DIRECTIONAL
    no model RESPONSE may use it. A response is synthetic content in both directions of travel and
    is one unfenced YAML 1.2 document, or plain text for an explicitly unstructured task

NEVER DUPLICATED INTO A WRAPPER
    the original is not embedded in a verbose envelope that repeats it, describes it in its own
    syntax, or fences it
```

The exception does not route through the payload compiler. The compiler exists to produce synthetic
content and would have to alter an original to emit it, which is the thing forbidden. Mandatory
rule: `rules.md` section 3.

---

## The five serialization contexts

Only the first is constrained by this document, and the original-source exception above is the one
carve-out inside it. Confusing these five is the most common way this rule gets misapplied.

| # | Context | Permitted formats | Rationale |
|---|---|---|---|
| 1 | Model-visible synthetic content | plain text, YAML 1.2 | This document |
| 2 | Internal application state | any typed representation | Never reaches a model |
| 3 | Browser and API traffic | JSON, OpenAPI | A browser is not a model |
| 4 | Database storage | relational columns, JSONB | Storage, not content |
| 5 | Provider wire protocol | whatever the SDK requires | The envelope, not the content |

The AWS SDK serializes its request as JSON. That is context 5 and is permitted. The text inside
the message it carries is context 1 and must be plain text or YAML. An SDK request object must
never be copied into model-visible content.

---

## Responsibility

Produce, validate, and audit every piece of content that a language model can see, and parse
every structured response it returns.

## Inputs

A mapping, or a string of prose, plus the name of the originating subsystem. **Nothing filing-shaped
and nothing domain-typed.** The gateway is generic by construction: it knows about model identity,
roles, budgets, formats, bytes, tokens, cost and latency, and it knows nothing about what a filing
contains. It must not learn.

## Outputs

A `CompiledPayload` carrying validated model-visible content, its declared format, an estimated
token count, and its originating subsystem. After invocation, a parsed Python object and an
`InvocationRecord`.

## Public interface

The complete surface of `packages.llm_gateway` as it exists today.

```
COMPILATION
    compile_yaml(payload, origin)                -> CompiledPayload
    compile_plain_text(text, origin)             -> CompiledPayload
    CompiledPayload                              content, format, estimated tokens, origin
    reject_native_tools(tools)                   -> None, raises NativeToolUseProhibitedError

VALIDATION
    validate_plain_text(text)                    -> BoundaryReport
    validate_yaml_text(text)                     -> BoundaryReport
    validate(text, format)                       -> BoundaryReport
    enforce(text, format, origin)                -> None, raises BoundaryViolationError
    BoundaryReport   ContentFormat   Violation

PARSING AND EMISSION
    parse_yaml(text)                             -> Any, raises YamlSafetyError/YamlParseError
    require_mapping(value)                       -> dict
    require_string(mapping, key)                 -> str
    to_yaml(mapping)                             -> str

INVOCATION AND ACCOUNTING
    estimate_tokens(text)                        -> int, a character-ratio ESTIMATE
    LlmGateway(provider).invoke(...)             -> GatewayResult
    Budget   GatewayResult   InvocationRecord
    PricingRegistry   ModelPricing   default_registry

ERRORS
    LlmGatewayError   BoundaryViolationError   BudgetExceededError
    NativeToolUseProhibitedError   ProviderError   YamlParseError   YamlSafetyError
```

Two names a reader may remember are gone. `ModelCapabilities` described a model this project has
never reached and had no constructor and no caller; `SerializationComparison` was the evidence shape
for the ADR-0013 decision, which is made and recorded. Both were deleted as dead code.

## Dependencies

`ruamel.yaml` for YAML 1.2 parsing and emission. Nothing else.

## Prohibited dependencies

No package outside `packages/llm_gateway/providers` may import a provider SDK. Enforced by
`tests/architecture/test_architecture.py::test_bedrock_client_not_imported_outside_provider`.

The gateway must not import any application package. Dependency flows toward the gateway, never out
of it. A domain type inside this package is how the footnote-shaped contract got here the first
time.

## Data owned

The invocation audit record, including the exact model-visible request body, the exact model
response body, token counts, cost, latency, and the boundary validation outcome.

## Data explicitly not owned

Filing content, preserved source artifacts, parsed artifacts, and summaries. The gateway transports
and validates; it does not interpret.

---

## Invariants

1. Model-visible synthetic content is plain text or one unfenced YAML 1.2 document.
2. Only `payload_compiler` produces model-visible synthetic content.
3. A preserved SEC artifact is admitted by provenance, sent intact, and never rewritten.
4. Only `providers/` imports a provider SDK.
5. The exact request and response bodies are recorded unmodified.
6. Budgets are checked before invocation, never after.
7. Native tool definitions are refused.
8. Every identifier emitted into YAML is quoted.
9. Model output is parsed by the hardened safe parser, never by a general-purpose loader.

---

## The pipeline

```
a mapping or a string of prose
  -> payload compiler          builds model-visible synthetic content
  -> boundary validator        rejects prohibited serializations
  -> budget guard              refuses before spend
  -> provider adapter          the only place a provider SDK is used
  -> boundary validator        applied to the response
  -> safe YAML parser          when the task is structured
  -> audit record              exact bodies preserved
```

The compiler is the primary control; the validator is a backstop that catches a bypass. Both
exist because a defence that depends on one mechanism has no failure margin.

A preserved SEC artifact enters at the provider adapter instead, carrying its recorded SHA-256. It
skips the compiler because the compiler would have to change it. Everything after the provider —
response validation, safe parsing, audit — is identical.

---

## Three verified YAML facts that drive the design

### YAML 1.2 does not coerce yes, no, on, off

PyYAML implements YAML 1.1, whose boolean resolver turns those bare scalars into booleans. A field
whose value is the word `no` would silently become `False`. `ruamel.yaml` in pure safe mode
implements the YAML 1.2 core schema and leaves them as strings.

Verified during Sprint 1:

```
a: yes    ->  'yes'   (str)
b: no     ->  'no'    (str)
c: on     ->  'on'    (str)
d: off    ->  'off'   (str)
```

Covered by `tests/unit/test_yaml_parser.py::test_yaml_12_does_not_coerce_yes_no_on_off`.

### YAML 1.2 destroys leading zeros on unquoted identifiers

```
cik: 0000320193      ->  320193       (int)  identifier destroyed
cik: "0000320193"    ->  '0000320193' (str)  correct
```

Every CIK, accession number, fiscal period, date, zero-prefixed label, and version string is quoted
by the serializer. `require_string` refuses to return an identifier that arrived unquoted
rather than coercing it back, because the leading zeros are already unrecoverable at that point.

Covered by `test_yaml_parser_preserves_quoted_cik` and `test_yaml_parser_preserves_accession`.

### A forced block scalar can carry a character the reader turns into a line break

```
quote: |-              a raw U+0085 inside a block scalar
  before<U+0085>after   -> read back as "before\nafter", and the indentation of
  second line              everything after it is broken

quote: "before\Nafter"  -> read back as the exact character
```

FOUND BY A REAL FILING. A 1996 10-K405 table quoted by a parsing model contained `U+0085 NEXT
LINE`. `to_yaml` forces style `|` on prose, which bypasses the emitter's own scalar analysis — the
analysis that would have refused block style for that string. The reader counts `U+0085`, `U+2028`
and `U+2029` as line breaks, so the character came back as a newline: silently, a preserved quote
stopped matching the bytes it cited; loudly, an assembly this repository had just written became
one it could not load.

A string containing any character a block scalar cannot return unchanged is double-quoted instead,
where the emitter escapes it (`\N`, `\L`, `\P`, `\v`, `\f`) and the reader restores it exactly.
Tab and newline are excluded from that set deliberately — a block scalar carries both, and EDGAR
text tables are made of them, so an ordinary table stays a readable block scalar.

Covered by `test_a_serialized_document_reads_back_the_character_it_was_given`,
`test_the_ordinary_characters_of_a_filing_still_get_a_readable_block_scalar` and
`test_every_character_a_filing_can_contain_survives_serialization`, which sweeps every code point
through U+10FFF.

---

## Parser safety limits

Model output is untrusted. The parser enforces:

| Limit | Value | Rationale |
|---|---|---|
| Input size | 4 MiB | Bounds memory on a hostile or malfunctioning response |
| Nesting depth | 32 | Prevents stack exhaustion by deeply nested collections |
| Collection size | 10,000 | Bounds a single mapping or sequence |
| Scalar length | 1,000,000 | Bounds one string |
| Document count | 1 | A second document is a protocol violation |
| Duplicate keys | rejected | Silently discards data in most parsers |
| Custom tags | rejected | Arbitrary object construction is the classic YAML vulnerability |
| Aliases | bounded | Prevents billion-laughs expansion |

---

## Failure modes

| Failure | Detection | Response |
|---|---|---|
| Compiler emits prohibited content | Boundary validator before invocation | Raise `BoundaryViolationError`; no spend |
| Caller bypasses the compiler | Boundary validator | Same; origin names the offending subsystem |
| Model returns JSON | Boundary validator on response | Record `BOUNDARY_REJECTED`, raise, do not parse |
| Model returns fenced YAML | Boundary validator | Same |
| Model returns prose then YAML | `YAML_PREAMBLE` violation | Same |
| Model returns two documents | `YAML_MULTIPLE_DOCUMENTS` | Same |
| Response exceeds a parser limit | Safe parser | `YamlSafetyError`, route to review |
| Caller passes native tools | `reject_native_tools` | `NativeToolUseProhibitedError` before any work |
| Budget would be exceeded | Budget guard | `BudgetExceededError` before invocation |

A boundary rejection writes an audit row before raising, so a rejected invocation is visible in
the record rather than vanishing.

## Retry behavior

Boundary violations are never retried unchanged; the content is deterministic, so a retry
produces the same violation. A model response rejected at the boundary may be retried once with a
repair instruction, then routed to review. Provider transient failures are retried with bounded
backoff by the provider adapter.

## Security requirements

Filing text is untrusted input. It is delivered as labeled source data, and system prompts state
that instructions found inside source content are ignored and reported.

`BoundaryViolationError` carries the origin, declared format, and violation names, and never the
offending content, which may be large and may itself carry an injection attempt.

Log records never contain payload bodies. The structured logger redacts a fixed field set.

## Observability requirements

Per invocation: correlation id, model id, provider, prompt version, request and response formats,
token counts, cost, latency, status, origin. Counters for boundary rejections by violation type
and by origin. An alert on any boundary rejection in a non-development environment, since it
indicates a code defect rather than a data problem.

## Scaling

The gateway is stateless and scales horizontally. Token estimation is a character-ratio calculation
and is not a bottleneck. The audit sink is the only shared resource. **Where the record is durably
written is undecided** — no application database exists and the persistent artifact store is
designed from measured artifacts, not before them. `InvocationRecord` is an in-process value today.

## Unit-test approach

Each detector is tested against a positive and a negative case. The compiler is tested to produce
content free of every prohibited construct. The parser is tested against duplicate keys, unsafe
tags, each resource limit, and the two identifier-preservation facts above.

## Pipeline-test approach

The full pipeline is exercised against the mock provider: compile, validate, invoke, validate the
response, parse, and assert the record holds the exact bodies. A provider returning JSON is asserted
to be rejected rather than parsed. There is no live-provider test, because no provider has been
reached.

## Current test coverage

```
tests/unit/test_llm_boundary.py          26 tests
tests/unit/test_yaml_parser.py           16 tests
tests/architecture/test_architecture.py  12 tests, of which 3 enforce this boundary
```

---

## Cost rationale

Serialization overhead multiplies across every filing processed and every unit of content within
one. JSON repeats every key on every record and escapes every quote in filing prose. XML repeats
every tag name twice. Markdown adds fence, pipe, and emphasis characters carrying no information a
model needs.

**No serialization measurement has been taken and no saving is claimed.** The comparison harness
that produced one — and the `SerializationComparison` shape it emitted — was removed once ADR-0013
was decided and recorded. `estimate_tokens` is a character-ratio heuristic adequate for a budget
guard and for relative comparison, and it is not a provider tokenizer count.

The production path selects plain text or YAML regardless of which serialization would tokenize
smallest, because the boundary is a correctness and security constraint rather than an
optimization. That is why losing the harness costs the decision nothing: the measurement quantified
a benefit, it never chose the format.
