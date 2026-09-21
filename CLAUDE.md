# CLAUDE.md

Read this file first, every session. It is the contract.

**Then read `docs/ARCHITECTURE_INVARIANTS.md` before planning or implementing any change
to financial data.** It holds the non-negotiable rules — never invent financial history,
detection may infer but resolution may not, identity changes are aliases rather than
transactions and never reset acquisition dates, failed verification is an exception and
never a guess. If a proposed implementation conflicts with one, **stop and flag the
conflict rather than improvising around it.** It also separates what is implemented and
verified from what is unresolved or deliberately excluded, so an intention is never read
as a guarantee.

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

## Scope — where the build actually is

**Asset class: Indian listed equities only.** That has not changed and is the boundary
that matters most. Phases 1–3 of `docs/FEATURE_BACKLOG.md` have substantially landed;
the phase numbers are a backlog ordering, not a statement that only Phase 1 exists.

**Built and in use:** manual entry, CSV import, tradebook import, Gmail forwarding,
contract-note PDF parsing, LLM-assisted extraction (off by default, staging-only). The
daily bhavcopy price pipe with historical archive tiers on both exchanges. Holdings,
FIFO lots, average cost, realised + unrealised P/L, XIRR, TWRR, absolute return, CAGR
(per-holding only — never a portfolio figure, see `docs/ENGINE_SPEC.md` §5), allocation,
contribution analysis, benchmark comparison, snapshots and historical value.
Corporate actions end to end — the reference table, three ledger paths, automated
BONUS/SPLIT verification, ISIN-change aliases. The Phase 3 tax engine — grandfathering,
indexation, Schedule 112A, ITR capital gains.

**Out (build the seams, not the features):** mutual funds, bonds, SGB, NPS, PMS, AIF,
REIT/InvIT, international, crypto, derivatives, execution. CAS *parsing* is still out;
CAS statements are consumed only as declared holdings for reconciliation.

Do not build for the out-of-scope list. Do make sure adding it later requires no
schema migration — see `docs/DATA_MODEL.md`, the `asset_class` discriminator.

**Dividends are modelled in four states, and conflating any two of them is the defining
mistake in this area.** `DECLARED` (a company announced an amount per share — the
`dividend_event` table) → `EXPECTED` (what a holder should receive: declared amount ×
quantity held at the ex-date — a projection computed on read, never stored) → `RECEIVED`
(evidence says cash arrived) → `REALISED` (a `DIVIDEND` ledger row exists, and therefore
enters XIRR, TWRR, contribution and realised income).

**There is deliberately no path from `EXPECTED` to `REALISED`.** "You should have received
₹10,000" and "you received ₹10,000" are different claims, and only the second belongs in a
performance figure. Declared and expected dividends are automated; **receipt is not**, and
the remaining gap is an ingestion-source one — no available feed carries a payment amount
or tax withheld, so `RECEIVED` needs a human or a credit advice. See
`docs/ARCHITECTURE_INVARIANTS.md` § "Future work" and `docs/INGESTION.md` Adapter 6 before
assuming anything downstream is broken.

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

Run `make test` before claiming anything works — but know what it covers. `make test` is
the **acceptance gate**: the hand-computed engine cases, contribution, the tax suite, the
golden portfolio, the demo fixture, and `make lint` (the architecture rules — no `float`
in the engine, no layer violation, no credential storage, no un-ignored client
documents). It is **not** the whole suite. The full run is:

```
.venv/bin/pytest tests/          # everything
```

A change that passes `make test` but was never put through `pytest tests/` has not been
regression-tested. Run the full suite before committing anything that touches `app/db/`,
`app/ingest/` or `app/routers/`.

**Two kinds of skip are normal and are not failures.** The `test_db_*.py` files spin up a
*throwaway* Postgres cluster from local binaries (`tests/conftest_db.py`) and skip cleanly
if `initdb`/`pg_ctl` are absent — install `postgresql@17` to actually exercise them. The
`test_zerodha_*` and redaction fixtures skip when real client documents are not on the
machine. **A green run with the DB tests skipped is a much weaker signal than it looks**;
check the skip reasons (`pytest tests/ -rs`) rather than the pass count alone.

## How to work

- **Plan mode for anything touching the schema or the engine.** Read the plan back,
  argue with it, then execute.
- **One feature per session, one commit per feature.** Long sessions drift.
- **Tests are the specification.** Write the failing test first, from
  `docs/ENGINE_SPEC.md`, then make it pass.
- **Never invent financial logic.** Every rule in `docs/ENGINE_SPEC.md` is stated
  explicitly. If a case is not covered there, ask — do not guess.

## Scope discipline — read before adding anything

`schema/asset_classes.json` lists 30 asset classes. **This system builds exactly one:
`EQ`.** The list exists so the enum never needs a migration, not as a to-do list. Seeding
all codes is correct; building all codes is not.

Likewise `docs/FEATURE_BACKLOG.md` is a backlog, not a plan. A row there is not
authorisation to build it — confirm the work is wanted before starting, and say so rather
than expanding scope on your own.

## Three things that must never appear in this codebase

1. **A credentials table** — no `broker_token`, `api_secret`, `otp_secret`,
   `encrypted_token`. Ingestion is file- and email-based by design; this is the legal
   basis for operating without FIU registration. `make lint` fails the build.
2. **A holdings table written by anything but a rebuild** — holdings are computed on
   read. A cache is permitted only once profiling proves it necessary, and must always
   be reproducible from the ledger.
3. **`float` anywhere in `trackr-backend/app/engine/`** — `make lint` fails the build.

## Where things live

**Code.** Everything that runs lives under `trackr-backend/app/` and `trackr-frontend/`.
The repo root still contains empty `engine/`, `db/`, `ingest/`, `prices/`, `api/` and
`storage/` directories holding nothing but `__pycache__` — leftovers from the
`trackr-backend/` move. They are **not** the source tree; ignore them, and read any
older doc that says `engine/x.py` as `trackr-backend/app/engine/x.py`.

```
trackr-backend/app/engine/    pure calculation — Decimal only, no framework imports
trackr-backend/app/ingest/    parsers and feeds — produce Transactions and stop
trackr-backend/app/prices/    the bhavcopy pipe and its sources
trackr-backend/app/db/        raw SQL repositories + numbered .sql migrations
trackr-backend/app/routers/   the HTTP surface
trackr-frontend/app/          Next.js App Router dashboard
tests/                        run from the repo root; imports `app.*` editable-installed
```

**Live specification — these describe what is true today.**

```
docs/ARCHITECTURE_INVARIANTS.md  the non-negotiable financial rules; READ FIRST
docs/ENGINE_SPEC.md      exact calculation rules — FIFO, XIRR, corporate actions
docs/ISIN_AUTOMATION.md  identity vs ratio; what's auto-verified vs permanently manual;
                         why merger/demerger never will be — dated 2026-09-20
docs/DATA_MODEL.md       tables, columns, invariants
docs/INGESTION.md        Gmail forwarding, CSV, tradebook, the price pipe; legal boundaries
docs/ARCHITECTURE.md     layers, boundaries, and what may import what
docs/TAX_ENGINE.md       grandfathering, indexation, CII, Schedule 112A
docs/COMPLIANCE.md       DPDP + SEBI obligations and go-live gates
docs/DEPLOYMENT.md       deploy steps, env vars, cron wiring
docs/KEY_ROTATION.md     encryption key rotation procedure
docs/BACKFILL_STRATEGY.md   how missing history is recovered, and what cannot be
docs/EMAIL_BACKFILL.md      the mailbox-history path specifically
docs/ONBOARDING_FLOW.md     the onboarding the app actually implements
docs/ONBOARDING_AS_IS_VS_TO_BE.md  a click-by-click trace of onboarding as it stands,
                         with the gaps named; dated 2026-09-07 against this branch
docs/ACCOUNT_AGGREGATOR.md  the AA route: why it is not taken today
docs/PRODUCT_VISION.md   why this exists, and what it refuses to be
docs/STACK_DECISION.md   why Postgres and one service — Django verdict SUPERSEDED, see its header
docs/FEATURE_BACKLOG.md  everything MProfit does, phased by value
schema/*.schema.json     JSON Schema for every core object (language-agnostic)
schema/asset_classes.json  the 30 asset-class codes; seed all, build only `EQ`
contracts/openapi.yaml   HTTP API contract — swap any backend behind this
fixtures/*.json          golden test data with verified answers
```

**Historical archive — do NOT read these as requirements.** They are dated session
prompts, build plans and point-in-time audits. Live code and tests cite them for
provenance, which is why they are kept, but every one of them describes the state of the
repo on the day it was written. **Where an archive doc and the live specification above
disagree, the live specification wins; where the live specification and the code
disagree, the code wins.** Never open a session by working through one of these.

```
docs/BUILD_PLAN.md, docs/PHASE1_CLOSEOUT_PROMPTS.md, docs/PHASE2_PROMPTS.md,
docs/PHASE3_PROMPTS.md, docs/PHASE3_SESSION10_STT_FIX.md,
docs/trackr_plus_phase1_overview.md, docs/trackr_plus_phase2_overview.md,
docs/trackr_plus_phase3_overview.md, docs/structure_revamp_plan.md,
docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md, docs/FULL_VISION_BACKEND_ROADMAP.md,
docs/BLUEPRINT_REVIEW.md, PHASE1_FIELD_TEST_REPORT.md
```

## Reference stack

**FastAPI + raw SQL (`psycopg`) + numbered `.sql` migrations + PostgreSQL**, with a
Next.js App Router frontend. There is **no Django, no DRF and no ORM** in this repository
— `docs/STACK_DECISION.md`'s original Django verdict was reversed on 14-08-2026 and that
file now carries the correction at the top. Introducing an ORM or a web framework is not
a refactor; it reopens a closed decision, and belongs in an update to
`STACK_DECISION.md` first.

Engine and parsers stay pure and framework-free so the stack remains swappable.

## For the human maintaining this

The stack is a suggestion, not a requirement. `contracts/openapi.yaml` and
`schema/*.json` define the system. Any language or framework that honours those
contracts and passes `fixtures/` is a valid implementation. See
`docs/ARCHITECTURE.md` § "Swapping the stack".
