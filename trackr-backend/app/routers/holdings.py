"""GET /investors/{id}/holdings, GET /investors/{id}/summary.

The shaping logic (``_portfolio``, ``_row``, ``_totals``, ``_unpriced``, ``_allocation``)
is moved verbatim from ``api/main.py`` -- see docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md
section 1. There is no calculation here and there must never be one: a number computed
in this file could not be reproduced by replaying the ledger, which is CLAUDE.md's one
architectural rule.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query

from app import securities
from app.database import get_conn, money, rate
from app.db.prices import latest_prices
from app.db.repository import load_transactions
from app.engine.holdings import compute_holdings
from app.engine.types import ZERO, Holding
from app.engine.valuation import value_holdings
from app.schemas.holdings import HoldingsResponse, SummaryResponse

router = APIRouter(prefix="/investors", tags=["derived"])


def _as_of(value: date | None) -> date:
    """Defaults to today. The parameter exists because the engine takes one and
    historical replay is the same call with an earlier date."""
    return value or date.today()


def _portfolio(
    connection: Any, investor_id: str, as_of: date, advised_only: bool = False
) -> dict[str, Any]:
    """Holdings, valued where a price exists, with the unpriced ones kept separate.

    THE PARTITION IS THE POINT. ``value_holdings`` is all-or-nothing: one unpriced ISIN
    raises ``MissingPriceError`` naming every one of them, because CLAUDE.md rule 4
    forbids substituting a number for a price nobody has. That is right for the engine
    and wrong for a dashboard, which would go blank over one delisted scrip.

    So the split happens here instead. Priced holdings are valued normally. Unpriced ones
    are returned by name with their invested cost and are EXCLUDED from every total --
    they are not valued at their cost, which would silently report a P&L of zero on them.

    weight_pct therefore sums to 1 across the priced holdings, not across everything held.

    ``advised_only`` restricts the ledger to accounts flagged ``is_advised`` (docs/
    DATA_MODEL.md, contracts/openapi.yaml) -- so a SEBI-registered adviser can report on
    the mandated account only.
    """
    transactions = load_transactions(
        connection, investor_id=investor_id, advised_only=advised_only
    )
    holdings = compute_holdings(transactions, as_of=as_of)

    prices = latest_prices(connection, [h.isin for h in holdings], as_of)
    priced = [h for h in holdings if h.isin in prices]
    unpriced = [h for h in holdings if h.isin not in prices]

    valued = value_holdings(priced, prices, as_of=as_of) if priced else []
    meta = securities.lookup(connection, [h.isin for h in holdings])

    return {
        "as_of": as_of,
        "valued": valued,
        "unpriced": unpriced,
        "meta": meta,
        "invested": sum((h.invested for h in valued), ZERO),
        "market_value": sum((h.market_value for h in valued), ZERO),
    }


def _row(book: dict[str, Any], holding: Holding) -> dict[str, Any]:
    """One holding as JSON, with its security metadata joined on."""
    described = securities.describe(book["meta"], holding.isin)
    return {
        "isin": holding.isin,
        "symbol": described["symbol"],
        "name": securities.display_name(book["meta"], holding.isin),
        "quantity": money(holding.quantity),
        "avg_cost": money(holding.avg_cost),
        "invested": money(holding.invested),
        "last_price": money(holding.last_price),
        "market_value": money(holding.market_value),
        "unrealised": money(holding.unrealised),
        "unrealised_pct": rate(holding.unrealised_pct),
        "weight_pct": rate(holding.weight_pct),
        "cagr": rate(holding.cagr),
        "cost_estimated": holding.cost_estimated,
    }


def _totals(book: dict[str, Any]) -> dict[str, Any]:
    """Portfolio totals over the PRICED holdings only."""
    invested, market_value = book["invested"], book["market_value"]
    unrealised = market_value - invested
    return {
        "invested": money(invested),
        "market_value": money(market_value),
        "unrealised": money(unrealised),
        "unrealised_pct": rate(unrealised / invested) if invested != ZERO else None,
        "cost_estimated": any(h.cost_estimated for h in book["valued"]),
    }


def _unpriced(book: dict[str, Any]) -> dict[str, Any]:
    """The excluded holdings, named. "Cannot value your portfolio" is unactionable;
    "no price for KDL-SM since 6 August" is something a person can go and fix."""
    return {
        "count": len(book["unpriced"]),
        "invested": money(sum((h.invested for h in book["unpriced"]), ZERO)),
        "holdings": [
            {
                "isin": h.isin,
                "symbol": securities.describe(book["meta"], h.isin)["symbol"],
                "name": securities.display_name(book["meta"], h.isin),
                "invested": money(h.invested),
            }
            for h in book["unpriced"]
        ],
    }


def _allocation(book: dict[str, Any]) -> list[dict[str, Any]]:
    """Market value grouped by asset class, each group carrying its own holdings."""
    groups: dict[str, list[Holding]] = {}
    for holding in book["valued"]:
        asset_class = securities.describe(book["meta"], holding.isin)["asset_class"]
        groups.setdefault(asset_class, []).append(holding)

    total = book["market_value"]
    out = []
    for asset_class, holdings in groups.items():
        group_value = sum((h.market_value for h in holdings), ZERO)
        out.append(
            {
                "asset_class": asset_class,
                "label": securities.label(asset_class),
                "market_value": money(group_value),
                "weight_pct": rate(group_value / total) if total != ZERO else None,
                "children": sorted(
                    (_row(book, h) for h in holdings),
                    key=lambda r: Decimal(r["market_value"]),
                    reverse=True,
                ),
            }
        )
    return sorted(out, key=lambda g: Decimal(g["market_value"]), reverse=True)


@router.get("/{investor_id}/summary", response_model=SummaryResponse)
def summary(
    investor_id: str, as_of: date | None = None, connection: Any = Depends(get_conn)
) -> dict[str, Any]:
    book = _portfolio(connection, investor_id, _as_of(as_of))
    return {
        "as_of": book["as_of"],
        **_totals(book),
        "unpriced": _unpriced(book),
        "allocation": _allocation(book),
    }


@router.get("/{investor_id}/holdings", response_model=HoldingsResponse)
def holdings(
    investor_id: str,
    as_of: date | None = None,
    asset_class: str | None = Query(default=None),
    advised_only: bool = False,
    connection: Any = Depends(get_conn),
) -> dict[str, Any]:
    """Implements contracts/openapi.yaml's ``/investors/{id}/holdings``, plus an
    ``asset_class`` filter so the equities screen asks for equities server-side.

    ``advised_only`` restricts to accounts flagged ``is_advised`` -- per
    contracts/openapi.yaml and docs/DATA_MODEL.md's account table."""
    book = _portfolio(connection, investor_id, _as_of(as_of), advised_only=advised_only)
    rows = [
        h
        for h in book["valued"]
        if asset_class is None
        or securities.describe(book["meta"], h.isin)["asset_class"] == asset_class
    ]
    subtotal_invested = sum((h.invested for h in rows), ZERO)
    subtotal_value = sum((h.market_value for h in rows), ZERO)
    unrealised = subtotal_value - subtotal_invested
    return {
        "as_of": book["as_of"],
        "holdings": sorted(
            (_row(book, h) for h in rows),
            key=lambda r: Decimal(r["market_value"]),
            reverse=True,
        ),
        "totals": {
            "invested": money(subtotal_invested),
            "market_value": money(subtotal_value),
            "unrealised": money(unrealised),
            "unrealised_pct": (
                rate(unrealised / subtotal_invested) if subtotal_invested != ZERO else None
            ),
        },
        "unpriced": _unpriced(book),
    }
