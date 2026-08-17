"""POST /investors/{id}/reconcile -- request validation and response shaping, no
database needed.

``app.schemas.reconcile`` is the exact boundary FastAPI validates the request body
against, and ``app.routers.reconcile._discrepancy_row`` is the exact boundary the
response is shaped through -- both are testable directly without a running Postgres
cluster, the same split ``tests/test_transactions_router.py`` uses for the sibling
POST /investors/{id}/transactions endpoint.

The cause-heuristic logic itself belongs to ``app.engine.reconcile.reconcile`` and is
pinned by ``tests/test_reconcile.py``; this file calls that same function -- never a
reimplementation of it -- and asserts only that the router carries its answer through
unchanged onto the wire.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.reconcile import reconcile
from app.engine.types import Transaction, TxnType
from app.routers.reconcile import _discrepancy_row
from app.schemas.reconcile import DeclaredHoldingIn, ReconcileRequest
from pydantic import ValidationError

ISIN = "INE153T01027"

BOUGHT_200 = [
    Transaction(
        isin=ISIN,
        txn_date=date(2024, 1, 10),
        txn_type=TxnType.BUY,
        quantity=Decimal("200"),
        price=Decimal("250"),
    )
]


# --- request validation ---------------------------------------------------------------


def test_a_valid_declared_holding_is_accepted() -> None:
    holding = DeclaredHoldingIn(isin=ISIN, quantity="400")
    assert holding.quantity == Decimal("400")


def test_an_isin_that_does_not_match_the_pattern_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeclaredHoldingIn(isin="NOTANISIN", quantity="100")


def test_a_negative_declared_quantity_is_rejected() -> None:
    """A depository or broker statement never declares a short position."""
    with pytest.raises(ValidationError):
        DeclaredHoldingIn(isin=ISIN, quantity="-5")


def test_holdings_defaults_to_an_empty_list() -> None:
    body = ReconcileRequest()
    assert body.holdings == []


def test_as_of_and_source_are_optional() -> None:
    body = ReconcileRequest(holdings=[{"isin": ISIN, "quantity": "200"}])
    assert body.as_of is None
    assert body.source is None


def test_source_is_accepted_per_the_contract() -> None:
    body = ReconcileRequest(source="CAS")
    assert body.source == "CAS"


def test_a_declared_quantity_with_bad_decimal_syntax_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeclaredHoldingIn(isin=ISIN, quantity="not-a-number")


# --- response shaping --------------------------------------------------------------


def test_doubled_quantity_shapes_into_a_bonus_discrepancy_row() -> None:
    """A known 2x mismatch, run through the real engine function, then shaped for the
    wire -- exactly what a client of this endpoint would receive."""
    (discrepancy,) = reconcile(BOUGHT_200, {ISIN: Decimal("400")})
    row = _discrepancy_row(discrepancy)

    assert row["isin"] == ISIN
    assert row["computed_qty"] == "200"
    assert row["declared_qty"] == "400"
    assert row["difference"] == "200"
    assert row["ratio"] == 2.0
    assert "bonus" in row["likely_cause"].lower()


def test_shaped_quantities_cross_as_strings_not_floats() -> None:
    """CLAUDE.md rule 1: money/quantity is Decimal end to end; only ``ratio`` is a
    display float, per schema/discrepancy.schema.json."""
    (discrepancy,) = reconcile(BOUGHT_200, {ISIN: Decimal("400")})
    row = _discrepancy_row(discrepancy)

    assert isinstance(row["computed_qty"], str)
    assert isinstance(row["declared_qty"], str)
    assert isinstance(row["difference"], str)
    assert isinstance(row["ratio"], float)


def test_a_clean_reconciliation_shapes_into_an_empty_list() -> None:
    assert reconcile(BOUGHT_200, {ISIN: Decimal("200")}) == []
