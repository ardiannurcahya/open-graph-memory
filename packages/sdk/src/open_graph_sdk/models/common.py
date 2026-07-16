from __future__ import annotations

from enum import StrEnum


class DatasetStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class DocumentStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    STORAGE_FAILED = "storage_failed"
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    PERSISTING = "persisting"
    INDEXED = "indexed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class ReviewState(StrEnum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
