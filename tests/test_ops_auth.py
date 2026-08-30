"""app.auth.ops.require_ops_key / require_cron_secret -- the gates on POST
/ops/prices/refresh, POST /ops/snapshots/run, and their GET /ops/cron/* counterparts.
Only the gates themselves: a missing/wrong/absent credential must reject the request
before app.prices.pipe.fetch_day or _run_snapshots ever runs, so none of this needs a
real database or network access. See tests/test_db_ownership.py's docstring for why an
HTTP TestClient is used rather than calling the handler directly -- the thing under test
is a route-level ``dependencies=[Depends(...)]`` guard, which calling the function would
skip.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

BASE_SETTINGS = {
    "database_url": "postgresql://unused/for-this-suite",
    "portfolio_encryption_key": "unused-in-this-suite",
    "portfolio_pan_pepper": "unused-in-this-suite",
    "jwt_secret": "test-jwt-secret-not-for-production",
    "debug": True,
}


@contextmanager
def client_with_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str):
    """A TestClient with get_conn stubbed out entirely: an auth gate must reject
    before the route body ever touches a connection."""
    for key, value in BASE_SETTINGS.items():
        monkeypatch.setenv(key.upper(), value)
    from app.config import Settings, get_settings

    get_settings.cache_clear()
    import app.main as main_module
    from app.database import get_conn as get_conn_dep
    from fastapi.testclient import TestClient

    settings = BASE_SETTINGS | overrides

    def _settings():
        return Settings(_env_file=None, **settings)

    main_module.app.dependency_overrides[get_conn_dep] = lambda: iter([None])
    main_module.app.dependency_overrides[get_settings] = _settings
    try:
        with TestClient(main_module.app) as c:
            yield c
    finally:
        main_module.app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_missing_header_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with client_with_settings(monkeypatch, ops_api_key="a-real-ops-key") as client:
        res = client.post("/ops/prices/refresh")
        assert res.status_code == 401


def test_wrong_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with client_with_settings(monkeypatch, ops_api_key="a-real-ops-key") as client:
        res = client.post("/ops/snapshots/run", headers={"X-Ops-Key": "not-the-real-key"})
        assert res.status_code == 403


def test_unconfigured_key_refuses_even_a_request_with_no_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with client_with_settings(monkeypatch) as client:
        res = client.post("/ops/prices/refresh")
        assert res.status_code == 500


# --- GET /ops/cron/* -- Vercel Cron's own convention: GET + Authorization: Bearer ----


def test_cron_missing_authorization_header_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with client_with_settings(monkeypatch, cron_secret="a-real-cron-secret") as client:
        res = client.get("/ops/cron/prices-refresh")
        assert res.status_code == 401


def test_cron_wrong_bearer_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with client_with_settings(monkeypatch, cron_secret="a-real-cron-secret") as client:
        res = client.get(
            "/ops/cron/snapshots-run", headers={"Authorization": "Bearer not-the-real-secret"}
        )
        assert res.status_code == 403


def test_cron_unconfigured_secret_refuses_even_a_request_with_no_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with client_with_settings(monkeypatch) as client:
        res = client.get("/ops/cron/prices-refresh")
        assert res.status_code == 500


def test_an_ops_key_does_not_satisfy_the_cron_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two credentials are deliberately not interchangeable -- X-Ops-Key on a
    /ops/cron/* route should still be refused, since that route only ever checks
    Authorization."""
    with client_with_settings(monkeypatch, cron_secret="a-real-cron-secret") as client:
        res = client.get("/ops/cron/prices-refresh", headers={"X-Ops-Key": "a-real-cron-secret"})
        assert res.status_code == 401
