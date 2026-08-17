"""Portfolio-snapshot persistence -- docs/ENGINE_SPEC.md section 8.

Narrow and typed, like ``app/db/prices.py``: this module only reads and writes rows. It
has no opinion about WHEN a snapshot should be computed or what to do when a price is
missing -- that orchestration lives in ``app.routers.analytical._run_snapshots``, the only
caller allowed to write here. Every row is a cache of ``compute_snapshot()``, never a
source of truth, so nothing in this module ever mutates a stored total in place.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.engine.types import Snapshot


def upsert_snapshot(
    conn: Any, investor_id: str, advised_only: bool, snapshot: Snapshot
) -> None:
    """Store one snapshot. Idempotent: rerunning a date changes nothing.

    ``ON CONFLICT DO UPDATE`` rather than ``DO NOTHING``, same reasoning as
    ``upsert_prices`` -- a rerun (say, after a price correction) should carry the better
    number through, not be a no-op forever.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO portfolio_snapshot
                (investor_id, as_of, advised_only, invested, market_value,
                 unrealised, realised_to_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (investor_id, as_of, advised_only) DO UPDATE
            SET invested = EXCLUDED.invested,
                market_value = EXCLUDED.market_value,
                unrealised = EXCLUDED.unrealised,
                realised_to_date = EXCLUDED.realised_to_date,
                computed_at = now()
            """,
            (
                investor_id,
                snapshot.as_of,
                advised_only,
                snapshot.invested,
                snapshot.market_value,
                snapshot.unrealised,
                snapshot.realised_to_date,
            ),
        )


def get_snapshot(
    conn: Any, investor_id: str, as_of: date, advised_only: bool = False
) -> Snapshot | None:
    """The persisted snapshot for one investor/date/series, or ``None`` if never written.

    A miss is not an error -- it means the caller should fall back to a live
    ``compute_snapshot()`` call, exactly as ``_fy_xirr``/``_period_xirr`` already do when
    this table has nothing for the date they need.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT as_of, invested, market_value, unrealised, realised_to_date
            FROM portfolio_snapshot
            WHERE investor_id = %s AND as_of = %s AND advised_only = %s
            """,
            (investor_id, as_of, advised_only),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return Snapshot(
        as_of=row[0],
        invested=row[1],
        market_value=row[2],
        unrealised=row[3],
        realised_to_date=row[4],
    )


def snapshot_dates_present(
    conn: Any, investor_id: str, advised_only: bool, start: date, end: date
) -> set[date]:
    """Dates already written for this investor/series, so a backfill can resume.

    Mirrors ``app.db.prices.price_dates_present`` for the same reason: a multi-year,
    multi-investor backfill is a lot of requests, and it has to be resumable rather than
    starting over after a timeout.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT as_of FROM portfolio_snapshot
            WHERE investor_id = %s AND advised_only = %s AND as_of BETWEEN %s AND %s
            """,
            (investor_id, advised_only, start, end),
        )
        return {row[0] for row in cur.fetchall()}
