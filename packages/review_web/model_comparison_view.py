"""Every recorded parse of one filing, side by side, in the order the runs were recorded.

WHAT THIS PAGE IS FOR. It is the page a person opens to decide whether a parse is any good. Every
run of one filing is measured against one denominator — the same mechanical inventory, the same
human classification of it — so the figures on two rows describe the same question asked of two
models. That is the only thing a shared denominator buys, and it is a lot: Phase 2.1 could report
`352/364 references resolved` for one model and `41/47 parts terminal` for another and could not
say which of them had left more of the filing unaccounted for.

WHAT THIS PAGE IS NOT, AND THE PROHIBITION IS STRUCTURAL RATHER THAN POLITE.

    NO RANKING. NO SORTING BY ANY COVERAGE FIGURE. NO AGGREGATE SCORE. NO HIGHLIGHTED WINNER.

    Rows are ordered by when the run was created and by nothing else. There is no comparison
    operator between two runs anywhere in this module, no threshold, and no cell whose styling
    depends on another row's value. `rules.md` section 21 rule 14 forbids selecting a parser, and
    a table sorted by a computed figure IS a selection: whatever the caption says, the reader takes
    the top row as the answer. `tests/unit/test_model_comparison.py` proves the ordering is
    insensitive to every figure on the page.

A STATUS IS NOT A SCORE EITHER. `MECHANICAL_COMPLETENESS_CANDIDATE` means one thing: the result
carries enough evidence to undergo human completeness review. A parse can pass all fourteen
conditions and be wrong about every number in the filing, because not one condition inspects
meaning. The page says so where the verdict is displayed, not only here.

THE SILENTLY OMITTED COUNT IS THE MOST IMPORTANT FIGURE AND IS RENDERED AS SUCH. A span in that
count is filing content the model never mentioned in any form — not cited, not declared unresolved,
not excluded by a reviewer. It is precisely the omission a reference rate cannot see, and it is the
one number on the page that a reviewer must not be able to miss. It is never carried by colour
alone: the cell reads SILENTLY OMITTED in words.

A RUN THAT NEVER PRODUCED A PARSE GETS A ROW SAYING SO. Many preserved runs failed at preflight or
at the provider with zero parts. Printing `0 of 1,750 covered` for one of them would read as a
measurement of a model that never answered, and hiding it would be worse. The row states what
happened and withholds the figures it does not have.

EVERY VALUE IS ESCAPED, INCLUDING THE ONES A MODEL CHOSE AND THE ONES A PROVIDER WROTE. A part
identifier, a table title, a cell's text, a coverage anchor and a provider error message are all
strings produced after reading an untrusted filing. They go through `html.esc` without exception —
this page exists to display attacker-influenceable bytes and hands none of them to a markup parser.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from packages.completeness import (
    BenchmarkTruth,
    CellOutcome,
    Condition,
    Disposition,
    ResolvedClaim,
    TableValidation,
    classify_cell,
    source_cell_text,
)
from packages.source_inventory import FilingInventory, TableElement

from .benchmark_view import (
    SPAN_TEXT_CHARACTERS,
    base_path,
    filing_heading,
    page_navigation,
    source_element_grid,
)
from .html import badge, each, esc, join, tag, url, warning
from .job_view import raw_pane

if TYPE_CHECKING:  # pragma: no cover - a typing edge, deliberately not a runtime one
    # THE RENDERER DOES NOT IMPORT THE ORCHESTRATION LAYER AT RUNTIME. `MeasuredRun` is a data
    # record and this module reads it; importing `packages.orchestrator` for real would pull the
    # provider gateway, the spend journal and the scheduler into a package whose entire job is
    # turning values into markup. The annotation is enough for the type check and costs nothing.
    from packages.orchestrator import MeasuredRun

#: How many silently omitted spans one detail page lists. The count is authoritative and is stated
#: beside the window: a silently shortened view of an omission list is the same defect as a
#: silently shortened request, and this is the list a reviewer most needs to look at.
OMITTED_SPANS_SHOWN: int = 200

#: How many structured tables one detail page places beside their source elements. Each renders two
#: full grids, and a parse emitting forty of them would otherwise produce a page measured in
#: megabytes.
TABLES_SHOWN: int = 40

#: How the four independent state dimensions are coloured. None of them is a score, so none of them
#: is coloured as one — `ok` here means "this dimension reports the unremarkable value", never
#: "this run is better".
_STATE_KIND = {
    "INVOKED": "ok",
    "CONVERGED": "ok",
    "RAW_PARSEABLE": "ok",
    "READY_FOR_REVIEW": "ok",
    "REPAIR_PARSEABLE": "warn",
    "INTERRUPTED": "warn",
    "TRUNCATED": "warn",
    "INCOMPATIBLE": "warn",
    "QUEUED": "neutral",
    "NOT_RUN": "neutral",
    "CANCELLED": "neutral",
    "UNPARSEABLE": "bad",
    "PROVIDER_FAILED": "bad",
    "CREDENTIAL_BLOCKED": "bad",
    "FAILED": "bad",
}

_COMPARISON_HEADERS = (
    "model",
    "region or profile",
    "source input",
    "execution",
    "serialization",
    "convergence",
    "visible spans covered",
    "silently omitted",
    "structured tables",
    "table validations",
    "cells not in source",
    "members accounted",
    "images accounted",
    "measured cost",
    "gate",
)


def models_base(cik: str, accession: str) -> tuple[str, ...]:
    """The URL prefix the comparison surface hangs from."""
    return (*base_path(cik, accession), "models")


def _state(value: Any) -> str:
    text = getattr(value, "value", str(value))
    return badge(text, _STATE_KIND.get(text, "neutral"))


def _withheld(reason: str) -> str:
    """A cell for a figure this run does not have, saying which figure is missing and why.

    NEVER A ZERO AND NEVER A DASH ALONE. `0` in a coverage column is a measurement; a run that
    never produced a parse has not made one, and printing zero would put an accusation against a
    model into a column a reader scans for exactly that.
    """
    return tag("span", esc(reason), class_="hint")


# --- the comparison table -----------------------------------------------------------------------


def _figure_cells(run: MeasuredRun) -> str:
    """The nine measured columns of one row, or the reason each is absent."""
    if run.ledger is None:
        return join(*[tag("td", _withheld("no ledger")) for _ in range(9)])
    if not run.parse_exists:
        return join(*[tag("td", _withheld("no parse")) for _ in range(9)])

    coverage = run.ledger.coverage
    tables = run.ledger.table_state
    images = run.ledger.image_state
    return join(
        tag(
            "td",
            esc(
                f"{coverage.spans_covered:,} of {coverage.spans_total:,} "
                f"({coverage.spans_percent}%)"
            ),
        ),
        tag(
            "td",
            badge(f"{coverage.spans_silently_omitted:,} SILENTLY OMITTED", "bad")
            if coverage.spans_silently_omitted
            else badge("0 silently omitted", "ok"),
            class_="omitted",
        ),
        tag(
            "td",
            esc(
                f"{tables.structured_emitted:,} emitted; "
                f"{tables.structured_source_resolved:,} resolved to a source element"
            ),
        ),
        tag("td", esc(f"{run.validations_passing:,} of {len(run.validations):,} passing")),
        tag("td", esc(f"{run.cells_missing_from_source:,}")),
        tag("td", esc(f"{coverage.members_accounted:,} of {coverage.members_total:,}")),
        tag("td", esc(f"{images.accounted:,} of {images.images_total:,}")),
        tag("td", esc(f"USD {run.cost_usd}")),
        tag("td", _gate_cell(run)),
    )


def _gate_cell(run: MeasuredRun) -> str:
    if run.gate is None:
        return _withheld("no gate verdict")
    passed = sum(1 for condition in run.gate.conditions if condition.passed)
    total = len(run.gate.conditions)
    return join(
        badge(run.gate.status, "ok" if run.gate.is_candidate else "warn"),
        tag("div", esc(f"{passed} of {total} conditions"), class_="hint"),
    )


def _run_rows(base: tuple[str, ...], run: MeasuredRun) -> str:
    """One run: a row of figures, and a row saying what happened to it.

    THE SECOND ROW IS NOT DECORATION. A run that failed at the provider carries no coverage figures
    and is still a recorded parse attempt against this filing; the sentence is the only thing on
    its row that says anything true about it.
    """
    profile = run.inference_profile_id or "no inference profile"
    figures = tag(
        "tr",
        join(
            tag(
                "td",
                join(
                    tag("a", esc(run.model_label), href=url(*base, run.run_id)),
                    tag("div", esc(f"{run.strategy} — {run.created_at[:19]}"), class_="hint"),
                ),
            ),
            tag("td", join(esc(run.region), tag("div", esc(profile), class_="hint"))),
            tag("td", esc(run.source_input_mode)),
            tag("td", _state(run.execution_state)),
            tag("td", _state(run.serialization)),
            tag("td", _state(run.convergence)),
            _figure_cells(run),
        ),
    )
    situation = tag(
        "tr",
        tag(
            "td",
            join(
                tag("span", esc(f"{run.run_id}: "), class_="mono"),
                esc(run.situation),
                tag("div", esc(run.refusal), class_="warning") if run.refusal else "",
            ),
            colspan=len(_COMPARISON_HEADERS),
            class_="hint",
        ),
    )
    return join(figures, situation)


def model_comparison_page(
    *,
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    runs: list[MeasuredRun],
    issuer_label: str,
) -> str:
    """Every recorded parse of one filing, one row each, in recorded order."""
    base = models_base(inventory.cik, inventory.accession)
    if not runs:
        body = tag(
            "div",
            join(
                tag("h2", "No run has been recorded against this filing"),
                tag(
                    "p",
                    esc(
                        "The mechanical inventory and the human classification of it exist and are "
                        "the denominator every parse of this filing will be measured against. "
                        "Nothing has been parsed yet, so there is nothing to compare — which is "
                        "reported here rather than as an empty table that reads as a measurement."
                    ),
                ),
            ),
            class_="card",
        )
    else:
        body = tag(
            "div",
            join(
                tag("h2", esc(f"{len(runs):,} recorded run(s), in the order they were created")),
                tag(
                    "p",
                    esc(
                        "Ordered by creation time and by nothing else. No column is sorted, no "
                        "figure is weighted, no row is highlighted and no run is recommended. Two "
                        "rows are two measurements against one denominator; deciding what they "
                        "mean is a person's work and is not done here."
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
                                tag(
                                    "tr",
                                    join(*[tag("th", header) for header in _COMPARISON_HEADERS]),
                                ),
                            ),
                            tag("tbody", each(runs, lambda run: _run_rows(base, run))),
                        ),
                    ),
                    class_="scroll-x",
                ),
            ),
            class_="card",
        )

    return join(
        filing_heading(inventory, truth),
        tag("p", esc(issuer_label)),
        page_navigation(base_path(inventory.cik, inventory.accession), "models"),
        # THE TABLE IS FIGURES; THE COMPARISON IS THE PARSES THEMSELVES. A reviewer deciding
        # between two models reads what each produced beside the filing, not a row of counts.
        tag(
            "p",
            tag(
                "a",
                "Compare two of these parses side by side, with the filing",
                href=url("benchmark", inventory.cik, inventory.accession, "compare"),
            ),
        )
        if runs
        else "",
        _what_this_measures_card(truth),
        body,
    )


def _what_this_measures_card(truth: BenchmarkTruth) -> str:
    return tag(
        "div",
        join(
            tag("h2", "What these figures are"),
            tag(
                "p",
                esc(
                    "Every row is measured against the same mechanical inventory of the same "
                    "preserved bytes, classified at benchmark truth version "
                    f"{truth.version}. A covered span is a span some resolved anchor or reference "
                    "reaches; it is NOT a claim that the model said anything correct about what is "
                    "inside it."
                ),
            ),
            tag(
                "p",
                esc(
                    "Correctness is unmeasured here and cannot be measured here. The gate's "
                    "strongest verdict, MECHANICAL_COMPLETENESS_CANDIDATE, means the result "
                    "carries enough evidence to undergo human completeness review. Only a person "
                    "may record the stronger statement, and it is scoped to this filing, this "
                    "source hash, this model, this model version, this region or profile, this "
                    "prompt version, these settings and this protocol."
                ),
                class_="hint",
            ),
        ),
        class_="card",
    )


# --- one run ------------------------------------------------------------------------------------


def model_run_page(
    *,
    inventory: FilingInventory,
    truth: BenchmarkTruth,
    run: MeasuredRun,
) -> str:
    """One recorded parse in full: the gate, the claims, the omissions, the tables, the unresolved."""
    base = models_base(inventory.cik, inventory.accession)
    return join(
        filing_heading(inventory, truth),
        page_navigation(base_path(inventory.cik, inventory.accession), "models"),
        tag(
            "h2",
            esc(f"{run.model_label} — run {run.run_id}"),
        ),
        tag(
            "p",
            join(
                tag("a", "back to every recorded run", href=url(*base)),
                tag("a", " the run's own page", href=url("runs", run.run_id)),
                tag(
                    "a",
                    " the parse itself",
                    href=url("runs", run.run_id, "jobs", run.job_id, "multipart")
                    if run.task_count
                    else url("runs", run.run_id, "jobs", run.job_id),
                ),
            ),
        ),
        _identity_card(run),
        _refusal_card(run),
        _gate_card(run),
        _claims_card(run),
        _omitted_card(inventory, run),
        _tables_card(inventory, run),
        _unresolved_card(run),
    )


def _identity_card(run: MeasuredRun) -> str:
    """Which model, where, how the filing reached it, and what the run ended up costing."""
    return tag(
        "div",
        join(
            tag("h2", "This run"),
            tag(
                "p",
                esc(
                    f"{run.model_label} in {run.region} "
                    f"({run.inference_profile_id or 'no inference profile'}); "
                    f"{run.strategy} protocol; source input {run.source_input_mode}; "
                    f"created {run.created_at}"
                ),
            ),
            tag(
                "p",
                join(
                    _state(run.execution_state),
                    " ",
                    _state(run.transport),
                    " ",
                    _state(run.serialization),
                    " ",
                    _state(run.convergence),
                ),
            ),
            tag(
                "p",
                esc(
                    f"{run.task_count:,} queued call(s); {run.part_documents:,} readable part "
                    f"artifact(s); USD {run.cost_usd} measured. {run.situation}"
                ),
            ),
            tag(
                "p",
                esc(
                    "The four states above are four independent dimensions and none of them is a "
                    "score. A run can have reached the provider, produced documents that would not "
                    "parse, covered most of the filing and stopped on a budget, and there is no "
                    "single word for that."
                ),
                class_="hint",
            ),
        ),
        class_="card",
    )


def _refusal_card(run: MeasuredRun) -> str:
    if not run.refusal:
        return ""
    return tag(
        "div",
        join(tag("h2", "No ledger could be computed"), warning(run.refusal)),
        class_="card",
    )


def _gate_card(run: MeasuredRun) -> str:
    """All fourteen conditions, each with its verdict and the evidence sentence behind it."""
    if run.gate is None:
        return ""

    def row(condition: Condition) -> str:
        return tag(
            "tr",
            join(
                tag("td", esc(str(condition.number))),
                tag("td", badge("passed", "ok") if condition.passed else badge("FAILS", "bad")),
                tag("td", esc(condition.name)),
                tag("td", esc(condition.detail)),
            ),
        )

    passed = sum(1 for condition in run.gate.conditions if condition.passed)
    return tag(
        "div",
        join(
            tag("h2", "The fourteen conditions"),
            tag(
                "p",
                join(
                    badge(run.gate.status, "ok" if run.gate.is_candidate else "warn"),
                    esc(f" {passed} of {len(run.gate.conditions)} conditions pass"),
                ),
            ),
            tag(
                "p",
                esc(
                    "Conjunctive on purpose. A weighted score would let a strong showing on twelve "
                    "dimensions outvote one silently omitted financial disclosure, and each "
                    "condition is a distinct way a parse can be unreviewable."
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
                            tag(
                                "tr",
                                join(
                                    *[
                                        tag("th", header)
                                        for header in ("", "verdict", "condition", "evidence")
                                    ]
                                ),
                            ),
                        ),
                        tag("tbody", each(run.gate.conditions, row)),
                    ),
                ),
                class_="scroll-x",
            ),
        ),
        class_="card",
    )


def _anchor_cell(outcome: Any, anchor: str) -> str:
    """One anchor, whether it resolved, and at which rung of the six-level ladder.

    THE LEVEL IS SHOWN BESIDE THE VERDICT RATHER THAN INSTEAD OF IT. An exact hit in the bytes as
    filed and a hit that needed markup stripped, entities decoded and whitespace collapsed are both
    resolutions and they are not the same evidence.
    """
    return tag(
        "td",
        join(
            badge(outcome.resolution.value, "ok" if outcome.resolved else "bad"),
            tag(
                "div",
                esc(
                    f"level {outcome.level}"
                    + (", markup stripped" if outcome.markup_stripped else "")
                    + (f", offset {outcome.offset:,}" if outcome.offset is not None else "")
                    + (f", {outcome.occurrences:,} occurrence(s)" if outcome.occurrences else "")
                ),
                class_="hint",
            ),
            tag("div", esc(anchor[:SPAN_TEXT_CHARACTERS])),
        ),
    )


def _claims_card(run: MeasuredRun) -> str:
    """Every coverage claim, its two anchors, and the interval the pair bounded.

    WHY A CLAIM HAS TWO ANCHORS AND NOT AN OFFSET. A model handed an artifact as text cannot count
    characters in it. It CAN quote the first sentence of a region and the last one, and both quotes
    either occur in the preserved bytes or they do not.
    """
    if run.ledger is None:
        return ""
    claims = run.ledger.resolved_claims

    def row(claim: ResolvedClaim) -> str:
        interval = claim.interval
        return tag(
            "tr",
            join(
                tag("td", tag("span", esc(claim.claim.part_id), class_="mono")),
                tag("td", tag("span", esc(claim.claim.member), class_="mono")),
                _anchor_cell(claim.start, claim.claim.start_anchor),
                _anchor_cell(claim.end, claim.claim.end_anchor),
                tag(
                    "td",
                    esc(f"{interval.start:,}–{interval.end:,} ({interval.length:,} characters)")
                    if interval is not None
                    else badge("bounds nothing", "bad"),
                ),
                tag(
                    "td",
                    join(
                        badge("model declared unresolved", "warn")
                        if claim.claim.unresolved
                        else "",
                        esc(claim.finding),
                    ),
                ),
            ),
        )

    bounded = sum(1 for claim in claims if claim.bounded)
    headers = ("part", "member", "start anchor", "end anchor", "interval bounded", "finding")
    return tag(
        "div",
        join(
            tag("h2", "Coverage claims"),
            tag(
                "p",
                esc(
                    f"{bounded:,} of {len(claims):,} claim(s) resolved to a bounded interval in "
                    "the preserved bytes. A claim with one resolving anchor bounds no region and "
                    "the part gets no credit for it, which is the honest outcome."
                ),
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
                        tag("tbody", each(claims, row)),
                    ),
                ),
                class_="scroll-x",
            )
            if claims
            else tag("p", "This parse made no coverage claim at all."),
        ),
        class_="card",
    )


def _omitted_card(inventory: FilingInventory, run: MeasuredRun) -> str:
    """The spans this parse never mentioned, with their offsets and their text.

    THE LIST A REVIEWER MOST NEEDS TO LOOK AT. Every other figure on this page can be argued about;
    a span in this list is filing content that the parse did not cite, did not declare unresolved
    and that nobody excluded. Showing the count without the text would leave a reviewer with a
    number they cannot check.
    """
    if run.ledger is None:
        return ""
    omitted = run.ledger.spans.ids(Disposition.SILENTLY_OMITTED)
    window = omitted[:OMITTED_SPANS_SHOWN]

    def row(span_id: str) -> str:
        span = inventory.span(span_id)
        if span is None:
            return tag(
                "tr",
                join(
                    tag("td", tag("span", esc(span_id), class_="mono")),
                    tag("td", "—"),
                    tag("td", "—"),
                    tag("td", esc("this span is no longer in the inventory")),
                ),
            )
        text = span.normalized_text[:SPAN_TEXT_CHARACTERS]
        clipped = (
            tag(
                "p",
                esc(
                    f"showing {len(text):,} of {len(span.normalized_text):,} normalised characters"
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
                tag("td", tag("span", esc(span.member), class_="mono")),
                tag("td", esc(f"{span.start:,}–{span.end:,} ({span.character_count:,})")),
                tag("td", join(tag("div", esc(text)), clipped)),
            ),
        )

    if not omitted:
        inner: str = tag(
            "p",
            esc(
                "Not one visible span of this filing is silently omitted by this parse. That is a "
                "statement about coverage and about nothing else."
            ),
        )
    else:
        inner = join(
            tag(
                "p",
                esc(
                    f"showing {len(window):,} of {len(omitted):,} silently omitted span(s). Each "
                    "is a source range this parse did not cite, did not declare unresolved, and "
                    "that no reviewer excluded."
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
                                        for header in ("span", "member", "offsets", "text")
                                    ]
                                ),
                            ),
                        ),
                        tag("tbody", each(window, row)),
                    ),
                ),
                class_="scroll-x",
            ),
        )
    return tag(
        "div",
        join(tag("h2", "Silently omitted source spans"), inner),
        class_="card",
    )


def _model_grid(table: Any, element: TableElement | None) -> str:
    """The model's own grid, with every cell that is nowhere in the source element marked.

    THE SAME RULE THE VALIDATOR COUNTED. `classify_cell` is the function `validate_table` uses, so
    the cells marked here are exactly the cells the `cells not in source` figure counted. A page
    that reimplemented the comparison would eventually mark a different set and nothing would say
    which was right.

    POSITIONS ARE AS THE MODEL DECLARED THEM AND THE GRID IS NOT RECONSTRUCTED. A cell spanning two
    rows appears once, at its origin. Emitting HTML `rowspan` on top of that would place the same
    cell twice and show a reviewer a grid that is not the one the validator checked.
    """
    cells = tuple(getattr(table, "cells", ()) or ())
    if not cells:
        return tag("p", "This table carries no cell.", class_="hint")
    source_text = source_cell_text(element) if element is not None else ""
    rows: dict[int, list[Any]] = {}
    for cell in cells:
        rows.setdefault(cell.row, []).append(cell)
    body = []
    for index in sorted(rows):
        rendered = []
        for cell in sorted(rows[index], key=lambda c: c.column):
            outcome = classify_cell(
                cell, source_text=source_text, source_present=element is not None
            )
            marker = (
                badge("NOT IN SOURCE", "bad")
                if outcome is CellOutcome.MISSING
                else badge("unresolved", "warn")
                if outcome is CellOutcome.UNRESOLVED
                else ""
            )
            span_note = (
                tag("span", esc(f" [{cell.row_span}×{cell.column_span}]"), class_="hint")
                if cell.row_span > 1 or cell.column_span > 1
                else ""
            )
            rendered.append(
                tag("th" if cell.is_header else "td", join(esc(cell.text), span_note, marker))
            )
        body.append(tag("tr", join(*rendered)))
    return tag("div", tag("table", tag("tbody", join(*body))), class_="scroll-x")


def _table_node(inventory: FilingInventory, table: Any, validation: TableValidation | None) -> str:
    """One structured table beside the mechanical source element it claims to represent."""
    source_id = str(getattr(table, "source_table_id", "") or "")
    element = inventory.table(source_id) if source_id else None
    verdict = (
        join(
            badge("validation passes", "ok")
            if validation.passes
            else badge("validation FAILS", "bad"),
            " ",
            badge(f"{validation.cells_text_found:,} cell text(s) found in source", "neutral"),
            " ",
            badge(f"{validation.cells_text_missing:,} not in source", "bad")
            if validation.cells_text_missing
            else "",
            " ",
            badge(f"{validation.cells_unresolved:,} declared unresolved", "warn")
            if validation.cells_unresolved
            else "",
        )
        if validation is not None
        else badge("no validation recorded", "neutral")
    )
    return tag(
        "div",
        join(
            tag(
                "div",
                esc(
                    f"{getattr(table, 'type_label', '') or 'no type'} — {source_id or 'no source'}"
                ),
                class_="kind",
            ),
            tag("div", esc(getattr(table, "title", "") or "(no title)"), class_="title"),
            tag("p", verdict),
            each(getattr(validation, "findings", ()) or (), warning),
            tag(
                "div",
                join(
                    tag(
                        "section",
                        join(
                            tag("h3", "What the model returned"),
                            _model_grid(table, element),
                        ),
                    ),
                    tag(
                        "section",
                        join(
                            tag("h3", "The mechanical source element"),
                            source_element_grid(element)
                            if element is not None
                            else tag(
                                "p",
                                esc(
                                    "This table names no table element that exists in the "
                                    "preserved bytes, so no cell of it can be checked against a "
                                    "source at all."
                                ),
                                class_="hint",
                            ),
                        ),
                    ),
                ),
                class_="panes",
            ),
        ),
        class_="node",
    )


def _tables_card(inventory: FilingInventory, run: MeasuredRun) -> str:
    """Every structured table this parse emitted, beside the element it claims to represent."""
    tables = run.tables
    validations = {v.table_id: v for v in run.validations}
    window = tables[:TABLES_SHOWN]
    if not tables:
        inner: str = tag(
            "p",
            esc(
                "This parse emitted no structured table. That is a measured fact about what the "
                "model returned and not a compliance failure: no prompt in this phase asks for "
                "one."
            ),
        )
    else:
        inner = join(
            tag(
                "p",
                esc(
                    f"showing {len(window):,} of {len(tables):,} structured table(s). The left "
                    "grid is what the model returned; the right one is what the mechanical walk "
                    "read out of the source element it names."
                ),
            ),
            each(
                window,
                lambda table: _table_node(
                    inventory, table, validations.get(str(getattr(table, "table_id", "") or ""))
                ),
            ),
        )
    return tag("div", join(tag("h2", "Structured tables"), inner), class_="card")


def _unresolved_card(run: MeasuredRun) -> str:
    """What the model itself said it could not resolve. Carried as the model's own words."""
    items = run.unresolved_items
    if not items:
        return tag(
            "div",
            join(
                tag("h2", "Model-declared unresolved items"),
                tag("p", "This parse declared nothing unresolved."),
            ),
            class_="card",
        )

    def item(entry: dict[str, Any]) -> str:
        return tag(
            "li",
            esc(
                "; ".join(
                    f"{key}: {value}"
                    for key, value in sorted(entry.items())
                    if value not in (None, "", [], {})
                )
                or "an empty unresolved entry"
            ),
        )

    return tag(
        "div",
        join(
            tag("h2", "Model-declared unresolved items"),
            tag(
                "p",
                esc(
                    f"{len(items):,} item(s). An explicitly unresolved region is not an omission: "
                    "the model said it could not finish it, and the ledger records that rather "
                    "than counting the region as content that vanished."
                ),
            ),
            tag("ul", each(items, item), class_="refs"),
        ),
        class_="card",
    )


# --- two parses of one filing, side by side ------------------------------------------------------


def _pane_pair(*, label: str, source: str, filename: str, parsed: str, note: str) -> str:
    """One model's row: the preserved source on the left, what that model made of it on the right."""
    return tag(
        "div",
        join(
            tag(
                "div",
                join(
                    tag("h2", esc(label)),
                    tag("p", esc(note), class_="hint") if note else "",
                ),
                class_="compare-head",
            ),
            tag("div", source, class_="compare-source"),
            tag("div", parsed, class_="compare-parsed"),
        ),
        class_="compare-row",
    )


def comparison_panes(
    *,
    cik: str,
    accession: str,
    issuer_label: str,
    form_as_filed: str,
    filename: str,
    source_text: str,
    left: dict[str, Any],
    right: dict[str, Any],
    choices: Sequence[dict[str, Any]],
) -> str:
    """Two models' parses of ONE filing, each beside the filing, in four panes.

    WHY FOUR PANES AND NOT THREE. The preserved bytes are identical for both models — every run of
    this accession carries the same `source_set_id`, and that is verified rather than assumed — so a
    single shared source pane would show the same characters. It is still rendered TWICE, because
    the two panes scroll independently: a reviewer parks each one at the passage its own parse is
    discussing, and comparing part 14 of one model against part 31 of another is the entire job.
    One shared pane forces the two comparisons to happen at the same scroll offset, which is exactly
    the position they are never both interesting at.

    THIS PAGE RANKS NOTHING AND RECOMMENDS NOTHING. No score, no winner, no ordering by any figure —
    `rules.md` section 21 rule 14, and the same prohibition `model_comparison_page` already carries.
    The reader chooses both sides and the page shows what each model produced.

    IT IS A COMPARISON SURFACE, NOT A SELECTION ONE. The product chooses a parsing model PER JOB —
    `docs/architecture/product-definition.md`: the user chooses each role independently, for every
    job — so nothing here advances a candidate, retires one, or records a preference. Comparing two
    parses is the feature; crowning one was never in the product.

    EITHER SIDE MAY BE ABSENT AND SAYS SO. A model whose parse produced no node is shown with that
    fact rather than omitted, because "this model returned nothing for this filing" is one of the
    more useful answers this page can give.
    """
    return join(
        tag("h1", esc(f"Compare parses — {form_as_filed} {accession}")),
        tag("p", esc(f"{issuer_label} — CIK {cik}")),
        _compare_chooser(cik, accession, choices, left, right),
        tag(
            "div",
            join(
                _pane_pair(
                    label=str(left.get("label") or "left"),
                    source=raw_pane(
                        filename=filename, text=source_text, focus=None, focus_length=1
                    ),
                    filename=filename,
                    parsed=str(left.get("parsed") or ""),
                    note=str(left.get("note") or ""),
                ),
                _pane_pair(
                    label=str(right.get("label") or "right"),
                    source=raw_pane(
                        filename=filename, text=source_text, focus=None, focus_length=1
                    ),
                    filename=filename,
                    parsed=str(right.get("parsed") or ""),
                    note=str(right.get("note") or ""),
                ),
            ),
            class_="compare-grid",
        ),
    )


def _compare_chooser(
    cik: str,
    accession: str,
    choices: Sequence[dict[str, Any]],
    left: dict[str, Any],
    right: dict[str, Any],
) -> str:
    """Two selects and a submit. A GET form, so a chosen pair is a URL a reviewer can send.

    IN THE ORDER THE HANDLER RESOLVED THEM, NEVER ORDERED BY A FIGURE. A dropdown sorted by node
    count would rank the candidates in the one control whose whole purpose is letting a person pick
    without being steered.
    """

    def select(name: str, chosen: dict[str, Any]) -> str:
        current = str(chosen.get("run_id") or "")
        return tag(
            "select",
            each(
                choices,
                lambda c: tag(
                    "option",
                    esc(f"{c['label']} — {c['nodes']} node(s) — {c['run_id']}"),
                    value=str(c["run_id"]),
                    selected="selected" if str(c["run_id"]) == current else None,
                ),
            ),
            name=name,
            id=f"compare-{name}",
        )

    return tag(
        "form",
        join(
            tag("label", "Left", for_="compare-a"),
            select("a", left),
            tag("label", "Right", for_="compare-b"),
            select("b", right),
            tag("button", "Compare", type="submit", class_="run-button"),
        ),
        method="get",
        action=url("benchmark", cik, accession, "compare"),
        class_="compare-chooser",
    )
