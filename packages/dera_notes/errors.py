"""DERA mirror errors."""

from __future__ import annotations


class DeraError(Exception):
    """Base class for DERA mirror failures."""


class DeraDiscoveryError(DeraError):
    """The authoritative dataset listing could not be parsed."""


class DeraLedgerError(DeraError):
    """The mirror ledger is inconsistent."""
