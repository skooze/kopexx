"""Measuring one filing's preserved bytes, and never saying a word about what they mean.

WHAT THESE TESTS ARE REALLY ABOUT. Not that a walker returns dataclasses; that is arithmetic. The
subject is the DENOMINATOR. Phase 2.1 could report that 352 of 364 model-emitted references
resolved and could not report what fraction of the filing that was, because a region no model ever
cited never entered the count. This package is the count, and a denominator that is wrong in a
plausible direction is worse than no denominator at all.

    a span ends at a BLOCK boundary and survives an INLINE one
    an offset is the SOURCE's, so text[start:end] is the filed bytes including every escape
    markup that hides content marks it hidden and never deletes it
    a grid position is the position a browser would render, after rowspan and colspan
    malformed markup is a filing, not a failure, and nothing here raises over it
    an image header is READ, never decoded, and an unreadable one answers None rather than a guess
    a duplicate is a byte observation, and both copies survive being called one

NOT ONE ASSERTION IN THIS FILE IS ABOUT MEANING. No test claims a span is a risk factor, a table is
a financial statement or an image is a chart. `packages/filing_acquisition/inventory.py` was deleted
for making judgements of exactly that kind (ADR-0017), and a test suite that asked for them would
put the judgement back one green run at a time.
"""

from __future__ import annotations

import pytest

from packages.source_inventory import (
    NOT_VISIBLE,
    FilingInventory,
    HiddenReason,
    MarkupUnreadableError,
    build_inventory,
    dimensions,
    media_type,
    normalize_text,
    plain_text_spans,
    walk_markup,
)
from packages.source_transport import MemberDisposition, SourceMember, SourceSet

MEMBER = "primary.htm"


# --- span boundaries ------------------------------------------------------------------------------


def test_an_inline_element_does_not_break_a_span_and_a_block_element_does() -> None:
    """MUTATION PROOF, AND THE ONE THE WHOLE DENOMINATOR RESTS ON.

    Each half alone is passed by a broken rule. Assert only the inline half and a walker that
    treats NO element as a boundary passes; assert only the block half and a walker that treats
    EVERY element as a boundary passes. The second is the live failure mode: inline XBRL shreds one
    rendered sentence across `span` and `ix:nonFraction`, and a per-element boundary turns ordinary
    prose into thousands of two-character fragments whose coverage percentage means nothing.
    """
    inline, _, _ = walk_markup(
        "<html><body><p>one <span>two</span> three</p></body></html>", member=MEMBER
    )
    assert [s.normalized_text for s in inline] == ["one two three"]

    block, _, _ = walk_markup(
        "<html><body><p>one</p><p>two</p><p>three</p></body></html>", member=MEMBER
    )
    assert [s.normalized_text for s in block] == ["one", "two", "three"]


def test_a_line_break_ends_a_span_even_though_br_is_an_inline_element() -> None:
    """`br` is inline in the content model and is a rendered line break, so it is a boundary."""
    spans, _, _ = walk_markup("<html><body><p>one<br>two</p></body></html>", member=MEMBER)
    assert [s.normalized_text for s in spans] == ["one", "two"]


def test_a_comment_between_two_words_neither_breaks_the_span_nor_enters_its_text() -> None:
    """A browser removes the comment and renders the text either side contiguously.

    The two halves are separate rules. The range covers the comment because that is the source
    slice a review UI highlights; the text does not, because taking the text from the slice would
    put `<!-- note -->` into a span reported as visible prose.
    """
    source = "<html><body><p>one <!-- note --> two</p></body></html>"
    spans, _, _ = walk_markup(source, member=MEMBER)
    assert [s.normalized_text for s in spans] == ["one two"]
    assert "<!-- note -->" in source[spans[0].start : spans[0].end]


def test_a_span_records_the_element_path_and_parent_it_was_flushed_under() -> None:
    spans, _, _ = walk_markup(
        "<html><body><div><p>first</p><p>second</p></div></body></html>", member=MEMBER
    )
    assert [s.element_path for s in spans] == [
        "html[1]/body[1]/div[1]/p[1]",
        "html[1]/body[1]/div[1]/p[2]",
    ]
    assert {s.parent_element for s in spans} == {"p"}


def test_whitespace_only_character_data_produces_no_span_at_all() -> None:
    """An empty span would be a denominator entry nothing can ever cover."""
    spans, _, _ = walk_markup("<html><body><p>   </p><p>\n\t</p></body></html>", member=MEMBER)
    assert spans == ()


def test_normalize_text_collapses_whitespace_without_folding_case() -> None:
    """Case folding would make NOTE and note the same span, which is a judgement about content."""
    assert normalize_text("  a \n\t b  ") == "a b"
    assert normalize_text("NOTE") != normalize_text("note")


# --- offsets are the source's ---------------------------------------------------------------------


def test_every_span_offset_pair_slices_exactly_the_source_it_came_from() -> None:
    source = (
        "<html><head><title>Cover</title></head><body>"
        "<p>one <span>two</span> three</p>"
        "<table><tr><td>cell</td></tr></table>"
        "<p>tail</p></body></html>"
    )
    spans, tables, _ = walk_markup(source, member=MEMBER)
    assert spans, "the specimen must produce spans or the loop below asserts nothing"
    for span in spans:
        assert source[span.start : span.end] == span.original_text
        assert span.character_count == span.end - span.start
    for table in tables:
        assert source[table.start : table.end].startswith("<table")
        assert table.byte_length == table.end - table.start


def test_a_spans_range_bounds_the_raw_escape_while_its_text_carries_the_decoded_character() -> None:
    """MUTATION PROOF for the rule that an end comes from the NEXT event, not from len(data).

    Asserting only the decoded text passes on a walker that derives every end from the decoded
    length, because the text is decoded either way. The second assertion is the one that fails
    there: `AT&amp;T` is seven source characters and `AT&T` is four, so a length-derived end lands
    three characters short and a review UI highlights a plausible, wrong range.
    """
    source = "<html><body><p>AT&amp;T earned &#36;5</p></body></html>"
    spans, _, _ = walk_markup(source, member=MEMBER)
    span = spans[0]

    assert span.normalized_text == "AT&T earned $5"
    assert source[span.start : span.end] == "AT&amp;T earned &#36;5"
    assert span.character_count > len(span.normalized_text)


def test_a_void_element_inside_a_run_stays_inside_the_range_and_out_of_the_text() -> None:
    source = '<html><body><p>See <img src="e.gif"> for detail.</p></body></html>'
    spans, _, _ = walk_markup(source, member=MEMBER)
    assert spans[0].normalized_text == "See for detail."
    assert '<img src="e.gif">' in source[spans[0].start : spans[0].end]


# --- what the source's own markup hides -----------------------------------------------------------


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("<html><head><div>Concealed</div></head><body><p>Shown</p></body></html>",
         HiddenReason.DOCUMENT_HEAD),
        ("<html><head><title>Concealed</title></head><body><p>Shown</p></body></html>",
         HiddenReason.DOCUMENT_HEAD),
        ("<html><body><script>Concealed</script><p>Shown</p></body></html>",
         HiddenReason.NON_RENDERED_ELEMENT),
        ("<html><body><style>Concealed</style><p>Shown</p></body></html>",
         HiddenReason.NON_RENDERED_ELEMENT),
        ("<html><body><noscript><p>Concealed</p></noscript><p>Shown</p></body></html>",
         HiddenReason.NON_RENDERED_ELEMENT),
        ("<html><body><ix:hidden><p>Concealed</p></ix:hidden><p>Shown</p></body></html>",
         HiddenReason.IX_HIDDEN),
        ("<html><body><ix:header><p>Concealed</p></ix:header><p>Shown</p></body></html>",
         HiddenReason.IX_HIDDEN),
        ('<html><body><div style="display:none">Concealed</div><p>Shown</p></body></html>',
         HiddenReason.STYLE_SUPPRESSED),
        ('<html><body><div style="visibility: hidden">Concealed</div><p>Shown</p></body></html>',
         HiddenReason.STYLE_SUPPRESSED),
    ],
)  # fmt: skip
def test_each_way_the_source_hides_content_is_recorded_with_its_own_reason(
    markup: str, expected: HiddenReason
) -> None:
    """MUTATION PROOF. Every case carries a `Shown` span that must stay VISIBLE.

    Without it a walker that marked EVERYTHING hidden would pass all nine cases, and a coverage
    report computed from it would show a filing with no visible content and no failure.
    """
    spans, _, _ = walk_markup(markup, member=MEMBER)
    concealed = next(s for s in spans if s.normalized_text == "Concealed")
    shown = next(s for s in spans if s.normalized_text == "Shown")

    assert concealed.hidden_reason is expected
    assert concealed.visible is False
    assert expected in NOT_VISIBLE
    assert shown.hidden_reason is HiddenReason.VISIBLE
    assert shown.visible is True


def test_a_hidden_span_is_still_inventoried_and_is_only_excluded_from_the_visible_count() -> None:
    """Hiding is recorded, never acted on. Dropping the span would delete a filed source range."""
    inventory = _inventory_of(
        _member(
            filename=MEMBER,
            sha256="1" * 64,
            text="<html><head><title>Concealed</title></head><body><p>Shown</p></body></html>",
        )
    )
    assert [s.normalized_text for s in inventory.spans] == ["Concealed", "Shown"]
    assert [s.normalized_text for s in inventory.visible_spans] == ["Shown"]


def test_an_ancestors_hiding_reaches_a_descendant_that_declares_nothing_itself() -> None:
    spans, _, _ = walk_markup(
        '<html><body><div style="display:none"><p>Deep</p></div></body></html>', member=MEMBER
    )
    assert spans[0].hidden_reason is HiddenReason.STYLE_SUPPRESSED


def test_an_ordinary_style_attribute_hides_nothing() -> None:
    """The regex must not fire on `display: block` or on a colour, or a rendered filing vanishes."""
    spans, _, _ = walk_markup(
        '<html><body><div style="display: block; color: none">Shown</div></body></html>',
        member=MEMBER,
    )
    assert spans[0].visible is True


# --- table grids ----------------------------------------------------------------------------------


def test_a_row_spanning_cell_pushes_the_next_rows_first_cell_to_the_column_it_leaves_free() -> None:
    """MUTATION PROOF by control table. The two tables differ only by the rowspan attribute.

    A walker that ignored rowspan entirely places C at column 0 in both, which is what the control
    half catches; a walker that hard-coded an offset places it at column 1 in both, which is what
    the spanned half catches. A reviewer comparing a model's table to this grid is comparing
    positions, so a grid that is confidently wrong is worse than none.
    """
    spanned = '<table><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>'
    _, tables, _ = walk_markup(spanned, member=MEMBER)
    grid = {cell.text: (cell.row_index, cell.column_index) for cell in tables[0].cells}
    assert grid == {"A": (0, 0), "B": (0, 1), "C": (1, 1)}
    assert (tables[0].row_count, tables[0].max_columns, tables[0].cell_count) == (2, 2, 3)

    control = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>"
    _, control_tables, _ = walk_markup(control, member=MEMBER)
    control_grid = {c.text: (c.row_index, c.column_index) for c in control_tables[0].cells}
    assert control_grid["C"] == (1, 0)


def test_a_column_spanning_cell_widens_the_grid_and_the_next_row_starts_at_column_zero() -> None:
    source = '<table><tr><td colspan="3">W</td></tr><tr><td>a</td><td>b</td><td>c</td></tr></table>'
    _, tables, _ = walk_markup(source, member=MEMBER)
    table = tables[0]
    assert (table.row_count, table.max_columns, table.cell_count) == (2, 3, 4)
    assert [(c.text, c.column_index) for c in table.cells] == [
        ("W", 0),
        ("a", 0),
        ("b", 1),
        ("c", 2),
    ]


def test_a_th_is_recorded_as_the_element_it_was_without_asserting_it_means_a_header() -> None:
    _, tables, _ = walk_markup("<table><tr><th>H</th><td>V</td></tr></table>", member=MEMBER)
    assert [(c.text, c.is_header) for c in tables[0].cells] == [("H", True), ("V", False)]


def test_a_span_attribute_that_is_zero_or_not_a_number_falls_back_to_one() -> None:
    """`rowspan="0"` is legal HTML meaning "to the end of the group" and is not implemented here.

    Treating it as 0 would mark no grid cell occupied and silently overlay the next cell on top of
    this one. One is the conservative reading: it never moves a cell somewhere nobody claimed.
    """
    source = '<table><tr><td rowspan="0" colspan="not a number">A</td><td>B</td></tr></table>'
    _, tables, _ = walk_markup(source, member=MEMBER)
    assert [(c.row_span, c.column_span, c.column_index) for c in tables[0].cells] == [
        (1, 1, 0),
        (1, 1, 1),
    ]


def test_a_cell_outside_any_row_is_placed_in_an_invented_row_and_reported() -> None:
    """The cell is kept, exactly as a browser keeps it, and the fact that this walk had to guess
    the row structure is on the record rather than folded into a clean-looking grid."""
    _, tables, findings = walk_markup("<table><td>Orphan</td></table>", member=MEMBER)
    assert tables[0].row_count == 1
    assert [c.text for c in tables[0].cells] == ["Orphan"]
    assert len(findings) == 1
    assert "outside any tr" in findings[0]
    assert findings[0].startswith(f"{MEMBER}#t1")


def test_a_table_that_never_closes_runs_to_the_end_of_the_member_and_says_so() -> None:
    """MUTATION PROOF. Malformed markup is normal before 2005, so the table must survive AND the
    fact that its extent was inferred rather than read must be reported. A walker that discarded
    the unclosed table would pass a findings-only assertion; one that swallowed it silently would
    pass a table-only assertion."""
    source = "<div><table><tr><td>Never closed</td></tr><p>after</p>"
    _, tables, findings = walk_markup(source, member=MEMBER)
    assert len(tables) == 1
    assert tables[0].start == source.index("<table")
    assert tables[0].end == len(source)
    assert any("never closed" in finding for finding in findings)


def test_a_well_formed_table_produces_no_finding_at_all() -> None:
    """The negative control for the two findings above: a finding must mean something happened."""
    _, tables, findings = walk_markup("<table><tr><td>A</td></tr></table>", member=MEMBER)
    assert len(tables) == 1
    assert findings == ()


def test_a_table_whose_cells_carry_no_text_is_reported_empty_without_being_called_layout() -> None:
    """`is_empty` is a transport observation. Whether the table is a layout device is the model's
    judgement, and this record deliberately cannot express it."""
    _, tables, _ = walk_markup("<table><tr><td> </td><td></td></tr></table>", member=MEMBER)
    assert tables[0].is_empty is True
    assert tables[0].cell_count == 2

    _, filled, _ = walk_markup("<table><tr><td>1995</td></tr></table>", member=MEMBER)
    assert filled[0].is_empty is False


def test_a_span_inside_a_cell_records_the_table_it_sits_in() -> None:
    spans, tables, _ = walk_markup(
        "<html><body><p>outside</p><table><tr><td>inside</td></tr></table></body></html>",
        member=MEMBER,
    )
    by_text = {s.normalized_text: s.table_id for s in spans}
    assert by_text == {"outside": "", "inside": tables[0].table_id}


# --- nested tables --------------------------------------------------------------------------------


def test_a_nested_table_records_its_parent_and_its_depth() -> None:
    source = (
        "<table><tr><td>Outer before "
        "<table><tr><td>Inner cell</td></tr></table>"
        " outer after</td></tr></table>"
    )
    _, tables, _ = walk_markup(source, member=MEMBER)
    outer, inner = tables

    assert (outer.nesting_depth, outer.parent_table_id) == (0, "")
    assert (inner.nesting_depth, inner.parent_table_id) == (1, outer.table_id)
    assert inner.element_path.startswith(outer.element_path + "/")


def test_the_outer_cells_text_includes_the_nested_tables_text_as_a_browser_renders_it() -> None:
    """MUTATION PROOF for appending character data to EVERY open cell, not just the innermost.

    Asserting the inner cell alone passes on a walker that appends only to the innermost cell. The
    outer assertion is the one that fails there, and it fails by dropping `Outer before` and
    `outer after` — text the reader plainly sees — out of the enclosing cell.
    """
    source = (
        "<table><tr><td>Outer before "
        "<table><tr><td>Inner cell</td></tr></table>"
        " outer after</td></tr></table>"
    )
    _, tables, _ = walk_markup(source, member=MEMBER)
    outer, inner = tables

    assert outer.cells[0].text == "Outer before Inner cell outer after"
    assert inner.cells[0].text == "Inner cell"


def test_two_tables_at_the_same_level_are_siblings_rather_than_nested() -> None:
    source = "<body><table><tr><td>a</td></tr></table><table><tr><td>b</td></tr></table></body>"
    _, tables, _ = walk_markup(source, member=MEMBER)
    assert [t.nesting_depth for t in tables] == [0, 0]
    assert [t.parent_table_id for t in tables] == ["", ""]


def test_tables_are_returned_in_source_order() -> None:
    """A nested table finishes BEFORE its parent, so collection order is not document order and a
    reviewer reading down the list would see the inner table first."""
    source = (
        "<table><tr><td><table><tr><td>in</td></tr></table></td></tr></table>"
        "<table><tr><td>after</td></tr></table>"
    )
    _, tables, _ = walk_markup(source, member=MEMBER)
    assert [t.start for t in tables] == sorted(t.start for t in tables)


# --- malformed markup is a filing, not a failure --------------------------------------------------


def test_an_end_tag_matching_nothing_open_is_ignored_and_nothing_raises() -> None:
    """MUTATION PROOF. Not raising is half the rule; the other half is that the walk keeps its
    place. A walker that swallowed the stray tag by unwinding one frame would still not raise, and
    the second span's path would move out from under `body`."""
    spans, _, findings = walk_markup(
        "<html><body><p>first</p></i></b><p>second</p></body></html>", member=MEMBER
    )
    assert [s.normalized_text for s in spans] == ["first", "second"]
    assert [s.element_path for s in spans] == [
        "html[1]/body[1]/p[1]",
        "html[1]/body[1]/p[2]",
    ]
    assert findings == ()


def test_an_end_tag_matching_a_lower_frame_closes_everything_above_it() -> None:
    """MUTATION PROOF by element path. `</div>` closes the div and the three unclosed elements
    inside it, so the following paragraph is a child of `body`.

    Asserting only that the text survives passes on a walker that never unwinds: the span is
    emitted either way. The path is what distinguishes them, and it is what the review UI uses to
    say where in the document a span sits.
    """
    spans, _, _ = walk_markup(
        "<html><body><div><b><i><p>inside</p></div><p>after</p></body></html>", member=MEMBER
    )
    assert [s.normalized_text for s in spans] == ["inside", "after"]
    assert spans[0].element_path == "html[1]/body[1]/div[1]/b[1]/i[1]/p[1]"
    assert spans[1].element_path == "html[1]/body[1]/p[1]"


def test_an_unclosed_void_element_never_corrupts_the_paths_after_it() -> None:
    """`img`, `br` and `hr` have no end tag. Pushing one on the stack nests everything after it."""
    spans, _, _ = walk_markup(
        '<html><body><img src="a.gif"><hr><p>after</p></body></html>', member=MEMBER
    )
    assert spans[0].element_path == "html[1]/body[1]/p[1]"


def test_an_end_tag_for_an_element_that_never_had_one_is_ignored() -> None:
    """`</br>` occurs in filed markup. Unwinding on it would close whatever else is open."""
    spans, _, _ = walk_markup("<body><p>one</p></br><p>two</p></body>", member=MEMBER)
    assert [s.element_path for s in spans] == ["body[1]/p[1]", "body[1]/p[2]"]


def test_a_self_closing_element_is_a_boundary_without_ever_entering_the_stack() -> None:
    """MUTATION PROOF. A self-closing BLOCK element ends a run — the first assertion — and must not
    be pushed, or every path after it is nested one level too deep, which the second catches."""
    spans, _, _ = walk_markup("<html><body>one<div/>two</body></html>", member=MEMBER)
    assert [s.normalized_text for s in spans] == ["one", "two"]
    assert [s.element_path for s in spans] == ["html[1]/body[1]", "html[1]/body[1]"]


def test_a_self_closing_inline_xbrl_element_does_not_break_the_run_around_it() -> None:
    source = '<html><body><p>one <ix:nonFraction contextRef="c"/> two</p></body></html>'
    spans, _, _ = walk_markup(source, member=MEMBER)
    assert [s.normalized_text for s in spans] == ["one two"]


def test_a_doctype_a_processing_instruction_and_a_marked_section_are_all_walked() -> None:
    """None of the three is character data, so none of them may break a run or enter a span's text.

    A browser removes each one and renders what is either side contiguously; a walk that treated
    `<![CDATA[...]]>` as a boundary would split one rendered sentence into two denominator entries.
    """
    source = (
        "<!DOCTYPE html><?xml version='1.0'?><html><body><p>a<![CDATA[raw]]>b</p></body></html>"
    )
    spans, _, findings = walk_markup(source, member=MEMBER)
    assert [s.normalized_text for s in spans] == ["ab"]
    assert findings == ()


def test_walking_a_document_with_no_markup_construct_raises_and_names_the_member() -> None:
    """Returning an empty inventory here is indistinguishable from a document with no content, and
    a filing whose tables silently became zero is the false negative this package exists against."""
    with pytest.raises(MarkupUnreadableError, match="carries no markup construct"):
        walk_markup("Plain prose with no angle bracket anywhere.", member="bare.txt")
    with pytest.raises(MarkupUnreadableError, match="bare.txt"):
        walk_markup("", member="bare.txt")


def test_a_single_element_is_enough_for_a_document_to_be_walkable() -> None:
    """The negative control for the refusal above: the guard must not reject real markup."""
    spans, _, _ = walk_markup("<p>only element</p>", member=MEMBER)
    assert [s.normalized_text for s in spans] == ["only element"]


# --- plain text members ---------------------------------------------------------------------------


def test_plain_text_spans_split_on_blank_lines_with_exact_offsets() -> None:
    source = "first line\nsecond line\n\n\nthird block\n"
    spans = plain_text_spans(source, member="notes.txt")

    assert [s.normalized_text for s in spans] == ["first line second line", "third block"]
    for span in spans:
        assert source[span.start : span.end] == span.original_text
    assert source[spans[0].start : spans[0].end] == "first line\nsecond line\n"
    assert source[spans[1].start : spans[1].end] == "third block\n"
    assert [s.span_id for s in spans] == ["notes.txt#s1", "notes.txt#s2"]


def test_a_plain_text_block_reaching_the_end_without_a_newline_is_still_a_span() -> None:
    source = "opening block\n\nclosing block with no newline"
    spans = plain_text_spans(source, member="notes.txt")
    assert len(spans) == 2
    assert spans[1].end == len(source)
    assert source[spans[1].start : spans[1].end] == "closing block with no newline"


def test_plain_text_carries_no_element_path_no_table_and_no_hiding() -> None:
    """There is no markup to derive any of them from, and a plausible default would be invented."""
    spans = plain_text_spans("a line\n", member="notes.txt")
    assert spans[0].element_path == ""
    assert spans[0].parent_element == ""
    assert spans[0].table_id == ""
    assert spans[0].hidden_reason is HiddenReason.VISIBLE


def test_plain_text_with_no_content_produces_no_span() -> None:
    assert plain_text_spans("", member="notes.txt") == ()
    assert plain_text_spans("\n\n  \n", member="notes.txt") == ()


# --- image headers --------------------------------------------------------------------------------
#
# Every specimen below is built from the format's own layout rather than checked in as a file. A
# checked-in binary cannot be read in review, and the thing under test IS the byte layout.


def _png(width: int, height: int) -> bytes:
    """Eight signature bytes, a chunk length, the mandatory first-chunk type, then two big-endian
    32-bit integers."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def _gif(width: int, height: int, signature: bytes = b"GIF89a") -> bytes:
    """A six-byte header, then a logical screen descriptor carrying LITTLE-endian dimensions."""
    return signature + width.to_bytes(2, "little") + height.to_bytes(2, "little")


def _jpeg_segment(marker: int, payload: bytes) -> bytes:
    """A JPEG segment. Its declared length counts the two length bytes themselves."""
    return bytes((0xFF, marker)) + (len(payload) + 2).to_bytes(2, "big") + payload


def _jpeg(width: int, height: int, *, before: bytes = b"") -> bytes:
    """A start-of-image, arbitrary preceding segments, then a start-of-frame carrying the size.

    `before` is the point of this helper. A JPEG's dimensions sit at no fixed offset: the frame
    header follows however many application and table segments the encoder wrote.
    """
    frame = _jpeg_segment(
        0xC0,
        b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03"
        + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01",
    )
    return b"\xff\xd8" + before + frame


#: A JFIF application segment, the one that in practice sits between the SOI and the frame header.
APP0 = _jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")

#: A Huffman table segment. Its marker, 0xC4, is inside the 0xC0-0xCF range and is NOT a frame
#: header. Its bytes are chosen so that misreading it as one yields 8888x9999 — a wrong answer that
#: is indistinguishable from a measured one downstream.
HUFFMAN_TABLE = _jpeg_segment(
    0xC4, b"\x00" + (9999).to_bytes(2, "big") + (8888).to_bytes(2, "big") + b"\x00" * 8
)


def test_a_png_header_gives_its_dimensions() -> None:
    assert dimensions(_png(640, 480)) == (640, 480)


@pytest.mark.parametrize("signature", [b"GIF87a", b"GIF89a"])
def test_both_gif_signatures_give_their_little_endian_dimensions(signature: bytes) -> None:
    """MUTATION PROOF against a big-endian read. 24 and 36 are asymmetric and both are wider than
    one byte, so a byte-order mistake produces 6144 and 9216 rather than the same numbers back."""
    assert dimensions(_gif(24, 36, signature)) == (24, 36)


def test_a_jpeg_frame_header_is_reached_by_walking_the_segments_that_precede_it() -> None:
    """MUTATION PROOF for the segment walk. The three specimens carry the same frame at three
    different offsets, so a fixed-offset read cannot satisfy all of them — and a fixed offset is
    precisely what works on the file a developer happened to test and fails on the next one.
    """
    assert dimensions(_jpeg(200, 100)) == (200, 100)
    assert dimensions(_jpeg(200, 100, before=APP0)) == (200, 100)
    assert dimensions(_jpeg(200, 100, before=APP0 + APP0)) == (200, 100)


def test_a_huffman_table_segment_is_stepped_over_rather_than_read_as_a_frame_header() -> None:
    """0xC4, 0xC8 and 0xCC sit inside the frame-marker range and are not frames. Reading one
    produces a confident wrong answer, which this specimen makes visible as 8888x9999."""
    assert dimensions(_jpeg(200, 100, before=APP0 + HUFFMAN_TABLE)) == (200, 100)


def test_padding_between_two_jpeg_segments_is_stepped_over_one_byte_at_a_time() -> None:
    """The walk resynchronises on the next marker instead of giving up at the first byte that is
    not one. An encoder that pads between segments is not a malformed file."""
    assert dimensions(_jpeg(200, 100, before=APP0 + b"\x00\x00")) == (200, 100)


def test_a_jpeg_marker_carrying_no_length_advances_two_bytes_rather_than_a_read_one() -> None:
    """A restart marker and a second start-of-image are two bytes with no segment behind them.
    Reading the two bytes after one as a length walks the cursor into the middle of the file."""
    assert dimensions(_jpeg(200, 100, before=b"\xff\xd0" + b"\xff\xd8" + APP0)) == (200, 100)


def test_a_jpeg_segment_declaring_an_impossible_length_reports_no_dimensions() -> None:
    """A declared length below two cannot include its own two length bytes. Advancing by it would
    loop forever or read a size out of image data."""
    assert dimensions(_jpeg(200, 100, before=b"\xff\xe1\x00\x00")) == (None, None)


def test_a_jpeg_that_ends_before_any_frame_header_reports_no_dimensions() -> None:
    assert dimensions(b"\xff\xd8" + APP0 + b"\xff\xd9" + b"\x00\x00\x00\x00") == (None, None)
    # A segment whose declared length runs past the end of the file: the cursor leaves the data
    # and the walk ends without a frame, rather than reading a size from beyond it.
    assert dimensions(b"\xff\xd8\xff\xe0" + (100).to_bytes(2, "big") + b"\x00" * 4) == (None, None)


def test_a_truncated_header_reports_no_dimensions_rather_than_a_partial_read() -> None:
    assert dimensions(_png(640, 480)[:20]) == (None, None)
    assert dimensions(_gif(24, 36)[:8]) == (None, None)
    assert dimensions(_jpeg(200, 100)[:8]) == (None, None)


def test_a_png_whose_first_chunk_is_not_ihdr_reports_no_dimensions() -> None:
    corrupt = bytearray(_png(640, 480))
    corrupt[12:16] = b"iTXt"
    assert dimensions(bytes(corrupt)) == (None, None)


def test_an_unrecognised_format_reports_no_dimensions_and_never_a_plausible_default() -> None:
    """MUTATION PROOF against a fabricated default. A fabricated dimension is indistinguishable
    from a measured one in every report downstream, so the honest answer is that it is not
    mechanically obtainable — and the recognised formats must still answer, or None means nothing.
    """
    assert dimensions(b"BM" + b"\x00" * 60) == (None, None)
    assert dimensions(b"") == (None, None)
    assert dimensions(b"%PDF-1.4\n") == (None, None)
    assert dimensions(_png(1, 1)) == (1, 1)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_png(1, 1), "image/png"),
        (_jpeg(1, 1), "image/jpeg"),
        (_gif(1, 1, b"GIF87a"), "image/gif"),
        (_gif(1, 1, b"GIF89a"), "image/gif"),
        (b"BM" + b"\x00" * 60, "application/octet-stream"),
        (b"", "application/octet-stream"),
    ],
)
def test_media_type_is_decided_by_the_signature_the_bytes_actually_carry(
    data: bytes, expected: str
) -> None:
    assert media_type(data) == expected


# --- a synthetic filing, built from real transport records ----------------------------------------
#
# The members are constructed directly rather than through `assemble_source_set`, which needs a
# filing inventory and a fetcher. Nothing here reaches a network, a credential or the filesystem.
#
# THE BYTES ARE INVENTED AND THE IDENTIFIERS ARE SHAPED LIKE EDGAR'S WITHOUT DESCRIBING ANY FILING.
# One issuer is a fixture and never a specification (ADR-0016); this one is not even an issuer.

PRIMARY_HTML = (
    "<html><body>"
    "<p>SPECIMEN FILER INCORPORATED</p>"
    '<table><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>'
    '<p>See <img src="exhibit.gif"> and <img src="charts/exhibit.gif?v=2">.</p>'
    '<p>Filed elsewhere <img src="nowhere.gif"></p>'
    "<p>SPECIMEN FILER INCORPORATED</p>"
    "</body></html>"
)
EXHIBIT_HTML = (
    "<html><body><p>SPECIMEN FILER INCORPORATED</p>"
    "<table><tr><th>Year</th><td>1995</td></tr></table></body></html>"
)
NOTES_TEXT = "First block line one\nline two\n\nSecond block\n"
EXHIBIT_GIF = _gif(24, 36)


def _member(
    *,
    filename: str,
    sha256: str,
    text: str | None = None,
    image_bytes: bytes | None = None,
    disposition: MemberDisposition = MemberDisposition.PARSER_INPUT_TEXT,
    image_format: str | None = None,
    sequence: int = 1,
) -> SourceMember:
    return SourceMember(
        sequence=sequence,
        declared_type="10-K405",
        description="",
        filename=filename,
        disposition=disposition,
        disposition_evidence="supplied by the test",
        sha256=sha256,
        byte_count=len(text.encode()) if text else len(image_bytes or b""),
        source_url=f"https://example.invalid/{filename}",
        separately_addressable=True,
        reused=False,
        encoding="utf-8" if text is not None else None,
        image_format=image_format,
        text=text,
        image_bytes=image_bytes,
    )


def _source_set(*members: SourceMember) -> SourceSet:
    return SourceSet(
        cik="0009999999",
        accession="0009999999-96-000001",
        form_as_filed="10-K405",
        filing_date="1996-03-28",
        report_period=None,
        issuer_label="Issuer Inc.",
        transport_era="early_html",
        members=members,
        declared_document_count=len(members),
        listed_document_count=len(members),
        members_separately_addressable=True,
    )


def _inventory_of(*members: SourceMember) -> FilingInventory:
    return build_inventory(_source_set(*members))


def _filing() -> FilingInventory:
    """One filing carrying every case `build_inventory` distinguishes between."""
    return _inventory_of(
        _member(filename="primary.htm", sha256="1" * 64, text=PRIMARY_HTML),
        _member(filename="exhibit.htm", sha256="2" * 64, text=EXHIBIT_HTML, sequence=2),
        # The same bytes filed a second time under a second name. Both copies stay.
        _member(filename="copy.htm", sha256="2" * 64, text=EXHIBIT_HTML, sequence=3),
        _member(
            filename="exhibit.gif",
            sha256="3" * 64,
            image_bytes=EXHIBIT_GIF,
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            image_format="gif",
            sequence=4,
        ),
        _member(
            filename="linkbase.xml",
            sha256="4" * 64,
            text="<link:linkbase/>",
            disposition=MemberDisposition.MACHINE_ONLY,
            sequence=5,
        ),
        _member(filename="notes.txt", sha256="5" * 64, text=NOTES_TEXT, sequence=6),
    )


def test_the_inventory_carries_the_filings_identity_from_the_source_set_it_measured() -> None:
    """The source-set hash, not the accession. A member fetched later or dispositioned differently
    is a different set from the same accession, and a denominator computed against one filing and
    reported against another is precisely, confidently wrong."""
    source_set = _source_set(_member(filename="a.htm", sha256="1" * 64, text="<p>x</p>"))
    inventory = build_inventory(source_set)

    assert inventory.cik == "0009999999"
    assert inventory.accession == "0009999999-96-000001"
    assert inventory.form_as_filed == "10-K405"
    assert inventory.filing_date == "1996-03-28"
    assert inventory.report_period is None
    assert inventory.source_set_sha256 == source_set.source_set_id


def test_every_filed_member_gets_a_record_whatever_its_transport_role_is() -> None:
    inventory = _filing()
    assert [m.member for m in inventory.members] == [
        "primary.htm",
        "exhibit.htm",
        "copy.htm",
        "exhibit.gif",
        "linkbase.xml",
        "notes.txt",
    ]


def test_only_the_members_whose_content_reaches_the_model_carry_spans_and_tables() -> None:
    """MUTATION PROOF. A machine-only linkbase is inventoried as a member and contributes nothing
    to the denominator, because no model was ever sent it and counting a document nobody saw as
    uncovered content makes complete coverage unreachable by construction.

    The second half is what stops the rule being satisfied by counting nothing anywhere.
    """
    inventory = _filing()
    linkbase = next(m for m in inventory.members if m.member == "linkbase.xml")

    assert linkbase.transport_role == MemberDisposition.MACHINE_ONLY.value
    assert linkbase.human_readable is False
    assert (linkbase.span_count, linkbase.table_count) == (0, 0)
    assert inventory.spans_for("linkbase.xml") == ()

    primary = next(m for m in inventory.members if m.member == "primary.htm")
    assert primary.human_readable is True
    assert (primary.span_count, primary.table_count) == (7, 1)


def test_a_member_record_keeps_the_declared_type_and_the_transport_role_apart() -> None:
    """`declared_type` is what the FILER wrote; `transport_role` is what the bytes were found to be.
    Collapsing them is how a declared label starts being treated as a verified fact."""
    inventory = _filing()
    primary = next(m for m in inventory.members if m.member == "primary.htm")

    assert primary.declared_type == "10-K405"
    assert primary.transport_role == MemberDisposition.PARSER_INPUT_TEXT.value
    assert primary.character_count == len(PRIMARY_HTML)
    assert primary.sha256 == "1" * 64


def test_a_member_media_type_follows_its_extension_and_then_its_content() -> None:
    inventory = _filing()
    by_member = {m.member: m.media_type for m in inventory.members}

    assert by_member["primary.htm"] == "text/html"
    assert by_member["exhibit.gif"] == "image/gif"
    # A `.txt` submission carrying elements is walked as markup, so the decision is by content;
    # this one carries none and stays plain.
    assert by_member["notes.txt"] == "text/plain"


def test_a_plain_text_member_is_split_into_line_blocks_and_has_no_tables() -> None:
    inventory = _filing()
    notes = next(m for m in inventory.members if m.member == "notes.txt")

    assert (notes.span_count, notes.table_count) == (2, 0)
    assert [s.normalized_text for s in inventory.spans_for("notes.txt")] == [
        "First block line one line two",
        "Second block",
    ]


def test_two_members_with_the_same_sha256_are_recorded_as_the_same_bytes_and_both_survive() -> None:
    """MUTATION PROOF, and the defect it guards is on the record. The deleted accession classifier
    ruled a courtesy PDF duplicated the primary document and SUPPRESSED a filed source range on
    that judgement (ADR-0017). Marking without dropping is the whole distinction: the first
    assertion proves the observation is made, the last proves nothing was removed for it.
    """
    inventory = _filing()
    by_member = {m.member: m.duplicate_of for m in inventory.members}

    assert by_member["copy.htm"] == "exhibit.htm"
    assert by_member["exhibit.htm"] == ""
    assert by_member["primary.htm"] == ""
    assert len(inventory.members) == 6
    assert inventory.spans_for("copy.htm") != ()


def test_a_member_with_no_filename_is_labelled_by_its_sequence_number() -> None:
    """A pre-2001 member inside a complete submission has no individual name. An empty label would
    collide with every other unnamed member in the duplicate table."""
    inventory = _inventory_of(_member(filename="", sha256="1" * 64, text="<p>x</p>", sequence=7))
    assert inventory.members[0].member == "sequence-7"


def test_a_repeated_normalised_text_points_at_the_first_span_that_carried_it() -> None:
    """MUTATION PROOF. A page header repeated on forty rendered pages is forty spans of identical
    characters; marking the repeats keeps the denominator honest without deleting anything.

    Asserting only that the repeats are marked passes on an implementation that marks EVERYTHING,
    including the original — and then no span is the one the repeats point at.
    """
    inventory = _filing()
    repeated = [s for s in inventory.spans if s.normalized_text.startswith("SPECIMEN FILER")]

    assert len(repeated) == 4
    assert repeated[0].duplicate_of == ""
    assert repeated[0].mechanically_duplicate is False
    assert [s.duplicate_of for s in repeated[1:]] == [repeated[0].span_id] * 3
    assert all(s.mechanically_duplicate for s in repeated[1:])


def test_duplicate_marking_crosses_member_boundaries() -> None:
    """The repeat is in `exhibit.htm` and the original is in `primary.htm`. Marking per member
    would report the same forty page headers once per document."""
    inventory = _filing()
    exhibit_header = inventory.spans_for("exhibit.htm")[0]
    assert exhibit_header.duplicate_of.startswith("primary.htm#")


def test_a_byte_identical_table_points_at_the_first_element_that_carried_those_bytes() -> None:
    inventory = _filing()
    by_table = {t.table_id: t.duplicate_of for t in inventory.tables}

    assert by_table["copy.htm#t1"] == "exhibit.htm#t1"
    assert by_table["exhibit.htm#t1"] == ""
    assert by_table["primary.htm#t1"] == ""
    assert inventory.table("copy.htm#t1") is not None, "the duplicate was dropped, not marked"


def test_two_tables_are_only_duplicates_when_their_source_slices_are_identical() -> None:
    """The negative control. Tables that render alike but were filed differently are two tables,
    and deciding otherwise would be a judgement about what they mean."""
    inventory = _inventory_of(
        _member(
            filename="a.htm",
            sha256="1" * 64,
            text="<table><tr><td>1995</td></tr></table><table><tr><td>1994</td></tr></table>",
        )
    )
    assert [t.duplicate_of for t in inventory.tables] == ["", ""]


def test_an_image_records_what_its_own_header_says_and_where_the_markup_points_at_it() -> None:
    """MUTATION PROOF on the reference offsets. `nowhere.gif` is referenced by the same markup and
    is not a member of this filing, so an implementation that recorded every `src` would find three
    references instead of two — and the offsets prove each one locates a real attribute rather than
    an arbitrary position that happens to be in range.
    """
    inventory = _filing()
    assert len(inventory.images) == 1
    image = inventory.images[0]

    assert image.filename == "exhibit.gif"
    assert image.media_type == "image/gif"
    assert (image.width, image.height) == (24, 36)
    assert image.byte_count == len(EXHIBIT_GIF)

    assert [member for member, _ in image.referenced_at] == ["primary.htm", "primary.htm"]
    assert PRIMARY_HTML[image.referenced_at[0][1] :].startswith('src="exhibit.gif"')
    assert PRIMARY_HTML[image.referenced_at[1][1] :].startswith('src="charts/exhibit.gif?v=2"')


def test_an_image_whose_bytes_were_not_preserved_reports_no_dimensions() -> None:
    """A member dispositioned as an image whose bytes are not in hand is still inventoried. The
    dimensions are None because they were never read, not because the image has none."""
    inventory = _inventory_of(
        _member(
            filename="logo.jpg",
            sha256="7" * 64,
            disposition=MemberDisposition.PARSER_INPUT_IMAGE,
            image_format="jpeg",
        )
    )
    image = inventory.images[0]
    assert image.media_type == "image/jpeg"
    assert (image.width, image.height) == (None, None)
    assert image.referenced_at == ()


def test_a_member_declared_as_markup_that_carries_none_is_inventoried_with_the_reason() -> None:
    """MUTATION PROOF. Raising would abandon the whole filing's inventory over one member, and
    falling back silently would hide that a document nobody can walk was counted as prose. Both
    halves are asserted: the spans exist AND the reason is on the record.
    """
    inventory = _inventory_of(
        _member(filename="bare.htm", sha256="8" * 64, text="No markup construct here at all.")
    )
    assert [s.normalized_text for s in inventory.spans] == ["No markup construct here at all."]
    assert len(inventory.findings) == 1
    assert inventory.findings[0].startswith("bare.htm:")
    assert "carries no markup construct" in inventory.findings[0]


def test_a_finding_raised_while_walking_one_member_reaches_the_filings_findings() -> None:
    inventory = _inventory_of(
        _member(filename="a.htm", sha256="1" * 64, text="<table><td>Orphan</td></table>")
    )
    assert any("outside any tr" in finding for finding in inventory.findings)


def test_a_filing_whose_members_all_walk_cleanly_reports_no_finding() -> None:
    """The negative control for the two above: a finding must mean something actually happened."""
    assert _filing().findings == ()


# --- the helpers a review UI and the completeness ledger call -------------------------------------


def test_spans_for_and_tables_for_return_only_the_named_members_own_units() -> None:
    inventory = _filing()

    assert {s.member for s in inventory.spans_for("exhibit.htm")} == {"exhibit.htm"}
    assert len(inventory.spans_for("exhibit.htm")) == 3
    assert [t.table_id for t in inventory.tables_for("primary.htm")] == ["primary.htm#t1"]
    assert inventory.spans_for("no-such-member.htm") == ()
    assert inventory.tables_for("no-such-member.htm") == ()


def test_a_lookup_answers_none_for_an_identifier_that_is_not_in_the_inventory() -> None:
    """MUTATION PROOF. A lookup that always answered None would satisfy the miss on its own, and a
    ledger built on it would report every model-cited table as unresolvable."""
    inventory = _filing()

    found = inventory.table("primary.htm#t1")
    assert found is not None and found.member == "primary.htm"
    assert inventory.table("primary.htm#t99") is None

    span = inventory.span("primary.htm#s1")
    assert span is not None and span.normalized_text.startswith("SPECIMEN FILER")
    assert inventory.span("primary.htm#s999") is None


def test_human_readable_members_excludes_images_and_machine_only_artifacts() -> None:
    inventory = _filing()
    assert [m.member for m in inventory.human_readable_members] == [
        "primary.htm",
        "exhibit.htm",
        "copy.htm",
        "notes.txt",
    ]


def test_visible_character_count_counts_only_the_spans_markup_does_not_hide() -> None:
    """MUTATION PROOF. The hidden span is deliberately far longer than the visible one, so a count
    that ignored hiding would be larger rather than merely different — and a coverage percentage
    computed against it would understate omission by most of the document.
    """
    inventory = _inventory_of(
        _member(
            filename="a.htm",
            sha256="1" * 64,
            text=(
                "<html><head><title>" + "concealed " * 40 + "</title></head>"
                "<body><p>Shown</p></body></html>"
            ),
        )
    )
    shown = next(s for s in inventory.spans if s.normalized_text == "Shown")

    assert inventory.visible_character_count == shown.character_count
    assert inventory.visible_character_count < sum(s.character_count for s in inventory.spans)
    assert len(inventory.visible_spans) == 1
    assert len(inventory.spans) == 2


def test_an_inventory_with_no_visible_span_counts_zero_characters_rather_than_failing() -> None:
    inventory = _inventory_of(
        _member(filename="a.htm", sha256="1" * 64, text="<html><body><p> </p></body></html>")
    )
    assert inventory.visible_spans == ()
    assert inventory.visible_character_count == 0


# --- the manifest ---------------------------------------------------------------------------------


def test_a_spans_manifest_entry_truncates_its_text_and_names_its_coordinate_system() -> None:
    """The manifest is a summary; the preserved member is authoritative and the offsets locate the
    full text in it. `character_count` stays the real length so a truncated excerpt can never be
    mistaken for the span itself."""
    spans, _, _ = walk_markup(
        "<html><body><p>" + ("word " * 200) + "</p></body></html>", member=MEMBER
    )
    mapping = spans[0].to_mapping()

    assert len(mapping["normalized_text"]) == 400
    assert mapping["character_count"] > 400
    assert mapping["offset_coordinate_system"] == "characters into the decoded preserved member"


def test_the_filing_manifest_states_that_nothing_in_it_is_a_semantic_judgement() -> None:
    """The note is load-bearing. Every consumer of this document — a review UI, a ledger, a person
    reading a run record — has to know that an element name is not a classification."""
    mapping = _filing().to_mapping()

    assert mapping["schema_version"] == "source-inventory-v1"
    assert "MEANS" in mapping["semantic_note"]
    assert mapping["member_count"] == 6
    assert mapping["human_readable_member_count"] == 4
    assert mapping["span_count"] == len(_filing().spans)
    assert mapping["image_count"] == 1
