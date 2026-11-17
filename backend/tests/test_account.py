"""Deleting an account removes every row the user owns and every uploaded file."""

from pathlib import Path

from psycopg import sql

from tests.test_export import fill


def test_delete_account_removes_everything(app, new_user, owner):
    a, b = new_user(), new_user()
    fill(a, "Northgate")
    fill(b, "Kept Co")
    files = Path(app.state.config.files_dir) / str(a.user_id)
    assert any(files.iterdir())

    assert a.request("DELETE", "/auth/me", json={"password": "wrong", "confirm": "delete my account"}).status_code == 401
    assert a.request("DELETE", "/auth/me", json={"password": a.password, "confirm": "yes"}).status_code == 422
    r = a.request("DELETE", "/auth/me", json={"password": a.password, "confirm": "Delete my account"})
    assert r.status_code == 204

    tables = [t for (t,) in owner.execute(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'owner_id' "
        "AND table_name IN (SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE')")]
    for t in tables:
        n = owner.execute(sql.SQL("SELECT count(*) FROM {} WHERE owner_id = %s").format(sql.Identifier(t)),
                          (a.user_id,)).fetchone()[0]
        assert n == 0, t
    assert owner.execute("SELECT count(*) FROM app_user WHERE id = %s", (a.user_id,)).fetchone()[0] == 0
    assert not files.exists()
    assert a.get("/auth/me").status_code == 401
    # The other user is untouched.
    assert b.get("/subjects").json()[0]["name"] == "Kept Co"
    assert owner.execute("SELECT count(*) FROM document WHERE owner_id = %s", (b.user_id,)).fetchone()[0] == 1


def test_function_does_nothing_without_a_user(owner, urls):
    import psycopg
    with psycopg.connect(urls["app"], autocommit=True) as conn:
        assert conn.execute("SELECT auth_delete_self()").fetchone()[0] is False
