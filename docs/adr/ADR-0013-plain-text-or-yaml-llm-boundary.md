# ADR-0013: Use plain text or YAML exclusively at the LLM content boundary

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

Every model interaction in this system carries filing content, financial values, and identifiers.
The serialization used at the model boundary determines token cost, the ease with which a model
can read the content, and the class of failures possible on the way back.

Four forces apply.

Cost. The corpus is on the order of 170,000 filings. Serialization overhead is multiplied by
every footnote in every filing. JSON repeats every key on every record and escapes every quote in
filing prose. XML repeats every tag name twice. Markdown adds fence, pipe, and emphasis
characters that carry no information the model needs.

Fidelity. Raw SEC HTML, inline XBRL, and XBRL instances are machine formats containing attributes,
namespaces, and layout markup that are noise to a summarizer and actively invite the model to
reason about markup rather than content.

Determinism on return. JSON emitted by a model is frequently truncated or fenced, and repairing it
is guesswork. A structured response needs a format whose failure modes are detectable.

Security. Filing text is untrusted. A format whose parser can construct arbitrary objects is an
unacceptable attack surface for content that originates outside our control.

## Decision

Model-visible content is exactly one of two formats.

    plain_text  unmarked normalized human-readable text, no Markdown
    yaml        exactly one unfenced YAML 1.2 document, no prose before or after

Prohibited in model-visible content in both directions: Markdown of any kind including fences,
tables, headings, links, blockquotes, and inline backticks; JSON; JSON Lines; JSON Schema; XML;
XBRL; inline XBRL; HTML; XHTML; native tool schemas; native tool arguments.

Native model tool calling is prohibited, because it requires JSON Schema tool definitions and
produces JSON tool arguments. Deep Analysis retrieval is application-orchestrated, or uses a
bounded YAML action protocol in which the server ignores any scope the model proposes and loads
scope from the session instead.

All model access passes through `packages/llm_gateway`, which owns payload compilation, boundary
validation, token counting, cost calculation, response validation, and audit persistence. Only
`packages/llm_gateway/providers` may import a provider SDK.

The exact model-visible request and the exact model response are persisted unmodified.

## The transport exception

Amazon Bedrock and the AWS SDK use JSON as their wire protocol. That is outside the model-visible
boundary and is permitted. The distinction is between the envelope and the content: the SDK may
serialize the request as JSON, but the text inside the message must be plain text or YAML. An SDK
request object must never be copied into model-visible content.

Five serialization contexts exist and only the first is constrained by this ADR.

    1. model-visible content ......... plain text or YAML only
    2. internal application state .... any typed representation
    3. browser and API traffic ....... JSON, per normal REST practice
    4. database storage .............. relational columns and JSONB
    5. provider wire protocol ........ whatever the SDK requires

## YAML specifics

### Parser selection, pinned

    library      ruamel.yaml
    version      0.19.1  (floor pinned at 0.18 by test)
    mode         YAML(typ="safe", pure=True)
    schema       YAML 1.2 core
    resolver     VersionedResolver
    python       3.14.6

`pure=True` forces the Python implementation, whose resolver behaviour is pinnable; the C loader
is not used because its behaviour is harder to guarantee across builds.

PyYAML is deliberately NOT used. It implements YAML 1.1, whose boolean resolver converts the bare
scalars yes, no, on, and off into booleans. A footnote field whose value is the word "no" would
silently become False. Verified Sprint 1, re-verified Sprint 2:

    a: yes  ->  'yes'  (str)      under YAML 1.2 core
    b: no   ->  'no'   (str)
    c: on   ->  'on'   (str)
    d: off  ->  'off'  (str)

Covered by `test_yaml_12_does_not_coerce_yes_no_on_off` and
`test_yaml_library_is_ruamel_with_yaml_12_semantics`.

Identifiers are always quoted. YAML 1.2 parses an unquoted 0000320193 as the integer 320193,
destroying the leading zeros that make it a valid CIK. Verified during Sprint 1. The serializer
quotes a defined set of identifier keys automatically, and the parser refuses to return an
identifier that arrived unquoted rather than coercing it back.

### Resource limits

    input size        4 MiB
    nesting depth     32
    collection size   10,000
    scalar length     1,000,000
    documents         1
    anchors           16      pre-parse
    aliases           16      pre-parse
    duplicate keys    rejected
    custom tags       rejected

### The alias bound, added in Sprint 2

The original limits ran AFTER parsing and were therefore useless against alias expansion, which
happens during parsing. Measured on the Sprint 1 parser: a five-line document with nine anchors,
each referencing the previous nine, expanded to 59,049 leaf nodes. Two further levels exhaust
memory.

The guard is a pre-parse textual scan of the raw source, because by the time a post-parse check
runs the allocation has already occurred. Detection deliberately does not attempt to exclude
quoted contexts: over-counting causes a safe, loud rejection, while under-counting would admit
the bomb.

None of our model-output schemas uses aliases, so the bound is set low. Covered by
`test_yaml_parser_rejects_excessive_aliases`, `test_yaml_parser_rejects_excessive_anchors`, and
`test_yaml_parser_allows_a_small_number_of_aliases`.

## Alternatives Considered

JSON with provider structured-output enforcement. Rejected: it requires sending JSON Schema to
the model, which is prohibited, and it couples the application to a provider feature that not
every candidate model offers.

Markdown for readability. Rejected: it carries formatting characters that convey nothing to a
summarizer, has no unambiguous structured form, and its tables lose the unit and scale metadata
that financial correctness depends on.

XML because filings are already XML. Rejected: it is the most verbose option and passes filing
markup to the model rather than the content.

Native tool calling for Deep Analysis. Rejected: it mandates JSON at the boundary, and the
security model requires the server to hold scope regardless of what the model asks for.

## Consequences

Token cost falls because keys are not repeated per record and prose is not escaped. Model input
is readable, which makes prompt debugging tractable. One parser and one validator cover every
model interaction. Provider structured-output and tool-calling features are unavailable to us, so
schema conformance is enforced by our own validation after parsing. A payload compiler must exist
before any model integration, which is why it is Sprint 1 work rather than Sprint 5 work.

## Testing

Enforcement is tested in three layers. Unit tests assert the validator rejects each prohibited
construct. Compiler tests assert produced payloads contain none of them. An architecture test
asserts no provider SDK is imported outside the provider directory, that no prompt file is
Markdown, and that no prompt instructs a model to emit a prohibited format.

## Migration Impact

Reversing this decision means rewriting the payload compiler, the response parser, every prompt,
and the Deep Analysis action protocol. The audit record preserves original bodies, so historical
invocations remain interpretable.

## Revisit Conditions

Revisit if measurement shows YAML tokenizes materially worse than an alternative for our actual
payloads, if a provider offers structured output that accepts a non-JSON schema description, or
if a YAML 1.2 parser vulnerability makes the format untenable for untrusted input.
