# Build Plan

Twelve sessions. One session ≈ one evening, one commit, one working thing.

**Rules for every session:** use plan mode for anything touching schema or engine.
Write the failing test first, from `ENGINE_SPEC.md`. Run `make test` before commit.
Never move to the next session with a red test.

---

## Phase A — the engine (sessions 1–4)

Build the engine before any UI, any database, any web framework. The engine is pure
functions and can be fully tested with zero infrastructure.

### Session 1 — Types and skeleton
- `Transaction`, `Holding`, `Lot`, `Realised`, `Snapshot` as dataclasses, generated
  from `schema/*.schema.json`.
- `Decimal` everywhere. Add a lint rule or test that fails if `float` appears in
  `engine/`.
- Wire `make test` to run `fixtures/engine_cases.json`. All red. That is correct.

**Done when:** `make test` runs and reports 9 failing cases by name.

### Session 2 — `compute_holdings` + `compute_lots`
- Implement §1 and §3 of `ENGINE_SPEC.md`.
- Cases 1, 2, 3, 6 must pass.

**Done when:** the bonus case passes — quantity 400, invested unchanged at 50,000,
average cost 125. If invested changed, the cost-pool rule is wrong.

### Session 3 — `compute_xirr` (both variants) + `compute_realised`
- §4 and §3. Use `pyxirr`; do not hand-roll a solver.
- Cases 4, 5, 6 must pass.
- **Both `xirr_all` and `xirr_holdings` from the start.** Not one now and one later.

**Done when:** case 4 returns 0.20 ± 0.0005, and case 5 *raises* rather than returning
a number.

### Session 4 — `reconcile` + the golden fixture
- §7. Cases 7, 8 pass.
- Then run `fixtures/golden_portfolio.json` end to end.

**Done when:**
```
invested       1579245.74
market_value   1360575.42
xirr_all         -0.174361  (± 0.0001)
xirr_holdings    -0.348107  (± 0.0001)
```
All four exact. **Do not proceed until this passes.** Everything above this line is
built on it.

---

## Phase B — persistence and ingestion (sessions 5–8)

### Session 5 — Database
- Postgres schema from `DATA_MODEL.md`. Migrations, not hand-run SQL.
- **`CREATE UNIQUE INDEX ON transaction (dedupe_key)`** — the single most important
  line in the schema.
- Repository layer: `save_transactions()`, `load_transactions()`. Nothing else.
- Case 9 (duplicate import is a no-op) must pass against the real database.

### Session 5b — Compliance scaffolding (do not skip)
- `client_consent`, `audit_log`, `investor_secret` tables.
- Field-level encryption on PAN/demat. Audit-log write on every mutation.
- Data export + erasure routines for a single investor.
- Retention config: default 5 years, legal-hold flag.

**Why here and not later:** retrofitting consent and audit trails after client data has
landed means backfilling records that cannot be backfilled honestly.

### Session 6 — CSV / tradebook adapter
- `Adapter` protocol from `INGESTION.md`.
- Zerodha tradebook parser. Multi-file upload, merge, dedupe.
- Validation-first: reject bad rows with row numbers, import the rest.
- **Stage to `import_batch.log_entries` with confidence scores. Never auto-commit.**
  A second explicit action promotes staged rows to transactions.

**Done when:** the 5 real Console exports load to exactly 324 unique transactions, and
re-uploading all 5 inserts 0.

> **Status:** only FOUR exports exist on disk — 259 rows, 2022-10-19 to 2026-01-28. The
> FY2026-27 file is absent and holds the remaining ~65 trades, including all 25 KDL rows.
> 324 is a real, cross-checked number (the contract notes reproduce it exactly); it simply
> lives partly in a file nobody has downloaded. `tests/test_db_imports.py` asserts
> `EXPECTED_TRADEBOOK_ROWS = 259` with the reason attached — drop the fifth export in and
> change that one constant. The half of the gate that actually matters, re-importing
> inserting zero, passes today and does not depend on the count.

### Session 7 — Price pipe
- NSE + BSE bhavcopy fetch, merged, keyed by ISIN, NSE wins conflicts.
- Cron entry. Failure alerts by email; never silently serves stale prices.
- Backfill for every ISIN in the ledger.

**Done when:** every held ISIN has a price, *including* the two that appear on only one
exchange — `INE0N6U01018` and `INE0O4R01018`.

> **Correction, from the live bhavcopy:** these are not both BSE-only. `INE0N6U01018`
> (KALYANI-M) is **BSE-only**; `INE0O4R01018` (KDL-SM) is **NSE-only**. The gate is
> stronger than originally written — fetching only NSE loses KALYANI-M, fetching only BSE
> loses KDL-SM, so either single-exchange implementation fails on a *different* holding.
> Both directions are asserted in `tests/test_prices.py`.

### Session 8 — Manual entry + corrections
- Form → `Transaction`. All ten `txn_type` values, including the awkward ones:
  off-market transfer, IPO allotment, buyback, rights, transfer-in **with cost**.
- Correction flow: reversing row, never an edit.

---

## Phase C — API and UI (sessions 9–10)

### Session 9 — API
- Implement `contracts/openapi.yaml`. FastAPI will regenerate it; diff the two and
  reconcile any drift.
- No `PUT /holdings`. No `DELETE /transactions`. If either appears, the architecture
  broke.
- The holdings response carries `cost_estimated` (see `schema/holding.schema.json`). Any
  consumer showing `invested` or `unrealised` must be able to show that flag too.

### Session 10 — Dashboard
- Server-rendered. Investor list → holdings table → performance.
- Mandatory: **both XIRRs side by side**, never one alone.
- Mandatory: **`cost_estimated` rendered per row** — "cost verified" vs "cost estimated".
  Two golden positions (KDL-SM, IGIL) reach their invested figure on broker-stated cost
  rather than replayed cost. An estimate shown unlabelled reads as a fact.
- Headline **"XIRR this FY"** beside `xirr_all` and `xirr_holdings`, never replacing the
  pair — `engine.xirr.compute_fy_xirr`. Its `opening_value` must be the market value on
  1 April, from a stored snapshot; where no snapshot exists, omit the metric rather than
  substitute today's value, which would count the year's gain as if it pre-existed.
- Mei Capital palette: Ink Navy `#1B2A41`, Cream `#F5F0E6`, Brass `#B08D3E`,
  Newsreader headings.

---

## Phase D — automation (sessions 11–12)

### Session 11 — Gmail forwarding
- Inbound-parse webhook → `POST /ingest/email`.
- Address scheme `{code}-{broker}-{doctype}@in.yourdomain.com`. Route by address only.
- Per-broker PDF password rules (Zerodha/Groww uppercase PAN, Upstox lowercase).
- Store raw payload before parsing.
- Client setup walkthrough page with the Gmail verification-code flow.

### Session 12 — Contract note parser + reconciliation loop
- `pdfplumber`, ISIN-anchored extraction, per-broker plugins.
- Keep real redacted PDFs as permanent fixtures.
- Monthly reconciliation job → email digest of discrepancies.

**Done when:** forwarding a real contract note updates holdings with no manual step,
and forwarding it twice changes nothing.

---

## Definition of done for the MVP

- [ ] `fixtures/golden_portfolio.json` passes exactly
- [ ] All 9 engine cases pass
- [ ] Re-importing any file inserts zero rows
- [ ] Both XIRRs displayed together, never one alone
- [ ] A missing price raises; the UI names the ISINs
- [ ] Prices refresh daily and alert on failure
- [ ] Reconciliation runs monthly and emails discrepancies
- [ ] No credentials stored anywhere in the codebase or database
- [ ] `grep -r "float" engine/` returns nothing
- [ ] Postgres backup taken *and* a restore actually tested
- [ ] `client_consent` populated; export + erasure routines tested
- [ ] `audit_log` writing on every mutation, retention set to 5 years
- [ ] No adapter commits without human review (manual entry excepted)

---

## What to build next (Phase 2, in value order)

1. **Daily snapshots** — unlocks the historical value chart and TWRR
2. **Benchmark comparison** — cash-flow-replicated NIFTY 50 TRI (`ENGINE_SPEC` §6)
3. **Dividends** — a real gap: no demat statement or broker API carries them
4. **CAS adapter** — multi-broker reconciliation without asking for more files
5. **Capital gains** — Section 112A grandfathering, bonus stripping, demerger ratios
6. **Attribution** — which holdings drove the return; the first real intelligence
7. **Mutual funds** — the `asset_class` seam already exists

Resist all seven until the MVP has run for a month on real data. What you actually
reach for will not be what you predicted.
