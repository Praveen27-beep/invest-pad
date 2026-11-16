"""Test setup: a fresh database per test session, migrated the same way production is.

Needs a Postgres it can create databases in:
    TEST_ADMIN_URL=postgresql://postgres@127.0.0.1:5432/postgres   (the default)
"""

import os
import secrets

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://postgres:postgres@127.0.0.1:5432/postgres")
APP_PASSWORD = "test-app-password"  # noqa: S105 - throwaway database


def _swap_db(url: str, name: str, user: str | None = None, password: str | None = None) -> str:
    info = psycopg.conninfo.conninfo_to_dict(url)
    info["dbname"] = name
    if user:
        info["user"], info["password"] = user, password
    return psycopg.conninfo.make_conninfo(**info)


@pytest.fixture(scope="session")
def urls():
    from app.migrate import migrate

    name = "investpad_test_" + secrets.token_hex(4)
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    owner = _swap_db(ADMIN_URL, name)
    migrate(owner, APP_PASSWORD)
    yield {"owner": owner, "app": _swap_db(ADMIN_URL, name, "investpad_app", APP_PASSWORD)}
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="session")
def app(urls):
    import tempfile
    os.environ.update(DATABASE_URL=urls["app"], COOKIE_SECURE="false", ALLOWED_ORIGINS="http://localhost:3000",
                      FILES_DIR=tempfile.mkdtemp(prefix="investpad-files-"), MAX_UPLOAD_MB="2")
    from app.main import app as fastapi_app
    with TestClient(fastapi_app):  # runs startup and shutdown
        yield fastapi_app


@pytest.fixture
def owner(urls):
    """A connection as the migration owner, for arranging and inspecting state."""
    with psycopg.connect(urls["owner"], autocommit=True) as conn:
        yield conn


@pytest.fixture
def new_user(app, owner):
    """Returns a function that signs up a fresh user and gives back a logged-in client."""
    def make(password: str = "correct horse battery"):
        invite = secrets.token_hex(8)
        owner.execute("INSERT INTO invite (code) VALUES (%s)", (invite,))
        client = TestClient(app)
        email = f"user-{secrets.token_hex(4)}@example.com"
        r = client.post("/auth/signup", json={"email": email, "password": password, "invite": invite})
        assert r.status_code == 201, r.text
        client.email, client.user_id, client.password = email, r.json()["id"], password
        return client
    return make
