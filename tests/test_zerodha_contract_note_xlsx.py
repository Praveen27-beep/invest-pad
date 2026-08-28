"""app/ingest/zerodha_contract_note_xlsx.py -- Zerodha contract notes exported as
XLSX, the historical-backfill path for XIRR (price AND charges, unlike tradebook CSV
which has no charges, and unlike CAS which has no price at all).

Two real shapes, both built here as small in-memory openpyxl workbooks that mirror the
real cell layout exactly -- including the layout quirk this suite exists to pin: the
bulk shape's charges sub-table is NOT column-aligned with its trades table ("NET
TOTAL" sits at a different column index than the trades header's own "Net Total
(Before Levies)" column). That mismatch silently zeroed every charge before it was
found and fixed; TEST_CHARGE_NET_TOTAL_COL below deliberately differs from
TEST_TRADE_NET_TOTAL_COL to keep it pinned.

A PORTFOLIO_LOCAL_DOCS-gated suite at the bottom runs the real YSL473_*.xlsx exports
and the clean-format sample end to end, same convention as
tests/test_zerodha_contract_note.py and tests/test_cas_pdf.py.
"""

from __future__ import annotations

import glob
import os
from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from app.engine.types import Source, TxnType
from app.ingest.base import CONFIDENCE_DERIVED
from app.ingest.zerodha_contract_note_xlsx import (
    ZerodhaContractNoteXlsxAdapter,
    classify_charge_label,
)

ACCOUNT = "11111111-1111-1111-1111-111111111111"

LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")
BULK_FILES = sorted(glob.glob(f"{LOCAL_DOCS}/YSL473_*.xlsx"))
CLEAN_FILES = sorted(glob.glob(f"{LOCAL_DOCS}/ContractNote_*.xlsx"))

#: Column layout for the synthetic bulk-shape sheets below, matching the real export's
#: 14-column header exactly (0-indexed).
TRADE_HEADER = [
    "Order No.", "Order Time.", "Trade No.", "Trade Time", "Security/Contract Description",
    "Buy(B) / Sell(S)", "Quantity", "Exchange", "Gross Rate / Trade Price Per Unit (Rs)",
    "Brokerage per Unit (Rs)", "Net Rate per Unit (Rs)",
    "Closing Rate per Unit (Only for Derivatives) (Rs)", "Net Total (Before Levies) (Rs)",
    "Remarks",
]
TRADE_NET_TOTAL_COL = 12

#: The charges sub-table's own "NET TOTAL" column -- deliberately DIFFERENT from
#: TRADE_NET_TOTAL_COL, matching the real export's column-misaligned layout.
CHARGE_NET_TOTAL_COL = 11


def _bulk_workbook(
    sheet_name: str,
    trade_date: str,
    contract_no: str,
    trades: list[tuple[str, str, str, int, float, str]],
    charges: dict[str, float],
) -> bytes:
    """One sheet, shaped like the real bulk export. ``trades`` is
    (order_no, trade_no, description, qty, price, side)."""
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name

    ws.append(["CONTRACT NOTE CUM TAX INVOICE"])
    ws.append(["Zerodha Broking Limited"])
    ws.append([])
    ws.append(["CONTRACT NOTE NO: ", None, None, contract_no])
    ws.append(["Trade Date:", None, None, trade_date, None, None, None, "Settlement No."])
    ws.append([])
    ws.append(TRADE_HEADER)
    for order_no, trade_no, description, qty, price, side in trades:
        row = [None] * len(TRADE_HEADER)
        row[0], row[2] = order_no, trade_no
        row[4], row[5] = description, side
        row[6], row[7] = qty, "NSE"
        row[8] = price
        row[TRADE_NET_TOTAL_COL] = -(qty * price) if side == "B" else qty * price
        ws.append(row)
    ws.append([])
    charge_header = [None] * 14
    charge_header[CHARGE_NET_TOTAL_COL] = "NET TOTAL"
    ws.append(charge_header)
    for label, amount in charges.items():
        row = [None] * 14
        row[0] = label
        row[CHARGE_NET_TOTAL_COL] = -amount
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _clean_workbook(
    trade_date: str,
    contract_no: str,
    trades: list[tuple[str, str, str, int, float]],
    charges: dict[str, float],
) -> bytes:
    """(isin, symbol, side, qty, price) per trade -- the clean shape's own columns."""
    import io

    wb = openpyxl.Workbook()
    trades_ws = wb.active
    trades_ws.title = "Trades"
    trades_ws.append(["Trades"])
    trades_ws.append([])
    trades_ws.append(["ISIN", "Symbol", "Side", "Exchange", "Quantity", "Price / WAP (₹)"])
    for isin, symbol, side, qty, price in trades:
        trades_ws.append([isin, symbol, side, "NSE", qty, price])

    charges_ws = wb.create_sheet("Charges & Net")
    charges_ws.append(["Charge", "Amount (₹)"])
    for label, amount in charges.items():
        charges_ws.append([label, amount])

    details_ws = wb.create_sheet("Note Details")
    details_ws.append(["Contract Note No.", contract_no])
    details_ws.append(["Trade date", trade_date])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def adapter() -> ZerodhaContractNoteXlsxAdapter:
    return ZerodhaContractNoteXlsxAdapter()


# --- charge-label classification, all three real vocabularies ----------------------


@pytest.mark.parametrize(
    ("label", "bucket"),
    [
        ("Brokerage", "brokerage"),
        ("Brokerage (taxable value)", "brokerage"),
        ("Securities transaction tax", "stt"),
        ("Securities transaction tax (STT)", "stt"),
        ("Exchange Transaction Charges", "exchange"),
        ("Exchange transaction charges", "exchange"),
        ("Integrated GST  (@18% of Brokerage, SEBI and Transaction Charges)", "igst"),
        ("IGST @18%", "igst"),
        ("Central GST  (@9% of Brokerage, SEBI and Transaction Charges)", "cgst"),
        ("State GST  (@9% of Brokerage, SEBI and Transaction Charges)", "sgst"),
        ("SEBI Turnover Fees", "sebi"),
        ("SEBI turnover fees", "sebi"),
        ("Stamp Duty", "stamp"),
        ("Stamp duty", "stamp"),
    ],
)
def test_every_real_label_variant_classifies_correctly(label, bucket) -> None:
    assert classify_charge_label(label) == bucket


def test_clearing_charges_is_not_a_recognised_bucket() -> None:
    """Always 0 for equity in every real sample -- absent from _CHARGE_RULES on
    purpose, matching the PDF adapter's behaviour of only summing named buckets."""
    assert classify_charge_label("Clearing Charges") is None


def test_totals_and_boilerplate_rows_are_not_charges() -> None:
    assert classify_charge_label("PAY IN / PAY OUT OBLIGATION") is None
    assert classify_charge_label("Net amount Receivable by Client / (Payable by Client)") is None


def test_igst_wins_over_the_word_brokerage_inside_its_own_label() -> None:
    """The real label mentions "Brokerage" and "SEBI" only as the rate-basis
    explanation for IGST -- must classify as igst, not brokerage or sebi."""
    label = "Integrated GST  (@18% of Brokerage, SEBI and Transaction Charges)"
    assert classify_charge_label(label) == "igst"


# --- bulk shape ----------------------------------------------------------------


def test_a_bulk_sheet_trade_row_becomes_a_transaction(adapter) -> None:
    content = _bulk_workbook(
        "19-10-2022",
        "19-10-2022",
        "CNT-22/23-131746361",
        trades=[("1666150200002063664", "14476900", "GUJTHEM - X / INE942C01029", 100, 714.0, "B")],
        charges={"Brokerage": 0.01, "Securities transaction tax": 71.0},
    )
    result = adapter.parse(content, account_id=ACCOUNT)
    assert result.rejected == 0
    (staged,) = result.rows
    txn = staged.transaction
    assert txn.isin == "INE942C01029"
    assert txn.txn_type is TxnType.BUY
    assert txn.txn_date == date(2022, 10, 19)
    assert txn.quantity == Decimal("100")
    assert txn.price == Decimal("714.0")
    assert txn.source is Source.CONTRACT_NOTE
    assert txn.source_ref == "14476900"
    assert staged.confidence == CONFIDENCE_DERIVED


def test_bulk_charges_read_from_the_charges_sub_tables_own_column_not_the_trades_one(
    adapter,
) -> None:
    """Regression: the charges sub-table's "NET TOTAL" column sits at a DIFFERENT
    index than the trades table's "Net Total (Before Levies)" column on the real
    export. Reading charge amounts from the trades header's column silently zeroed
    every charge -- this pins the fix."""
    content = _bulk_workbook(
        "19-10-2022", "19-10-2022", "CNT-1",
        trades=[("1", "100", "GUJTHEM - X / INE942C01029", 100, 714.0, "B")],
        charges={"Brokerage": 0.01, "Securities transaction tax": 71.0, "Stamp Duty": 11.0},
    )
    (staged,) = adapter.parse(content, account_id=ACCOUNT).rows
    assert staged.transaction.charges == Decimal("82.01")
    assert staged.transaction.stt == Decimal("71.0")


def test_trade_no_is_the_identity_not_order_no(adapter) -> None:
    """Verified against the real busy 31-01-2023 sheet: one Order No. covers several
    Trade No. fills at different prices. source_ref must be the trade number."""
    content = _bulk_workbook(
        "31-01-2023", "31-01-2023", "CNT-1",
        trades=[
            ("SAME_ORDER", "T1", "ADANIGREEN - EQ / INE364U01010", 6, 1200.0, "B"),
            ("SAME_ORDER", "T2", "ADANIGREEN - EQ / INE364U01010", 5, 1200.0, "B"),
        ],
        charges={"Brokerage": 1.0},
    )
    rows = adapter.parse(content, account_id=ACCOUNT).rows
    assert {r.transaction.source_ref for r in rows} == {"T1", "T2"}


def test_charges_are_apportioned_by_turnover_and_sum_exactly(adapter) -> None:
    content = _bulk_workbook(
        "01-01-2024", "01-01-2024", "CNT-1",
        trades=[
            ("1", "T1", "GUJTHEM - X / INE942C01029", 18, 2663.95, "B"),
            ("2", "T2", "BLS - EQ / INE153T01027", 6, 2663.95, "B"),
        ],
        charges={"Brokerage": 7.39},
    )
    rows = adapter.parse(content, account_id=ACCOUNT).rows
    big, small = rows[0].transaction, rows[1].transaction
    assert big.charges + small.charges == Decimal("7.39")
    assert big.charges > small.charges


def test_an_options_contract_description_is_rejected_not_guessed(adapter) -> None:
    """Verified against a real F&O row in the 2024-25 export -- no ISIN, so it must
    never become a phantom equity security."""
    content = _bulk_workbook(
        "12-08-2024", "12-08-2024", "CNT-1",
        trades=[("1", "T1", "ADANIENT24AUG3050PE", 1, 10.0, "B")],
        charges={},
    )
    result = adapter.parse(content, account_id=ACCOUNT)
    assert result.parsed == 0
    assert result.rejected == 1


def test_the_date_range_note_covers_every_recognised_day(adapter) -> None:
    import io

    wb = openpyxl.Workbook()
    del wb["Sheet"]
    for name, trade_date in [("19-10-2022", "19-10-2022"), ("29-03-2023", "29-03-2023")]:
        ws = wb.create_sheet(name)
        ws.append(["CONTRACT NOTE NO: ", None, None, "CNT-X"])
        ws.append(["Trade Date:", None, None, trade_date])
        ws.append(TRADE_HEADER)
        row = [None] * len(TRADE_HEADER)
        row[0], row[2], row[4], row[5], row[6], row[8] = (
            "1", "T1", "GUJTHEM - X / INE942C01029", "B", 1, 100.0,
        )
        row[TRADE_NET_TOTAL_COL] = -100.0
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)

    result = adapter.parse(buf.getvalue(), account_id=ACCOUNT)
    assert any("2022-10-19 to 2023-03-29" in n for n in result.notes)


def test_a_sheet_with_no_recognisable_header_is_rejected_by_name(adapter) -> None:
    import io

    wb = openpyxl.Workbook()
    wb.active.title = "Not A Trading Day"
    wb.active.append(["just some unrelated text"])
    buf = io.BytesIO()
    wb.save(buf)

    result = adapter.parse(buf.getvalue(), account_id=ACCOUNT)
    assert result.parsed == 0
    assert result.rejected == 1
    assert "Not A Trading Day" in result.rejections[0].reason


# --- clean shape -----------------------------------------------------------------


def test_clean_shape_trades_use_the_isin_and_symbol_columns_directly(adapter) -> None:
    content = _clean_workbook(
        "31-07-2026", "CNT-26/27-69548230",
        trades=[
            ("INE322A01010", "GILLETTE", "BUY", 1, 7724.0),
            ("INE022Q01020", "IEX", "BUY", 20, 133.05),
        ],
        charges={"Brokerage (taxable value)": 0.01, "Securities transaction tax (STT)": 13.0},
    )
    result = adapter.parse(content, account_id=ACCOUNT)
    assert result.rejected == 0
    assert len(result.rows) == 2
    first = result.rows[0].transaction
    assert first.isin == "INE322A01010"
    assert first.txn_type is TxnType.BUY
    assert first.txn_date == date(2026, 7, 31)
    assert first.source is Source.CONTRACT_NOTE


def test_clean_shape_sell_side_is_the_full_word_not_a_single_letter(adapter) -> None:
    """The clean shape spells the side out ("BUY"/"SELL"), unlike the bulk shape's
    single letter -- verified against the real ContractNote_31Jul2026_Parasu.xlsx."""
    content = _clean_workbook(
        "31-07-2026", "CNT-1",
        trades=[("INE322A01010", "GILLETTE", "SELL", 1, 100.0)],
        charges={},
    )
    (staged,) = adapter.parse(content, account_id=ACCOUNT).rows
    assert staged.transaction.txn_type is TxnType.SELL


def test_clean_shape_charges_reconcile_to_the_stated_total(adapter) -> None:
    content = _clean_workbook(
        "31-07-2026", "CNT-1",
        trades=[
            ("INE322A01010", "GILLETTE", "BUY", 1, 7724.0),
            ("INE022Q01020", "IEX", "BUY", 20, 133.05),
        ],
        charges={
            "Brokerage (taxable value)": 0.01,
            "Exchange transaction charges": 0.42,
            "IGST @18%": 0.08,
            "Securities transaction tax (STT)": 13.0,
            "SEBI turnover fees": 0.01,
            "Stamp duty": 2.0,
        },
    )
    rows = adapter.parse(content, account_id=ACCOUNT).rows
    total = sum((r.transaction.charges for r in rows), Decimal("0"))
    assert total == Decimal("15.52")


# --- the real files, gated ---------------------------------------------------------


@pytest.mark.skipif(not BULK_FILES, reason="real Console contract-note exports not present")
def test_the_real_bulk_exports_parse_with_real_charges() -> None:
    adapter = ZerodhaContractNoteXlsxAdapter()
    for path in BULK_FILES:
        with open(path, "rb") as f:
            content = f.read()
        result = adapter.parse(content, account_id=ACCOUNT, filename=path)
        assert result.parsed > 0, f"{path}: nothing recognised at all"
        # Regression guard for the column-misalignment bug: every real note in this
        # project carries nonzero brokerage/STT, so an all-zero result means the
        # charges column drifted again, not that this particular note was free.
        assert any(r.transaction.charges > 0 for r in result.rows), f"{path}: no charges read"
        assert all(r.transaction.source is Source.CONTRACT_NOTE for r in result.rows)


@pytest.mark.skipif(not CLEAN_FILES, reason="real clean-format contract note not present")
def test_the_real_clean_format_note_parses() -> None:
    adapter = ZerodhaContractNoteXlsxAdapter()
    for path in CLEAN_FILES:
        with open(path, "rb") as f:
            content = f.read()
        result = adapter.parse(content, account_id=ACCOUNT, filename=path)
        assert result.parsed > 0
        assert all(r.transaction.charges > 0 for r in result.rows)
