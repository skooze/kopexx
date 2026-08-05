"""The parser-review UI, rendered and read back.

HERMETIC. Every page here is built from a synthetic mapping assembled in this file. Nothing reads a
store, a filing on disk, a credential or a socket, and no page is served: these are the render
functions called directly and their output parsed with `html.parser` from the standard library.

WHAT IS ACTUALLY BEING TESTED. Not that a function returns a string containing a word. The subject
is the small set of properties that make this surface safe and honest, each of which has already
been got wrong somewhere by somebody:

    ESCAPING. Two of the three things this UI displays are untrusted in the strongest sense — the
    preserved bytes of an SEC filing, and whatever a language model returned after reading one. A
    filing is never rendered as markup. Every escaping test below is paired with a MUTATION
    assertion that the escaped form is present, because "the dangerous string is absent" also
    passes when the content was silently dropped, and a renderer that drops content is the other
    defect this page exists to catch.

    REFUSALS THE UI MAKES VISIBLE. A disabled candidate keeps its concrete reason. A Run button
    with nothing to run is disabled rather than hopeful. An unresolved source reference is marked
    and is deliberately NOT a link, because a link renders it as though it were cited.

    NO TAXONOMY. `type` and `title` are strings the model produced. They are displayed verbatim.
    rules.md section 21 rule 2 — a renderer that quietly normalised an unfamiliar label would hide
    exactly the finding the first experiments exist to produce.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

import pytest

from packages.review_web import (
    FILING,
    SCRIPT,
    STYLESHEET,
    destination,
    esc,
    home,
    job_page,
    layout,
    panel_shell,
    parsed_pane,
    preflight_page,
    raw_pane,
    run_page,
    search_panel,
)
from packages.review_web.html import attributes, badge, tag, void, warning
from packages.review_web.job_view import _RESOLUTION_KIND
from packages.review_web.views import _REVIEW_KIND, _STATE_KIND

#: The string that must never survive a render as markup, in every escaping test below.
HOSTILE = "<script>alert(1)</script>"
HOSTILE_ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "link", "meta", "source", "track"}


# --- reading the rendered page back --------------------------------------------------------


class _Ancestry(HTMLParser):
    """Records the chain of open elements above every element carrying one class."""

    def __init__(self, wanted: str) -> None:
        super().__init__(convert_charrefs=True)
        self._wanted = wanted
        self._stack: list[str] = []
        self.chains: list[tuple[str, ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._wanted in (dict(attrs).get("class") or "").split():
            self.chains.append(tuple(self._stack))
        if tag not in _VOID:
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass


class _Collector(HTMLParser):
    """Every element of one name, as (attributes, the text it encloses)."""

    def __init__(self, wanted: str) -> None:
        super().__init__(convert_charrefs=True)
        self._wanted = wanted
        self._depth = 0
        self._attrs: dict[str, str | None] = {}
        self._text: list[str] = []
        self.found: list[tuple[dict[str, str | None], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == self._wanted:
            if self._depth == 0:
                self._attrs = dict(attrs)
                self._text = []
            self._depth += 1

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._wanted and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self.found.append((self._attrs, "".join(self._text)))


class _OptionReader(HTMLParser):
    """Every option of the one select whose attributes match, in document order."""

    def __init__(self, match: dict[str, str]) -> None:
        super().__init__(convert_charrefs=True)
        self._match = match
        self._inside = False
        self._current: dict[str, str | None] | None = None
        self._text: list[str] = []
        self.options: list[tuple[dict[str, str | None], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = dict(attrs)
        if tag == "select":
            self._inside = all(mapping.get(k) == v for k, v in self._match.items())
        elif tag == "option" and self._inside:
            self._current = mapping
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._current is not None:
            self.options.append((self._current, "".join(self._text)))
            self._current = None
        elif tag == "select":
            self._inside = False


def _ancestors(markup: str, class_name: str) -> list[tuple[str, ...]]:
    parser = _Ancestry(class_name)
    parser.feed(markup)
    return parser.chains


def _elements(markup: str, name: str) -> list[tuple[dict[str, str | None], str]]:
    parser = _Collector(name)
    parser.feed(markup)
    return parser.found


def _element(markup: str, name: str, text: str) -> dict[str, str | None]:
    """The attributes of the one element of `name` whose text is exactly `text`."""
    found = [attrs for attrs, body in _elements(markup, name) if body.strip() == text]
    assert len(found) == 1, f"expected exactly one <{name}> reading {text!r}, got {len(found)}"
    return found[0]


def _by_id(markup: str, name: str, element_id: str) -> dict[str, str | None]:
    """The attributes of the one element of `name` carrying an id."""
    found = [attrs for attrs, _ in _elements(markup, name) if attrs.get("id") == element_id]
    assert len(found) == 1, f"expected exactly one <{name} id={element_id}>, got {len(found)}"
    return found[0]


def _options(markup: str, **match: str) -> list[tuple[dict[str, str | None], str]]:
    parser = _OptionReader(match)
    parser.feed(markup)
    return parser.options


def _list_item(markup: str, containing: str) -> str:
    """The raw source of the one list item holding a substring, brackets and all.

    Raw rather than parsed on purpose: the assertion that matters about an unresolved reference is
    that no anchor was emitted, and a parsed tree that dropped the anchor would look identical to
    one that never had it.
    """
    items = [chunk.split("</li>")[0] for chunk in markup.split("<li>")[1:]]
    matching = [item for item in items if containing in item]
    assert len(matching) == 1, f"expected one <li> containing {containing!r}, got {len(matching)}"
    return matching[0]


# --- synthetic mappings, none of them real -------------------------------------------------


def _entry(**overrides: Any) -> dict[str, Any]:
    """One selector row, shaped exactly as `SelectorEntry.to_mapping` shapes it."""
    entry: dict[str, Any] = {
        "label": "Model One",
        "provider": "Provider",
        "version": "v1",
        "region": "region-one",
        "in_preferred_region": True,
        "inference_profile_id": None,
        "uses_inference_profile": False,
        "text_input": True,
        "image_input": False,
        "multimodal": False,
        "badge": "Text only",
        "context_tokens": 128000,
        "max_output_tokens": 4096,
        "available": True,
        "disabled_reason": None,
        "price_input_per_1k": "0.001",
        "price_output_per_1k": "0.004",
        "currency": "USD",
    }
    entry.update(overrides)
    return entry


def _selectors(entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = entries if entries is not None else [_entry()]

    def role(name: str) -> dict[str, Any]:
        required = name == "parsing"
        return {
            "required": required,
            "blank_option": (
                None if required else {"label": "", "display": "None — skip this stage"}
            ),
            "executed_in_this_phase": required,
            "entries": [dict(row) for row in rows],
        }

    return {
        "preferred_region": "region-one",
        "roles": {name: role(name) for name in ("parsing", "image", "summary", "analysis")},
    }


def _entity(**overrides: Any) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "cik": "0000320193",
        "filing_count": 3,
        "earliest_filing_date": "1994-01-26",
        "latest_filing_date": "2025-10-31",
        "forms_present": ["10-K", "10-Q"],
    }
    entity.update(overrides)
    return entity


def _job(**overrides: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "job_id": "job-1",
        "parent_run_id": "run-1",
        "filing": {
            "cik": "0000320193",
            "accession": "0000320193-25-000079",
            "form_as_filed": "10-K",
            "filing_date": "2025-10-31",
            "issuer_label": "An Issuer",
            "transport_era": "inline_xbrl",
        },
        "model_routing": {
            "label": "Model One",
            "invocation_id": "provider.model-one",
            "region": "region-one",
            "multimodal": False,
            "inference_profile_id": None,
            "cross_region_reason": None,
        },
        "prompt": {"prompt_id": "parse", "version": "1", "sha256": "0" * 64},
        "settings": {"max_output_tokens": 4096, "temperature": "0"},
        "execution_state": "READY_FOR_REVIEW",
        "review_state": "EVALUATION",
        "source_set_id": "aaaabbbbccccdddd0000",
        "source_set": {"reused_members": 2, "fetched_members": 1},
        "image_coverage": None,
        "attempts": [
            {
                "input_tokens": 120000,
                "output_tokens": 8000,
                "stop_reason": "end_turn",
                "latency_ms": 42000,
                "reasoning_characters": 0,
            }
        ],
        "reserved_cost_usd": "0.20",
        "actual_cost_usd": "0.11",
    }
    job.update(overrides)
    return job


def _parsed(**overrides: Any) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "nodes": [
            {
                "id": "n1",
                "type": "a-shape-nobody-anticipated",
                "title": "Explanatory Note Regarding Restatement (unaudited)",
                "content": "The registrant restated prior period amounts.",
                "tables": [],
                "image": False,
            }
        ],
        "unresolved": [],
    }
    parsed.update(overrides)
    return parsed


def _outcome(**overrides: Any) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        "node_id": "n1",
        "filename": "issuer-20250927.htm",
        "quote": "Total net sales",
        "resolution": "EXACT",
        "occurrences": 1,
        "offset": 4096,
    }
    outcome.update(overrides)
    return outcome


def _validation(**overrides: Any) -> dict[str, Any]:
    validation: dict[str, Any] = {
        "status": "PARTIAL",
        "status_note": "coverage signals only",
        "findings": [],
        "node_count": 1,
        "table_count": 0,
        "reference_count": 1,
        "references_resolved": 1,
        "references_ambiguous": 0,
        "references_unresolved": 0,
        "artifacts_referenced": 1,
        "artifacts_submitted": 1,
        "source_to_response_ratio": 12.5,
        "numeric": {
            "numbers_verbatim_in_source": 3,
            "numbers_checked": 4,
            "tables_with_a_coherent_column": 0,
            "tables_checked": 0,
        },
        "model_selected_types": {"a-shape-nobody-anticipated": 1},
        "references": [],
    }
    validation.update(overrides)
    return validation


def _render_job_page(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "run": {"run_id": "run-1"},
        "job": _job(),
        "view": "side-by-side",
        "artifacts": ["issuer-20250927.htm"],
        "artifact": "issuer-20250927.htm",
        "artifact_text": "Total net sales were 391,035.",
        "focus": None,
        "focus_length": 1,
        "parsed": _parsed(),
        "raw_response": "artifact:\n  nodes: []\n",
        "reasoning": "",
        "validation": None,
        "comments": [],
        "csrf": "a-csrf-token",
        "permitted_reviews": ["APPROVED", "REJECTED"],
    }
    kwargs.update(overrides)
    return job_page(**kwargs)


def _plan(**overrides: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "filings": [
            {
                "filing": {
                    "form_as_filed": "10-K",
                    "accession": "0000320193-25-000079",
                    "transport_era": "inline_xbrl",
                },
                "submitted_members": 3,
                "submitted_bytes": 4_000_000,
                "reused_members": 2,
                "fetched_members": 1,
                "compatibility": {"estimated_input_tokens": 900_000},
                "requested_output_tokens": 8000,
                "worst_case_cost_usd": "1.20",
                "compatible": False,
                "reason": "exceeds the context limit",
                "detail": "The complete source set does not fit in one invocation.",
            }
        ],
        "routing": {
            "parsing": {
                "label": "Model One",
                "role": "parsing",
                "region": "region-one",
                "preferred_region": "region-one",
                "multimodal": False,
                "invocation_id": "provider.model-one",
                "cross_region_reason": None,
                "inference_profile_id": None,
            }
        },
        "prompt": {"prompt_id": "parse", "version": "1", "sha256": "0" * 64},
        "worst_case_total_usd": "1.20",
        "already_spent_usd": "0.00",
        "ceiling_usd": "5.00",
        "cost_note": "Every figure here is a bound, not a measurement.",
        "within_ceiling": True,
        "compatible_filings": 0,
    }
    plan.update(overrides)
    return plan


# --- html.py: escaping is the headline ------------------------------------------------------


def test_escaping_covers_angle_brackets_ampersands_and_both_quote_characters() -> None:
    """Attribute quoting is single OR double in the wild, so escaping only one is escaping none.

    `attributes` wraps every value in double quotes, which makes `"` the break-out character here;
    `'` is escaped anyway so a value can never break out of markup this module did not build.
    """
    assert esc("<") == "&lt;"
    assert esc(">") == "&gt;"
    assert esc("&") == "&amp;"
    assert esc('"') == "&quot;"
    assert esc("'") == "&#x27;"


def test_escaping_preserves_the_content_it_escapes() -> None:
    """Anti-vacuity. Every "the dangerous string is absent" assertion below also passes on ""."""
    assert esc(HOSTILE) == HOSTILE_ESCAPED
    assert "alert(1)" in esc(HOSTILE)
    assert esc("plain text") == "plain text"


def test_an_attribute_value_cannot_close_its_own_quote() -> None:
    rendered = attributes(title='He said "go" & left')
    assert rendered == ' title="He said &quot;go&quot; &amp; left"'
    assert '"go"' not in rendered


def test_attributes_drop_only_none_and_false_and_keep_the_empty_string() -> None:
    """`value=""` is a real attribute — a blank option needs one — and `False` is an absent flag."""
    assert attributes(disabled=False, hidden=None) == ""
    assert attributes(disabled=True) == " disabled"
    assert attributes(value="") == ' value=""'


def test_a_badge_and_a_warning_escape_their_own_text() -> None:
    """Both take a caller-supplied string, and one of the callers passes a model-chosen label."""
    assert HOSTILE not in badge(HOSTILE)
    assert HOSTILE_ESCAPED in badge(HOSTILE)
    assert HOSTILE not in warning(HOSTILE)
    assert HOSTILE_ESCAPED in warning(HOSTILE)


def test_tag_takes_its_element_name_positionally_so_a_name_attribute_still_works() -> None:
    """A form needs `name="cik"`, and a keyword `element` would have collided with it."""
    assert tag("input", "", name="cik") == '<input name="cik"></input>'


def test_a_void_element_is_written_without_a_closing_tag_and_still_escapes() -> None:
    """`void` is the only way to emit an element that must not be closed, and it escapes too."""
    assert void("meta", charset="utf-8") == '<meta charset="utf-8">'
    assert void("link", href='a"b') == '<link href="a&quot;b">'


# --- job_view.py: a filing is never rendered as markup --------------------------------------


def test_a_filing_containing_a_script_tag_is_rendered_as_escaped_text() -> None:
    """SECURITY-INVARIANT: no preserved byte ever reaches a markup parser as markup.

    This is why the content security policy can stay strict and why there is no sanitizer to get
    wrong: the browser is never asked to decide whether filing content is safe.
    """
    rendered = raw_pane(filename="f.htm", text=HOSTILE, focus=None, focus_length=1)
    assert "<script>" not in rendered
    assert HOSTILE_ESCAPED in rendered, "the hostile content was dropped rather than escaped"


def test_a_filing_stays_escaped_across_the_highlighted_range() -> None:
    """The focus split cuts the source into three pieces; each one is escaped separately.

    A boundary that landed inside a tag would be the natural place for one piece to escape the
    escaping, so the cut is placed inside `<script>` deliberately.
    """
    text = "before " + HOSTILE + " after"
    rendered = raw_pane(filename="f.htm", text=text, focus=9, focus_length=4)
    assert "<script>" not in rendered
    assert "&lt;" in rendered and "alert(1)" in rendered
    assert '<mark id="focus">' in rendered


def test_a_model_response_containing_markup_is_rendered_as_escaped_text() -> None:
    """rules.md section 11: model output is DATA. It is rendered, never evaluated."""
    rendered = parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="parsed",
        parsed=None,
        outcomes_by_node={},
        raw_response=HOSTILE,
    )
    assert "<script>" not in rendered
    assert HOSTILE_ESCAPED in rendered


def test_a_model_chosen_node_title_is_escaped() -> None:
    """`title` is a string the model produced. It is displayed, and it is not trusted."""
    parsed = _parsed(nodes=[{"id": "n1", "type": "note", "title": HOSTILE, "content": ""}])
    rendered = parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="parsed",
        parsed=parsed,
        outcomes_by_node={},
        raw_response="",
    )
    assert "<script>" not in rendered
    assert HOSTILE_ESCAPED in rendered


def test_a_comment_body_is_escaped() -> None:
    """A reviewer's own text is the third untrusted source, and it is stored and replayed."""
    rendered = _render_job_page(
        comments=[
            {
                "created_at": "2026-08-03T12:00:00Z",
                "author": "a reviewer",
                "target_type": "parsed_node",
                "target_id": "n1",
                "text": '<img src=x onerror="alert(1)">',
            }
        ]
    )
    assert "<img" not in rendered
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in rendered


def test_a_raw_pane_with_no_preserved_text_says_so_rather_than_rendering_empty() -> None:
    rendered = raw_pane(filename="f.htm", text="", focus=None, focus_length=1)
    assert "No preserved text is held for this artifact." in rendered


def test_a_display_window_states_that_it_is_one() -> None:
    """A silently truncated view of a source of truth is the same defect as a truncated request."""
    rendered = raw_pane(filename="f.htm", text="x" * 300_000, focus=None, focus_length=1)
    assert "this is a display window" in rendered
    assert "of 300,000" in rendered


def test_a_whole_short_artifact_carries_no_window_note() -> None:
    """Anti-vacuity for the note above: it must not appear on a document shown in full."""
    rendered = raw_pane(filename="f.htm", text="x" * 100, focus=None, focus_length=1)
    assert "display window" not in rendered


# --- views.layout: the run identifier is anchored to the viewport ---------------------------


def _layout(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "title": "a page",
        "panel": "<p>the panel</p>",
        "main": "<p>the workspace</p>",
        "run_id": "run-1",
        "collapsed": False,
        "https": True,
        # A TRAIL IS REQUIRED AND HAS NO DEFAULT. `layout` refuses to render without one, so a
        # handler that forgets it fails the type check rather than shipping a blank strip.
        "crumbs": (),
    }
    kwargs.update(overrides)
    return layout(**kwargs)


def test_the_run_identifier_bar_is_rendered_outside_the_panel() -> None:
    """It is anchored to the VIEWPORT, not to the panel, and the markup has to agree.

    Nesting it in the panel would make the stylesheet's `position: fixed` a lie the moment the
    panel is collapsed, and the run identifier is what a person quotes in a bug report.
    """
    chains = _ancestors(_layout(), "run-id")
    assert len(chains) == 1, "the run identifier bar is rendered exactly once"
    assert "aside" not in chains[0], f"the bar is nested in the panel: {chains[0]}"
    assert chains[0][-1] == "body"


def test_the_run_identifier_bar_survives_a_collapsed_panel() -> None:
    rendered = _layout(collapsed=True)
    # The collapsed MODE is stated on `body` rather than on the panel, so one class change can
    # swap the panel and its reopen control together. See the toggle test below for why.
    assert 'class="panel-collapsed"' in rendered
    chains = _ancestors(rendered, "run-id")
    assert len(chains) == 1
    assert "aside" not in chains[0]


def test_the_reopen_control_is_rendered_in_both_modes() -> None:
    """This is what makes collapsing free, and it is the whole reason the mode moved to `body`.

    Rendering the reopen control only when the panel was ALREADY collapsed meant it had to be
    FETCHED, so collapsing cost a full page load. With it always present the toggle is a class
    change and nothing is requested. If a later change starts omitting it again, the reload comes
    back silently — the page would still work, it would just be slow in a way nothing would catch.
    """
    for collapsed in (True, False):
        rendered = _layout(collapsed=collapsed)
        assert 'data-panel="open"' in rendered, f"reopen control missing (collapsed={collapsed})"
        # It remains a real link, so the panel still reopens with scripting disabled.
        assert 'href="?panel=open"' in rendered


def test_the_run_identifier_carries_a_copy_control_with_an_accessible_label() -> None:
    """Status and affordance are never carried by a glyph alone; the control names its subject."""
    attrs = _element(_layout(), "button", "copy")
    assert attrs["data-copy"] == "run-1"
    assert attrs["aria-label"] == "copy run identifier run-1"


def test_a_page_with_no_parent_run_renders_no_identifier_bar() -> None:
    """Anti-vacuity. The bar must be absent when there is nothing to name, not blank."""
    assert _ancestors(_layout(run_id=None), "run-id") == []
    assert "run-id" not in _layout(run_id=None)


def test_plain_http_is_labelled_as_local_development_mode() -> None:
    assert "LOCAL DEVELOPMENT MODE" in _layout(https=False)
    assert "LOCAL DEVELOPMENT MODE" not in _layout(https=True)


# --- views.search_panel: four selectors, and the refusals they make visible ------------------


def _panel(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {"selectors": _selectors(), "csrf": "a-csrf-token"}
    kwargs.update(overrides)
    return search_panel(**kwargs)


def test_the_collapse_control_is_a_real_link_and_a_toggle_target() -> None:
    """Both at once, deliberately: `data-panel` is the enhancement, `href` is the fallback.

    THE CONTROL MOVED FROM `search_panel` TO `panel_shell`, which is why this reads from the shell
    now. It belongs to the panel rather than to the search form: both panel modes need it, and a
    review menu with no way to collapse is a corner a reader gets stuck in.

    THE HREF IS SUPPLIED RATHER THAN LITERAL. It used to be the bare `?panel=closed`, which
    discarded the entity and model selections the panel had just been rebuilt from — collapsing
    the panel silently reset the form. The caller builds it with `with_query`.
    """
    rendered = panel_shell(
        active="home",
        collapse_href="/runs?cik=0000320193&panel=closed",
        mode="search",
        search_href="/runs?panel_mode=search",
        review_href="/runs?panel_mode=review",
        review_reason="no parse or filing is open on this page",
        body="<p>the panel</p>",
    )
    assert 'data-panel="closed"' in rendered
    assert 'href="/runs?cik=0000320193&amp;panel=closed"' in rendered
    # The selections survive the click, which is the point of supplying the href.
    assert "cik=0000320193" in rendered


def test_all_four_model_selectors_render() -> None:
    """Four models, chosen independently. A role with no selector is a role nobody can choose."""
    rendered = _panel()
    ids = {attrs.get("id") for attrs, _ in _elements(rendered, "select")}
    assert {"sel-parsing", "sel-image", "sel-summary", "sel-analysis"} <= ids


def test_the_three_optional_roles_offer_a_named_blank_option() -> None:
    """Skipping a stage is a VISIBLE choice with a label, never a hidden default."""
    rendered = _panel()
    for role in ("image", "summary", "analysis"):
        blanks = [
            text for attrs, text in _options(rendered, id=f"sel-{role}") if attrs["value"] == ""
        ]
        assert blanks == ["None — skip this stage"], f"{role} has no named blank option"


def test_the_parsing_selector_offers_no_blank_option() -> None:
    """ONLY THE PARSING MODEL IS REQUIRED, and a required role has nothing blank to select."""
    blanks = [text for attrs, text in _options(_panel(), id="sel-parsing") if attrs["value"] == ""]
    assert blanks == []


def test_an_unavailable_candidate_is_disabled_and_keeps_its_concrete_reason() -> None:
    """A greyed row with no explanation sends a user to a support channel.

    `packages/model_catalog` returns disabled candidates rather than filtering them away precisely
    so the reason has somewhere to go; this is the somewhere.
    """
    reason = "Model Two is not enabled in region-one."
    rendered = _panel(
        selectors=_selectors(
            [_entry(), _entry(label="Model Two", available=False, disabled_reason=reason)]
        )
    )
    rows = dict(
        (attrs["value"], (attrs, text)) for attrs, text in _options(rendered, id="sel-parsing")
    )
    disabled_attrs, disabled_text = rows["Model Two"]
    assert "disabled" in disabled_attrs
    assert f"UNAVAILABLE: {reason}" in disabled_text


def test_an_available_candidate_is_neither_disabled_nor_labelled_unavailable() -> None:
    """Anti-vacuity for the test above: the guard must distinguish the two states."""
    rendered = _panel(selectors=_selectors([_entry()]))
    attrs, text = _options(rendered, id="sel-parsing")[0]
    assert "disabled" not in attrs
    assert "UNAVAILABLE" not in text


def test_a_selector_row_carries_every_field_the_specification_puts_on_it() -> None:
    """A price with no currency and a limit with no number are what a guessed row looks like."""
    _, text = _options(_panel(), id="sel-parsing")[0]
    for fragment in ("Model One", "Provider", "Text only", "region-one", "128,000", "4,096"):
        assert fragment in text
    assert "in USD 0.001/1k in, 0.004/1k out" in text


def test_a_profile_only_candidate_says_so_on_its_row() -> None:
    """Invoking through a profile may route across regions, and the row is where that is stated."""
    entry = _entry(uses_inference_profile=True, inference_profile_id="geo.provider.model-one")
    _, text = _options(_panel(selectors=_selectors([entry])), id="sel-parsing")[0]
    assert "via inference profile" in text


def test_a_directly_invocable_candidate_claims_no_profile() -> None:
    """Anti-vacuity: the note is conditional on the reviewed snapshot, not decoration."""
    _, text = _options(_panel(), id="sel-parsing")[0]
    assert "inference profile" not in text


def test_the_developer_mode_filing_selector_offers_the_timeframe_and_each_filing() -> None:
    """Every filing is its own billable unit, so choosing exactly one has to be possible."""
    rendered = _panel(
        entity=_entity(),
        filings=[
            {
                "form_as_filed": "10-K",
                "filing_date": "2025-10-31",
                "accession": "0000320193-25-000079",
                "primary_estimated_tokens": 900_000,
            }
        ],
    )
    offered = _options(rendered, id="accession")
    assert offered[0][0]["value"] == ""
    assert offered[0][1] == "every filing in the timeframe"
    assert offered[1][0]["value"] == "0000320193-25-000079"
    assert "~900,000 est tokens" in offered[1][1]


def _shell(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "active": "home",
        "collapse_href": "/?panel=closed",
        "mode": "search",
        "search_href": "/?panel_mode=search",
        "review_href": "/?panel_mode=review",
        "review_reason": "no parse or filing is open on this page",
        "body": "<p>the panel</p>",
    }
    kwargs.update(overrides)
    return panel_shell(**kwargs)


def test_cumulative_spend_is_shown_against_the_authorized_ceiling() -> None:
    """rules.md section 21 rule 11: spend is previewed and authorized, never reconciled after.

    READ FROM THE SHELL, NOT FROM THE SEARCH FORM. The figure moved to `panel_shell` with the
    collapse control, so it shows in BOTH panel modes: it used to vanish the moment a reader opened
    a parse, which is the one page where every queue control spends against this same ceiling.
    """
    rendered = _shell(spend={"spent_usd": "1.23", "ceiling_usd": "5.00"})
    assert "Cumulative authorized spend: USD 1.23 of 5.00." in rendered


def test_the_panel_shows_no_spend_line_when_the_figure_was_not_supplied() -> None:
    """ABSENT RATHER THAN ZERO. `USD 0.00 of 0.00` would be a measurement, and a wrong one."""
    assert "Cumulative authorized spend" not in _shell()


def test_the_search_form_no_longer_renders_the_spend_line() -> None:
    """MUTATION PROOF: the figure lives in exactly one place, so it cannot be shown twice.

    `search_panel` does not accept `spend` at all — a parameter accepted and ignored is worse than
    one that is absent, because a caller passing it has no way to see nothing came of it.
    """
    assert "Cumulative authorized spend" not in _panel()
    with pytest.raises(TypeError):
        _panel(spend={"spent_usd": "1.23", "ceiling_usd": "5.00"})


def _run_button(markup: str) -> dict[str, str | None]:
    return _element(markup, "button", "Preflight and run")


def test_the_run_button_is_disabled_with_no_entity_chosen() -> None:
    attrs = _run_button(_panel(chosen={"parsing_label": "Model One"}))
    assert "disabled" in attrs


def test_the_run_button_is_disabled_with_no_parsing_model_chosen() -> None:
    """rules.md section 21: no stage is silently selected on the user's behalf."""
    attrs = _run_button(_panel(entity=_entity()))
    assert "disabled" in attrs


def test_the_run_button_is_disabled_when_the_chosen_parsing_model_is_unavailable() -> None:
    """No silent substitution. An unavailable choice blocks the run rather than routing elsewhere."""
    rendered = _panel(
        selectors=_selectors([_entry(available=False, disabled_reason="access not granted")]),
        entity=_entity(),
        chosen={"parsing_label": "Model One"},
    )
    assert "disabled" in _run_button(rendered)


def test_the_run_button_is_enabled_once_an_entity_and_a_parsing_model_are_chosen() -> None:
    """Anti-vacuity. Without this the three assertions above pass on a permanently dead button."""
    rendered = _panel(entity=_entity(), chosen={"parsing_label": "Model One"})
    assert "disabled" not in _run_button(rendered)
    assert "Select an entity and an available parsing model." not in rendered


def test_a_blocked_run_says_the_optional_selectors_may_stay_blank() -> None:
    """A parser-only run is a complete, valid run, and the panel has to say so."""
    assert "The image, summary and analysis selectors may stay blank." in _panel()


def test_the_image_selector_is_disabled_when_the_parsing_model_is_multimodal() -> None:
    """A multimodal parser handles filed images itself; a second image stage would double-bill."""
    rendered = _panel(
        selectors=_selectors(
            [_entry(), _entry(label="Vision One", multimodal=True, image_input=True)]
        ),
        entity=_entity(),
        chosen={"parsing_label": "Vision One"},
    )
    assert "disabled" in _by_id(rendered, "select", "sel-image")
    assert "disabled" not in _by_id(rendered, "select", "sel-parsing")
    assert "the selected parsing model is multimodal" in rendered
    assert "No separate image model is invoked." in rendered


def test_the_image_selector_stays_enabled_for_a_text_only_parsing_model() -> None:
    """Anti-vacuity: the disable is conditional on the measured modality, not always on."""
    rendered = _panel(entity=_entity(), chosen={"parsing_label": "Model One"})
    assert "disabled" not in _by_id(rendered, "select", "sel-image")
    assert "the selected parsing model is multimodal" not in rendered


def test_the_timeframe_is_bounded_by_the_filings_that_actually_exist() -> None:
    rendered = _panel(entity=_entity())
    dates = [attrs for attrs, _ in _elements(rendered, "input") if attrs.get("type") == "date"]
    assert len(dates) == 2
    assert all(attrs["min"] == "1994-01-26" and attrs["max"] == "2025-10-31" for attrs in dates)
    assert "3 qualifying filing(s) between" in rendered


def test_a_search_match_is_escaped_before_it_is_offered() -> None:
    """An issuer name comes from SEC. It is data here exactly as a filing body is."""
    rendered = _panel(matches=[{"name": HOSTILE, "cik": "0000000001", "tickers": []}])
    assert "<script>" not in rendered
    assert HOSTILE_ESCAPED in rendered


# --- job_view: three views, and what belongs in each ----------------------------------------


def test_the_raw_view_renders_only_the_raw_pane() -> None:
    rendered = _render_job_page(view="raw")
    assert "Raw source — issuer-20250927.htm" in rendered
    assert "<h2>Parsed</h2>" not in rendered


def test_the_parsed_view_renders_only_the_parsed_pane() -> None:
    rendered = _render_job_page(view="parsed")
    assert "<h2>Parsed</h2>" in rendered
    assert "Raw source —" not in rendered


def test_the_side_by_side_view_renders_both_panes_together() -> None:
    """roadmap.md 2b: a parsed artifact cannot be evaluated without the filing it came from."""
    rendered = _render_job_page(view="side-by-side")
    assert "Raw source — issuer-20250927.htm" in rendered
    assert "<h2>Parsed</h2>" in rendered
    assert '<div class="panes">' in rendered


def test_the_exact_response_is_shown_in_every_view() -> None:
    """The parsed view is DERIVED. The bytes are authoritative when the two could disagree."""
    for view in ("raw", "parsed", "side-by-side"):
        rendered = _render_job_page(view=view, raw_response="artifact:\n  nodes: []\n")
        assert "<h2>Exact model response</h2>" in rendered


def test_a_multi_member_source_set_offers_one_control_per_artifact() -> None:
    """A source set is a set. Showing one member and calling it the filing would hide the rest."""
    rendered = _render_job_page(
        view="raw",
        artifacts=["issuer-20250927.htm", "exhibit-21.htm"],
        artifact="exhibit-21.htm",
    )
    links = {text: attrs for attrs, text in _elements(rendered, "a")}
    assert "issuer-20250927.htm" in links and "exhibit-21.htm" in links
    assert links["exhibit-21.htm"]["class"] == "active"
    assert "class" not in links["issuer-20250927.htm"]


def test_a_single_member_source_set_offers_no_artifact_switcher() -> None:
    """Anti-vacuity: a switcher between one thing and itself is noise, not a control."""
    rendered = _render_job_page(view="raw", artifacts=["issuer-20250927.htm"])
    assert "issuer-20250927.htm" not in [text for _, text in _elements(rendered, "a")]


def test_a_table_inside_a_node_renders_its_rows_escaped() -> None:
    """A table is the model's, cell by cell. Its caption and cells are untrusted text like any."""
    parsed = _parsed(
        nodes=[
            {
                "id": "n1",
                "type": "financial-table",
                "title": "a title",
                "content": "",
                "tables": [{"caption": HOSTILE, "rows": [["2025", "391,035"], "a lone cell"]}],
            }
        ]
    )
    rendered = parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="parsed",
        parsed=parsed,
        outcomes_by_node={},
        raw_response="",
    )
    assert "<script>" not in rendered
    assert HOSTILE_ESCAPED in rendered
    assert "<td>2025</td><td>391,035</td>" in rendered
    assert "<td>a lone cell</td>" in rendered, "a row that is not a list is still one cell"


# --- job_view: source-reference navigation --------------------------------------------------


def _reference_pane(*outcomes: dict[str, Any]) -> str:
    nodes = [
        {"id": o["node_id"], "type": "note", "title": f"node {o['node_id']}", "content": ""}
        for o in outcomes
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["node_id"], []).append(outcome)
    return parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="raw",
        parsed={"nodes": nodes, "unresolved": []},
        outcomes_by_node=grouped,
        raw_response="",
    )


def test_a_resolved_reference_is_a_link_carrying_the_byte_offset() -> None:
    """Navigation is a link, not a script: it works with scripting disabled and can be shared."""
    rendered = _reference_pane(_outcome(offset=4096, quote="Total net sales"))
    item = _list_item(rendered, "Total net sales")
    assert "<a " in item
    assert "offset=4096" in item
    assert "length=15" in item, "the highlight length is the quote length"
    assert "artifact=issuer-20250927.htm" in item
    assert "#focus" in item, "the link must land on the marked range, not the top of the document"
    assert item.endswith("</a>")


def test_a_reference_at_offset_zero_is_still_a_link() -> None:
    """Offset 0 is a real location. A falsiness test rather than an `is None` test loses it."""
    item = _list_item(_reference_pane(_outcome(offset=0)), "Total net sales")
    assert "<a " in item
    assert "offset=0" in item


def test_an_unresolved_reference_is_marked_and_is_not_a_link() -> None:
    """A link renders a reference as though it were cited, which is the one thing it is not.

    The assertion is made against the raw markup on purpose: a parsed tree with the anchor missing
    looks the same as one that never had it.
    """
    item = _list_item(
        _reference_pane(
            _outcome(node_id="n2", resolution="UNRESOLVED", offset=None, quote="ghost")
        ),
        "ghost",
    )
    assert "<a " not in item and "</a>" not in item
    assert "UNRESOLVED" in item
    assert "not located in the preserved bytes" in item


def test_a_node_with_no_reference_at_all_says_so() -> None:
    rendered = parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="raw",
        parsed=_parsed(),
        outcomes_by_node={},
        raw_response="",
    )
    assert "No source reference was supplied for this node." in rendered


def test_every_reference_on_one_node_is_rendered_not_just_the_first() -> None:
    """Nothing is merged away. Two citations for one node are two rows."""
    rendered = _reference_pane(
        _outcome(quote="first quote"),
        _outcome(quote="second quote", offset=8192),
    )
    assert "first quote" in rendered and "second quote" in rendered


def test_validation_references_reach_the_parsed_pane_through_the_job_page() -> None:
    """The grouping by node id is the join between the validator and the renderer."""
    rendered = _render_job_page(
        view="parsed",
        validation=_validation(references=[_outcome(quote="Total net sales")]),
    )
    assert "Total net sales" in _list_item(rendered, "Total net sales")


# --- job_view: the warnings the specification requires at the point of use -------------------


def test_unanalysed_image_content_is_warned_about_and_the_count_is_named() -> None:
    """Uncertainty produces a stated gap, never a silent claim of coverage."""
    rendered = _render_job_page(
        job=_job(
            image_coverage={
                "image_member_count": 4,
                "analysed": False,
                "reason": "the selected parsing model is text only.",
            }
        )
    )
    assert "4 image-bearing member(s) were filed and were NOT analysed" in rendered
    assert "This run does not claim image coverage." in rendered
    assert "the selected parsing model is text only." in rendered


def test_analysed_image_content_produces_no_warning() -> None:
    """Anti-vacuity. A warning that always fires is indistinguishable from no warning at all."""
    rendered = _render_job_page(
        job=_job(image_coverage={"image_member_count": 4, "analysed": True, "reason": ""})
    )
    assert "image-bearing member(s)" not in rendered


def test_a_response_that_will_not_parse_shows_the_warning_and_the_exact_bytes() -> None:
    """When a response will not parse there is no parsed view, and the bytes are all there is.

    The run is kept either way: it was billable and cannot be regenerated for free.
    """
    response = '<b>not yaml</b> & "quoted"'
    rendered = _render_job_page(view="parsed", parsed=None, raw_response=response)
    assert "Structured parse unavailable" in rendered
    assert "<b>" not in rendered
    assert "&lt;b&gt;not yaml&lt;/b&gt; &amp; &quot;quoted&quot;" in rendered


def test_a_response_that_parsed_shows_no_unavailable_warning() -> None:
    """Anti-vacuity for the warning above."""
    assert "Structured parse unavailable" not in _render_job_page(view="parsed")


def test_every_validation_finding_renders_as_a_warning() -> None:
    """A finding recorded but not shown protects nobody."""
    findings = ["the response cited no artifact", "one reference did not resolve"]
    rendered = _render_job_page(validation=_validation(findings=findings))
    for finding in findings:
        assert f'<p class="warning" role="status">{finding}</p>' in rendered


def test_model_declared_unresolved_content_is_shown_as_its_own_block() -> None:
    """The model's own statement of what it could not resolve is a required product output."""
    rendered = parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="parsed",
        parsed=_parsed(
            unresolved=[{"what": "an exhibit", "where": "page 88", "why": "it is an image"}]
        ),
        outcomes_by_node={},
        raw_response="",
    )
    assert "Declared unresolved by the model" in rendered
    assert "an exhibit - page 88 - it is an image" in rendered


# --- job_view: no taxonomy ------------------------------------------------------------------


def test_an_unfamiliar_node_type_and_title_are_displayed_verbatim() -> None:
    """rules.md section 21 rule 2: NO UNIVERSAL FILING TAXONOMY.

    A renderer that normalised or dropped an unrecognised label would hide exactly the finding the
    first experiments exist to produce. The strings below are not in any vocabulary anywhere.
    """
    rendered = _render_job_page(view="parsed")
    assert "a-shape-nobody-anticipated" in rendered
    assert "Explanatory Note Regarding Restatement (unaudited)" in rendered
    assert "(no type)" not in rendered
    assert "(no title)" not in rendered


def test_a_node_with_no_type_is_marked_as_having_none_rather_than_guessed() -> None:
    """Anti-vacuity, and a refusal: the renderer states the absence instead of inventing a label."""
    rendered = parsed_pane(
        base="/runs/run-1/jobs/job-1",
        view="parsed",
        parsed={"nodes": [{"id": "n1", "content": "body"}], "unresolved": []},
        outcomes_by_node={},
        raw_response="",
    )
    assert "(no type)" in rendered
    assert "(no title)" in rendered


def test_the_parsed_pane_states_that_no_backend_taxonomy_was_applied() -> None:
    """The apostrophe is escaped in the rendered form; asserting the raw prose would pass on air."""
    rendered = _render_job_page(view="parsed")
    assert "in the filing&#x27;s own vocabulary" in rendered
    assert "No backend taxonomy is applied" in rendered
    assert "an unfamiliar label is displayed rather than dropped" in rendered


# --- job_view: the review form --------------------------------------------------------------


def test_the_review_form_offers_only_the_permitted_transitions() -> None:
    """The permitted set is computed elsewhere; the form must not widen it back out.

    Offering a transition the state machine will refuse turns a governed workflow into a guess.
    """
    rendered = _render_job_page(permitted_reviews=["APPROVED", "REJECTED"])
    offered = [attrs["value"] for attrs, _ in _options(rendered, name="review_state")]
    assert offered == ["APPROVED", "REJECTED"]
    for absent in ("SUPERSEDED", "INVALIDATED", "UNDER_REVIEW"):
        assert absent not in offered


def test_a_different_permitted_set_produces_a_different_form() -> None:
    """Anti-vacuity: the options come from the argument, not from a list inside the renderer."""
    rendered = _render_job_page(permitted_reviews=["UNDER_REVIEW"])
    offered = [attrs["value"] for attrs, _ in _options(rendered, name="review_state")]
    assert offered == ["UNDER_REVIEW"]
    assert "APPROVED" not in offered


def test_an_evaluation_job_says_approval_activates_nothing() -> None:
    rendered = _render_job_page(job=_job(review_state="EVALUATION"))
    assert "Approval records a judgement and activates nothing" in rendered


def test_both_forms_carry_the_csrf_token() -> None:
    """A state transition and a comment are both writes, and neither is exempt."""
    rendered = _render_job_page(csrf="a-csrf-token")
    tokens = [
        attrs for attrs, _ in _elements(rendered, "input") if attrs.get("name") == "csrf_token"
    ]
    assert len(tokens) == 2
    assert all(attrs["value"] == "a-csrf-token" for attrs in tokens)


# --- views: the remaining pages -------------------------------------------------------------


def test_an_entity_label_on_the_home_page_is_escaped() -> None:
    run = {
        "run_id": "run-1",
        "created_at": "2026-08-03T12:00:00Z",
        "entity_label": HOSTILE,
        "parsing_label": "Model One",
        "job_count": 1,
        "ready_for_review": 0,
        "actual_cost_usd": "0.11",
    }
    rendered = home(runs=[run], catalog={"entity_count": 112, "filing_count": 613})
    assert "<script>" not in rendered
    assert HOSTILE_ESCAPED in rendered


def test_the_home_page_says_so_when_no_run_is_stored() -> None:
    """An empty table and an empty state are different statements."""
    rendered = home(runs=[], catalog={"entity_count": 0, "filing_count": 0})
    assert "No evaluation runs are stored yet." in rendered


def test_a_preflight_with_nothing_compatible_refuses_instead_of_offering_a_run() -> None:
    """INTACT_SOURCE_ONLY. Nothing is shrunk, dropped or downgraded to fit, so there is no button."""
    rendered = preflight_page(plan=_plan(), csrf="a-csrf-token", form={"cik": "0000320193"})
    assert "This run cannot start" in rendered
    assert "Nothing is shrunk, dropped or downgraded to fit." in rendered
    assert not [text for _, text in _elements(rendered, "button") if text == "Run now"]


def test_a_preflight_with_a_compatible_filing_offers_the_run() -> None:
    """Anti-vacuity for the refusal above, and the carried form must survive the round trip."""
    plan = _plan(compatible_filings=1)
    plan["filings"][0]["compatible"] = True
    rendered = preflight_page(plan=plan, csrf="a-csrf-token", form={"cik": "0000320193"})
    assert _element(rendered, "button", "Run now")["type"] == "submit"
    carried = [attrs for attrs, _ in _elements(rendered, "input") if attrs.get("name") == "cik"]
    assert carried and carried[0]["value"] == "0000320193"


def test_a_run_page_states_that_blank_selectors_ran_no_stage() -> None:
    """ONLY THE PARSING MODEL IS REQUIRED, and a blank role borrowed nobody else's model."""
    run = {
        "run_id": "run-1",
        "entity_label": "An Issuer",
        "cik": "0000320193",
        "selections": {"parsing": "Model One"},
        "selected_roles": ["parsing"],
    }
    job = {
        "job_id": "job-1",
        "filing": {"form_as_filed": "10-K", "accession": "0000320193-25-000079"},
        "execution_state": "READY_FOR_REVIEW",
        "review_state": "EVALUATION",
        "validation_status": "PARTIAL",
        "actual_cost_usd": "0.11",
    }
    rendered = run_page(run=run, jobs=[job], events=[])
    assert "ran NO stage" in rendered
    assert "the parsing model was not borrowed" in rendered
    assert "0000320193-25-000079" in rendered


# --- assets ---------------------------------------------------------------------------------


def test_the_stylesheet_and_the_script_are_non_empty_strings() -> None:
    """They are module constants, not files: an empty one would ship silently."""
    assert isinstance(STYLESHEET, str) and isinstance(SCRIPT, str)
    assert len(STYLESHEET.strip()) > 500
    assert len(SCRIPT.strip()) > 200


def test_the_script_evaluates_nothing_and_assigns_no_markup() -> None:
    """The one script copies an identifier. It has no path from a filing to a markup parser.

    `innerHTML` would reintroduce the sanitizer problem the server-rendered escaping removes, and
    `eval` would reintroduce it with the strict content security policy still switched on.
    """
    lowered = SCRIPT.lower()
    for forbidden in ("eval(", "innerhtml", "outerhtml", "document.write", "new function("):
        assert forbidden not in lowered, f"the script uses {forbidden}"


def test_the_script_is_the_copy_control_and_nothing_else() -> None:
    """Anti-vacuity: the scan above has something real to scan, and it is the shipped script."""
    assert "data-copy" in SCRIPT
    assert "clipboard" in SCRIPT
    assert "fetch(" not in SCRIPT and "XMLHttpRequest" not in SCRIPT


def test_every_badge_kind_the_views_emit_has_a_rule_in_the_stylesheet() -> None:
    """Status is never carried by colour alone, but an unstyled badge is still a broken one.

    `neutral` is the base `.badge` rule by design and has no modifier of its own.
    """
    kinds = set(_STATE_KIND.values()) | set(_REVIEW_KIND.values()) | set(_RESOLUTION_KIND.values())
    assert kinds, "there are no badge kinds to check"
    for kind in kinds - {"neutral"}:
        assert f".badge-{kind}" in STYLESHEET, f"badge kind {kind} has no rule"
    assert ".badge {" in STYLESHEET
    assert ".warning {" in STYLESHEET


def test_the_stylesheet_anchors_the_run_identifier_to_the_viewport() -> None:
    """The markup test above only proves the bar is outside the panel; this is the other half."""
    block = STYLESHEET.split(".run-id {", 1)[1].split("}", 1)[0]
    assert "position: fixed" in block


# --- the menu is navigation, not a printed URL list ---------------------------------------------


def test_a_destination_does_not_print_its_own_href() -> None:
    """MEASURED, NOT STYLISTIC. The panel is 320px and the URLs were 67% of its text.

    18 printed hrefs averaging 75 characters sat against 689 characters of labels and counts on one
    parse page. `.mono` is 12.5px monospace with no truncation, so a 96-character path needs about
    720px and wrapped to three lines: the menu rendered roughly 54 lines of URL.
    """
    rendered = destination("Read the parts", "/runs/r1/jobs/j1/multipart", kind="page")
    assert 'href="/runs/r1/jobs/j1/multipart"' in rendered
    assert '<span class="mono">' not in rendered
    assert rendered.count("/runs/r1/jobs/j1/multipart") == 1


def test_a_destination_still_says_what_it_will_do_and_what_it_is_about() -> None:
    """The URL went; nothing else did. Dropping the kind word would hide a POST behind a link."""
    rendered = destination(
        "Judgements", "/benchmark/1/2/judgements", kind="page", scope=FILING, count="3 recorded"
    )
    assert "page" in rendered
    assert "[filing]" in rendered
    assert "3 recorded" in rendered


# --- the invocation card may not claim a call that never happened -------------------------------


def test_a_mock_answered_run_says_no_real_model_was_invoked() -> None:
    """rules.md section 10. The card printed a Bedrock id, a region and USD for an offline stub."""
    rendered = _render_job_page(attempt_providers=["mock"])
    assert "NO REAL MODEL WAS INVOKED" in rendered
    assert "mock" in rendered
    # THE FIGURES STAY. The journal counted them, so hiding them replaces a false claim with a
    # missing one; the warning goes above them instead.
    assert "Invocation" in rendered


def test_a_bedrock_answered_run_carries_no_provider_warning() -> None:
    """MUTATION PROOF: the warning must not fire on the runs it is not about."""
    rendered = _render_job_page(attempt_providers=["bedrock"])
    assert "NO REAL MODEL WAS INVOKED" not in rendered
    assert "does not record which provider" not in rendered


def test_an_attempt_with_no_recorded_provider_is_reported_as_unknown() -> None:
    """Not accused of being a mock. Every run stored before the field existed reads back empty."""
    rendered = _render_job_page(attempt_providers=[""])
    assert "does not record which provider answered it" in rendered
    assert "NO REAL MODEL WAS INVOKED" not in rendered


def test_a_job_with_no_attempt_at_all_carries_no_provider_sentence() -> None:
    """An absent invocation is not an unrecorded one, and the two get different pages."""
    rendered = _render_job_page(attempt_providers=[])
    assert "does not record which provider" not in rendered
    assert "NO REAL MODEL WAS INVOKED" not in rendered


# --- a multipart parse has no job-level response, and that is not a failure ---------------------


def test_a_multipart_parse_says_where_its_responses_are() -> None:
    """It used to claim the response was unreadable YAML and then show an empty block."""
    rendered = parsed_pane(
        base=("runs", "r1", "jobs", "j1"),
        view="side-by-side",
        parsed=None,
        outcomes_by_node={},
        raw_response="",
        responses_live_on_tasks=True,
    )
    assert "no single response" in rendered
    assert "not one readable YAML" not in rendered
    assert 'href="/runs/r1/jobs/j1/multipart"' in rendered
    assert 'href="/runs/r1/jobs/j1/assembled"' in rendered


def test_an_absent_response_does_not_claim_bytes_are_shown_below() -> None:
    """The pane promised the exact bytes and rendered an empty block. Now it says there are none."""
    rendered = parsed_pane(
        base=("runs", "r1", "jobs", "j1"),
        view="parsed",
        parsed=None,
        outcomes_by_node={},
        raw_response="",
    )
    assert "no response is stored against this job at all" in rendered
    assert "<pre" not in rendered


def test_an_unparseable_response_still_shows_its_exact_bytes() -> None:
    """MUTATION PROOF: the honest case above must not have removed the case that has bytes."""
    rendered = parsed_pane(
        base=("runs", "r1", "jobs", "j1"),
        view="parsed",
        parsed=None,
        outcomes_by_node={},
        raw_response="}{ not yaml",
    )
    assert "not one readable YAML" in rendered
    assert "}{ not yaml" in rendered


# --- a multipart parse is read from its assembly, beside the filing -----------------------------


def _assembly(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "part_count": 2,
        "node_count": 1,
        "status": "INCOMPLETE_WORK",
        "status_note": "not a completeness verdict",
        "parts": [
            {
                "part_id": "cover",
                "title": "FORM 10-Q",
                "type": "filing cover",
                "task_id": "tsk_1",
                "node_count": 1,
                "reference_count": 1,
                "references_resolved": 1,
                "output_tokens": 900,
                "truncated": False,
                "task_state": "SUCCEEDED",
                "stop_reason": "end_turn",
                "nodes": [
                    {
                        "id": "n1",
                        "type": HOSTILE,
                        "title": "Cover",
                        "content": "Total net sales were 391,035.",
                        "source": [{"filename": "a.htm", "quote": "Total net sales"}],
                    }
                ],
            },
            {
                "part_id": "risks",
                "title": "Risk Factors",
                "type": "section",
                "task_id": "tsk_2",
                "node_count": 0,
                "reference_count": 0,
                "references_resolved": 0,
                "output_tokens": 8000,
                "truncated": True,
                "task_state": "TRUNCATED",
                "stop_reason": "max_tokens",
                "nodes": [],
            },
        ],
    }
    body.update(overrides)
    return body


def test_a_multipart_parse_renders_its_assembled_nodes_beside_the_filing() -> None:
    """The whole Phase 2.1 protocol had an empty parsed pane on the screen built to show it."""
    rendered = _render_job_page(assembly=_assembly())
    assert "2 part(s) and 1 node(s)" in rendered
    assert "Total net sales were 391,035." in rendered
    assert "FORM 10-Q" in rendered
    assert "Risk Factors" in rendered


def test_a_part_that_produced_nothing_is_shown_with_the_reason() -> None:
    """35 of 81 parts of the benchmark parse produced no node, 16 of them truncated.

    Rendering only the parts with content would show a clean parse and hide every truncation in it.
    """
    rendered = _render_job_page(assembly=_assembly())
    assert "produced no node" in rendered
    assert "max_tokens" in rendered
    assert "blind continuation is prohibited" in rendered


def test_the_assembled_pane_states_its_status_and_claims_no_completeness() -> None:
    rendered = _render_job_page(assembly=_assembly())
    assert "INCOMPLETE_WORK" in rendered
    assert "not a completeness verdict" in rendered


def test_a_quoted_string_is_not_rendered_as_a_located_citation() -> None:
    """A job's validation carries no per-node outcome, so a resolution badge would be invented."""
    rendered = _render_job_page(assembly=_assembly())
    assert "quoted by the model" in rendered
    assert "not a located citation" in rendered
    for resolution in ("EXACT", "WHITESPACE_NORMALISED", "UNRESOLVED"):
        assert f">{resolution}<" not in rendered


def test_a_model_chosen_node_type_is_escaped_in_the_assembled_pane() -> None:
    """A part id, a title and a node type are strings a model wrote after reading a filing."""
    rendered = _render_job_page(assembly=_assembly())
    assert HOSTILE not in rendered
    assert HOSTILE_ESCAPED in rendered


def test_a_single_response_parse_is_unaffected_by_the_assembly_path() -> None:
    """MUTATION PROOF: the protocol that already worked must still read its own response."""
    rendered = _render_job_page()
    assert "part(s) and" not in rendered
    # The apostrophe is escaped by `esc`, so the assertion avoids one rather than encoding it.
    assert "own vocabulary" in rendered
    assert "a-shape-nobody-anticipated" in rendered
