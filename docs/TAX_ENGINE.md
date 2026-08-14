# Tax Engine (Phase 3 — do not build in MVP)

The highest-risk component in the system. Specified now so the data model does not
block it; **built only after the MVP has run on real data for a full quarter.**

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
