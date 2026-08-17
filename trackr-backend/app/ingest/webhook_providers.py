"""Per-provider request verification and payload translation for ``POST /ingest/email``.

The three inbound-parse providers this endpoint accepts do not share one request shape
or one verification scheme:

- **Mailgun** posts ``multipart/form-data`` with numbered attachment fields
  (``attachment-1``, ``attachment-2``, ...) and signs the request: ``signature`` must
  equal ``hmac_sha256(signing_key, timestamp + token)``.
- **SendGrid** also posts ``multipart/form-data`` with numbered attachment fields
  (``attachment1``, ``attachment2``, ...), but signs nothing -- Inbound Parse has no
  custom-header support, so a shared secret travels as HTTP Basic Auth instead
  (typically by embedding it in the configured webhook URL).
- **Postmark** posts JSON, differently cased (``To``, ``From``,
  ``Attachments: [{Name, Content, ContentType}]``, ``Content`` already base64), and
  also signs nothing -- HTTP Basic Auth against a configured user/password pair.

Isolating that variance here, behind one ``verify_and_translate``, is what lets
``app.ingest.webhook.handle_inbound_email`` stay exactly what its own docstring says it
is: provider-ignorant. It only ever sees ``(to, attachments)`` in the one internal shape
it already consumed before this module existed -- ``{filename, content_type,
content_b64}`` per attachment.

Verification always runs before translation, and translation never runs at all if
verification fails -- an unverified request must never reach ``stage_batch``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import Request

if TYPE_CHECKING:
    from app.config import Settings


class WebhookAuthError(Exception):
    """Base for a failed webhook credential check."""


class MissingWebhookCredentialError(WebhookAuthError):
    """No credential was presented at all, or it was malformed -- 401."""


class InvalidWebhookCredentialError(WebhookAuthError):
    """A credential was presented but does not check out -- 403."""


class WebhookNotConfiguredError(Exception):
    """``INGEST_WEBHOOK_PROVIDER`` is unset -- there is no verifier to run.

    Never a 200 that stages an unverified file: an unconfigured deploy must refuse
    every request here, the same as a wrongly-configured one does.
    """


# --- shared HTTP Basic Auth helpers (Postmark, SendGrid) --------------------------


def _parse_basic_auth(request: Request) -> tuple[str, str]:
    header = request.headers.get("authorization", "")
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        raise MissingWebhookCredentialError("missing Basic Authorization header")
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise MissingWebhookCredentialError("malformed Basic Authorization header") from exc
    username, sep, password = decoded.partition(":")
    if not sep:
        raise MissingWebhookCredentialError("malformed Basic Authorization header")
    return username, password


async def _numbered_attachments(
    request: Request, prefix: str, count_field: str
) -> list[dict[str, Any]]:
    """``attachment-count``/``attachment-1..N`` (Mailgun) or ``attachments``/
    ``attachment1..N`` (SendGrid) -- real file uploads, not base64, so each is read and
    re-encoded into the one shape ``handle_inbound_email`` already consumes."""
    form = await request.form()
    try:
        count = int(form.get(count_field, 0))
    except (TypeError, ValueError):
        count = 0

    attachments = []
    for i in range(1, count + 1):
        upload = form.get(f"{prefix}{i}")
        if upload is None or not hasattr(upload, "read"):
            continue
        content = await upload.read()
        attachments.append(
            {
                "filename": upload.filename or "",
                "content_type": upload.content_type or "application/octet-stream",
                "content_b64": base64.b64encode(content).decode("ascii"),
            }
        )
    return attachments


# --- Mailgun ------------------------------------------------------------------------


async def _verify_mailgun(request: Request, settings: Settings) -> None:
    form = await request.form()
    timestamp = form.get("timestamp")
    token = form.get("token")
    signature = form.get("signature")
    if not timestamp or not token or not signature:
        raise MissingWebhookCredentialError("mailgun signature fields missing")

    # settings.ingest_mailgun_signing_key is guaranteed set: app.config.Settings
    # validates this combination at startup, not per-request.
    expected = hmac.new(
        settings.ingest_mailgun_signing_key.encode(),
        f"{timestamp}{token}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, str(signature)):
        raise InvalidWebhookCredentialError("mailgun signature does not match")


async def _translate_mailgun(request: Request) -> tuple[str, list[dict[str, Any]]]:
    form = await request.form()
    to = str(form.get("recipient", ""))
    attachments = await _numbered_attachments(
        request, prefix="attachment-", count_field="attachment-count"
    )
    return to, attachments


# --- SendGrid -----------------------------------------------------------------------


async def _verify_sendgrid(request: Request, settings: Settings) -> None:
    _username, password = _parse_basic_auth(request)
    # settings.ingest_sendgrid_shared_secret is guaranteed set -- see _verify_mailgun.
    if not hmac.compare_digest(password, settings.ingest_sendgrid_shared_secret):
        raise InvalidWebhookCredentialError("sendgrid shared secret does not match")


async def _translate_sendgrid(request: Request) -> tuple[str, list[dict[str, Any]]]:
    form = await request.form()
    to = str(form.get("to", ""))
    attachments = await _numbered_attachments(
        request, prefix="attachment", count_field="attachments"
    )
    return to, attachments


# --- Postmark -----------------------------------------------------------------------


async def _verify_postmark(request: Request, settings: Settings) -> None:
    username, password = _parse_basic_auth(request)
    # settings.ingest_postmark_basic_auth_user/_password are guaranteed set -- see
    # _verify_mailgun.
    user_ok = hmac.compare_digest(username, settings.ingest_postmark_basic_auth_user)
    password_ok = hmac.compare_digest(password, settings.ingest_postmark_basic_auth_password)
    if not (user_ok and password_ok):
        raise InvalidWebhookCredentialError("postmark basic auth credentials do not match")


async def _translate_postmark(request: Request) -> tuple[str, list[dict[str, Any]]]:
    body = await request.json()
    to = str(body.get("To", ""))
    attachments = [
        {
            "filename": a.get("Name", ""),
            "content_type": a.get("ContentType", "application/octet-stream"),
            # Postmark already base64-encodes attachment content in the JSON payload --
            # no re-encoding needed, unlike the multipart providers above.
            "content_b64": a.get("Content", ""),
        }
        for a in body.get("Attachments", [])
    ]
    return to, attachments


# --- registry, selected by INGEST_WEBHOOK_PROVIDER --------------------------------

_VERIFIERS: dict[str, Callable[[Request, Settings], Awaitable[None]]] = {
    "mailgun": _verify_mailgun,
    "sendgrid": _verify_sendgrid,
    "postmark": _verify_postmark,
}

_TRANSLATORS: dict[str, Callable[[Request], Awaitable[tuple[str, list[dict[str, Any]]]]]] = {
    "mailgun": _translate_mailgun,
    "sendgrid": _translate_sendgrid,
    "postmark": _translate_postmark,
}


async def verify_and_translate(
    request: Request, settings: Settings
) -> tuple[str, list[dict[str, Any]]]:
    """Verify the inbound request's provider-specific credential, then translate its
    provider-specific shape into ``(to, attachments)`` -- the internal shape
    ``app.ingest.webhook.handle_inbound_email`` already consumes.

    Raises:
        MissingWebhookCredentialError: no credential was presented, or it was
            malformed -- the router answers 401.
        InvalidWebhookCredentialError: a credential was presented but does not check
            out -- the router answers 403.

    ``settings.ingest_webhook_provider`` is validated to be one of this module's three
    registered names at Settings construction (see ``app.config``), so a configured
    deployment always resolves here; an unconfigured one (``None``) is handled by the
    router before this is called.
    """
    verify = _VERIFIERS[settings.ingest_webhook_provider]
    translate = _TRANSLATORS[settings.ingest_webhook_provider]
    await verify(request, settings)
    return await translate(request)
