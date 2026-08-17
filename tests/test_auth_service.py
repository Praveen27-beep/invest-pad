"""app/auth/service.py -- the pieces that don't need a database connection.

Password hashing is pure. So is everything ``current_user`` does with a token that
fails before it ever reaches the session table (malformed, wrong signature, expired) --
``jwt.decode`` raises before ``repository.get_active_session_by_token_hash`` is called,
so ``conn`` is never touched on those paths and can safely be ``None`` here.

Everything that DOES need a session row (issue/verify against a real session, the
collapsed invalid-credentials error, session revocation) is in tests/test_db_auth.py,
against a real Postgres cluster, per this repo's existing db-test convention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.auth import service
from app.config import Settings

REQUIRED_SETTINGS = dict(
    database_url="postgresql://unused/for-this-suite",
    portfolio_encryption_key="unused-in-this-suite",
    portfolio_pan_pepper="unused-in-this-suite",
    jwt_secret="test-jwt-secret-not-for-production",
    # app/config.py's _validate_ingest_domain only accepts the dev placeholder domain
    # under DEBUG -- this suite is exactly that dev context.
    debug=True,
)


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None, jwt_expiry_seconds=3600, **REQUIRED_SETTINGS)


# --- password hashing ------------------------------------------------------------


def test_hash_password_round_trips() -> None:
    hashed = service.hash_password("correct horse battery staple")
    assert service.verify_password("correct horse battery staple", hashed) is True


def test_hash_password_rejects_the_wrong_password() -> None:
    hashed = service.hash_password("correct horse battery staple")
    assert service.verify_password("a completely different password", hashed) is False


def test_hash_password_salts_so_the_same_password_hashes_differently() -> None:
    a = service.hash_password("same password")
    b = service.hash_password("same password")
    assert a != b
    assert service.verify_password("same password", a) is True
    assert service.verify_password("same password", b) is True


# --- current_user: paths that fail before touching the database ------------------


def test_current_user_rejects_a_malformed_token(settings: Settings) -> None:
    with pytest.raises(service.InvalidTokenError):
        service.current_user(None, settings, "not-a-jwt-at-all")


def test_current_user_rejects_a_token_signed_with_a_different_secret(
    settings: Settings,
) -> None:
    forged = jwt.encode(
        {"sub": "someone", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "a-secret-this-service-never-configured",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(service.InvalidTokenError):
        service.current_user(None, settings, forged)


def test_current_user_rejects_an_expired_token(settings: Settings) -> None:
    expired = jwt.encode(
        {"sub": "someone", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(service.InvalidTokenError):
        service.current_user(None, settings, expired)
