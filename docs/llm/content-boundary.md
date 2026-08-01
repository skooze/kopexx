# LLM Content Boundary

IMPLEMENTATION STATUS: IMPLEMENTED (Sprint 1)
OWNER PACKAGE: `packages/llm_gateway`
DECISION RECORD: `docs/adr/ADR-0013-plain-text-or-yaml-llm-boundary.md`

---

## The rule

Model-visible content is exactly one of two formats.

```
plain_text   unmarked normalized human-readable text, containing no Markdown
yaml         exactly one unfenced YAML 1.2 document, with no prose before or after it
```

Prohibited in model-visible content, in both directions:

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

## The five serialization contexts

Only the first is constrained by this document. Confusing them is the most common way this rule
gets misapplied.

| # | Context | Permitted formats | Rationale |
|---|---|---|---|
| 1 | Model-visible content | plain text, YAML 1.2 | This document |
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

Typed domain objects: a canonical footnote with its source blocks and tables, a Deep Analysis
request with its authorized scope and retrieved evidence, a scope-classification request.

## Outputs

A `CompiledPayload` carrying validated model-visible content, its declared format, an estimated
token count, and its originating subsystem. After invocation, a parsed Python object and an
`InvocationRecord`.

## Public interface

```
packages.llm_gateway
    compile_yaml(payload, origin)                -> CompiledPayload
    compile_plain_text(text, origin)             -> CompiledPayload
    compile_footnote_summary_request(request)    -> CompiledPayload
    validate_plain_text(text)                    -> BoundaryReport
    validate_yaml_text(text)                     -> BoundaryReport
    enforce(text, format, origin)                -> None, raises BoundaryViolationError
    parse_yaml(text)                             -> Any, raises YamlSafetyError/YamlParseError
    require_string(mapping, key)                 -> str
    to_yaml(mapping)                             -> str
    LlmGateway(provider).invoke(...)             -> GatewayResult
    reject_native_tools(tools)                   -> None, raises NativeToolUseProhibitedError
```

## Dependencies

`ruamel.yaml` for YAML 1.2 parsing and emission. Nothing else.

## Prohibited dependencies

No package outside `packages/llm_gateway/providers` may import a provider SDK. Enforced by
`tests/architecture/test_architecture.py::test_bedrock_client_not_imported_outside_provider`.

The gateway must not import `packages/summarization`, `packages/deep_analysis`, or any other
application package. Dependency flows toward the gateway, never out of it.

## Data owned

The invocation audit record, including the exact model-visible request body, the exact model
response body, token counts, cost, latency, and the boundary validation outcome.

## Data explicitly not owned

Filing content, canonical footnotes, financial facts, and summaries. The gateway transports and
validates; it does not interpret.

---

## Invariants

1. Model-visible content is plain text or one unfenced YAML 1.2 document.
2. Only `payload_compiler` produces model-visible content.
3. Only `providers/` imports a provider SDK.
4. The exact request and response bodies are persisted unmodified.
5. Budgets are checked before invocation, never after.
6. Native tool definitions are refused.
7. Every identifier emitted into YAML is quoted.
8. Model output is parsed by the hardened safe parser, never by a general-purpose loader.

---

## The pipeline

```
typed domain object
  -> payload compiler          builds model-visible content from typed fields
  -> boundary validator        rejects prohibited serializations
  -> budget guard              refuses before spend
  -> provider adapter          the only place a provider SDK is used
  -> boundary validator        applied to the response
  -> safe YAML parser          when the task is structured
  -> audit record              exact bodies preserved
```

The compiler is the primary control; the validator is a backstop that catches a bypass. Both
exist because a defence that depends on one mechanism has no failure margin.

---

## Two verified YAML facts that drive the design

### YAML 1.2 does not coerce yes, no, on, off

PyYAML implements YAML 1.1, whose boolean resolver turns those bare scalars into booleans. A
footnote field whose value is the word `no` would silently become `False`. `ruamel.yaml` in pure
safe mode implements the YAML 1.2 core schema and leaves them as strings.

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

Every CIK, accession number, fiscal period, zero-prefixed footnote number, and version string is
quoted by the serializer. `require_string` refuses to return an identifier that arrived unquoted
rather than coercing it back, because the leading zeros are already unrecoverable at that point.

Covered by `test_yaml_parser_preserves_quoted_cik` and `test_yaml_parser_preserves_accession`.

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

The gateway is stateless and scales horizontally. Token estimation is a character-ratio
calculation and is not a bottleneck. The audit sink is the only shared resource; in production it
writes bodies to object storage and a row to PostgreSQL.

## Unit-test approach

Each detector is tested against a positive and a negative case. The compiler is tested to produce
content free of every prohibited construct. The parser is tested against duplicate keys, unsafe
tags, each resource limit, and the two identifier-preservation facts above.

## Integration-test approach

The full pipeline is exercised against the mock provider: compile, validate, invoke, validate the
response, parse, and assert the audit record holds the exact bodies. A provider returning JSON is
asserted to be rejected rather than parsed.

## Current test coverage

```
tests/unit/test_llm_boundary.py     26 tests
tests/unit/test_yaml_parser.py      10 tests
tests/architecture/test_architecture.py  8 tests, of which 3 enforce this boundary
```

---

## Cost rationale

Serialization overhead multiplies across roughly 170,000 filings and every footnote within them.
JSON repeats every key on every record and escapes every quote in filing prose. XML repeats every
tag name twice. Markdown adds fence, pipe, and emphasis characters carrying no information a
summarizer needs.

The token comparison harness in `packages/llm_gateway/token_counter.py` records, for every
benchmark fixture:

```
serialization_comparison:
  plain_text_tokens: 0
  yaml_tokens: 0
  markdown_tokens: 0
  json_tokens: 0
  xml_tokens: 0
  selected_format: yaml
  selected_tokens: 0
```

The production path selects plain text or YAML regardless of which serialization tokenizes
smallest, because the boundary is a correctness and security constraint rather than an
optimization. The measurement exists so the decision rests on evidence and so a regression is
visible.
