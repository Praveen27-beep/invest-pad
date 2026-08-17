# Trackr-Plus Phase 2: Analytics Depth — Overview & Execution Skeleton

Generated 2026-08-18, at the start of Phase 2, before any Phase 2 code exists. This is
**not** an audit of finished work the way `docs/trackr_plus_phase1_overview.md` was —
that document verified what already ran and passed. This one is the skeleton: what
Phase 2 is scoped to build, how it fits the existing architecture, and what's still
undecided. Every status in §3 is honestly `⏳ Pending Implementation` because nothing
below has been written yet. Update this document in place as each session in
`docs/PHASE2_PROMPTS.md` lands, the same way the Phase 1 overview was kept current
through its own build.

**Read this before starting any Phase 2 session.** It has the dependency map, the
already-existing scaffolding (BenchmarkOut, the `benchmark` query param, the DIVIDEND
txn_type — several Phase 2 features have more of their contract already in place than
their name suggests), and the open questions that block naive implementation.

---

## 1. Executive Summary & Phase Goals

**Phase 1 is closed.** Verified today, not assumed: `.venv/bin/pytest tests/ -q -rs`
reports **381 passed, 217 skipped, 1 deselected, 0 failed**; `make lint`'s three
architecture checks (no `float` in `app/engine/`, no cross-layer imports, no credential
storage) pass; and every item `docs/PHASE1_CLOSEOUT_PROMPTS.md` flagged as missing
(per-holding CAGR, period XIRR from an adviser onboarding date, the DPDP privacy screen,
consent capture and enforcement, investor onboarding through the UI) is present in the
code today, not just planned — checked directly against
`trackr-backend/app/schemas/holdings.py`, `trackr-backend/app/routers/consent.py`,
`trackr-frontend/app/privacy/page.tsx`, `trackr-frontend/app/settings/page.tsx`, and
migration `009_investor_onboarding.sql`.

**What Phase 2 is.** Per `docs/FEATURE_BACKLOG.md`'s Phase 2 table — the document
`CLAUDE.md` designates as the tie-breaker whenever another doc disagrees about scope —
Phase 2 is **"Analytics depth (still equities)"**: eight features that deepen what the
system can say about a portfolio that is already correctly tracked, without adding a
second asset class, without touching tax, and without adding any new ingestion adapter.
`docs/PRODUCT_VISION.md` frames the shift precisely: Phase 1 built the tracker; Phase 2
starts building "the intelligence layer" — the part of the product that *explains* a
portfolio rather than just recording it. Two of this phase's eight features (benchmark
comparison, contribution analysis) are the first real answers to questions
`docs/PRODUCT_VISION.md` poses directly: *"Am I beating the benchmark, on my actual cash
flows?"* and *"Which holdings contributed most?"*

**What Phase 2 is not.** Not Phase 3 (tax engine — gated behind a full quarter of real
data and mandatory CA sign-off, `docs/TAX_ENGINE.md`), not Phase 4 (a second asset
class), not a CAS adapter (named in `docs/BUILD_PLAN.md`'s build-next list and
`docs/FULL_VISION_BACKEND_ROADMAP.md`'s Section D, but absent from
`docs/FEATURE_BACKLOG.md`'s actual Phase 2 table — see `docs/PHASE2_PROMPTS.md`'s "Not
included on purpose" section). `docs/BUILD_PLAN.md` itself cautions: *"Resist all seven
[items on its own longer list] until the MVP has run for a month on real data."* That
caution stands; see §7.

**The one architectural rule still applies, with one new nuance.** `CLAUDE.md`:
*"Everything is derived from transactions... Holdings are NEVER stored."* Phase 2
introduces this system's first persisted derived artifact beyond `price` and
`holding_snapshot` (which is CAS-reconciliation-only, per `docs/DATA_MODEL.md`): a daily
**portfolio-level** snapshot table (§2, §4). This is not an exception to the rule — it
is explicitly anticipated by `docs/ENGINE_SPEC.md` §8 ("Snapshots are a cache of a
derivation, not a source of truth — they must always be recomputable from the ledger")
and by `CLAUDE.md`'s own carve-out ("A cache is permitted only once profiling proves it
necessary, and must always be reproducible from the ledger"). It stores portfolio
totals, never per-ISIN quantities — it is not a holdings table under a different name.
Treat this distinction as load-bearing throughout Phase 2, not a technicality.

**Correctness bar, unchanged from Phase 1.** `fixtures/golden_portfolio.json` (the
client's real 324-trade portfolio) is still not present on this machine. Nothing built
in Phase 2 should be called "verified" in the `CLAUDE.md` sense until it lands and
`pytest tests/test_golden_portfolio.py -v` passes against it. `fixtures/
engine_cases.json`'s hand-computed cases remain the interim bar — every new formula this
phase introduces needs a new case added there before implementation, not after.

---

## 2. Architecture & Data Flow

The core pipeline from `CLAUDE.md` is unchanged and remains the frame for everything
below:

```
Transactions -> Holdings -> Portfolio -> Performance -> Analytics -> Insights
```

Phase 2 adds two things to this picture that Phase 1 never needed: a **persisted
derivation** and **external reference data**.

### 2a. The new persisted-derivation path (daily snapshots)

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
   [NEW] a daily backfill/write job persists ONE row per (investor[, advised_only?], as_of)
        |
        v
   [NEW] app/db/snapshots.py  --  read path
        |
        +--> historical value chart endpoint  --> Dashboard chart (Session 2)
        +--> period-wise XIRR opening_value lookups  --> Performance page (Session 4)
        +--> TWRR sub-period series  --> Performance page (Session 5)
        +--> _fy_xirr / _period_xirr's opening_value  --> refactored to prefer this table
             over a live compute_snapshot call (Session 1's actual payoff)
```

The write side must only ever be a rebuild job calling `compute_snapshot()` — never a
hand-written `UPDATE`, never written incidentally by a request handler. The read side is
what every other Phase 2 session downstream of Session 1 actually touches. Nothing here
changes how holdings themselves are computed — `compute_holdings` remains derived-on-read
and un-persisted, exactly as `CLAUDE.md` requires.

### 2b. External reference data (new to this phase)

Two Phase 2 features need a data source that isn't a bhavcopy or a client-supplied
transaction — both are genuinely new dependencies, not implementation details, and both
need a Plan Mode decision before coding (see `docs/PHASE2_PROMPTS.md` sessions 3 and 7):

```
[NEW] index-level TRI source (NIFTY 50 / SENSEX)  -->  app/engine/benchmark.py
                                                    -->  performance response, gated
                                                         behind the `benchmark` query
                                                         param already declared in
                                                         contracts/openapi.yaml

[NEW] sector/industry reference data (NSE equity list or equivalent)
                                                    -->  security.sector enrichment
                                                    -->  allocation grouped by sector
                                                         (app/engine/holdings.py,
                                                         same weight_pct math as the
                                                         existing asset_class grouping)
```

Neither of these is a transaction and neither should ever be confused with one — an
index level is not a security price and must not pass through
`app/engine/valuation.py`'s per-holding path; a sector label is reference metadata on
`security`, not derived from the ledger at all.

### 2c. Layer rules, unchanged

`docs/ARCHITECTURE.md`'s "Swapping the stack" section and `make lint`'s architecture
checks still govern every file this phase touches:

- `app/engine/` stays framework-free, pure, and `float`-free. `app/engine/benchmark.py`,
  `app/engine/twrr.py`, `app/engine/dividends.py`, and `app/engine/contribution.py` —
  all new this phase — must not import `app.db`, `app.routers`, `app.ingest`,
  `app.storage`, `app.prices`, or `app.auth`, exactly like every existing engine module.
- The ingestion layer still never touches analytics — nothing in this phase adds an
  ingestion adapter, so this boundary is not exercised by Phase 2, only preserved.
- `contracts/openapi.yaml` and `schema/*.schema.json` remain the source of truth per
  `docs/ARCHITECTURE.md`: *"The contracts are the product; the code is one expression of
  them."* Every new/changed endpoint in §5 below must be reflected in the contract
  **before** or **alongside** implementation, not as an afterthought — this is already
  half-true for benchmark comparison, where the contract anticipated the feature before
  the engine did (see §5).

---

## 3. Feature & Test Matrix

| Feature | Target Router/Engine File | Target Frontend Component | Target Test Suite | Status |
|---|---|---|---|---|
| Daily snapshot persistence | `app/engine/snapshot.py` (existing, unchanged) + `app/db/snapshots.py` (new) + `app/routers/analytical.py` (`_fy_xirr`/`_period_xirr` refactored to read-then-fallback) | — (backend-only; unblocks the row below) | `tests/test_db_snapshots.py` (new) | ⏳ Pending Implementation |
| Historical portfolio value chart | new `GET /investors/{investor_id}/snapshots` (`app/routers/analytical.py` or new router) | `HistoricalChartPlaceholder.tsx` → replaced with a real chart component; wired into `app/page.tsx` | schema-level response test + `tests/test_db_snapshots.py` range-read case | ⏳ Pending Implementation |
| Benchmark XIRR (NIFTY 50 TRI / SENSEX TRI) | `app/engine/benchmark.py` (new) + `app/routers/analytical.py`'s `performance()` (wire the existing unused `benchmark` query param) | `app/performance/page.tsx`, `components/DualXirrCard.tsx` | `tests/test_benchmark.py` (new) + a new `fixtures/engine_cases.json` case | ⏳ Pending Implementation |
| Period-wise XIRR (1Y / 3Y / 5Y / FY) | `app/engine/xirr.py`'s `compute_period_xirr` (existing, reused) + `app/routers/analytical.py` (new shared helper generalizing `_fy_xirr`/`_period_xirr`) | `app/performance/page.tsx`, `components/DualXirrCard.tsx` (period selector) | extended `tests/test_engine_cases.py` / `fixtures/engine_cases.json` cases | ⏳ Pending Implementation |
| TWRR | `app/engine/twrr.py` (new — **formula not yet pinned in `ENGINE_SPEC.md`, see §4/§7**) | `app/performance/page.tsx` | `tests/test_twrr.py` (new) | ⏳ Pending Implementation |
| Dividends as a first-class feature | `app/engine/dividends.py` (new) + `app/routers/holdings.py` (new endpoint) | `app/holdings/[isin]/page.tsx` (new section); portfolio-wide summary placement TBD | `tests/test_dividends.py` (new) | ⏳ Pending Implementation |
| Sector / market-cap breakdown | `app/engine/holdings.py` (extended grouping) + `app/routers/holdings.py` + new `security.sector` loader under `app/db/` | `components/AllocationDonut.tsx` (extended past its documented single-slice Phase 1 state) | extended `tests/test_holdings.py` | ⏳ Pending Implementation |
| Contribution analysis | `app/engine/contribution.py` (new — **formula not yet pinned in `ENGINE_SPEC.md`, see §4/§7**) | `app/holdings/page.tsx` (new ranked section) | `tests/test_contribution.py` (new) | ⏳ Pending Implementation |

---

## 4. Engine & Formula Specifications

Formulas already fully specified in `docs/ENGINE_SPEC.md` — Phase 2 implements against
these verbatim, does not reinterpret them:

**Snapshot (§8, unchanged, already implemented as `compute_snapshot`):**
```
Snapshot { as_of, invested, market_value, unrealised, realised_to_date }
```
Phase 2's job is persistence and backfill, not a new formula.

**Benchmark XIRR (§6, verbatim):**
```
for each portfolio cash flow (date, amount):
      units = amount ÷ index_level(date)
      accumulate units
benchmark_terminal = total_units × index_level(as_of)
benchmark_xirr     = xirr(same dates, same amounts, benchmark_terminal)
```
TRI (total return) indices only — a price index excludes dividends and understates the
benchmark. Comparing portfolio XIRR against a headline index CAGR is explicitly
forbidden by the spec, not merely discouraged.

**Period XIRR (§4, verbatim, reused unchanged for the 1Y/3Y/5Y/FY windows):**
```
flow 1     : (start_date, −opening_value)      portfolio value at start_date
flows 2..n : every transaction after start_date
final flow : (as_of, +current market value)
```
Every intermediate transaction must appear as its own dated flow — the pinned failure
mode (`period_xirr_mid_period_deposit_not_inflated` in `fixtures/engine_cases.json`) is
what an implementation that aggregates flows into the opening/closing value produces
instead, silently.

**Dividends (§ none dedicated, but fully implied by `docs/DATA_MODEL.md`'s `txn_type`
table and `ENGINE_SPEC.md` §4's cash-flow table):** per-ISIN, per-financial-year sum of
`dividend_amount` across `DIVIDEND` transactions. No new formula — an aggregation over
data the engine already correctly ingests and already includes in XIRR.

**Sector allocation (§2, reused with a different grouping key):**
```
weight_pct = market_value ÷ Σ market_value
```
Identical to the existing asset_class allocation math, grouped by `security.sector`
instead. Not a new formula — a new grouping dimension over an existing one.

### Not yet specified — must be written before implementation

Two Phase 2 features have **no formula in `docs/ENGINE_SPEC.md` today**. Per `CLAUDE.md`
("Never invent financial logic... if a case is not covered there, ask, do not guess"),
implementing either from a plausible-sounding guess is exactly the failure mode this
project's own spec repeatedly warns about (see §4's mid-period-deposit case for what it
looks like when caught, and note it's *always* the case that a wrong number here looks
like a right one). Both are called out with a `STOP` instruction in the relevant
`docs/PHASE2_PROMPTS.md` session:

- **TWRR.** `docs/ENGINE_SPEC.md` §5 says only that snapshots unlock it and states its
  purpose (it measures the adviser, not the client) — it does not specify the sub-period
  chaining convention. Standard implementations diverge here in ways that produce
  materially different numbers (true daily valuation vs. Modified Dietz approximation,
  treatment of same-day flows). This must be pinned in `ENGINE_SPEC.md` §5 with a worked
  example before `app/engine/twrr.py` is written.
- **Contribution analysis.** Named as a Phase 2 deliverable in three separate documents
  (`FEATURE_BACKLOG.md`, `FULL_VISION_BACKEND_ROADMAP.md`, `PRODUCT_VISION.md`) but
  defined precisely in none of them. Open questions that need explicit, written answers
  (not defaults): how a mid-period buy or full sell is weighted, and how contributions
  that individually exceed 100% of the portfolio's total return (a real, correct
  possibility when gains and losses partially offset) should be presented. This needs a
  new `docs/ENGINE_SPEC.md` §10 with a worked example before `app/engine/contribution.py`
  is written.

---

## 5. API Router Contracts

**Already anticipated by the contract, not yet implemented** — the clearest case of the
contract being ahead of the code in this codebase:

```yaml
# contracts/openapi.yaml, GET /investors/{investor_id}/performance
parameters:
  - { name: benchmark, in: query, schema: { type: string, enum: [NIFTY50_TRI, SENSEX_TRI] } }
```
```json
// schema/performance.schema.json — benchmark object, already defined
"benchmark": {
  "type": ["object", "null"],
  "properties": {
    "name": { "type": "string", "enum": ["NIFTY50_TRI", "SENSEX_TRI"] },
    "xirr": { "type": ["number", "null"] },
    "terminal_value": { "$ref": "transaction.schema.json#/$defs/decimal" }
  }
}
```
`app/schemas/analytical.py`'s `BenchmarkOut` and `trackr-frontend/lib/api-types.ts`'s
`BenchmarkOut` interface both already exist, unused. Session 3 in
`docs/PHASE2_PROMPTS.md` wires the query param through to a real computation — no
contract change needed for benchmark comparison itself, only implementation.

**New endpoints this phase needs to add to `contracts/openapi.yaml`** (exact shapes to
be finalized in each session's Plan Mode step, not decided here):

| Endpoint (proposed) | Purpose | Session |
|---|---|---|
| `GET /investors/{investor_id}/snapshots?start=&end=` | Range read of persisted daily snapshots, for the historical value chart | 2 |
| `POST /ops/snapshots/run` | Daily/backfill snapshot job, mirroring the existing `POST /ops/prices/refresh` auth/notifier pattern | 1 |
| `GET /investors/{investor_id}/performance` (extended) | Add `xirr_1y` / `xirr_3y` / `xirr_5y` fields or a unified `trailing_xirr` map (decide in Session 4's Plan Mode step — this is a breaking-shape decision, not additive) and a `twrr` field | 4, 5 |
| `GET /investors/{investor_id}/dividends` | Per-ISIN, per-FY dividend summary | 6 |
| `GET /investors/{investor_id}/holdings` (extended) or a new endpoint | Sector-grouped allocation alongside the existing asset_class grouping | 7 |
| `GET /investors/{investor_id}/contribution` | Ranked per-holding contribution to total return | 8 |

Every row above needs a corresponding `schema/*.schema.json` file or extension,
following `schema/performance.schema.json`'s existing conventions
(`additionalProperties: false`, explicit `required`, money via the shared
`transaction.schema.json#/$defs/decimal` `$ref`, rates as bare JSON numbers). None of
these are finalized contracts — they are the shape each session's own Plan Mode step
should confirm or revise before writing code, per `docs/ARCHITECTURE.md`'s "contracts
are the product" rule.

---

## 6. Frontend & UI Specifications

| Surface | Change | Depends on |
|---|---|---|
| Dashboard (`app/page.tsx`) | `HistoricalChartPlaceholder.tsx`'s honest disabled state replaced with a real line chart (market value, optionally invested/cost-basis) over a selectable range | Session 1 (data), Session 2 (endpoint + component); **no charting library is in `trackr-frontend/package.json` today** — Session 2 adds one deliberately, see §7 |
| Performance (`app/performance/page.tsx`, `components/DualXirrCard.tsx`) | A period selector (FY / 1Y / 3Y / 5Y) beside the existing dual-XIRR pair; a benchmark comparison card/row, never showing a bare index CAGR; TWRR shown beside XIRR, never replacing it | Sessions 3, 4, 5 |
| Holdings detail (`app/holdings/[isin]/page.tsx`) | A dividend history section, alongside the existing FIFO-lots and realised-history sections already on that page | Session 6 |
| Holdings / Dashboard | A ranked contribution list (best/worst contributors to overall return) | Session 8 |
| Allocation (`components/AllocationDonut.tsx`) | Extended past today's documented single-slice Phase 1 state to group by sector, with an honest "unclassified" slice for anything not yet backfilled — never a fabricated or silently-merged "Other" bucket | Session 7 |

Existing frontend conventions Phase 2 must keep using rather than inventing new ones:
`trackr-frontend/lib/format.ts` (`formatMoney`, `formatPercent`, `formatDate`,
`signClass`) for all display formatting — never raw JS `Number` math on a money string;
`trackr-frontend/lib/api-client.ts` / `use-fetch.ts` for API calls; the existing
null-handling pattern used by `UnpricedBanner.tsx` / `MissingPriceNotice.tsx` for any
metric that can legitimately come back absent (every new metric in this phase can: a
period XIRR window with no reachable snapshot, a benchmark with no configured index
source, a TWRR with an incomplete snapshot series).

---

## 7. Known Gaps & Risks (Honesty Section)

- **The golden fixture is still not on this machine.** `fixtures/golden_portfolio.json`
  remains the one gate that actually matters for calling anything in this phase
  "verified," not just "built" — see `docs/FULL_VISION_BACKEND_ROADMAP.md`'s "Decision
  (2026-08-16)" section. Asking the client for it directly is still the correct fix, and
  still not a blocker to any session in `docs/PHASE2_PROMPTS.md`.
- **Two formulas genuinely don't exist yet** — TWRR and contribution analysis (§4). This
  is not a documentation oversight to patch quickly; both need a real, worked-example-
  backed decision from whoever owns the product spec before either session can start
  safely. Treat these two sessions as higher-risk and higher-latency than the other six
  for that reason alone.
- **Two external data dependencies are undecided.** A TRI index-level source for
  benchmark comparison, and a sector/industry classification source for the allocation
  breakdown. Neither is a code problem — both are "does a suitable, reliably fetchable
  source actually exist and is it acceptable to depend on" questions that belong in each
  session's Plan Mode step, not assumed away. If a source turns out not to exist or not
  to be reliable enough, that is a legitimate reason to report a session as blocked
  rather than build against something fragile.
- **Historical bhavcopy backfill range is unknown.** Daily snapshot backfill (Session 1)
  and, downstream, the 5Y period-XIRR window and TWRR's usefulness, are all bounded by
  how far back `app/prices/sources.py`'s NSE/BSE sources actually serve data — this has
  not been checked against the live sources as part of scoping this document and should
  be one of the first things Session 1 confirms, before committing to a specific
  backfill range in its plan.
- **No charting library exists in the frontend today.** `trackr-frontend/package.json`
  has only `next`/`react`/`react-dom` as runtime dependencies. Session 2 is the first
  session in this project to add a new frontend runtime dependency — pick deliberately
  and note the reasoning in the commit, since nothing today constrains the choice.
- **This is the first persisted-derivation table in the system's history.** Every
  previous derived object (`Holding`, `Lot`, `Realised`) has been computed-on-read only.
  Daily snapshots are the first thing that breaks that pattern, deliberately and with
  the spec's own blessing (§8, §1 above) — but it is exactly the kind of schema change
  `CLAUDE.md` requires Plan Mode for, and exactly the kind of change a future session
  could misread as license to start persisting *other* derived data (per-ISIN holdings,
  say) without the same care. Treat Session 1 as setting the precedent for what "a cache
  of a derivation" is allowed to look like in this codebase, not just shipping one table.
- **CAS adapter and capital-gains work are explicitly parked, not silently dropped** —
  see `docs/PHASE2_PROMPTS.md`'s "Not included on purpose" section for why each is
  excluded from this phase's scope despite appearing in other planning documents.
- **Concurrent sessions.** This repository has previously had multiple simultaneous
  Claude Code sessions active against the same working tree (see
  `docs/FULL_VISION_BACKEND_ROADMAP.md`'s callout from 2026-08-16). Before starting any
  session in `docs/PHASE2_PROMPTS.md`, re-check `git status` and `git log` rather than
  assuming this document's snapshot of the codebase is still current — the same
  discipline that document itself recommends.
