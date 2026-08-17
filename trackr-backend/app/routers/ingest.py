"""POST /ingest/csv, POST /ingest/email, GET /ingest/stage/{batch_id},
POST /ingest/stage/{batch_id}/promote, POST /ingest/stage/{batch_id}/discard.

Everything here is a thin HTTP layer over ``app/db/imports.py``'s already-tested staging
state machine (``stage_batch`` / ``review_batch`` / ``promote_batch`` / ``discard_batch``)
and, for the inbound-email path, ``app/ingest/webhook.py``. No adapter writes to the
ledger from this router: staging only, until ``promote`` -- an authenticated,
attributed, separate call. See docs/INGESTION.md "Staging: why nothing auto-commits".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.auth.dependencies import get_current_user
from app.config import Settings, get_settings
from app.database import get_conn
from app.db import consent, imports
from app.ingest import webhook, webhook_providers
from app.ingest.webhook_providers import WebhookNotConfiguredError
from app.ingest.zerodha_tradebook import ZerodhaTradebookAdapter
from app.schemas.ingest import (
    DiscardRequest,
    PromoteResultOut,
    ReviewBatchOut,
    StageResultOut,
)
from app.storage.factory import get_store

router = APIRouter(prefix="/ingest", tags=["ingestion"])

#: adapter query param -> factory. Only "zerodha_tradebook" has a real parser; the
#: openapi.yaml contract also lists "generic_csv", which does not exist yet -- CLAUDE.md:
#: never invent a parser to fill a contract slot.
_CSV_ADAPTERS = {"zerodha_tradebook": ZerodhaTradebookAdapter}


def _investor_code(conn: Any, investor_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM investor WHERE id = %s", (investor_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such investor: {investor_id}")
    return row[0]


@router.post("/csv", response_model=list[StageResultOut], status_code=status.HTTP_202_ACCEPTED)
async def ingest_csv(
    investor_id: str = Form(...),
    account_id: str = Form(...),
    adapter: str = Form(...),
    files: list[UploadFile] = File(...),
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Multi-file by design -- Console caps each tradebook download at 365 days, so a
    full history is several files. Each is staged independently; merge-and-dedupe
    happens at promotion, via the same ``dedupe_key`` unique index every import uses."""
    factory = _CSV_ADAPTERS.get(adapter)
    if factory is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"no adapter for {adapter!r}; supported: {sorted(_CSV_ADAPTERS)}",
        )

    investor_code = _investor_code(conn, investor_id)
    consent.require_consent(conn, investor_id)
    store = get_store(settings)
    results = []
    for upload in files:
        content = await upload.read()
        results.append(
            imports.stage_batch(
                conn,
                factory(),
                content,
                investor_id=investor_id,
                account_id=account_id,
                filename=upload.filename or "",
                store=store,
                investor_code=investor_code,
                actor_uid=None,
            )
        )
    return results


def _reject_if_oversized(request: Request, settings: Settings) -> None:
    """Refuse an oversized request from ``Content-Length`` alone, before FastAPI reads
    the body into memory at all -- let alone before any provider translator
    base64-decodes an attachment out of it."""
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > settings.ingest_max_attachment_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"request exceeds INGEST_MAX_ATTACHMENT_BYTES ({settings.ingest_max_attachment_bytes})",
        )


@router.post(
    "/email", response_model=list[StageResultOut], status_code=status.HTTP_202_ACCEPTED
)
async def ingest_email(
    request: Request,
    conn: Any = Depends(get_conn),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Inbound-parse webhook (SendGrid / Mailgun / Postmark). Public internet surface:
    verifies the request's provider-specific credential and translates its
    provider-specific shape -- see app/ingest/webhook_providers.py -- before anything
    reaches app/ingest/webhook.py's provider-ignorant ``handle_inbound_email``. Routing
    beyond that is by the ``to`` address alone -- see app/ingest/webhook.py."""
    # The dependency-injected settings, not app.main's module-level get_settings() --
    # app.main's auth-failure handlers read this back for their log line, since a
    # registered @app.exception_handler is called by Starlette directly and never goes
    # through FastAPI's dependency injection (so it would otherwise see the real
    # process-wide Settings even under a test's dependency_overrides).
    request.state.settings = settings
    _reject_if_oversized(request, settings)
    if settings.ingest_webhook_provider is None:
        raise WebhookNotConfiguredError()
    to, attachments = await webhook_providers.verify_and_translate(request, settings)
    store = get_store(settings)
    return webhook.handle_inbound_email(conn, store, to, attachments)


@router.get("/stage/{batch_id}", response_model=ReviewBatchOut)
def review_stage(batch_id: str, conn: Any = Depends(get_conn)) -> dict[str, Any]:
    """What a human reads before deciding. Predicts what promotion will do, including
    which rows are already in the ledger, rather than reporting it afterwards."""
    result = imports.review_batch(conn, batch_id)
    result["needs_review"] = [
        {
            "row_number": r["row_number"],
            "confidence": (
                str(r["confidence"]) if isinstance(r["confidence"], Decimal) else r["confidence"]
            ),
        }
        for r in result["needs_review"]
    ]
    return result


@router.post("/stage/{batch_id}/promote", response_model=PromoteResultOut)
def promote_stage(
    batch_id: str,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """The second explicit, attributed action. Writes staged rows to the ledger --
    the only place this router writes a transaction."""
    summary = imports.promote_batch(conn, batch_id, actor_uid=current_user["id"])
    return {
        "inserted": summary.inserted,
        "skipped_duplicates": summary.skipped_duplicates,
        "rejected": summary.rejected,
    }


@router.post("/stage/{batch_id}/discard")
def discard_stage(
    batch_id: str,
    body: DiscardRequest,
    conn: Any = Depends(get_conn),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Reject a batch without promoting it. The staged rows are kept, not deleted --
    what was rejected and why is the evidence that review happened."""
    imports.discard_batch(conn, batch_id, body.reason, actor_uid=current_user["id"])
    return {"status": "discarded"}
