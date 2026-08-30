"""Price persistence and the staleness rule, against a real cluster."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.db import prices as dbprices
from app.engine.holdings import MAX_PRICE_STALENESS_DAYS
from app.prices.pipe import fetch_day

from tests.test_prices import HELD, NSE_ONLY, PRICE_DATE, both_sources

pytestmark = pytest.mark.db

BLS = "INE153T01027"


def seed(db, isin=BLS, on=None, close="100", source="NSE_BHAVCOPY"):
    from app.prices.pipe import MergedPrice

    with db.cursor() as cur:
        cur.execute("INSERT INTO security (isin) VALUES (%s) ON CONFLICT DO NOTHING", (isin,))
    return dbprices.upsert_prices(
        db,
        [MergedPrice(isin=isin, price_date=on or PRICE_DATE, close=Decimal(close), source=source)],
    )


def test_upsert_stores_a_price(db) -> None:
    assert seed(db) == 1
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE) == {BLS: Decimal("100")}


def test_upsert_is_idempotent(db) -> None:
    """Re-running a day must change nothing."""
    seed(db)
    seed(db)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM price")
        assert cur.fetchone()[0] == 1


def test_a_republished_bhavcopy_corrects_the_price(db) -> None:
    """Exchanges do republish after a data error, and the later file is the better one."""
    seed(db, close="100")
    seed(db, close="105")
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE) == {BLS: Decimal("105")}


def test_the_most_recent_price_wins(db) -> None:
    seed(db, on=PRICE_DATE - timedelta(days=2), close="90")
    seed(db, on=PRICE_DATE, close="100")
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE) == {BLS: Decimal("100")}


def test_a_future_price_is_not_used(db) -> None:
    """Historical replay must value a portfolio as it stood, not as it turned out."""
    seed(db, on=PRICE_DATE, close="100")
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE - timedelta(days=1)) == {}


# --- staleness -----------------------------------------------------------------


def test_a_price_inside_the_window_is_used(db) -> None:
    seed(db, on=PRICE_DATE - timedelta(days=MAX_PRICE_STALENESS_DAYS), close="90")
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE) == {BLS: Decimal("90")}


def test_a_stale_price_is_omitted_rather_than_served(db) -> None:
    """A stale price does not fail. It produces a confidently wrong market value.

    Omitting it instead surfaces as MissingPriceError naming the ISIN -- a visible,
    fixable problem rather than an invisible wrong one.
    """
    seed(db, on=PRICE_DATE - timedelta(days=MAX_PRICE_STALENESS_DAYS + 1), close="90")
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE) == {}
    assert dbprices.missing_prices(db, [BLS], PRICE_DATE) == [BLS]


def test_missing_prices_names_the_isins(db) -> None:
    """ "Cannot value your portfolio" is unactionable. Naming the security is not."""
    seed(db)
    missing = dbprices.missing_prices(db, [BLS, NSE_ONLY], PRICE_DATE)
    assert missing == [NSE_ONLY]


def test_the_staleness_window_is_configurable(db) -> None:
    seed(db, on=PRICE_DATE - timedelta(days=10), close="90")
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE) == {}
    assert dbprices.latest_prices(db, [BLS], PRICE_DATE, max_staleness_days=30)


# --- the gate, end to end through the database ---------------------------------


def test_a_full_days_prices_land_and_cover_every_holding(db) -> None:
    """Fetch both exchanges, store, and read back a complete valuation set."""
    result = fetch_day(PRICE_DATE, sources=both_sources())
    with db.cursor() as cur:
        for price in result.prices:
            cur.execute(
                "INSERT INTO security (isin) VALUES (%s) ON CONFLICT DO NOTHING",
                (price.isin,),
            )
    stored = dbprices.upsert_prices(db, result.prices)
    assert stored == len(result.prices)

    held = sorted(HELD)
    assert dbprices.missing_prices(db, held, PRICE_DATE) == []
    assert len(dbprices.latest_prices(db, held, PRICE_DATE)) == len(held)


def test_valuation_runs_off_stored_prices(db, investor) -> None:
    """End to end: bhavcopy -> database -> engine valuation. No layer knows the others."""
    from app.engine.types import Holding
    from app.engine.valuation import value_holdings

    result = fetch_day(PRICE_DATE, sources=both_sources())
    with db.cursor() as cur:
        cur.execute("INSERT INTO security (isin) VALUES (%s) ON CONFLICT DO NOTHING", (BLS,))
    dbprices.upsert_prices(db, [p for p in result.prices if p.isin == BLS])

    prices = dbprices.latest_prices(db, [BLS], PRICE_DATE)
    holding = Holding(
        isin=BLS,
        quantity=Decimal("795"),
        avg_cost=Decimal("268.9685"),
        invested=Decimal("213829.96"),
    )
    (valued,) = value_holdings([holding], prices)
    assert valued.market_value == Decimal("795") * prices[BLS]


# --- backfill support ----------------------------------------------------------


def test_stored_dates_are_reported_so_a_backfill_can_resume(db) -> None:
    """A three-year backfill is ~750 requests; one timeout must not mean starting over."""
    seed(db, on=date(2026, 8, 10))
    seed(db, on=date(2026, 8, 11))
    present = dbprices.price_dates_present(db, date(2026, 8, 1), date(2026, 8, 31))
    assert present == {date(2026, 8, 10), date(2026, 8, 11)}


def test_held_isins_covers_everything_ever_traded(db, investor) -> None:
    """Not only current holdings: a historical snapshot needs prices for closed positions."""
    import os

    from app.db import repository
    from app.engine.types import Source, Transaction, TxnType

    with db.cursor() as cur:
        cur.execute("INSERT INTO security (isin) VALUES (%s) ON CONFLICT DO NOTHING", (BLS,))
    repository.save_transactions(
        db,
        [
            Transaction(
                isin=BLS,
                txn_date=date(2024, 1, 10),
                txn_type=TxnType.BUY,
                quantity=Decimal("10"),
                price=Decimal("100"),
                account_id=os.environ["_TEST_ACCOUNT_ID"],
                source=Source.MANUAL,
                source_ref="A",
            ),
            Transaction(
                isin=BLS,
                txn_date=date(2024, 6, 10),
                txn_type=TxnType.SELL,
                quantity=Decimal("10"),
                price=Decimal("120"),
                account_id=os.environ["_TEST_ACCOUNT_ID"],
                source=Source.MANUAL,
                source_ref="B",
            ),
        ],
    )
    assert dbprices.held_isins(db) == [BLS], "closed position still needs historical prices"


def test_fixtures_are_real_files(dummy=None) -> None:
    """Trimmed, not synthesised. Real headers and real closes from 2026-08-12."""
    base = Path(__file__).parent.parent / "fixtures" / "bhavcopy"
    for name in ("nse_20260812.csv", "bse_20260812.csv"):
        header = (base / name).read_text().splitlines()[0]
        assert header.startswith("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN")
