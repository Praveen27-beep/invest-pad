"""Connection handling and the JSON conventions, in one place.

Thin deliberately. ``app/db/connection.py`` already owns the connection lifecycle; this
adds the two things the web layer needs on top of it -- a per-request connection sourced
from ``app/config.py`` rather than a bare environment read, and the rule for how a
Decimal crosses the JSON boundary. Moved here verbatim from ``api/deps.py``, logic
unchanged -- see docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md section 1.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.db.connection import connect


def get_conn() -> Iterator[Any]:
    """FastAPI dependency: one connection per request. No pool.

    Given the load this serves -- an adviser with tens of clients, refreshed on trade
    days -- a pool would be a moving part bought with no measured problem. Add one when
    profiling says to, not before.
    """
    settings = get_settings()
    with connect(settings.database_url) as connection:
        yield connection


def money(value: Decimal | None) -> str | None:
    """Money crosses as a STRING, per schema/transaction.schema.json#/$defs/decimal.

    A JSON number is an IEEE double by the time any client parses it, and a system that
    keeps Decimal end-to-end through the engine and NUMERIC(20,6) in Postgres would be
    throwing that away at the last step. The consumer formats the string; it never does
    arithmetic on it.
    """
    return None if value is None else str(value)


def rate(value: Decimal | None) -> float | None:
    """A ratio crosses as a NUMBER, per schema/holding.schema.json.

    Deliberately different from ``money``. This is a display ratio -- 0.323012 meaning
    32.3% -- never something a downstream sum has to be exact about. The float()
    conversion is confined to this function so the boundary stays greppable, and it lives
    in ``app/`` rather than ``app/engine/``, where ``make lint`` forbids it outright.
    """
    return None if value is None else float(value)
