"""DTOs for GET /investors/{id}/holdings and GET /investors/{id}/summary."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class HoldingOut(BaseModel):
    isin: str
    symbol: str | None
    name: str | None
    quantity: str
    avg_cost: str
    invested: str
    last_price: str | None = None
    market_value: str | None = None
    unrealised: str | None = None
    unrealised_pct: float | None = None
    weight_pct: float | None = None
    cagr: float | None = None
    cost_estimated: bool = False


class TotalsOut(BaseModel):
    invested: str | None
    market_value: str | None
    unrealised: str | None
    unrealised_pct: float | None = None
    cost_estimated: bool = False


class UnpricedHoldingOut(BaseModel):
    isin: str
    symbol: str | None
    name: str | None
    invested: str


class UnpricedOut(BaseModel):
    count: int
    invested: str | None
    holdings: list[UnpricedHoldingOut]


class AllocationGroupOut(BaseModel):
    asset_class: str
    label: str
    market_value: str | None
    weight_pct: float | None = None
    children: list[HoldingOut]


class SectorAllocationGroupOut(BaseModel):
    sector: str | None
    label: str
    market_value: str | None
    weight_pct: float | None = None
    children: list[HoldingOut]


class MarketCapAllocationGroupOut(BaseModel):
    market_cap_bucket: str | None
    label: str
    market_value: str | None
    weight_pct: float | None = None
    children: list[HoldingOut]


class HoldingsResponse(BaseModel):
    as_of: date
    holdings: list[HoldingOut]
    totals: TotalsOut
    unpriced: UnpricedOut


class SummaryResponse(BaseModel):
    as_of: date
    invested: str | None
    market_value: str | None
    unrealised: str | None
    unrealised_pct: float | None = None
    cost_estimated: bool = False
    unpriced: UnpricedOut
    allocation: list[AllocationGroupOut]
    allocation_by_sector: list[SectorAllocationGroupOut]
    allocation_by_market_cap: list[MarketCapAllocationGroupOut]
