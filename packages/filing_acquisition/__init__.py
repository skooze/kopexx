"""Filing acquisition: download a filing's source objects and preserve them with provenance."""

from .acquisition import (
    SUPPORTED_ERAS,
    AcquiredObject,
    AcquisitionResult,
    acquire_filing,
    plan_inline_xbrl,
    storage_key,
)
from .documents import (
    FiledDocument,
    declared_document_count,
    list_filed_documents,
    looks_like_complete_submission,
    submission_header,
)
from .errors import (
    FilingAcquisitionError,
    MissingPrimaryDocumentError,
    SubmissionFormatError,
    UnsupportedEraError,
)
from .member_fetch import SecMemberFetcher

__all__ = [
    "SUPPORTED_ERAS",
    "AcquiredObject",
    "AcquisitionResult",
    "FiledDocument",
    "FilingAcquisitionError",
    "MissingPrimaryDocumentError",
    "SecMemberFetcher",
    "SubmissionFormatError",
    "UnsupportedEraError",
    "acquire_filing",
    "declared_document_count",
    "list_filed_documents",
    "looks_like_complete_submission",
    "plan_inline_xbrl",
    "storage_key",
    "submission_header",
]
