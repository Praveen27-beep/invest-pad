# Invest-pad

Invest-pad remembers why you bought, passed, or walked away from a stock, so you don't
research it all over again.

A research and information tool. Not investment advice.

**Status:** early build. Done so far: accounts with per-user isolation enforced by the
database (M1), and the workspace (M2) — companies, notes in a block editor, a new version
on every save, `[[links]]` between notes, backlinks, and search. No documents, thesis or
AI yet. See `docs/04-roadmap.md` and `docs/HANDOFF.md`.

## Run it locally

Needs Docker.

```
cp .env.example .env        # then edit the two passwords
docker compose up --build
```

Create an invite code (in a second terminal, same folder):

```
docker compose exec api python -m app.migrate invite my-first-invite
```

Open http://localhost:3000, choose "I have an invite code", and sign up. Each invite code
works once; make one per person.

The API itself is at http://localhost:8000 (`/health`, interactive docs at `/docs`).

## Run the tests

Needs a Postgres you can create databases in.

```
cd backend
pip install -e ".[dev]"
TEST_ADMIN_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres pytest -q
ruff check .
```

## Using notes

- Add a company, open it, create a note. **Save** (or Ctrl/Cmd+S) records a new version;
  earlier versions stay readable under History.
- Link notes by typing `[[Note title]]`. The side panel shows where a note links, which
  notes link to it, and notes that mention its title without linking.
- "Copy link to this block" gives a `[[Title#^block]]` link to one paragraph.
- Renaming a note updates the links in other notes and records that in their history.
- Links are shown as plain `[[text]]` in the editor for now; use the side panel to follow them.

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
web/                 the app (Next.js); talks to the API through /api/*
e2e/                 a real-browser check of the workspace (run by hand, see the file)
docs/                plans, research, handoff
```

This branch (`invest-pad/main`) is a clean tree. The older `codex/invest-pad-ui` branch
holds an earlier prototype built on a different codebase and is not used here.
