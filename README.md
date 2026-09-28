# Trackr+ — Portfolio Intelligence Platform

A portfolio intelligence platform for Indian listed equities. **Built and running**, not
a plan: FastAPI + raw SQL + PostgreSQL behind a Next.js dashboard.

## If you are Claude Code

Read **`CLAUDE.md`** first, every session, then **`docs/ARCHITECTURE_INVARIANTS.md`**
before touching anything financial. Do not work through a phase plan or a prompt archive
— `CLAUDE.md` separates the live specification from the historical archive, and the
archive is provenance, not requirements.

## If you are the developer maintaining this

The stack is disposable. **The contracts are the product:**

| File | What it fixes |
|---|---|
| `contracts/openapi.yaml` | the HTTP surface |
| `schema/*.schema.json` | the object shapes |
| `fixtures/*.json` | the correctness bar |

Any language or framework honouring those three is a valid implementation — generate
types with `quicktype`, generate server stubs with `openapi-generator`, port the fixtures
into your test runner, keep the layer rule from `docs/ARCHITECTURE.md`. Nothing here
assumes Python beyond the reference implementation. (One caveat: `docs/STACK_DECISION.md`
originally picked Django; that verdict was **reversed** and the file says so at the top.
Its Postgres-over-Firebase reasoning still stands.)

## Read in this order

```
1. CLAUDE.md                       the contract — scope, rules, where things live
2. docs/ARCHITECTURE_INVARIANTS.md the non-negotiable financial rules, and what is
                                   implemented vs unresolved vs deliberately excluded
3. docs/PRODUCT_VISION.md          what it is, and what it refuses to be
4. docs/ARCHITECTURE.md            four layers, dependency rule, stack swapping
5. docs/DATA_MODEL.md              tables, invariants, extension points
6. docs/ENGINE_SPEC.md             exact maths — FIFO, XIRR, corporate actions
7. docs/INGESTION.md               Gmail forwarding, CSV, the price pipe, legal boundaries
```

## Running it

```
make install      # editable-installs the root package and trackr-backend
make test         # acceptance gate: engine, contribution, tax, golden, fixture + lint
pytest tests/     # the full suite; DB tests need a live Postgres
make dev          # uvicorn app.main:app --reload
```

## The three things that matter most

**1. Everything derives from transactions.** Holdings are computed on read, never
stored. `transactions` is append-only; corrections are reversing rows.

**2. Correctness is defined, not argued.** `fixtures/golden_portfolio.json` is a real
324-trade portfolio with answers verified twice, independently. Hit these exactly:

| Metric | Expected |
|---|---|
| Invested | `1579245.74` |
| Market value | `1360575.42` |
| XIRR — all transactions | `-0.174361` |
| XIRR — current holdings | `-0.348107` |

**3. Never store credentials.** Ingestion is file- and email-based by design. This is
the legal basis on which the platform operates without regulatory registration — see
`docs/INGESTION.md`.

## Provenance

This spec was derived from a working, validated Excel implementation:
324 real trades (Oct-2022 → Aug-2026), reconciled against Zerodha's own holdings
export (17/20 positions matching exactly) and against two consecutive CDSL CAS
statements (17/17 positions, zero mismatches, correctly handling T+1 settlement).

The numbers in `fixtures/` are not invented test data. They came from a system that
already works. 
