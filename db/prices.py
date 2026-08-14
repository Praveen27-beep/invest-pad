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

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from engine.holdings import MAX_PRICE_STALENESS_DAYS


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


def price_dates_present(conn: Any, start: date, end: date) -> set[date]:
    """Dates already stored, so a backfill can skip them.

    A three-year backfill is roughly 750 requests. It has to be resumable, or one timeout
    means starting again.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT price_date FROM price WHERE price_date BETWEEN %s AND %s",
            (start, end),
        )
        return {row[0] for row in cur.fetchall()}


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
