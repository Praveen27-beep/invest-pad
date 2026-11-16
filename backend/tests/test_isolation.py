"""Tenant isolation. These tests are the reason the foundation exists.

Two layers are checked: the HTTP API (what a user can do) and the database itself (what
the API's role can do even if the application code had a bug).
"""

import psycopg
import pytest


def test_user_b_cannot_see_or_touch_user_a_data(new_user):
    a, b = new_user(), new_user()
    subject = a.post("/subjects", json={"name": "IEX", "identifiers": {"isin": "INE022Q01020"}}).json()

    assert [s["name"] for s in a.get("/subjects").json()] == ["IEX"]
    assert b.get("/subjects").json() == []
    assert b.get(f"/subjects/{subject['id']}").status_code == 404
    assert b.delete(f"/subjects/{subject['id']}").status_code == 404
    assert a.get(f"/subjects/{subject['id']}").status_code == 200  # still there

    # Names are unique per user, not globally: B's "IEX" is B's own.
    assert b.post("/subjects", json={"name": "IEX"}).status_code == 201
    assert a.post("/subjects", json={"name": "IEX"}).status_code == 409
    assert len(a.get("/subjects").json()) == len(b.get("/subjects").json()) == 1


def test_signed_out_requests_get_nothing(app, new_user):
    from fastapi.testclient import TestClient
    a = new_user()
    sid = a.post("/subjects", json={"name": "Private"}).json()["id"]
    anon = TestClient(app)
    assert anon.get("/subjects").status_code == 401
    assert anon.get(f"/subjects/{sid}").status_code == 401
    assert anon.post("/subjects", json={"name": "x"}).status_code == 401


def test_deleting_own_subject_works_and_is_audited(new_user, owner):
    a = new_user()
    sid = a.post("/subjects", json={"name": "Temp"}).json()["id"]
    assert a.delete(f"/subjects/{sid}").status_code == 204
    assert a.get("/subjects").json() == []
    actions = [r[0] for r in owner.execute(
        "SELECT action FROM audit_log WHERE owner_id = %s ORDER BY id", (a.user_id,))]
    assert actions == ["subject.create", "subject.delete"]


# ------------------------------------------------------------ the database layer

@pytest.fixture
def as_app(urls):
    with psycopg.connect(urls["app"]) as conn:
        yield conn


def test_api_role_without_a_user_sees_no_rows(new_user, as_app):
    new_user().post("/subjects", json={"name": "Hidden"})
    assert as_app.execute("SELECT count(*) FROM subject").fetchone()[0] == 0
    assert as_app.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 0


def test_api_role_cannot_write_rows_for_another_user(new_user, as_app):
    a, b = new_user(), new_user()
    as_app.execute("SELECT set_config('app.user_id', %s, true)", (a.user_id,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # row-level security violation
        as_app.execute("INSERT INTO subject (owner_id, name) VALUES (%s, 'forged')", (b.user_id,))


def test_api_role_cannot_move_a_row_to_another_user(new_user, as_app):
    a, b = new_user(), new_user()
    a.post("/subjects", json={"name": "Mine"})
    as_app.execute("SELECT set_config('app.user_id', %s, true)", (a.user_id,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app.execute("UPDATE subject SET owner_id = %s", (b.user_id,))


@pytest.mark.parametrize("statement", [
    "SELECT * FROM app_user",
    "SELECT * FROM session",
    "SELECT * FROM invite",
    "INSERT INTO invite (code) VALUES ('self-service')",
    "UPDATE audit_log SET action = 'rewritten'",
    "DELETE FROM audit_log",
    "ALTER TABLE subject DISABLE ROW LEVEL SECURITY",
    "SELECT enable_owner_isolation('subject')",
])
def test_api_role_is_denied(as_app, statement):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app.execute(statement)


def test_the_user_setting_does_not_outlive_its_transaction(new_user, as_app):
    a = new_user()
    a.post("/subjects", json={"name": "Scoped"})
    as_app.execute("SELECT set_config('app.user_id', %s, true)", (a.user_id,))
    assert as_app.execute("SELECT count(*) FROM subject").fetchone()[0] == 1
    as_app.commit()
    assert as_app.execute("SELECT count(*) FROM subject").fetchone()[0] == 0


# ------------------------------------------------------------ schema guards

def test_every_owned_table_is_isolated(owner):
    """Fails the build if anyone adds a table with owner_id and forgets the policy."""
    rows = owner.execute("""
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
        FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'owner_id' AND NOT a.attisdropped
        WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
    """).fetchall()
    assert {r[0] for r in rows} >= {"subject", "audit_log"}
    unprotected = [name for name, rls, forced, policies in rows if not (rls and forced and policies)]
    assert unprotected == []


def test_references_between_owned_tables_include_the_owner(owner):
    """A foreign key from one owned table to another must carry owner_id.

    Foreign-key checks bypass row-level security, so without owner_id in the key a user
    could attach their row to someone else's. References to app_user are exempt: that is
    the owner column itself.
    """
    rows = owner.execute("""
        SELECT con.conrelid::regclass::text, con.confrelid::regclass::text, con.conname,
               EXISTS (SELECT 1 FROM unnest(con.conkey) k
                       JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k
                       WHERE a.attname = 'owner_id')
        FROM pg_constraint con
        WHERE con.contype = 'f'
          AND con.confrelid <> 'app_user'::regclass
          AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = con.conrelid AND a.attname = 'owner_id')
          AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = con.confrelid AND a.attname = 'owner_id')
    """).fetchall()
    assert len(rows) >= 3
    assert [r[:3] for r in rows if not r[3]] == []


def test_api_role_has_no_special_powers(owner):
    row = owner.execute(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = 'investpad_app'"
    ).fetchone()
    assert row == (False, False, False, False)


def test_migrations_are_idempotent(urls):
    from app.migrate import migrate
    from tests.conftest import APP_PASSWORD
    assert migrate(urls["owner"], APP_PASSWORD) == []
