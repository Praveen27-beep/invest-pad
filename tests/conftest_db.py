"""A throwaway Postgres cluster for the database tests.

Boots a real cluster on a free port, applies the migrations, and tears it down. A real
server rather than a substitute because the things worth testing here -- the unique index,
the append-only trigger, NUMERIC(20,6) precision, JSONB -- are exactly the things a
substitute would not reproduce. A green suite against SQLite would prove the shim worked,
not the schema.

Skips cleanly when the Postgres binaries are absent, so the rest of the suite still runs
on a machine without them.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

PG_BIN_CANDIDATES = [
    "/opt/homebrew/opt/postgresql@17/bin",
    "/opt/homebrew/opt/postgresql@16/bin",
    "/usr/local/opt/postgresql@17/bin",
    "/usr/lib/postgresql/17/bin",
]

TEST_DB = "portfolio_test"


def find_pg_bin() -> Path | None:
    """Locate initdb/pg_ctl -- on PATH, or in a keg-only Homebrew prefix."""
    if shutil.which("initdb") and shutil.which("pg_ctl"):
        return Path(shutil.which("initdb")).parent
    for candidate in PG_BIN_CANDIDATES:
        path = Path(candidate)
        if (path / "initdb").exists() and (path / "pg_ctl").exists():
            return path
    return None


def free_port() -> int:
    """A port the OS says is free. Never the default 5432 -- these tests must not be able
    to reach, let alone write to, a real cluster someone has running."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _existing_server_admin_url() -> str | None:
    """Opt-in fallback for sandboxed environments with no root and therefore no
    initdb/pg_ctl on PATH (e.g. this project's own dev container has no sudo), but which
    do have an already-running Postgres server available -- this project's own
    docker-compose dev database, most commonly. Set TEST_PG_ADMIN_URL to that server's
    admin connection (a URL that can CREATE/DROP DATABASE), e.g.
    postgresql://trackr:trackr_dev@localhost:5433/postgres -- unset by default, so this
    changes nothing for any machine or CI runner that already has real binaries."""
    return os.environ.get("TEST_PG_ADMIN_URL")


@pytest.fixture(scope="session")
def pg_cluster() -> Iterator[str]:
    """Yield a libpq URL for a running throwaway cluster."""
    pg_bin = find_pg_bin()
    admin_url = _existing_server_admin_url()
    if pg_bin is None and not admin_url:
        pytest.skip("Postgres binaries not found (brew install postgresql@17)")
    try:
        import psycopg  # noqa: F401
    except ImportError:
        pytest.skip("psycopg not installed (pip install -e '.[db]')")

    if pg_bin is None:
        # Fall back to an existing server rather than booting a private cluster --
        # see _existing_server_admin_url. Still isolated: a dedicated TEST_DB database,
        # dropped and recreated fresh for this session, never the app's own `portfolio`.
        import psycopg

        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            conn.execute(f"CREATE DATABASE {TEST_DB}")
        base = admin_url.rsplit("/", 1)[0]
        url = f"{base}/{TEST_DB}"
        try:
            yield url
        finally:
            with psycopg.connect(admin_url, autocommit=True) as conn:
                conn.execute(
                    f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"
                )
        return

    data_dir = Path(tempfile.mkdtemp(prefix="portfolio-pgdata-"))
    sock_dir = Path(tempfile.mkdtemp(prefix="portfolio-pgsock-"))
    port = free_port()
    log = data_dir / "server.log"

    # LC_ALL is not optional on macOS: without a valid locale the postmaster becomes
    # multithreaded during startup and dies with a FATAL that names the locale only in a
    # hint. C is the right choice here anyway - a test cluster wants deterministic
    # collation, not whatever the developer's shell happens to be set to.
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    subprocess.run(
        [
            str(pg_bin / "initdb"), "-D", str(data_dir), "-U", "postgres", "--auth=trust",
            # Encoding must be stated explicitly. Under LC_ALL=C initdb otherwise picks
            # SQL_ASCII, and a SQL_ASCII connection hands psycopg bytes where it expects
            # str -- which surfaces far from here, as a TypeError deep in a query result.
            "--encoding=UTF8", "--lc-collate=C", "--lc-ctype=C",
        ],
        check=True, capture_output=True, env=env,
    )
    subprocess.run(
        [
            str(pg_bin / "pg_ctl"), "-D", str(data_dir), "-l", str(log), "-w", "start",
            # listen on the socket dir only; no TCP surface beyond loopback
            "-o", f"-p {port} -k {sock_dir} -c listen_addresses=127.0.0.1",
        ],
        check=True, capture_output=True, env=env,
    )

    url = f"postgresql://postgres@127.0.0.1:{port}/{TEST_DB}"
    try:
        import psycopg

        for _ in range(50):
            try:
                with psycopg.connect(
                    f"postgresql://postgres@127.0.0.1:{port}/postgres", autocommit=True
                ) as conn:
                    conn.execute(f"CREATE DATABASE {TEST_DB}")
                break
            except psycopg.OperationalError:
                time.sleep(0.1)
        else:
            pytest.skip("Postgres did not accept connections in time")

        yield url
    finally:
        subprocess.run(
            [str(pg_bin / "pg_ctl"), "-D", str(data_dir), "-m", "immediate", "-w", "stop"],
            check=False, capture_output=True, env=env,
        )
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.rmtree(sock_dir, ignore_errors=True)


@pytest.fixture()
def db(pg_cluster: str) -> Iterator[object]:
    """A migrated, empty database. Truncated between tests, not re-migrated.

    Each test gets a clean slate; re-running the migrations per test would be slow and
    would stop them from exercising the idempotency the runner promises.
    """
    import psycopg
    from app.db.migrate import migrate

    with psycopg.connect(pg_cluster) as conn:
        migrate(conn)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public' AND tablename <> 'schema_migrations'
                """
            )
            tables = [r[0] for r in cur.fetchall()]
            if tables:
                # The append-only trigger blocks DELETE but not TRUNCATE; announcing the
                # authorisation anyway keeps teardown honest about what it is doing.
                cur.execute("SET LOCAL app.erasure_authorised = 'on'")
                cur.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
        conn.commit()

        # retention_policy seeds live in the migration; TRUNCATE removed them.
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retention_policy (entity_type, retain_years, note) VALUES
                    ('audit_log', 5, 'SEBI Reg. 19 governs'),
                    ('transaction', 5, 'Advisory record'),
                    ('investor', 5, 'From first interaction')
                ON CONFLICT DO NOTHING
                """
            )
        conn.commit()
        yield conn


@pytest.fixture()
def crypto_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test secrets. Two distinct values, as in production."""
    from app.db.crypto import ENCRYPTION_KEY_ENV, PAN_PEPPER_ENV, generate_key

    monkeypatch.setenv(ENCRYPTION_KEY_ENV, generate_key())
    monkeypatch.setenv(PAN_PEPPER_ENV, "test-pepper-not-for-production")


@pytest.fixture()
def investor(db: object) -> str:
    """One investor with one account and one security, ready to receive transactions."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO investor (code, display_name) VALUES ('C001', 'Test') RETURNING id"
        )
        investor_id = str(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO account (investor_id, broker, is_advised) "
            "VALUES (%s, 'ZERODHA', true) RETURNING id",
            (investor_id,),
        )
        account_id = str(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO security (isin, symbol, exchange) "
            "VALUES ('INE153T01027', 'BLS', 'NSE') ON CONFLICT DO NOTHING"
        )
    db.commit()
    os.environ["_TEST_ACCOUNT_ID"] = account_id
    return investor_id


@pytest.fixture()
def consented_investor(db: object, investor: str) -> str:
    """The ``investor`` fixture with a live consent grant already in place -- for tests
    that exercise a consent-gated endpoint (ingestion, manual transaction entry) and
    are not themselves testing the gate's refusal path (see
    tests/test_db_compliance.py and tests/test_db_consent_router.py for that; those use
    the plain ``investor`` fixture, which deliberately has no consent, and must keep
    it that way)."""
    from app.db import consent

    consent.record_consent(db, investor, notice_version="v1", evidence_ref="test-fixture")
    return investor
