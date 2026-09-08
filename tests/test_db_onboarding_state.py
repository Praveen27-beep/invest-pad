"""GET /investors/{id}/onboarding and GET /brokers, over REAL HTTP.

Both endpoints exist to remove a lie the frontend used to tell itself.

``/onboarding`` replaces a localStorage key. "They finished setup" lived in one browser,
so the same account on a phone was offered the wizard again -- and offered to create a
second broker account with it. The fix is not a ``setup_complete`` column: onboarding
progress is already derivable from rows the database holds for other reasons, so it is
derived on read like everything else in this codebase (CLAUDE.md's one architectural
rule). These tests pin that derivation, and pin that "complete" deliberately excludes
email forwarding -- declining an optional feature is a finished setup, not a failed one.

``/brokers`` replaces three hardcoded copies of ``"ZERODHA"``. Its contract is that no
capability may be claimed that the codebase does not have; tests/test_brokers.py pins the
derivation itself, and these pin what reaches the wire.

See docs/ONBOARDING_AS_IS_VS_TO_BE.md sections 4, 5 and 6 (loopholes L4, L7, L13).
"""

from __future__ import annotations

import pytest
from app.terms import CURRENT_TOS_VERSION

pytestmark = pytest.mark.db

BASE_SETTINGS = {
    "database_url": "postgresql://unused/for-this-suite",
    "portfolio_encryption_key": "unused-in-this-suite",
    "portfolio_pan_pepper": "unused-in-this-suite",
    "jwt_secret": "test-jwt-secret-not-for-production",
    "debug": True,
}


@pytest.fixture()
def app_module(monkeypatch: pytest.MonkeyPatch):
    for key, value in BASE_SETTINGS.items():
        monkeypatch.setenv(key.upper(), value)
    from app.config import get_settings

    get_settings.cache_clear()
    import app.main as main_module

    yield main_module
    get_settings.cache_clear()


def _client(app_module, db, settings_overrides: dict | None = None):
    from app.config import Settings
    from app.config import get_settings as get_settings_dep
    from app.database import get_conn as get_conn_dep
    from fastapi.testclient import TestClient

    settings = BASE_SETTINGS | (settings_overrides or {})
    app_module.app.dependency_overrides[get_conn_dep] = lambda: db
    app_module.app.dependency_overrides[get_settings_dep] = lambda: Settings(
        _env_file=None, **settings
    )
    return TestClient(app_module.app)


@pytest.fixture()
def client(app_module, db):
    with _client(app_module, db) as c:
        yield c
    app_module.app.dependency_overrides.clear()


def _register(client, email: str) -> dict:
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "password-1", "tos_version": CURRENT_TOS_VERSION},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _auth(body: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {body['token']}"}


def _state(client, body: dict) -> dict:
    res = client.get(f"/investors/{body['investor_id']}/onboarding", headers=_auth(body))
    assert res.status_code == 200, res.text
    return res.json()


# --- the derivation ------------------------------------------------------------------


def test_a_brand_new_signup_has_terms_and_nothing_else(client) -> None:
    """The terms tick is the ONE mandatory step, and it is done by the time an account
    exists at all. Everything after it is a choice the product respects."""
    state = _state(client, _register(client, "fresh@example.com"))

    assert state["terms_accepted"] is True
    assert state["consent"] is False
    assert state["accounts"] == 0
    assert state["transactions"] == 0
    assert state["complete"] is False
    assert state["next_step"] == "permission"


def test_next_step_walks_forward_as_each_fact_becomes_true(client, db) -> None:
    """Resuming is a checklist, not a rerun: the wizard opens on the first unfinished
    step so nobody re-walks screens they already got through."""
    body = _register(client, "walker@example.com")
    investor_id = body["investor_id"]

    from app.db.consent import record_consent

    record_consent(db, investor_id, notice_version="v1", evidence_ref="onboarding-tests")
    assert _state(client, body)["next_step"] == "brokers"

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'ZERODHA', true) RETURNING id",
            (investor_id,),
        )
        account_id = str(cur.fetchone()[0])

    state = _state(client, body)
    assert state["accounts"] == 1
    assert state["next_step"] == "history"
    assert state["complete"] is False, "an account with no trades is not a set-up account"

    _insert_transaction(db, investor_id, account_id)

    state = _state(client, body)
    assert state["transactions"] == 1
    assert state["complete"] is True
    assert state["next_step"] is None


def test_completion_never_depends_on_email_forwarding(client, db) -> None:
    """docs/ONBOARDING_AS_IS_VS_TO_BE.md section 6. Plenty of people will upload a file
    once a quarter and never touch forwarding. Counting it would make declining an
    optional feature read as failing setup -- and on this deployment there is no
    forwarding to decline, which must not hold anyone back."""
    body = _register(client, "no-forwarding@example.com")
    investor_id = body["investor_id"]
    _complete_setup(db, investor_id)

    state = _state(client, body)
    assert state["forwarding_available"] is False, "the dev placeholder domain offers none"
    assert state["complete"] is True


def test_forwarding_availability_follows_the_deployment_domain(app_module, db) -> None:
    """One backend condition, not a frontend flag: the day a real INGEST_DOMAIN is
    configured the forwarding step reappears on its own."""
    with _client(app_module, db, {"ingest_domain": "ingest.mei.capital"}) as client:
        body = _register(client, "real-domain@example.com")
        assert _state(client, body)["forwarding_available"] is True
    app_module.app.dependency_overrides.clear()


# --- the same answer on every device, which is the entire point ----------------------


def test_the_state_is_read_from_the_database_not_from_a_caller_hint(client, db) -> None:
    """A second, entirely fresh client -- a phone, a cleared browser -- gets the same
    answer, because nothing about it was ever stored client-side (loophole L4)."""
    body = _register(client, "two-devices@example.com")
    _complete_setup(db, body["investor_id"])

    first = _state(client, body)
    second = _state(client, body)
    assert first == second
    assert first["complete"] is True


def test_onboarding_state_is_owner_gated(client) -> None:
    mine = _register(client, "owner-state@example.com")
    theirs = _register(client, "other-state@example.com")

    res = client.get(f"/investors/{mine['investor_id']}/onboarding", headers=_auth(theirs))
    assert res.status_code == 403, res.text

    assert client.get(f"/investors/{mine['investor_id']}/onboarding").status_code == 401


# --- GET /brokers --------------------------------------------------------------------


def test_the_broker_registry_is_served_and_authenticated(client) -> None:
    assert client.get("/brokers").status_code == 401

    body = _register(client, "brokers@example.com")
    res = client.get("/brokers", headers=_auth(body))
    assert res.status_code == 200, res.text

    brokers = {b["code"]: b for b in res.json()}
    assert "ZERODHA" in brokers
    assert brokers["ZERODHA"]["parses_tradebooks"] is True
    # No mail-receiving domain on this deployment, so nobody is offered an address --
    # which is what keeps a dead @ingest.example.com off every screen.
    assert all(not b["forwarding"] for b in brokers.values())


def test_no_broker_promises_a_parser_it_does_not_have(client) -> None:
    body = _register(client, "honest-badges@example.com")
    brokers = client.get("/brokers", headers=_auth(body)).json()

    for broker in brokers:
        if not broker["documents"]:
            assert broker["parses_contract_notes"] is False
            assert broker["parses_tradebooks"] is False
            assert broker["document_labels"] == []
        # Every broker is usable by file upload regardless, so every one has to say
        # where its files come from.
        assert broker["console_steps"]


# --- helpers -------------------------------------------------------------------------


def _insert_transaction(db, investor_id: str, account_id: str) -> None:
    """One row straight into the ledger. The onboarding endpoint only counts, so this
    does not need to go through an adapter -- and staying out of the import path keeps
    this test about the derivation rather than about parsing.

    ``investor_id`` is used for the dedupe key only: ``transaction`` is scoped by
    ACCOUNT, which is why the endpoint has to reach the ledger through a join.
    """
    with db.cursor() as cur:
        # transaction.isin is a foreign key into security, and this suite seeds no
        # fixtures -- so the security has to exist before the trade that references it.
        cur.execute(
            "INSERT INTO security (isin, symbol, name, asset_class) "
            "VALUES ('INE153T01027', 'BLS', 'BLS International', 'EQ') "
            "ON CONFLICT (isin) DO NOTHING"
        )
        cur.execute(
            """
            INSERT INTO transaction (
                account_id, isin, txn_date, txn_type,
                quantity, price, charges, source, dedupe_key
            )
            VALUES (%s, 'INE153T01027', DATE '2024-01-10', 'BUY',
                    100, 200.5, 0, 'MANUAL', %s)
            """,
            (account_id, f"onboarding-test-{investor_id}"),
        )


def _complete_setup(db, investor_id: str) -> None:
    """Consent + an account + a trade: everything ``complete`` is defined as."""
    from app.db.consent import record_consent

    record_consent(db, investor_id, notice_version="v1", evidence_ref="onboarding-tests")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'ZERODHA', true) RETURNING id",
            (investor_id,),
        )
        account_id = str(cur.fetchone()[0])
    _insert_transaction(db, investor_id, account_id)
