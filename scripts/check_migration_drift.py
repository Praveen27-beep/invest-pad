#!/usr/bin/env python3
"""``make lint``'s migration-drift check -- run from the repo root as
``cd trackr-backend && python ../scripts/check_migration_drift.py``.

See ``app.db.migrate.check_drift`` for why this exists at all: six migrations (025
through 030) sat fully written and fully tested while a real local database silently
stayed six versions behind, because the test suite migrates its own throwaway cluster
automatically and nothing else ever compared a real database's applied versions against
the files on disk. This script is that comparison, wired into the same gate every other
architecture rule runs through.

EXIT CODES, chosen so a CI or sandbox environment with no reachable database does not
fail a gate it cannot evaluate -- the same posture ``tests/conftest_db.py`` takes for the
Postgres-backed test suite:

  0  drift-free (every migration on disk is applied), OR no ``DATABASE_URL`` configured,
     OR configured but unreachable -- SKIPPED, not passed, and printed as such.
  1  reachable, and one or more migrations on disk have not been applied. This is the
     failure this script exists to catch.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trackr-backend"))


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("checking: schema migrations match the configured database -- "
              "SKIPPED (no DATABASE_URL configured)")
        return 0

    try:
        import psycopg
    except ImportError:
        print("checking: schema migrations match the configured database -- "
              "SKIPPED (psycopg not installed)")
        return 0

    try:
        conn = psycopg.connect(database_url, connect_timeout=5)
    except Exception as exc:
        print(
            "checking: schema migrations match the configured database -- "
            f"SKIPPED (DATABASE_URL configured but unreachable: {type(exc).__name__})"
        )
        return 0

    try:
        from app.db.migrate import check_drift

        missing = check_drift(conn)
    finally:
        conn.close()

    if missing:
        print("FAIL: the configured database is missing migrations that exist on disk:")
        for name in missing:
            print(f"  {name}")
        print(
            "\nThis means code in this repository assumes a schema the database does not "
            "have -- exactly what let dividend_event stay unqueryable for six sessions "
            "while the test suite stayed green throughout. Run the migration runner "
            "against this database before trusting any other gate."
        )
        return 1

    print("checking: schema migrations match the configured database -- all applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
