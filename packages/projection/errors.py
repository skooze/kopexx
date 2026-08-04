"""Typed errors for the source projection."""

from __future__ import annotations


class ProjectionError(Exception):
    """Base class for every failure in this package."""


class ProjectionIncompleteError(ProjectionError):
    """The projection would not carry every visible unit the inventory measured.

    Raised rather than returned, and this is the invariant the whole package rests on. A projection
    that silently drops a span is exactly the visible-content projection `rules.md` section 21 rule
    7 spent two phases refusing to authorize: it decides, in backend code, that some of a filing did
    not matter. The check is mechanical — every visible span id, every table element id and every
    image id the inventory found must appear in the document — and it fails closed.
    """
