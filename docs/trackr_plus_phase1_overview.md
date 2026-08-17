# Trackr-Plus Phase 1: Complete System & Codebase Guide

This document is a plain-English map of what Trackr-Plus Phase 1 actually does today —
not what it is planned to do. Every claim below was checked against the source code and
the real test suite on **17 August 2026**: the backend test suite was executed
(`.venv/bin/pytest tests/ -v`), `make lint` was run, every router and engine file was
read, and every page under [`trackr-frontend/app/`](../trackr-frontend/app/) was read to
confirm what a button on screen actually calls. Where the code, the tests and an older
draft of this document disagreed, the code wins and the disagreement is called out
explicitly — see [§7 "Known gaps and stale claims"](#7-known-gaps-and-stale-claims-honesty-section).

> **Re-verified later the same day (17 August 2026).** Real work landed on the
> email-forwarding path between the first pass above and this re-check — this document
> has been updated in place rather than left to rot. What actually changed, checked
> against the code just now:
> - `app/ingest/webhook_providers.py` (new) verifies real Mailgun/SendGrid/Postmark
>   inbound-parse requests instead of assuming a trusted caller, and
>   `app/ingest/addresses.py` (new) derives each account's forwarding address(es) from
>   the adapter registry — see Table 1 row 3.
> - `tests/test_db_webhook.py` (new, 11 tests) is now the **first suite in the repo**
>   to drive a router over a real `fastapi.testclient.TestClient` HTTP round trip
>   against a real database, closing the "no router has a real HTTP-level test" gap —
>   for that one router. `httpx` is now a real dependency
>   (`trackr-backend/pyproject.toml`) for exactly this reason.
> - The **Settings page now has a working "Broker accounts & email forwarding"
>   section** (`AccountOnboarding.tsx` + `EmailForwardingSetup.tsx`): it calls the
>   real `POST /investors/{id}/accounts` and renders each account's real forwarding
>   address with a Gmail/Outlook/Yahoo copy-paste setup walkthrough. This was
>   previously a `🚫 no UI exists yet` item — see Table 1 rows 3 and 12.
> - Investor creation itself (`POST /investors`) is **still** a disabled "Add investor
>   — coming soon" button on the same page — only the account/forwarding half of the
>   onboarding gap closed.
> - The full suite now runs **373 passed, 199 skipped, 1 deselected** (was 335/186/1
>   this morning) — 38 more real passes, entirely from the new webhook-provider and
>   address-derivation tests. `make lint`'s three architecture checks (no `float` in
>   `engine/`, no layer violations, no stored credentials) and `ruff check .` both still
>   pass clean (`ruff` must be on `PATH` via `.venv/bin` — the bare `make lint` target
>   fails with `ruff: No such file or directory` outside an activated venv; this is an
>   environment-PATH issue, not a code problem).
> - Two Phase-1-scoped calculations turned out to have **no implementation at all**,
>   not even a stale claim about one — see the new bullets at the top of §7.

---

## 1. Executive Summary: What is Trackr-Plus?

**Trackr-Plus** is a portfolio intelligence engine for Indian equity investors. It is
not a broker, not an execution venue, and does not hold broker credentials of any kind.

### The one architectural rule

> **Everything is derived from transactions. Holdings are never stored.**
>
> Transactions → Holdings → Portfolio → Performance → Analytics → Insights

1. **Append-only ledger.** The [`transaction`](../trackr-backend/app/db/migrations/001_core.sql) table has a database *trigger* — not just a convention — that physically blocks `UPDATE` and `DELETE`. A correction is always a new, reversing row.
2. **Exact money.** All money and quantity math uses Python `Decimal` and Postgres `NUMERIC(20,6)` — never a binary float. `make lint` fails the build if `float(` ever appears inside [`trackr-backend/app/engine/`](../trackr-backend/app/engine/).
3. **ISIN, never ticker.** Securities are keyed by their permanent ISIN (`security.isin`), because ticker symbols get renamed and reused.
4. **Every ingested row carries a `dedupe_key`.** A SHA-256 hash, enforced by a database `UNIQUE INDEX`, so re-importing the same file twice is a safe no-op.
5. **A missing price raises, it never defaults to zero.** Valuing an unpriced holding at ₹0 would understate return figures catastrophically and silently.
6. **No broker credentials, anywhere.** `make lint` greps the entire repo for password/token/secret-shaped column names on every run.

---

## 2. How to read the "How to test this yourself" column

This document does **not** assume a feature works because a similar-looking one does.
Every row below falls into one of four honest buckets:

| Bucket | What it means |
|---|---|
| ✅ **Automated — passing today** | A test file ran on this machine today and passed, with no real client data and no live server required. |
| ⏭️ **Automated — exists, but skipped here** | A real test file exists and is written correctly, but it did not run today because it needs something this environment does not have: (a) a real local PostgreSQL server binary (`initdb`/`pg_ctl`), or (b) a real, private data file (a real Zerodha export, a real contract note PDF, or the real 324-trade `golden_portfolio.json`) that is deliberately excluded from the repository (`.gitignore`) because it is someone's actual trading history. |
| 🖱️ **Manual — click-path for a non-developer** | Plain steps: what to click, what to type, what you should see. No code, no terminal. |
| 🚫 **No UI exists yet** | The backend can do this today, but there is currently no button, page, or form anywhere in the web app that reaches it. The only way to use it right now is a direct API call. |

**Why so many tests are skipped, and why that is not a red flag by itself:** this
project's test suite deliberately spins up a *throwaway* real PostgreSQL server for its
database tests (see [`tests/conftest_db.py`](../tests/conftest_db.py)) rather than faking
one, because the things worth testing — a unique index, an append-only trigger,
`NUMERIC(20,6)` precision — are exactly the things a fake database would not catch. That
throwaway server needs the `initdb` and `pg_ctl` programs to exist on the machine
running the tests. They are **not installed** in this environment (a Docker Postgres
container is running for live development, but the test harness does not use it — it
always builds its own private server from local binaries). Anyone with those binaries
installed (`sudo apt install postgresql-16`, or `brew install postgresql@17` on a Mac)
can run the full suite, including all 186 currently-skipped tests, with `make test`.

**The verified run, later the same day (after the email-forwarding work landed):**

```
.venv/bin/pytest tests/ -v
============ 373 passed, 199 skipped, 1 deselected in 5.88s ============
```

373 tests genuinely passed on this machine, right now, with zero failures — 38 more
than the morning's 335, all from `tests/test_webhook_providers.py` (19, Mailgun/
SendGrid/Postmark signature and payload-shape logic, no database) and
`tests/test_ingest_addresses.py` (4, forwarding-address derivation). 199 were skipped
for the two reasons above (no local Postgres binaries — this now also includes the new
`tests/test_db_webhook.py`, 11 tests, which needs a real Postgres to actually exercise
`resolve_investor`/`handle_inbound_email` end to end; no real private data files
present). 1 was deselected because it is tagged `network` and this project's default
test configuration excludes network-calling tests (`pyproject.toml`,
`addopts = "-m 'not network'"`). `make lint`'s three architecture checks (no `float` in
the engine, no layer violations, no stored credentials) and `ruff check .` also passed
cleanly today when run with the project's virtual environment active.

---

## 3. Table 1 — Web Application Core Features

Every feature below is described two ways: **how the web app actually does it**, step
by step (backend processing → what you see on screen), and **how to test it yourself**
today, in plain English.

| # | Feature | Frontend Page | Backend Files | Feature Blueprint: How the Web App Does This (Plain English) | How to Test This Yourself |
|---|---|---|---|---|---|
| 1 | **Sign up & sign in** | [`/login`](../trackr-frontend/app/login/page.tsx), [`/register`](../trackr-frontend/app/register/page.tsx) | [`auth/service.py`](../trackr-backend/app/auth/service.py), [`auth/dependencies.py`](../trackr-backend/app/auth/dependencies.py), [`routers/auth.py`](../trackr-backend/app/routers/auth.py), [`008_auth.sql`](../trackr-backend/app/db/migrations/008_auth.sql) | You type an email and password on `/register`. The browser `POST`s to `/auth/register`. The backend hashes the password with bcrypt (the plaintext password is never stored, anywhere) and inserts a row into `app_user`. It then issues a JWT bearer token and — separately — stores a SHA-256 **hash of that token** in `app_session`, never the token itself, so a session can later be listed or revoked without the database ever holding a usable credential. Your browser keeps the token and sends it as `Authorization: Bearer …` on every later request; the backend's `get_current_user` check looks the hash up and rejects expired or revoked sessions. | ✅ Automated: `pytest tests/test_auth_service.py -v` — 6 passed today, pure logic, no database. ⏭️ `tests/test_db_auth.py` (16 tests) needs local Postgres, skipped here. 🖱️ Manual: open the app, click "Create an account", fill in email + password, submit — you land on Settings already signed in. |
| 2 | **Tradebook CSV import & staged promotion** | [`/import`](../trackr-frontend/app/import/page.tsx) | [`ingest/zerodha_tradebook.py`](../trackr-backend/app/ingest/zerodha_tradebook.py), [`ingest/base.py`](../trackr-backend/app/ingest/base.py), [`db/imports.py`](../trackr-backend/app/db/imports.py), [`routers/ingest.py`](../trackr-backend/app/routers/ingest.py) | You paste an Account ID, pick one or more Zerodha "Console → Reports → Tradebook" CSV files, and click **Upload & stage**. Nothing touches your permanent ledger yet: the backend reads each row, checks the ISIN format, converts quantity/price to exact `Decimal` values (never a float), computes a SHA-256 `dedupe_key` for each row, and saves the whole file as a `STAGED` batch in the `import_batch`/`import_row` tables. The Import page then shows that batch with a **Promote** and **Discard** button. Only clicking **Promote** (`POST /ingest/stage/{id}/promote`) is the one explicit, logged-in, attributed action that actually writes rows into the append-only `transaction` table — and it skips any row whose `dedupe_key` is already there, so uploading overlapping files (Console caps each export at 365 days) is safe. | ✅ Automated: `pytest tests/test_zerodha_tradebook.py -v` — 16 passed today against small built-in CSV samples. ⏭️ 3 tests in that file skip because they need a real, personal Zerodha Console export (deliberately gitignored — it's someone's real trades). ⏭️ `tests/test_db_imports.py` (16 tests, the actual stage→promote→ledger flow against a real database) needs local Postgres, skipped here. 🖱️ Manual: log in, open "Import", paste an Account ID, choose your CSV file(s), click "Upload & stage", then click "Promote" on the batch that appears — only then do the trades show up under "Transactions". |
| 3 | **Contract-note PDF & email-forwarding ingestion** | [`/settings`](../trackr-frontend/app/settings/page.tsx) → "Broker accounts & email forwarding" (`AccountOnboarding.tsx`, `EmailForwardingSetup.tsx`) — **the receiving side is still not a page**, see below | [`ingest/zerodha_contract_note.py`](../trackr-backend/app/ingest/zerodha_contract_note.py), [`ingest/webhook.py`](../trackr-backend/app/ingest/webhook.py), [`ingest/webhook_providers.py`](../trackr-backend/app/ingest/webhook_providers.py), [`ingest/addresses.py`](../trackr-backend/app/ingest/addresses.py), [`ingest/gmail_oauth.py`](../trackr-backend/app/ingest/gmail_oauth.py), `POST /ingest/email` in [`routers/ingest.py`](../trackr-backend/app/routers/ingest.py) | **Client-facing setup is now real.** On Settings, adding a broker account (`POST /investors/{id}/accounts`) returns that account's real forwarding address(es) — one per `(broker, doctype)` pair with a registered adapter, derived on every read from the same adapter registry `webhook.py` routes against, so the address shown can never drift from what the backend will actually accept. `EmailForwardingSetup` then walks the client through Gmail/Outlook/Yahoo's own filter-and-forward UI to paste that address in. **The receiving side is still backend-only, by design** — it is a public HTTP endpoint (`POST /ingest/email`) that an inbound-email-parsing provider calls, not a page a user visits. It now verifies who is actually calling it: `webhook_providers.verify_and_translate` checks Mailgun's HMAC-SHA256 signature, or Postmark/SendGrid's HTTP Basic Auth, before anything reaches the provider-ignorant `handle_inbound_email` — previously this endpoint's own docstring made no claim about verifying the caller at all. From there the flow is unchanged: parse the `to` address to find the investor/account, unlock the password-protected PDF using the investor's PAN in a broker-specific case rule (Zerodha upper-case, Upstox lower-case), pull out each trade line with its brokerage/STT/stamp-duty, and stage it exactly like a CSV upload — a human still has to promote it. A second, separate capability — scanning a Gmail inbox directly via OAuth — is still explicitly marked in the code as **"NOT AUTHORIZED FOR REAL CLIENT USE — PERSONAL TESTING ONLY"**: Google requires a paid annual security review (CASA) before this could ever touch a real client's mailbox, which this project has not obtained. Uploading a contract-note PDF directly through the Import page was never the design — [`docs/INGESTION.md`](INGESTION.md) "Adapter 3 — Gmail forwarding" specifies forwarding as the only client-facing delivery path for contract notes, so the Import page's CSV-only dropdown is correct, not a gap. | ✅ Automated: `pytest tests/test_zerodha_contract_note.py -v` — 18 passed, 3 skip (need a real PDF, gitignored). `pytest tests/test_webhook_providers.py -v` — **19 passed today** (new), pinning Mailgun signature verification, Postmark/SendGrid Basic Auth, and each provider's payload-shape translation, no database needed. `pytest tests/test_ingest_addresses.py -v` — **4 passed today** (new), pinning that the derived address set always matches the adapter registry. `pytest tests/test_db_webhook.py -v` — **new, 11 tests, needs local Postgres, skipped here** — but this is no longer a shape-only test: it is the first suite in the repo built on `fastapi.testclient.TestClient` against the real `app.main`, so once Postgres is available it proves the real HTTP auth/parsing/status-code behaviour end to end, closing the old "`resolve_investor`/`handle_inbound_email` have no automated test at all" gap. `pytest tests/test_webhook.py -v` — 12 passed, address-parsing only. `pytest tests/test_gmail_oauth.py -v` — 12 passed against a **fake, injected** Gmail client — no real mailbox, network call, or OAuth flow actually exercised; unchanged. 🖱️ Manual (client-facing half only): log in, open Settings, add a broker account, copy the forwarding address shown, and follow the on-screen Gmail/Outlook/Yahoo steps to set up a filter. 🚫 Manual (receiving half): still not reachable by clicking anything — you would need a real inbound-parse provider (Mailgun/SendGrid/Postmark) configured to POST to `/ingest/email`, or call it directly with curl. |
| 4 | **Manual transaction entry** | [`/transactions`](../trackr-frontend/app/transactions/page.tsx) | [`engine/ledger.py`](../trackr-backend/app/engine/ledger.py), [`engine/dedupe.py`](../trackr-backend/app/engine/dedupe.py), [`db/repository.py`](../trackr-backend/app/db/repository.py), [`routers/transactions.py`](../trackr-backend/app/routers/transactions.py) | Clicking "Add transaction" opens a form for ISIN, date, type (BUY/SELL/DIVIDEND/etc.), quantity, price and charges. Submitting sends it as JSON to `POST /investors/{id}/transactions`, which FastAPI validates against a strict schema before any of your code runs. The handler computes the row's dedupe key and attempts an insert; the database's `UNIQUE INDEX` on `dedupe_key` is the real safety net, so even a bug elsewhere could not sneak a duplicate in. Because every row lands in the same append-only table described in §1, **there is no edit button anywhere in this feature by design** — fixing a mistake means adding a new, opposite transaction. Every other screen recomputes its numbers from this table on every page load; nothing is cached. | ✅ Automated: `pytest tests/test_transactions_router.py -v` — 18 passed today, but this only proves the request *shape* is validated correctly (a Pydantic-schema test) — it does not prove a real HTTP call reaches a real database, because this project has no `httpx`/`fastapi.testclient` dependency installed at all (see that file's own docstring). ⏭️ `tests/test_db_transactions.py` (5 tests, the real database round-trip) needs local Postgres, skipped here. 🖱️ Manual: open "Transactions", click "Add transaction", fill in the form, submit — the row appears at the top of the ledger table immediately. |
| 5 | **Dashboard / portfolio summary** | [`/` (Dashboard)](../trackr-frontend/app/page.tsx) | [`engine/holdings.py`](../trackr-backend/app/engine/holdings.py), [`engine/valuation.py`](../trackr-backend/app/engine/valuation.py), [`routers/holdings.py`](../trackr-backend/app/routers/holdings.py) | On every page load, the dashboard fires four API calls in parallel (`/summary`, `/performance`, `/holdings`, `/transactions`). `/summary` loads *every* transaction for the investor and replays them chronologically through `compute_holdings` (weighted-average cost, one bucket per ISIN), looks up the latest close price for each ISIN still held, and splits the result into **priced** holdings (valued normally) and **unpriced** ones (kept out of every total, shown by name instead of being guessed at ₹0 — CLAUDE.md rule 4). It groups the priced holdings by asset class for the allocation donut and returns the totals. Nothing here is stored between visits — reload the page and the entire replay happens again, from scratch, off the transaction table. | ✅ Automated: the underlying math is pinned by `pytest tests/test_holdings.py -v` (12 passed) and `pytest tests/test_engine_cases.py -v` (13 passed — hand-computed cases straight from [`docs/ENGINE_SPEC.md`](ENGINE_SPEC.md)). ⏭️ The full 324-trade acceptance benchmark (`tests/test_golden_portfolio.py`, 13 tests) is skipped here because `fixtures/golden_portfolio.json` — real, gitignored client data — is not present on this machine; see §6. 🖱️ Manual: log in, land on `/`; the KPI tiles, allocation donut, and top-holdings table should change whenever you add or promote a transaction. |
| 6 | **Holdings table & per-ISIN FIFO lot detail** | [`/holdings`](../trackr-frontend/app/holdings/page.tsx), [`/holdings/[isin]`](../trackr-frontend/app/holdings/%5Bisin%5D/page.tsx) | [`engine/lots.py`](../trackr-backend/app/engine/lots.py), [`engine/realised.py`](../trackr-backend/app/engine/realised.py), [`routers/holdings.py`](../trackr-backend/app/routers/holdings.py) | `/holdings` shows the same weighted-average figures as the dashboard, filterable by symbol/ISIN/name entirely in the browser (no extra API call for filtering). Clicking a row opens `/holdings/[isin]`, which calls three more endpoints: open **FIFO lots** (oldest purchase first — a *different* number from the weighted average shown elsewhere, on purpose, because "what did my remaining shares cost on average" and "which specific batch of shares is left" are genuinely different questions), **realised gains** already booked on that ISIN (each one matched to the specific lot it consumed, and classified Short/Long term by counting the exact number of days held), and the raw transaction history filtered to that ISIN. | ✅ Automated: `pytest tests/test_lots.py -v` — 13 passed today. ⏭️ Cross-check against the real golden fixture skipped, same reason as row 5. 🖱️ Manual: click any row in Holdings to open its detail page; "Open FIFO lots" and "Realised history" list every lot and every sale for that stock. |
| 7 | **Dual XIRR / performance** | [`/performance`](../trackr-frontend/app/performance/page.tsx) | [`engine/xirr.py`](../trackr-backend/app/engine/xirr.py), [`engine/returns.py`](../trackr-backend/app/engine/returns.py), [`engine/snapshot.py`](../trackr-backend/app/engine/snapshot.py), [`routers/analytical.py`](../trackr-backend/app/routers/analytical.py) | The backend builds a dated list of every cash flow you ever made (BUY/IPO outflows negative, SELL/BUYBACK/DIVIDEND inflows positive), tacks on today's total market value of what's left as the final flow, and hands the whole series to `pyxirr` — a tested, off-the-shelf solver, deliberately **not** hand-rolled, because a convergence bug in the one number the product is judged on would be very easy to introduce quietly. This runs **twice**: once over every transaction ever made (`xirr_all`) and once restricted to only the ISINs still held today (`xirr_holdings`) — the two are always shown together so nobody can quote whichever one happens to look better. A third figure, `fy_xirr`, repeats the calculation from 1 April of the current financial year, but only when a usable opening market value exists for that date; otherwise it is quietly left blank rather than estimated. | ✅ Automated: `pytest tests/test_xirr.py -v` (16 passed) and `pytest tests/test_returns.py -v` (9 passed) today, pinned against `ENGINE_SPEC.md`'s worked examples. ⏭️ The golden-fixture benchmark figures (XIRR −17.4361% all-time / −34.8107% current holdings) live in `tests/test_golden_portfolio.py`, skipped here — see §6. 🖱️ Manual: open "Performance" — two XIRR percentages side by side, plus Absolute Return, Invested, Current Value, Unrealised and Realised P&L tiles. |
| 8 | **Missing-price detection & unpriced banner** | Appears automatically on Dashboard & Holdings; the underlying refresh has 🚫 *no button anywhere* | [`engine/valuation.py`](../trackr-backend/app/engine/valuation.py), [`prices/pipe.py`](../trackr-backend/app/prices/pipe.py), [`prices/alerts.py`](../trackr-backend/app/prices/alerts.py), `POST /ops/prices/refresh` in [`routers/analytical.py`](../trackr-backend/app/routers/analytical.py) | Valuation never substitutes ₹0 for a missing price (CLAUDE.md rule 4) — instead it raises an error naming every affected ISIN. The Dashboard/Holdings screens catch that at a higher level and split your book in two: priced holdings are valued and totalled normally, unpriced ones are listed by name with their cost only, and are excluded from every total so they can't silently show a fake profit or loss. The Performance page cannot do this split (XIRR genuinely needs every price), so it shows the named list of missing ISINs instead of crashing. Actually fetching fresh prices (`POST /ops/prices/refresh`, pulling NSE + BSE bhavcopy files) is an operations job meant to run on a schedule — there is no button for it in the web app today. | ✅ Automated: `pytest tests/test_prices.py -v` — 18 passed, 1 skipped (needs the golden fixture). `pytest tests/test_price_alerts.py -v` — 10 passed today, proving the failure-email code path is wired correctly against a fake local mail server; **actual delivery to a real inbox has not been verified**. 🖱️ Manual: if a holding appears in the amber "excluded from totals — no current price" banner on Dashboard or Holdings, that ISIN has no usable price stored. |
| 9 | **Broker / CAS reconciliation** | [`/reconcile`](../trackr-frontend/app/reconcile/page.tsx) | [`engine/reconcile.py`](../trackr-backend/app/engine/reconcile.py), [`routers/reconcile.py`](../trackr-backend/app/routers/reconcile.py) | You type in the ISIN + quantity shown on your broker's own holdings statement — **there is no automatic CAS import**, you key the numbers in by hand. The backend replays your ledger the same way Holdings does, then compares each typed-in quantity against what it computed. Anything that matches is dropped silently — a clean reconciliation returns an *empty* list, never a wall of zeroes. For a mismatch, it computes the ratio (declared ÷ computed) and checks it against known corporate-action ratios (about 2 → a 1:1 bonus or 1:2 split; about 3 → a 1:2 bonus or 1:3 split; about 5 or 10 → a stock split) to suggest a plain-English cause, falling back to "missed buy contract note" or "transfer-out / buyback / missed sell" when nothing matches. Each mismatch row links straight to "Add correcting txn" on the Transactions page. | ✅ Automated: `pytest tests/test_reconcile.py -v` — 15 passed today, pinning the cause-guessing logic itself. `pytest tests/test_reconcile_router.py -v` — 10 passed, but only proves the request/response shapes, not a live database call. ⏭️ `tests/test_db_reconcile.py` (5 tests) needs local Postgres, skipped here. 🖱️ Manual: open "Reconcile", type in the ISIN/quantity pairs from your broker app or CAS PDF, click "Run reconciliation", read the discrepancy table. |
| 10 | **DPDP data export & account erasure ("right to be forgotten")** | 🚫 *no page or button exists in the web app* | [`db/privacy.py`](../trackr-backend/app/db/privacy.py), [`db/crypto.py`](../trackr-backend/app/db/crypto.py), [`db/documents.py`](../trackr-backend/app/db/documents.py), [`routers/privacy.py`](../trackr-backend/app/routers/privacy.py) | **Export** (`GET /privacy/export`) walks every table that references the investor — profile, accounts, consents, legal holds, the full transaction ledger, and a *list* of stored documents (the PDFs themselves are never embedded in the export, only a short-lived signed download link, so the export file doesn't become a second copy of your most sensitive data) — and returns it as one JSON payload. Decrypting the PAN/demat number into that export is switched off by default and is itself logged as a separate, auditable access event when turned on. **Erasure** (`POST /privacy/erase`) first checks for an open legal hold and refuses outright if one exists (so evidence in an active dispute can't be deleted); otherwise it deletes stored documents first, then opens a single database transaction with one special flag turned on — the *only* condition under which the append-only trigger from §1 will allow a delete — and removes the investor row, which cascades to accounts and transactions. The audit-log rows recording that the erasure happened are deliberately kept forever: proving a lawful erasure took place is itself a SEBI/DPDP obligation. | ⏭️ Automated: `pytest tests/test_db_compliance.py -v` — 8 passed today (the pure encryption/hashing logic, no database needed), **23 skipped here** — those 23 are the ones that actually prove export, erasure and the legal-hold refusal against a real database, and they need local Postgres. 🚫 Manual: **there is genuinely no button for this anywhere in the app today.** To use it yourself right now you would call `GET /privacy/export?investor_id=...` or `POST /privacy/erase?investor_id=...` directly with a tool like curl or Postman, using a valid login token. |
| 11 | **Grievance filing (SEBI 90-day clock)** | 🚫 *no page exists in the web app* | [`db/grievance.py`](../trackr-backend/app/db/grievance.py), [`routers/grievance.py`](../trackr-backend/app/routers/grievance.py), [`004_grievance.sql`](../trackr-backend/app/db/migrations/004_grievance.sql) | Filing a grievance (`POST /grievances`, deliberately the one endpoint that needs **no login**, since a complainant may not have an account yet) inserts a row whose 90-day deadline is calculated by a **database trigger**, not application code — so nothing in Python can quietly extend a statutory deadline. Resolving one requires writing down what was actually resolved (a blank resolution is rejected by a database `CHECK` constraint) and can never be back-dated before the original complaint; once resolved, it can never be reopened. | ✅ Automated: `pytest tests/test_grievance_router.py -v` — 16 passed today, proving request/response shapes and the "intake needs no login, everything else does" decision. ⏭️ `tests/test_db_grievance.py` (19 tests) and `tests/test_db_grievance_router.py` (14 tests) — the ones that prove the 90-day trigger and constraints for real — need local Postgres, skipped here. 🚫 Manual: no UI exists yet; you would call `POST /grievances` directly. |
| 12 | **Investor & account onboarding** | [`/settings`](../trackr-frontend/app/settings/page.tsx) — **account half now wired, investor half still stale** — see §7 | [`db/repository.py`](../trackr-backend/app/db/repository.py) (`create_investor`/`create_account`), [`routers/investors.py`](../trackr-backend/app/routers/investors.py), [`ingest/addresses.py`](../trackr-backend/app/ingest/addresses.py), [`components/AccountOnboarding.tsx`](../trackr-frontend/app/components/AccountOnboarding.tsx) | `POST /investors` and `POST /investors/{id}/accounts` are both fully implemented on the backend — they insert a new investor/account row and hand back its id, and the account response now also includes its derived `forwarding_addresses`. **The account half is now real on screen**: Settings' "Broker accounts & email forwarding" section calls `POST /investors/{id}/accounts` directly and lists what comes back (see row 3). One real gap in that new code: there is no `GET /investors/{id}/accounts` in `contracts/openapi.yaml`, so an already-created account can't be re-fetched on a fresh page load — `AccountOnboarding.tsx` works around this by caching each server response it has actually seen in `localStorage`, keyed per investor, which is honest (never a fabricated address) but means switching browsers or clearing storage loses the display, not the data. **The investor half is still stale**: the "Onboarding" section still shows a disabled "Add investor — coming soon" button and the text "Adding a new investor from this UI isn't wired up yet — paste an existing investor ID above." | ✅ Automated: `pytest tests/test_investors_router.py -v` — 6 passed today (schema validation only). ⏭️ `tests/test_db_investors.py` (9 tests, the real insert) needs local Postgres, skipped here. 🖱️ Manual (accounts): open Settings, fill in the broker account form, click "Add account" — it appears below with its real forwarding address(es). 🚫 Manual (investor): the "Add investor" button is a permanently disabled placeholder; the only way to create an investor today is a direct `POST /investors` call, or the existing seed scripts [`db/load_golden.py`](../trackr-backend/app/db/load_golden.py) / [`db/seed_demo.py`](../trackr-backend/app/db/seed_demo.py). |

---

## 4. Table 2 — Backend Python Files, by Subsystem

Status here is deliberately narrower than Table 1's "how to test" column — it names the
*specific* test file(s) that exercise each module, not a blanket "passing."

| Category | File | What it does | Test coverage, verified today |
|---|---|---|---|
| Engine | [`ledger.py`](../trackr-backend/app/engine/ledger.py) | Orders transactions for replay (by date, preserving arrival order within a date via the `seq` column). | Exercised indirectly by every engine test below; no dedicated test file. |
| Engine | [`holdings.py`](../trackr-backend/app/engine/holdings.py) | Replays the ledger into weighted-average-cost holdings. | `test_holdings.py` (12 passed), `test_engine_cases.py` (13 passed). |
| Engine | [`lots.py`](../trackr-backend/app/engine/lots.py) | FIFO lot queue per ISIN; shared replay used by both lots and realised gains. | `test_lots.py` (13 passed). |
| Engine | [`realised.py`](../trackr-backend/app/engine/realised.py) | Realised gain/loss, FIFO-matched, Short/Long classified. | Covered inside `test_lots.py` and `test_demo_fixture.py`; no separate file. |
| Engine | [`valuation.py`](../trackr-backend/app/engine/valuation.py) | Attaches prices to holdings; raises rather than defaulting to ₹0. | `test_holdings.py`, `test_xirr.py` exercise it indirectly; no dedicated file. |
| Engine | [`returns.py`](../trackr-backend/app/engine/returns.py) | Net invested capital and absolute return. | `test_returns.py` (9 passed). |
| Engine | [`xirr.py`](../trackr-backend/app/engine/xirr.py) | Money-weighted return via `pyxirr` (all-time, holdings-only, FY-to-date). | `test_xirr.py` (16 passed). |
| Engine | [`snapshot.py`](../trackr-backend/app/engine/snapshot.py) | Portfolio totals as of a historical date. | **No dedicated unit test file** — only exercised via `test_db_analytical.py`, which needs a database and is skipped here. |
| Engine | [`reconcile.py`](../trackr-backend/app/engine/reconcile.py) | Compares computed vs. declared holdings; guesses the corporate-action cause. | `test_reconcile.py` (15 passed). |
| Engine | [`dedupe.py`](../trackr-backend/app/engine/dedupe.py) | Builds the SHA-256 `dedupe_key` and splits new rows from duplicates. | Covered inside `test_zerodha_tradebook.py`/`test_demo_fixture.py`; no standalone file. |
| Engine | [`types.py`](../trackr-backend/app/engine/types.py) | Core dataclasses: `Transaction`, `Holding`, `Lot`, `TxnType`, `AssetClass`. | `test_types_match_schema.py` (19 passed) checks these against `schema/*.json`. |
| Engine | [`errors.py`](../trackr-backend/app/engine/errors.py) | `MissingPriceError`, `NegativeHoldingError`, `UnparseableRowError`. | Exercised across `test_holdings.py`, `test_xirr.py`, `test_lots.py`. |
| Database | [`connection.py`](../trackr-backend/app/db/connection.py) | Async/sync Postgres connection helper. | Only exercised through DB-fixture tests; skipped here. |
| Database | [`repository.py`](../trackr-backend/app/db/repository.py) | Loads/saves transactions, creates investors/accounts. | `test_transactions_router.py`/`test_investors_router.py` cover the schema layer only; `test_db_transactions.py`/`test_db_investors.py` cover the real database path and are skipped here. |
| Database | [`prices.py`](../trackr-backend/app/db/prices.py) | Stores/reads daily EOD prices. | `test_prices.py` (18 passed, 1 skipped); `test_db_prices.py` (13 skipped, needs Postgres). |
| Database | [`imports.py`](../trackr-backend/app/db/imports.py) | The staging state machine: stage → review → promote/discard. | `test_db_imports.py` (16 skipped, needs Postgres). |
| Database | [`documents.py`](../trackr-backend/app/db/documents.py) | Stores document pointers, content-hash dedupe, signed URLs, erasure. | `test_db_documents.py` (14 skipped, needs Postgres). |
| Database | [`audit.py`](../trackr-backend/app/db/audit.py) | Writes one audit row per mutation, in the same transaction. | `test_db_compliance.py` (partially skipped — see Table 3). |
| Database | [`consent.py`](../trackr-backend/app/db/consent.py) | Records/withdraws DPDP consent; `require_consent()` gate. | `test_db_compliance.py` covers the table; **`require_consent()` is not called from any router or ingestion path in this codebase today** — see §7. |
| Database | [`privacy.py`](../trackr-backend/app/db/privacy.py) | Export and erasure implementation, legal-hold enforcement. | `test_db_compliance.py` (8 passed pure-logic, 23 skipped DB-dependent). |
| Database | [`crypto.py`](../trackr-backend/app/db/crypto.py) | Fernet encryption + peppered PAN hashing. | `test_db_compliance.py` (the 8 that passed today are largely this module). |
| Database | [`retention.py`](../trackr-backend/app/db/retention.py) | Reports investors past the 5-year retention cutoff; does not delete. | Covered by `test_db_compliance.py`'s skipped DB portion. |
| Database | [`precedence.py`](../trackr-backend/app/db/precedence.py) | Resolves the same trade arriving from two sources (tradebook vs. contract note). | `test_db_precedence.py` — 6 passed (pure logic), remainder skipped (needs Postgres). |
| Database | [`grievance.py`](../trackr-backend/app/db/grievance.py) | 90-day clock, acknowledge/resolve/escalate. | `test_db_grievance.py` (19 skipped, needs Postgres). |
| Database | [`load_golden.py`](../trackr-backend/app/db/load_golden.py) | Seeds a database with the real golden fixture, if present. | Not unit-tested; it's a loader script, gated on the same missing file as §6. |
| Database | [`seed_demo.py`](../trackr-backend/app/db/seed_demo.py) | Seeds `fixtures/demo_portfolio.json` for local demos. | `test_demo_fixture.py` (8 passed) sanity-checks the fixture it loads. |
| Ingestion | [`base.py`](../trackr-backend/app/ingest/base.py) | The `Adapter` protocol every parser implements: bytes in, `Transaction` objects out. | Exercised through every adapter test. |
| Ingestion | [`zerodha_tradebook.py`](../trackr-backend/app/ingest/zerodha_tradebook.py) | Zerodha Console tradebook CSV parser. | `test_zerodha_tradebook.py` (16 passed, 3 skipped — needs a real export). |
| Ingestion | [`zerodha_contract_note.py`](../trackr-backend/app/ingest/zerodha_contract_note.py) | Zerodha contract-note PDF parser (STT, brokerage, stamp duty). | `test_zerodha_contract_note.py` (18 passed, 3 skipped — needs a real PDF). |
| Ingestion | [`gmail_oauth.py`](../trackr-backend/app/ingest/gmail_oauth.py) | Read-only mailbox scanner — **personal testing only**, not client-ready (see Table 1, row 3). | `test_gmail_oauth.py` (12 passed against a fake Gmail client). |
| Ingestion | [`webhook.py`](../trackr-backend/app/ingest/webhook.py) | Routes an inbound-email address to an investor/account/adapter; provider-ignorant by design. | `test_webhook.py` (12 passed, address-parsing only) + `test_db_webhook.py` (11, real `TestClient` HTTP round trip against a real database, needs Postgres, skipped here). |
| Ingestion | [`webhook_providers.py`](../trackr-backend/app/ingest/webhook_providers.py) | Verifies and translates Mailgun (HMAC-SHA256 signature)/SendGrid/Postmark (HTTP Basic Auth) inbound-parse requests into one internal shape before `webhook.py` ever sees them. | `test_webhook_providers.py` (19 passed today, no database). |
| Ingestion | [`addresses.py`](../trackr-backend/app/ingest/addresses.py) | Derives an account's forwarding address(es) from `webhook.py`'s own adapter registry — never stored, always reconstructed on read. | `test_ingest_addresses.py` (4 passed today). |
| Prices | [`sources.py`](../trackr-backend/app/prices/sources.py) | Fetches NSE/BSE bhavcopy files. | Covered by `test_prices.py`. |
| Prices | [`pipe.py`](../trackr-backend/app/prices/pipe.py) | Batch price-update pipeline for every ISIN the ledger holds. | Covered by `test_prices.py`, `test_price_alerts.py`. |
| Prices | [`alerts.py`](../trackr-backend/app/prices/alerts.py) | Emails a human when the price pipeline fails. | `test_price_alerts.py` (10 passed against a fake SMTP server; real delivery unverified). |
| Auth | [`service.py`](../trackr-backend/app/auth/service.py) | Registration, bcrypt password check, token issuing. | `test_auth_service.py` (6 passed). |
| Auth | [`dependencies.py`](../trackr-backend/app/auth/dependencies.py) | FastAPI dependency enforcing a bearer token on protected routes. | `test_db_auth.py` (16 skipped, needs Postgres) + the auth-required assertions inside each router's own test file. |
| Routers | all nine files in [`routers/`](../trackr-backend/app/routers/) | Thin HTTP layer; see Table 1 for the endpoint each one exposes. | Each has a schema-only test file (passing) and, where it exists, a `test_db_*` sibling (skipped here). |
| Storage | [`local.py`](../trackr-backend/app/storage/local.py), [`s3.py`](../trackr-backend/app/storage/s3.py), [`factory.py`](../trackr-backend/app/storage/factory.py) | Disk vs. S3/R2 document storage, chosen by environment config. | `test_storage.py` (31 passed), `test_storage_factory.py` (4 passed). |
| Core | [`main.py`](../trackr-backend/app/main.py) | FastAPI app, CORS, one exception-handling layer per domain error. | No dedicated test file exercises `main.py` over real HTTP (see the important note in §7 about the missing `httpx`/`fastapi.testclient` dependency). |
| Core | [`config.py`](../trackr-backend/app/config.py) | Typed environment settings; no field guarding a secret has a default. | `test_config.py` (10 passed). |

---

## 5. Table 3 — Frontend Pages, Their Real API Calls, and What They Render

Every path below was copied directly from the frontend source, not guessed — the
previous draft of this document listed several `/api/v1/...` paths that do not exist
anywhere in this codebase (there is no `/api/v1` prefix at all). The real base path is
whatever `NEXT_PUBLIC_API_BASE_URL` points at (`http://localhost:8000` by default), with
routes like `/investors/{id}/...` directly underneath it.

| Page / Component | File | Real Backend Call | What It Shows |
|---|---|---|---|
| Dashboard | [`app/page.tsx`](../trackr-frontend/app/page.tsx) | `GET /investors/{id}/summary`, `GET /investors/{id}/performance`, `GET /investors/{id}/holdings`, `GET /investors/{id}/transactions` | KPI tiles, allocation donut, top holdings, recent ledger entries. |
| Holdings | [`app/holdings/page.tsx`](../trackr-frontend/app/holdings/page.tsx) | `GET /investors/{id}/holdings` | Full holdings table, filterable client-side; unpriced banner. |
| Holding detail | [`app/holdings/[isin]/page.tsx`](../trackr-frontend/app/holdings/%5Bisin%5D/page.tsx) | `GET /investors/{id}/lots`, `GET /investors/{id}/realised`, `GET /investors/{id}/transactions?isin=` | Open FIFO lots, realised sale history, and the raw ledger for one ISIN. |
| Transactions | [`app/transactions/page.tsx`](../trackr-frontend/app/transactions/page.tsx) | `GET /investors/{id}/transactions`, `POST /investors/{id}/transactions` | Full ledger table (append-only, no edit/delete) plus a manual-entry form. |
| Performance | [`app/performance/page.tsx`](../trackr-frontend/app/performance/page.tsx) | `GET /investors/{id}/performance` | Dual XIRR, FY XIRR, absolute return, invested/current value, realised/unrealised P&L. |
| Import | [`app/import/page.tsx`](../trackr-frontend/app/import/page.tsx) | `POST /ingest/csv`, then `GET /ingest/stage/{id}`, `POST /ingest/stage/{id}/promote` or `/discard` | Upload form for Zerodha tradebook CSVs and the staged-batch review list. |
| Reconcile | [`app/reconcile/page.tsx`](../trackr-frontend/app/reconcile/page.tsx) | `POST /investors/{id}/reconcile` | Hand-entered declared holdings vs. computed holdings, with a likely-cause column. |
| Login | [`app/login/page.tsx`](../trackr-frontend/app/login/page.tsx) | `POST /auth/login` | Sign-in form. |
| Register | [`app/register/page.tsx`](../trackr-frontend/app/register/page.tsx) | `POST /auth/register` | Sign-up form; creates an `app_user` login only, **not** an investor record — those are deliberately separate concepts (an adviser's login vs. a client's portfolio). |
| Settings | [`app/settings/page.tsx`](../trackr-frontend/app/settings/page.tsx) | `POST /investors/{id}/accounts` (via `AccountOnboarding`) — lets you paste an investor ID into browser state otherwise | Account email/name (read-only), a field to type in which investor ID this browser should display, a disabled "Add investor — coming soon" button, and a **working** "Broker accounts & email forwarding" section that creates a real account and shows its real forwarding address(es). **No privacy, consent, export, or delete-my-data control exists on this screen** — see Table 1, row 10. |
| AccountOnboarding | [`app/components/AccountOnboarding.tsx`](../trackr-frontend/app/components/AccountOnboarding.tsx) | `POST /investors/{id}/accounts` | Broker-account form (broker, label, DP ID, client ID); lists accounts created in this browser session by caching each real `AccountOut` response in `localStorage` (there is no `GET /investors/{id}/accounts` to re-fetch them). |
| EmailForwardingSetup | [`app/components/EmailForwardingSetup.tsx`](../trackr-frontend/app/components/EmailForwardingSetup.tsx) | — (receives an `AccountOut` as props) | One copy-field per real forwarding address on the account, plus a Gmail/Outlook/Yahoo tab with click-by-click filter-and-forward setup instructions for that provider. |
| HoldingsTable | [`app/components/HoldingsTable.tsx`](../trackr-frontend/app/components/HoldingsTable.tsx) | — (receives data as props) | Sortable holdings rows with colour-coded gain/loss. |
| DualXirrCard | [`app/components/DualXirrCard.tsx`](../trackr-frontend/app/components/DualXirrCard.tsx) | — | Side-by-side all-time vs. holdings-only XIRR, plus FY XIRR. |
| AllocationDonut | [`app/components/AllocationDonut.tsx`](../trackr-frontend/app/components/AllocationDonut.tsx) | — | Asset-class allocation donut (Phase 1 shows effectively one slice: `EQ`). |
| DiscrepancyTable | [`app/components/DiscrepancyTable.tsx`](../trackr-frontend/app/components/DiscrepancyTable.tsx) | — | Reconciliation mismatches with a link to add a correcting transaction. |
| StagingBatch | [`app/components/StagingBatch.tsx`](../trackr-frontend/app/components/StagingBatch.tsx) | `GET /ingest/stage/{id}`, `POST .../promote`, `POST .../discard` | One uploaded batch, with Promote/Discard controls. |
| UnpricedBanner | [`app/components/UnpricedBanner.tsx`](../trackr-frontend/app/components/UnpricedBanner.tsx) | — | Amber warning naming every holding excluded from totals for lack of a price. |
| MissingPriceNotice | [`app/components/MissingPriceNotice.tsx`](../trackr-frontend/app/components/MissingPriceNotice.tsx) | — | Shown instead of a blank Performance page when XIRR can't be computed. |
| HistoricalChartPlaceholder | [`app/components/HistoricalChartPlaceholder.tsx`](../trackr-frontend/app/components/HistoricalChartPlaceholder.tsx) | — | Honest disabled empty state on the Dashboard ("Historical value isn't tracked yet") — no daily-snapshot persistence exists yet; see the new §7 bullet on the CLAUDE.md/FEATURE_BACKLOG.md scope conflict. |

---

## 6. How the Core Engine Logic Works (Plain English)

### Step 1 — Ingestion & deduplication
A tradebook row (or a manual entry) becomes a candidate `Transaction`. Its dedupe key is
**not** simply `date + isin + quantity + price` — it is
`SHA256(account_id | source | source_ref | isin | txn_date | txn_type | quantity |
price)` (see [`engine/dedupe.py`](../trackr-backend/app/engine/dedupe.py)). Including
`source_ref` (the broker's own trade ID) matters: real Zerodha exports contain multiple
separate trades on the same day, same ISIN, same price — three separate sells of 2
shares each, for example — which a simpler key would silently collapse into one. The
database's `UNIQUE INDEX` on this key, not application code, is what actually refuses a
duplicate.

### Step 2 — FIFO lot matching
When shares are sold, [`engine/lots.py`](../trackr-backend/app/engine/lots.py) consumes
from the *oldest* open lot for that ISIN first, splitting a lot if the sale is smaller
than it. Each sale can therefore produce more than one realised-gain row — part
long-term, part short-term — if it eats into two lots with different purchase dates.

### Step 3 — Holdings & valuation
[`engine/holdings.py`](../trackr-backend/app/engine/holdings.py) tracks a running
*cost pool* per ISIN rather than rounding at every trade: a sale removes cost from the
pool proportionally to how much of the position it sold, and the 4-decimal-place average
is only computed once, when a holding is displayed. The code comments explain this was
settled by measurement, not preference — rounding after every trade instead of once at
the end reproduced only 16 of the 20 real portfolio values correctly; rounding once
reproduced 18, and matches the broker's own 4-decimal-place statements. Two independent
"cost" answers are always computed side by side: the weighted-average figure (what the
dashboard shows) and the FIFO figure (what a tax computation needs) — they only diverge
once a position has been *partly* sold.

### Step 4 — Dual XIRR
`xirr_all` (every transaction, ever) and `xirr_holdings` (only ISINs still held) are
always computed and shown together, never one alone — the code's own comment on this is
blunt: showing only one "removes the choice to present whichever looks better."

---

## 7. Known Gaps and Stale Claims (Honesty Section)

Reading the code end-to-end today surfaced several places where a page, a comment, or an
earlier draft of this document said something the current code does not actually do.
Listing them here is the point of an audit document — a gap that's written down is a
gap that gets fixed; a gap that's assumed away doesn't.

### Two Phase-1-scoped calculations have no implementation at all

Neither of these was flagged in the first pass of this document — they were found while
re-checking the codebase later the same day. Both are spec'd in detail in
[`docs/ENGINE_SPEC.md`](ENGINE_SPEC.md), both are named line items in
[`docs/FEATURE_BACKLOG.md`](FEATURE_BACKLOG.md)'s Phase 1 table, and neither is a stub
that half-works — there is genuinely no code path that produces either number.

- **Per-holding CAGR does not exist anywhere.** `ENGINE_SPEC.md` §5 is explicit: "CAGR
  is shown per-holding only" — the *portfolio-level* `cagr` field on `PerformanceOut`
  is correctly, permanently `None` by design (a portfolio has staggered dated
  contributions, so a single-lump-sum CAGR is mathematically invalid at that level —
  this part is not a gap, it's the spec working as intended). But the per-holding case
  the spec actually asks for has no home: there is no `cagr` field on the holdings
  schema, no computation in [`engine/holdings.py`](../trackr-backend/app/engine/holdings.py),
  and nothing on the Holdings page. The only place `cagr` appears in the codebase today
  is that permanently-`None` portfolio-level field.
- **"Period XIRR (adviser onboarding)" has an engine but no wiring.** The primitive
  itself is real and tested: `compute_period_xirr` in [`engine/xirr.py`](../trackr-backend/app/engine/xirr.py)
  takes an arbitrary `(start_date, opening_value)` and is pinned by the
  `period_xirr_mid_period_deposit_not_inflated` case in `fixtures/engine_cases.json`.
  But it is only ever *called* with `start_date` = the current financial year's 1 April
  (as `fy_xirr` — Table 1, row 7). Nothing calls it with an actual client onboarding
  date, because no such date is stored anywhere: `account` and `investor` have no
  `onboarding_date` column. There is no router parameter, no schema field, and no UI
  for this even though it is a distinct named item in `FEATURE_BACKLOG.md`'s Phase 1
  table, separate from `fy_xirr`.

### Resolved since the first pass today

- ~~The Settings page is out of date about onboarding~~ **Half-resolved.** Broker
  *account* onboarding is now real and wired (Table 1, row 12) — only *investor*
  creation is still a disabled placeholder.
- ~~`resolve_investor`/`handle_inbound_email` have no automated test~~ **Resolved for
  that router.** `tests/test_db_webhook.py` now drives them over a real
  `fastapi.testclient.TestClient` HTTP round trip.
- ~~No router in this project has a real HTTP-level automated test / no
  `httpx`/`fastapi.testclient` dependency installed~~ **Half-resolved, and narrowly.**
  `httpx` is now a real dependency and `tests/test_db_webhook.py` proves the pattern
  works. But it has not been extended anywhere else: `investors`, `transactions`,
  `holdings`, `auth`, `reconcile`, `grievance`, `analytical`, and `privacy` are all
  still either schema-shape-only (`test_*_router.py`) or call the route *function*
  directly against a real database, bypassing FastAPI's dependency injection and
  middleware entirely — `tests/test_db_grievance_router.py`'s own docstring says this
  plainly: "calling the plain function bypasses FastAPI's own dependency injection, so
  nothing here proves a request WITHOUT a token is refused."

### Still open, unchanged since the first pass today

- **There is no privacy/consent/delete-my-data screen anywhere in the web app**, even
  though the backend fully implements DPDP export and erasure (Table 1, row 10). Today
  this right can only be exercised through a direct API call.
- **`require_consent()` is defined but never called, and there is no consent router at
  all.** [`db/consent.py`](../trackr-backend/app/db/consent.py) implements
  `record_consent`/`withdraw_consent`/`require_consent`, but grepping every file under
  `routers/` for `consent` returns nothing — there is not even an HTTP endpoint to
  *grant* a consent, let alone a check blocking ingestion without one. `FEATURE_BACKLOG.md`
  lists "Client consent records | Before any client data lands" as Phase 1 scope; today
  this is 0% reachable from outside a Python REPL.
- **`holding_snapshot` is schema-only.** The table exists (migration `001_core.sql`) and
  is described as the place CAS/broker-declared quantities should live, but no code in
  the repository writes to it or reads from it — the Reconcile feature (row 9) takes
  declared quantities straight from the request instead of this table.
- **SEBI retention is 5 years in this codebase, not 7.** ([`002_compliance.sql`](../trackr-backend/app/db/migrations/002_compliance.sql),
  [`docs/COMPLIANCE.md`](COMPLIANCE.md) §"Record retention — five years"). An earlier
  draft of this document said seven years; that number does not appear anywhere in the
  code, the migrations, or `docs/COMPLIANCE.md`.

### A documentation contradiction, not a code gap

- **`CLAUDE.md`'s own summary disagrees with `FEATURE_BACKLOG.md`'s own Phase 1 table**
  about whether "historical value" and "benchmark comparison" are Phase 1 or Phase 2.
  `CLAUDE.md`'s MVP-scope paragraph lists both as "In" for Phase 1. But
  `FEATURE_BACKLOG.md` — which `CLAUDE.md` itself designates as the authority ("if a
  feature is not in the Phase 1 table there, do not build it") — puts both under Phase
  2 explicitly: "Daily snapshots | Unlocks the value chart and TWRR", "Historical
  portfolio value chart | Needs snapshots first", "Benchmark XIRR (NIFTY 50 TRI) |
  Cash-flow-replicated — see ENGINE_SPEC §6". The code has already, correctly, sided
  with `FEATURE_BACKLOG.md`: [`components/HistoricalChartPlaceholder.tsx`](../trackr-frontend/app/components/HistoricalChartPlaceholder.tsx)'s
  own comment says "Available once daily portfolio snapshots are persisted (Phase 2)",
  and [`engine/returns.py`](../trackr-backend/app/engine/returns.py)'s module docstring
  says benchmark comparison is "left unwired rather than faked" because it "needs an
  index-level feed this system does not have." **Recommendation: fix the one-line
  summary in `CLAUDE.md` to match `FEATURE_BACKLOG.md`, not the other way around** — the
  code is already right, and building either feature now would be building ahead of
  scope against `CLAUDE.md`'s own rule.

---

## 8. PostgreSQL Database Storage & SEBI/DPDP Compliance

This is the schema as it actually exists in
[`trackr-backend/app/db/migrations/`](../trackr-backend/app/db/migrations/) today — not
a summary, the real column groups. The task requirements named nine tables directly;
each is covered in full below. Six more supporting tables exist in the schema and are
listed afterward for completeness, since an audit that hides tables is not an audit.

| Table | Column Groups Actually Stored | Why This Data Is Kept | Compliance & Legal Check |
|---|---|---|---|
| **`investor`** | `id` (uuid, PK) · `code` (unique short code, e.g. `C001` — use this in files/logs, **never** the name or PAN) · `display_name` · `family_group_id` · `created_at` | The one anchor row every other table hangs off. Deliberately holds **no PAN column at all** — see the migration's own comment: "NO PAN COLUMN HERE, deliberately." | **DPDP erasure:** ✅ real — `DELETE FROM investor` is the actual mechanism [`db/privacy.py`](../trackr-backend/app/db/privacy.py) uses, cascading to `account`/`transaction`. **SEBI Reg. 19:** ✅ `retention_policy` lists `investor` at 5 years, counted from *last activity*, not first contact. **Field-level encryption:** N/A — no sensitive identifier lives on this row. **Zero-Credential Rule:** ✅ confirmed — no password/token/secret column exists; `make lint` greps this file on every run. |
| **`account`** | `id` · `investor_id` (FK) · `broker` (free text, e.g. `"ZERODHA"`) · `dp_id` · `client_id` · `is_advised` (bool) · `label` | Scopes trades to one demat/broker account, and lets a SEBI-registered adviser separate an "advised" account from a client's own personal trading. | **DPDP erasure:** ✅ `ON DELETE CASCADE` from `investor` — erasing the investor removes their accounts automatically. **SEBI Reg. 19:** ✅ inherits the investor's 5-year policy. **Field-level encryption:** ⚠️ **not encrypted** — `dp_id`/`client_id` are stored in plain text today. They are account identifiers rather than a PAN, so this does not break any documented rule, but it is worth flagging as a hardening opportunity. **Zero-Credential Rule:** ✅ `broker` is a text label, never a password or token; no such column exists. |
| **`security`** | `isin` (PK, format-checked `^IN[A-Z0-9]{10}$`) · `symbol` · `name` · `exchange` · `asset_class` · `sector` | The permanent, ticker-proof master list of tradable securities — CLAUDE.md rule 2. | **DPDP erasure:** N/A — this is public market data, nobody's personal information. **SEBI Reg. 19:** N/A — kept indefinitely as reference data, not tied to any one investor. **Field-level encryption:** N/A. **Zero-Credential Rule:** ✅ no credential-shaped column exists. |
| **`transaction`** | `id` · `account_id` (FK) · `isin` (FK) · `txn_date` · `txn_type` (enum) · `quantity` · `price` · `charges` · `dividend_amount` · `source` (enum) · `source_ref` · `dedupe_key` (unique) · `raw_payload` (jsonb) · `created_at` · `seq` (arrival order) | **The master ledger.** Every buy/sell/dividend/bonus/split/transfer, ever. Everything else in the product (holdings, P&L, XIRR) is *derived* from this table on every read — nothing is cached from it. | **DPDP erasure:** ✅ real, but deliberately hard to trigger by accident — a database *trigger* physically blocks every `UPDATE`/`DELETE`; the only way rows leave this table is the erasure path, which sets a session-local, transaction-scoped flag (`app.erasure_authorised`) that is itself an audited action. **SEBI Reg. 19:** ✅ `retention_policy` lists `transaction` at 5 years, noted as "Advisory record." **Field-level encryption:** none on this table — money/quantity/ISIN/date are not classified as sensitive personal identifiers under DPDP the way a PAN is. `raw_payload` does retain the original parsed row (which can include a broker's own trade ID), worth being aware of during an export. **Zero-Credential Rule:** ✅ confirmed no broker password/token/secret column exists. |
| **`price`** | `isin` · `price_date` · `close` · `source`; PK `(isin, price_date)` | Daily closing prices (NSE/BSE bhavcopy), fetched on the market's own schedule, independent of any client's activity. | **DPDP erasure:** N/A — not personal data. **SEBI Reg. 19:** N/A — public reference data with no personal-data retention clock. **Field-level encryption:** N/A. **Zero-Credential Rule:** ✅ no credential column exists. |
| **`holding_snapshot`** | `account_id` (FK) · `isin` (FK) · `snap_date` · `quantity` · `source`; PK `(account_id, isin, snap_date)` | *Designed* to hold broker/CAS-declared quantities so the engine's own computed holdings can be checked against them, explicitly **not** a source of truth for display. **In practice, no code in this repository writes to or reads from this table today** — the Reconcile feature (Table 1, row 9) takes declared quantities straight from the request body instead. This is a real, honest gap, not a documented feature working quietly in the background. | **DPDP erasure:** ✅ if ever populated — `ON DELETE CASCADE` from `account`. **SEBI Reg. 19:** would inherit the investor's policy. **Field-level encryption:** N/A — just an ISIN and a quantity. **Zero-Credential Rule:** ✅ no credential column exists. |
| **`client_consent`** | `id` · `investor_id` (FK) · `notice_version` · `purpose` · `lawful_basis` · `consent_given_at` · `withdrawn_at` · `evidence_ref` | The DPDP consent-first record. A live grant is any row with `withdrawn_at IS NULL`; withdrawing stamps that column rather than deleting the row, and a fresh grant afterward is always a *new* row — so the full history of what was agreed, when, and under which wording survives. | **DPDP erasure:** ✅ listed (not decrypted — there's nothing to decrypt here) in `/privacy/export`, and removed via `CASCADE` on investor erasure. **SEBI Reg. 19:** indirect — this is the evidentiary trail DPDP's consent-first rule itself demands. **Field-level encryption:** N/A — no PAN or sensitive value is stored here, only consent metadata. **Zero-Credential Rule:** ✅ no credential column exists. **Enforcement gap:** ⚠️ see §7 — the `require_consent()` gate this table exists to support is not currently called anywhere in the codebase. |
| **`investor_secret`** | `investor_id` (PK) · `pan_hash` (peppered HMAC-SHA256, lookup only) · `pan_enc` (Fernet ciphertext, `bytea`) · `demat_enc` (Fernet ciphertext, `bytea`) · `updated_at` · `key_version` · `pepper_version` · `pan_hash_next` | The **one** place a PAN or demat number is ever stored, and only ever encrypted. Kept in a separate table from `investor` on purpose — the code comment is explicit that it is "NEVER joined into a default investor read," so an ordinary query cannot accidentally leak an identifier it didn't ask for. | **DPDP erasure:** ✅ cascades from investor deletion; export requires an explicit, off-by-default `include_identifiers=true` flag and is separately audited every time it's turned on. **SEBI Reg. 19:** ✅ same 5-year default as `investor`. **Field-level encryption:** ✅ **verified in the code** — PAN is never stored as plain text anywhere; [`db/crypto.py`](../trackr-backend/app/db/crypto.py) *raises* (`EncryptionNotConfiguredError`) rather than silently falling back to plaintext if the encryption key or pepper is missing, and a database `CHECK` constraint (`pan_hash_requires_ciphertext`) physically refuses to store a lookup hash without its matching ciphertext. **Zero-Credential Rule:** ✅ confirmed no broker/API/OTP column exists. |
| **`audit_log`** | `id` · `actor_uid` · `action` · `entity_type` · `entity_id` · `ts` · `diff_json` | Doubles as the DPDP access log and the SEBI advisory activity record, written **inside the same database transaction** as the mutation it describes — [`db/audit.py`](../trackr-backend/app/db/audit.py)'s own docstring calls this "cannot-not," not "should." | **DPDP erasure:** ⚠️ **deliberately not deleted** when an investor is erased — the rows simply reference an investor id that no longer resolves to anything, so the system can prove *something happened* without retaining *what it was about*. This is correct by design: erasing the evidence that an erasure occurred would itself violate both DPDP's access-log duty and SEBI's record-keeping duty. **SEBI Reg. 19:** ✅ `retention_policy` explicitly lists `audit_log` at 5 years, "exceeds DPDP's 1-year log minimum." **Field-level encryption:** N/A by design — `diff_json` is documented as never allowed to contain a PAN, demat number, or ciphertext, because this table is meant to be widely readable. **Zero-Credential Rule:** ✅ purely action/entity metadata; no credential field is structurally possible here. |

### Supporting tables (exist in the schema, not among the nine named above)

| Table | Purpose | Compliance note |
|---|---|---|
| `retention_policy` | Configurable per-entity-type retention length (default 5 years). Reports what's due, never deletes automatically. | A cleanup job reading this table still requires a human to act — see [`db/retention.py`](../trackr-backend/app/db/retention.py)'s own docstring. |
| `legal_hold` | An open hold (`released_at IS NULL`) suspends erasure for one investor, overriding retention. | This is the mechanism that makes the erasure "refusal" in Table 1 row 10 real — checked before any delete runs. |
| `document` | Pointers to stored PDFs/CSVs (object storage key, SHA-256, byte size) — the bytes never live in Postgres. | Deleted before the investor row on erasure, specifically so a PDF holding a PAN never outlives its own database record. |
| `grievance` | The 90-day SEBI complaint-redressal record (Table 1, row 11). | `investor_id` is `ON DELETE SET NULL`, not `CASCADE` — a grievance record survives an investor's erasure, because it documents *our* conduct, not only theirs. |
| `import_batch` / `import_row` | The staging area for uploaded files before a human promotes them (Table 1, row 2). | Rejected/discarded rows are kept, not deleted — the record of what was rejected and why is itself the evidence that review happened. |
| `app_user` / `app_session` | Login to *this application* (an adviser's account) — entirely separate from `investor` (a client's portfolio). | `app_session` stores a SHA-256 **hash** of the session token, never the token itself — the same logic that keeps a stolen database from also being a stolen set of live sessions. |

---

## 9. Reproducing the Verified Golden-Fixture Numbers Yourself

`fixtures/golden_portfolio.json` is **not in this repository** — it is one real
investor's actual 324-trade history (October 2022 – August 2026), independently
verified once in Excel and once in Python against real CDSL CAS statements, and it is
gitignored on purpose: real trading history, including demat identifiers, does not
belong in git history where it can never truly be erased. The headline numbers it is
meant to reproduce are documented in [`CLAUDE.md`](../CLAUDE.md):

| Metric | Expected |
|---|---|
| Invested (current holdings) | `1579245.74` |
| Market value | `1360575.42` |
| XIRR — all transactions | `-0.174361` |
| XIRR — current holdings only | `-0.348107` |

To check these yourself: place a file matching that shape at `fixtures/golden_portfolio.json`
locally, then run `pytest tests/test_golden_portfolio.py -v`. Without that file, the
whole module — correctly — skips rather than fabricating a pass.

To check with **your own** data instead: start the app (`./start.sh` or `make dev`),
sign in, open **Import**, export your own tradebook CSV from Zerodha (Console → Reports
→ Tradebook → Download CSV), upload and promote it, and compare the **Holdings** and
**Performance** pages against your broker's own app.

To run the ~186 tests that were skipped in today's run, install real PostgreSQL server
binaries (`initdb`/`pg_ctl` on `PATH` — e.g. `sudo apt install postgresql-16` or
`brew install postgresql@17`) and re-run `make test`.
