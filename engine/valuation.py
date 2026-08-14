"""Valuation -- docs/ENGINE_SPEC.md section 2.

Where prices meet holdings, and nowhere else. Kept separate from ``compute_holdings``
because prices are a SEPARATE PIPE: client transactions arrive on trade days from files
and email, prices arrive every day from the exchange. Neither blocks the other, and on a
day with no trades the price job still moves the dashboard.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from engine.errors import MissingPriceError
from engine.types import ZERO, Holding


def value_holdings(
    holdings: list[Holding], prices: dict[str, Decimal]
) -> list[Holding]:
    """Attach price-derived fields to holdings.

    ::

        market_value   = quantity * last_price
        unrealised     = market_value - invested
        unrealised_pct = unrealised / invested        (None when invested is 0)
        weight_pct     = market_value / total market_value

    Raises:
        MissingPriceError: naming EVERY unpriced ISIN, not just the first. Someone has to
            go and find those prices; handing them one ISIN per attempt wastes their day.

    A missing price is never substituted with zero. Valuing an unpriced holding at zero
    understates XIRR catastrophically and does it silently, which is the worst
    combination. Two holdings in the golden fixture trade only on BSE, so a price pipe
    that fetched NSE alone would land exactly here.

    Staleness is not checked here: this takes a flat ISIN-to-price mapping with no dates.
    Enforcing MAX_PRICE_STALENESS_DAYS belongs to the price pipe that builds the mapping.
    """
    missing = [h.isin for h in holdings if h.isin not in prices]
    if missing:
        raise MissingPriceError(missing)

    valued = []
    for holding in holdings:
        last_price = prices[holding.isin]
        market_value = holding.quantity * last_price
        unrealised = market_value - holding.invested
        valued.append(
            replace(
                holding,
                last_price=last_price,
                market_value=market_value,
                unrealised=unrealised,
                unrealised_pct=(
                    unrealised / holding.invested if holding.invested != ZERO else None
                ),
            )
        )

    total = sum((h.market_value for h in valued), ZERO)
    if total == ZERO:
        return valued
    return [replace(h, weight_pct=h.market_value / total) for h in valued]


def total_market_value(
    holdings: list[Holding], prices: dict[str, Decimal]
) -> Decimal:
    """Market value of everything held. The terminal cash flow of an XIRR series.

    This is why a tradebook alone cannot produce XIRR: trade files record what already
    happened and have no idea what an unsold position is worth today.
    """
    return sum((h.market_value for h in value_holdings(holdings, prices)), ZERO)
