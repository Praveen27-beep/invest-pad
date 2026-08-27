# Phase 2 (Analytics Depth) — closeout prompts

Originally generated 2026-08-18 as eight from-scratch build prompts. **Rewritten
2026-08-20** after auditing the actual codebase against those eight: seven sessions are
implemented, tested, and committed; the eighth (contribution analysis) is implemented
and tested but sits uncommitted in the working tree. See `docs/
trackr_plus_phase2_overview.md` for the full file-by-file evidence — read it first, it
has the complete map this document assumes, including a real test run
(`460 passed, 246 skipped, 1 deselected, 0 failed`).

**This document no longer contains the original eight build prompts.** Building any of
the eight features from scratch would duplicate work that already exists and passes its
own tests — check `docs/trackr_plus_phase2_overview.md` §3 before assuming otherwise.
What follows is what's actually left: four short closeout sessions, in priority order,
plus a standing reminder that isn't a coding session at all.

**Every session below still respects the golden-fixture gate.** `fixtures/
golden_portfolio.json` is not present on this machine. Nothing here should fabricate a
replacement or describe its own output as "verified" in the `CLAUDE.md` sense — see
Session 5 below.

Suggested order: **1, then 2, then 3 and 4 in either order.** Session 1 is nearly free
(it's a review-and-commit, not new code) and unblocks nothing else, so there's no reason
to delay it. Session 2 (real-Postgres verification) is worth doing before 3 or 4 because
it's the one thing that would catch a DB-layer bug in *already-committed* Phase 2 code,
not just new work. Sessions 3 and 4 are independent of each other and of 1/2.

---

## 1. Commit contribution analysis (Phase 2 Session 8)

```
Read docs/trackr_plus_phase2_overview.md's §3 row for "Contribution analysis" and §7's
first bullet before doing anything else -- they name every file involved.

Context: contribution analysis (docs/ENGINE_SPEC.md section 10, the first genuine
intelligence-layer feature per docs/PRODUCT_VISION.md) is fully implemented and fully
tested right now, sitting uncommitted in the working tree. This is NOT a build session --
do not add scope, do not refactor, do not "improve while you're in there." CLAUDE.md's
"one feature per session, one commit per feature" rule exists precisely so a session like
this stays small.

First, re-check git status -- another concurrent session may have already committed this,
or changed it further, since this audit. If the untracked/modified files described below
are no longer present in that shape, stop and report what you actually find rather than
assuming this prompt is still accurate.

Untracked files this session should add:
- trackr-backend/app/engine/contribution.py
- schema/contribution.schema.json
- tests/test_contribution.py
- trackr-frontend/app/components/ContributionTable.tsx
- trackr-frontend/app/contribution/ (the new page)

Modified files this session should include (the wiring for the above):
- contracts/openapi.yaml (new GET /investors/{investor_id}/contribution path)
- docs/ENGINE_SPEC.md (new section 10)
- fixtures/engine_cases.json (new contribution_mid_period_buy_sell_and_dividend case)
- tests/test_analytical_router.py, tests/test_engine_cases.py, tests/test_types_match_schema.py
- trackr-backend/app/engine/types.py, app/routers/analytical.py, app/schemas/analytical.py
- trackr-frontend/app/components/Sidebar.tsx, trackr-frontend/lib/api-types.ts

Task:
1. Read the actual diff (`git diff` for modified files, read the untracked files in
   full) before committing anything. Confirm for yourself -- don't take this prompt's
   word for it -- that:
   - docs/ENGINE_SPEC.md section 10 has a formula, a worked example, and an explicit
     "what is still undefined" subsection, matching the style of every other numbered
     section in that file.
   - app/engine/contribution.py stays framework-free (no app.db/routers/schemas/ingest/
     prices/auth imports) and Decimal-only, no float.
   - The Makefile's `test` target already includes a `test-contribution` step
     (`pytest tests/test_contribution.py -v`) -- confirm this wasn't half-wired.
2. Run `.venv/bin/pytest tests/test_contribution.py tests/test_engine_cases.py
   tests/test_analytical_router.py tests/test_types_match_schema.py -v` and confirm
   everything passes. Then `source .venv/bin/activate && make test` for the full
   engine/contribution/demo-fixture/lint suite (the venv needs to be on PATH -- see
   docs/trackr_plus_phase2_overview.md section 7's note on this, it isn't a real
   failure if you forget it, but it looks like one).
3. Stage exactly the files listed above (not `git add -A` -- there may be unrelated
   work from a concurrent session in the same tree; check `git status` for anything
   that doesn't belong to this feature before staging).
4. Commit with a message describing what shipped and why, following this repo's
   existing commit style (see `git log` -- descriptive body, not just a one-liner,
   Co-Authored-By trailer).

Do not run `npm run build` in trackr-frontend/ if a `next dev` server might be running
against this same repo -- it corrupts the shared .next build. Use `tsc --noEmit` if a
type-check is needed.

This session's only deliverable is a clean, reviewed, correctly-scoped commit. If you
find something genuinely broken while reviewing, report it rather than silently fixing
it inside this commit -- that's a different session's scope.
```

---

## 2. Verify Phase 2's DB-backed tests against a real Postgres cluster

```
Read docs/trackr_plus_phase2_overview.md's section 7, the "DB-backed half of this
phase's own test suite has never actually run" bullet, first.

Context: tests/conftest_db.py spins up an ephemeral local Postgres cluster per test
session via initdb/pg_ctl found on PATH (or a Homebrew keg-only prefix) -- it does not
use Docker or an external DATABASE_URL, and its skip message ("Postgres binaries not
found (brew install postgresql@17)") is macOS-authored even though this box is Linux.
Every DB-backed test in this repo -- including every Phase 2 test that proves a
persisted table round-trips correctly -- has been skipping silently for this reason,
which means Phase 2's persistence layer (portfolio_snapshot, index_level, and the
sector-enriched security rows) has only ever been checked at the pure-function level,
never against a real database write-then-read.

This is a verification session, not a feature session -- the goal is to make the
existing skipped tests actually run and report what happens, then fix anything that
surfaces (which may be nothing; the code may be entirely correct and simply
unexercised).

Task:
1. Get initdb and pg_ctl onto PATH on this Linux machine. The straightforward route is
   the distro package (e.g. `apt-get install postgresql` on Debian/Ubuntu -- check
   `/usr/lib/postgresql/*/bin/` afterward, which is the typical install location and
   may need adding to PATH explicitly, mirroring what find_pg_bin() in
   tests/conftest_db.py already checks for in a Homebrew prefix). Docker is available
   on this machine as a fallback ONLY if package installation isn't feasible in this
   environment -- but note that tests/conftest_db.py wants local binaries, not a
   running server to connect to, so a Docker Postgres container alone won't satisfy it;
   you'd need to extract or install initdb/pg_ctl some other way. Try the direct package
   install first.
2. Once available, run the full suite: `.venv/bin/pytest tests/ -q -rs` and read what
   changes -- specifically how many of the current 246 skips convert to passes, and
   whether any convert to failures instead. The Phase 2 files most likely to be
   affected: tests/test_db_snapshots.py, tests/test_db_index_levels.py,
   tests/test_db_analytical.py, tests/test_holdings_router.py, plus the DB-marked cases
   inside tests/test_benchmark.py, tests/test_dividends.py, and
   tests/test_sector_sources.py.
3. If anything fails: this is a real bug in already-committed code, not something to
   paper over. Read the failure, find the root cause, fix it under
   app/db/snapshots.py, app/db/index_levels.py, app/db/load_sectors.py, or wherever the
   failure actually points -- not by loosening the test's assertion. Re-run to confirm
   the fix and that nothing else regressed.
4. If everything passes cleanly: report that plainly. Update
   docs/trackr_plus_phase2_overview.md's section 7 bullet on this to reflect that the
   DB-backed suite has now actually run and passed, with the real pass count, so this
   gap doesn't get re-flagged by a future session that doesn't know it's closed.

Do not skip straight to "mark it verified" -- CLAUDE.md's bar is a real run producing a
real result, not the absence of a skip message.
```

---

## 3. Market-cap bucketing (the unbuilt half of "Sector / market-cap breakdown")

```
Read docs/FEATURE_BACKLOG.md's current Phase 2 table entry for this ("market-cap
bucketing is a separate, still-unbuilt security-master field") and
docs/trackr_plus_phase2_overview.md's section 7 bullet on it first.

Context: sector allocation (the other half of this originally-combined feature) is done
-- app/db/load_sectors.py, app/engine/holdings.py's _sector_allocation,
AllocationDonut.tsx's grouping-agnostic rendering, all committed and tested. Market-cap
bucketing is a clean, separate, genuinely unbuilt gap: no market_cap column exists on
the security table (migrations/001_core.sql), and nothing anywhere in app/engine,
app/routers, app/db, or the frontend references market cap in any form (checked via a
repo-wide case-insensitive grep for "market.?cap" -- zero hits outside documentation).

This touches the schema, so start in Plan Mode per CLAUDE.md ("Plan mode for anything
touching the schema or the engine"). Decide, and get sign-off via the plan, on:
1. The data source. Market cap isn't a static classification the way NSE's sector list
   is -- it moves daily with price, and "large/mid/small-cap" bucket boundaries are
   themselves periodically redefined by AMFI/SEBI (the last several redefinitions have
   moved the large-cap/mid-cap and mid-cap/small-cap cutoffs). Two real options worth
   weighing explicitly rather than defaulting to the first one that looks workable:
   (a) a periodically-refreshed AMFI/SEBI classification list (the official large/mid/
   small-cap ranking, refreshed twice yearly) mapped onto held ISINs, closer to how
   app/prices/sector_sources.py sources sector today; or (b) computing market cap
   live from shares-outstanding x latest price, which needs a shares-outstanding data
   source this system doesn't have today and introduces a second kind of reference
   data with a different staleness profile than sector. If neither is a concrete,
   reliably fetchable source you can name and cite, say so plainly in the plan --
   CLAUDE.md's "ask, do not guess" rule applies to reference data exactly as it does to
   financial formulas, and a wrong or stale market-cap bucket is a materially different
   kind of wrong than a missing sector.
2. Whether this is a security-level classification (a stored bucket, refreshed
   periodically, mirroring security.sector's shape) or a computed-on-read value. Lean
   toward mirroring security.sector's existing pattern unless there's a concrete reason
   not to -- consistency with the sibling feature this is explicitly the other half of
   matters here.
3. New migration file trackr-backend/app/db/migrations/012_<name>.sql (the next free
   number after 011_index_level.sql) if a stored column is the chosen shape -- read
   that migration's own comments for the house style (CHECK constraints, WHY-focused
   comments) before writing this one.

Task, once the plan is agreed:
- A narrow loader mirroring app/db/load_sectors.py's shape if a stored classification
  was chosen.
- Extend app/engine/holdings.py's allocation grouping a third way (asset_class, sector,
  now market_cap_bucket), reusing the exact same weight_pct = market_value / Sigma
  market_value math -- this is a new grouping dimension, not a new calculation.
- Extend AllocationDonut.tsx's consumption (the component itself is already
  grouping-agnostic, per its own doc comment -- confirm that holds before assuming you
  need to touch the component itself, not just what calls it) with the same honest
  "Unclassified" treatment sector already established for anything outside coverage.
- Add the grouping to whichever endpoint currently serves allocation-by-sector
  (app/routers/holdings.py) and to contracts/openapi.yaml alongside it.

Write tests first: mirror however sector allocation is tested today (check
tests/test_holdings_router.py and any engine-level allocation test before assuming none
exists), including a null/unclassified case.

Run `make test` and `make lint` before claiming done. This is a new commit, separate
from Session 1's contribution commit above -- per CLAUDE.md, don't bundle them even
though both are "finishing Phase 2."
```

---

## 4. Fix the two Phase 1 field-test regressions blocking real Phase 2 usage

```
Read PHASE1_FIELD_TEST_REPORT.md in full first -- it has reproduced stack tracebacks,
exact reproduction steps, and independently-computed expected values for both findings
below, from real broker contract notes a client actually provided.

Context: this is technically Phase 1 scope (both bugs are in ingestion, not analytics),
but it belongs in this closeout list because it is the single biggest practical risk to
everything Phase 2 built: no matter how correct benchmark XIRR, TWRR, dividends, sector
allocation, or contribution analysis are, a brand-new investor cannot get a single
manually-entered transaction into the ledger today, and a specific class of real-world
file crashes the one CSV import path instead of being rejected cleanly. Neither finding
was hypothetical -- both were reproduced against this exact checkout, driven by
Playwright against the real running app, using real transactions from real contract
notes.

Finding 1 (CRITICAL): POST /investors/{id}/transactions
(trackr-backend/app/routers/transactions.py's create_transactions) inserts directly into
the transaction table, which has a foreign-key reference to security. Nothing on this
path creates the security row first, so ANY transaction referencing an ISIN not already
in the security table fails with an unhandled ForeignKeyViolation, surfaced to the
browser as a generic "Failed to fetch." For a fresh investor, every ISIN is new, so this
is a 100%-reproducible failure of the entire manual-entry path -- one of Phase 1's two
named ingestion methods in CLAUDE.md. app/db/imports.py's CSV path already handles this
correctly and explains why in its own comment ("the import IS how a new holding is
discovered") -- the fix here is almost certainly to give manual entry the same
security-row-creation step CSV import already has, not to invent a new mechanism.

Finding 2 (HIGH): trackr-backend/app/ingest/zerodha_tradebook.py decodes any upload as
UTF-8 and hands it straight to csv.DictReader before validating its shape. A file whose
bytes happen to contain a raw newline inside what csv.py reads as an unquoted field
raises an uncaught csv.Error, producing an unhandled 500 -- and because the crash
happens after CORS middleware has already handed off to the route, the response has no
CORS header, which Chrome reports as a CORS failure (a misleading symptom worth noting
in the fix's commit message so a future engineer doesn't chase the wrong thing). The
same adapter already has a graceful, specific rejection path for a different kind of
malformed input (a file missing required columns) -- the fix should extend that same
graceful-rejection discipline to cover a csv.Error during parsing, not introduce a
different error-handling shape.

Task:
1. Reproduce both findings first, against this checkout, before fixing anything --
   PHASE1_FIELD_TEST_REPORT.md has the exact ISINs, file, and steps. Confirm they're
   still live (another concurrent session may have already fixed one) rather than
   assuming the report is current.
2. Fix Finding 1: give create_transactions (or a shared helper it calls) the same
   security-row-creation-before-insert step app/db/imports.py already has, reusing that
   logic rather than reimplementing it if it's factorable into something both paths can
   call.
3. Fix Finding 2: catch csv.Error (and any other parse-time exception this adapter can
   realistically raise) inside zerodha_tradebook.py's parse path and turn it into the
   same kind of specific, structured rejection the missing-columns case already
   produces -- not a generic 500, and not a bare try/except: pass either. The response
   still needs a real HTTP status code (400 is right for "this file doesn't parse") and
   a message specific enough to be useful, matching this repo's existing error
   conventions (see how the missing-columns case is already worded).
4. Write a failing test first for each: a manual-entry transaction referencing a
   brand-new ISIN succeeds and creates the security row (extend whatever test file
   covers app/routers/transactions.py today); a malformed CSV with an embedded raw
   newline in an unquoted field is rejected with a clean 400, not a 500 (extend
   tests/test_zerodha_tradebook.py or wherever that adapter's other malformed-input
   cases live).

Run `make test` and `make lint` before claiming done. This is Phase 1 remediation, not
a Phase 2 feature -- keep it as its own commit, separate from anything else in this
document.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 5. Standing reminder — not a coding session

The golden fixture (`fixtures/golden_portfolio.json`, the client's real 324-trade
portfolio) is still not present on this machine. This has been a standing item since
before Phase 2 started and nothing above changes it — ask the client for it directly,
in parallel with everything else. Once it lands, `pytest tests/test_golden_portfolio.py
-v` is the one run that actually earns the word "verified" per `CLAUDE.md`'s own
definition, for both Phase 1's headline numbers and everything Phase 2 added on top of
them. Do not fabricate a substitute, and do not describe any of the four sessions above
as "verified" in commit messages or documentation — "tested against `fixtures/
engine_cases.json`" and "verified" are different claims; keep using the first one until
the fixture makes the second one true.

---

## Not included on purpose

Unchanged from the original plan, still correct:

- **CAS adapter (multi-broker reconciliation input).** Not a `docs/FEATURE_BACKLOG.md`
  Phase 2 line item; raise it with whoever owns product scope before turning it into a
  session prompt.
- **Capital gains (Section 112A grandfathering, bonus stripping, demerger cost ratios,
  tax-software exports).** Explicitly Phase 3, gated behind a full quarter of real data
  plus mandatory CA sign-off. Do not pull it forward.
- **Mutual funds and any other new asset class.** Explicitly Phase 4. Nothing in this
  closeout list should add engine support for a second `asset_class`.
