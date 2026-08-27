# Tax Engine (Phase 3 — do not build in MVP)

The highest-risk component in the system. Specified now so the data model does not
block it; **built only after the MVP has run on real data for a full quarter.**

## Gate-ahead decision — 2026-08-20

Per `docs/PHASE3_PROMPTS.md`'s Session 0 precondition check, condition 1's second
branch: the product owner has explicitly decided to build Phase 3 ahead of "the MVP
has run on real data for a full quarter," on hand-computed test cases only. This is
recorded here in writing per that document's own rule ("get that decision in writing
... don't infer it from silence").

Consequences of this decision, unchanged from the gate's original intent:
- `fixtures/golden_portfolio.json` still does not exist on this machine as of this
  writing, so nothing produced under this decision may be called "verified" in
  `CLAUDE.md`'s sense.
- Nothing built under this decision may inform a real filing until **both** a full-FY
  reconciliation against a broker Tax P&L **and** CA sign-off (Session 9 in
  `docs/PHASE3_PROMPTS.md`) are complete.
- Sessions 1–4 and 6 of the nine-session plan had already landed (uncommitted) before
  this note was written; this decision formalizes what was, until now, implicit.

## ITR-format capital gains report and tax software exports — 2026-08-20

`docs/FEATURE_BACKLOG.md`'s Phase 3 table lists these as two rows; built as two
commits over the same underlying data (Sessions 2–7's classified, grandfathered,
indexed realised gains), per `docs/PHASE3_PROMPTS.md` Session 8.

- **ITR-format capital gains report**: shipped. Broader than Schedule 112A (LTCG
  only) — covers STCG under section 111A too. Field layout (Schedule CG items
  A2(i) and B3) sourced directly from CBDT's own AY 2026-27 ITR-2 offline utility,
  cross-confirmed against CBDT's AY 2026-27 validation-rules document; see
  `app/engine/itr_capital_gains.py`'s module docstring for the full sourcing trail
  and for two fields (section 94(7)/94(8) loss disallowance, section 54F deduction)
  the real form has that this codebase does not yet compute.
- **Tax software exports (ClearTax, Winman, CompuTax, Spectrum, Genius)**:
  evaluated, not built. Same "ask, do not guess" sourcing bar applied — none of the
  five vendors has a publicly findable, authoritative current column-level import
  spec (checked each vendor's own help documentation, downloadable templates, and
  third-party reverse-engineered samples). Building against a guessed layout risks
  a format that silently fails on import into the real tool, which is worse than
  not building it. Revisit once a real source exists: either a vendor publishes
  one, or someone with a live account can supply an actual exported/template file
  to build against.

## Why it waits

Realised-gain *display* (Phase 1) and tax-grade *computation* (Phase 3) are different
products. The first informs; the second is relied upon for a filing. The gap between
them is grandfathering, bonus stripping, demerger cost ratios, per-asset-class holding
periods, and annual budget changes — each independently capable of being quietly wrong.

## Grandfathering — 31 January 2018

For equity and equity mutual funds acquired before 1 Feb 2018:

```
cost_of_acquisition = max( actual_buy_price,
                           min( fmv_31jan2018, actual_sell_price ) )
```

Requires `security.fmv_31jan2018` — a one-time historical constant per ISIN. Source it
once from exchange archives.

## Indexation

Applies to debt mutual funds purchased before 1 Apr 2023, property, and unlisted
assets. Needs a static CII table (CBDT values, hardcoded, one row per FY).

```
indexed_cost = cost x (CII_sale_year / CII_purchase_year)
```

## Holding-period thresholds

Not uniform. Read `long_term_days` from `schema/asset_classes.json`:

| Class | Long-term after |
|---|---|
| Listed equity, equity MF, REIT, InvIT | 12 months |
| Debt MF (pre-Apr-2023), property | 24–36 months |
| Unlisted, physical | varies |

Budget 2024 cut REIT/InvIT from 36 to 12 months. **These change annually** — keep them
in data, never in code.

## Corporate action tax nuances

- **Bonus shares** enter the FIFO queue at cost 0, dated the ex-date. This makes bonus
  stripping computable.
- **Demergers** carry two ratios: a *quantity* ratio and a *cost* ratio. Brokers
  typically have only the quantity ratio, which is why broker tax P&Ls are frequently
  wrong on demerged shares. The cost ratio comes from the company's scheme document.
- **Buybacks** — treatment changed with effect from 1 Oct 2024; proceeds are now taxed
  as deemed dividend in the shareholder's hands. Verify current treatment before
  implementing.

## Never mutate history

An "Auto Corporate Actions" tool inserts **new adjustment transactions** after
confirmation. It never edits a historical BUY or SELL row. This is both an
architectural rule and an audit requirement.

## Verification gates

1. Every rule a pure function with hand-computed unit tests.
2. One full FY reconciled against Zerodha's own Tax P&L report.
3. **CA sign-off on one full FY before any client filing.**

Note that legitimate methodological differences exist between providers — MProfit
itself acknowledges its capital gains can differ from a broker's without either being
wrong. Know which methodology you implemented and why, and be able to state it.

### Status — 2026-08-21: gates #2 and #3 still open

A real-data dry run (`local/PHASE3_TAX_RECONCILIATION_REPORT.md`, gitignored — contains
real client data) ran a real, matched tradebook + Zerodha Tax P&L pair for one Zerodha
account through the actual Sessions 1–8 pipeline. Result: 12 of 16 positions reproduced
Zerodha's own numbers to the paisa, validating the FIFO engine against real broker data
for the first time. But the data covers only part of FY2026-27 (not a full FY — the gate's
literal requirement), and it surfaced a genuine bug candidate — STT is bundled into the
combined `charges` field and applied to tax cost basis, which Income Tax Act Section 48
disallows — that should be fixed before Schedule 112A or the ITR capital-gains report
informs anything real. **Gate #2 is not satisfied by this run alone. Gate #3 (CA
sign-off) is unchanged — untouched, and not something a coding session can satisfy on its
own.** See the report for the full reconciliation, the STT finding, and recommended next
steps. Nothing in this phase may yet be described as "verified" or inform a real filing.

### Status — 2026-08-21 (Session 10): the STT bug from the note above is fixed

`Transaction` gained an `stt` field (a subset of `charges`, not additive), threaded
through the contract-note adapter (`app.ingest.zerodha_contract_note`, apportioned pro
rata by turnover the same way `charges` is), the staging/DB pipeline, and the engine:
`Realised` gained `cost_stt`/`proceeds_stt`, and `app.engine.realised.tax_cost`/
`tax_proceeds` exclude STT from cost of acquisition and full value of consideration.
`app.engine.schedule_112a` and `app.engine.itr_capital_gains` now read those instead of
the raw, STT-inclusive `Realised.cost`/`.proceeds`. Phase 1's display numbers
(`holdings.py`'s weighted-average `invested`/`avg_cost`, and `Realised.cost`/`.proceeds`
themselves) are unchanged by design — proven by a regression test, not just assumed —
since STT is a real cash cost for that real-cash figure, and only the tax-facing view
excludes it. See `docs/PHASE3_SESSION10_STT_FIX.md` for the full task and
`local/PHASE3_TAX_RECONCILIATION_REPORT.md` §5 for the original finding.

This closes the one concrete bug the §5 finding named. It does **not** close gate #2 (a
full FY reconciled against a real Zerodha Tax P&L is still needed — this fix has not
itself been reconciled against real STT-bearing data, since the reconciliation dry run's
own dataset had `charges=0` throughout) or gate #3 (CA sign-off, unchanged, not something
a coding session can satisfy). Nothing in this phase may yet be described as "verified"
or inform a real filing.
