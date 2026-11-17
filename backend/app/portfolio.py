"""Holdings, watchlist, the investor's own limits, alerts, the monthly review, and the
connection graph.

Everything in this file is arithmetic and lookups over what the investor recorded. No
model is called. Nothing says what to buy or sell: an alert states that a number the
investor set has been crossed, and a review asks questions.
"""

import csv
import io
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel, Field

from . import auth, db

router = APIRouter()

# ---------------------------------------------------------------- reading a holdings file

COLUMNS = {
    "symbol": ("instrument", "symbol", "tradingsymbol", "stock", "scrip", "name", "company", "security",
               "stock name", "company name", "scrip name", "security name", "instrument name"),
    "quantity": ("qty", "quantity", "shares", "units"),
    "value": ("cur val", "current value", "market value", "value", "present value"),
    "price": ("ltp", "price", "close", "cmp", "current price", "market price"),
    "invested": ("invested", "invested value", "buy value", "cost value", "investment"),
    "avg_cost": ("avg cost", "average price", "avg price", "buy price", "average cost"),
}


def _key(header: str) -> str:
    return re.sub(r"[^a-z ]", "", header.lower().replace("_", " ")).strip()


def _number(text: str) -> Decimal | None:
    cleaned = re.sub(r"[₹$,\s]", "", text or "")
    if cleaned in ("", "-"):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_holdings(data: bytes) -> list[dict]:
    """Read a holdings CSV from a broker or tracker. Returns [{symbol, quantity, value, invested}].

    Column names are matched loosely (Zerodha's "Instrument, Qty., Avg. cost, LTP, Cur. val"
    works as is). Value is taken from a value column, or quantity × price. Raises ValueError
    with a message for the user if the file cannot be understood.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("This is not a text CSV file. Export holdings as CSV and try again.") from None
    rows = list(csv.reader(io.StringIO(text)))
    header_at = next((i for i, r in enumerate(rows[:15])
                      if {_key(c) for c in r} & set(COLUMNS["symbol"]) and {_key(c) for c in r} & set(COLUMNS["quantity"])),
                     None)
    if header_at is None:
        raise ValueError("Could not find the header row. The file needs a column for the stock name or symbol "
                         "and one for quantity.")
    index = {}
    for position, cell in enumerate(rows[header_at]):
        for field, names in COLUMNS.items():
            if _key(cell) in names and field not in index:
                index[field] = position
    if "value" not in index and "price" not in index:
        raise ValueError("The file needs a current value column, or a price column to multiply by quantity.")

    def cell(row, field):
        return row[index[field]] if field in index and index[field] < len(row) else ""

    merged: dict[str, dict] = {}
    for row in rows[header_at + 1:]:
        symbol, quantity = cell(row, "symbol").strip(), _number(cell(row, "quantity"))
        if not symbol or quantity is None or quantity <= 0 or symbol.lower().startswith("total"):
            continue
        value = _number(cell(row, "value"))
        if value is None and (price := _number(cell(row, "price"))) is not None:
            value = quantity * price
        if value is None or value < 0:
            continue
        invested = _number(cell(row, "invested"))
        if invested is None and (cost := _number(cell(row, "avg_cost"))) is not None:
            invested = quantity * cost
        item = merged.setdefault(symbol.lower(), {"symbol": symbol[:60], "quantity": Decimal(0), "value": Decimal(0),
                                                  "invested": None})
        item["quantity"] += quantity
        item["value"] += value
        if invested is not None:
            item["invested"] = (item["invested"] or Decimal(0)) + invested
    if not merged:
        raise ValueError("No holdings were found below the header row.")
    if len(merged) > 500:
        raise ValueError("More than 500 holdings in one file. Is this the right export?")
    return sorted(merged.values(), key=lambda h: -h["value"])


# ---------------------------------------------------------------- the portfolio now

def current_portfolio(cur) -> dict:
    """The latest snapshot with weights and each holding's company page, if linked."""
    cur.execute("SELECT id, source, filename, total_value, created_at FROM holding_snapshot "
                "ORDER BY created_at DESC LIMIT 1")
    snapshot = cur.fetchone()
    if not snapshot:
        return {"snapshot": None, "holdings": []}
    cur.execute(
        "SELECT h.symbol, h.quantity, h.value, h.invested, s.id AS subject_id, s.name AS subject_name, "
        "  (SELECT p.seq FROM position p WHERE p.subject_id = s.id) AS thesis_seq, "
        "  (SELECT count(*) FROM decision d WHERE d.subject_id = s.id) AS decisions "
        "FROM holding h LEFT JOIN holding_link l ON l.symbol_key = lower(h.symbol) "
        "LEFT JOIN subject s ON s.id = l.subject_id OR (l.subject_id IS NULL AND lower(s.name) = lower(h.symbol)) "
        "WHERE h.snapshot_id = %s ORDER BY h.value DESC, h.symbol", (snapshot["id"],))
    holdings = cur.fetchall()
    total = snapshot["total_value"]
    for h in holdings:
        h["weight_pct"] = (h["value"] * 100 / total).quantize(Decimal("0.01")) if total else Decimal(0)
        h["has_thesis"] = bool(h.pop("thesis_seq"))
    return {"snapshot": snapshot, "holdings": holdings}


RULES = {
    "max_position_pct": "No single position above this % of the portfolio",
    "max_top3_pct": "The three largest positions together stay below this %",
    "max_positions": "No more than this many positions",
    "thesis_required": "Every holding has a written thesis",
}


def breaches(holdings: list[dict], rules: dict[str, Decimal]) -> list[dict]:
    """Which enabled limits are crossed right now. Pure: same holdings and rules, same answer."""
    found = []
    if (limit := rules.get("max_position_pct")) is not None:
        for h in holdings:
            if h["weight_pct"] > limit:
                found.append({"rule_key": "max_position_pct", "symbol": h["symbol"],
                              "message": f'{h["symbol"]} is {h["weight_pct"]}% of the portfolio. '
                                         f"Your limit for one position is {limit:f}%."})
    if (limit := rules.get("max_top3_pct")) is not None and len(holdings) >= 3:
        top = sum(h["weight_pct"] for h in holdings[:3])
        if top > limit:
            names = ", ".join(h["symbol"] for h in holdings[:3])
            found.append({"rule_key": "max_top3_pct", "symbol": "",
                          "message": f"Your three largest positions ({names}) are {top}% of the portfolio. "
                                     f"Your limit is {limit:f}%."})
    if (limit := rules.get("max_positions")) is not None and len(holdings) > limit:
        found.append({"rule_key": "max_positions", "symbol": "",
                      "message": f"You hold {len(holdings)} positions. Your limit is {limit:f}."})
    if "thesis_required" in rules:
        for h in holdings:
            if not h["has_thesis"]:
                found.append({"rule_key": "thesis_required", "symbol": h["symbol"],
                              "message": f'You hold {h["symbol"]} ({h["weight_pct"]}%) with no written thesis. '
                                         "Your rule is that every holding has one."})
    return found


def refresh_alerts(cur) -> None:
    """Bring alerts in line with the portfolio: open new ones, close those no longer true."""
    cur.execute("SELECT key, value FROM limit_rule WHERE enabled")
    rules = {r["key"]: r["value"].normalize() for r in cur.fetchall()}
    now = breaches(current_portfolio(cur)["holdings"], rules)
    live = {(b["rule_key"], b["symbol"]) for b in now}
    cur.execute("SELECT id, rule_key, symbol FROM alert WHERE status <> 'resolved'")
    for row in cur.fetchall():
        if (row["rule_key"], row["symbol"]) not in live:
            cur.execute("UPDATE alert SET status = 'resolved', closed_at = now() WHERE id = %s", (row["id"],))
    for b in now:
        # An existing open or acknowledged alert for the same rule and symbol is left as it is,
        # with its message brought up to date.
        cur.execute(
            "INSERT INTO alert (rule_key, symbol, message) VALUES (%s, %s, %s) "
            "ON CONFLICT (owner_id, rule_key, symbol) WHERE status <> 'resolved' DO UPDATE SET message = excluded.message",
            (b["rule_key"], b["symbol"], b["message"]))


# ---------------------------------------------------------------- holdings endpoints

@router.post("/portfolio/import", status_code=201)
def import_holdings(file: UploadFile = File(...), user: dict = Depends(auth.current_user)):
    data = file.file.read(1_000_001)
    if len(data) > 1_000_000:
        raise HTTPException(413, "File is larger than 1 MB")
    try:
        holdings = parse_holdings(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    total = sum(h["value"] for h in holdings)
    with db.as_user(user["id"]) as cur:
        cur.execute("INSERT INTO holding_snapshot (source, filename, total_value) VALUES ('csv', %s, %s) RETURNING id",
                    ((file.filename or "")[:200], total))
        snapshot_id = cur.fetchone()["id"]
        for h in holdings:
            cur.execute("INSERT INTO holding (snapshot_id, symbol, quantity, value, invested) VALUES (%s, %s, %s, %s, %s)",
                        (snapshot_id, h["symbol"], h["quantity"], h["value"], h["invested"]))
        refresh_alerts(cur)
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('portfolio.import', %s)", (str(snapshot_id),))
        return _portfolio(cur)


def _portfolio(cur) -> dict:
    portfolio = current_portfolio(cur)
    cur.execute("SELECT key, value, enabled FROM limit_rule")
    saved = {r["key"]: r for r in cur.fetchall()}
    portfolio["limits"] = [{"key": k, "label": label, "value": saved[k]["value"] if k in saved else Decimal(0),
                            "enabled": saved[k]["enabled"] if k in saved else False} for k, label in RULES.items()]
    cur.execute("SELECT id, rule_key, symbol, message, status, note, created_at FROM alert WHERE status <> 'resolved' "
                "ORDER BY created_at DESC")
    portfolio["alerts"] = cur.fetchall()
    cur.execute("SELECT id, name, watch_since, "
                "  (SELECT count(*) FROM note n WHERE n.subject_id = s.id) AS notes, "
                "  (SELECT count(*) FROM document d WHERE d.subject_id = s.id) AS documents "
                "FROM subject s WHERE watch_since IS NOT NULL ORDER BY watch_since")
    held = {h["subject_id"] for h in portfolio["holdings"]}
    portfolio["watchlist"] = [w | {"held": w["id"] in held} for w in cur.fetchall()]
    return portfolio


@router.get("/portfolio")
def get_portfolio(user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        return _portfolio(cur)


@router.delete("/portfolio", status_code=204)
def delete_portfolio(user: dict = Depends(auth.current_user)):
    """Remove every imported snapshot of holdings, and the alerts built on them."""
    with db.as_user(user["id"]) as cur:
        cur.execute("DELETE FROM holding_snapshot")
        cur.execute("DELETE FROM alert")
        cur.execute("INSERT INTO audit_log (action) VALUES ('portfolio.delete')")


class LinkIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=60)
    subject_id: uuid.UUID | None


@router.put("/portfolio/link")
def link_holding(body: LinkIn, user: dict = Depends(auth.current_user)):
    """Say which company page a symbol in the holdings file belongs to (or clear it)."""
    try:
        with db.as_user(user["id"]) as cur:
            cur.execute("DELETE FROM holding_link WHERE symbol_key = %s", (body.symbol.lower(),))
            if body.subject_id:
                cur.execute("INSERT INTO holding_link (symbol_key, subject_id) VALUES (%s, %s)",
                            (body.symbol.lower(), body.subject_id))
            refresh_alerts(cur)
            return _portfolio(cur)
    except ForeignKeyViolation:
        raise HTTPException(404, "Company not found") from None


class LimitIn(BaseModel):
    key: str
    value: Decimal = Field(ge=0, le=1000)
    enabled: bool


@router.put("/portfolio/limits")
def set_limit(body: LimitIn, user: dict = Depends(auth.current_user)):
    if body.key not in RULES:
        raise HTTPException(422, "Unknown limit")
    if body.enabled and body.key != "thesis_required" and body.value <= 0:
        raise HTTPException(422, "Enter a number above zero to turn this limit on")
    with db.as_user(user["id"]) as cur:
        cur.execute("INSERT INTO limit_rule (key, value, enabled) VALUES (%s, %s, %s) "
                    "ON CONFLICT (owner_id, key) DO UPDATE SET value = excluded.value, enabled = excluded.enabled",
                    (body.key, body.value, body.enabled))
        refresh_alerts(cur)
        return _portfolio(cur)


class AckIn(BaseModel):
    note: str = Field(default="", max_length=2_000)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: uuid.UUID, body: AckIn, user: dict = Depends(auth.current_user)):
    """"I have seen this." Optionally with a note on why it stands. It stays listed until it is no longer true."""
    with db.as_user(user["id"]) as cur:
        cur.execute("UPDATE alert SET status = 'acknowledged', note = %s WHERE id = %s AND status = 'open' RETURNING id",
                    (body.note.strip(), alert_id))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        return _portfolio(cur)


class WatchIn(BaseModel):
    watching: bool


@router.put("/subjects/{subject_id}/watch")
def set_watch(subject_id: uuid.UUID, body: WatchIn, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("UPDATE subject SET watch_since = CASE WHEN %s THEN coalesce(watch_since, now()) END "
                    "WHERE id = %s RETURNING id, watch_since", (body.watching, subject_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return row


# ---------------------------------------------------------------- the monthly review

def build_review(cur, today: datetime) -> list[dict]:
    """Questions for this month, each resting on something the investor recorded. At most ten."""
    portfolio = current_portfolio(cur)
    holdings = portfolio["holdings"]
    cur.execute("SELECT key, value FROM limit_rule WHERE enabled")
    rules = {r["key"]: r["value"].normalize() for r in cur.fetchall()}
    items: list[dict] = []

    def add(kind, question, basis, subject_id=None):
        items.append({"kind": kind, "question": question, "basis": basis, "subject_id": subject_id})

    limit = rules.get("max_position_pct")
    for h in holdings:
        if limit is not None and h["weight_pct"] > limit:
            add("over_limit", f'What is the case for holding {h["symbol"]} above your own limit?',
                f'{h["symbol"]} is {h["weight_pct"]}% of the portfolio; your limit is {limit:f}%.', h["subject_id"])

    for h in holdings:
        if not h["subject_id"]:
            continue
        cur.execute(
            "SELECT v.body, v.created_at FROM assumption a JOIN position p ON p.id = a.position_id "
            "JOIN assumption_version v ON v.assumption_id = a.id AND v.seq = a.seq "
            "WHERE p.subject_id = %s AND v.state = 'broken' ORDER BY v.created_at LIMIT 1", (h["subject_id"],))
        broken = cur.fetchone()
        if broken:
            add("broken_assumption", f'You still hold {h["symbol"]}. What has replaced the assumption you marked broken?',
                f'On {broken["created_at"]:%d %b %Y} you marked as broken: “{broken["body"]}”. '
                f'{h["symbol"]} is {h["weight_pct"]}% of the portfolio.', h["subject_id"])

    for h in holdings:
        if not h["has_thesis"]:
            add("no_thesis", f'What must be true for {h["symbol"]} to work?',
                f'You hold {h["symbol"]} ({h["weight_pct"]}%) and have not written a thesis for it.', h["subject_id"])
        elif not h["decisions"]:
            add("no_decision", f'Why did you buy {h["symbol"]}? Record the one reason that decided it.',
                f'You hold {h["symbol"]} ({h["weight_pct"]}%) with a thesis but no decision in the journal.',
                h["subject_id"])

    if holdings and holdings[0]["subject_id"]:
        top = holdings[0]
        cur.execute(
            "SELECT count(*) FILTER (WHERE e.direction = 'for') AS pro, count(*) FILTER (WHERE e.direction = 'against') AS con "
            "FROM evidence e JOIN assumption a ON a.id = e.assumption_id JOIN position p ON p.id = a.position_id "
            "WHERE p.subject_id = %s AND e.retracted_at IS NULL", (top["subject_id"],))
        ev = cur.fetchone()
        add("largest_position", f'Is the size of {top["symbol"]} matched by what you know about it?',
            f'{top["symbol"]} is your largest position at {top["weight_pct"]}%. You have recorded {ev["pro"]} piece(s) '
            f'of evidence for its assumptions and {ev["con"]} against.', top["subject_id"])

    held = {h["subject_id"] for h in holdings}
    cur.execute("SELECT s.id, s.name, s.watch_since, "
                "  (SELECT count(*) FROM note n WHERE n.subject_id = s.id) + "
                "  (SELECT count(*) FROM document d WHERE d.subject_id = s.id) AS work, "
                "  (SELECT max(d.decided_on) FROM decision d WHERE d.subject_id = s.id) AS last_decision "
                "FROM subject s WHERE s.watch_since IS NOT NULL ORDER BY s.watch_since")
    for w in cur.fetchall():
        days = (today - w["watch_since"]).days
        if w["id"] not in held and days >= 60 and w["work"] > 0 and not w["last_decision"]:
            add("watchlist", f'What is stopping you on {w["name"]} — and what would settle it either way?',
                f'{w["name"]} has been on your watchlist for {days} days with {w["work"]} note(s) and document(s), '
                "and no decision recorded.", w["id"])

    if holdings:
        add("open", "Which position would you not buy today at its current weight?",
            f"You hold {len(holdings)} position(s).")
    return items[:10]


def _review(cur, review_id) -> dict:
    cur.execute("SELECT id, period, created_at FROM review WHERE id = %s", (review_id,))
    review = cur.fetchone()
    cur.execute("SELECT id, ordinal, kind, subject_id, question, basis, answer, answered_at FROM review_item "
                "WHERE review_id = %s ORDER BY ordinal", (review_id,))
    review["items"] = cur.fetchall()
    return review


@router.get("/review/status")
def review_status(user: dict = Depends(auth.current_user)):
    """For the nav badge: unanswered questions in this month's review, if it has been opened.
    Reading this never builds the review, so the questions are still built from whatever the
    user has recorded by the time they actually open it."""
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT count(*) AS n FROM review_item i JOIN review r ON r.id = i.review_id "
                    "WHERE r.period = %s AND i.answered_at IS NULL", (datetime.now(UTC).strftime("%Y-%m"),))
        return {"unanswered": cur.fetchone()["n"]}


@router.get("/review")
def get_review(user: dict = Depends(auth.current_user)):
    """This month's review. Built the first time it is opened in a month, then fixed, so the
    questions do not shift while you are answering them."""
    now = datetime.now(UTC)
    period = now.strftime("%Y-%m")
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT id FROM review WHERE period = %s", (period,))
        row = cur.fetchone()
        if not row:
            items = build_review(cur, now)
            if not items:
                return {"id": None, "period": period, "items": [], "past": _past(cur)}
            cur.execute("INSERT INTO review (period) VALUES (%s) ON CONFLICT (owner_id, period) DO NOTHING RETURNING id",
                        (period,))
            row = cur.fetchone()
            if row:
                for ordinal, item in enumerate(items, 1):
                    cur.execute("INSERT INTO review_item (review_id, ordinal, kind, subject_id, question, basis) "
                                "VALUES (%s, %s, %s, %s, %s, %s)",
                                (row["id"], ordinal, item["kind"], item["subject_id"], item["question"], item["basis"]))
            else:
                cur.execute("SELECT id FROM review WHERE period = %s", (period,))
                row = cur.fetchone()
        return _review(cur, row["id"]) | {"past": _past(cur)}


def _past(cur) -> list[dict]:
    cur.execute("SELECT r.id, r.period, count(i.id) AS questions, count(i.answered_at) AS answered "
                "FROM review r LEFT JOIN review_item i ON i.review_id = r.id GROUP BY r.id ORDER BY r.period DESC")
    return cur.fetchall()


@router.get("/review/{review_id}")
def get_past_review(review_id: uuid.UUID, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("SELECT 1 FROM review WHERE id = %s", (review_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        return _review(cur, review_id)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=4_000)


@router.put("/review/items/{item_id}")
def answer_item(item_id: uuid.UUID, body: AnswerIn, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("UPDATE review_item SET answer = %s, answered_at = now() WHERE id = %s "
                    "RETURNING id, answer, answered_at", (body.answer.strip(), item_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return row


# ---------------------------------------------------------------- the connection graph

@router.get("/graph")
def graph(subject_id: uuid.UUID | None = None, user: dict = Depends(auth.current_user)):
    """Everything that is connected, as nodes and edges: companies, notes, documents,
    assumptions and decisions, joined by the links, citations and filings between them.

    For one company, or across all of them. Read from the record; nothing is inferred.
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(kind, ident, label, **extra):
        nodes[f"{kind}:{ident}"] = {"id": f"{kind}:{ident}", "kind": kind, "ref": str(ident), "label": label[:80], **extra}

    def edge(a, b, kind):
        if a in nodes and b in nodes and a != b:
            edges.append({"from": a, "to": b, "kind": kind})

    with db.as_user(user["id"]) as cur:
        one = "(%s::uuid IS NULL OR {col} = %s)"
        args = (subject_id, subject_id)
        cur.execute(f"SELECT id, name FROM subject s WHERE {one.format(col='s.id')}", args)
        subjects = cur.fetchall()
        if subject_id and not subjects:
            raise HTTPException(404, "Not found")
        for s in subjects:
            node("company", s["id"], s["name"])
        cur.execute(f"SELECT id, title, subject_id, title_key FROM note n WHERE {one.format(col='n.subject_id')}", args)
        notes = cur.fetchall()
        by_title = {n["title_key"]: n["id"] for n in notes}
        for n in notes:
            node("note", n["id"], n["title"])
            edge(f"note:{n['id']}", f"company:{n['subject_id']}", "filed under")
        cur.execute(f"SELECT id, title, subject_id FROM document d WHERE {one.format(col='d.subject_id')}", args)
        for d in cur.fetchall():
            node("document", d["id"], d["title"])
            edge(f"document:{d['id']}", f"company:{d['subject_id']}", "filed under")
        cur.execute(
            "SELECT a.id, v.body, v.state, p.subject_id FROM assumption a JOIN position p ON p.id = a.position_id "
            f"JOIN assumption_version v ON v.assumption_id = a.id AND v.seq = a.seq WHERE {one.format(col='p.subject_id')}",
            args)
        for a in cur.fetchall():
            node("assumption", a["id"], a["body"], state=a["state"])
            edge(f"assumption:{a['id']}", f"company:{a['subject_id']}", "thesis of")
        cur.execute(f"SELECT id, type, decided_on, subject_id, assumptions FROM decision d WHERE {one.format(col='d.subject_id')}",
                    args)
        for d in cur.fetchall():
            node("decision", d["id"], f'{d["type"]} · {d["decided_on"]:%d %b %Y}')
            edge(f"decision:{d['id']}", f"company:{d['subject_id']}", "decision on")
            for a in d["assumptions"]:
                edge(f"decision:{d['id']}", f"assumption:{a['id']}", "rested on")
        # Note-to-note links; a link whose target note is outside this view is skipped.
        cur.execute("SELECT DISTINCT from_note_id, to_title_key FROM note_link")
        for link in cur.fetchall():
            if link["to_title_key"] in by_title:
                edge(f"note:{link['from_note_id']}", f"note:{by_title[link['to_title_key']]}", "links to")
        # Evidence: the document or note an assumption's evidence cites.
        cur.execute("SELECT DISTINCT e.assumption_id, e.direction, c.document_id, e.note_id FROM evidence e "
                    "LEFT JOIN chunk c ON c.id = e.chunk_id WHERE e.retracted_at IS NULL")
        for e in cur.fetchall():
            source = f"document:{e['document_id']}" if e["document_id"] else f"note:{e['note_id']}"
            edge(source, f"assumption:{e['assumption_id']}", f"evidence {e['direction']}")
    seen, unique = set(), []
    for e in edges:
        key = (e["from"], e["to"], e["kind"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return {"nodes": list(nodes.values()), "edges": unique}
