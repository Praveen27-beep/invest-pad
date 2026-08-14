"""Migration runner -- numbered .sql files, applied in order, recorded once.

Deliberately not an ORM migration framework. Six tables do not need one, and keeping the
DDL as plain SQL is what lets a Go or Node implementation read the same schema. See
``docs/ARCHITECTURE.md`` on swapping the stack.

Migrations are FORWARD-ONLY. There is no downgrade path, because a downgrade that drops a
column holding client data is not a thing anyone should be able to run by accident.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

#: 001_core.sql -> version 1
VERSION_PATTERN = re.compile(r"^(\d+)_.*\.sql$")

BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     integer PRIMARY KEY,
    filename    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def discover(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """Every migration on disk, in version order.

    Raises:
        ValueError: two files claim the same version. Ambiguous ordering is worse than
            no ordering, because it applies differently on different machines.
    """
    found: dict[int, Path] = {}
    for path in sorted(directory.glob("*.sql")):
        match = VERSION_PATTERN.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in found:
            raise ValueError(f"duplicate migration version {version}: {found[version]}, {path}")
        found[version] = path
    return sorted(found.items())


def applied_versions(conn: Any) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(BOOTSTRAP)
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def migrate(conn: Any, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every unapplied migration. Returns the filenames applied.

    Idempotent: running twice applies nothing the second time. Each migration runs inside
    the caller's transaction, so a failure part-way leaves the schema untouched rather
    than half-built.
    """
    already = applied_versions(conn)
    applied: list[str] = []

    for version, path in discover(directory):
        if version in already:
            continue
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute(
                "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s)",
                (version, path.name),
            )
        applied.append(path.name)

    return applied
