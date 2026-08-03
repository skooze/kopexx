# Historical Filing Transport

IMPLEMENTATION STATUS: REFERENCE. Byte-exact acquisition and preservation are IMPLEMENTED in
`packages/filing_acquisition`; the decoding contract below is PLANNED.

> **THIS DOCUMENT DESCRIBES CONTAINERS, NOT CONTENT.** It records how SEC packaged filings in each
> era so the backend can retrieve, preserve and hand over the right bytes. It says nothing about
> what a historical filing MEANS, and nothing in it may be turned into code that decides. The
> selected parsing model determines semantic structure; the backend transports and proves
> (ADR-0016, ADR-0017). An earlier version of this file specified a `FilingParser` protocol, an
> era-to-parser dispatch table and regex section extraction. All of it is deleted.

## Why this matters at all

Under `INTACT_SOURCE_ONLY` the preserved artifact goes to the parsing model in whatever syntax SEC
published. The backend therefore has to know what a package physically IS — how many addressable
members it has, what wraps them, and how the bytes decode — in order to assemble the complete
relevant human-readable source set mechanically. That is the whole of the interest here.

Dated Phase 0 corpus evidence: 613 filings across six transport eras, of which **281 are plain-text
or SGML** and 113 are inline XBRL. Historical transport is not an edge case in this corpus.

## Pre-2001 — one flat SGML stream

**A pre-2001 submission exposes no individually addressable documents.** The EDGAR submissions API
reports `primaryDocument = ""`, there is no per-document URL to fetch, and the archive path serves
one flat text file containing the entire submission. Anything that expects to enumerate a document
list, or to fetch a primary document by name, gets nothing and must not silently treat that as an
empty filing.

### PEM armor

Many filings of this era are wrapped in privacy-enhanced-mail armor:

```
-----BEGIN PRIVACY-ENHANCED MESSAGE-----
Proc-Type: 2001,MIC-CLEAR
Originator-Name: ...
MIC-Info: RSA-MD5,RSA,...
```

The armor is part of the preserved bytes and is preserved with them. It is a transport envelope, not
content, and it is never stripped from the stored original.

### IMS, not SEC, container tags

Filings of this era use `<IMS-DOCUMENT>` and `<IMS-HEADER>` where modern filings use
`<SEC-DOCUMENT>` and `<SEC-HEADER>`. Anything written against the modern tags reads the header block
as though it were the document — silently, with no error and no short read.

### Verified retrievable

Apple's 1994 10-K, accession `0000320193-94-000016`, returns HTTP 200 and 240,556 characters of
plain text. Retrieval and preservation of the era is proven; nothing about interpretation is.

## SGML container shape, generally

Across the pre-XBRL eras the submission is a single SGML stream in which member documents are
delimited by container tags rather than by separate HTTP resources. Member boundaries are transport
structure and may be used to enumerate what was filed. **Member ROLE is not.** The accession
document classifier that assigned a nine-term Regulation S-K role taxonomy was deleted for exactly
this reason (ADR-0017 section 7), and what replaces it is a non-classifying lister that reports the
filer's own declared metadata — filename, sequence, declared type, description, size — and no
verdict of its own.

## Encoding

Filings are read and stored as bytes. Where text is needed, decoding follows a documented fallback
chain — UTF-8, then cp1252, then latin-1 with replacement — and **the decoding actually used is
recorded alongside the artifact**, because a replacement character inside a financial value is a
data-quality event and not a rendering detail. The chain is specified here and is not yet
implemented; storage today is byte-exact and decoding-free.

## Warnings versus failures

A warning means bytes were handled with a caveat. A failure means they could not be handled and the
source set is incomplete. **A failure is never downgraded to a warning to make a run look
successful**, and an incomplete source set is never sent to a model as though it were complete.
