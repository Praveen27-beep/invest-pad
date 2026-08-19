# Feature Backlog

Derived from your developer's MProfit feature archaeology, re-sequenced by value and
dependency rather than by MProfit's menu structure.

**Reading rule:** everything in Phase 1 is scope. Everything after is a *backlog*, not
a plan. Do not build ahead.

---

## Phase 1 — MVP (equities only)

| Feature | Notes |
|---|---|
| Manual transaction entry | All 10 `txn_type` values including off-market, IPO, buyback |
| CSV / tradebook import, multi-file | Console caps downloads at 365 days |
| Import review before commit | Confidence score; **never auto-commit** |
| Import log with provenance | Which transaction came from which file |
| Holdings (weighted average) | Computed on read |
| FIFO lots | Runs alongside average cost |
| Realised + unrealised gains | Display only; not a tax return |
| **XIRR — all-time and current-holdings** | Both, always |
| Period XIRR | Adviser onboarding date |
| Absolute return, CAGR | CAGR per-holding only |
| Allocation (by holding, sector) | |
| Daily EOD price pipe (NSE + BSE) | Both exchanges mandatory |
| **Reconciliation vs CAS/broker holdings** | The corporate-action detector |
| Gmail forwarding ingestion | Contract notes |
| Audit log | DPDP + SEBI record-keeping |
| Client consent records | Before any client data lands |

---

## Phase 2 — Analytics depth (still equities)

| Feature | Why it waits |
|---|---|
| Daily snapshots | Unlocks the value chart and TWRR; needs historical bhavcopy backfill |
| Historical portfolio value chart | Needs snapshots first |
| Benchmark XIRR (NIFTY 50 TRI) | Cash-flow-replicated — see `ENGINE_SPEC` §6 |
| Period-wise XIRR (1Y / 3Y / 5Y / FY) | Trivial once snapshots exist |
| TWRR | Measures the adviser; XIRR measures the client |
| Dividends | **No data source provides these** — manual or Console report |
| Market-cap breakdown | Sector is done (Phase 1 row above, `app/db/load_sectors.py` / NSE Industry classification); market-cap bucketing is a separate, still-unbuilt security-master field |
| Contribution analysis | First real intelligence: which holdings drove the return |

---

## Phase 3 — Tax engine (highest risk)

Treat as its own project. See `docs/TAX_ENGINE.md`.

| Feature |
|---|
| STCG / LTCG classification per asset class |
| 31-Jan-2018 grandfathering |
| Indexation (CII table) for pre-Apr-2023 debt |
| Schedule 112A generation |
| ITR-format capital gains report |
| Bonus stripping rules |
| Demerger cost-ratio allocation |
| Tax software exports (ClearTax, Winman, CompuTax, Spectrum, Genius) |

**Gate:** CA review of one full FY before this informs any filing.

---

## Phase 4 — Multi-asset

Add classes in the order in `schema/asset_classes.json`. Mutual funds first — the
registrar CAS carries cost basis, so it is the cheapest second class by a wide margin.

Each new class needs: enum value, any class-specific `txn_type`s, holding-period rule,
data source, and golden fixtures. **No new tables.**

---

## Phase 5 — Practice tooling (the B2B layer)

This is where an adviser product diverges from a personal tracker.

| Feature | Notes |
|---|---|
| Family / client groups | Schema already supports `family_group_id` |
| Client sharing, read-only by default | SEBI posture |
| Cross-client global reports | AUM, allocation, top-5, closing balances |
| Model portfolio vs actual drift | **Your real differentiator.** "Which clients haven't bought the new idea yet?" |
| Concentration limits and alerts | |
| PaRRVA-ready performance export | |
| White-label branding | |

Model-portfolio drift is the feature MProfit does not have and an adviser genuinely
needs. It is worth more than any three tax exports.

---

## Deliberately not building

| Excluded | Reason |
|---|---|
| Broker API sync (Zerodha, Dhan) | Daily client re-login; order-capable token; single-broker. See `BLUEPRINT_REVIEW.md` §Corrected-1. |
| MF CAS API (PAN + OTP) | AMFI closed third-party MF Central access in September 2025 |
| Any credential storage | Legal exposure with no compensating benefit |
| Execution / order placement | Not a broker. Ever. |
| Auto-generated buy/sell recommendations | Would blur accounting software into regulated advice |
| Realtime tick feed | A long-horizon book does not need intraday |
