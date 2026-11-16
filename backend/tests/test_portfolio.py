"""Holdings, limits and alerts, watchlist, the monthly review, the graph — and that none of it gives advice."""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app import portfolio

ZERODHA = """Instrument,Qty.,Avg. cost,LTP,Cur. val,P&L,Net chg.,Day chg.
IEX,1000,150.00,170.00,"1,70,000.00",20000,13.3,0.5
GSMFOILS,500,100.00,120.00,60000.00,10000,20,1.0
PVRINOX,100,1500,1000,100000,-50000,-33.3,-1
"""


def load(client, text=ZERODHA, name="holdings.csv"):
    return client.post("/portfolio/import", files={"file": (name, text.encode(), "text/csv")})


@pytest.fixture
def me(new_user):
    return new_user()


def test_zerodha_export_is_read_and_weighted(me):
    r = load(me)
    assert r.status_code == 201, r.text
    p = r.json()
    assert Decimal(p["snapshot"]["total_value"]) == Decimal("330000.00")
    assert [(h["symbol"], h["weight_pct"]) for h in p["holdings"]] == [
        ("IEX", 51.52), ("PVRINOX", 30.3), ("GSMFOILS", 18.18)]
    assert Decimal(p["holdings"][0]["invested"]) == Decimal("150000.00")
    assert sum(Decimal(str(h["weight_pct"])) for h in p["holdings"]) == Decimal("100.00")


def test_other_layouts_and_bad_files():
    rows = portfolio.parse_holdings(b"Report generated 16 Nov\n\nStock Name,Quantity,Current Price\nABC Ltd,10,50\n"
                                    b"ABC Ltd,5,50\nTotal,15,\nXYZ,0,10\n")
    assert rows == [{"symbol": "ABC Ltd", "quantity": Decimal(15), "value": Decimal(750), "invested": None}]
    rupees = portfolio.parse_holdings("Symbol,Qty,Market Value\nIEX,10,\"₹ 1,700.50\"\n".encode())
    assert rupees[0]["value"] == Decimal("1700.50")
    for bad, message in [(b"\xff\xfe\x00binary", "not a text CSV"), (b"a,b\n1,2\n", "header row"),
                         (b"Symbol,Qty\nIEX,10\n", "current value column"), (b"Symbol,Qty,Value\n", "No holdings")]:
        with pytest.raises(ValueError, match=message):
            portfolio.parse_holdings(bad)


def test_bad_upload_is_explained(me):
    r = load(me, "just,some\nrandom,text\n")
    assert r.status_code == 422 and "header row" in r.json()["detail"]
    assert me.get("/portfolio").json()["snapshot"] is None


def test_limits_are_off_until_turned_on_then_alert_and_resolve(me):
    load(me)
    assert me.get("/portfolio").json()["alerts"] == []
    assert [limit["enabled"] for limit in me.get("/portfolio").json()["limits"]] == [False] * 4
    assert me.put("/portfolio/limits", json={"key": "max_position_pct", "value": 0, "enabled": True}).status_code == 422
    assert me.put("/portfolio/limits", json={"key": "nonsense", "value": 5, "enabled": True}).status_code == 422

    p = me.put("/portfolio/limits", json={"key": "max_position_pct", "value": 25, "enabled": True}).json()
    assert sorted(a["message"] for a in p["alerts"]) == [
        "IEX is 51.52% of the portfolio. Your limit for one position is 25%.",
        "PVRINOX is 30.30% of the portfolio. Your limit for one position is 25%."]

    # Acknowledge one with a note; it stays listed while it is still true.
    iex = next(a for a in p["alerts"] if a["symbol"] == "IEX")
    acked = me.post(f"/alerts/{iex['id']}/acknowledge", json={"note": "Deliberate: highest conviction."}).json()
    assert {a["symbol"]: (a["status"], a["note"]) for a in acked["alerts"]}["IEX"] == (
        "acknowledged", "Deliberate: highest conviction.")
    assert me.post(f"/alerts/{iex['id']}/acknowledge", json={}).status_code == 404

    # A new import: IEX is still over (alert kept, not duplicated, message updated); PVRINOX is not (alert closes).
    after = load(me, "Symbol,Qty,Value\nIEX,1000,170000\nPVRINOX,100,40000\nGSMFOILS,500,60000\nNEWCO,1,230000\n").json()
    alerts = {a["symbol"]: a for a in after["alerts"]}
    assert set(alerts) == {"IEX", "NEWCO"}
    assert alerts["IEX"]["status"] == "acknowledged" and "34.00%" in alerts["IEX"]["message"]
    assert alerts["NEWCO"]["status"] == "open"

    # Turning the limit off clears what depended on it.
    off = me.put("/portfolio/limits", json={"key": "max_position_pct", "value": 25, "enabled": False}).json()
    assert off["alerts"] == []


def test_the_other_limits(me):
    load(me)
    me.put("/portfolio/limits", json={"key": "max_top3_pct", "value": 80, "enabled": True})
    me.put("/portfolio/limits", json={"key": "max_positions", "value": 2, "enabled": True})
    p = me.put("/portfolio/limits", json={"key": "thesis_required", "value": 0, "enabled": True}).json()
    messages = sorted(a["message"] for a in p["alerts"])
    assert "You hold 3 positions. Your limit is 2." in messages
    assert "Your three largest positions (IEX, PVRINOX, GSMFOILS) are 100.00% of the portfolio. Your limit is 80%." in messages
    assert sum("with no written thesis" in m for m in messages) == 3

    # Linking a holding to a company page that has a thesis satisfies the thesis rule for it.
    company = me.post("/subjects", json={"name": "Indian Energy Exchange"}).json()["id"]
    me.put(f"/subjects/{company}/thesis", json={"body": "Incumbent keeps share."})
    linked = me.put("/portfolio/link", json={"symbol": "IEX", "subject_id": company}).json()
    assert linked["holdings"][0]["subject_name"] == "Indian Energy Exchange" and linked["holdings"][0]["has_thesis"]
    assert sum("with no written thesis" in a["message"] for a in linked["alerts"]) == 2
    # A company named exactly like the symbol is matched without linking.
    me.post("/subjects", json={"name": "gsmfoils"})
    assert me.get("/portfolio").json()["holdings"][2]["subject_name"] == "gsmfoils"
    assert me.put("/portfolio/link", json={"symbol": "IEX", "subject_id": None}).json()["holdings"][0]["subject_id"] is None


def test_nothing_in_alerts_or_reviews_reads_as_advice(me):
    """Every sentence this module can produce, checked for instructions to trade."""
    load(me)
    for key, value in [("max_position_pct", 10), ("max_top3_pct", 50), ("max_positions", 1), ("thesis_required", 0)]:
        me.put("/portfolio/limits", json={"key": key, "value": value, "enabled": True})
    company = me.post("/subjects", json={"name": "IEX"}).json()["id"]
    me.put(f"/subjects/{company}/thesis", json={"body": "t"})
    a = me.post(f"/subjects/{company}/assumptions", json={"body": "Coupling is limited", "basis": "judgement"}).json()["id"]
    me.put(f"/assumptions/{a}", json={"body": "Coupling is limited", "basis": "judgement", "state": "broken", "reason": "r"})
    text = " ".join([x["message"] for x in me.get("/portfolio").json()["alerts"]]
                    + [i["question"] + " " + i["basis"] for i in me.get("/review").json()["items"]])
    assert len(text) > 400
    banned = r"\b(sell|buy more|trim|reduce|exit|rebalance|offset|hedge|you should|we recommend|consider selling)\b"
    assert not re.search(banned, text, re.IGNORECASE), re.findall(banned, text, re.IGNORECASE)


def test_watchlist(me):
    company = me.post("/subjects", json={"name": "Watch Co"}).json()["id"]
    on = me.put(f"/subjects/{company}/watch", json={"watching": True}).json()
    assert on["watch_since"] is not None
    again = me.put(f"/subjects/{company}/watch", json={"watching": True}).json()
    assert again["watch_since"] == on["watch_since"]                      # the clock is not reset
    [w] = me.get("/portfolio").json()["watchlist"]
    assert (w["name"], w["held"], w["notes"]) == ("Watch Co", False, 0)
    assert me.put(f"/subjects/{company}/watch", json={"watching": False}).json()["watch_since"] is None
    assert me.get("/portfolio").json()["watchlist"] == []


def test_review_questions_rest_on_the_record(me, owner):
    load(me)
    me.put("/portfolio/limits", json={"key": "max_position_pct", "value": 25, "enabled": True})
    iex = me.post("/subjects", json={"name": "IEX"}).json()["id"]
    me.put(f"/subjects/{iex}/thesis", json={"body": "Incumbent keeps share."})
    a = me.post(f"/subjects/{iex}/assumptions", json={"body": "Coupling stays limited to DAM", "basis": "judgement"}).json()["id"]
    me.put(f"/assumptions/{a}", json={"body": "Coupling stays limited to DAM", "basis": "judgement", "state": "broken",
                                      "reason": "Extended to RTM."})
    pvr = me.post("/subjects", json={"name": "PVRINOX"}).json()["id"]
    me.put(f"/subjects/{pvr}/thesis", json={"body": "Screens recover."})
    stuck = me.post("/subjects", json={"name": "Stuck Co"}).json()["id"]
    me.post("/notes", json={"title": "Stuck note", "subject_id": stuck, "blocks": []})
    me.put(f"/subjects/{stuck}/watch", json={"watching": True})
    owner.execute("UPDATE subject SET watch_since = now() - interval '75 days' WHERE id = %s", (stuck,))

    review = me.get("/review").json()
    assert review["period"] == datetime.now(UTC).strftime("%Y-%m")
    by_kind = {}
    for item in review["items"]:
        by_kind.setdefault(item["kind"], []).append(item)
    assert [i["basis"] for i in by_kind["over_limit"]] == [
        "IEX is 51.52% of the portfolio; your limit is 25%.", "PVRINOX is 30.30% of the portfolio; your limit is 25%."]
    assert "Coupling stays limited to DAM" in by_kind["broken_assumption"][0]["basis"]
    assert by_kind["no_thesis"][0]["basis"].startswith("You hold GSMFOILS (18.18%)")
    assert {i["question"] for i in by_kind["no_decision"]} == {
        "Why did you buy IEX? Record the one reason that decided it.",
        "Why did you buy PVRINOX? Record the one reason that decided it."}
    assert "largest position at 51.52%" in by_kind["largest_position"][0]["basis"]
    assert by_kind["watchlist"][0]["basis"].startswith("Stuck Co has been on your watchlist for 75 days with 1 note(s)")
    assert by_kind["open"][0]["question"] == "Which position would you not buy today at its current weight?"
    assert len(review["items"]) <= 10

    # Opened again in the same month, it is the same review even though the record has moved on.
    me.post(f"/subjects/{iex}/decisions", json={"type": "bought", "decided_on": str(date.today()),
                                               "decisive_reason": "Asymmetric payoff after the fall."})
    assert [i["id"] for i in me.get("/review").json()["items"]] == [i["id"] for i in review["items"]]

    item = review["items"][0]
    saved = me.put(f"/review/items/{item['id']}", json={"answer": "Highest conviction; I accept the size."}).json()
    assert saved["answered_at"] is not None
    past = me.get("/review").json()["past"]
    assert past[0]["answered"] == 1 and past[0]["questions"] == len(review["items"])
    assert me.get(f"/review/{review['id']}").json()["items"][0]["answer"] == "Highest conviction; I accept the size."


def test_no_review_without_anything_to_ask_about(me):
    empty = me.get("/review").json()
    assert empty["id"] is None and empty["items"] == []


def test_graph_shows_what_is_connected(me):
    from tests.test_documents import pdf, upload
    company = me.post("/subjects", json={"name": "IEX"}).json()["id"]
    other = me.post("/subjects", json={"name": "Other"}).json()["id"]
    n1 = me.post("/notes", json={"title": "Thesis notes", "subject_id": company, "blocks": [
        {"id": "b1", "content": [{"text": "See [[Coupling]] and [[Elsewhere]]."}]}]}).json()["id"]
    n2 = me.post("/notes", json={"title": "Coupling", "subject_id": company, "blocks": []}).json()["id"]
    me.post("/notes", json={"title": "Elsewhere", "subject_id": other, "blocks": []})
    doc = upload(me, company, pdf("Round one covers the day-ahead market only."), "order.pdf").json()["id"]
    chunk = me.get(f"/documents/{doc}/passages").json()[0]["id"]
    a = me.post(f"/subjects/{company}/assumptions", json={"body": "Coupling stays limited", "basis": "fact"}).json()["id"]
    me.post(f"/assumptions/{a}/evidence", json={"direction": "for", "kind": "fact", "body": "Order says so.", "chunk_id": chunk})
    d = me.post(f"/subjects/{company}/decisions", json={"type": "bought", "decided_on": str(date.today()),
                                                       "decisive_reason": "Limited downside.", "assumption_ids": [a]}).json()["id"]

    g = me.get("/graph", params={"subject_id": company}).json()
    assert {n["kind"] for n in g["nodes"]} == {"company", "note", "document", "assumption", "decision"}
    assert len(g["nodes"]) == 6                                                    # nothing from the other company
    edges = {(e["from"], e["to"], e["kind"]) for e in g["edges"]}
    assert (f"note:{n1}", f"note:{n2}", "links to") in edges
    assert (f"document:{doc}", f"assumption:{a}", "evidence for") in edges
    assert (f"decision:{d}", f"assumption:{a}", "rested on") in edges
    assert (f"note:{n1}", f"company:{company}", "filed under") in edges
    assert not any("Elsewhere" in str(e) for e in g["edges"])

    everything = me.get("/graph").json()
    assert len(everything["nodes"]) == 8                                           # both companies and the third note
    assert any(e["kind"] == "links to" and e["from"] == f"note:{n1}" for e in everything["edges"])
    assert me.get("/graph", params={"subject_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_other_users_see_none_of_it(me, new_user):
    load(me)
    p = me.put("/portfolio/limits", json={"key": "max_position_pct", "value": 10, "enabled": True}).json()
    company = me.post("/subjects", json={"name": "IEX"}).json()["id"]
    me.put(f"/subjects/{company}/watch", json={"watching": True})
    review = me.get("/review").json()

    b = new_user()
    theirs = b.get("/portfolio").json()
    assert theirs["snapshot"] is None and theirs["holdings"] == [] and theirs["alerts"] == [] and theirs["watchlist"] == []
    assert [limit["enabled"] for limit in theirs["limits"]] == [False] * 4
    assert b.post(f"/alerts/{p['alerts'][0]['id']}/acknowledge", json={}).status_code == 404
    assert b.put("/portfolio/link", json={"symbol": "IEX", "subject_id": company}).status_code == 404
    assert b.put(f"/subjects/{company}/watch", json={"watching": False}).status_code == 404
    assert b.get(f"/review/{review['id']}").status_code == 404
    assert b.put(f"/review/items/{review['items'][0]['id']}", json={"answer": "x"}).status_code == 404
    assert b.get("/graph").json() == {"nodes": [], "edges": []}
    assert b.get("/graph", params={"subject_id": company}).status_code == 404
    assert b.get("/review").json()["id"] is None
    assert me.get("/portfolio").json()["snapshot"] is not None


def test_portfolio_can_be_deleted(me, owner):
    load(me)
    me.put("/portfolio/limits", json={"key": "max_position_pct", "value": 10, "enabled": True})
    assert me.delete("/portfolio").status_code == 204
    p = me.get("/portfolio").json()
    assert p["snapshot"] is None and p["alerts"] == []
    for table in ("holding", "holding_snapshot", "alert"):
        assert owner.execute(f"SELECT count(*) FROM {table} WHERE owner_id = %s", (me.user_id,)).fetchone()[0] == 0


def test_breaches_is_pure_arithmetic():
    holdings = [{"symbol": "A", "weight_pct": Decimal("60"), "has_thesis": True},
                {"symbol": "B", "weight_pct": Decimal("40"), "has_thesis": False}]
    assert portfolio.breaches(holdings, {}) == []
    assert [b["symbol"] for b in portfolio.breaches(holdings, {"max_position_pct": Decimal("40")})] == ["A"]   # at the limit is fine
    assert [b["rule_key"] for b in portfolio.breaches(holdings, {"thesis_required": Decimal(0)})] == ["thesis_required"]
    assert portfolio.breaches(holdings, {"max_top3_pct": Decimal(1)}) == []                                     # fewer than three
    old = datetime.now(UTC) - timedelta(days=1)
    assert isinstance(old, datetime)
