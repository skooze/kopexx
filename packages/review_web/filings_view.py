"""Two landing pages: every filing, and every judgement recorded about one filing.

WHY THESE EXIST. Until now this instance had one way in, the run list, and a run is machinery — a
reservation, an event log, a set of selections. The question a person actually arrives with is
"what has been judged, and what has not", which is a question about filings. So filings get a page
of their own, and the counters `nav.global_nav` deliberately refuses to carry on the shell of every
page live here instead, on the page that exists to produce them.

THERE WAS A THIRD PAGE IN THIS MODULE AND IT IS DELETED, ALONG WITH THE `Reviews` NAV SECTION THAT
REACHED IT. It indexed every parse, which is exactly what the home page already lists: every run,
and every parse under it. Two nav items reaching the same content teach a reader that the
navigation does not mean anything, so the second door was removed rather than the room.
`nav.active_section` records the same decision from the other side, and everything under `/runs/`
is Home.

WHAT THESE PAGES REFUSE TO DO.

    THEY COMPUTE NOTHING AND REACH NO SERVICE. Every figure arrives as an argument.
    `ParserReviewService.inventoried_filing` calls `assemble_source_set` unconditionally on every
    invocation, so a landing page that reached it to print a coverage figure would re-walk the
    preserved bytes of every filing it lists — 71 stored parses today, unbounded tomorrow. A count
    that is not cheaply available RENDERS AS NO COUNT, never as a zero, which is the discipline
    `model_comparison_view._withheld` already applies for exactly this reason.

    THEY NEVER RENDER AN EMPTY TABLE AS IF THERE WERE NOTHING TO DO. `review_history` is empty on
    all 71 stored parses and `var/evaluation-runs/benchmarks/` does not exist, so not one verdict
    and not one classification has ever been recorded on this instance. An empty judgements table
    would read as a settled system that has finished its work; the absence is stated in words
    instead, which is what every `no judgement recorded` sentence below is for.

    THEY NEVER FOLD DIFFERENT FACTS TOGETHER. `recorded parses` counts parses stored against a
    filing. `recorded judgements` counts stored benchmark-truth VERSIONS, which is a count of
    documents and not of items. Neither is a verdict: REVIEWED is a job's `review_state` and it is
    shown where a job is, and OPENED is a page this server rendered and it is `progress`'s word
    alone. Several of the obvious synonyms already mean one of the other two, which is why every
    column heading here says `recorded` and stops.

    THEY NEVER LINK WHERE A LINK WOULD 404. A filing this instance holds evidence about is not
    necessarily in the benchmark catalog, and `_for_display` raises `FilingNotInCatalogError` for
    one that is not. Those entries render as disabled text carrying the reason, exactly as
    `ReviewApp._benchmark_href` and `views.tabs` already do: a link that 404s is worse than one that
    is visibly unavailable.

    THEY NEVER SORT, RANK OR RECOMMEND. Rows arrive in the order the handler resolved them and are
    rendered in that order. No column is ordered by a figure and no row is highlighted —
    `rules.md` section 21 rule 14, and the prohibition `model_comparison_view` states one level up.

EVERY VALUE IS ESCAPED. An issuer label, a form string, a reviewer's note and a classification's
evidence line all come from a filing, a manifest or a person, and every one of them goes through
`esc` before it reaches the page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from .benchmark_view import CLASSIFICATION_KIND
from .html import badge, each, esc, join, tag, url
from .nav import destination

#: How many judgements one truth version's card lists. The count is authoritative and is stated
#: beside the window: a silently shortened list of what a person has decided is the same defect as
#: a silently shortened request, and one fully classified filing carries 1,750 span judgements.
JUDGEMENTS_SHOWN: int = 200

#: Why a filing this instance holds evidence about may still have no completeness pages. The
#: sentence is the reason, not an apology: without a catalog record there is no preserved source
#: set to inventory, so there is nothing to measure a parse against.
_NOT_IN_CATALOG: Final[str] = (
    "this filing is not in the benchmark catalog, so it has no denominator to measure against"
)

#: The three item kinds a benchmark judgement may attach to, mapped from the group each is stored
#: under in a truth document to the word a reader sees. There is no fourth group: a judgement about
#: anything else has no inventory item to attach to.
_JUDGEMENT_GROUPS: Final[tuple[tuple[str, str], ...]] = (
    ("spans", "text span"),
    ("tables", "table element"),
    ("images", "filed image"),
)

_FILING_HEADERS: Final[tuple[str, ...]] = (
    "filing",
    "issuer",
    "filed",
    "recorded parses",
    "recorded judgements",
)

_VERSION_HEADERS: Final[tuple[str, ...]] = (
    "version",
    "source set",
    "judgements recorded",
    "unaccepted suggestions",
    "standing",
)

_JUDGEMENT_HEADERS: Final[tuple[str, ...]] = (
    "item kind",
    "item",
    "classification",
    "reviewer",
    "recorded at",
    "standing",
    "note",
)


# --- shared fragments ---------------------------------------------------------------------------


def _mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """One nested mapping of a stored record, or an empty one.

    A JOB, A TASK AND A TRUTH DOCUMENT ARE READ AS MAPPINGS AND NOT AS RECORDS, exactly as
    `multipart_view` reads them: importing the record classes would pull the evaluation store, and
    through it the orchestration layer, into a package whose entire job is turning values into
    markup. The cost is that a missing branch has to be tolerated here rather than at load time,
    and tolerating it as an empty mapping is what stops one malformed stored document taking a
    whole index page down.
    """
    value = source.get(key)
    return value if isinstance(value, Mapping) else {}


def _text(source: Mapping[str, Any], key: str) -> str:
    """One scalar field of a stored record as text. `None` becomes empty, never the word None."""
    value = source.get(key)
    return "" if value is None else str(value)


def _withheld(reason: str) -> str:
    """A cell for a figure this page was not given, saying which figure is missing and why.

    NEVER A ZERO AND NEVER A DASH ALONE, the rule `model_comparison_view._withheld` states. A zero
    in a count column is a measurement: `0 recorded parses` says this filing has never been parsed,
    and a page that prints it because the handler did not tally anything has made that claim
    without measuring it.
    """
    return tag("span", esc(reason), class_="hint")


def _table(headers: Sequence[str], body: str) -> str:
    """One table that scrolls inside its own box. The page itself never scrolls sideways."""
    return tag(
        "div",
        tag(
            "table",
            join(
                tag("thead", tag("tr", each(headers, lambda header: tag("th", esc(header))))),
                tag("tbody", body),
            ),
        ),
        class_="scroll-x",
    )


def _state(value: Any) -> str:
    """One judgement's classification as a badge, coloured by the map `benchmark_view` owns.

    THE COLOURING IS IMPORTED RATHER THAN REPEATED. This page and the pages that record a
    classification must agree on what REQUIRES_REVIEW looks like, and two dictionaries of the same
    twelve values drift the moment a thirteenth is added. A COLOUR IS A CATEGORY AND NEVER A SCORE,
    and every badge carries its value as a WORD, so the colour is redundant by construction — the
    no-colour-alone rule, and `img-src 'none'` means it could not have been a glyph in any case.
    """
    text = "" if value is None else str(value)
    return (
        badge(text, CLASSIFICATION_KIND.get(text, "neutral")) if text else _withheld("not recorded")
    )


def _unavailable(label: str, reason: str) -> str:
    """A destination that exists but cannot be reached from here, with the reason beside it.

    THE REASON IS IN THE DOCUMENT, NOT IN A TOOLTIP. `title` does not exist on touch and is
    invisible to a keyboard, and the whole point of rendering the unavailable entry at all is that
    a reader learns the destination exists and what it needs — the rule `views.tabs` states.
    """
    return join(
        tag("span", esc(label), aria_disabled="true"),
        tag("span", esc(reason), class_="hint"),
    )


def _recorded_count(value: Any, *, nothing: str, template: str, absent: str) -> str:
    """A measured count, the honest word for a measured zero, or no figure at all.

    THE THREE CASES ARE GENUINELY DIFFERENT AND ARE KEPT APART. A count the handler tallied is a
    measurement and is printed. A tally that came back zero is also a measurement and is printed as
    a sentence rather than as a bare `0`, because `0` beside a filing reads as an accusation. A key
    the handler did not supply is not a measurement of anything, and printing zero for it would
    invent one.

    `bool` IS EXCLUDED DELIBERATELY. It is a subclass of `int` in Python, so `True` would otherwise
    format as the count `1` — a flag silently becoming a figure is the kind of defect that survives
    review because it reads correctly.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return _withheld(absent)
    if value == 0:
        return tag("span", esc(nothing), class_="hint")
    return esc(template.format(count=f"{value:,}"))


def _filing_link(*, cik: str, accession: str, held: bool, label: str, tail: Sequence[str]) -> str:
    """A link into this filing's completeness surface, or disabled text carrying the catalog reason.

    `held` is `catalog.filing(cik, accession) is not None`, resolved by the handler. When it is
    False every benchmark route 404s for this accession, so nothing here is rendered as a link.
    """
    if not held or not cik or not accession:
        return _unavailable(label, _NOT_IN_CATALOG)
    return tag("a", esc(label), href=url("benchmark", cik, accession, *tail))


# --- every filing ---------------------------------------------------------------------------------


def filings_index(*, filings: Sequence[Mapping[str, Any]]) -> str:
    """Every filing this instance holds evidence about, with what has been recorded against each.

    Each entry is a plain mapping the handler builds, and every key but the first four is optional:

        cik, accession, form_as_filed, filing_date, issuer_label
                            identity, as `FilingRecord.to_mapping()` spells it
        benchmark_held      `catalog.filing(cik, accession) is not None`. ABSENT MEANS NOT HELD,
                            which fails towards a disabled entry rather than towards a link into a
                            404 — the direction `ReviewApp._benchmark_href` already fails in
        parse_count         recorded parses of this filing; absent means the handler did not tally
                            them, and renders as no figure rather than as zero
        judgement_versions  stored benchmark-truth versions; `0` is a measurement and says no
                            judgement has ever been recorded, absent says nobody counted

    Order is the handler's and is passed through untouched.
    """
    return join(
        tag("h1", esc("Filings — every filing this instance holds evidence about")),
        _filings_intro_card(),
        _filings_card(filings),
    )


def _filings_intro_card() -> str:
    return tag(
        "div",
        join(
            tag("h2", "What evidence means here"),
            tag(
                "p",
                esc(
                    "Preserved bytes with a recorded hash, whatever parses have been run against "
                    "them, and whatever a person has classified about the mechanical inventory of "
                    "them. A filing appears here because something is stored about it, never "
                    "because it was judged interesting."
                ),
            ),
            tag(
                "p",
                esc(
                    "A filing with no catalog record has no completeness pages: without a "
                    "preserved source set there is nothing to inventory, so there is no "
                    "denominator to measure a parse against. Those entries say so rather than "
                    "offering a link that would 404."
                ),
                class_="hint",
            ),
        ),
        class_="card",
    )


def _filing_row(filing: Mapping[str, Any]) -> str:
    """One filing: how to reach its evidence, and what has been recorded against it."""
    cik = _text(filing, "cik")
    accession = _text(filing, "accession")
    held = bool(filing.get("benchmark_held"))
    label = f"{_text(filing, 'form_as_filed')} {accession}".strip()
    return tag(
        "tr",
        join(
            tag(
                "td",
                _filing_link(
                    cik=cik, accession=accession, held=held, label=label or accession, tail=()
                ),
            ),
            tag("td", esc(_text(filing, "issuer_label"))),
            tag("td", esc(_text(filing, "filing_date"))),
            tag(
                "td",
                join(
                    _recorded_count(
                        filing.get("parse_count"),
                        nothing="no parse recorded",
                        template="{count} recorded parse(s)",
                        absent="not counted here",
                    ),
                    tag(
                        "div",
                        _filing_link(
                            cik=cik,
                            accession=accession,
                            held=held,
                            label="every parse of this filing",
                            tail=("models",),
                        ),
                        class_="hint",
                    ),
                ),
            ),
            tag(
                "td",
                join(
                    _recorded_count(
                        filing.get("judgement_versions"),
                        nothing="no judgement recorded",
                        template="{count} recorded version(s)",
                        absent="not counted here",
                    ),
                    tag(
                        "div",
                        _filing_link(
                            cik=cik,
                            accession=accession,
                            held=held,
                            label="judgements recorded",
                            tail=("judgements",),
                        ),
                        class_="hint",
                    ),
                ),
            ),
        ),
    )


def _filings_card(filings: Sequence[Mapping[str, Any]]) -> str:
    if not filings:
        return tag(
            "div",
            join(
                tag("h2", "No filing has evidence stored against it"),
                tag(
                    "p",
                    esc(
                        "Nothing has been acquired, parsed or classified on this instance yet. "
                        "That is reported here rather than as an empty table, which would read as "
                        "a catalog with nothing in it."
                    ),
                ),
            ),
            class_="card",
        )
    return tag(
        "div",
        join(
            tag("h2", esc(f"{len(filings):,} filing(s)")),
            tag(
                "p",
                esc(
                    "In the order the handler resolved them. Nothing here is ranked and no filing "
                    "is recommended; the two count columns say what has been recorded, not whether "
                    "any of it was any good."
                ),
                class_="hint",
            ),
            _table(_FILING_HEADERS, each(filings, _filing_row)),
        ),
        class_="card",
    )


# --- every judgement about one filing --------------------------------------------------------------


def judgements_page(
    *,
    filing: Mapping[str, Any],
    versions: Sequence[int],
    documents: Sequence[Mapping[str, Any]],
) -> str:
    """Every human judgement recorded about one filing, superseded versions included.

    `filing` carries `cik`, `accession`, `form_as_filed`, `issuer_label` and `benchmark_held`, as
    `filings_index` reads them.

    `versions` is `EvaluationStore.benchmark_truth_versions` verbatim — every stored version for
    this filing, from a key listing that reads no document. It is the AUTHORITATIVE history.

    `documents` is whichever of those versions the handler actually loaded, each one
    `BenchmarkTruth.to_mapping()` verbatim. It may be shorter than `versions` and is never longer;
    a version present in the history with no document loaded renders its row with the figures
    withheld rather than with zeros, because nobody read it.

    NOTHING IS OVERWRITTEN AND THE PAGE SHOWS THAT. Each version is one more judgement than the one
    before it and the previous document stays on disk, exactly as an accepted artifact is superseded
    rather than rewritten. A completeness figure computed against version 3 would mean nothing if
    version 3 could be edited into version 4 under the same name.

    NOTHING ON THIS PAGE RECORDS ANYTHING. Every classification control is a form POST on the page
    that shows the item beside its source, and this page says where those are.
    """
    cik = _text(filing, "cik")
    accession = _text(filing, "accession")
    held = bool(filing.get("benchmark_held"))
    label = f"{_text(filing, 'form_as_filed')} {accession}".strip()
    return join(
        tag("h1", esc(f"Judgements recorded — {label or accession}")),
        tag("p", esc(f"{_text(filing, 'issuer_label')} — CIK {cik}")),
        _what_a_judgement_is_card(),
        _versions_card(versions, documents),
        each(documents, _document_card),
        _where_a_judgement_is_recorded_card(cik=cik, accession=accession, held=held),
    )


def _what_a_judgement_is_card() -> str:
    return tag(
        "div",
        join(
            tag("h2", "What a judgement here is"),
            tag(
                "p",
                esc(
                    "One reviewer's classification of ONE item of ONE filing's mechanical "
                    "inventory — a text span, a table element or a filed image — with who said it "
                    "and when. It is evidence about this accession at this source hash and it is "
                    "never a rule about filings: one issuer is a fixture, never a specification."
                ),
            ),
            tag(
                "p",
                esc(
                    "The default classification of every item is REQUIRES_REVIEW, and that is not "
                    "a placeholder. An unreviewed item is neither demanded nor excused; it blocks "
                    "the mechanical gate until a person looks at it, which is the correct pressure."
                ),
                class_="hint",
            ),
            tag(
                "p",
                esc(
                    "A mechanical suggestion is displayed as an unaccepted proposal with its "
                    "evidence attached and is NOT a judgement. It is marked as such in the table "
                    "below and counts towards nothing until a person records one."
                ),
                class_="hint",
            ),
        ),
        class_="card",
    )


def _versions_card(versions: Sequence[int], documents: Sequence[Mapping[str, Any]]) -> str:
    """The version history, newest first, with the current version named as such."""
    loaded = {
        int(document.get("version") or 0): document
        for document in documents
        if isinstance(document, Mapping)
    }
    # THE UNION, NOT THE HISTORY ALONE. A document the handler loaded whose version the key listing
    # did not report is a disagreement between two reads of the same store, and hiding either side
    # of it would hide the disagreement itself.
    known = sorted(set(versions) | set(loaded), reverse=True)
    if not known:
        return tag(
            "div",
            join(
                tag("h2", "No judgement has ever been recorded for this filing"),
                tag(
                    "p",
                    esc(
                        "No benchmark truth document is stored, so every text span, every table "
                        "element and every filed image of this filing is REQUIRES_REVIEW. Any "
                        "coverage percentage computed against this filing today is a ratio against "
                        "an unclassified denominator, and that is a fact about the denominator "
                        "rather than about any model."
                    ),
                ),
                tag(
                    "p",
                    esc(
                        "This is reported here rather than as an empty table, which would read as "
                        "a filing whose classification was finished."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        )
    current = known[0]
    return tag(
        "div",
        join(
            tag("h2", esc(f"{len(known):,} recorded version(s), newest first")),
            tag(
                "p",
                esc(
                    "Each version records one more judgement than the one before it, and the "
                    "earlier document stays on disk unchanged. A version whose document was not "
                    "loaded for this page reports no figures rather than zeros."
                ),
                class_="hint",
            ),
            _table(
                _VERSION_HEADERS,
                each(known, lambda version: _version_row(version, loaded, current=current)),
            ),
        ),
        class_="card",
    )


def _version_row(version: int, loaded: Mapping[int, Mapping[str, Any]], *, current: int) -> str:
    document = loaded.get(version)
    standing = "current" if version == current else "superseded"
    if document is None:
        figures = join(
            tag("td", _withheld("this version was not loaded for this page")),
            tag("td", _withheld("not loaded")),
            tag("td", _withheld("not loaded")),
        )
    else:
        figures = join(
            tag("td", esc(_text(document, "source_set_sha256")[:16]), class_="mono"),
            tag(
                "td",
                _recorded_count(
                    document.get("reviewed_count"),
                    nothing="no judgement at this version",
                    template="{count} judgement(s)",
                    absent="not recorded in this document",
                ),
            ),
            tag(
                "td",
                _recorded_count(
                    document.get("suggestion_count"),
                    nothing="no unaccepted suggestion",
                    template="{count} unaccepted suggestion(s)",
                    absent="not recorded in this document",
                ),
            ),
        )
    return tag("tr", join(tag("td", esc(version)), figures, tag("td", esc(standing))))


def _judgements(document: Mapping[str, Any]) -> list[tuple[str, str, Mapping[str, Any]]]:
    """Every judgement in one truth document as (item kind, item id, judgement), in stored order.

    The item id is the KEY the document stores the judgement under, which is what the ledger and
    the gate resolve against. A judgement whose body disagrees with its key would be a corrupted
    document, and the key is the side that everything else in the application uses.
    """
    found: list[tuple[str, str, Mapping[str, Any]]] = []
    for group_key, kind in _JUDGEMENT_GROUPS:
        for item_id, raw in _mapping(document, group_key).items():
            if isinstance(raw, Mapping):
                found.append((kind, str(item_id), raw))
    return found


def _judgement_row(kind: str, item_id: str, judgement: Mapping[str, Any]) -> str:
    suggested = bool(judgement.get("is_unaccepted_suggestion"))
    evidence = _text(judgement, "evidence")
    return tag(
        "tr",
        join(
            tag("td", esc(kind)),
            tag("td", esc(item_id), class_="mono"),
            tag("td", _state(judgement.get("classification"))),
            tag("td", esc(_text(judgement, "reviewer"))),
            tag("td", esc(_text(judgement, "at")[:19])),
            tag(
                "td",
                badge("unaccepted suggestion", "warn")
                if suggested
                else tag("span", esc("recorded by a person"), class_="hint"),
            ),
            tag(
                "td",
                join(
                    esc(_text(judgement, "note")),
                    tag("div", esc(evidence), class_="hint") if evidence else "",
                ),
            ),
        ),
    )


def _document_card(document: Mapping[str, Any]) -> str:
    """One stored truth version, and every judgement it carries."""
    version = _text(document, "version")
    judgements = _judgements(document)
    if not judgements:
        return tag(
            "div",
            join(
                tag("h2", esc(f"Version {version}")),
                tag(
                    "p",
                    esc(
                        "This version carries no judgement and no suggestion. It is shown because "
                        "it is stored, not because it is empty."
                    ),
                    class_="hint",
                ),
            ),
            class_="card",
        )
    shown = judgements[:JUDGEMENTS_SHOWN]
    window = (
        tag(
            "p",
            esc(
                f"{len(judgements):,} entries are recorded at this version; the first "
                f"{JUDGEMENTS_SHOWN:,} are listed. The count above it is authoritative."
            ),
            class_="hint",
        )
        if len(shown) < len(judgements)
        else ""
    )
    return tag(
        "div",
        join(
            tag("h2", esc(f"Version {version} — {len(judgements):,} entry(ies)")),
            window,
            _table(
                _JUDGEMENT_HEADERS,
                each(shown, lambda entry: _judgement_row(*entry)),
            ),
        ),
        class_="card",
    )


def _where_a_judgement_is_recorded_card(*, cik: str, accession: str, held: bool) -> str:
    """Where the controls are, since there are none on this page.

    THIS PAGE IS A RECORD AND NOT A FORM. A classification is recorded beside the item it is about,
    with the source bytes on the same screen, because a judgement made from a list of identifiers
    is a judgement made without looking at the evidence.
    """
    entries = (
        (
            "Text spans",
            ("spans",),
            "every visible span of one member, a window at a time, with the control that "
            "classifies it",
        ),
        (
            "Table elements",
            ("tables",),
            "every table element with its extracted grid beside its raw source slice",
        ),
        ("Filed images", ("images",), "every image filed with this accession"),
        (
            "The completeness benchmark",
            (),
            "the mechanical inventory of the preserved bytes, and what has been classified of it",
        ),
        (
            "Every parse of this filing",
            ("models",),
            "every recorded parse, in recorded order, measured against this denominator",
        ),
    )

    def item(entry: tuple[str, tuple[str, ...], str]) -> str:
        label, tail, note = entry
        if not held or not cik or not accession:
            return tag("li", _unavailable(label, _NOT_IN_CATALOG))
        return tag(
            "li",
            destination(label, url("benchmark", cik, accession, *tail), kind="page", note=note),
        )

    return tag(
        "div",
        join(
            tag("h2", "Where a judgement is recorded"),
            tag(
                "p",
                esc(
                    "Nothing on this page records anything. Every classification control is a form "
                    "post on the page that shows the item beside the source bytes it came from."
                ),
                class_="hint",
            ),
            tag("ul", each(entries, item), class_="menu"),
        ),
        class_="card",
    )
