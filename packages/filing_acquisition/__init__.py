"""Filing acquisition: download a filing's source objects and preserve them with provenance."""

from .acquisition import (
    SUPPORTED_ERAS,
    AcquiredObject,
    AcquisitionResult,
    acquire_filing,
    plan_inline_xbrl,
    storage_key,
)
from .errors import (
    FilingAcquisitionError,
    MissingPrimaryDocumentError,
    UnsupportedEraError,
)

__all__ = [
    "SUPPORTED_ERAS",
    "AcquiredObject",
    "AcquisitionResult",
    "FilingAcquisitionError",
    "MissingPrimaryDocumentError",
    "UnsupportedEraError",
    "acquire_filing",
    "plan_inline_xbrl",
    "storage_key",
]
