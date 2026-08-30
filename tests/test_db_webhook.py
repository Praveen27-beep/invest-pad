"""POST /ingest/email, driven end to end over a real HTTP round trip against a real
database -- the request-parsing, auth-verification, and status-code behaviour
tests/test_webhook_providers.py's direct calls into app.ingest.webhook_providers cannot
exercise, because that suite never goes through FastAPI's own routing or app.main's
registered exception handlers.

This is the first suite in the repo to use ``fastapi.testclient.TestClient`` (see
trackr-backend/pyproject.toml's dev extra for why httpx had to be added) and the first to
import ``app.main`` at all -- everything else calls a router's handler function directly,
bypassing FastAPI's dependency injection entirely (see tests/test_db_grievance_router.py's
docstring). That shortcut does not work here: the whole point of this endpoint is
authenticating and parsing a real HTTP request, which calling the Python function with
pre-built arguments would skip past.

``app.main``'s module-level ``settings = get_settings()`` needs the four base secrets
Settings always requires; the ``app_module`` fixture below sets them via ``monkeypatch``
(reverted after the test) rather than a real ``.env`` -- app.main is imported lazily
inside that fixture, not at module scope, precisely so nothing leaks into the rest of the
suite. Per-test webhook configuration (which provider, which secret, storage location)
overrides ``get_settings`` on top of that; ``get_conn`` is overridden to the ``db``
fixture's already-migrated, already-open connection, so nothing here needs a commit to
see what the request staged -- it is the same transaction.

Attachment content is contract-note TEXT, not a real PDF: app.ingest.zerodha_contract_note
.ZerodhaContractNoteAdapter.parse() only calls pdfplumber when the bytes start with
``%PDF-``, decoding anything else as UTF-8 directly (the same shortcut
tests/test_zerodha_contract_note.py takes via parse_text()) -- and the investor fixture
below has no PAN on file, so app.ingest.webhook._pdf_password resolves to "", matching an
unencrypted document. That is enough to exercise the real adapter without pdfplumber or a
password-protected PDF in the repository.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from app.config import Settings

pytestmark = pytest.mark.db

BASE_SETTINGS = {
    "database_url": "postgresql://unused/for-this-suite",
    "portfolio_encryption_key": "unused-in-this-suite",
    "portfolio_pan_pepper": "unused-in-this-suite",
    "jwt_secret": "test-jwt-secret-not-for-production",
    # app/config.py's _validate_ingest_domain only accepts the dev placeholder
    # (ingest.example.com, matched by TO below) under DEBUG -- this suite is exactly
    # that dev context.
    "debug": True,
}

TO = "c001-zerodha-contractnote@ingest.example.com"

HEADER = """CONTRACT NOTE CUM TAX INVOICE
Zerodha Broking Limited
SEBI registration: INZ000031633
Contract Note No: CNT-26/27-77963149
Trade Date: 12/08/2026 Settlement No: 2026151
Order No. Order Time Trade No. Trade Time Security / Contract Description Buy(B) /
"""

CHARGES = """Pay in/Pay out obligation (Rs) (47951.10) 0.00 (47951.10)
Taxable value of Supply (Brokerage) (Rs)2 (0.01) (0.01)
IGST (@18% of Brok, SEBI, Trans & Clearing Charges) (Rs)3 (0.33) (0.33)
SEBI turnover fees (Rs) (0.05) (0.05)
Stamp duty (Rs) (7.00) (7.00)
"""

TRADE_A = (
    "1786505400085603080 12:19:40 1089300 12:19:40 WAAREEENER-A/INE377N01017 B BSE 18 "
    "0.0000 2663.95 (47951.10)\n"
)
TRADE_B = (
    "1786505400085603099 13:05:12 1089399 13:05:12 WAAREEENER-A/INE377N01017 B BSE 5 "
    "0.0000 2700.00 (13500.00)\n"
)

NOTE_A = (HEADER + TRADE_A + CHARGES).encode()
NOTE_B = (HEADER.replace("77963149", "77963200") + TRADE_B + CHARGES).encode()

MAILGUN_KEY = "test-mailgun-signing-key"
POSTMARK_USER = "hookuser"
POSTMARK_PASSWORD = "hookpass"


# --- fixtures ------------------------------------------------------------------------


@pytest.fixture()
def app_module(monkeypatch: pytest.MonkeyPatch):
    """Import app.main lazily -- the four base secrets Settings always requires are set
    here via monkeypatch (auto-reverted) rather than a real .env, and nowhere else in the
    suite imports this module, so the leak stays contained to this fixture's lifetime."""
    for key, value in BASE_SETTINGS.items():
        monkeypatch.setenv(key.upper(), value)
    from app.config import get_settings

    get_settings.cache_clear()
    import app.main as main_module

    yield main_module
    get_settings.cache_clear()


@pytest.fixture()
def make_client(app_module, db, monkeypatch: pytest.MonkeyPatch):
    """A factory: ``make_client(settings)`` returns a TestClient wired to the real app,
    with ``get_conn`` bound to this test's ``db`` connection and ``get_settings`` bound
    to whatever webhook configuration the test wants active."""
    from app.config import get_settings as get_settings_dep
    from app.database import get_conn as get_conn_dep
    from app.storage.local import SIGNING_SECRET_ENV
    from fastapi.testclient import TestClient

    monkeypatch.setenv(SIGNING_SECRET_ENV, "test-signing-secret")

    def _make(settings: Settings) -> TestClient:
        app_module.app.dependency_overrides[get_conn_dep] = lambda: db
        app_module.app.dependency_overrides[get_settings_dep] = lambda: settings
        return TestClient(app_module.app)

    yield _make
    app_module.app.dependency_overrides.clear()


def mailgun_settings(tmp_path, **overrides: object) -> Settings:
    fields = {
        **BASE_SETTINGS,
        "storage_backend": "local",
        "local_storage_root": str(tmp_path / "objects"),
        "ingest_webhook_provider": "mailgun",
        "ingest_mailgun_signing_key": MAILGUN_KEY,
        **overrides,
    }
    return Settings(_env_file=None, **fields)


def postmark_settings(tmp_path, **overrides: object) -> Settings:
    fields = {
        **BASE_SETTINGS,
        "storage_backend": "local",
        "local_storage_root": str(tmp_path / "objects"),
        "ingest_webhook_provider": "postmark",
        "ingest_postmark_basic_auth_user": POSTMARK_USER,
        "ingest_postmark_basic_auth_password": POSTMARK_PASSWORD,
        **overrides,
    }
    return Settings(_env_file=None, **fields)


def mailgun_signature(signing_key: str, timestamp: str, token: str) -> str:
    return hmac.new(
        signing_key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()


def post_mailgun(
    client,
    *,
    recipient: str = TO,
    attachments: list[tuple[str, bytes]] = (),
    timestamp: str = "1700000000",
    token: str = "tok-abc",
    signature: str | None = None,
):
    """A Mailgun-shaped ``multipart/form-data`` inbound-route POST: numbered
    ``attachment-N`` file fields plus the ``timestamp``/``token``/``signature`` triple."""
    if signature is None:
        signature = mailgun_signature(MAILGUN_KEY, timestamp, token)
    data = {
        "recipient": recipient,
        "timestamp": timestamp,
        "token": token,
        "signature": signature,
        "attachment-count": str(len(attachments)),
    }
    files = {
        f"attachment-{i}": (filename, content, "application/pdf")
        for i, (filename, content) in enumerate(attachments, start=1)
    }
    return client.post("/ingest/email", data=data, files=files or None)


def post_postmark(client, *, to: str = TO, attachments: list[tuple[str, bytes]] = ()):
    """A Postmark-shaped JSON POST, differently cased, Content already base64."""
    credentials = base64.b64encode(f"{POSTMARK_USER}:{POSTMARK_PASSWORD}".encode()).decode()
    payload = {
        "To": to,
        "From": "noreply@zerodha.com",
        "Subject": "Contract Note",
        "Attachments": [
            {
                "Name": filename,
                "ContentType": "application/pdf",
                "Content": base64.b64encode(content).decode("ascii"),
            }
            for filename, content in attachments
        ],
    }
    return client.post(
        "/ingest/email",
        content=json.dumps(payload),
        headers={
            "authorization": f"Basic {credentials}",
            "content-type": "application/json",
        },
    )


def batch_count(db) -> int:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM import_batch")
        return cur.fetchone()[0]


# --- correctly-signed Mailgun -> 202, staged, bytes reach storage ------------------


def test_correctly_signed_mailgun_request_stages_the_attachment(
    make_client, db, consented_investor, tmp_path
) -> None:
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, attachments=[("note.pdf", NOTE_A)])

    assert response.status_code == 202
    (result,) = response.json()
    assert result["parsed"] == 1
    assert result["rejected"] == 0
    assert result["document_id"]

    from app.db import documents
    from app.storage.local import LocalDocumentStore

    (doc,) = documents.documents_for_investor(db, consented_investor)
    store = LocalDocumentStore(tmp_path / "objects")
    assert store.get(doc["storage_key"]) == NOTE_A

    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM transaction")
        assert cur.fetchone()[0] == 0, "staging must not touch the ledger"


# --- tampered / missing signature: 403 (recognized-but-wrong) / 401 (absent) -------


def test_a_tampered_mailgun_signature_is_rejected_and_nothing_is_staged(
    make_client, db, investor, tmp_path
) -> None:
    """A present-but-wrong signature is a *recognized* credential that fails the check
    -- 403, not 401. 401 is reserved for a credential that is missing or malformed
    entirely (the next test below), per app.ingest.webhook_providers's own split
    between MissingWebhookCredentialError and InvalidWebhookCredentialError."""
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, attachments=[("note.pdf", NOTE_A)], signature="0" * 64)

    assert response.status_code == 403
    assert batch_count(db) == 0


def test_a_missing_mailgun_signature_field_is_rejected_and_nothing_is_staged(
    make_client, db, investor, tmp_path
) -> None:
    client = make_client(mailgun_settings(tmp_path))
    data = {
        "recipient": TO,
        "timestamp": "1700000000",
        "token": "tok-abc",
        # signature omitted entirely
        "attachment-count": "1",
    }
    response = client.post(
        "/ingest/email", data=data, files={"attachment-1": ("note.pdf", NOTE_A, "application/pdf")}
    )

    assert response.status_code == 401
    assert batch_count(db) == 0


# --- correctly-authenticated Postmark -> 202 ----------------------------------------


def test_correctly_authenticated_postmark_request_stages_the_attachment(
    make_client, db, consented_investor, tmp_path
) -> None:
    client = make_client(postmark_settings(tmp_path))
    response = post_postmark(client, attachments=[("note.pdf", NOTE_A)])

    assert response.status_code == 202
    (result,) = response.json()
    assert result["parsed"] == 1


def test_postmark_with_the_wrong_password_is_rejected(make_client, db, investor, tmp_path) -> None:
    client = make_client(postmark_settings(tmp_path))
    credentials = base64.b64encode(f"{POSTMARK_USER}:wrong".encode()).decode()
    payload = {"To": TO, "From": "noreply@zerodha.com", "Subject": "x", "Attachments": []}
    response = client.post(
        "/ingest/email",
        content=json.dumps(payload),
        headers={"authorization": f"Basic {credentials}", "content-type": "application/json"},
    )

    assert response.status_code == 403
    assert batch_count(db) == 0


# --- routing failures reach main.py's registered handlers --------------------------


def test_an_unroutable_to_address_is_422(make_client, db, investor, tmp_path) -> None:
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, recipient="not-routable@ingest.example.com")
    assert response.status_code == 422
    assert batch_count(db) == 0


def test_an_unknown_investor_code_is_404(make_client, db, investor, tmp_path) -> None:
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, recipient="zzz99-zerodha-contractnote@ingest.example.com")
    assert response.status_code == 404
    assert batch_count(db) == 0


def test_a_broker_with_no_matching_account_is_404(make_client, db, investor, tmp_path) -> None:
    """The investor fixture creates only a ZERODHA account -- routing to upstox has
    nowhere to land."""
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, recipient="c001-upstox-contractnote@ingest.example.com")
    assert response.status_code == 404
    assert batch_count(db) == 0


def test_an_unsupported_doctype_is_422(make_client, db, investor, tmp_path) -> None:
    """zerodha+tradebook has no registered adapter factory in app.ingest.webhook --
    only zerodha+contractnote does."""
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, recipient="c001-zerodha-tradebook@ingest.example.com")
    assert response.status_code == 422
    assert batch_count(db) == 0


# --- consent gate (app/db/consent.py, wired into handle_inbound_email) -------------


def test_a_consent_less_investor_is_refused_and_nothing_is_staged(
    make_client, db, investor, tmp_path
) -> None:
    """Routing succeeds -- the investor and its ZERODHA account both exist -- but no
    consent has been granted, so the gate refuses before anything is staged. Checked
    after routing/account/adapter resolution (see app.ingest.webhook.handle_inbound_email),
    which is why the sibling routing-failure tests above are unaffected by this gate:
    they never get far enough to reach it."""
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, attachments=[("note.pdf", NOTE_A)])

    assert response.status_code == 403
    assert batch_count(db) == 0


def test_a_consented_investor_is_no_longer_refused(
    make_client, db, consented_investor, tmp_path
) -> None:
    client = make_client(mailgun_settings(tmp_path))
    response = post_mailgun(client, attachments=[("note.pdf", NOTE_A)])

    assert response.status_code == 202
    assert batch_count(db) == 1


# --- the multi-attachment rollback fix ---------------------------------------------


def test_a_duplicate_attachment_does_not_discard_a_legitimate_one_alongside_it(
    make_client, db, consented_investor, tmp_path
) -> None:
    """NOTE_A is staged alone first. A second message then carries NOTE_B (new) followed
    by NOTE_A again (byte-identical to the first message's attachment) -- before the
    fix, DuplicateUploadError escaping stage_batch's loop rolled back NOTE_B too, on the
    same shared connection. It must not: NOTE_B has to stay staged."""
    settings = mailgun_settings(tmp_path)
    client = make_client(settings)

    first = post_mailgun(client, attachments=[("note_a.pdf", NOTE_A)])
    assert first.status_code == 202
    assert batch_count(db) == 1

    second = post_mailgun(client, attachments=[("note_b.pdf", NOTE_B), ("note_a_dup.pdf", NOTE_A)])
    assert second.status_code == 202
    new_result, duplicate_result = second.json()

    assert new_result["parsed"] == 1
    assert new_result["batch_id"] != first.json()[0]["batch_id"]

    assert duplicate_result["parsed"] == 0
    assert duplicate_result["batch_id"] == first.json()[0]["batch_id"]

    # The real proof: NOTE_B's batch actually persisted on the shared connection rather
    # than being discarded by a rollback triggered by NOTE_A's duplicate.
    assert batch_count(db) == 2
    with db.cursor() as cur:
        cur.execute("SELECT filename FROM import_batch WHERE id = %s", (new_result["batch_id"],))
        assert cur.fetchone()[0] == "note_b.pdf"


# --- oversized request -> 413 -------------------------------------------------------


def test_an_oversized_request_is_rejected_before_staging_anything(
    make_client, db, investor, tmp_path
) -> None:
    settings = mailgun_settings(tmp_path, ingest_max_attachment_bytes=64)
    client = make_client(settings)

    response = post_mailgun(client, attachments=[("note.pdf", NOTE_A)])

    assert response.status_code == 413
    assert batch_count(db) == 0
