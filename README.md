# Invest-pad

Invest-pad remembers why you bought, passed, or walked away from a stock, so you don't
research it all over again.

A research and information tool. Not investment advice.

**Status:** early build, milestones M1–M5 of six before the first usable version.

Works today:

- accounts, with each person's data isolated by the database;
- notes in a block editor, a new version on every save, `[[links]]`, backlinks, search;
- a Chrome notepad that sends notes and questions to an inbox;
- documents: upload PDF, Excel or Word, read page by page, search passages by company,
  period and type;
- a thesis per company with versions and diffs, assumptions, evidence for and against
  (a fact must cite a passage; your opinion is kept separate), a decision journal, a
  red-flag checklist, and a first screen that shows your last decision and the reason
  for it when you come back.

Not built yet: anything that calls an AI model (the question queue is M6), scheduled
routines, export. See `docs/04-roadmap.md` and `docs/HANDOFF.md`.

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

## Documents, thesis and decisions

- **Documents tab:** upload a file. Type and period are guessed from the file name
  (`IEX Q4FY26 concall.pdf` → concall, Q4 FY26) and can be corrected. Scanned PDFs with
  no text layer are reported as such; text recognition is not built.
- **Thesis tab:** write the thesis, add the assumptions it rests on, and record changes
  to an assumption's state with a reason. Nothing saved is edited; changes add versions.
- **Evidence:** open a document, pick a passage, choose "Use as evidence". That is a
  fact, shown with its source and page. Your own view goes in as an opinion.
- **Decisions:** record what you did and the one reason that decided it. A journal entry
  cannot be edited.
- **Overview tab:** the first thing you see on reopening a company — the last decision,
  the reason in your words, what it rested on and how that stands now, open questions,
  and what has changed since.
- **Deleting a document** removes its file, text and passages. Evidence that cited it
  stays as your own words and is no longer shown as a fact.

## The browser extension

A notepad in Chrome's side panel for jotting a note or a question about the page you are
reading. It lands in your Inbox.

1. Open `chrome://extensions`, switch on **Developer mode**, click **Load unpacked**, and
   choose the `extension` folder of this repository.
2. In Invest-pad, open **Settings**, create a token, and copy it.
3. Click the Invest-pad toolbar button (or press Alt+Shift+I). Enter the address
   (`http://localhost:3000`) and the token, and allow access when Chrome asks.

Then: open the notepad on any page, or select text, right-click and choose **Add to
Invest-pad**. The page's title, address and your selected text are attached; you can
remove them before saving. If Invest-pad is unreachable, what you write is kept in the
browser and sent later.

What the extension can and cannot do:

- It reads a page only at the moment you open the notepad on it or use the right-click
  menu. It runs nothing in the background on other pages.
- Its token can add captures and read your company names. It cannot read notes.
- It talks only to the one address you connect it to.

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
extension/           the Chrome notepad (Manifest V3, no build step)
e2e/                 real-browser checks (run by hand; see each file)
docs/                plans, research, handoff
```

This branch (`invest-pad/main`) is a clean tree. The older `codex/invest-pad-ui` branch
holds an earlier prototype built on a different codebase and is not used here.
