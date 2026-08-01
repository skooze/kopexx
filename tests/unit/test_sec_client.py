"""SEC throttle classification and rate limiting tests."""

from __future__ import annotations

from pathlib import Path

from packages.sec_client import (
    FakeClock,
    SecRateLimitedError,
    SecRateLimiters,
    SecUndeclaredAutomationError,
    ThrottleKind,
    TokenBucketLimiter,
    classify_403,
    extract_reference_id,
    looks_like_directory_listing,
    raise_for_403,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_sec_throttle_classification() -> None:
    """A rate block must be recognised from the body; the status code alone cannot tell."""
    body = _fixture("sec_403_rate_limit.html")
    assert classify_403(body) is ThrottleKind.RATE_LIMITED
    error = raise_for_403(body)
    assert isinstance(error, SecRateLimitedError)
    assert error.retryable is True


def test_undeclared_automation_classification() -> None:
    """A configuration defect must NOT be retryable; retrying only generates blocked traffic."""
    body = _fixture("sec_403_undeclared_automation.html")
    assert classify_403(body) is ThrottleKind.UNDECLARED_AUTOMATION
    error = raise_for_403(body)
    assert isinstance(error, SecUndeclaredAutomationError)
    assert error.retryable is False


def test_reference_id_is_extracted() -> None:
    """SEC asks for the reference identifier when reporting access problems."""
    assert extract_reference_id(_fixture("sec_403_rate_limit.html")) == (
        "0.a1b2c3d4.1754067600.2f3e4d5c"
    )
    assert extract_reference_id("no reference here") is None


def test_unknown_403_is_treated_as_rate_limit() -> None:
    """Fail safe: pausing on an unrecognised 403 is cheap, hammering is not."""
    error = raise_for_403("<html><body>Forbidden</body></html>")
    assert isinstance(error, SecRateLimitedError)


def test_directory_listing_rejected() -> None:
    """HISTORICAL-FORMAT: a folder URL returns 200 with an index page, not a filing."""
    assert looks_like_directory_listing(_fixture("sec_directory_listing.html"))
    assert not looks_like_directory_listing("<html><body>Item 1A. Risk Factors</body></html>")


def test_global_rate_limit() -> None:
    """The global bucket must pace sustained traffic at the configured rate."""
    clock = FakeClock()
    limiter = TokenBucketLimiter(6.0, clock=clock)
    limiter.acquire()  # first token is free from the initial fill
    total_wait = sum(limiter.acquire() for _ in range(6))
    # Six further requests at six per second require about one second of waiting.
    assert 0.9 <= total_wait <= 1.1, total_wait


def test_efts_rate_limit() -> None:
    """efts.sec.gov gets its own, slower bucket.

    Verified during research: efts returned HTTP 500 on the eighth of eight rapid requests while
    data.sec.gov sustained twenty-five sequential requests cleanly.
    """
    clock = FakeClock()
    limiters = SecRateLimiters(global_rps=6.0, efts_rps=1.0, clock=clock)
    assert limiters.for_host("efts.sec.gov") is limiters.efts_bucket
    assert limiters.for_host("https://efts.sec.gov/LATEST/search-index") is limiters.efts_bucket
    assert limiters.efts_bucket.requests_per_second == 1.0

    limiters.efts_bucket.acquire()
    waited = limiters.efts_bucket.acquire()
    assert 0.9 <= waited <= 1.1, waited


def test_sec_hosts_share_one_bucket() -> None:
    """SEC-INVARIANT: the documented limit is aggregate across hosts and machines."""
    limiters = SecRateLimiters()
    assert limiters.for_host("www.sec.gov") is limiters.for_host("data.sec.gov")
    assert limiters.for_host("https://www.sec.gov/Archives/edgar") is limiters.global_bucket


def test_try_acquire_does_not_block() -> None:
    clock = FakeClock()
    limiter = TokenBucketLimiter(1.0, clock=clock)
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is False
    clock.advance(1.0)
    assert limiter.try_acquire() is True
