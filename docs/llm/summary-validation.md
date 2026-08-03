# Summary Validation

---

# CURRENT DIRECTION — AUTHORITATIVE. Everything below this section is historical.

**NOT IMPLEMENTED. NO SUMMARY HAS BEEN VALIDATED BECAUSE NONE EXISTS.**

## What validation proves, and who proves it

The backend proves it, independently, against the preserved bytes. **A model's own claim that its
output is complete is never accepted as evidence.**

```
COVERAGE     every human-readable source range is represented in the accepted parse or
             explicitly marked unresolved
CITATIONS    every cited offset resolves inside the preserved source at its stated position
NUMBERS      every reported number appears verbatim in the source
FOOTNOTES    every footnote the accepted parse identified still exists as an independent node
             with its own summary, and none was merged away
```

Failure produces `PARTIAL` or `REVIEW_REQUIRED`. **A false complete is a defect**, and uncertainty
never rounds up.

## Validation is against the SOURCE, not against a taxonomy

Coverage is reconciled against discovered source material, never against a count of sections. A
count of extracted sections says nothing about whether a paragraph between two of them was dropped.

There is no expected list of section kinds to check for, because there is no universal taxonomy.
What is checked is that the preserved bytes are accounted for.

## Summary-specific validation

A summary must be grounded in the accepted parse it references, must not introduce numbers absent
from the evidence, and must not become the sole support for a material claim. A summary whose parse
has been superseded is invalidated rather than silently retained.


IMPLEMENTATION STATUS: PLANNED (Sprint 5); boundary validation IMPLEMENTED
OWNER PACKAGE: `packages/validation`

## Principle

The model is not the source of record for anything numeric. Validation is what makes a
model-generated summary safe to display next to filed financial data.

## Stages, in order

Each stage runs only if the previous passed. Ordering is cheapest-first.

```
1  boundary        response is one unfenced YAML 1.2 document       IMPLEMENTED
2  schema          every required field, correct types, valid enums
3  identity        content unit id and accession match what was requested
4  source          every cited id was actually supplied in the request
5  coverage        blocks_referenced == blocks_supplied, same for tables
6  citation        each cited source belongs to THIS unit or an approved child, and supports
                   the claim
7  numeric         every important_fact reconciles against a table cell or filed fact
8  foreign issuer  no company other than the subject is presented as the subject
9  truncation      response is complete, not cut off
10 chunk lineage   for an aggregate, every leaf chunk of the unit has an accepted summary and
                   the aggregate cites only those
```

Stage 10 is what makes hierarchical chunking safe. Without it an aggregate could be built from the
first three chunks of an eight-chunk Item and validate perfectly against them.

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

> **Corrected in Sprint 4.1 (ADR-0016).** The second clause previously read "every valid canonical
> footnote", which made a filing publishable as complete while its MD&A had no summary at all.

```
a summary is publishable only when validation_status is VALIDATED or VALIDATED_NORMALIZED

a filing's SUMMARY layer is complete only when every canonical content unit whose
summary_required is true has one such active summary

a filing's FOOTNOTE layer is complete only when every valid canonical footnote has one of its
own — the general rule does not absorb this one

an AGGREGATE summary may not be active while any required child unit lacks an accepted summary;
it is PARTIAL and names what is missing
```

An unsupported value is never presented as authoritative dashboard data. Where a summary is
withheld, the **content unit** still appears with its title, its filed position, and a link to the
original, because a missing section is worse than a missing summary.
