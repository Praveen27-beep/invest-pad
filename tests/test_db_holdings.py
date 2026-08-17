"""GET /investors/{id}/holdings' advised_only filter -- app.routers.holdings.holdings,
against a real database. See docs/FULL_VISION_BACKEND_ROADMAP.md section A4.

Calls the route handler directly with the ``db`` fixture's connection, the same pattern
tests/test_db_reconcile.py uses. ``asset_class`` is passed explicitly as ``None`` on every
direct call: its FastAPI-level default is ``Query(default=None)``, a sentinel object that
only resolves to plain ``None`` when FastAPI itself supplies it via a real request -- a
direct call bypasses that resolution, so leaving it unset would silently exclude every
holding instead of exercising the "no filter" path.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from app.db import prices as dbprices
from app.prices.pipe import MergedPrice
from app.routers.holdings import holdings
from app.routers.transactions import create_transactions
from app.schemas.transactions import TransactionIn

pytestmark = pytest.mark.db

ISIN_ADVISED = "INE153T01027"
ISIN_UNADVISED = "INE242A01010"
AS_OF = date(2024, 9, 30)


def buy(
    account_id: str, isin: str, day: date, quantity: str, price: str, ref: str
) -> TransactionIn:
    return TransactionIn(
        account_id=account_id,
        isin=isin,
        txn_date=day,
        txn_type="BUY",
        quantity=quantity,
        price=price,
        source="MANUAL",
        source_ref=ref,
    )


def add_unadvised_account(db, investor_id: str) -> str:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'GROWW', false) RETURNING id",
            (investor_id,),
        )
        account_id = str(cur.fetchone()[0])
    db.commit()
    return account_id


def add_security(db, isin: str, symbol: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO security (isin, symbol, exchange) VALUES (%s, %s, 'NSE') "
            "ON CONFLICT DO NOTHING",
            (isin, symbol),
        )
    db.commit()


def seed_price(db, isin: str, on: date, close: str) -> None:
    dbprices.upsert_prices(
        db, [MergedPrice(isin=isin, price_date=on, close=Decimal(close), source="NSE_BHAVCOPY")]
    )


def seed_advised_and_unadvised_holdings(db, investor_id: str) -> None:
    advised_account = os.environ["_TEST_ACCOUNT_ID"]
    unadvised_account = add_unadvised_account(db, investor_id)
    add_security(db, ISIN_UNADVISED, "UNADV")
    create_transactions(
        investor_id,
        [
            buy(advised_account, ISIN_ADVISED, date(2023, 1, 10), "100", "100", "ADV"),
            buy(unadvised_account, ISIN_UNADVISED, date(2023, 1, 10), "50", "300", "UNADV"),
        ],
        connection=db,
    )
    seed_price(db, ISIN_ADVISED, AS_OF, "150")
    seed_price(db, ISIN_UNADVISED, AS_OF, "400")


def test_advised_only_excludes_the_unadvised_accounts_holding(db, investor) -> None:
    seed_advised_and_unadvised_holdings(db, investor)

    everything = holdings(investor, as_of=AS_OF, asset_class=None, connection=db)
    advised_only = holdings(
        investor, as_of=AS_OF, asset_class=None, advised_only=True, connection=db
    )

    assert {h["isin"] for h in everything["holdings"]} == {ISIN_ADVISED, ISIN_UNADVISED}
    assert {h["isin"] for h in advised_only["holdings"]} == {ISIN_ADVISED}
    assert Decimal(advised_only["totals"]["invested"]) == Decimal("10000")


def test_advised_only_defaults_to_false(db, investor) -> None:
    seed_advised_and_unadvised_holdings(db, investor)

    default = holdings(investor, as_of=AS_OF, asset_class=None, connection=db)

    assert {h["isin"] for h in default["holdings"]} == {ISIN_ADVISED, ISIN_UNADVISED}
