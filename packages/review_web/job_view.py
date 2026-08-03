"""The review surface for one child filing job: raw, parsed, and both at once.

THIS IS THE POINT OF PHASE 2. roadmap.md 2b: a parsed artifact cannot be evaluated without looking
at it beside the filing it came from, and reading a YAML document in a terminal is not evaluation.
Everything else built in this phase exists so that this page can show something true.

FOUR THINGS ARE SHOWN AND NEVER CONFLATED.

    RAW              the preserved bytes, escaped, exactly as SEC published them
    PARSED           the model's structure, in the model's own vocabulary
    EXACT RESPONSE   the bytes the model actually returned, before anything read them
    VALIDATION       what the backend proved against the preserved bytes

    The third exists because the second is DERIVED. When a response will not parse there is no
    parsed view at all, and the exact bytes are the only honest thing to show.

SOURCE-REFERENCE NAVIGATION IS A LINK, NOT A SCRIPT. A resolved reference links to the raw view at
the byte offset where the quote was found, and the raw view highlights it there. An unresolved one
is marked as unresolved and is deliberately NOT a link — the UX specification requires that it is
never rendered as though it were cited.
"""

from __future__ import annotations

from typing import Any

from .html import badge, each, esc, join, tag, url, warning

_VIEWS = (("raw", "Raw"), ("parsed", "Parsed"), ("side-by-side", "Side by side"))

_RESOLUTION_KIND = {
    "EXACT": "ok",
    "WHITESPACE_NORMALISED": "ok",
    "TEXT_ONLY": "ok",
    "AMBIGUOUS": "warn",
    "UNRESOLVED": "bad",
    "NO_SUCH_ARTIFACT": "bad",
    "EMPTY_QUOTE": "warn",
}

#: A filing can be megabytes. The browser is sent a window around the point of interest rather
#: than the whole document, and the window is STATED — a silently truncated view of a source of
#: truth is the same defect as a silently truncated request.
RAW_WINDOW_CHARACTERS: int = 240_000


def view_controls(base: tuple[str, ...], current: str, artifact: str) -> str:
    return tag(
        "div",
        join(
            *[
                tag(
                    "a",
                    label,
                    href=url(*base, view=key, artifact=artifact),
                    class_="active" if key == current else None,
                )
                for key, label in _VIEWS
            ]
        ),
        class_="views",
    )


def artifact_controls(base: tuple[str, ...], view: str, artifacts: list[str], current: str) -> str:
    if len(artifacts) < 2:
        return ""
    return tag(
        "div",
        join(
            *[
                tag(
                    "a",
                    esc(name),
                    href=url(*base, view=view, artifact=name),
                    class_="active" if name == current else None,
                )
                for name in artifacts
            ]
        ),
        class_="views",
    )


def raw_pane(*, filename: str, text: str, focus: int | None, focus_length: int) -> str:
    """The preserved bytes as escaped text, with the cited range marked when one was requested."""
    if not text:
        return tag("div", tag("p", "No preserved text is held for this artifact."), class_="card")

    window_note = ""
    start = 0
    body = text
    if focus is not None and 0 <= focus < len(text):
        half = RAW_WINDOW_CHARACTERS // 2
        start = max(0, focus - half)
        body = text[start : start + RAW_WINDOW_CHARACTERS]
    elif len(text) > RAW_WINDOW_CHARACTERS:
        body = text[:RAW_WINDOW_CHARACTERS]

    if len(body) < len(text):
        window_note = tag(
            "p",
            esc(
                f"Showing characters {start:,} to {start + len(body):,} of {len(text):,}. "
                "The preserved artifact is complete on disk; this is a display window."
            ),
            class_="hint",
        )

    if focus is not None and start <= focus < start + len(body):
        local = focus - start
        end = min(local + max(focus_length, 1), len(body))
        marked = join(
            esc(body[:local]),
            tag("mark", esc(body[local:end]), id="focus"),
            esc(body[end:]),
        )
    else:
        marked = esc(body)

    return tag(
        "section",
        join(
            tag("h2", esc(f"Raw source — {filename}")),
            window_note,
            tag("pre", marked, class_="source"),
        ),
    )


def _reference(base: tuple[str, ...], view: str, outcome: dict[str, Any]) -> str:
    kind = _RESOLUTION_KIND.get(outcome["resolution"], "neutral")
    label = badge(outcome["resolution"], kind)
    quote = tag("span", esc(f" “{outcome['quote'][:110]}”"))
    if outcome["offset"] is not None:
        # `match_length` is the length of the span that ACTUALLY matched in the original text,
        # which is not the length of the quote whenever whitespace was collapsed or markup was
        # removed to find it. Highlighting the quote's length would mark the wrong range.
        target = (
            url(
                *base,
                view=view,
                artifact=outcome["filename"],
                offset=outcome["offset"],
                length=max(int(outcome.get("match_length") or 0), len(outcome["quote"]), 1),
            )
            + "#focus"
        )
        return tag("li", join(label, tag("a", quote, href=target)))
    # An unresolved reference is NEVER a link. The UX specification requires that it is marked
    # rather than rendered as cited, and a link would render it as cited.
    return tag("li", join(label, quote, tag("span", " — not located in the preserved bytes")))


def _table(table: dict[str, Any]) -> str:
    rows = table.get("rows") or []
    caption = table.get("caption") or table.get("title") or ""
    return tag(
        "div",
        join(
            tag("h3", esc(caption)) if caption else "",
            tag(
                "table",
                tag(
                    "tbody",
                    each(
                        rows,
                        lambda row: tag(
                            "tr",
                            join(
                                *[
                                    tag("td", esc(cell))
                                    for cell in (row if isinstance(row, list) else [row])
                                ]
                            ),
                        ),
                    ),
                ),
            ),
        ),
        class_="scroll-x",
    )


def parsed_pane(
    *,
    base: tuple[str, ...],
    view: str,
    parsed: dict[str, Any] | None,
    outcomes_by_node: dict[str, list[dict[str, Any]]],
    raw_response: str,
) -> str:
    """The model's structure in the model's own words, or the exact bytes when it will not parse."""
    if parsed is None:
        return tag(
            "section",
            join(
                tag("h2", "Parsed"),
                warning(
                    "Structured parse unavailable: the response is not one readable YAML 1.2 "
                    "document. The exact bytes the model returned are shown below and the run is "
                    "kept - it was billable and cannot be regenerated for free."
                ),
                tag("h3", "Exact model response"),
                tag("pre", esc(raw_response), class_="source"),
            ),
        )

    nodes = parsed.get("nodes") or []

    def node(item: dict[str, Any]) -> str:
        references = outcomes_by_node.get(str(item.get("id") or ""), [])
        return tag(
            "div",
            join(
                tag("div", esc(item.get("type") or "(no type)"), class_="kind"),
                tag("div", esc(item.get("title") or "(no title)"), class_="title"),
                tag("div", esc(item.get("content") or ""), class_="body"),
                (
                    warning(
                        "This node depends on image content. Whether that image was analysed is "
                        "recorded in the image-coverage report for this job."
                    )
                    if item.get("image")
                    else ""
                ),
                (
                    tag("p", esc("Ambiguity: " + str(item["ambiguity"])), class_="hint")
                    if item.get("ambiguity")
                    else ""
                ),
                each(item.get("tables") or [], _table),
                (
                    tag(
                        "ul",
                        each(references, lambda o: _reference(base, view, o)),
                        class_="refs",
                    )
                    if references
                    else tag("p", "No source reference was supplied for this node.", class_="refs")
                ),
            ),
            class_="node",
        )

    unresolved = parsed.get("unresolved") or []
    unresolved_block = (
        tag(
            "div",
            join(
                tag("h3", "Declared unresolved by the model"),
                tag(
                    "ul",
                    each(
                        unresolved,
                        lambda u: tag(
                            "li",
                            esc(f"{u.get('what', '')} - {u.get('where', '')} - {u.get('why', '')}"),
                        ),
                    ),
                ),
            ),
            class_="card",
        )
        if unresolved
        else ""
    )

    return tag(
        "section",
        join(
            tag("h2", "Parsed"),
            tag(
                "p",
                esc(
                    f"{len(nodes)} node(s), in the filing's own vocabulary. No backend taxonomy is "
                    "applied and an unfamiliar label is displayed rather than dropped."
                ),
                class_="hint",
            ),
            each(nodes, node),
            unresolved_block,
        ),
    )


def _invocation_card(job: dict[str, Any]) -> str:
    routing = job.get("model_routing") or {}
    cross = warning(routing["cross_region_reason"]) if routing.get("cross_region_reason") else ""
    attempts = job.get("attempts") or []
    last = attempts[-1] if attempts else {}
    source_set = job.get("source_set") or {}
    return tag(
        "div",
        join(
            tag("h2", "Invocation"),
            tag(
                "p",
                esc(
                    f"{routing.get('label')} - {routing.get('invocation_id')} - region "
                    f"{routing.get('region')} - "
                    f"{'multimodal' if routing.get('multimodal') else 'text only'}"
                ),
            ),
            cross,
            (
                tag(
                    "p",
                    esc(
                        "Invoked through inference profile "
                        f"{routing['inference_profile_id']}. The profile may route across more "
                        "than one AWS region."
                    ),
                )
                if routing.get("inference_profile_id")
                else ""
            ),
            tag(
                "p",
                esc(
                    f"prompt {job['prompt']['prompt_id']} version {job['prompt']['version']} "
                    f"(sha256 {job['prompt']['sha256'][:16]}), output cap "
                    f"{job['settings']['max_output_tokens']:,}, temperature "
                    f"{job['settings']['temperature']}"
                ),
            ),
            tag(
                "p",
                esc(
                    f"{last.get('input_tokens', 0):,} input and {last.get('output_tokens', 0):,} "
                    f"output tokens, stop reason {last.get('stop_reason') or 'unreported'}, "
                    f"{last.get('latency_ms', 0):,} ms, USD {job.get('actual_cost_usd') or '0'} "
                    f"(reserved USD {job.get('reserved_cost_usd') or '0'})"
                ),
            ),
            (
                tag(
                    "p",
                    esc(
                        f"{last.get('reasoning_characters', 0):,} characters of reasoning content "
                        "were returned before the answer and are preserved separately."
                    ),
                )
                if last.get("reasoning_characters")
                else ""
            ),
            tag(
                "p",
                esc(
                    f"source set {str(job.get('source_set_id') or '')[:16]} - "
                    f"{source_set.get('reused_members', 0)} member(s) reused from local storage, "
                    f"{source_set.get('fetched_members', 0)} fetched from SEC"
                ),
            ),
        ),
        class_="card",
    )


def _validation_card(validation: dict[str, Any] | None) -> str:
    if not validation:
        return ""
    return tag(
        "div",
        join(
            tag("h2", "Validation"),
            tag(
                "p",
                join(badge(validation["status"], "info"), esc(" " + validation["status_note"])),
            ),
            tag(
                "p",
                esc(
                    f"{validation['node_count']} node(s), {validation['table_count']} table(s), "
                    f"{validation['references_resolved']} of {validation['reference_count']} "
                    f"references resolved, {validation['references_ambiguous']} ambiguous, "
                    f"{validation['references_unresolved']} unresolved; "
                    f"{validation['artifacts_referenced']} of "
                    f"{validation['artifacts_submitted']} submitted artifact(s) cited; "
                    f"source-to-response ratio {validation['source_to_response_ratio']}"
                ),
            ),
            tag(
                "p",
                esc(
                    "numeric signals: "
                    f"{validation['numeric']['numbers_verbatim_in_source']} of "
                    f"{validation['numeric']['numbers_checked']} reported numbers occur in the "
                    f"source; {validation['numeric']['tables_with_a_coherent_column']} of "
                    f"{validation['numeric']['tables_checked']} tables have an arithmetically "
                    "coherent column"
                ),
            ),
            tag(
                "p",
                esc(
                    "model-selected types: "
                    + ", ".join(f"{k} ({v})" for k, v in validation["model_selected_types"].items())
                ),
                class_="hint",
            ),
            each(validation.get("findings", []), warning),
        ),
        class_="card",
    )


def job_page(
    *,
    run: dict[str, Any],
    job: dict[str, Any],
    view: str,
    artifacts: list[str],
    artifact: str,
    artifact_text: str,
    focus: int | None,
    focus_length: int,
    parsed: dict[str, Any] | None,
    raw_response: str,
    reasoning: str,
    validation: dict[str, Any] | None,
    comments: list[dict[str, Any]],
    csrf: str,
    permitted_reviews: list[str],
) -> str:
    """The whole review page for one child filing job."""
    base = ("runs", run["run_id"], "jobs", job["job_id"])
    filing = job["filing"]
    outcomes_by_node: dict[str, list[dict[str, Any]]] = {}
    for outcome in (validation or {}).get("references", []):
        outcomes_by_node.setdefault(outcome["node_id"], []).append(outcome)

    raw = raw_pane(filename=artifact, text=artifact_text, focus=focus, focus_length=focus_length)
    structured = parsed_pane(
        base=base,
        view=view,
        parsed=parsed,
        outcomes_by_node=outcomes_by_node,
        raw_response=raw_response,
    )

    if view == "raw":
        panes = raw
    elif view == "parsed":
        panes = structured
    else:
        panes = tag("div", join(raw, structured), class_="panes")

    coverage = job.get("image_coverage") or {}
    image_warning = (
        warning(
            f"{coverage.get('image_member_count', 0)} image-bearing member(s) were filed and were "
            "NOT analysed. This run does not claim image coverage. "
            + str(coverage.get("reason", ""))
        )
        if coverage.get("image_member_count") and not coverage.get("analysed")
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

    comment_form = tag(
        "form",
        join(
            tag("input", "", type="hidden", name="csrf_token", value=csrf),
            tag(
                "select",
                join(
                    *[
                        tag("option", esc(t), value=t)
                        for t in (
                            "child_job",
                            "parsed_node",
                            "table",
                            "source_reference",
                            "raw_response",
                            "validation_warning",
                            "parent_run",
                        )
                    ]
                ),
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

    comment_list = (
        tag(
            "ul",
            each(
                comments,
                lambda c: tag(
                    "li",
                    esc(
                        f"[{c['created_at'][:19]}] {c['author']} on {c['target_type']}"
                        f"{(' ' + c['target_id']) if c['target_id'] else ''}: {c['text']}"
                    ),
                ),
            ),
            class_="refs",
        )
        if comments
        else tag("p", "No comments yet.", class_="hint")
    )

    reasoning_card = (
        tag(
            "div",
            join(tag("h2", "Reasoning content"), tag("pre", esc(reasoning), class_="source")),
            class_="card",
        )
        if reasoning
        else ""
    )

    evaluation_note = (
        tag(
            "span",
            esc(
                "  EVALUATION - not approved for reuse. Approval records a judgement and "
                "activates nothing: no search consults this artifact and no cache is populated."
            ),
            class_="hint",
        )
        if job["review_state"] == "EVALUATION"
        else ""
    )

    return join(
        tag(
            "h1", esc(f"{filing['form_as_filed']} {filing['accession']} - {filing['issuer_label']}")
        ),
        tag(
            "p",
            join(
                tag("a", esc(f"run {run['run_id']}"), href=url("runs", run["run_id"])),
                tag("span", esc(f" child job {job['job_id']}"), class_="mono"),
            ),
        ),
        tag(
            "p",
            join(
                badge(job["execution_state"], "info"),
                " ",
                badge(job["review_state"], "neutral"),
                evaluation_note,
            ),
        ),
        image_warning,
        view_controls(base, view, artifact),
        artifact_controls(base, view, artifacts, artifact),
        panes,
        _invocation_card(job),
        _validation_card(validation),
        reasoning_card,
        tag(
            "div",
            join(
                tag("h2", "Exact model response"),
                tag(
                    "p",
                    esc(
                        "The bytes the model returned, preserved before anything read them. This "
                        "is authoritative when it and the parsed view could disagree."
                    ),
                    class_="hint",
                ),
                tag("pre", esc(raw_response), class_="source"),
            ),
            class_="card",
        ),
        tag("div", join(tag("h2", "Review"), review_form), class_="card"),
        tag("div", join(tag("h2", "Comments"), comment_list, comment_form), class_="card"),
    )
