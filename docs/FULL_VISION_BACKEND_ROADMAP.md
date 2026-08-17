# Full-Vision Backend Roadmap

Everything that remains to be built, audited directly against the current code — not
against `docs/structure_revamp_plan.md` or `docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md`'s
assumptions, which were written when `trackr-backend/app/` was still an empty skeleton.
Since those documents were written, the Phase 4 move they described has actually been
executed on disk. This document audits what exists now.

**Planning and audit only.** Nothing in this document was implemented by writing it —
see "Method" below for how the audit was done, including what was run.

---

## Important: this repo has four other active sessions on it right now

`ListAgents` shows four other interactive Claude Code sessions on this machine, open
against this same repository, started between 1 and 3 hours before this audit. One of
them almost certainly executed the `trackr-backend/app/` migration this document audits
— the resulting file layout, naming (`app/db/`, `app/ingest/webhook.py`,
`app/storage/factory.py`, `008_auth.sql`, `session_token_hash`) and even in-code comments
match `docs/structure_revamp_plan.md` and `docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md`
file-for-file. That is a good sign — it means the plan was followed, not diverged from —
but two things follow from it:

1. **This snapshot can go stale within the hour.** Re-run the "Method" checks below
   before acting on any specific line item if time has passed.
2. **Nothing from this migration is committed.** `git status` shows the entire move as a
   mix of staged renames, unstaged modifications, and untracked new files — 80+ files
   changed, zero commits. With multiple sessions active on the same working tree, this is
   the point to either commit it (so concurrent work has a shared base to branch from) or
   coordinate who is holding the working tree — not to keep layering further changes on
   top of an uncommitted move. Flagging this; not committing it, since that decision
   belongs to whoever is coordinating the other sessions.

---

## Method

Every claim below was checked against the actual repository, not inferred from the two
planning documents:

- Read all of `docs/*.md` (`PRODUCT_VISION`, `ARCHITECTURE`, `DATA_MODEL`, `ENGINE_SPEC`,
  `INGESTION`, `COMPLIANCE`, `TAX_ENGINE`, `FEATURE_BACKLOG`, `BUILD_PLAN`,
  `BLUEPRINT_REVIEW`, `KEY_ROTATION`, `STACK_DECISION`), `contracts/openapi.yaml`,
  `schema/*.json`, and `CLAUDE.md`.
- Read every file under `trackr-backend/app/` — not just listed it — including all six
  routers, `app/auth/*`, `app/ingest/webhook.py`, `app/storage/factory.py`,
  `app/config.py`, `app/database.py`, `app/main.py`, and the new `008_auth.sql` migration.
- Ran `.venv/bin/pytest -q -rs`: **221 passed, 127 skipped, 0 failed.** Every skip has a
  legitimate, printed reason — no Postgres binaries in this environment,
  `fixtures/golden_portfolio.json` absent, real broker files absent. Nothing is silently
  green.
- Ran `.venv/bin/ruff check trackr-backend/app tests`: **clean.** (Bare `make lint` fails
  in a non-activated shell only because `ruff` isn't on `PATH` outside `.venv/bin` —
  environment issue, not a code issue. `make lint`'s three architecture greps — no float
  in `app/engine/`, no cross-layer imports, no credential field names — all pass silently
  before that point.)
- Grepped for specific claims (e.g. `advised_only`, `reconcile`, `MultiFernet`) rather
  than assuming a feature exists because a file with a plausible name does.
- Confirmed `fixtures/golden_portfolio.json` does not exist anywhere on this machine
  (`find / -iname golden_portfolio.json` — empty).

---

## Decision (2026-08-16): the golden-fixture gate is deferred, not abandoned

`fixtures/golden_portfolio.json` is the client's own real 324-trade portfolio. It was
gitignored on purpose when the repo was shared with the developer — correct handling of
real personal financial data, not data loss. The developer working this repo doesn't
have a copy; the client does.

**Decision:** proceed through the backend (and later frontend, and later phases)
without it, rather than blocking on a file that isn't available yet. Two things make
this safe rather than reckless:

1. **The correct fix for A10 is asking the client for the file directly** — he's
   reachable, he has it, and it costs him nothing to hand over a JSON export. This
   should still happen, in parallel with everything else, not be replaced by the
   decision below.
2. **`fixtures/engine_cases.json` — 10 hand-computed cases from `ENGINE_SPEC.md`,
   already present, already passing — is the interim correctness bar** while A10 is
   open. It's real, independently-verified math (worked out by hand, not reverse
   engineered from a test file), just not at 324-trade real-world scale.

**Hard rule that follows from this:** no file gets created at `fixtures/golden_portfolio.json`
except the client's real one. A synthetic or "temporary" replica built to satisfy
`test_golden_portfolio.py`'s 11 assertions would make the test pass without proving
anything — the exact failure mode `CLAUDE.md` names when it says *"if your
implementation disagrees, your implementation is wrong."* A fabricated file can't
disagree with anything; it was written to agree. If a lighter smoke-test of the test
*plumbing itself* is ever wanted, it must live under a clearly different name, be
labelled as a plumbing check, and never be presented as evidence of correctness.

Every phase below can proceed on this basis. What it means in practice: nothing gets
called "verified" in the `CLAUDE.md` sense — the specific bar the client's own spec
sets — until the real file lands and `test_golden_portfolio.py` passes against it. That
stays true whether it happens after Phase 1, or as one consolidated real-data pass after
several phases are built. State it plainly whenever a phase is reported "done" so it
doesn't quietly get treated as fully closed.

---

## Master status table — every item, one place

**Read this table's third column carefully.** "Needs real client data" and "needs a
running Postgres" are different requirements — a running Postgres can be exercised with
made-up test rows (that's what every `test_db_*.py` file already does) and is a solvable
infrastructure problem. Needing *real client data specifically* means no amount of
infrastructure fixes it — only two rows in this entire document have that property, and
they're marked accordingly.

Status legend: ✅ done · 🟡 partial · ⏸️ blocked on a decision, not a build task · ❌ not
started.

### Section A — Backend Phase 1

| Item | Status | What's left |
|---|---|---|
| A1 — Manual transaction entry | ✅ | Nothing to build. Re-verify via Step 8 (artifact) when convenient — no real data needed. |
| A2 — Reconciliation endpoint | ✅ | Same — re-verify only. |
| A3 — FY XIRR wiring | ✅ | Same — re-verify only; this session also found and fixed a real engine bug. |
| A4 — `advised_only` filter | ✅ | Same — re-verify only. |
| A5 — Investor/account onboarding | 🟡 Contract only, router not built | Decide the 4 open questions (PAN on create vs. separate call; add `GET /investors`?; inline schemas vs. `components/`; the new tag) — see A5's prose below — then build + test. No real data needed. |
| A6 — HTTP-layer test coverage | ✅ 48 tests added | Nothing to build. Some of these tests need a running Postgres; none need real client data. |
| A7 — Grievance HTTP route | ❌ | Build a router over the already-working `app/db/grievance.py`. First decide whether intake can be unauthenticated (it needs to accept complaints from people with no investor record yet). No real data needed. |
| A8 — Price-alert delivery | ❌ | Wire a real notifier (email/Slack/whatever you pick) into `prices/alerts.py`, which already calls it on every failure — only the notifier itself is a stub. Testable by forcing a failure path; no real data needed. |
| A9 — Portfolio absolute return / CAGR | ⏸️ Blocked on Section B | Needs `net_invested` defined in `ENGINE_SPEC.md` and an explicit yes/no on portfolio-level CAGR before it's buildable at all. No real data needed once decided. |
| A10 — Golden portfolio fixture | ⏸️ Deferred by decision | **Needs real client data. No substitute exists.** Ask the client directly — see the Decision section above. |

### Section C — Frontend

| Item | Status | What's left |
|---|---|---|
| Everything in Section C's checklist | ❌ 0% built | Full Next.js build — see the itemized checklist below. Most of it (pages render, generated types match `openapi.yaml`) is testable with no backend running at all. A full login/data round-trip needs a *running* backend + Postgres with seeded test data — still not real client data, just infrastructure. |

### Sections D–G — later phases, "if possible"

| Item | Status | What's left |
|---|---|---|
| D — Analytics depth (D1–D8) | ❌ Not started | See Section D below for the 8 sub-items. None require real client data to build or unit-test; benchmark/historical-value accuracy is more meaningful once A10 eventually lands, but that's a quality concern, not a blocker. |
| E — Tax engine | ❌ Not started | **The other item in this document that structurally requires real data** — `docs/TAX_ENGINE.md` gates itself on "the MVP has run on real data for a full quarter" plus mandatory CA sign-off before any number informs a filing. Can be built and unit-tested against hand-computed cases the same way the engine was; cannot be *trusted* without real data any more than A10 can. |
| F — Multi-asset | ❌ Not started | New asset class per `FEATURE_BACKLOG.md`'s order (mutual funds first). No real data needed to build; will eventually want its own golden fixture, same principle as A10, for whichever real account represents that asset class. |
| G — Practice tooling | ❌ Not started | B2B layer. No real data needed to build. |

### Section I — Process / infrastructure

| Item | Status | What's left |
|---|---|---|
| CI | ❌ None | Add a workflow running `pytest` + `ruff` on push. No real data needed. |
| Docker / `docker-compose.yml` | ❌ None | Gives you a reproducible local Postgres instead of hand-extracting binaries each time. No real data needed. |
| Commit the migration | ⏸️ Deferred by you | Whenever you're ready to test and commit yourself. |

Underlying system-level facts, for reference: engine (`app/engine/`) is all 11 files,
moved verbatim, 10/10 `engine_cases.json` cases passing. DB layer (`app/db/`) is 14
modules plus new `app/auth/`, migrations `001`–`008` present. HTTP layer is 6 routers in
`app/main.py`/`app/routers/` with a full exception-handling layer. `make lint`'s three
architecture checks pass.

---

## Section A — Backend, Phase 1 (MVP): what's left to close it out

These are the gaps inside the scope `CLAUDE.md` and `docs/FEATURE_BACKLOG.md` Phase 1
already commit to. Everything here is scoped tightly against code that already exists —
none of it requires new engine logic.

### A1. Manual transaction entry has no HTTP endpoint

`app/db/repository.py:save_transactions` exists and is exactly what
`contracts/openapi.yaml`'s `POST /investors/{investor_id}/transactions` needs
(idempotent on `dedupe_key`, returns `{inserted, skipped_duplicates, rejected}`) — but no
router calls it. `app/routers/transactions.py` currently only has the three `GET`
endpoints (`transactions`, `lots`, `realised`).

This is the literal first line of `docs/FEATURE_BACKLOG.md`'s Phase 1 table ("Manual
transaction entry — All 10 `txn_type` values including off-market, IPO, buyback") and
`docs/BUILD_PLAN.md` Session 8, and it's the fallback path every other adapter needs when
parsing fails. **Nothing blocks this** — wire a `POST` handler in
`transactions.py` calling `save_transactions`, with a Pydantic request model covering
all 10 `txn_type` values from `docs/DATA_MODEL.md`.

### A2. No reconciliation endpoint

`app/engine/reconcile.py` (`reconcile(transactions, declared_holdings, as_of)`) exists
and is fully specified in `docs/ENGINE_SPEC.md` §7, but `contracts/openapi.yaml`'s
`POST /investors/{investor_id}/reconcile` has no router anywhere in
`app/routers/`. `docs/BLUEPRINT_REVIEW.md` calls this out specifically: *"build it in
week one, not as a tool in month six."* It's the corporate-action detector and the
parser-drift alarm — currently unreachable over HTTP.

### A3. FY XIRR is implemented in the engine but not wired into the API

`app/engine/xirr.py` has `compute_fy_xirr`, `compute_period_xirr`,
`financial_year_start`, and `period_warning` — all present, all covered by the engine
case fixtures. But `app/routers/analytical.py`'s `performance()` only calls
`compute_xirr` and `compute_xirr_holdings`; `PerformanceResponse` (`app/schemas/
analytical.py`) has no `fy_xirr` or `period_xirr` field.

`docs/BUILD_PLAN.md` Session 10 calls this mandatory: *"Headline 'XIRR this FY' beside
`xirr_all` and `xirr_holdings`, never replacing the pair."* It is not a one-line change:
`compute_fy_xirr`'s docstring requires `opening_value` to be the **market value on 1
April**, sourced from a stored snapshot or `compute_snapshot` run against that date's
prices — and there is no persisted snapshot store yet (that's Phase 2, see D1). For
Phase 1, the router needs to call `compute_snapshot` on the fly against 1-April prices
(`app/db/prices.py` currently only exposes `latest_prices`, not a price lookup pinned to
an arbitrary historical date — check whether it already supports that before assuming a
new function is needed) and **omit the field when no 1-April price exists**, per the
engine docstring's own instruction, rather than substituting today's value.

The same router gap applies to `compute_period_xirr` — `openapi.yaml`'s `period_start` /
`period_opening_value` query parameters for the adviser-onboarding case are specified in
the contract but not read anywhere in `analytical.py`.

### A4. `advised_only` filter missing

`contracts/openapi.yaml`'s `GET /investors/{investor_id}/holdings` specifies an
`advised_only` boolean query parameter (restrict to accounts flagged `is_advised`, per
`docs/DATA_MODEL.md`'s `account.is_advised` column — "so a SEBI-registered adviser can
report on the mandated account only"). Neither `holdings.py` nor `transactions.py`
reads or filters on it anywhere.

### A5. No investor/account onboarding API — and it's not in the contract either

Every endpoint takes an `investor_id`, but nothing in `contracts/openapi.yaml` or
`app/routers/` creates an investor or an account. Today the only way data gets into
those tables is `app/db/load_golden.py`, which seeds one specific fixture investor. This
is a real product gap (an adviser cannot onboard a second client without hand-writing
SQL) and it's missing from the HTTP contract itself, not just the implementation —
worth deciding the shape (`POST /investors`, `POST /investors/{id}/accounts`) and adding
it to `openapi.yaml` before building it, so the contract stays the source of truth.

### A6. Zero test coverage for the entire new HTTP layer

No test file exists for `app/auth/service.py`, `app/auth/repository.py`,
`app/auth/dependencies.py`, any of the six files in `app/routers/`,
`app/ingest/webhook.py`, `app/config.py`, `app/database.py`, or
`app/storage/factory.py`. Every other package in this repo has direct test coverage; this
is the newest and least-proven code in the system — JWT issuance/revocation, webhook
address routing, and the staging-to-HTTP wiring have no fixtures pinning their behaviour.
`CLAUDE.md`: *"Tests are the specification."* Concretely needed:

- `tests/test_auth.py` — registration, login (including the timing-oracle mitigation and
  the collapsed "invalid credentials" error for both wrong-email and wrong-password),
  token verification, session revocation.
- Router-level tests using FastAPI's `TestClient` against `app/main.py` — at minimum, one
  happy-path and one error-path test per router, confirming the exception handlers in
  `main.py` actually produce the status codes they claim to (this is exactly the kind of
  wiring that looks correct on read and is wrong at runtime).
- `tests/test_webhook.py` — `parse_to_address` edge cases (malformed addresses),
  `resolve_investor`/`resolve_account` not-found paths, the PDF password case-mapping
  table.
- `tests/test_storage_factory.py` — unknown backend name raises rather than silently
  defaulting.

### A7. Grievance intake has no HTTP surface

`app/db/grievance.py` implements the full DPDP 90-day-clock workflow
(`docs/COMPLIANCE.md`: *"grievance intake with a 90-day clock... maintained by a trigger
... refused by CHECK constraints, not by convention"*), but no router exposes it. Intake
needs to accept complaints "from people not yet matched to an investor record" per the
compliance doc, so this specifically cannot wait for the auth layer the way the other
routers reasonably do — a grievance route may need to be intentionally unauthenticated
or use a separate, lighter-weight verification path. Worth a explicit design decision,
not just a router that mirrors `privacy.py`.

### A8. Price-pipe alert delivery is still log-only

Carried over unchanged from before the move, and still true: `docs/INGESTION.md` says
*"Alert delivery is NOT wired. `prices/alerts.py` defines the notifier and the pipe
calls it on every failure path, but the default only logs."* `docs/BUILD_PLAN.md`'s MVP
definition of done requires prices to *"refresh daily and alert on failure"* — the
refresh exists (`POST /ops/prices/refresh`, A3's sibling endpoint, already wired), the
alert does not reach a human yet.

### A9. Portfolio-level absolute return and CAGR — decided (2026-08-16), not yet implemented

`app/routers/analytical.py` still leaves `absolute_return` and `cagr` as `None` as of
this writing. The spec gap this section used to describe is now closed:

- `net_invested` (for `absolute_return`) is defined in `docs/ENGINE_SPEC.md` §5 as
  **net lifetime cash contributed** — total `BUY`/`IPO_ALLOT` outflows minus total
  `SELL`/`BUYBACK` inflows across the full transaction history, the same cash-flow
  universe `xirr_all` solves over. Undefined (return `None`) when `net_invested <= 0`.
- Portfolio-level `cagr` is **permanently out of scope**, not deferred. §5 already
  scoped CAGR to per-holding only for a stated mathematical reason (lump-sum
  assumption); this only makes explicit that there is no future revisit — see §5's
  closing paragraph for why no valid portfolio-level `start_value`/`days` exists that
  XIRR doesn't already cover.

`CLAUDE.md`'s MVP scope table has been corrected to qualify CAGR as per-holding only,
resolving the conflict with `FEATURE_BACKLOG.md` recorded in Section B below.
**Remaining work:** wire `net_invested` and `absolute_return` into the engine and API
per the new §5 definition — this is an engine change and needs a plan per `CLAUDE.md`'s
own rule, not a direct edit.

### A10. The one gate that actually matters — deferred, tracked, not forgotten

`fixtures/golden_portfolio.json` is the client's own real portfolio; he has it, the repo
correctly doesn't. **Action: ask him for it directly** — that's the actual fix, not a
data-recovery or synthesis task (see the Decision section above for why a fabricated
replacement is worse than no file at all). Until it lands, `fixtures/engine_cases.json`'s
10 hand-computed cases are the interim correctness bar. Nothing in this document can be
honestly called "MVP-complete" in the `CLAUDE.md` sense until the real file is in place
and `pytest tests/test_golden_portfolio.py -v` passes with the exact headline numbers
from its table — but by decision, the rest of Section A onward no longer waits on that
happening first.

---

## Section B — Conflicts between the project's own vision documents

Not code gaps — places where two source-of-truth documents disagree, surfaced by trying
to audit against both at once. Each needs a decision, then a doc correction, so the next
session (human or agent) doesn't re-litigate it.

| Feature | `CLAUDE.md` says | `docs/FEATURE_BACKLOG.md` says | Current code |
|---|---|---|---|
| Benchmark comparison | Phase 1, "in" | Phase 2 — needs a cash-flow-replicated index feed (`ENGINE_SPEC` §6) | Not implemented; `analytical.py`'s docstring explains why (no index-level data source wired) |
| Dividends | Phase 1, "in" | Phase 2 — *"No data source provides these — manual or Console report"* | `DIVIDEND` txn_type + XIRR treatment fully implemented at the engine level; only reachable once A1 (manual entry) ships |
| Historical portfolio value | Phase 1, "in" | Phase 2 — *"needs snapshots first"* | `compute_snapshot` exists but nothing persists a daily snapshot (see D1) |
| ~~Absolute return / CAGR~~ | ~~Phase 1, "in", unqualified~~ **Resolved 2026-08-16** — `CAGR` now qualified "per-holding only" | Not listed as a phase item; `ENGINE_SPEC` §5 scopes CAGR to per-holding only | Left `None` at the API layer; `absolute_return`'s `net_invested` now has a precise definition (A9), implementation still pending |

Recommendation: `FEATURE_BACKLOG.md`'s phasing is the more specific and better-reasoned
of the remaining three cases (each has a concrete technical reason for waiting, not just
a preference). Suggest updating `CLAUDE.md`'s MVP table to match `FEATURE_BACKLOG.md`
rather than the reverse for those — but that's a call for whoever owns the
product spec, not one to make silently while auditing.

---

## Section C — Frontend (`trackr-frontend/`): effectively 100% remaining

Only `.gitkeep` files exist. Full scope, per `docs/structure_revamp_plan.md`'s target
tree and `docs/BUILD_PLAN.md` Session 10:

- [ ] `app/layout.tsx` — shell, Mei Capital palette (Ink Navy `#1B2A41`, Cream `#F5F0E6`,
      Brass `#B08D3E`, Newsreader headings)
- [ ] Auth: login/register pages, token storage, an authenticated fetch wrapper for
      every call to a router that requires `get_current_user` (A6's routers: `ingest`
      promote/discard, `ops/prices/refresh`, both `privacy` endpoints)
- [ ] `app/page.tsx` — dashboard summary (`GET /investors/{id}/summary`)
- [ ] `app/holdings/page.tsx` — holdings + FIFO lots table. Must render `cost_estimated`
      per row, not just in a tooltip — `docs/BUILD_PLAN.md` Session 10: *"Two golden
      positions (KDL-SM, IGIL) reach their invested figure on broker-stated cost rather
      than replayed cost. An estimate shown unlabelled reads as a fact."*
- [ ] `app/performance/page.tsx` — both XIRR variants side by side, always (never one
      alone — this is a hard rule, not a layout preference), plus FY XIRR once A3 ships
- [ ] `app/import/page.tsx` — multi-file CSV/PDF upload, staging review screen (surfaces
      `GET /ingest/stage/{batch_id}`'s `needs_review` / `will_skip_as_duplicate` fields
      from `app/schemas/ingest.py`), promote/discard actions
- [ ] A typed API client. Recommend generating from `contracts/openapi.yaml`
      (`openapi-typescript` or equivalent) rather than hand-written `fetch` calls — per
      `docs/ARCHITECTURE.md`'s "Swapping the stack" guidance, this is what keeps the two
      packages from drifting out of sync with the contract that's supposed to define the
      boundary between them. Note the contract itself needs A5's investor/account
      endpoints added before the frontend can build an onboarding flow against it.
- [ ] Unpriced-holdings banner — `holdings.py`'s `_unpriced` partition (priced holdings
      valued normally, unpriced ones named and excluded from totals rather than the whole
      dashboard going blank per `MissingPriceError`) needs a corresponding UI treatment,
      not just API support.

---

## Section D — Phase 2: Analytics depth (still equities only)

Per `docs/FEATURE_BACKLOG.md` Phase 2 and `docs/BUILD_PLAN.md`'s "what to build next."
`docs/BUILD_PLAN.md` says *"resist all seven until the MVP has run for a month on real
data"* — by the deferred-golden-gate decision above, that real-data check now happens
later rather than gating each phase individually. Section A should still close first;
A10 itself does not have to pass first, but stays open and gets run for real (see A10)
before this phase's output is presented to the client as verified, not just built.

- **D1. Daily snapshot persistence.** `compute_snapshot` exists and is called live inside
  `performance()` today, but nothing writes a daily row. This unlocks: the historical
  portfolio value chart, TWRR (`ENGINE_SPEC` §5 notes TWRR needs snapshots from day one),
  and removes A3's on-the-fly-1-April-price workaround.
- **D2. Benchmark XIRR** (NIFTY 50 TRI / SENSEX TRI, cash-flow-replicated per
  `ENGINE_SPEC` §6). `BenchmarkOut` already exists in `schemas/analytical.py` as an
  unused optional field — the schema anticipated this before the engine did.
- **D3. Period-wise XIRR (1Y/3Y/5Y/FY)** — trivial once D1 lands; `compute_period_xirr`
  already supports an arbitrary window.
- **D4. TWRR** — measures the adviser, distinct from XIRR (measures the client).
- **D5. Dividends as a first-class feature** — beyond A1's raw manual-entry support:
  a per-holding dividend summary / "expected dividends" view. `FEATURE_BACKLOG.md` is
  explicit that there is still no automated data source for these.
- **D6. Sector / market-cap breakdown** — needs `security.sector` populated; currently
  `null` for every security (`docs/DATA_MODEL.md`: `sector text null`).
- **D7. Contribution analysis** — "which holdings drove the return." First real
  Intelligence-layer feature per `docs/PRODUCT_VISION.md`.
- **D8. CAS adapter** — multi-broker reconciliation input, feeds A2's reconcile endpoint
  with real declared-holdings data instead of manual entry.

---

## Section E — Phase 3: Tax engine (highest risk — see `docs/TAX_ENGINE.md` in full)

Not started. Explicitly gated: *"built only after the MVP has run on real data for a
full quarter"* and requires CA sign-off before informing any filing. Concretely absent
from the schema and code today:

- `security.fmv_31jan2018` column (grandfathering formula needs it) — not in
  `docs/DATA_MODEL.md`'s current table, so this is a schema addition, not just code.
- CII table (indexation) — no static data anywhere in the repo.
- Section 112A / Schedule 112A report generation.
- Bonus-stripping and demerger cost-ratio rules — `FIFO` lots already push bonus shares
  at cost 0 (`app/engine/lots.py`, per `ENGINE_SPEC` §3), which is the prerequisite this
  phase builds on, but nothing consumes it for tax purposes yet.
- Tax-software export formats (ClearTax, Winman, CompuTax, Spectrum, Genius).

---

## Section F — Phase 4: Multi-asset

`schema/asset_classes.json` is fully seeded (all 30 codes, correctly a lookup table, not
buildable scope per its own `_comment` field). Only `EQ` has any engine support. Per
`docs/FEATURE_BACKLOG.md`, mutual funds are next — *"the registrar CAS carries cost
basis, so it is the cheapest second class by a wide margin."* Each new class needs (per
`docs/DATA_MODEL.md` "Adding an asset class later"): an enum value (already present),
class-specific `txn_type`s, a holding-period rule (already in
`asset_classes.json.long_term_days`), a data source, and golden fixtures. **No new
tables** — if a Phase 4 change looks like it needs one, that's a signal the design is
wrong, not that the rule doesn't apply this time.

---

## Section G — Phase 5: Practice tooling (the B2B layer)

Not started. `investor.family_group_id` already exists in the schema
(`docs/DATA_MODEL.md`), so the seam is there. Everything else — client sharing
(read-only by default, per `docs/COMPLIANCE.md`'s SEBI posture), cross-client reports,
model-portfolio-vs-actual drift (`docs/FEATURE_BACKLOG.md`: *"worth more than any three
tax exports"*), concentration alerts, white-label branding — is unbuilt.

---

## Section H — Compliance & go-live gates: current status vs `docs/COMPLIANCE.md`

Re-checked against the actual migrations and code, not assumed from the checklist's own
prior "as of Session 5b" claim:

| Gate | Status |
|---|---|
| PAN/demat encrypted at rest, separate table/access path | ✅ `investor_secret` (`002_compliance.sql`), `app/db/crypto.py` |
| Key-rotation schema support (`key_version`, `pepper_version`, `pan_hash_next`, the `pan_hash_requires_ciphertext` constraint) | ✅ Present — landed inside `003_documents.sql` rather than a separately-named migration, but the columns and constraint from `docs/KEY_ROTATION.md` §4 are there. Verified by reading the migration, not assumed. |
| Key-rotation **code** (`MultiFernet`, comma-separated key list) | ❌ Not yet — `docs/KEY_ROTATION.md` itself says this is the one code change rotation needs and it hasn't landed. Not urgent per that doc's own framing ("rotate because something happened, not because a calendar said to") but should not be assumed to exist. |
| No credential storage anywhere | ✅ `make lint`'s grep passes; the one named exception (`gmail_oauth.py`) is unchanged and still correctly scoped |
| Private object storage, signed-URL only | ✅ `app/storage/` (local + S3/R2), `app/storage/factory.py` new |
| `audit_log` retained ≥ 5 years, legal hold | ✅ `app/db/audit.py`, `app/db/retention.py` |
| `client_consent` populated, export + erasure tested | ✅ logic present (`app/db/consent.py`, `app/db/privacy.py`); now also reachable over HTTP (`app/routers/privacy.py`) — this closes a gap the compliance doc didn't know it had, since the export/erase routes are new in this move |
| Grievance intake, 90-day clock | ⚠️ DB layer done (`app/db/grievance.py`); **no HTTP route** (A7) |
| DPAs with host/email/price vendors | ❌ Outside the codebase — contracting task |
| Breach playbook, 72-hour Board filing readiness | ❌ Outside the codebase — operational task |
| Lawyer + CA review | ❌ Outside the codebase |
| Exports labelled as records, not advice; no auto-generated recommendations; read-only client access by default | Not yet applicable — no client-facing export or recommendation surface exists yet to check this against |

---

## Section I — Production-readiness gaps outside the phase system

Not called for by any of the docs above as a numbered phase, but real gaps against the
"production-grade" framing this restructuring is being done under:

- **No CI.** Nothing runs `pytest` or `ruff` automatically on a push or PR. `make test`
  and `make lint` exist and work; nothing invokes them without a human remembering to.
- **No Dockerfile / `docker-compose.yml`.** `docs/STACK_DECISION.md` doesn't mandate
  containerisation, but there's currently no reproducible way to stand up
  Postgres + the API together for local development or deployment.
- **Nothing committed.** The entire migration audited in this document is uncommitted
  working-tree state (see the callout at the top). A production-readiness pass on an
  uncommitted 80-file change is auditing something that could still be lost.

---

## Priority order, if asked "what's next"

1. **Ask the client for `fixtures/golden_portfolio.json`** — a parallel, low-effort ask,
   not a blocker to the items below. Runs independently of everything else.
2. A1 (manual entry) and A2 (reconcile) — both are thin routers over engine/db code that
   already exists; highest value for lowest risk. *(Done — see the session-prompts
   artifact.)*
3. A6 (tests for the new HTTP layer) — before, not after, more routers get built on top
   of untested foundations. *(Done.)*
4. A3 (FY XIRR) and A4 (`advised_only`) — close the contract-vs-implementation gaps in
   what's already shipped. *(Done.)*
5. A5 (investor/account onboarding contract + endpoint) — needed before the frontend
   (Section C) can build anything beyond the seeded golden-fixture investor. *(Contract
   proposed; router not yet built — awaiting decisions on PAN handling, the missing GET
   endpoints, and schema layout.)*
6. Resolve Section B's four conflicts with whoever owns the product spec, then update
   `CLAUDE.md` or `FEATURE_BACKLOG.md` accordingly. Still open.
7. Commit the Phase 4 migration (coordinate with the other active sessions first). Still
   deliberately deferred — not committing until tested.
8. Frontend (Section C) — deliberately on hold; UI direction not decided yet.
9. Once the client's real file lands: run `pytest tests/test_golden_portfolio.py -v` and
   report the exact result before calling anything above "verified" rather than just
   "built."
