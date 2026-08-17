# Phase 1 closeout — one prompt per session

Generated 2026-08-17 from a fresh audit of the codebase against `CLAUDE.md`,
`docs/ENGINE_SPEC.md`, `docs/FEATURE_BACKLOG.md`'s Phase 1 table, and
`docs/trackr_plus_phase1_overview.md` (updated the same day — read it first in any
session, it has the file-by-file map).

Each block below is meant to be pasted as the **first message of a brand-new chat
session**. They're self-contained: background, files, and acceptance criteria are all
inline, because the new session has none of this conversation's context. Do them in
separate sessions and separate commits, per `CLAUDE.md`'s "one feature per session, one
commit per feature" rule — don't bundle two of these into one session even though it's
tempting.

Suggested order: 1 and 2 unblock nothing else and can happen anytime. 3 and 4 touch
compliance surfaces the product can't legally claim otherwise. 5 finishes an onboarding
flow that's half-done. 6 is pure test-writing and safe to run last or in parallel.

---

## 1. Per-holding CAGR

```
Read CLAUDE.md and docs/ENGINE_SPEC.md §5 ("Other return measures") first.

docs/trackr_plus_phase1_overview.md's §7 (the honesty section, near the top) documents
this gap precisely — read that bullet before starting.

Context: ENGINE_SPEC.md §5 requires CAGR to be shown per-holding, and explicitly says
it must NEVER be computed at the portfolio level (a portfolio has staggered dated
contributions, which breaks CAGR's single-lump-sum assumption — that part is already
correctly implemented as a permanent None on the portfolio-level PerformanceOut schema
in trackr-backend/app/schemas/analytical.py, don't touch it). What's missing is the
per-holding case the spec actually asks for: there is no cagr field anywhere on the
holdings schema, no computation in trackr-backend/app/engine/holdings.py, and nothing
on the Holdings page (trackr-frontend/app/holdings/page.tsx).

Task: implement per-holding CAGR end to end.
- Formula per ENGINE_SPEC.md §5: cagr = (end_value / start_value)^(365.25/days) - 1.
  For a holding, start_value is the cost basis at the earliest open lot's purchase
  date (or however the spec's "single lump sum" framing resolves for a position built
  from multiple buys — read the spec's worked examples and fixtures/engine_cases.json
  for anything already pinning this; if the spec is genuinely silent on how to handle
  a holding built from multiple buy dates, stop and ask rather than inventing a rule —
  CLAUDE.md is explicit: "Never invent financial logic... if a case is not covered
  there, ask, do not guess.")
  end_value is current market value; days is calendar days held.
- Add the field to whatever engine type represents a holding
  (trackr-backend/app/engine/types.py) and to the holdings response schema.
  Follow the same None-when-undefined convention used elsewhere (e.g. a holding with
  no current price can't have a CAGR either — don't default to 0).
  Check schema/*.schema.json for whether the holdings JSON Schema needs updating too
  (see tests/test_types_match_schema.py, which pins that the two never drift).
- Wire it through trackr-backend/app/routers/holdings.py so GET
  /investors/{id}/holdings returns it per row.
- Display it on trackr-frontend/app/holdings/page.tsx (and check
  trackr-frontend/app/components/HoldingsTable.tsx) next to the existing per-holding
  figures — match the existing null-handling pattern used for unpriced holdings
  (UnpricedBanner.tsx) rather than inventing a new one.

Write the failing test first, from ENGINE_SPEC.md's worked examples if any exist for
this, or construct one by hand and verify it against a calculator — this is exactly
the kind of number that silently looks plausible when wrong (CLAUDE.md's "money is
Decimal" rule applies: compute in Decimal, never float).

Run `make test` before claiming done. This does not touch the schema/migrations layer
(no new DB columns needed — it's derived, like everything else), so full Plan Mode
isn't required, but do read the relevant ENGINE_SPEC section fully before writing code.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 2. Period XIRR from adviser onboarding date

```
Read CLAUDE.md and docs/ENGINE_SPEC.md's "Period XIRR (advisor onboarding)" section
first (search for that heading — it's near the Dual XIRR section).

docs/trackr_plus_phase1_overview.md's §7 documents this gap precisely — read that
bullet before starting.

Context: FEATURE_BACKLOG.md's Phase 1 table lists "Period XIRR | Adviser onboarding
date" as its own line item, separate from the FY-XIRR feature that already ships. The
engine primitive already exists and is already tested: compute_period_xirr in
trackr-backend/app/engine/xirr.py takes an arbitrary (start_date, opening_value) pair,
and fixtures/engine_cases.json's "period_xirr_mid_period_deposit_not_inflated" case
already pins its correctness — in particular the failure mode ENGINE_SPEC.md calls
out explicitly: an implementation that drops intermediate transactions between
start_date and as_of will silently inflate the return whenever a deposit happens
mid-period. Do not reintroduce that bug.

The only thing calling compute_period_xirr today is _fy_xirr in
trackr-backend/app/routers/analytical.py, which always uses start_date = 1 April of
the current financial year. Nothing calls it with a real onboarding date, because no
such date is stored anywhere.

Task — this DOES touch the schema, so start in Plan Mode per CLAUDE.md ("Plan mode
for anything touching the schema or the engine"):
1. Decide and get sign-off (via the plan) on where an onboarding date belongs — most
   likely a new nullable onboarding_date column on `account` (an advisory
   relationship starts per-account, not per-investor-globally — but check
   docs/DATA_MODEL.md's description of `account` vs `investor` before assuming this;
   if investor-level fits the product's actual meaning of "adviser onboarding"
   better, argue for that instead). This needs a new numbered migration file under
   trackr-backend/app/db/migrations/ (follow the existing naming pattern, e.g.
   009_something.sql) — read a couple of the existing migrations first for the
   house style (comments explaining WHY, CHECK constraints, etc.).
2. Expose it: allow setting onboarding_date on account creation
   (trackr-backend/app/routers/investors.py, AccountIn/AccountOut schemas) and add a
   period-XIRR field to the performance response
   (trackr-backend/app/routers/analytical.py, schemas/analytical.py) that resolves
   opening_value the same honest way _fy_xirr already does today (read _fy_xirr's own
   docstring closely — it explains exactly why opening_value must come from a live
   snapshot/price lookup, never a stand-in, and what to do when no usable price
   exists: omit the metric, don't estimate it). If onboarding_date is null for an
   account, the metric should be omitted the same way fy_xirr is omitted when it
   can't be computed — never guess a start date.
3. Show it on trackr-frontend/app/performance/page.tsx next to the existing dual
   XIRR / FY XIRR display (components/DualXirrCard.tsx is probably the right place to
   extend, or a sibling card — look at how fy_xirr is already threaded through before
   deciding).

Write the failing test first from the ENGINE_SPEC.md worked example and the existing
fixture case. Run `make test` before claiming done — including confirming the golden
portfolio numbers in CLAUDE.md are unaffected (this is a new, additive metric, it must
not change any existing computed value).

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 3. DPDP privacy screen (export + erasure UI)

```
Read CLAUDE.md and docs/COMPLIANCE.md first.

Context: the backend fully implements DPDP data export and account erasure today —
trackr-backend/app/routers/privacy.py (mounted in main.py as app.include_router
(privacy.router)), backed by trackr-backend/app/db/privacy.py. GET /privacy/export
walks every table referencing an investor and returns one JSON payload (PAN/demat
decryption is off by default, and is itself a separately audited action when turned
on). POST /privacy/erase checks for an open legal_hold first and refuses if one
exists, otherwise deletes stored documents, then removes the investor row under a
special session flag that is the only thing the append-only trigger on `transaction`
will ever honor as a delete.

None of this is reachable from the web app. There is no /privacy page, and Settings
(trackr-frontend/app/settings/page.tsx) has zero mention of export, erasure, or
consent. Today the only way to exercise a client's DPDP rights is a raw curl call to
an authenticated endpoint — that's a real product-and-legal gap, not just a UI nicety
(docs/COMPLIANCE.md explains why this matters).

Task: build the frontend for this. Read trackr-backend/app/routers/privacy.py and
db/privacy.py fully first to know the real request/response shapes (check
contracts/openapi.yaml for the documented contract) before writing any frontend code.
- A new page, most likely trackr-frontend/app/privacy/page.tsx (or a section within
  Settings — look at how Settings is laid out today and use your judgement on which
  reads better; either is defensible, just be consistent with the existing
  glass-card section style already used elsewhere on that page).
- An "Export my data" action calling GET /privacy/export, that lets the user actually
  see or download the JSON it returns. Do NOT expose the include_identifiers=true
  flag casually — read how it's gated on the backend (it's logged as a separate
  audited access event every time it's used) and make sure the frontend doesn't turn
  that into a one-click default; require an explicit, clearly-labelled confirmation
  step for it, distinct from the plain export action.
- A "Delete my account" / erasure action calling POST /privacy/erase, with a
  destructive-action confirmation pattern (type-to-confirm or a clear two-step
  dialog — this permanently deletes real data). Handle and clearly surface the
  legal-hold-refusal case (the backend will refuse with a specific error when an open
  legal_hold exists) — don't let that error surface as a generic failure toast; the
  user needs to understand why they can't self-serve delete right now.
- Follow the existing frontend patterns in this repo for API calls (lib/api-client),
  auth (lib/auth-context), and error display (components/PageState.tsx or however
  other pages like Reconcile/Import surface backend errors) rather than inventing new
  ones.

This is a frontend-only task against an already-complete backend contract — no schema
or engine changes, so Plan Mode isn't required, but do read contracts/openapi.yaml's
privacy section and the two backend files closely before writing UI code, since a
mistake here is a real DPDP-compliance mistake, not just a cosmetic bug.

Test manually against a real running backend + Postgres (this can't be meaningfully
verified with schema-only tests) — start the app per docs/BUILD_PLAN.md, create a
throwaway investor, export their data, confirm the JSON looks right, then erase them
and confirm the erasure actually refuses when you set a legal_hold row first and
succeeds when you don't.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 4. Consent capture — endpoint + enforcement + UI

```
Read CLAUDE.md and docs/COMPLIANCE.md first.

docs/trackr_plus_phase1_overview.md's §7 documents this gap precisely — read that
bullet ("require_consent() is defined but never called, and there is no consent
router at all") before starting.

Context: FEATURE_BACKLOG.md's Phase 1 table lists "Client consent records | Before any
client data lands" as in-scope. trackr-backend/app/db/consent.py already implements
record_consent, withdraw_consent, has_live_consent, and a require_consent() gate meant
to block processing without a live grant. But today this is entirely dead code from
the outside: there is no router anywhere under trackr-backend/app/routers/ that
mentions consent at all — no way to grant one over HTTP, and require_consent() is
never called by any router or ingestion path. The client_consent table can exist in
principle but nothing in the running system ever populates or checks it.

This is a real gap between what the product claims (consent-first, per
docs/COMPLIANCE.md) and what the code does (no enforcement whatsoever) — treat it with
the seriousness that implies.

Task — start in Plan Mode (this touches how ingestion paths behave, a load-bearing
decision):
1. Read db/consent.py fully, and docs/COMPLIANCE.md's description of what DPDP
   consent-first actually requires (notice_version, purpose, lawful_basis — these are
   already fields on client_consent per the migration; read 002_compliance.sql).
2. Add a router (trackr-backend/app/routers/consent.py, or fold into
   routers/investors.py if that reads better — use your judgement, but check how the
   other domain routers are split first) exposing at minimum: grant consent (POST,
   takes notice_version/purpose/lawful_basis/evidence_ref) and withdraw consent (POST
   or DELETE). Mount it in main.py alongside the other routers.
3. Decide, in the plan, exactly which paths require_consent() should gate — CLAUDE.md
   and FEATURE_BACKLOG.md both frame this as "before any client data lands," which
   most plausibly means the ingestion entry points: POST /ingest/csv, POST
   /ingest/email, and manual transaction entry (POST /investors/{id}/transactions).
   Read require_consent()'s existing signature/docstring in db/consent.py to see what
   it already expects to be called with, and wire it into each of those three router
   handlers so a missing/withdrawn consent produces a clear, specific HTTP error
   rather than silently proceeding. Do not guess at scope beyond what
   COMPLIANCE.md/FEATURE_BACKLOG.md actually state — if it's ambiguous whether e.g.
   the reconcile endpoint needs the same gate, ask rather than assume.
4. Frontend: a minimal consent-grant step somewhere in the onboarding flow (Settings
   page, near the new account-onboarding section built recently — see
   trackr-frontend/app/components/AccountOnboarding.tsx for the current pattern of
   calling a backend endpoint and showing the result) — a checkbox/confirmation
   naming what's being consented to, calling the new grant endpoint. This does not
   need to be elaborate; it needs to exist and actually call the real endpoint.

Write tests first: a test proving require_consent() correctly blocks an ingestion
call with no live consent, and correctly allows one after granting it. Check
tests/test_db_compliance.py for existing consent-adjacent test patterns to follow.
Run `make test` before claiming done, and confirm this doesn't break any existing
ingestion test that doesn't currently grant consent first (you may need to add a
consent-granting step to shared test fixtures — check tests/conftest_db.py).

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 5. Investor onboarding — wire the "Add investor" button

```
Read CLAUDE.md first, and read docs/trackr_plus_phase1_overview.md's Table 1 row 12
and Table 3 Settings row (updated 2026-08-17) — they describe exactly what's already
done and what's left.

Context: broker-account onboarding on the Settings page was recently built and works
end to end (trackr-frontend/app/components/AccountOnboarding.tsx calls the real POST
/investors/{id}/accounts and displays each account's forwarding address via
EmailForwardingSetup.tsx) — use that component as your template for style and error
handling. What's still stale is investor creation itself: Settings
(trackr-frontend/app/settings/page.tsx)'s "Onboarding" section shows a permanently
disabled "Add investor — coming soon" button with the text "Adding a new investor
from this UI isn't wired up yet." The backend endpoint this should call,
POST /investors, is already fully implemented in
trackr-backend/app/routers/investors.py and has been for a while — this is purely a
frontend wiring gap.

Task:
- Replace the disabled placeholder in the "Onboarding" section of
  trackr-frontend/app/settings/page.tsx with a real form (display_name at minimum —
  check InvestorIn's schema in trackr-backend/app/schemas/investors.py for the full
  set of fields it accepts) that calls POST /investors.
- On success, the natural next step is setting the newly-returned investor id as the
  active investorId (the same setInvestorId flow the existing "paste an investor ID"
  form on that page already uses) so the user doesn't have to copy-paste their own
  new UUID by hand.
- Follow AccountOnboarding.tsx's existing conventions closely: same error-display
  pattern (ApiError handling), same submitting/disabled-button state, same general
  visual structure as the rest of that page.

This is a small, frontend-only, already-unblocked task — no schema or engine changes,
Plan Mode not required. Test manually: start the app (see docs/BUILD_PLAN.md /
start.sh), open Settings, create a new investor through the form, confirm the
dashboard for that investor loads (empty, since it has no transactions yet) rather
than erroring.

Do not run `npm run build` while another `next dev` server might be running against
this same repo — it corrupts the shared .next build for anyone else using it. Use
`tsc --noEmit` for a type-check instead, and only run the dev server for actual
manual testing.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## 6. Extend real HTTP-level tests to the remaining routers

```
Read CLAUDE.md first, and read docs/trackr_plus_phase1_overview.md's §7 "Resolved
since the first pass today" bullet about router-level HTTP tests — it explains
exactly what changed and what didn't.

Context: this repo's test suite has two very different kinds of "router test," and
the difference matters. Every test_*_router.py file (test_investors_router.py,
test_transactions_router.py, etc.) only checks that Pydantic request/response shapes
validate correctly — it never makes an HTTP request. Every test_db_*_router.py file
(test_db_grievance_router.py, and similar ones for other routers where they exist)
calls the route handler function directly with a hand-built connection and a
hand-built current_user, which — per that file's own docstring — "bypasses FastAPI's
own dependency injection entirely," so it proves nothing about what happens when a
request arrives WITHOUT a valid token, or with a malformed body, or hits actual
FastAPI middleware/exception handlers.

tests/test_db_webhook.py just became the first (and, as of this audit, only) suite in
the repo to close that gap for real: it uses fastapi.testclient.TestClient against the
actual app.main application, with get_conn and get_settings overridden via FastAPI's
own dependency_overrides mechanism rather than being bypassed. Read that file's
top-of-file docstring and its app_module/make_client fixtures closely — they are the
pattern to replicate, including WHY app.main is imported lazily inside a fixture
(module-level settings = get_settings() needs real secrets, set via monkeypatch and
reverted after each test, so nothing leaks into the rest of the suite) and why
attachment content in that file is plain text rather than a real PDF (parse() only
invokes pdfplumber when bytes start with %PDF-).

Task: extend this same TestClient-based pattern to the other routers that currently
lack it: investors, transactions, holdings, auth, reconcile, grievance, analytical,
privacy (check trackr-backend/app/routers/ for the full current list; ingest.py's
non-webhook endpoints — /ingest/csv, /stage/{id}, /promote, /discard — are also
covered by this same gap and worth including). For each router:
- New test file test_db_<router>_http.py (or fold into the existing test_db_<router>
  file if one exists and this doesn't collide with its current direct-call tests —
  use your judgement, but don't delete the existing direct-call tests, they still
  cover something real: business logic correctness. The new tests are additive,
  proving the HTTP/auth/routing layer specifically).
- At minimum for each router: one test proving a request with a missing/invalid
  bearer token is correctly rejected (this is exactly what the direct-call tests
  structurally cannot prove), and one or two tests proving the happy path actually
  works end to end through real FastAPI routing (not just that the handler function
  returns the right dict).
- This is inherently a database test (pytestmark = pytest.mark.db, like
  test_db_webhook.py) since it needs a real connection behind get_conn — it will skip
  in this environment without local Postgres binaries, same as every other db-marked
  test today. That's expected and fine; the point is the test exists and is correct,
  not that you can watch it pass here.

Given how mechanical and repetitive this is across 8-9 routers, do it inside ONE
session but as one commit per router (small, reviewable, bisectable commits) rather
than one giant commit — this matches the spirit of "one feature per session, one
commit per feature" better than either extreme.

Run `make test` after each router's addition and confirm nothing regresses (skip
counts should go up, pass/fail should stay clean) before moving to the next router.

> [!IMPORTANT]
> **Production Standards Mandatory Rules**:
> 1. **No Superficial Symptom Patches or Mock/Dummy Fallbacks**: Never introduce fake return values or hardcoded dummy objects to swallow errors.
> 2. **Explicit & Graceful Error Handling**: Eliminate silent `try...except: pass` or empty catch blocks. Log rich structured context and return explicit HTTP status codes (`400`, `401`, `403`, `404`, `429`, `500`).
> 3. **12-Factor Environment Configuration**: All endpoints, OAuth redirect URIs, service hostnames, and storage paths MUST be loaded dynamically from `.env` environment variables. Works strictly under both `DEBUG=True` and `DEBUG=False`.

```

---

## Not included on purpose

A few things that came up in the audit but deliberately aren't prompts above:

- **Historical value chart / daily snapshots, and benchmark comparison.**
  `CLAUDE.md`'s summary paragraph lists both as Phase 1, but `FEATURE_BACKLOG.md`'s
  actual Phase 1 table — which `CLAUDE.md` itself designates as the tie-breaker —
  places both under Phase 2. The code already sides with `FEATURE_BACKLOG.md`
  (`HistoricalChartPlaceholder.tsx` and `engine/returns.py` both say so explicitly in
  their own comments). Building either now would be building ahead of scope against
  CLAUDE.md's own stated rule. The one real action item here is a one-line edit to
  CLAUDE.md's summary paragraph to stop contradicting its own backlog — small enough
  to just do directly rather than spinning up a session for it, if you agree with the
  recommendation in the updated overview doc's §7.
- **Contract-note PDF direct upload on the Import page.** Not a gap — `docs/INGESTION.md`
  "Adapter 3 — Gmail forwarding" specifies forwarding as the only client-facing
  delivery path for contract notes by design. The Import page correctly only offers
  CSV.
- **Sector/market-cap allocation breakdown.** `security.sector` is null for every row
  today by design (Phase 1 is equities-only with no sector master data yet) —
  `AllocationDonut.tsx`'s own comment confirms the single-slice rendering is correct,
  not a bug. `FEATURE_BACKLOG.md` phases real sector breakdown into Phase 2.
- **`holding_snapshot` wiring.** Real gap (documented in the overview doc's §7), but
  deliberately left out of this list because it needs a product decision first
  (should Reconcile actually persist declared quantities into this table, or should
  the table be retired if the request-body approach is sufficient forever?) rather
  than a default "wire it up" instruction — raise this with whoever owns product
  scope before turning it into an implementation prompt.
