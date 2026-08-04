"""What an image's OWN header bytes say about it. Nothing else.

DIMENSIONS ARE READ, NEVER DECODED. No pixel is examined, no image library is imported, and no
dependency is added — `roadmap.md` and ADR-0019 both keep this application on the standard library.
Width and height come from the format's header, which is a transport fact in exactly the sense
`rules.md` invariant 14 permits: size, format, location.

WHAT IS NOT HERE, AND WILL NOT BE. Nothing describes, transcribes, captions or classifies an image.
A filed image goes to a MULTIMODAL parsing model intact, or it is reported unanalysed. Backend code
never says what a picture shows — `packages/source_transport/dispositions.py` carries the same rule
for the same reason.

AN UNREADABLE HEADER RETURNS None, NOT A GUESS. A fabricated dimension is indistinguishable from a
measured one in every report downstream, so the honest answer for a format this module does not
read is that the dimensions are not mechanically obtainable.
"""

from __future__ import annotations

from typing import Final

#: Byte signature to media type. The same signatures `source_transport.dispositions` recognises,
#: because a member's format must not depend on which module asked.
_SIGNATURES: Final[tuple[tuple[bytes, str], ...]] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

#: JPEG start-of-frame markers. The three excluded values in the 0xC0-0xCF range are a Huffman
#: table, a JPEG-LS extension and an arithmetic-coding table: they are not frame headers and
#: reading a size out of one produces a confident wrong answer.
_JPEG_FRAME_MARKERS: Final[frozenset[int]] = frozenset(set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC})


def media_type(data: bytes) -> str:
    """The media type these bytes actually are, or the octet-stream fallback."""
    for signature, name in _SIGNATURES:
        if data.startswith(signature):
            return name
    return "application/octet-stream"


def dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Width and height from the header, or (None, None) when they are not obtainable."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png(data)
    if data.startswith((b"GIF87a", b"GIF89a")):
        return _gif(data)
    if data.startswith(b"\xff\xd8\xff"):
        return _jpeg(data)
    return None, None


def _png(data: bytes) -> tuple[int | None, int | None]:
    # An IHDR chunk is mandatory and must be first: 8 signature bytes, a 4-byte length, the type,
    # then width and height as big-endian unsigned 32-bit integers.
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None, None
    return (
        int.from_bytes(data[16:20], "big"),
        int.from_bytes(data[20:24], "big"),
    )


def _gif(data: bytes) -> tuple[int | None, int | None]:
    # The logical screen descriptor follows the 6-byte header: width then height, little-endian.
    if len(data) < 10:
        return None, None
    return (
        int.from_bytes(data[6:8], "little"),
        int.from_bytes(data[8:10], "little"),
    )


def _jpeg(data: bytes) -> tuple[int | None, int | None]:
    """Walk the segment chain to the first start-of-frame marker.

    A JPEG carries no size in a fixed position: the frame header sits after an arbitrary number of
    application and quantisation segments whose lengths must be followed one at a time. A fixed
    offset works on the files a developer happened to test and fails on the next one.
    """
    cursor = 2
    limit = len(data)
    while cursor + 3 < limit:
        if data[cursor] != 0xFF:
            cursor += 1
            continue
        marker = data[cursor + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            cursor += 2
            continue
        if marker == 0xD9:
            return None, None
        length = int.from_bytes(data[cursor + 2 : cursor + 4], "big")
        if length < 2:
            return None, None
        if marker in _JPEG_FRAME_MARKERS:
            if cursor + 9 > limit:
                return None, None
            return (
                int.from_bytes(data[cursor + 7 : cursor + 9], "big"),
                int.from_bytes(data[cursor + 5 : cursor + 7], "big"),
            )
        cursor += 2 + length
    return None, None
