# Backups

Local Postgres dumps, taken before a schema change touches a database holding real
account data. Dumps never enter git — the same DPDP reasoning `.gitignore` states for
client documents applies to a full database export, only more so. This file is the
record of what exists and where, since nothing else in the repository tracks it.

## Log

| Date | File | Database | Why | Restore-verified |
|---|---|---|---|---|
| 2026-09-24 | `~/trackr-backups/portfolio-pre-migration-20260924-193403.dump` | `portfolio` (local dev, `postgresql://localhost/portfolio`) | Before applying migrations 032/033/034. `PRAVEEND-4335` — a real, claimed investor account with 324 transactions spanning 2022-10-19 onward — lives in this database, not test fixtures. | Yes. Restored into a disposable scratch database (`trackr_backup_verify`); every table's row count matched the live database exactly (investor 4, account 5, transaction 643, document 6, price 389, security 62). Scratch database dropped after verification. |

## How this dump was taken and verified

```bash
pg_dump -Fc -f ~/trackr-backups/portfolio-pre-migration-<timestamp>.dump \
    postgresql://localhost/portfolio
```

`-Fc` (custom format): compressed, and restorable with `pg_restore` independently of the
original database — not a raw SQL stream that only proves it *executed*, not that its
DDL still matches a live schema.

Before trusting a dump, restore it somewhere disposable and compare row counts against
the source — a dump that ran without error is not the same claim as a dump that restores
correctly:

```bash
psql postgresql://localhost/postgres -c "CREATE DATABASE trackr_backup_verify;"
pg_restore -d postgresql://localhost/trackr_backup_verify <dump file>
# compare row counts per table against the source database
psql postgresql://localhost/postgres -c "DROP DATABASE trackr_backup_verify;"
```

`pg_dump`/`pg_restore` and the server version should match exactly (`pg_dump --version`
vs. `SHOW server_version`) — a version mismatch is the kind of gap that surfaces only
when the restore is actually needed, which is the worst time to find it.

## When to take one

Before any migration that is not purely additive (a new table, a new nullable column) —
in particular before anything using `ALTER TYPE ... ADD VALUE`, which PostgreSQL cannot
reverse (there is no `DROP VALUE`), or any `ALTER`/`DROP` touching an existing column.
See `docs/ARCHITECTURE_INVARIANTS.md`'s "Future work" section for `033_funds_statement_source.sql`
as a worked example of a migration held deliberately unapplied for exactly this reason.

`app.db.migrate.migrate()` runs each migration inside the caller's transaction, so a
failure *during* one migration cannot leave the schema half-built. A backup protects
against a different risk: a migration that succeeds but does something you did not
intend, or needing to return to the pre-migration schema after the fact.
