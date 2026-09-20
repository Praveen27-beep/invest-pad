"""The actual plumbing behind /ops/security-alias/* and /ops/demerger-watch/* --
test_ops_auth.py proves the credential gates reject; this proves what happens once they
let a request through, against a real database.

Closes the exact gap test_ops_auth.py's own dividend-refresh test names: a fully-tested
db-layer function with no HTTP endpoint means nothing in a real deployment ever calls
it. These prove the endpoint actually calls through, not just that it exists.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from app.db import repository
from app.db import security_alias as alias_db
from app.db.security_alias import SecurityAlias
from app.engine.corporate_actions import Verification
from app.engine.types import Source, Transaction, TxnType

pytestmark = pytest.mark.db

OLD, NEW = "INE411D01015", "INE411D01023"
BASE_SETTINGS = {
    "database_url": "postgresql://unused/for-this-suite",
    "portfolio_encryption_key": "unused-in-this-suite",
    "portfolio_pan_pepper": "unused-in-this-suite",
    "jwt_secret": "test-jwt-secret-not-for-production",
    "debug": True,
}


def _client(monkeypatch: pytest.MonkeyPatch, db, **overrides: str):
    for key, value in BASE_SETTINGS.items():
        monkeypatch.setenv(key.upper(), value)
    import app.main as main_module
    from app.config import Settings, get_settings
    from app.database import get_conn as get_conn_dep
    from fastapi.testclient import TestClient

    def _get_conn():
        yield db

    settings = BASE_SETTINGS | overrides
    get_settings.cache_clear()
    main_module.app.dependency_overrides[get_conn_dep] = _get_conn
    main_module.app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, **settings
    )
    client = TestClient(main_module.app)
    return client


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    import app.main as main_module
    from app.config import get_settings

    main_module.app.dependency_overrides.clear()
    get_settings.cache_clear()


def _txn(isin, t, q, p, d, acc):
    return Transaction(
        isin=isin, txn_date=date.fromisoformat(d), txn_type=TxnType(t),
        quantity=Decimal(q), price=Decimal(p), account_id=acc, source=Source.CONTRACT_NOTE,
    )


def test_security_alias_refresh_runs_the_feed_then_promotion_in_sequence(
    monkeypatch: pytest.MonkeyPatch, db, investor
) -> None:
    """The real behavioural claim: one POST does BOTH jobs, feed then promotion, in one
    response -- not two independent things a caller has to remember to trigger."""
    account_id = os.environ["_TEST_ACCOUNT_ID"]
    with db.cursor() as cur:
        for isin in (OLD, NEW):
            cur.execute("INSERT INTO security (isin) VALUES (%s) ON CONFLICT DO NOTHING", (isin,))
    repository.save_transactions(
        db,
        [
            _txn(OLD, "BUY", "1", "194.06", "2025-04-25", account_id),
            _txn(NEW, "BUY", "10", "232.35", "2026-06-02", account_id),
        ],
    )
    # A DRAFT alias already on file, as if a previous poll created it -- this call must
    # promote it, proving promotion really runs, not just the feed half.
    alias_db.add_alias(db, SecurityAlias(
        old_isin=OLD, current_isin=NEW, effective_date=date(2026, 1, 9),
        source="NSDL ISIN change notice", source_url="https://example.invalid/isin-change",
        verification=Verification.DRAFT,
    ))
    db.commit()

    # The feed itself hits a real NSE endpoint; stub it to a harmless empty result so
    # this test is offline and only proves the SEQUENCING, which is what's under test.
    with patch(
        "app.routers.security_alias.icc_db.refresh_isin_change_feed",
        return_value={"fetched": 0, "aliases_created": 0, "skipped": 0,
                      "breaker_open": False, "error": None},
    ) as fake_feed:
        client = _client(monkeypatch, db, ops_api_key="a-real-ops-key")
        res = client.post("/ops/security-alias/refresh", headers={"X-Ops-Key": "a-real-ops-key"})

    assert res.status_code == 200
    body = res.json()
    assert body["feed"] == {"fetched": 0, "aliases_created": 0, "skipped": 0,
                             "breaker_open": False, "error": None}
    assert body["promotion"]["verified"] == 1  # the pre-existing DRAFT alias, promoted
    fake_feed.assert_called_once()

    assert OLD in alias_db.verified_map(db)


def test_demerger_watch_check_reports_skipped_when_flag_is_off(
    monkeypatch: pytest.MonkeyPatch, db
) -> None:
    with patch("app.routers.demerger_watch.check_demerger_watch") as fake_check:
        client = _client(
            monkeypatch, db, ops_api_key="a-real-ops-key", demerger_watch_enabled="false"
        )
        res = client.post("/ops/demerger-watch/check", headers={"X-Ops-Key": "a-real-ops-key"})

    assert res.status_code == 200
    assert res.json() == {"skipped": True, "logged": 0}
    fake_check.assert_not_called()


def test_demerger_watch_check_runs_when_flag_is_on(monkeypatch: pytest.MonkeyPatch, db) -> None:
    with patch("app.routers.demerger_watch.check_demerger_watch", return_value=3) as fake_check:
        client = _client(
            monkeypatch, db, ops_api_key="a-real-ops-key", demerger_watch_enabled="true"
        )
        res = client.post("/ops/demerger-watch/check", headers={"X-Ops-Key": "a-real-ops-key"})

    assert res.status_code == 200
    assert res.json() == {"skipped": False, "logged": 3}
    fake_check.assert_called_once()
