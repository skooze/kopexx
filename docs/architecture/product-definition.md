# Product Definition

IMPLEMENTATION STATUS: PLANNED (the product; the foundation supporting it is IMPLEMENTED)

## Vision

An investor types a ticker and receives that company's SEC filings already digested: deterministic
financial charts, and one plain-language summary for every financial-statement footnote in every
10-K and 10-Q the company has ever filed. When they want to go deeper, they explicitly start a
Deep Analysis session locked to that issuer.

A 10-K may run a hundred pages, of which only a page or two is the financial statements. The rest
is footnotes explaining *why* the company did what it did. The footnotes are the product.

## Primary users

The retail or semi-professional investor researching a company, who can read a financial statement
but will not read ninety pages of footnotes. The analyst who will read them but wants to find the
three that matter first. Neither wants to touch raw SEC HTML.

## Core user journeys

1. **Look up a company.** Type a ticker, get identity, filing timeline, charts, and every
   footnote summarized. No model call occurs.
2. **Follow a number.** Click a line on a chart, land on the footnote that explains it, read the
   summary, open the original SEC rendering if wanted.
3. **Scan what changed.** Compare a footnote topic across periods and see which changed.
4. **Go deep deliberately.** Start a Deep Analysis session from a footnote, a filing, or a
   timeframe, ask a question or accept the generic forensic analysis, and get cited findings.
5. **Check coverage.** See honestly how much of a filing has been processed.

## Product boundaries

The system reads SEC filings and explains them. It does not price securities, execute trades,
manage portfolios, recommend actions, or predict prices.

## Non-goals for the MVP

Real-time market pricing, brokerage integration, trade execution, personalized recommendations,
portfolio management, news scraping, social sentiment, earnings-call transcription, options
analytics, non-US filing systems, mobile applications, full valuation modeling, and SEC form types
beyond 10-K and 10-Q.

## The three non-negotiable properties

```
EVERY actual financial-statement footnote in every processed 10-K and 10-Q has one canonical
record and one active accepted summary.

ORDINARY dashboard access never invokes a language model.

DEEP ANALYSIS is a deliberate, scoped, metered, auditable feature bound to one issuer, not a
general-purpose financial chatbot.
```

## Definitions the product must fix

Full algorithms in `docs/financial/fiscal-periods.md`.

| Term | Definition |
|---|---|
| All-time | Every 10-K and 10-Q ever filed electronically, reaching the 1990s |
| Current year | The issuer's most recent fiscal year with any filed 10-K or 10-Q; may be partial |
| Previous year | The fiscal year immediately preceding current year |
| Five years | Current year plus the four preceding fiscal years |
| Ten years | Current year plus the nine preceding fiscal years |

"Year" always means the **issuer's** fiscal year, never the calendar year, because Apple's fiscal
2025 ends in September and comparing it to a calendar year would be wrong.

### What all-time actually delivers

Verified: Apple's 1994 10-K is retrievable and readable. Documents and footnote summaries reach
the 1990s. Structured **numeric** series are XBRL-bound and effectively complete from 2011,
because XBRL did not exist before 2009. Pre-2009 numeric extraction is Phase 10.

The dashboard shows a per-company coverage badge rather than silently rendering a short chart.

## Issuer identity

CIK is identity. Ticker is a temporal alias. Full model in `docs/sec/issuer-identity.md`.

| Case | Behaviour |
|---|---|
| Ticker reuse | Resolution is always as-of a date. `BBBY` maps to two different issuers |
| Delisted issuer | Remains in the universe if it ever filed a 10-K or 10-Q |
| Renamed issuer | Former names retained; name matching alone is unreliable |
| Multiple share classes | Share a CIK; one company, several listings |
| Spinoffs, mergers, successors | Recorded as issuer relationships where known |
| Excluded filer | Preserved with a reason, not discarded |
| Foreign private issuer | Excluded from the active universe; files 20-F, not 10-K |

A ticker that has never filed a 10-K or 10-Q does not appear in search or autocomplete. Showing a
symbol we cannot serve is worse than not showing it.

## Future expansion

Additional form types (20-F, 8-K, DEF 14A, S-1), delisted-issuer historical backfill, pre-2009
numeric extraction, and cross-issuer comparison as a distinct scope type. The ingestion layer is
form-extensible so these are additions rather than rewrites.
