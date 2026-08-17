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


@lru_cache
def get_settings() -> Settings:
    """Cached: ``Settings()`` re-reads the environment on every call otherwise, and a
    request-scoped dependency calling this on every request should not re-parse .env
    each time."""
    return Settings()
