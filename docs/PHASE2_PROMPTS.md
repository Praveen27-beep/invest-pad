# Phase 2 (Analytics Depth) — one prompt per session

Generated 2026-08-18, after confirming Phase 1 is genuinely closed: `.venv/bin/pytest
tests/ -q -rs` currently reports **381 passed, 217 skipped, 1 deselected, 0 failed**,
`make lint`'s three architecture checks pass, and every item in
`docs/PHASE1_CLOSEOUT_PROMPTS.md` (per-holding CAGR, period XIRR from an onboarding
date, the DPDP privacy screen, consent capture, investor onboarding, and the
`consent`/`grievance` HTTP-level test suites) is already present in the code — not just
planned. See `docs/trackr_plus_phase2_overview.md` for the file-by-file detail behind
that claim; read it first, it has the full map this document assumes.

**One feature per session, one commit per feature.**

Each block below is meant to be pasted as the **first message of a brand-new chat
session**. They're self-contained: background, files, and acceptance criteria are all
inline, because the new session has none of this conversation's context. Do them in
separate sessions and separate commits, per `CLAUDE.md`'s "one feature per session, one
commit per feature" rule — don't bundle two of these into one session even though it's
tempting, and don't shrink a session below what's written here just to make it smaller;
`CLAUDE.md`'s own Phase 1 sessions (see `docs/BUILD_PLAN.md`) were built at this scope,
and Sonnet-in-Claude-Code handles it fine.

Scope for all eight: **`docs/FEATURE_BACKLOG.md`'s Phase 2 table** ("Analytics depth —
still equities"), which `CLAUDE.md` itself designates as the tie-breaker document
whenever another doc disagrees about scope. `docs/FULL_VISION_BACKEND_ROADMAP.md`
Section D and `docs/BUILD_PLAN.md`'s "what to build next" list cover the same ground in
more implementation detail and are cited throughout — but if either ever conflicts with
`FEATURE_BACKLOG.md`'s table on what's *in scope*, the table wins. See "Not included on
purpose" at the end for the items that appear in the roadmap/build-plan but not in the
table.

**Every session below still respects the golden-fixture gate.** `fixtures/
golden_portfolio.json` (the client's real 324-trade portfolio) is not present on this
machine and none of these sessions should fabricate a replacement — see
`docs/FULL_VISION_BACKEND_ROADMAP.md`'s "Decision (2026-08-16)" section. Write tests
against `fixtures/engine_cases.json` (hand-computed, already the Phase 1 correctness
bar) and add new hand-computed cases there for any new formula. Nothing built in Phase 2
should be described as "verified" in the `CLAUDE.md` sense until the real fixture lands.

Suggested order: **1 first, always** — it is the one genuine dependency in this phase.
Sessions 2, 4, and 5 all read from the table Session 1 builds and cannot be meaningfully
tested without it (they can be *written* in parallel sessions against a stub, but don't
merge them before 1 lands). Sessions 3, 6, 7, and 8 are independent of 1 and of each
other and can happen in any order, including before Session 1 if that's more convenient
for whoever's picking up the work.

---

## 1. Daily snapshot persistence

```
Read CLAUDE.md and docs/ENGINE_SPEC.md §8 ("Snapshots") first, then
docs/trackr_plus_phase2_overview.md §4 for this feature's full spec.

Context: app/engine/snapshot.py's compute_snapshot(transactions, prices, on_date) is a
pure function that already exists, is already correct, and is already called LIVE on
every /investors/{id}/performance request — twice, in fact: app/routers/analytical.py's
_fy_xirr and _period_xirr helpers each call it on the fly against historical prices to
get an honest opening_value for 1-April and the investor's onboarding_date respectively.
Nothing persists the result. docs/ENGINE_SPEC.md §8 says plainly: "Persisting a daily
snapshot enables the portfolio-value chart and TWRR later," and docs/FEATURE_BACKLOG.md
Phase 2's first line is "Daily snapshots | Unlocks the value chart and TWRR; needs
historical bhavcopy backfill." This session is that persistence layer. Sessions 2
(historical value chart), 4 (period-wise XIRR), and 5 (TWRR) all read from the table
this session builds — do this one first.

This touches the schema AND the engine-adjacent db layer, so start in Plan Mode per
CLAUDE.md ("Plan mode for anything touching the schema or the engine"). Decide, and get
sign-off via the plan, on:
1. Grain: one row per (investor_id, as_of), matching how GET .../performance already
   aggregates across all of an investor's accounts (see migration
   009_investor_onboarding.sql's own reasoning for putting onboarding_date on
   `investor` rather than `account`, for the same kind of argument) — or does
   advised_only=true need its own separate snapshot series? Read how performance()
   handles advised_only today (app/routers/analytical.py) before deciding; don't let
   the snapshot table silently only ever represent the unfiltered view if the advised
   view is a materially different number an adviser will actually want charted.
2. How far back to backfill. Bounded by two independent limits: how far back the
   ledger's own transaction history reaches per investor, and how far back NSE/BSE
   bhavcopy is actually fetchable through app/prices/sources.py (nse_source/
   bse_source) — check what date range those sources actually support before assuming
   "as far back as the ledger goes" is achievable. app/prices/pipe.py's fetch_day only
   fetches a single date and trading_days(start, end) only enumerates dates — there is
   no existing loop that calls fetch_day across a range; this session needs to add
   that backfill loop (a new function, not a copy-pasted script), reusing fetch_day
   and trading_days rather than reimplementing bhavcopy fetching.
3. How the daily job runs going forward: a POST /ops/snapshots/run endpoint mirroring
   POST /ops/prices/refresh's existing shape in app/routers/analytical.py (same
   get_current_user-gated pattern, same notifier-on-failure convention via
   app/prices/alerts.py), a cron-invoked script, or both. Read refresh_prices() in
   analytical.py closely as the template either way.
4. New migration file trackr-backend/app/db/migrations/010_<name>.sql (the next free
   number after 009_investor_onboarding.sql) — read that migration and
   006_source_precedence.sql first for the house style (comments explaining WHY, CHECK
   constraints on things like as_of not being in the future).

Task, once the plan is agreed:
- The new table stores PORTFOLIO-LEVEL totals only (invested, market_value,
  unrealised, realised_to_date, as_of, investor_id) — never per-ISIN quantities. That
  distinction matters: CLAUDE.md's "a holdings table written by anything but a
  rebuild" ban is about a table standing in for compute_holdings' per-position output;
  this table is the existing, already-documented Snapshot dataclass
  (app/engine/types.py, class Snapshot) made persistent, which ENGINE_SPEC.md §8
  itself anticipates ("Snapshots are a cache of a derivation, not a source of truth —
  they must always be recomputable from the ledger"). Never write a row from anywhere
  except a rebuild job that calls compute_snapshot() itself. No UPDATE of a stored
  total by hand, ever.
- New trackr-backend/app/db/snapshots.py (mirror app/db/prices.py's shape: a narrow,
  typed read/write module, not business logic) with at minimum a write/upsert
  function and a point lookup (investor_id, as_of) -> Snapshot | None.
- The backfill/daily-write path must handle MissingPriceError per date, not abort the
  whole run — follow _fy_xirr's existing exact pattern (catch it, log the specific
  ISINs and date, skip that date, continue) rather than inventing a new error-handling
  shape.
- Refactor _fy_xirr and _period_xirr (app/routers/analytical.py) to look up a
  persisted snapshot FIRST and only fall back to the live compute_snapshot path when
  no persisted row exists for that exact date — this is what actually removes the
  on-the-fly recomputation these two helpers currently do on every request, and it's
  the concrete payoff of this session beyond "a table exists."
- All money fields NUMERIC(20,6) in the migration, Decimal in Python — CLAUDE.md rule 1,
  make lint enforces no float in app/engine/ but this new db module is not under
  engine/, so be disciplined about it anyway.

Write tests first: tests/test_db_snapshots.py (pytest.mark.db, like every other
DB-backed test here), proving (a) a written/backfilled snapshot for a given date is
byte-for-byte identical to what compute_snapshot() computes live for the same ledger and
date — this is the "always recomputable" invariant ENGINE_SPEC.md §8 states, and it
deserves a direct test, not just an implicit assumption — and (b) _fy_xirr/_period_xirr
now prefer the persisted row and only fall back to live computation when one is absent,
without changing any existing golden number (CLAUDE.md's headline table in the root
CLAUDE.md must still reproduce exactly once fixtures/golden_portfolio.json is available;
for now, confirm fixtures/engine_cases.json's existing period_xirr and fy_xirr-adjacent
cases still pass unchanged).

Run `make test` and `make lint` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 2. Historical portfolio value chart

```
Read CLAUDE.md first, then docs/trackr_plus_phase2_overview.md §4 and §6 for this
feature's spec — it depends directly on Session 1 (daily snapshot persistence); do not
start this until that table exists and is being written to, or there is nothing real to
chart.

Context: trackr-frontend/app/components/HistoricalChartPlaceholder.tsx is today an
honest, deliberately disabled empty state on the Dashboard — its own comment says
historical value isn't tracked yet, and that was correct until Session 1 landed.
docs/FEATURE_BACKLOG.md Phase 2's second line, "Historical portfolio value chart | Needs
snapshots first," is this session. There is no charting library in
trackr-frontend/package.json today (checked directly — only next/react/react-dom are
dependencies) — adding one is part of this session's scope, not a prerequisite someone
else handles.

Task:
- Backend: a new read endpoint serving a date range of persisted snapshots — decide
  the exact shape in coordination with contracts/openapi.yaml (e.g. GET
  /investors/{investor_id}/snapshots?start=&end=), add it to the contract, and add a
  matching schema/*.schema.json file following performance.schema.json's existing
  style (additionalProperties: false, explicit required fields, money as strings via
  the existing $ref: 'transaction.schema.json#/$defs/decimal' pattern). Read from
  app/db/snapshots.py's range-read function (add one if Session 1 didn't need one) —
  never recompute the full ledger replay per point on this endpoint; the entire reason
  Session 1 exists is to make this cheap.
- Pick a charting library deliberately (check what's already common in a Next.js 14 +
  Tailwind stack like this one — e.g. Recharts is a reasonable default given its React
  API and light footprint, but use your judgement and note the choice in the commit
  message) and add it to trackr-frontend/package.json.
- Replace HistoricalChartPlaceholder.tsx's disabled state with a real line chart of
  market_value (and optionally invested, to show the cost-basis line alongside it)
  over the requested range, wired into trackr-frontend/app/page.tsx (Dashboard) where
  the placeholder currently sits.
- Use trackr-frontend/lib/format.ts's existing formatMoney/formatDate helpers for any
  axis labels or tooltips — do not do raw JS Number math on the money strings the API
  returns; those are Decimal-sourced and JS floats will silently misrepresent paise
  the same way CLAUDE.md rule 1 warns about server-side.
- A day with no persisted snapshot (before backfill's earliest reachable date, or a gap
  from a failed run) must render as an honest gap — do not interpolate a value between
  two known points. Match the project's general convention for this (the unpriced
  banner, MissingPriceNotice.tsx) rather than silently smoothing over it.

Write tests first where testable: a schema-level test for the new endpoint's response
shape (following the test_*_router.py pattern already used for the read-only routers),
and if a real DB test is feasible, one proving the range query returns exactly the
persisted rows in date order with no silent gap-filling.

Test the frontend manually: seed a handful of days of snapshots (either via Session 1's
backfill job against demo data, or by hand-inserting rows for a quick check), start the
app per docs/BUILD_PLAN.md, load the Dashboard, and confirm the chart renders real
values and that an empty range renders the same honest empty state the placeholder used
to show, not a broken or blank chart component.

Do not run `npm run build` while another `next dev` server might be running against this
same repo — it corrupts the shared `.next` build for anyone else using it. Use `tsc
--noEmit` for a type-check instead.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 3. Benchmark XIRR (NIFTY 50 TRI / SENSEX TRI)

```
Read CLAUDE.md and docs/ENGINE_SPEC.md §6 ("Benchmark comparison") first — it is short
and fully specifies the method; read it in full before writing any code.

Context: this is the one Phase 2 feature the contract already anticipates in detail.
contracts/openapi.yaml's GET /investors/{investor_id}/performance already declares a
benchmark query parameter (enum: [NIFTY50_TRI, SENSEX_TRI]) that the router silently
ignores today (app/routers/analytical.py's performance() accepts no such parameter at
all currently — the contract is ahead of the code). schema/performance.schema.json
already has a full benchmark object definition (name/xirr/terminal_value) and
app/schemas/analytical.py's BenchmarkOut model already exists — both unused. What's
actually missing is (a) a source of index-level TRI values and (b) the cash-flow
replication engine function itself.

Task:
1. Decide the index-level data source in Plan Mode (this is a new external dependency,
   not a code-only decision) — NSE publishes NIFTY 50 TRI values; confirm a concrete,
   reliably fetchable source before writing an adapter, following the same pattern
   app/prices/sources.py already uses for bhavcopy (HttpBhavcopySource-style fetch +
   parse). If no free, reliable, machine-fetchable TRI series is actually available,
   say so plainly in the plan rather than building against a source that will break in
   production — this is exactly the kind of external dependency CLAUDE.md's "ask, do
   not guess" rule is for.
2. Decide where index levels live: a new small table, or the existing `price` table
   with some clearly-distinguished synthetic key. Do NOT let an index level be
   confused with a security price anywhere in the schema or the engine — a NIFTY 50
   TRI value is not an ISIN's price and must not silently join against `security` or
   pass through app/engine/valuation.py's per-holding valuation path.
3. New app/engine/benchmark.py (a new module, not grown inside xirr.py — this is a
   distinct calculation, not a variant of portfolio XIRR) implementing exactly the
   method from ENGINE_SPEC.md §6:
   for each portfolio cash flow (date, amount): units = amount / index_level(date);
   accumulate units. benchmark_terminal = total_units * index_level(as_of).
   benchmark_xirr = xirr(same dates, same amounts, benchmark_terminal).
   Reuse app/engine/xirr.py's _transaction_flows for "the same dates, same amounts" —
   it is the exact same cash-flow universe compute_xirr already solves over (BUY/
   IPO_ALLOT negative, SELL/BUYBACK/DIVIDEND positive per §4) — do not reimplement
   cash-flow construction from scratch.
4. MVP benchmarks are TRI (total return) only, never a price index — ENGINE_SPEC.md is
   explicit that a price index excludes dividends and understates the benchmark. Add a
   test that would fail if a price-index level were substituted, so this constraint is
   pinned, not just documented.
5. Wire it into performance() (app/routers/analytical.py): read the benchmark query
   param, populate BenchmarkOut when requested, leave it null/absent when not
   requested — do not compute it on every request by default given the extra data
   dependency.
6. Frontend: trackr-frontend/app/performance/page.tsx and
   components/DualXirrCard.tsx (or a sibling card, following that component's existing
   conventions) — show the benchmark XIRR beside the portfolio's own xirr_all /
   xirr_holdings, never as a bare index CAGR (ENGINE_SPEC.md: "Comparing portfolio XIRR
   against a headline index CAGR is not a valid comparison and must not be shown" — this
   is a hard rule, treat a bare CAGR display as a bug, not a simpler alternative).
   trackr-frontend/lib/api-types.ts already has a BenchmarkOut interface stubbed —
   confirm it actually matches what the backend now returns rather than assuming it
   does.

Write the failing test first: hand-compute a small worked example (a handful of
BUY/SELL cash flows against a synthetic index-level series you construct by hand) and
add it to fixtures/engine_cases.json, following the existing case format, before writing
app/engine/benchmark.py. Then tests/test_benchmark.py covering the replication math
directly, plus a router-level test confirming the query param actually changes the
response.

Run `make test` and `make lint` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 4. Period-wise XIRR (1Y / 3Y / 5Y / FY)

```
Read CLAUDE.md first, then docs/ENGINE_SPEC.md's "Period XIRR (advisor onboarding)"
section (§4) — the primitive this session reuses. This session depends on Session 1
(daily snapshot persistence); do it after, not before, or every window's opening_value
falls back to an expensive on-the-fly recompute that may not even reach far enough back.

Context: app/engine/xirr.py's compute_period_xirr(transactions, prices, start_date,
opening_value, as_of) is already generic, already tested, and already used twice today
— as compute_fy_xirr's engine (financial_year_start(as_of) as start_date) and as the
adviser-onboarding period_xirr (investor.onboarding_date as start_date, wired in
app/routers/analytical.py's _period_xirr). docs/FEATURE_BACKLOG.md Phase 2 calls
1Y/3Y/5Y/FY windows "trivial once snapshots exist" — this session is exactly that: the
same primitive, four more start dates, each needing a fast opening_value lookup that
Session 1's persisted table now provides instead of a live compute_snapshot per window.

Task — start in Plan Mode (this changes an existing response shape, a contract
decision, not just an addition):
1. Decide whether fy_xirr and period_xirr (both already top-level fields on
   PerformanceResponse today) get folded into a new unified structure — e.g. a
   trailing_xirr: {label: value | null} map covering FY/1Y/3Y/5Y — or stay separate
   fields with three new siblings added (xirr_1y, xirr_3y, xirr_5y). Changing an
   existing field's shape is a breaking contract change for anything already reading
   fy_xirr/period_xirr as flat fields (the frontend's DualXirrCard.tsx, at minimum) —
   weigh that against a cleaner API before picking. Update contracts/openapi.yaml,
   schema/performance.schema.json, and app/schemas/analytical.py's PerformanceResponse
   together, not just the Python model.
2. Compute each window's start_date as resolved_as_of minus 1/3/5 calendar years (mind
   leap years — use a real date-arithmetic helper, not a naive `days=365*n` shortcut,
   which drifts by a day every four years and would make the "1Y XIRR" label subtly
   wrong).
3. Look up each window's opening_value from Session 1's persisted snapshot table,
   on/nearest-before that date. Generalize the existing pattern in _fy_xirr/
   _period_xirr (app/routers/analytical.py) into a shared helper taking (label,
   start_date) rather than copy-pasting the same MissingPriceError-catch-and-log
   structure four more times.
4. Each window must be independently omittable. A holding history shorter than 5 years
   (or a backfill that hasn't reached that far back) must blank ONLY the 5Y figure,
   never all four — this is the same "never guess a start date, never substitute a
   nearby one" discipline _fy_xirr already established, just applied per-window now.
5. Frontend: trackr-frontend/app/performance/page.tsx and DualXirrCard.tsx — a
   period selector (tabs or a small button row: FY / 1Y / 3Y / 5Y) next to the
   existing dual-XIRR display. Follow the existing null-handling convention (a window
   with no computable value shows as genuinely absent, not a blank "0.00%" that reads
   as a real number).

Write tests first: a case proving each window is computed independently (one missing
snapshot doesn't blank the other three), and confirm the existing fy_xirr/period_xirr
golden values in fixtures/engine_cases.json are unchanged if the refactor touches shared
code — this is an additive feature, it must not silently change an existing number.

Run `make test` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 5. TWRR (time-weighted rate of return)

```
Read CLAUDE.md and docs/ENGINE_SPEC.md §5's TWRR paragraph first (the last paragraph of
"Other return measures" — it is short: "TWRR (time-weighted) is Phase 2... Store dated
snapshots from day one and both become computable."). This session depends on Session 1
(daily snapshot persistence) — TWRR needs the full sub-period snapshot series between
two dates, not just the two endpoints, which is structurally different from every other
metric in this codebase so far.

Context: docs/FEATURE_BACKLOG.md Phase 2: "TWRR | Measures the adviser; XIRR measures
the client." docs/PRODUCT_VISION.md frames the distinction the same way. Unlike every
other Phase 2 item, ENGINE_SPEC.md does NOT give a worked formula for TWRR beyond naming
it and stating its purpose — it says snapshots unlock it, not how to chain them.

STOP before implementing: per CLAUDE.md's explicit rule ("Never invent financial logic.
Every rule in docs/ENGINE_SPEC.md is stated explicitly. If a case is not covered there,
ask — do not guess"), the exact chaining convention is NOT pinned anywhere in this repo
today. Standard TWRR implementations diverge on real details that produce different
numbers from the same data — true daily valuation vs. Modified Dietz approximation
between snapshot dates, how a same-day deposit-and-trade is treated, whether dividends
are treated as an external flow or a return component. Do not pick one silently. Either
find the precise rule already pinned somewhere in ENGINE_SPEC.md/fixtures that a
narrower search turns up, or write up the two or three candidate conventions and their
concrete numeric difference on a small example, and get an explicit answer before
writing app/engine code. This is exactly the "plausible-looking, silently wrong" failure
mode CLAUDE.md warns about elsewhere in this same document (see the Period XIRR
mid-period-deposit case in ENGINE_SPEC.md §4 for what that failure mode looks like when
it's caught, versus what it looks like when it isn't).

Task, once the exact chaining rule is confirmed:
- New app/engine/twrr.py (a distinct module — TWRR is a genuinely different algorithm
  from XIRR, not a variant of it, and does not belong bolted onto xirr.py just because
  the names are adjacent).
- Consume Session 1's persisted snapshot series between two dates (app/db/
  snapshots.py's range-read, likely the same one Session 2's chart endpoint uses) —
  chain sub-period returns geometrically between consecutive snapshot dates, with each
  external cash flow closing one sub-period and opening the next, per whatever
  convention was confirmed above.
- All Decimal, no float, per CLAUDE.md rule 1. Geometric chaining (a product of (1 +
  r_i) terms) is straightforward in Decimal; check how app/engine/xirr.py already
  delegates root-finding to pyxirr rather than hand-rolling it, and use the same
  external-library-over-hand-rolled-math judgement here if TWRR needs anything beyond
  multiplication (it generally doesn't — no root-finding is needed for TWRR itself,
  only for annualising it if that's part of what's confirmed above).
- Wire into app/routers/analytical.py (a new field on PerformanceResponse — update
  contracts/openapi.yaml and schema/performance.schema.json together) and
  trackr-frontend/app/performance/page.tsx, positioned as a companion to the XIRR
  figures, not a replacement — the whole point per docs/PRODUCT_VISION.md is that TWRR
  and XIRR answer different questions and both should be visible together, the same
  "never show one alone" discipline already applied to xirr_all/xirr_holdings.

Write the failing test first: a hand-computed TWRR worked example added to
fixtures/engine_cases.json, ideally cross-checked against a second independent method
(a spreadsheet, the way fixtures/golden_portfolio.json itself was validated twice per
CLAUDE.md) before trusting it as the pinned answer. Then tests/test_twrr.py against it.

Run `make test` and `make lint` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 6. Dividends as a first-class feature

```
Read CLAUDE.md and docs/DATA_MODEL.md's `txn_type` table (the DIVIDEND row) first.

Context: unlike most of this phase, the underlying data model and engine treatment
already exist and are correct — DIVIDEND is a full txn_type (qty=0, price=0, the amount
lives in a dedicated dividend_amount column, not price — docs/DATA_MODEL.md is explicit
about why: "dividends are per-holding cash events, not per-unit trades") and
ENGINE_SPEC.md §4's XIRR cash-flow table already includes DIVIDEND as a positive flow.
The only way a dividend reaches the ledger today is manual transaction entry
(trackr-frontend/app/transactions/page.tsx) — docs/FEATURE_BACKLOG.md Phase 2 is blunt
about why nothing automates this: "No data source provides these — manual or Console
report." This session does NOT add a new data source; it adds the missing display/
summary layer over dividends that are already, correctly, in the ledger.

Task:
- New app/engine/dividends.py (or extend app/engine/holdings.py if a small addition
  reads better once you're looking at it — use your judgement, but a new module is
  probably cleaner given this is a distinct aggregation, not a holdings computation):
  a function summing DIVIDEND transactions' dividend_amount per ISIN, and per
  financial year within each ISIN. Reuse financial_year_start (app/engine/xirr.py) for
  FY boundaries rather than reimplementing 1-April-to-31-March logic a second time.
- New endpoint — decide the shape and add it to contracts/openapi.yaml first (e.g. GET
  /investors/{investor_id}/dividends), backed by a new schema/*.schema.json file and a
  matching Pydantic model under app/schemas/. Router: app/routers/holdings.py (dividends
  are naturally holding-scoped) unless a case emerges for putting it in analytical.py —
  check how the existing routers are split by responsibility before deciding.
- Frontend: trackr-frontend/app/holdings/[isin]/page.tsx already shows FIFO lots and
  realised sale history for one ISIN (see its existing three-call pattern) — a
  dividend history section is a natural fourth call on that same page, following its
  existing layout conventions. Consider whether a portfolio-wide dividend summary also
  belongs somewhere (e.g. a small section on the Dashboard or a dedicated view) — not
  required for this session to be complete, but worth a deliberate yes/no rather than
  an oversight.
- Follow trackr-frontend/lib/format.ts's formatMoney/formatDate for display, and the
  existing component conventions (HoldingsTable.tsx, UnpricedBanner.tsx) for any new
  component rather than inventing new patterns.

Business logic note: a holding that has genuinely paid zero dividends is a real, known
zero — this is NOT the "missing price defaults to zero" case CLAUDE.md rule 4 forbids
(that rule is about VALUING an unpriced position at zero, which understates a return
figure; an equity that simply never declared a dividend has a true zero dividend total).
Do not add unnecessary caveats or "no data" language around a legitimate zero — but do
be precise in code comments if this distinction matters to a reviewer, since the two
zeros look identical in the UI and it's worth being deliberate about which one you're
looking at.

Write the failing test first: tests/test_dividends.py (or fold into test_holdings.py if
that reads better) with a hand-built transaction list including DIVIDEND rows across
more than one financial year for the same ISIN, asserting correct per-ISIN and per-FY
totals.

Run `make test` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 7. Sector / market-cap breakdown

```
Read CLAUDE.md first, then docs/DATA_MODEL.md's `security` table definition (the
`sector text null` column) and docs/trackr_plus_phase1_overview.md's §7 note on this —
it confirms `security.sector` is null for every row today BY DESIGN, and that
AllocationDonut.tsx's current single-slice rendering is correct Phase 1 behaviour, not a
bug to silently "fix" without the data behind it.

Context: docs/FEATURE_BACKLOG.md Phase 2: "Sector / market-cap breakdown | Needs a
security master with sector data." This is genuinely two things, and both need to be
done for the feature to mean anything: (a) get real sector classification into
security.sector for the ISINs actually held in this system, and (b) extend the
allocation view to group by sector once that data exists. Building (b) without (a) would
just be a differently-shaped version of today's honest single-slice placeholder.

Task — start in Plan Mode for part (a), it's a new external data dependency, not a code
change:
1. Decide the sector-data source. NSE publishes equity lists with industry/sector
   classification; confirm a concrete source before writing an importer. Do not hand-
   guess or hardcode a sector for any specific ISIN — that would be exactly the kind of
   fabricated-but-plausible data CLAUDE.md's fixture-integrity rules warn against
   elsewhere in this project, just applied to reference data instead of transaction
   data.
2. Build a narrow loader (a script or a small module under app/db/, following the
   shape of app/db/load_golden.py or app/db/seed_demo.py as loader-script precedent)
   that populates security.sector for ISINs already present in the `security` table —
   this is enrichment of an existing row, not a new table. schema/asset_classes.json
   is NOT the place for this — that file is asset_class codes (EQ, MF, etc.), a
   completely different concept from sector; do not conflate the two anywhere in this
   session's code or naming.
3. Engine: extend app/engine/holdings.py's existing allocation grouping (the same
   mechanism that already groups by asset_class for AllocationDonut.tsx, per
   ENGINE_SPEC.md §2's weight_pct = market_value / Σ market_value) to also group by
   security.sector. Reuse the existing weight_pct math exactly — this is a different
   grouping key over the same already-correct numbers, not a new calculation.
4. Router: app/routers/holdings.py (or wherever the existing allocation-by-asset_class
   response is served today — read it first) — add sector as an additional grouping
   dimension in the response, or a new query-param-selectable grouping, matching
   however asset_class is currently exposed.
5. Frontend: trackr-frontend/app/components/AllocationDonut.tsx — extend it past its
   documented single-slice Phase 1 state. A security whose sector is still null (not
   yet in the loader's coverage) must show as a genuinely, visibly "unclassified"
   slice — never silently merged into a fake "Other" bucket that hides the gap, per
   this project's general convention (the unpriced banner does the equivalent thing
   for missing prices).

Write tests first: a test proving sector-grouped allocation math on a hand-built
holdings list (mirroring how the existing asset_class grouping is presumably tested —
check for it first rather than assuming none exists), including one case with a null
sector to confirm it surfaces as unclassified rather than disappearing or crashing.

Test manually: seed sector data for a few ISINs actually in your test/demo portfolio,
load the Holdings or Dashboard page, confirm the donut shows real sector slices plus an
honest "unclassified" slice for anything not yet covered.

Run `make test` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 8. Contribution analysis

```
Read CLAUDE.md and docs/PRODUCT_VISION.md's "The intelligence layer" section first — it
names this exact feature ("Which holdings contributed most?") as the first real
intelligence-layer question the system should answer, distinct from the accounting
figures (holdings, XIRR) built so far.

Context: docs/FEATURE_BACKLOG.md Phase 2's last line: "Contribution analysis | First
real intelligence: which holdings drove the return." docs/FULL_VISION_BACKEND_ROADMAP.md
Section D calls it "the first real Intelligence-layer feature per
docs/PRODUCT_VISION.md." Unlike every other item in this phase, there is currently NO
formula for this anywhere in docs/ENGINE_SPEC.md — it names return measures (XIRR,
absolute return, CAGR, benchmark, TWRR) and reconciliation in detail, but never defines
"contribution."

STOP before implementing: per CLAUDE.md's explicit rule ("Never invent financial logic
... if a case is not covered there, ask — do not guess"), this session's FIRST
deliverable is not code. It is:
1. Writing a precise, worked-example-backed definition into ENGINE_SPEC.md itself (a
   new numbered section, e.g. §10 "Contribution analysis," following the existing
   sections' style: a formula, a worked example, an explicit statement of what's
   undefined and why).
2. Getting that definition confirmed before writing app/engine code against it.

A reasonable starting proposal to put in front of whoever confirms it (not to silently
treat as final): each holding's contribution to the portfolio's overall return over a
period = that holding's own realised + unrealised gain over the period, expressed as a
fraction of the portfolio's total gain over the same period. The genuinely open
questions that need an explicit answer, not a guess:
- A holding fully sold mid-period: does its realised gain still count toward
  contribution for the whole period, or only the portion of the period it was held?
- A holding bought mid-period: same question, the other direction.
- Does a holding with a negative return "contribute negatively," and if two holdings
  have offsetting positive/negative contributions bigger than 100% of the actual total
  return, is that shown as-is (which is mathematically correct but can look strange —
  e.g. one holding at +140% contribution and another at −40%) or normalized somehow?
Pin the answers in ENGINE_SPEC.md with a worked example the way §4's mid-period-deposit
case pins Period XIRR's behaviour, precisely because this is the same class of "looks
plausible, silently wrong" risk CLAUDE.md warns about — a contribution number that
quietly double-counts or drops a mid-period trade will look like a real number, not an
error.

Task, once the spec is written and confirmed:
- New app/engine/contribution.py implementing exactly what ENGINE_SPEC.md's new section
  now specifies.
- Add the worked example as a new case in fixtures/engine_cases.json, following the
  existing case format (see period_xirr_mid_period_deposit_not_inflated for the shape
  a case like this should take).
- Router: a new endpoint (add to contracts/openapi.yaml first) — likely
  app/routers/holdings.py given this is a per-holding breakdown of a portfolio-level
  number, but check whether it reads better in analytical.py given its dependence on
  return figures; use your judgement.
- Frontend: trackr-frontend/app/holdings/page.tsx or a new dashboard section — a
  ranked list (best/worst contributors) is probably the most useful presentation;
  follow HoldingsTable.tsx's existing sortable-table conventions if a table fits, or
  propose something else if a ranked list reads better, but stay consistent with the
  rest of the app's visual language rather than introducing a new UI pattern for one
  feature.

Write the failing test first, from the ENGINE_SPEC.md worked example added above.
tests/test_contribution.py.

Run `make test` and `make lint` before claiming done.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## Not included on purpose

A few things that came up while scoping this phase but deliberately aren't prompts
above:

- **CAS adapter (multi-broker reconciliation input).** Named explicitly in
  `docs/BUILD_PLAN.md`'s "what to build next" value-order list (#4) and in
  `docs/FULL_VISION_BACKEND_ROADMAP.md` Section D (as D8) — but it is **not** a line
  item in `docs/FEATURE_BACKLOG.md`'s Phase 2 table, which `CLAUDE.md` designates as the
  tie-breaker whenever docs disagree on scope. It's also a different kind of feature
  from the other eight — it feeds the *existing* Phase 1 reconciliation endpoint
  (`app/engine/reconcile.py`, ENGINE_SPEC.md §7) with real declared-holdings data
  instead of manual entry, rather than adding new analytics. Worth doing, but raise it
  with whoever owns product scope to confirm it belongs in this phase (vs. being treated
  as a Phase 1 reconciliation enhancement, or its own later phase) before turning it
  into a session prompt — the same reasoning `docs/PHASE1_CLOSEOUT_PROMPTS.md` used to
  park `holding_snapshot` wiring rather than defaulting it into a prompt.
- **Capital gains (Section 112A grandfathering, bonus stripping, demerger cost ratios,
  tax-software exports).** Explicitly Phase 3 per `docs/FEATURE_BACKLOG.md`, and gated
  behind "the MVP has run on real data for a full quarter" plus mandatory CA sign-off
  (`docs/TAX_ENGINE.md`) — even though `docs/BUILD_PLAN.md`'s value-order list places a
  capital-gains item 5th, right after this phase's items. Do not pull it forward; the
  gate is explicit and deliberate, not an oversight.
- **Mutual funds and any other new asset class.** Explicitly Phase 4
  (`docs/FEATURE_BACKLOG.md`) — `schema/asset_classes.json` seeds all 30 codes on
  purpose, as a lookup table, not a to-do list (`CLAUDE.md`'s own scope-discipline
  section says this plainly). Nothing in this phase should add engine support for a
  second `asset_class`.
- **Treating any Phase 2 output as "verified" in the `CLAUDE.md` sense.**
  `fixtures/golden_portfolio.json` is still not present on this machine
  (`docs/FULL_VISION_BACKEND_ROADMAP.md`'s "Decision (2026-08-16)" section — ask the
  client directly, in parallel with everything else, rather than blocking on it or
  fabricating a substitute). Every session above should report against
  `fixtures/engine_cases.json`'s hand-computed cases, and state plainly that the real
  324-trade acceptance bar is still pending, the same honesty discipline
  `docs/trackr_plus_phase1_overview.md` applied throughout Phase 1.
