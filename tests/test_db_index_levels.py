"""``index_level`` persistence, against a real cluster -- docs/ENGINE_SPEC.md section 6."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.db.index_levels import get_index_levels, upsert_index_levels
from app.prices.index_sources import IndexLevelRow

pytestmark = pytest.mark.db

INDEX_NAME = "NIFTY50_TRI"


def a_row(on: date, close: str, source: str = "NIFTYINDICES_TRI") -> IndexLevelRow:
    return IndexLevelRow(index_name=INDEX_NAME, level_date=on, close=Decimal(close), source=source)


# --- upsert / range read ------------------------------------------------------------


def test_upsert_and_read_round_trip(db) -> None:
    upsert_index_levels(
        db,
        [
            a_row(date(2024, 1, 10), "25412.35"),
            a_row(date(2024, 1, 11), "25550.02"),
        ],
    )

    levels = get_index_levels(db, INDEX_NAME, [date(2024, 1, 10), date(2024, 1, 11)])
    assert levels == {
        date(2024, 1, 10): Decimal("25412.35"),
        date(2024, 1, 11): Decimal("25550.02"),
    }


def test_upsert_is_idempotent_and_a_rerun_corrects_the_stored_close(db) -> None:
    """Same reasoning as app.db.prices.upsert_prices: a republished/corrected value
    should carry through, not be a no-op forever."""
    upsert_index_levels(db, [a_row(date(2024, 1, 10), "25000")])
    upsert_index_levels(db, [a_row(date(2024, 1, 10), "25412.35")])

    levels = get_index_levels(db, INDEX_NAME, [date(2024, 1, 10)])
    assert levels[date(2024, 1, 10)] == Decimal("25412.35")

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM index_level WHERE index_name = %s", (INDEX_NAME,))
        assert cur.fetchone()[0] == 1


def test_index_level_is_never_keyed_by_isin_or_joinable_to_security(db) -> None:
    """Structural proof of the CLAUDE.md separation this table exists to enforce: no
    ISIN column at all, so it cannot be confused with -- or accidentally joined against
    -- a security price."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'index_level'"
        )
        columns = {row[0] for row in cur.fetchall()}
    assert "isin" not in columns
    assert {"index_name", "level_date", "close", "source"} <= columns


# --- on-or-before / staleness resolution ------------------------------------------------


def test_a_target_date_resolves_to_the_most_recent_level_on_or_before_it(db) -> None:
    """Mirrors app.db.prices.latest_prices' on-or-before semantics -- a requested date
    that falls on a weekend/holiday still resolves against the last published level."""
    upsert_index_levels(db, [a_row(date(2024, 1, 10), "25412.35")])

    # 2024-01-13 is a Saturday -- no level published that day.
    levels = get_index_levels(db, INDEX_NAME, [date(2024, 1, 13)])
    assert levels[date(2024, 1, 13)] == Decimal("25412.35")


def test_a_date_with_no_level_within_the_staleness_window_is_omitted(db) -> None:
    upsert_index_levels(db, [a_row(date(2024, 1, 1), "25000")])

    levels = get_index_levels(
        db, INDEX_NAME, [date(2024, 3, 1)], max_staleness_days=5
    )
    assert date(2024, 3, 1) not in levels


def test_a_date_with_no_level_at_all_is_simply_absent_not_an_error(db) -> None:
    levels = get_index_levels(db, INDEX_NAME, [date(2024, 1, 10)])
    assert levels == {}
