"""Decode filed bytes to text without losing a single one of them.

WHY THIS IS PERMITTED AT ALL. The intact-source rule forbids rewriting, slicing or reconstructing
an original artifact. It explicitly permits provider-required transport adaptation that preserves
the complete compatible source — and "decoding source bytes with a recorded encoding" is the first
example the Phase 2 brief gives. A Converse text block takes a Python string; the artifact is a
byte sequence; something has to decode, and the honest thing is to decode losslessly and record
which codec did it.

THE ROUND TRIP IS VERIFIED, NOT ASSUMED. Every decode is re-encoded and compared to the original
bytes. If they differ, the member is marked lossy and the discrepancy is recorded rather than
shipped. In practice the fallback makes that impossible — latin-1 maps all 256 byte values to the
first 256 code points and always round-trips — which is exactly why it is the last resort and not
the first: a filing that is really UTF-8 must be read as UTF-8, or every non-ASCII character in it
reaches the model as mojibake.

HISTORICAL-FORMAT. Malformed markup is normal before 2005 and declared encodings are frequently
absent or wrong. The declared encoding is therefore RECORDED as a declaration and is not trusted
as an instruction: the codec that actually decodes the bytes is the one that is used, and both are
reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: Tried in order. The first that decodes without error and round-trips exactly is used.
#: `latin-1` is last and always succeeds, so decoding never fails and never silently drops a byte.
_CODECS: Final[tuple[str, ...]] = ("utf-8", "cp1252", "latin-1")

_XML_ENCODING = re.compile(rb"""<\?xml[^>]*encoding\s*=\s*["']([\w.-]+)["']""", re.IGNORECASE)
_META_CHARSET = re.compile(rb"""charset\s*=\s*["']?([\w.-]+)""", re.IGNORECASE)


@dataclass(frozen=True)
class DecodedText:
    """Text plus the evidence that it is the same content the bytes were."""

    text: str
    codec: str
    declared_encoding: str | None
    lossless: bool

    @property
    def characters(self) -> int:
        return len(self.text)


def declared_encoding(data: bytes) -> str | None:
    """The encoding the document DECLARES, which is not necessarily the one it uses."""
    head = data[:4096]
    match = _XML_ENCODING.search(head)
    if match:
        return match.group(1).decode("ascii", errors="replace")
    match = _META_CHARSET.search(head)
    if match:
        return match.group(1).decode("ascii", errors="replace")
    return None


def decode_source(data: bytes) -> DecodedText:
    """Decode filed bytes losslessly, recording which codec did it."""
    declared = declared_encoding(data)
    for codec in _CODECS:
        try:
            text = data.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
        return DecodedText(
            text=text,
            codec=codec,
            declared_encoding=declared,
            lossless=text.encode(codec, errors="strict") == data,
        )
    # Unreachable while latin-1 is in the list. Kept because removing the guarantee upstream
    # should fail here loudly rather than produce a silently mangled filing.
    raise UnicodeDecodeError(
        "source", data, 0, len(data), "no codec in the chain decoded these bytes"
    )
