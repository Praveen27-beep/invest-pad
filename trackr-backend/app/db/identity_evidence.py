"""Confirm split identity against dated NSE records, never against issuer resemblance alone."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from app.db import corporate_actions as ca
from app.db.reference_sync import enqueue
from app.db.security_alias import SecurityAlias, add_alias, reconcile_after_alias, verify_alias
from app.engine.corporate_actions import CorporateAction, Verification, check_price_consistency
from app.ingest.corporate_action_feed import parse_corporate_action_feed
from app.prices.sources import (
    LEGACY_NSE_URL,
    NSE_CURRENT_FORMAT_SINCE,
    NSE_URL,
    NotPublished,
    nse_source,
)
from app.prices.udiff import parse


class EvidencePending(ValueError):
    pass


def schedule_identity(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT t.account_id::text, c.circular_number, c.new_isin
               FROM isin_change_circular c JOIN transaction t
                   ON left(t.isin,7)=left(c.new_isin,7)
               WHERE c.ex_date IS NOT NULL AND c.pdf_sha256 IS NOT NULL"""
        )
        pairs = cur.fetchall()
    for account, number, new_isin in pairs:
        # resolve_split needs NSDL's exact record for the NEW ISIN, which no holding
        # names yet -- so reference_sync.schedule (held ISINs only) would never fetch it.
        enqueue(conn, "NSDL", f"{new_isin}:circular", {"query": new_isin, "page": 1, "seen": []})
        enqueue(conn, "IDENTITY", number, {"circular_number": number})
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reference_sync_dependency VALUES (%s,'IDENTITY',%s) "
                "ON CONFLICT DO NOTHING",
                (account, number),
            )


def _day(conn, on: date, source):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_url,payload_sha256 FROM reference_bhavcopy_day WHERE price_date=%s",
            (on,),
        )
        receipt = cur.fetchone()
    if receipt is None:
        payload = source.fetch(on)
        rows = parse(payload, "NSE")
        if not rows or any(r.price_date != on for r in rows):
            raise EvidencePending("Exchange archive date does not match requested date")
        url = (
            NSE_URL.format(d=on)
            if on >= NSE_CURRENT_FORMAT_SINCE
            else LEGACY_NSE_URL.format(d=on, mon=on.strftime("%b").upper())
        )
        digest = hashlib.sha256(payload).hexdigest()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reference_bhavcopy_day VALUES (%s,%s,%s,now()) ON CONFLICT DO NOTHING",
                (on, url, digest),
            )
            cur.executemany(
                "INSERT INTO reference_bhavcopy_security VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                [(on, r.isin, r.symbol, r.series, r.close) for r in rows],
            )
        conn.commit()
        receipt = (url, digest)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT isin,symbol,series,close FROM reference_bhavcopy_security WHERE price_date=%s",
            (on,),
        )
        return cur.fetchall(), {"date": on.isoformat(), "url": receipt[0], "sha256": receipt[1]}


def resolve_split(conn, number: str, source=None) -> None:
    """Require the circular's terms plus dated exchange identities and traded prices.

    NSDL classification can reject a different instrument, but does not independently
    corroborate the issuer's terms. The observed cum/ex traded prices are independent
    of the announcement and corroborate the ratio. Symbol and issuer resemblance
    alone never qualify. All account replays must also reconcile before commit.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol,new_isin,ex_date,remarks_raw,source_url,pdf_sha256,wef_date "
            "FROM isin_change_circular WHERE circular_number=%s",
            (number,),
        )
        circular = cur.fetchone()
    if not circular:
        raise EvidencePending("Circular is not parsed yet")
    symbol, new, ex_date, remarks, url, digest, wef_date = circular
    if ex_date > date.today():
        raise EvidencePending("Corporate action has not become effective")
    notices = parse_corporate_action_feed(
        json.dumps(
            [
                {
                    "isin": new,
                    "symbol": symbol,
                    "exDate": ex_date.strftime("%d-%b-%Y"),
                    "subject": remarks,
                }
            ]
        ).encode()
    )
    if len(notices) != 1 or notices[0].action_type.value != "SPLIT":
        raise EvidencePending("Circular needs terms beyond the supported split identity proof")
    source = source or nse_source()
    after, after_receipt = _day(conn, ex_date, source)
    new_rows = [r for r in after if r[0] == new and r[1] == symbol]
    identity_receipt = after_receipt
    if not new_rows and wef_date and wef_date > ex_date:
        # The real Tata Steel 2022 circular says ex July 28, w.e.f. July 29.
        # July 28's archive still prints the OLD ISIN with the split-adjusted price.
        # Consult only the document's explicit implementation date, never search for
        # an arbitrary later symbol match. Price corroboration still uses the ex-date.
        identity_rows, identity_receipt = _day(conn, wef_date, source)
        new_rows = [r for r in identity_rows if r[0] == new and r[1] == symbol]
    if len(new_rows) != 1:
        raise EvidencePending("New ISIN/symbol is not unique on the circular's dated sessions")
    before = []
    for offset in range(1, 8):
        on = ex_date - timedelta(days=offset)
        if on.weekday() >= 5:
            continue
        try:
            rows, before_receipt = _day(conn, on, source)
        except NotPublished:
            continue
        before = [r for r in rows if r[1] == symbol]
        # Use the immediately preceding published session; do not hunt for an older
        # convenient identity when the nearest session contradicts it.
        break
    if len(before) != 1:
        raise EvidencePending("Old ISIN/symbol is not unique in the preceding exchange file")
    old = before[0][0]
    if old == new or old[:9] != new[:9] or not old.startswith("INE"):
        raise EvidencePending("Observed identifiers are not a same-class equity replacement")
    ex_rows = [r for r in after if r[1] == symbol]
    if len(ex_rows) != 1 or ex_rows[0][0] not in (old, new):
        raise EvidencePending("Ex-date archive contradicts the observed replacement identifiers")
    if len({before[0][2], ex_rows[0][2], new_rows[0][2]}) != 1:
        raise EvidencePending("Exchange series changed across the replacement")
    row = notices[0]
    action = CorporateAction(
        isin=new,
        action_type=row.action_type,
        ex_date=ex_date,
        face_value_before=row.face_value_before,
        face_value_after=row.face_value_after,
        source=f"NSE circular {number}",
        source_url=url,
        verification=Verification.VERIFIED,
        price_cum=before[0][3],
        price_ex=ex_rows[0][3],
    )
    failure = check_price_consistency(action)
    if failure:
        raise EvidencePending(f"Split evidence requires review: {failure.code}")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT isin,instrument FROM security_reference WHERE isin=ANY(%s)", ([old, new],)
        )
        registry = dict(cur.fetchall())
    if registry.get(new) != "EQUITY SHARES":
        raise EvidencePending("Waiting for exact new-ISIN equity classification from NSDL")
    if old in registry and registry[old] != "EQUITY SHARES":
        raise EvidencePending("NSDL old instrument classification contradicts equity replacement")
    with conn.cursor() as cur:
        for isin in (old, new):
            cur.execute(
                "INSERT INTO security(isin,symbol,exchange,asset_class) "
                "VALUES (%s,%s,'NSE','EQ') ON CONFLICT(isin) DO NOTHING",
                (isin, symbol),
            )
        cur.execute(
            "SELECT current_isin,effective_date,verification::text FROM security_alias "
            "WHERE old_isin=%s",
            (old,),
        )
        existing = cur.fetchone()
    if existing and (existing[:2] != (new, ex_date) or existing[2] == "DISPUTED"):
        raise EvidencePending("Existing alias conflicts with dated exchange evidence")
    if not existing:
        add_alias(conn, SecurityAlias(old, new, ex_date, action.source, url))
    evidence = {
        "circular": {"url": url, "sha256": digest},
        "before": before_receipt,
        "after": after_receipt,
        "identity_session": identity_receipt,
        "ex_price_isin": ex_rows[0][0],
        "series": ex_rows[0][2],
        "old_isin": old,
        "new_isin": new,
        "symbol": symbol,
    }
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO security_alias_evidence VALUES (%s,%s,%s,%s::jsonb,now()) "
            "ON CONFLICT(old_isin) DO NOTHING",
            (old, new, ex_date, json.dumps(evidence)),
        )
    existing_actions = ca.list_corporate_actions(conn, [old, new])
    matches = [
        a for a in existing_actions if a.action_type == action.action_type and a.ex_date == ex_date
    ]
    if matches:
        if len(matches) != 1 or matches[0].multiplier() != action.multiplier():
            raise EvidencePending("Conflicting corporate-action ratios or duplicate identities")
        if matches[0].verification is Verification.DISPUTED:
            raise EvidencePending("Corporate action was disputed")
        verify_alias(conn, old)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE corporate_action SET price_cum=%s,price_ex=%s WHERE id=%s",
                (action.price_cum, action.price_ex, matches[0].id),
            )
        ca.verify_corporate_action(conn, matches[0].id)
    else:
        verify_alias(conn, old)
        ca.add_corporate_action(conn, action)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT account_id::text FROM transaction WHERE isin=ANY(%s)", ([old, new],)
        )
        accounts = [r[0] for r in cur.fetchall()]
    for account in accounts:
        ca.apply_known_actions_for_account(conn, account)
        result = reconcile_after_alias(conn, account, old, new, date.today())
        if not result.ok:
            raise EvidencePending(
                "Linked history does not reconcile: " + "; ".join(result.failures)
            )
    conn.commit()
