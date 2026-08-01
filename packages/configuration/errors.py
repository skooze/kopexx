"""Configuration errors. A misconfiguration must fail at startup, never at request time."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Base class for configuration failures."""


class InvalidUserAgentError(ConfigurationError):
    """The configured SEC User-Agent is missing, generic, or lacks a contact address.

    SEC-INVARIANT: SEC denylists known automation User-Agents and returns HTTP 403 with an
    "Undeclared Automated Tool" page. That 403 is indistinguishable by status code from a
    rate-limit block but requires the opposite response, so we refuse to start rather than
    generate traffic that will be blocked.
    """
