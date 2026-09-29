"""Public source boundary and real PostgreSQL retries/derived-history regressions."""

import json
import os
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from io import BytesIO

import pytest
from app import reference_worker as worker
from app.config import Settings
from app.db import corporate_actions as ca
from app.db import reference_sync as queue
from app.db import repository
from app.engine.corporate_actions import CorpActionType, CorporateAction, Verification
from app.engine.holdings import compute_holdings
from app.engine.lots import compute_lots
from app.engine.types import Source, Transaction, TxnType
from app.ingest.nsdl import NsdlError, NsdlParticipantSource, parse_page

ISIN = "INE153T01027"


def settings(debug=True):
    return Settings(
        _env_file=None,
        database_url="postgresql://unused/test",
        portfolio_encryption_key="test-only",
        portfolio_pan_pepper="test-only",
        jwt_secret="test-only",
        debug=debug,
        ingest_domain="mail.example.test",
        allow_local_storage_in_production=True,
        local_storage_root="/tmp/test-documents",
        local_storage_base_url="https://api.example.test/documents",
    )


def nsdl_payload(isin=ISIN, count=1):
    return json.dumps(
        {
            "status_code": 200,
            "count": str(count),
            "data": [
                {
                    "field_isin": isin,
                    "name": "Test issuer",
                    "isin_description__value": "Equity",
                    "security_description": "EQUITY SHARES",
                    "isin_status": "ACTIVE",
                }
            ],
        }
    ).encode()


@pytest.mark.parametrize(
    "payload",
    [
        b"<html>blocked</html>",
        b"[]",
        b"{}",
        b'{"status_code":200,"count":1,"data":[]}',
        nsdl_payload("INE153T01028"),
    ],
)
def test_nsdl_rejects_block_pages_and_incomplete_or_invalid_data(payload):
    with pytest.raises(NsdlError):
        parse_page(payload, "https://nsdl.com/test")


def test_nsdl_retries_transport_and_uses_actual_endpoint_parameters():
    calls, sleeps = [], []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) < 3:
            raise TimeoutError("source unavailable")
        return BytesIO(nsdl_payload())

    page = NsdlParticipantSource(opener=opener, sleep=sleeps.append).search(ISIN)
    assert page.records[0].isin == ISIN
    assert sleeps == [1, 2]
    assert "search_type=DetailedSearch" in calls[0][0]
    assert "isin=" + ISIN in calls[0][0]
    assert len(page.sha256) == 64


def buy(qty="10", on=date(2024, 1, 10)):
    return Transaction(
        isin=ISIN,
        txn_date=on,
        txn_type=TxnType.BUY,
        quantity=D(qty),
        price=D("100"),
        source=Source.TRADEBOOK,
        account_id=os.environ["_TEST_ACCOUNT_ID"],
    )


def split(on=date(2024, 6, 3)):
    return CorporateAction(
        isin=ISIN,
        action_type=CorpActionType.SPLIT,
        ex_date=on,
        face_value_before=D("10"),
        face_value_after=D("5"),
        price_cum=D("100"),
        price_ex=D("50"),
        verification=Verification.VERIFIED,
        source="test evidence",
        source_url="https://example.test/notice",
    )


@pytest.mark.db
def test_import_trigger_schedule_is_idempotent_and_investor_scoped(db, investor):
    repository.save_transactions(db, [buy()])
    assert queue.status(db, investor)["state"] == "processing"
    queue.schedule(db, date(2024, 2, 10))
    first = queue.status(db, investor)
    queue.schedule(db, date(2024, 2, 10))
    assert queue.status(db, investor)["pending"] == first["pending"] == 4
    assert queue.status(db, "00000000-0000-0000-0000-000000000000")["pending"] == 0


@pytest.mark.db
@pytest.mark.parametrize("debug", [True, False])
def test_worker_retries_recovers_crash_and_preserves_work_in_both_modes(db, monkeypatch, debug):
    queue.enqueue(db, "NSDL", "test", {"query": ISIN, "page": 1})
    db.commit()

    def fail(*args):
        raise TimeoutError("source timeout")

    monkeypatch.setattr(worker, "process", fail)
    assert worker.run_once(db, settings(debug), limit=1)["failed"] == 1
    row = db.execute("SELECT state,attempts,last_error FROM reference_sync_task").fetchone()
    assert row[:2] == ("retry", 1)
    assert "TimeoutError" in row[2]
    assert worker.run_once(db, settings(debug), limit=1)["processed"] == 0
    db.execute("UPDATE reference_sync_task SET state='running',available_at=now()")
    db.commit()
    monkeypatch.setattr(worker, "process", lambda *args: None)
    assert worker.run_once(db, settings(debug), limit=1)["processed"] == 1
    assert db.execute("SELECT state,attempts,last_error FROM reference_sync_task").fetchone() == (
        "done",
        0,
        None,
    )


@pytest.mark.db
def test_nsdl_overlapping_pages_never_report_complete(db, monkeypatch):
    page = parse_page(nsdl_payload(count=2), "https://nsdl.com/test")
    monkeypatch.setattr(NsdlParticipantSource, "search", lambda *a, **k: page)
    checkpoint = worker.process(db, "NSDL", "key", {"query": ISIN, "page": 1}, settings())
    assert checkpoint["page"] == 2
    with pytest.raises(ValueError, match="overlapping"):
        worker.process(db, "NSDL", "key", checkpoint, settings())
    assert db.execute("SELECT count(*) FROM security_reference_history").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM security_alias").fetchone()[0] == 0


@pytest.mark.db
def test_legacy_prefix_task_retires_without_fetching_or_recording(db, monkeypatch):
    def fail(*a, **k):
        raise AssertionError("a prefix traversal must never be fetched")

    monkeypatch.setattr(NsdlParticipantSource, "search", fail)
    assert worker.process(db, "NSDL", "k", {"query": ISIN[:7], "page": 1}, settings()) is None
    assert db.execute("SELECT count(*) FROM security_reference").fetchone()[0] == 0


@pytest.mark.db
def test_schedule_queries_nsdl_by_exact_held_isin(db, investor):
    repository.save_transactions(db, [buy()])
    queue.schedule(db, date(2024, 2, 10))
    rows = db.execute(
        "SELECT task_key, payload->>'query' FROM reference_sync_task WHERE kind='NSDL'"
    ).fetchall()
    assert rows == [(f"{ISIN}:2024-02-10", ISIN)]


@pytest.mark.db
def test_non_equity_registry_records_do_not_become_equity_securities(db):
    payload = json.loads(nsdl_payload())
    payload["data"][0]["security_description"] = "DEBENTURES"
    page = parse_page(json.dumps(payload).encode(), "https://nsdl.com/test")
    queue.store_nsdl_page(db, page, ISIN[:7])
    assert db.execute("SELECT count(*) FROM security_reference").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM security").fetchone()[0] == 0


@pytest.mark.db
def test_queued_work_for_erased_accounts_does_not_recreate_portfolios(db):
    missing = "00000000-0000-0000-0000-000000000000"
    worker.process(db, "REPLAY", missing, {"account_id": missing}, settings())
    worker.process(
        db,
        "SNAPSHOT",
        missing,
        {"investor_id": missing, "on": "2024-01-31", "advised_only": False},
        settings(),
    )
    assert db.execute("SELECT count(*) FROM portfolio_snapshot").fetchone()[0] == 0


@pytest.mark.db
def test_late_import_recalculates_splits_preserving_fifo_dates_and_stored_rows(db, investor):
    repository.save_transactions(db, [buy()])
    ca.add_corporate_action(db, split())
    repository.save_transactions(db, [buy("5", date(2024, 2, 1))])
    ca.apply_known_actions_for_account(db, os.environ["_TEST_ACCOUNT_ID"])
    rows = repository.load_transactions(db, investor_id=investor)
    assert compute_holdings(rows)[0].quantity == 30
    lots = compute_lots(rows)
    assert [(lot.open_date, lot.quantity_open, lot.cost_per_unit) for lot in lots] == [
        (date(2024, 1, 10), D(20), D(50)),
        (date(2024, 2, 1), D(10), D(50)),
    ]
    raw = repository.load_transactions(db, investor_id=investor, apply_aliases=False)
    assert [t.quantity for t in raw if t.txn_type is TxnType.SPLIT_ADJ] == [D(10)]
    assert [t.quantity for t in rows if t.txn_type is TxnType.SPLIT_ADJ] == [D(15)]


@pytest.mark.db
def test_fractional_bonus_waits_for_settlement_evidence(db, investor):
    repository.save_transactions(db, [buy("1")])
    bonus = CorporateAction(
        isin=ISIN,
        action_type=CorpActionType.BONUS,
        ex_date=date(2024, 6, 3),
        bonus_new=1,
        bonus_for=2,
        price_cum=D(150),
        price_ex=D(100),
        source="test evidence",
        source_url="https://example.test/notice",
        verification=Verification.VERIFIED,
    )
    ca.add_corporate_action(db, bonus)
    assert compute_holdings(repository.load_transactions(db, investor_id=investor))[0].quantity == 1
    assert any("Fractional" in r["reason"] for r in queue.status(db, investor)["unresolved"])


def test_split_precedes_ex_date_buy_and_retains_original_lot_dates(monkeypatch):
    monkeypatch.setenv("_TEST_ACCOUNT_ID", "test-account")
    original = buy()
    on = date(2024, 6, 3)
    rows = [
        original,
        buy("4", on),
        replace(
            original, txn_date=on, txn_type=TxnType.SPLIT_ADJ, price=D(0), source=Source.CORP_ACTION
        ),
    ]
    lots = compute_lots(rows)
    assert [(lot.open_date, lot.quantity_open, lot.cost_per_unit) for lot in lots] == [
        (original.txn_date, D(20), D(50)),
        (on, D(4), D(100)),
    ]


@pytest.mark.db
@pytest.mark.parametrize("archive_lags", [False, True])
def test_dated_split_evidence_links_old_new_without_rewriting_broker_trades(
    db, investor, archive_lags
):
    from app.db.identity_evidence import resolve_split
    from app.db.isin_change_circulars import refresh_isin_change_feed
    from app.db.security_alias import verified_map

    from tests.test_db_isin_change_circulars import TATA_STEEL_PDF, _tata_listing_payload

    old, new = "INE081A01012", "INE081A01020"
    db.execute("INSERT INTO security(isin,symbol,exchange) VALUES (%s,'TATASTEEL','NSE')", (old,))
    repository.save_transactions(db, [replace(buy(), isin=old, txn_date=date(2022, 1, 1))])

    class Circulars:
        def list_circulars(self, start, end):
            return _tata_listing_payload()

        def fetch_pdf(self, url):
            return TATA_STEEL_PDF

    refresh_isin_change_feed(db, date(2022, 7, 1), date(2022, 7, 31), source=Circulars())
    assert verified_map(db) == {}
    queue.store_nsdl_page(db, parse_page(nsdl_payload(new), "https://nsdl.com/test"), new[:7])
    db.commit()
    calls = []

    class Exchange:
        def fetch(self, on):
            calls.append(on)
            if on == date(2022, 7, 27):
                isin, close = old, "959.4"
            elif on == date(2022, 7, 28):
                isin, close = (old if archive_lags else new), "100.35"
            else:
                assert on == date(2022, 7, 29)
                isin, close = new, "107.6"
            return (
                "ISIN,ClsPric,TradDt,TckrSymb,SctySrs,FinInstrmTp\n"
                f"{isin},{close},{on},TATASTEEL,EQ,STK\n"
            ).encode()

    resolve_split(db, "53019", source=Exchange())
    resolve_split(db, "53019", source=Exchange())
    assert len(calls) == (3 if archive_lags else 2)  # persisted evidence, no repeated fetches
    assert verified_map(db) == {old: new}
    assert verified_map(db, date(2022, 7, 27)) == {}
    current = repository.load_transactions(db, investor_id=investor)
    assert compute_holdings(current)[0].quantity == 100
    assert compute_lots(current)[0].open_date == date(2022, 1, 1)
    historic = repository.load_transactions(db, investor_id=investor, date_to=date(2022, 7, 27))
    assert [(t.isin, t.quantity) for t in historic] == [(old, D(10))]
    raw = repository.load_transactions(db, investor_id=investor, apply_aliases=False)
    assert [(t.isin, t.quantity) for t in raw if t.source is Source.TRADEBOOK] == [(old, D(10))]
    from app.db.prices import latest_prices

    assert latest_prices(db, [new], date(2022, 7, 28)) == {new: D("100.35")}
    assert latest_prices(db, [new], date(2022, 8, 30)) == {}
    assert latest_prices(db, [new], date(2022, 7, 27)) == {}


@pytest.mark.db
def test_analytics_adjusts_split_series_without_changing_exchange_closes(db, investor):
    from app.db.prices import adjusted_price_series, price_series

    ca.add_corporate_action(db, split())
    for on, close in [(date(2024, 5, 31), 100), (date(2024, 6, 3), 50)]:
        db.execute(
            "INSERT INTO price(isin,price_date,close,source) VALUES (%s,%s,%s,'NSE')",
            (ISIN, on, close),
        )
    start, end = date(2024, 5, 31), date(2024, 6, 3)
    assert adjusted_price_series(db, [ISIN], start, end)[ISIN] == [(start, D(50)), (end, D(50))]
    assert price_series(db, [ISIN], start, end)[ISIN] == [(start, D(100)), (end, D(50))]
    assert adjusted_price_series(db, [ISIN], start, start)[ISIN] == [(start, D(100))]


@pytest.mark.db
def test_replay_invalidates_and_rebuilds_snapshot_after_late_import(db, investor):
    from app.db.snapshots import get_snapshot, upsert_snapshot
    from app.engine.snapshot import compute_snapshot

    repository.save_transactions(db, [buy()])
    on = date(2024, 1, 31)
    upsert_snapshot(db, investor, False, compute_snapshot([buy()], {ISIN: D(100)}, on))
    repository.save_transactions(db, [buy("5", date(2024, 1, 12))])
    db.execute(
        "INSERT INTO price(isin,price_date,close,source) VALUES (%s,%s,100,'NSE')", (ISIN, on)
    )
    worker.process(db, "REPLAY", "test", {"account_id": os.environ["_TEST_ACCOUNT_ID"]}, settings())
    assert get_snapshot(db, investor, on) is None
    key, payload = db.execute(
        "SELECT task_key,payload FROM reference_sync_task WHERE kind='SNAPSHOT'"
    ).fetchone()
    worker.process(db, "SNAPSHOT", key, payload, settings())
    assert get_snapshot(db, investor, on).market_value == D(1500)


@pytest.mark.network
@pytest.mark.db
def test_live_tata_split_reference_evidence(db, investor):
    """Real NSE/NSDL responses with a test-only holding in disposable PostgreSQL."""
    import hashlib

    from app.db.identity_evidence import resolve_split
    from app.db.isin_change_circulars import _upsert_circular
    from app.db.prices import latest_prices
    from app.db.security_alias import verified_map
    from app.ingest.isin_change_feed import (
        NseCircularListSource,
        extract_pdf_text,
        parse_circular_listing,
        parse_isin_change_circular,
    )

    feed = NseCircularListSource()
    listings = parse_circular_listing(feed.list_circulars(date(2022, 7, 1), date(2022, 7, 31)))
    listing = next(row for row in listings if row.circular_number == "53019")
    document = feed.fetch_pdf(listing.pdf_url)
    circular = parse_isin_change_circular(extract_pdf_text(document))
    old, new = "INE081A01012", circular.new_isin
    db.execute("INSERT INTO security(isin,symbol,exchange) VALUES (%s,'TATASTEEL','NSE')", (old,))
    repository.save_transactions(db, [replace(buy(), isin=old, txn_date=date(2022, 1, 1))])
    _upsert_circular(
        db,
        listing,
        circular,
        old_isin=None,
        alias_created=False,
        skip_reason=None,
        pdf_sha256=hashlib.sha256(document).hexdigest(),
    )
    queue.store_nsdl_page(db, NsdlParticipantSource().search(new), new[:7])
    db.commit()
    resolve_split(db, "53019")
    assert verified_map(db) == {old: new}
    assert (
        compute_holdings(repository.load_transactions(db, investor_id=investor))[0].quantity == 100
    )
    assert latest_prices(db, [new], date(2022, 7, 28)) == {new: D("100.35")}
