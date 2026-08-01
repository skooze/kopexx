"""Token-bucket rate limiting for SEC access.

SEC-INVARIANT: the documented limit is ten requests per second "regardless of the number of
machines used to submit requests". Sharding across processes, containers, or addresses does not
multiply the budget, so the bucket must be shared. This module provides an in-process
implementation and a Redis-backed interface for the distributed case.

SEC-INVARIANT: efts.sec.gov (full-text search) tolerates far less than the main hosts. It is
given its own, much slower bucket.

IMPLEMENTATION STATUS: in-process limiter IMPLEMENTED; Redis-backed distributed limiter PLANNED.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


class Clock:
    """Injectable clock so rate-limiter tests are deterministic and fast."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FakeClock(Clock):
    """A manually advanced clock for tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self.slept: list[float] = []

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._now += seconds

    def advance(self, seconds: float) -> None:
        self._now += seconds


# Floating-point tolerance for token comparison.
#
# After sleeping exactly the computed delay, the refill can land a fraction below 1.0 because
# `tokens + elapsed * rate` is not exactly `1.0` in binary floating point. Without a tolerance the
# acquire loop spins forever on ever-smaller deltas: each pass computes a tinier deficit, sleeps a
# tinier interval, and still fails the `>= 1.0` test. One nanotoken is far below the resolution of
# any real request rate.
TOKEN_EPSILON = 1e-9


@dataclass
class _Bucket:
    capacity: float
    tokens: float
    refill_per_second: float
    updated_at: float


class TokenBucketLimiter:
    """A thread-safe token bucket.

    ``capacity`` bounds burst size. A capacity of 1 makes the limiter strictly paced, which is
    what SEC access wants: bursts are not blocked by SEC, but sustained rate is enforced, so a
    burst merely borrows against the next second and provides no benefit.
    """

    def __init__(
        self,
        requests_per_second: float,
        *,
        capacity: float | None = None,
        clock: Clock | None = None,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._clock = clock or Clock()
        self._lock = threading.Lock()
        cap = capacity if capacity is not None else 1.0
        self._bucket = _Bucket(
            capacity=cap,
            tokens=cap,
            refill_per_second=requests_per_second,
            updated_at=self._clock.now(),
        )

    @property
    def requests_per_second(self) -> float:
        return self._bucket.refill_per_second

    def _refill_locked(self) -> None:
        now = self._clock.now()
        elapsed = max(0.0, now - self._bucket.updated_at)
        self._bucket.tokens = min(
            self._bucket.capacity,
            self._bucket.tokens + elapsed * self._bucket.refill_per_second,
        )
        self._bucket.updated_at = now

    def try_acquire(self) -> bool:
        """Consume one token without blocking. Returns False when none is available."""
        with self._lock:
            self._refill_locked()
            if self._bucket.tokens >= 1.0 - TOKEN_EPSILON:
                self._bucket.tokens = max(0.0, self._bucket.tokens - 1.0)
                return True
            return False

    def acquire(self) -> float:
        """Block until a token is available. Returns the seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                self._refill_locked()
                if self._bucket.tokens >= 1.0 - TOKEN_EPSILON:
                    self._bucket.tokens = max(0.0, self._bucket.tokens - 1.0)
                    return waited
                deficit = 1.0 - self._bucket.tokens
                delay = deficit / self._bucket.refill_per_second
            self._clock.sleep(delay)
            waited += delay


class SecRateLimiters:
    """The two buckets SEC access requires, held together so callers cannot forget one."""

    def __init__(
        self,
        global_rps: float = 6.0,
        efts_rps: float = 1.0,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.global_bucket = TokenBucketLimiter(global_rps, clock=clock)
        self.efts_bucket = TokenBucketLimiter(efts_rps, clock=clock)

    def for_host(self, host: str) -> TokenBucketLimiter:
        """Return the bucket governing a host.

        SEC-INVARIANT: www.sec.gov and data.sec.gov share one bucket because the documented limit
        is aggregate. efts.sec.gov gets its own, slower bucket.
        """
        normalized = host.lower().strip()
        if normalized.startswith("http"):
            normalized = normalized.split("//", 1)[-1]
        normalized = normalized.split("/", 1)[0]
        if normalized.startswith("efts."):
            return self.efts_bucket
        return self.global_bucket
