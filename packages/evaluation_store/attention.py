"""Which destinations a reviewer has already had rendered, and at which version of the evidence.

WHY THIS IS A STORE CONCERN AND NOT `localStorage`. The marker has to be rendered INTO the link,
before it is clicked, which is the only place it is useful — so the server has to be able to see
it. A cookie was measured against the same requirement and refused: roughly 4 KB of headroom
against 724 stored task records today, and one filing carries 77 parts across seven parses. A
progress indicator that silently drops its oldest entries is worse than none.

WHY IT IS NOT ON THE JOB OR THE TASK RECORD. `EvaluationStore.save_job` and `save_task` stamp
`updated_at` on every write, so recording an open there would move the timestamp on an evidence
manifest — saying a model's artifact changed because somebody looked at it. Marks therefore live
under a NEW TOP-LEVEL PREFIX, `attention/`, sibling of `runs/` and `benchmarks/`. Deleting that
directory resets every mark and loses not one byte that was paid for, and that property is the
whole reason it must not live inside `runs/`.

WHAT A MARK MAY CLAIM, EXACTLY. That this server rendered that destination for that reviewer at the
version stated. Never reviewed, seen, checked, done or complete: three of those already mean
something else here, and `review_state` is the only place a judgement is ever recorded. The word is
`opened`, which is mechanically true of a GET and cannot under-count.

WHAT THIS MODULE REFUSES. It reads no evidence object and hashes nothing over response bytes: a
fingerprint is built from values already in a durable record, so computing one costs nothing. It
holds no count, no percentage and no opinion about whether a parse is correct. Nothing here is ever
sent to a model, and no orchestration, validation or completeness code reads it.

SECURITY-INVARIANT: EVERY SEGMENT OF AN ATTENTION KEY IS MINTED HERE OR VALIDATED AGAINST A CLOSED
ALPHABET, because an attention key becomes a filesystem path. The reviewer segment is a hex digest
of a configured label and never the label itself; run, job and task segments go through the same
`require_*` guards the run tree uses; the CIK and accession through `cik_padded` and
`accession_dashed`; the item through a closed literal set or a store-issued identifier; the
fingerprint through a fixed hex pattern. Two dots, a forward slash and a backslash are outside every
one of those alphabets — the same discipline `EvaluationStore._task_evidence_key` states for a
model-chosen part identifier, and it applies here for the same reason: a guard that exists only
because "no caller would do that" stops holding the first time a caller does.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

from packages.sec_identity import accession_dashed, cik_padded

from .errors import InvalidIdentifierError
from .identity import (
    RUN_PREFIX,
    TASK_PREFIX,
    require_job_id,
    require_run_id,
    require_task_id,
)

#: The single top-level prefix every mark is written under. Named once, so the promise that
#: `rm -r var/evaluation-runs/attention/` resets all progress is enforced by construction rather
#: than by everybody remembering it.
ATTENTION: Final[str] = "attention"

#: Every destination that is not identified by a store-issued identifier.
#:
#: A CLOSED SET, NOT A CONVENTION. These strings become filenames. Membership is exact and there is
#: no normalisation step: `Hub` is not `hub`, because a guard that repairs its input teaches callers
#: that the guard is optional.
ITEMS: Final[frozenset[str]] = frozenset(
    {
        "hub",
        "hierarchy",
        "assembled",
        "read-raw",
        "read-parsed",
        "read-side-by-side",
        "overview",
        "inventory",
        "spans",
        "tables",
        "images",
        "models",
        "judgements",
    }
)

#: The two scope segments. `runs` mirrors the run tree's own spelling so a reviewer reading a
#: directory listing can see which job a mark belongs to without a lookup.
_RUNS: Final[str] = "runs"
_JOBS: Final[str] = "jobs"
_BENCHMARK: Final[str] = "benchmark"

#: What `reviewer_token` mints and what a key segment is checked against. Fixed width, lowercase
#: hex: an author label may contain a space, a dot or a slash and none of them ever reaches a key.
_REVIEWER_TOKEN = re.compile(r"^[0-9a-f]{32}$")

#: What `fingerprint` mints. Sixteen hex characters is 64 bits over values that already differ by
#: construction; it is a version stamp for a comparison, never a security claim.
_FINGERPRINT = re.compile(r"^[0-9a-f]{16}$")

# BOTH ARE APPLIED WITH `fullmatch`, NOT `match`, AND THE DIFFERENCE IS NOT COSMETIC. `$` also
# matches immediately before a trailing newline, so 32 hex characters followed by "\n" satisfies
# `^[0-9a-f]{32}$` under `match` — and that string would then be a path segment carrying a newline.
# `fullmatch` admits the exact string or nothing.

#: The LITERAL segments of each scope, by position, ending in the empty field a trailing slash
#: produces. Every position not named here is an identity, and `require_prefix` hands each of those
#: to the guard that owns it rather than pattern-matching it. Written as the shape of a split so a
#: prefix is checked whole — a missing trailing slash is a different string, not a near miss.
_JOB_SHAPE: Final[tuple[str, ...]] = (ATTENTION, _RUNS, _JOBS, "")
_FILING_SHAPE: Final[tuple[str, ...]] = (ATTENTION, _BENCHMARK, "")


def reviewer_token(author: str) -> str:
    """A fixed-width path segment for one reviewer identity, from a label that may be anything.

    `ParserReviewService.author` is a configured LABEL supplied from ignored environment state. It
    is free text — it may carry a space, a dot, a slash or a backslash — so it never reaches a
    storage key; its digest does. The digest is not a secret and is not treated as one: it says
    whose scratch trail this is, and the same label on two machines produces the same segment, which
    is what makes a trail follow the person rather than the process.
    """
    return hashlib.sha256(author.encode("utf-8")).hexdigest()[:32]


def fingerprint(*parts: object) -> str:
    """A stable stamp of the VERSION of one destination, from values already in a durable record.

    NO EVIDENCE OBJECT IS READ AND NOTHING IS HASHED OVER RESPONSE BYTES. Every input a caller has
    to supply — a job's `updated_at`, a task's `idempotency`, an assembly's part count, a source-set
    hash, a truth version — is already parsed and in hand where the marker is rendered, so a stale
    mark is detected for the cost of a string comparison. Fingerprinting the artifact itself would
    put a read of a preserved model response behind a decoration on a link.

    THE UNIT SEPARATOR IS NOT DECORATION. Joining on it keeps ("ab", "c") and ("a", "bc") apart, and
    it cannot occur inside any of the identifiers, states, hashes or ISO timestamps that are passed
    here.
    """
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def require_item(item: str) -> str:
    """SECURITY-INVARIANT: an item becomes a FILENAME, so it is a closed literal or an issued id.

    Two admissible shapes and no third. A member of `ITEMS`, which is matched exactly; or an
    identifier this store minted — `tsk_…` for one multipart call, `run_…` for one run's ledger —
    which is checked by the same guard the run tree uses. Both alphabets exclude a dot, a slash, a
    backslash and an upper-case letter, so no traversal fragment survives either path, and the dot
    exclusion is also what makes `{item}.{fingerprint}.txt` split back apart unambiguously.
    """
    if item in ITEMS:
        return item
    if item.startswith(TASK_PREFIX):
        return require_task_id(item)
    if item.startswith(RUN_PREFIX):
        return require_run_id(item)
    raise InvalidIdentifierError(
        f"{item!r} is not an attention item. An item becomes a filename, so it is either one of "
        f"the {len(ITEMS)} known destination names or an identifier this store issued: "
        f"{TASK_PREFIX} or {RUN_PREFIX} followed by 26 lowercase base32 characters."
    )


def job_prefix(reviewer_token: str, run_id: str, job_id: str) -> str:
    """Every mark one reviewer has made about ONE child job, as a listable prefix.

    Scoped to the job rather than to the run because that is the unit a reviewer works through and
    the unit a panel renders: one listing answers "what have I opened of this parse" for all of it.
    """
    return (
        f"{ATTENTION}/{_require_reviewer_token(reviewer_token)}"
        f"/{_RUNS}/{require_run_id(run_id)}/{_JOBS}/{require_job_id(job_id)}/"
    )


def filing_prefix(reviewer_token: str, cik: str, accession: str) -> str:
    """Every mark one reviewer has made about ONE filing, as a listable prefix.

    The filing scope is separate from the job scope on purpose: a filing's completeness surfaces
    outlive every parse against it, exactly as its benchmark truth does, so filing them under
    whichever run happened to exist first would tie a reviewer's trail to that run's lifetime.

    `cik_padded` and `accession_dashed` are the single home for that normalisation — rules.md
    section 5 — and they refuse everything that is not a ten-digit CIK and a dashed accession, which
    is why nothing here pads or hyphenates anything itself.
    """
    return (
        f"{ATTENTION}/{_require_reviewer_token(reviewer_token)}"
        f"/{_BENCHMARK}/{cik_padded(cik)}/{accession_dashed(accession)}/"
    )


def opened_key(prefix: str, item: str, fingerprint: str) -> str:
    """The one immutable object recording that a destination was rendered at a version.

    THE FINGERPRINT IS IN THE FILENAME AND NOT IN THE BODY. `list_keys(prefix, max_depth=1)` then
    answers "opened, opened at an earlier version, or not opened" for every destination of a scope
    with ZERO file reads, and staleness is a string comparison. The panel renders that marker into
    as many as 77 links on one page; a body read per link would be 77 opens for a decoration.

    NOTHING IS EVER MERGED INTO THIS OBJECT. One key per (reviewer, scope, item, fingerprint) is
    what makes two browser tabs safe without a lock: they either write the same key with a different
    timestamp, which loses nothing, or two different keys, which lose nothing either.

    ONE MARK IS ONE PLAIN-TEXT OBJECT holding one timestamp line, named `{item}.{fingerprint}.txt`.
    Neither field admits a dot, so `EvaluationStore.opened_items` splits the name back apart on one
    without a pattern to keep in step.
    """
    name = f"{require_item(item)}.{_require_fingerprint(fingerprint)}.txt"
    return f"{require_prefix(prefix)}{name}"


def require_prefix(prefix: str) -> str:
    """SECURITY-INVARIANT: re-validate a scope prefix by REBUILDING it, segment by segment.

    A prefix reaches the store as one string, and a string accepted whole carries whatever the
    caller put in it. This splits it, hands every segment back to the guard that owns it and returns
    what `job_prefix` or `filing_prefix` would have minted — so an accepted prefix is by
    construction one this module could have produced, and anything else raises before a key exists.

    The trailing slash is required rather than tolerated: it is what makes the remainder of a listed
    key a filename, which is the whole of `opened_items`.
    """
    parts = prefix.split("/")
    if len(parts) == 7 and (parts[0], parts[2], parts[4], parts[6]) == _JOB_SHAPE:
        return job_prefix(parts[1], parts[3], parts[5])
    if len(parts) == 6 and (parts[0], parts[2], parts[5]) == _FILING_SHAPE:
        return filing_prefix(parts[1], parts[3], parts[4])
    raise InvalidIdentifierError(
        f"{prefix!r} is not an attention prefix. Build one with `job_prefix` or `filing_prefix`: "
        f"every segment of a key under {ATTENTION}/ is minted by this module or validated against "
        "a closed alphabet, and a prefix taken as free text would be neither."
    )


def _require_reviewer_token(value: str) -> str:
    if not _REVIEWER_TOKEN.fullmatch(value):
        raise InvalidIdentifierError(
            f"{value!r} is not a reviewer token. `reviewer_token` mints one as 32 lowercase "
            "hexadecimal characters; the author label it is derived from never reaches a key."
        )
    return value


def _require_fingerprint(value: str) -> str:
    if not _FINGERPRINT.fullmatch(value):
        raise InvalidIdentifierError(
            f"{value!r} is not a destination fingerprint. `fingerprint` mints one as 16 lowercase "
            "hexadecimal characters, and it is a path segment like every other."
        )
    return value
