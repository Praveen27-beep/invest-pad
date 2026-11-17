# Deploying Invest-pad (preparation only)

Nothing has been deployed. Hosting accounts, the domain and DNS are Parasu's to create;
this file lists what a deployment needs so that step is quick. Never on meicapital.in.

## What runs

| Service | What | Needs |
|---|---|---|
| `db` | Postgres 16 (pgvector image) | A persistent volume; daily backups |
| `api` | FastAPI (`backend/`), runs migrations on start | `DATABASE_URL`, `MIGRATE_DATABASE_URL`, `APP_DB_PASSWORD`, `FILES_DIR` on a persistent volume, `SECRET_KEY` |
| `web` | Next.js (`web/`), proxies `/api/*` to the API | `API_URL` **at build time** |

One API process (rate limits are held in memory; see `backend/app/ratelimit.py`).

## Settings to set in production

- `SECRET_KEY`: 32-byte urlsafe base64 (Fernet). Encrypts stored model keys. If unset, one
  is created in `FILES_DIR/.secret_key`. Losing it makes stored keys unreadable (users
  re-enter them); leaking it exposes them. Keep it out of the repo.
- `COOKIE_SECURE=true` and HTTPS in front of `web`.
- `ALLOWED_ORIGINS=https://<your domain>` (cross-site write check).
- `MAX_UPLOAD_MB` (default 40), `TASK_COST_CAP_USD` (0.25), `MONTHLY_CREDIT_USD` (2).
- Optional included model: `PLATFORM_MODEL_URL`, `PLATFORM_MODEL_NAME`, `PLATFORM_MODEL_KEY`,
  prices. Leave unset to require users' own keys (no platform spend).

## Before inviting anyone

1. `docker compose up --build` on the target and run `e2e/workspace.py` and
   `e2e/thesis.py` against it.
2. Backups: schedule `scripts/backup.sh`; restore once into a scratch stack with
   `scripts/restore.sh` and sign in. (The scripts are written for docker compose and
   have not been run under Docker yet; the dump/restore step itself was checked against
   Postgres 16 with row security intact.)
3. Privacy policy and terms: `docs/legal/*-DRAFT.md` reviewed by a lawyer, then published.
4. Create invites: `docker compose exec api python -m app.migrate invite <code>`.
5. Chrome extension: set the server address in the side panel; Web Store publishing is a
   separate step (Parasu's account).
