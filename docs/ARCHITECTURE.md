# Architecture

## The four layers

```
┌─────────────────────────────────────────────────────────────┐
│  4. INTELLIGENCE      "why did this happen?"                │
│     attribution, concentration, sector drift, alerts        │
├─────────────────────────────────────────────────────────────┤
│  3. ANALYTICS         "what happened?"                      │
│     XIRR, TWRR, CAGR, allocation, benchmark, snapshots      │
├─────────────────────────────────────────────────────────────┤
│  2. ENGINE            "what is true?"                       │
│     FIFO lots, holdings, realised/unrealised, corp actions  │
├─────────────────────────────────────────────────────────────┤
│  1. INGESTION         "get the rows in"                     │
│     manual, CSV, tradebook, Gmail, (later: CAS, AA, API)    │
└─────────────────────────────────────────────────────────────┘
```

### Dependency rule

**Imports point downward only.** Layer 1 may not import from 2, 3, or 4. Layer 2 may
not import from 3 or 4. Enforce this in code review; it is the single thing that keeps
the system extensible.

The critical boundary is **1 → 2**. Ingestion's entire job is to produce a list of
`Transaction` objects. The engine has no idea whether a row came from a Zerodha
tradebook, a forwarded Gmail attachment, or a human typing into a form.

This is what makes "source-agnostic ingestion" real rather than aspirational: adding
Account Aggregator support in 2027 means writing one new adapter in layer 1 and
changing **nothing** in layers 2–4.

## Price is a separate pipe

A recurring mistake is treating prices as part of ingestion. They are not.

```
  CLIENT-SPECIFIC                        PUBLIC
  (who owns what, at what cost)          (what is it worth)
  ────────────────────────────           ─────────────────────
  transactions                           prices
  arrives: on trade, monthly             arrives: every day
  source: files, email                   source: bhavcopy / vendor
  scope: one investor                    scope: everyone
```

These pipes run on independent schedules and neither blocks the other. On a day with
no trades, the price job still runs and the dashboard still moves. This is exactly how
every mature tracker works, and it is why "live tracking" is really "daily sync plus a
price feed".

**Price source for MVP:** NSE + BSE end-of-day bhavcopy, merged, keyed by ISIN.
Both exchanges are required — real example: two holdings in our golden fixture
(`INE0N6U01018`, `INE0O4R01018`) do not appear in the NSE file at all.

## Component map

```
                    ┌──────────────┐
   Gmail ──────────►│              │
   CSV upload ─────►│  INGESTION   │──── Transaction[] ───┐
   Manual form ────►│  (adapters)  │                      │
                    └──────────────┘                      ▼
                                                  ┌───────────────┐
   NSE/BSE bhavcopy ──► PRICE JOB ──► prices ────►│    ENGINE     │
                                                  │  (pure funcs) │
                                                  └───────┬───────┘
                                                          │
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                     holdings       performance      snapshots
                                          │               │               │
                                          └───────────────┼───────────────┘
                                                          ▼
                                                    ┌──────────┐
                                                    │   API    │  openapi.yaml
                                                    └────┬─────┘
                                                         ▼
                                                    ┌──────────┐
                                                    │    UI    │
                                                    └──────────┘
```

## The engine is pure functions

Layer 2 must be implementable as pure functions: transactions in, results out. No
database calls, no network, no clock reads inside the calculation.

```
compute_holdings(transactions)                  -> Holding[]
compute_lots(transactions)                      -> Lot[]
compute_realised(transactions)                  -> RealisedGain[]
compute_xirr(transactions, prices, as_of)       -> Decimal
compute_snapshot(transactions, prices, on_date) -> Snapshot
```

Why this matters practically: it makes the golden fixtures runnable without any
infrastructure, and it means a rewrite in another language is a mechanical exercise
rather than an archaeology project.

Pass `as_of` explicitly. Never call `date.today()` inside the engine — that makes
tests non-deterministic and historical replay impossible.

## Suggested MVP stack (a suggestion, not a requirement)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | `pyxirr`, `pandas`, mature Decimal support |
| API | FastAPI | generates OpenAPI automatically; matches `contracts/openapi.yaml` |
| DB | Postgres (Neon) | `NUMERIC` type, JSONB for raw payloads |
| Jobs | cron (Render/Railway) | two jobs: price fetch, email poll |
| UI | Server-rendered templates | 20 holdings does not need an SPA |

## Swapping the stack

The stack above is disposable. The system is defined by:

1. `contracts/openapi.yaml` — the HTTP surface
2. `schema/*.schema.json` — the object shapes
3. `fixtures/*.json` — the correctness bar

Any implementation honouring those three is valid. Concretely, a developer preferring
Node + Prisma + Next.js, or Go + sqlc + htmx, should:

- generate types from `schema/*.schema.json` (use `quicktype` or equivalent)
- generate server stubs from `contracts/openapi.yaml` (`openapi-generator`)
- port `fixtures/golden_portfolio.json` into their test runner
- keep the four-layer dependency rule

Nothing in this repo assumes Python beyond the reference implementation. The
**contracts are the product**; the code is one expression of them.

## What is deliberately absent

| Not built | Why |
|---|---|
| Broker API integration | Daily client re-login; order-capable tokens; single-broker. See `docs/INGESTION.md`. |
| Credential storage | Legal exposure with no compensating benefit |
| Real-time tick feed | A long-horizon portfolio does not need intraday. EOD is sufficient and free. |
| Microservices | 20 holdings and 10 clients. A single process is correct. |
| Stored holdings cache | Violates the core rule. Recompute; it is milliseconds. |
