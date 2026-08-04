"""Walk one preserved markup document once and record what is mechanically there.

ONE PASS, TWO PRODUCTS. Text spans and table elements come out of the same walk because they share
the same coordinate system and the same element stack. Two walks would be two chances to disagree
about where a table starts.

THE ONLY CATEGORY JUDGEMENT MADE HERE IS HTML'S OWN. A span ends at a BLOCK-level boundary and
survives an INLINE one. That distinction is in the HTML content model, not in anything about SEC
filings, and it is the difference between a denominator that means something and one that does not:

    inline XBRL shreds a single rendered sentence across `span` and `ix:nonFraction` elements.
    Treating every element as a boundary turns ordinary prose into thousands of two-character
    fragments, and a coverage figure computed over those fragments answers a question nobody asked.

OFFSETS ARE EXACT AND ARE DERIVED FROM THE NEXT EVENT, NOT FROM A LENGTH. `HTMLParser.getpos()`
reports where the construct being handled STARTS. Deriving the end from `len(data)` is wrong the
moment an entity reference is decoded, because the decoded string is shorter than its source. Every
construct's end is therefore the next construct's start, and the last one ends at the end of the
document. That is exact for entities, for malformed markup, and for anything else the parser
chooses to normalise.

A SPAN'S RANGE AND A SPAN'S TEXT ARE COMPUTED DIFFERENTLY, ON PURPOSE. The range is the source
slice, because that is what a review UI highlights in the preserved bytes. The text is the
concatenated CHARACTER DATA, because a comment or an inline element sitting between two words is
inside the range and is not something a reader sees. Taking the text from the slice would put
`<!-- -->` into a visible-text span.

MALFORMED MARKUP IS NORMAL AND IS NOT AN ERROR. rules.md records that malformed markup is normal
before 2005, and a filing whose `p` elements never close is a filing, not a failure. An end tag
that matches nothing is ignored; an end tag matching something further down the stack closes
everything above it. A table left open runs to the end of the member and says so. None of it raises.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final

from packages.storage import sha256_text

from .errors import MarkupUnreadableError
from .records import HiddenReason, TableCell, TableElement, TextSpan

#: Elements after which a rendered line does not continue. HTML's own block-level content model,
#: plus `br`, which is inline but is a line break and therefore a span boundary.
_BLOCK_TAGS: Final[frozenset[str]] = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "br", "caption", "center", "col",
        "colgroup", "dd", "details", "dialog", "div", "dl", "dt", "fieldset", "figcaption",
        "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr",
        "html", "legend", "li", "main", "nav", "noscript", "ol", "option", "p", "pre", "script",
        "section", "select", "style", "summary", "table", "tbody", "td", "textarea", "tfoot", "th",
        "thead", "title", "tr", "ul",
    }
)  # fmt: skip

#: Elements that never have an end tag. Pushing one onto the stack corrupts every path after it.
_VOID_TAGS: Final[frozenset[str]] = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr",
    }
)  # fmt: skip

#: Elements whose content a browser never renders as prose.
_NON_RENDERED: Final[frozenset[str]] = frozenset({"script", "style", "noscript"})

#: Inline-XBRL containers that exist to carry tagged facts WITHOUT displaying them. `ix:hidden` is
#: the one the specification names for exactly that; the other three are metadata containers.
_IX_HIDDEN_TAGS: Final[frozenset[str]] = frozenset(
    {"ix:hidden", "ix:header", "ix:references", "ix:resources"}
)

_DISPLAY_NONE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:;|$)", re.IGNORECASE
)
_WHITESPACE_RUN = re.compile(r"\s+")

#: A document with no element at all is not markup. Returning an empty inventory for it would be
#: indistinguishable from a document whose tables were missed.
_ANY_TAG = re.compile(r"<[a-zA-Z!/?]")


def normalize_text(text: str) -> str:
    """Collapse whitespace runs to one space and strip the ends. No case or Unicode folding.

    Deliberately weaker than the anchor-resolution ladder in `packages/completeness`. This is the
    identity used to recognise that two spans carry the same characters; folding case here would
    make `NOTE` and `note` the same span, which is a judgement about content rather than a
    transport observation.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


@dataclass
class _Frame:
    """One open element."""

    tag: str
    path: str
    children: dict[str, int] = field(default_factory=dict)
    hidden: HiddenReason | None = None


@dataclass
class _CellBuilder:
    is_header: bool
    row_span: int
    column_span: int
    start: int
    fragments: list[str] = field(default_factory=list)
    end: int = 0


@dataclass
class _TableBuilder:
    table_id: str
    start: int
    path: str
    parent_table_id: str
    depth: int
    rows: list[list[_CellBuilder]] = field(default_factory=list)
    current_cell: _CellBuilder | None = None
    end: int = 0


class _Walker(HTMLParser):
    """Collect every construct's start offset in document order.

    Nothing is interpreted in this class. It exists so the second pass can compute an exact end for
    every construct from the start of the one after it.
    """

    def __init__(self, text: str) -> None:
        # convert_charrefs=True gives readable character data; the offsets do not depend on it,
        # because every end comes from the next event rather than from a decoded length.
        super().__init__(convert_charrefs=True)
        self._text = text
        starts = [0]
        position = text.find("\n")
        while position != -1:
            starts.append(position + 1)
            position = text.find("\n", position + 1)
        self._line_starts = starts
        #: (offset, kind, tag, attrs, data)
        self.events: list[tuple[int, str, str, dict[str, str], str]] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        if line - 1 >= len(self._line_starts):
            return len(self._text)
        return min(self._line_starts[line - 1] + column, len(self._text))

    @staticmethod
    def _attrs(pairs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {name.lower(): (value or "") for name, value in pairs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.events.append((self._offset(), "start", tag, self._attrs(attrs), ""))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.events.append((self._offset(), "startend", tag, self._attrs(attrs), ""))

    def handle_endtag(self, tag: str) -> None:
        self.events.append((self._offset(), "end", tag, {}, ""))

    def handle_data(self, data: str) -> None:
        self.events.append((self._offset(), "data", "", {}, data))

    def handle_comment(self, data: str) -> None:
        self.events.append((self._offset(), "other", "", {}, ""))

    def handle_decl(self, decl: str) -> None:
        self.events.append((self._offset(), "other", "", {}, ""))

    def handle_pi(self, data: str) -> None:
        self.events.append((self._offset(), "other", "", {}, ""))

    def unknown_decl(self, data: str) -> None:
        self.events.append((self._offset(), "other", "", {}, ""))


class _Inventory:
    """The second pass: turn ordered events into spans and tables."""

    def __init__(self, text: str, member: str) -> None:
        self._text = text
        self._member = member
        self._stack: list[_Frame] = []
        self._root_children: dict[str, int] = {}
        self._spans: list[TextSpan] = []
        self._tables: list[TableElement] = []
        self._table_stack: list[_TableBuilder] = []
        #: (source start, source end, character data) for the run being accumulated.
        self._run: list[tuple[int, int, str]] = []
        self._table_ordinal = 0
        self._span_ordinal = 0
        self.findings: list[str] = []

    # --- element paths ---------------------------------------------------------------------

    def _path_for(self, tag: str) -> str:
        counter = self._stack[-1].children if self._stack else self._root_children
        counter[tag] = counter.get(tag, 0) + 1
        parent = self._stack[-1].path if self._stack else ""
        return f"{parent}/{tag}[{counter[tag]}]" if parent else f"{tag}[{counter[tag]}]"

    @property
    def _hidden(self) -> HiddenReason:
        for frame in reversed(self._stack):
            if frame.hidden is not None:
                return frame.hidden
        return HiddenReason.VISIBLE

    # --- spans -----------------------------------------------------------------------------

    def _flush_span(self) -> None:
        """Emit the accumulated run as one span, if its character data carries anything."""
        if not self._run:
            return
        run, self._run = self._run, []
        normalized = normalize_text("".join(fragment for _, _, fragment in run))
        if not normalized:
            return
        start, end = run[0][0], run[-1][1]
        self._span_ordinal += 1
        self._spans.append(
            TextSpan(
                span_id=f"{self._member}#s{self._span_ordinal}",
                member=self._member,
                start=start,
                end=end,
                original_text=self._text[start:end],
                normalized_text=normalized,
                hidden_reason=self._hidden,
                element_path=self._stack[-1].path if self._stack else "",
                parent_element=self._stack[-1].tag if self._stack else "",
                table_id=self._table_stack[-1].table_id if self._table_stack else "",
                duplicate_of="",
            )
        )

    # --- elements --------------------------------------------------------------------------

    def _hidden_reason_for(self, tag: str, attrs: dict[str, str]) -> HiddenReason | None:
        if tag in _NON_RENDERED:
            return HiddenReason.NON_RENDERED_ELEMENT
        if tag in ("head", "title"):
            return HiddenReason.DOCUMENT_HEAD
        if tag in _IX_HIDDEN_TAGS:
            return HiddenReason.IX_HIDDEN
        style = attrs.get("style", "")
        if style and _DISPLAY_NONE.search(style):
            return HiddenReason.STYLE_SUPPRESSED
        return None

    def _open(self, tag: str, attrs: dict[str, str], start: int, *, void: bool) -> None:
        if tag in _BLOCK_TAGS:
            self._flush_span()
        path = self._path_for(tag)

        if tag == "table":
            self._table_ordinal += 1
            self._table_stack.append(
                _TableBuilder(
                    table_id=f"{self._member}#t{self._table_ordinal}",
                    start=start,
                    path=path,
                    parent_table_id=self._table_stack[-1].table_id if self._table_stack else "",
                    depth=len(self._table_stack),
                )
            )
        elif self._table_stack:
            table = self._table_stack[-1]
            if tag == "tr":
                self._close_cell(table, start)
                table.rows.append([])
            elif tag in ("td", "th"):
                self._close_cell(table, start)
                if not table.rows:
                    # A cell outside any row. Filings do this; a browser invents a row, and so does
                    # this walk, rather than discarding the cell.
                    table.rows.append([])
                    self.findings.append(
                        f"{table.table_id}: a cell appeared outside any tr and was placed in an "
                        "invented first row, as a browser would render it"
                    )
                table.current_cell = _CellBuilder(
                    is_header=tag == "th",
                    row_span=_positive_int(attrs.get("rowspan")),
                    column_span=_positive_int(attrs.get("colspan")),
                    start=start,
                )
                table.rows[-1].append(table.current_cell)

        if void or tag in _VOID_TAGS:
            return
        self._stack.append(_Frame(tag=tag, path=path, hidden=self._hidden_reason_for(tag, attrs)))

    @staticmethod
    def _close_cell(table: _TableBuilder, end: int) -> None:
        if table.current_cell is not None:
            table.current_cell.end = end
            table.current_cell = None

    def _close(self, tag: str, end: int) -> None:
        if tag in _VOID_TAGS:
            return
        depth = None
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].tag == tag:
                depth = index
                break
        if depth is None:
            # An end tag matching nothing open. Ignored, exactly as a browser ignores it.
            return
        if tag in _BLOCK_TAGS:
            self._flush_span()
        if self._table_stack:
            table = self._table_stack[-1]
            if tag in ("td", "th"):
                self._close_cell(table, end)
            elif tag == "table":
                self._close_cell(table, end)
                self._finish_table(end)
        del self._stack[depth:]

    def _finish_table(self, end: int) -> None:
        builder = self._table_stack.pop()
        builder.end = end
        self._tables.append(_build_table(builder, self._text, self._member))

    # --- the walk --------------------------------------------------------------------------

    def run(self, events: list[tuple[int, str, str, dict[str, str], str]]) -> None:
        total = len(self._text)
        for position, (offset, kind, tag, attrs, data) in enumerate(events):
            end = events[position + 1][0] if position + 1 < len(events) else total
            end = max(end, offset)
            if kind == "data":
                if data:
                    self._run.append((offset, end, data))
                    # Text inside a nested table is inside its ancestor cells too, exactly as a
                    # browser renders it. Appending only to the innermost cell silently drops
                    # everything an outer cell says around a nested table.
                    for table in self._table_stack:
                        if table.current_cell is not None:
                            table.current_cell.fragments.append(data)
            elif kind == "start":
                self._open(tag, attrs, offset, void=False)
            elif kind == "startend":
                self._open(tag, attrs, offset, void=True)
            elif kind == "end":
                self._close(tag, end)
            # `other` — a comment, a doctype or a processing instruction — deliberately does NOT
            # break a span. A browser removes it and renders the text either side contiguously.
        self._flush_span()
        while self._table_stack:
            self.findings.append(
                f"{self._table_stack[-1].table_id}: the table element was never closed; its range "
                "runs to the end of the member"
            )
            self._finish_table(total)

    def results(self) -> tuple[tuple[TextSpan, ...], tuple[TableElement, ...]]:
        return tuple(self._spans), tuple(sorted(self._tables, key=lambda t: t.start))


def _positive_int(value: str | None, default: int = 1) -> int:
    """A span attribute, or the default. A filing that writes `rowspan="0"` gets the default."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _build_table(builder: _TableBuilder, text: str, member: str) -> TableElement:
    """Resolve a table's cells onto a grid, applying row and column spans as a browser would."""
    occupied: set[tuple[int, int]] = set()
    cells: list[TableCell] = []
    max_columns = 0
    for row_index, row in enumerate(builder.rows):
        column = 0
        for cell in row:
            while (row_index, column) in occupied:
                column += 1
            for row_offset in range(cell.row_span):
                for column_offset in range(cell.column_span):
                    occupied.add((row_index + row_offset, column + column_offset))
            cells.append(
                TableCell(
                    row_index=row_index,
                    column_index=column,
                    row_span=cell.row_span,
                    column_span=cell.column_span,
                    is_header=cell.is_header,
                    text=normalize_text("".join(cell.fragments)),
                    start=cell.start,
                    end=cell.end or cell.start,
                )
            )
            column += cell.column_span
            max_columns = max(max_columns, column)
    source = text[builder.start : builder.end]
    return TableElement(
        table_id=builder.table_id,
        member=member,
        start=builder.start,
        end=builder.end,
        element_path=builder.path,
        parent_table_id=builder.parent_table_id,
        nesting_depth=builder.depth,
        row_count=len(builder.rows),
        max_columns=max_columns,
        cell_count=len(cells),
        sha256=sha256_text(source),
        cells=tuple(cells),
    )


def walk_markup(
    text: str, *, member: str
) -> tuple[tuple[TextSpan, ...], tuple[TableElement, ...], tuple[str, ...]]:
    """Inventory one markup member: its text spans, its table elements, and any finding."""
    if not _ANY_TAG.search(text):
        raise MarkupUnreadableError(
            f"{member!r} carries no markup construct at all, so walking it as markup would report "
            "zero spans and zero tables for a document that may well have content"
        )
    walker = _Walker(text)
    walker.feed(text)
    walker.close()
    inventory = _Inventory(text, member)
    inventory.run(walker.events)
    spans, tables = inventory.results()
    return spans, tables, tuple(inventory.findings)


def plain_text_spans(text: str, *, member: str) -> tuple[TextSpan, ...]:
    """Spans for a member that is plain text: one span per maximal run of non-blank lines.

    A pre-2001 complete submission has no markup to walk. Its rendered line structure IS its
    structure, so a run of non-blank lines is the closest transport-level analogue of a block, and
    it is derived from line breaks rather than from anything about what the lines say.
    """
    spans: list[TextSpan] = []
    ordinal = 0
    start: int | None = None
    cursor = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            if start is None:
                start = cursor
        elif start is not None:
            ordinal += 1
            spans.append(_line_span(text, member, ordinal, start, cursor))
            start = None
        cursor += len(line)
    if start is not None:
        ordinal += 1
        spans.append(_line_span(text, member, ordinal, start, len(text)))
    return tuple(spans)


def _line_span(text: str, member: str, ordinal: int, start: int, end: int) -> TextSpan:
    original = text[start:end]
    return TextSpan(
        span_id=f"{member}#s{ordinal}",
        member=member,
        start=start,
        end=end,
        original_text=original,
        normalized_text=normalize_text(original),
        hidden_reason=HiddenReason.VISIBLE,
        element_path="",
        parent_element="",
        table_id="",
        duplicate_of="",
    )
