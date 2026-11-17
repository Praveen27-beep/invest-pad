# HANDOFF

Last updated: 17 Nov 2026, session 2 (M7 done; most of M8–M9 done; see `docs/MVP-REPORT.md`
for the state of things and `docs/REMAINING.md` for what is left).

## Session 2 (17 Nov 2026), on `invest-pad/m8-export`, merged to `invest-pad/main`

- Full export ZIP (`GET /export`) and company Markdown export; Settings button.
- Delete audit: deleting a document, note or company leaves no copy of its text in any
  column of any owned table (008); account deletion (011).
- Calculations with formulas (`app/calc.py`, Numbers tab).
- Contradiction scan (`app/scan.py`, 009): suggestions only; user accepts or dismisses.
- Editable checklists + forensic checklist (010).
- Workspace Connections page, decision Journal, review badge (`/review/status`).
- Hardening: rate limits, prompt-tag fencing, injection and cross-tenant tests.
- Read-only MCP server (`app/mcp.py`).
- Backup/restore scripts, getting-started guide, eval runner (`backend/eval/`).
- Docs: `DEPLOY.md`, `DEMO.md`, `MVP-REPORT.md`, `legal/*-DRAFT.md` (for lawyer review).

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

## M3 Capture — done

- `backend/migrations/003_capture.sql`, `backend/app/capture.py`: extension tokens (shown
  once, stored as a hash, revocable, capture-only), `/ext/captures` and `/ext/subjects`
  for the extension, and the inbox: assign a company, turn a capture into a note (keeps
  the selection and source), dismiss, restore, delete. Retried captures do not duplicate.
- `extension/`: Manifest V3, plain JavaScript, no build step. Side-panel notepad opened
  by toolbar button, Alt+Shift+I, or the right-click menu. Captures go to a local queue
  first and are sent when Invest-pad is reachable. Permissions: sidePanel, storage,
  contextMenus, activeTab, scripting; access to the Invest-pad address is asked for when
  connecting; no blanket access to sites.
- `web/`: Inbox and Settings pages.
- Tests: 57 backend tests; 8 extension unit tests (queue logic); `e2e/capture.py` loads
  the real extension in Chrome and passes (connect, wrong token, save with page context,
  offline then resend, inbox, make a note, revoke).

**Not exercised by any test — check by hand in Chrome:** the toolbar button, the
Alt+Shift+I shortcut, the right-click menu, the side panel opening, reading the selected
text from a real page, and Chrome's permission prompt on Connect. These are browser
controls an automated browser cannot press.

**Decisions taken:** voice dictation left out (not attempted; revisit if wanted). No
in-page floating button; the side panel is the notepad. Questions sit in the inbox as
captures until the question queue exists (M6).

## Direction change, 16 Nov 2026 (read `docs/07-second-brain.md`)

Parasu ran the app and said it is "too simple, only Google-Doc-like". He wants an
investment studio: an AI chatbot, a second brain that answers in the floating pad,
remembers his investing style, guards against decisions that deviate from it, checks the
portfolio for risk (with a Trackr+ connection), asks hard questions monthly on position
sizing, and compares portfolio with watchlist. He also supplied seven references.

Decisions taken in response:
- M6 split into **M6a** (done, below) and **M6b**; portfolio, watchlist and the monthly
  review go to **M7**.
- "How I invest" added as a first-class, versioned, user-written layer.
- **Held, because it is his own rule:** no buy/sell/sizing advice. The portfolio check will
  show where holdings break limits *he* wrote and ask about it; it will not say what to
  trade to "offset" risk. Flagged to him; needs his answer.
- Trackr+ link: start with a holdings CSV upload; a live link needs a change in Trackr+,
  which is off-limits without his say-so.
- **Open question to him:** "No obsidian like backlink connection" — read as "couldn't find
  it", not "remove it". Confirm.

## M6a Assistant — done

- `006_analyst.sql`, `app/llm.py`, `app/ask.py`, `app/assistant.py`.
- Model connection: any OpenAI-compatible endpoint, user's own key encrypted (Fernet),
  shown as last four characters, never returned or logged. Optional platform model via
  environment. A built-in **test model** (not an AI) runs the whole flow at no cost.
- Ask: advice questions refused before any call; nothing found → `unknown`, no call; else
  top passages from that company's documents and notes go to the model with the rules;
  each returned claim is kept only if its quotation is in the cited source, its figures
  are in the quotation, and it does not read as advice. Removed claims are counted.
- Guardrail: `POST /subjects/{id}/decisions/check` compares a draft decision with "How I
  invest"; a flag is kept only if the rule it quotes is really in the user's text. Flags
  shown are stored with the decision and appear on the reopen view.
- Cost: per-question cap checked before the call; monthly platform credit; usage ledger.
- Deleting a document deletes citations to it and any claim left without one.
- Notepad: tokens can be created with permission to ask; "Ask now" shows the cited answer
  in the panel. A notepad token can read back only questions asked from the notepad.
- Web: Ask tab on the company page; Settings has How I invest, AI model, and tokens.
- Tests: 134 backend, 9 extension; four browser runs pass (workspace, capture, thesis,
  assistant incl. notepad ask).

**Not proven:** answer quality with a real model. Every test uses a scripted or the
built-in test model. No real key has been used and no money spent. The first real-model
run needs Parasu's key (stop condition).

**Known limits:** period labels (FY25, Q2) are not checked by the figure rule; answers run
in a background task, not a worker; one model call per question, no multi-step reasoning;
no calculation tools yet; notes are cited whole, not by block.

## M4 Documents and retrieval — done

- `004_documents.sql`, `app/extract.py`, `app/documents.py`: upload PDF / .xlsx / .docx
  (type judged by content, 40 MB default cap), original kept on disk with SHA-256,
  extraction per page / sheet, passages of up to 1,800 characters cut at paragraph and
  sentence ends, type and period guessed from the file name, status `ready` /
  `no_text` (scanned) / `failed`. Retrieval filters by company, period and type before
  ranking and returns passages with page labels, plus matching notes.
- Delete removes the row, passages and file; a test searches every table and the disk for
  a planted marker and the file digest.
- **Changed from the plan:** no vector search yet. pgvector could not be installed in the
  build environment, so it could not be tested here, and the plan already said the vector
  half ships only if the eval shows it beats keyword search. Retrieval is Postgres
  full-text for now; embeddings are a later migration, decided in M6 with the eval.
- **Changed from the plan:** extraction runs in a background task of the API process, not
  a separate worker. The worker arrives with the question queue in M6.
- Notes are retrieved whole, not block by block. Block-level citations of notes are M6.

## M5 Thesis engine — done

- `005_thesis.sql`, `app/thesis.py`, `backend/packs/investing/pack.json`: one thesis per
  company with append-only versions and word-level diffs; assumptions with basis
  (source / judgement), state (holds / challenged / broken / outdated) and a required
  reason for state changes; evidence for/against stored by kind — a fact must cite a
  passage from that company's documents, an opinion is the investor's words, `ai` is
  reserved for M6; decision journal with a required decisive reason that snapshots the
  thesis version and the chosen assumptions; red-flag checklist (12 items, each run kept).
- `GET /subjects/{id}/overview` is the reopen view: last decision, reason, what it rested
  on then and now, open questions, changes since. No model involved.
- The API role cannot update or delete thesis versions, assumption versions, decisions or
  checklist runs, and cannot delete evidence (it can be withdrawn, not erased).
- Deleting a document flags evidence that cited it as "source deleted": it stays as the
  investor's words and stops being shown as a fact.
- Web: company page has tabs — Overview, Thesis & decisions, Documents, Notes, Red flags —
  and a document page where a passage becomes evidence.
- Tests: 96 backend tests. `e2e/thesis.py` runs the success test in real Chrome and
  passes: after leaving and reopening the company, the first screen shows the decision,
  the reason verbatim and above the fold, the broken assumption with its reason, and the
  changes since — without opening a document.

**The success test passes on a synthetic company with AI switched off (there is no AI
yet).** It has not been run on IEX: your IEX drafts are working notes, not a thesis with
a recorded decision. Loading them means you writing the thesis, assumptions and decision
in the app — that is the real test, and only you can do it.

**Known limits:** thesis is a plain text box, not the block editor; evidence can cite a
document passage but note-linked evidence has no UI yet; red-flag items are a generic
starting list, not yet your forensic checklist; no OCR; large PDFs are read in-process.

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

M7 is done except the items listed in `docs/REMAINING.md` (16 Nov 2026): holdings CSV
import, user-set limits with alerts, watchlist, monthly review and the connection graph are
built, tested (147 backend tests, `e2e/portfolio.py`) and merged. **`docs/REMAINING.md` is
the ordered queue for everything still to build**, written so a cheaper model can continue.

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
