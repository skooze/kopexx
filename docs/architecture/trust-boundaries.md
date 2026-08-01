# Trust Boundaries and Security Architecture

IMPLEMENTATION STATUS: boundary and input controls IMPLEMENTED; identity, network, and
infrastructure controls PLANNED

## Boundaries

```
+--------------------------------------------------------------+
|  UNTRUSTED                                                   |
|    browser requests                                          |
|    SEC filing content                                        |
|    model responses                                           |
+--------------------------------------------------------------+
                          |  validation at every crossing
+--------------------------------------------------------------+
|  TRUSTED                                                     |
|    session records, fact lake, curated metric definitions,   |
|    prompt files, configuration                               |
+--------------------------------------------------------------+
```

Filing content is the boundary most often mistaken for trusted. It arrives from SEC, so it is
authentic, but authenticity is not trustworthiness: a filing is written by the company and can
contain anything, including text shaped like instructions to a language model.

## Controls by boundary

### Browser to API

Schema validation rejecting unknown fields rather than ignoring them. Authentication and session
ownership on every request. Per-principal rate limits and request size limits. Output encoding.
Parameterized queries throughout.

### SEC to FinTek — IMPLEMENTED in part

Declared User-Agent, validated at startup. Content assertions before persistence: a directory
listing is never stored as a filing. Every object hashed. Archives are streamed, never expanded
blindly, so a zip bomb cannot exhaust inodes or disk.

### FinTek to model — IMPLEMENTED

Content boundary enforced in both directions. Only the compiler produces model-visible content.
Only the provider adapter imports a provider SDK. Native tool calling refused. Budgets enforced
before invocation. Exact bodies persisted.

### Model to FinTek — IMPLEMENTED

Response validated at the boundary before parsing. Hardened YAML parser with limits on size,
depth, collection size, scalar length, and document count, rejecting duplicate keys and custom
tags. Citations validated against supplied evidence. Numeric claims reconciled against facts
before display.

## Prompt injection

Filing text is data. The system prompts state that instructions found inside source content are
ignored and reported. The structural defence is that scope lives in the tools and the session, not
in the prompt, so a model persuaded to want something out of scope still cannot retrieve it.

## Secrets

In a secrets manager, never in the repository. The structured logger redacts a fixed field set.
`BoundaryViolationError` carries origin and violation names but never content.

## IAM — PLANNED

Separate least-privilege roles for API, ingestion, workers, and deployment. The API cannot write
to the raw object store. Workers cannot read session records. Deployment cannot read data.

## Data deletion — PLANNED

Filing data is public and retained indefinitely. User data, sessions, messages, and memory are
deletable on request. Model invocation records are retained with the principal identifier
anonymized rather than the row deleted, because cost accounting must remain reconcilable.

## Incident response — PLANNED

Scope violation: log, alert on rate, review the detector, add a test.
Credential exposure: rotate, audit access, review logs for use.
Prompt injection observed: capture the filing, add it as a security fixture, verify no behaviour
changed.
Boundary rejection in production: treat as a code defect, page, and roll back the deploy.
