"""12-factor configuration -- the single ``Settings`` object every new module reads from.

``db/connection.py`` and ``db/crypto.py`` read their env vars directly and keep doing so
unchanged (see their own modules) -- ``Settings`` sources from the same names, so both
paths agree without one having to call the other. New code added on top of them (auth,
the routers, the webhook) takes config via dependency injection from here instead.

No field below that guards a secret has a default. A ``DEBUG=True`` fallback secret is
exactly the kind of dummy value CLAUDE.md's Rule 1 forbids: local dev sets a real value
in ``.env``, same as production.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: provider name -> the Settings field names its verifier requires. Keys here are the
#: only values INGEST_WEBHOOK_PROVIDER accepts -- see app/ingest/webhook_providers.py,
#: which is registered by the same three names.
_WEBHOOK_PROVIDER_REQUIRES: dict[str, tuple[str, ...]] = {
    "mailgun": ("ingest_mailgun_signing_key",),
    "postmark": ("ingest_postmark_basic_auth_user", "ingest_postmark_basic_auth_password"),
    "sendgrid": ("ingest_sendgrid_shared_secret",),
}

#: Dev-only placeholder domain -- RFC 2606 reserves example.com so this can never
#: resolve and never collides with a real client-facing address. Matches the address
#: already used throughout tests/test_webhook.py and tests/test_db_webhook.py.
_INGEST_DOMAIN_DEV_DEFAULT = "ingest.example.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # --- database -----------------------------------------------------------------
    # Exact existing name: db/connection.py's DATABASE_URL_ENV. No default -- a silent
    # fallback to localhost is how a test run ends up writing to something real.
    database_url: str

    # --- field-level encryption -----------------------------------------------------
    # Exact existing names: db/crypto.py's ENCRYPTION_KEY_ENV and PAN_PEPPER_ENV.
    portfolio_encryption_key: str
    portfolio_pan_pepper: str

    # --- auth -------------------------------------------------------------------
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600
    # The server-side session's horizon, deliberately far longer than the token's:
    # the short JWT is what travels on every request; app_session is what a refresh
    # exchange actually renews. Without this gap there is nothing to refresh -- a
    # session that dies with its token makes "invalid or expired token" permanent
    # until the next full login.
    session_ttl_seconds: int = 30 * 24 * 3600

    # --- ops endpoints (app.auth.ops) --------------------------------------------
    # Shared secret for POST /ops/prices/refresh and /ops/snapshots/run -- unset means
    # those two endpoints refuse every request, same "no safe default" posture as
    # jwt_secret above. Not a per-user credential: these mutate every investor's stored
    # data at once and are meant for a cron job or you, curling the box directly, not a
    # signed-up alpha user.
    ops_api_key: str | None = None

    # Vercel's own cron-authentication convention (docs/DEPLOYMENT.md): set a
    # CRON_SECRET project env var and Vercel automatically sends it as
    # `Authorization: Bearer <value>` on every cron-triggered request -- no other
    # signing or IP-allowlisting mechanism exists for Vercel Cron. Deliberately
    # separate from ops_api_key rather than reused for it: Vercel Cron can only send
    # GET with this one header shape, so it hits its own GET /ops/cron/* routes
    # (app.routers.analytical), while ops_api_key keeps gating the POST routes a human
    # or a non-Vercel scheduler would call directly.
    cron_secret: str | None = None

    # --- web --------------------------------------------------------------------
    # Comma-separated in the environment; split into a list for CORSMiddleware.
    cors_origins: str = "http://localhost:3000"
    debug: bool = False

    # --- document storage ---------------------------------------------------------
    # "local" or "s3". Local is the development default; production selects s3 (R2).
    storage_backend: str = "local"
    local_storage_root: str = "./data/documents"
    # Exact existing names, read directly by storage/s3.py and storage/local.py -- kept
    # here too so app/storage/factory.py can choose and construct a backend at startup
    # without duplicating storage/s3.py's own env parsing.
    portfolio_storage_bucket: str | None = None
    portfolio_storage_endpoint: str | None = None
    portfolio_storage_signing_secret: str | None = None

    # --- price-pipe failure alerts (prices/alerts.py) ------------------------------
    # Required only to send real alerts -- app.prices.alerts.get_notifier() falls back
    # to log-only when any of the three below is unset, same "required only when
    # selected" convention as the storage backend fields above. No default host/from/
    # recipient: a fallback that looked configured but pointed nowhere would be worse
    # than the honest log-only fallback it would be hiding.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str | None = None
    smtp_alert_recipient: str | None = None

    # --- inbound-email forwarding addresses (app/ingest/addresses.py) ---------------
    # Not a secret -- this is mailed to clients, so unlike jwt_secret et al. above it
    # may carry a placeholder dev default, the same way cors_origins does. Production
    # must still set a real value: _validate_ingest_domain below fails at startup
    # rather than mailing addresses at a domain that will bounce.
    ingest_domain: str = _INGEST_DOMAIN_DEV_DEFAULT

    # --- inbound-email webhook (app/ingest/webhook_providers.py) --------------------
    # POST /ingest/email is internet-facing, so unlike storage_backend/SMTP above --
    # which degrade gracefully to a safe fallback when unset -- an unset or
    # inconsistent choice here must fail loudly rather than accept a request nothing
    # can verify. ingest_webhook_provider itself keeps the same "no safe default"
    # shape as storage_backend (None means the feature is off; the router refuses
    # every request rather than guessing a provider), but the field it selects is
    # validated below, eagerly, at Settings construction -- not lazily at first
    # request -- so a provider chosen without its matching secret fails at startup.
    ingest_webhook_provider: str | None = None
    ingest_mailgun_signing_key: str | None = None
    ingest_postmark_basic_auth_user: str | None = None
    ingest_postmark_basic_auth_password: str | None = None
    ingest_sendgrid_shared_secret: str | None = None
    # Not secret-guarding, so unlike the fields above this may default: 25 MiB matches
    # Mailgun's own combined-attachment cap.
    ingest_max_attachment_bytes: int = 26_214_400

    # --- in-app AI assistant (app/ai/gemini.py, app/routers/assistant.py) -----------
    # Degrades gracefully to "assistant unavailable" when unset, same convention as
    # storage_backend/SMTP above -- a hobby feature going dark must never take the rest
    # of the app down with it.
    gemini_api_key: str | None = None

    # --- LLM-assisted document extraction (app/ai/groq.py, app/ingest/llm_*.py) -----
    # TWO FACTS, DELIBERATELY SEPARATE. ``groq_api_key`` is "we hold credentials";
    # ``llm_parsing_enabled`` is "we are permitted to transmit the contents of client
    # financial documents to a fourth Data Processor" -- which docs/COMPLIANCE.md gates
    # on a signed DPA and an MITC AI-usage clause, both currently OPEN gates.
    #
    # Those are not the same fact and must not share a switch: turning the feature off
    # would otherwise mean deleting the key, which is how keys get pasted back in by
    # whoever needs it next. A key present with the flag false is the NORMAL state.
    groq_api_key: str | None = None
    # Not secret-guarding, so unlike the key this may default. Swappable by env alone --
    # Groq's endpoint is OpenAI-compatible and takes any model it serves, so trying a
    # cheaper or newer one is a config change, not a code change. Must support
    # response_format={"type": "json_object"}.
    groq_model: str = "openai/gpt-oss-20b"
    llm_parsing_enabled: bool = False

    # --- demerger/amalgamation notification watch (app/ingest/demerger_watch.py) ----
    # ON BY DEFAULT since 2026-09-22 AND DELIBERATELY LIGHTWEIGHT. Reuses the SAME NSE
    # circulars source app.ingest.isin_change_feed already relies on (interim,
    # unofficial, confirmed live -- see that module's docstring) rather than adding a
    # second, less-vetted third-party dependency; this feature adds no new ToS exposure
    # of its own. It writes NOTHING to the ledger, NOTHING to security_alias, and never
    # touches app.engine.demerger -- it only shortens the gap between a company filing
    # an apportionment letter and a human knowing to go read it. A log line, not a queue.
    #
    # WHAT DEFAULTING IT TO TRUE COMMITS TO, since a default is the value most
    # deployments will actually run. One GET to a feed this codebase already polls
    # daily, and warnings on stderr. Measured before flipping, over a real 90-day NSE
    # window (2026-06-24..2026-09-22): 8 notices matched company-restructuring terms
    # market-wide -- roughly one every eleven days -- and 0 of them named a symbol this
    # project's own database tracks. The steady state of this feature is therefore
    # silence, which is why it is a log line and not a queue, and why enabling it cannot
    # bury anything. If that ratio ever inverts, the thing to revisit is the notification
    # channel, not this flag.
    demerger_watch_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_ingest_domain(self) -> Settings:
        """Outside DEBUG mode, the dev placeholder must have been overridden -- a
        forgotten INGEST_DOMAIN in production would mail every client an address at
        a domain nothing receives, which fails silently until someone asks why their
        forwarded statement never showed up. Fail at startup instead.

        Checks falsiness too, not just equality to the placeholder: an ``INGEST_DOMAIN=``
        line left blank in a copied ``.env`` parses as ``""``, not the placeholder
        string, and ``""`` would be an even worse address to hand out.
        """
        placeholder = not self.ingest_domain or self.ingest_domain == _INGEST_DOMAIN_DEV_DEFAULT
        if not self.debug and placeholder:
            raise ValueError(
                "INGEST_DOMAIN must be set to a real, mail-receiving domain outside "
                f"of DEBUG mode (got {self.ingest_domain!r})"
            )
        return self

    @model_validator(mode="after")
    def _validate_webhook_provider(self) -> Settings:
        provider = self.ingest_webhook_provider
        if provider is None:
            return self
        required = _WEBHOOK_PROVIDER_REQUIRES.get(provider)
        if required is None:
            raise ValueError(
                f"INGEST_WEBHOOK_PROVIDER={provider!r} is not a known provider "
                f"(expected one of {sorted(_WEBHOOK_PROVIDER_REQUIRES)})"
            )
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise ValueError(
                f"INGEST_WEBHOOK_PROVIDER={provider!r} requires "
                f"{', '.join(name.upper() for name in missing)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_storage_backend(self) -> Settings:
        """Outside DEBUG mode, ``local`` must not be the storage backend.

        ``LocalDocumentStore`` writes to a real directory on disk (``mkdir`` then
        ``write_bytes``) -- true on a VPS, but on Vercel (docs/DEPLOYMENT.md) the
        deployed function directory is read-only and only ``/tmp`` is writable, and
        even that is wiped between invocations. Left at the ``local`` default outside
        DEBUG, every document upload would fail with a raw filesystem error the first
        time someone actually tried one -- possibly days after deploying, whenever
        someone first uploads a statement. Fail at startup instead, the same posture
        ``_validate_ingest_domain`` takes for a forgotten ``INGEST_DOMAIN``.
        """
        if not self.debug and self.storage_backend == "local":
            raise ValueError(
                "STORAGE_BACKEND=local is a development-only default and will not "
                "work outside of DEBUG mode -- set STORAGE_BACKEND=s3 and the "
                "PORTFOLIO_STORAGE_* variables instead (see docs/DEPLOYMENT.md)"
            )
        return self



    @model_validator(mode="after")
    def _validate_llm_parsing(self) -> Settings:
        """Enabling LLM parsing without the credentials it needs fails at startup, in
        the shape ``_validate_webhook_provider`` uses -- a feature that sends personal
        data to a third party must not discover its own misconfiguration mid-request.

        Deliberately NOT gated on DEBUG, unlike ``_validate_storage_backend``. Code
        cannot know whether a Data Processing Agreement has been signed, and a check
        that pretended to would be dishonest about what it verified. The DPA is tracked
        as a go-live gate in docs/COMPLIANCE.md, where a human reads it.
        """
        if not self.llm_parsing_enabled:
            return self
        missing = [
            name
            for name in ("groq_api_key", "groq_model")
            if not (getattr(self, name) or "").strip()
        ]
        if missing:
            raise ValueError(
                "LLM_PARSING_ENABLED=true requires " + ", ".join(n.upper() for n in missing)
            )
        return self
@lru_cache
def get_settings() -> Settings:
    """Cached: ``Settings()`` re-reads the environment on every call otherwise, and a
    request-scoped dependency calling this on every request should not re-parse .env
    each time."""
    return Settings()
