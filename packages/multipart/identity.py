"""Carrying a MODEL-CREATED identifier safely, without ever changing it.

TWO VALUES, ONE MEANING, AND THEY ARE NOT INTERCHANGEABLE.

    part_id         exactly what the model returned. Displayed, compared, reported, sent back to
                    the model in the next request. Never rewritten, never normalised, never
                    lower-cased, never truncated.

    storage_token   a mechanically derived, filesystem-safe rendering of it, used ONLY where a
                    human needs to recognise a directory. It is never an identity: two different
                    exact identifiers can never produce the same token, because the token carries a
                    digest of the exact value.

WHY BOTH RATHER THAN JUST THE SAFE ONE. The Phase 2.1 brief is explicit that part identifiers are
opaque to the backend and that the backend may sanitise for storage "while preserving the exact
original model-returned ID". Keeping only the sanitised form would be the backend renaming the
model's work — the same failure as normalising a model's section titles into a vocabulary, one
layer down.

WHY THE STORE STILL DOES NOT USE THIS IN A KEY. `packages/evaluation_store` builds every path from
identifiers it minted itself. This token appears inside manifests and in the UI, so a hostile
identifier is at worst escaped text. That is defence in depth, not redundancy: the guard here is
what makes the token safe to display and to log, and the guard there is what makes the path safe.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Final

from .errors import UnsafePartIdentifierError

#: Beyond this a model-chosen identifier is not an identifier. The bound is generous — a model may
#: reasonably return something descriptive — and it exists so an identifier cannot become a payload.
MAX_PART_IDENTIFIER_CHARACTERS: Final[int] = 200

#: How much of the sanitised form survives into the token. The digest after it carries the identity.
_SLUG_CHARACTERS: Final[int] = 40
_DIGEST_CHARACTERS: Final[int] = 12

_UNSAFE = re.compile(r"[^a-z0-9]+")


def require_part_identifier(value: str) -> str:
    """Return the model's identifier unchanged, or refuse it with the reason.

    Refuses: an empty or whitespace-only identifier, one longer than the bound, and one carrying a
    control character. Everything else — spaces, punctuation, a non-Latin script, the filing's own
    numbering — is accepted exactly as returned, because the model names its own work.
    """
    if not isinstance(value, str) or not value.strip():
        raise UnsafePartIdentifierError(
            "a part identifier is empty. The model names its own parts, and an unnamed part "
            "cannot be scheduled, cited, rerun or reviewed."
        )
    if len(value) > MAX_PART_IDENTIFIER_CHARACTERS:
        raise UnsafePartIdentifierError(
            f"a part identifier of {len(value)} characters exceeds the "
            f"{MAX_PART_IDENTIFIER_CHARACTERS}-character bound; an identifier that long is content "
            "rather than an identifier"
        )
    control = [c for c in value if unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"}]
    if control:
        raise UnsafePartIdentifierError(
            "a part identifier carries a control or formatting character, which would corrupt "
            "every record and every log line that quotes it"
        )
    return value


def storage_token(part_identifier: str) -> str:
    """A safe, recognisable, collision-free rendering of a model-created identifier.

    The digest is not decoration. Two identifiers that sanitise to the same slug — `Note 3` and
    `note-3`, or two 60-character titles sharing a prefix — would otherwise become the same
    directory name, and the second parse would overwrite the first. The digest is taken over the
    EXACT identifier, so distinct identifiers always produce distinct tokens.
    """
    require_part_identifier(part_identifier)
    digest = hashlib.sha256(part_identifier.encode("utf-8")).hexdigest()[:_DIGEST_CHARACTERS]
    slug = (
        _UNSAFE.sub("-", part_identifier.strip().lower()).strip("-")[:_SLUG_CHARACTERS].strip("-")
    )
    return f"{slug}-{digest}" if slug else f"part-{digest}"
