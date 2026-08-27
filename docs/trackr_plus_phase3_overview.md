# Trackr-Plus Phase 3: Tax Engine — Overview & Status

Generated 2026-08-21, audited directly against the current working tree — not inferred
from `docs/PHASE3_PROMPTS.md`'s own session prompts, `docs/TAX_ENGINE.md`'s status
notes, or assumption. Every claim below was checked against the code, the migrations,
`contracts/openapi.yaml`, `fixtures/engine_cases.json`, and a real test run
(`.venv/bin/pytest tests/ -q -rs` → **553 passed, 254 skipped, 1 deselected, 0 failed**;
`ruff check trackr-backend/app tests` → clean; `make lint`'s three architecture checks —
no `float` in `app/engine/`, no cross-layer imports out of `app/engine/`, no credential
storage — all pass). Companion to `docs/trackr_plus_phase2_overview.md`: same audit
discipline, same "checked directly, not assumed" posture, for the highest-risk phase in
the system.

**The headline finding: eight of Phase 3's nine build sessions produced real, tested
code, but the phase has zero HTTP surface, zero frontend surface, one build session
that silently doesn't persist to the database, and neither of its two human-verification
gates has closed.** `make test` — the command `CLAUDE.md` says to run "before claiming
anything works" — does not execute a single one of Phase 3's 67 new tests; they only
run under a bare `pytest tests/`. None of this is hidden — `docs/TAX_ENGINE.md`'s own
"Status" notes and the reconciliation report they point to already say most of it — but
it has never been assembled into one place the way Phase 1 and Phase 2 each got. See §7
for the full list, and read it before treating anything in this phase as closed.

---

## 1. Executive Summary & Phase Goals

**Phase 1 and Phase 2 are closed** (per their own overview documents) — not
re-litigated here.

**What Phase 3 was scoped to be.** Per `docs/FEATURE_BACKLOG.md`'s Phase 3 table — the
document `CLAUDE.md` designates as the tie-breaker on scope — Phase 3 is **"Tax
engine (highest risk) ... treat as its own project"**: eight features that turn
Phase 1's realised-gain *display* into tax-grade *computation*, gated behind "CA review
of one full FY before this informs any filing." `docs/TAX_ENGINE.md` states the same
gate independently and adds a second, textual one: nothing may be built at all until
"the MVP has run on real data for a full quarter" — **or** the product owner explicitly
decides to build ahead of that, in writing. That decision was made and recorded on
2026-08-20 (`docs/TAX_ENGINE.md`'s "Gate-ahead decision" section): build ahead, on
hand-computed test cases only, accepting that nothing produced may be called "verified"
or inform a filing until the CA-sign-off gate separately closes. That is the authority
this phase's code was built under — it is real, it is written down, and it does not
by itself close the CA gate, which is a different, still-open thing (see below).

**What Phase 3 actually delivered, in one paragraph.** All eight `FEATURE_BACKLOG.md`
rows except one have working, unit-tested engine code: asset-class-aware STCG/LTCG
classification reading its threshold from `schema/asset_classes.json` rather than a
hardcoded 365; 31-January-2018 grandfathering exactly as `docs/TAX_ENGINE.md` states
the formula, gated on the *lot's* acquisition date, never the security's; indexation
for pre-April-2023 debt-MF lots against a new CBDT Cost Inflation Index table, raising
rather than defaulting to 1.0 on a missing year; bonus-stripping, confirmed (not
rebuilt — Phase 1's FIFO already did the work) with two new end-to-end test cases;
Schedule 112A and an ITR-format capital-gains report, both built by reading CBDT's own
current-AY primary sources column-by-column rather than reconstructing them from
memory, with the sourcing trail kept in the module docstrings; and demerger cost-ratio
allocation, a genuinely new `ENGINE_SPEC.md` §11 with a worked example, correctly
wired into both the weighted-average and FIFO replay paths. The eighth row — tax
software exports for ClearTax/Winman/CompuTax/Spectrum/Genius — was evaluated and
explicitly declined: no authoritative current column-level spec was findable for any
of the five vendors, and `docs/TAX_ENGINE.md` records that as a permanent-until-a-real-
source-exists decision, not an oversight.

**What Phase 3 is not, and has not touched.** No router, no Pydantic response schema,
and no `contracts/openapi.yaml` path exists for any tax module — every one of Sessions
2–8's functions is reachable only from Python, not HTTP. No frontend component
references any of it. Confirmed directly: grepping `app/routers/`, `app/schemas/`, and
`contracts/openapi.yaml` for `schedule_112a`, `itr_capital_gains`, `grandfathering`,
`indexation`, or `tax_classification` returns nothing. This is a materially different
shape of "not done yet" than Phase 2 ever had — Phase 2's features all had a
router the same session they got an engine function.

**Correctness bar — this phase's own decision, not the standing one.** Because Phase 3
was explicitly built ahead of "MVP on real data for a full quarter," `fixtures/
engine_cases.json`'s hand-computed cases are *not* this phase's bar the way they were
for Phase 1/2 — Phase 3 added no cases there at all (still 15, unchanged; see §3).
Instead, each of the eight built features has its own standalone test file with
hand-computed cases (67 tests total, §3), and Session 9 additionally ran a real
partial-year reconciliation against one real Zerodha account's own Tax P&L report.
Per `docs/TAX_ENGINE.md`'s verification gates, none of this may be called "verified" in
the `CLAUDE.md` sense: gate #1 (hand-computed unit tests) is met; gates #2 (one full FY
reconciled against a broker Tax P&L) and #3 (CA sign-off) are both explicitly open — see
§7.

---

## 2. Architecture & Data Flow

Unchanged at the top level:

```
Transactions -> Holdings -> Portfolio -> Performance -> Analytics -> Insights
```

Phase 3 adds a sixth stage below Analytics that nothing in Phases 1–2 needed: tax-grade
*reclassification and reporting* of numbers Phase 1 already computes, never a second
source of truth for them.

### 2a. What consumes what — confirmed by reading every module, not assumed

```
transaction ledger (append-only, unchanged)
        |
        v
compute_lots / compute_realised            (app/engine/lots.py, app/engine/realised.py
        |                                   -- unchanged Phase 1 FIFO, now STT-aware,
        |                                   see 2c)
        v
app.engine.tax_classification.classify_term     STCG/LTCG per Realised lot, reading
        |                                        long_term_days from schema/
        |                                        asset_classes.json (never hardcoded)
        v
   +----+----------------------------+
   |                                 |
   v                                 v
app.engine.grandfathering        app.engine.indexation
  (LTCG, pre-1-Feb-2018 lots        (MF_DEBT, pre-1-Apr-2023 lots
   only -- needs security.           only -- needs cost_inflation_index,
   fmv_31jan2018)                    not reachable in Phase 1/2 data today)
   |                                 |
   v                                 v
app.engine.schedule_112a.build_schedule_112a    LTCG-only, CBDT column layout
        |
        v
app.engine.itr_capital_gains.build_itr_capital_gains   STCG (111A) + reads
                                                         Schedule112AReport.total_ltcg
                                                         for its own LTCG (112A) line,
                                                         never re-derives it
```

`app.engine.demerger.demerger_cost_split` sits outside this chain — it is a correction
to the *cost pool* (feeding `holdings.py`'s weighted average and `lots.py`'s FIFO
replay directly, §2c), not a consumer of classified/grandfathered/indexed gains. It
produces two new `Transaction` rows (`DEMERGER_COST_OUT`/`DEMERGER_COST_IN`), never
edits, per `docs/TAX_ENGINE.md`'s "Never mutate history" rule — but see §7 for why
those rows cannot currently survive a save/reload round trip.

**Every arrow above is Python function calls within `app/engine/`, confirmed to have no
router or schema on either end.** Nothing in this diagram is reachable from
`contracts/openapi.yaml` today (§5).

### 2b. Reference data — two new sources, one already-existing pattern reused

```
security.fmv_31jan2018   <-- app/prices/fmv_31jan2018_source.py (locally-sourced CSV,
                              no live URL -- see its own docstring for why)
                          <-- app/db/load_fmv_31jan2018.py (loader, enrichment-only,
                              never inserts a security row)
                          -- migration 013_grandfathering_indexation.sql
                          -- NO REAL VALUES SEEDED YET (schema + loader only)

cost_inflation_index      <-- app/prices/cii_source.py (locally-sourced CSV, same
  (new table)                 reasoning as FMV -- no stable CBDT URL re-serves the
                              whole historical series)
                          <-- app/db/load_cii.py
                          -- migration 013_grandfathering_indexation.sql
                          -- NO REAL VALUES SEEDED YET (schema + loader only)

security.market_cap_bucket  <-- app/prices/market_cap_sources.py (AMFI XLSX, live URL,
  (NOT Phase 3 scope --         refreshed ~6-monthly)
   see note below)          <-- app/db/load_market_cap.py
                            -- migration 012_market_cap.sql
                            -- fully wired end to end: engine/holdings.py's
                               _market_cap_allocation, routers/holdings.py, schemas/
                               holdings.py, securities.py -- the ONE new module this
                               phase's diff touches that has a complete HTTP path
```

**Market-cap bucketing is not a Phase 3 feature** — it is `docs/FEATURE_BACKLOG.md`'s
Phase 2 "Sector / market-cap breakdown" row, the specific gap both
`docs/FULL_VISION_BACKEND_ROADMAP.md` and `docs/trackr_plus_phase2_overview.md`
flagged as unbuilt. It landed in this same working-tree pass, fully wired
(engine → router → schema, unlike everything actually in scope for this phase), and is
mentioned here only because it explains several of the "modified" files in `git status`
(`holdings.py`, `routers/holdings.py`, `schemas/holdings.py`, `securities.py`,
`migrations/012_market_cap.sql`) that are not tax code. It closes that standing Phase 2
gap; it is not evidence of Phase 3 progress.

`fmv_31jan2018` and `cost_inflation_index` are **schema and loader only** — both
migrations exist, both parsers exist and are tested against synthetic CSVs, but neither
has been pointed at a real source file and loaded. This is explicitly the sourcing work
`docs/PHASE3_PROMPTS.md` Sessions 3 and 4 scoped *out* of the engine session itself
("Sourcing real fmv_31jan2018 values is explicitly out of scope for the *code* in this
session ... it's data acquisition"). Confirmed directly: no CSV fixture for either
exists anywhere under `fixtures/`, and neither `load_cii.main()` nor
`load_fmv_31jan2018.main()` has ever been run against real data on this machine.

### 2c. STT — the one change that touches Phase 1's own code paths

Session 10 (`docs/PHASE3_SESSION10_STT_FIX.md`) is the one piece of this phase that
modifies code Phase 1 already shipped, rather than adding new modules beside it:
`Transaction.stt` (new field, schema + engine type + migration `014_stt_column.sql`),
threaded through `app.ingest.zerodha_contract_note`'s pro-rata apportionment (the same
turnover-weighted split `charges` already used, computed independently), the staging
payload round-trip (`app/db/imports.py`), the DB read/write path
(`app/db/repository.py`), and `app.engine.lots._replay`/`_consume`, which now carry a
per-lot `stt_per_unit` alongside `cost_per_unit` and emit `Realised.cost_stt`/
`.proceeds_stt`. `app.engine.realised.tax_cost`/`tax_proceeds` are the only new
consumers — `schedule_112a.py` and `itr_capital_gains.py` call these, never the raw
`Realised.cost`/`.proceeds`.

**Confirmed by direct read, not assumed: Phase 1's own numbers are untouched.**
`holdings.py`'s weighted-average `invested`/`avg_cost` still uses `txn.charges`
(STT-inclusive) exactly as before, and `Realised.cost`/`.proceeds` themselves are
unchanged — only the two new `tax_cost`/`tax_proceeds` functions exclude STT. A
dedicated regression test (`tests/test_holdings.py::
test_invested_is_identical_whether_stt_is_populated_or_zero`) pins this, matching
`docs/PHASE3_SESSION10_STT_FIX.md`'s own explicit requirement ("Confirm this with a
test, don't just assume the two code paths stay isolated").

### 2d. Layer rules — still holding, checked directly

`make lint`'s three architecture checks pass against the current tree, Phase 3 modules
included: `grep -rn "float(" trackr-backend/app/engine/` — zero hits.
`grep -rnE "^\s*(from|import) app\.(ingest|db|storage|prices|auth|routers|schemas)"
trackr-backend/app/engine/` — zero hits, confirming `tax_classification.py`,
`grandfathering.py`, `indexation.py`, `demerger.py`, `schedule_112a.py`, and
`itr_capital_gains.py` all take plain data in and return plain data out, exactly as
`docs/PHASE3_PROMPTS.md`'s non-negotiable rule #2 requires. The credential-storage grep
is unaffected — nothing in this phase touches auth or broker credentials.

---

## 3. Feature & Test Matrix

Rows follow `docs/FEATURE_BACKLOG.md`'s Phase 3 table order exactly, so the mapping
stays legible.

| Feature | Engine File | Router / Schema | Test Suite | Status |
|---|---|---|---|---|
| STCG / LTCG classification per asset class | `app/engine/tax_classification.py` | none | `tests/test_tax_classification.py` (6 tests) | ✅ **Built & tested, not exposed over HTTP.** Reads `long_term_days` from `schema/asset_classes.json`; raises `CapitalGainsNotApplicableError` rather than guessing for classes like FD/PPF_EPF where the threshold is `null`. |
| 31-Jan-2018 grandfathering | `app/engine/grandfathering.py` | none | `tests/test_grandfathering.py` (6 tests) | ✅ **Built & tested, not exposed over HTTP.** Date-gated on the lot's own `open_date`, never the security's listing date. |
| Indexation (CII table) for pre-Apr-2023 debt MF | `app/engine/indexation.py` | none | `tests/test_indexation.py` (7 tests) | ✅ **Built & tested, not exposed over HTTP.** Raises `MissingCIIError` on a lookup miss, never defaults to 1.0. **No real CII values loaded** — `cost_inflation_index` is an empty table on any real database (§2b, §7). |
| Schedule 112A generation | `app/engine/schedule_112a.py` | none | `tests/test_schedule_112a.py` (12 tests) | ✅ **Built & tested, not exposed over HTTP.** Column layout sourced from CBDT's own AY 2026-27 CSV-upload instructions and validation-rules document, cited in the module docstring; the Rs 1,25,000 exemption is one notch weaker-sourced (no primary CBDT page reachable, only secondary confirmation) — see §7. |
| ITR-format capital gains report | `app/engine/itr_capital_gains.py` | none | `tests/test_itr_capital_gains.py` (5 tests) | ✅ **Built & tested, not exposed over HTTP.** Field layout read from CBDT's actual AY 2026-27 ITR-2 offline utility workbook via `openpyxl` (not a regex scrape). Sections 94(7)/94(8) loss disallowance and 54F deduction are named-but-always-zero — real form fields this codebase does not compute, documented as such, not silently omitted. |
| Bonus stripping rules | `app/engine/lots.py` (existing FIFO, unchanged this phase) | none | `tests/test_lots.py`'s `test_bonus_pushes_a_zero_cost_lot_at_the_action_date` and `test_bonus_stripping_scenario_sells_original_at_a_loss_keeps_bonus_lot` | ✅ **Confirmed, not rebuilt** — exactly the outcome `docs/PHASE3_PROMPTS.md` Session 5 anticipated ("largely a verification task ... not new logic"). No new module exists because none was needed. |
| Demerger cost-ratio allocation | `app/engine/demerger.py`, wired into `app/engine/holdings.py` and `app/engine/lots.py` | none | `tests/test_demerger.py` (7 tests) | 🟡 **Engine built, tested, and correctly wired into both replay paths — but cannot be persisted.** No migration adds a `cost_transfer` column to `transaction`; `app/db/repository.py`'s INSERT/SELECT and `app/db/imports.py`'s staging round-trip never reference it. A `DEMERGER_COST_OUT`/`DEMERGER_COST_IN` pair built by `demerger_cost_split` and saved via `save_transactions` today would silently lose its `cost_transfer` value on the next read. See §7 — this is the single most concrete gap in the phase. |
| Tax software exports (ClearTax, Winman, CompuTax, Spectrum, Genius) | — | — | — | ❌ **Evaluated, explicitly declined.** `docs/TAX_ENGINE.md`: no authoritative current column-level import spec is publicly findable for any of the five vendors; building against a guessed layout risks a silent import failure, judged worse than not building it. This is a written decision, not an oversight — revisit only if a vendor publishes a spec or someone with a live account supplies a real template. |
| *(ninth, unnumbered row)* CA reconciliation & sign-off | — | — | `local/PHASE3_TAX_RECONCILIATION_REPORT.md` (gitignored, real client data) | 🟡 **Dry run complete, both formal gates still open.** See §7. |

**All ten new Phase 3 test files pass as their own suite:**
`.venv/bin/pytest tests/test_tax_classification.py tests/test_grandfathering.py
tests/test_indexation.py tests/test_demerger.py tests/test_schedule_112a.py
tests/test_itr_capital_gains.py tests/test_cii_source.py
tests/test_fmv_31jan2018_source.py tests/test_market_cap_sources.py
tests/test_import_staging.py -q` → **67 passed, 0 failed, 0 skipped.** `tests/
test_import_staging.py` is not a tax-rule test — it pins the STT staging-payload round
trip (§2c) specifically, added because Session 10 found that a correctly-computed field
can still be silently dropped at the staging boundary, a distinct failure mode from
never computing it.

**`fixtures/engine_cases.json` was not extended this phase** — still 15 cases, the same
count Phase 2 left it at (§3 of `docs/trackr_plus_phase2_overview.md` cites 16; the
discrepancy is unresolved and not investigated as part of this audit, but the file as it
stands today has 15, confirmed by direct count). No demerger, grandfathering,
indexation, or classification case was added there. This is a real divergence from
Phase 1/2's own convention (every new formula got a worked example folded into the
shared fixture) — not necessarily wrong, since Phase 3's ten standalone test files serve
the same "hand-computed, specification-first" role, but worth naming so a future session
does not assume `engine_cases.json` is Phase 3's test-of-record the way it was for
Phases 1–2.

---

## 4. Engine & Formula Specifications

Every formula below is implemented exactly as `docs/TAX_ENGINE.md` states it — checked
by reading each implementation against its spec section directly, not assumed from a
plausible-looking function name.

**STCG/LTCG threshold** — `classify_term(realised, asset_class, long_term_days)`
raises `CapitalGainsNotApplicableError` when `long_term_days` is `None`, and is
strictly-greater-than at the boundary (a lot held exactly `long_term_days` is SHORT;
`long_term_days + 1` is the first LONG day), matching `engine/lots.py`'s existing
Phase 1 convention. The threshold itself is never hardcoded in the function body — it
is a required parameter, resolved once by `long_term_days_for` from an
already-parsed `schema/asset_classes.json`.

**Grandfathering** — `grandfathered_cost_of_acquisition(lot, fmv_31jan2018,
sell_price)` implements `max(buy_price, min(fmv_31jan2018, sell_price))` verbatim.
The date gate (`GRANDFATHERING_CUTOFF_DATE = date(2018, 2, 1)`) is checked against
`lot.open_date` — the FIFO-derived acquisition date — never the security's listing
date or any other proxy, exactly as `docs/TAX_ENGINE.md` requires. Falls back to
`lot.cost_per_unit` (no grandfathering) whenever either the date gate or a missing
`fmv_31jan2018` makes the formula inapplicable — never a raised error for the common
case of "this security never needed one."

**Indexation** — `indexed_cost_of_acquisition(cost, purchase_fy, sale_fy,
cii_table)` implements `cost × (CII_sale_year / CII_purchase_year)`. The 1 April 2023
cutoff is expressed as `INDEXATION_CUTOFF_FY = "2023-24"` (a named constant, string-
compared against FY labels, not a bare date literal). A missing FY in `cii_table`
raises `MissingCIIError` rather than defaulting to 1.0 or silently skipping
indexation — `CLAUDE.md` rule 4 ("a missing price raises, never defaults to zero"),
applied here to CII lookups exactly as the module's own docstring states.

**Demerger cost-ratio** — `demerger_cost_split` and its two ledger-replay consumers
(`engine/holdings.py`'s weighted-average pool adjustment, `engine/lots.py`'s
`_spread_cost_delta`) both implement `ENGINE_SPEC.md` §11's proportional-by-quantity
spread: `per_unit_shift = delta / total_open_quantity`, applied flatly to every open
lot regardless of that lot's own size. Both consumers raise `DemergerAdjustmentError`
when there is no open position to adjust, the same failure posture as
`NegativeHoldingError` on the quantity side. This section did not exist in
`ENGINE_SPEC.md` before this phase — written and confirmed with the product owner on
2026-08-20, per `CLAUDE.md`'s "never invent financial logic ... ask" rule, exactly as
§10 (contribution analysis) was in Phase 2.

**Schedule 112A** — `build_schedule_112a` reproduces both of CBDT's two row shapes:
scrip-wise "BE" rows (acquired on or before the grandfathering cutoff, needs per-ISIN
FMV) and a single consolidated "AE" row (acquired after, ISIN literally
`INNOTREQUIRD`, name `CONSOLIDATED`) for everything else — a real, non-obvious CBDT
convention that a guessed implementation would very likely have missed. Column-by-
column sourcing (CBDT's CSV-upload instructions, cross-confirmed by the AY 2026-27
validation-rules document) is cited in the module docstring with retrieval dates.
`SECTION_112A_EXEMPTION = Decimal("125000")` is named and commented as the one number
in this module the docstring itself flags as one notch weaker-sourced — confirmed
only by secondary sources, not a primary CBDT page — and explicitly marked for
re-confirmation at CA sign-off (Session 9) rather than trusted blindly.

**ITR-format capital gains report** — `build_itr_capital_gains` covers STCG under
section 111A (Schedule CG item A2, sub-item (i)) in addition to Schedule 112A's LTCG,
per `docs/FEATURE_BACKLOG.md`'s framing of this as the broader of the two report rows.
Field Sl.No. labels were read out of CBDT's actual AY 2026-27 ITR-2 offline utility
workbook (`ITR2_AY_26-27_V1.3.xlsm`) using `openpyxl` against the workbook's own named
Excel ranges — the docstring notes a first-pass regex read gave the wrong Sl.No.
because of merged cells, and that this was caught before shipping, not after. B3a
(LTCG total) is read directly off `Schedule112AReport.total_ltcg` rather than
re-summed, matching the CBDT workbook's own formula (`=ROUND(Total_Balance_112A,0)`)
exactly — a genuine cross-module consistency guarantee, not a coincidence.

**STT exclusion** — `tax_cost(realised) = realised.cost - realised.cost_stt`;
`tax_proceeds(realised) = realised.proceeds + realised.proceeds_stt`. Both are one-line
functions in `app/engine/realised.py`, but the STT figure they consume is threaded all
the way from `zerodha_contract_note.py`'s own already-parsed-but-previously-discarded
STT regex match, through the staging payload, the DB columns, and `lots.py`'s per-lot
`stt_per_unit` tracking (§2c) — the arithmetic is trivial; the plumbing is not, and all
of it is exercised by tests.

---

## 5. API Router Contracts

**None.** Checked directly against `contracts/openapi.yaml`: the only path this phase's
diff adds is `/investors/{investor_id}/contribution`, which is Phase 2's contribution-
analysis endpoint (§7 of `docs/trackr_plus_phase2_overview.md` already flagged this as
sitting uncommitted). Grepping the contract for `tax`, `schedule`, `112a`, `itr`,
`grandfather`, `indexation`, or `demerger` returns nothing. `app/schemas/` has no
Pydantic model for any Phase 3 report, and `app/routers/` has no file that imports
`tax_classification`, `grandfathering`, `indexation`, `schedule_112a`, or
`itr_capital_gains`.

This is a scope statement, not a claim that something is missing that should already
be there — none of the nine `docs/PHASE3_PROMPTS.md` sessions asked for an HTTP layer,
and `docs/TAX_ENGINE.md`'s own gates make an HTTP-exposed, self-service tax report a
premature thing to ship before CA sign-off exists at all. It is recorded here because
`docs/trackr_plus_phase2_overview.md`'s own §5 exists and a reader comparing the two
documents should not have to infer the absence from silence.

---

## 6. Frontend & UI Specifications

**None.** `git status` shows exactly three frontend files touched this pass
(`Sidebar.tsx`, `page.tsx`, `lib/api-types.ts`), and all three are Phase 2's
contribution-analysis wiring (confirmed by reading each diff directly — the
`api-types.ts` additions are `Contribution`/`ContributionResponse` types, nothing
tax-shaped). No component, page, or generated type anywhere in `trackr-frontend/`
references Schedule 112A, the ITR report, grandfathering, indexation, or demerger cost
ratios.

---

## 7. Known Gaps & Risks (Honesty Section)

Ranked by how directly each blocks the phase's own stated purpose — informing a real
filing — rather than by how it was discovered.

- **Demerger cost-ratio corrections cannot be persisted.** `app/engine/demerger.py`'s
  `demerger_cost_split` produces `DEMERGER_COST_OUT`/`DEMERGER_COST_IN` transactions
  carrying a `cost_transfer` value, and both `docs/ENGINE_SPEC.md` §11 and
  `docs/DATA_MODEL.md` document a `cost_transfer numeric(20,6)` column the same way
  `dividend_amount` already exists. **That column does not exist in the database.**
  No migration among `012`–`014` (or any earlier one) adds it; `app/db/repository.py`'s
  `_INSERT`/`load_transactions` and `app/db/imports.py`'s staging payload round-trip
  all omit it (confirmed by reading every line that touches the `transaction` table).
  `Transaction.cost_transfer` defaults to `ZERO` on the dataclass, so a
  `DEMERGER_COST_OUT`/`DEMERGER_COST_IN` pair saved via `save_transactions` today would
  not error — it would silently write everything except the one field that makes the
  correction meaningful, and reload as a no-op adjustment forever after. `tests/
  test_demerger.py`'s 7 tests all exercise the pure function directly and never touch
  `save_transactions`, so nothing currently in the suite would catch this. This is the
  single most actionable gap in the phase: a one-migration, two-file fix, not a design
  question.
- **`make test` does not run any of Phase 3's tests.** The `Makefile` was updated for
  Phase 2's `test-contribution` target but not for any of the ten new Phase 3 test
  files — `test: test-engine test-contribution test-golden test-demo-fixture lint`
  invokes none of `test_tax_classification.py`, `test_grandfathering.py`,
  `test_indexation.py`, `test_demerger.py`, `test_schedule_112a.py`,
  `test_itr_capital_gains.py`, `test_cii_source.py`, `test_fmv_31jan2018_source.py`,
  `test_market_cap_sources.py`, or `test_import_staging.py`. Confirmed by running
  `make test` directly: it reports success (`All checks passed!`) having executed
  exactly 0 of the phase's 67 tests. `ruff check .` inside `lint` still covers these
  files for style, so a real regression would eventually surface as a lint failure at
  best — `pytest tests/` (no path argument) is the only command that currently
  exercises this phase at all. Given `CLAUDE.md`'s own instruction to "run `make test`
  before claiming anything works," this gap means every session that followed that
  instruction literally this phase would have seen a misleadingly clean result.
- **CII and FMV reference tables are empty on any real database.** Both migrations and
  both loaders exist and are unit-tested against synthetic CSVs, but no real CBDT CII
  series or exchange-archive FMV list has been sourced or loaded — this was explicitly
  scoped out of Sessions 3/4's own code ("sourcing real values is data acquisition, not
  this session's job"). Practically: `indexed_cost_of_acquisition` and
  `grandfathered_cost_of_acquisition` are correct functions with nothing to look up yet,
  for any lot that isn't supplied test data directly.
- **Gate #2 (one full FY reconciled against a broker Tax P&L) is not met.** A real
  dry run (`local/PHASE3_TAX_RECONCILIATION_REPORT.md`, gitignored — real client data,
  not reproduced here) ran one real, matched tradebook + Zerodha Tax P&L pair for one
  account through the actual Sessions 1–8 pipeline. Result: 12 of 16 in-window
  positions reproduced Zerodha's own open-quantity/value figures to the paisa — real
  external validation of the FIFO engine against broker data for the first time — and
  the run surfaced the STT-in-cost-basis bug that Session 10 then fixed (§2c). But the
  data covers only part of the current financial year, not a full FY as the gate
  literally requires, and none of grandfathering, indexation, demerger cost ratios, or
  bonus stripping were exercised on real data at all (every real trade in the window
  postdates 2018 and is plain equity). The dry run earned its keep; it did not close
  the gate.
- **Gate #3 (CA sign-off) is untouched, and cannot be closed by a coding session.**
  `docs/TAX_ENGINE.md` is explicit about this, restated here because it's the gate that
  actually matters: nothing in this phase may inform a real filing until an actual CA
  has reviewed one full FY's reconciled output. No date, plan, or engagement for that
  review exists in this repository as of this writing.
- **`fixtures/golden_portfolio.json` is still absent.** Unchanged, standing gap from
  Phase 1 — still worth asking the client for directly, still the thing that would let
  any of this be called "verified" rather than "built" in `CLAUDE.md`'s strict sense.
- **A real-client-data-derived report is already committed and already pushed.**
  `PHASE1_FIELD_TEST_REPORT.md` (repo root) contains real name/ISIN/quantity/cost-basis
  detail, is not covered by any `.gitignore` rule, and — confirmed directly —
  is tracked by git (`git ls-files`) inside commit `c4d12af`, which the current branch's
  upstream (`origin/backup-safe-checkpoint`) shows as already pushed to the GitHub
  remote. This was flagged as a housekeeping risk inside the (correctly gitignored)
  `local/PHASE3_TAX_RECONCILIATION_REPORT.md` itself, but nothing has acted on that
  flag yet. This is not a Phase 3 code gap, but it was surfaced by this phase's own
  reconciliation session and remains open — worth the user's own judgment call on
  remediation (e.g. history rewrite, or extending `.gitignore` to catch report-shaped
  files going forward) rather than a default action, given how disruptive rewriting
  already-pushed history is.
- **Nothing in this phase is committed.** Every file listed in `git status` — all ten
  new engine modules, three new migrations, ten new test files, and every modified doc
  — sits uncommitted in the working tree atop `c4d12af`, exactly as Phase 2's
  contribution-analysis work did before it. Unlike that case, this is nine sessions'
  worth of work, not one.
- **Two real Schedule CG fields are permanently unimplemented, by design, not by
  gap.** Section 94(7)/94(8) loss disallowance and Section 54F deduction are both
  always reported as `0` in `itr_capital_gains.py` — no detection logic for either
  scenario exists anywhere in this codebase, and the module docstring says so plainly.
  Correct for a filer who triggered neither; silently wrong for one who did. Not a
  regression to fix so much as a scope boundary a CA reviewing this phase's output
  needs to know about explicitly.
- **`SECTION_112A_EXEMPTION` (Rs 1,25,000) is sourced one notch weaker than everything
  else in this phase.** The module's own docstring says so: no primary CBDT page
  stating the figure in plain text was reachable, only multiple secondary sources
  agreeing on it. Flagged for re-confirmation at CA sign-off, not silently trusted.
- **Buyback tax treatment remains explicitly out of scope**, unchanged from
  `docs/TAX_ENGINE.md`'s own standing caution: treatment changed 1 Oct 2024 and the
  spec itself says to verify current treatment before implementing anything. No session
  this phase built buyback-specific tax logic, and none should without that
  verification happening first.
- **Concurrent sessions.** Unchanged risk from both prior overview documents — re-check
  `git status` and `git log` before starting any further Phase 3 or closeout session;
  this document's snapshot goes stale the moment another session commits.
