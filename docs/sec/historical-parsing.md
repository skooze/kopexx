# Historical Parsing

IMPLEMENTATION STATUS: PLANNED (Stage 2 phases W-2 and W-3)
OWNER PACKAGE: `packages/filing_parser`

## Common interface

```python
class FilingParser(Protocol):
    def can_parse(self, source: FilingSource) -> bool: ...
    def parse(self, source: FilingSource) -> ParsedFiling: ...
```

Every `ParsedFiling` reports: parser id, parser version, source hash, detected era, warnings,
confidence, sections found, footnotes found, tables found, facts found, unsupported constructs,
and validation failures. A parser never returns a partial result silently; low confidence routes
to review.

## Parser selection

By era, determined from the filing record rather than by sniffing content, with content assertions
confirming the choice.

| Parser | Era | Trigger |
|---|---|---|
| `InlineXbrlParser` | 2019 onward | `isInlineXBRL = 1` |
| `StandaloneXbrlParser` | 2009 to 2018 | `isXBRL = 1 and isInlineXBRL = 0` |
| `HtmlNoXbrlParser` | 2001 to 2008 | `isXBRL = 0` and a primary document exists |
| `PlainTextSubmissionParser` | pre-2001 | `primaryDocument = ""` |
| `PemArmoredParser` | 1990s | PEM armor detected in the flat text |

## Era-specific handling

### Inline XBRL, 2019 onward

The SEC-extracted instance removes the need for inline transformation. Where the hot path must
parse inline directly, `continuedAt` and `ix:continuation` chains must be resolved transitively
with a visited set, because a parser reading only the element body gets the footnote **title and
nothing else**, silently, with no error. Measured: one Apple 10-Q has 16 chains, up to 3 hops.

### Standalone XBRL, 2009 to 2018

Text blocks live in a separate instance document, not the HTML, and their content is
**double-escaped HTML**. Unescape exactly twice, with a stopping condition. Repeatedly calling a
generic unescape until the string stops changing will corrupt content that legitimately contains
an ampersand sequence.

### Plain text, pre-2001

Filings are wrapped in PEM armor:

```
-----BEGIN PRIVACY-ENHANCED MESSAGE-----
Proc-Type: 2001,MIC-CLEAR
Originator-Name: ...
MIC-Info: RSA-MD5,RSA,...
```

and use `<IMS-DOCUMENT>` and `<IMS-HEADER>` rather than the modern `<SEC-DOCUMENT>` and
`<SEC-HEADER>`. A parser written against modern filings reads the header block as though it were
the document.

Verified retrievable: Apple's 1994 10-K, accession `0000320193-94-000016`, returns HTTP 200 with
240,556 characters of plain text containing real content, including 31 occurrences of "Net sales"
and both Item 1 and Item 7.

Section extraction here is regex over plain text with document-order constraints. There are no
anchors, so the table-of-contents strategy is unavailable and confidence is correspondingly lower.

## Encoding

Filings are read as bytes and decoded with a documented fallback chain: UTF-8, then cp1252, then
latin-1 with replacement. The decoding used is recorded on the parse result, because a
replacement character in a financial value is a data-quality event.

## Warnings versus failures

A warning means content was parsed with a caveat. A failure means content could not be parsed and
the filing is not complete. A parser never converts a failure into a warning to make a run look
successful.
