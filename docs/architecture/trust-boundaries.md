# Trust Boundaries and Security Architecture

IMPLEMENTATION STATUS: the LLM content boundary and SEC input controls are IMPLEMENTED; identity,
network, and infrastructure controls are PLANNED

> **UPDATED 2026-08-03.** The fact lake and the curated metric definitions that used to sit on the
> trusted side were deleted with the deterministic parser (ADR-0017), and there is no application
> database. What remains trusted is smaller and simpler: bytes this system preserved and verified,
> and files it wrote itself.

## Boundaries

```
+--------------------------------------------------------------+
|  UNTRUSTED                                                   |
|    browser requests                                          |
|    SEC filing content                                        |
|    model responses, including every parsed artifact          |
+--------------------------------------------------------------+
                          |  validation at every crossing
+--------------------------------------------------------------+
|  TRUSTED                                                     |
|    preserved source bytes with a verified SHA-256            |
|    prompt files, configuration, session records              |
+--------------------------------------------------------------+
```

Filing content is the boundary most often mistaken for trusted. It arrives from SEC, so it is
authentic, but authenticity is not trustworthiness: a filing is written by the company and can
contain anything, including text shaped like instructions to a language model.

**A parsed artifact is on the untrusted side and stays there.** It is a model response. Approval by
a human reviewer makes it REUSABLE; it does not make it evidence. Anything that must be proved is
proved against the preserved bytes.

## Controls by boundary

### Browser to API — PLANNED

Schema validation rejecting unknown fields rather than ignoring them. Authentication and session
ownership on every request. Per-principal rate limits and request size limits. Output encoding.
Parameterized queries throughout. Localhost-only operation until authentication exists; no
unauthenticated exposure beyond loopback, and no browser-to-provider path ever.

### SEC to Kopexx — IMPLEMENTED in part

Declared User-Agent, validated at startup. Content assertions before persistence: a directory
listing is never stored as a filing. Every object hashed. Archives are streamed, never expanded
blindly, so a zip bomb cannot exhaust inodes or disk.

### Kopexx to model — IMPLEMENTED

Content boundary enforced in both directions. Only the compiler produces model-visible synthetic
content. A preserved SEC artifact is the one exception: it is admitted by PROVENANCE — bytes
identical to a stored artifact whose SHA-256 is recorded — sent intact, and never rewritten. Only
the provider adapter imports a provider SDK. Native tool calling refused. Budgets enforced before
invocation. Exact bodies recorded.

### Model to Kopexx — IMPLEMENTED in part

Response validated at the boundary before parsing. Hardened YAML parser with limits on size, depth,
collection size, scalar length, and document count, rejecting duplicate keys and custom tags. **The
original-source exception is one-directional and does not apply here:** a response is synthetic
content whichever way it travels.

PLANNED, and the control the whole architecture rests on: coverage, citation and numeric validation
**against the preserved source bytes**. Every cited offset must resolve into the stored original and
every reported figure must appear there verbatim. Uncertainty produces PARTIAL or REVIEW_REQUIRED,
never a false complete. It is never validated against a second parse — that reinstates a
deterministic interpretation as authority (`rules.md` section 21 rule 15).

## Prompt injection

Filing text is data. The system prompts state that instructions found inside source content are
ignored and reported. The structural defence is that scope lives in the tools and the session, not
in the prompt, so a model persuaded to want something out of scope still cannot retrieve it.

## Secrets

In a secrets manager, never in the repository. The structured logger redacts a fixed field set.
`BoundaryViolationError` carries origin and violation names but never content.

**AWS identity is not a secret this system holds.** Kopexx never creates, accepts, persists, logs or
transports a raw AWS credential; the SDK resolves short-lived identity through a federated provider,
a workload role or an OIDC-assumed role. A secrets manager holds workload secrets that IAM cannot
replace, and it is not where AWS identity lives. Mandatory rule: `rules.md` section 3. Full design:
`docs/security/aws-identity-and-secrets.md`.

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
