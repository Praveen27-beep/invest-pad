"""Durable, shared public-data work. A crashed worker never loses an import request."""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, timedelta
from typing import Any

from app.ingest.nsdl import SearchPage


def enqueue(conn, kind: str, key: str, payload: dict, *, refresh: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO reference_sync_task(kind, task_key, payload)
               VALUES (%s, %s, %s::jsonb)
               ON CONFLICT(kind, task_key) DO UPDATE SET
                   payload = CASE WHEN %s THEN EXCLUDED.payload
                                  ELSE reference_sync_task.payload END,
                   state = CASE WHEN %s THEN 'pending' ELSE reference_sync_task.state END,
                   available_at = CASE WHEN %s THEN now()
                                       ELSE reference_sync_task.available_at END""",
            (kind, key, json.dumps(payload), refresh, refresh, refresh),
        )


def schedule(conn, today: date | None = None) -> None:
    """Coalesce uploads; shared issuer/month tasks prevent per-investor scraping."""
    today = today or date.today()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT r.account_id::text, min(t.txn_date),
                      array_agg(DISTINCT t.isin), r.requested_at, r.scheduled_at
               FROM reference_sync_import r JOIN transaction t ON t.account_id = r.account_id
               WHERE t.source != 'CORP_ACTION'
               GROUP BY r.account_id, r.requested_at, r.scheduled_at"""
        )
        accounts = cur.fetchall()
    for account_id, start, isins, requested, scheduled in accounts:
        changed = scheduled is None or requested > scheduled
        dependencies = []
        for prefix in sorted({isin[:7] for isin in isins if isin.startswith("IN")}):
            # A new daily key makes the observation date explicit. Old tasks/retries survive.
            key = f"{prefix}:{today.isoformat()}"
            enqueue(conn, "NSDL", key, {"query": prefix, "page": 1, "seen": []})
            dependencies.append((account_id, "NSDL", key))
        cursor = start.replace(day=1)
        while cursor <= today:
            end = min(cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1]), today)
            key = f"{cursor.isoformat()}:{end.isoformat()}"
            enqueue(conn, "NSE", key, {"start": cursor.isoformat(), "end": end.isoformat()})
            dependencies.append((account_id, "NSE", key))
            cursor = end + timedelta(days=1)
        enqueue(conn, "REPLAY", account_id, {"account_id": account_id}, refresh=changed)
        dependencies.append((account_id, "REPLAY", account_id))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO reference_sync_dependency(account_id, kind, task_key)
                   VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                dependencies,
            )
            cur.execute(
                "UPDATE reference_sync_import SET scheduled_at = %s WHERE account_id = %s",
                (requested, account_id),
            )
    conn.commit()


def store_nsdl_page(conn, page: SearchPage, prefix: str) -> int:
    """Never delete absent securities or turn a failed search into an inactive record."""
    matched = [r for r in page.records if r.isin.startswith(prefix)]
    with conn.cursor() as cur:
        for record in matched:
            raw = json.dumps(record.raw, sort_keys=True)
            # Issuer searches include debt/preference series. Keep their exact registry
            # observations without registering them as equities in the portfolio master.
            if record.instrument.upper() == "EQUITY SHARES":
                cur.execute(
                    """INSERT INTO security(isin, name) VALUES (%s,%s)
                       ON CONFLICT(isin) DO UPDATE
                           SET name = COALESCE(security.name, EXCLUDED.name)""",
                    (record.isin, record.issuer),
                )
            cur.execute(
                """INSERT INTO security_reference
                       (isin, issuer, description, instrument, status, source_url,
                        response_sha256, raw_payload)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(isin) DO UPDATE SET issuer=EXCLUDED.issuer,
                       description=EXCLUDED.description, instrument=EXCLUDED.instrument,
                       status=EXCLUDED.status, source_url=EXCLUDED.source_url,
                       response_sha256=EXCLUDED.response_sha256,
                       raw_payload=EXCLUDED.raw_payload, observed_at=now()""",
                (
                    record.isin,
                    record.issuer,
                    record.description,
                    record.instrument,
                    record.status,
                    page.url,
                    page.sha256,
                    raw,
                ),
            )
            cur.execute(
                """INSERT INTO security_reference_history
                       (isin, record_sha256, source_url, raw_payload) VALUES (%s,%s,%s,%s::jsonb)
                   ON CONFLICT DO NOTHING""",
                (record.isin, hashlib.sha256(raw.encode()).hexdigest(), page.url, raw),
            )
    return len(matched)


def status(conn, investor_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT t.state, count(*), max(t.last_success_at), max(t.updated_at)
               FROM reference_sync_task t JOIN (
                   SELECT DISTINCT d.kind, d.task_key FROM reference_sync_dependency d
                   JOIN account a ON a.id=d.account_id WHERE a.investor_id=%s
               ) d USING(kind, task_key) GROUP BY t.state""",
            (investor_id,),
        )
        states = cur.fetchall()
        cur.execute(
            """SELECT count(*) FROM reference_sync_import r JOIN account a ON a.id=r.account_id
               WHERE a.investor_id=%s AND
                   (r.scheduled_at IS NULL OR r.requested_at > r.scheduled_at)""",
            (investor_id,),
        )
        unscheduled = cur.fetchone()[0]
        cur.execute(
            """SELECT DISTINCT s.old_isin, s.current_isin, s.verification::text
               FROM security_alias s JOIN transaction t
                   ON t.isin IN (s.old_isin,s.current_isin)
               JOIN account a ON a.id=t.account_id
               WHERE a.investor_id=%s AND s.verification != 'VERIFIED'""",
            (investor_id,),
        )
        aliases = [{"isin": r[0], "related_isin": r[1], "reason": r[2]} for r in cur.fetchall()]
        cur.execute(
            """SELECT DISTINCT n.isin,n.subject FROM reference_notice n JOIN transaction t
               ON n.isin=t.isin JOIN account a ON a.id=t.account_id
               WHERE a.investor_id=%s""",
            (investor_id,),
        )
        aliases.extend({"isin": r[0], "related_isin": None, "reason": r[1]} for r in cur.fetchall())
        cur.execute(
            """SELECT DISTINCT t.isin,r.status FROM transaction t
               JOIN account a ON a.id=t.account_id
               LEFT JOIN security_reference r ON r.isin=t.isin
               LEFT JOIN security_alias s ON s.old_isin=t.isin
                   AND s.verification='VERIFIED' AND s.effective_date <= current_date
               WHERE a.investor_id=%s AND s.old_isin IS NULL
                   AND (r.isin IS NULL OR upper(r.status) != 'ACTIVE')""",
            (investor_id,),
        )
        aliases.extend(
            {
                "isin": r[0],
                "related_isin": None,
                "reason": (
                    f"NSDL status: {r[1]}; replacement identity is not established"
                    if r[1]
                    else "Exact NSDL record has not been observed"
                ),
            }
            for r in cur.fetchall()
        )
        cur.execute(
            "SELECT DISTINCT i.isin,i.reason FROM reference_account_issue i "
            "JOIN account a ON a.id=i.account_id WHERE a.investor_id=%s",
            (investor_id,),
        )
        aliases.extend({"isin": r[0], "related_isin": None, "reason": r[1]} for r in cur.fetchall())
    counts = {row[0]: row[1] for row in states}
    active = counts.get("pending", 0) + counts.get("running", 0) + unscheduled
    retry = counts.get("retry", 0)
    last_success = max((row[2] for row in states if row[2]), default=None)
    latest = max((row[3] for row in states if row[3]), default=None)
    phase = (
        "retrying" if retry else "processing" if active else "needs_evidence" if aliases else "idle"
    )
    return {
        "state": phase,
        "pending": active,
        "retrying": retry,
        "completed": counts.get("done", 0),
        "last_success_at": last_success,
        "updated_at": latest,
        "unresolved": aliases,
    }
