"""How a reader knows where they are, what a link will do, and which way is back.

WHY ONE MODULE FOR ALL OF IT. Six surfaces render links into each other — the panel, the parse hub,
the call hierarchy, one call, the completeness benchmark and the comparison — and every one of them
has to answer the same three questions before a click: where am I, what will this do, and have I
been here already. Answered surface by surface those answers drift, and a preview that disagrees
with the destination is worse than no preview. They are answered here once.

WHAT THIS MODULE REFUSES TO DO.

    IT NEVER DERIVES A TRAIL FROM THE PATH. `crumbs` is handed its ancestry by the handler that has
    already loaded the records. Splitting `request.path` would render `0000320193-25-000008` as its
    own crumb label, and it could not produce the issuer name or the form string at all.

    IT NEVER READS CLIENT STATE FOR THE MODE. `panel_mode` is a pure function of the route the
    router matched, never of a cookie, so a panel offering a parse menu is on a page that names a
    parse, a shared URL reproduces the same panel, and the whole thing renders with scripting
    disabled.

    IT NEVER CARRIES A COUNTER. `Home 71 awaiting` on the shell of every page would walk the run
    store — 71 runs and 765 task manifests today, unbounded tomorrow — to render a figure nobody
    asked this page for. Counts belong on the pages that exist to produce them.

    IT NEVER SIGNALS STATE BY COLOUR ALONE, AND NEVER BY A TOOLTIP. `title` does not exist on touch
    and is invisible to a keyboard, so every marker rendered here is text in the document.

    IT IMPORTS NO ORCHESTRATION. Nothing here reaches `packages.orchestrator`,
    `packages.completeness` or `packages.source_inventory`, at runtime or under `TYPE_CHECKING`.
    `ParserReviewService.inventoried_filing` calls `assemble_source_set` unconditionally on every
    invocation; a navigation helper that touched it would re-walk a multi-megabyte submission on
    each of the 77 task pages of a single parse.

EVERY VALUE IS ESCAPED. A crumb label carries a form string and an issuer name out of a filing, and
a destination label names a part a language model chose after reading one. Both are untrusted text
and both go through `esc`. There is exactly one exception, `destination`'s `marker`, which is
markup already built from these same helpers; it is documented where it is taken.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlencode

from .html import each, esc, join, tag

# --- panel modes --------------------------------------------------------------------------------

#: The three things the left panel can be. `SEARCH` is the entity-and-model form the panel has
#: always been; `PARSE` and `FILING` are the two subjects a page can have open, and each gets the
#: review menu written for it.
SEARCH: Final[str] = "search"
PARSE: Final[str] = "parse"
FILING: Final[str] = "filing"

#: The generic request the mode strip's own link carries. It is deliberately NOT a subject: a page
#: has a parse open or a filing open, never a "review", so this word is accepted from the query
#: string and mapped onto whichever subject the page actually has.
_REVIEW: Final[str] = "review"


def panel_subject(path: str, params: dict[str, str]) -> str:
    """What this page is ABOUT, read from the parameters the router matched.

    THE ROUTE IS THE ONLY EVIDENCE USED. `ReviewApp.handle` binds `Request(..., params=params, ...)`
    before calling the handler, so the subject is whatever the matched pattern named — not a guess
    from the path text, and not a remembered selection that a shared URL would not carry.
    """
    if params.get("run_id") and params.get("job_id"):
        return PARSE
    if path.startswith("/benchmark/") and params.get("cik") and params.get("accession"):
        return FILING
    return ""


def subject_mode(subject: str) -> str:
    """The panel mode a subject gets. The identity for `PARSE` and `FILING`.

    It exists so the mode strip can link at the generic word `review` and have it land on whichever
    subject the page has. Keeping the seam named — rather than comparing a query value against a
    subject directly — is what lets a requested mode and a page's subject be spelled differently
    without either meaning drifting.
    """
    return subject


def panel_mode(path: str, params: dict[str, str], requested: str) -> str:
    """Which panel body this page gets. A pure function of the ROUTE, never of a cookie.

    A MODE THAT CANNOT DISAGREE WITH ITS PAGE. The subject is read from the parameters the router
    matched, so a panel showing a parse menu is on a page that named a parse. A shared URL
    reproduces the same panel, and the whole thing renders with scripting disabled.

    `?panel_mode=review` ON A PAGE WITH NO SUBJECT IS IGNORED, and the mode strip renders that item
    disabled with its reason beside it. A control that appears and disappears is one nobody can
    learn — the rule `views.tabs` already states.

    THE QUERY KEY IS `panel_mode`, NEVER `panel`. `ReviewApp._panel_collapsed` reads `panel` for
    `open|closed` and falls back to the `kopexx_panel` cookie; reusing that key would force a
    reader to choose between a collapsed panel and a forced mode.

    `requested` is attacker-controlled query text and never reaches a page: anything outside the
    closed set resolves to `SEARCH` rather than being echoed or reflected.
    """
    subject = panel_subject(path, params)
    if requested == SEARCH:
        return SEARCH
    if subject == "" or (requested and requested not in {_REVIEW, subject_mode(subject)}):
        return SEARCH
    return subject_mode(subject)


# --- query-preserving hrefs ---------------------------------------------------------------------


#: The query keys a link may carry forward. Every one of these is read by a handler to rebuild
#: page state; anything else is a key this application does not know, and an unknown key reflected
#: into an href is attacker-controlled text on the reader's page for no benefit.
PRESERVED_QUERY_KEYS: Final[frozenset[str]] = frozenset(
    {
        # the search panel's own state
        "q",
        "cik",
        "accession",
        "from_date",
        "to_date",
        "strategy",
        "parsing_label",
        "image_label",
        "summary_label",
        "analysis_label",
        # NOT view/show/member/start. Those are page-local and were never preserved by the
        # literal `?panel=closed` this replaced, so dropping them is not a regression — and
        # `member` is a free-text identifier from the URL, which is the one key an attacker can
        # fill with anything. A page's own controls carry its own view state.
        # the panel's two independent controls
        "panel",
        "panel_mode",
    }
)


def with_query(path: str, query: dict[str, list[str]], **overrides: str | None) -> str:
    """`path` with the current query string, each override replacing or (on None) dropping a key.

    PERCENT-ENCODED HERE, HTML-ESCAPED BY `attributes`, exactly as `html.url` splits the two.
    Confusing them is the double-escape defect `html.url`'s docstring records: escaped once here
    and once again in the attribute, `run&1` became `href="/runs/run&amp;amp;1"`, which a browser
    resolves to a different run entirely.

    WHY THE WHOLE QUERY SURVIVES A CLICK. The collapse control was the bare literal `?panel=closed`,
    which discarded `cik`, `parsing_label`, `from_date` and `accession` — the four keys
    `ReviewApp._panel` rebuilds the entire panel from — so collapsing the panel silently deselected
    the entity and the model. That is the `Collapse preserves selections | NOT MET` row of the UX
    specification, and it closes by preserving what is already there rather than by every call site
    remembering to re-add it.

    A REPLACED KEY KEEPS ITS POSITION, so the same page reached twice produces the same URL and two
    links to one destination are one destination in a history list.

    `path` is passed through unchanged: it arrived from the router already percent-encoded, and
    encoding it a second time would turn `%2F` into `%252F`.

    ONLY KEYS THIS APPLICATION READS SURVIVE, AND THAT IS A SECURITY PROPERTY RATHER THAN TIDINESS.
    Preserving the WHOLE query string means any key an attacker puts in a URL is reflected back
    into an `href` on the page. Percent-encoding and attribute escaping make that non-executable —
    it is not an injection — but a crafted link would still put attacker-chosen text on a page the
    reader believes is theirs, and there is no reason for a key nothing reads to make the trip. The
    allow-list is the keys `ReviewApp` actually rebuilds state from; everything else is dropped.
    """
    pairs: list[tuple[str, str]] = []
    for key, values in query.items():
        if key not in PRESERVED_QUERY_KEYS and key not in overrides:
            continue
        if key in overrides:
            replacement = overrides[key]
            if replacement is not None:
                pairs.append((key, replacement))
            continue
        pairs.extend((key, value) for value in values)
    for key, value in overrides.items():
        if key not in query and value is not None:
            pairs.append((key, value))
    if not pairs:
        return path
    return path + "?" + urlencode(pairs)


# --- the global sections ------------------------------------------------------------------------

#: The two sections, their landing pages, and the one line each that says what is behind it.
#:
#: THERE WERE THREE. `Reviews` indexed every parse, which the home page already lists under the run
#: each parse belongs to, so it was a second door onto one room; `active_section` records why it
#: went. Adding a section here means adding a room, never a second way into an existing one.
#:
#: NO COUNTER ON ANY ITEM. `Home 71 awaiting` would need `list_run_ids()` and a `load_job` for
#: every run on the shell of every page, and the cost grows with the store. The blurb carries the
#: meaning instead, and it costs nothing to render.
_SECTIONS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("home", "Home", "/", "every run this instance has recorded"),
    ("filings", "Filings", "/filings", "every filing this instance holds evidence about"),
)


def _glyph(current: bool) -> str:
    """The third signal of active, rendered in the MARKUP and not in the stylesheet.

    `aria-current` is invisible to a sighted reader and a filled surface is invisible to a reader
    whose stylesheet never arrived. A text character in the document survives both, which is what
    the stylesheet's own standing rule means by never carrying status with colour alone. It is
    `aria-hidden` because `aria-current` already states the same fact to a screen reader, and
    announcing the name of a triangle twice per item is noise.
    """
    return tag("span", "&#9656; " if current else "&middot; ", aria_hidden="true")


def global_nav(active: str) -> str:
    """The two sections, always both, with the current one marked three ways.

    `active` is a key from `_SECTIONS` or the empty string. `/sign-in`, `/health` and `/static/*`
    light nothing, and an empty string is the honest rendering of that rather than a section
    arbitrarily marked current.
    """

    def item(key: str, label: str, href: str, blurb: str) -> str:
        current = key == active
        return tag(
            "li",
            join(
                tag(
                    "a",
                    join(_glyph(current), esc(label)),
                    href=href,
                    class_="nav-item nav-active" if current else "nav-item",
                    aria_current="page" if current else None,
                ),
                tag("span", esc(blurb), class_="hint"),
            ),
        )

    return tag(
        "nav",
        tag("ul", each(_SECTIONS, lambda section: item(*section))),
        class_="panel-nav",
        aria_label="sections",
    )


def active_section(path: str) -> str:
    """Which section this path belongs to. THE ORDER OF THESE TESTS IS LOAD-BEARING.

    EVERYTHING UNDER `/runs/` IS HOME, INCLUDING A PARSE. An earlier version put parses under their
    own `Reviews` section, on the reasoning that running a model and judging what it produced are
    different work. That was true and it was still the wrong nav: the home page ALREADY lists every
    run and every parse under it, so `Reviews` was a second door onto the same room. Two nav items
    reaching the same content teach a reader that the navigation does not mean anything.
    """
    if path == "/filings" or path.startswith("/benchmark/"):
        return "filings"
    if path in {"/", "/preflight", "/runs"} or path.startswith("/runs/"):
        return "home"
    return ""


# --- the panel mode strip -----------------------------------------------------------------------


def _mode_item(label: str, href: str, *, active: bool, reason: str) -> str:
    """One mode. Without an href it is a disabled span carrying why, never a hidden control."""
    if not href:
        return join(
            tag(
                "span",
                join(_glyph(False), esc(label)),
                class_="mode mode-disabled",
                aria_disabled="true",
            ),
            tag("span", esc(reason), class_="hint") if reason else "",
        )
    return tag(
        "a",
        join(_glyph(active), esc(label)),
        href=href,
        class_="mode mode-active" if active else "mode",
        aria_current="true" if active else None,
    )


def mode_strip(*, mode: str, search_href: str, review_href: str, review_reason: str) -> str:
    """The two things the panel can be, both always rendered, whichever this page can offer.

    THE UNAVAILABLE ITEM IS DISABLED, NOT HIDDEN — the rule `views.tabs` states: a control that
    appears and disappears depending on state is one a person cannot learn, and one that is visibly
    unavailable tells them the mode exists and what it needs. `review_reason` is that "what it
    needs", shown beside the item rather than in a tooltip.

    THREE SIGNALS FOR ACTIVE, NEVER COLOUR ALONE: `aria-current`, the filled `.mode-active`
    surface, and a leading glyph in the markup, so the active mode still reads as active to a
    keyboard, to a screen reader, and to a browser whose stylesheet never loaded.

    `Search and run` IS ALWAYS AVAILABLE AND DOES NOT CLAIM TO PRESERVE SELECTIONS. A job URL
    carries no `cik`, so the panel rebuilt from it has no entity and the form says so; that is a
    statement about the page, not a reason to withhold the mode.
    """
    return tag(
        "nav",
        join(
            tag("span", esc("PANEL"), class_="hint"),
            _mode_item("Search and run", search_href, active=mode == SEARCH, reason=""),
            _mode_item("Review menu", review_href, active=mode != SEARCH, reason=review_reason),
        ),
        class_="panel-mode",
        aria_label="panel mode",
    )


# --- breadcrumbs --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Crumb:
    """One ancestor of this page. An empty `href` makes it the current page: text, not a link."""

    label: str
    href: str = ""


def crumbs(trail: Sequence[Crumb]) -> str:
    """The ancestry of this page. Every crumb but the last is a link.

    SUPPLIED BY THE HANDLER, NEVER DERIVED FROM THE PATH. A trail split out of `request.path` would
    render `0000320193-25-000008` as its own label, and it could not produce the issuer name or the
    form string at all — those are already in hand where the records were loaded, and nowhere else.

    EVERY CRUMB NAMES ITS SCOPE, NOT AN IDENTIFIER, except the run, whose identifier is exactly what
    a person quotes in a bug report. The same filing reached under `Runs` and under `Filings` shows
    different trails on purpose: which route was taken determines what the parent crumb should do.

    An empty trail renders nothing at all, which is what the sign-in page passes. A page reached
    before authentication has no ancestry, and an empty strip is the honest rendering of that.
    """
    if not trail:
        return ""
    last = len(trail) - 1
    parts: list[str] = []
    for index, crumb in enumerate(trail):
        if index:
            parts.append(tag("span", "/", class_="sep", aria_hidden="true"))
        if index == last:
            parts.append(tag("span", esc(crumb.label), aria_current="page"))
        elif crumb.href:
            parts.append(tag("a", esc(crumb.label), href=crumb.href))
        else:
            # An ancestor with no page of its own is text. It is NOT given `aria-current`: that
            # belongs to exactly one crumb, the last, and two of them would tell a screen reader
            # the reader is in two places.
            parts.append(tag("span", esc(crumb.label)))
    return tag("nav", join(*parts), class_="crumbs", aria_label="breadcrumb")


# --- what a link will do, before it is clicked ---------------------------------------------------

#: The two moves in this UI where the SUBJECT of the page changes rather than just the page. Today
#: they happen silently through the two-tab strip, which is how a reviewer ends up reading a
#: filing's denominator believing it is a property of one model's run.
_SCOPES: Final[dict[str, str]] = {
    FILING: "[filing]",
    PARSE: "[parse]",
}

#: What a destination will DO, in one word:
#:
#:     page     an ordinary GET that renders a page
#:     anchor   a fragment of the page you are on, or of one page away
#:     POST     a form submission; there is no GET behind it
#:     stream   a server-sent-event stream that holds the connection
#:
#: The set is closed because the word is a promise. `/runs/{r}/jobs/{j}/queue` and
#: `/benchmark/{c}/{a}/judgements` were both POST-only, and a menu that offered either as a page
#: would have sent a reviewer into a 405; the progress route holds its connection open, and a reader
#: who clicks it expecting a page believes the browser has hung.
_KINDS: Final[tuple[str, ...]] = ("page", "anchor", "POST", "stream")


def scope_marker(kind: str) -> str:
    """`[filing]` or `[parse]`: this link changes what the page is ABOUT, not just which page.

    The brackets are in the markup rather than in the stylesheet, for the same reason every status
    marker on this surface is a word: a marker a disabled stylesheet erases is not a marker.

    An empty kind means "this link stays in the current scope" and renders nothing. Any other
    unknown value RAISES: a third scope would be a claim about the product that nobody has made,
    and silently rendering it would put that claim on a page.
    """
    if not kind:
        return ""
    if kind not in _SCOPES:
        raise ValueError(f"unknown link scope {kind!r}; the scopes are {sorted(_SCOPES)}")
    return tag("span", esc(_SCOPES[kind]), class_="scope")


def kind_word(kind: str) -> str:
    """The one word that says what this destination will do, before it is clicked.

    A KIND IS REQUIRED AND AN UNKNOWN ONE RAISES, including the empty string. A destination with no
    stated kind is precisely the defect this mechanism exists to prevent, and a renderer that
    quietly dropped the word would leave a POST-only control looking like an ordinary link.
    """
    if kind not in _KINDS:
        raise ValueError(f"unknown destination kind {kind!r}; the kinds are {list(_KINDS)}")
    return tag("span", esc(kind), class_="kind-word")


def _spaced(*parts: str) -> str:
    """Join rendered fragments with one space so two inline elements never abut.

    Without it `<a>Read the parts</a><span class="kind-word">page</span>` reads as one run-on string
    the moment the stylesheet that separates them is not there, which is the state every one of
    these markers is written to survive.
    """
    return " ".join(part for part in parts if part)


def destination(
    label: str,
    href: str,
    *,
    kind: str,
    note: str = "",
    count: str = "",
    scope: str = "",
    marker: str = "",
) -> str:
    """One link with everything a reader needs before clicking it. THE ONLY PLACE THAT RENDERS ONE.

    THE FIVE MECHANISMS, TOGETHER, BECAUSE APART THEY DRIFT.

        `note`    the destination SENTENCE — what evidence is there, not what the page is called.
                  Not `Spans`; `every visible span of one member, 200 to a window, with the control
                  that classifies it`.
        `count`   a figure, ONLY where it is cheap. A count that would cost an inventory walk or the
                  anchor ladder is passed as the empty string and renders nothing at all — NEVER as
                  a zero, because a zero in a coverage position is a measurement, which is the
                  discipline `model_comparison_view._withheld` already applies.
        `kind`    what the destination DOES, as a word: page, anchor, POST or stream.
        `scope`   `[filing]` or `[parse]` when following this link changes the subject of the page.
        `marker`  the opened marker, three words and never a bare glyph.

    `marker` IS MARKUP AND IS THE ONE VALUE NOT ESCAPED HERE. It is what `progress.marker` returns,
    built from these same helpers out of a stored fingerprint comparison; it holds no filing text,
    no model text and no stored free text. Everything else — the label a model chose for a part,
    the sentence and the figure — goes through `esc`.

    THE HREF IS NOT PRINTED BESIDE THE LINK, AND IT USED TO BE. The reasoning was that the owner
    quotes URLs in bug reports, which is true; the measurement is what killed it. On one parse page
    the panel carried 18 printed hrefs averaging 75 characters against 689 characters of actual
    labels and counts — 67 percent of the panel's text was the URLs. `.panel` is 320 pixels wide and
    `.mono` is 12.5-pixel monospace with no truncation, so a 96-character path needs about 720
    pixels and wraps to three lines: 18 links rendered roughly 54 lines of URL. A menu nobody can
    read is not navigation, and the address bar already holds the URL of wherever a click lands.

    AN EMPTY HREF RAISES. A destination that is unavailable is rendered by its caller as a disabled
    span carrying the reason — `views.tabs` and `ReviewApp._benchmark_href` both already do exactly
    that, because a link that 404s is worse than one that is visibly unavailable. A link to nowhere
    is the third option, and it is not offered.

    A FRAGMENT, NOT A BLOCK. The caller supplies the `li`, the `td` or the tile, because the same
    destination is rendered in all three and only the caller knows which.
    """
    if not href:
        raise ValueError(
            f"destination {label!r} has no href; an unavailable destination is a disabled span "
            "carrying its reason, never a link to nowhere"
        )
    return _spaced(
        scope_marker(scope),
        tag("a", esc(label), href=href),
        kind_word(kind),
        marker,
        tag("span", esc(note), class_="hint") if note else "",
        tag("span", esc(count), class_="hint") if count else "",
    )
