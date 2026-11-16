# Remaining work (written 16 Nov 2026, after M7)

For whoever picks this up next (a cheaper model is fine). Everything below is specified
tightly enough to build without new design decisions. Read `docs/HANDOFF.md` first, then
this file. Rules that never bend are in `HANDOFF.md` under "Non-negotiables" and "Stop
conditions"; the short version: no buy/sell/sizing advice, every AI claim cited, history is
append-only, tenant isolation in the database, no paid keys or spend without Parasu.

## How to work here

- Branch from `invest-pad/main`, one branch per item, fast-forward merge when CI is green.
- Backend tests: `TEST_ADMIN_URL=postgresql://postgres@127.0.0.1:55432/postgres pytest -q`
  (local Postgres 16; start command is in `HANDOFF.md`). `ruff check .` must pass.
- Web: `API_URL=http://127.0.0.1:8767 npx next build` (API_URL is baked at build time).
- E2E scripts in `e2e/` are run by hand; each needs a fresh invite code (single use).
- Every new owned table: `owner_id`, `enable_owner_isolation('<table>')`, and composite
  foreign keys that include `owner_id`. `tests/test_isolation.py` fails the build otherwise.
- Alert/review/assistant wording must pass the banned-words test in `test_portfolio.py`.

## What exists (M1–M7, all on `invest-pad/main`)

Accounts and invites, companies, notes with versions and `[[links]]`, Chrome side-panel
capture and ask, documents (PDF/XLSX/DOCX) with passage search, thesis/assumptions/evidence/
decision journal, red-flag checklist, the reopen view, cited Q&A with claim verification,
advice refusal, cost caps, "How I invest" guardrail on decisions, bring-your-own model key;
and from M7: holdings CSV import, user-set limits with alerts, watchlist, monthly review
questions, connection graph (`GET /graph`, Connections tab).

## Queue, in order

### 1. Full export (non-negotiable, not yet built) — small
`GET /export` streams a ZIP for the signed-in user: one folder per company with notes as
Markdown (current text plus `versions.json`), thesis/assumptions/evidence/decisions as JSON
and a readable `thesis.md`, original uploaded files, Q&A with claims and citations, holdings
snapshots, limits, alerts, reviews, profile versions, captures. No other user's rows; no
model keys.
Done when: a test creates two users, exports one, and asserts every table with `owner_id`
contributes at least one row for that user and none for the other; a Settings button
downloads it.

### 2. Delete cascade audit (non-negotiable; partly built) — small
Deleting a document already removes chunks and marks evidence "source deleted". Add a test
that walks every table referencing `document`, `note`, `subject` and proves delete leaves no
orphan text (answers/claims/citations quoting the deleted passage included). Fix what fails.

### 3. Calculation tools with visible formulas (M6b) — medium
`backend/app/calc.py`: pure functions on `Decimal`, each returning value + formula string +
inputs: CAGR, margins, ROE, ROCE, DuPont (3-step), working-capital days, net debt/EBITDA,
interest cover, FCF and FCF conversion, Beneish M-score, Sloan accruals. `POST /calc/{name}`.
The assistant may cite a calc result only by calling these; it never does arithmetic in
text. UI: a "Numbers" tab where the user types or picks inputs and sees formula and result.
Done when: each function has tests with hand-worked values, including zero/negative
denominators returning "not meaningful" rather than a number.

### 4. First real-model run + 50-question eval (M6b) — needs Parasu
Blocked on him adding his own key in Settings for a DeepSeek model **hosted by a third
party** (never DeepSeek's own API). Check the host's live price and data-region statement
before the run and put both in `docs/MVP-REPORT.md`. Build `backend/eval/run.py`: loads the
synthetic corpus, asks the 50 templates in `docs/05-eval-plan.md`, scores citation validity
(automatic), refusal correctness (automatic) and answer correctness (hand-marked CSV).
Estimated spend must be printed and confirmed before sending anything.

### 5. Trackr+ link — needs Parasu
Trackr+ repo is off-limits without his say-so. Contract to propose to him (do not build the
Trackr+ side): user creates a read-only token inside Trackr+; pastes it in Invest-pad
Settings; Invest-pad calls `GET <trackr>/api/v1/holdings` returning
`[{symbol, isin, quantity, avg_cost, current_value, as_of}]`; result goes through the same
`store_snapshot` path as the CSV import. Token stored Fernet-encrypted like model keys.
Until then the CSV import is the supported path (Trackr+ export works if it has symbol,
quantity and value columns; add header aliases to `HEADERS` in `portfolio.py` if not).

### 6. Rest of M7 — medium
- Contradiction scan: when a document is added, run the existing retrieval for each live
  assumption; passages the model marks as contradicting become "evidence against —
  suggested" (never auto-accepted, never changes assumption state).
- "How I invest" suggestions: after 3+ decisions share a stated reason, propose a rule
  as a suggestion the user accepts or dismisses; accepted ones create a new profile version.
- Review: add a monthly nav badge when the current period has unanswered items.
- Graph: a whole-workspace view at `/graph` (endpoint already supports no `subject_id`).

### 7. M8 — medium
User-editable checklists (copy the built-in pack, edit items; runs record the pack version),
forensic and DuPont checklists using the calc tools, Markdown/PDF export of a company page,
journal view across companies, MCP server exposing read-only search over the user's own
workspace (token-scoped like the extension).

### 8. M9 — medium, parts need Parasu
Rate limits on auth and ask endpoints; prompt-injection tests (a document containing
"ignore your instructions…" must not change answers or leak another passage; a captured
page must not trigger tool use); cross-tenant tests for every new endpoint; backup/restore
script; onboarding walkthrough on the empty home screen; demo script; draft privacy policy
and terms marked DRAFT — FOR LAWYER REVIEW (Parasu must have them reviewed; do not publish).
Deployment prep only as documentation: hosting accounts, domain and DNS are his.

### 9. `docs/MVP-REPORT.md`, then landing page
Report: what works, evidence (test counts, e2e runs), eval results, known gaps, costs.
Landing page on its own branch, only features that exist, no SEBI or advice claims, no
testimonials or invented numbers, no deployment, nothing on meicapital.in.

## Known gaps to state honestly in any report

- No real model has answered a question yet; answer quality is unmeasured.
- Vector search is not built (keyword search only); pgvector is in the Docker image.
- `docker compose up` has never been confirmed working on Parasu's Mac.
- Extension toolbar button, shortcut, context menu and permission prompt were never tested
  in a headed browser.
- Large real annual reports (300+ pages, scanned) are untested; there is no OCR.
- Holdings import was tested on a Zerodha-style layout and two generic ones, synthetic data.
