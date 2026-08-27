# Trackr-Plus Phase 2: Analytics Depth — Overview & Status

Generated 2026-08-18, at the start of Phase 2, as a skeleton — before any Phase 2 code
existed. **Updated 2026-08-20** against the actual state of the working tree, not
assumption: every claim below was checked directly against the code, the migrations,
`contracts/openapi.yaml`, and a real test run (`.venv/bin/pytest tests/ -q -rs` →
**460 passed, 246 skipped, 1 deselected, 0 failed**; `make test` with the venv on
`PATH` → all four suites plus `make lint` pass, ruff included). This is now much closer
to `docs/trackr_plus_phase1_overview.md`'s role than its own original one: an audit of
finished work, not a plan for unstarted work.

**The headline change since 2026-08-18: seven of the eight Phase 2 features are built,
tested, and committed. The eighth (contribution analysis) is built and tested but sits
uncommitted in the working tree right now.** See §3 for the file-by-file evidence and
§7 for what genuinely remains — it is a short list, and none of it is "write the
feature," it is "commit it," "run it against a real database once," "close the one
named sub-feature nobody built yet," and "fix a Phase-1 regression a field test just
found that blocks every one of these features from ever seeing a real user's data."

**Read this before starting any further Phase 2 or closeout session.** `docs/
PHASE2_PROMPTS.md` has been rewritten to match — it no longer contains the original
eight build prompts (they're done; kept here as a record instead) but a short closeout
list for what §7 below identifies as still open.

---

## 1. Executive Summary & Phase Goals

**Phase 1 is closed** — confirmed again as part of this update, not re-litigated.

**What Phase 2 was scoped to be.** Per `docs/FEATURE_BACKLOG.md`'s Phase 2 table — the
document `CLAUDE.md` designates as the tie-breaker whenever another doc disagrees about
scope — Phase 2 is **"Analytics depth (still equities)"**: eight features that deepen
what the system can say about a portfolio that is already correctly tracked. That table
has itself been edited since 2026-08-18 (compare its current text to what this document
originally quoted): the "Sector / market-cap breakdown" line has been split, because
sector allocation turned out to already be Phase 1 scope (`docs/FEATURE_BACKLOG.md`'s
Phase 1 table has always carried "Allocation (by holding, sector)") — building it this
phase closed a standing Phase 1 gap as much as it delivered a Phase 2 one. What remains
genuinely Phase 2 and **unbuilt** under that line is market-cap bucketing specifically
— see §7.

**What Phase 2 actually delivered, in one paragraph.** Daily portfolio-level snapshots
are persisted and preferred over live recomputation; the Dashboard has a real
historical value line chart with honest gaps; NIFTY 50 TRI benchmark XIRR is computed
by cash-flow replication and shown beside the portfolio's own XIRR, never as a bare
index CAGR; four fixed-calendar trailing XIRR windows (FY/1Y/3Y/5Y) sit beside the
existing all-time and onboarding-period XIRR; TWRR is computed via a chaining
convention that was genuinely undefined at the start of this phase and is now pinned
in `docs/ENGINE_SPEC.md` §5 with a worked example, shown beside XIRR on the same
windows; dividends have a per-ISIN, per-financial-year summary on the holding detail
page; sector allocation is real (NSE-sourced, ~750-company coverage, honest
"Unclassified" slice for anything outside it) instead of Phase 1's documented
single-slice placeholder; and contribution analysis — the first genuine
intelligence-layer feature per `docs/PRODUCT_VISION.md` — has a formula that was
likewise undefined at the start of this phase, is now pinned in a new `docs/
ENGINE_SPEC.md` §10 with a worked example and an explicit, confirmed decision on every
open question §4 originally flagged, and has a working ranked contribution page.

**What Phase 2 is not, still.** Not Phase 3 (tax engine), not Phase 4 (a second asset
class), not a CAS adapter. Nothing built this phase touched either boundary — checked
directly, not assumed: no new `asset_class` code is used anywhere in engine or router
code, and no capital-gains logic exists under `app/engine/`.

**The persisted-derivation nuance from the original plan held.** `portfolio_snapshot`
(migration `010_portfolio_snapshots.sql`) stores portfolio-level totals only, grained
by `(investor_id, as_of, advised_only)` — the `advised_only` decision this document
originally flagged as needing a call was made and is worth reading directly from the
migration's own comment, because it explains *why* rather than just recording the
choice: an adviser-restricted ledger is a materially different set of transactions,
not a display filter over the same one, so it gets its own row. A second, unrelated
persisted table appeared this phase that the original plan didn't anticipate:
`index_level` (migration `011_index_level.sql`), holding fetched NIFTY 50 TRI values.
It is reference data, not a derivation of the transaction ledger, and both `docs/
ENGINE_SPEC.md` §6 and `app/prices/index_sources.py`'s own docstring are explicit that
an index level must never be confused with or joined against a security price.

**Correctness bar, unchanged and still not met in the strict sense.** `fixtures/
golden_portfolio.json` is still not on this machine. Every number this phase produces
has been checked against `fixtures/engine_cases.json`'s hand-computed cases (now 16,
up from the original set — benchmark, TWRR, and contribution cases were added, each
following the existing worked-example format) and, where a case is genuinely
independent of Postgres, against the real engine directly. But per `CLAUDE.md`'s own
definition, nothing here is "verified" until the golden fixture lands and `pytest
tests/test_golden_portfolio.py -v` passes against it — see §7.

---

## 2. Architecture & Data Flow

Unchanged from the original plan, and matches what actually got built:

```
Transactions -> Holdings -> Portfolio -> Performance -> Analytics -> Insights
```

### 2a. The persisted-derivation path (daily snapshots) — built as planned

```
transaction ledger (append-only, unchanged)
        |
        v
compute_holdings / compute_realised / value_holdings   (app/engine/*, unchanged, pure)
        |
        v
compute_snapshot(transactions, prices, on_date)         (app/engine/snapshot.py, unchanged)
        |
        v
   app/routers/analytical.py's _run_snapshots  --  POST /ops/snapshots/run
   the ONLY writer of portfolio_snapshot, resumable, per-investor start clamped to
   max(requested start, NSE bhavcopy archive floor, that investor's earliest txn)
        |
        v
   app/db/snapshots.py  --  read path
        |
        +--> GET /investors/{id}/snapshots  --> HistoricalValueChart.tsx on the Dashboard
        +--> _window_xirr's opening_value lookups (FY/1Y/3Y/5Y/onboarding), read-first
             with a live compute_snapshot fallback only when no persisted row exists
        +--> _window_twrr's sub-period series, same read-first/fallback shape
```

Confirmed by direct read of `app/routers/analytical.py`: `_window_xirr` and
`_window_twrr` are the generalized successors to the original plan's `_fy_xirr`/
`_period_xirr`, and both read `portfolio_snapshot` before ever calling
`compute_snapshot()` live. The write side is exactly as constrained as planned — no
hand-written `UPDATE`, only the rebuild job.

### 2b. External reference data — both sources decided and built

```
NIFTY 50 TRI  -->  app/prices/index_sources.py (niftyindices.com, real adapter)
                -->  app/db/index_levels.py + migration 011_index_level.sql
                -->  app/engine/benchmark.py
                -->  performance response's `benchmark` field, gated behind the
                     `benchmark` query param

SENSEX TRI    -->  NO SOURCE. app/prices/index_sources.py's own docstring: BSE's index
                     archive has no reachable data endpoint, Asia Index has no
                     documented API, and a third-party aggregator isn't fit as a
                     system-of-record source for a financial product. The contract
                     still declares SENSEX_TRI as a valid enum value; requesting it
                     gets an explicit 400 from the router, not a silent null and not a
                     guess. This is a permanent, documented decision, not a TODO.

NSE sector/industry classification (NIFTY Total Market list, ~750 companies, ISIN-keyed)
                -->  app/prices/sector_sources.py (real adapter)
                -->  app/db/load_sectors.py (loader script)
                -->  security.sector enrichment
                -->  app/engine/holdings.py's _sector_allocation, same weight_pct math
                     as asset_class allocation
                -->  AllocationDonut.tsx, grouping-agnostic, honest "Unclassified"
                     slice for any ISIN outside the ~750-company coverage
```

Neither external source is confused with a transaction or a security price anywhere in
the schema or the engine — checked directly in `app/engine/benchmark.py` and `app/
engine/holdings.py`.

### 2c. Layer rules — still holding

`make lint`'s three architecture checks (no `float` in `app/engine/`, no cross-layer
imports out of `app/engine/`, no credential storage) pass against the current tree,
new modules included: `app/engine/benchmark.py`, `app/engine/twrr.py`, `app/engine/
dividends.py`, `app/engine/contribution.py` are all framework-free and import nothing
from `app.db`, `app.routers`, `app.ingest`, `app.storage`, `app.prices`, or `app.auth`.
`contracts/openapi.yaml` and `schema/*.schema.json` were updated alongside the code for
every new/changed endpoint this phase touched — checked directly, not assumed; see §5.

---

## 3. Feature & Test Matrix

| Feature | Target Router/Engine File | Target Frontend Component | Target Test Suite | Status |
|---|---|---|---|---|
| Daily snapshot persistence | `app/engine/snapshot.py` (unchanged) + `app/db/snapshots.py` + `app/routers/analytical.py` (`_run_snapshots`, `_window_xirr`) | — (backend-only) | `tests/test_db_snapshots.py`, `tests/test_db_analytical.py` | ✅ **Implemented & committed** (`5a49b93`). DB-backed cases still skip locally (no Postgres binary on this machine, see §7) but the engine-level "always recomputable" invariant and read-first/fallback logic are exercised by the non-DB test paths and pass. |
| Historical portfolio value chart | `GET /investors/{investor_id}/snapshots` (`app/routers/analytical.py`) | `HistoricalValueChart.tsx`, wired into `app/page.tsx` (Dashboard), replacing the old placeholder | schema-level tests in `tests/test_analytical_router.py`; component reads persisted rows only, never recomputes | ✅ **Implemented & committed** (`c4d12af`). `recharts` added to `trackr-frontend/package.json` (the deliberate charting-library choice this phase called for). A gap wider than 7 calendar days renders as a genuine line break, not an interpolation — confirmed directly in `HistoricalValueChart.tsx`. |
| Benchmark XIRR (NIFTY 50 TRI) | `app/engine/benchmark.py` + `app/routers/analytical.py`'s `performance()` | `app/performance/page.tsx` benchmark card (selector defaults to NIFTY50_TRI; SENSEX_TRI shown but disabled in the `<select>`, never silently selectable) | `tests/test_benchmark.py`, `tests/test_engine_cases.py`'s `benchmark_cash_flow_replication` case | ✅ **Implemented & committed** (`c4d12af`). SENSEX_TRI is real scope, permanently descoped for lack of a source — see §2b, not a gap in this row. |
| Period-wise XIRR (1Y/3Y/5Y/FY) | `app/engine/xirr.py`'s `compute_period_xirr` (reused) + `app/routers/analytical.py`'s `_window_xirr` | `DualXirrCard.tsx`, all four windows shown together with `xirr_all`/`xirr_holdings`/`period_xirr` | `tests/test_engine_cases.py`, `tests/test_analytical_router.py` | ✅ **Implemented & committed** (`c4d12af`). Contract decision made: `xirr_1y`/`xirr_3y`/`xirr_5y` are flat sibling fields on `PerformanceResponse` alongside `fy_xirr`, not folded into a map — confirmed in `app/schemas/analytical.py` and `contracts/openapi.yaml`. Windows are computed and omitted independently (checked in `_window_xirr`'s per-window `MissingPriceError` handling). |
| TWRR | `app/engine/twrr.py` | `DualXirrCard.tsx`, `fy_twrr`/`twrr_1y`/`twrr_3y`/`twrr_5y` shown beside their XIRR counterparts, never alone | `tests/test_twrr.py`, `tests/test_engine_cases.py`'s `twrr_dividend_and_contribution_sub_periods` case | ✅ **Implemented & committed** (`c4d12af`). The chaining convention this document originally flagged as unpinned is now pinned in `docs/ENGINE_SPEC.md` §5, "confirmed by product decision on 2026-08-20," with a worked example matching the fixture case exactly. |
| Dividends as a first-class feature | `app/engine/dividends.py` + `GET /investors/{id}/dividends` (`app/routers/transactions.py`) | Dividend history section on `app/holdings/[isin]/page.tsx` | `tests/test_dividends.py` | ✅ **Implemented & committed** (`c4d12af`). Router placement diverged from the original plan's guess (`app/routers/holdings.py`) in favor of `app/routers/transactions.py`, alongside the existing lots/realised endpoints — a reasonable call, not a deviation worth correcting. |
| Sector allocation | `app/db/load_sectors.py` (loader) + `app/engine/holdings.py`'s `_sector_allocation` + `app/routers/holdings.py` | `AllocationDonut.tsx`, extended past its Phase 1 single-slice state, grouping-agnostic (renders either `allocation` or `allocation_by_sector`) | extended `tests/test_holdings_router.py`, `tests/test_sector_sources.py` | ✅ **Implemented & committed** (`c4d12af`). **Market-cap bucketing — the other half of this feature's original name — was never built.** No `market_cap` column, loader, engine grouping, or frontend code exists anywhere in the tree (checked directly, zero matches). `docs/FEATURE_BACKLOG.md`'s Phase 2 table now lists this as its own line, still unbuilt — see §7. |
| Contribution analysis | `app/engine/contribution.py` | `ContributionTable.tsx` + new `app/contribution/page.tsx`, linked from `Sidebar.tsx` | `tests/test_contribution.py` (7 cases), `tests/test_engine_cases.py`'s `contribution_mid_period_buy_sell_and_dividend` case | ✅ **Implemented, fully tested (7/7 passing) — NOT YET COMMITTED.** Sitting in the working tree right now: `trackr-backend/app/engine/contribution.py`, `schema/contribution.schema.json`, `tests/test_contribution.py`, `trackr-frontend/app/components/ContributionTable.tsx`, and `trackr-frontend/app/contribution/` are untracked; `contracts/openapi.yaml`, `docs/ENGINE_SPEC.md`, `fixtures/engine_cases.json`, `app/routers/analytical.py`, `app/schemas/analytical.py`, `app/engine/types.py`, and `Sidebar.tsx` carry uncommitted modifications that wire it in. The formula this document originally flagged as unpinned is now `docs/ENGINE_SPEC.md` §10, with every open question §4 listed (mid-period buy/sell weighting, whether contributions can exceed 100%) answered explicitly: percentages are shown uncapped, never normalized (confirmed 2026-08-20). This is a "commit it" gap, not a "build it" gap — see §7. |

**All engine cases pass as one suite:** `.venv/bin/pytest tests/test_engine_cases.py -v`
→ 16/16, including all three cases added this phase. `make test` (engine + contribution
+ demo-fixture suites + full `ruff`/no-float/no-cross-layer/no-credential lint) passes
cleanly end to end once the venv is on `PATH` — see §7 for the one environment note
that trips this up if it isn't.

---

## 4. Engine & Formula Specifications

Both formulas this document originally flagged as **not yet specified** are now pinned,
confirmed, and implemented. Neither was guessed at — both went through the "ask, do not
guess" discipline `CLAUDE.md` requires.

**TWRR — `docs/ENGINE_SPEC.md` §5, "Chaining convention (pinned, confirmed by product
decision on 2026-08-20)."** Sub-periods chain over consecutive *persisted* snapshot
rows (a missed backfill day widens a sub-period rather than being filled). Each
sub-period's flow is signed from the portfolio's side — the mirror image of §4's
investor-side XIRR sign table — because this system has no cash sleeve. Dividends are
counted as return, not backed out (Candidate B of the product decision): a dividend is
a negative flow in the same formula that treats a SELL as a negative flow, which is
mathematically equivalent to crediting it into the sub-period's return. Annualised the
same way CAGR is, `365.25`-day-year, fractional power at the end. The worked example in
the spec is byte-for-byte the same numbers as `fixtures/engine_cases.json`'s
`twrr_dividend_and_contribution_sub_periods` case.

**Contribution analysis — new `docs/ENGINE_SPEC.md` §10.** `gain = (end_value −
start_value) − net_flow`, the per-holding rupee mirror of TWRR's flow adjustment,
expressed as a rupee amount over a single period rather than an annualised rate — the
spec is explicit that there is no "contribution IRR" and no multi-period chaining
variant, unlike TWRR, because rupee amounts don't compound the way ratios do. Every
open question this document originally listed is answered:
- A holding bought or sold mid-period: `net_flow` backs the trade out of the value
  change, so only the price-and-dividend gain counts, not the capital moved.
- A fully-exited holding: stays in the result with `end_value = 0`, never dropped —
  "which investments destroyed value?" per `docs/PRODUCT_VISION.md` requires it to be
  visible.
- Percentages exceeding 100% or going negative when holdings offset: **shown as-is,
  never normalized** — `docs/ENGINE_SPEC.md` §10's own subsection heading is literally
  "Percentages are shown as-is, never capped (confirmed 2026-08-20)."

Both spec additions carry a worked example, matching `docs/ENGINE_SPEC.md`'s existing
convention (formula, worked example, explicit statement of what's still undefined) —
for TWRR, that's the annualisation-vs-chaining boundary; for contribution, it's
explicitly that trailing-window contribution (FY/1Y) is just a single call with a
different `start_date`, not a new mechanism.

All previously-specified formulas (snapshot, period XIRR, dividends aggregation,
sector `weight_pct`) were implemented verbatim against `docs/ENGINE_SPEC.md` as
originally planned — no reinterpretation, confirmed by reading each implementation
against its section.

---

## 5. API Router Contracts

Every endpoint this phase's original plan proposed now exists in `contracts/
openapi.yaml`, checked directly against the file's current path list:

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /investors/{investor_id}/snapshots?start=&end=` | Range read of persisted daily snapshots | ✅ Implemented, in contract, schema-backed |
| `POST /ops/snapshots/run` | Daily/backfill snapshot job | ✅ Implemented, in contract |
| `GET /investors/{investor_id}/performance` | Extended: `benchmark` param now wired (was declared, unused, at the start of this phase); `xirr_1y`/`xirr_3y`/`xirr_5y` and `fy_twrr`/`twrr_1y`/`twrr_3y`/`twrr_5y` added as flat fields | ✅ Implemented, in contract and `schema/performance.schema.json` |
| `GET /investors/{investor_id}/dividends` | Per-ISIN, per-FY dividend summary | ✅ Implemented, in contract, `schema/dividend.schema.json` |
| `GET /investors/{investor_id}/holdings` | Extended with sector-grouped allocation alongside asset_class | ✅ Implemented, in contract |
| `GET /investors/{investor_id}/contribution?period_start=&as_of=` | Ranked per-holding contribution to total return | ✅ Implemented, in contract, `schema/contribution.schema.json` — **but this endpoint's own commit is still pending, see §3/§7** |

`schema/contribution.schema.json` and `schema/dividend.schema.json` both follow the
established convention exactly: `additionalProperties: false`, explicit `required`,
money via `transaction.schema.json#/$defs/decimal`, rates as bare numbers.
`tests/test_types_match_schema.py` now includes `Contribution` in its
`TYPE_TO_SCHEMA` map and passes, confirming the Pydantic model and the JSON Schema
agree.

---

## 6. Frontend & UI Specifications

| Surface | Change | Status |
|---|---|---|
| Dashboard (`app/page.tsx`) | Real `HistoricalValueChart.tsx` (recharts), range presets 1M/6M/1Y/3Y/Max, honest gap rendering | ✅ Wired in |
| Performance (`app/performance/page.tsx`, `DualXirrCard.tsx`) | All four XIRR windows + all four TWRR windows + onboarding period XIRR shown together; benchmark card with NIFTY50_TRI selectable, SENSEX_TRI visibly disabled, not hidden | ✅ Wired in |
| Holdings detail (`app/holdings/[isin]/page.tsx`) | Dividend history section, fourth call alongside lots/realised/transactions | ✅ Wired in |
| Contribution (new `app/contribution/page.tsx`, linked from `Sidebar.tsx`) | Ranked contribution table with period presets (This FY / 1Y / 3Y) and custom date range | ✅ Wired in, uncommitted (see §3) |
| Allocation (`AllocationDonut.tsx`) | Grouping-agnostic, renders sector allocation with an honest "Unclassified" slice — never a fabricated "Other" bucket | ✅ Wired in. **No market-cap grouping exists to render — see §7.** |

All existing conventions were kept, not reinvented — confirmed directly: every new
component uses `formatMoney`/`formatPercent`/`formatDate`/`signClass` from `lib/
format.ts`, and every new data-fetching call goes through `use-fetch.ts`.

---

## 7. Known Gaps & Risks (Honesty Section)

This section replaces the original plan's speculative risk list with what's actually
still open, checked directly rather than assumed:

- **Contribution analysis (Session 8) is fully built and tested but sitting
  uncommitted.** `trackr-backend/app/engine/contribution.py`, `schema/
  contribution.schema.json`, `tests/test_contribution.py`, `trackr-frontend/app/
  components/ContributionTable.tsx`, and `trackr-frontend/app/contribution/` are
  untracked; eight other files carry uncommitted modifications that wire it in. All
  tests pass (`tests/test_contribution.py`: 7/7; the new `fixtures/engine_cases.json`
  case: passing) and `make test`/`make lint` are clean against the current tree. This
  is the single highest-priority remaining item precisely because it's the cheapest —
  nothing needs to be written, only reviewed and committed as its own commit, per
  `CLAUDE.md`'s "one feature per session, one commit per feature."
- **Market-cap bucketing was never built.** `docs/FEATURE_BACKLOG.md`'s Phase 2 table
  now names this as its own line ("market-cap bucketing is a separate, still-unbuilt
  security-master field") distinct from sector, which is done. No `market_cap` column
  exists on `security` (checked directly against `migrations/001_core.sql`), and no
  loader, engine grouping, or frontend code references it anywhere in the tree — this
  is a clean, well-scoped gap, not a partially-started one.
- **The DB-backed half of this phase's own test suite has never actually run.**
  `tests/test_db_snapshots.py`, `tests/test_db_index_levels.py`,
  `tests/test_db_analytical.py`, `tests/test_holdings_router.py`, and the DB-dependent
  cases inside `tests/test_benchmark.py`/`tests/test_dividends.py`/
  `tests/test_sector_sources.py` all skip on this machine — `tests/conftest_db.py`
  looks for local `initdb`/`pg_ctl` binaries (its skip message says "brew install
  postgresql@17," which is a macOS-authored message on what is actually this session's
  Linux box) and finds none. Every Phase 2 feature that touches a persisted table —
  which is most of them — has therefore been verified at the pure-function level
  (`fixtures/engine_cases.json`) but never against a real database round-trip. This is
  a materially bigger gap than it looks: it is the one thing standing between "the
  formula is right" and "the formula is right *and* it's actually being written and
  read back correctly."
- **The golden fixture is still not on this machine.** `fixtures/golden_portfolio.json`
  remains the one gate that actually matters for calling anything in Phase 1 *or*
  Phase 2 "verified" rather than "built," per `CLAUDE.md`'s own definition. Unchanged
  from the original plan — still worth asking the client for directly.
- **A field test of Phase 1's ingestion paths, run this same day, found two
  regressions that block every Phase 2 feature above from ever seeing a real user's
  data.** `PHASE1_FIELD_TEST_REPORT.md` (new this session, committed in `c4d12af`)
  documents, with a reproduced stack trace: (1) manual transaction entry — one of
  Phase 1's two ingestion paths — throws an unhandled `ForeignKeyViolation` for *any*
  ISIN not already in the `security` table, which for a brand-new investor is every
  security; confirmed still present by reading `app/routers/transactions.py`'s
  `create_transactions` directly — it has no security-row-creation step, unlike `app/
  db/imports.py`'s CSV path, which does this deliberately. (2) a malformed CSV/XLSX
  upload can crash the tradebook parser with an unhandled `csv.Error` instead of the
  same adapter's own graceful rejection path, and the resulting 500 arrives without a
  CORS header, which reads in-browser as a CORS failure — a genuinely misleading
  symptom. Neither is Phase 2 scope to fix, but both are directly blocking: no matter
  how correct the benchmark, TWRR, or contribution math is, a new investor cannot get
  a single manually-entered trade into the ledger today. Treat this as a
  higher-priority fix than any remaining Phase 2 polish — see `docs/PHASE2_PROMPTS.md`.
- **`c4d12af` bundled five of the eight sessions (2, 3, 5, 6, 7) into one commit.**
  `docs/PHASE2_PROMPTS.md`'s own instructions were explicit — "don't bundle two of
  these into one session even though it's tempting" — and this bundling happened
  anyway, evidently across whatever sessions actually did the work. Not a code defect;
  every bundled feature passes its own tests. Worth naming plainly so it isn't repeated
  finishing the two remaining items (commit contribution separately; don't fold
  market-cap into that same commit either).
- **`make test`/`make lint` require the project's venv on `PATH`.** Running `make test`
  with the system `pytest` (no venv activated) fails immediately on `ModuleNotFoundError:
  No module named 'app'` — not a code problem, but worth documenting since it looks
  like a real failure at first glance. `source .venv/bin/activate` before `make test`
  or `make lint` resolves it; ruff itself is present and clean once that's done.
- **SENSEX_TRI has no source and this is permanent, not pending.** Restated from §2b
  because it's easy to misread the contract's still-present `SENSEX_TRI` enum value as
  an in-progress gap. It isn't — `app/prices/index_sources.py`'s docstring documents
  why no reliable, machine-fetchable, free source exists, and the router 400s on
  request rather than guessing. Nothing in `docs/PHASE2_PROMPTS.md` should ask a future
  session to "finish" this.
- **Concurrent sessions.** Unchanged risk from the original plan — this repository has
  had multiple simultaneous Claude Code sessions against the same working tree before.
  Re-check `git status` and `git log` before starting any closeout session in `docs/
  PHASE2_PROMPTS.md`; this document's snapshot will go stale the moment another session
  commits.
