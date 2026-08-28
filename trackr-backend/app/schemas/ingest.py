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
    #: Rows written to holding_snapshot (app.db.holdings.record_snapshot), 0 for every
    #: adapter except cas_pdf -- see app.db.imports.stage_batch. Not a ledger count and
    #: not gated on review/promote: holding_snapshot is a checking dataset, not the
    #: transaction ledger.
    declared_holdings: int = 0


class BatchSummaryOut(BaseModel):
    """One row of GET /ingest/batches -- enough to find a batch again and decide what
    to do with it; the row-level detail is review_batch's job."""

    batch_id: str
    filename: str | None
    adapter: str
    status: str
    row_count: int
    rejected_count: int
    uploaded_at: datetime


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
