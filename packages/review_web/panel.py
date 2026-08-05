"""The panel's review menu: every step of the parse in front of you, as ordinary links.

WHY A MENU AND NOT A WORKLIST. The parse this UI was built to review is 77 provider calls of one
filing, and the first shape tried for the panel was a flat list of all 77. A flat list of 77 rows in
a 320-pixel column is not navigation: it is the same scrolling problem moved to a narrower place. So
the panel names the SEVEN QUESTIONS a reviewer asks of a parse, in the order that puts the cheap and
decisive ones first, and offers exactly two positions into the call list — the next call nobody has
opened, and the next call carrying evidence. The list itself is one click away and never moves.

THE ORDER OF THE STEPS IS AN ARGUMENT, NOT A STATE MACHINE. Nothing here is gated on anything else,
the server enforces no workflow, and every step is a link a reader may take in any order. Steps 2, 3
and 4 come before step 5 because they are cheap and can make reading 77 parts unnecessary; step 7 is
last because a verdict recorded before the evidence is what this whole surface exists to prevent.

WHAT THIS MODULE REFUSES TO DO.

    IT COMPUTES NOTHING. Every value it renders is a plain string, integer or mapping already in
    `PanelContext`, put there by the handler that had the records in hand. The prohibition is
    measured rather than stylistic: `ParserReviewService.inventoried_filing` memoises only
    `build_inventory` and calls `assemble_source_set` unconditionally on every invocation, so a
    panel that reached it would re-assemble and re-walk a multi-megabyte submission on every one of
    the 77 task pages of a single parse. Nothing here imports `packages.orchestrator`,
    `packages.completeness` or `packages.source_inventory`, at runtime or under `TYPE_CHECKING`.

    IT CARRIES NO COVERAGE FIGURE AND NO LEDGER NUMBER. `206 SILENTLY OMITTED`, `1,544 of 1,750`
    and `88.23%` each need the mechanical inventory AND the anchor ladder over ~900,000 characters.
    They belong on the ledger page, which is the page that pays for them; steps 2, 3 and 4 name that
    page in words and say where the figure is computed instead of printing one here.

    IT NEVER PRINTS A ZERO IT DID NOT MEASURE. A figure the context does not carry renders as no
    figure at all — the discipline `model_comparison_view._withheld` already applies, for the same
    reason: a zero in a count position is a measurement, and a fabricated one is an accusation.

    IT NEVER LINKS INTO A 404. A filing outside the benchmark catalog has no inventory and no truth
    document, so the four filing destinations and steps 2, 3 and 4 render as visibly unavailable
    spans carrying the reason. `ReviewApp._benchmark_href` already performs exactly this check, and
    its docstring gives the rule: a link that 404s is worse than one that is visibly unavailable.

    IT HAS NO FORM AND NO BILLABLE CONTROL. Every entry is a GET. The four queue actions that spend
    money stay POST buttons on the page beside the hierarchy they act on, because a link is
    something a browser can be made to follow.

EVERY VALUE IS ESCAPED, INCLUDING THE ONES A MODEL CHOSE. A part identifier is a string a language
model wrote after reading an untrusted filing, and an issuer label and a form string come out of
bytes SEC published. All of them reach the page through `html.esc` or through `nav.destination`,
which escapes everything it is given except the already-built opened marker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from . import progress
from .html import esc, join, tag, url
from .nav import FILING, PARSE, destination, scope_marker, with_query

# --- the attention items this menu can name -----------------------------------------------------
#
# These are the literals of the closed attention item set, spelled where they are rendered. They are
# NOT re-derived from a URL: an item is the durable key a reader's opened mark is stored under,
# and a key computed from a path would move the moment a route did, orphaning every mark.

_HUB: Final[str] = "hub"
_HIERARCHY: Final[str] = "hierarchy"
_ASSEMBLED: Final[str] = "assembled"
_READ_SIDE_BY_SIDE: Final[str] = "read-side-by-side"

#: The three ways one job's artifact is read, as (label, `view` query value, attention item).
_READ_VIEWS: Final[tuple[tuple[str, str, str], ...]] = (
    ("Side by side", "side-by-side", _READ_SIDE_BY_SIDE),
    ("Raw source", "raw", "read-raw"),
    ("Parsed", "parsed", "read-parsed"),
)

#: The seven pages of one filing's completeness surface, as (label, path segment, attention item).
#: The overview's segment is empty because it IS the surface's root; `html.url` drops empty parts.
_FILING_PAGES: Final[tuple[tuple[str, str, str], ...]] = (
    ("Completeness overview", "", "overview"),
    ("Source inventory", "inventory", "inventory"),
    ("Spans", "spans", "spans"),
    ("Tables", "tables", "tables"),
    ("Images", "images", "images"),
    ("Every parse", "models", "models"),
    ("Judgements", "judgements", "judgements"),
)

#: Why a filing destination is unavailable. Stated in full beside every entry it disables rather
#: than once at the top of the block: a reader who scans to the entry they want is the reader who
#: needs the reason, and a legend three inches away is a legend nobody reads.
_NO_BENCHMARK: Final[str] = (
    "this filing is not in the benchmark catalog, so it has no denominator to measure against"
)

#: A call whose state alone says something happened that a reviewer has to look at. Kept as a closed
#: set rather than a predicate over the state machine, because this module never imports it.
_EVIDENCE_STATES: Final[frozenset[str]] = frozenset(
    {"TRUNCATED", "FAILED", "BLOCKED", "INTERRUPTED"}
)

#: The separator every count line in this UI uses, matching `progress`.
_SEPARATOR: Final[str] = " · "


# --- the records the handler hands over ----------------------------------------------------------


@dataclass(frozen=True)
class TaskRow:
    """One call of a multipart parse, flattened to plain values before it reaches this module.

    THE RENDERER NEVER SEES AN ENUM AND NEVER SEES A STORE RECORD. `state` and `task_type` are the
    strings a `MultipartTask` mapping already carries, and `superseded_by` is what
    `packages.multipart.resolve_effective` resolved in the handler — flattened to a task id, so that
    the one place in the application that knows a `FORMAT_REPAIR` supersedes a `PARSE_PART` stays
    the one place that decides it.

    `fingerprint` IS THE VERSION THIS CALL CARRIES RIGHT NOW, computed by the handler from durable
    record fields only. An empty one means the version is unknown, and `progress` renders no marker
    at all rather than guessing `not opened` about a reader nobody measured.
    """

    task_id: str
    part_id: str = ""
    task_type: str = ""
    state: str = ""
    order: int = 0
    depth: int = 0
    attempt_count: int = 0
    idempotency: str = ""
    superseded_by: str = ""
    has_findings: bool = False
    commented: bool = False
    fingerprint: str = ""


@dataclass(frozen=True)
class ParseRow:
    """One recorded parse of one filing, in the order it was recorded and with no figure attached.

    NO COVERAGE FIGURE, NO RANK AND NO SCORE IS CARRIED HERE, and that is structural rather than
    polite: `rules.md` section 21 rule 14 forbids selecting a parser, and a list ordered by a
    computed figure IS a selection whatever its caption says. The two states are carried because the
    stored job record has them; this menu shows the model's name and nothing else.
    """

    run_id: str
    job_id: str = ""
    model_label: str = ""
    created_at: str = ""
    execution_state: str = ""
    review_state: str = ""


@dataclass(frozen=True)
class PanelContext:
    """Everything the review menu renders from, and the boundary that keeps it cheap.

    BUILT BY THE HANDLER, WHICH IS THE ONLY PLACE THE RECORDS ARE ALREADY IN HAND. Every field is a
    plain value, a plain mapping, or a tuple of the two flat records above. Nothing is inferred here
    and nothing is fetched here, so rendering the panel costs no store walk, no source assembly and
    no inventory build — the cost that would otherwise be paid on every page of a 77-call parse.

    AN EMPTY COLLECTION MEANS THE HANDLER DID NOT LOAD IT, NEVER THAT IT IS EMPTY. `tasks` empty is
    a page that did not pay for the task manifests, and the blocks that need them are omitted rather
    than rendered with zeros; `parses` empty is a page that did not already resolve them, and only
    the two pages whose handlers resolve them anyway pass a non-empty tuple.
    """

    subject: str
    # --- parse subject ---------------------------------------------------------------------------
    run_id: str = ""
    job_id: str = ""
    form_as_filed: str = ""
    accession: str = ""
    cik: str = ""
    issuer_label: str = ""
    model_label: str = ""
    strategy: str = ""
    created_at: str = ""
    review_state: str = ""
    benchmark_held: bool = False
    session: dict[str, Any] = field(default_factory=dict)
    assembly: dict[str, Any] | None = None
    tasks: tuple[TaskRow, ...] = ()
    opened: dict[str, frozenset[str]] = field(default_factory=dict)
    current_item: str = ""
    current_task_id: str = ""
    # --- filing subject --------------------------------------------------------------------------
    parses: tuple[ParseRow, ...] = ()
    source_set_sha256: str = ""


# --- fragments every block shares ----------------------------------------------------------------


def _spaced(*parts: str) -> str:
    """Join rendered fragments with one space so two inline elements never abut.

    The same reason `nav` keeps its own: without it a link and the marker beside it read as one
    run-on string the moment the stylesheet that separates them is not there, which is the state
    every marker on this surface is written to survive.
    """
    return " ".join(part for part in parts if part)


def _section(title: str, body: str) -> str:
    """One titled block of the menu. The heading is a real `h2`, in document order."""
    return tag("div", join(tag("h2", esc(title)), body), class_="panel-section")


def _unavailable(label: str, reason: str, *, scope: str = "") -> str:
    """A destination this page cannot offer: visibly unavailable, with WHY, never hidden.

    A CONTROL THAT APPEARS AND DISAPPEARS IS ONE NOBODY CAN LEARN — the rule `views.tabs` states and
    `ReviewApp._benchmark_href` already enforces. The reason travels beside the label rather than in
    a `title`, because a tooltip does not exist on touch and is invisible to a keyboard.
    """
    return _spaced(
        scope_marker(scope),
        tag("span", esc(label), class_="step-disabled", aria_disabled="true"),
        tag("span", esc(reason), class_="hint"),
    )


def _anchored(href: str, fragment: str) -> str:
    """`href` with one of this module's literal fragments appended.

    The href arrived percent-encoded from `html.url` and the fragment is a constant written here, so
    there is nothing to encode and nothing to escape twice; `html.attributes` applies the single
    HTML escape when it reaches the element.
    """
    return href + "#" + fragment


def _opened_marker(context: PanelContext, item: str, fingerprint: str = "") -> str:
    """The three-word marker for one destination, or nothing when its version is unknown.

    THE PANEL MARKS WHAT IT CAN FINGERPRINT, WHICH TODAY IS A CALL AND NOTHING ELSE. A destination's
    marker needs the version that destination carries right now, and `PanelContext` carries one only
    per `TaskRow`. The job-scoped and filing-scoped items — the hub, the three read views, the seven
    completeness pages — are fingerprinted from `job.updated_at`, the artifact filename and the
    inventory's source-set hash, none of which is a field of this record.

    SO THEY RENDER NO MARKER, AND THAT IS THE HONEST RENDERING RATHER THAN A GAP. `progress.marker`
    returns nothing for an empty fingerprint by design: without the current version there is no way
    to tell a live mark from a superseded one, and printing `not opened` beside a page the reader
    read yesterday would be exactly the dishonesty the three-word vocabulary exists to prevent.
    """
    return progress.marker(item, fingerprint, context.opened)


def _figures(*terms: str) -> str:
    """The present terms of a count line, joined; nothing at all when none of them is present.

    A COUNT THE RECORD DOES NOT CARRY IS ABSENT, NEVER ZERO. Every caller passes the result of
    `_figure`, which returns the empty string for a key a stored mapping does not hold, so a job
    record written before a field existed produces a shorter line instead of a fabricated `0 calls`.
    """
    return _SEPARATOR.join(term for term in terms if term)


def _figure(value: Any, noun: str) -> str:
    """One stored integer with its noun — `77 calls` — or nothing when the record has no figure.

    A value that is absent or is not an integer yields the empty string. It is never coerced to
    zero: a stored mapping missing `truncated` has not told us there were no truncations.
    """
    if value is None or isinstance(value, bool):
        return ""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return ""
    return f"{count:,} {noun}"


# --- block 1: what is being reviewed -------------------------------------------------------------


def _reviewing_block(context: PanelContext) -> str:
    """The filing, the issuer and the invocation, as three lines of text, plus the hub.

    THREE LINES OF TEXT AND ONE LINK, DELIBERATELY. This block answers "what am I looking at" and
    nothing else; every identifier in it is text because a reviewer who is already on the page does
    not need four more ways to leave it. The hub is the exception: it is where the verdict is
    recorded, and it is one click from every page of the parse.
    """
    filing = " ".join(part for part in (context.form_as_filed, context.accession) if part)
    issuer = " — ".join(
        part for part in (context.issuer_label, f"CIK {context.cik}" if context.cik else "") if part
    )
    invocation = _SEPARATOR.join(
        part
        for part in (
            context.model_label,
            context.strategy,
            f"created {context.created_at}" if context.created_at else "",
        )
        if part
    )
    hub = url("runs", context.run_id, "jobs", context.job_id, "review")
    return _section(
        "Reviewing",
        join(
            tag("p", esc(filing)) if filing else "",
            tag("p", esc(issuer), class_="hint") if issuer else "",
            tag("p", esc(invocation), class_="hint") if invocation else "",
            tag(
                "p",
                destination(
                    "the parse hub",
                    hub,
                    kind="page",
                    marker=_opened_marker(context, _HUB),
                ),
            ),
        ),
    )


# --- block 2: the seven steps --------------------------------------------------------------------


def _step(context: PanelContext, *, item: str, body: str) -> str:
    """One numbered step. The step whose destination IS this page is marked current, three ways.

    `aria-current="step"`, the filled surface the stylesheet gives that attribute, and a leading
    glyph in the markup — never colour alone, and never a glyph alone either, since the step's own
    label is the word beside it.

    ONE PAGE MAY BE THE DESTINATION OF TWO STEPS AND BOTH ARE THEN CURRENT. The hierarchy is step 1
    and step 5, and the ledger is steps 2, 3 and 4 at three fragments of one page load. Marking one
    of them current and not the others would need a distinction the URL does not carry, and
    inventing one would put a claim about where the reader is onto the page.
    """
    current = bool(item) and item == context.current_item
    return tag(
        "li",
        join(tag("span", "&#9656; ", aria_hidden="true") if current else "", body),
        aria_current="step" if current else None,
    )


def _step_what_happened(context: PanelContext, base: tuple[str, ...]) -> str:
    """Step 1. The call hierarchy for a multipart parse; the response itself for a single one.

    `job.multipart` IS `{}` FOR A SINGLE-RESPONSE JOB AND THAT IS NOT AN ERROR. Thirty preserved
    runs used the single-response protocol and both protocols stay runnable, so the step names what
    actually happened — one response — and points at the page that shows it, instead of offering a
    hierarchy of one row.
    """
    session = context.session
    if not session:
        return _step(
            context,
            item=_READ_SIDE_BY_SIDE,
            body=destination(
                "What happened when it ran",
                url(*base, view="side-by-side"),
                kind="page",
                count="one response · the single-response protocol",
                marker=_opened_marker(context, _READ_SIDE_BY_SIDE),
            ),
        )
    return _step(
        context,
        item=_HIERARCHY,
        body=destination(
            "What happened when it ran",
            url(*base, "multipart"),
            kind="page",
            count=_figures(
                _figure(session.get("task_count"), "calls"),
                _figure(session.get("truncated"), "truncated"),
            ),
            marker=_opened_marker(context, _HIERARCHY),
        ),
    )


def _ledger_step(context: PanelContext, label: str, fragment: str) -> str:
    """Steps 2, 3 and 4: three questions of the ledger, at three fragments of ONE page load.

    THE FIGURE IS NAMED AND NOT SHOWN. Every one of the three — silently omitted spans, resolved
    citations, cells located in the source — needs the filing's mechanical inventory and the anchor
    ladder, which is tens of seconds of work over ~900,000 characters. Printing one here would buy a
    number on the panel at the price of that walk on every page of the parse, so the step says where
    the number is computed and links there.

    A FILING WITH NO BENCHMARK HAS NO DENOMINATOR, so there is no ledger to link to and the step is
    a disabled span carrying that sentence rather than a link into a 404.
    """
    if not context.benchmark_held:
        return _step(context, item="", body=_unavailable(label, _NO_BENCHMARK, scope=FILING))
    ledger = url("benchmark", context.cik, context.accession, "models", context.run_id)
    return _step(
        context,
        # THE LEDGER'S ATTENTION ITEM IS THE RUN IDENTIFIER, which is what the store issues for one
        # parse's ledger. It is not a literal of the closed item set and is not spelled as one.
        item=context.run_id,
        body=destination(
            label,
            _anchored(ledger, fragment),
            kind="page",
            scope=FILING,
            marker=_opened_marker(context, context.run_id),
        ),
    )


def _step_read_the_parts(context: PanelContext, base: tuple[str, ...]) -> str:
    """Step 5. The unbounded one, placed after everything that might make it unnecessary."""
    return _step(
        context,
        item=_HIERARCHY,
        body=destination(
            "Read the parts",
            url(*base, "multipart", show="unopened"),
            kind="page",
            count=_opened_count_sentence(context, noun="calls"),
            marker=_opened_marker(context, _HIERARCHY),
        ),
    )


def _step_could_not_do(context: PanelContext, base: tuple[str, ...]) -> str:
    """Step 6. What the model itself declared it could not resolve, and what was cut off.

    The two figures come from the stored assembly and cost nothing to read. A parse with no assembly
    written yet shows neither, rather than showing `0 unresolved` about work that never finished.
    """
    assembly = context.assembly or {}
    return _step(
        context,
        item=_ASSEMBLED,
        body=destination(
            "What it said it could not do",
            _anchored(url(*base, "assembled"), "unresolved"),
            kind="page",
            count=_figures(
                _figure(assembly.get("unresolved_item_count"), "unresolved"),
                _figure(assembly.get("truncation_events"), "truncation event(s)"),
            ),
            marker=_opened_marker(context, _ASSEMBLED),
        ),
    )


def _step_record_the_verdict(context: PanelContext, base: tuple[str, ...]) -> str:
    """Step 7, last, because a verdict recorded before the evidence is what this surface prevents.

    THE REVIEW STATE IS SHOWN AND THE TRANSITION COUNT IS NOT. `review_history` is empty on all
    seven recorded parses, so `0 transitions` would be true today and would be a fabricated zero
    the moment a context reached this module without the history — and the history is not a field
    of `PanelContext`. The hub, which loads the job record, is where that count belongs.
    """
    return _step(
        context,
        item=_HUB,
        body=destination(
            "Record the verdict",
            _anchored(url(*base, "review"), "verdict"),
            kind="anchor",
            count=context.review_state,
            marker=_opened_marker(context, _HUB),
        ),
    )


def _steps_block(context: PanelContext) -> str:
    """The seven questions, numbered, in the order that puts the decisive ones first.

    IT IS A LAYOUT OPINION AND NOT A WORKFLOW. No step is gated on another, the server enforces no
    order, and an `ol` is used because the steps are argued in a sequence — not because a reader who
    takes them out of order is doing anything wrong.
    """
    base = ("runs", context.run_id, "jobs", context.job_id)
    return _section(
        "The seven steps",
        tag(
            "ol",
            join(
                _step_what_happened(context, base),
                _ledger_step(context, "What it never mentioned", "omitted"),
                _ledger_step(context, "Whether its citations exist", "claims"),
                _ledger_step(context, "Whether its numbers exist", "tables"),
                _step_read_the_parts(context, base),
                _step_could_not_do(context, base),
                _step_record_the_verdict(context, base),
            ),
            class_="steps",
        ),
    )


# --- block 3: two positions into the call list ---------------------------------------------------


def _effective_rows(context: PanelContext) -> tuple[TaskRow, ...]:
    """The calls that ARE the parse: one row per part, the superseding artifact where one exists.

    A PART COUNTS ONCE, AND IT COUNTS AT ITS EFFECTIVE ARTIFACT. A `PARSE_PART` that a
    `FORMAT_REPAIR` superseded is excluded here because the repair is itself a row in the same
    tuple; counting both would make one part two, and counting the original would say a reader who
    read the empty original and never opened the repair has read the part. They have not. The
    original stays linked and reachable everywhere else — `packages/multipart/effective.py` and
    invariant 7 both require it.
    """
    return tuple(row for row in context.tasks if not row.superseded_by)


def _not_opened(context: PanelContext, row: TaskRow) -> bool:
    """No mark exists for this call at any version. A row whose version is unknown is never claimed.

    This restates `progress`'s definition of its third word as a boolean, and deliberately does not
    spell the word: `progress` is the only module that renders it.
    """
    return bool(row.fingerprint) and not (context.opened.get(row.task_id) or frozenset())


def _carries_evidence(row: TaskRow) -> bool:
    """A call a reviewer has to look at, from facts already recorded against it.

    IT COMPUTES NO NEW JUDGEMENT. A terminal state that is not success, a validation finding the
    backend recorded, or an artifact something else superseded — three facts the row already
    carries. Nothing here weighs them, ranks them or decides what any of them means.
    """
    return row.state in _EVIDENCE_STATES or row.has_findings or bool(row.superseded_by)


def _current_index(context: PanelContext, rows: tuple[TaskRow, ...]) -> int:
    """Where the reader is in plan order, or -1 for a page that is not one call."""
    for index, row in enumerate(rows):
        if row.task_id == context.current_task_id:
            return index
    return -1


def _next_matching(rows: tuple[TaskRow, ...], start: int, predicate: Any) -> TaskRow | None:
    """The first row after `start` satisfying `predicate`, wrapping once to the beginning.

    THIS IS A POSITION, NOT A REORDERING. The list itself never moves: `multipart_view` renders the
    calls in the model's own plan order and this only says which of them to jump to. Reordering 77
    rows by a computed property is the selection `rules.md` 21.14 forbids one level up.
    """
    total = len(rows)
    for offset in range(1, total + 1):
        row = rows[(start + offset) % total]
        if predicate(row):
            return row
    return None


def _jump(context: PanelContext, label: str, row: TaskRow | None) -> str:
    """One jump into the call list, or nothing at all when no call matches.

    ABSENCE IS SILENT HERE, UNLIKE AN UNAVAILABLE FILING LINK. A missing benchmark is a capability
    the page cannot offer and says so; no unopened call is simply a fact about this parse, and
    writing `every call has been opened` would state something about the reader that this module
    measured only over the calls whose version it could resolve.
    """
    if row is None:
        return ""
    base = ("runs", context.run_id, "jobs", context.job_id)
    return tag(
        "li",
        destination(
            label,
            url(*base, "tasks", row.task_id),
            kind="page",
            note=_SEPARATOR.join(
                part for part in (row.part_id or row.task_id, row.task_type) if part
            ),
            marker=_opened_marker(context, row.task_id, row.fingerprint),
        ),
    )


def _walk(context: PanelContext, rows: tuple[TaskRow, ...], index: int) -> str:
    """Previous, position, next — the line a reader on one call needs and no other page does.

    `call 14 of 77` IS A POSITION AND NOT A PROGRESS RATIO. It says where in the model's own plan
    order this call sits; it counts nothing about what was read, judged or proved, which is why it
    is written here and not through `progress` — whose sentences carry no denominator by
    construction, precisely so `12 of 77` cannot be written about attention anywhere.
    """
    if index < 0:
        return ""
    base = ("runs", context.run_id, "jobs", context.job_id)
    previous = rows[index - 1] if index > 0 else None
    following = rows[index + 1] if index + 1 < len(rows) else None
    return tag(
        "li",
        _spaced(
            (
                destination(
                    "previous call",
                    url(*base, "tasks", previous.task_id),
                    kind="page",
                    marker=_opened_marker(context, previous.task_id, previous.fingerprint),
                )
                if previous
                else ""
            ),
            tag("span", esc(f"call {index + 1:,} of {len(rows):,}"), class_="hint"),
            (
                destination(
                    "next call",
                    url(*base, "tasks", following.task_id),
                    kind="page",
                    marker=_opened_marker(context, following.task_id, following.fingerprint),
                )
                if following
                else ""
            ),
        ),
    )


def _opened_count_sentence(context: PanelContext, *, noun: str) -> str:
    """The three tallies over this parse's calls, or nothing when the page did not load them.

    ONE PART, ONE TALLY, AT ITS EFFECTIVE ARTIFACT — see `_effective_rows`. Calls whose fingerprint
    the handler could not compute enter no tally at all, which `progress.counts` does by refusing to
    classify an item whose current version is unknown.
    """
    rows = _effective_rows(context)
    if not rows:
        return ""
    return progress.counts_sentence(
        progress.counts(
            [row.task_id for row in rows],
            {row.task_id: row.fingerprint for row in rows},
            context.opened,
        ),
        noun=noun,
    )


def _parts_block(context: PanelContext) -> str:
    """Two positions into the call list and one link to the whole of it. Never the list itself.

    A FLAT LIST OF 77 ROWS IN A 320-PIXEL COLUMN IS NOT NAVIGATION, which is what this replaced.
    What a reviewer needs from the panel is where to go next and how much is left; the list itself
    is a page, one click away, and it keeps a stable order so "where was I" stays answerable.

    A PAGE THAT DID NOT LOAD THE TASK MANIFESTS SHOWS NO ROWS. The count line survives on its own,
    because it comes from `job.multipart`, which every job record carries and which costs nothing.

    THE TOTAL AND THE THREE TALLIES ARE COUNTED OVER DIFFERENT THINGS AND WILL NOT ALWAYS SUM. The
    total is every call that ran; the tallies count each part once, at its effective artifact, so a
    parse carrying a format repair has more calls than it has things to read. That is the honest
    arithmetic rather than a rounding error: a superseded response is still a call that ran, it is
    still reachable, and it is not a second thing a reviewer has to open.
    """
    rows = context.tasks
    total = f"{len(rows):,} calls" if rows else _figure(context.session.get("task_count"), "calls")
    if not rows and not total:
        return ""
    index = _current_index(context, rows)
    effective = _effective_rows(context)
    body = join(
        tag(
            "p",
            esc(_figures(total, _opened_count_sentence(context, noun=""))),
            class_="hint",
        ),
        tag(
            "ul",
            join(
                _jump(
                    context,
                    "next not opened",
                    _next_matching(
                        effective,
                        _current_index(context, effective),
                        lambda r: _not_opened(context, r),
                    ),
                ),
                _jump(
                    context,
                    "next carrying evidence",
                    _next_matching(rows, index, _carries_evidence),
                ),
                _walk(context, rows, index),
                tag(
                    "li",
                    destination(
                        "the full list",
                        url("runs", context.run_id, "jobs", context.job_id, "multipart"),
                        kind="page",
                        count=total,
                    ),
                ),
            ),
            class_="menu",
        ),
    )
    return _section("Parts", body)


# --- block 4: the three ways one artifact is read ------------------------------------------------


def _read_block(context: PanelContext) -> str:
    """The preserved filing, what the model made of it, and the two beside each other."""
    base = ("runs", context.run_id, "jobs", context.job_id)
    return _section(
        "Read it",
        tag(
            "ul",
            join(
                *[
                    tag(
                        "li",
                        destination(
                            label,
                            url(*base, view=view),
                            kind="page",
                            marker=_opened_marker(context, item),
                        ),
                    )
                    for label, view, item in _READ_VIEWS
                ]
            ),
            class_="menu",
        ),
    )


# --- block 5: the filing this parse is of --------------------------------------------------------


def _filing_block(context: PanelContext) -> str:
    """The four filing-scoped destinations, each marked `[filing]`, each with no count.

    THE MARKER IS TEXT AND IT IS THE POINT. These four are the only links in the parse menu where
    the SUBJECT changes: a source inventory and a completeness denominator are properties of a
    filing, not of one model's run, and today that crossing happens silently through a two-tab
    strip. `[filing]` says it before the click, in words, where a colour would say it to nobody
    whose stylesheet did not arrive.

    NO COUNT APPEARS ON ANY OF THEM. Every figure a reader would want here — spans covered, spans
    silently omitted, judgements recorded — is on the far side of the inventory walk and the anchor
    ladder. The destination names what is there instead.
    """
    filing = ("benchmark", context.cik, context.accession)
    entries = (
        ("The completeness benchmark", url(*filing), "overview"),
        ("Every parse of this filing", url(*filing, "models"), "models"),
        ("This parse's ledger", url(*filing, "models", context.run_id), context.run_id),
        ("Judgements recorded", url(*filing, "judgements"), "judgements"),
    )
    if not context.benchmark_held:
        body = join(
            *[
                tag("li", _unavailable(label, _NO_BENCHMARK, scope=FILING))
                for label, _href, _item in entries
            ]
        )
    else:
        body = join(
            *[
                tag(
                    "li",
                    destination(
                        label,
                        href,
                        kind="page",
                        scope=FILING,
                        marker=_opened_marker(context, item),
                    ),
                )
                for label, href, item in entries
            ]
        )
    return _section("This filing", tag("ul", body, class_="menu"))


# --- block 6: leaving ----------------------------------------------------------------------------


def _leave_block(context: PanelContext, *, path: str, query: dict[str, list[str]]) -> str:
    """The two ways out: back to the search form, and up to the section this page belongs to.

    `Search and run` PRESERVES THE WHOLE QUERY STRING AND CLAIMS NOTHING MORE. `ReviewApp._panel`
    rebuilds the search form from `cik`, `parsing_label`, `from_date` and `accession`, and a job URL
    carries none of them — so the form it returns to has no entity selected and says so. What
    `with_query` guarantees is that nothing already in the URL is thrown away by the click, which is
    the defect the bare literal `?panel=closed` had.
    """
    # UP IS THE SECTION THIS PAGE BELONGS TO, NOT THE PAGE BEFORE IT. A parse of one filing lives
    # under Home, beneath the run that produced it, and a filing lives under Filings — the same seam
    # `nav.active_section` draws and the breadcrumb states, so the panel and the trail cannot send a
    # reader two different ways.
    up_label, up_href = (
        ("Back to Filings", "/filings") if context.subject == FILING else ("Back to Home", "/")
    )
    return _section(
        "Leave",
        tag(
            "ul",
            join(
                tag(
                    "li",
                    destination(
                        "Search and run",
                        with_query(path, query, panel_mode="search"),
                        kind="page",
                    ),
                ),
                tag("li", destination(up_label, up_href, kind="page")),
            ),
            class_="menu",
        ),
    )


# --- the filing menu -----------------------------------------------------------------------------


def _filing_menu(context: PanelContext, *, path: str, query: dict[str, list[str]]) -> str:
    """The menu for a page whose subject is a FILING rather than one parse of it.

    THE PARSES BLOCK RENDERS ONLY WHERE ITS RECORDS ARE ALREADY IN HAND. `context.parses` is empty
    unless the handler resolved them, and only the two comparison pages do — their handlers walk
    every recorded run for this filing anyway. Rendering the block everywhere would put that walk on
    the spans page, which is the same unbounded cost the global nav refuses to carry.

    RECORDED ORDER, PASSED STRAIGHT THROUGH. No sort, no rank, no coverage figure and no highlighted
    winner: `rules.md` section 21 rule 14 forbids selecting a parser, and a reader takes the top row
    of an ordered list as the answer whatever the caption says.
    """
    filing = ("benchmark", context.cik, context.accession)
    heading = _SEPARATOR.join(
        part
        for part in (
            " ".join(p for p in (context.form_as_filed, context.accession) if p),
            f"CIK {context.cik}" if context.cik else "",
        )
        if part
    )
    reviewing = _section(
        "Reviewing",
        join(
            tag("p", esc(heading)) if heading else "",
            (
                tag("p", esc(f"source set {context.source_set_sha256[:16]}"), class_="hint")
                if context.source_set_sha256
                else ""
            ),
        ),
    )
    pages = _section(
        "This filing",
        tag(
            "ul",
            join(
                *[
                    tag(
                        "li",
                        destination(
                            label,
                            url(*filing, segment),
                            kind="page",
                            marker=_opened_marker(context, item),
                        ),
                    )
                    for label, segment, item in _FILING_PAGES
                ]
            ),
            class_="menu",
        ),
    )
    parses = (
        _section(
            "The parses",
            tag(
                "ul",
                join(
                    *[
                        tag(
                            "li",
                            _spaced(
                                tag("span", "&middot; ", aria_hidden="true"),
                                destination(
                                    parse.model_label or parse.run_id,
                                    url(*filing, "models", parse.run_id),
                                    kind="page",
                                    marker=_opened_marker(context, parse.run_id),
                                ),
                            ),
                        )
                        for parse in context.parses
                    ]
                ),
                class_="menu",
            ),
        )
        if context.parses
        else ""
    )
    return join(reviewing, pages, parses, _leave_block(context, path=path, query=query))


# --- the menu ------------------------------------------------------------------------------------


def review_menu(context: PanelContext, *, csrf: str, path: str, query: dict[str, list[str]]) -> str:
    """The panel body for a page that has a parse or a filing open. Six blocks, or four.

    THE SUBJECT DECIDES, AND AN UNKNOWN ONE RAISES. `nav.panel_mode` resolves the mode from the
    parameters the router matched, so a menu rendered here is on a page that named its subject; a
    third subject would be a claim about the product that nobody has made, and rendering something
    for it would put that claim on a page. `nav.scope_marker` and `nav.kind_word` refuse the same
    way and for the same reason.

    `csrf` IS ACCEPTED AND DELIBERATELY UNUSED. Not one entry in either menu is a form: every one is
    a GET link, and the controls that spend money stay POST buttons on the pages beside the work
    they act on. The token is part of the panel's contract because a panel that grows a form must
    take it from the caller, which holds the session, rather than mint one in a renderer.
    """
    if context.subject == FILING:
        return _filing_menu(context, path=path, query=query)
    if context.subject != PARSE:
        raise ValueError(
            f"unknown panel subject {context.subject!r}; the subjects are {[PARSE, FILING]}"
        )
    return join(
        _reviewing_block(context),
        _steps_block(context),
        _parts_block(context),
        _read_block(context),
        _filing_block(context),
        _leave_block(context, path=path, query=query),
    )
