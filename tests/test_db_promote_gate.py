"""Rows no parser could vouch for do not reach the ledger by accident.

``promote_batch`` used to promote every STAGED row regardless of confidence --
``REVIEW_THRESHOLD`` only ever populated an advisory ``needs_review`` list that nothing
enforced. That was harmless while every adapter scored 0.8 or 1.0. It stops being
harmless the moment a parser exists whose output is a transcription rather than a read
(app/ingest/llm_verify.py), so the gate lands before that parser does.

The regression guard at the bottom is the point of the whole file: contract-note rows
score CONFIDENCE_DERIVED (0.8) and MUST keep promoting with no ceremony. A gate set at
REVIEW_THRESHOLD (0.9) instead of PROMOTE_FLOOR (0.5) would block every contract note
this system has ever parsed, and it would do it quietly.
"""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal

import pytest
from app.db import imports
from app.engine.dedupe import make_dedupe_key
from app.engine.types import Source, Transaction, TxnType
from app.ingest.base import CONFIDENCE_CERTAIN, CONFIDENCE_DERIVED, CONFIDENCE_UNCERTAIN

pytestmark = pytest.mark.db

ACTOR = "11111111-1111-1111-1111-111111111111"


@pytest.fixture()
def account_id(investor: str) -> str:
    return os.environ["_TEST_ACCOUNT_ID"]


def _stage_rows(db, investor_id: str, account_id: str, confidences: list[Decimal]) -> str:
    """One batch holding one row per confidence given. Built directly rather than through
    an adapter: this file is about the gate, not about any particular parser."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO import_batch (investor_id, account_id, adapter, sha256, "
            "row_count, rejected_count) VALUES (%s,%s,'test',%s,%s,0) RETURNING id",
            (investor_id, account_id, os.urandom(16).hex(), len(confidences)),
        )
        batch_id = str(cur.fetchone()[0])
        for i, confidence in enumerate(confidences, start=1):
            txn = Transaction(
                isin="INE153T01027",
                txn_date=date(2024, 1, i),
                txn_type=TxnType.BUY,
                quantity=Decimal("10"),
                price=Decimal("100.00"),
                account_id=account_id,
                source=Source.CONTRACT_NOTE,
                source_ref=f"row-{i}",
            )
            cur.execute(
                "INSERT INTO import_row (batch_id, row_number, confidence, dedupe_key, "
                "payload) VALUES (%s,%s,%s,%s,%s)",
                (
                    batch_id,
                    i,
                    confidence,
                    make_dedupe_key(txn),
                    json.dumps({"transaction": imports._txn_to_payload(txn), "raw": {}}),
                ),
            )
    db.commit()
    return batch_id


def _ledger_count(db) -> int:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        return cur.fetchone()[0]


# --- the gate ------------------------------------------------------------------


def test_an_unverified_row_refuses_promotion(db, investor, account_id) -> None:
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_UNCERTAIN])
    with pytest.raises(imports.UnreviewedRowsError) as exc:
        imports.promote_batch(db, batch_id, actor_uid=ACTOR)
    assert exc.value.count == 1
    assert exc.value.batch_id == batch_id


def test_a_refusal_writes_nothing_at_all(db, investor, account_id) -> None:
    """Counted before the rows are even read, so a refused promotion leaves the ledger
    and the batch exactly as they were -- not a partial import somebody has to unpick."""
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_CERTAIN, CONFIDENCE_UNCERTAIN])
    before = _ledger_count(db)

    with pytest.raises(imports.UnreviewedRowsError):
        imports.promote_batch(db, batch_id, actor_uid=ACTOR)

    assert _ledger_count(db) == before
    with db.cursor() as cur:
        cur.execute("SELECT status FROM import_batch WHERE id = %s", (batch_id,))
        assert cur.fetchone()[0] == imports.STATUS_STAGED
        cur.execute(
            "SELECT count(*) FROM import_row WHERE batch_id = %s AND status <> 'STAGED'",
            (batch_id,),
        )
        assert cur.fetchone()[0] == 0


def test_the_refusal_names_the_count(db, investor, account_id) -> None:
    """"3 rows need your confirmation" is actionable; "promotion refused" is not."""
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_UNCERTAIN] * 3)
    with pytest.raises(imports.UnreviewedRowsError) as exc:
        imports.promote_batch(db, batch_id, actor_uid=ACTOR)
    assert "3 row(s)" in str(exc.value)


def test_acknowledging_promotes_them(db, investor, account_id) -> None:
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_UNCERTAIN])
    summary = imports.promote_batch(
        db, batch_id, actor_uid=ACTOR, acknowledge_uncertain=True
    )
    assert summary.inserted == 1


def test_the_acknowledgement_is_recorded_as_a_count(db, investor, account_id) -> None:
    """The audit entry is what answers, later, whether a human was told these rows came
    from a parser that could not verify them -- the SEBI AI-usage disclosure obligation.
    A count, never a value: audit.py forbids identifiers in a diff."""
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_UNCERTAIN] * 2)
    imports.promote_batch(db, batch_id, actor_uid=ACTOR, acknowledge_uncertain=True)

    with db.cursor() as cur:
        cur.execute(
            "SELECT diff_json FROM audit_log WHERE action = %s AND entity_id = %s",
            (imports.ACTION_BATCH_PROMOTED, batch_id),
        )
        diff = cur.fetchone()[0]
    assert diff["acknowledged_uncertain"] == 2


def test_acknowledging_a_batch_that_has_nothing_uncertain_records_zero(
    db, investor, account_id
) -> None:
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_CERTAIN])
    imports.promote_batch(db, batch_id, actor_uid=ACTOR, acknowledge_uncertain=True)
    with db.cursor() as cur:
        cur.execute(
            "SELECT diff_json FROM audit_log WHERE action = %s AND entity_id = %s",
            (imports.ACTION_BATCH_PROMOTED, batch_id),
        )
        assert cur.fetchone()[0]["acknowledged_uncertain"] == 0


# --- THE REGRESSION GUARD ------------------------------------------------------


def test_contract_note_rows_still_promote_untouched(db, investor, account_id) -> None:
    """CONFIDENCE_DERIVED (0.8) is what every contract-note row scores, and it sits BELOW
    REVIEW_THRESHOLD (0.9). Gating on that threshold instead of PROMOTE_FLOOR would block
    all 40 real notes in this project. This test is why the floor is 0.5."""
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_DERIVED] * 3)
    summary = imports.promote_batch(db, batch_id, actor_uid=ACTOR)  # no acknowledgement
    assert summary.inserted == 3


def test_certain_rows_still_promote_untouched(db, investor, account_id) -> None:
    batch_id = _stage_rows(db, investor, account_id, [CONFIDENCE_CERTAIN] * 2)
    assert imports.promote_batch(db, batch_id, actor_uid=ACTOR).inserted == 2


def test_the_floor_sits_below_the_review_threshold(db) -> None:
    """Pins the relationship the two tests above depend on, so a future edit to either
    constant fails here with an explanation rather than in a distant integration test."""
    from app.ingest.base import REVIEW_THRESHOLD

    assert imports.PROMOTE_FLOOR < CONFIDENCE_DERIVED < REVIEW_THRESHOLD
