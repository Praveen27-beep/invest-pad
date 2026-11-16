# Invest-pad

Invest-pad remembers why you bought, passed, or walked away from a stock, so you don't
research it all over again.

A research and information tool. Not investment advice.

**Status:** early build. Milestone M1 (foundation) is done: accounts, sessions, and
per-user data isolation enforced by the database. There is no user interface yet — that
starts in M2. See `docs/04-roadmap.md` and `docs/HANDOFF.md`.

## Run it locally

Needs Docker.

```
cp .env.example .env        # then edit the two passwords
docker compose up --build
```

The API is at http://localhost:8000 (`/health`, interactive docs at `/docs`).

Create an invite code, then sign up with it:

```
docker compose exec api python -m app.migrate invite my-first-invite
curl -c cookies.txt -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a long password","invite":"my-first-invite"}' \
  http://localhost:8000/auth/signup
curl -b cookies.txt http://localhost:8000/auth/me
```

## Run the tests

Needs a Postgres you can create databases in.

```
cd backend
pip install -e ".[dev]"
TEST_ADMIN_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres pytest -q
ruff check .
```

## How isolation works

- The API connects as `investpad_app`, a role with no special powers.
- Every table that holds user data has an `owner_id` and a row-level-security policy.
- Each request sets the signed-in user's id on its database transaction; the database
  returns only that user's rows. With no user set, it returns none.
- A test fails the build if any table with `owner_id` lacks a policy.

## Layout

```
backend/app/         API (FastAPI, raw SQL)
backend/migrations/  numbered .sql files, applied in order
backend/tests/
docs/                plans, research, handoff
```

This branch (`invest-pad/main`) is a clean tree. The older `codex/invest-pad-ui` branch
holds an earlier prototype built on a different codebase and is not used here.
