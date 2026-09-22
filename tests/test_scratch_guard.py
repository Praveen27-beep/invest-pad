"""``app.db.scratch``: what an ad hoc script is allowed to connect to.

The failure being pinned here is the one that cannot be seen once it has happened. A
probe that connected to the real database and only read from it looks exactly like a
probe that connected to a disposable one, so "it was fine last time" carries no
information. These tests assert the refusals, and specifically assert that each guard
refuses for its OWN reason -- a test that only checks "it raised" would pass against a
guard chain where the strongest link had quietly stopped firing.

The URL-level cases need no database and run everywhere. The tag-table cases take
``pg_cluster`` and skip with the rest of the Postgres suite (see tests/conftest_db.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.db.connection import DATABASE_URL_ENV
from app.db.scratch import (
    SCRATCH_URL_ENV,
    TAG_TABLE,
    NotATestDatabaseError,
    _resolve_url,
    connect_scratch,
    tag_as_scratch,
)

REAL = "postgresql://trackr:pw@localhost:5433/portfolio"
SCRATCH = "postgresql://trackr:pw@localhost:5433/portfolio_test"


# --- guard 1: no inheritance, no fallback -------------------------------------------


def test_no_url_anywhere_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SCRATCH_URL_ENV, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(NotATestDatabaseError) as exc:
        _resolve_url(None)

    assert SCRATCH_URL_ENV in str(exc.value)


def test_a_configured_application_database_is_never_inherited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole bug in one test: DATABASE_URL is set and usable, and asking for a
    scratch connection still gets nothing."""
    monkeypatch.delenv(SCRATCH_URL_ENV, raising=False)
    monkeypatch.setenv(DATABASE_URL_ENV, REAL)

    with pytest.raises(NotATestDatabaseError):
        _resolve_url(None)


# --- guard 2: not the application's own database -------------------------------------


def test_passing_the_application_url_explicitly_still_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, REAL)

    with pytest.raises(NotATestDatabaseError) as exc:
        _resolve_url(REAL)

    assert DATABASE_URL_ENV in str(exc.value)


# --- guard 3: the name, refusal-only -------------------------------------------------


def test_a_production_shaped_name_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """And refuses on the NAME, not merely because it matched DATABASE_URL -- which is
    what makes the guard survive a script run without .env exported."""
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(NotATestDatabaseError) as exc:
        _resolve_url(REAL)

    assert "not named as disposable" in str(exc.value)


def test_a_query_string_cannot_smuggle_the_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    """``?options=-c_test`` is not a database name. Guard 3 reads the path only, so a
    URL whose real target is ``portfolio`` cannot pass by appending text after it."""
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(NotATestDatabaseError):
        _resolve_url("postgresql://h:5433/portfolio?options=-c%20search_path_test")


@pytest.mark.parametrize("name", ["portfolio_test", "probe_scratch", "x_throwaway"])
def test_the_three_disposable_suffixes_pass_the_name_guard(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    url = f"postgresql://h:5433/{name}"

    assert _resolve_url(url) == url


def test_the_environment_variable_is_used_when_no_url_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    monkeypatch.setenv(SCRATCH_URL_ENV, SCRATCH)

    assert _resolve_url(None) == SCRATCH


# --- guard 4/5: the in-database tag, the only vouching step --------------------------


def _drop_tag(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {TAG_TABLE}")


def test_an_untagged_disposable_database_still_refuses(
    pg_cluster: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named right, reachable, and refused anyway. This is rule 10 of
    ARCHITECTURE_INVARIANTS applied to a connection: the name rejects, it never vouches."""
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    _drop_tag(pg_cluster)

    with pytest.raises(NotATestDatabaseError) as exc:
        with connect_scratch("probe with no tag", url=pg_cluster):
            pass

    assert TAG_TABLE in str(exc.value)
    assert "python -m app.db.scratch --tag" in str(exc.value)


def test_a_tagged_database_connects_and_commits(
    pg_cluster: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    tagged = tag_as_scratch(pg_cluster, note="test_scratch_guard's own probe")

    assert tagged == "portfolio_test"
    with connect_scratch("read one row", url=pg_cluster) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1


def test_a_truncated_tag_is_not_a_tag(pg_cluster: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The tag table lives in the same schema tests/conftest_db.py truncates between
    tests, so an empty-but-present table is a state that really occurs."""
    import psycopg

    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    tag_as_scratch(pg_cluster, note="about to be truncated")
    with psycopg.connect(pg_cluster, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {TAG_TABLE}")

    with pytest.raises(NotATestDatabaseError) as exc:
        with connect_scratch("probe against an emptied tag", url=pg_cluster):
            pass

    assert "empty" in str(exc.value)


def test_a_tag_written_for_a_different_database_refuses(
    pg_cluster: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard 5. A pg_dump of a tagged scratch database carries this row into whatever it
    is restored over, which would otherwise hand the restored database a tag nobody
    granted it."""
    import psycopg

    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    tag_as_scratch(pg_cluster, note="tagged here, then claimed elsewhere")
    with psycopg.connect(pg_cluster, autocommit=True) as conn:
        conn.execute(f"UPDATE {TAG_TABLE} SET database_name = 'some_other_scratch'")

    with pytest.raises(NotATestDatabaseError) as exc:
        with connect_scratch("probe on a travelled tag", url=pg_cluster):
            pass

    assert "some_other_scratch" in str(exc.value)


def test_tagging_refuses_the_configured_application_database(
    pg_cluster: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The obvious way to defeat guard 4 is to tag production so the script stops
    complaining. Tagging runs guards 2 and 3 first, so that attempt fails before any
    table is created."""
    monkeypatch.setenv(DATABASE_URL_ENV, pg_cluster)

    with pytest.raises(NotATestDatabaseError):
        tag_as_scratch(pg_cluster, note="this should never be written")


def test_a_tag_needs_a_note(pg_cluster: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    with pytest.raises(ValueError):
        tag_as_scratch(pg_cluster, note="   ")


# --- the guard cannot be migrated into existence ------------------------------------


def test_the_tag_table_appears_in_no_migration() -> None:
    """Guard 4 works only because the real database does not have this table. A
    migration creating it would put the tag everywhere and disarm the one check that
    proves anything -- so the absence is asserted, not just intended."""
    migrations = Path(__file__).resolve().parent.parent / "trackr-backend/app/db/migrations"
    offenders = [p.name for p in sorted(migrations.glob("*.sql")) if TAG_TABLE in p.read_text()]

    assert offenders == [], f"{TAG_TABLE} must never be migrated: {offenders}"
