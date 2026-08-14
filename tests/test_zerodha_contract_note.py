"""The Zerodha contract-note PDF adapter.

Contract notes are the only document carrying charges, so this adapter is what stops a
cost basis being understated by exactly the brokerage, STT, GST and stamp duty.

Most tests feed TEXT rather than PDF bytes: pdfplumber is slow, and the parsing logic --
which is where bugs live -- is independent of how the bytes became text.
"""

from __future__ import annotations

import glob
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.dedupe import make_dedupe_key
from engine.types import Source, TxnType
from ingest.base import CONFIDENCE_CERTAIN, CONFIDENCE_DERIVED
from ingest.zerodha_contract_note import (
    ISIN_PATTERN,
    ZerodhaContractNoteAdapter,
    parse_charges,
)

ACCOUNT = "11111111-1111-1111-1111-111111111111"

#: Real broker documents stay OUT of the repository -- they are one investor's financial
#: history. Point this at a local folder to run the tests that need them; without it they
#: skip. See .gitignore.
LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")

NOTES = sorted(glob.glob(f"{LOCAL_DOCS}/[Cc]ontract note*.pdf"))

HEADER = """CONTRACT NOTE CUM TAX INVOICE
Zerodha Broking Limited
SEBI registration: INZ000031633
Contract Note No: CNT-26/27-77963149
Trade Date: 12/08/2026 Settlement No: 2026151
Order No. Order Time Trade No. Trade Time Security / Contract Description Buy(B) /
"""

TRADE = (
    "1786505400085603080 12:19:40 1089300 12:19:40 WAAREEENER-A/INE377N01017 B BSE 18 "
    "0.0000 2663.95 (47951.10)\n"
)

CHARGES = """Pay in/Pay out obligation (Rs) (47951.10) 0.00 (47951.10)
Taxable value of Supply (Brokerage) (Rs)2 (0.01) (0.01)
IGST (@18% of Brok, SEBI, Trans & Clearing Charges) (Rs)3 (0.33) (0.33)
SEBI turnover fees (Rs) (0.05) (0.05)
Stamp duty (Rs) (7.00) (7.00)
"""


@pytest.fixture()
def adapter() -> ZerodhaContractNoteAdapter:
    return ZerodhaContractNoteAdapter()


def parse(adapter, body: str = TRADE, charges: str = CHARGES):
    return adapter.parse_text(HEADER + body + charges, account_id=ACCOUNT)


# --- happy path ----------------------------------------------------------------


def test_a_trade_row_becomes_a_transaction(adapter) -> None:
    result = parse(adapter)
    assert result.rejected == 0
    (staged,) = result.rows

    txn = staged.transaction
    assert txn.isin == "INE377N01017"
    assert txn.txn_type is TxnType.BUY
    assert txn.txn_date == date(2026, 8, 12)
    assert txn.quantity == Decimal("18")
    assert txn.price == Decimal("2663.95")
    assert txn.source is Source.CONTRACT_NOTE


def test_source_ref_is_the_trade_number(adapter) -> None:
    """The same identifier the tradebook calls trade_id, so one trade has one identity."""
    (staged,) = parse(adapter).rows
    assert staged.transaction.source_ref == "1089300"


def test_a_sell_maps_to_sell(adapter) -> None:
    (staged,) = parse(adapter, TRADE.replace(" B BSE ", " S BSE ")).rows
    assert staged.transaction.txn_type is TxnType.SELL


def test_the_older_layout_still_parses(adapter) -> None:
    """Zerodha changed the format between 2023 and 2026, and clients hold both."""
    older = HEADER.replace("Trade Date: 12/08/2026", "Tradedate: 07/09/2023").replace(
        "Contract Note No:", "ContractNoteno.:"
    )
    result = adapter.parse_text(older + TRADE + CHARGES, account_id=ACCOUNT)
    assert result.parsed == 1
    assert result.rows[0].transaction.txn_date == date(2023, 9, 7)


# --- charges, which is the whole point -----------------------------------------


def test_charges_are_read_and_attached(adapter) -> None:
    """0.01 brokerage + 0.33 IGST + 0.05 SEBI + 7.00 stamp = 7.39."""
    (staged,) = parse(adapter).rows
    assert staged.transaction.charges == Decimal("7.39")


def test_every_charge_component_is_recognised() -> None:
    charges = parse_charges(
        "Taxable value of Supply (Brokerage) (Rs)2 (1.00) "
        "Securities transaction tax (Rs) (2.00) "
        "Exchange transaction charges (Rs) (3.00) "
        "IGST (@18%) (Rs)3 (4.00) SEBI turnover fees (Rs) (5.00) Stamp duty (Rs) (6.00)"
    )
    assert charges == {
        "brokerage": Decimal("1.00"), "stt": Decimal("2.00"), "exchange": Decimal("3.00"),
        "igst": Decimal("4.00"), "sebi": Decimal("5.00"), "stamp": Decimal("6.00"),
    }


def test_charges_are_apportioned_by_turnover(adapter) -> None:
    """One note, two trades of unequal size. The bigger trade carries more of the cost."""
    second = (
        "1786505400085603081 12:20:00 1089301 12:20:00 BLS-A/INE153T01027 B NSE 6 "
        "0.0000 2663.95 (15983.70)\n"
    )
    rows = parse(adapter, TRADE + second).rows
    assert len(rows) == 2
    big, small = rows[0].transaction, rows[1].transaction

    assert big.charges + small.charges == Decimal("7.39"), "apportionment loses nothing"
    assert big.charges > small.charges, "18 shares carries more than 6"
    assert big.charges / small.charges == pytest.approx(3, abs=0.1)


def test_apportionment_sums_to_exactly_the_stated_total(adapter) -> None:
    """The last row absorbs the rounding remainder.

    Otherwise a portfolio reconciled against the note is out by a few paise for no reason.
    """
    rows = parse(
        adapter,
        "".join(
            f"178650540008560308{i} 12:2{i}:00 108930{i} 12:2{i}:00 BLS-A/INE153T01027 "
            f"B NSE 7 0.0000 100.00 (700.00)\n"
            for i in range(3)
        ),
    ).rows
    assert sum(r.transaction.charges for r in rows) == Decimal("7.39")


def test_rows_are_derived_not_certain(adapter) -> None:
    """Charges were apportioned, not read per trade. The score has to say so."""
    (staged,) = parse(adapter).rows
    assert staged.confidence == CONFIDENCE_DERIVED
    assert staged.confidence < CONFIDENCE_CERTAIN


def test_a_note_with_no_charge_lines_says_so(adapter) -> None:
    result = parse(adapter, charges="")
    assert result.rows[0].transaction.charges == Decimal("0")
    assert any("NO CHARGE LINES FOUND" in n for n in result.notes)


def test_the_note_records_what_was_apportioned(adapter) -> None:
    joined = " ".join(parse(adapter).notes)
    assert "7.39" in joined
    assert "brokerage" in joined and "stamp" in joined


# --- the ISIN prefix fix -------------------------------------------------------


def test_the_brokers_sebi_registration_is_not_an_isin() -> None:
    """INZ000031633 is printed on every note and matches a naive ^IN[A-Z0-9]{10}$.

    Without the INE/INF narrowing, every contract note would produce a phantom security
    named after the broker's licence.
    """
    assert not ISIN_PATTERN.match("INZ000031633")
    assert ISIN_PATTERN.match("INE377N01017")
    assert ISIN_PATTERN.match("INF732E01037"), "mutual fund ISINs are INF"


def test_a_row_carrying_a_non_security_isin_is_rejected(adapter) -> None:
    bad = TRADE.replace("INE377N01017", "INZ000031633")
    result = adapter.parse_text(HEADER + bad + CHARGES, account_id=ACCOUNT)
    assert result.parsed == 0
    assert "not a security ISIN" in result.rejections[0].reason


# --- validation-first ----------------------------------------------------------


def test_a_file_that_is_not_a_contract_note_is_refused(adapter) -> None:
    result = adapter.parse_text("Some other document entirely", account_id=ACCOUNT)
    assert "not a contract note" in result.rejections[0].reason


def test_a_note_without_a_trade_date_is_refused_whole(adapter) -> None:
    """A transaction needs a date. Guessing one would be inventing financial data."""
    result = adapter.parse_text(
        HEADER.replace("Trade Date: 12/08/2026", "") + TRADE, account_id=ACCOUNT
    )
    assert result.parsed == 0
    assert "no trade date" in result.rejections[0].reason


def test_a_bad_row_does_not_cost_the_good_ones(adapter) -> None:
    good = TRADE
    bad = TRADE.replace("INE377N01017", "INZ000031633").replace("1089300", "1089399")
    result = adapter.parse_text(HEADER + good + bad + CHARGES, account_id=ACCOUNT)
    assert result.parsed == 1
    assert result.rejected == 1


def test_rejections_carry_a_line_number(adapter) -> None:
    bad = TRADE.replace("INE377N01017", "INZ000031633")
    result = adapter.parse_text(HEADER + bad + CHARGES, account_id=ACCOUNT)
    assert result.rejections[0].row_number > 0


def test_unreadable_bytes_are_refused(adapter) -> None:
    assert adapter.parse(b"\xff\xfe\x00garbage", account_id=ACCOUNT).parsed == 0


# --- against the 40 real notes -------------------------------------------------


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_every_real_note_parses(adapter) -> None:
    """40 real PDFs spanning both layouts, 2023 to 2026. No rejections."""
    parsed = rejected = 0
    for path in NOTES:
        result = adapter.parse(Path(path).read_bytes(), account_id=ACCOUNT)
        assert result.rejected == 0, f"{Path(path).name}: {result.rejections[:2]}"
        parsed += result.parsed
        rejected += result.rejected
    assert parsed == 208
    assert rejected == 0


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_real_notes_supply_the_charges_a_tradebook_lacks(adapter) -> None:
    """The reason this adapter exists."""
    total = Decimal("0")
    with_charges = 0
    for path in NOTES:
        result = adapter.parse(Path(path).read_bytes(), account_id=ACCOUNT)
        note_total = sum((r.transaction.charges for r in result.rows), Decimal("0"))
        if note_total > 0:
            with_charges += 1
            total += note_total
    # Pinned to the real figures. An earlier charge pattern stopped at the "(Rs)"
    # currency marker sitting between label and value, silently reading 0 for most notes
    # -- 25 of 40 instead of 38, and 2759.69 instead of 8278.12. A charge that quietly
    # becomes zero understates cost basis and nothing else complains, so the numbers are
    # asserted rather than bounded.
    assert with_charges == 38
    assert total == Decimal("8278.12")


# --- THE FINDING: cross-source duplicates are NOT caught -----------------------


@pytest.mark.skipif(not NOTES, reason="real contract notes not present")
def test_the_same_trade_from_two_sources_does_not_currently_dedupe(adapter) -> None:
    """PINS A KNOWN, UNRESOLVED RISK. Importing both sources double-counts.

    146 of these trades appear in BOTH the tradebook exports and the contract notes. Their
    dedupe keys differ, so importing both would insert each of them twice.

    Two independent causes, and BOTH have to be fixed for the collision to work:

      1. `source` is part of the key (DATA_MODEL says so), and the two rows carry
         TRADEBOOK vs CONTRACT_NOTE.
      2. Prices differ in precision -- the tradebook exports 43.119999 where the note
         prints 43.12 -- so even with `source` removed the keys would still differ.

    `engine/dedupe.py`'s own docstring claims these should collide. They do not. This test
    asserts the CURRENT behaviour so the gap is visible; when the key is fixed this test
    will fail and should be inverted.
    """
    from ingest.zerodha_tradebook import ZerodhaTradebookAdapter

    tradebooks = sorted(
        glob.glob(f"{LOCAL_DOCS}/tradebook-*-EQ*.csv")
    )
    if not tradebooks:
        pytest.skip("tradebooks not present")

    tb = {}
    for path in tradebooks:
        for staged in ZerodhaTradebookAdapter().parse(
            Path(path).read_bytes(), account_id=ACCOUNT
        ).rows:
            tb[staged.transaction.source_ref] = staged.transaction

    cn = {}
    for path in NOTES:
        for staged in adapter.parse(Path(path).read_bytes(), account_id=ACCOUNT).rows:
            cn[staged.transaction.source_ref] = staged.transaction

    shared = set(tb) & set(cn)
    assert len(shared) == 146, "the same 146 trades are described by both sources"

    colliding = sum(1 for t in shared if make_dedupe_key(tb[t]) == make_dedupe_key(cn[t]))
    assert colliding == 0, (
        "KNOWN GAP: none of the 146 shared trades dedupe across sources. "
        "If this now fails, the key was fixed - invert this assertion."
    )
