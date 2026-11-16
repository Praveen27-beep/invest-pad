# HANDOFF

Last updated: 16 Nov 2026, session 1 (Phases 0–2 done; Phase 3 M1 and M2 done).

Branches (both pushed):
- `invest-pad/main` — the build. Clean tree, no Trackr+ files. Planning docs live here too.
- `invest-pad/planning` — the Phase 0–2 docs on top of the old prototype branch (history only).

## Done

- Phase 0: `docs/00-inventory.md`.
- Phase 1: `docs/01-landscape.md`, `docs/06-data-sources.md`.
- Phase 2: `docs/02-product-spec.md`, `docs/03-architecture.md`, `docs/04-roadmap.md`,
  `docs/05-eval-plan.md`.

## M1 Foundation — done

- FastAPI + raw SQL; `backend/migrations/001_foundation.sql`; `python -m app.migrate`.
- Sign-up with single-use invite codes, login, logout, server-side sessions (argon2;
  only a hash of the session token is stored), login rate limit, cross-site write check.
- Isolation: API role `investpad_app` has no special powers and no direct access to
  account tables; every owned table has forced row-level security keyed on a
  transaction-local user id. First owned tables: `subject` (company), `audit_log`.
- Request log: one line per request, no bodies, query strings, headers or cookies.
- 29 tests pass locally against Postgres 16; ruff clean. Tests cover the HTTP layer, the
  database layer (what the API role can do directly), a guard that fails if any table
  with `owner_id` lacks a policy, and a planted-secret search of the logs.
- CI workflow added (`.github/workflows/ci.yml`).

**Not verified:** `docker compose up` was not run — this environment has no Docker
daemon. The server was run directly with uvicorn and exercised end to end instead.
First thing to check on a real machine.

## M2 Workspace — done

- `backend/migrations/002_workspace.sql`, `backend/app/notes.py`: notes with append-only
  versions (the API role cannot edit or delete a version), `[[Title]]`,
  `[[Title|text]]` and `[[Title#^block]]` links, linked backlinks with their surrounding
  text, unlinked mentions, rename that retargets links in other notes and records why,
  keyword search with highlights, owner delete that removes versions and links.
- **Isolation hole found and closed:** foreign-key checks ignore row-level security, so a
  user could have attached a note to another user's company by id. Every reference
  between owned tables now includes `owner_id`, and a test enforces that for future tables.
- `web/`: Next.js app — sign in / sign up, companies, company page, note page with the
  BlockNote editor (MPL-2.0 core packages only) and a side panel for links, backlinks,
  mentions and history, search page. Calls the API through a same-origin `/api` proxy.
- Tests: 47 backend tests; `e2e/workspace.py` passes in real Chrome (sign-up → company →
  linked notes → backlinks → rename → history → search → sign-out). The e2e script is run
  by hand, not in CI yet.

**Known limits:** links are plain `[[text]]` inside the editor (followed from the side
panel, not by clicking in the text); history shows a version's text, not a visual diff
(diffs arrive with the thesis in M5); no autosave — Save creates the version.

## Checkpoint 1 — one-page summary

**Landscape.** Analysis is crowded (Investi in the US; Screener AI, Multibagg AI,
Trendlyne in India). Memory of the investor's own reasoning is thinly served. Closest in
shape: TradeClips (extension + ticker page + thesis + cited chat), then Stockxy,
StockGeniuses, Folyo's unfinished Workbook. No Indian product found that keeps the user's
own versioned thesis.

**Wedge.** A dated, cited, versioned record of one investor's reasoning, handed back when
they reopen the company. No scores, no AI-written thesis.

**Honest risk.** "NotebookLM plus a folder" is good enough for reading reports. The
product only works if testers return weekly to write.

**Borrow.** Notion: blocks, slash menu, fixed views and counters. Obsidian: wikilinks,
block links, linked and unlinked backlinks, plain-file export. Skip: generic databases,
graph view, plugin system.

**Build vs adopt.** Adopt an editor library (Tiptap, MIT, or BlockNote core, MPL-2.0 —
avoid its GPL `xl-*` packages). Do not fork any second-brain app: Khoj, Obsidian Copilot,
AppFlowy, SiYuan, Logseq are AGPL; Outline is BSL. Open Notebook (MIT) is worth reading
for its multi-provider adapter.

**Data sources.** MVP is uploads, notes and pasted pages, private per user, no shared
corpus. Zip Filings plugs in first as "download ZIP, upload ZIP". Screener's terms rule it
out as a source. NSE/BSE terms unverified; NSE Data portals require written consent to
redistribute.

## Checkpoint 2 — summary

**Spec.** The success test is met by structure, not by AI: the decisive reason is a
required field written at decision time, shown first when a company is reopened. It must
pass with the AI switched off. Core objects are domain-neutral; investing is a pack.

**Architecture.** One FastAPI service, one worker, Postgres + pgvector, Next.js, MV3
extension. Raw SQL migrations. Isolation by Postgres row-level security. Job queue is a
Postgres table. One OpenAI-compatible model adapter. No Redis, Celery or agent framework.

**Hosts (read 16 Nov 2026).** V4.1 Flash is $0.30/$1.20 per 1M tokens on Together and
Fireworks, less on DeepInfra. Only Together states a region (US processing, +25%), and it
stores prompts unless zero-retention is switched on. DeepInfra and Fireworks do not store
open-model prompts by default but state no region on the pages read.

**Caps.** With assumed token sizes, a typical question costs about $0.005–0.006 on Flash;
$2 buys roughly 317. Pro is about four times dearer; proposed as own-key only.

**Roadmap.** MVP M1–M6 estimated at 29 build days (rough). **Eval.** 50 question
templates in eight groups; synthetic corpus for CI, real IEX corpus kept local.

## Decisions made by Parasu (16 Nov 2026)

- Build on a separate branch inside `invest-pad`; leave `codex/invest-pad-ui` untouched.
- Repo stays public until the MVP is built.
- `BEXPD1234F` in tests is not a real PAN.

## Assumed, please confirm

- Demo company: IEX. Notes received 16 Nov 2026 (three drafts, ~23,000 words) and kept
  **outside the repo** because it is public. They are drafts, not a clean thesis; the
  decision and decisive reason will need Parasu's confirmation when loaded in M5.
- Owner delete = hard delete with cascade; all other history append-only.
- Question-first ritual is an investing-template default, not a core rule; the AI may
  answer queued questions from the user's own corpus.
- MCP later; scheduled agents use uploads, notes, pasted pages and web/news only.
- Raw SQL + numbered migrations (Trackr+ style); pgvector added behind an eval.
- Floating notepad = Chrome side panel opened by shortcut, plus optional in-page button.
- Editor: BlockNote core unless Phase 2 finds a blocker; Tiptap as fallback.
- Build branch will be a clean tree (orphan branch `invest-pad/main`), not the Trackr+ files.
- Default model DeepSeek V4.1 Flash on platform credit; V4 Pro on the user's own key.
- Host chosen after written region confirmation; fallback Together US-pinned + zero retention.
- Local embedding model; hybrid search ships only if the eval shows it beats keyword-only.
- One thesis per company per user; decision types as listed in `02-product-spec.md` §9.

## Next

1. M3 Capture: MV3 extension with side panel, capture-only tokens, inbox in the app.
2. Then M4–M6 in order; `docs/MVP-REPORT.md` before M7.

## Not done / not verified

- Desktop "investing space" folder never inspected; unpushed local changes unknown.
- `docker compose up` not run (no Docker daemon in the build environment).
- Backend test suite not re-run.
- AlphaNote not found; several pricing pages not opened; ChatGPT Projects behaviour not
  verified (see `01-landscape.md` §7).
- NSE and BSE website terms not retrieved.

## Things only Parasu can do

- Run `docker compose up --build` once on your machine and report any error.
- Supply the DuPont skill; send the AlphaNote link.
- Provide a model API key and spending limit before the first paid eval run (stop condition).
- Ask DeepInfra and Fireworks, in writing, where inference runs.
- Read and query NSE/BSE terms (questions listed in `06-data-sources.md` §3).
- Lawyer review: SEBI position on an IA operating this tool; privacy policy and terms
  before analyst friends get accounts; storing captured web pages.

## Open questions

- Are Mei Capital references acceptable in a public Invest-pad repo?
- Keep the PVR INOX pilot as a second demo?
