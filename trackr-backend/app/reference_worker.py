"""Free-source reference worker: python -m app.reference_worker [--once]."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import time
from datetime import date, timedelta

from app.config import Settings, get_settings
from app.db import corporate_actions as ca
from app.db import identity_evidence as identity
from app.db import reference_sync as queue
from app.db.connection import connect
from app.db.isin_change_circulars import refresh_isin_change_feed
from app.db.security_alias import promote_draft_aliases
from app.engine.corporate_actions import Verification, check_price_consistency
from app.ingest.corporate_action_feed import (
    NSE_CORP_ACTIONS_URL,
    NseCorporateActionFeedSource,
    parse_corporate_action_feed,
)
from app.ingest.isin_change_feed import NseCircularListSource, parse_circular_listing
from app.ingest.nsdl import NsdlParticipantSource
from app.prices.sources import NotPublished, nse_source

logger = logging.getLogger("reference_worker")
_WORKER_LOCK = 804732916  # session lock: survives commits, released on connection death
_UNSUPPORTED = re.compile(
    r"demerger|amalgamation|scheme of arrangement|\bmerger\b|consolidation|"
    r"reduction of capital|capital reduction|rights|partly paid|conversion|warrant",
    re.IGNORECASE,
)


class RecordingActionSource:
    def __init__(self, conn, source=None):
        self.conn = conn
        self.source = source or NseCorporateActionFeedSource()

    def fetch(self, start, end):
        payload = self.source.fetch(start, end)
        rows = json.loads(payload)
        if not isinstance(rows, list):
            raise ValueError("NSE corporate actions did not return a list")
        # Preserve non-automatic events instead of dropping the notices on the floor.
        with self.conn.cursor() as cur:
            for row in rows:
                if not isinstance(row, dict) or not _UNSUPPORTED.search(
                    str(row.get("subject", ""))
                ):
                    continue
                raw = json.dumps(row, sort_keys=True)
                cur.execute(
                    """INSERT INTO reference_notice
                       (notice_hash,isin,symbol,ex_date,subject,source_url,payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                    (
                        hashlib.sha256(raw.encode()).hexdigest(),
                        str(row.get("isin", "")),
                        str(row.get("symbol", "")),
                        str(row.get("exDate", "")),
                        row["subject"],
                        NSE_CORP_ACTIONS_URL.format(start=start, end=end),
                        raw,
                    ),
                )
        self.conn.commit()
        return payload


def _schedule_actions(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT t.account_id::text,c.id::text FROM corporate_action c
               JOIN transaction t ON left(t.isin,7)=left(c.isin,7)
               WHERE c.action_type IN ('BONUS','SPLIT') AND c.verification='DRAFT'"""
        )
        pairs = cur.fetchall()
    for account, action_id in pairs:
        queue.enqueue(conn, "ACTION", action_id, {"action_id": action_id})
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reference_sync_dependency VALUES (%s,'ACTION',%s) "
                "ON CONFLICT DO NOTHING",
                (account, action_id),
            )


def _verify_action(conn, action_id, source=None):
    action = ca.get_corporate_action(conn, action_id)
    if action is None or action.verification is Verification.DISPUTED:
        raise identity.EvidencePending("Action is absent or disputed")
    if action.verification is Verification.VERIFIED:
        return
    if action.ex_date > date.today():
        raise identity.EvidencePending("Action is not effective yet")
    source = source or nse_source()
    after, after_receipt = identity._day(conn, action.ex_date, source)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT old_isin FROM security_alias WHERE current_isin=%s AND verification='VERIFIED'",
            (action.isin,),
        )
        identifiers = {action.isin, *(r[0] for r in cur.fetchall())}
    prior_rows = []
    for offset in range(1, 8):
        on = action.ex_date - timedelta(days=offset)
        if on.weekday() >= 5:
            continue
        try:
            before, before_receipt = identity._day(conn, on, source)
        except NotPublished:
            continue
        prior_rows = [r for r in before if r[0] in identifiers]
        break
    ex_rows = [r for r in after if r[0] == action.isin]
    if len(prior_rows) != 1 or len(ex_rows) != 1:
        raise identity.EvidencePending("Waiting for unique cum/ex exchange prices or ISIN link")
    from dataclasses import replace

    candidate = replace(action, price_cum=prior_rows[0][3], price_ex=ex_rows[0][3])
    if check_price_consistency(candidate):
        raise identity.EvidencePending("Exchange prices contradict the announced ratio")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE corporate_action SET price_cum=%s,price_ex=%s WHERE id=%s",
            (candidate.price_cum, candidate.price_ex, action_id),
        )
        cur.execute(
            "INSERT INTO reference_action_evidence VALUES (%s,%s::jsonb,now()) "
            "ON CONFLICT DO NOTHING",
            (
                action_id,
                json.dumps(
                    {
                        "before": before_receipt,
                        "after": after_receipt,
                        "announcement": action.source_url,
                    }
                ),
            ),
        )
    ca.verify_corporate_action(conn, action_id)
    conn.commit()


def process(conn, kind: str, key: str, payload: dict, settings: Settings) -> dict | None:
    """Return a checkpoint for more work, or None when this task is complete."""
    if kind == "NSDL":
        if len(payload["query"]) != 12:
            # Legacy issuer-prefix task. NSDL's prefix pagination overlaps and skips rows,
            # so it can never complete; exact-ISIN tasks replace it. Retiring it records
            # nothing: unresolved identities are derived from security_reference itself.
            logger.info("Retiring legacy NSDL prefix task %s", key)
            return None
        page_no = payload["page"]
        if page_no > settings.reference_nsdl_max_pages:
            raise ValueError("NSDL pagination exceeded configured page limit")
        page = NsdlParticipantSource(timeout=settings.reference_http_timeout_seconds).search(
            payload["query"],
            page=page_no,
        )
        seen = set(payload.get("seen", []))
        new = {r.isin for r in page.records}
        if seen & new:
            raise ValueError("NSDL returned overlapping pages; refusing incomplete success")
        if page_no > 1 and page.count != payload["count"]:
            # The source changed mid-pagination: restart the next attempt, preserving
            # observations already stored, and do not declare the traversal complete.
            return {"query": payload["query"], "page": 1, "seen": []}
        queue.store_nsdl_page(conn, page, payload["query"])
        seen |= new
        if len(seen) < page.count:
            return {**payload, "page": page_no + 1, "seen": sorted(seen), "count": page.count}
        if len(seen) != page.count:
            raise ValueError("NSDL count did not reconcile")
    elif kind == "NSE":
        start, end = date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"])
        circulars = refresh_isin_change_feed(
            conn,
            start,
            end,
            source=NseCircularListSource(timeout=settings.reference_http_timeout_seconds),
            max_documents=10,
        )
        identity.schedule_identity(conn)
        if circulars.get("error") or circulars.get("breaker_open"):
            raise ValueError(circulars.get("error") or "NSE circular circuit breaker is open")
        if circulars.get("remaining"):
            return payload
        actions = ca.refresh_corporate_action_feed(
            conn, start, end, source=RecordingActionSource(conn)
        )
        _schedule_actions(conn)
        if actions.get("error"):
            raise ValueError(actions["error"])
    elif kind == "IDENTITY":
        identity.resolve_split(conn, payload["circular_number"])
    elif kind == "ACTION":
        _verify_action(conn, payload["action_id"])
    elif kind == "REPLAY":
        ca.apply_known_actions_for_account(conn, payload["account_id"])
        _invalidate_snapshots(conn, payload["account_id"])
    elif kind == "SNAPSHOT":
        _rebuild_snapshot(conn, payload)
    else:
        raise ValueError(f"Unknown reference task kind: {kind}")
    return None


def _invalidate_snapshots(conn, account_id):
    """Invalidate derived caches atomically with durable rebuild requests."""
    with conn.cursor() as cur:
        cur.execute("SELECT investor_id::text FROM account WHERE id=%s", (account_id,))
        owner = cur.fetchone()
        if owner is None:  # the account may have been erased while work was queued
            return
        investor_id = owner[0]
        cur.execute(
            "SELECT as_of,advised_only FROM portfolio_snapshot WHERE investor_id=%s", (investor_id,)
        )
        dates = cur.fetchall()
        for on, advised in dates:
            key = f"{investor_id}:{on}:{advised}"
            queue.enqueue(
                conn,
                "SNAPSHOT",
                key,
                {
                    "investor_id": investor_id,
                    "on": on.isoformat(),
                    "advised_only": advised,
                },
                refresh=True,
            )
            cur.execute(
                "INSERT INTO reference_sync_dependency VALUES (%s,'SNAPSHOT',%s) "
                "ON CONFLICT DO NOTHING",
                (account_id, key),
            )
        cur.execute("DELETE FROM portfolio_snapshot WHERE investor_id=%s", (investor_id,))


def _rebuild_snapshot(conn, payload):
    """Replay using date-effective identities and observed prices; never retain stale totals."""
    from app.db.prices import latest_prices
    from app.db.repository import load_transactions
    from app.db.snapshots import upsert_snapshot
    from app.engine.holdings import compute_holdings_partitioned
    from app.engine.snapshot import compute_snapshot

    on = date.fromisoformat(payload["on"])
    investor_id, advised = payload["investor_id"], payload["advised_only"]
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM investor WHERE id=%s", (investor_id,))
        if cur.fetchone() is None:
            return  # erasure must not leave a job recreating deleted portfolio caches
    transactions = load_transactions(
        conn, investor_id=investor_id, advised_only=advised, date_to=on
    )
    holdings, _ = compute_holdings_partitioned(transactions, on)
    prices = latest_prices(conn, [h.isin for h in holdings], on)
    # MissingPriceError leaves the job retryable until the existing price pipe supplies it.
    snapshot = compute_snapshot(transactions, prices, on)
    upsert_snapshot(conn, investor_id, advised, snapshot)


def run_once(conn, settings: Settings, limit: int | None = None) -> dict:
    if not settings.reference_sync_enabled:
        return {"enabled": False, "processed": 0, "failed": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_WORKER_LOCK,))
        acquired = cur.fetchone()[0]
    if not acquired:
        return {"enabled": True, "busy": True, "processed": 0, "failed": 0}
    processed = failed = 0
    try:
        # We hold the sole worker lock: 'running' now means an earlier process died.
        with conn.cursor() as cur:
            cur.execute("UPDATE reference_sync_task SET state='pending' WHERE state='running'")
        queue.schedule(conn)
        identity.schedule_identity(conn)
        _schedule_actions(conn)
        conn.commit()
        for _ in range(limit or settings.reference_worker_batch_size):
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT kind,task_key,payload,attempts FROM reference_sync_task
                       WHERE state IN ('pending','retry') AND available_at <= now()
                       ORDER BY available_at,kind,task_key LIMIT 1 FOR UPDATE SKIP LOCKED"""
                )
                row = cur.fetchone()
                if row is None:
                    break
                kind, key, payload, attempts = row
                cur.execute(
                    "UPDATE reference_sync_task SET state='running',updated_at=now() "
                    "WHERE kind=%s AND task_key=%s",
                    (kind, key),
                )
            conn.commit()
            try:
                checkpoint = process(conn, kind, key, payload, settings)
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE reference_sync_task SET state=%s, payload=%s::jsonb,
                           last_error=NULL, updated_at=now(), attempts=0,
                           last_success_at=CASE WHEN %s THEN now() ELSE last_success_at END,
                           available_at=now()+interval '1 second' WHERE kind=%s AND task_key=%s""",
                        (
                            "pending" if checkpoint else "done",
                            json.dumps(checkpoint or payload),
                            checkpoint is None,
                            kind,
                            key,
                        ),
                    )
                    if kind in ("ACTION", "IDENTITY") and checkpoint is None:
                        # Apply newly verified facts to accounts already imported.
                        cur.execute(
                            "UPDATE reference_sync_task SET state='pending',available_at=now() "
                            "WHERE kind='REPLAY'"
                        )
                conn.commit()
                processed += 1
            except Exception as exc:
                conn.rollback()
                delay = min(21600, 60 * 2 ** min(attempts, 9))
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE reference_sync_task SET state='retry',attempts=attempts+1,
                           last_error=%s,updated_at=now(),
                           available_at=now() + %s * interval '1 second'
                           WHERE kind=%s AND task_key=%s""",
                        (f"{type(exc).__name__}: {str(exc)[:500]}", delay, kind, key),
                    )
                conn.commit()
                failed += 1
                logger.warning("Reference task %s/%s failed: %s", kind, key, type(exc).__name__)
        promote_draft_aliases(conn)
        conn.commit()
        return {"enabled": True, "processed": processed, "failed": failed}
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_WORKER_LOCK,))
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--probe-isin", help="Check live free sources for this ISIN; no database writes"
    )
    args = parser.parse_args()
    if args.probe_isin:
        # A deployment connectivity check, never a substitute for ingestion or proof
        # of historical coverage. The caller supplies the security; no sentinel list.
        end = date.today()
        start = end - timedelta(days=30)
        failed = False
        probes = {
            "NSDL": lambda: {
                "records": len(NsdlParticipantSource().search(args.probe_isin).records)
            },
            "NSE circulars": lambda: {
                "isin_notices": len(
                    parse_circular_listing(NseCircularListSource().list_circulars(start, end))
                )
            },
            "NSE actions": lambda: {
                "bonus_split_notices": len(
                    parse_corporate_action_feed(NseCorporateActionFeedSource().fetch(start, end))
                )
            },
        }
        for name, probe in probes.items():
            try:
                print(json.dumps({"source": name, "ok": True, **probe()}), flush=True)
            except Exception as exc:
                failed = True
                print(json.dumps({"source": name, "ok": False, "error": str(exc)}), flush=True)
        raise SystemExit(1 if failed else 0)
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with connect(settings.database_url) as conn:
                result = run_once(conn, settings)
            logger.info("Reference cycle: %s", result)
            if args.once:
                raise SystemExit(1 if result.get("failed") else 0)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            logger.exception("Reference cycle failed; work remains queued")
            if args.once:
                raise SystemExit(1) from None
        time.sleep(settings.reference_worker_poll_seconds)


if __name__ == "__main__":
    main()
