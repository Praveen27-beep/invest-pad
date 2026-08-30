"""Staged imports against the real Console exports and a real database.

The session gate lives here: the real files load to a known count, and re-uploading them
inserts zero.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest
from app.db import imports
from app.ingest.zerodha_tradebook import ZerodhaTradebookAdapter
from app.storage.local import SIGNING_SECRET_ENV, LocalDocumentStore

pytestmark = pytest.mark.db

#: Real broker documents stay OUT of the repository -- they are one investor's financial
#: history. Point this at a local folder to run the tests that need them; without it they
#: skip. See .gitignore.
LOCAL_DOCS = os.environ.get("PORTFOLIO_LOCAL_DOCS", "")

TRADEBOOKS = sorted(glob.glob(f"{LOCAL_DOCS}/tradebook-*-EQ*.csv"))

#: What the four Console exports on disk actually contain.
#:
#: BUILD_PLAN states the gate as 324 across FIVE exports. Only four exist here: they span
#: 2022-10-19 to 2026-01-28, and the FY2026-27 file -- which holds the remaining ~65 trades,
#: including all 25 KDL rows -- is absent. 324 is a real number, cross-checked against the
#: contract notes; it simply lives partly in a file nobody has downloaded yet. Drop that
#: export in and change this constant; nothing else needs to move.
EXPECTED_TRADEBOOK_ROWS = 259

ACTOR = "22222222-2222-2222-2222-222222222222"


@pytest.fixture()
def adapter() -> ZerodhaTradebookAdapter:
    return ZerodhaTradebookAdapter()


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalDocumentStore:
    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")
    return LocalDocumentStore(tmp_path / "objects")


CSV = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
    "BLS,INE153T01027,2024-01-10,NSE,EQ,EQ,buy,false,100.000000,200.500000,"
    "12345,99001,2024-01-10T10:15:00\n"
)


def stage(db, adapter, investor, content=None, filename="tradebook.csv", store=None):
    import os

    content = CSV.encode() if content is None else content

    return imports.stage_batch(
        db,
        adapter,
        content,
        investor_id=investor,
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        filename=filename,
        store=store,
        investor_code="C001",
    )


def txn_count(db) -> int:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        return cur.fetchone()[0]


# --- the never-auto-commit rule ------------------------------------------------


def test_staging_writes_nothing_to_the_ledger(db, adapter, investor) -> None:
    """The whole point of staging. An adapter must not be able to reach the ledger."""
    batch = stage(db, adapter, investor)
    assert batch["parsed"] == 1
    assert txn_count(db) == 0


def test_promotion_is_a_separate_explicit_action(db, adapter, investor) -> None:
    batch = stage(db, adapter, investor)
    assert txn_count(db) == 0

    summary = imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)
    assert summary.inserted == 1
    assert txn_count(db) == 1


def test_promotion_without_an_actor_is_refused(db, adapter, investor) -> None:
    """Who put these numbers into a client's portfolio is not an optional field."""
    batch = stage(db, adapter, investor)
    with pytest.raises(ValueError, match="requires an actor"):
        imports.promote_batch(db, batch["batch_id"], actor_uid="")
    assert txn_count(db) == 0


def test_the_database_also_refuses_an_unattributed_promotion(db, adapter, investor) -> None:
    import psycopg

    batch = stage(db, adapter, investor)
    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "UPDATE import_batch SET status='PROMOTED', promoted_at=now() WHERE id=%s",
            (batch["batch_id"],),
        )
    db.rollback()


def test_promoting_twice_is_refused(db, adapter, investor) -> None:
    """A no-op at the ledger thanks to the unique index, but it would imply a second
    review that never happened."""
    batch = stage(db, adapter, investor)
    imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)
    with pytest.raises(imports.BatchAlreadyResolvedError):
        imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)


def test_a_discarded_batch_cannot_be_promoted(db, adapter, investor) -> None:
    batch = stage(db, adapter, investor)
    imports.discard_batch(db, batch["batch_id"], reason="wrong client")
    with pytest.raises(imports.BatchAlreadyResolvedError):
        imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)
    assert txn_count(db) == 0


# --- reparse: the retry path for a document that failed for a reason since fixed -----


def test_reparsing_a_staged_batch_replaces_its_rows_not_duplicates_them(
    db, adapter, investor, store
) -> None:
    """The mechanics this exists to get right: DELETE-then-INSERT against the SAME
    stored bytes, not an accumulation. Reparsing twice must not double the row count."""
    batch = stage(db, adapter, investor, store=store)
    assert batch["parsed"] == 1

    result = imports.reparse_batch(db, store, batch["batch_id"], adapter, actor_uid=ACTOR)
    assert result["parsed"] == 1

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM import_row WHERE batch_id = %s", (batch["batch_id"],))
        assert cur.fetchone()[0] == 1


def test_reparse_actually_picks_up_a_state_change(db, investor, store) -> None:
    """The real scenario this was built for: a CAS PDF staged before the investor's
    PAN was on file rejects; adding the PAN afterward does nothing until something
    reparses against it. Simulated here with a fake adapter whose behaviour depends
    on external state read fresh on each parse() call, the same shape
    CasPdfAdapter(pan=...) has -- no real encrypted PDF needed to prove the mechanism."""
    from datetime import date
    from decimal import Decimal

    from app.engine.types import Source, Transaction, TxnType
    from app.ingest.base import CONFIDENCE_CERTAIN, ParseResult, Rejection, StagedRow

    class FlakyAdapter:
        name = "flaky"
        unlocked = False  # mutated between the two parse() calls, like a PAN being added

        def parse(self, content, account_id, filename=""):
            if not FlakyAdapter.unlocked:
                return ParseResult(rejections=[Rejection(0, "could not unlock")])
            return ParseResult(
                rows=[
                    StagedRow(
                        row_number=1,
                        transaction=Transaction(
                            isin="INE153T01027",
                            txn_date=date(2024, 1, 1),
                            txn_type=TxnType.BUY,
                            quantity=Decimal("1"),
                            price=Decimal("1"),
                            account_id=account_id,
                            source=Source.CSV,
                        ),
                        confidence=CONFIDENCE_CERTAIN,
                    )
                ]
            )

    flaky = FlakyAdapter()
    batch = stage(db, flaky, investor, store=store)
    assert batch["parsed"] == 0
    assert batch["rejected"] == 1

    FlakyAdapter.unlocked = True  # the PAN "got saved"
    result = imports.reparse_batch(db, store, batch["batch_id"], flaky, actor_uid=ACTOR)
    assert result["parsed"] == 1
    assert result["rejected"] == 0

    with db.cursor() as cur:
        cur.execute(
            "SELECT row_count, rejected_count FROM import_batch WHERE id = %s",
            (batch["batch_id"],),
        )
        row_count, rejected_count = cur.fetchone()
    assert (row_count, rejected_count) == (1, 0)


def test_a_promoted_batch_cannot_be_reparsed(db, adapter, investor, store) -> None:
    """A promoted batch's rows are the ledger's provenance record and must not
    change under it."""
    batch = stage(db, adapter, investor, store=store)
    imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)
    with pytest.raises(imports.BatchAlreadyResolvedError):
        imports.reparse_batch(db, store, batch["batch_id"], adapter, actor_uid=ACTOR)


def test_a_discarded_batch_cannot_be_reparsed(db, adapter, investor, store) -> None:
    batch = stage(db, adapter, investor, store=store)
    imports.discard_batch(db, batch["batch_id"], reason="wrong client")
    with pytest.raises(imports.BatchAlreadyResolvedError):
        imports.reparse_batch(db, store, batch["batch_id"], adapter, actor_uid=ACTOR)


def test_reparsing_an_unknown_batch_is_refused(db, adapter, store) -> None:
    with pytest.raises(imports.BatchNotFoundError):
        imports.reparse_batch(
            db, store, "00000000-0000-0000-0000-000000000000", adapter, actor_uid=ACTOR
        )


def test_reparsing_with_a_mismatched_adapter_is_refused(db, adapter, investor, store) -> None:
    """Reparse must use the SAME adapter the batch was staged with -- passing the
    wrong one would silently reinterpret one document type's bytes as another's."""
    batch = stage(db, adapter, investor, store=store)

    class OtherAdapter:
        name = "something_else"

        def parse(self, content, account_id, filename=""):
            raise AssertionError("should never be called")

    with pytest.raises(ValueError, match="staged with adapter"):
        imports.reparse_batch(db, store, batch["batch_id"], OtherAdapter(), actor_uid=ACTOR)


def test_discarding_requires_a_reason(db, adapter, investor) -> None:
    batch = stage(db, adapter, investor)
    with pytest.raises(ValueError, match="requires a reason"):
        imports.discard_batch(db, batch["batch_id"], reason="  ")


def test_reuploading_the_identical_file_is_caught_before_parsing(db, adapter, investor) -> None:
    stage(db, adapter, investor)
    with pytest.raises(imports.DuplicateUploadError):
        stage(db, adapter, investor)


def _investor_with_account(db: object, code: str) -> tuple[str, str]:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor (code, display_name) VALUES (%s, 'Test') RETURNING id",
            (code,),
        )
        investor_id = str(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'ZERODHA', true) RETURNING id",
            (investor_id,),
        )
        account_id = str(cur.fetchone()[0])
    db.commit()
    return investor_id, account_id


def test_the_same_file_stages_independently_for_another_investor(db, adapter, investor) -> None:
    """Regression: the sha256 short-circuit used to match GLOBALLY, so another tenant's
    identical upload blocked this one and named a batch id the ownership guard then
    refused to serve -- 'this investor belongs to another account'. A file hash identifies
    bytes, not a tenant."""
    other_investor, other_account = _investor_with_account(db, "C002")

    mine = stage(db, adapter, investor)
    theirs = imports.stage_batch(
        db,
        adapter,
        CSV.encode(),
        investor_id=other_investor,
        account_id=other_account,
        filename="tradebook.csv",
    )

    assert theirs["parsed"] == 1
    assert theirs["batch_id"] != mine["batch_id"]

    # Each investor's own re-upload is still the cheap no-op -- and still names their
    # own batch, never the other's.
    with pytest.raises(imports.DuplicateUploadError) as mine_again:
        stage(db, adapter, investor)
    assert str(mine_again.value.batch_id) == mine["batch_id"]
    with pytest.raises(imports.DuplicateUploadError) as theirs_again:
        imports.stage_batch(
            db,
            adapter,
            CSV.encode(),
            investor_id=other_investor,
            account_id=other_account,
            filename="tradebook.csv",
        )
    assert str(theirs_again.value.batch_id) == theirs["batch_id"]


def test_reuploading_to_another_account_of_the_same_investor_stages(db, adapter, investor) -> None:
    """dedupe_key begins with account_id: two accounts are two ledgers, so one account's
    staged file must not answer for the other's."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'ZERODHA', true) RETURNING id",
            (investor,),
        )
        other_account = str(cur.fetchone()[0])
    db.commit()

    first = stage(db, adapter, investor)
    second = imports.stage_batch(
        db,
        adapter,
        CSV.encode(),
        investor_id=investor,
        account_id=other_account,
        filename="tradebook.csv",
    )

    assert second["parsed"] == 1
    assert second["batch_id"] != first["batch_id"]


# --- review --------------------------------------------------------------------


def test_review_predicts_the_duplicates_promotion_will_skip(db, adapter, investor) -> None:
    """ "23 of your 115 rows are already here" is worth knowing BEFORE clicking promote."""
    first = stage(db, adapter, investor, filename="a.csv")
    imports.promote_batch(db, first["batch_id"], actor_uid=ACTOR)

    overlapping = CSV + (
        "BLS,INE153T01027,2024-02-11,NSE,EQ,EQ,buy,false,5.000000,210.000000,"
        "12399,99002,2024-02-11T10:15:00\n"
    )
    second = stage(db, adapter, investor, content=overlapping.encode(), filename="b.csv")

    review = imports.review_batch(db, second["batch_id"])
    assert review["staged"] == 2
    assert review["will_skip_as_duplicate"] == 1
    assert review["will_insert"] == 1

    summary = imports.promote_batch(db, second["batch_id"], actor_uid=ACTOR)
    assert (summary.inserted, summary.skipped_duplicates) == (1, 1)


def test_review_surfaces_rejections_with_row_numbers(db, adapter, investor) -> None:
    bad = CSV + CSV.split("\n")[1].replace(",buy,", ",transfer,").replace("12345", "12346") + "\n"
    batch = stage(db, adapter, investor, content=bad.encode())
    review = imports.review_batch(db, batch["batch_id"])
    assert len(review["rejections"]) == 1
    assert review["rejections"][0]["row_number"] == 3
    assert "transfer" in review["rejections"][0]["reason"]
    assert review["staged"] == 1, "the good row is still importable alongside the bad one"


def test_review_changes_nothing(db, adapter, investor) -> None:
    batch = stage(db, adapter, investor)
    imports.review_batch(db, batch["batch_id"])
    assert txn_count(db) == 0
    assert imports.review_batch(db, batch["batch_id"])["status"] == "STAGED"


# --- the raw file is kept ------------------------------------------------------


def test_the_uploaded_file_is_stored_before_it_is_parsed(db, adapter, investor, store) -> None:
    """A parser bug then costs a reparse, not the data."""
    batch = stage(db, adapter, investor, store=store)
    assert batch["document_id"]

    from app.db import documents

    (doc,) = documents.documents_for_investor(db, investor)
    assert store.get(doc["storage_key"]) == CSV.encode()


# --- THE SESSION GATE, against the real Console exports ------------------------


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_the_real_exports_load_and_reimporting_inserts_zero(db, adapter, investor) -> None:
    """The gate.

    Four real files stage to EXPECTED_TRADEBOOK_ROWS, promote to exactly that many
    transactions, and re-uploading every one of them inserts NOTHING.
    """
    batches = []
    for path in TRADEBOOKS:
        batches.append(
            stage(db, adapter, investor, content=Path(path).read_bytes(), filename=Path(path).name)
        )

    assert sum(b["parsed"] for b in batches) == EXPECTED_TRADEBOOK_ROWS
    assert sum(b["rejected"] for b in batches) == 0
    assert txn_count(db) == 0, "staging must not have touched the ledger"

    inserted = sum(
        imports.promote_batch(db, b["batch_id"], actor_uid=ACTOR).inserted for b in batches
    )
    assert inserted == EXPECTED_TRADEBOOK_ROWS
    assert txn_count(db) == EXPECTED_TRADEBOOK_ROWS

    # Re-upload all four. Content hashing catches them before parsing; even forcing past
    # that, the unique index means promotion inserts nothing.
    for path in TRADEBOOKS:
        with pytest.raises(imports.DuplicateUploadError):
            stage(db, adapter, investor, content=Path(path).read_bytes(), filename=Path(path).name)

    assert txn_count(db) == EXPECTED_TRADEBOOK_ROWS, "re-importing inserted zero"


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_a_renamed_reupload_still_inserts_zero(db, adapter, investor) -> None:
    """The real defence is the dedupe key, not the filename or the file hash.

    A client who re-exports the same period gets a byte-different file with the same
    trades. The hash will not catch that; the unique index must.
    """
    content = Path(TRADEBOOKS[0]).read_bytes()
    first = stage(db, adapter, investor, content=content, filename="original.csv")
    count = imports.promote_batch(db, first["batch_id"], actor_uid=ACTOR).inserted
    assert count > 0

    # Same trades, different bytes: a trailing newline is enough to change the hash.
    second = stage(db, adapter, investor, content=content + b"\n", filename="reexport.csv")
    summary = imports.promote_batch(db, second["batch_id"], actor_uid=ACTOR)

    assert summary.inserted == 0
    assert summary.skipped_duplicates == count
    assert txn_count(db) == count


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_promotion_registers_unknown_securities(db, adapter, investor) -> None:
    """An import is how a new holding is first discovered; requiring the security master
    to be pre-populated would make that impossible."""
    for path in TRADEBOOKS:
        batch = stage(
            db, adapter, investor, content=Path(path).read_bytes(), filename=Path(path).name
        )
        imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM security")
        assert cur.fetchone()[0] == 32, "32 distinct ISINs across the four exports"


@pytest.mark.skipif(not TRADEBOOKS, reason="real Console exports not present")
def test_the_ledger_replays_into_holdings(db, adapter, investor) -> None:
    """End to end: real files -> database -> engine. Nothing in between knows the others."""
    from app.db import repository
    from app.engine.holdings import compute_holdings

    for path in TRADEBOOKS:
        batch = stage(
            db, adapter, investor, content=Path(path).read_bytes(), filename=Path(path).name
        )
        imports.promote_batch(db, batch["batch_id"], actor_uid=ACTOR)

    transactions = repository.load_transactions(db, investor_id=investor)
    assert len(transactions) == EXPECTED_TRADEBOOK_ROWS

    # The four exports stop at 2026-01-28 and are missing the corporate actions the CAS
    # carries, so some positions go negative - exactly the condition NegativeHoldingError
    # exists to announce, and the same gap the golden fixture had to be anchored around.
    from app.engine.errors import NegativeHoldingError

    with pytest.raises(NegativeHoldingError):
        compute_holdings(transactions)
