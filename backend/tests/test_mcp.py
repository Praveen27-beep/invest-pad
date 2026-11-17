"""Read-only MCP server: token-scoped, the user's own workspace only, no writes."""

import pytest
from fastapi.testclient import TestClient

from tests.test_documents import pdf, upload


@pytest.fixture
def setup(app, new_user):
    co = new_user()
    sid = co.post("/subjects", json={"name": "Northgate"}).json()["id"]
    upload(co, sid, pdf("Revenue from operations was 608 crore in FY25."), "AR FY25.pdf")
    co.put(f"/subjects/{sid}/thesis", json={"body": "Northgate keeps share."})
    token = co.post("/tokens", json={"label": "mcp", "can_ask": True}).json()["token"]
    capture_only = co.post("/tokens", json={"label": "capture"}).json()["token"]
    return TestClient(app), sid, token, capture_only


def rpc(client, token, method, params=None, ident=1):
    body = {"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})}
    if ident is not None:
        body["id"] = ident
    return client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})


def text(r):
    return r.json()["result"]["content"][0]["text"]


def test_handshake_and_tools(setup):
    client, sid, token, _ = setup
    init = rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                              "clientInfo": {"name": "t", "version": "1"}}).json()["result"]
    assert init["serverInfo"]["name"] == "invest-pad" and "tools" in init["capabilities"]
    assert rpc(client, token, "notifications/initialized", ident=None).status_code == 202
    tools = rpc(client, token, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"list_companies", "search_workspace", "get_company"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)

    assert f"Northgate — id {sid}" in text(rpc(client, token, "tools/call", {"name": "list_companies", "arguments": {}}))
    found = text(rpc(client, token, "tools/call", {"name": "search_workspace", "arguments": {"query": "revenue operations"}}))
    assert "608 crore" in found and "AR FY25" in found
    md = text(rpc(client, token, "tools/call", {"name": "get_company", "arguments": {"company_id": sid}}))
    assert md.startswith("# Northgate") and "Northgate keeps share." in md


def test_errors_and_access(setup, new_user, app):
    client, sid, token, capture_only = setup
    assert rpc(client, "ipx_nope", "tools/list").status_code == 401
    assert rpc(client, capture_only, "tools/list").status_code == 403
    assert rpc(client, token, "resources/list").json()["error"]["code"] == -32601
    bad = rpc(client, token, "tools/call", {"name": "get_company", "arguments": {"company_id": "x"}}).json()["result"]
    assert bad["isError"]
    assert rpc(client, token, "tools/call", {"name": "delete_everything", "arguments": {}}).json()["result"]["isError"]
    # Another user's token sees nothing of this workspace.
    other = new_user()
    theirs = other.post("/tokens", json={"label": "mcp", "can_ask": True}).json()["token"]
    assert "Nothing" in text(rpc(client, theirs, "tools/call", {"name": "search_workspace", "arguments": {"query": "revenue"}}))
    assert text(rpc(client, theirs, "tools/call", {"name": "get_company", "arguments": {"company_id": sid}})) == "No such company."
    # A session cookie is not enough: the token is required.
    assert other.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
