"""The Zerodha tradebook parser. Pure -- no database, no storage.

The load-bearing assertion is that trade_id reaches dedupe_key: without it, 16 genuine
trades in this project's own real exports would be silently destroyed.
"""

from __future__ import annotations

import csv
import glob
import os
from datetime import date
from decimal import Decimal

import pytest

from engine.dedupe import make_dedupe_key
from engine.types import Source, TxnType
from ingest.zerodha_tradebook import ZerodhaTradebookAdapter

ACCOUNT = "11111111-1111-1111-1111-111111111111"

#: Real broker documents stay OUT of the repository -- they are one investor's financial
#: history. Point this at a local folder to run the tests that need them; without it they
#: skip. See .gitignore.
LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")

HEADER = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
)
GOOD = (
    "BLS,INE153T01027,2024-01-10,NSE,EQ,EQ,buy,false,100.000000,200.500000,"
    "12345,99001,2024-01-10T10:15:00\n"
)

TRADEBOOKS = sorted(
    glob.glob(f"{LOCAL_DOCS}/tradebook-*-EQ*.csv")
)


@pytest.fixture()
def adapter() -> ZerodhaTradebookAdapter:
    return ZerodhaTradebookAdapter()


def parse(adapter, body: str):
    return adapter.parse((HEADER + body).encode(), account_id=ACCOUNT)


# --- happy path ----------------------------------------------------------------


def test_a_buy_becomes_a_transaction(adapter) -> None:
    result = parse(adapter, GOOD)
    assert result.rejected == 0
    (staged,) = result.rows

    txn = staged.transaction
    assert txn.isin == "INE153T01027"
    assert txn.txn_type is TxnType.BUY
    assert txn.txn_date == date(2024, 1, 10)
    assert txn.quantity == Decimal("100.000000")
    assert txn.price == Decimal("200.500000")
    assert txn.source is Source.TRADEBOOK
    assert txn.source_ref == "12345"


def test_a_sell_maps_to_sell(adapter) -> None:
    (staged,) = parse(adapter, GOOD.replace(",buy,", ",sell,")).rows
    assert staged.transaction.txn_type is TxnType.SELL


def test_quantities_stay_decimal(adapter) -> None:
    """A price routed through a binary numeric type would undo the whole discipline."""
    (staged,) = parse(adapter, GOOD).rows
    assert isinstance(staged.transaction.price, Decimal)
    assert staged.transaction.price == Decimal("200.500000")


def test_charges_are_zero_and_the_absence_is_stated(adapter) -> None:
    """A tradebook carries no charges. That is missing data, not free trades."""
    result = parse(adapter, GOOD)
    assert result.rows[0].transaction.charges == Decimal("0")
    assert any("charges" in note for note in result.notes)


def test_structured_rows_are_certain(adapter) -> None:
    assert parse(adapter, GOOD).rows[0].confidence == Decimal("1.0")


# --- validation-first ----------------------------------------------------------


def test_a_bad_row_is_rejected_and_the_others_survive(adapter) -> None:
    """One malformed line must not cost the rest of the file."""
    bad = GOOD.replace(",buy,", ",transfer,")
    result = parse(adapter, GOOD + bad + GOOD.replace("12345", "12346"))
    assert result.parsed == 2
    assert result.rejected == 1


def test_rejections_carry_the_row_number(adapter) -> None:
    """Whoever fixes the file needs to be told which line to open."""
    result = parse(adapter, GOOD + GOOD.replace(",buy,", ",transfer,"))
    (rejection,) = result.rejections
    assert rejection.row_number == 3, "header is row 1, so the second data row is row 3"
    assert "transfer" in rejection.reason


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda r: r.replace("INE153T01027", "NOTANISIN"), "ISIN"),
        (lambda r: r.replace("2024-01-10", "10/01/2024"), "trade_date"),
        (lambda r: r.replace(",100.000000,", ",abc,"), "quantity/price"),
        (lambda r: r.replace(",100.000000,", ",-5,"), "positive"),
        (lambda r: r.replace(",EQ,EQ,", ",FO,EQ,"), "Phase 1"),
        (lambda r: r.replace(",12345,", ",,"), "trade_id"),
    ],
)
def test_rows_are_rejected_rather_than_guessed(adapter, mutation, expected) -> None:
    result = parse(adapter, mutation(GOOD))
    assert result.parsed == 0
    assert expected in result.rejections[0].reason


def test_a_file_that_is_not_a_tradebook_is_refused_whole(adapter) -> None:
    result = adapter.parse(b"a,b,c\n1,2,3\n", account_id=ACCOUNT)
    assert result.parsed == 0
    assert "not a Zerodha tradebook" in result.rejections[0].reason


def test_an_empty_file_is_refused(adapter) -> None:
    assert adapter.parse(b"", account_id=ACCOUNT).rejections[0].reason == "file is empty"


# --- the finding this parser is shaped around ----------------------------------


def test_trade_id_separates_otherwise_identical_trades(adapter) -> None:
    """Three sells of 2 @ 484.100006 on one day are three trades, not one.

    Taken from the real export: INE142Q01026, 2024-09-10. A dedupe key without trade_id
    would collapse them and look like it worked.
    """
    body = "".join(
        "SULA,INE142Q01026,2024-09-10,NSE,EQ,EQ,sell,false,2.000000,484.100006,"
        f"{tid},60456,2024-09-10T11:00:0{i}\n"
        for i, tid in enumerate(["604560109", "604560108", "604560111"])
    )
    result = parse(adapter, body)
    assert result.parsed == 3
    keys = {make_dedupe_key(s.transaction) for s in result.rows}
    assert len(keys) == 3, "identical trades must not collapse into one"


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_every_real_row_gets_a_distinct_dedupe_key(adapter) -> None:
    """Measured, not assumed: 259 real rows, 259 distinct keys.

    Without trade_id this drops to 243 -- 16 genuine trades destroyed across 12 groups.
    """
    keys, rows = set(), 0
    for path in TRADEBOOKS:
        result = adapter.parse(open(path, "rb").read(), account_id=ACCOUNT)
        assert result.rejected == 0, f"{path}: {result.rejections[:3]}"
        rows += result.parsed
        keys |= {make_dedupe_key(s.transaction) for s in result.rows}

    assert rows == 259
    assert len(keys) == rows, "every real trade must be individually identifiable"


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_dropping_trade_id_would_destroy_real_trades(adapter) -> None:
    """The counterfactual, asserted so the reason for the design cannot be forgotten."""
    from dataclasses import replace

    keys_without = set()
    rows = 0
    for path in TRADEBOOKS:
        result = adapter.parse(open(path, "rb").read(), account_id=ACCOUNT)
        rows += result.parsed
        keys_without |= {
            make_dedupe_key(replace(s.transaction, source_ref=None)) for s in result.rows
        }
    assert rows - len(keys_without) == 16, "16 trades would vanish without trade_id"


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_real_exports_parse_without_rejections(adapter) -> None:
    """Real files, real columns. Every row is a clean equity trade."""
    for path in TRADEBOOKS:
        expected = sum(1 for _ in csv.DictReader(open(path)))
        result = adapter.parse(open(path, "rb").read(), account_id=ACCOUNT)
        assert result.parsed == expected
        assert result.rejected == 0
