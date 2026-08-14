"""Database connections.

Thin on purpose. The system is defined by ``contracts/openapi.yaml``,
``schema/*.schema.json`` and ``fixtures/*.json``; Postgres is the reference store, not the
specification. Keeping this to a connection factory is what leaves the stack swappable.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

#: Standard libpq URL. No default: a silent fallback to localhost is how a test run ends
#: up writing to something real.
DATABASE_URL_ENV = "DATABASE_URL"


class DatabaseNotConfiguredError(RuntimeError):
    """No connection string. Raised rather than guessed at."""


def database_url() -> str:
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        raise DatabaseNotConfiguredError(
            f"{DATABASE_URL_ENV} is not set. Refusing to guess a connection string: "
            "defaulting to localhost is how a test run ends up writing to production."
        )
    return url


@contextmanager
def connect(url: str | None = None) -> Iterator[Any]:
    """Yield a connection, committing on success and rolling back on any exception.

    All-or-nothing is the point. A mutation and its audit row share one transaction, so a
    failure that loses the audit must lose the mutation too.
    """
    import psycopg

    conn = psycopg.connect(url or database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
