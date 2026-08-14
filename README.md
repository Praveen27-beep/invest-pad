# Portfolio Intelligence Platform — Specification

A complete build specification. Two audiences, one repo.

## If you are Claude Code

Read **`CLAUDE.md`** first, every session. Then work through
**`docs/BUILD_PLAN.md`** one session at a time. Never skip the fixtures.

## If you are the developer maintaining this

The stack is disposable. **The contracts are the product:**

| File | What it fixes |
|---|---|
| `contracts/openapi.yaml` | the HTTP surface |
| `schema/*.schema.json` | the object shapes |
| `fixtures/*.json` | the correctness bar |

Any language or framework honouring those three is a valid implementation. Prefer
Node + Prisma? Go + sqlc? Django? Fine — generate types with `quicktype`, generate
server stubs with `openapi-generator`, port the fixtures into your test runner, keep
the layer rule from `docs/ARCHITECTURE.md`. Nothing here assumes Python beyond the
reference implementation.

## Read in this order

```
1. docs/PRODUCT_VISION.md   what it is, and what it refuses to be
2. docs/ARCHITECTURE.md     four layers, dependency rule, stack swapping
3. docs/DATA_MODEL.md       six tables, invariants, extension points
4. docs/ENGINE_SPEC.md      exact maths - FIFO, XIRR, corporate actions
5. docs/INGESTION.md        Gmail forwarding, CSV, the legal boundary
6. docs/BUILD_PLAN.md       twelve sessions, in order
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
