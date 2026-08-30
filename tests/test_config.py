"""app/config.py -- Settings must fail loudly when a required secret is absent, not
default to something that looks like it works. Every ``Settings(...)`` construction
here passes ``_env_file=None`` so the test is not at the mercy of whatever ``.env``
file, if any, happens to sit in the current working directory.
"""

from __future__ import annotations

import pytest
from app.config import Settings, get_settings
from pydantic import ValidationError

REQUIRED = {
    "database_url": "postgresql://localhost/test",
    "portfolio_encryption_key": "test-encryption-key",
    "portfolio_pan_pepper": "test-pan-pepper",
    "jwt_secret": "test-jwt-secret",
}


def test_missing_all_required_fields_raises() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    missing = {error["loc"][0] for error in excinfo.value.errors()}
    assert missing == set(REQUIRED)


@pytest.mark.parametrize("omitted", sorted(REQUIRED))
def test_missing_a_single_required_field_raises(omitted: str) -> None:
    kwargs = {name: value for name, value in REQUIRED.items() if name != omitted}
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **kwargs)
    missing = {error["loc"][0] for error in excinfo.value.errors()}
    assert missing == {omitted}


def test_all_required_fields_present_constructs_cleanly() -> None:
    settings = Settings(_env_file=None, debug=True, **REQUIRED)
    assert settings.database_url == REQUIRED["database_url"]
    assert settings.portfolio_encryption_key == REQUIRED["portfolio_encryption_key"]
    assert settings.portfolio_pan_pepper == REQUIRED["portfolio_pan_pepper"]
    assert settings.jwt_secret == REQUIRED["jwt_secret"]


def test_debug_true_does_not_supply_a_default_for_any_secret() -> None:
    """The module docstring is explicit that a DEBUG=True fallback secret is exactly
    the dummy value CLAUDE.md's Rule 1 forbids -- confirm there is no such branch by
    setting debug=True and still omitting every secret."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, debug=True)


def test_optional_fields_default_sensibly() -> None:
    """``ingest_domain`` and ``storage_backend`` are deliberately overridden here, not
    left at their dev defaults: both are only safe under DEBUG=True (see the
    INGEST_DOMAIN block below, and test_storage_backend_local_outside_debug_fails_at_
    construction for storage_backend), and this test's whole point is checking every
    OTHER field's default with ``debug`` at its own real default of False."""
    settings = Settings(
        _env_file=None,
        ingest_domain="ops.example.test",
        storage_backend="s3",
        **REQUIRED,
    )
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expiry_seconds == 3600
    assert settings.debug is False
    assert settings.local_storage_root == "./data/documents"
    assert settings.cors_origins == "http://localhost:3000"
    assert settings.portfolio_storage_bucket is None
    assert settings.portfolio_storage_endpoint is None
    assert settings.portfolio_storage_signing_secret is None
    assert settings.smtp_host is None
    assert settings.smtp_port == 587
    assert settings.smtp_use_tls is True
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_from_address is None
    assert settings.smtp_alert_recipient is None
    assert settings.ingest_domain == "ops.example.test"
    assert settings.ingest_webhook_provider is None
    assert settings.ingest_mailgun_signing_key is None
    assert settings.ingest_postmark_basic_auth_user is None
    assert settings.ingest_postmark_basic_auth_password is None
    assert settings.ingest_sendgrid_shared_secret is None
    assert settings.ingest_max_attachment_bytes == 26_214_400


def test_cors_origin_list_splits_and_strips_and_drops_empties() -> None:
    settings = Settings(
        _env_file=None,
        debug=True,
        cors_origins=" http://a.example.com ,http://b.example.com,, ",
        **REQUIRED,
    )
    assert settings.cors_origin_list == ["http://a.example.com", "http://b.example.com"]


# --- INGEST_DOMAIN: not a secret, so it may keep a dev placeholder default -- but
# --- unlike storage_backend, that default is not a safe *production* fallback, so it
# --- is validated eagerly (at construction) outside DEBUG mode, the same "fail at
# --- startup, not on the first mailed address" shape as INGEST_WEBHOOK_PROVIDER below --


def test_ingest_domain_defaults_to_the_dev_placeholder_under_debug() -> None:
    settings = Settings(_env_file=None, debug=True, **REQUIRED)
    assert settings.ingest_domain == "ingest.example.com"


def test_ingest_domain_left_at_the_dev_placeholder_outside_debug_fails_at_construction() -> None:
    with pytest.raises(ValidationError, match="INGEST_DOMAIN"):
        Settings(_env_file=None, **REQUIRED)


def test_ingest_domain_blank_outside_debug_also_fails_at_construction() -> None:
    """An ``INGEST_DOMAIN=`` line left blank in a copied .env parses as ``""``, not the
    placeholder string -- must still be caught, not silently handed out as an address
    with no domain at all."""
    with pytest.raises(ValidationError, match="INGEST_DOMAIN"):
        Settings(_env_file=None, ingest_domain="", **REQUIRED)


def test_ingest_domain_explicit_value_constructs_cleanly_without_debug() -> None:
    settings = Settings(
        _env_file=None,
        ingest_domain="ingest.realclient.example",
        storage_backend="s3",
        **REQUIRED,
    )
    assert settings.ingest_domain == "ingest.realclient.example"


# --- STORAGE_BACKEND: "local" writes to a real directory on disk -- fine for a VPS,
# --- fails outright on Vercel's read-only function filesystem (docs/DEPLOYMENT.md) ---


def test_storage_backend_local_outside_debug_fails_at_construction() -> None:
    with pytest.raises(ValidationError, match="STORAGE_BACKEND"):
        Settings(_env_file=None, ingest_domain="ops.example.test", **REQUIRED)


def test_storage_backend_local_is_fine_under_debug() -> None:
    settings = Settings(_env_file=None, debug=True, **REQUIRED)
    assert settings.storage_backend == "local"


def test_storage_backend_s3_is_fine_without_debug() -> None:
    settings = Settings(
        _env_file=None, ingest_domain="ops.example.test", storage_backend="s3", **REQUIRED
    )
    assert settings.storage_backend == "s3"


# --- INGEST_WEBHOOK_PROVIDER: required only when a provider is chosen, but validated
# --- as a combination eagerly (at construction), not lazily on the first request -----


def test_no_webhook_provider_constructs_cleanly_with_none_of_the_secrets() -> None:
    """Unlike storage_backend, there is no safe *working* default here -- but leaving it
    unset must still construct cleanly, since app.routers.ingest refuses every request
    at runtime when it is None rather than this failing at startup for deployments that
    do not expose the webhook at all."""
    settings = Settings(_env_file=None, debug=True, **REQUIRED)
    assert settings.ingest_webhook_provider is None


def test_mailgun_without_its_signing_key_fails_at_construction() -> None:
    with pytest.raises(ValidationError, match="INGEST_MAILGUN_SIGNING_KEY"):
        Settings(_env_file=None, debug=True, ingest_webhook_provider="mailgun", **REQUIRED)


def test_mailgun_with_its_signing_key_constructs_cleanly() -> None:
    settings = Settings(
        _env_file=None,
        debug=True,
        ingest_webhook_provider="mailgun",
        ingest_mailgun_signing_key="a-real-signing-key",
        **REQUIRED,
    )
    assert settings.ingest_webhook_provider == "mailgun"


@pytest.mark.parametrize(
    "provided",
    [
        {},
        {"ingest_postmark_basic_auth_user": "hookuser"},
        {"ingest_postmark_basic_auth_password": "hookpass"},
    ],
)
def test_postmark_requires_both_user_and_password(provided: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="INGEST_POSTMARK_BASIC_AUTH"):
        Settings(
            _env_file=None, debug=True, ingest_webhook_provider="postmark", **provided, **REQUIRED
        )


def test_postmark_with_both_user_and_password_constructs_cleanly() -> None:
    settings = Settings(
        _env_file=None,
        debug=True,
        ingest_webhook_provider="postmark",
        ingest_postmark_basic_auth_user="hookuser",
        ingest_postmark_basic_auth_password="hookpass",
        **REQUIRED,
    )
    assert settings.ingest_webhook_provider == "postmark"


def test_sendgrid_without_its_shared_secret_fails_at_construction() -> None:
    with pytest.raises(ValidationError, match="INGEST_SENDGRID_SHARED_SECRET"):
        Settings(_env_file=None, debug=True, ingest_webhook_provider="sendgrid", **REQUIRED)


def test_sendgrid_with_its_shared_secret_constructs_cleanly() -> None:
    settings = Settings(
        _env_file=None,
        debug=True,
        ingest_webhook_provider="sendgrid",
        ingest_sendgrid_shared_secret="topsecret",
        **REQUIRED,
    )
    assert settings.ingest_webhook_provider == "sendgrid"


def test_an_unrecognised_provider_name_fails_at_construction() -> None:
    """A typo in INGEST_WEBHOOK_PROVIDER must fail at boot, the same as a chosen
    provider missing its secret -- not silently resolve to no verifier at request time."""
    with pytest.raises(ValidationError, match="not a known provider"):
        Settings(_env_file=None, debug=True, ingest_webhook_provider="mailchimp", **REQUIRED)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """``lru_cache`` should mean a request-scoped dependency calling this repeatedly
    doesn't re-parse the environment (or re-open a dotenv file) on every call."""
    monkeypatch.setenv("DEBUG", "true")
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name.upper(), value)
    get_settings.cache_clear()
    try:
        first = get_settings()
        second = get_settings()
        assert first is second
    finally:
        get_settings.cache_clear()
