"""Investor isolation over REAL HTTP -- the bug this closes: two logins could read one
database because /investors/{id} scopes authorised nothing. Every claim below needs
FastAPI's routing, dependency injection and auth dependency to actually run, which
calling handler functions directly skips (see tests/test_db_webhook.py's docstring for
why that shortcut proves nothing about status codes).

Covers:
  - register provisions a personal investor owned by the caller, echoed as
    TokenResponse.investor_id;
  - another login reading that investor gets 403; no token gets 401; an unknown id 404;
  - POST /ingest/csv stages per file: a re-uploaded duplicate answers 202 naming its
    existing batch while the other files in the same request still stage;
  - GET /ingest/batches lists only the owner's staged batches, and batch ids are
    discoverable from it (the "where even is my batch id" complaint);
  - /ingest/stage/{batch_id} authorises against the owning investor.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.db

BASE_SETTINGS = {
    "database_url": "postgresql://unused/for-this-suite",
    "portfolio_encryption_key": "unused-in-this-suite",
    "portfolio_pan_pepper": "unused-in-this-suite",
    "jwt_secret": "test-jwt-secret-not-for-production",
    "debug": True,
}

CSV_ROW = (
    "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,"
    "trade_id,order_id,order_execution_time\n"
    "BLS,INE153T01027,2024-01-10,NSE,EQ,EQ,buy,false,100.000000,{price:.6f},"
    "{trade_id},{order_id},2024-01-10T10:15:00\n"
)


def tradebook_csv(trade_id: str, order_id: str, price: float = 200.5) -> bytes:
    return CSV_ROW.format(trade_id=trade_id, order_id=order_id, price=price).encode()


@pytest.fixture()
def app_module(monkeypatch: pytest.MonkeyPatch):
    for key, value in BASE_SETTINGS.items():
        monkeypatch.setenv(key.upper(), value)
    from app.config import get_settings

    get_settings.cache_clear()
    import app.main as main_module

    yield main_module
    get_settings.cache_clear()


@pytest.fixture()
def client(app_module, db, tmp_path, monkeypatch: pytest.MonkeyPatch):
    """TestClient bound to the ``db`` fixture's connection and a local storage root."""
    from app.config import Settings
    from app.config import get_settings as get_settings_dep
    from app.database import get_conn as get_conn_dep
    from app.storage.local import SIGNING_SECRET_ENV
    from fastapi.testclient import TestClient

    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")
    settings = BASE_SETTINGS | {
        "storage_backend": "local",
        "local_storage_root": str(tmp_path / "objects"),
    }
    app_module.app.dependency_overrides[get_conn_dep] = lambda: db

    def _settings():
        return Settings(_env_file=None, **settings)

    app_module.app.dependency_overrides[get_settings_dep] = _settings
    with TestClient(app_module.app) as c:
        yield c
    app_module.app.dependency_overrides.clear()


@pytest.fixture()
def consent_for(db):
    def _grant(investor_id: str) -> None:
        from app.db.consent import record_consent

        record_consent(db, investor_id, notice_version="v1", evidence_ref="ownership-tests")

    return _grant


@pytest.fixture()
def account_for(db):
    def _make(investor_id: str) -> str:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO account (investor_id, broker, is_advised) "
                "VALUES (%s, 'ZERODHA', true) RETURNING id",
                (investor_id,),
            )
            return str(cur.fetchone()[0])

    return _make


def _register(client, email: str) -> dict:
    res = client.post("/auth/register", json={"email": email, "password": "password-1"})
    assert res.status_code == 201, res.text
    return res.json()


# --- registration provisions an owned investor ---------------------------------------


def test_register_provisions_a_personal_investor_and_echoes_it(client, db) -> None:
    body = _register(client, "owner-a@example.com")

    assert body["investor_id"], "register must hand back the investor it created"
    with db.cursor() as cur:
        cur.execute("SELECT owner_user_id FROM investor WHERE id = %s", (body["investor_id"],))
        row = cur.fetchone()
    assert row is not None, "the provisioned investor must exist"
    assert str(row[0]) == body["user"]["id"], "and must be owned by the new login"


def test_login_echoes_the_caller_s_investor_id(client) -> None:
    _register(client, "owner-login@example.com")
    body = client.post(
        "/auth/login", json={"email": "owner-login@example.com", "password": "password-1"}
    ).json()
    assert body["investor_id"]


# --- the isolation wall ---------------------------------------------------------------


def test_a_second_login_cannot_read_the_first_s_portfolio(client) -> None:
    mine = _register(client, "iso-a@example.com")["investor_id"]
    theirs = _register(client, "iso-b@example.com")["investor_id"]
    token_b = client.post(
        "/auth/login", json={"email": "iso-b@example.com", "password": "password-1"}
    ).json()["token"]

    auth = {"Authorization": f"Bearer {token_b}"}
    res = client.get(f"/investors/{mine}/transactions", headers=auth)
    assert res.status_code == 403
    # ...and B still reads their own fine.
    ok = client.get(f"/investors/{theirs}/transactions", headers=auth)
    assert ok.status_code == 200


def test_no_token_at_all_is_unauthorized_on_data_reads(client) -> None:
    investor_id = _register(client, "iso-c@example.com")["investor_id"]
    for path in (
        f"/investors/{investor_id}/transactions",
        f"/investors/{investor_id}/holdings",
        f"/investors/{investor_id}/summary",
        f"/investors/{investor_id}/lots",
        f"/investors/{investor_id}/realised",
        f"/investors/{investor_id}/dividends",
        f"/ingest/batches?investor_id={investor_id}",
    ):
        res = client.get(path)
        assert res.status_code == 401, path


def test_an_unknown_investor_reads_as_not_found(client) -> None:
    _register(client, "iso-c2@example.com")
    token = client.post(
        "/auth/login", json={"email": "iso-c2@example.com", "password": "password-1"}
    ).json()["token"]
    res = client.get(
        f"/investors/{uuid.uuid4()}/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_privacy_export_is_owner_gated_too(client) -> None:
    mine = _register(client, "iso-d@example.com")["investor_id"]
    _register(client, "iso-e@example.com")
    token_e = client.post(
        "/auth/login", json={"email": "iso-e@example.com", "password": "password-1"}
    ).json()["token"]

    res = client.get(
        f"/privacy/export?investor_id={mine}",
        headers={"Authorization": f"Bearer {token_e}"},
    )
    assert res.status_code == 403


# --- multi-file staging survives a duplicate -----------------------------------------


def _upload(client, token: str, investor_id: str, account_id: str, files: list[tuple[str, bytes]]):
    return client.post(
        "/ingest/csv",
        data={"investor_id": investor_id, "account_id": account_id, "adapter": "zerodha_tradebook"},
        files=[("files", (name, content, "text/csv")) for name, content in files],
        headers={"Authorization": f"Bearer {token}"},
    )


def test_multi_file_upload_survives_a_previously_staged_file(
    client, consent_for, account_for
) -> None:
    investor_id = _register(client, "upload-a@example.com")["investor_id"]
    consent_for(investor_id)
    account_id = account_for(investor_id)
    token = client.post(
        "/auth/login", json={"email": "upload-a@example.com", "password": "password-1"}
    ).json()["token"]

    first = tradebook_csv("9001", "8001")
    second = tradebook_csv("9002", "8002", price=210.0)

    res1 = _upload(client, token, investor_id, account_id, [("day1.csv", first)])
    assert res1.status_code == 202, res1.text

    # day1 again (duplicate) plus a genuinely new file: BOTH answers must come back,
    # not a wholesale failure that rolls back the new staging too.
    res2 = _upload(
        client, token, investor_id, account_id, [("day1.csv", first), ("day2.csv", second)]
    )
    assert res2.status_code == 202, res2.text
    results = res2.json()
    assert len(results) == 2
    dupes = [r for r in results if any("already staged" in n for n in r["notes"])]
    fresh = [r for r in results if r not in dupes]
    assert len(dupes) == 1, results
    assert dupes[0]["batch_id"] == res1.json()[0]["batch_id"], "duplicate names its batch"
    assert len(fresh) == 1 and fresh[0]["parsed"] == 1

    listed = client.get(
        f"/ingest/batches?investor_id={investor_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    ids = {row["batch_id"] for row in listed.json()}
    assert {r["batch_id"] for r in results} <= ids


def test_batches_and_stage_are_scoped_to_the_owner(client, consent_for, account_for) -> None:
    owner = _register(client, "batch-owner@example.com")
    intruder = _register(client, "batch-other@example.com")
    token_owner = client.post(
        "/auth/login", json={"email": "batch-owner@example.com", "password": "password-1"}
    ).json()["token"]
    token_other = client.post(
        "/auth/login", json={"email": "batch-other@example.com", "password": "password-1"}
    ).json()["token"]

    consent_for(owner["investor_id"])
    account_id = account_for(owner["investor_id"])
    files = [("t.csv", tradebook_csv("9100", "8100"))]
    staged = _upload(client, token_owner, owner["investor_id"], account_id, files).json()[0][
        "batch_id"
    ]

    res = client.get(f"/ingest/stage/{staged}", headers={"Authorization": f"Bearer {token_other}"})
    assert res.status_code == 403

    res = client.post(
        f"/ingest/stage/{staged}/promote", headers={"Authorization": f"Bearer {token_other}"}
    )
    assert res.status_code == 403

    # The owner sees their batch; the intruder's own list is empty.
    own = client.get(
        f"/ingest/batches?investor_id={owner['investor_id']}",
        headers={"Authorization": f"Bearer {token_owner}"},
    ).json()
    assert [b["batch_id"] for b in own] == [staged]
    empty = client.get(
        f"/ingest/batches?investor_id={intruder['investor_id']}",
        headers={"Authorization": f"Bearer {token_other}"},
    ).json()
    assert empty == []


# --- rate limiting ---------------------------------------------------------------
# Disabled everywhere else in this suite by tests/conftest.py's autouse fixture --
# every other test above registers/logs in repeatedly from the same fake client
# address, which the limiter would otherwise throttle. Re-enabled just here, for just
# long enough to prove app.rate_limit.limiter is actually wired into /auth/register.


def test_register_is_rate_limited_per_ip(client) -> None:
    from app.rate_limit import limiter

    limiter.enabled = True
    try:
        for i in range(5):
            res = client.post(
                "/auth/register",
                json={"email": f"rate-limit-{i}@example.com", "password": "password-1"},
            )
            assert res.status_code == 201, res.text
        blocked = client.post(
            "/auth/register",
            json={"email": "rate-limit-6@example.com", "password": "password-1"},
        )
        assert blocked.status_code == 429
    finally:
        limiter.enabled = False
