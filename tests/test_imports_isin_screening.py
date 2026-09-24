"""Every staged row's ISIN is screened against app.isin before it can key anything.

WHY THIS SUITE EXISTS. ``app.isin.classify`` was written with the ISIN lineage work and
wired to nothing, so until now an adapter could stage a damaged identifier and it would
quietly become a second, phantom security -- CLAUDE.md rule 2's failure mode exactly.
``app.db.imports._screen_isins`` is the one place every adapter's output passes through.

The identifiers here are COMPUTED, never typed: ``check_digit`` builds the valid ones and
deliberately off-by-one builds the invalid ones. An ISIN typed from memory is as likely as
not to be invalid, and a fixture that is wrong for a reason nobody notices gets "fixed" by
weakening the validation it was meant to prove.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from app.db import imports
from app.engine.types import Source, Transaction, TxnType
from app.ingest.base import (
    CONFIDENCE_CERTAIN,
    CONFIDENCE_DERIVED,
    CONFIDENCE_UNCERTAIN,
    ParseResult,
    Rejection,
    StagedRow,
)
from app.ingest.zerodha_tradebook import ZerodhaTradebookAdapter
from app.isin import check_digit
from app.storage.local import SIGNING_SECRET_ENV, LocalDocumentStore

ACCOUNT = "11111111-1111-1111-1111-111111111111"
ACTOR = "22222222-2222-2222-2222-222222222222"

#: Seeded by the ``investor`` fixture in conftest_db, so it is "already known".
SEEDED = "INE153T01027"

#: Same issuer body as SEEDED with a deliberately wrong check digit -- the case
#: app.isin's docstring singles out: dirty reference data on a security we already hold.
SEEDED_BAD_DIGIT = "INE153T0102" + str((check_digit("INE153T0102") + 1) % 10)

#: Valid, and deliberately NOT seeded anywhere.
UNSEEDED = "INE009A0102" + str(check_digit("INE009A0102"))
UNSEEDED_BAD_DIGIT = "INE009A0102" + str((check_digit("INE009A0102") + 1) % 10)

#: Ten alphanumerics after "IN", so the adapter's old ``^IN[A-Z0-9]{10}$`` accepted it.
#: ISO 6166 requires a DIGIT in position 12, so classify() refuses it on shape.
SHAPE_BAD = "INE153T0102X"


def _staged(isin: str, row_number: int = 1, confidence: Decimal = CONFIDENCE_CERTAIN) -> StagedRow:
    return StagedRow(
        row_number=row_number,
        transaction=Transaction(
            isin=isin,
            txn_date=date(2026, 8, 12),
            txn_type=TxnType.BUY,
            quantity=Decimal("18"),
            price=Decimal("2663.95"),
            account_id=ACCOUNT,
            source=Source.TRADEBOOK,
            source_ref=str(1089300 + row_number),
        ),
        confidence=confidence,
        raw={"isin": isin},
    )


class _FakeConn:
    """Just enough of a connection for ``app.securities.lookup``: it answers with the
    ISINs it was told exist, so the unit tests below need no Postgres."""

    def __init__(self, known: set[str]) -> None:
        self.known = known
        self.queries = 0

    def cursor(self) -> Any:
        conn = self

        class _Cur:
            def __enter__(self) -> Any:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def execute(self, sql: str, params: tuple = ()) -> None:
                conn.queries += 1
                asked = params[0] if params else []
                self._rows = [
                    (i, "SYM", "Name", "EQ", None, None, "NSE") for i in asked if i in conn.known
                ]

            def fetchall(self) -> list[tuple]:
                return self._rows

        return _Cur()


# --- the screen itself, no database ------------------------------------------------


def test_a_valid_isin_passes_through_untouched() -> None:
    row = _staged(UNSEEDED)
    result = imports._screen_isins(_FakeConn(set()), ParseResult(rows=[row]))
    assert result.rejections == []
    assert result.rows[0].transaction.isin == UNSEEDED
    assert result.rows[0].confidence == CONFIDENCE_CERTAIN


def test_a_shape_failure_is_rejected_even_though_the_old_pattern_allowed_it() -> None:
    """``^IN[A-Z0-9]{10}$`` accepted a non-digit check position. ISO 6166 does not."""
    result = imports._screen_isins(_FakeConn(set()), ParseResult(rows=[_staged(SHAPE_BAD)]))
    assert result.rows == []
    assert "not an ISO 6166 identifier" in result.rejections[0].reason
    assert result.rejections[0].row_number == 1


def test_a_checksum_failure_on_an_unknown_isin_is_rejected() -> None:
    result = imports._screen_isins(
        _FakeConn(set()), ParseResult(rows=[_staged(UNSEEDED_BAD_DIGIT)])
    )
    assert result.rows == []
    assert "check digit failed" in result.rejections[0].reason


def test_a_checksum_failure_on_an_already_known_isin_stages_for_review() -> None:
    """app.isin: dirty reference data is evidence about the stored row, not grounds to
    discard a holding. It stages, but below REVIEW_THRESHOLD so a human sees it."""
    result = imports._screen_isins(
        _FakeConn({SEEDED_BAD_DIGIT}), ParseResult(rows=[_staged(SEEDED_BAD_DIGIT)])
    )
    assert result.rejections == []
    assert result.rows[0].confidence == CONFIDENCE_DERIVED
    assert result.rows[0].confidence < imports.REVIEW_THRESHOLD


def test_the_checksum_escape_hatch_never_raises_confidence() -> None:
    """A row a parser could not vouch for (0.5, below PROMOTE_FLOOR) must not be
    promoted to 0.8 by surviving this screen."""
    row = _staged(SEEDED_BAD_DIGIT, confidence=CONFIDENCE_UNCERTAIN)
    result = imports._screen_isins(_FakeConn({SEEDED_BAD_DIGIT}), ParseResult(rows=[row]))
    assert result.rows[0].confidence == CONFIDENCE_UNCERTAIN
    assert result.rows[0].confidence <= imports.PROMOTE_FLOOR


@pytest.mark.parametrize("damaged", [f" {SEEDED} ", "INE153T 01027", f"{SEEDED}​"])
def test_extraction_damage_is_normalised_rather_than_rejected(damaged: str) -> None:
    """Interior spaces and zero-width characters survive PDF extraction. The NORMALISED
    form is what gets stored -- keying on the damaged spelling is the phantom security."""
    result = imports._screen_isins(_FakeConn(set()), ParseResult(rows=[_staged(damaged)]))
    assert result.rejections == []
    assert result.rows[0].transaction.isin == SEEDED


def test_an_empty_isin_is_a_missing_identifier_not_a_cash_line() -> None:
    result = imports._screen_isins(_FakeConn(set()), ParseResult(rows=[_staged("")]))
    assert result.rows == []
    assert "carries no ISIN" in result.rejections[0].reason


def test_existing_rejections_are_preserved() -> None:
    prior = Rejection(7, "unknown trade_type 'xyz'", {})
    result = imports._screen_isins(
        _FakeConn(set()), ParseResult(rows=[_staged(SHAPE_BAD)], rejections=[prior])
    )
    assert prior in result.rejections
    assert len(result.rejections) == 2


def test_one_lookup_serves_the_whole_batch() -> None:
    """Not one query per row -- a 115-row export must not become 115 round trips."""
    conn = _FakeConn({SEEDED_BAD_DIGIT})
    rows = [_staged(SEEDED_BAD_DIGIT, row_number=n) for n in range(1, 11)]
    imports._screen_isins(conn, ParseResult(rows=rows))
    assert conn.queries == 1


def test_a_clean_batch_costs_no_lookup_at_all() -> None:
    conn = _FakeConn(set())
    imports._screen_isins(conn, ParseResult(rows=[_staged(UNSEEDED)]))
    assert conn.queries == 0


# --- end to end through stage_batch, against a real database -----------------------

HEADER = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
)


def _csv(*isins: str) -> bytes:
    rows = "".join(
        f"BLS,{isin},2026-08-12,NSE,EQ,EQ,buy,false,18.000000,2663.949951,"
        f"{1089300 + n},{99001 + n},2026-08-12T12:19:40\n"
        for n, isin in enumerate(isins)
    )
    return (HEADER + rows).encode()


def _stage(db: Any, investor: str, content: bytes, filename: str) -> dict[str, Any]:
    return imports.stage_batch(
        db,
        ZerodhaTradebookAdapter(),
        content,
        investor_id=investor,
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        filename=filename,
        investor_code="C001",
    )


@pytest.mark.db
def test_a_damaged_isin_never_reaches_a_staged_row(db: Any, investor: str) -> None:
    summary = _stage(db, investor, _csv(SEEDED, SHAPE_BAD), "mixed.csv")
    assert summary["parsed"] == 1
    assert summary["rejected"] == 1
    with db.cursor() as cur:
        cur.execute(
            "SELECT status, reason FROM import_row WHERE batch_id = %s AND status = 'REJECTED'",
            (summary["batch_id"],),
        )
        rejected = cur.fetchall()
    assert len(rejected) == 1
    assert "ISO 6166" in rejected[0][1]


@pytest.mark.db
def test_the_batch_counts_match_the_rows_actually_written(db: Any, investor: str) -> None:
    """row_count/rejected_count are read off the screened result, so a screen that ran
    after the batch insert would record counts contradicting its own rows."""
    summary = _stage(db, investor, _csv(SEEDED, SHAPE_BAD, UNSEEDED_BAD_DIGIT), "counts.csv")
    with db.cursor() as cur:
        cur.execute(
            "SELECT row_count, rejected_count FROM import_batch WHERE id = %s",
            (summary["batch_id"],),
        )
        row_count, rejected_count = cur.fetchone()
        cur.execute(
            "SELECT status, count(*) FROM import_row WHERE batch_id = %s GROUP BY status",
            (summary["batch_id"],),
        )
        actual = dict(cur.fetchall())
    assert row_count == actual.get("STAGED", 0) == 1
    assert rejected_count == actual.get("REJECTED", 0) == 2


@pytest.mark.db
def test_a_reparse_screens_too(db: Any, investor: str, tmp_path: Any, monkeypatch: Any) -> None:
    """reparse_batch REPLACES a batch's rows from the stored bytes. Unscreened, it would
    be a way to land an identifier the original staging had already refused."""
    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")
    store = LocalDocumentStore(tmp_path / "objects")

    batch = imports.stage_batch(
        db,
        ZerodhaTradebookAdapter(),
        _csv(SEEDED, SHAPE_BAD),
        investor_id=investor,
        account_id=os.environ["_TEST_ACCOUNT_ID"],
        filename="reparse.csv",
        investor_code="C001",
        store=store,
    )
    assert batch["parsed"] == 1

    result = imports.reparse_batch(
        db, store, batch["batch_id"], ZerodhaTradebookAdapter(), actor_uid=ACTOR
    )
    assert result["parsed"] == 1
    assert result["rejected"] == 1

    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM import_row WHERE batch_id = %s AND status = 'STAGED'",
            (batch["batch_id"],),
        )
        assert cur.fetchone()[0] == 1


@pytest.mark.db
def test_a_known_isin_with_a_bad_check_digit_stages_and_is_surfaced_for_review(
    db: Any, investor: str
) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO security (isin, symbol) VALUES (%s, 'BLS') ON CONFLICT DO NOTHING",
            (SEEDED_BAD_DIGIT,),
        )
    db.commit()

    summary = _stage(db, investor, _csv(SEEDED_BAD_DIGIT), "dirty.csv")
    assert summary["parsed"] == 1
    assert summary["rejected"] == 0

    # Header is row 1, so the one data row is row 2.
    review = imports.review_batch(db, summary["batch_id"])
    assert len(review["needs_review"]) == 1
    assert review["needs_review"][0]["row_number"] == 2
    assert review["needs_review"][0]["confidence"] == CONFIDENCE_DERIVED
