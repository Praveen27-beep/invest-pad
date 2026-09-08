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


def _hold(db, isin: str, on: date, symbol: str = "X") -> None:
    """Put ``isin`` in the ledger from ``on``, so a backfill considers it wanted from
    that date. Uses the ``investor`` fixture's account, created by ``_TEST_ACCOUNT_ID``."""
    import os

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO security (isin, symbol) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (isin, symbol),
        )
        cur.execute(
            """
            INSERT INTO transaction (account_id, isin, txn_date, txn_type, quantity,
                                     price, charges, source, dedupe_key)
            VALUES (%s, %s, %s, 'BUY', 1, 100, 0, 'MANUAL', %s)
            """,
            (os.environ["_TEST_ACCOUNT_ID"], isin, on, f"settled-test-{isin}-{on}"),
        )


def test_stored_dates_are_reported_so_a_backfill_can_resume(db, investor) -> None:
    """A three-year backfill is ~750 requests; one timeout must not mean starting over."""
    _hold(db, BLS, date(2026, 8, 1))
    seed(db, on=date(2026, 8, 10))
    seed(db, on=date(2026, 8, 11))
    settled = dbprices.price_dates_settled(db, date(2026, 8, 1), date(2026, 8, 31))
    assert settled == {date(2026, 8, 10), date(2026, 8, 11)}


# --- the newly-bought-security gap, and why resumability is per (date, security) ------


NEWCO = "INE000X01011"


def test_a_newly_bought_security_reopens_the_dates_it_needs(db, investor) -> None:
    """THE BUG THIS FUNCTION EXISTS TO PREVENT.

    Resumability used to be keyed on the date alone: any date holding ANY price row was
    skipped. That answers "does some security have a price here", and uses it for
    "have we fetched this date for the securities we care about" -- two questions that
    agree only while the ledger never changes.

    Buy something new and every historical date already has prices for the older
    holdings, so every date looks done, so bhavcopy is never re-fetched, so the new
    holding never acquires ANY history. Observed live on this project's own database:
    30 of 46 held securities had no price before the fortnight they were imported in.
    """
    _hold(db, BLS, date(2026, 8, 1))
    seed(db, on=date(2026, 8, 10))
    seed(db, on=date(2026, 8, 11))
    assert dbprices.price_dates_settled(db, date(2026, 8, 1), date(2026, 8, 31)) == {
        date(2026, 8, 10),
        date(2026, 8, 11),
    }

    # Buy something new, dated before those two days.
    _hold(db, NEWCO, date(2026, 8, 5), symbol="NEWCO")

    assert dbprices.price_dates_settled(db, date(2026, 8, 1), date(2026, 8, 31)) == set(), (
        "both dates postdate NEWCO's first transaction and have no price for it, "
        "so a backfill must fetch them again"
    )


def test_a_security_is_not_wanted_before_anybody_owned_it(db, investor) -> None:
    """The clause that stops the fix being worse than the bug.

    Without it, one new holding would re-open the ENTIRE archive -- hundreds of requests
    to establish prices for dates on which nobody held the thing and no snapshot will
    ever ask about it.
    """
    _hold(db, BLS, date(2026, 8, 1))
    seed(db, on=date(2026, 8, 10))
    _hold(db, NEWCO, date(2026, 8, 20), symbol="NEWCO")

    settled = dbprices.price_dates_settled(db, date(2026, 8, 1), date(2026, 8, 31))
    assert date(2026, 8, 10) in settled, "10 Aug predates NEWCO, so NEWCO cannot unsettle it"


def test_a_recorded_absence_settles_a_date_that_will_never_have_a_price(db, investor) -> None:
    """The clause that makes the fix terminate.

    A scrip that legitimately did not trade -- suspended, pre-listing, an illiquid SME
    line -- has no price on that date and never will. Without a way to record "we looked
    and it was not there", that date stays unsettled and is re-fetched on every single
    run, forever.
    """
    _hold(db, BLS, date(2026, 8, 1))
    _hold(db, NEWCO, date(2026, 8, 1), symbol="NEWCO")
    seed(db, on=date(2026, 8, 10))

    assert dbprices.price_dates_settled(db, date(2026, 8, 1), date(2026, 8, 31)) == set()

    assert dbprices.record_absent_prices(db, date(2026, 8, 10), [NEWCO]) == 1

    assert dbprices.price_dates_settled(db, date(2026, 8, 1), date(2026, 8, 31)) == {
        date(2026, 8, 10)
    }


def test_recording_an_absence_twice_is_a_no_op(db, investor) -> None:
    """A re-run must neither fail nor rewrite when it establishes the same absence."""
    _hold(db, NEWCO, date(2026, 8, 1), symbol="NEWCO")
    dbprices.record_absent_prices(db, date(2026, 8, 10), [NEWCO])
    dbprices.record_absent_prices(db, date(2026, 8, 10), [NEWCO])
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM price_absent")
        assert cur.fetchone()[0] == 1


def test_recording_no_absences_touches_nothing(db) -> None:
    assert dbprices.record_absent_prices(db, date(2026, 8, 10), []) == 0


def test_a_range_never_fetched_is_entirely_unsettled(db, investor) -> None:
    """An empty result means "fetch all of it", which is what a first run must do."""
    _hold(db, BLS, date(2024, 1, 1))
    assert dbprices.price_dates_settled(db, date(2024, 1, 1), date(2024, 1, 31)) == set()


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
