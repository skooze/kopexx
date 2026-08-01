"""SEC HTTP access with mandatory rate control and throttle classification."""

from .client import FetchResult, SecHttpClient
from .errors import (
    DirectoryListingError,
    SecClientError,
    SecNotFoundError,
    SecRateLimitedError,
    SecTransientError,
    SecUndeclaredAutomationError,
)
from .rate_limiter import Clock, FakeClock, SecRateLimiters, TokenBucketLimiter
from .throttle import (
    ThrottleKind,
    classify_403,
    extract_reference_id,
    looks_like_directory_listing,
    raise_for_403,
)

__all__ = [
    "Clock",
    "FetchResult",
    "SecHttpClient",
    "DirectoryListingError",
    "FakeClock",
    "SecClientError",
    "SecNotFoundError",
    "SecRateLimitedError",
    "SecRateLimiters",
    "SecTransientError",
    "SecUndeclaredAutomationError",
    "ThrottleKind",
    "TokenBucketLimiter",
    "classify_403",
    "extract_reference_id",
    "looks_like_directory_listing",
    "raise_for_403",
]
