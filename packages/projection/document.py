"""Project one preserved filing into ONE YAML document, losslessly for everything a human reads.

WHAT THIS IS FOR, AND THE MEASUREMENT THAT JUSTIFIES IT. Apple's 10-Q accession
0000320193-25-000008 is 915,890 characters as SEC published it and 142,096 characters of words a
person actually reads — a markup overhead of 6.4x. Sent intact, it costs roughly 254,000 tokens and
exceeds the runtime context of four of the five approved candidates; the fifth, Qwen3 235B A22B at a
measured 262,144, refused it with "at least 262,017 input tokens" and no room for an answer.

    THE FILING WAS NEVER TOO BIG. Its content is about 39,000 tokens. The HTML around the content is
    what did not fit, and no model was ever given the chance to fail at parsing it.

WHY THIS IS A PROJECTION AND NOT A PARSE. It carries three things and decides nothing:

    prose blocks   every visible text span the mechanical inventory found, in document order,
                   each with the member it came from and its offset in that member
    tables         every `table` element, as the GRID the inventory measured — row, column, row
                   span, column span, cell text — rather than as markup or as flattened prose
    images         every filed image, by identity, hash and dimensions

There is no title, no section, no type, no classification and no judgement about importance
anywhere in the output. A block is a run of characters at an offset. What any of it MEANS is still
the selected parsing model's decision, and `rules.md` invariant 14 and section 21 rule 1 are
untouched by a transform that changes syntax and not meaning.

WHY THE TABLES ARE WORTH THEIR TOKENS. Flattening this filing to plain prose costs about 39,957
tokens; carrying the table grids costs about 61,951. The extra 22,000 buys back the fact that
`Total net sales 124,300 119,575` is a row with two period columns. Plain text destroys that, and on
a financial filing destroying it is data loss rather than compression.

LOSSLESS IS CHECKED, NOT ASSERTED. `project` refuses to return a document that does not carry every
visible span, every table element and every image the inventory measured. A projection that quietly
dropped content would be the exact failure mode section 21 rule 7 exists to prevent, and an
assertion in a docstring is not a check.

THE ORIGINAL IS UNTOUCHED AND STAYS AUTHORITATIVE. Nothing here rewrites, replaces or supersedes a
preserved artifact. Every block carries `member` and `at`, so every citation a model makes against
this document resolves back into the bytes SEC published, at the offset the inventory recorded, and
`packages/coverage_validation` proves it there rather than here.
"""

from __future__ import annotations

from html import unescape
from typing import Any

from packages.source_inventory import FilingInventory

from .errors import ProjectionIncompleteError

#: The document's own version, so a stored projection can be told apart from a later shape.
SCHEMA_VERSION = "source-projection-v1"


def _blocks(inventory: FilingInventory) -> list[dict[str, Any]]:
    """Every visible span that is NOT inside a table, in document order.

    A span inside a table is carried by its table's grid instead. Emitting it twice would put the
    same characters in front of the model in two shapes and invite it to represent them twice.
    """
    return [
        {
            "id": span.span_id,
            "member": span.member,
            "at": span.start,
            "text": unescape(span.normalized_text),
        }
        for span in inventory.visible_spans
        if not span.table_id
    ]


def _tables(inventory: FilingInventory) -> list[dict[str, Any]]:
    """Every table element as a grid.

    EMPTY CELLS ARE DROPPED AND THE GRID POSITIONS ARE NOT. Apple's statements are laid out on a
    24-column grid of which most cells are spacing, so carrying them would triple the table cost to
    say nothing. Each surviving cell states its own row and column, so the shape is preserved
    exactly without the padding.
    """
    return [
        {
            "id": table.table_id,
            "member": table.member,
            "at": table.start,
            "rows": table.row_count,
            "columns": table.max_columns,
            "cells": [
                [cell.row_index, cell.column_index, cell.row_span, cell.column_span, cell.text]
                for cell in table.cells
                if cell.text.strip()
            ],
        }
        for table in inventory.tables
    ]


def _images(inventory: FilingInventory) -> list[dict[str, Any]]:
    """Every filed image by identity. The BYTES still travel separately to a multimodal parser.

    This entry exists so a text-only model knows an image is there and can say it could not read
    it, rather than never learning it existed. It is not a description: nothing in this repository
    says what a picture shows.
    """
    return [
        {
            "id": image.filename,
            "member": image.member,
            "media_type": image.media_type,
            "sha256": image.sha256,
            "width": image.width,
            "height": image.height,
        }
        for image in inventory.images
    ]


def project(inventory: FilingInventory) -> dict[str, Any]:
    """The projection of one filing, as a mapping ready for the YAML serializer.

    Raises `ProjectionIncompleteError` when it would not carry everything the inventory measured.
    """
    blocks = _blocks(inventory)
    tables = _tables(inventory)
    images = _images(inventory)

    # THE COMPLETENESS CHECK. Every visible span is either carried as a block or belongs to a table
    # that is carried as a grid; every table element and every image is carried. Anything else is a
    # projection that lost content, and it fails closed.
    carried_spans = {block["id"] for block in blocks}
    carried_tables = {table["id"] for table in tables}
    missing = [
        span.span_id
        for span in inventory.visible_spans
        if span.span_id not in carried_spans and span.table_id not in carried_tables
    ]
    if missing:
        raise ProjectionIncompleteError(
            f"{len(missing)} visible span(s) would not appear in the projection, the first being "
            f"{missing[0]!r}. A projection that drops content is the failure mode this transform "
            "was refused authorization for; it is refused here rather than returned."
        )
    if len(tables) != len(inventory.tables):
        raise ProjectionIncompleteError(
            f"the inventory measured {len(inventory.tables)} table element(s) and the projection "
            f"carries {len(tables)}"
        )
    if len(images) != len(inventory.images):
        raise ProjectionIncompleteError(
            f"the inventory measured {len(inventory.images)} image(s) and the projection "
            f"carries {len(images)}"
        )

    return {
        "projection": SCHEMA_VERSION,
        "filing": {
            "cik": inventory.cik,
            "accession": inventory.accession,
            "form_as_filed": inventory.form_as_filed,
            "filing_date": inventory.filing_date,
            "report_period": inventory.report_period,
        },
        "source_set_sha256": inventory.source_set_sha256,
        "members": [
            {
                "id": member.member,
                "sha256": member.sha256,
                "bytes": member.byte_count,
                "sec_declared_type": member.declared_type,
            }
            for member in inventory.members
            if member.human_readable or member.image
        ],
        "blocks": blocks,
        "tables": tables,
        "images": images,
        "what_this_is": (
            "Every human-readable unit of this filing, taken from the bytes SEC published and "
            "carried without its markup. A block is a run of characters at an offset in the member "
            "named beside it. A table is the grid its own markup describes. Nothing here has been "
            "titled, classified, summarised, reordered or judged, and no unit has been dropped."
        ),
        "how_to_cite": (
            "Quote a block's text verbatim. Every offset is a character offset into the preserved "
            "original member, so a quote is checked against the bytes SEC published rather than "
            "against this document."
        ),
    }


def projection_note(inventory: FilingInventory, projected_characters: int) -> dict[str, Any]:
    """What the projection cost and what it carried, for the run record and the review UI."""
    raw = sum(m.character_count for m in inventory.members if m.human_readable)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_characters": raw,
        "projected_characters": projected_characters,
        "reduction_multiple": round(raw / projected_characters, 2) if projected_characters else 0,
        "visible_spans_carried": len(inventory.visible_spans),
        "table_elements_carried": len(inventory.tables),
        "images_carried": len(inventory.images),
        "lossless_check": "every visible span, table element and image the inventory measured",
        "original_status": (
            "preserved, unmodified and authoritative. The projection is what the model reads; the "
            "bytes SEC published are what every citation is proved against."
        ),
    }
