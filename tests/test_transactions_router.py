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


#: The three txn_types whose documented quantity/price effect is 0 (docs/DATA_MODEL.md's
#: txn_type table) -- DIVIDEND (amount in dividend_amount) and the DEMERGER_COST_OUT/IN
#: pair (amount in cost_transfer). `base()`'s quantity=100/price=200 defaults are wrong
#: for these three; TransactionIn now enforces that, so the test fixture must match.
_ZERO_QTY_OVERRIDES: dict[str, dict[str, object]] = {
    "DIVIDEND": {"quantity": "0", "price": "0", "dividend_amount": "500"},
    "DEMERGER_COST_OUT": {"quantity": "0", "price": "0", "cost_transfer": "500"},
    "DEMERGER_COST_IN": {"quantity": "0", "price": "0", "cost_transfer": "500"},
}


@pytest.mark.parametrize("txn_type", [t.value for t in TxnType])
def test_all_ten_txn_types_are_accepted(txn_type: str) -> None:
    """docs/DATA_MODEL.md's txn_type enum, all ten values, none rejected."""
    txn = TransactionIn(**base(txn_type=txn_type, **_ZERO_QTY_OVERRIDES.get(txn_type, {})))
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


def test_zero_quantity_is_rejected_for_a_real_trade() -> None:
    """A field test found this landing as a permanent row in the append-only ledger --
    ``ge=0`` alone (needed so DIVIDEND's genuine zero keeps working) does not stop a BUY
    from being zero too. Only DIVIDEND/DEMERGER_COST_OUT/DEMERGER_COST_IN may be zero."""
    with pytest.raises(ValidationError):
        TransactionIn(**base(quantity="0"))


def test_negative_price_is_rejected() -> None:
    """The other half of the same field-test finding: price had no floor at all, so a
    negative price landed permanently in the ledger too."""
    with pytest.raises(ValidationError):
        TransactionIn(**base(price="-100"))


def test_absurdly_large_quantity_is_rejected() -> None:
    """A fat-fingered extra digit (12+ digits) garbled the Holdings table's numeric
    columns and blew every dashboard aggregate out to a meaningless figure -- a sanity
    ceiling well above any real single entry (the golden portfolio's largest line is
    2,250 shares) catches the typo without constraining real trading."""
    with pytest.raises(ValidationError):
        TransactionIn(**base(quantity="999999999999"))


def test_dividend_requires_zero_quantity_and_price() -> None:
    """DIVIDEND's amount lives in dividend_amount -- docs/DATA_MODEL.md's txn_type table
    is explicit that quantity and price are both 0, not just unused."""
    with pytest.raises(ValidationError):
        TransactionIn(**base(txn_type="DIVIDEND", quantity="10", price="0", dividend_amount="500"))
    with pytest.raises(ValidationError):
        TransactionIn(**base(txn_type="DIVIDEND", quantity="0", price="50", dividend_amount="500"))
    # The correct shape is accepted.
    txn = TransactionIn(**base(txn_type="DIVIDEND", quantity="0", price="0", dividend_amount="500"))
    assert txn.dividend_amount == Decimal("500")


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
