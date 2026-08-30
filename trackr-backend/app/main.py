"""The FastAPI application: JSON API, CORS, and one exception-handling layer.

The server-rendered screens and ``api/templates/*.html`` from the root package are
RETIRED here, not carried forward -- ``trackr-frontend/`` is the replacement UI, and
this becomes a pure JSON API. See docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md section 1.

Every handler below logs before responding: request id, method, path, and the full
traceback for a 500. Never a bare ``except: pass`` -- Rule 2 has zero exceptions.

    cd trackr-backend && DATABASE_URL=postgresql:///portfolio uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth.ops import (
    CronSecretInvalidError,
    CronSecretMissingError,
    CronSecretNotConfiguredError,
    OpsKeyInvalidError,
    OpsKeyMissingError,
    OpsNotConfiguredError,
)
from app.auth.service import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.config import get_settings
from app.db.connection import DatabaseNotConfiguredError
from app.db.consent import ConsentMissingError
from app.db.crypto import InvalidPANError
from app.db.grievance import AlreadyResolvedError
from app.db.imports import BatchAlreadyResolvedError, BatchNotFoundError, DuplicateUploadError
from app.db.privacy import LegalHoldError
from app.db.repository import DuplicateInvestorCodeError
from app.engine.errors import MissingPriceError, NegativeHoldingError, UnparseableRowError
from app.ingest.webhook import (
    NoMatchingAccountError,
    NoSuchInvestorError,
    UnroutableAddressError,
    UnsupportedDocumentError,
)
from app.ingest.webhook_providers import (
    InvalidWebhookCredentialError,
    MissingWebhookCredentialError,
    WebhookNotConfiguredError,
)
from app.rate_limit import limiter
from app.routers import (
    analytical,
    assistant,
    auth,
    consent,
    grievance,
    holdings,
    ingest,
    investors,
    privacy,
    reconcile,
    transactions,
)

logger = logging.getLogger("app")

settings = get_settings()

app = FastAPI(title="Trackr Portfolio Intelligence", version="0.1.0-mvp")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class CatchAllExceptionMiddleware:
    """Convert any exception that reaches here into the generic 500 JSON response
    (``unhandled_exception_handler`` below), positioned inside ``CORSMiddleware`` so
    that response still carries CORS headers.

    Deliberately NOT ``@app.exception_handler(Exception)``: Starlette hoists a handler
    registered for the bare ``Exception`` class straight into ``ServerErrorMiddleware``
    -- the true outermost ASGI layer, above ``CORSMiddleware`` and every other
    middleware, by design (``starlette/applications.py``:
    ``if key in (500, Exception): error_handler = value``). A response built there is
    sent via the raw, unwrapped ASGI ``send``, bypassing CORS entirely -- every
    unhandled 500 reaches the browser with no ``Access-Control-Allow-Origin`` header,
    which the browser reports as a CORS failure and masks the real error. Catching it
    here instead, below CORS in the middleware stack, is what actually lets CORS add
    its headers -- confirmed against a local repro before this was written; see the
    session that added this comment for the reproduction script if it resurfaces.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            response = await unhandled_exception_handler(Request(scope, receive=receive), exc)
            await response(scope, receive, send)


app.add_middleware(CatchAllExceptionMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestContextMiddleware:
    """Assign a request id up front so every log line for this request -- including
    an exception handler's -- can be correlated, and echo it back so a client-reported
    error can be found in the server log from the header alone.

    Plain ASGI, deliberately not ``@app.middleware("http")`` (Starlette's
    ``BaseHTTPMiddleware``): that runs the downstream app in a background task, and
    when a route raises, its ``call_next()`` re-raises the original exception a second
    time even after ``CatchAllExceptionMiddleware`` above has already produced and sent
    a clean response -- harmless once that middleware exists, but it double-logs every
    error and needlessly surfaces a second traceback at the ASGI-server level. A plain
    ASGI middleware only wraps ``send``, so it never buffers or re-raises around a
    response Starlette's exception handling already sent.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.monotonic()
        status_code = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_wrapper)
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id,
            scope["method"],
            scope["path"],
            status_code,
            (time.monotonic() - started) * 1000,
        )


app.add_middleware(RequestContextMiddleware)


def _error(request: Request, status_code: int, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": message,
            "request_id": getattr(request.state, "request_id", None),
            **extra,
        },
    )


# --------------------------------------------------------------------------------------
# engine.errors -- CLAUDE.md rule 4: a missing price raises, never defaults to zero.
# --------------------------------------------------------------------------------------


@app.exception_handler(MissingPriceError)
async def missing_price_handler(request: Request, exc: MissingPriceError) -> JSONResponse:
    return _error(
        request,
        409,
        "one or more held ISINs have no usable price within the staleness window",
        isins=exc.isins,
    )


@app.exception_handler(NegativeHoldingError)
async def negative_holding_handler(request: Request, exc: NegativeHoldingError) -> JSONResponse:
    deficit = -exc.quantity if exc.quantity is not None else None
    return _error(
        request,
        409,
        f"holding for {exc.isin} went negative; buy history is incomplete",
        isin=exc.isin,
        deficit=str(deficit) if deficit is not None else None,
        as_of=str(exc.as_of) if exc.as_of is not None else None,
    )


@app.exception_handler(UnparseableRowError)
async def unparseable_row_handler(request: Request, exc: UnparseableRowError) -> JSONResponse:
    return _error(request, 422, str(exc), row=exc.row, reason=exc.reason)


# --------------------------------------------------------------------------------------
# staging / imports
# --------------------------------------------------------------------------------------


@app.exception_handler(BatchNotFoundError)
async def batch_not_found_handler(request: Request, exc: BatchNotFoundError) -> JSONResponse:
    return _error(request, 404, str(exc))


@app.exception_handler(BatchAlreadyResolvedError)
async def batch_resolved_handler(request: Request, exc: BatchAlreadyResolvedError) -> JSONResponse:
    return _error(request, 409, str(exc))


@app.exception_handler(DuplicateUploadError)
async def duplicate_upload_handler(request: Request, exc: DuplicateUploadError) -> JSONResponse:
    return _error(request, 409, str(exc), batch_id=exc.batch_id)


# --------------------------------------------------------------------------------------
# inbound-email webhook routing (app/ingest/webhook.py)
# --------------------------------------------------------------------------------------


@app.exception_handler(UnroutableAddressError)
async def unroutable_address_handler(request: Request, exc: UnroutableAddressError) -> JSONResponse:
    return _error(request, 422, str(exc))


@app.exception_handler(NoSuchInvestorError)
async def no_such_investor_handler(request: Request, exc: NoSuchInvestorError) -> JSONResponse:
    return _error(request, 404, f"no such investor: {exc}")


@app.exception_handler(NoMatchingAccountError)
async def no_matching_account_handler(
    request: Request, exc: NoMatchingAccountError
) -> JSONResponse:
    return _error(request, 404, str(exc))


@app.exception_handler(UnsupportedDocumentError)
async def unsupported_document_handler(
    request: Request, exc: UnsupportedDocumentError
) -> JSONResponse:
    return _error(request, 422, str(exc))


# --------------------------------------------------------------------------------------
# inbound-email webhook auth (app/ingest/webhook_providers.py) -- POST /ingest/email is
# public internet, so every rejection here is logged with the provider that was
# configured to check it, not just the blanket per-request line request_context already
# writes. Never a 200 that stages an unverified file.
# --------------------------------------------------------------------------------------


def _webhook_provider_for_log(request: Request) -> str | None:
    """The dependency-injected Settings the route actually used, stashed on
    ``request.state`` by app.routers.ingest.ingest_email -- a registered
    ``@app.exception_handler`` is called by Starlette directly, never through FastAPI's
    dependency injection, so it would otherwise see app.main's module-level
    ``get_settings()`` even under a test's ``dependency_overrides``."""
    settings = getattr(request.state, "settings", None)
    return settings.ingest_webhook_provider if settings is not None else None


@app.exception_handler(MissingWebhookCredentialError)
async def missing_webhook_credential_handler(
    request: Request, exc: MissingWebhookCredentialError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "request_id=%s provider=%s inbound-email webhook credential missing/malformed: %s",
        request_id,
        _webhook_provider_for_log(request),
        exc,
    )
    return _error(request, 401, str(exc))


@app.exception_handler(InvalidWebhookCredentialError)
async def invalid_webhook_credential_handler(
    request: Request, exc: InvalidWebhookCredentialError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "request_id=%s provider=%s inbound-email webhook credential did not verify: %s",
        request_id,
        _webhook_provider_for_log(request),
        exc,
    )
    return _error(request, 403, str(exc))


@app.exception_handler(WebhookNotConfiguredError)
async def webhook_not_configured_handler(
    request: Request, exc: WebhookNotConfiguredError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "request_id=%s INGEST_WEBHOOK_PROVIDER is unset; refusing the inbound-email "
        "webhook request rather than accepting an unverifiable one",
        request_id,
    )
    return _error(request, 500, "the server is not configured correctly")


# --------------------------------------------------------------------------------------
# ops endpoints (app/auth/ops.py) -- same three-way shape as the webhook handlers above:
# missing/invalid/not-configured, not collapsed, since there is no account-enumeration
# concern for a single shared operational secret.
# --------------------------------------------------------------------------------------


@app.exception_handler(OpsKeyMissingError)
async def ops_key_missing_handler(request: Request, exc: OpsKeyMissingError) -> JSONResponse:
    logger.warning(
        "request_id=%s path=%s ops request missing X-Ops-Key",
        getattr(request.state, "request_id", None),
        request.url.path,
    )
    return _error(request, 401, "missing X-Ops-Key header")


@app.exception_handler(OpsKeyInvalidError)
async def ops_key_invalid_handler(request: Request, exc: OpsKeyInvalidError) -> JSONResponse:
    logger.warning(
        "request_id=%s path=%s ops request's X-Ops-Key did not verify",
        getattr(request.state, "request_id", None),
        request.url.path,
    )
    return _error(request, 403, "invalid X-Ops-Key")


@app.exception_handler(OpsNotConfiguredError)
async def ops_not_configured_handler(request: Request, exc: OpsNotConfiguredError) -> JSONResponse:
    logger.error(
        "request_id=%s path=%s OPS_API_KEY is unset; refusing the ops request rather "
        "than accepting an unverifiable one",
        getattr(request.state, "request_id", None),
        request.url.path,
    )
    return _error(request, 500, "the server is not configured correctly")


@app.exception_handler(CronSecretMissingError)
async def cron_secret_missing_handler(
    request: Request, exc: CronSecretMissingError
) -> JSONResponse:
    logger.warning(
        "request_id=%s path=%s cron request missing Authorization header",
        getattr(request.state, "request_id", None),
        request.url.path,
    )
    return _error(request, 401, "missing Authorization header")


@app.exception_handler(CronSecretInvalidError)
async def cron_secret_invalid_handler(
    request: Request, exc: CronSecretInvalidError
) -> JSONResponse:
    logger.warning(
        "request_id=%s path=%s cron request's Authorization header did not verify",
        getattr(request.state, "request_id", None),
        request.url.path,
    )
    return _error(request, 403, "invalid Authorization header")


@app.exception_handler(CronSecretNotConfiguredError)
async def cron_secret_not_configured_handler(
    request: Request, exc: CronSecretNotConfiguredError
) -> JSONResponse:
    logger.error(
        "request_id=%s path=%s CRON_SECRET is unset; refusing the cron request rather "
        "than accepting an unverifiable one",
        getattr(request.state, "request_id", None),
        request.url.path,
    )
    return _error(request, 500, "the server is not configured correctly")


# --------------------------------------------------------------------------------------
# privacy (app/db/privacy.py)
# --------------------------------------------------------------------------------------


@app.exception_handler(LegalHoldError)
async def legal_hold_handler(request: Request, exc: LegalHoldError) -> JSONResponse:
    return _error(request, 409, str(exc), investor_id=exc.investor_id, reasons=exc.reasons)


@app.exception_handler(LookupError)
async def lookup_error_handler(request: Request, exc: LookupError) -> JSONResponse:
    return _error(request, 404, str(exc) or "not found")


# --------------------------------------------------------------------------------------
# consent (app/db/consent.py) -- DPDP is consent-first: this is what makes that real.
# --------------------------------------------------------------------------------------


@app.exception_handler(ConsentMissingError)
async def consent_missing_handler(request: Request, exc: ConsentMissingError) -> JSONResponse:
    # 403, not 401/404: the request is otherwise well-formed and the investor exists --
    # it's refused because DPDP requires a live grant before personal data is processed.
    return _error(request, 403, str(exc), investor_id=exc.investor_id)


# --------------------------------------------------------------------------------------
# grievance (app/db/grievance.py)
# --------------------------------------------------------------------------------------


@app.exception_handler(AlreadyResolvedError)
async def grievance_already_resolved_handler(
    request: Request, exc: AlreadyResolvedError
) -> JSONResponse:
    return _error(request, 409, f"grievance {exc} is already resolved and cannot be reopened")


# --------------------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------------------


@app.exception_handler(EmailAlreadyRegisteredError)
async def email_taken_handler(request: Request, exc: EmailAlreadyRegisteredError) -> JSONResponse:
    return _error(request, 409, str(exc))


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(
    request: Request, exc: InvalidCredentialsError
) -> JSONResponse:
    return _error(request, 401, "invalid email or password")


# --------------------------------------------------------------------------------------
# onboarding (app/routers/investors.py, app/db/repository.py)
# --------------------------------------------------------------------------------------


@app.exception_handler(DuplicateInvestorCodeError)
async def duplicate_investor_code_handler(
    request: Request, exc: DuplicateInvestorCodeError
) -> JSONResponse:
    return _error(request, 409, str(exc), code=exc.code)


@app.exception_handler(InvalidPANError)
async def invalid_pan_handler(request: Request, exc: InvalidPANError) -> JSONResponse:
    return _error(request, 400, str(exc))


# --------------------------------------------------------------------------------------
# infrastructure
# --------------------------------------------------------------------------------------


@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(
    request: Request, exc: DatabaseNotConfiguredError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error("request_id=%s database not configured: %s", request_id, exc, exc_info=True)
    # The connection string is never in the client-facing message -- a 500 body is not
    # the place to confirm or deny what DATABASE_URL happens to be.
    return _error(request, 500, "the server is not configured correctly")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never a bare ``except: pass``. Every unhandled exception is logged with its full
    traceback, the request id, and the route, then answered with a generic 500 -- the
    client never sees internals, but the server log always has them.

    Called directly from ``CatchAllExceptionMiddleware`` above, not registered via
    ``@app.exception_handler(Exception)`` -- see that middleware's docstring for why."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "request_id=%s method=%s path=%s unhandled_exception=%s",
        request_id,
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return _error(request, 500, "internal server error")


app.include_router(auth.router)
app.include_router(investors.router)
app.include_router(holdings.router)
app.include_router(transactions.router)
app.include_router(ingest.router)
app.include_router(analytical.router)
app.include_router(privacy.router)
app.include_router(reconcile.router)
app.include_router(grievance.router)
app.include_router(consent.router)
app.include_router(assistant.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No DB round trip -- a probe that touches the database turns a
    slow query into an outage."""
    return {"status": "ok"}
