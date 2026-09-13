# Backend Reuse & Implementation Gap Analysis

> ### ⚠️ HISTORICAL ARCHIVE — not a specification, and not a to-do list
>
> This is **a module-by-module plan for that same split, since executed**. It describes the repository **as it was on the day it was written**
> and has not been maintained since. Live code and tests cite it for provenance, which is
> why it is kept.
>
> **Do not treat anything here as a requirement, and never open a session by working
> through it.** Where this file and `docs/ARCHITECTURE_INVARIANTS.md`, `docs/ENGINE_SPEC.md`,
> `docs/DATA_MODEL.md` or `docs/INGESTION.md` disagree, **those win**. Where they and the
> code disagree, **the code wins**. Start from `CLAUDE.md`.

Companion to `docs/structure_revamp_plan.md`. That document says *where* things go; this
one says, module by module, *what is reused verbatim, what is modified, and what is
genuinely new* — so the move from the current flat layout to `trackr-backend/app/` is a
relocation of working, tested code plus a small, explicit set of additions, not a
rewrite.

Scope: this is a planning document. No files are moved by writing it. The move itself
(Phase 4 of `structure_revamp_plan.md`) touches `engine/` and the schema-adjacent `db/`
layer, so per `CLAUDE.md` ("Plan mode for anything touching the schema or the engine")
it should be confirmed as its own step before execution, separately from this analysis.

---

## 1. Reuse map

Legend: **Verbatim** = file moves with no logic change (import paths only). **Wrapped**
= existing logic reused unchanged, called from new code above it. **New** = does not
exist today.

### `engine/` → `trackr-backend/app/engine/` — all 11 files, Verbatim

| File | What it does | Reuse note |
|---|---|---|
| `types.py` | `Transaction`, `Holding`, `Lot`, etc. dataclasses | No changes. This is the schema-in-code; `schema/*.schema.json` must keep agreeing with it (`tests/test_types_match_schema.py` enforces this today and must keep passing post-move). |
| `dedupe.py` | `make_dedupe_key` | Verbatim. |
| `ledger.py` | Shared replay ordering (`ordered()`) | Verbatim. Both FIFO and weighted-average costing import this — moving it without moving its callers in lockstep would break both. |
| `lots.py`, `holdings.py`, `realised.py`, `valuation.py`, `reconcile.py`, `snapshot.py`, `xirr.py` | The calculation layer | Verbatim. Pure functions, no I/O — nothing here should need to change to live under `app/`. |
| `errors.py` | `MissingPriceError`, `DuplicateTransactionError`, `UnparseableRowError`, `NegativeHoldingError` | Verbatim. See §3 for how `app/main.py`'s exception handlers map these to HTTP status codes — that's new code, but it wraps these unchanged classes rather than replacing them. |

**Nothing in `engine/` is a gap.** It is the one layer already complete against
`docs/ENGINE_SPEC.md`. The only new engine-adjacent work is wiring its exceptions to
HTTP responses, which belongs in `app/main.py`/`app/routers/`, not in `engine/` itself.

### `db/` → `trackr-backend/app/db/` — 14 files Verbatim + 1 new migration

| File | What it does | Reuse note |
|---|---|---|
| `connection.py` | `connect()`, `DatabaseNotConfiguredError` | Verbatim. `app/database.py` is a thin wrapper around this, not a replacement (see §2). |
| `repository.py` | `load_transactions` and the other ledger read paths `api/main.py` calls today | Verbatim. |
| `migrate.py` | Applies `migrations/*.sql` in numbered order | Verbatim. Extended with one new entry, `008_auth.sql` (new, see §2). |
| `load_golden.py` | Seeds the golden-fixture investor/prices for local dev | Verbatim. |
| `audit.py` | `audit_log` writes (DPDP access log, SEBI record) | Verbatim. Already the pattern every new mutating endpoint should call into — no new audit mechanism needed for the auth or webhook routes, they call this. |
| `consent.py` | `client_consent` enforcement | Verbatim. |
| `crypto.py` | Field-level PAN/demat encryption (`PORTFOLIO_ENCRYPTION_KEY`, `PORTFOLIO_PAN_PEPPER`) | Verbatim. `app/config.py`'s `Settings` must expose these two env vars under these exact names (see §4) — this module already raises rather than defaulting when they're missing, which is the correct behaviour to preserve, not rebuild. |
| `privacy.py` | `GET /privacy/export`, `POST /privacy/erase` semantics | Verbatim logic. **Wrapped**: needs a router (`app/routers/`) exposing it over HTTP — that router is new, the logic is not. Not in the original task's named gap list; flagging because `structure_revamp_plan.md`'s router list doesn't currently allocate a home for it. Suggest `app/routers/privacy.py` or folding into `auth.py` alongside `/auth/me`. |
| `retention.py` | SEBI 5-year retention rules | Verbatim. |
| `grievance.py` | Grievance handling | Verbatim. No router exists for this yet either — same flag as `privacy.py`. Out of scope for this pass unless the user wants it wired up now; noting it so it isn't lost. |
| `documents.py` | `store_document` — object write, then row (the ordering that keeps a storage bug recoverable) | Verbatim. Depends on `storage/` (below). |
| `imports.py` | `stage`, `review_batch`, `promote_batch`, `discard` — the entire staging/promote state machine | Verbatim. **This is the load-bearing point of the whole "staging endpoints" gap**: the workflow already exists and is tested (`tests/test_db_imports.py`); the only new work is the HTTP layer calling it (§3). |
| `precedence.py` | Contract-note-beats-tradebook arbitration | Verbatim. Interim measure per its own docstring (the real fix is a `dedupe_key` that collides across sources); not this pass's problem to solve, just to not lose in the move. |
| `prices.py` | `latest_prices`, staleness window (`MAX_PRICE_STALENESS_DAYS`) | Verbatim. |

Migrations `001_core.sql` through `007_transaction_seq.sql` move verbatim into
`app/db/migrations/`. `008_auth.sql` is new (§2).

### `ingest/` → `trackr-backend/app/ingest/` — 4 files Verbatim + 1 New

| File | What it does | Reuse note |
|---|---|---|
| `base.py` | `Adapter` protocol, `REVIEW_THRESHOLD`, `ParseResult` | Verbatim. |
| `zerodha_tradebook.py` | CSV tradebook parser | Verbatim. |
| `zerodha_contract_note.py` | PDF contract-note parser, pro-rata charge apportionment, two-layout support | Verbatim. |
| `gmail_oauth.py` | Retroactive OAuth mailbox scan | Verbatim **but never wired into a router**. Ship it under the `gmail` extra, exactly as today, restricted to developer-only use per its own docstring and `docs/INGESTION.md`. This is a hard constraint, not a style preference — see the `make lint` credential exception carved out specifically for this one file. |
| `webhook.py` | Inbound-parse handler for `POST /ingest/email` | **New.** Resolves investor + adapter from the `to` address, stores the raw payload via `db/documents.store_document` before parsing (per `docs/INGESTION.md` "Where documents land"), unlocks the PDF per the per-broker password rule, calls the existing adapter's `.parse()`, and stages via `db/imports.stage` — it does not itself parse or decide precedence; it is glue over modules that already exist. |

### `prices/` → `trackr-backend/app/prices/` — all 4 files, Verbatim

`alerts.py`, `pipe.py`, `sources.py`, `udiff.py` move unchanged. Note from
`docs/INGESTION.md`: **alert delivery is not wired today** — `alerts.py` defines the
notifier and `pipe.py` calls it on every failure path, but the default only logs. If
"automated discrepancy audits" / production alerting is in scope for this phase, wiring
a real notifier here is a named gap, not a move.

### `storage/` → `trackr-backend/app/storage/` — all 4 files, Verbatim

`base.py` (the `DocumentStore` protocol), `keys.py` (content-addressed key scheme),
`local.py`, `s3.py` (R2/S3-compatible backend, exercised against `moto` in tests). No
changes needed — this package was simply missing from the original plan's target tree
entirely; it has a home now.

### `api/` → split across `app/main.py`, `app/securities.py`, `app/routers/`

| Current file | Where it goes | Reuse note |
|---|---|---|
| `api/deps.py` | `app/database.py` (the `conn()` context manager) + a small `app/schemas/_convert.py` or inline helpers (the `money()`/`rate()` Decimal↔JSON boundary functions) | Verbatim logic, relocated. These two functions are the entire "Decimal crosses as string, ratio crosses as float" boundary rule — keep them exactly as commented, do not reimplement. |
| `api/securities.py` | `app/securities.py` | Verbatim. |
| `api/main.py` — JSON routes (`/investors`, `/investors/{id}/summary`, `/investors/{id}/holdings`) | Split into `app/routers/holdings.py`, `app/routers/transactions.py`, `app/routers/analytical.py` per `contracts/openapi.yaml`'s actual path list | Logic reused; only the FastAPI route registration changes shape (one file → several routers included into `app/main.py`). |
| `api/main.py` — server-rendered routes (`/`, `/ui/{investor_id}`, `/ui/{investor_id}/equities`) + `api/templates/*.html` | **Retired**, not moved | `trackr-frontend/` replaces server-rendered HTML. Carrying the Jinja routes into `trackr-backend/app/main.py` would mean maintaining two UIs; `app/main.py` becomes a pure JSON API. Confirm with the user before deleting `api/templates/` outright — it's live, working code, not a stub. |

---

## 2. Genuinely new work

Nothing below has an existing implementation to reuse. Each is scoped to be as thin as
possible over the modules in §1.

| Component | Scope | Depends on |
|---|---|---|
| `app/config.py` | `pydantic-settings` `Settings` class. Fields must alias the **existing** env var names — `DATABASE_URL`, `PORTFOLIO_ENCRYPTION_KEY`, `PORTFOLIO_PAN_PEPPER` — plus new ones this phase introduces: `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_SECONDS`, `CORS_ORIGINS`, `DEBUG`. | Nothing — foundational, build first. |
| `app/auth/` | Password hashing (`passlib`/`bcrypt`), JWT issue/verify, `/auth/register`, `/auth/login`, `/auth/me`. Stores users in a new table via raw SQL (per the confirmed persistence decision), never an ORM model. | `app/config.py` for `JWT_SECRET`; `db/migrations/008_auth.sql`. |
| `db/migrations/008_auth.sql` | `users` and `sessions`/`refresh_tokens` tables. Applied by the existing `db/migrate.py` — no Alembic. | None. |
| `app/ingest/webhook.py` | `POST /ingest/email` handler (see §1 `ingest/` table). | `db/documents`, `db/imports`, `ingest/base.Adapter`, per-broker PDF password rules from `docs/INGESTION.md`. |
| `app/routers/ingest.py` — staging endpoints | HTTP layer over `db/imports.review_batch` / `promote_batch` / `discard`: `GET /ingest/stage/{batch_id}`, `POST /ingest/stage/{batch_id}/promote`, `POST /ingest/stage/{batch_id}/discard`. `promote` must carry `actor_uid` from the authenticated JWT — this is the first place auth and the ledger actually meet. | `app/auth/` (for `actor_uid`), `db/imports.py` (unchanged). |
| `app/schemas/ingest.py` | Pydantic DTOs for stage/review/promote payloads. | `engine/types.py`'s dataclasses as the source of truth for field shapes. |
| `trackr-frontend/` | Entire Next.js app. Nothing to reuse — `api/templates/*.html` is Jinja, not portable. | `contracts/openapi.yaml` as the contract to build against (recommend generating a typed client from it, per `docs/ARCHITECTURE.md`). |

Not in the original task's four named gaps, but surfaced by this mapping — flagged for
a scoping decision, not built by default:
- HTTP routers for `db/privacy.py` (DPDP export/erase) and `db/grievance.py`.
- A real alert notifier for `prices/alerts.py` (currently log-only).

---

## 3. Error handling enforcement (Rule 2)

A single exception-handling layer in `app/main.py`, registered once, translating the
existing exception taxonomy — none of it re-thrown as something generic:

| Exception (unchanged, from `engine/errors.py` / `db/imports.py` / `storage/base.py`) | HTTP status | Body |
|---|---|---|
| `engine.errors.MissingPriceError` | 409 | ISINs named, per `CLAUDE.md` Rule 4 — never silently 200 with a zero value |
| `engine.errors.NegativeHoldingError` | 409 | ISIN + quantity |
| `engine.errors.DuplicateTransactionError` | *not an error* — caught in the import path and counted, never surfaced as a 4xx/5xx |
| `engine.errors.UnparseableRowError` | 422, one entry per row, rest of the batch still processes | Row number + reason |
| `db.imports.BatchNotFoundError` | 404 | |
| `db.imports.BatchAlreadyResolvedError` | 409 | |
| `db.connection.DatabaseNotConfiguredError` | 500 | Logged with full traceback + request ID server-side; client sees a generic message, never the connection string |
| `storage.base.ObjectNotFoundError` | 404 | |
| `storage.base.SignatureError` | 403 | |
| Auth: bad credentials | 401 | |
| Auth: valid token, insufficient scope | 403 | |
| JWT malformed/expired | 401 | |
| Rate limiting (new, if added this phase) | 429 | |
| Anything unhandled | 500 | Structured log: traceback, request ID, authenticated user ID if present, route. Never a bare `except: pass` — this is the one hard rule from the task brief with zero exceptions. |

Every handler logs before responding: request ID (new middleware, generated per
request), route, authenticated user ID (if any), and the full traceback for 5xx. This
is new code, but it is the FastAPI-idiomatic version of what `db/audit.py` already does
for data mutations — the same "never silent" posture, applied to the transport layer.

---

## 4. 12-Factor configuration enforcement (Rule 3)

`app/config.py` is the single `Settings` object every module reads from — no module
below it calls `os.environ` directly once this lands (today, `db/connection.py` and
`db/crypto.py` do, directly; that continues to work unchanged since `Settings` sources
from the same env vars, but new code should receive config via dependency injection from
`app/config.py`, not read the environment itself).

Required for both `DEBUG=True` and `DEBUG=False`:
- `DATABASE_URL` — no default, matches `db/connection.py`'s existing
  `DatabaseNotConfiguredError` behaviour (fail loud, never fall back to localhost).
- `PORTFOLIO_ENCRYPTION_KEY`, `PORTFOLIO_PAN_PEPPER` — no defaults, matches
  `db/crypto.py`'s existing behaviour.
- `JWT_SECRET` — no default. A `DEBUG=True` fallback secret is explicitly the kind of
  thing Rule 1 (no dummy fallbacks) forbids; local dev sets a real value in `.env`.
- `CORS_ORIGINS` — comma-separated list, environment-specific (`localhost:3000` for dev,
  the Vercel domain for prod).
- Storage backend selection (`local` vs `s3`) plus `S3_*` / `R2_*` vars when the `s3`
  backend is selected — mirrors `storage/s3.py`'s existing parameter set.

`app/.env.example` documents every one of these with the exact names above — matching
existing env vars is what keeps this from silently breaking today's Makefile (`make dev`
→ `uvicorn api.main:app --reload`) and any deployment scripts already using them.

---

## 5. Invariant preservation checklist

Since §1 is almost entirely "Verbatim," most invariants carry over mechanically. The
places that actually get new code are where they need explicit attention:

- **Decimal precision**: `api/deps.py`'s `money()`/`rate()` boundary functions move
  verbatim (§1) — this is the only place Decimal crosses into JSON today and must stay
  the only place. New Pydantic schemas (`app/schemas/`) must type money fields as `str`
  (matching `schema/*.schema.json`'s `$defs/decimal`), never `float`.
- **ISIN keying**: untouched — no new code introduces a ticker-keyed lookup.
- **Append-only ledger**: untouched — `app/routers/ingest.py`'s new `promote` endpoint
  calls `db/imports.promote_batch`, which is the *only* path that writes transactions,
  unchanged from today.
- **Zero broker credentials**: the new `users`/`sessions` auth tables store the
  *investor's own login* to this application, not broker credentials — this is not the
  thing Rule 6 / `make lint`'s credential check exists to prevent, but the migration and
  the auth module must still avoid field names the lint regex would (correctly) flag
  (`api_secret`, `access_token`, etc. — a session/JWT concept needs different naming,
  e.g. `session_token_hash`, stored hashed, never the raw token).
- **`make lint`**: needs its three `grep` targets (`engine/`, cross-layer import check,
  credential field names) repointed at `trackr-backend/app/...` when the move happens.
  Until `engine/`, `db/`, etc. at the repo root are deleted, run lint against **both**
  paths during the transition rather than dropping coverage of the old location early.

---

## 6. What this document does not decide

- Whether `api/templates/` and the Jinja UI get deleted immediately on cutover or kept
  running in parallel until `trackr-frontend/` reaches feature parity. Recommend parallel
  running — it's the one path currently proven against the golden fixture.
- Whether `db/privacy.py` and `db/grievance.py` get routers in this phase or a later one
  (flagged in §2, not in the original four named gaps).
- The exact test layout after the move (whether `tests/` stays at the repo root
  importing `trackr_backend.app...`, or relocates under `trackr-backend/tests/`). Either
  works; pick one and update all 23 test files' imports in the same commit as the file
  move, not incrementally — a half-moved import graph is worse than not starting.
