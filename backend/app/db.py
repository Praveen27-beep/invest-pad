"""Database access. Raw SQL, one pool, and one rule:

every query for a signed-in user runs inside `as_user(user_id)`, which sets app.user_id
for that transaction only. Row-level security does the rest. A query run without it sees
no owned rows at all.
"""

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def open_pool(database_url: str) -> None:
    global _pool
    _pool = ConnectionPool(database_url, min_size=1, max_size=10, open=True,
                           kwargs={"row_factory": dict_row})
    _pool.wait()


def close_pool() -> None:
    if _pool:
        _pool.close()


@contextmanager
def anonymous():
    """A transaction with no user. Only the auth_* functions are useful here."""
    with _pool.connection() as conn, conn.cursor() as cur:
        yield cur


@contextmanager
def as_user(user_id):
    """A transaction scoped to one user. Commits on success, rolls back on error."""
    with _pool.connection() as conn, conn.cursor() as cur:
        # set_config(..., true) is transaction-local: it cannot leak to the next request
        # that borrows this pooled connection.
        cur.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))
        yield cur
