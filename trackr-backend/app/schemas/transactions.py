"""DTOs for GET /investors/{id}/transactions, /lots, /realised, /dividends, and
POST /investors/{id}/transactions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.engine.types import Source, TxnType


class TransactionIn(BaseModel):
    """One row of the POST /investors/{id}/transactions request body.

    Mirrors the writable fields of ``schema/transaction.schema.json``. ``txn_type`` and
    ``source`` reuse the engine's own enums rather than a second hand-typed list, so this
    can never drift from ``docs/DATA_MODEL.md`` -- an unlisted value is a validation
    error (422), never silently accepted. ``id``, ``dedupe_key`` and ``created_at`` are
    deliberately absent: the first and third are server-assigned on insert, and the key
    is always derived by ``app.engine.dedupe.make_dedupe_key`` rather than accepted from
    a caller who has no way to compute it correctly.

    ``account_id`` is required here even though the shared schema leaves it optional --
    that optionality is for pure-engine fixtures; ``transaction.account_id`` is
    ``NOT NULL`` in the database, and failing that at the request boundary with a 422
    beats a raw integrity-constraint error surfacing as a 500.
    """

    account_id: str
    isin: str = Field(pattern=r"^IN[A-Z0-9]{10}$")
    txn_date: date
    txn_type: TxnType
    quantity: Decimal = Field(ge=0)
    price: Decimal
    charges: Decimal = Decimal("0")
    stt: Decimal = Decimal("0")
    dividend_amount: Decimal = Decimal("0")
    cost_transfer: Decimal = Decimal("0")
    source: Source | None = None
    source_ref: str | None = None
    raw_payload: dict[str, Any] | None = None


class ImportSummaryOut(BaseModel):
    """Mirrors ``engine.types.ImportSummary`` -- the response shape for
    POST /investors/{id}/transactions per contracts/openapi.yaml."""

    inserted: int
    skipped_duplicates: int
    rejected: list[dict[str, Any]]


class TransactionOut(BaseModel):
    id: str | None
    account_id: str | None
    isin: str
    txn_date: date
    txn_type: str
    quantity: str
    price: str
    charges: str
    stt: str
    dividend_amount: str
    cost_transfer: str
    source: str | None
    source_ref: str | None
    created_at: datetime | None = None


class LotOut(BaseModel):
    isin: str
    open_date: date
    quantity_open: str
    cost_per_unit: str


class RealisedOut(BaseModel):
    isin: str | None
    sell_date: date | None
    quantity: str
    proceeds: str
    cost: str
    gain: str
    term: str
    holding_days: int | None


class DividendYearOut(BaseModel):
    fy: str
    amount: str


class DividendSummaryOut(BaseModel):
    isin: str
    total: str
    by_year: list[DividendYearOut]
