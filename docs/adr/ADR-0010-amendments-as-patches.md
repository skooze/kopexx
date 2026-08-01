# ADR-0010: Model amendments as patches, never as replacements

STATUS: ACCEPTED
DATE: 2026-08-01
SPRINT: 1

## Context

The intuitive model is that a 10-K/A supersedes the 10-K it amends. Verification shows that is
false often enough to be dangerous.

AMD's 10-K/A, accession 0000002488-26-000021, is 545,192 bytes against the original's 14,078,338.
It was filed the same day, carries the same report date, and reuses the same primary document
filename. NTRB's amendment is a 95 KB document containing a single text block of four characters
and no Item 1A content at all.

Amendments are frequently partial: adding Part III, correcting an exhibit, or refiling a single
section. In one recent quarter 373 amendments were filed against 621 original annual reports, so
this is not an edge case.

Treating an amendment as a replacement would blank the dashboard for every amended filer.

## Decision

An amendment is a patch related to an original filing, never a tombstone. Both filings are
retained and independently retrievable. The system records which sections, footnotes, and facts
the amendment actually changes, and whether it constitutes complete replacement content.

The dashboard presents a current amended view composed of the original plus applied patches, and
can also present the original as filed. Summaries follow the same rule: an amended footnote gets a
new summary version, and the original version is superseded rather than deleted.

## Alternatives Considered

Replace the original. Rejected on the evidence above.

Ignore amendments. Rejected: an amendment can materially change a restated figure or add Part III
compensation disclosure.

## Consequences

The filing model carries an explicit amendment relationship and a patch-scope record. Queries must
be explicit about whether they want the as-filed or amended view. Detecting what an amendment
actually changed is real work and is a source of parse uncertainty that routes to review.

## Migration Impact

None; this is the initial model.

## Revisit Conditions

Revisit if measurement shows a class of amendments that genuinely replaces the original in full,
in which case the patch record simply reflects that.
