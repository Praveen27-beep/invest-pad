"""DTOs for /ingest/*. Staging review/promote payloads.

The inbound-email webhook body is NOT modeled here: Mailgun and SendGrid post
multipart/form-data and Postmark posts differently-cased JSON, so there is no one
Pydantic body FastAPI could validate the same way across all three -- see
app/ingest/webhook_providers.py, which reads ``Request`` directly per provider and
produces the same internal shape.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StageResultOut(BaseModel):
    """One adapter's ``ParseResult`` after staging. Mirrors ``db.imports.stage_batch``'s
    return value -- see docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md section 2."""

    batch_id: str
    parsed: int
    rejected: int
    sha256: str
    document_id: str | None
    notes: list[str]


class RejectionOut(BaseModel):
    row_number: int
    reason: str


class NeedsReviewOut(BaseModel):
    row_number: int
    confidence: str


class ReviewBatchOut(BaseModel):
    """What a human reads before deciding to promote. Mirrors
    ``db.imports.review_batch``'s return value."""

    status: str
    adapter: str
    filename: str | None
    row_count: int
    rejected_count: int
    notes: list[str] | None
    uploaded_at: datetime
    staged: int
    will_insert: int
    will_skip_as_duplicate: int
    rejections: list[RejectionOut]
    needs_review: list[NeedsReviewOut]


class PromoteResultOut(BaseModel):
    """Mirrors ``engine.types.ImportSummary``."""

    inserted: int
    skipped_duplicates: int
    rejected: list[dict]


class DiscardRequest(BaseModel):
    reason: str
