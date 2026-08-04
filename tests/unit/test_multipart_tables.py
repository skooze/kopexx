"""Reading a structured table a model returned: structure carried, meaning never inferred.

WHY THERE IS ANYTHING TO TEST HERE AT ALL. `table_count` was ZERO in all seven Phase 2.1 proof
runs. Not one of the five candidates emitted a structured table from a financial filing, on either
the 1996 10-K405 or the 2025 10-Q/A, and no prompt in that phase asked for one — so what a model
will actually return is UNMEASURED. Every test below is written against that ignorance: two row
shapes are accepted because a contract accepting one would measure which shape the prompt happened
to suggest, a bare scalar is accepted, an unknown key survives, and a missing envelope key is a
finding rather than a refusal.

WHAT THESE TESTS MUST NEVER START ASSERTING. That a table has a header row. That its type is one of
a list. That a unit string is well formed. That a financial statement looks like anything in
particular. `rules.md` section 21 rule 2 forbids a universal filing taxonomy without explicit user
approval, and a table schema is the easiest place in this system to build one by accident, because
every financial filing really does have an income statement. The only questions asked below are
whether a table names itself, whether its cells declare a grid position, and whether a span is a
positive integer.

NARRATIVE REPETITION OF A NUMBER IS NOT A TABLE, WHICH IS WHY THE GRID IS THE SUBJECT. Phase 2.1's
candidates carried tabular material as node content, and the numeric validator confirmed those
figures occurred in the preserved bytes. That proves a number appears in the filing and says
nothing about which row, which column and which period it belonged to — and those three facts are
what a table IS. The counting tests below are therefore about the grid the cells describe, not
about the lists the model happened to write them in.
"""

from __future__ import annotations

from typing import Any

import pytest

from packages.multipart import (
    MAX_PART_IDENTIFIER_CHARACTERS,
    TABLE_ENVELOPE_KEYS,
    UnsafePartIdentifierError,
    read_table,
    read_tables,
    require_part_identifier,
    storage_token,
)

#: One table carrying every shape the reader distinguishes at once: a header block, two body rows
#: written the two different ways, a footer whose last cell spans wider than any row is long, a
#: cell the model could not resolve, and a separately declared unresolved cell.
COUNTED_TABLE: dict[str, Any] = {
    "table_id": "segment-information-1",
    "source_member": "aapl-20250628.htm",
    "header_rows": [["Segment", "2024", "2023"]],
    "rows": [
        ["Americas", "40,315", "37,670"],
        [{"text": "Europe"}, {"text": "", "unresolved": True}, {"text": "23,945"}],
    ],
    "footer_rows": [["Total", {"text": "65,245", "column_span": 3}]],
    "unresolved_cells": [{"why": "the figure is legible only in a filed image"}],
}


# --- a table has to name itself, and that is nearly all it has to do -----------------------------


def test_a_table_that_names_no_identifier_is_dropped_and_the_rest_of_the_part_survives() -> None:
    """A table with no identifier cannot be cited, compared, reviewed or linked to a source element.

    It is dropped here rather than raised, and the raw list is what validation reports the loss
    from. Raising would throw away a part whose other tables are fine — and the response was paid
    for, cannot be regenerated for free, and is the only evidence of what this model emits.
    """
    assert read_table({"title": "a table the model forgot to name"}) is None
    assert read_table("not a mapping at all") is None
    assert read_table(None) is None

    kept = read_tables(
        [
            {"title": "no identifier"},
            {"table_id": "t-1"},
            "a stray scalar in the tables list",
            {"table_id": "t-2"},
        ]
    )
    assert [table.table_id for table in kept] == ["t-1", "t-2"]


@pytest.mark.parametrize(
    "identifier",
    [
        pytest.param("x" * (MAX_PART_IDENTIFIER_CHARACTERS + 1), id="over-the-bound"),
        pytest.param("segment\x00table", id="control-character"),
    ],
)
def test_an_identifier_that_is_not_an_identifier_is_refused(identifier: str) -> None:
    """The two things a model-chosen name may never be: content, and a corruption of every log line.

    Everything else it might be — a space, punctuation, a non-Latin script, the filing's own
    numbering — is accepted exactly as returned, because the model names its own work. Refusal is
    reserved for the two cases where carrying the name would damage something downstream.
    """
    with pytest.raises(UnsafePartIdentifierError):
        read_table({"table_id": identifier, "rows": []})


def test_an_empty_identifier_is_dropped_by_the_reader_and_refused_by_the_guard() -> None:
    """The same defect gets two different responses, and both are correct for where they sit.

    A table naming nothing is a table the reader cannot use, so it is dropped as a finding. The
    guard beneath it still raises, because anything that reaches it has already claimed to be an
    identifier and silently accepting an empty one would let a nameless directory be created.
    """
    assert read_table({"table_id": "   ", "rows": []}) is None
    assert read_table({"table_id": "", "rows": []}) is None
    with pytest.raises(UnsafePartIdentifierError, match="empty"):
        require_part_identifier("   ")


def test_two_table_identifiers_that_sanitise_alike_still_get_different_storage_tokens() -> None:
    """The digest is not decoration: without it the second table would overwrite the first.

    `Table 3` and `table-3` sanitise to the same slug, and a token that was only the slug would
    make them one directory. The token is derived from the exact identifier the model returned, and
    the identifier itself is carried beside it untouched, so neither value has to stand in for the
    other.
    """
    first = read_table({"table_id": "Table 3", "rows": []})
    second = read_table({"table_id": "table-3", "rows": []})
    assert first is not None and second is not None
    assert first.storage_token == storage_token("Table 3")
    assert first.storage_token != second.storage_token
    assert first.table_id == "Table 3", "the model's own name is never replaced by the token"


# --- the grid, in whichever of the two shapes the model chose -------------------------------------


def test_a_row_written_as_a_list_takes_its_grid_position_from_the_order_it_was_written() -> None:
    """The implied shape, which is the one a model writing compactly will reach for.

    Position comes from order and nothing else, so a filing's simplest tables survive without the
    model having to number every cell. The row index is what makes this a grid rather than a bag of
    strings, and it is the fact that narrative repetition of a figure cannot carry.
    """
    table = read_table({"table_id": "t-1", "rows": [["Americas", "40,315"], ["Europe", "24,930"]]})
    assert table is not None
    assert [(c.row, c.column, c.text) for c in table.cells] == [
        (0, 0, "Americas"),
        (0, 1, "40,315"),
        (1, 0, "Europe"),
        (1, 1, "24,930"),
    ]


def test_a_cell_that_declares_its_own_position_overrides_the_implied_one() -> None:
    """The explicit shape wins over the order the cell was written in, and it wins per cell.

    CHARACTERISATION OF WHAT MIXING THE TWO SHAPES ACTUALLY DOES, recorded rather than smoothed
    over. A declared column moves the cursor its neighbours count from, and a declared row does
    not: the undeclared cell below lands on the implied row 0 and on column 5. That is a grid
    nobody intended, and a reader looking at a model that mixed the shapes needs to see it in the
    cells rather than have the reader guess which of the two the model meant.
    """
    table = read_table(
        {
            "table_id": "t-1",
            "rows": [[{"text": "Americas", "row": 3, "column": 4}, {"text": "40,315"}]],
        }
    )
    assert table is not None
    assert (table.cells[0].row, table.cells[0].column) == (3, 4)
    assert (table.cells[1].row, table.cells[1].column) == (0, 5)
    assert table.row_count == 4, "the row count follows the cells, including the declared one"


def test_header_body_and_footer_rows_stack_into_one_grid() -> None:
    """Three lists, one coordinate system, and the offsets between them are not the model's job.

    A header row is row 0 and the first body row is row 1, so a reviewer comparing this grid to the
    mechanical inventory's grid for the same `table` element is comparing the same positions. Three
    independently zero-based blocks would put a header and a total on the same row and make the
    comparison meaningless.
    """
    table = read_table(
        {
            "table_id": "t-1",
            "header_rows": [["Segment", "2024"]],
            "rows": [["Americas", "40,315"], ["Europe", "24,930"]],
            "footer_rows": [["Total", "65,245"]],
        }
    )
    assert table is not None
    assert [(c.row, c.text) for c in table.cells if c.column == 0] == [
        (0, "Segment"),
        (1, "Americas"),
        (2, "Europe"),
        (3, "Total"),
    ]


def test_a_bare_scalar_in_a_row_becomes_a_cell_carrying_that_scalar() -> None:
    """The simplest thing a model can write is still structure, and refusing it would lose it.

    A one-column table written as a plain list of values is a real shape, and a reader that
    demanded a mapping per cell would drop it entirely — turning a table the model DID emit into
    part of the zero that Phase 2.1 measured. A scalar that is not a string is carried as its text,
    and a null cell becomes an empty one rather than disappearing and shortening the grid.
    """
    table = read_table({"table_id": "t-1", "rows": ["Total net sales", 124300, None]})
    assert table is not None
    assert [(c.row, c.column, c.text) for c in table.cells] == [
        (0, 0, "Total net sales"),
        (1, 0, "124300"),
        (2, 0, ""),
    ]


def test_every_cell_of_a_header_row_is_a_header_and_so_is_one_that_says_so_itself() -> None:
    """Two ways to say the same thing, both honoured, neither inferred from what a cell contains.

    Nothing here reads a cell's text and decides it looks like a heading. `is_header` is either the
    block the model put the cell in or the flag the model set on it, which is the difference
    between recording a model's structure and inventing one for it.
    """
    table = read_table(
        {
            "table_id": "t-1",
            "header_rows": [["Segment", "2024"]],
            "rows": [[{"text": "Three months ended", "is_header": True}, {"text": "40,315"}]],
        }
    )
    assert table is not None
    assert [(c.text, c.is_header) for c in table.cells] == [
        ("Segment", True),
        ("2024", True),
        ("Three months ended", True),
        ("40,315", False),
    ]
    assert table.header_cell_count == 3


@pytest.mark.parametrize(
    "declared",
    [
        pytest.param(0, id="zero"),
        pytest.param(-3, id="negative"),
        pytest.param(True, id="boolean"),
        pytest.param("2", id="string"),
        pytest.param(2.5, id="float"),
        pytest.param(None, id="null"),
    ],
)
def test_a_span_that_is_not_a_positive_integer_is_read_as_one(declared: Any) -> None:
    """A cell occupies at least one position, and a zero span would make a grid nothing occupies.

    The substitution is silent because the alternative is refusing the whole table over one cell,
    which loses far more than it protects. `True` is in this list deliberately: a bool is an int in
    Python, and a span of `1` arrived at by accident is a span nobody declared.
    """
    table = read_table(
        {
            "table_id": "t-1",
            "rows": [[{"text": "Americas", "row_span": declared, "column_span": declared}]],
        }
    )
    assert table is not None
    assert (table.cells[0].row_span, table.cells[0].column_span) == (1, 1)


def test_a_span_the_model_actually_declared_survives() -> None:
    """MUTATION on the guard above: a reader that defaulted every span to one would also pass it.

    It would also flatten every merged header a filing writes, which is precisely the structure a
    column heading spanning two periods carries — and the reason this contract exists.
    """
    table = read_table(
        {
            "table_id": "t-1",
            "rows": [[{"text": "Three months ended", "row_span": 2, "column_span": 4}]],
        }
    )
    assert table is not None
    assert (table.cells[0].row_span, table.cells[0].column_span) == (2, 4)


# --- what survives, what is reported, and what is counted ----------------------------------------


def test_a_key_nobody_declared_survives_on_both_the_table_and_the_cell() -> None:
    """The point of running five candidates through a new contract is to find out what they emit.

    A reader that silently discarded the surprising half of a response would guarantee the surprise
    was never seen. `table_count` was zero across the whole proof, so the FIRST structured table any
    candidate returns is the most informative artifact this contract will ever receive, and none of
    it may be thrown away for being unexpected.
    """
    table = read_table(
        {
            "table_id": "t-1",
            "rows": [[{"text": "Americas", "cell_note": "read from the image"}]],
            "presentation_hint": "the model invented this key on its own",
        }
    )
    assert table is not None
    assert table.extra == {"presentation_hint": "the model invented this key on its own"}
    assert table.cells[0].extra == {"cell_note": "read from the image"}


def test_a_key_the_reader_understood_is_not_also_dumped_into_extra() -> None:
    """MUTATION. The preservation test above passes vacuously if `extra` is just the whole mapping.

    `extra` has to be the complement of what the reader understood, or every field is reported
    twice and `extra` stops being evidence that a model emitted something nobody planned for.
    """
    table = read_table(COUNTED_TABLE)
    assert table is not None
    assert table.extra == {}
    for known in ("table_id", "source_member", "header_rows", "rows", "footer_rows"):
        assert known not in table.extra, f"{known} is a key the reader understood"
    for cell in table.cells:
        assert "text" not in cell.extra and "unresolved" not in cell.extra


def test_a_missing_envelope_key_is_reported_exactly_and_never_refused() -> None:
    """A table missing its source anchors is still a table, and discarding it loses a measurement.

    The absence is carried to a reviewer as a finding. `table_id` can never appear in this tuple —
    a table without one was dropped before the tuple was built — so the reported set is exactly the
    absent members of the published envelope and nothing else.
    """
    complete = read_table(COUNTED_TABLE)
    bare = read_table({"table_id": "t-1"})
    partial = read_table({"table_id": "t-1", "rows": []})
    assert complete is not None and bare is not None and partial is not None
    assert complete.missing_envelope_keys == ()
    assert bare.missing_envelope_keys == ("source_member", "rows")
    assert partial.missing_envelope_keys == ("source_member",)
    assert set(TABLE_ENVELOPE_KEYS) == {"table_id", "source_member", "rows"}
    assert bare.table_id == "t-1", "a usable table was thrown away over a missing key"


def test_the_counts_are_computed_from_the_cells_rather_than_from_the_row_lists() -> None:
    """Counting the lists the model wrote would report the shape of the response, not of the grid.

    The distinction is load-bearing here: no row of this table is more than three entries long, and
    the grid is four columns wide because a footer cell spans three of them. A column count taken
    from the longest row would say three, and a reviewer comparing this to the source element's
    grid would be looking at a width the model never claimed.

    `unresolved_cell_count` adds the cells the model flagged to the cells it described separately,
    because both are the model saying it could not read something and a count reporting one of them
    would understate what the parse admits it does not have.
    """
    table = read_table(COUNTED_TABLE)
    assert table is not None
    assert table.row_count == 4
    assert table.column_count == 4
    assert table.header_cell_count == 3
    assert table.unresolved_cell_count == 2
    assert len(table.cells) == 11
    assert max(len(row) for row in COUNTED_TABLE["rows"]) == 3, "no row list is four entries long"


def test_the_exported_mapping_says_the_classification_is_the_models_word() -> None:
    """A grid printed without the sentence saying who classified it is a taxonomy by silence.

    `type` and `classification` are carried verbatim and checked against nothing, so the record an
    auditor reads has to travel with the statement that a human reviewer may overrule both.
    """
    table = read_table({**COUNTED_TABLE, "type": "a kind no backend has heard of"})
    assert table is not None
    mapping = table.to_mapping()
    assert mapping["type"] == "a kind no backend has heard of"
    assert "MODEL's words" in mapping["classification_note"]
    assert mapping["cell_count"] == len(table.cells)
    assert mapping["missing_envelope_keys"] == []
