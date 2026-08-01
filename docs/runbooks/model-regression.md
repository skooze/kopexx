# Runbook: model or prompt regression

SEVERITY: high

## Symptoms

Validation failure rate rises. Review backlog rises. Numeric fidelity falls on the benchmark.
Structured output validity falls, usually visible as boundary rejections.

## Procedure

1. Identify what changed: prompt version, model identifier, provider-side model update, or
   temperature-equivalent configuration.
2. Re-run the benchmark corpus against both the previous and current configuration.
3. Compare against the production gates in
   `prompts/footnote-summary/v1.0.0/evaluation.yaml`.

## Rollback

Activate the previous prompt version, or pin the previous model identifier. Summaries are
versioned, so affected summaries are superseded rather than overwritten and the previous ones
remain available.

Do **not** delete the regressed summaries. They are evidence for the post-mortem.

## Provider-side drift

A provider may update a model behind a stable identifier. If nothing changed on our side and the
benchmark still regressed, that is the likely cause. Record the observation, pin a dated model
identifier if the provider offers one, and re-run the benchmark on a schedule to detect it sooner
next time.
