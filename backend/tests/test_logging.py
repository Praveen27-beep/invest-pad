import logging
import secrets

from fastapi.testclient import TestClient


def test_logs_carry_no_secrets(app, owner, caplog):
    """Plant recognisable secrets in every input, then search everything that was logged."""
    password = "PLANTED-PASSWORD-" + secrets.token_hex(6)
    invite = "PLANTED-INVITE-" + secrets.token_hex(6)
    owner.execute("INSERT INTO invite (code) VALUES (%s)", (invite,))
    email = f"log-{secrets.token_hex(4)}@example.com"

    with caplog.at_level(logging.DEBUG):
        client = TestClient(app)
        client.post("/auth/signup", json={"email": email, "password": password, "invite": invite})
        client.post("/auth/login", json={"email": email, "password": password})
        client.post("/auth/login", json={"email": email, "password": password + "-wrong"})
        client.get("/subjects?q=PLANTED-QUERY")
        client.post("/subjects", json={"name": "PLANTED-COMPANY"})
        token = client.cookies["investpad_session"]

    # Everything the server logged. The test client's own logger (httpx) is excluded:
    # it is not part of the running service.
    text = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    assert "POST /auth/signup status=201" in text          # the log line exists
    assert f"user={client.get('/auth/me').json()['id']}" in text
    for secret in (password, invite, token, "PLANTED-QUERY", "PLANTED-COMPANY", email):
        assert secret not in text


def test_health(app):
    assert TestClient(app).get("/health").json() == {"ok": True}
