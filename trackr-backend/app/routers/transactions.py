"""GET /investors/{id}/transactions, POST /investors/{id}/transactions,
GET /investors/{id}/lots, GET /investors/{id}/realised."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_conn, money
from app.db.consent import require_consent
from app.db.repository import load_transactions, save_transactions
from app.engine.lots import compute_lots
from app.engine.realised import compute_realised
from app.engine.types import Transaction
from app.schemas.transactions import (
    ImportSummaryOut,
    LotOut,
    RealisedOut,
    TransactionIn,
    TransactionOut,
)

router = APIRouter(prefix="/investors", tags=["transactions", "derived"])


@router.get("/{investor_id}/transactions", response_model=list[TransactionOut])
def transactions(
    investor_id: str,
    isin: str | None = None,
    account_id: str | None = None,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    connection: Any = Depends(get_conn),
) -> list[dict[str, Any]]:
    """List the ledger. ``from``/``to`` per contracts/openapi.yaml; ``from`` is a Python
    keyword, so the query parameter alias is applied here rather than to the field name."""
    rows = load_transactions(
        connection,
        investor_id=investor_id,
        account_id=account_id,
        isin=isin,
        date_from=from_,
        date_to=to,
    )
    return [
        {
            "id": t.id,
            "account_id": t.account_id,
            "isin": t.isin,
            "txn_date": t.txn_date,
            "txn_type": str(t.txn_type),
            "quantity": money(t.quantity),
            "price": money(t.price),
            "charges": money(t.charges),
            "dividend_amount": money(t.dividend_amount),
            "source": str(t.source) if t.source else None,
            "source_ref": t.source_ref,
            "created_at": t.created_at,
        }
        for t in rows
    ]


@router.post("/{investor_id}/transactions", response_model=ImportSummaryOut)
def create_transactions(
    investor_id: str,
    body: list[TransactionIn],
    connection: Any = Depends(get_conn),
) -> dict[str, Any]:
    """Append transactions -- manual entry, and the fallback path every other adapter
    needs when parsing fails. Idempotent on ``dedupe_key``: a duplicate is skipped and
    counted, never rejected as an error, per contracts/openapi.yaml.

    ``investor_id`` scopes the URL; each row still carries its own ``account_id``, which
    is what ``save_transactions`` actually writes against -- unvalidated here against
    ``investor_id`` for the same reason the sibling GET endpoints do not validate it
    either, a database foreign key still refuses an account that does not exist.

    All logic lives in ``app.db.repository.save_transactions``; this handler only
    translates between the wire shape and ``Transaction``.
    """
    require_consent(connection, investor_id)
    transactions = [
        Transaction(
            isin=t.isin,
            txn_date=t.txn_date,
            txn_type=t.txn_type,
            quantity=t.quantity,
            price=t.price,
            charges=t.charges,
            dividend_amount=t.dividend_amount,
            account_id=t.account_id,
            source=t.source,
            source_ref=t.source_ref,
            raw_payload=t.raw_payload,
        )
        for t in body
    ]
    summary = save_transactions(connection, transactions)
    return {
        "inserted": summary.inserted,
        "skipped_duplicates": summary.skipped_duplicates,
        "rejected": summary.rejected,
    }


@router.get("/{investor_id}/lots", response_model=list[LotOut])
def lots(
    investor_id: str, as_of: date | None = None, connection: Any = Depends(get_conn)
) -> list[dict[str, Any]]:
    """Open FIFO lots. ``as_of`` enables the same historical replay every derived
    endpoint supports -- the engine takes one and today is simply the default."""
    rows = load_transactions(connection, investor_id=investor_id)
    return [
        {
            "isin": lot.isin,
            "open_date": lot.open_date,
            "quantity_open": money(lot.quantity_open),
            "cost_per_unit": money(lot.cost_per_unit),
        }
        for lot in compute_lots(rows, as_of=as_of)
    ]


def _financial_year_bounds(fy: str) -> tuple[date, date]:
    """``"2025-26"`` -> (2025-04-01, 2026-03-31). April-to-March, the same boundary
    ``app.engine.xirr.financial_year_start`` documents -- this only applies that existing
    rule as a filter, it does not define a new one."""
    try:
        start_year_str, end_suffix = fy.split("-", 1)
        start_year = int(start_year_str)
        end_year = (
            start_year // 100 * 100 + int(end_suffix)
            if len(end_suffix) == 2
            else int(end_suffix)
        )
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"fy must look like '2025-26', got {fy!r}"
        ) from exc
    if end_year != start_year + 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"fy must span consecutive years, got {fy!r}"
        )
    return date(start_year, 4, 1), date(end_year, 3, 31)


@router.get("/{investor_id}/realised", response_model=list[RealisedOut])
def realised(
    investor_id: str, fy: str | None = None, connection: Any = Depends(get_conn)
) -> list[dict[str, Any]]:
    """Realised gains, FIFO-matched, short/long classified. ``fy`` filters to one
    Indian financial year, e.g. ``2025-26``."""
    rows = load_transactions(connection, investor_id=investor_id)
    gains = compute_realised(rows)

    if fy is not None:
        start, end = _financial_year_bounds(fy)
        gains = [g for g in gains if g.sell_date is not None and start <= g.sell_date <= end]

    return [
        {
            "isin": g.isin,
            "sell_date": g.sell_date,
            "quantity": money(g.quantity),
            "proceeds": money(g.proceeds),
            "cost": money(g.cost),
            "gain": money(g.gain),
            "term": str(g.term),
            "holding_days": g.holding_days,
        }
        for g in gains
    ]
