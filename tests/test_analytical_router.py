"""GET /investors/{id}/snapshots -- response shaping, no database needed.

``app.routers.analytical._snapshot_row`` is the exact boundary the response is shaped
through, and ``app.schemas.analytical.SnapshotOut`` is the exact boundary FastAPI
validates it against -- the same split ``tests/test_reconcile_router.py`` uses for
``_discrepancy_row``/``DeclaredHoldingIn``. The 400-on-inverted-range check is router
logic, not a database concern, so it belongs here too.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.types import Snapshot, Transaction, TxnType
from app.prices.index_sources import IndexSourceFetchFailed
from app.routers.analytical import (
    _benchmark,
    _snapshot_row,
    _window_twrr,
    contribution,
    list_snapshots,
)
from app.schemas.analytical import SnapshotOut
from fastapi import HTTPException
from pydantic import ValidationError

AS_OF = date(2024, 9, 30)


def a_snapshot(
    as_of: date = AS_OF,
    invested: str = "1000",
    market_value: str = "1200",
    unrealised: str = "200",
    realised_to_date: str = "0",
) -> Snapshot:
    return Snapshot(
        as_of=as_of,
        invested=Decimal(invested),
        market_value=Decimal(market_value),
        unrealised=Decimal(unrealised),
        realised_to_date=Decimal(realised_to_date),
    )


# --- response shaping ------------------------------------------------------------------


def test_snapshot_row_shapes_money_as_strings_not_floats() -> None:
    """CLAUDE.md rule 1: money is Decimal end to end; only crosses the wire as a string,
    same convention as holdings.py's _row and reconcile.py's _discrepancy_row."""
    row = _snapshot_row(a_snapshot())

    assert row["as_of"] == AS_OF
    assert row["invested"] == "1000"
    assert row["market_value"] == "1200"
    assert row["unrealised"] == "200"
    assert row["realised_to_date"] == "0"
    assert isinstance(row["invested"], str)
    assert isinstance(row["market_value"], str)


def test_snapshot_row_round_trips_through_snapshot_out() -> None:
    """The shaped row is exactly what SnapshotOut, the endpoint's response_model item
    type, accepts -- proving the router's shaping and the schema agree."""
    row = _snapshot_row(a_snapshot())
    out = SnapshotOut(**row)

    assert out.as_of == AS_OF
    assert out.market_value == "1200"


# --- SnapshotOut boundary ---------------------------------------------------------------


def test_snapshot_out_requires_as_of_invested_and_market_value() -> None:
    """Mirrors schema/snapshot.schema.json's required list exactly -- unrealised and
    realised_to_date stay optional there too."""
    with pytest.raises(ValidationError):
        SnapshotOut(invested="1000", market_value="1200")  # missing as_of


def test_snapshot_out_unrealised_and_realised_to_date_are_optional() -> None:
    out = SnapshotOut(as_of=AS_OF, invested="1000", market_value="1200")
    assert out.unrealised is None
    assert out.realised_to_date is None


# --- range validation --------------------------------------------------------------------


def test_list_snapshots_rejects_start_after_end_before_touching_the_database() -> None:
    """The 400 must fire from the query params alone -- checked before ``connection`` is
    ever used, so passing None here still proves the guard, no Postgres required."""
    with pytest.raises(HTTPException) as exc_info:
        list_snapshots(
            investor_id="does-not-matter",
            start=date(2024, 8, 10),
            end=date(2024, 8, 1),
            advised_only=False,
            connection=None,
        )
    assert exc_info.value.status_code == 400


def test_contribution_rejects_period_start_after_as_of_before_touching_the_database() -> None:
    """Mirrors list_snapshots' guard above (ENGINE_SPEC section 10): the 400 fires from
    period_start/as_of alone, before load_transactions ever reaches ``connection``, so
    None still proves it with no Postgres required."""
    with pytest.raises(HTTPException) as exc_info:
        contribution(
            investor_id="does-not-matter",
            period_start=date(2024, 8, 10),
            as_of=date(2024, 8, 1),
            advised_only=False,
            connection=None,
        )
    assert exc_info.value.status_code == 400


# --- TWRR windows (ENGINE_SPEC.md section 5) ---------------------------------------------


def test_window_twrr_blanks_when_window_predates_earliest_transaction() -> None:
    """Same history guard _window_xirr uses (step 1): a window that predates the
    investor's earliest transaction must blank to None before ever reaching
    connection -- checkable with connection=None, no Postgres required."""
    result = _window_twrr(
        connection=None,
        investor_id="does-not-matter",
        transactions=[],
        target_start=date(2024, 1, 1),
        earliest_txn=date(2024, 6, 1),
        as_of=date(2025, 1, 1),
        advised_only=False,
        closing_snapshot=Snapshot(
            as_of=date(2025, 1, 1), invested=Decimal("0"), market_value=Decimal("0")
        ),
    )
    assert result is None


def test_window_twrr_blanks_when_there_are_no_transactions_at_all() -> None:
    """earliest_txn=None (an empty ledger) must blank the same way, mirroring
    _window_xirr's identical guard -- also checkable with no database."""
    result = _window_twrr(
        connection=None,
        investor_id="does-not-matter",
        transactions=[],
        target_start=date(2024, 1, 1),
        earliest_txn=None,
        as_of=date(2025, 1, 1),
        advised_only=False,
        closing_snapshot=Snapshot(
            as_of=date(2025, 1, 1), invested=Decimal("0"), market_value=Decimal("0")
        ),
    )
    assert result is None


# --- benchmark (ENGINE_SPEC.md section 6) ------------------------------------------------


def test_sensex_tri_is_rejected_before_touching_the_database() -> None:
    """SENSEX_TRI is a valid contract enum value with no reliable free, machine-
    fetchable source behind it (confirmed in Plan Mode). It must 400 explicitly rather
    than silently return null or a guessed number -- and the 400 must fire from the
    requested name alone, exactly like list_snapshots' start>end check, so this is
    checkable with no database at all."""
    with pytest.raises(HTTPException) as exc_info:
        _benchmark(
            request=None,
            connection=None,
            investor_id="does-not-matter",
            transactions=[],
            name="SENSEX_TRI",
            as_of=date(2025, 1, 10),
        )
    assert exc_info.value.status_code == 400
    assert "SENSEX_TRI" in exc_info.value.detail


def test_no_transactions_produces_a_null_valued_benchmark_without_touching_the_database() -> None:
    """An investor with an empty ledger has nothing to replicate -- required_index_dates
    returns no dates, so get_index_levels/fetch_and_store are never reached (checkable
    with connection=None). Distinct from the MissingIndexLevelError case: the caller
    DID ask for a benchmark and gets one back, just with null xirr/terminal_value,
    rather than the whole field disappearing the way a genuine data gap makes it."""
    result = _benchmark(
        request=None,
        connection=None,
        investor_id="does-not-matter",
        transactions=[],
        name="NIFTY50_TRI",
        as_of=date(2025, 1, 10),
    )
    assert result == {"name": "NIFTY50_TRI", "xirr": None, "terminal_value": None}


def test_a_failed_live_fetch_degrades_to_null_rather_than_500ing_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An optional field's external dependency (niftyindices.com) hiccupping -- network
    error, or its undocumented response shape changing -- must never fail the whole
    /performance request. Mirrors _fy_xirr/_period_xirr's MissingPriceError handling,
    just for a fetch failure instead of a data gap."""
    import app.routers.analytical as analytical_router

    transactions = [
        Transaction(
            isin="INE153T01027",
            txn_date=date(2024, 1, 10),
            txn_type=TxnType.BUY,
            quantity=Decimal("100"),
            price=Decimal("200"),
        )
    ]

    monkeypatch.setattr(analytical_router, "get_index_levels", lambda *a, **k: {})

    def _raise(*args: object, **kwargs: object) -> None:
        raise IndexSourceFetchFailed("NIFTY 50 TRI: simulated network failure")

    monkeypatch.setattr(analytical_router, "fetch_and_store", _raise)

    result = _benchmark(
        request=None,
        connection=object(),  # never touched: both DB calls above are monkeypatched
        investor_id="does-not-matter",
        transactions=transactions,
        name="NIFTY50_TRI",
        as_of=date(2025, 1, 10),
    )
    assert result is None
