"""Build the mechanical inventory of one filing from its assembled source set.

WHY THIS TAKES A `SourceSet` AND NOT A DIRECTORY. `packages/source_transport` already decided, from
byte evidence alone, which members are human-readable text, which are images, which are machine
artifacts and which are EDGAR's own renderer output. Re-deciding here would give that question two
homes and two answers — rules.md section 5. This package measures what those members CONTAIN; it
does not revisit what they ARE.

WHAT COUNTS AS A DENOMINATOR MEMBER. Only the members whose content reaches the parsing model:
`PARSER_INPUT_TEXT` and `PARSER_INPUT_IMAGE`. A machine-only linkbase and an EDGAR renderer page
are inventoried as members, with their transport role recorded, and they carry no spans and no
tables — because no model was ever sent them, and counting a document nobody saw as uncovered
content would make complete coverage unreachable by construction. That is the same defect
`COVERED_DISPOSITIONS` was widened to fix in `source_transport/dispositions.py`.

DUPLICATE IS A BYTE OBSERVATION, NOT A JUDGEMENT. Two members with the same SHA-256 are the same
bytes. Two spans with the same normalised characters are the same characters. Two tables with the
same source slice are the same slice. None of that says one is redundant, and nothing here drops
either copy — the deleted classifier ruled a courtesy PDF "duplicated" the primary document on a
judgement like that and suppressed a filed source range for it (ADR-0017).
"""

from __future__ import annotations

import re
from typing import Final

from packages.source_transport import MemberDisposition, SourceMember, SourceSet

from .errors import MarkupUnreadableError
from .images import dimensions, media_type
from .markup import normalize_text, plain_text_spans, walk_markup
from .records import (
    FilingInventory,
    ImageRecord,
    MemberRecord,
    TableElement,
    TextSpan,
)

_SRC_ATTRIBUTE = re.compile(r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
_MARKUP_EXTENSIONS: Final[frozenset[str]] = frozenset({".htm", ".html", ".xhtml", ".sgml"})


def _text_media_type(filename: str, text: str) -> str:
    lowered = filename.lower()
    extension = lowered[lowered.rfind(".") :] if "." in lowered else ""
    if extension in _MARKUP_EXTENSIONS:
        return "text/html"
    # An EDGAR complete submission is an SGML envelope whose documents may themselves be markup.
    # Deciding by content rather than by extension keeps a `.txt` submission from being walked as
    # plain text when it plainly carries elements.
    return "text/html" if "<" in text[:16384] and ">" in text[:16384] else "text/plain"


def _spans_and_tables(
    member: SourceMember, text: str
) -> tuple[tuple[TextSpan, ...], tuple[TableElement, ...], tuple[str, ...]]:
    if _text_media_type(member.filename, text) == "text/plain":
        return plain_text_spans(text, member=member.filename), (), ()
    try:
        return walk_markup(text, member=member.filename)
    except MarkupUnreadableError as error:
        # A member declared as markup that carries none is inventoried as plain text, with the
        # reason recorded. Raising would abandon the whole filing's inventory over one member.
        return (
            plain_text_spans(text, member=member.filename),
            (),
            (f"{member.filename}: {error}",),
        )


def _image_references(text: str, filenames: frozenset[str]) -> list[tuple[str, int]]:
    """Every `src` attribute pointing at one of this filing's images, with its source offset."""
    found: list[tuple[str, int]] = []
    for match in _SRC_ATTRIBUTE.finditer(text):
        value = match.group(1) or match.group(2) or match.group(3) or ""
        basename = value.rsplit("/", 1)[-1].split("?", 1)[0]
        if basename in filenames:
            found.append((basename, match.start()))
    return found


def build_inventory(source_set: SourceSet) -> FilingInventory:
    """Every mechanically observable unit of one filing, measured from the preserved bytes."""
    findings: list[str] = []
    spans: list[TextSpan] = []
    tables: list[TableElement] = []
    members: list[MemberRecord] = []

    image_filenames = frozenset(m.filename for m in source_set.image_members if m.filename)
    references: dict[str, list[tuple[str, int]]] = {}

    #: SHA-256 to the first member that carried it, so a byte-identical member is recognisable.
    seen_member_bytes: dict[str, str] = {}
    for member in source_set.members:
        text = member.text or ""
        member_spans: tuple[TextSpan, ...] = ()
        member_tables: tuple[TableElement, ...] = ()
        if member.disposition is MemberDisposition.PARSER_INPUT_TEXT and text:
            member_spans, member_tables, member_findings = _spans_and_tables(member, text)
            findings.extend(member_findings)
            for name, offset in _image_references(text, image_filenames):
                references.setdefault(name, []).append((member.filename, offset))
            spans.extend(member_spans)
            tables.extend(member_tables)

        label = member.filename or f"sequence-{member.sequence}"
        duplicate_of = seen_member_bytes.get(member.sha256, "")
        if not duplicate_of and member.sha256:
            seen_member_bytes[member.sha256] = label

        members.append(
            MemberRecord(
                filename=member.filename,
                member=label,
                declared_type=member.declared_type,
                description=member.description,
                media_type=(
                    f"image/{member.image_format}"
                    if member.image_format
                    else _text_media_type(member.filename, text)
                    if text
                    else "application/octet-stream"
                ),
                byte_count=member.byte_count,
                sha256=member.sha256,
                transport_role=member.disposition.value,
                human_readable=member.disposition is MemberDisposition.PARSER_INPUT_TEXT,
                image=member.disposition is MemberDisposition.PARSER_INPUT_IMAGE,
                character_count=len(text),
                duplicate_of=duplicate_of,
                span_count=len(member_spans),
                table_count=len(member_tables),
            )
        )

    images = [
        ImageRecord(
            filename=member.filename,
            member=member.filename,
            media_type=(
                media_type(member.image_bytes)
                if member.image_bytes
                else f"image/{member.image_format or 'unknown'}"
            ),
            byte_count=member.byte_count,
            sha256=member.sha256,
            width=dimensions(member.image_bytes)[0] if member.image_bytes else None,
            height=dimensions(member.image_bytes)[1] if member.image_bytes else None,
            referenced_at=tuple(references.get(member.filename, ())),
        )
        for member in source_set.image_members
    ]

    return FilingInventory(
        cik=source_set.cik,
        accession=source_set.accession,
        form_as_filed=source_set.form_as_filed,
        filing_date=source_set.filing_date,
        report_period=source_set.report_period,
        source_set_sha256=source_set.source_set_id,
        members=tuple(members),
        spans=_mark_duplicate_spans(spans),
        tables=_mark_duplicate_tables(tables),
        images=tuple(images),
        findings=tuple(findings),
    )


def _mark_duplicate_spans(spans: list[TextSpan]) -> tuple[TextSpan, ...]:
    """Point every repeat of a normalised text at the first span that carried it.

    A page header repeated on forty rendered pages is forty spans of identical characters. Marking
    the repeats keeps the denominator honest without deleting anything: a reviewer still sees all
    forty, and a coverage ledger can report them as repeated rather than as forty separate
    omissions.
    """
    first: dict[str, str] = {}
    marked: list[TextSpan] = []
    for span in spans:
        key = normalize_text(span.normalized_text)
        original = first.get(key)
        if original is None:
            first[key] = span.span_id
            marked.append(span)
            continue
        marked.append(
            TextSpan(
                span_id=span.span_id,
                member=span.member,
                start=span.start,
                end=span.end,
                original_text=span.original_text,
                normalized_text=span.normalized_text,
                hidden_reason=span.hidden_reason,
                element_path=span.element_path,
                parent_element=span.parent_element,
                table_id=span.table_id,
                duplicate_of=original,
            )
        )
    return tuple(marked)


def _mark_duplicate_tables(tables: list[TableElement]) -> tuple[TableElement, ...]:
    """Point every byte-identical table at the first one that carried those bytes."""
    first: dict[str, str] = {}
    marked: list[TableElement] = []
    for table in tables:
        original = first.get(table.sha256)
        if original is None:
            first[table.sha256] = table.table_id
            marked.append(table)
            continue
        marked.append(
            TableElement(
                table_id=table.table_id,
                member=table.member,
                start=table.start,
                end=table.end,
                element_path=table.element_path,
                parent_table_id=table.parent_table_id,
                nesting_depth=table.nesting_depth,
                row_count=table.row_count,
                max_columns=table.max_columns,
                cell_count=table.cell_count,
                sha256=table.sha256,
                cells=table.cells,
                duplicate_of=original,
            )
        )
    return tuple(marked)
