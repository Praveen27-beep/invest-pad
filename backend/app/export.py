"""Full export: everything a user has put into Invest-pad, as one ZIP they can keep.

Layout of the ZIP:

    README.txt                     what is where
    data/<table>.json              every row of every table the user owns (all history included)
    companies/<name>/thesis.md     the current thesis, assumptions and decisions, readable
    companies/<name>/notes/*.md    each note's current text (all versions are in data/note_version.json)
    companies/<name>/documents/*   the original uploaded files
    notes/*.md                     notes not filed under a company

Which tables are exported is not a hand-kept list: it is every table in the schema with an
`owner_id` column, so a table added later is exported without anyone remembering to. Row
security limits each query to the signed-in user's rows. Left out on purpose: encrypted
model keys (`key_ciphertext`) and search indexes (tsvector columns), which are derived.
"""

import json
import re
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from psycopg import sql

from . import auth, db

router = APIRouter()

SECRET_COLUMNS = {"key_ciphertext"}

README = """Invest-pad export, made {when} UTC.

data/<table>.json   Every row you own, in every table, including all past versions,
                    decisions, answers with their citations, holdings imports and reviews.
                    Dates are ISO 8601; amounts are strings so nothing is rounded.
companies/          One folder per company: thesis.md (readable summary), notes/ (current
                    text of each note), documents/ (the files you uploaded).
notes/              Notes not filed under a company.

Not included: your password, session and extension tokens, and stored model API keys.
"""


def owned_tables(cur) -> list[tuple[str, list[str]]]:
    """Every table with an owner_id column, with the columns safe to export."""
    cur.execute("""
        SELECT c.table_name, array_agg(c.column_name::text ORDER BY c.ordinal_position) AS cols
          FROM information_schema.columns c
          JOIN information_schema.tables t USING (table_schema, table_name)
         WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
           AND c.data_type <> 'tsvector'
           AND c.table_name IN (SELECT table_name FROM information_schema.columns
                                 WHERE table_schema = 'public' AND column_name = 'owner_id')
         GROUP BY c.table_name ORDER BY c.table_name""")
    return [(r["table_name"], [c for c in r["cols"] if c not in SECRET_COLUMNS]) for r in cur.fetchall()]


def _rows(cur, table: str, cols: list[str]) -> list[dict]:
    order = "id" if "id" in cols else cols[0]
    cur.execute(sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        sql.SQL(", ").join(map(sql.Identifier, cols)), sql.Identifier(table), sql.Identifier(order)))
    return cur.fetchall()


def _safe(name: str, ident, taken: set) -> str:
    """A file name that is safe on every OS and unique within its folder."""
    base = re.sub(r"[^\w .()&+-]", "_", name).strip(" .")[:80] or "untitled"
    out = base if base.lower() not in taken else f"{base} ({str(ident)[:8]})"
    taken.add(out.lower())
    return out


def _thesis_md(name: str, data: dict, subject_id) -> str:
    def latest(rows, key, ident):
        mine = [r for r in rows if r[key] == ident]
        return max(mine, key=lambda r: r["seq"]) if mine else None

    lines = [f"# {name}", ""]
    position = next((p for p in data["position"] if p["subject_id"] == subject_id), None)
    if position:
        current = latest(data["position_version"], "position_id", position["id"])
        lines += ["## Thesis", "", f"_Version {current['seq']}, {current['created_at']:%Y-%m-%d}_", "", current["body"], ""]
        assumptions = [a for a in data["assumption"] if a["position_id"] == position["id"]]
        if assumptions:
            lines += ["## Assumptions", ""]
            for a in assumptions:
                v = latest(data["assumption_version"], "assumption_id", a["id"])
                lines.append(f"- **{v['state']}** ({v['basis']}): {v['body']}" + (f" — {v['reason']}" if v["reason"] else ""))
                for e in (e for e in data["evidence"] if e["assumption_id"] == a["id"] and not e["retracted_at"]):
                    gone = " [source deleted]" if e["source_deleted"] else ""
                    lines.append(f"    - evidence {e['direction']} ({e['kind']}): {e['body']}{gone}")
            lines.append("")
    decisions = sorted((d for d in data["decision"] if d["subject_id"] == subject_id), key=lambda d: d["decided_on"])
    if decisions:
        lines += ["## Decisions", ""]
        for d in decisions:
            lines.append(f"- {d['decided_on']} **{d['type']}**: {d['decisive_reason']}")
            if d["would_change_mind"]:
                lines.append(f"    - would change my mind: {d['would_change_mind']}")
        lines.append("")
    if len(lines) == 2:
        lines.append("No thesis or decisions recorded.")
    return "\n".join(lines) + "\n"


def build(owner_id, files_dir: str, out) -> None:
    """Write the user's whole workspace as a ZIP into the file object `out`."""
    with db.as_user(owner_id) as cur:
        data = {table: _rows(cur, table, cols) for table, cols in owned_tables(cur)}

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README.format(when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M")))
        for table, rows in data.items():
            z.writestr(f"data/{table}.json", json.dumps(rows, default=str, ensure_ascii=False, indent=1))

        folders: dict = {}
        taken: set = set()
        for s in data["subject"]:
            folders[s["id"]] = "companies/" + _safe(s["name"], s["id"], taken)
            z.writestr(f"{folders[s['id']]}/thesis.md", _thesis_md(s["name"], data, s["id"]))

        note_names: dict = {}
        for n in data["note"]:
            folder = (folders.get(n["subject_id"]) + "/notes") if n["subject_id"] in folders else "notes"
            name = _safe(n["title"], n["id"], note_names.setdefault(folder, set()))
            z.writestr(f"{folder}/{name}.md", f"# {n['title']}\n\n{n['body']}\n")

        doc_names: dict = {}
        root = Path(files_dir) / str(uuid.UUID(str(owner_id)))
        for d in data["document"]:
            path = root / str(uuid.UUID(str(d["id"])))
            if not path.is_file():
                continue
            folder = folders[d["subject_id"]] + "/documents"
            stem, dot, ext = d["filename"].rpartition(".")
            name = _safe(stem or d["filename"], d["id"], doc_names.setdefault(folder, set()))
            z.write(path, f"{folder}/{name}{dot}{ext if stem else ''}")


@router.get("/export")
def export(request: Request, user: dict = Depends(auth.current_user)):
    with db.as_user(user["id"]) as cur:
        cur.execute("INSERT INTO audit_log (action, object) VALUES ('export', '')")
    out = tempfile.SpooledTemporaryFile(max_size=50_000_000)
    build(user["id"], request.app.state.config.files_dir, out)
    out.seek(0)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return StreamingResponse(iter(lambda: out.read(1 << 20), b""), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="invest-pad-export-{stamp}.zip"'})
