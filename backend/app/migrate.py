"""Apply numbered .sql migrations, in order, once each.

    python -m app.migrate                 apply pending migrations
    python -m app.migrate invite CODE     create an invite code

Connects with MIGRATE_DATABASE_URL (the owner role). Creates the API role
`investpad_app` with APP_DB_PASSWORD if it does not exist yet.
"""

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def migrate(owner_url: str, app_password: str) -> list[str]:
    applied = []
    with psycopg.connect(owner_url, autocommit=True) as conn:
        # Roles are cluster-wide, so "create if missing" and always set the password.
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'investpad_app'").fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(sql.SQL(
            "{} ROLE investpad_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}"
        ).format(sql.SQL(verb), sql.Literal(app_password)))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migration "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT name FROM schema_migration")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():  # a failed migration leaves nothing behind
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


def main() -> None:
    owner_url = os.environ["MIGRATE_DATABASE_URL"]
    if len(sys.argv) == 3 and sys.argv[1] == "invite":
        with psycopg.connect(owner_url, autocommit=True) as conn:
            conn.execute("INSERT INTO invite (code) VALUES (%s)", (sys.argv[2],))
        print(f"invite created: {sys.argv[2]}")
        return
    applied = migrate(owner_url, os.environ["APP_DB_PASSWORD"])
    print("applied:", ", ".join(applied) if applied else "nothing to do")


if __name__ == "__main__":
    main()
