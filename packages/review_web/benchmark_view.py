"""The completeness review surface: one filing's mechanical inventory, classified by a person.

WHAT THIS EXISTS TO PRODUCE, AND THE DEFECT IT CLOSES. Phase 2.1 could report `352/364 references
resolved` and could not say what fraction of the filing that described, because a source region a
model never cited never entered the denominator. `packages/source_inventory` supplies the
denominator — for the benchmark filing, 63 members, 1,750 visible spans, 41 table elements and 2
images, measured from the preserved bytes with no model involved. This surface is where a person
turns that raw count into a REQUIRED SET, one item at a time, on the record.

WHY A PERSON AND NOT CODE. The inventory can say there are 41 table elements. It cannot say which
carry data, which are the filing agent's page-layout scaffolding, and which are the same rendering
twice. Deciding that in backend code would be the universal filing taxonomy `rules.md` section 21
rule 1 and rule 2 forbid, and it would be a taxonomy derived from one issuer. So the classification
is DATA: who said it, when, at which version, scoped to one accession at one source hash.

THE DEFAULT IS `REQUIRES_REVIEW` AND IT IS NOT A PLACEHOLDER. An unreviewed item is neither
demanded nor excused — it blocks the mechanical gate, which is the correct pressure. This surface
therefore shows unreviewed counts as prominently as reviewed ones.

TWO MECHANICAL SUGGESTIONS ARE SHOWN AND NEITHER IS APPLIED. `completeness.suggest` proposes a
classification for a table element whose cells carry no non-whitespace character, and for one whose
source slice is byte-identical to an earlier element. Both are byte observations with the evidence
attached, both are displayed as unaccepted proposals, and neither counts as a judgement until a
person records one.

EVERY VALUE ON EVERY PAGE IS FILING-DERIVED AND UNTRUSTED. A member filename, a declared type, a
span's text and a table cell all come from bytes SEC published, and this surface exists precisely to
display them. They go through `html.esc` without exception — a source slice rendered raw would be
stored cross-site scripting in the one page whose whole purpose is showing attacker-influenceable
content. Nothing here is ever handed to a markup parser.

EVERY STATE CHANGE IS A FORM POST WITH A CSRF TOKEN. Not one classification control is a link: a
link is something a browser can be made to follow, and recording a judgement changes the
denominator of a benchmark.
"""

from __future__ import annotations

from collections.abc import Iterable

from packages.completeness import (
    BenchmarkTruth,
    ImageClassification,
    Judgement,
    SpanClassification,
    TableClassification,
)
from packages.source_inventory import (
    FilingInventory,
    ImageRecord,
    MemberRecord,
    TableCell,
    TableElement,
    TextSpan,
)

from .html import badge, each, esc, join, tag, url, warning

#: One member's spans, one screen at a time. The primary document of the benchmark filing carries
#: 1,486 of them and each row renders a six-option control, so a single page would be megabytes of
#: markup. The window is STATED on the page rather than applied quietly — a silently shortened view
#: of a denominator is the same defect as a silently shortened request.
SPANS_PER_PAGE: int = 200

#: How much of one span's normalised text a row shows. The preserved member is authoritative and
#: the offsets beside it locate the whole span in it; one span of the benchmark filing is 56,644
#: characters of inline-XBRL hidden facts, and a table row is not where that is read.
SPAN_TEXT_CHARACTERS: int = 600

#: How much of one table element's raw source slice is shown beside its extracted grid.
TABLE_SLICE_CHARACTERS: int = 12_000

#: How the classification of an item is coloured. REQUIRES_REVIEW is deliberately a warning: it is
#: the state that blocks the gate, and rendering it as neutral would make an unreviewed filing look
#: settled.
_CLASSIFICATION_KIND = {
    "REQUIRES_REVIEW": "warn",
    "MATERIAL_FILING_CONTENT": "ok",
    "DATA_BEARING": "ok",
    "REPEATED_CONTENT": "neutral",
    "NAVIGATION": "neutral",
    "PURE_TRANSPORT_MARKUP": "neutral",
    "NOT_HUMAN_READABLE": "neutral",
    "LAYOUT": "neutral",
    "DUPLICATE_RENDERING": "neutral",
    "EMPTY": "neutral",
    "LOGO": "neutral",
    "DECORATIVE": "neutral",
}

#: The three item kinds a judgement may attach to, and the closed set of values each accepts. The
#: same mapping is what the POST handler validates against, so a page can never offer an option the
#: route would refuse.
KIND_CLASSIFICATIONS: dict[str, tuple[str, ...]] = {
    "span": tuple(value.value for value in SpanClassification),
    "table": tuple(value.value for value in TableClassification),
    "image": tuple(value.value for value in ImageClassification),
}


def base_path(cik: str, accession: str) -> tuple[str, ...]:
    """The URL prefix every page and every form on this surface hangs from."""
    return ("benchmark", cik, accession)


# --- shared fragments --------------------------------------------------------------------------


def _tabs(items: Iterable[tuple[str, str, bool]]) -> str:
    """A strip of (href, label, active) links. The page navigation and the member strip are both."""
    return tag(
        "div",
        join(
            *[
                tag("a", esc(label), href=href, class_="active" if active else None)
                for href, label, active in items
            ]
        ),
        class_="views",
    )


def page_navigation(base: tuple[str, ...], current: str) -> str:
    """The strip every page of this surface carries. A page nobody can reach is not a surface."""
    pages = (
        ("", "Overview"),
        ("inventory", "Source inventory"),
        ("spans", "Spans"),
        ("tables", "Tables"),
        ("images", "Images"),
        ("models", "Model runs"),
    )
    return _tabs(
        (url(*base, page) if page else url(*base), label, page == current) for page, label in pages
    )


def filing_heading(inventory: FilingInventory, truth: BenchmarkTruth) -> str:
    """The filing this surface is about, and the truth version it is being classified at.

    A SOURCE-HASH DISAGREEMENT IS SHOWN AT THE TOP OF EVERY PAGE. The stored judgements describe
    one set of bytes; the inventory below describes another. `build_ledger` refuses that pairing
    outright — coverage of one filing computed against another filing's denominator is precisely,
    confidently wrong — and a reviewer who cannot see the mismatch would go on classifying items
    that no longer exist.
    """
    drift = (
        warning(
            f"the stored benchmark truth describes source set {truth.source_set_sha256} and this "
            f"inventory describes {inventory.source_set_sha256}. A member has been acquired or "
            "re-acquired since the judgements below were recorded, and a completeness ledger "
            "refuses this pairing rather than reconciling it."
        )
        if truth.source_set_sha256 and truth.source_set_sha256 != inventory.source_set_sha256
        else ""
    )
    return join(
        tag(
            "h1",
            esc(
                f"Completeness benchmark — {inventory.form_as_filed} {inventory.accession} — "
                f"CIK {inventory.cik}"
            ),
        ),
        tag(
            "p",
            esc(
                f"filed {inventory.filing_date}; period {inventory.report_period or 'unstated'}; "
                f"source set {inventory.source_set_sha256[:16]}; "
                f"benchmark truth version {truth.version}"
            ),
            class_="mono",
        ),
        drift,
    )


def _classification_control(
    base: tuple[str, ...],
    *,
    csrf: str,
    kind: str,
    item_id: str,
    current: str,
    member: str = "",
    start: int = 0,
) -> str:
    """One POST form that records one classification. Never a link, and never a GET.

    `member` and `start` travel with the post so the reviewer is returned to the same page and the
    same window they were reading. They are NOT a redirect target: the handler builds the location
    from the item kind, so nothing a browser sends can point this redirect off the origin.
    """
    options = KIND_CLASSIFICATIONS[kind]
    return tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag("input", "", type="hidden", name="kind", value=kind),
            tag("input", "", type="hidden", name="item_id", value=item_id),
            tag("input", "", type="hidden", name="member", value=member),
            tag("input", "", type="hidden", name="start", value=str(start)),
            tag(
                "select",
                join(
                    *[
                        tag("option", esc(value), value=value, selected=(value == current))
                        for value in options
                    ]
                ),
                name="classification",
                aria_label=f"classification of {item_id}",
            ),
            tag("input", "", type="text", name="note", placeholder="reason"),
            tag("button", "Record", type="submit"),
        ),
        method="post",
        action=url(*base, "judgements"),
        class_="inline",
    )


def _suggestion_note(judgement: Judgement | None) -> str:
    """An unaccepted mechanical proposal, shown with its evidence and marked as not applied."""
    if judgement is None or not judgement.suggested:
        return ""
    return tag(
        "p",
        esc(
            f"mechanical suggestion, NOT APPLIED: {judgement.classification} — {judgement.evidence}"
        ),
        class_="hint",
    )


def _recorded_note(judgement: Judgement | None) -> str:
    """Who recorded an accepted judgement and when. A judgement without provenance is an opinion."""
    if judgement is None or judgement.suggested:
        return ""
    trailer = f" — {judgement.note}" if judgement.note else ""
    return tag(
        "p",
        esc(
            f"recorded by {judgement.reviewer or 'an unnamed reviewer'} at {judgement.at}{trailer}"
        ),
        class_="hint",
    )


def _classification_block(
    base: tuple[str, ...],
    *,
    csrf: str,
    kind: str,
    item_id: str,
    judgement: Judgement | None,
    current: str,
    member: str = "",
    start: int = 0,
) -> str:
    """What every classifiable item shows: the state, the proposal, the provenance, the control.

    ONE BLOCK FOR ALL THREE KINDS. A span, a table element and an image are classified against
    different vocabularies and are otherwise the same activity, and the four pieces have to stay
    together: a page that showed the current state without the unaccepted proposal behind it would
    let a reviewer accept a byte observation they never saw.
    """
    return join(
        tag("p", badge(current, _CLASSIFICATION_KIND.get(current, "neutral"))),
        _suggestion_note(judgement),
        _recorded_note(judgement),
        _classification_control(
            base,
            csrf=csrf,
            kind=kind,
            item_id=item_id,
            current=current,
            member=member,
            start=start,
        ),
    )


def _progress(total: int, reviewed: int, suggested: int) -> str:
    return esc(
        f"{reviewed} of {total} classified by a person; {total - reviewed} unreviewed; "
        f"{suggested} carry an unaccepted mechanical suggestion"
    )


def _counts(item_ids: Iterable[str], judgements: dict[str, Judgement]) -> tuple[int, int, int]:
    """(measured, classified by a person, carrying an unaccepted suggestion) for one item kind.

    ONE FUNCTION FOR ALL THREE KINDS, because the rule they share is the one that matters and it
    must not be able to drift between them: A SUGGESTION IS NOT A JUDGEMENT. An item carrying only
    a mechanical proposal is counted as unreviewed, exactly as an item carrying nothing is, and it
    goes on blocking the gate until a person records a decision.
    """
    total = reviewed = suggested = 0
    for item_id in item_ids:
        total += 1
        found = judgements.get(item_id)
        if found is None:
            continue
        if found.suggested:
            suggested += 1
        else:
            reviewed += 1
    return total, reviewed, suggested


def _span_counts(inventory: FilingInventory, truth: BenchmarkTruth) -> tuple[int, int, int]:
    return _counts((span.span_id for span in inventory.visible_spans), truth.spans)


def _table_counts(inventory: FilingInventory, truth: BenchmarkTruth) -> tuple[int, int, int]:
    return _counts((element.table_id for element in inventory.tables), truth.tables)


def _image_counts(inventory: FilingInventory, truth: BenchmarkTruth) -> tuple[int, int, int]:
    return _counts((image.filename for image in inventory.images), truth.images)


def _findings_card(inventory: FilingInventory) -> str:
    if not inventory.findings:
        return tag(
            "div",
            join(
                tag("h2", "Findings"),
                tag("p", "The inventory walk reported no finding on this filing."),
            ),
            class_="card",
        )
    return tag(
        "div",
        join(
            tag("h2", "Findings"),
            tag(
                "p",
                esc(
                    "Recorded by the mechanical walk, not by any model. A finding is an observation "
                    "about transport; it says nothing about what the member contains."
                ),
                class_="hint",
            ),
            each(inventory.findings, warning),
        ),
        class_="card",
    )


# --- the overview ------------------------------------------------------------------------------


def benchmark_index(
    *,
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    truth_versions: list[int],
    issuer_label: str,
) -> str:
    """Where the reviewer starts: what was measured, what has been classified, what has not."""
    base = base_path(inventory.cik, inventory.accession)
    spans_total, spans_reviewed, spans_suggested = _span_counts(inventory, truth)
    tables_total, tables_reviewed, tables_suggested = _table_counts(inventory, truth)
    images_total, images_reviewed, images_suggested = _image_counts(inventory, truth)

    def row(label: str, page: str, counts: tuple[int, int, int]) -> str:
        total, reviewed, suggested = counts
        return tag(
            "tr",
            join(
                tag("td", tag("a", esc(label), href=url(*base, page))),
                tag("td", esc(f"{total:,}")),
                tag("td", esc(f"{reviewed:,}")),
                tag(
                    "td",
                    badge(f"{total - reviewed:,} unreviewed", "warn" if total > reviewed else "ok"),
                ),
                tag("td", esc(f"{suggested:,}")),
            ),
        )

    stored = (
        ", ".join(str(version) for version in truth_versions)
        if truth_versions
        else "none — no judgement has been recorded for this filing yet"
    )

    return join(
        filing_heading(inventory, truth),
        tag("p", esc(issuer_label)),
        page_navigation(base, ""),
        tag(
            "div",
            join(
                tag("h2", "What was measured"),
                tag(
                    "p",
                    esc(
                        f"{len(inventory.members):,} package member(s), "
                        f"{len(inventory.human_readable_members):,} human-readable; "
                        f"{len(inventory.spans):,} text span(s) of which "
                        f"{spans_total:,} are visible; "
                        f"{inventory.visible_character_count:,} visible character(s); "
                        f"{tables_total:,} table element(s); {images_total:,} image(s)."
                    ),
                ),
                tag(
                    "p",
                    esc(
                        "Every figure above is a transport measurement taken from the preserved "
                        "bytes. No model was invoked to produce any of it and nothing here says "
                        "what any span, table or image means."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        ),
        tag(
            "div",
            join(
                tag("h2", "Human classification"),
                tag(
                    "p",
                    esc(
                        f"Benchmark truth version {truth.version}. Stored versions: {stored}. "
                        "A version is superseded, never overwritten."
                    ),
                ),
                tag(
                    "div",
                    tag(
                        "table",
                        join(
                            tag(
                                "thead",
                                tag(
                                    "tr",
                                    join(
                                        *[
                                            tag("th", header)
                                            for header in (
                                                "items",
                                                "measured",
                                                "classified",
                                                "outstanding",
                                                "unaccepted suggestions",
                                            )
                                        ]
                                    ),
                                ),
                            ),
                            tag(
                                "tbody",
                                join(
                                    row(
                                        "Visible text spans",
                                        "spans",
                                        (spans_total, spans_reviewed, spans_suggested),
                                    ),
                                    row(
                                        "Table elements",
                                        "tables",
                                        (tables_total, tables_reviewed, tables_suggested),
                                    ),
                                    row(
                                        "Filed images",
                                        "images",
                                        (images_total, images_reviewed, images_suggested),
                                    ),
                                ),
                            ),
                        ),
                    ),
                    class_="scroll-x",
                ),
                tag(
                    "p",
                    esc(
                        "An unreviewed item is neither required nor excused. It blocks the "
                        "mechanical gate until a person looks at it, which is the correct pressure "
                        "and not a defect to route around."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        ),
        tag(
            "div",
            join(
                tag("h2", "No completeness ledger is shown"),
                tag(
                    "p",
                    esc(
                        "A completeness ledger measures ONE PARSE against this truth: which items "
                        "a model covered, which it declared unresolved, which a reviewer excluded, "
                        "and which it never mentioned at all. No model has parsed this filing — "
                        "Phase 2.2 issued no provider request — so there is nothing to measure and "
                        "nothing is displayed rather than a ledger computed against an absent "
                        "parse, which would report every span as omitted and mean nothing."
                    ),
                ),
                tag(
                    "p",
                    esc(
                        "The classification recorded here is what a ledger will be computed against "
                        "when a parse exists. It is evidence about this accession at this source "
                        "hash and is never a rule about filings."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        ),
        _findings_card(inventory),
    )


# --- the source inventory ----------------------------------------------------------------------


def inventory_page(*, inventory: FilingInventory, truth: BenchmarkTruth) -> str:
    """Every package member with its transport role, size, hash and measured contents."""
    base = base_path(inventory.cik, inventory.accession)

    def row(member: MemberRecord) -> str:
        name = tag("span", esc(member.member), class_="mono")
        if member.human_readable:
            name = tag(
                "a",
                esc(member.member),
                href=url(*base, "spans", member=member.member),
                class_="mono",
            )
        return tag(
            "tr",
            join(
                tag("td", name),
                tag("td", esc(member.transport_role)),
                tag("td", esc(member.declared_type or "—")),
                tag("td", esc(member.media_type)),
                tag("td", esc(f"{member.byte_count:,}")),
                tag("td", esc(f"{member.character_count:,}")),
                tag("td", tag("span", esc(member.sha256), class_="mono")),
                tag("td", esc(f"{member.span_count:,}")),
                tag("td", esc(f"{member.table_count:,}")),
                tag("td", tag("span", esc(member.duplicate_of or "—"), class_="mono")),
            ),
        )

    headers = (
        "member",
        "transport role",
        "SEC-declared type",
        "media type",
        "bytes",
        "characters",
        "sha256",
        "spans",
        "tables",
        "byte-identical to",
    )
    total_bytes = sum(member.byte_count for member in inventory.members)
    total_characters = sum(member.character_count for member in inventory.members)
    return join(
        filing_heading(inventory, truth),
        page_navigation(base, "inventory"),
        tag(
            "div",
            join(
                tag("h2", "Package members"),
                tag(
                    "p",
                    esc(
                        "The transport role was decided from byte evidence by "
                        "packages/source_transport and is not revisited here. The SEC-declared "
                        "type beside it is what the FILER typed into EDGAR's envelope: one is a "
                        "measurement, the other is a claim, and they are kept apart."
                    ),
                    class_="hint",
                ),
                tag(
                    "div",
                    tag(
                        "table",
                        join(
                            tag(
                                "thead",
                                tag("tr", join(*[tag("th", header) for header in headers])),
                            ),
                            tag("tbody", each(inventory.members, row)),
                        ),
                    ),
                    class_="scroll-x",
                ),
                tag(
                    "p",
                    esc(
                        f"{len(inventory.members):,} member(s); {total_bytes:,} byte(s); "
                        f"{total_characters:,} decoded character(s); "
                        f"{len(inventory.spans):,} span(s); "
                        f"{len(inventory.tables):,} table element(s); "
                        f"{len(inventory.images):,} image(s)."
                    ),
                ),
                tag(
                    "p",
                    esc(
                        "A member whose content never reaches the parsing model carries no span "
                        "and no table. It is inventoried with its role rather than counted as "
                        "uncovered content, because no model was ever sent it."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        ),
        _findings_card(inventory),
    )


# --- one member's spans ------------------------------------------------------------------------


def spans_page(
    *,
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    member: str,
    start: int,
    csrf: str,
) -> str:
    """Every visible span of one member, with the control that classifies it."""
    base = base_path(inventory.cik, inventory.accession)
    readable = inventory.human_readable_members
    spans = inventory.spans_for(member)
    window = spans[start : start + SPANS_PER_PAGE]

    def row(span: TextSpan) -> str:
        judgement = truth.spans.get(span.span_id)
        current = truth.span(span.span_id).value
        text = span.normalized_text[:SPAN_TEXT_CHARACTERS]
        clipped = (
            tag(
                "p",
                esc(
                    f"showing {len(text):,} of {len(span.normalized_text):,} normalised "
                    "characters; the preserved member is authoritative and the offsets locate the "
                    "whole span in it"
                ),
                class_="hint",
            )
            if len(text) < len(span.normalized_text)
            else ""
        )
        return tag(
            "tr",
            join(
                tag("td", tag("span", esc(span.span_id), class_="mono")),
                tag("td", esc(f"{span.start:,}–{span.end:,}")),
                tag("td", esc(f"{span.character_count:,}")),
                tag(
                    "td",
                    badge("visible", "ok")
                    if span.visible
                    else badge(span.hidden_reason.value, "neutral"),
                ),
                tag(
                    "td",
                    tag("span", esc(span.duplicate_of), class_="mono")
                    if span.mechanically_duplicate
                    else "—",
                ),
                tag("td", join(tag("div", esc(text)), clipped)),
                tag(
                    "td",
                    _classification_block(
                        base,
                        csrf=csrf,
                        kind="span",
                        item_id=span.span_id,
                        judgement=judgement,
                        current=current,
                        member=member,
                        start=start,
                    ),
                ),
            ),
        )

    headers = (
        "span",
        "offsets",
        "characters",
        "rendering",
        "same characters as",
        "normalised text",
        "human classification",
    )
    member_links = _tabs(
        (url(*base, "spans", member=record.member), record.member, record.member == member)
        for record in readable
    )
    pagination = _pagination(base, member=member, start=start, total=len(spans))

    if not spans:
        body = tag(
            "div",
            join(
                tag("h2", "No spans"),
                tag(
                    "p",
                    esc(
                        f"{member or 'no member'} carries no inventoried text span. A member whose "
                        "content never reaches the parsing model is inventoried without spans."
                    ),
                ),
            ),
            class_="card",
        )
    else:
        body = tag(
            "div",
            join(
                tag("h2", esc(f"Spans of {member}")),
                tag(
                    "p",
                    esc(
                        f"showing span {start + 1:,} to {start + len(window):,} of "
                        f"{len(spans):,}. A span is one maximal run of character data between two "
                        "BLOCK-level markup boundaries, so an inline element does not split a "
                        "rendered sentence."
                    ),
                ),
                pagination,
                tag(
                    "div",
                    tag(
                        "table",
                        join(
                            tag(
                                "thead",
                                tag("tr", join(*[tag("th", header) for header in headers])),
                            ),
                            tag("tbody", each(window, row)),
                        ),
                    ),
                    class_="scroll-x",
                ),
                pagination,
            ),
            class_="card",
        )

    return join(
        filing_heading(inventory, truth),
        page_navigation(base, "spans"),
        member_links,
        body,
    )


def _pagination(base: tuple[str, ...], *, member: str, start: int, total: int) -> str:
    previous = max(0, start - SPANS_PER_PAGE)
    following = start + SPANS_PER_PAGE
    links: list[tuple[str, str, bool]] = []
    if start > 0:
        links.append((url(*base, "spans", member=member, start=previous), "previous", False))
    if following < total:
        links.append((url(*base, "spans", member=member, start=following), "next", False))
    return _tabs(links) if links else ""


# --- the table elements ------------------------------------------------------------------------


def tables_page(
    *,
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    slices: dict[str, str],
    csrf: str,
) -> str:
    """Every table element, its raw source slice beside its extracted grid, and its classification.

    THE TWO SIDES ARE SHOWN TOGETHER BECAUSE THEY ANSWER DIFFERENT QUESTIONS. The slice is what SEC
    published; the grid is what the mechanical walk read out of it. A reviewer deciding whether an
    element carries data or is page furniture needs both, and a disagreement between them is itself
    the finding.
    """
    base = base_path(inventory.cik, inventory.accession)

    def element(table: TableElement) -> str:
        judgement = truth.tables.get(table.table_id)
        current = truth.table(table.table_id).value
        raw = slices.get(table.table_id, "")
        shown = raw[:TABLE_SLICE_CHARACTERS]
        clipped = (
            tag(
                "p",
                esc(
                    f"showing {len(shown):,} of {len(raw):,} source characters; the preserved "
                    "member is complete on disk and the offsets above locate this element in it"
                ),
                class_="hint",
            )
            if len(shown) < len(raw)
            else ""
        )
        markers = join(
            badge("empty of text", "warn") if table.is_empty else "",
            badge(f"byte-identical to {table.duplicate_of}", "warn") if table.duplicate_of else "",
            badge(f"nested at depth {table.nesting_depth}", "info") if table.nesting_depth else "",
        )
        return tag(
            "div",
            join(
                tag("div", esc(f"{table.member} — {table.element_path}"), class_="kind"),
                tag("div", esc(table.table_id), class_="title"),
                tag(
                    "p",
                    esc(
                        f"characters {table.start:,}–{table.end:,} "
                        f"({table.byte_length:,} of source); {table.row_count:,} row(s); "
                        f"{table.max_columns:,} column(s) at the widest; "
                        f"{table.cell_count:,} cell(s); sha256 {table.sha256}"
                    ),
                    class_="hint",
                ),
                tag("p", markers) if markers else "",
                tag(
                    "div",
                    join(
                        tag(
                            "section",
                            join(
                                tag("h3", "Raw source slice"),
                                tag("pre", esc(shown), class_="source"),
                                clipped,
                            ),
                        ),
                        tag(
                            "section", join(tag("h3", "Extracted grid"), source_element_grid(table))
                        ),
                    ),
                    class_="panes",
                ),
                _classification_block(
                    base,
                    csrf=csrf,
                    kind="table",
                    item_id=table.table_id,
                    judgement=judgement,
                    current=current,
                ),
            ),
            class_="node",
        )

    total, reviewed, suggested = _table_counts(inventory, truth)
    return join(
        filing_heading(inventory, truth),
        page_navigation(base, "tables"),
        tag(
            "div",
            join(
                tag("h2", "Table elements"),
                tag("p", _progress(total, reviewed, suggested)),
                tag(
                    "p",
                    esc(
                        "Nothing here decides what a table is FOR. Financial statement, layout "
                        "scaffold, navigation strip, duplicate rendering — the inventory cannot "
                        "tell them apart and does not try. That judgement is recorded below, by a "
                        "person, scoped to this filing."
                    ),
                    class_="hint",
                ),
                each(inventory.tables, element)
                if inventory.tables
                else tag("p", "This filing carries no inventoried table element."),
            ),
            class_="card",
        ),
    )


def source_element_grid(table: TableElement) -> str:
    """The extracted cells at their computed grid positions, every value escaped.

    POSITIONS ARE POST-SPAN AND THE GRID IS NOT RECONSTRUCTED. `row_index` and `column_index`
    already account for the row and column spans of earlier cells, so a cell that spans two rows
    appears once, at its origin, and the position it covers below is simply absent. Emitting HTML
    `rowspan` on top of that would place the same cell twice and show a reviewer a grid that is not
    the one the ledger compares a model's table against.
    """
    if not table.cells:
        return tag("p", "No cell was extracted from this element.", class_="hint")
    rows: dict[int, list[TableCell]] = {}
    for cell in table.cells:
        rows.setdefault(cell.row_index, []).append(cell)
    body = []
    for index in sorted(rows):
        rendered = []
        for cell in sorted(rows[index], key=lambda c: c.column_index):
            span_note = (
                tag("span", esc(f" [{cell.row_span}×{cell.column_span}]"), class_="hint")
                if cell.row_span > 1 or cell.column_span > 1
                else ""
            )
            rendered.append(tag("th" if cell.is_header else "td", join(esc(cell.text), span_note)))
        body.append(tag("tr", join(*rendered)))
    return tag("div", tag("table", tag("tbody", join(*body))), class_="scroll-x")


# --- the filed images --------------------------------------------------------------------------


def images_page(*, inventory: FilingInventory, truth: BenchmarkTruth, csrf: str) -> str:
    """Each filed image with what its own header bytes say, where it is referenced, and its class."""
    base = base_path(inventory.cik, inventory.accession)
    declared = {member.filename: member.declared_type for member in inventory.members}

    def image(record: ImageRecord) -> str:
        judgement = truth.images.get(record.filename)
        current = truth.image(record.filename).value
        dimensions = (
            f"{record.width}×{record.height} pixels"
            if record.width is not None and record.height is not None
            else "not mechanically obtainable from this format's header"
        )
        references = record.referenced_at
        reference_list = (
            tag(
                "ul",
                each(
                    references,
                    lambda pair: tag("li", esc(f"{pair[0]} at character offset {pair[1]:,}")),
                ),
                class_="refs",
            )
            if references
            else tag(
                "p",
                esc(
                    "No src attribute in any human-readable member points at this image. It was "
                    "filed and is not referenced by the markup this walk read."
                ),
                class_="hint",
            )
        )
        return tag(
            "div",
            join(
                tag("div", esc(record.member), class_="kind"),
                tag("div", esc(record.filename), class_="title"),
                tag(
                    "p",
                    esc(
                        f"{record.byte_count:,} bytes; media type {record.media_type} read from "
                        f"the header bytes; SEC-declared type "
                        f"{declared.get(record.filename) or 'unstated'}; {dimensions}; "
                        f"sha256 {record.sha256}"
                    ),
                ),
                tag("h3", "Referenced at"),
                reference_list,
                _classification_block(
                    base,
                    csrf=csrf,
                    kind="image",
                    item_id=record.filename,
                    judgement=judgement,
                    current=current,
                ),
            ),
            class_="node",
        )

    total, reviewed, suggested = _image_counts(inventory, truth)
    return join(
        filing_heading(inventory, truth),
        page_navigation(base, "images"),
        tag(
            "div",
            join(
                tag("h2", "Filed images"),
                tag("p", _progress(total, reviewed, suggested)),
                tag(
                    "p",
                    esc(
                        "The media type is read from the image's own signature bytes rather than "
                        "from its filename or its declared type, so a member named one thing and "
                        "encoded as another is visible here rather than silently mislabelled."
                    ),
                    class_="hint",
                ),
                each(inventory.images, image)
                if inventory.images
                else tag("p", "This filing carries no filed image."),
            ),
            class_="card",
        ),
    )
