"""GET /investors/{id}/summary's allocation grouping -- response shaping, no database
needed. Same split ``tests/test_analytical_router.py`` uses for ``_snapshot_row`` etc.:
build the exact ``book`` dict ``_portfolio`` produces, feed it straight to the private
shaping functions.

``_allocation`` (by asset_class) and ``_sector_allocation`` (by security.sector) share
one mechanism, ``_group_holdings`` -- these tests pin that the weight_pct arithmetic
(ENGINE_SPEC section 2) agrees between the two, and that an unclassified sector groups
under its own honest entry rather than vanishing or crashing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.engine.types import Holding
from app.routers.holdings import (
    UNCLASSIFIED_SECTOR_LABEL,
    _allocation,
    _sector_allocation,
)


def a_holding(isin: str, market_value: str, invested: str = "1000") -> Holding:
    return Holding(
        isin=isin,
        quantity=Decimal("10"),
        avg_cost=Decimal(invested) / Decimal("10"),
        invested=Decimal(invested),
        market_value=Decimal(market_value),
        unrealised=Decimal(market_value) - Decimal(invested),
        unrealised_pct=None,
        weight_pct=None,
    )


def a_book(holdings: list[Holding], meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "valued": holdings,
        "meta": meta,
        "market_value": sum((h.market_value for h in holdings), Decimal("0")),
    }


META = {
    "INE1": {
        "symbol": "AAA", "name": "Alpha Ltd", "asset_class": "EQ", "sector": "Financial Services"
    },
    "INE2": {
        "symbol": "BBB", "name": "Beta Ltd", "asset_class": "EQ", "sector": "Information Technology"
    },
    "INE3": {"symbol": "CCC", "name": "Gamma Ltd", "asset_class": "EQ", "sector": None},
}


def test_asset_class_allocation_unchanged_single_eq_group() -> None:
    """Regression pin: Phase 1 is EQ-only, so asset_class grouping still yields one
    group covering the whole book -- this is the behaviour the sector split must not
    disturb."""
    holdings = [a_holding("INE1", "6000"), a_holding("INE2", "4000")]
    book = a_book(holdings, META)

    groups = _allocation(book)

    assert len(groups) == 1
    assert groups[0]["asset_class"] == "EQ"
    assert Decimal(groups[0]["market_value"]) == Decimal("10000")
    assert groups[0]["weight_pct"] == 1.0


def test_sector_allocation_groups_and_weights_correctly() -> None:
    holdings = [a_holding("INE1", "6000"), a_holding("INE2", "4000")]
    book = a_book(holdings, META)

    groups = _sector_allocation(book)

    by_sector = {g["sector"]: g for g in groups}
    assert set(by_sector) == {"Financial Services", "Information Technology"}
    assert by_sector["Financial Services"]["weight_pct"] == 0.6
    assert by_sector["Information Technology"]["weight_pct"] == 0.4
    # Same market_value/Sigma(market_value) formula as asset_class grouping -- not a
    # separately reimplemented calculation.
    assert Decimal(by_sector["Financial Services"]["market_value"]) == Decimal("6000")


def test_sector_allocation_surfaces_null_sector_as_unclassified() -> None:
    holdings = [a_holding("INE1", "6000"), a_holding("INE3", "4000")]
    book = a_book(holdings, META)

    groups = _sector_allocation(book)

    by_sector = {g["sector"]: g for g in groups}
    assert None in by_sector, "the null-sector holding must appear, not vanish"
    unclassified = by_sector[None]
    assert unclassified["label"] == UNCLASSIFIED_SECTOR_LABEL
    assert unclassified["weight_pct"] == 0.4
    assert [c["isin"] for c in unclassified["children"]] == ["INE3"]
    # It must not have been folded into some other bucket.
    assert len(groups) == 2


def test_sector_allocation_does_not_merge_unclassified_into_a_real_sector() -> None:
    holdings = [a_holding("INE1", "5000"), a_holding("INE3", "5000")]
    book = a_book(holdings, META)

    groups = _sector_allocation(book)

    labels = {g["label"] for g in groups}
    assert "Financial Services" in labels
    assert UNCLASSIFIED_SECTOR_LABEL in labels
    assert len(groups) == 2
