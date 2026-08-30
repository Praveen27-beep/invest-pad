"""Snapshots -- docs/ENGINE_SPEC.md section 8."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engine.holdings import compute_holdings
from app.engine.realised import compute_realised
from app.engine.types import ZERO, Snapshot, Transaction
from app.engine.valuation import value_holdings


def compute_snapshot(
    transactions: list[Transaction],
    prices: dict[str, Decimal],
    on_date: date,
) -> Snapshot:
    """Portfolio totals as at ``on_date``.

    Same functions as the live view, a historical ``as_of``, and historical prices.
    Note ``on_date`` is a parameter and not a clock read: the engine must never call
    ``date.today()``, because that makes tests non-deterministic and historical replay
    impossible.

    Persisting one of these per day is what later unlocks the portfolio-value chart and
    TWRR. They remain a cache of a derivation, always recomputable from the ledger --
    which is the property that makes backfilling one safe.

    Raises:
        MissingPriceError: a held position has no price on ``on_date``. Backfilling a
            historical snapshot needs historical prices for every ISIN held THEN, not
            merely the ones held now.
    """
    holdings = value_holdings(compute_holdings(transactions, on_date), prices)

    invested = sum((h.invested for h in holdings), ZERO)
    market_value = sum((h.market_value for h in holdings), ZERO)
    realised_to_date = sum((r.gain for r in compute_realised(transactions, on_date)), ZERO)

    return Snapshot(
        as_of=on_date,
        invested=invested,
        market_value=market_value,
        unrealised=market_value - invested,
        realised_to_date=realised_to_date,
    )
