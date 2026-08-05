"""The one page a reviewer lands on to answer a single question: is this parse correct?

WHY A HUB EXISTS AT ALL. A multipart parse of one filing scatters its evidence across up to
thirteen destinations — a call hierarchy, seventy-seven call pages, an assembled index, a ledger
with three cards on it, a comparison, a benchmark, a judgement history — and until now the first
click off a run page went to a different one of them depending on a field the reader could not see.
The first question anybody has about a job is not "which calls ran"; it is whether the thing the
model produced is right. This page asks that question in its heading and then orders the evidence
by what is cheapest to read and most likely to settle it.

THE ORDER OF THE SEVEN STEPS IS AN ARGUMENT, NOT A STATE MACHINE. Nothing here is gated on anything
else, the server enforces no workflow, and every step is an ordinary link that works with scripting
disabled and survives being pasted into a bug report. The page says so in words, beneath the table,
because a numbered list that does not say this is read as a wizard.

WHAT THIS MODULE REFUSES TO DO.

    IT CARRIES NO COVERAGE FIGURE AND NO PERCENTAGE. Not one span count, not one silently-omitted
    tally, not one ratio. Every one of those needs the filing's mechanical inventory AND the
    six-level anchor ladder over the preserved bytes, and `ParserReviewService.inventoried_filing`
    re-assembles the source set on every call. Putting such a figure here would re-walk a
    multi-megabyte submission on the landing page of every job, to render a number the ledger page
    already computes and pays for. Steps 2, 3 and 4 therefore name their destination in words and
    say, in the row itself, that the count is computed THERE and why it is not computed here.

    IT COMPUTES NOTHING IT WAS NOT HANDED. Every figure on this page is read from the job record,
    the stored multipart session, the stored assembly or the task manifests the hierarchy page
    already loads. A figure that is not cheaply available renders as NO figure — never as a zero,
    which in a review surface is a measurement. That is the discipline `model_comparison_view`
    states for a run that never produced a parse, applied to a page instead of a cell.

    IT NEVER WIDENS WHAT AN OPENED MARK CLAIMS. Every marker and every count on this page comes out
    of `progress`, which is the only place a count becomes words, so `12 of 77` and `88 percent of
    the work` are not forms this page declines to print — they are forms it has no function to print
    them with. The sentence that says what the mark actually asserts accompanies the count.

    IT NEVER OFFERS A TRANSITION THE REVIEW TABLE FORBIDS, AND NEVER HIDES ONE EITHER. The verdict
    control offers exactly the states permitted from the current one, and then names the states that
    are not, so a reviewer learns the shape of the machine rather than discovering it on submit.

    IT NEVER RANKS, SCORES OR RECOMMENDS. No parse is compared with another here, no run is
    promoted, and the word `correct` appears only as the question the page asks — never as an
    answer. `rules.md` section 21 rule 14.

EVERY VALUE IS ESCAPED, INCLUDING THE ONES A MODEL CHOSE. A part identifier, a stop reason, a
blocked reason, a provider failure and a comment are all text written after something read an
untrusted filing. They go through `html.esc` without exception, and none of them is ever handed to
a markup parser.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from packages.evaluation_store import ReviewState

from . import progress
from .html import badge, each, esc, join, tag, url, warning
from .multipart_view import _TASK_STATE_KIND
from .nav import FILING, destination, scope_marker, with_query

#: How many calls of the hierarchy this page shows before handing over to the page that shows all
#: of them. Twelve rows orient a reader; seventy-seven rows on a landing page are the call hierarchy
#: with a different heading, and the hierarchy already exists and is one click away.
CALLS_SHOWN: int = 12

#: Attention items for the destinations this page names, spelled as `attention.ITEMS` spells them.
#: They are the reviewer's own scratch keys and never touch orchestration; the store owns the
#: closed set and validates every one of them on the way in.
_HIERARCHY: str = "hierarchy"
_ASSEMBLED: str = "assembled"
_SIDE_BY_SIDE: str = "read-side-by-side"
_OVERVIEW: str = "overview"

#: Why steps 2, 3 and 4 and the filing tile are not links for some filings. `_benchmark_href`
#: applies exactly this check for exactly this reason: a link that 404s is worse than one that is
#: visibly unavailable and says what it needs.
_NO_BENCHMARK: str = (
    "this filing is not in the benchmark catalog, so it has no denominator to measure against"
)

#: The comment targets the existing comment form offers. Reproduced rather than imported because
#: `job_view` builds its form inline; the list is the record's own vocabulary and nothing here
#: interprets it.
_COMMENT_TARGETS: tuple[str, ...] = (
    "child_job",
    "parsed_node",
    "table",
    "source_reference",
    "raw_response",
    "validation_warning",
    "parent_run",
)

_CALL_HEADERS: tuple[str, ...] = ("part or call", "kind", "state", "out", "stop", "spend")

_STEP_HEADERS: tuple[str, ...] = ("#", "question", "what you will see", "where")


def _cost(value: Any) -> str:
    return f"USD {value or '0'}"


def _measured_cost(job: Mapping[str, Any], tasks: Sequence[Mapping[str, Any]]) -> str:
    """What this parse actually cost, from the settled figures and from nothing estimated.

    SUMMED OVER THE TASKS WHENEVER TASKS EXIST, which is `summarise_tasks`'s own definition of a
    multipart parse's cost: a multipart job spends on its calls, and the job record's own amount
    describes the single-response protocol. Reading the job's field for a multipart parse would
    report a number that belongs to a different protocol.
    """
    if not tasks:
        return str(job.get("actual_cost_usd") or 0)
    return str(sum((Decimal(str(task.get("actual_cost_usd") or 0)) for task in tasks), Decimal(0)))


def _marker(
    item: str, opened_counts: Mapping[str, str], opened: Mapping[str, frozenset[str]]
) -> str:
    """The three-word opened marker for one destination, or nothing when its version is unknown."""
    return progress.marker(item, opened_counts.get(item, ""), opened)


def _unavailable(label: str, reason: str, *, scope: str = "") -> str:
    """A destination that exists but cannot be reached from here, with the reason beside it.

    A DISABLED SPAN, NEVER A HIDDEN ROW. A control that appears and disappears depending on state is
    one nobody can learn — the rule `views.tabs` states — and a reader who cannot see that a ledger
    exists cannot ask why this filing has none.
    """
    return join(
        scope_marker(scope),
        tag("span", esc(label), class_="step-disabled", aria_disabled="true"),
        tag("span", esc(reason), class_="hint"),
    )


def _parse_destinations(
    *,
    run_id: str,
    session: Mapping[str, Any],
    assembly: Mapping[str, Any] | None,
    benchmark_held: bool,
) -> tuple[str, ...]:
    """Exactly the destinations THIS page names, which is the scope its opened count is over.

    A DENOMINATOR THAT MOVES IS NOT A DENOMINATOR. The scope is built from what the page actually
    renders — a hierarchy only when there is a multipart session, an assembled index only when one
    was written, the two filing-scoped destinations only when the filing is in the benchmark catalog
    — so the count never describes links the reader was never offered.
    """
    items = [_SIDE_BY_SIDE]
    if session:
        items.append(_HIERARCHY)
    if assembly is not None:
        items.append(_ASSEMBLED)
    if benchmark_held:
        items.extend((run_id, _OVERVIEW))
    return tuple(items)


def _call_items(
    tasks: Sequence[Mapping[str, Any]], superseded_by: Mapping[str, str]
) -> tuple[str, ...]:
    """The attention item of every call, resolved through the artifact that now holds its content.

    A PART COUNTS AS OPENED ONLY WHEN ITS EFFECTIVE ARTIFACT HAS BEEN OPENED. A reader who opened a
    part whose response would not parse, and never opened the successful FORMAT_REPAIR that carries
    its content, has not read the part — and telling them they had would be the false-complete this
    repository spends its effort refusing, wearing a progress marker. The original stays listed,
    stays linked and keeps its own marker; it is the TALLY that resolves.
    """
    return tuple(superseded_by.get(str(task["task_id"]), str(task["task_id"])) for task in tasks)


# --- D. this parse ------------------------------------------------------------------------------


def _this_parse_card(job: Mapping[str, Any], *, measured_cost: str) -> str:
    """Which model, where, under which protocol and prompt, at what cap and what cost."""
    routing = job.get("model_routing") or {}
    prompt = job.get("prompt") or {}
    settings = job.get("settings") or {}
    incompatibility = job.get("incompatibility") or {}
    coverage = job.get("image_coverage") or {}
    ceiling = job.get("budget_ceiling_usd")
    budget = _cost(ceiling) if ceiling else "no per-filing ceiling recorded"
    return tag(
        "div",
        join(
            tag("h2", "This parse"),
            tag(
                "p",
                esc(
                    f"{routing.get('label')} in {routing.get('region')} "
                    f"({routing.get('inference_profile_id') or 'no inference profile'}); "
                    f"{'multimodal' if routing.get('multimodal') else 'text only'}; "
                    f"{job.get('strategy')} protocol; created {job.get('created_at')}"
                ),
            ),
            tag(
                "p",
                esc(
                    f"{prompt.get('prompt_id')}@{prompt.get('version')} "
                    f"sha256 {str(prompt.get('sha256') or '')[:16]}"
                ),
                class_="mono",
            ),
            tag(
                "p",
                esc(
                    f"output cap {int(settings.get('max_output_tokens') or 0):,} tokens - "
                    f"filing budget {budget} - {_cost(measured_cost)} measured"
                ),
            ),
            tag(
                "p",
                join(
                    badge(str(job.get("execution_state") or ""), "info"),
                    " ",
                    badge(str(job.get("review_state") or ""), "neutral"),
                ),
            ),
            # THE SENTENCE IS `job_view`'S, WORD FOR WORD. An artifact in EVALUATION has been
            # judged by nobody, and the two states beside each other invite exactly the reading it
            # forbids: that reaching READY_FOR_REVIEW is an endorsement of anything.
            (
                tag(
                    "p",
                    esc(
                        "EVALUATION - not approved for reuse. Approval records a judgement and "
                        "activates nothing: no search consults this artifact and no cache is "
                        "populated."
                    ),
                    class_="hint",
                )
                if job.get("review_state") == ReviewState.EVALUATION.value
                else ""
            ),
            warning(str(incompatibility.get("detail"))) if incompatibility.get("detail") else "",
            warning(str(job.get("failure"))) if job.get("failure") else "",
            # VERBATIM FROM `job_view`, BECAUSE A CLAIM ABOUT IMAGE COVERAGE MUST READ THE SAME
            # WHEREVER IT APPEARS. Two wordings of one refusal is how one of them softens.
            (
                warning(
                    f"{coverage.get('image_member_count', 0)} image-bearing member(s) were filed "
                    "and were NOT analysed. This run does not claim image coverage. "
                    + str(coverage.get("reason", ""))
                )
                if coverage.get("image_member_count") and not coverage.get("analysed")
                else ""
            ),
        ),
        class_="card",
    )


# --- E. what has been recorded, and what has not ------------------------------------------------


def _recorded_card(
    *,
    job: Mapping[str, Any],
    destinations: progress.Counts,
) -> str:
    """The two facts a reviewer most often assumes wrongly: what was judged, and what was read.

    THEY ARE STATED SEPARATELY AND NEVER IN ONE CELL. A review state is a judgement a person
    recorded under a transition table; an opened count is a record that this server rendered a page.
    One cell holding both is how "I looked at it" starts reading as "it was checked", and
    `review_history` is empty on all seven recorded parses, so every such reading would be false.
    """
    history = job.get("review_history") or []
    state = str(job.get("review_state") or "")
    recorded = f"Review state {state}. {len(history):,} transition(s) recorded"
    tail = (
        " - no verdict has ever been recorded for this parse."
        if not history
        else f"; the most recent is {str((history[-1] or {}).get('at') or 'undated')}."
    )
    return tag(
        "div",
        join(
            tag("h2", "What has been recorded, and what has not"),
            tag("p", esc(recorded + tail)),
            tag(
                "p",
                esc(progress.counts_sentence(destinations, noun="destinations of this parse")),
            ),
            tag("p", esc(progress.OPENED_NOTE), class_="hint"),
            tag(
                "p",
                esc(
                    "This trail is scratch, not evidence. Deleting the evaluation store's "
                    "attention prefix removes every mark and touches nothing that was paid for, "
                    "which is why it does not live on the job or the task record."
                ),
                class_="hint",
            ),
        ),
        class_="card",
    )


# --- F. the seven steps -------------------------------------------------------------------------


def _step_row(number: int, question: str, evidence: str, where: str) -> str:
    return tag(
        "tr",
        join(
            tag("td", esc(str(number))),
            tag("td", esc(question)),
            tag("td", esc(evidence)),
            tag("td", where, class_="where"),
        ),
    )


def _steps_table(
    *,
    base: tuple[str, ...],
    filing: Mapping[str, Any],
    run_id: str,
    job: Mapping[str, Any],
    session: Mapping[str, Any],
    assembly: Mapping[str, Any] | None,
    tasks: Sequence[Mapping[str, Any]],
    calls: progress.Counts,
    benchmark_held: bool,
    opened: Mapping[str, frozenset[str]],
    opened_counts: Mapping[str, str],
) -> str:
    """Seven questions, the evidence that answers each, and where that evidence is.

    COLUMN THREE DESCRIBES THE EVIDENCE, NEVER THE PAGE NAME. `Spans` tells a reader nothing they
    can act on; `every visible span of one member, with the control that classifies it` tells them
    whether the click is worth it. That is the first of the five mechanisms `nav.destination`
    renders, and the reason all five are rendered by one function is that apart they drift.
    """
    cik = str(filing.get("cik") or "")
    accession = str(filing.get("accession") or "")
    ledger = url("benchmark", cik, accession, "models", run_id)
    ledger_marker = _marker(run_id, opened_counts, opened)
    multipart = bool(session)
    history = job.get("review_history") or []
    review_state = str(job.get("review_state") or "")

    def ledger_destination(label: str, fragment: str) -> str:
        if not benchmark_held:
            return _unavailable(label, _NO_BENCHMARK, scope=FILING)
        return destination(
            label,
            ledger + fragment,
            kind="page",
            scope=FILING,
            marker=ledger_marker,
        )

    if multipart:
        first = destination(
            "the call hierarchy",
            url(*base, "multipart"),
            kind="page",
            count=(
                f"{int(session.get('task_count') or 0):,} calls, "
                f"{int(session.get('truncated') or 0):,} truncated"
            ),
            marker=_marker(_HIERARCHY, opened_counts, opened),
        )
        first_evidence = (
            "every call in the model's own plan order, with its output cap, its stop reason, its "
            "spend and what the backend proved about its response. The queue controls are POST "
            "only and sit at the #queue anchor of that page."
        )
        fifth = destination(
            "the parts, unopened first",
            url(*base, "multipart", show="unopened"),
            kind="page",
            count=progress.counts_sentence(calls, noun="calls") if tasks else "",
            marker=_marker(_HIERARCHY, opened_counts, opened),
        )
        fifth_evidence = (
            "the preserved filing beside what the model made of it, one call at a time. This is "
            "the unbounded one and it comes after everything that might make it unnecessary."
        )
    else:
        first = destination(
            "the response and the filing, side by side",
            url(*base, view="side-by-side"),
            kind="page",
            count="one response, the single-response protocol",
            marker=_marker(_SIDE_BY_SIDE, opened_counts, opened),
        )
        first_evidence = (
            "the exact bytes the model returned, the structured reading of them, and the preserved "
            "filing beside both. This parse used the single-response protocol, so it has no plan "
            "and no call hierarchy."
        )
        fifth = destination(
            "the parsed reading of it",
            url(*base, view="parsed"),
            kind="page",
            marker=_marker(_SIDE_BY_SIDE, opened_counts, opened),
        )
        fifth_evidence = (
            "the model's structure in the model's own vocabulary, every node with the source "
            "reference it cited, linked to the byte offset where that quote was found."
        )

    if assembly is None:
        sixth = _unavailable(
            "the assembled index",
            "no mechanical assembly has been written for this parse",
        )
    else:
        sixth = destination(
            "the assembled index",
            url(*base, "assembled") + "#unresolved",
            kind="page",
            count=(
                f"{int(assembly.get('unresolved_item_count') or 0):,} unresolved, "
                f"{int(assembly.get('truncation_events') or 0):,} truncation event(s)"
            ),
            marker=_marker(_ASSEMBLED, opened_counts, opened),
        )

    rows = join(
        _step_row(1, "What happened when it ran", first_evidence, first),
        _step_row(
            2,
            "What it never mentioned",
            "every visible span this parse did not cite, did not declare unresolved, and that no "
            "reviewer excluded - with its text. The count is computed on the ledger page, against "
            "this filing's mechanical inventory and the human classification of it. It is not "
            "computed here: doing so would walk the preserved bytes of the filing on every load of "
            "this page.",
            ledger_destination("this parse's ledger, at the omissions", "#omitted"),
        ),
        _step_row(
            3,
            "Whether its citations exist",
            "every coverage claim, both of its anchors, the rung of the six-level ladder each one "
            "resolved at, and the interval the pair bounded. Levels 5 and 6 are human-review "
            "candidates and never proof. The count is computed on the ledger page and not here: "
            "resolving an anchor runs that ladder over the preserved bytes.",
            ledger_destination("this parse's ledger, at the claims", "#claims"),
        ),
        _step_row(
            4,
            "Whether its numbers exist",
            "each structured table the parse emitted, beside the source element it names, with "
            "every cell that is nowhere in that source marked. The count is computed on the ledger "
            "page and not here: it needs the mechanical walk of the preserved bytes that produced "
            "the source element.",
            ledger_destination("this parse's ledger, at the tables", "#tables"),
        ),
        _step_row(5, "Read the parts", fifth_evidence, fifth),
        _step_row(
            6,
            "What it said it could not do",
            "the model's own unresolved list, the branches that reached the output limit, and the "
            "calls that were blocked or failed. An explicitly unresolved region is not an "
            "omission, and this is where the difference is visible.",
            sixth,
        ),
        _step_row(
            7,
            "Record the verdict",
            f"the transitions permitted from {review_state}, the states that are not, and a note "
            "field. It is last because a verdict recorded before the evidence is what this page "
            "exists to prevent.",
            destination(
                "the verdict control on this page",
                "#verdict",
                kind="anchor",
                count=f"{review_state}, {len(history):,} transitions recorded",
            ),
        ),
    )

    return tag(
        "div",
        join(
            tag("h2", "The seven steps"),
            tag(
                "div",
                tag(
                    "table",
                    join(
                        tag(
                            "thead",
                            tag("tr", join(*[tag("th", header) for header in _STEP_HEADERS])),
                        ),
                        tag("tbody", rows),
                    ),
                    class_="steps-table",
                ),
                class_="scroll-x",
            ),
            tag(
                "p",
                esc(
                    "The order is an argument, not a state machine. Steps 2, 3 and 4 are cheap to "
                    "read and can settle the question on their own; step 5 is unbounded and comes "
                    "after everything that might make it unnecessary; step 7 is last for the "
                    "reason its own row gives. No step is gated on another, the server enforces no "
                    "workflow, every step is an ordinary link, and they may be read in any order "
                    "or not at all."
                ),
                class_="hint",
            ),
        ),
        class_="card",
    )


# --- G. the calls -------------------------------------------------------------------------------


def _call_rows(
    base: tuple[str, ...],
    task: Mapping[str, Any],
    *,
    superseded_by: Mapping[str, str],
    opened: Mapping[str, frozenset[str]],
    opened_counts: Mapping[str, str],
) -> str:
    """One call: its figures, then its opened marker and whatever superseded it.

    TWO ROWS, BECAUSE THE MARKER NEVER SHARES A CELL WITH A FIGURE ABOUT THE PARSE. A cell holding
    both `0.0610` and `opened` reads as though the spend had been checked. The same two-row shape
    `model_comparison_view` uses for a run and the sentence about it, for the same reason.

    A SUPERSEDED ORIGINAL KEEPS ITS ROW AND KEEPS ITS LINK. The repair carries the part's content;
    the original is still exactly what the provider returned and is still evidence — supersede,
    never overwrite.
    """
    task_id = str(task["task_id"])
    attempts = task.get("attempts") or []
    last = attempts[-1] if attempts else {}
    depth = int(task.get("depth") or 0)
    created = task.get("model_created") or {}
    task_type = str(task.get("task_type") or "")
    state = str(task.get("state") or "")
    label = str(created.get("part_id") or "") or task_type.replace("_", " ").lower()
    replacement = superseded_by.get(task_id, "")

    figures = tag(
        "tr",
        join(
            tag(
                "td",
                join(
                    tag("span", "    " * depth) if depth else "",
                    tag("a", esc(label), href=url(*base, "tasks", task_id)),
                ),
            ),
            tag("td", esc(task_type)),
            tag("td", badge(state, _TASK_STATE_KIND.get(state, "neutral"))),
            tag("td", esc(f"{int(last.get('output_tokens') or 0):,}")),
            tag("td", esc(str(last.get("stop_reason") or "-"))),
            tag("td", esc(_cost(task.get("actual_cost_usd")))),
        ),
    )
    superseded = (
        join(
            esc(" its content is now carried by "),
            tag("a", esc(replacement), href=url(*base, "tasks", replacement), class_="mono"),
            esc(", and this original is preserved exactly as it was returned"),
        )
        if replacement
        else ""
    )
    return join(
        figures,
        tag(
            "tr",
            tag(
                "td",
                join(_marker(task_id, opened_counts, opened), superseded),
                colspan=len(_CALL_HEADERS),
                class_="hint",
            ),
        ),
    )


def _calls_card(
    *,
    base: tuple[str, ...],
    session: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    calls: progress.Counts,
    superseded_by: Mapping[str, str],
    opened: Mapping[str, frozenset[str]],
    opened_counts: Mapping[str, str],
) -> str:
    """The first twelve calls in the model's own plan order, and the way to all of them.

    THE ORDER IS THE STORE'S AND IS NEVER RECOMPUTED HERE. Rows arrive in `load_tasks` order with
    the model's own indentation, and a stable position is what makes "where was I" answerable across
    seventy-seven of them. Reordering by a computed figure is the selection rule 21.14 forbids one
    level up, and it would be no better one level down.
    """
    if not tasks:
        return tag(
            "div",
            join(
                tag("h2", "The calls"),
                tag(
                    "p",
                    esc(
                        "No call has been recorded for this parse yet."
                        if session
                        else "This parse used the single-response protocol, so it has no calls."
                    ),
                ),
            ),
            class_="card",
        )

    window = list(tasks)[:CALLS_SHOWN]
    footer = tag(
        "tr",
        tag(
            "td",
            join(
                esc(f"{len(window):,} of {len(tasks):,} shown - "),
                tag(
                    "a",
                    join(esc(f"all {len(tasks):,} in the call hierarchy"), " &#8594;"),
                    href=url(*base, "multipart"),
                ),
            ),
            colspan=len(_CALL_HEADERS),
            class_="hint",
        ),
    )
    return tag(
        "div",
        join(
            tag("h2", "The calls"),
            tag(
                "p",
                esc(f"{len(tasks):,} calls - " + progress.counts_sentence(calls, noun="")),
            ),
            tag(
                "div",
                tag(
                    "table",
                    join(
                        tag(
                            "thead",
                            tag("tr", join(*[tag("th", header) for header in _CALL_HEADERS])),
                        ),
                        tag(
                            "tbody",
                            join(
                                each(
                                    window,
                                    lambda task: _call_rows(
                                        base,
                                        task,
                                        superseded_by=superseded_by,
                                        opened=opened,
                                        opened_counts=opened_counts,
                                    ),
                                ),
                                footer,
                            ),
                        ),
                    ),
                ),
                class_="scroll-x",
            ),
        ),
        class_="card",
    )


# --- H. the verdict -----------------------------------------------------------------------------


def _verdict_card(
    *,
    base: tuple[str, ...],
    job: Mapping[str, Any],
    csrf: str,
    permitted_reviews: Sequence[str],
    base_query: dict[str, list[str]],
) -> str:
    """The only control on this page that records anything, at the URL where the decision was made.

    IT POSTS TO THE ROUTE THE HUB IS SERVED FROM. Deciding a verdict and recording one used to be
    two different URLs, so recording one returned the reviewer to a page that was not the evidence
    they had just read. The query string is carried across with `with_query` for the reason that
    function exists: a bare action would discard the panel and entity selections the reader arrived
    with.

    THE STATES THAT ARE NOT OFFERED ARE NAMED, WITH THE REASON. A control that silently omits
    SUPERSEDED teaches a reviewer that the state does not exist; one that offers it and refuses the
    submission teaches them the form is unreliable. The transition table is stated instead.
    """
    offered = sorted(permitted_reviews)
    current = str(job.get("review_state") or "")
    not_offered = sorted(
        state.value
        for state in ReviewState
        if state.value not in offered and state.value != current
    )

    if offered:
        control: str = tag(
            "form",
            join(
                tag("input", "", type="hidden", name="csrf_token", value=csrf),
                tag(
                    "select",
                    join(*[tag("option", esc(state), value=state) for state in offered]),
                    name="review_state",
                    aria_label="review state",
                ),
                tag("input", "", type="text", name="note", placeholder="reason or note"),
                tag("button", "Record this verdict", type="submit"),
            ),
            method="post",
            action=with_query(url(*base, "review"), base_query),
            class_="inline",
        )
        permitted_note: str = tag(
            "p",
            esc(f"Permitted from {current}: " + ", ".join(offered) + "."),
            class_="hint",
        )
    else:
        control = tag(
            "p",
            esc(
                f"{current} is terminal: the review table permits no transition out of it, so no "
                "control is offered. The artifact and everything recorded about it stay readable."
            ),
        )
        permitted_note = ""

    refused = (
        tag(
            "p",
            esc(
                ", ".join(not_offered)
                + (" is " if len(not_offered) == 1 else " are ")
                + f"not permitted from {current} and so not offered. A transition the review table "
                "does not allow is absent from the control rather than offered and refused on "
                "submit."
            ),
            class_="hint",
        )
        if not_offered
        else ""
    )

    return tag(
        "div",
        join(
            tag("h2", "Verdict"),
            # `job_view`'S SENTENCE, WORD FOR WORD. Approval is a recorded judgement and nothing
            # else in this project acts on it: Phase 4 is where APPROVED becomes operational, and
            # that gate is not switched on. A reviewer who believes approving publishes something
            # will approve differently.
            tag(
                "p",
                esc(
                    "Approval records a judgement and activates nothing: no search consults this "
                    "artifact and no cache is populated."
                ),
            ),
            control,
            permitted_note,
            refused,
        ),
        class_="card",
        id="verdict",
    )


# --- I. comments --------------------------------------------------------------------------------


def _comments_card(
    *,
    base: tuple[str, ...],
    comments: Sequence[Mapping[str, Any]],
    csrf: str,
) -> str:
    """The job's comments and the existing comment form, unchanged.

    A COMMENT IS THE ONLY PLACE A REVIEWER SAYS SOMETHING ABOUT ONE PART. There is deliberately no
    per-part review state: Phase 2.1 refused to overload review states, and a fourth state machine
    for parts would repeat that. A comment against `multipart_task` is the mechanism that exists.
    """
    listing = (
        tag(
            "ul",
            each(
                comments,
                lambda comment: tag(
                    "li",
                    esc(
                        f"[{str(comment['created_at'])[:19]}] {comment['author']} on "
                        f"{comment['target_type']}"
                        f"{(' ' + str(comment['target_id'])) if comment.get('target_id') else ''}: "
                        f"{comment['text']}"
                    ),
                ),
            ),
            class_="refs",
        )
        if comments
        else tag("p", "No comments yet.", class_="hint")
    )
    form = tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag(
                "select",
                join(*[tag("option", esc(t), value=t) for t in _COMMENT_TARGETS]),
                name="target_type",
                aria_label="comment target type",
            ),
            tag("input", "", type="text", name="target_id", placeholder="node id or warning"),
            tag("textarea", "", name="text", required=True, aria_label="comment text"),
            tag("button", "Add comment", type="submit"),
        ),
        method="post",
        action=url(*base, "comments"),
        class_="inline",
    )
    return tag("div", join(tag("h2", "Comments"), listing, form), class_="card")


# --- J. where the rest is -----------------------------------------------------------------------


def _where_the_rest_is_card(
    *,
    base: tuple[str, ...],
    filing: Mapping[str, Any],
    benchmark_held: bool,
    opened: Mapping[str, frozenset[str]],
    opened_counts: Mapping[str, str],
) -> str:
    """The destinations the seven steps do not reach, so none of them is only findable by luck.

    THE QUEUE IS AN ANCHOR AND SAYS SO. `/runs/{r}/jobs/{j}/queue` answers POST and nothing else; a
    menu offering it as a page would send a reviewer into a 405. It is reached at the fragment of
    the card that sits beside the hierarchy those actions act on, and every one of those actions is
    a form button rather than a link, because a link is something a browser can be made to follow.

    THE FILING'S OWN SURFACES ARE TWO CLICKS AWAY, DELIBERATELY. A source inventory belongs to the
    filing and is the denominator every parse of it is measured against; reaching it through this
    parse would say it is a property of one model's run, which is the misreading `_benchmark_page`
    already refuses by withholding the run identifier.
    """
    cik = str(filing.get("cik") or "")
    accession = str(filing.get("accession") or "")
    rows = [
        destination(
            "the single-response view of this job",
            url(*base, view="side-by-side"),
            kind="page",
            note=(
                "the preserved filing, the exact bytes the model returned and the structured "
                "reading of them, in one page"
            ),
            marker=_marker(_SIDE_BY_SIDE, opened_counts, opened),
        ),
        destination(
            "the queue controls",
            url(*base, "multipart") + "#queue",
            kind="anchor",
            note=(
                "four explicit actions that may spend money. Every one is a form POST with a CSRF "
                "token and none of them is a link; there is no page behind them"
            ),
        ),
        tag(
            "span",
            esc(
                "One call is reached from the call list above, or from the full hierarchy. There "
                "is no index of calls other than the hierarchy, and no call has a review state of "
                "its own: a verdict applies to the whole child job."
            ),
        ),
        (
            destination(
                "the completeness benchmark for this filing",
                url("benchmark", cik, accession),
                kind="page",
                scope=FILING,
                note=(
                    "the source inventory, the spans, the tables and the images are reached from "
                    "there. They are denominator work rather than parse work, and they belong to "
                    "the filing rather than to this parse"
                ),
                marker=_marker(_OVERVIEW, opened_counts, opened),
            )
            if benchmark_held
            else _unavailable(
                "the completeness benchmark for this filing", _NO_BENCHMARK, scope=FILING
            )
        ),
    ]
    return tag(
        "div",
        join(
            tag("h2", "Where the rest is"),
            tag("ul", join(*[tag("li", row) for row in rows]), class_="refs"),
        ),
        class_="card",
    )


# --- the page -----------------------------------------------------------------------------------


def hub(
    *,
    run: Mapping[str, Any],
    job: Mapping[str, Any],
    session: Mapping[str, Any],
    assembly: Mapping[str, Any] | None,
    tasks: Sequence[Mapping[str, Any]],
    superseded_by: Mapping[str, str],
    comments: Sequence[Mapping[str, Any]],
    opened: Mapping[str, frozenset[str]],
    opened_counts: Mapping[str, str],
    benchmark_held: bool,
    csrf: str,
    permitted_reviews: Sequence[str],
    base_query: dict[str, list[str]],
) -> str:
    """Everything a reviewer needs to decide whether one parse of one filing is correct.

    EVERY ARGUMENT IS ALREADY IN THE HANDLER'S HAND, AND THAT IS THE WHOLE COST MODEL OF THIS PAGE.
    `run` and `job` are records the handler loaded to route the request at all; `session` is
    `job.multipart` verbatim; `assembly` is the stored assembly or None; `tasks` are the task
    manifests the hierarchy page already pays for and the fingerprinted task cache then serves free;
    `superseded_by` is `EffectiveArtifacts.superseded_by` flattened to plain strings so no enum
    reaches a renderer. Nothing here builds an inventory, walks the run store, resolves an anchor or
    computes a ledger, and that is why the landing page of a job is cheap.

    `opened` is `EvaluationStore.opened_items` verbatim - each destination against every fingerprint
    ever recorded for it - merged across this parse's job scope and its filing's scope, whose item
    names cannot collide. `opened_counts` is the companion the markers are read against: each
    destination against the version stamp it carries NOW, computed by the handler from durable
    records alone. A destination absent from it renders no marker and enters no tally, because its
    version is unknown and neither `opened` nor `not opened` would be true of it.

    `benchmark_held` is `catalog.filing(cik, accession) is not None`, resolved by the handler. The
    check is made once and its answer is passed, rather than made three times in three renderers
    that could disagree about whether a link 404s.
    """
    run_id = str(run["run_id"])
    base = ("runs", run_id, "jobs", str(job["job_id"]))
    filing = job["filing"]

    destinations = progress.counts(
        _parse_destinations(
            run_id=run_id,
            session=session,
            assembly=assembly,
            benchmark_held=benchmark_held,
        ),
        opened_counts,
        opened,
    )
    calls = progress.counts(_call_items(tasks, superseded_by), opened_counts, opened)

    return join(
        tag(
            "h1",
            esc(
                f"Is this parse correct? - {filing.get('form_as_filed')} {filing.get('accession')}"
            ),
        ),
        tag("p", esc(f"{filing.get('issuer_label')} - CIK {filing.get('cik')}")),
        _this_parse_card(job, measured_cost=_measured_cost(job, tasks)),
        _recorded_card(job=job, destinations=destinations),
        _steps_table(
            base=base,
            filing=filing,
            run_id=run_id,
            job=job,
            session=session,
            assembly=assembly,
            tasks=tasks,
            calls=calls,
            benchmark_held=benchmark_held,
            opened=opened,
            opened_counts=opened_counts,
        ),
        _calls_card(
            base=base,
            session=session,
            tasks=tasks,
            calls=calls,
            superseded_by=superseded_by,
            opened=opened,
            opened_counts=opened_counts,
        ),
        _verdict_card(
            base=base,
            job=job,
            csrf=csrf,
            permitted_reviews=permitted_reviews,
            base_query=base_query,
        ),
        _comments_card(base=base, comments=comments, csrf=csrf),
        _where_the_rest_is_card(
            base=base,
            filing=filing,
            benchmark_held=benchmark_held,
            opened=opened,
            opened_counts=opened_counts,
        ),
    )
