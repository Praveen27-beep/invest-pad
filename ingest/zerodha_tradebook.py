"""Zerodha Console tradebook CSV adapter.

Console caps each download at 365 days, so a full history is several files that a client
sends together and which may overlap. Merging and deduplicating them is the normal case,
not an edge case.

WHY ``trade_id`` IS LOAD-BEARING. Measured against the four real exports in this project:
``trade_id`` is unique across all 259 rows, but ``order_id`` is unique across only 125 --
one order fills as several trades. More pointedly, 12 groups of rows are identical on
(isin, date, type, quantity, price), covering 16 trades. A dedupe key without ``trade_id``
would silently destroy those 16 and look like it had worked. So ``source_ref`` carries
``trade_id`` and nothing else.

Real example: INE142Q01026 on 2024-09-10, three separate sells of 2 @ 484.100006.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from engine.types import Source, Transaction, TxnType
from ingest.base import CONFIDENCE_CERTAIN, ParseResult, Rejection, StagedRow

ISIN_PATTERN = re.compile(r"^IN[A-Z0-9]{10}$")

TRADE_TYPES = {"buy": TxnType.BUY, "sell": TxnType.SELL}

REQUIRED_COLUMNS = {"isin", "trade_date", "trade_type", "quantity", "price", "trade_id"}

#: Phase 1 is equities. Anything else is rejected rather than quietly mis-modelled: a
#: derivative in an equity ledger produces a cost basis that is wrong in a way nobody
#: notices until a tax return.
SUPPORTED_SEGMENT = "EQ"


class ZerodhaTradebookAdapter:
    name = "zerodha_tradebook"

    def parse(self, content: bytes, account_id: str, filename: str = "") -> ParseResult:
        rows: list[StagedRow] = []
        rejections: list[Rejection] = []
        notes: list[str] = [
            "Tradebook exports carry no charges; brokerage, STT, GST and stamp duty live "
            "on the contract note. charges is 0 on every row here - that is absence of "
            "data, not evidence the trades were free."
        ]

        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        if reader.fieldnames is None:
            return ParseResult(rejections=[Rejection(0, "file is empty")], notes=notes)

        missing = REQUIRED_COLUMNS - {(f or "").strip() for f in reader.fieldnames}
        if missing:
            return ParseResult(
                rejections=[
                    Rejection(0, f"not a Zerodha tradebook: missing {sorted(missing)}")
                ],
                notes=notes,
            )

        # Row 1 is the header, so data starts at 2 -- which is what a person sees when they
        # open the file to find the row a rejection names.
        for row_number, raw in enumerate(reader, start=2):
            parsed = self._parse_row(raw, account_id, row_number)
            if isinstance(parsed, Rejection):
                rejections.append(parsed)
            else:
                rows.append(parsed)

        return ParseResult(rows=rows, rejections=rejections, notes=notes)

    def _parse_row(
        self, raw: dict[str, Any], account_id: str, row_number: int
    ) -> StagedRow | Rejection:
        def reject(reason: str) -> Rejection:
            return Rejection(row_number, reason, {k: v for k, v in raw.items() if v})

        segment = (raw.get("segment") or "").strip().upper()
        if segment and segment != SUPPORTED_SEGMENT:
            return reject(f"segment {segment!r} is not supported in Phase 1 (equities only)")

        isin = (raw.get("isin") or "").strip().upper()
        if not ISIN_PATTERN.match(isin):
            return reject(f"not a valid ISIN: {isin!r}")

        trade_type = (raw.get("trade_type") or "").strip().lower()
        if trade_type not in TRADE_TYPES:
            return reject(f"unknown trade_type {trade_type!r}")

        try:
            txn_date = date.fromisoformat((raw.get("trade_date") or "").strip())
        except ValueError:
            return reject(f"unparseable trade_date {raw.get('trade_date')!r}")

        try:
            # Decimal(str(...)) throughout. Routing a price through a binary numeric type
            # here would undo the precision discipline the whole engine is built on.
            quantity = Decimal(str(raw.get("quantity") or "").strip())
            price = Decimal(str(raw.get("price") or "").strip())
        except (InvalidOperation, ValueError):
            return reject(
                f"unparseable quantity/price: {raw.get('quantity')!r}/{raw.get('price')!r}"
            )

        if quantity <= 0:
            return reject(f"quantity must be positive, got {quantity}")
        if price < 0:
            return reject(f"price cannot be negative, got {price}")

        trade_id = (raw.get("trade_id") or "").strip()
        if not trade_id:
            return reject("missing trade_id, which is the only stable identity a "
                          "tradebook row has")

        return StagedRow(
            row_number=row_number,
            transaction=Transaction(
                isin=isin,
                txn_date=txn_date,
                txn_type=TRADE_TYPES[trade_type],
                quantity=quantity,
                price=price,
                charges=Decimal("0"),
                account_id=account_id,
                source=Source.TRADEBOOK,
                source_ref=trade_id,
            ),
            # Nothing here is inferred. Every field was read from a structured column.
            confidence=CONFIDENCE_CERTAIN,
            raw={k: v for k, v in raw.items() if v},
        )
