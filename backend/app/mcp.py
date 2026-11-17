"""A read-only MCP server over the user's own workspace.

Lets an MCP client (Claude Desktop, Claude Code, others) search the user's documents and
notes and read a company's record, using an extension token that is allowed to ask. It
cannot write, delete, or call a model; it returns what is recorded, with where it came from.

Transport: MCP "Streamable HTTP", JSON responses only (no server-sent events), stateless.
One endpoint, POST /mcp, JSON-RPC 2.0. Spec: https://modelcontextprotocol.io/specification
"""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from . import db
from .assistant import asking_token
from .documents import find_passages
from .export import company_markdown

router = APIRouter()

PROTOCOL = "2025-06-18"
TOOLS = [
    {"name": "list_companies",
     "description": "List the companies in the user's Invest-pad workspace, with their ids.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "search_workspace",
     "description": "Full-text search of the user's uploaded documents and notes. Returns passages with the "
                    "document title, period and page, so answers can cite them.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Words to search for"},
         "company_id": {"type": "string", "description": "Optional: limit to one company (id from list_companies)"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
         "required": ["query"]}},
    {"name": "get_company",
     "description": "One company's record as Markdown: current thesis, assumptions with evidence, decisions with "
                    "the user's reasons, documents, and notes in full.",
     "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string"}}, "required": ["company_id"]}},
]
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def call_tool(owner, name: str, args: dict) -> dict:
    if name == "list_companies":
        with db.as_user(owner) as cur:
            cur.execute("SELECT id, name FROM subject ORDER BY lower(name)")
            rows = cur.fetchall()
        return _text("\n".join(f"{r['name']} — id {r['id']}" for r in rows) or "No companies yet.")

    if name == "search_workspace":
        query = str(args.get("query") or "").strip()
        if not query:
            return _text("query is required", True)
        company = args.get("company_id")
        if company and not _uuid(company):
            return _text("company_id is not a valid id; use list_companies", True)
        limit = args.get("limit") if isinstance(args.get("limit"), int) else 8
        found = find_passages(owner, query, _uuid(company) if company else None, limit=min(max(limit, 1), 20))
        out = []
        for p in found["passages"]:
            where = ", ".join(x for x in (p["title"], p["period"], p["label"]) if x)
            out.append(f"[document: {where}]\n{p['body']}")
        for n in found["notes"]:
            out.append(f"[my note: {n['title']}]\n{n['snippet'].replace('<<', '').replace('>>', '')}")
        return _text("\n\n---\n\n".join(out) or "Nothing in the workspace matches.")

    if name == "get_company":
        ident = _uuid(args.get("company_id"))
        if not ident:
            return _text("company_id is not a valid id; use list_companies", True)
        try:
            return _text(company_markdown(ident, {"id": owner}).body.decode())
        except Exception:  # noqa: BLE001 - not found is the only expected failure
            return _text("No such company.", True)

    return _text(f"Unknown tool: {name}", True)


def _reply(ident, result=None, error=None) -> dict:
    body = {"jsonrpc": "2.0", "id": ident}
    body["error" if error else "result"] = error or result
    return body


@router.post("/mcp")
async def mcp(request: Request, owner: str = Depends(asking_token)):
    try:
        msg = await request.json()
    except ValueError:
        return JSONResponse(_reply(None, error={"code": -32700, "message": "Parse error"}), status_code=400)
    if isinstance(msg, list) or not isinstance(msg, dict):
        return JSONResponse(_reply(None, error={"code": -32600, "message": "Send one request at a time"}),
                            status_code=400)
    method, ident, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if ident is None:                     # a notification, e.g. notifications/initialized
        return Response(status_code=202)
    if method == "initialize":
        return _reply(ident, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                              "serverInfo": {"name": "invest-pad", "version": "0.1"},
                              "instructions": "Read-only access to the user's own research. Cite document, period "
                                              "and page from search results. Do not give buy, sell or sizing advice."})
    if method == "ping":
        return _reply(ident, {})
    if method == "tools/list":
        return _reply(ident, {"tools": [{**t, "annotations": READ_ONLY} for t in TOOLS]})
    if method == "tools/call":
        args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        return _reply(ident, call_tool(owner, str(params.get("name")), args))
    return _reply(ident, error={"code": -32601, "message": f"Method not found: {method}"})
