"""POST /investors/{id}/reconcile -- app.routers.reconcile.reconcile_holdings, against
a real database. See docs/FULL_VISION_BACKEND_ROADMAP.md section A2.

Calls the route handler directly with the ``db`` fixture's connection, the same pattern
tests/test_db_transactions.py uses for ``transactions.create_transactions``: a FastAPI
route decorator returns the plain function underneath, so no HTTP client is needed to
exercise it against a real Postgres cluster. Transactions are seeded through
``transactions.create_transactions`` rather than raw SQL, so the ledger this test
reconciles against is written the same way the real ingestion path writes it.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from app.routers.reconcile import reconcile_holdings
from app.routers.transactions import create_transactions
from app.schemas.reconcile import DeclaredHoldingIn, ReconcileRequest
from app.schemas.transactions import TransactionIn

pytestmark = pytest.mark.db

ISIN = "INE153T01027"


def seed_a_buy(db, investor: str, quantity: str = "200") -> None:
    txn = TransactionIn(
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        isin=ISIN,
        txn_date=date(2024, 1, 10),
        txn_type="BUY",
        quantity=quantity,
        price="250",
        source="MANUAL",
        source_ref="T1",
    )
    create_transactions(investor, [txn], connection=db)


def test_matching_declared_quantity_reconciles_clean(db, investor) -> None:
    seed_a_buy(db, investor)
    body = ReconcileRequest(holdings=[DeclaredHoldingIn(isin=ISIN, quantity="200")])
    assert reconcile_holdings(investor, body, connection=db) == []


def test_a_doubled_declared_quantity_reads_as_a_bonus(db, investor) -> None:
    seed_a_buy(db, investor)
    body = ReconcileRequest(holdings=[DeclaredHoldingIn(isin=ISIN, quantity="400")])

    (discrepancy,) = reconcile_holdings(investor, body, connection=db)

    assert discrepancy["isin"] == ISIN
    assert discrepancy["computed_qty"] == "200"
    assert discrepancy["declared_qty"] == "400"
    assert discrepancy["difference"] == "200"
    assert discrepancy["ratio"] == 2.0
    assert "bonus" in discrepancy["likely_cause"].lower()


def test_an_isin_never_bought_but_declared_reads_as_an_unrecorded_transfer_in(
    db, investor
) -> None:
    """Nothing seeded at all -- the ledger has no rows for this investor, so every
    declared quantity is a surplus against a computed zero."""
    body = ReconcileRequest(holdings=[DeclaredHoldingIn(isin=ISIN, quantity="100")])

    (discrepancy,) = reconcile_holdings(investor, body, connection=db)

    assert discrepancy["computed_qty"] == "0"
    assert discrepancy["ratio"] is None
    assert "transfer-in" in discrepancy["likely_cause"].lower()


def test_as_of_truncates_the_ledger_before_reconciling(db, investor) -> None:
    """A declared quantity from a statement dated before a later buy must not be
    penalised for a purchase that, as of that date, had not happened yet."""
    seed_a_buy(db, investor, quantity="200")
    body = ReconcileRequest(
        as_of=date(2023, 12, 31),
        holdings=[DeclaredHoldingIn(isin=ISIN, quantity="0")],
    )
    assert reconcile_holdings(investor, body, connection=db) == []


def test_no_declared_holdings_reports_every_computed_holding_as_a_full_exit(
    db, investor
) -> None:
    seed_a_buy(db, investor)
    body = ReconcileRequest(holdings=[])

    (discrepancy,) = reconcile_holdings(investor, body, connection=db)

    assert discrepancy["declared_qty"] == "0"
    assert "full exit" in discrepancy["likely_cause"].lower()
