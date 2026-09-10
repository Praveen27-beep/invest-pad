"""app/ingest/cas_pdf.py -- the CDSL/NSDL Consolidated Account Statement PDF adapter.

Most tests feed TEXT built from the real row shapes found in a real July-2026 CDSL
statement, not PDF bytes -- same reasoning as tests/test_zerodha_contract_note.py:
pdfplumber is slow, and the parsing logic (where bugs live) is independent of how the
bytes became text. The row shapes below (the ISIN-then-words-then-date layout, the
ISIN-omitted continuation row, the corporate-action phrase split across a settlement
reference number) are not invented -- each was found by actually opening the real
sample and is the reason its corresponding regex/classification logic exists at all.

One test at the bottom exercises the real PDF end to end and is gated on
PORTFOLIO_LOCAL_DOCS, exactly like the contract-note suite: it skips cleanly in any
environment without the file.
"""

from __future__ import annotations

import glob
import os
from datetime import date
from decimal import Decimal

import pytest
from app.engine.types import Source, TxnType
from app.ingest.base import CONFIDENCE_DERIVED
from app.ingest.cas_pdf import CasPdfAdapter, DeclaredHolding, _password_candidates

ACCOUNT = "11111111-1111-1111-1111-111111111111"

#: Real CAS PDFs stay OUT of the repository -- one investor's holdings and PAN. Point
#: this at a local folder to run the tests that need one; without it they skip.
LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")
CAS_FILES = sorted(glob.glob(f"{LOCAL_DOCS}/*CAS*.pdf") + glob.glob(f"{LOCAL_DOCS}/*cas*.pdf"))

MARKER = "CONSOLIDATED ACCOUNT STATEMENT (CAS) FOR SECURITIES HELD IN DEMAT FORM\n"

#: One clean corporate-action credit row, ISIN immediately before the date -- the
#: simple case (e.g. "ACTION CONSTRUCTION EQUIPMENTS LIMITED" in the real sample).
SPLIT_ROW = (
    "ACME WIDGETS LIMITED INTDEP-CR CM\n"
    "EQUITY SHARES - M51766 TM/CP\n"
    "INE000000001 28-07-2026 0.000 5.000 -- 5.000 0\n"
    "EQUITY SHARES OF RS. 2/- 13906 SETT\n"
    "AFTER SPLIT 1211232026139\n"
)

#: A BONUS credit, same shape.
BONUS_ROW = (
    "BETA CORP LIMITED PAYOUT-CR CM\n"
    "EQUITY SHARES M51766 TM/CP\n"
    "INE000000002 28-07-2026 100.000 20.000 -- 120.000 0\n"
    "EQUITY SHARES OF RS. 10/- 13906 SETT\n"
    "AFTER BONUS 1211232026140\n"
)

#: ISIN separated from the date by description words, and the "SUB DIVISION" phrase
#: split by an interposed settlement reference number -- both verified against the
#: real sample (Indian Energy Exchange, INE022Q01020).
WRAPPED_SPLIT_ROW = (
    "GAMMA EXCHANGE\n"
    "PAYOUT-CR CM\n"
    "LIMITED#NEW\n"
    "M51766 TM/CP\n"
    "INE000000003 EQUITY SHARES FACE 27-07-2026 36.000 495.000 -- 531.000 0\n"
    "13906 SETT\n"
    "VALUE RE. 1/- AFTER SUB\n"
    "1211232026138\n"
    "DIVISION\n"
)

#: A second event for the SAME security, ISIN omitted -- verified against the real
#: sample (EDELWEISS FINANCIAL SERVICES has two credit events in one statement; only
#: the first row carries the ISIN).
CONTINUATION_ROW = (
    "INTDEP-CR CM\n"
    "M51766 TM/CP\n"
    "29-07-2026 400.000 -- 410.000 0\n"
    "13906 SETT\n"
    "1211232026141\n"
)

#: A credit with no corporate-action wording anywhere nearby -- verified against the
#: real sample (INDIAMART INTERMESH, credited 1 share with no explanation in text).
UNEXPLAINED_CREDIT_ROW = (
    "DELTA HOLDINGS\n"
    "INTDEP-CR CM\n"
    "LIMITED # EQUITY SHARES M51766 TM/CP\n"
    "INE000000004 28-07-2026 0.000 1.000 -- 1.000 0\n"
    "13906 SETT\n"
    "1211232026142\n"
)

#: A decrease (opening > closing) -- e.g. a sale settlement or transfer-out. CAS
#: carries no price for this, so it must never become a Transaction.
DECREASE_ROW = "INE000000005 28-07-2026 50.000 -- 20.000 30.000 0\n"

#: Holdings ("Market Value") table rows for the same securities.
HOLDINGS_TABLE = (
    "ACME WIDGETS\n"
    "INE000000001 LIMITED - EQUITY SHARES OF RS. 2/- 5.000 -- -- -- 5.000 1070.1000 5,350.50\n"
    "AFTER SPLIT\n"
    "BETA CORP\n"
    "INE000000002 LIMITED - EQUITY SHARES 120.000 -- -- -- 120.000 50.0000 6,000.00\n"
)

MF_FOLIO_BLOCK = "Scheme Name : Example Fund - Direct Plan\nFolio No : 12345/0\n"

ONE_DP_SUMMARY = (
    "ZERODHA BROKING LIMITED\n"
    "CDSL Demat Account 2 12,75,726.20\n"
    "DP Id: 12081600 Client Id :46203315\n"
)

TWO_DP_SUMMARY = (
    "ZERODHA BROKING LIMITED\n"
    "CDSL Demat Account 2 12,75,726.20\n"
    "DP Id: 12081600 Client Id :46203315\n"
    "AXIS SECURITIES LIMITED\n"
    "NSDL Demat Account 1 500.00\n"
    "DP Id: IN304295 Client Id :95211973\n"
)

AS_ON_LINE = "Portfolio Value ` 12,75,726.20 as on 31-07-2026\n"


@pytest.fixture()
def adapter() -> CasPdfAdapter:
    return CasPdfAdapter(broker_accounts={"zerodha": "ACCT-ZERODHA"})


def parse(adapter: CasPdfAdapter, body: str, summary: str = ONE_DP_SUMMARY):
    text = MARKER + summary + AS_ON_LINE + body
    return adapter.parse_text(text, account_id="ACCT-FALLBACK")


# --- marker / not-a-CAS -----------------------------------------------------------


def test_non_cas_text_is_rejected() -> None:
    result = CasPdfAdapter().parse_text("just some random PDF text", account_id=ACCOUNT)
    assert result.parsed == 0
    assert result.rejected == 1
    assert "not a CAS" in result.rejections[0].reason


# --- classification: the whole point -----------------------------------------------


def test_a_split_credit_becomes_split_adj(adapter) -> None:
    result = parse(adapter, SPLIT_ROW)
    assert result.rejected == 0
    (staged,) = result.rows

    txn = staged.transaction
    assert txn.isin == "INE000000001"
    assert txn.txn_type is TxnType.SPLIT_ADJ
    assert txn.quantity == Decimal("5")
    assert txn.price == Decimal("0")
    assert txn.txn_date == date(2026, 7, 28)
    assert txn.source is Source.CAS
    assert txn.account_id == "ACCT-ZERODHA"
    assert staged.confidence == CONFIDENCE_DERIVED


def test_a_bonus_credit_becomes_bonus(adapter) -> None:
    (staged,) = parse(adapter, BONUS_ROW).rows
    assert staged.transaction.txn_type is TxnType.BONUS
    assert staged.transaction.quantity == Decimal("20")


def test_isin_separated_from_date_by_description_words_still_parses(adapter) -> None:
    """The row this regression pins (real ISIN INE022Q01020, Indian Energy Exchange)
    silently disappeared before this fix -- no row, no rejection, a straight data loss
    that violates base.py's VALIDATION-FIRST rule."""
    result = parse(adapter, WRAPPED_SPLIT_ROW)
    assert result.rejected == 0
    (staged,) = result.rows
    assert staged.transaction.isin == "INE000000003"
    assert staged.transaction.quantity == Decimal("495")
    assert staged.transaction.txn_type is TxnType.SPLIT_ADJ


def test_sub_division_split_by_a_settlement_number_is_still_recognised(adapter) -> None:
    """Same row as above: "AFTER SUB" / reference number / "DIVISION" must still read
    as one corporate-action phrase, not three unrelated tokens."""
    (staged,) = parse(adapter, WRAPPED_SPLIT_ROW).rows
    assert staged.transaction.txn_type is TxnType.SPLIT_ADJ


def test_isin_omitted_on_a_second_event_inherits_the_last_one(adapter) -> None:
    result = parse(adapter, SPLIT_ROW + CONTINUATION_ROW)
    assert result.rejected == 0
    assert len(result.rows) == 2
    first, second = (r.transaction for r in result.rows)
    assert first.isin == "INE000000001"
    assert second.isin == "INE000000001", "continuation row must inherit the last seen ISIN"
    assert second.quantity == Decimal("10")


def test_a_decrease_is_rejected_not_recorded_as_a_free_transfer(adapter) -> None:
    """CAS carries no price, so a decrease (sale settlement, transfer-out, buyback)
    must never be silently dropped OR silently staged -- rejected, with a reason."""
    result = parse(adapter, DECREASE_ROW)
    assert result.parsed == 0
    assert result.rejected == 1
    assert "not a credit" in result.rejections[0].reason


def test_a_credit_with_no_corporate_action_wording_is_rejected_not_guessed(adapter) -> None:
    result = parse(adapter, UNEXPLAINED_CREDIT_ROW)
    assert result.parsed == 0
    assert result.rejected == 1
    assert "not guessed" in result.rejections[0].reason


# --- holdings table: reconciliation data, not a Transaction ------------------------


def test_holdings_table_rows_are_not_double_counted_from_transaction_rows(adapter) -> None:
    """HOLDING_ROW and the Transaction Details row shape both start with an ISIN and
    end in decimal-looking tokens -- without excluding DATA_SUFFIX matches, every
    security would be reconciled twice, once from each table."""
    text = MARKER + ONE_DP_SUMMARY + AS_ON_LINE + SPLIT_ROW + BONUS_ROW + HOLDINGS_TABLE
    holdings = adapter._extract_holdings(text, "ACCT-ZERODHA")
    assert len(holdings) == 2
    by_isin = {h.isin: h for h in holdings}
    assert by_isin["INE000000001"].quantity == Decimal("5")
    assert by_isin["INE000000001"].market_value == Decimal("5350.50")
    assert by_isin["INE000000002"].quantity == Decimal("120")


def test_parse_declared_holdings_reads_the_as_of_date(adapter) -> None:
    text = MARKER + ONE_DP_SUMMARY + AS_ON_LINE + HOLDINGS_TABLE
    holdings = adapter.parse_declared_holdings(text.encode(), account_id="ACCT-ZERODHA")
    assert all(h.snap_date == date(2026, 7, 31) for h in holdings)
    assert all(isinstance(h, DeclaredHolding) for h in holdings)


def test_mf_folios_are_noted_not_parsed(adapter) -> None:
    result = parse(adapter, SPLIT_ROW + MF_FOLIO_BLOCK)
    assert any("mutual fund folio" in n for n in result.notes)


# --- multi-account resolution -------------------------------------------------------


def test_single_active_dp_resolves_via_broker_accounts(adapter) -> None:
    (staged,) = parse(adapter, SPLIT_ROW, summary=ONE_DP_SUMMARY).rows
    assert staged.transaction.account_id == "ACCT-ZERODHA"


def test_multiple_active_dps_fall_back_and_warn(adapter) -> None:
    result = parse(adapter, SPLIT_ROW, summary=TWO_DP_SUMMARY)
    (staged,) = result.rows
    assert staged.transaction.account_id == "ACCT-FALLBACK"
    assert any("could not be split per account" in n for n in result.notes)


def test_no_broker_accounts_map_falls_back_to_the_caller_account() -> None:
    plain = CasPdfAdapter()  # no broker_accounts at all
    (staged,) = parse(plain, SPLIT_ROW).rows
    assert staged.transaction.account_id == "ACCT-FALLBACK"


# --- PAN password candidates ---------------------------------------------------------


def test_password_candidates_try_upper_lower_asis_then_empty() -> None:
    assert _password_candidates("abCde1234f") == ["ABCDE1234F", "abcde1234f", "abCde1234f", ""]


def test_password_candidates_dedupe_when_already_uppercase() -> None:
    assert _password_candidates("ABCDE1234F") == ["ABCDE1234F", "abcde1234f", ""]


def test_password_candidates_include_empty_when_pan_is_blank() -> None:
    assert _password_candidates("") == [""]


# --- the real file, gated -----------------------------------------------------------


@pytest.mark.skipif(not CAS_FILES, reason="a real CAS PDF is not present")
def test_the_real_cas_pdf_unlocks_and_parses() -> None:
    """PORTFOLIO_LOCAL_DOCS points at a folder containing a real CAS PDF and the
    investor's real PAN -- set PORTFOLIO_LOCAL_DOCS and PORTFOLIO_LOCAL_PAN to run
    this against it. Everything else in this file runs everywhere with no fixture."""
    pan = os.environ.get("PORTFOLIO_LOCAL_PAN", "")
    for path in CAS_FILES:
        with open(path, "rb") as f:
            content = f.read()
        result = CasPdfAdapter(pan=pan).parse(content, account_id=ACCOUNT, filename=path)
        assert result.parsed + result.rejected > 0, f"{path}: nothing recognised at all"
        assert all(r.transaction.source is Source.CAS for r in result.rows)
        assert all(r.transaction.price == Decimal("0") for r in result.rows)
        assert all(
            r.transaction.txn_type in (TxnType.BONUS, TxnType.SPLIT_ADJ) for r in result.rows
        )
