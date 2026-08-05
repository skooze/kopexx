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

from typing import Any, Final

from .html import badge, each, esc, join, tag, url, warning
from .multipart_view import assembled_pane

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
    responses_live_on_tasks: bool = False,
) -> str:
    """The model's structure in the model's own words, or an honest account of why there is none.

    THE TWO ABSENCES ARE DIFFERENT AND WERE BEING REPORTED AS ONE. `parsed is None` was rendered as
    "the response is not one readable YAML 1.2 document" in both cases, and on a multipart parse
    that sentence was simply false: there is no job-level response to be unreadable, because every
    response belongs to a task. The reviewer was then told "the exact bytes are shown below" and
    shown an empty block, since `response-visible.txt` does not exist at job level either. Two
    wrong statements about a run that was working exactly as designed.

    `responses_live_on_tasks` is the handler's answer to "did this parse put its responses
    somewhere else", and only the handler can know it.
    """
    if parsed is None and responses_live_on_tasks:
        return tag(
            "section",
            join(
                tag("h2", "Parsed"),
                warning(
                    "This is a multipart parse and it has no single response. Every response "
                    "belongs to a call, and the assembled index is built from them - so there is "
                    "nothing at this level to show, and that is the design rather than a failure."
                ),
                tag(
                    "ul",
                    join(
                        tag("li", tag("a", "Read the calls", href=url(*base, "multipart"))),
                        tag(
                            "li", tag("a", "Read the assembled index", href=url(*base, "assembled"))
                        ),
                    ),
                    class_="menu",
                ),
            ),
        )
    if parsed is None:
        return tag(
            "section",
            join(
                tag("h2", "Parsed"),
                warning(
                    "Structured parse unavailable: the response is not one readable YAML 1.2 "
                    "document. The exact bytes the model returned are shown below and the run is "
                    "kept - it was billable and cannot be regenerated for free."
                    if raw_response
                    else "Structured parse unavailable, and no response is stored against this "
                    "job at all - so there are no bytes to show. An empty block here used to "
                    "claim the opposite."
                ),
                tag("h3", "Exact model response"),
                tag("pre", esc(raw_response), class_="source") if raw_response else "",
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


#: The adapters that reach a real provider and bill for it. Anything else answered locally, and a
#: page that reports its label, its region and its dollar cost as though it had not is lying.
_BILLABLE_PROVIDERS: Final[frozenset[str]] = frozenset({"bedrock"})


def _provider_warning(attempt_providers: list[str]) -> str:
    """Say plainly when no real provider answered, before any figure that implies one did.

    THE CARD USED TO CLAIM A CALL THAT NEVER HAPPENED. With `LLM_PROVIDER=mock` the review page
    printed `Claude Haiku 4.5 - us.anthropic.claude-haiku-4-5-20251001-v1:0 - region us-east-1` and
    `USD 0.0905289` for a response the mock adapter produced offline in four lines of stub YAML.
    Every one of those values is real CONFIGURATION and none of them is a real INVOCATION, which is
    the distinction `model_routing` cannot make on its own — it records what was selected, not what
    answered. rules.md section 10 requires the invocation to record what it invoked; this is the
    reader's half of that.

    THE FIGURES ARE STILL SHOWN, NOT SUPPRESSED. A mock run's token counts and its journal entry
    are real facts about this instance — the spend journal counted them, which is why a ceiling can
    read as consumed by runs that never reached a provider. Hiding them would replace a false claim
    with a missing one. The warning goes ABOVE them so the qualifier is read first.

    AN ATTEMPT WITH NO RECORDED PROVIDER IS NOT ACCUSED OF BEING A MOCK. Runs stored before the
    field existed read back empty, and empty means unknown: it is reported as unknown.

    THE ATTEMPTS COME FROM THE HANDLER AND SPAN THE TASKS, WHICH IS THE WHOLE POINT ON THIS PAGE. A
    multipart job carries `attempts: []` of its own — every attempt belongs to a call — so a warning
    derived from `job["attempts"]` alone would fall silent on exactly the runs that need it, while
    the card above it printed a model, a region and a dollar figure.
    """
    named = {p for p in attempt_providers if p}
    if not named:
        return (
            warning(
                "This run does not record which provider answered it, so nothing on this card "
                "establishes that a real model was invoked. The model, region and cost below are "
                "the configuration this run was created with."
            )
            if attempt_providers
            else ""
        )
    if named & _BILLABLE_PROVIDERS:
        return ""
    listed = ", ".join(sorted(named))
    return warning(
        f"NO REAL MODEL WAS INVOKED. This run was answered by the {listed} provider, offline, and "
        "no request reached AWS. The model, region, token counts and USD figure below describe the "
        "configuration and the local stub, NOT a provider call - and the cost was still written to "
        "the spend journal, so it counts against the ceiling."
    )


def _invocation_card(job: dict[str, Any], attempt_providers: list[str]) -> str:
    routing = job.get("model_routing") or {}
    cross = warning(routing["cross_region_reason"]) if routing.get("cross_region_reason") else ""
    attempts = job.get("attempts") or []
    last = attempts[-1] if attempts else {}
    source_set = job.get("source_set") or {}
    return tag(
        "div",
        join(
            tag("h2", "Invocation"),
            # BEFORE THE LABEL, NOT AFTER THE COST. A reader who has already read "Claude Haiku 4.5
            # - region us-east-1 - USD 0.09" has formed the belief this warning exists to prevent.
            _provider_warning(attempt_providers),
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


def _assembly_validation_card(validation: dict[str, Any]) -> str:
    """A multipart job's validation: what the mechanical assembly checked, and what it found."""
    assembly = validation.get("assembly") or {}
    if not assembly:
        return tag(
            "div",
            join(tag("h2", "Validation"), tag("p", esc(str(validation.get("note") or "")))),
            class_="card",
        )
    expected = assembly.get("parts_expected")
    terminal = assembly.get("parts_with_a_terminal_result")
    findings = assembly.get("findings") or []
    rows = [
        ("parts expected", expected),
        ("parts with a terminal result", terminal),
        ("reconciliation cycles", assembly.get("reconciliation_cycles")),
        ("unresolved items", assembly.get("unresolved_items")),
        ("declared cost USD", assembly.get("declared_cost_usd")),
        ("recomputed cost USD", assembly.get("recomputed_cost_usd")),
    ]
    return tag(
        "div",
        join(
            tag("h2", "Validation"),
            tag(
                "p",
                join(
                    badge(
                        "consistent" if assembly.get("consistent") else "inconsistent",
                        "ok" if assembly.get("consistent") else "warn",
                    ),
                    esc(" " + str(assembly.get("verdict_note") or validation.get("note") or "")),
                ),
            ),
            tag(
                "p",
                esc(
                    "THIS IS AN ASSEMBLY CHECK, NOT A JUDGEMENT OF THE PARSE. It says the parts "
                    "reconcile with the plan and with the spend journal. It says nothing about "
                    "whether any part is correct."
                ),
                class_="hint",
            ),
            tag(
                "ul",
                each(
                    [(label, value) for label, value in rows if value is not None],
                    lambda row: tag("li", esc(f"{row[0]}: {row[1]}")),
                ),
                class_="refs",
            ),
            tag("h3", "Checks run") if assembly.get("checks_run") else "",
            tag(
                "ul",
                each(assembly.get("checks_run") or [], lambda c: tag("li", esc(str(c)))),
                class_="refs",
            )
            if assembly.get("checks_run")
            else "",
            warning(f"{len(findings)} assembly finding(s)") if findings else "",
            tag(
                "ul",
                each(findings, lambda f: tag("li", esc(str(f)))),
                class_="refs",
            )
            if findings
            else "",
        ),
        class_="card",
    )


def _validation_card(validation: dict[str, Any] | None) -> str:
    """The validation record, in whichever of its two shapes this job carries.

    TWO PROTOCOLS PRODUCE TWO DIFFERENT RECORDS AND THIS USED TO ASSUME ONE OF THEM. A
    single-response job validates a document: node count, table count, references resolved,
    a status and a note. A MULTIPART job validates an ASSEMBLY: parts expected against parts with
    a terminal result, duplicate identifiers, orphan subparts, whether the costs reconcile. It has
    no `status` key at all, and reading one raised `KeyError` on the spot.

    THE PAGE NEVER REACHED THAT BRANCH BEFORE, WHICH IS WHY NOBODY SAW IT. The run page sent a
    multipart job to its call hierarchy and only a single-response job here, so the crash sat
    behind a link nothing followed. Pointing every job at its hub — where the reader can choose
    this view — is what surfaced it.

    A FIELD THAT IS NOT IN THIS SHAPE RENDERS AS NOTHING, NEVER AS A ZERO. A zero node count on a
    parse that produced nine parts would be a measurement, and a wrong one.
    """
    if not validation:
        return ""
    if "status" not in validation:
        return _assembly_validation_card(validation)
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
    responses_live_on_tasks: bool = False,
    attempt_providers: list[str] | None = None,
    assembly: dict[str, Any] | None = None,
    stage_texts: dict[str, str] | None = None,
) -> str:
    """The whole review page for one child filing job.

    `attempt_providers` is the adapter that answered EVERY attempt this parse made, the job's own
    and its calls', gathered by the handler. An empty string in the list is an attempt whose
    provider was never recorded, and it is carried rather than dropped: the count of attempts is
    what separates "nothing was invoked" from "something was invoked and nobody wrote down what".
    """
    base = ("runs", run["run_id"], "jobs", job["job_id"])
    filing = job["filing"]
    # DEFAULTS TO THE JOB'S OWN ATTEMPTS so a single-response parse needs no extra argument, and a
    # caller that omits it on a multipart job gets the "nobody recorded it" warning rather than
    # silence — the direction that fails towards saying less than it knows.
    providers = (
        attempt_providers
        if attempt_providers is not None
        else [str(a.get("provider") or "") for a in (job.get("attempts") or [])]
    )
    outcomes_by_node: dict[str, list[dict[str, Any]]] = {}
    for outcome in (validation or {}).get("references", []):
        outcomes_by_node.setdefault(outcome["node_id"], []).append(outcome)

    raw = raw_pane(filename=artifact, text=artifact_text, focus=focus, focus_length=focus_length)
    # A MULTIPART PARSE IS READ FROM ITS ASSEMBLY, WHICH IS WHERE ITS CONTENT IS. `parsed_pane`
    # reads the job's own single response, and a multipart job has none — so this half of the
    # side-by-side was empty for the whole Phase 2.1 protocol, on the screen this module exists
    # for. The single-response path is untouched and still reads `parsed`.
    structured = (
        assembled_pane(base=base, assembly=assembly)
        if assembly
        else parsed_pane(
            base=base,
            view=view,
            parsed=parsed,
            outcomes_by_node=outcomes_by_node,
            raw_response=raw_response,
            responses_live_on_tasks=responses_live_on_tasks,
        )
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

    # A MULTIPART JOB'S OWN REVIEW LIVES ONE LEVEL DOWN, AND THIS PAGE SAYS SO RATHER THAN
    # PRETENDING THE JOB HAS ONE RESPONSE. Everything below still renders — the preserved filing,
    # the invocation card, the review controls — because they are properties of the child job under
    # either protocol. What a multipart job has no single answer for is "the exact model response",
    # and the link is what leads to the dozen that exist.
    multipart_link = (
        tag(
            "p",
            join(
                tag(
                    "a",
                    "this filing was parsed with the model-directed multipart protocol: open the "
                    "call hierarchy",
                    href=url("runs", run["run_id"], "jobs", job["job_id"], "multipart"),
                ),
            ),
        )
        if job.get("strategy") == "multipart"
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
        multipart_link,
        # THE COMPLETENESS BENCHMARK IS SCOPED TO THE FILING, NOT TO THIS RUN, AND THE LINK SAYS SO.
        # The classification behind it is the denominator every parse of this accession is measured
        # against; reading it as a property of one run is exactly the misreading that would make two
        # runs of the same filing measurable against two different denominators.
        tag(
            "p",
            tag(
                "a",
                "completeness benchmark for this filing — the mechanical inventory and its human "
                "classification, shared by every run of this accession",
                href=url("benchmark", filing["cik"], filing["accession"]),
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
        stages_card(job, base, stage_texts or {}),
        _invocation_card(job, providers),
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


#: How an optional stage's status is coloured. A COLOUR IS A CATEGORY, NEVER A SCORE: `FAILED` is
#: red because the stage did not return, not because the answer was poor — nothing here judges a
#: stage's content, which is what the reviewer is for.
_STAGE_KIND: Final[dict[str, str]] = {"READY_FOR_REVIEW": "ok", "FAILED": "bad"}

#: What each optional stage is, in one line, so a reviewer knows what they are looking at before
#: they read it. rules.md section 1: only the parsing model is required and each of these runs ONLY
#: because the user selected it.
_STAGE_NOTE: Final[dict[str, str]] = {
    "summary": "one entry per node of the parse, in the model's own prose. It is level 5 in the "
    "source-of-truth hierarchy and is never evidence for a financial value.",
    "image": "one entry per image filed with this accession, in filed order, including the ones "
    "the model could not read.",
    "analysis": "an answer bound to THIS accession, with a citation for every material claim. It "
    "is level 6 and is navigation, never evidence.",
}


def stages_card(job: dict[str, Any], base: tuple[str, ...], texts: dict[str, str]) -> str:
    """What the optional stages produced, or nothing at all when none was selected.

    A ROLE THE USER LEFT BLANK RENDERS NOTHING, NOT AN EMPTY ROW. A blank selector is a complete,
    valid configuration — rules.md section 1 — and a card reading `summary: not run` would report a
    missing feature where the user made a choice. Absence of the key IS the absence of the stage.

    THE EXACT BYTES ARE SHOWN, NOT A READING OF THEM. Every stage response is preserved before
    anything parses it, and this card renders that text. Nothing here validates a stage's YAML, and
    nothing here decides whether its content is any good: both are the reviewer's, and a card that
    scored a summary would be the backend judging a model's output.
    """
    stages = job.get("stages") or {}
    if not stages:
        return ""

    def one(role: str) -> str:
        info = stages.get(role) or {}
        status = str(info.get("status") or "")
        text = texts.get(role, "")
        return tag(
            "div",
            join(
                tag(
                    "h3",
                    join(
                        esc(role),
                        " ",
                        badge(status, _STAGE_KIND.get(status, "neutral")),
                    ),
                ),
                tag("p", esc(_STAGE_NOTE.get(role, "")), class_="hint"),
                tag(
                    "p",
                    esc(
                        f"{info.get('model_label') or 'unrecorded model'} in "
                        f"{info.get('region') or 'an unrecorded region'} — prompt "
                        f"{info.get('prompt') or 'unrecorded'} — "
                        f"{info.get('output_tokens') or 0} output token(s) — "
                        f"USD {info.get('actual_cost_usd') or '0'}"
                    ),
                    class_="hint",
                ),
                warning(str(info["error"])) if info.get("error") else "",
                tag("pre", esc(text), class_="source") if text else "",
            ),
            class_="node",
        )

    return tag(
        "div",
        join(
            tag("h2", "Optional stages"),
            tag(
                "p",
                esc(
                    "Each of these ran because it was selected. A role left blank runs nothing and "
                    "appears nowhere here — only the parsing model is required."
                ),
                class_="hint",
            ),
            each(sorted(stages), one),
        ),
        class_="card",
    )
