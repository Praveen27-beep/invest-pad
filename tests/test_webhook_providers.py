"""app/ingest/webhook_providers.py -- per-provider verification and payload translation
for POST /ingest/email, exercised directly against Starlette ``Request`` objects built
from raw ASGI scopes.

No database and no real HTTP server needed: verification and translation only ever read
the request (headers, form, JSON body) and ``Settings``, so building a minimal ASGI
``receive`` callable is enough to drive them exactly as FastAPI would. Every function
under test is a coroutine; this project has no async-test plugin installed (no existing
test in the repo is ``async def``), so each is driven with a bare ``asyncio.run`` from an
ordinary sync test rather than adding one.

The full route -- provider selection, the 401/403/413/500 status codes, and the fix for
the multi-attachment rollback bug -- is covered end to end in tests/test_db_webhook.py,
which needs a real database because the route does.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest
from app.config import Settings
from app.ingest.webhook_providers import (
    InvalidWebhookCredentialError,
    MissingWebhookCredentialError,
    _parse_basic_auth,
    _verify_mailgun,
    _verify_postmark,
    _verify_sendgrid,
    verify_and_translate,
)
from starlette.requests import Request

REQUIRED = {
    "database_url": "postgresql://unused/for-this-suite",
    "portfolio_encryption_key": "unused-in-this-suite",
    "portfolio_pan_pepper": "unused-in-this-suite",
    "jwt_secret": "test-jwt-secret-not-for-production",
    # app/config.py's _validate_ingest_domain only accepts the dev placeholder domain
    # under DEBUG -- this suite is exactly that dev context.
    "debug": True,
}


def run(coro):  # noqa: ANN001, ANN201 -- a thin asyncio.run alias, not worth annotating
    return asyncio.run(coro)


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


def _urlencode_form(fields: dict[str, str]) -> bytes:
    return urlencode(fields).encode()


def make_request(
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    content_type: str = "application/x-www-form-urlencoded",
) -> Request:
    """A Starlette ``Request`` over a fixed body, built the same way an ASGI server
    delivers one: a single ``http.request`` message, then disconnect."""
    raw_headers = [(b"content-type", content_type.encode())]
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))

    scope = {
        "type": "http",
        "method": method,
        "headers": raw_headers,
        "path": "/ingest/email",
    }

    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


# --- HTTP Basic Auth parsing (Postmark, SendGrid) -----------------------------------


def test_basic_auth_round_trips_username_and_password() -> None:
    credentials = base64.b64encode(b"alice:s3cret").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    assert _parse_basic_auth(request) == ("alice", "s3cret")


def test_basic_auth_missing_header_is_missing_not_invalid() -> None:
    request = make_request()
    with pytest.raises(MissingWebhookCredentialError):
        _parse_basic_auth(request)


def test_basic_auth_wrong_scheme_is_missing() -> None:
    request = make_request(headers={"authorization": "Bearer sometoken"})
    with pytest.raises(MissingWebhookCredentialError):
        _parse_basic_auth(request)


def test_basic_auth_malformed_base64_is_missing_not_a_500() -> None:
    request = make_request(headers={"authorization": "Basic not-valid-base64!!"})
    with pytest.raises(MissingWebhookCredentialError):
        _parse_basic_auth(request)


def test_basic_auth_with_no_colon_is_malformed() -> None:
    encoded = base64.b64encode(b"nocolonhere").decode()
    request = make_request(headers={"authorization": f"Basic {encoded}"})
    with pytest.raises(MissingWebhookCredentialError):
        _parse_basic_auth(request)


# --- Mailgun: hmac_sha256(signing_key, timestamp + token) == signature -------------


def _mailgun_signature(signing_key: str, timestamp: str, token: str) -> str:
    return hmac.new(
        signing_key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()


def test_mailgun_accepts_a_correctly_computed_signature() -> None:
    cfg = settings(ingest_webhook_provider="mailgun", ingest_mailgun_signing_key="key-123")
    signature = _mailgun_signature("key-123", "1700000000", "tok-abc")
    request = make_request(
        body=_urlencode_form(
            {"timestamp": "1700000000", "token": "tok-abc", "signature": signature}
        )
    )
    run(_verify_mailgun(request, cfg))  # does not raise


def test_mailgun_rejects_a_tampered_signature() -> None:
    cfg = settings(ingest_webhook_provider="mailgun", ingest_mailgun_signing_key="key-123")
    request = make_request(
        body=_urlencode_form({"timestamp": "1700000000", "token": "tok-abc", "signature": "0" * 64})
    )
    with pytest.raises(InvalidWebhookCredentialError):
        run(_verify_mailgun(request, cfg))


def test_mailgun_rejects_a_signature_computed_with_the_wrong_key() -> None:
    cfg = settings(ingest_webhook_provider="mailgun", ingest_mailgun_signing_key="key-123")
    wrong_key_signature = _mailgun_signature("a-different-key", "1700000000", "tok-abc")
    request = make_request(
        body=_urlencode_form(
            {"timestamp": "1700000000", "token": "tok-abc", "signature": wrong_key_signature}
        )
    )
    with pytest.raises(InvalidWebhookCredentialError):
        run(_verify_mailgun(request, cfg))


@pytest.mark.parametrize("missing", ["timestamp", "token", "signature"])
def test_mailgun_rejects_a_request_missing_any_signature_field(missing: str) -> None:
    cfg = settings(ingest_webhook_provider="mailgun", ingest_mailgun_signing_key="key-123")
    fields = {"timestamp": "1700000000", "token": "tok-abc", "signature": "0" * 64}
    del fields[missing]
    request = make_request(body=_urlencode_form(fields))
    with pytest.raises(MissingWebhookCredentialError):
        run(_verify_mailgun(request, cfg))


# --- SendGrid: shared secret as the Basic Auth password ----------------------------


def test_sendgrid_accepts_the_configured_shared_secret() -> None:
    cfg = settings(ingest_webhook_provider="sendgrid", ingest_sendgrid_shared_secret="topsecret")
    credentials = base64.b64encode(b"sendgrid:topsecret").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    run(_verify_sendgrid(request, cfg))  # does not raise


def test_sendgrid_rejects_the_wrong_secret() -> None:
    cfg = settings(ingest_webhook_provider="sendgrid", ingest_sendgrid_shared_secret="topsecret")
    credentials = base64.b64encode(b"sendgrid:wrong").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    with pytest.raises(InvalidWebhookCredentialError):
        run(_verify_sendgrid(request, cfg))


def test_sendgrid_ignores_the_username_and_checks_only_the_password() -> None:
    """SendGrid's Inbound Parse URL carries the secret as the password half of an
    embedded ``user:pass@host`` URL -- the username is whatever the operator chose and
    is not part of the check."""
    cfg = settings(ingest_webhook_provider="sendgrid", ingest_sendgrid_shared_secret="topsecret")
    credentials = base64.b64encode(b"whatever-username:topsecret").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    run(_verify_sendgrid(request, cfg))  # does not raise


# --- Postmark: HTTP Basic Auth, user AND password both required -------------------


def test_postmark_accepts_the_configured_user_and_password() -> None:
    cfg = settings(
        ingest_webhook_provider="postmark",
        ingest_postmark_basic_auth_user="hookuser",
        ingest_postmark_basic_auth_password="hookpass",
    )
    credentials = base64.b64encode(b"hookuser:hookpass").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    run(_verify_postmark(request, cfg))  # does not raise


def test_postmark_rejects_the_right_password_with_the_wrong_username() -> None:
    cfg = settings(
        ingest_webhook_provider="postmark",
        ingest_postmark_basic_auth_user="hookuser",
        ingest_postmark_basic_auth_password="hookpass",
    )
    credentials = base64.b64encode(b"someoneelse:hookpass").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    with pytest.raises(InvalidWebhookCredentialError):
        run(_verify_postmark(request, cfg))


def test_postmark_rejects_the_right_username_with_the_wrong_password() -> None:
    cfg = settings(
        ingest_webhook_provider="postmark",
        ingest_postmark_basic_auth_user="hookuser",
        ingest_postmark_basic_auth_password="hookpass",
    )
    credentials = base64.b64encode(b"hookuser:wrong").decode()
    request = make_request(headers={"authorization": f"Basic {credentials}"})
    with pytest.raises(InvalidWebhookCredentialError):
        run(_verify_postmark(request, cfg))


# --- translation: provider shape -> the one internal shape -------------------------


def test_postmark_translation_remaps_casing_and_keeps_content_already_base64() -> None:
    cfg = settings(
        ingest_webhook_provider="postmark",
        ingest_postmark_basic_auth_user="hookuser",
        ingest_postmark_basic_auth_password="hookpass",
    )
    credentials = base64.b64encode(b"hookuser:hookpass").decode()
    payload = {
        "To": "c001-zerodha-contractnote@ingest.example.com",
        "From": "noreply@zerodha.com",
        "Subject": "Contract Note",
        "Attachments": [
            {"Name": "note.pdf", "ContentType": "application/pdf", "Content": "aGVsbG8="}
        ],
    }
    request = make_request(
        headers={"authorization": f"Basic {credentials}"},
        body=json.dumps(payload).encode(),
        content_type="application/json",
    )
    to, attachments = run(verify_and_translate(request, cfg))
    assert to == "c001-zerodha-contractnote@ingest.example.com"
    assert attachments == [
        {"filename": "note.pdf", "content_type": "application/pdf", "content_b64": "aGVsbG8="}
    ]


def test_a_failed_verification_never_reaches_translation() -> None:
    """The request body carries an attachment, but the signature is wrong -- proving
    translate() never ran is exactly proving stage_batch never saw it."""
    cfg = settings(ingest_webhook_provider="mailgun", ingest_mailgun_signing_key="key-123")
    request = make_request(
        body=_urlencode_form(
            {
                "timestamp": "1700000000",
                "token": "tok-abc",
                "signature": "0" * 64,
                "recipient": "c001-zerodha-contractnote@ingest.example.com",
            }
        )
    )
    with pytest.raises(InvalidWebhookCredentialError):
        run(verify_and_translate(request, cfg))
