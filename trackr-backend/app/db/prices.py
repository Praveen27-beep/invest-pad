"""Price persistence, and the staleness rule.

Staleness is enforced HERE and not in the engine, deliberately. ``engine/valuation.py``
takes a flat ISIN-to-price mapping with no dates in it and therefore cannot know whether a
price is current. This layer builds that mapping, so this is the only place that can refuse
to put a stale price into it.

Refusing matters: a stale price does not fail, it produces a confidently wrong market value
and a confidently wrong XIRR. Omitting it instead surfaces as ``MissingPriceError`` naming
the ISIN, which is the failure the whole system is designed to make loud.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.engine.holdings import MAX_PRICE_STALENESS_DAYS


def upsert_prices(conn: Any, prices: list[Any]) -> int:
    """Store merged prices. Idempotent: re-running a day changes nothing.

    ``ON CONFLICT DO UPDATE`` rather than ``DO NOTHING`` because a re-run should carry a
    correction through -- exchanges do republish a bhavcopy after a data error, and the
    later file is the better one.
    """
    if not prices:
        return 0
    with conn.cursor() as cur:
        for price in prices:
            cur.execute(
                """
                INSERT INTO price (isin, price_date, close, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (isin, price_date) DO UPDATE
                SET close = EXCLUDED.close, source = EXCLUDED.source
                """,
                (price.isin, price.price_date, price.close, price.source),
            )
    return len(prices)


def latest_prices(
    conn: Any,
    isins: list[str],
    as_of: date,
    max_staleness_days: int = MAX_PRICE_STALENESS_DAYS,
) -> dict[str, Decimal]:
    """Most recent close per ISIN, on or before ``as_of``, within the staleness window.

    An ISIN whose newest price is older than the window is OMITTED rather than returned.
    The caller then gets a ``MissingPriceError`` naming it, which is a fixable, visible
    problem -- unlike a week-old price presented as today's, which is not.
    """
    if not isins:
        return {}
    floor = as_of - timedelta(days=max_staleness_days)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (isin) isin, close
            FROM price
            WHERE isin = ANY(%s) AND price_date <= %s AND price_date >= %s
            ORDER BY isin, price_date DESC
            """,
            (list(isins), as_of, floor),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def prices_on_date(conn: Any, isins: list[str], price_date: date) -> dict[str, Decimal]:
    """Closes stored for EXACTLY ``price_date`` -- no carry-forward, no staleness window.

    ``latest_prices`` deliberately walks back up to ``MAX_PRICE_STALENESS_DAYS`` to find
    the newest usable close, which is right for valuing a portfolio and wrong for asking
    "has tonight's bhavcopy landed yet?". That second question is what decides whether an
    intraday yfinance quote is still needed for today (app.routers.holdings._portfolio),
    and answering it with a carried-forward close would say "settled" on every trading
    morning -- the live quote would then never be reached.

    Same omit-rather-than-substitute contract as everything else in this module: an ISIN
    with no row on that exact date is simply absent.
    """
    if not isins:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT isin, close FROM price WHERE isin = ANY(%s) AND price_date = %s",
            (list(isins), price_date),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def missing_prices(
    conn: Any,
    isins: list[str],
    as_of: date,
    max_staleness_days: int = MAX_PRICE_STALENESS_DAYS,
) -> list[str]:
    """ISINs with no usable price. Named, so a UI can name them too.

    "Cannot value your portfolio" is unactionable. "No price for KDL-SM since 6 August" is
    something a person can go and fix.
    """
    have = latest_prices(conn, isins, as_of, max_staleness_days)
    return sorted(set(isins) - set(have))


def price_dates_settled(conn: Any, start: date, end: date) -> set[date]:
    """Dates a backfill may skip, because every security it would ask about already has
    an answer -- a stored price, or a recorded absence.

    A three-year backfill is roughly 750 requests. It has to be resumable, or one timeout
    means starting again. This is what makes it resumable WITHOUT also making it blind.

    WHY THIS IS NOT "DATES THAT HAVE ANY PRICE ROW", which is what it used to be. That
    asks whether SOME security has a price on a date, and uses the answer for a different
    question: whether we have fetched that date for the securities we actually care about.
    The two agree only while the ledger never changes. Buy a new stock and every
    historical date already has prices for the older holdings -- so every date looks
    "present", bhavcopy is never re-fetched, and the new holding never gets any history.
    It stays permanently unvaluable, and every snapshot touching it is skipped forever.

    TWO THINGS BOUND THE WORK, and both are needed or the fix is worse than the bug:

    1. **A security is only wanted from its first transaction onward.** Nothing needs a
       price for a stock on a date nobody owned it. Without this clause, one new holding
       would re-open the entire archive -- hundreds of requests to establish nothing.
    2. **A recorded absence counts as an answer** (``price_absent``, migration 022). A
       scrip that legitimately did not trade that day -- suspended, pre-listing, an
       illiquid SME line -- would otherwise leave its dates unsettled and re-fetched on
       every run, forever.

    Dates with no answer of any kind are simply absent from the result, so a range that
    was never fetched comes back empty and the whole of it is fetched, as it should be.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH wanted AS (
                SELECT isin, min(txn_date) AS first_held FROM transaction GROUP BY isin
            ),
            answered AS (
                SELECT DISTINCT price_date FROM price WHERE price_date BETWEEN %s AND %s
                UNION
                SELECT DISTINCT price_date FROM price_absent
                WHERE price_date BETWEEN %s AND %s
            )
            SELECT a.price_date
            FROM answered a
            WHERE NOT EXISTS (
                SELECT 1 FROM wanted w
                WHERE w.first_held <= a.price_date
                  AND NOT EXISTS (
                      SELECT 1 FROM price p
                      WHERE p.isin = w.isin AND p.price_date = a.price_date
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM price_absent x
                      WHERE x.isin = w.isin AND x.price_date = a.price_date
                  )
            )
            """,
            (start, end, start, end),
        )
        return {row[0] for row in cur.fetchall()}


def record_absent_prices(conn: Any, on_date: date, isins: Sequence[str]) -> int:
    """Remember that these securities were NOT in the bhavcopy we fetched for this date.

    Call this ONLY after a fetch that actually returned data. Recording an absence for a
    day the archive never answered -- a weekend, a holiday, a timed-out request -- would
    mark that date settled forever and permanently lose the prices it should have had,
    which is a far more expensive mistake than fetching it again.

    Idempotent: re-recording an absence leaves the original ``recorded_at`` alone, so a
    repeated run neither fails nor rewrites history.
    """
    if not isins:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO price_absent (isin, price_date) VALUES (%s, %s) "
            "ON CONFLICT (isin, price_date) DO NOTHING",
            [(isin, on_date) for isin in isins],
        )
    return len(isins)


def held_isins(conn: Any, investor_id: str | None = None) -> list[str]:
    """Every ISIN in the ledger -- what a backfill needs prices for.

    Every ISIN EVER traded, not only those currently held: a historical snapshot values the
    portfolio as it stood then, which includes positions since closed.
    """
    with conn.cursor() as cur:
        if investor_id:
            cur.execute(
                "SELECT DISTINCT t.isin FROM transaction t "
                "JOIN account a ON a.id = t.account_id WHERE a.investor_id = %s",
                (investor_id,),
            )
        else:
            cur.execute("SELECT DISTINCT isin FROM transaction")
        return sorted(row[0] for row in cur.fetchall())
