"""Server-rendered pages for the parser-review UI.

WHY THE SERVER RENDERS. The review surface has to show a preserved SEC filing beside a parsed
artifact, and a filing is untrusted bytes. Rendering on the server means those bytes are escaped
once, in `html.esc`, and reach the browser as text that no parser will ever treat as markup. It
also means the raw view, the parsed view, side-by-side, source-reference navigation, comments and
review actions are ordinary links and form posts — so the review surface keeps no client-side
state that can disagree with what was stored, and works with scripting disabled.

WHAT THE PARSED VIEW MUST NOT DO. It renders whatever `type` and `title` the model produced. There
is no vocabulary to validate against, no mapping to a canonical name, and an unfamiliar label is
displayed rather than dropped — rules.md section 21 rule 2 and the UX specification say the same
thing, and a renderer that silently omitted an unrecognised node would hide exactly the finding the
first experiments exist to produce.

THE THREE WARNINGS THE UX SPECIFICATION REQUIRES appear at the point of use, in the same view as
the content they qualify: an unresolved source reference, image-bearing content that was not
analysed, and unresolved content in the parse.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from .assets import STYLESHEET  # noqa: F401 - re-exported for the asset route
from .html import badge, each, esc, join, tag, url, warning
from .nav import Crumb, global_nav, mode_strip
from .nav import crumbs as render_crumbs

_STATE_KIND = {
    "READY_FOR_REVIEW": "ok",
    "RUNNING": "info",
    "QUEUED": "info",
    "PREFLIGHT": "info",
    "SOURCE_READY": "info",
    "CREATED": "neutral",
    "RESPONSE_RECEIVED": "info",
    "VALIDATING": "info",
    "FAILED": "bad",
    "INCOMPATIBLE": "warn",
    "INTERRUPTED": "warn",
    "CANCELLED": "neutral",
}

_REVIEW_KIND = {
    "EVALUATION": "neutral",
    "UNDER_REVIEW": "info",
    "APPROVED": "ok",
    "REJECTED": "bad",
    "SUPERSEDED": "warn",
    "INVALIDATED": "warn",
}


#: The two things a person does in this workspace, and they are genuinely different jobs.
#:
#: FILING is "is this parse any good" — the raw source beside what a model made of it, the gaps,
#: the tables, the nodes. BENCHMARK is "which model should we use" — every candidate against one
#: filing on the same denominator. Forcing them into one screen makes both worse: the filing view
#: wants a whole viewport for two documents side by side, and the benchmark view wants a wide table
#: nobody scrolls a document inside.
FILING_TAB: Final[str] = "filing"
BENCHMARK_TAB: Final[str] = "benchmark"


def tabs(active: str, *, filing_href: str = "", benchmark_href: str = "") -> str:
    """The dashboard's two views, as a tab strip.

    A TAB WITH NOWHERE TO GO IS RENDERED DISABLED RATHER THAN HIDDEN. A control that appears and
    disappears depending on state is one a person cannot learn; one that is visibly unavailable
    tells them the view exists and what it needs. Same reasoning as the model selector, which shows
    an unavailable candidate with its reason instead of dropping it from the list.
    """

    def one(key: str, label: str, href: str) -> str:
        if not href:
            return tag("span", esc(label), class_="tab tab-disabled", aria_disabled="true")
        return tag(
            "a",
            esc(label),
            class_="tab tab-active" if key == active else "tab",
            href=href,
            aria_current="page" if key == active else None,
        )

    return tag(
        "nav",
        join(
            one(FILING_TAB, "Filing", filing_href),
            one(BENCHMARK_TAB, "Benchmark", benchmark_href),
        ),
        class_="tabs",
        aria_label="dashboard view",
    )


def panel_shell(
    *,
    active: str,
    collapse_href: str,
    mode: str,
    search_href: str,
    review_href: str,
    review_reason: str,
    body: str,
    spend: dict[str, Any] | None = None,
) -> str:
    """The panel chrome both modes share: collapse, title, global nav, mode strip, then the body.

    WHY THE CHROME IS HERE AND NOT IN EITHER MODE. `search_panel` used to own the collapse control
    and the title, which meant the review menu could only get them by duplicating them — and a
    duplicated control is one that drifts. Both modes now receive identical chrome by construction.

    `collapse_href` IS SUPPLIED RATHER THAN LITERAL. It used to be the bare string "?panel=closed",
    which discarded the entity and model selections the panel had just been rebuilt from: collapsing
    the panel silently reset the form. The caller builds it with `nav.with_query`, which preserves
    every other key.
    """
    return join(
        tag(
            "a",
            "&#8592; collapse",
            class_="collapse-control",
            href=collapse_href,
            data_panel="closed",
        ),
        tag("h1", "Kopexx parser review"),
        global_nav(active),
        mode_strip(
            mode=mode,
            search_href=search_href,
            review_href=review_href,
            review_reason=review_reason,
        ),
        tag("div", body, class_="panel-body"),
        # THE MONEY COUNTER IS PANEL CHROME AND SHOWS IN BOTH MODES. It used to sit inside the
        # search form, so it vanished the moment a reader opened a parse — the one place the
        # figure actually bears on a decision, because every queue control on those pages spends
        # against this same ceiling.
        _spend_line(spend),
    )


def _spend_line(spend: dict[str, Any] | None) -> str:
    """The cumulative authorized spend, or nothing when the caller could not cheaply supply it.

    ABSENT RATHER THAN ZERO. A `USD 0.00 of 0.00` would be a measurement, and a wrong one.
    """
    if not spend:
        return ""
    return tag(
        "p",
        esc(f"Cumulative authorized spend: USD {spend['spent_usd']} of {spend['ceiling_usd']}."),
        class_="hint panel-spend",
    )


def layout(
    *,
    title: str,
    panel: str,
    main: str,
    run_id: str | None,
    collapsed: bool,
    https: bool,
    crumbs: Sequence[Crumb],
    tab_strip: str = "",
) -> str:
    """The shell: a persistent left panel, the workspace, and the anchored run identifier.

    BOTH PANEL CONTROLS ARE ALWAYS IN THE DOCUMENT, and CSS shows whichever the current mode calls
    for. Rendering only the applicable one meant the other had to be fetched, which is why
    collapsing the panel used to cost a full page load; with both present the toggle is a class
    change on `body` and nothing is requested at all.

    THE SERVER STILL RENDERS THE CORRECT MODE. `collapsed` comes from the request, so the markup
    arrives in the state the reader left it in and there is no flash of an open panel snapping
    shut after the script runs.
    """
    reopen = tag("a", "&#9776; menu", class_="reopen", href="?panel=open", data_panel="open")
    mode = (
        ""
        if https
        else tag(
            "p",
            esc(
                "LOCAL DEVELOPMENT MODE. This instance is served over plain HTTP and makes no "
                "production security claim. Prefer loopback plus an SSH tunnel over binding to a "
                "network interface."
            ),
            class_="mode-note",
        )
    )
    return join(
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title)}</title>",
        '<link rel="stylesheet" href="/static/app.css">',
        '<script src="/static/app.js" defer></script>',
        "</head>",
        f'<body class="{"panel-collapsed" if collapsed else ""}">',
        tag("aside", panel, class_="panel"),
        tag("main", join(reopen, render_crumbs(crumbs), tab_strip, main, mode)),
        _run_id_bar(run_id),
        "</body></html>",
    )


def _run_id_bar(run_id: str | None) -> str:
    """The parent run identifier, anchored to the VIEWPORT and not to the panel.

    It stays visible when the panel is collapsed, because it is what a person quotes in a bug
    report and what an operator uses to find the run.
    """
    if not run_id:
        return ""
    return tag(
        "div",
        join(
            tag("span", "run"),
            tag("a", esc(run_id), href=url("runs", run_id), title="open this run"),
            tag(
                "button",
                "copy",
                type="button",
                data_copy=run_id,
                aria_label=f"copy run identifier {run_id}",
            ),
        ),
        class_="run-id",
    )


# --- the left search panel -----------------------------------------------------------------


def _selector(role: str, spec: dict[str, Any], selected: str, *, disabled: bool) -> str:
    """One model dropdown, with every field the UX specification puts on a row."""
    options = []
    blank = spec.get("blank_option")
    if blank is not None:
        options.append(
            tag(
                "option",
                esc(blank["display"]),
                value="",
                selected=(selected == ""),
            )
        )
    for entry in spec["entries"]:
        detail = (
            f"{entry['label']} — {entry['provider']} — {entry['badge']} — {entry['region']}"
            f" — context {entry['context_tokens']:,} — output {entry['max_output_tokens']:,}"
            f" — in {entry['currency']} {entry['price_input_per_1k']}/1k in,"
            f" {entry['price_output_per_1k']}/1k out"
        )
        if entry["uses_inference_profile"]:
            detail += " — via inference profile"
        if not entry["available"]:
            detail += f" — UNAVAILABLE: {entry['disabled_reason']}"
        options.append(
            tag(
                "option",
                esc(detail),
                value=entry["label"],
                selected=(selected == entry["label"]),
                disabled=not entry["available"],
            )
        )
    required = " (required)" if spec["required"] else " (optional)"
    note = (
        "This stage is not executed in Phase 2. The selector exists so the progressive workflow "
        "is real."
        if not spec["executed_in_this_phase"]
        else ""
    )
    if disabled:
        note = (
            "Disabled for this run: the selected parsing model is multimodal and handles filed "
            "images itself. No separate image model is invoked."
        )
    return join(
        tag("label", esc(role.title() + " model" + required), for_=f"sel-{role}"),
        tag(
            "select",
            join(*options),
            name=f"{role}_label",
            id=f"sel-{role}",
            disabled=disabled,
            aria_describedby=f"note-{role}" if note else None,
        ),
        tag("p", esc(note), class_="hint", id=f"note-{role}") if note else "",
    )


def search_panel(
    *,
    selectors: dict[str, Any],
    csrf: str,
    query: str = "",
    entity: dict[str, Any] | None = None,
    matches: list[dict[str, Any]] | None = None,
    filings: list[dict[str, Any]] | None = None,
    chosen: dict[str, str] | None = None,
) -> str:
    """The persistent vertical search form. The chrome around it belongs to `panel_shell`.

    IT TAKES NO `spend` AND CANNOT RENDER ONE. The cumulative figure moved to `panel_shell` for the
    same reason the collapse control and the title did: it belongs to the panel rather than to this
    form, and rendering it only in search mode meant the spend disappeared on every parse page —
    precisely where a reader is looking at what a run cost and deciding whether to spend again. The
    parameter stayed behind for a while, accepted and ignored, which is worse than either: a caller
    passing it had no way to see that nothing came of it.
    """
    chosen = chosen or {}
    roles = selectors["roles"]
    parsing_label = chosen.get("parsing_label", "")
    parsing_entry = next(
        (e for e in roles["parsing"]["entries"] if e["label"] == parsing_label), None
    )
    multimodal = bool(parsing_entry and parsing_entry["multimodal"])

    match_list = ""
    if matches:
        match_list = tag(
            "ul",
            each(
                matches,
                lambda m: tag(
                    "li",
                    tag(
                        "a",
                        esc(f"{m['name']} ({m['cik']})"),
                        href=url(cik=m["cik"]),
                    )
                    + (
                        tag("span", esc(" " + ", ".join(m["tickers"])), class_="hint")
                        if m["tickers"]
                        else ""
                    ),
                ),
            ),
            class_="hint",
        )

    timeframe = ""
    filing_options = ""
    if entity:
        timeframe = join(
            tag("label", "Timeframe", for_="from-date"),
            tag(
                "p",
                esc(
                    f"{entity['filing_count']} qualifying filing(s) between "
                    f"{entity['earliest_filing_date']} and {entity['latest_filing_date']}. "
                    f"Forms present: {', '.join(entity['forms_present'])}."
                ),
                class_="hint",
            ),
            tag(
                "input",
                "",
                type="date",
                id="from-date",
                name="from_date",
                value=chosen.get("from_date", ""),
                min=entity["earliest_filing_date"],
                max=entity["latest_filing_date"],
            ),
            tag(
                "input",
                "",
                type="date",
                name="to_date",
                value=chosen.get("to_date", ""),
                min=entity["earliest_filing_date"],
                max=entity["latest_filing_date"],
            ),
        )
    if filings:
        filing_options = join(
            tag("label", "Exact filing (developer mode)", for_="accession"),
            tag(
                "select",
                join(
                    tag("option", "every filing in the timeframe", value=""),
                    *[
                        tag(
                            "option",
                            esc(
                                f"{f['form_as_filed']} {f['filing_date']} "
                                f"{f['accession']} ~{f['primary_estimated_tokens']:,} est tokens"
                            ),
                            value=f["accession"],
                            selected=(chosen.get("accession") == f["accession"]),
                        )
                        for f in filings
                    ],
                ),
                name="accession",
                id="accession",
            ),
        )

    # THE PROTOCOL IS AN EXPLICIT CHOICE WITH BOTH OPTIONS VISIBLE, NEVER A HIDDEN DEFAULT.
    # Phase 2.1 added model-directed multipart parsing and did NOT retire the single-response
    # protocol: thirty preserved runs used it, and the comparison the phase exists to enable
    # requires both to remain runnable. Multipart is preselected because it is the intended
    # product behaviour; single response is one click away and says what it is.
    strategy = chosen.get("strategy") or "multipart"
    strategy_control = join(
        tag("label", "Parsing protocol", for_="sel-strategy"),
        tag(
            "select",
            join(
                tag(
                    "option",
                    esc(
                        "Multipart, model-directed — the model plans, then produces one part per "
                        "call"
                    ),
                    value="multipart",
                    selected=(strategy == "multipart"),
                ),
                tag(
                    "option",
                    esc("Single response — the Phase 2 protocol, kept for comparison"),
                    value="single_response",
                    selected=(strategy == "single_response"),
                ),
            ),
            name="strategy",
            id="sel-strategy",
        ),
        tag(
            "p",
            esc(
                "The complete filing goes to the model intact under both. What differs is whether "
                "the whole parse has to fit in one response."
            ),
            class_="hint",
        ),
    )

    can_run = bool(entity and parsing_label and parsing_entry and parsing_entry["available"])
    blocked = (
        ""
        if can_run
        else tag(
            "p",
            esc(
                "Select an entity and an available parsing model. The image, summary and "
                "analysis selectors may stay blank."
            ),
            class_="hint",
        )
    )

    # THE COLLAPSE CONTROL AND THE TITLE MOVED TO `panel_shell`. They belong to the panel itself
    # rather than to the search form, and both panel modes need them — a review menu with no way
    # back to search, and no way to collapse, is a corner a reader gets stuck in.
    return join(
        tag(
            "form",
            join(
                tag("label", "Entity or ticker", for_="q"),
                tag("input", "", type="search", id="q", name="q", value=query, placeholder="AAPL"),
                tag("button", "Search", type="submit", class_="run-button"),
            ),
            method="get",
            action="/",
        ),
        match_list,
        tag(
            "form",
            join(
                tag("input", "", type="hidden", name="csrf_token", value=csrf),
                tag("input", "", type="hidden", name="cik", value=entity["cik"] if entity else ""),
                timeframe,
                filing_options,
                strategy_control,
                _selector("parsing", roles["parsing"], parsing_label, disabled=False),
                _selector(
                    "image", roles["image"], chosen.get("image_label", ""), disabled=multimodal
                ),
                _selector(
                    "summary", roles["summary"], chosen.get("summary_label", ""), disabled=False
                ),
                _selector(
                    "analysis", roles["analysis"], chosen.get("analysis_label", ""), disabled=False
                ),
                tag(
                    "button",
                    "Preflight and run",
                    type="submit",
                    class_="run-button",
                    disabled=not can_run,
                ),
                blocked,
            ),
            method="post",
            action="/preflight",
        ),
    )


# --- pages ---------------------------------------------------------------------------------


def home(*, runs: list[dict[str, Any]], catalog: dict[str, Any]) -> str:
    """The workspace before a run is open: the catalog, and every stored run."""
    rows = each(
        runs,
        lambda r: tag(
            "tr",
            join(
                tag(
                    "td",
                    tag("a", esc(r["run_id"]), href=f"/runs/{esc(r['run_id'])}"),
                    class_="mono",
                ),
                tag("td", esc(r["created_at"][:19])),
                tag("td", esc(r["entity_label"])),
                tag("td", esc(r["parsing_label"])),
                tag("td", esc(r["job_count"])),
                tag("td", esc(r["ready_for_review"])),
                tag("td", esc(f"USD {r['actual_cost_usd']}")),
            ),
        ),
    )
    table = (
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
                                    tag("th", h)
                                    for h in (
                                        "run",
                                        "created",
                                        "entity",
                                        "parsing model",
                                        "filings",
                                        "ready",
                                        "spend",
                                    )
                                ]
                            ),
                        ),
                    ),
                    tag("tbody", rows),
                ),
            ),
            class_="scroll-x",
        )
        if runs
        else tag("p", "No evaluation runs are stored yet.")
    )
    return join(
        tag("h1", "Parser review"),
        tag(
            "div",
            join(
                tag("h2", "Catalog"),
                tag(
                    "p",
                    esc(
                        f"{catalog['entity_count']} entities and {catalog['filing_count']} "
                        "preserved filings are available. An entity with no qualifying filing "
                        "never appears."
                    ),
                ),
            ),
            class_="card",
        ),
        tag("div", join(tag("h2", "Evaluation runs"), table), class_="card"),
    )


def preflight_page(*, plan: dict[str, Any], csrf: str, form: dict[str, str]) -> str:
    """What a run would send and what it could cost, before anything billable happens."""
    rows = each(
        plan["filings"],
        lambda item: tag(
            "tr",
            join(
                tag("td", esc(item["filing"]["form_as_filed"])),
                tag("td", esc(item["filing"]["accession"]), class_="mono"),
                tag("td", esc(item["filing"]["transport_era"])),
                tag("td", esc(f"{item['submitted_members']} ({item['submitted_bytes']:,} B)")),
                tag(
                    "td",
                    esc(f"{item['reused_members']} reused / {item['fetched_members']} fetched"),
                ),
                tag("td", esc(f"{item['compatibility']['estimated_input_tokens']:,}")),
                tag("td", esc(f"{item['requested_output_tokens']:,}")),
                tag("td", esc(f"USD {item['worst_case_cost_usd']}")),
                tag(
                    "td",
                    badge("fits", "ok") if item["compatible"] else badge(item["reason"], "warn"),
                ),
            ),
        ),
    )
    incompatible = [i for i in plan["filings"] if not i["compatible"]]
    notes = each(incompatible, lambda i: warning(i["detail"]))
    routing = plan["routing"]["parsing"]
    cross = warning(routing["cross_region_reason"]) if routing["cross_region_reason"] else ""
    profile = (
        tag(
            "p",
            esc(
                f"Invoked through inference profile {routing['inference_profile_id']}. The profile "
                "may route across more than one AWS region; the executing region is recorded when "
                "the provider reports it."
            ),
        )
        if routing["inference_profile_id"]
        else ""
    )
    hidden = join(
        tag("input", "", type="hidden", name="csrf_token", value=csrf),
        *[
            tag("input", "", type="hidden", name=key, value=value)
            for key, value in form.items()
            if key != "csrf_token"
        ],
    )
    return join(
        tag("h1", "Cost preflight"),
        tag(
            "div",
            join(
                tag("h2", "Routing"),
                tag(
                    "p",
                    esc(
                        f"{routing['label']} as {routing['role']} in {routing['region']} "
                        f"(preferred {routing['preferred_region']}); "
                        f"{'multimodal' if routing['multimodal'] else 'text only'}; "
                        f"invocation identifier {routing['invocation_id']}"
                    ),
                ),
                cross,
                profile,
                tag(
                    "p",
                    esc(
                        f"Prompt {plan['prompt']['prompt_id']} version "
                        f"{plan['prompt']['version']}, sha256 {plan['prompt']['sha256'][:16]}…"
                    ),
                ),
            ),
            class_="card",
        ),
        tag(
            "div",
            join(
                tag("h2", "Filings"),
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
                                            tag("th", h)
                                            for h in (
                                                "form",
                                                "accession",
                                                "era",
                                                "submitted",
                                                "source",
                                                "est. input",
                                                "output cap",
                                                "worst case",
                                                "compatible",
                                            )
                                        ]
                                    ),
                                ),
                            ),
                            tag("tbody", rows),
                        ),
                    ),
                    class_="scroll-x",
                ),
                notes,
                tag(
                    "p",
                    esc(
                        f"Worst case for this run: USD {plan['worst_case_total_usd']}. "
                        f"Cumulative spend so far USD {plan['already_spent_usd']} against a "
                        f"ceiling of USD {plan['ceiling_usd']}."
                    ),
                ),
                tag("p", esc(plan["cost_note"]), class_="hint"),
                (
                    tag(
                        "form",
                        join(hidden, tag("button", "Run now", type="submit", class_="run-button")),
                        method="post",
                        action="/runs",
                    )
                    if plan["within_ceiling"] and plan["compatible_filings"]
                    else warning(
                        "This run cannot start: no filing is compatible, or the worst case would "
                        "exceed the cumulative authorized ceiling. Nothing is shrunk, dropped or "
                        "downgraded to fit."
                    )
                ),
            ),
            class_="card",
        ),
    )


def run_page(
    *,
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    hub: str = "",
) -> str:
    """One parent run: its child filing jobs, each with its own identifier and terminal state.

    `hub` IS THE PARSE HUB, INLINED WHEN THIS RUN HAS EXACTLY ONE JOB. Every run in this store has
    one — verified across 71 of them — so the job table is otherwise a one-row indirection between
    the reader and the only thing on the page they came for. It is NOT inlined for a multi-job run:
    thirteen destination rows times eleven jobs is not a page, and each row links to its own hub.

    The run page is not redirected away even when it inlines the hub. The run owns the selections
    that produced it and its stored event log, and the anchored run-identifier bar links here.
    """
    rows = each(
        jobs,
        lambda j: tag(
            "tr",
            join(
                tag(
                    "td",
                    tag(
                        "a",
                        esc(j["job_id"]),
                        # EVERY JOB OPENS AT ITS HUB, WHATEVER PROTOCOL RAN IT. This used to
                        # branch on `strategy`, so the same click went to two different pages
                        # depending on a field the reader could not see. It also answered the
                        # wrong question: the first thing a reviewer wants of a job is not "which
                        # calls ran" but "is this parse correct", and the hierarchy is one click
                        # away from the hub as steps 1 and 5.
                        href=url("runs", run["run_id"], "jobs", j["job_id"], "review"),
                    ),
                    class_="mono",
                ),
                tag("td", esc(j.get("strategy") or "single_response")),
                tag("td", esc(j["filing"]["form_as_filed"])),
                tag("td", esc(j["filing"]["accession"]), class_="mono"),
                tag(
                    "td",
                    badge(j["execution_state"], _STATE_KIND.get(j["execution_state"], "neutral")),
                ),
                tag("td", badge(j["review_state"], _REVIEW_KIND.get(j["review_state"], "neutral"))),
                tag("td", esc(j.get("validation_status") or "—")),
                tag("td", esc(f"USD {j.get('actual_cost_usd') or '0'}")),
            ),
        ),
    )
    event_rows = each(
        events,
        lambda e: tag(
            "tr",
            join(
                tag("td", esc(e["event_id"]), class_="mono"),
                tag("td", esc(e["at"][11:19])),
                tag("td", esc(e["kind"])),
                tag("td", esc(e["message"])),
            ),
        ),
    )
    return join(
        tag("h1", esc(f"Run {run['run_id']}")),
        tag(
            "div",
            join(
                tag(
                    "p",
                    esc(
                        f"{run['entity_label']} ({run['cik']}) — parsing model "
                        f"{run['selections']['parsing']} - stages executed: "
                        f"{', '.join(run['selected_roles'])}"
                    ),
                ),
                tag(
                    "p",
                    esc(
                        "Blank image, summary and analysis selectors ran NO stage. No model was "
                        "chosen for them and the parsing model was not borrowed."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        ),
        # THE HUB, WHEN THERE IS EXACTLY ONE JOB TO HUB. Rendered above the job table rather than
        # instead of it: the table still states the job identifier, its protocol and its terminal
        # states, which are run-level facts the hub does not repeat.
        hub,
        tag(
            "div",
            join(
                tag("h2", "Child filing jobs"),
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
                                            tag("th", h)
                                            for h in (
                                                "job",
                                                "protocol",
                                                "form",
                                                "accession",
                                                "execution",
                                                "review",
                                                "validation",
                                                "spend",
                                            )
                                        ]
                                    ),
                                ),
                            ),
                            tag("tbody", rows),
                        ),
                    ),
                    class_="scroll-x",
                ),
            ),
            class_="card",
        ),
        tag(
            "div",
            join(
                tag("h2", "Progress"),
                tag(
                    "p",
                    esc(
                        "Live events stream from /runs/"
                        + run["run_id"]
                        + "/events and resume with Last-Event-ID. This table is the stored log."
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
                                    join(*[tag("th", h) for h in ("id", "at", "kind", "message")]),
                                ),
                            ),
                            tag("tbody", event_rows),
                        ),
                    ),
                    class_="scroll-x",
                ),
            ),
            class_="card",
        ),
    )
