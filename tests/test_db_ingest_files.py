"""POST /ingest/files -- the mixed multi-file upload, against a real database.

Two behaviours are the point of the route and both are asserted here:

1. **Routing without asking.** A first-time user hands over whatever their broker gave
   them; the server decides per file which adapter reads it. A tradebook CSV and a
   contract-note XLSX in the SAME request must both land, under different adapters.
2. **Per-file outcomes.** One unreadable file is a fact about that file. The good files
   in the same request still stage -- the opposite of ``/ingest/csv``'s all-or-nothing
   validation, which is correct there because that route has a declared slot to be wrong
   about.

The tier-1/tier-2 classification itself is unit-tested without a database in
tests/test_file_validation.py; what is tested here is that the route honours it, that
nothing reaches the ledger before an explicit promote, and that the enforcement on the
single-adapter routes is real rather than advisory.
"""

from __future__ import annotations

import pytest
from app.terms import CURRENT_TOS_VERSION

from tests.test_file_validation import (
    CAS_PDF,
    CONTRACT_NOTE_CLEAN_XLSX,
    CONTRACT_NOTE_PDF,
    TRADEBOOK_CSV,
)

pytestmark = pytest.mark.db

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


#: The same settings tests/test_db_ownership.py's TestClient runs on. Defined here rather
#: than shared: conftest_db.py is imported by the whole ~250-test database suite, and a
#: new fixture there is a wider blast radius than this one file needs.
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


@pytest.fixture()
def client(app_module, db, tmp_path, monkeypatch: pytest.MonkeyPatch):
    """TestClient bound to the ``db`` fixture's connection and a local storage root.

    A real HTTP round trip, not a direct call to the route function: the multipart
    body, the ``Authorization`` header and the ownership/consent dependencies are all
    part of what these tests are checking, and calling the plain function underneath the
    decorator would bypass every one of them.
    """
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
    with TestClient(app_module.app) as test_client:
        yield test_client
    app_module.app.dependency_overrides.clear()


@pytest.fixture()
def consent_for(db):
    def _grant(investor_id: str) -> None:
        from app.db.consent import record_consent

        record_consent(db, investor_id, notice_version="v1", evidence_ref="ingest-files-tests")

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
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password-1",
            # Registration will not create an account without an accepted terms
            # version any more (app.auth.schemas.RegisterRequest) -- an acceptance is
            # a record, and a login with none is a login we cannot prove was shown
            # anything. See migration 021.
            "tos_version": CURRENT_TOS_VERSION,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _login(client, email: str) -> str:
    return client.post("/auth/login", json={"email": email, "password": "password-1"}).json()[
        "token"
    ]


def _post_files(client, token, investor_id, account_id, files):
    return client.post(
        "/ingest/files",
        data={"investor_id": investor_id, "account_id": account_id},
        files=[("files", (name, content, mime)) for name, content, mime in files],
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture()
def session(client, consent_for, account_for):
    """A registered, consented investor with one account, and a token for them."""
    email = "files-upload@example.com"
    investor_id = _register(client, email)["investor_id"]
    consent_for(investor_id)
    return {
        "investor_id": investor_id,
        "account_id": account_for(investor_id),
        "token": _login(client, email),
    }


def test_one_request_routes_each_file_to_its_own_adapter(client, session) -> None:
    res = _post_files(
        client,
        session["token"],
        session["investor_id"],
        session["account_id"],
        [
            ("tradebook.csv", TRADEBOOK_CSV, "text/csv"),
            ("note.xlsx", CONTRACT_NOTE_CLEAN_XLSX, XLSX_MIME),
        ],
    )
    assert res.status_code == 202, res.text
    body = res.json()

    by_name = {f["filename"]: f for f in body["files"]}
    assert by_name["tradebook.csv"]["adapter"] == "zerodha_tradebook"
    assert by_name["note.xlsx"]["adapter"] == "zerodha_contract_note_xlsx"
    assert by_name["tradebook.csv"]["parsed"] == 1


def test_a_bad_file_does_not_take_the_good_ones_with_it(client, session) -> None:
    res = _post_files(
        client,
        session["token"],
        session["investor_id"],
        session["account_id"],
        [
            ("cas.pdf", CAS_PDF, "application/pdf"),
            ("tradebook.csv", TRADEBOOK_CSV, "text/csv"),
        ],
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["accepted"] == 1 and body["rejected"] == 1

    rejected = next(f for f in body["files"] if not f["ok"])
    assert rejected["filename"] == "cas.pdf"
    assert rejected["batch_id"] is None, "a rejected file must leave no batch behind"
    assert rejected["reason"] and rejected["hint"], "both sentences, always"
    assert len(body["staged_batch_ids"]) == 1


def test_a_renamed_contract_note_is_caught_by_content_not_by_name(client, session) -> None:
    """The brief's case: a contract-note PDF renamed to .csv. Tier 1 passes it; only the
    magic bytes catch it, and the message has to say which file and what to do."""
    res = _post_files(
        client,
        session["token"],
        session["investor_id"],
        session["account_id"],
        [("tradebook-2024.csv", CONTRACT_NOTE_PDF, "text/csv")],
    )
    assert res.status_code == 202, res.text
    outcome = res.json()["files"][0]
    assert outcome["ok"] is False
    assert outcome["container"] == "pdf"
    assert "actually a PDF" in outcome["reason"]


def test_nothing_reaches_the_ledger_before_promote(client, session) -> None:
    """Routing files automatically is a convenience; committing them automatically is
    not (docs/INGESTION.md, "Staging: why nothing auto-commits")."""
    headers = {"Authorization": f"Bearer {session['token']}"}
    res = _post_files(
        client,
        session["token"],
        session["investor_id"],
        session["account_id"],
        [("tradebook.csv", TRADEBOOK_CSV, "text/csv")],
    )
    batch_id = res.json()["staged_batch_ids"][0]

    before = client.get(f"/investors/{session['investor_id']}/transactions", headers=headers)
    assert before.json() == []

    promoted = client.post(f"/ingest/stage/{batch_id}/promote", headers=headers)
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["inserted"] == 1

    after = client.get(f"/investors/{session['investor_id']}/transactions", headers=headers)
    assert len(after.json()) == 1


def test_re_uploading_the_same_file_is_reported_as_already_imported(client, session) -> None:
    args = (client, session["token"], session["investor_id"], session["account_id"])
    first = _post_files(*args, [("tradebook.csv", TRADEBOOK_CSV, "text/csv")])
    again = _post_files(*args, [("tradebook.csv", TRADEBOOK_CSV, "text/csv")])

    outcome = again.json()["files"][0]
    assert outcome["ok"] is True, "a duplicate is an answer, not a failure"
    assert outcome["batch_id"] == first.json()["staged_batch_ids"][0]
    assert any("Already imported" in note for note in outcome["notes"])


def test_the_route_is_consent_gated_like_every_other_ingest_path(client, account_for) -> None:
    """No consent, no processing -- DPDP consent-first (docs/COMPLIANCE.md section 1).
    Deliberately uses an investor with NO grant, unlike the ``session`` fixture."""
    investor_id = _register(client, "files-no-consent@example.com")["investor_id"]
    res = _post_files(
        client,
        _login(client, "files-no-consent@example.com"),
        investor_id,
        account_for(investor_id),
        [("tradebook.csv", TRADEBOOK_CSV, "text/csv")],
    )
    assert res.status_code == 403, res.text


def test_the_route_is_owner_gated(client, session, account_for) -> None:
    stranger_id = _register(client, "files-stranger@example.com")["investor_id"]
    res = _post_files(
        client,
        _login(client, "files-stranger@example.com"),
        session["investor_id"],
        session["account_id"],
        [("tradebook.csv", TRADEBOOK_CSV, "text/csv")],
    )
    assert res.status_code == 403, res.text
    assert stranger_id != session["investor_id"]


# --- the single-adapter routes enforce the same check --------------------------------


def test_ingest_csv_refuses_a_contract_note_and_stages_nothing(client, session) -> None:
    """Tier 2 on the declared-slot route. All-or-nothing there on purpose: a wrong file
    means the wrong things were picked, and half-importing the selection leaves the
    person guessing which half."""
    res = client.post(
        "/ingest/csv",
        data={
            "investor_id": session["investor_id"],
            "account_id": session["account_id"],
            "adapter": "zerodha_tradebook",
        },
        files=[
            ("files", ("good.csv", TRADEBOOK_CSV, "text/csv")),
            ("files", ("note.csv", CONTRACT_NOTE_PDF, "text/csv")),
        ],
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert "Nothing was imported" in detail
    assert "note.csv" in detail

    listed = client.get(
        f"/ingest/batches?investor_id={session['investor_id']}",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assert listed.json() == [], "the valid file in the same request must not have staged"


def test_ingest_xlsx_names_the_slot_a_tradebook_belongs_in(client, session) -> None:
    res = client.post(
        "/ingest/xlsx",
        data={
            "investor_id": session["investor_id"],
            "account_id": session["account_id"],
            "adapter": "zerodha_contract_note_xlsx",
        },
        files=[("files", ("tradebook.xlsx", TRADEBOOK_CSV, XLSX_MIME))],
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assert res.status_code == 422, res.text
    assert "tradebook.xlsx" in res.json()["detail"]


def test_a_valid_upload_still_passes_the_new_check(client, session) -> None:
    """The guard must not have become a wall: the ordinary path is unchanged."""
    res = client.post(
        "/ingest/csv",
        data={
            "investor_id": session["investor_id"],
            "account_id": session["account_id"],
            "adapter": "zerodha_tradebook",
        },
        files=[("files", ("good.csv", TRADEBOOK_CSV, "text/csv"))],
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    assert res.status_code == 202, res.text
    assert res.json()[0]["parsed"] == 1
