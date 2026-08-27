"""app.db.imports._txn_to_payload / _payload_to_txn -- the staging-payload round trip.

Pure functions, no database needed: they serialize a Transaction to the JSON-able dict
an import batch stages before promotion, and back. Exists to catch one specific failure
mode -- an ingest adapter computes a field correctly (see
tests/test_zerodha_contract_note.py's `stt` apportionment) and the staging boundary
silently drops it before promotion ever runs, which is a worse, more confusing bug than
never computing the field at all. See docs/PHASE3_SESSION10_STT_FIX.md.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.db.imports import _payload_to_txn, _txn_to_payload
from app.engine.types import Source, Transaction, TxnType


def _txn(**kw) -> Transaction:
    return Transaction(
        isin=kw.get("isin", "INE153T01027"),
        txn_date=date(2024, 1, 10),
        txn_type=TxnType.BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        charges=Decimal(kw.get("charges", "0")),
        stt=Decimal(kw.get("stt", "0")),
        account_id=kw.get("account_id"),
        source=Source.CONTRACT_NOTE,
        source_ref=kw.get("source_ref"),
    )


def test_stt_survives_the_staging_payload_round_trip() -> None:
    original = _txn(charges="25", stt="15")
    restored = _payload_to_txn(_txn_to_payload(original))
    assert restored.stt == Decimal("15")
    assert restored.charges == Decimal("25")


def test_payload_omitting_stt_defaults_to_zero() -> None:
    """A staged payload written before this field existed (or from an adapter that
    never sets it) must not fail to load -- absence of data, not evidence of error."""
    payload = _txn_to_payload(_txn())
    del payload["stt"]
    restored = _payload_to_txn(payload)
    assert restored.stt == Decimal("0")
