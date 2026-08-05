"""The three words a progress marker may say, and the only place a count becomes words.

WHY THIS MODULE EXISTS AT ALL. A progress indicator on a review surface is the easiest thing in this
application to make dishonest. `12 of 77` reads as a fraction of the work done and is nothing of the
kind: it is a count of pages this server rendered, at the version of the evidence they carried when
it rendered them. The claim is narrowed here until it is exactly true of what is measured, and every
caller is routed through the same three words so that no page can widen it locally.

WHAT THIS MODULE REFUSES TO DO.

    IT NEVER FOLDS THE THREE STATES TOGETHER. `opened`, `opened at an earlier version` and
    `not opened` are three counts and are rendered as three. A superseded artifact folded into one
    total is the indicator the brief calls worse than none: it reports progress through evidence
    that has since moved, and the reader has no way to see that it moved.

    IT CANNOT EMIT `12 of 77`, AND THAT IS STRUCTURAL RATHER THAN POLITE. `Counts` carries no total
    and no property that computes one, so `counts_sentence` has no denominator to format and no
    percentage to divide. Because this is the only place a count is turned into words, the N-of-M
    form is unwritable in the rest of the application rather than merely discouraged.

    IT NEVER USES A REVIEW WORD. `FORBIDDEN_WORDS` is enforced by test 7.7, and three of the five
    already name something else here: `reviewed` is a job's `review_state`, `complete` is
    `HUMAN_APPROVED_COMPLETE_FOR_THIS_FILING` and the fourteen-condition mechanical gate, and
    `checked` is what the backend proves about a citation against the preserved bytes. A marker
    borrowing one of them would report a judgement where none has been recorded — and
    `review_history` is empty on all seven recorded parses, so every such marker would be false.

    IT NEVER CARRIES STATUS BY A GLYPH OR A COLOUR ALONE. Every marker is a word, in text, in the
    markup. A tick has no accessible name, and `img-src 'none'` means it could not have been an
    image in any case.

    IT NEVER GUESSES WHEN THE CURRENT VERSION IS UNKNOWN. An item whose fingerprint could not be
    computed — the record behind the destination no longer loads — renders NO marker and enters NO
    tally. It is never reported as `not opened`: that would be a measurement of a reader, exactly as
    a zero in a coverage column is a measurement of a model, and `model_comparison_view._withheld`
    states the same discipline for the same reason.

WHAT AN OPENED MARK ACTUALLY ASSERTS is one sentence long, it is `OPENED_NOTE`, and it accompanies
every count this module produces: the server rendered that page, at that version, and nothing else.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from .html import esc, tag

#: A key exists for this item at the fingerprint its destination carries RIGHT NOW.
OPENED: Final[str] = "opened"

#: A key exists, but only at a fingerprint the destination no longer carries — a retried call, a
#: superseding `FORMAT_REPAIR`, a re-acquired member, a recorded judgement. The evidence moved after
#: it was read, so what was read is not what is there.
EARLIER: Final[str] = "opened at an earlier version"

#: No key for this item at any fingerprint.
NEVER: Final[str] = "not opened"

#: The three words, and their stylesheet classes. There is no fourth entry and no default: a state
#: this mapping does not name cannot be rendered, which is what keeps "NEVER FOUR" mechanical.
_CLASSES: Final[dict[str, str]] = {
    OPENED: "opened",
    EARLIER: "opened-earlier",
    NEVER: "opened-never",
}

#: The separator between the terms of a count line, matching every other count line in this UI.
_SEPARATOR: Final[str] = " · "

# THE SENTENCE'S SECOND TERM IS DERIVED, NOT WRITTEN OUT AGAIN. A marker stands alone beside a link
# and says the whole phrase; the sentence's second term follows `N opened` and would repeat it —
# "9 opened · 3 opened at an earlier version". Taking the tail from the word itself is what stops
# the marker and the sentence drifting apart when one of them is edited.
_EARLIER_IN_A_SENTENCE: Final[str] = EARLIER.removeprefix(OPENED + " ")

#: The sentence that accompanies EVERY opened count, wherever one appears. It is the whole of what
#: the mark asserts, and it is stated rather than left to be inferred from the word `opened`.
OPENED_NOTE: Final[str] = (
    "Opened means this server rendered that page for you at the version stated. It is not a "
    "review, it is not a judgement, and it says nothing about whether the parse is correct."
)

#: Words a progress marker may never use. Three of them already mean something else in this
#: repository and would be read as the thing they already mean; `done` and `seen` claim a
#: completion that rendering a page is not. Test 7.7 reads this set, so adding a word here tightens
#: the check at every call site at once rather than in one view.
FORBIDDEN_WORDS: Final[frozenset[str]] = frozenset(
    {"reviewed", "done", "complete", "checked", "seen"}
)


def _state(current_fingerprint: str, marks: frozenset[str]) -> str:
    """Which of the three words one item gets. The only classification in this module.

    `marks` is every fingerprint recorded for the item, so an item read at three superseded versions
    and never at the current one is `EARLIER` once — never three times, and never `OPENED` because
    some older mark happens to exist.
    """
    if not marks:
        return NEVER
    if current_fingerprint in marks:
        return OPENED
    return EARLIER


def marker(item: str, current_fingerprint: str, opened: Mapping[str, frozenset[str]]) -> str:
    """The opened marker for one destination: an element carrying one of the three words.

    `opened` is `EvaluationStore.opened_items` verbatim — item to every fingerprint recorded for
    it — and `current_fingerprint` is what the destination carries now, computed from durable
    records only (section 4.4 reads no evidence file and hashes no response bytes).

    AN EMPTY `current_fingerprint` RENDERS NOTHING. It means the record the fingerprint is computed
    from could not be loaded, so the item's version is unknown and neither `opened` nor `not opened`
    is true of it. Emitting `not opened` there would state a fact about the reader that nobody
    measured; the mark is orphaned, and section 4.5 leaves naming it to the page where it occurs.
    This is `model_comparison_view._withheld`'s rule — no figure, never a zero — applied to a word.
    """
    if not current_fingerprint:
        return ""
    state = _state(current_fingerprint, opened.get(item) or frozenset())
    return tag("span", esc(state), class_=_CLASSES[state])


@dataclass(frozen=True)
class Counts:
    """Three tallies over one named scope, and deliberately NO total.

    THERE IS NO `total` FIELD AND NO PROPERTY THAT COMPUTES ONE. A denominator in this record is
    what would make `12 of 77` and `88.23%` writable, and the entire reason every count in the
    application is routed through this module is that they are not. A caller that needs to say how
    large a scope is says it from the scope itself — `77 calls` beside the sentence, never inside
    it, and never divided into anything.
    """

    opened: int = 0
    earlier: int = 0
    never: int = 0


def counts(
    items: Iterable[str],
    fingerprints: Mapping[str, str],
    opened: Mapping[str, frozenset[str]],
) -> Counts:
    """Tally one scope. `items` names the scope; `fingerprints` says what each item carries now.

    TWO KINDS OF ITEM ARE EXCLUDED FROM EVERY TALLY, AND BOTH EXCLUSIONS ARE THE HONEST ONE.

        An item in `items` with no current fingerprint cannot be classified at all: without the
        version the destination carries there is no way to tell a current mark from a superseded
        one, and calling it `not opened` would be a claim rather than an absence.

        A mark in `opened` for an item outside `items` belongs to a different scope — a task of
        another job, a filing page reached from somewhere else — and counting it would inflate the
        scope the sentence goes on to name.

    An item repeated in `items` is tallied ONCE. A hierarchy that lists one task twice must not make
    the same page count twice, which is the arithmetic every ratio-shaped progress bar gets wrong.
    """
    tallies = {OPENED: 0, EARLIER: 0, NEVER: 0}
    for item in dict.fromkeys(items):
        current = fingerprints.get(item) or ""
        if not current:
            continue
        tallies[_state(current, opened.get(item) or frozenset())] += 1
    return Counts(opened=tallies[OPENED], earlier=tallies[EARLIER], never=tallies[NEVER])


def counts_sentence(counts: Counts, *, noun: str) -> str:
    """The three tallies as one line: `9 calls opened · 3 at an earlier version · 65 not opened`.

    THE ONLY PLACE IN THE APPLICATION WHERE A COUNT BECOMES WORDS. Three terms, always three, always
    in this order, each built from the constants above. No total is available to this function, so
    an N-of-M form and a percentage are not things it declines to print — they are things it has no
    numbers to print.

    `noun` is a PLURAL noun naming the scope the three numbers were counted over: `calls`,
    `destinations of this parse`, `windows of this member`. Section 4.6 requires a denominator to be
    scoped and named, and naming the scope in the sentence is what stops one page's `9 opened` being
    read against another page's scope. It is not a total and no number is ever printed beside it.

    Returns PLAIN TEXT, not markup. The caller escapes it exactly as it escapes every other value.
    """
    opened_term = " ".join(part for part in (f"{counts.opened:,}", noun.strip(), OPENED) if part)
    return _SEPARATOR.join(
        (
            opened_term,
            f"{counts.earlier:,} {_EARLIER_IN_A_SENTENCE}",
            f"{counts.never:,} {NEVER}",
        )
    )
