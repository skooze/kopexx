"""Inline-XBRL tagged spans in the primary document.

An inline-XBRL filing marks each block of narrative with an element naming the concept it carries:

    <ix:nonNumeric name="us-gaap:DebtDisclosureTextBlock" ...> ... the whole note ... </ix:nonNumeric>

**That element is the note boundary, drawn by the filer.** Anything inside it — paragraphs,
tables, nested tagged facts — is part of that note. This is what makes table ownership a
containment test rather than a proximity guess.

Apple's FY2025 10-K contains 58 such TextBlock facts. That is the same 58 the project's
`13-not-58` correction is named after: 58 tagged blocks, 13 of which are notes and the rest of
which are the tables and details filed underneath them. Both numbers come from here.

SPANS NEST. `aapl:CommercialPaperCashFlowSummaryTableTextBlock` sits inside
`us-gaap:DebtDisclosureTextBlock`. A table inside the inner one is inside both, and the INNERMOST
containing span is the most specific answer. Resolving the innermost concept back through the
presentation linkbase reaches the same note either way, because a child role attaches to its
parent — which is the attachment already audited in stage 3.

SPANS ALSO CONTINUE, AND MISSING THAT LOSES REAL TABLES. A fact whose content is not contiguous
carries `continuedAt="f-361-1"`, and the rest of it lives in `<ix:continuation id="f-361-1">`,
which may itself continue onward. Apple's FY2025 10-K has 24 continued TextBlocks and 35
continuation elements, 11 of them chained further.

This is not an edge case. The debt note's maturity schedule, its commercial-paper table, and the
purchase-obligation table all sit in continuations rather than inside the TextBlock element
itself. Treating only the element as the note boundary classified those tables as unowned filing
furniture — a false negative that would have silently narrowed what Sprint 5 can validate a
summary against. A concept's span is the element PLUS its whole continuation chain.

WHY A SCANNER RATHER THAN AN XML PARSER. The document is a 1.5 MB inline-XBRL file whose body is
HTML with XBRL attributes. A strict XML parse is possible but unnecessary here: what is needed is
the byte span of each tagged element, and a tag scanner that tracks depth gives exactly that
without materialising a DOM for a 220,000-word document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Only `ix:` elements that carry a fact. `ix:header`, `ix:references` and friends carry metadata
# and never wrap narrative.
FACT_TAG = re.compile(
    r"<(?P<close>/?)(?P<tag>ix:(?:nonNumeric|nonFraction|continuation))\b(?P<attrs>[^>]*)>",
    re.IGNORECASE,
)
SELF_CLOSING = re.compile(r"/\s*>$")
NAME_ATTR = re.compile(r'\bname\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
CONTINUED_AT_ATTR = re.compile(r'\bcontinuedAt\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
ID_ATTR = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

TEXT_BLOCK_SUFFIX = "TextBlock"


@dataclass(frozen=True)
class TaggedSpan:
    """One inline-XBRL fact element and the byte range it encloses."""

    concept: str
    start: int
    end: int
    tag: str
    element_id: str | None = None
    continued_at: str | None = None
    # True when this span is a continuation region resolved onto its originating concept, rather
    # than the element that declared the concept. Kept so provenance stays honest.
    is_continuation: bool = False

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def is_text_block(self) -> bool:
        return self.concept.endswith(TEXT_BLOCK_SUFFIX)

    def contains(self, offset: int) -> bool:
        return self.start <= offset < self.end


def find_tagged_spans(raw: str) -> list[TaggedSpan]:
    """Every inline-XBRL fact element in the document, with its byte range.

    Nesting is tracked with a stack so an inner element's range is its own, not its parent's. An
    unbalanced close tag is ignored rather than raising: filings occasionally carry stray markup,
    and losing the whole document to one of them would be worse than losing one span.
    """
    spans: list[TaggedSpan] = []
    # (concept, start offset, tag, element id, continuedAt target)
    stack: list[tuple[str, int, str, str | None, str | None]] = []

    for match in FACT_TAG.finditer(raw):
        tag = match.group("tag").lower()
        if match.group("close"):
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][2] == tag:
                    concept, start, _, element_id, continued = stack.pop(index)
                    spans.append(
                        TaggedSpan(
                            concept=concept,
                            start=start,
                            end=match.end(),
                            tag=tag,
                            element_id=element_id,
                            continued_at=continued,
                        )
                    )
                    del stack[index:]
                    break
            continue

        if SELF_CLOSING.search(match.group(0)):
            continue

        attrs = match.group("attrs")
        name_match = NAME_ATTR.search(attrs)
        id_match = ID_ATTR.search(attrs)
        continued_match = CONTINUED_AT_ATTR.search(attrs)
        stack.append(
            (
                name_match.group(1) if name_match else "",
                match.start(),
                tag,
                id_match.group(1) if id_match else None,
                continued_match.group(1) if continued_match else None,
            )
        )

    return sorted(spans, key=lambda s: (s.start, -s.length))


def resolve_continuations(spans: list[TaggedSpan]) -> list[TaggedSpan]:
    """Extend each concept's coverage over its continuation chain.

    A continuation element carries no `name`, so on its own it says nothing about what it belongs
    to. Walking `continuedAt` from the declaring fact assigns each continuation region the
    originating concept, and the chain is followed transitively.

    A cycle would hang the walk, so visited ids terminate it. Malformed markup is a filing defect,
    not a reason to lose the document.
    """
    by_id = {span.element_id: span for span in spans if span.element_id}
    resolved = list(spans)

    for span in spans:
        if not span.concept or not span.continued_at:
            continue
        seen: set[str] = set()
        next_id: str | None = span.continued_at
        while next_id and next_id not in seen:
            seen.add(next_id)
            target = by_id.get(next_id)
            if target is None:
                break
            resolved.append(
                TaggedSpan(
                    concept=span.concept,
                    start=target.start,
                    end=target.end,
                    tag=target.tag,
                    element_id=target.element_id,
                    continued_at=target.continued_at,
                    is_continuation=True,
                )
            )
            next_id = target.continued_at

    return sorted(resolved, key=lambda s: (s.start, -s.length))


def text_block_spans(raw: str) -> list[TaggedSpan]:
    """Every region belonging to a narrative block, continuations included.

    Continuations are resolved BEFORE filtering to TextBlocks: a continuation element has no name
    of its own, so filtering first would discard it before it could inherit one.
    """
    resolved = resolve_continuations(find_tagged_spans(raw))
    return [span for span in resolved if span.is_text_block and span.concept]


def innermost_span_at(spans: list[TaggedSpan], offset: int) -> TaggedSpan | None:
    """The smallest tagged span containing an offset, or None when none does.

    Smallest rather than first: spans nest, and the innermost is the most specific statement about
    what that byte belongs to. A table inside a maturity-schedule TextBlock inside a debt note
    belongs to the schedule, which in turn belongs to the note.
    """
    containing = [span for span in spans if span.contains(offset)]
    if not containing:
        return None
    return min(containing, key=lambda s: s.length)
