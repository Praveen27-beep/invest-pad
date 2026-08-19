"""DTOs for GET /investors/{id}/performance, POST /ops/prices/refresh, and
POST /ops/snapshots/run."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class BenchmarkOut(BaseModel):
    name: str
    xirr: float | None = None
    terminal_value: str | None = None


class PerformanceResponse(BaseModel):
    as_of: date
    # Both variants together, always -- CLAUDE.md: reporting one alone leaves a choice
    # about which number flatters the portfolio.
    xirr_all: float | None
    xirr_holdings: float | None
    # Never shown alone either (app.engine.xirr.compute_fy_xirr's docstring) -- sits
    # beside the pair above. No default: the router must always say so explicitly, even
    # when it is null because no 1-April price exists for a held ISIN.
    fy_xirr: float | None
    # Fixed-calendar trailing windows, same resolution as fy_xirr (see
    # app.routers.analytical._window_xirr) -- 1/3/5 calendar years back from as_of, via
    # years_before (app.engine.xirr). Each is independently null: a portfolio with 2
    # years of history gets a null xirr_5y alongside real xirr_1y/xirr_3y values, never
    # all blanked together and never a mislabeled xirr_all standing in for the window.
    xirr_1y: float | None = None
    xirr_3y: float | None = None
    xirr_5y: float | None = None
    # TWRR (app.engine.twrr, ENGINE_SPEC section 5) -- the adviser-skill companion to
    # the fy/1y/3y/5y XIRR windows above, never shown alone. Same fixed-calendar
    # resolution, same independent nullability -- chains the persisted daily snapshot
    # series instead of solving a single money-weighted rate.
    fy_twrr: float | None = None
    twrr_1y: float | None = None
    twrr_3y: float | None = None
    twrr_5y: float | None = None
    # Adviser-onboarding variant: since investor.onboarding_date (docs/DATA_MODEL.md),
    # resolved the same honest way as fy_xirr -- see
    # app.routers.analytical._window_xirr. period_start echoes back the date actually
    # used; both are None together, exactly when no onboarding_date is usable.
    period_xirr: float | None = None
    period_start: date | None = None
    absolute_return: float | None = None
    cagr: float | None = None
    invested: str | None = None
    market_value: str | None = None
    unrealised: str | None = None
    realised_to_date: str | None = None
    benchmark: BenchmarkOut | None = None
    warning: str | None = None


class PriceRefreshResponse(BaseModel):
    prices_stored: int
    missing_isins: list[str]
    price_date: date


class SnapshotOut(BaseModel):
    """One persisted ``portfolio_snapshot`` row -- the shape ``schema/snapshot.schema.json``
    already defines. ``GET /investors/{id}/snapshots`` returns a bare array of these
    (mirrors ``holding.schema.json`` reused as ``holdings``' array items), so no separate
    top-level schema file was added for the range-read response itself."""

    as_of: date
    invested: str
    market_value: str
    unrealised: str | None = None
    realised_to_date: str | None = None


class SkippedSnapshotOut(BaseModel):
    investor_id: str
    advised_only: bool
    as_of: date
    isins: list[str]


class SnapshotRunResponse(BaseModel):
    snapshots_written: int
    price_dates_fetched: int
    skipped_missing_price: list[SkippedSnapshotOut]
