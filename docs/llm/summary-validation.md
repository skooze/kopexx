# Summary Validation

IMPLEMENTATION STATUS: PLANNED (Phase 6); boundary validation IMPLEMENTED
OWNER PACKAGE: `packages/validation`

## Principle

The model is not the source of record for anything numeric. Validation is what makes a
model-generated summary safe to display next to filed financial data.

## Stages, in order

Each stage runs only if the previous passed. Ordering is cheapest-first.

```
1  boundary        response is one unfenced YAML 1.2 document       IMPLEMENTED
2  schema          every required field, correct types, valid enums
3  identity        footnote id and accession match what was requested
4  source          every cited id was actually supplied in the request
5  coverage        blocks_referenced == blocks_supplied, same for tables
6  citation        each cited source belongs to THIS footnote and supports the claim
7  numeric         every important_fact reconciles against a table cell or filed fact
8  foreign issuer  no company other than the subject is presented as the subject
9  truncation      response is complete, not cut off
```

## Numeric validation

For each `important_facts` entry, locate the value in the supplied tables or in the filed facts
and compare on **five** dimensions. All five must match.

```
value    within a tolerance that accounts for stated rounding
unit     exact
scale    exact
sign     exact
period   exact start and end, and instant versus duration
```

A value matching on amount but not on scale is a failure, not a rounding difference. "1,250" in a
table headed USD millions is 1,250,000,000, and a summary reporting 1,250 USD is wrong by six
orders of magnitude.

## Result states

```
VALIDATED                  every stage passed
VALIDATED_NORMALIZED       passed after a documented normalization, for example a unit
                           conversion the summary stated correctly in different terms
SOURCE_PRESENT_AMBIGUOUS   the source exists but more than one candidate matches
SOURCE_NOT_FOUND           the cited id resolves to nothing
UNIT_MISMATCH
SCALE_MISMATCH
PERIOD_MISMATCH
SIGN_MISMATCH
UNSUPPORTED                a claim carries no citation at all
REQUIRES_REVIEW            a human must decide
FAILED                     retries exhausted
```

## Transitions

```
GENERATED -> VALIDATING -> VALIDATED             -> ACTIVE
                        -> VALIDATED_NORMALIZED  -> ACTIVE
                        -> any mismatch          -> REQUIRES_REVIEW
                        -> schema failure        -> REPAIRING -> VALIDATING
                                                              -> REQUIRES_REVIEW
REQUIRES_REVIEW -> ACTIVE            reviewer accepted
                -> REJECTED          reviewer rejected; a new attempt is queued
ACTIVE -> SUPERSEDED                 a newer version was activated
```

Only `ACTIVE` summaries are displayed and only they count toward completeness.

## Publishing gate

```
a summary is publishable only when validation_status is VALIDATED or VALIDATED_NORMALIZED
a filing is complete only when every valid canonical footnote has one such active summary
```

An unsupported value is never presented as authoritative dashboard data. Where a summary is
withheld, the footnote still appears with its title and a link to the original, because a missing
footnote is worse than a missing summary.
