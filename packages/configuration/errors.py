"""Configuration errors. A misconfiguration must fail at startup, never at request time."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Base class for configuration failures."""


class MissingModelRegionError(ConfigurationError):
    """A real model provider was selected with no region configured.

    There is deliberately no default. The region used to default to a hardcoded `us-east-1`, and
    Phase 1 discovery showed why that is unsafe rather than convenient: one of the five approved
    candidates is not offered in `us-east-1` at all, so a silent default would report a real model
    as unavailable and leave nothing in the code to point at.
    """


class InvalidUserAgentError(ConfigurationError):
    """The configured SEC User-Agent is missing, generic, or lacks a contact address.

    SEC-INVARIANT: SEC denylists known automation User-Agents and returns HTTP 403 with an
    "Undeclared Automated Tool" page. That 403 is indistinguishable by status code from a
    rate-limit block but requires the opposite response, so we refuse to start rather than
    generate traffic that will be blocked.
    """
