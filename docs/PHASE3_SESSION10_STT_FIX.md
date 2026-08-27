# Phase 3, Session 10 — STT must not reduce taxable capital gains

Companion to `docs/PHASE3_PROMPTS.md` (same format, same "hand this whole block to a
fresh session" intent), written after Session 9's real-data reconciliation dry run
surfaced this as the one genuine bug candidate worth its own session. Read
`local/PHASE3_TAX_RECONCILIATION_REPORT.md` §5 in full before anything else — it has the
real evidence (a real Zerodha Tax P&L report compared against this engine's output) this
prompt only summarizes. That file is gitignored (real client data) — if it's missing on
your machine, ask whoever is running you for it before proceeding on memory of this
summary alone.

## Precondition

This touches `app/engine/` and very likely `schema/transaction.schema.json`. Per
`CLAUDE.md`: **start in Plan Mode.** Read the plan back, argue with it, get explicit
sign-off, then execute. Do not go straight to code.

## The bug

`schema/transaction.schema.json` documents `charges` as "Brokerage + STT + GST + stamp,
combined" — one lump sum. `app/engine/lots.py` applies that combined figure to both BUY
cost (`lots.py:70`, `cost_total = txn.quantity * txn.price + txn.charges`) and SELL
proceeds (`lots.py:138`, `proceeds_per_unit = (txn.quantity * txn.price - txn.charges) /
txn.quantity`), and that same `Realised.cost` / `Realised.proceeds` is what
`schedule_112a.py` and `itr_capital_gains.py` (`itr_capital_gains.py:126`,
`cost_of_acquisition = sum(r.cost for r in stcg_realised)`) report as Schedule CG figures.

Indian tax law (Income Tax Act, Section 48) disallows STT as a deductible expense when
computing capital gains on STT-paid equity — a well-established rule (it's the reason the
old Section 88E STT rebate was withdrawn at the same time). Bundling STT into `charges`
and letting it reduce cost of acquisition / increase-appearing sale proceeds therefore
**overstates cost, understates consideration, and understates reported capital gains** —
wrong in the direction that understates tax liability. This is exactly the "quietly
wrong" failure mode `docs/TAX_ENGINE.md` names as the reason this phase needs CA sign-off
before informing a filing.

**Corroborating evidence, already in the codebase:** Zerodha's own Tax P&L report (real
export, see the reconciliation report) reports per-scrip Realised P&L as a clean `Sell
Value − Buy Value` with **no charges netted in at all**, and gives combined charges only
as a separate portfolio-level total, specifically so the STT/non-STT distinction isn't
pre-judged. `app/ingest/zerodha_contract_note.py` **already parses STT out separately**
(`"stt": re.compile(r"Securities [Tt]ransaction [Tt]ax" + _AMOUNT)`) before summing it
into one `total_charges` and apportioning that combined figure — the data this fix needs
is already being extracted at ingestion time, it's just collapsed one step too early.

## What must NOT change

- **Phase 1's display numbers are out of scope.** `docs/DATA_MODEL.md` /
  `docs/ENGINE_SPEC.md` §1's weighted-average `invested`/`avg_cost` (computed in
  `holdings.py`, a separate code path from `lots.py`) should keep including all charges,
  STT included — that's real cash the investor spent, and it's a portfolio-performance
  number, not a tax filing. `CLAUDE.md`'s golden-fixture headline numbers (Invested
  1,579,245.74, Market value 1,360,575.42, both XIRRs) must not move. Confirm this with a
  test, don't just assume the two code paths stay isolated.
- **`zerodha_tradebook.py`'s `charges=0` convention is correct and must not change** —
  tradebook exports genuinely carry no charges; this bug is invisible on tradebook-sourced
  data and only lives wherever contract-note-sourced charges flow through, which is
  exactly why Session 9's reconciliation (tradebook-only) didn't surface it as a numeric
  mismatch — it was found by reading the code, not by a failing comparison.
- **One feature per session, one commit** (`CLAUDE.md`) — this is STT-in-cost-basis only.
  Don't fold in unrelated Phase 3 cleanup.

## Task

1. Decide, in the plan, how STT reaches the tax-facing layer without breaking the
   layer-purity rule (`app/engine/` takes plain data in, no `app.ingest`/`app.db` imports
   — `make lint` enforces this). Candidate shapes to weigh, not a prescribed answer:
   - A new `stt: Decimal = ZERO` field on `Transaction` (schema + engine type), separate
     from `charges`, populated by `zerodha_contract_note.py` from the STT figure it
     already parses (`parse_charges`) instead of folding it into the combined total.
   - Whether `Lot`/`Realised` need their own `stt`-tracking fields so `schedule_112a.py`/
     `itr_capital_gains.py` can subtract it out at the point of use, versus computing a
     second, tax-specific cost/proceeds figure earlier in `lots.py`'s replay.
   - Confirm from a current, authoritative source (not memory) whether STT applies to
     the BUY leg, the SELL leg, or both for delivery-based equity under current rules —
     this determines whether the fix needs to touch cost of acquisition, sale
     consideration, or both. Don't assume; the rate and which-leg rules have changed
     before Session 5's buyback caution in `docs/TAX_ENGINE.md` is a reminder of the same
     discipline.
   - `app/ingest/zerodha_tradebook.py` and any other adapter that only ever produces
     `charges=0` needs no change — `stt` defaults to zero the same way.
2. Update `app/engine/lots.py`, `app/engine/schedule_112a.py`, `app/engine/
   itr_capital_gains.py` per the plan so tax cost of acquisition / sale consideration
   excludes STT, while `Realised.cost`/`Realised.proceeds` (or a clearly-named
   tax-specific variant) stays correct for Phase 1's non-tax realised-P/L display, which
   should still include STT as a real cost.
3. Update `app/ingest/zerodha_contract_note.py` to carry the STT component through
   instead of discarding it into the combined `total_charges` sum.
4. Hand-computed unit tests, written first per `CLAUDE.md`'s "tests are the
   specification": a lot with STT-only charges (proves STT alone doesn't move the tax
   figure), a lot with STT + brokerage mixed (proves the split is real, not all-or-
   nothing), and a regression test pinning that `holdings.py`'s weighted-average
   `invested` is unaffected by this change. If useful, the real KDL numbers in
   `local/PHASE3_TAX_RECONCILIATION_REPORT.md` §4 (sell value 185,295.00, term SHORT, 69
   holding days) are a real-data anchor, though that specific case has `charges=0` so it
   won't exercise the STT path itself — construct a synthetic case for that.
5. Run `make test` and `make lint` before claiming done.

## When this is done

This does not by itself close `docs/TAX_ENGINE.md`'s verification gates #2 or #3 — it
fixes one bug gate #9's dry run found. Gate #2 (one full FY reconciled against a real
Zerodha Tax P&L) and gate #3 (actual CA sign-off) are still open; see
`local/PHASE3_TAX_RECONCILIATION_REPORT.md` §9 for what's left there. Note the fix in
`docs/TAX_ENGINE.md`'s "Status — 2026-08-21" note (append, don't rewrite it) once merged.
