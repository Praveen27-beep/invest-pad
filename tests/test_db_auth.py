"""app/auth/service.py and app/auth/repository.py, against a real cluster.

Everything here needs a real ``app_user`` / ``app_session`` row -- issuing a token,
verifying it back, the collapsed "invalid credentials" error, and session revocation.
Path-that-fail-before-touching-the-database live in tests/test_auth_service.py instead.

Session revocation is exercised by writing ``revoked_at`` directly, the same way
tests/test_db_grievance.py exercises DB-level enforcement: at the time this suite was
written, there was no ``repository.revoke_session`` / logout endpoint yet -- only the
column and ``get_active_session_by_token_hash``'s ``revoked_at IS NULL`` clause. That is
flagged separately; these tests pin the read-side behaviour that already exists.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.auth import repository, service
from app.config import Settings

pytestmark = pytest.mark.db


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        debug=True,
        database_url="postgresql://unused/for-this-suite",
        portfolio_encryption_key="unused-in-this-suite",
        portfolio_pan_pepper="unused-in-this-suite",
        jwt_secret="test-jwt-secret-not-for-production",
        jwt_expiry_seconds=3600,
    )


# --- repository, directly ---------------------------------------------------------


def test_create_user_round_trips(db) -> None:
    row = repository.create_user(db, "person@example.com", "hashed-value", "Person")
    assert row["email"] == "person@example.com"
    assert row["display_name"] == "Person"
    assert row["is_active"] is True
    assert isinstance(row["id"], str)


def test_create_user_rejects_a_duplicate_email(db) -> None:
    import psycopg

    repository.create_user(db, "dup@example.com", "hash-a")
    db.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        repository.create_user(db, "dup@example.com", "hash-b")
    db.rollback()


def test_get_user_by_email_is_none_when_absent(db) -> None:
    assert repository.get_user_by_email(db, "nobody@example.com") is None


def test_get_user_by_id_is_none_when_absent(db) -> None:
    assert repository.get_user_by_id(db, "00000000-0000-0000-0000-000000000000") is None


def test_active_session_lookup_is_none_for_an_unknown_hash(db) -> None:
    assert repository.get_active_session_by_token_hash(db, "not-a-real-hash") is None


def test_active_session_lookup_excludes_an_expired_session(db) -> None:
    user = repository.create_user(db, "expiring@example.com", "hash")
    expired = datetime.now(UTC) - timedelta(seconds=1)
    repository.create_session(db, user["id"], "token-hash-expired", expired)
    assert repository.get_active_session_by_token_hash(db, "token-hash-expired") is None


def test_active_session_lookup_excludes_a_revoked_session(db) -> None:
    user = repository.create_user(db, "revoked@example.com", "hash")
    future = datetime.now(UTC) + timedelta(hours=1)
    repository.create_session(db, user["id"], "token-hash-revoked", future)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE app_session SET revoked_at = now() WHERE session_token_hash = %s",
            ("token-hash-revoked",),
        )
    assert repository.get_active_session_by_token_hash(db, "token-hash-revoked") is None


# --- service, end to end -----------------------------------------------------------


def test_register_creates_a_user_with_a_normalised_email(db) -> None:
    user = service.register(db, " New.Person@Example.com ", "a-strong-password")
    assert user["email"] == "new.person@example.com"
    stored = repository.get_user_by_email(db, "new.person@example.com")
    assert stored is not None
    assert service.verify_password("a-strong-password", stored["password_hash"]) is True


def test_register_rejects_an_already_registered_email(db) -> None:
    service.register(db, "taken@example.com", "a-strong-password")
    with pytest.raises(service.EmailAlreadyRegisteredError):
        service.register(db, "taken@example.com", "a-different-password")


def test_login_issues_a_token_that_verifies_back_to_the_same_user(db, settings: Settings) -> None:
    registered = service.register(db, "login@example.com", "a-strong-password")
    token, expires_in, user = service.login(db, settings, "login@example.com", "a-strong-password")
    assert expires_in == settings.jwt_expiry_seconds
    assert user["id"] == registered["id"]

    current = service.current_user(db, settings, token)
    assert current["id"] == registered["id"]
    assert current["email"] == "login@example.com"


def test_login_is_case_and_whitespace_insensitive_on_email(db, settings: Settings) -> None:
    service.register(db, "case@example.com", "a-strong-password")
    _token, _expires_in, user = service.login(
        db, settings, " Case@Example.com ", "a-strong-password"
    )
    assert user["email"] == "case@example.com"


def test_wrong_email_and_wrong_password_raise_the_identical_collapsed_error(
    db, settings: Settings
) -> None:
    """service.InvalidCredentialsError's docstring: telling an attacker WHICH check
    failed is a free account-enumeration oracle, so both must produce the same error."""
    service.register(db, "real@example.com", "a-strong-password")

    with pytest.raises(service.InvalidCredentialsError) as wrong_email:
        service.login(db, settings, "nosuchperson@example.com", "irrelevant-password")
    with pytest.raises(service.InvalidCredentialsError) as wrong_password:
        service.login(db, settings, "real@example.com", "the-wrong-password")

    assert str(wrong_email.value) == str(wrong_password.value)


def test_login_rejects_a_deactivated_account_with_the_same_collapsed_error(
    db, settings: Settings
) -> None:
    user = service.register(db, "deactivated@example.com", "a-strong-password")
    with db.cursor() as cur:
        cur.execute("UPDATE app_user SET is_active = false WHERE id = %s", (user["id"],))

    with pytest.raises(service.InvalidCredentialsError) as deactivated:
        service.login(db, settings, "deactivated@example.com", "a-strong-password")
    with pytest.raises(service.InvalidCredentialsError) as wrong_password:
        service.login(db, settings, "nosuchperson@example.com", "irrelevant-password")

    assert str(deactivated.value) == str(wrong_password.value)


def test_issue_token_records_a_session_row_matching_the_token(db, settings: Settings) -> None:
    user = service.register(db, "session-row@example.com", "a-strong-password")
    token, expires_in = service.issue_token(settings, db, user["id"])
    assert expires_in == settings.jwt_expiry_seconds

    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == user["id"]

    session = repository.get_active_session_by_token_hash(db, service._hash_token(token))
    assert session is not None
    assert str(session["user_id"]) == user["id"]


def test_current_user_rejects_a_revoked_session(db, settings: Settings) -> None:
    service.register(db, "logout@example.com", "a-strong-password")
    token, _expires_in, _user = service.login(
        db, settings, "logout@example.com", "a-strong-password"
    )

    service.current_user(db, settings, token)  # valid before revocation

    token_hash = service._hash_token(token)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE app_session SET revoked_at = now() WHERE session_token_hash = %s",
            (token_hash,),
        )

    with pytest.raises(service.InvalidTokenError):
        service.current_user(db, settings, token)


def test_current_user_rejects_a_token_for_a_since_deactivated_user(db, settings: Settings) -> None:
    """The is_active check in current_user is defense in depth beyond login-time: an
    account deactivated mid-session must stop working before its token expires."""
    user = service.register(db, "later-deactivated@example.com", "a-strong-password")
    token, _expires_in, _user = service.login(
        db, settings, "later-deactivated@example.com", "a-strong-password"
    )
    service.current_user(db, settings, token)  # valid before deactivation

    with db.cursor() as cur:
        cur.execute("UPDATE app_user SET is_active = false WHERE id = %s", (user["id"],))

    with pytest.raises(service.InvalidTokenError):
        service.current_user(db, settings, token)


# --- refresh ------------------------------------------------------------------------


def expired_jwt_settings() -> Settings:
    """A token whose exp is already in the past at issue time. The session it is
    recorded under still lives its full ``session_ttl_seconds`` -- exactly the state a
    real client is in one hour after login."""
    return Settings(
        _env_file=None,
        debug=True,
        database_url="postgresql://unused/for-this-suite",
        portfolio_encryption_key="unused-in-this-suite",
        portfolio_pan_pepper="unused-in-this-suite",
        jwt_secret="test-jwt-secret-not-for-production",
        jwt_expiry_seconds=-10,
    )


def test_the_session_outlives_the_token(db, settings: Settings) -> None:
    """The premise the whole refresh flow stands on: app_session's horizon is
    ``session_ttl_seconds``, not the token's hour."""
    user = service.register(db, "horizon@example.com", "a-strong-password")
    token, _expires_in = service.issue_token(settings, db, user["id"])

    session = repository.get_active_session_by_token_hash(db, service._hash_token(token))
    assert session is not None
    remaining = session["expires_at"] - datetime.now(UTC)
    assert remaining > timedelta(seconds=settings.jwt_expiry_seconds)
    assert remaining <= timedelta(seconds=settings.session_ttl_seconds)


def test_refresh_issues_a_fresh_working_token_and_rotates_the_old_one(
    db, settings: Settings
) -> None:
    service.register(db, "rotate@example.com", "a-strong-password")
    old_token, _e, _u = service.login(db, settings, "rotate@example.com", "a-strong-password")

    new_token, expires_in, user = service.refresh(db, settings, old_token)

    assert expires_in == settings.jwt_expiry_seconds
    assert new_token != old_token
    assert user["email"] == "rotate@example.com"
    assert service.current_user(db, settings, new_token)["id"] == user["id"]
    with pytest.raises(service.InvalidTokenError):
        service.current_user(db, settings, old_token)


def test_refresh_accepts_an_expired_token_whose_session_is_alive(db, settings: Settings) -> None:
    """THE case: the JWT's hour is up -- current_user refuses it -- but the server-side
    session is still live, so the client gets back in without re-typing a password."""
    service.register(db, "expired@example.com", "a-strong-password")
    stale_settings = expired_jwt_settings()
    expired_token, _e, _u = service.login(
        db, stale_settings, "expired@example.com", "a-strong-password"
    )

    with pytest.raises(service.InvalidTokenError):
        service.current_user(db, stale_settings, expired_token)

    new_token, _e, user = service.refresh(db, settings, expired_token)
    assert user["email"] == "expired@example.com"
    assert service.current_user(db, settings, new_token)["email"] == user["email"]


def test_refresh_is_refused_once_the_session_window_itself_has_closed(
    db, settings: Settings
) -> None:
    """The grace window is the SESSION's, not infinite: expire the row and even a
    correctly signed token buys nothing."""
    service.register(db, "window@example.com", "a-strong-password")
    token, _e, _u = service.login(db, settings, "window@example.com", "a-strong-password")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE app_session SET expires_at = now() - interval '1 second' "
            "WHERE session_token_hash = %s",
            (service._hash_token(token),),
        )

    with pytest.raises(service.InvalidTokenError, match="revoked or expired"):
        service.refresh(db, settings, token)


def test_refresh_is_refused_for_a_revoked_session(db, settings: Settings) -> None:
    service.register(db, "refresh-revoked@example.com", "a-strong-password")
    token, _e, _u = service.login(db, settings, "refresh-revoked@example.com", "a-strong-password")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE app_session SET revoked_at = now() WHERE session_token_hash = %s",
            (service._hash_token(token),),
        )

    with pytest.raises(service.InvalidTokenError):
        service.refresh(db, settings, token)


def test_refresh_rejects_a_wrongly_signed_token_even_with_exp_relaxed(
    db, settings: Settings
) -> None:
    """verify_exp is the ONLY relaxation. A token that does not verify against the
    secret must fail before any session lookup, grace window or not."""
    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "exp": datetime.now(UTC)},
        "not-the-real-secret",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(service.InvalidTokenError):
        service.refresh(db, settings, forged)


def test_repository_revoke_session_stops_the_session_and_is_idempotent(
    db, settings: Settings
) -> None:
    user = repository.create_user(db, "revoke-fn@example.com", "hash")
    future = datetime.now(UTC) + timedelta(hours=1)
    session_id = repository.create_session(db, user["id"], "revoke-fn-hash", future)

    repository.revoke_session(db, session_id)
    assert repository.get_active_session_by_token_hash(db, "revoke-fn-hash") is None

    repository.revoke_session(db, session_id)  # second call changes nothing, raises nothing
