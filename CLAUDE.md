# CLAUDE.md

Read this file first, every session. It is the contract.

## What this is

A portfolio intelligence platform for Indian investors. **Not** a broker, **not** an
execution venue, **not** a PDF parser. The product is the *engine and the insight*;
parsing is a feature.

## The one architectural rule

**Everything is derived from transactions.**

```
Transactions -> Holdings -> Portfolio -> Performance -> Analytics -> Insights
```

Holdings are NEVER stored. They are computed on read, every time, from the
transaction ledger. If you find yourself writing `UPDATE holdings SET quantity = ...`,
stop — you have broken the architecture.

Consequences you must respect:
- The `transactions` table is **append-only**. No UPDATE, no DELETE.
- A correction is a new reversing transaction, not an edit.
- Any number shown to a user must be reproducible by replaying the ledger.

## Non-negotiable coding rules

1. **Money is `Decimal`. Never `float`.** Floats lose paise and reconciliation fails
   in ways that take days to find. In Python use `decimal.Decimal`; in Postgres use
   `NUMERIC(20,6)`; in JS use a decimal library, never a `number`.
2. **Securities are keyed by ISIN, never by ticker.** Tickers get renamed and reused.
   Real example from our data: Indosolar's ISIN now resolves to the symbol
   `WAAREEINDO`. The ISIN never moved.
3. **Every ingested row carries a `dedupe_key`.** Re-importing the same file must be
   a no-op. This is not optional — email forwarding *will* deliver duplicates.
4. **A missing price raises, never defaults to zero.** Silently valuing an unpriced
   holding at 0 understates XIRR catastrophically. Fail loudly.
5. **The ingestion layer never touches the analytics layer.** Parsers produce
   `Transaction` objects and stop. The engine must not know or care which broker,
   file format, or email a row came from.
6. **No broker credentials are ever stored.** Not passwords, not API tokens, not
   OTP secrets. Ingestion is file- and email-based by design. See
   `docs/INGESTION.md` for why this is a legal requirement, not a preference.

## MVP scope — Phase 1 only

**In:** Indian listed equities. Manual entry, CSV import, tradebook import, Gmail
forwarding. Holdings, FIFO lots, average cost, realised + unrealised P/L, dividends,
XIRR, absolute return, CAGR, allocation, benchmark comparison, historical value.

**Out (build the seams, not the features):** mutual funds, bonds, SGB, NPS, PMS, AIF,
REIT/InvIT, international, crypto, derivatives, CAS parsing, execution.

Do not build for the out-of-scope list. Do make sure adding it later requires no
schema migration — see `docs/DATA_MODEL.md`, the `asset_class` discriminator.

## Correctness is defined, not opinion

`fixtures/golden_portfolio.json` contains a real 324-trade portfolio with
independently verified answers (validated twice — once in Excel, once in Python).
**These are acceptance tests.** If your implementation disagrees, your implementation
is wrong.

Headline values you must reproduce exactly:

| Metric | Expected |
|---|---|
| Invested (current holdings) | `1579245.74` |
| Market value | `1360575.42` |
| XIRR — all transactions | `-0.174361` |
| XIRR — current holdings only | `-0.348107` |

Run `make test` before claiming anything works.

## How to work

- **Plan mode for anything touching the schema or the engine.** Read the plan back,
  argue with it, then execute.
- **One feature per session, one commit per feature.** Long sessions drift.
- **Tests are the specification.** Write the failing test first, from
  `docs/ENGINE_SPEC.md`, then make it pass.
- **Never invent financial logic.** Every rule in `docs/ENGINE_SPEC.md` is stated
  explicitly. If a case is not covered there, ask — do not guess.

## Scope discipline — read before adding anything

`schema/asset_classes.json` lists 30 asset classes. **Phase 1 builds exactly one: `EQ`.**
The list exists so the enum never needs a migration, not as a to-do list. Seeding all
codes is correct; building all codes is not.

Likewise `docs/FEATURE_BACKLOG.md` is a backlog, not a plan. If a feature is not in the
Phase 1 table there, do not build it — say so and move on.

## Three things that must never appear in this codebase

1. **A credentials table** — no `broker_token`, `api_secret`, `otp_secret`,
   `encrypted_token`. Ingestion is file- and email-based by design; this is the legal
   basis for operating without FIU registration. `make lint` fails the build.
2. **A holdings table written by anything but a rebuild** — holdings are computed on
   read. A cache is permitted only once profiling proves it necessary, and must always
   be reproducible from the ledger.
3. **`float` anywhere in `engine/`** — `make lint` fails the build.

## Where things live

```
docs/PRODUCT_VISION.md   why this exists, and what it refuses to be
docs/BLUEPRINT_REVIEW.md what was merged from the stack blueprints, and what was corrected
docs/STACK_DECISION.md   Django + Postgres, and why the stack is disposable anyway
docs/COMPLIANCE.md       DPDP + SEBI obligations and go-live gates
docs/FEATURE_BACKLOG.md  everything MProfit does, phased by value
docs/TAX_ENGINE.md       Phase 3 spec - grandfathering, indexation, CII
docs/ARCHITECTURE.md     layers, boundaries, and what may import what
docs/DATA_MODEL.md       tables, columns, invariants
docs/ENGINE_SPEC.md      exact calculation rules — FIFO, XIRR, corporate actions
docs/INGESTION.md        Gmail forwarding, CSV, tradebook; legal boundaries
docs/BUILD_PLAN.md       session-by-session build order for Claude Code
schema/*.schema.json     JSON Schema for every core object (language-agnostic)
schema/asset_classes.json  the 30 asset-class codes; seed all, build only `EQ`
contracts/openapi.yaml   HTTP API contract — swap any backend behind this
fixtures/*.json          golden test data with verified answers
```

## Reference stack

Django 5 + DRF + PostgreSQL, one deployable service. Engine and parsers stay pure and
framework-free so the stack remains swappable — see `docs/STACK_DECISION.md`.

## For the human maintaining this

The stack is a suggestion, not a requirement. `contracts/openapi.yaml` and
`schema/*.json` define the system. Any language or framework that honours those
contracts and passes `fixtures/` is a valid implementation. See
`docs/ARCHITECTURE.md` § "Swapping the stack".
