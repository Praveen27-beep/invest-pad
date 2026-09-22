"""Membership of the cross-sectional ranking universe -- see
``app/db/migrations/032_analytics_and_universe.sql``.

A factor score is a PERCENTILE, and a percentile without a stated population is not a
number, it is a decoration. "Momentum 66/100" means nothing until you know 66th out of
what. Ranking a portfolio only against its own holdings is the specific failure this
exists to prevent: with fifteen positions, every percentile is an artefact of the fifteen.

Membership is stored rather than inferred because the population must stay explicable
after the fact. Index constituents change; a score computed last quarter was computed
against last quarter's population, and `removed_on` is what keeps that answerable instead
of quietly re-writing history every time the index is rebalanced.

The universe costs no extra fetch. The bhavcopy this system already downloads every day
carries every listed scrip -- ``app.prices.pipe.main`` simply discards all but the held
ones. Widening that filter to include universe members buys a real population for the
price of rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger("db.universe")

#: The default ranking population. Named and stored on every score that uses it, because
#: a mid-cap book ranked against a large-cap index is as misleading as no universe at all.
#:
#: "TRACKED" is deliberately a descriptive name, not an index name: it is the set of
#: securities this installation actually retains prices for, which is what the percentiles
#: are genuinely computed against. Calling it NIFTY100 while it holds something else would
#: put a false population on every factor score on the screen. Replace the NAME at the same
#: time as the membership when a real index constituent list is loaded, never before.
DEFAULT_UNIVERSE = "TRACKED"


@dataclass(frozen=True, slots=True)
class UniverseMember:
    isin: str
    universe: str
    added_on: date
    removed_on: date | None


def current_universe_isins(conn: Any, universe: str | None = None) -> list[str]:
    """ISINs currently in ``universe`` (all universes when None). Sorted, for determinism."""
    sql = "SELECT isin FROM universe_member WHERE removed_on IS NULL"
    params: tuple[Any, ...] = ()
    if universe is not None:
        sql += " AND universe = %s"
        params = (universe,)
    sql += " ORDER BY isin"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [row[0] for row in cur.fetchall()]


def list_members(conn: Any, universe: str, include_removed: bool = False) -> list[UniverseMember]:
    sql = "SELECT isin, universe, added_on, removed_on FROM universe_member WHERE universe = %s"
    if not include_removed:
        sql += " AND removed_on IS NULL"
    sql += " ORDER BY isin"
    with conn.cursor() as cur:
        cur.execute(sql, (universe,))
        return [UniverseMember(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def ensure_universe_securities(conn: Any, rows: dict[str, dict[str, Any]]) -> int:
    """Create ``security`` rows for universe members that have none yet.

    ``rows`` is ISIN -> {"symbol", "name", "exchange"}, taken from a bhavcopy. Needed
    because ``universe_member.isin`` and ``price.isin`` are both foreign keys to
    ``security``: a universe member with no security row can be neither enrolled nor priced.

    ``ON CONFLICT DO NOTHING`` -- this only fills gaps. It must never overwrite a security
    the ledger already knows about, whose symbol is maintained by
    ``app.db.symbols.refresh_symbols`` and whose sector and cap bucket are loaded from NSE
    and AMFI. Returns the number of rows actually created.
    """
    if not rows:
        return 0
    created = 0
    with conn.cursor() as cur:
        for isin, meta in rows.items():
            cur.execute(
                """
                INSERT INTO security (isin, symbol, name, exchange, asset_class)
                VALUES (%s, %s, %s, %s, 'EQ')
                ON CONFLICT (isin) DO NOTHING
                """,
                (isin, meta.get("symbol"), meta.get("name"), meta.get("exchange")),
            )
            created += cur.rowcount or 0
    return created


def set_universe(conn: Any, universe: str, isins: list[str], on: date) -> dict[str, int]:
    """Make ``isins`` the exact current membership of ``universe`` as of ``on``.

    Additive and subtractive in one call, which is what a rebalance actually is. An ISIN
    already a current member is left alone -- its ``added_on`` is not bumped, because the
    date it joined is a fact and re-stating it on every sync would erase the tenure the
    table exists to record. A current member absent from ``isins`` is marked
    ``removed_on``, never deleted.

    A previously-removed ISIN that returns is re-admitted by clearing ``removed_on`` and
    re-dating ``added_on``: that genuinely is a new tenure.
    """
    wanted = set(isins)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT isin, removed_on FROM universe_member WHERE universe = %s",
            (universe,),
        )
        known = {row[0]: row[1] for row in cur.fetchall()}

        current = {isin for isin, removed in known.items() if removed is None}
        to_add = wanted - current
        to_remove = current - wanted

        for isin in sorted(to_add):
            if isin in known:  # returning member: a new tenure, not a resurrection
                cur.execute(
                    "UPDATE universe_member SET universe = %s, added_on = %s, "
                    "removed_on = NULL WHERE isin = %s",
                    (universe, on, isin),
                )
            else:
                cur.execute(
                    "INSERT INTO universe_member (isin, universe, added_on) VALUES (%s, %s, %s)",
                    (isin, universe, on),
                )
        for isin in sorted(to_remove):
            cur.execute(
                "UPDATE universe_member SET removed_on = %s WHERE isin = %s AND universe = %s",
                (on, isin, universe),
            )

    if to_add or to_remove:
        logger.info(
            "universe %s updated on %s: +%d -%d", universe, on, len(to_add), len(to_remove)
        )
    return {"added": len(to_add), "removed": len(to_remove), "current": len(wanted)}
