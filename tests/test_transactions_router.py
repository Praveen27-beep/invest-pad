"""POST /investors/{id}/transactions request validation -- no database needed.

``app.schemas.transactions.TransactionIn`` is the exact boundary FastAPI validates a
request body against, so testing it directly here pins the same behaviour the router
gets, without depending on a running Postgres cluster the way
tests/test_db_transactions.py's integration test does.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.engine.types import TxnType
from app.schemas.transactions import TransactionIn
from pydantic import ValidationError

ACCOUNT_ID = "11111111-1111-1111-1111-111111111111"
ISIN = "INE153T01027"


def base(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "account_id": ACCOUNT_ID,
        "isin": ISIN,
        "txn_date": date(2024, 1, 10),
        "txn_type": "BUY",
        "quantity": "100",
        "price": "200",
    }
    fields.update(overrides)
    return fields


@pytest.mark.parametrize("txn_type", [t.value for t in TxnType])
def test_all_ten_txn_types_are_accepted(txn_type: str) -> None:
    """docs/DATA_MODEL.md's txn_type enum, all ten values, none rejected."""
    txn = TransactionIn(**base(txn_type=txn_type))
    assert txn.txn_type is TxnType(txn_type)


def test_an_unlisted_txn_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TransactionIn(**base(txn_type="ROLLOVER"))


def test_txn_type_is_not_silently_coerced() -> None:
    """A near-miss must fail loudly, not get normalised into a real value."""
    with pytest.raises(ValidationError):
        TransactionIn(**base(txn_type="buy"))


def test_missing_required_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TransactionIn(isin=ISIN, txn_date=date(2024, 1, 10), txn_type="BUY")


def test_negative_quantity_is_rejected() -> None:
    """quantity is ALWAYS POSITIVE per DATA_MODEL.md -- direction comes from txn_type."""
    with pytest.raises(ValidationError):
        TransactionIn(**base(quantity="-5"))


def test_an_isin_that_does_not_match_the_pattern_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TransactionIn(**base(isin="NOTANISIN"))


def test_decimal_fields_stay_exact() -> None:
    """CLAUDE.md rule 1: money is Decimal, never float. A value that would lose
    precision as a binary float must survive unchanged through validation."""
    txn = TransactionIn(**base(quantity="100.123456", price="43.119999"))
    assert txn.quantity == Decimal("100.123456")
    assert txn.price == Decimal("43.119999")


def test_charges_and_dividend_amount_default_to_zero() -> None:
    txn = TransactionIn(**base())
    assert txn.charges == Decimal("0")
    assert txn.dividend_amount == Decimal("0")


def test_source_and_source_ref_are_optional() -> None:
    txn = TransactionIn(**base())
    assert txn.source is None
    assert txn.source_ref is None
