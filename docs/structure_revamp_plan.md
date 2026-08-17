# Architecture Implementation & Structure Revamp Plan: Trackr-plus

This document specifies the production-grade architectural plan for restructuring
**Trackr-plus** into a dual-package architecture:

1. **`trackr-backend/`**: FastAPI application — the existing, verified engine, ingestion,
   pricing, storage and DPDP-compliance modules, reorganised under `app/`, plus the
   genuinely missing pieces (JWT auth, the inbound-email webhook, staging HTTP endpoints).
2. **`trackr-frontend/`**: Next.js 14+ (App Router) dashboard replacing the current
   server-rendered Jinja UI, built against `contracts/openapi.yaml`.

> **Revision note (2026-08-15):** this supersedes the first draft of this document. That
> draft was cross-checked against the actual repository — not just the target-vision
> capabilities image it cited — and several claims did not survive contact with the code.
> See "Corrections made in this review" below before reading the rest.

---

## Corrections made in this review

The original draft was directionally reasonable (FastAPI + Next.js, correct invariants
copied from `CLAUDE.md`) but had one contradiction serious enough to block execution, and
several comprehensiveness gaps that would have silently discarded working code.

1. **SQLAlchemy 2.0/SQLModel + Alembic contradicts a dated, explicit decision already
   recorded in this repo.** `docs/STACK_DECISION.md` ("Superseded 14-08-2026") says in so
   many words: *"Django's value is its ORM, admin, migrations and auth; this system
   deliberately uses none of them — migrations are numbered `.sql` applied by
   `db/migrate.py`."* Introducing an ORM is not a reorganisation, it is reopening a
   decision the repo already made, with no new information cited to justify reversing it.
   **Corrected to:** keep raw SQL (`psycopg[binary]`) + numbered `.sql` migrations,
   applied by the existing `db/migrate.py` pattern. If there is a reason to revisit this,
   it belongs in an update to `STACK_DECISION.md` first, not a silent change smuggled in
   via a directory rename.
2. **Nine of fourteen `db/` modules were missing from the target tree entirely.**
   `db/audit.py`, `consent.py`, `crypto.py`, `documents.py`, `grievance.py`, `imports.py`,
   `precedence.py`, `privacy.py`, `retention.py` are not stubs — they are working,
   individually tested (`tests/test_db_*.py`) implementations of DPDP compliance, the
   staging/review/promote workflow, and cross-source (tradebook vs. contract-note)
   precedence arbitration. A plan that doesn't name them risks a rewrite that discards
   them. **Corrected:** all fourteen are mapped explicitly below.
3. **`storage/` had no home in the target tree at all**, despite being named in the old
   Phase 3 bullet list. Content-addressed document storage (local + S3/R2, per
   `docs/INGESTION.md` "Where documents land") is load-bearing for every ingest adapter.
   **Corrected:** `app/storage/` added.
4. **`engine/ledger.py` and `engine/errors.py` were missing** from the target
   `app/engine/` tree. `ledger.py` defines the single replay ordering both FIFO and
   weighted-average costing depend on — it is not optional. `errors.py` is the entire
   error taxonomy (`MissingPriceError`, `DuplicateTransactionError`,
   `UnparseableRowError`, `NegativeHoldingError`) that Rule 4 of this project depends on.
   **Corrected:** both added; `app/engine/` now lists exactly the 11 files that exist
   today.
5. **The capabilities image conflates two different Gmail mechanisms**, and the plan
   inherited the conflation. `ingest/gmail_oauth.py` already exists — but its own
   docstring and `docs/INGESTION.md` are explicit that it is **not authorised for
   client use** until a Google CASA security assessment clears (USD 500–4,500/yr, 4–8
   weeks, recurring annually — a business/legal gate, not an engineering task). The
   client-facing mechanism is **forwarding** (`POST /ingest/email`), which genuinely does
   not exist yet. **Corrected:** the capability map and target tree now distinguish
   "forwarding webhook — real gap" from "OAuth mailbox scan — already built, dev-only,
   must not be wired into any router."
6. **"Zero Broker Credential Security" was listed as future work.** It is a current,
   `make lint`-enforced invariant (checks stored-credential field names across the repo,
   with one named exception for `gmail_oauth.py`) — not something to build. **Corrected:**
   moved to the "verified now" column.
7. **`trackr-backend/requirements.txt` breaks with the repo's existing tooling.** The root
   already has `pyproject.toml` with `uv.lock` and optional-dependency groups (`db`,
   `storage`, `pdf`, `gmail`) that map cleanly onto the layer packages. **Corrected:**
   `trackr-backend/pyproject.toml`, uv-managed, preserving the same extras split — in
   particular keeping the `gmail` extra isolated, given point 5.
8. **`make lint`'s three checks were not addressed.** No float in `engine/`, no
   cross-layer imports (`engine` must not import `ingest`/`api`/`db`/`storage`/`prices`),
   no stored credentials. These must be repointed at `trackr-backend/app/...` paths and
   continue to pass, not be silently dropped in the move.
9. **The golden-fixture verification claim doesn't hold in this checkout.**
   `fixtures/golden_portfolio.json` — the file `CLAUDE.md`'s acceptance table depends on —
   is **not present** in `fixtures/` right now (only `bhavcopy/` and `engine_cases.json`
   are). `tests/test_prices.py` has an uncommitted, in-progress change
   (`skipif(not GOLDEN_PATH.exists())`) that treats it as local-only. Phase 4's "verify
   golden portfolio benchmarks pass 100%" needs that file restored to this machine first —
   it is not guaranteed by the repo alone. This is a pre-existing gap, not one this
   restructuring creates; flagging it so it isn't rediscovered as a surprise later.
10. **Test count corrected**: 290 `test_` functions across 23 files in `tests/` (not
    "220+" — that wasn't wrong, just imprecise; the real number is now known and confirmed
    via `grep -rc "^def test_"`).

None of this changes the headline decision (FastAPI backend, Next.js frontend, dual
package). It changes what gets reused vs. rebuilt, and removes one change that would have
quietly reversed a decision already on record.

---

## Production Standards & Mandatory Rules

> [!IMPORTANT]
> **Mandatory Production Standards (Non-Negotiable):**
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake
>    return values, silent `try...except: pass` blocks, or hardcoded dummy objects to
>    swallow errors.
> 2. **Explicit & Graceful Error Handling**: Log rich structured context (traceback,
>    request ID, user ID) and return explicit, standardized HTTP error responses
>    (`400`, `401`, `403`, `404`, `409`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, DB connection strings, OAuth
>    credentials, JWT secrets, CORS origins, service hostnames, and storage paths MUST be
>    loaded dynamically from `.env` via `pydantic-settings`. Must operate strictly under
>    both `DEBUG=True` and `DEBUG=False`.
>    Note: today this is done ad hoc via `os.environ.get(...)` calls scattered across
>    `db/connection.py` (`DATABASE_URL`), `db/crypto.py` (`PORTFOLIO_ENCRYPTION_KEY`,
>    `PORTFOLIO_PAN_PEPPER`). `app/config.py`'s `Settings` model must use these **exact**
>    existing env var names as field names/aliases — introducing new names would silently
>    break every existing deployment script and the Makefile's `dev` target.

> [!IMPORTANT]
> **Core Architectural Invariants from `CLAUDE.md`:**
> 1. **Ledger Derivation**: Holdings and analytics metrics are NEVER stored as state in DB
>    tables; they are derived on read from the append-only `transactions` ledger.
> 2. **Money Precision**: Money is ALWAYS high-precision `Decimal` (Python
>    `decimal.Decimal`, Postgres `NUMERIC(20,6)`). Floating point currency math is
>    strictly forbidden — enforced today by `make lint`'s float-in-`engine/` check.
> 3. **ISIN Keying**: Securities are keyed strictly by ISIN, never by ticker symbol.
> 4. **Deduplication**: Every transaction carries a deterministic `dedupe_key` hash.
> 5. **No Missing Price Defaults**: Missing prices fail loudly (`MissingPriceError`,
>    surfaced as HTTP 409 naming the ISINs) rather than defaulting to ₹0.
> 6. **Zero Stored Broker Credentials**: No broker passwords, API tokens, or OTP secrets
>    stored in the system — enforced today by `make lint`'s credential-field-name check.

---

## Capability Alignment & Target Vision Map

The reference image at
`/home/hypthes/.gemini/antigravity-ide/brain/3d281374-546e-446f-8e67-97b7ee47dcf6/trackr_capabilities_overview_1786742843725.png`
undersold what's already built and conflated two distinct Gmail mechanisms. Corrected
mapping, verified directly against the code:

```
┌────────────────────────────────────────┬────────────────────────────────────────┐
│      WHAT IT CAN DO NOW (VERIFIED)      │        REMAINING TARGET WORK            │
├────────────────────────────────────────┼────────────────────────────────────────┤
│ • Pure Decimal Financial Engine         │ • Inbound Gmail *forwarding* webhook    │
│ • FIFO Lot Matching & Weighted Cost     │   (POST /ingest/email) — genuinely new  │
│ • PyXIRR Multi-Period Solver            │ • JWT auth (no auth layer exists today) │
│ • Zerodha CSV & PDF Contract Note       │ • Staging HTTP endpoints over the       │
│   parsers, with format-drift handling   │   existing db/imports.py workflow       │
│ • NSE/BSE Bhavcopy Daily Pipeline       │ • Side-by-side Dual-XIRR & FY-return    │
│   (both exchanges mandatory)            │   UI cards                              │
│ • Append-Only Ledger & Deduplication    │ • Automated Discrepancy Audits (CAS)    │
│ • Cross-source precedence arbitration   │ • Multi-Asset Seams (MF, Bonds, SGB)    │
│   (contract note beats tradebook)       │ • Production Next.js 14+ / Vercel UI    │
│ • DPDP compliance: consent, audit log,  │                                          │
│   privacy export/erase, retention       │                                          │
│ • Field-level encryption (PAN/demat)    │                                          │
│ • Document storage, local + S3/R2       │                                          │
│ • Zero Broker Credential Security       │                                          │
│   (`make lint`-enforced today, not a    │                                          │
│    future feature)                      │                                          │
│ • Gmail OAuth mailbox scan — exists,    │                                          │
│   but dev-only / CASA-gated. Not a      │                                          │
│   client-facing feature to build toward │                                          │
└────────────────────────────────────────┴────────────────────────────────────────┘
```

---

## Target Directory Structure (`trackr-backend/`)

```
Trackr-plus/
├── docs/
│   ├── structure_revamp_plan.md          # This master architecture document
│   └── BACKEND_REUSE_AND_GAP_ANALYSIS.md # Detailed code reuse & gap roadmap
│
├── trackr-backend/                       # Production FastAPI Application
│   ├── .env.example                      # 12-factor environment template (see note above
│   │                                      #   re: matching existing env var names exactly)
│   ├── pyproject.toml                    # uv-managed; mirrors root's optional-dep groups
│   │                                      #   (db, storage, pdf, gmail) — NOT requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── config.py                     # Pydantic-Settings (12-Factor env loader)
│       ├── database.py                   # Thin sync connection factory wrapping
│       │                                  #   db/connection.py's connect() — psycopg3,
│       │                                  #   per-request connection, no pool (matches
│       │                                  #   api/deps.py's existing, deliberate choice;
│       │                                  #   add pooling only if profiling demands it)
│       ├── main.py                       # FastAPI app, CORS, exception handlers.
│       │                                  #   Server-rendered `/`, `/ui/*` routes and
│       │                                  #   api/templates/ are RETIRED here — the
│       │                                  #   Next.js frontend takes over rendering; this
│       │                                  #   becomes a pure JSON API.
│       ├── securities.py                 # ISIN -> symbol/name/asset_class join at the
│       │                                  #   web boundary (from api/securities.py)
│       ├── auth/                         # JWT Authentication — genuinely new, no
│       │   │                              #   existing code to reuse here
│       │   ├── __init__.py
│       │   ├── repository.py             # Raw SQL against new users/sessions tables
│       │   ├── service.py                # Password hashing, JWT issue/verify
│       │   └── schemas.py                # Pydantic request/response DTOs
│       ├── engine/                       # Pure Python, no ORM/I/O — reused verbatim
│       │   ├── __init__.py
│       │   ├── dedupe.py
│       │   ├── errors.py                 # MissingPriceError, DuplicateTransactionError,
│       │   │                              #   UnparseableRowError, NegativeHoldingError
│       │   ├── holdings.py
│       │   ├── ledger.py                 # Shared replay ordering — both FIFO and
│       │   │                              #   weighted-average costing depend on this
│       │   ├── lots.py
│       │   ├── realised.py
│       │   ├── reconcile.py
│       │   ├── snapshot.py
│       │   ├── types.py
│       │   ├── valuation.py
│       │   └── xirr.py
│       ├── ingest/                       # Parsers + inbound email webhook
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── webhook.py                # NEW — inbound-parse webhook handler for
│       │   │                              #   POST /ingest/email (forwarding, not OAuth)
│       │   ├── zerodha_contract_note.py
│       │   ├── zerodha_tradebook.py
│       │   └── gmail_oauth.py            # Reused as-is, `gmail` extra only. NEVER wired
│       │                                  #   into a router; dev-only per docs/INGESTION.md
│       ├── prices/                       # Bhavcopy exchange pipeline — reused verbatim
│       │   ├── __init__.py
│       │   ├── alerts.py
│       │   ├── pipe.py
│       │   ├── sources.py
│       │   └── udiff.py
│       ├── storage/                      # Document store — reused verbatim
│       │   ├── __init__.py
│       │   ├── base.py                   # DocumentStore protocol
│       │   ├── keys.py                   # Content-addressed key scheme
│       │   ├── local.py
│       │   └── s3.py                     # R2/S3-compatible backend
│       ├── db/                           # Persistence — raw SQL, reused verbatim +
│       │   │                              #   one new migration for auth tables
│       │   ├── __init__.py
│       │   ├── connection.py             # DatabaseNotConfiguredError, connect()
│       │   ├── repository.py             # load_transactions, etc.
│       │   ├── migrate.py                # Applies migrations/*.sql in order
│       │   ├── load_golden.py            # Golden-fixture seeder
│       │   ├── audit.py                  # DPDP access log / SEBI record
│       │   ├── consent.py                # client_consent enforcement
│       │   ├── crypto.py                 # PAN/demat field-level encryption
│       │   ├── privacy.py                # GET /privacy/export, POST /privacy/erase
│       │   ├── retention.py              # SEBI 5-year retention rules
│       │   ├── grievance.py
│       │   ├── documents.py              # store_document (object write, then row)
│       │   ├── imports.py                # stage / review_batch / promote_batch /
│       │   │                              #   discard — the staging workflow itself
│       │   │                              #   already exists; only the HTTP layer is new
│       │   ├── precedence.py             # Contract-note-beats-tradebook arbitration
│       │   ├── prices.py                 # latest_prices, staleness window
│       │   └── migrations/
│       │       ├── 001_core.sql
│       │       ├── 002_compliance.sql
│       │       ├── 003_documents.sql
│       │       ├── 004_grievance.sql
│       │       ├── 005_import_batch.sql
│       │       ├── 006_source_precedence.sql
│       │       ├── 007_transaction_seq.sql
│       │       └── 008_auth.sql          # NEW — users/sessions for JWT auth
│       ├── routers/                      # FastAPI controllers, aligned to
│       │   │                              #   contracts/openapi.yaml's actual paths
│       │   ├── __init__.py
│       │   ├── auth.py                   # /auth/register, /auth/login, /auth/me — NEW
│       │   ├── holdings.py               # /investors/{id}/holdings
│       │   ├── transactions.py           # /investors/{id}/transactions, /lots, /realised
│       │   ├── ingest.py                 # /ingest/csv, /ingest/email (NEW),
│       │   │                              #   /ingest/stage, /review, /promote (NEW HTTP
│       │   │                              #   layer over existing db/imports.py)
│       │   └── analytical.py             # /investors/{id}/performance, /reconcile,
│       │                                  #   /ops/prices/refresh
│       └── schemas/                      # Pydantic request/response DTOs
│           ├── __init__.py
│           ├── analytical.py
│           ├── auth.py
│           ├── holdings.py
│           ├── ingest.py                 # NEW — staging review/promote payloads
│           └── transactions.py
│
└── trackr-frontend/                      # Next.js 14+ App Router Frontend (Vercel)
    ├── package.json
    ├── tailwind.config.js
    └── app/
        ├── layout.tsx
        ├── page.tsx                      # Dashboard Summary
        ├── holdings/page.tsx             # Dense Holdings & FIFO Lot Table
        ├── performance/page.tsx          # Dual-XIRR & Benchmark Visualizations
        ├── import/page.tsx               # Multi-file Tradebook & PDF Ingestion,
        │                                  #   staging review/promote UI
        └── components/
            ├── HoldingsTable.tsx         # Indian currency formatted table (₹)
            ├── SummaryCards.tsx          # Invested, Value, Dual-XIRR cards
            ├── AllocationPie.tsx         # Asset class donut chart
            └── XirrTrajectory.tsx        # Portfolio performance vs NIFTY 50

Recommendation (not mandatory): generate the frontend's API client/types from
contracts/openapi.yaml (e.g. openapi-typescript) rather than hand-written fetch calls,
per docs/ARCHITECTURE.md's "Swapping the stack" guidance — keeps the two packages from
drifting out of sync with the contract that's supposed to define the boundary.
```

---

## Execution Workflow Roadmap

### Phase 1: Plan Validation & Alignment — done in this revision
1. Reviewed `docs/structure_revamp_plan.md` against the actual repository, not just the
   target-vision image.
2. Corrected the ten issues listed in "Corrections made in this review" above.
3. **Awaiting explicit user confirmation** on the raw-SQL-vs-ORM correction (item 1) before
   any directory is created, since it's the one change that reverses what was drafted
   rather than merely filling a gap.

### Phase 2: Directory Skeleton Creation (Non-Destructive)
1. Create the backend and frontend directory structures using `mkdir -p` only — no code,
   no `__init__.py` contents beyond empty files.
2. Create empty `.gitkeep` files in leaf subdirectories to establish the structure in git.

### Phase 3: Code Reuse & Implementation Gap Assessment
1. Create `docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md` detailing, module by module:
   * How each of the 14 `db/` modules, 11 `engine/` modules, 4 `storage/` modules, 4
     `prices/` modules, and 4 `ingest/` modules (including the dev-only `gmail_oauth.py`)
     maps into `trackr-backend/app/`.
   * What is genuinely new: `POST /ingest/email` webhook handler, JWT auth
     (`app/auth/`), `008_auth.sql`, the staging HTTP endpoints (`review`/`promote`)
     over the already-working `db/imports.py`, and `app/config.py`.
   * Exact zero-mock error-handling strategy per Rule 2, and how `.env`-driven config
     (Rule 3) maps onto the existing `DATABASE_URL` / `PORTFOLIO_ENCRYPTION_KEY` /
     `PORTFOLIO_PAN_PEPPER` env vars rather than inventing new names.
   * How `make lint`'s three checks get repointed at `trackr-backend/app/...` and
     continue to pass.

### Phase 4: Production Implementation & Verification
1. Implement `trackr-backend` modules adhering strictly to 12-Factor config and
   zero-mock error handling.
2. Run `.venv/bin/pytest` — 290 tests across 23 files today; all must continue to pass
   after the move (import paths inside `tests/` will need updating, this is a real
   migration, not a copy).
3. Before claiming the golden-portfolio acceptance benchmarks pass: confirm
   `fixtures/golden_portfolio.json` is present on the machine running the test — it is
   not currently in this checkout (local-only, per the in-progress change to
   `tests/test_prices.py`). If absent, say so explicitly rather than reporting a skip as
   a pass.
