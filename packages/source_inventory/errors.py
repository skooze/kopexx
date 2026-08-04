"""Typed errors for the mechanical source inventory.

Every error names the member it concerns. An inventory that fails without saying which document it
was reading is indistinguishable from one that read nothing.
"""

from __future__ import annotations


class SourceInventoryError(Exception):
    """Base class for every failure in this package."""


class MarkupUnreadableError(SourceInventoryError):
    """The bytes claimed to be markup could not be walked at all.

    Raised rather than returning an empty inventory. An empty inventory is indistinguishable from a
    document with no content, and a filing whose tables silently became zero is exactly the false
    negative this package exists to prevent.
    """


class ImageUnreadableError(SourceInventoryError):
    """An image's dimensions could not be read from its own header bytes.

    NOT raised for an unrecognised format: that returns dimensions of None, which is an honest
    "not mechanically obtainable". This is for a header that is present and malformed.
    """
