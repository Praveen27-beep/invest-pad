"""Source precedence: which document wins when two describe the same trade.

The guard exists because dedupe_key does not catch cross-source duplicates. It is an
interim measure and every test here says so, because the moment the key is fixed most of
this should be deleted rather than maintained.
"""

from __future__ import annotations

import glob
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.db import imports, precedence, repository
from app.engine.types import Source, Transaction, TxnType
from app.ingest.zerodha_contract_note import ZerodhaContractNoteAdapter
from app.ingest.zerodha_tradebook import ZerodhaTradebookAdapter

#: Real broker documents stay OUT of the repo. Point this at them to run the tests
#: that need them; without it those tests skip.
LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")

pytestmark = pytest.mark.db

ACTOR = "22222222-2222-2222-2222-222222222222"
ISIN = "INE153T01027"

TRADEBOOK_CSV = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
    "BLS,INE153T01027,2026-08-12,NSE,EQ,EQ,buy,false,18.000000,2663.949951,"
    "1089300,99001,2026-08-12T12:19:40\n"
)

NOTE_TEXT = """CONTRACT NOTE CUM TAX INVOICE
Contract Note No: CNT-26/27-77963149
Trade Date: 12/08/2026
1786505400085603080 12:19:40 1089300 12:19:40 BLS-A/INE153T01027 B NSE 18 0.0000 2663.95 (47951.10)
Taxable value of Supply (Brokerage) (Rs)2 (0.01) (0.01)
Stamp duty (Rs) (7.00) (7.00)
"""


#: A literal, so the pure ranking tests need no database fixture.
ACCOUNT = "11111111-1111-1111-1111-111111111111"


def txn(source: Source, ref: str = "1089300", price: str = "2663.95") -> Transaction:
    return Transaction(
        isin=ISIN, txn_date=date(2026, 8, 12), txn_type=TxnType.BUY,
        quantity=Decimal("18"), price=Decimal(price),
        account_id=ACCOUNT, source=source, source_ref=ref,
    )


def seed_security(db):
    with db.cursor() as cur:
        cur.execute("INSERT INTO security (isin) VALUES (%s) ON CONFLICT DO NOTHING", (ISIN,))


def stage(db, adapter, investor, content, filename):
    return imports.stage_batch(
        db, adapter, content, investor_id=investor,
        account_id=os.environ["_TEST_ACCOUNT_ID"], filename=filename, investor_code="C001",
    )


def txn_count(db) -> int:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        return cur.fetchone()[0]


# --- the ranking ---------------------------------------------------------------


def test_a_contract_note_outranks_a_tradebook() -> None:
    """Because it carries charges and the tradebook does not."""
    assert precedence.rank(Source.CONTRACT_NOTE) < precedence.rank(Source.TRADEBOOK)


def test_an_unknown_source_ranks_last() -> None:
    """A document nobody has characterised must not silently outrank one that is."""
    assert precedence.rank("SOMETHING_NEW") == precedence.UNRANKED
    assert precedence.rank(None) == precedence.UNRANKED


def test_identity_ignores_price(dummy=None) -> None:
    """The whole rule depends on this.

    The tradebook exports 2663.949951 where the note prints 2663.95 -- one fill rendered
    by two systems. An identity including price would call them different trades.
    """
    a = precedence.trade_identity(txn(Source.TRADEBOOK, price="2663.949951"))
    b = precedence.trade_identity(txn(Source.CONTRACT_NOTE, price="2663.95"))
    assert a == b


def test_identity_needs_a_trade_number(dummy=None) -> None:
    """Without one there is nothing stable to match on, and guessing from price and
    quantity would collapse the genuinely distinct same-price fills Session 6 found."""
    anonymous = Transaction(
        isin=ISIN, txn_date=date(2026, 8, 12), txn_type=TxnType.BUY,
        quantity=Decimal("18"), price=Decimal("100"), account_id="acct", source_ref=None,
    )
    assert precedence.trade_identity(anonymous) is None


def test_same_source_is_left_to_the_dedupe_key() -> None:
    """Precedence arbitrates BETWEEN documents. Re-importing one file is the index's job."""
    decision = precedence.decide(txn(Source.TRADEBOOK), "TRADEBOOK", "some-id")
    assert decision.action == precedence.ACTION_INSERT


def test_every_decision_carries_a_reason() -> None:
    """Never a silent skip."""
    for existing in (None, "TRADEBOOK", "CONTRACT_NOTE", "MANUAL"):
        decision = precedence.decide(txn(Source.CONTRACT_NOTE), existing, "id")
        assert decision.reason.strip(), f"no reason given for existing={existing}"


# --- against the database ------------------------------------------------------


def test_a_tradebook_row_is_excluded_when_the_note_is_already_there(db, investor) -> None:
    seed_security(db)
    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)
    assert txn_count(db) == 1

    book = stage(db, ZerodhaTradebookAdapter(), investor, TRADEBOOK_CSV.encode(), "tb.csv")
    imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)

    assert txn_count(db) == 1, "the same trade must not be counted twice"
    (kept,) = repository.load_transactions(db, investor_id=investor)
    assert kept.source is Source.CONTRACT_NOTE
    assert kept.charges == Decimal("7.01"), "the charge-bearing row is the one kept"


def test_the_exclusion_is_recorded_not_silent(db, investor) -> None:
    seed_security(db)
    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)
    book = stage(db, ZerodhaTradebookAdapter(), investor, TRADEBOOK_CSV.encode(), "tb.csv")
    imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)

    with db.cursor() as cur:
        cur.execute(
            "SELECT status, reason FROM import_row WHERE batch_id = %s", (book["batch_id"],)
        )
        status, reason = cur.fetchone()
    assert status == "EXCLUDED"
    assert "1089300" in reason, "the reason names the trade"
    assert "CONTRACT_NOTE" in reason and "double-counting" in reason


def test_the_exclusion_is_audited_as_its_own_event(db, investor) -> None:
    """Somebody asking "why is this trade not in the ledger?" must be able to find out."""
    seed_security(db)
    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)
    book = stage(db, ZerodhaTradebookAdapter(), investor, TRADEBOOK_CSV.encode(), "tb.csv")
    imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)

    with db.cursor() as cur:
        cur.execute(
            "SELECT diff_json FROM audit_log WHERE action = %s", (imports.ACTION_ROWS_EXCLUDED,)
        )
        (diff,) = cur.fetchone()
    assert len(diff["excluded"]) == 1
    assert "1089300" in diff["excluded"][0]["reason"]


def test_a_note_arriving_later_supersedes_the_tradebook_row(db, investor) -> None:
    """The realistic order: tradebooks imported months ago, notes arriving now.

    The ledger is append-only, so the earlier row is REVERSED rather than deleted -- the
    correction pattern DATA_MODEL already specifies. Net position is unchanged and the
    charge-bearing row is the one that stands.
    """
    seed_security(db)
    book = stage(db, ZerodhaTradebookAdapter(), investor, TRADEBOOK_CSV.encode(), "tb.csv")
    imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)
    assert txn_count(db) == 1

    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)

    rows = repository.load_transactions(db, investor_id=investor)
    assert len(rows) == 3, "original + reversal + replacement"

    net = sum(
        (r.quantity if r.txn_type is TxnType.BUY else -r.quantity) for r in rows
    )
    assert net == Decimal("18"), "the reversal cancels the original exactly"
    assert sum(r.charges for r in rows) == Decimal("7.01"), "charges arrive with the note"


def test_the_supersession_is_recorded(db, investor) -> None:
    seed_security(db)
    book = stage(db, ZerodhaTradebookAdapter(), investor, TRADEBOOK_CSV.encode(), "tb.csv")
    imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)
    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)

    with db.cursor() as cur:
        cur.execute(
            "SELECT status, reason FROM import_row WHERE batch_id = %s", (note["batch_id"],)
        )
        status, reason = cur.fetchone()
    assert status == "SUPERSEDED"
    assert "reversed and replaced" in reason


def test_a_reversal_explains_itself(db, investor) -> None:
    seed_security(db)
    book = stage(db, ZerodhaTradebookAdapter(), investor, TRADEBOOK_CSV.encode(), "tb.csv")
    imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)
    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)

    reversal = next(
        r for r in repository.load_transactions(db, investor_id=investor)
        if str(r.source_ref).startswith("REVERSAL-")
    )
    assert reversal.txn_type is TxnType.SELL
    assert reversal.source is Source.MANUAL
    assert "superseded" in reversal.raw_payload["reason"]


def test_unrelated_trades_are_untouched(db, investor) -> None:
    """The guard must only fire on the actual overlap."""
    seed_security(db)
    note = stage(db, ZerodhaContractNoteAdapter(), investor, NOTE_TEXT.encode(), "note.txt")
    imports.promote_batch(db, note["batch_id"], actor_uid=ACTOR)

    other = TRADEBOOK_CSV.replace("1089300,99001", "7777777,99002").replace(
        "2026-08-12,NSE", "2026-08-11,NSE"
    )
    book = stage(db, ZerodhaTradebookAdapter(), investor, other.encode(), "tb.csv")
    summary = imports.promote_batch(db, book["batch_id"], actor_uid=ACTOR)

    assert summary.inserted == 1, "a different trade is not an overlap"
    assert txn_count(db) == 2


# --- the real files ------------------------------------------------------------


@pytest.mark.skipif(
    not glob.glob(f"{LOCAL_DOCS}/[Cc]ontract note*.pdf"),
    reason="real documents not present",
)
def test_the_real_overlap_does_not_double_count(db, investor) -> None:
    """The 146 shared trades, end to end through the database.

    Without this guard both sources import in full and every shared trade lands twice.
    """
    notes = sorted(glob.glob(f"{LOCAL_DOCS}/[Cc]ontract note*.pdf"))
    books = sorted(
        glob.glob(f"{LOCAL_DOCS}/tradebook-*-EQ*.csv")
    )
    if not books:
        pytest.skip("tradebooks not present")

    for path in notes:
        try:
            batch = stage(db, ZerodhaContractNoteAdapter(), investor,
                          Path(path).read_bytes(), Path(path).name)
        except imports.DuplicateUploadError:
            # Contract note39 and note40 are byte-identical. The hash catches it, which is
            # the outer defence working exactly as intended.
            continue
        imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)
    after_notes = txn_count(db)

    excluded = 0
    for path in books:
        batch = stage(db, ZerodhaTradebookAdapter(), investor,
                      Path(path).read_bytes(), Path(path).name)
        imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM import_row WHERE batch_id = %s AND status = 'EXCLUDED'",
                (batch["batch_id"],),
            )
            excluded += cur.fetchone()[0]

    assert excluded == 146, "exactly the known overlap, excluded rather than duplicated"
    assert txn_count(db) == after_notes + (259 - 146), "each trade in the ledger once"
