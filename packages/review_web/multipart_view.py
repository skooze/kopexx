"""The review surface for a multipart parse: the hierarchy, one task, and the assembled index.

WHAT A REVIEWER HAS TO BE ABLE TO SEE, AND WHY EACH ONE IS SEPARATE.

    THE HIERARCHY      which calls ran, in the order the model's own plan put them, with each
                       one's state, cost, output size, stop reason and validation. A parse of a
                       dozen calls is not reviewable as a list of runs.

    ONE TASK           the exact request, the exact response, the structured reading of it, the
                       preserved filing beside it, and every citation checked against the bytes.
                       This is the Phase 2 review page, one level down.

    THE ASSEMBLED VIEW the parts in the model's order, under the model's titles, with a link from
                       every part back to the response that produced it. It is an INDEX and says so
                       — nothing here is a rewritten parse.

A TRUNCATED BRANCH IS SHOWN AS A BRANCH, NOT AS A FAILED MODEL. Section 21.5 of the Phase 2.1 brief
is explicit and the reason is measurable: Phase 2 labelled whole candidates truncated because one
response hit a cap. A truncated attempt here shows the cap it reached, the tokens it produced, its
exact partial output, the replanning call it caused, the subparts that came out of that, and
whether the branch finished.

EVERY VALUE IS ESCAPED, INCLUDING THE ONES A MODEL CHOSE. A part identifier, a title and a node
type are strings a language model wrote after reading an untrusted filing. They are displayed as
text through `html.esc`, exactly as filing bytes are, and they are never interpreted.
"""

from __future__ import annotations

from typing import Any

from .html import badge, each, esc, join, tag, url, warning

_TASK_STATE_KIND = {
    "SUCCEEDED": "ok",
    "READY_FOR_REVIEW": "ok",
    "RUNNING": "info",
    "RESERVED": "info",
    "READY": "info",
    "VALIDATING": "info",
    "RESPONSE_RECEIVED": "info",
    "WAITING_FOR_RECONCILIATION": "info",
    "CREATED": "neutral",
    "BLOCKED": "warn",
    "TRUNCATED": "warn",
    "INTERRUPTED": "warn",
    "CANCELLED": "neutral",
    "FAILED": "bad",
}

#: Queue controls, each an explicit user action that may spend money. Every one is a form POST with
#: a CSRF token; none is a link, because a link is something a browser can be made to follow.
_QUEUE_ACTIONS = (
    ("resume", "Resume interrupted work"),
    ("unblock", "Re-arm budget-paused work"),
    ("advance", "Run the next queued call"),
    ("reconcile", "Run reconciliation now"),
)


def _cost(value: Any) -> str:
    return f"USD {value or '0'}"


def _task_row(base: tuple[str, ...], task: dict[str, Any]) -> str:
    """One row of the hierarchy. Indentation carries the model's own parent relationship."""
    attempts = task.get("attempts") or []
    last = attempts[-1] if attempts else {}
    depth = int(task.get("depth") or 0)
    created = task.get("model_created") or {}
    label = str(created.get("part_id") or "") or task["task_type"].replace("_", " ").lower()
    indent = "    " * depth
    return tag(
        "tr",
        join(
            tag(
                "td",
                join(
                    tag("span", indent) if depth else "",
                    tag("a", esc(label), href=url(*base, "tasks", task["task_id"])),
                ),
            ),
            tag("td", esc(task["task_type"])),
            tag("td", badge(task["state"], _TASK_STATE_KIND.get(task["state"], "neutral"))),
            tag("td", esc(task["prompt"]["prompt_id"] + "@" + task["prompt"]["version"])),
            tag("td", esc(f"{int(last.get('output_tokens') or 0):,}")),
            tag("td", esc(f"{int(task['settings']['max_output_tokens']):,}")),
            tag("td", esc(last.get("stop_reason") or "—")),
            tag("td", esc(_cost(task.get("actual_cost_usd")))),
            tag("td", esc(_validation_summary(task))),
        ),
    )


def _validation_summary(task: dict[str, Any]) -> str:
    """One line of what the backend proved about this task's response, or why it could not."""
    validation = task.get("validation") or {}
    coverage = validation.get("coverage") or {}
    if coverage:
        return (
            f"{coverage.get('references_resolved', 0)}/{coverage.get('reference_count', 0)} refs, "
            f"{coverage.get('node_count', 0)} nodes"
        )
    if "schedulable" in validation:
        return "plan schedulable" if validation["schedulable"] else "plan NOT schedulable"
    if task.get("error"):
        return "unreadable"
    return "—"


def _session_card(job: dict[str, Any]) -> str:
    """The run-strategy header section 21.1 requires, with every field it names."""
    session = job.get("multipart") or {}
    routing = job.get("model_routing") or {}
    by_state = session.get("by_state") or {}
    return tag(
        "div",
        join(
            tag("h2", "Multipart model-directed parse"),
            tag(
                "p",
                esc(
                    f"{routing.get('label')} in {routing.get('region')} — "
                    f"{job['filing']['form_as_filed']} {job['filing']['accession']} — "
                    f"source set {str(job.get('source_set_id') or '')[:16]}"
                ),
            ),
            tag(
                "p",
                esc(
                    f"plan {session.get('parse_plan_id') or 'not yet produced'}; "
                    f"{session.get('planned_part_count', 0)} planned part(s); "
                    f"{session.get('task_count', 0)} task(s), "
                    f"{by_state.get('SUCCEEDED', 0)} succeeded, "
                    f"{by_state.get('READY', 0) + by_state.get('CREATED', 0)} queued, "
                    f"{session.get('truncated', 0)} truncated, "
                    f"{session.get('blocked', 0)} paused, "
                    f"{session.get('failed', 0)} failed, "
                    f"{session.get('interrupted', 0)} interrupted"
                ),
            ),
            tag(
                "p",
                esc(
                    f"reconciliation cycle limit {session.get('reconciliation_cycle_limit')}; "
                    f"recursion depth limit {session.get('recursion_depth_limit')}; "
                    f"format repairs per artifact {session.get('format_repair_limit_per_artifact')}"
                ),
                class_="hint",
            ),
            tag(
                "p",
                esc(
                    f"this filing has spent USD {session.get('filing_spent_usd', '0')} of its "
                    f"USD {session.get('filing_budget_usd')} budget; "
                    f"USD {session.get('filing_remaining_usd', '0')} remains. Phase "
                    f"{session.get('phase') or 'unlabelled'} has spent USD "
                    f"{session.get('phase_spent_usd', '0')} of "
                    f"USD {session.get('phase_ceiling_usd')}."
                ),
            ),
            (
                tag(
                    "p",
                    esc(f"mechanical assembly: {session.get('assembly_status')}"),
                )
                if session.get("assembly_status")
                else ""
            ),
        ),
        class_="card",
    )


def _queue_controls(base: tuple[str, ...], csrf: str) -> str:
    """Authenticated development controls. Every one is a POST and every one spends or unblocks."""
    return tag(
        "div",
        join(
            tag("h2", "Queue"),
            tag(
                "p",
                esc(
                    "Every control below is an explicit action. Nothing on this page resumes, "
                    "retries or re-invokes anything on its own — a rerun is billable, and money is "
                    "never spent by a page being opened."
                ),
                class_="hint",
            ),
            *[
                tag(
                    "form",
                    join(
                        tag("input", "", type="hidden", name="csrf_token", value=csrf),
                        tag("input", "", type="hidden", name="action", value=action),
                        tag("button", esc(label), type="submit"),
                    ),
                    method="post",
                    action=url(*base, "queue"),
                    class_="inline",
                )
                for action, label in _QUEUE_ACTIONS
            ],
        ),
        class_="card",
    )


def multipart_page(
    *,
    run: dict[str, Any],
    job: dict[str, Any],
    tasks: list[dict[str, Any]],
    assembly: dict[str, Any] | None,
    csrf: str,
) -> str:
    """The hierarchy view for one filing's multipart parse."""
    base = ("runs", run["run_id"], "jobs", job["job_id"])
    headers = (
        "part or call",
        "kind",
        "state",
        "prompt",
        "output",
        "cap",
        "stop",
        "spend",
        "validation",
    )
    rows = each(tasks, lambda t: _task_row(base, t))
    truncated = [t for t in tasks if t["state"] == "TRUNCATED"]
    blocked = [t for t in tasks if t["state"] == "BLOCKED"]

    return join(
        tag("h1", esc(f"Multipart parse — {job['filing']['accession']}")),
        tag(
            "p",
            join(
                tag("a", esc(f"run {run['run_id']}"), href=url("runs", run["run_id"])),
                tag("span", esc(f"  child job {job['job_id']}"), class_="mono"),
                tag("a", " assembled view", href=url(*base, "assembled")),
                tag("a", " single-response review page", href=url(*base)),
            ),
        ),
        _session_card(job),
        each(
            truncated,
            lambda t: warning(
                f"part {(t.get('model_created') or {}).get('part_id') or ''} reached the output "
                f"limit of {t['settings']['max_output_tokens']:,} tokens. The partial response is "
                "preserved and is NOT merged into the parse; a replanning call divides the part."
            ),
        ),
        each(
            blocked,
            lambda t: warning(
                f"a call is paused: {t.get('blocked_reason') or 'no reason recorded'}"
            ),
        ),
        tag(
            "div",
            join(
                tag("h2", "Calls, in the model's own order"),
                tag(
                    "p",
                    esc(
                        "Indentation is the model's own parent relationship. Part identifiers and "
                        "titles are the model's words and are never renamed."
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
                                tag("tr", join(*[tag("th", h) for h in headers])),
                            ),
                            tag("tbody", rows),
                        ),
                    ),
                    class_="scroll-x",
                ),
            ),
            class_="card",
        ),
        _assembly_card(base, assembly),
        _queue_controls(base, csrf),
    )


def _assembly_card(base: tuple[str, ...], assembly: dict[str, Any] | None) -> str:
    if assembly is None:
        return tag(
            "div",
            join(
                tag("h2", "Mechanical assembly"),
                tag("p", "No assembly has been written for this parse yet."),
            ),
            class_="card",
        )
    validation = assembly.get("validation") or {}
    return tag(
        "div",
        join(
            tag("h2", "Mechanical assembly"),
            tag("p", join(badge(assembly["status"], "info"), esc(" " + assembly["status_note"]))),
            tag(
                "p",
                esc(
                    f"{assembly['parts_with_a_terminal_result']} of {assembly['parts_expected']} "
                    f"part(s) reached a terminal result; {assembly['node_count']} node(s); "
                    f"{assembly['references_resolved']} of {assembly['reference_count']} source "
                    f"references located in the preserved bytes; "
                    f"{assembly['unresolved_item_count']} unresolved item(s); "
                    f"{assembly['truncation_events']} truncation event(s)"
                ),
            ),
            tag(
                "p",
                esc(
                    f"{assembly['total_input_tokens']:,} input and "
                    f"{assembly['total_output_tokens']:,} output tokens across "
                    f"{len(assembly['tasks'])} call(s); largest single response "
                    f"{assembly['maximum_single_response_output_tokens']:,} tokens; "
                    f"{assembly['total_latency_ms']:,} ms; "
                    f"{_cost(assembly['total_cost_usd'])}"
                ),
            ),
            tag(
                "p",
                esc(
                    "model-declared complete: "
                    f"{assembly['model_declared_complete']}; reconciliation unresolved: "
                    f"{assembly['reconciliation_unresolved']}; human review required: "
                    f"{assembly['human_review_required']}"
                ),
                class_="hint",
            ),
            each(validation.get("findings", []), warning),
            tag("p", tag("a", "open the assembled filing view", href=url(*base, "assembled"))),
        ),
        class_="card",
    )


# --- the assembled view -----------------------------------------------------------------------


def assembled_page(*, run: dict[str, Any], job: dict[str, Any], assembly: dict[str, Any]) -> str:
    """The parts in the model's order, under the model's titles, linked back to their responses."""
    base = ("runs", run["run_id"], "jobs", job["job_id"])

    def part(entry: dict[str, Any]) -> str:
        nodes = entry.get("nodes") or []
        return tag(
            "div",
            join(
                tag(
                    "div",
                    esc(f"{entry['type'] or '(no type)'} — part {entry['part_id']}"),
                    class_="kind",
                ),
                tag("div", esc(entry["title"] or "(no title)"), class_="title"),
                tag(
                    "p",
                    esc(
                        f"declared {entry['declared_status'] or 'nothing'}; "
                        f"{entry['node_count']} node(s); "
                        f"{entry['references_resolved']} of {entry['reference_count']} references "
                        f"located; {entry['output_tokens']:,} output tokens; "
                        f"{_cost(entry['actual_cost_usd'])}"
                    ),
                    class_="hint",
                ),
                (
                    warning(
                        "this part's attempt reached the output limit. Its partial content is "
                        "preserved as evidence and is not part of the assembled parse."
                    )
                    if entry["truncated"]
                    else ""
                ),
                (
                    tag("p", esc("coverage: " + entry["coverage_summary"]))
                    if entry.get("coverage_summary")
                    else ""
                ),
                tag(
                    "ul",
                    each(
                        nodes,
                        lambda n: tag(
                            "li",
                            esc(
                                f"{n.get('type') or '(no type)'} — {n.get('title') or '(no title)'}"
                            ),
                        ),
                    ),
                    class_="refs",
                ),
                tag(
                    "p",
                    tag(
                        "a",
                        "open the exact response that produced this part",
                        href=url(*base, "tasks", entry["task_id"]),
                    ),
                ),
            ),
            class_="node",
        )

    unresolved = [p for p in assembly["parts"] if p["unresolved_count"]]
    coverage = assembly.get("image_coverage") or {}
    return join(
        tag("h1", esc(f"Assembled parse — {job['filing']['accession']}")),
        tag(
            "p",
            join(
                tag("a", "back to the call hierarchy", href=url(*base, "multipart")),
                tag("span", esc(f"  {assembly['part_count']} part(s)"), class_="mono"),
            ),
        ),
        tag(
            "div",
            join(
                tag("h2", "What this view is"),
                tag("p", esc(assembly["assembly_note"])),
                tag("p", esc(assembly["status_note"]), class_="hint"),
            ),
            class_="card",
        ),
        (
            warning(
                f"{coverage.get('image_member_count', 0)} image-bearing member(s) were filed and "
                "were NOT analysed. This parse does not claim image coverage. "
                + str(coverage.get("reason", ""))
            )
            if coverage.get("image_member_count") and not coverage.get("analysed")
            else ""
        ),
        (
            warning(
                f"{sum(p['unresolved_count'] for p in unresolved)} item(s) across "
                f"{len(unresolved)} part(s) were declared unresolved by the model."
            )
            if unresolved
            else ""
        ),
        tag("div", join(tag("h2", "Parts"), each(assembly["parts"], part)), class_="card"),
    )


# --- one task ---------------------------------------------------------------------------------


def task_page(
    *,
    run: dict[str, Any],
    job: dict[str, Any],
    task: dict[str, Any],
    view: str,
    artifacts: list[str],
    artifact: str,
    artifact_text: str,
    focus: int | None,
    focus_length: int,
    parsed: dict[str, Any] | None,
    request_brief: str,
    raw_response: str,
    reasoning: str,
    comments: list[dict[str, Any]],
    csrf: str,
    permitted_reviews: list[str],
) -> str:
    """The review page for ONE call of a multipart parse.

    Deliberately built from the same panes as the single-response page — raw, parsed, side by side,
    source-reference navigation — because a part IS a parsed artifact and reviewing one is the same
    activity one level down. What is added is the call's place in the parse and, when the call was
    truncated, what happened to it.
    """
    from .job_view import parsed_pane, raw_pane, view_controls

    base = ("runs", run["run_id"], "jobs", job["job_id"])
    task_base = (*base, "tasks", task["task_id"])
    created = task.get("model_created") or {}
    attempts = task.get("attempts") or []
    last = attempts[-1] if attempts else {}
    coverage = (task.get("validation") or {}).get("coverage") or {}

    outcomes_by_node: dict[str, list[dict[str, Any]]] = {}
    for outcome in coverage.get("references", []):
        outcomes_by_node.setdefault(outcome["node_id"], []).append(outcome)

    raw = raw_pane(filename=artifact, text=artifact_text, focus=focus, focus_length=focus_length)
    structured = parsed_pane(
        base=task_base,
        view=view,
        parsed=parsed,
        outcomes_by_node=outcomes_by_node,
        raw_response=raw_response,
    )
    panes = (
        raw
        if view == "raw"
        else structured
        if view == "parsed"
        else tag("div", join(raw, structured), class_="panes")
    )

    truncation = task.get("truncation") or {}
    truncation_card = (
        tag(
            "div",
            join(
                tag("h2", "Output limit reached"),
                warning(
                    f"this attempt stopped at the provider's output limit. Stop reason "
                    f"{truncation.get('stop_reason')}; {truncation.get('output_tokens', 0):,} "
                    f"output tokens against a configured cap of "
                    f"{truncation.get('configured_cap', 0):,}."
                ),
                tag("p", esc(str(truncation.get("disposition") or ""))),
            ),
            class_="card",
        )
        if truncation
        else ""
    )

    review_form = tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag(
                "select",
                join(*[tag("option", esc(state), value=state) for state in permitted_reviews]),
                name="review_state",
                aria_label="review state",
            ),
            tag("input", "", type="text", name="note", placeholder="reason or note"),
            tag("button", "Set review state", type="submit"),
        ),
        method="post",
        action=url(*base, "review"),
        class_="inline",
    )

    retry_form = tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag("input", "", type="hidden", name="action", value="retry"),
            tag("input", "", type="hidden", name="task_id", value=task["task_id"]),
            tag("button", "Retry this call (billable)", type="submit"),
        ),
        method="post",
        action=url(*base, "queue"),
        class_="inline",
    )
    cancel_form = tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag("input", "", type="hidden", name="action", value="cancel_branch"),
            tag("input", "", type="hidden", name="task_id", value=task["task_id"]),
            tag("button", "Cancel this branch", type="submit"),
        ),
        method="post",
        action=url(*base, "queue"),
        class_="inline",
    )

    comment_form = tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag("input", "", type="hidden", name="target_type", value="multipart_task"),
            tag("input", "", type="hidden", name="target_id", value=task["task_id"]),
            tag("textarea", "", name="text", required=True, aria_label="comment text"),
            tag("button", "Add comment", type="submit"),
        ),
        method="post",
        action=url(*base, "comments"),
        class_="inline",
    )

    return join(
        tag(
            "h1",
            esc(
                f"{task['task_type']} — {created.get('part_id') or 'no part'} — "
                f"{job['filing']['accession']}"
            ),
        ),
        tag(
            "p",
            join(
                tag("a", "back to the call hierarchy", href=url(*base, "multipart")),
                tag("span", esc(f"  task {task['task_id']}"), class_="mono"),
            ),
        ),
        tag(
            "p",
            join(
                badge(task["state"], _TASK_STATE_KIND.get(task["state"], "neutral")),
                " ",
                badge(task["task_type"], "neutral"),
            ),
        ),
        truncation_card,
        view_controls(task_base, view, artifact),
        panes,
        tag(
            "div",
            join(
                tag("h2", "Invocation"),
                tag(
                    "p",
                    esc(
                        f"prompt {task['prompt']['prompt_id']} version "
                        f"{task['prompt']['version']} (sha256 {task['prompt']['sha256'][:16]}); "
                        f"output cap {task['settings']['max_output_tokens']:,}; "
                        f"target {task.get('output_target_tokens') or 0:,} visible tokens; "
                        f"temperature {task['settings']['temperature']}"
                    ),
                ),
                tag(
                    "p",
                    esc(
                        f"{int(last.get('input_tokens') or 0):,} input and "
                        f"{int(last.get('output_tokens') or 0):,} output tokens, stop reason "
                        f"{last.get('stop_reason') or 'unreported'}, "
                        f"{int(last.get('latency_ms') or 0):,} ms, "
                        f"{_cost(task.get('actual_cost_usd'))} "
                        f"(reserved {_cost(task.get('reserved_cost_usd'))}), "
                        f"{task.get('attempt_count', 0)} attempt(s)"
                    ),
                ),
                (
                    tag("p", esc(f"blocked: {task['blocked_reason']}"), class_="warning")
                    if task.get("blocked_reason")
                    else ""
                ),
                (
                    tag("p", esc(f"error: {task['error']}"), class_="warning")
                    if task.get("error")
                    else ""
                ),
                tag(
                    "p",
                    esc(
                        "identity for duplicate-schedule protection: "
                        + str(task.get("idempotency") or "")[:16]
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        ),
        _coverage_card(coverage),
        tag(
            "div",
            join(
                tag("h2", "Exact request brief"),
                tag(
                    "p",
                    esc(
                        "the synthetic half of the request, exactly as it was compiled. The "
                        "complete filing travelled beside it as preserved artifacts."
                    ),
                    class_="hint",
                ),
                tag("pre", esc(request_brief), class_="source"),
            ),
            class_="card",
        ),
        tag(
            "div",
            join(
                tag("h2", "Exact model response"),
                tag(
                    "p",
                    esc(
                        "the bytes the model returned, preserved before anything read them. This "
                        "is authoritative when it and the parsed view could disagree."
                    ),
                    class_="hint",
                ),
                tag("pre", esc(raw_response), class_="source"),
            ),
            class_="card",
        ),
        (
            tag(
                "div",
                join(tag("h2", "Reasoning content"), tag("pre", esc(reasoning), class_="source")),
                class_="card",
            )
            if reasoning
            else ""
        ),
        tag("div", join(tag("h2", "Queue"), retry_form, cancel_form), class_="card"),
        tag("div", join(tag("h2", "Review this filing"), review_form), class_="card"),
        tag(
            "div",
            join(
                tag("h2", "Comments"),
                (
                    tag(
                        "ul",
                        each(
                            comments,
                            lambda c: tag(
                                "li",
                                esc(
                                    f"[{c['created_at'][:19]}] {c['author']} on "
                                    f"{c['target_type']} {c['target_id']}: {c['text']}"
                                ),
                            ),
                        ),
                        class_="refs",
                    )
                    if comments
                    else tag("p", "No comments yet.", class_="hint")
                ),
                comment_form,
            ),
            class_="card",
        ),
    )


def _coverage_card(coverage: dict[str, Any]) -> str:
    if not coverage:
        return ""
    return tag(
        "div",
        join(
            tag("h2", "Validation"),
            tag(
                "p",
                join(badge(coverage["status"], "info"), esc(" " + coverage["status_note"])),
            ),
            tag(
                "p",
                esc(
                    f"{coverage['node_count']} node(s), {coverage['table_count']} table(s), "
                    f"{coverage['references_resolved']} of {coverage['reference_count']} "
                    f"references resolved, {coverage['references_ambiguous']} ambiguous, "
                    f"{coverage['references_unresolved']} unresolved"
                ),
            ),
            each(coverage.get("findings", []), warning),
        ),
        class_="card",
    )
