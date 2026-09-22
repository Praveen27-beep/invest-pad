# Phase 3 (Tax Engine) — implementation prompts

> ### ⚠️ HISTORICAL ARCHIVE — not a specification, and not a to-do list
>
> This is **Phase 3 tax-engine session prompts, generated 2026-08-20**. It describes the repository **as it was on the day it was written**
> and has not been maintained since. Live code and tests cite it for provenance, which is
> why it is kept.
>
> **Do not treat anything here as a requirement, and never open a session by working
> through it.** Where this file and `docs/ARCHITECTURE_INVARIANTS.md`, `docs/ENGINE_SPEC.md`,
> `docs/DATA_MODEL.md` or `docs/INGESTION.md` disagree, **those win**. Where they and the
> code disagree, **the code wins**. Start from `CLAUDE.md`.

Generated 2026-08-20, audited directly against the current codebase (not inferred from
`docs/BACKEND_REUSE_AND_GAP_ANALYSIS.md` or any other planning doc). Companion to
`docs/PHASE2_PROMPTS.md` — same format, same "hand this whole block to a fresh session"
intent — but for the highest-risk phase in the system.

## Read this before anything else: the gate is not open

`CLAUDE.md`, `docs/TAX_ENGINE.md`, and `docs/FEATURE_BACKLOG.md` all say the same thing
independently:

- `CLAUDE.md`, `docs/PHASE2_PROMPTS.md` §"Not included on purpose": *"Capital gains ...
  Explicitly Phase 3, gated behind a full quarter of real data plus mandatory CA
  sign-off. Do not pull it forward."*
- `docs/TAX_ENGINE.md` §1 (its title): *"Phase 3 — do not build in MVP ... built only
  after the MVP has run on real data for a full quarter."*
- `docs/FEATURE_BACKLOG.md` §"Phase 3": *"Treat as its own project ... Gate: CA review
  of one full FY before this informs any filing."*

As of this writing, none of that has happened: `fixtures/golden_portfolio.json` (the
client's real portfolio, the thing that would let Phase 1 even be called "verified" in
`CLAUDE.md`'s sense) is still not present on this machine, and there is no evidence
anywhere in this repo of the MVP having run on real client data for any stretch of
time, let alone a full quarter. **This document exists so the nine sessions below are
fully specified and ready to run the moment the gate opens — not so they get run now.**
Every session prompt repeats its own precondition check for exactly this reason: this
file will likely be read by a session that has no memory of this paragraph.

If you are a Claude Code session that has just been handed one of the prompts below:
**stop and confirm the gate is open before writing any code.** Ask whoever is running
you. "The document exists" is not the same as "the gate is open."

## What "the gate is open" means, concretely

Both conditions, not either:

1. The MVP has been in real use on real client data for a full financial quarter
   (per `docs/TAX_ENGINE.md`), **or** the person who owns product scope has explicitly
   decided to build ahead of that on hand-computed test cases only, accepting that
   nothing produced can inform a filing until condition 2 is also met. If it's the
   latter, get that decision in writing (a commit message, a doc update) before
   starting — don't infer it from silence.
2. There is a concrete plan for CA sign-off on one full FY, even if that sign-off
   itself happens after Sessions 1–9 below are built and unit-tested. Building without
   *any* path to sign-off produces code nobody may ever be allowed to use.

## Why this is its own document and not folded into `PHASE2_PROMPTS.md`

`docs/FEATURE_BACKLOG.md` is explicit: *"Treat as \[the tax engine\] its own project."*
Phase 2 was eight features deepening analytics on top of an already-correct ledger.
Phase 3 is different in kind, not degree: it is regulatory-facing, wrong-by-default in
subtle ways (`docs/TAX_ENGINE.md`: *"each independently capable of being quietly
wrong"*), and explicitly not allowed to inform a real filing without human (CA)
sign-off no matter how many tests pass. Mixing it into the Phase 2 closeout list would
bury a nine-session, own-project-scale effort inside what should stay a short list.

## Non-negotiable rules that apply to every session below

Restated here because a fresh session working from one prompt in isolation may not have
read `CLAUDE.md` or `docs/TAX_ENGINE.md` in full:

1. **Money is `Decimal`. Never `float`.** `make lint` greps `app/engine/` for `float(`
   and fails the build — this applies to tax code exactly as it does to the existing
   engine.
2. **The tax module stays framework-free**, like every other file in `app/engine/`.
   `make lint`'s second check greps for `app.(ingest|db|storage|prices|auth|routers|
   schemas)` imports inside `app/engine/` and fails the build on any hit. Tax functions
   take plain data in (transactions, lots, a CII table, an FMV table) and return plain
   data out — no DB session, no HTTP request object, ever, at this layer.
3. **Never mutate history.** `docs/TAX_ENGINE.md` §"Never mutate history": an "Auto
   Corporate Actions" tool inserts *new* adjustment transactions after confirmation; it
   never edits a historical `BUY` or `SELL` row. This is the same append-only rule
   `CLAUDE.md` states for the ledger generally, restated here because corporate-action
   handling is exactly where the temptation to "just fix the row" is strongest.
4. **Holding-period thresholds and CII values live in data, never in code.**
   `schema/asset_classes.json`'s `long_term_days` already varies by class (365 for
   equity, 1095 for debt MF, `null` where capital gains don't apply) and is explicitly
   documented as changing with the annual budget (REIT/InvIT moved 36→12 months in
   Budget 2024). A CII table is the same shape of fact: one static row per FY, sourced
   from CBDT, never hardcoded into a formula.
5. **Every rule is a pure function with hand-computed unit tests**
   (`docs/TAX_ENGINE.md` §"Verification gates" #1) — write the test from the spec
   first, per `CLAUDE.md`'s standing rule, not from whatever the function happens to
   return.
6. **Never invent financial logic.** If a case isn't covered in `docs/TAX_ENGINE.md`,
   `docs/ENGINE_SPEC.md`, or `docs/DATA_MODEL.md`, ask — don't guess. This phase has
   more of these gaps than any other; §"What's deliberately left undefined below" in
   several of the prompts names the ones already known.
7. **One feature per session, one commit per feature**, exactly as `CLAUDE.md` states.
   Session boundaries below follow `docs/FEATURE_BACKLOG.md`'s own Phase 3 table
   row-for-row so that mapping stays legible later.
8. **Nothing built in this phase may be described as "verified"** in the `CLAUDE.md`
   sense, or presented to the client as informing a filing, until both the golden
   fixture (A10) situation is resolved *and* a CA has signed off on one full FY per
   `docs/TAX_ENGINE.md`'s own verification gates. "Tested against hand-computed cases"
   and "verified" remain different claims here exactly as `docs/PHASE2_PROMPTS.md` §5
   established for Phase 2.

## Suggested order

**1, then 2, then 3–8 roughly as numbered (3 and 4 can swap; 5 and 6 can swap), then 9,
then the standing CA-reconciliation item last of all — but note 9 (CA reconciliation)
is not really "after" 1–8, it's the thing that validates them and may send you back to
fix any of them.** Session 0 (the precondition check) isn't numbered because it isn't a
build session — it's the gate check every session above already tells you to do, listed
once here so there's one obvious place to point a future session that asks "can I start
yet."

---

## 0. Standing precondition check — not a coding session, run this first every time

```
Before treating any session prompt in docs/PHASE3_PROMPTS.md as runnable, check:

1. Does fixtures/golden_portfolio.json exist yet (`find . -iname golden_portfolio.json`)?
   If not, that alone doesn't block Phase 3 per the FULL_VISION_BACKEND_ROADMAP.md
   Section E framing (build/unit-test can proceed on hand-computed cases the same way
   the engine itself did) -- but it does mean nothing produced this phase can be called
   "verified," and the person requesting this work should be told that plainly before
   you start, not after.
2. Has the person who owns product scope confirmed, in writing somewhere in this repo
   (a commit message, a doc edit, an explicit instruction in this session), that it's
   OK to build Phase 3 ahead of "the MVP has run on real data for a full quarter"
   (docs/TAX_ENGINE.md's literal gate)? If you can't find that confirmation, stop and
   ask -- do not infer permission from the mere existence of this prompt file.
3. Re-read docs/TAX_ENGINE.md and docs/FEATURE_BACKLOG.md's Phase 3 table in full, not
   just this document's summary of them -- they may have been edited since this
   document was generated (2026-08-20), especially the buyback tax-treatment note and
   any annual CII/threshold updates.
4. Check git status and git log for work already done under trackr-backend/app/engine/
   on any tax-shaped filename (grep for fmv_31jan2018, cii, grandfather, section_112a,
   stcg, ltcg, bonus_strip, demerger) -- another session may have already started or
   finished part of this list since this document was written.

Report what you find. Only proceed to a numbered session below if 1-4 all check out.
```

---

## 1. Schema prep: FMV table and CII table

```
Read docs/TAX_ENGINE.md's "Grandfathering" and "Indexation" sections and
docs/DATA_MODEL.md's `security` table section before doing anything else.

Context: this is the one Phase 3 session that touches the schema, so per CLAUDE.md
("Plan mode for anything touching the schema or the engine") it must start in Plan
Mode -- read the plan back, argue with it, get explicit sign-off, then execute. Nothing
downstream (Sessions 2-8) can be built correctly without this landing first: STCG/LTCG
classification needs holding-period data that already exists (schema/
asset_classes.json's long_term_days -- confirm no schema change is needed there before
assuming one is), but grandfathering (Session 3) needs a per-ISIN FMV constant that does
not exist anywhere in the schema today, and indexation (Session 4) needs a CII table
that doesn't exist either.

Two additions, both reference data (not derived, not per-transaction):

1. `security.fmv_31jan2018` -- docs/TAX_ENGINE.md: "a one-time historical constant per
   ISIN. Source it once from exchange archives." Nullable (most securities won't have
   one -- anything listed after 31 Jan 2018 never needs it). Decide in the plan: is this
   a column on the existing `security` table (mirrors how `sector` and
   `market_cap_bucket` were added -- read trackr-backend/app/db/migrations/012_market_cap.sql
   for the house style before writing this one) or a separate table? Lean toward a
   column, consistent with how sector/market-cap were added, unless there's a concrete
   reason not to.
2. A new small static reference table for CII values -- one row per financial year, per
   docs/TAX_ENGINE.md's "Needs a static CII table (CBDT values, hardcoded, one row per
   FY)." This is reference data with the same shape as `index_level`
   (migrations/011_index_level.sql) -- read that migration for precedent on how this
   codebase already models "static external reference data, not derived from the
   ledger, never joined against a security price." Do not overload the `price` table.

New migration file trackr-backend/app/db/migrations/013_<name>.sql (next free number
after 012_market_cap.sql). Read that migration's own comments for the house style
(CHECK constraints, WHY-focused comments) before writing this one -- match it.

Do not seed real CII values or real FMV data as part of this session. That's sourcing
work (Session 3 and Session 4 respectively) -- this session only builds the seam.
CLAUDE.md's asset_classes.json precedent applies here too: seeding the shape is this
session's job; populating it with real historical figures is not, unless the plan
explicitly decides otherwise and says why.

Run `make test` and `make lint` before claiming done. This is its own commit --
schema-only, no engine logic yet.
```

---

## 2. STCG / LTCG classification per asset class

```
Read docs/TAX_ENGINE.md's "Holding-period thresholds" section and
schema/asset_classes.json in full before doing anything else.

Context: this is the foundation every other Phase 3 session sits on -- grandfathering,
indexation, and both report-generation sessions all need to know whether a given
realised lot is short-term or long-term before they can do anything else with it.
docs/DATA_MODEL.md's Realised type already has a `term` field documented as
`SHORT | LONG` (see the "Derived — computed, never stored" section) -- confirm whether
trackr-backend/app/engine/realised.py already populates it in any form before assuming
this is greenfield; if it's already partially there, this session is "make it correct
and asset-class-aware," not "build from nothing."

Task:
1. Write a pure function (new file, trackr-backend/app/engine/tax_classification.py or
   fold into realised.py if the existing Realised type already carries `term` -- decide
   based on what you find in step 0 above) that takes a Realised lot plus its ISIN's
   `asset_class` and returns SHORT or LONG, reading the threshold from
   schema/asset_classes.json's `long_term_days` for that class -- never a hardcoded 365
   or 1095 anywhere in the function body. Where `long_term_days` is `null` for a class
   (FD, PPF_EPF, gold/jewellery among others), the function must say explicitly that
   capital-gains classification doesn't apply rather than silently returning a term.
2. Handle the two asset classes actually reachable in Phase 1/2 data first (EQ, and any
   others already flowing through the system) -- do not build special-casing for asset
   classes with zero rows in this system today (per CLAUDE.md's scope-discipline rule:
   "Seeding all codes is correct; building all codes is not" applies to tax logic the
   same way it applies to the engine).
3. Note the Budget 2024 REIT/InvIT threshold change (36→12 months) as a worked example
   of why this reads from data, not as something to implement now (REIT isn't Phase 1/2
   scope) -- but write the test that would catch a regression if someone hardcodes a
   threshold later.
4. Write hand-computed unit tests first, per CLAUDE.md's "tests are the specification"
   rule -- at minimum: a lot exactly at the threshold boundary (day 365 vs day 366 for
   equity), a lot for an asset class with `long_term_days: null`, and a lot for an asset
   class with a non-365 threshold (debt MF at 1095) to prove the function isn't
   hardcoding equity's number.

Run `make test` and `make lint` before claiming done.
```

---

## 3. 31-January-2018 grandfathering

```
Read docs/TAX_ENGINE.md's "Grandfathering" section (the exact formula is there) before
doing anything else. Confirm Session 1 (the fmv_31jan2018 column) has landed -- this
session cannot proceed without it.

Context: this only applies to equity and equity mutual funds acquired before
1 Feb 2018. Per docs/TAX_ENGINE.md, the formula is:

    cost_of_acquisition = max( actual_buy_price,
                               min( fmv_31jan2018, actual_sell_price ) )

Task:
1. Write a pure function that takes a lot's actual buy price, the security's
   fmv_31jan2018 (nullable -- most lots won't have one, and a lot bought after
   1 Feb 2018 must never apply this formula regardless of whether the security happens
   to have an FMV value), and the actual sell price, and returns the cost of
   acquisition to use for gain calculation.
2. The date check matters as much as the formula: a lot's applicability is decided by
   the lot's own acquisition date (from FIFO), not the security's. Get the source lots
   from trackr-backend/app/engine/lots.py rather than re-deriving acquisition dates.
3. Sourcing real fmv_31jan2018 values is explicitly out of scope for the *code* in this
   session (it's data acquisition, "source it once from exchange archives" per the
   spec) -- but the loader/seeding mechanism for that data (mirroring how
   app/db/load_sectors.py or app/db/load_market_cap.py load their respective reference
   data) is in scope, since Session 4's indexation table needs the same kind of loader
   and this session is a reasonable place to establish the pattern once.
4. Hand-computed unit tests: a lot before 1 Feb 2018 where FMV sits between buy and
   sell price (the formula's actual gate), a lot before 1 Feb 2018 where FMV exceeds
   the sell price (capped), a lot before 1 Feb 2018 where FMV is below the buy price
   (buy price wins), and a lot after 1 Feb 2018 (formula must not apply regardless of
   FMV value, even if a test intentionally supplies one to prove the date-gate is real).

Run `make test` and `make lint` before claiming done.
```

---

## 4. Indexation (CII table) for pre-April-2023 debt mutual funds

```
Read docs/TAX_ENGINE.md's "Indexation" section before doing anything else. Confirm
Session 1 (the CII reference table) has landed.

Context: applies to debt mutual funds purchased before 1 Apr 2023 (property and
unlisted assets are named in the spec too, but neither is reachable in this system's
data today -- per CLAUDE.md's scope discipline, build for MF_DEBT only, note the seam
for the rest). Formula:

    indexed_cost = cost x (CII_sale_year / CII_purchase_year)

Task:
1. Write a pure function taking a lot's cost, purchase FY, and sale FY, looking up CII
   values from the Session 1 table (passed in as data, not queried from inside this
   function -- keep the layer-purity rule: app/engine/ never imports app/db/).
2. The 1 Apr 2023 cutoff is itself a fact that could change; per CLAUDE.md's "these
   change annually -- keep them in data, never in code" rule, do not hardcode the date
   as a bare literal buried in an if-statement without a named constant that a future
   session can find and question.
3. CII table population (real CBDT values) is data-sourcing work, same caveat as
   Session 3's FMV data -- reuse whatever loader pattern Session 3 established rather
   than inventing a second one.
4. Hand-computed unit tests: a lot straddling a known CII table gap (what happens if a
   purchase-year or sale-year CII value is missing from the table -- this must raise,
   never default to 1.0 or silently skip indexation, per CLAUDE.md's "a missing price
   raises, never defaults to zero" rule applied to its tax-engine equivalent), and at
   least one lot with real (or clearly-labelled placeholder, if real CBDT figures aren't
   sourced yet) CII values producing a hand-verified indexed cost.

Run `make test` and `make lint` before claiming done.
```

---

## 5. Bonus stripping rules

```
Read docs/TAX_ENGINE.md's "Corporate action tax nuances" section (the bonus-share
paragraph specifically) and docs/DATA_MODEL.md's txn_type table (`BONUS` row) before
doing anything else.

Context: docs/DATA_MODEL.md already states bonus shares "enter the FIFO queue at cost
0, dated the ex-date" -- confirm trackr-backend/app/engine/lots.py already does this
(it should, since this is existing Phase 1 FIFO behaviour, not new) before writing
anything. This session is specifically about making bonus *stripping* -- the tax
strategy of selling original high-cost shares at a loss while the low-cost bonus shares
remain held, or vice versa -- correctly computable, which docs/TAX_ENGINE.md says the
cost-0 FIFO entry already enables.

Task:
1. Confirm (write a test if none exists) that a BONUS transaction produces a lot with
   cost_per_unit = 0 and the ex-date as its FIFO date, and that FIFO sale ordering
   against a mixed original/bonus position produces the correct realised gain per lot
   -- this is largely a verification task over existing FIFO code, not new logic, per
   the spec's own framing ("This makes bonus stripping computable" -- past tense,
   describing what already exists).
2. If gaps exist (e.g., FIFO ordering ties between an original lot and a bonus lot
   dated the same day), resolve them per whatever FIFO tie-break rule
   docs/ENGINE_SPEC.md §3 already specifies -- do not invent a new tie-break rule here.
3. Write the hand-computed unit test showing a full bonus-stripping scenario end to end:
   original shares bought, bonus issued, original shares sold at a loss, bonus shares
   still held -- confirm the realised loss and remaining bonus-lot position both come
   out right.

Run `make test` and `make lint` before claiming done.
```

---

## 6. Demerger cost-ratio allocation

```
Read docs/TAX_ENGINE.md's "Corporate action tax nuances" section (the demerger
paragraph) and docs/DATA_MODEL.md's txn_type table (`DEMERGER_IN` row) before doing
anything else.

Context: docs/TAX_ENGINE.md is explicit that this is the one corporate action brokers
routinely get wrong: "Demergers carry two ratios: a quantity ratio and a cost ratio.
Brokers typically have only the quantity ratio... The cost ratio comes from the
company's scheme document." DEMERGER_IN already exists as a txn_type
(qty effect +, cash effect 0) but per docs/DATA_MODEL.md's own note, "see ENGINE_SPEC
for cost ratio" -- check whether docs/ENGINE_SPEC.md actually has this today; if it
doesn't, that's a spec gap to raise, not one to fill by guessing (CLAUDE.md: "never
invent financial logic... if a case is not covered there, ask").

Task:
1. If docs/ENGINE_SPEC.md has no demerger cost-ratio rule, stop and get one written
   there first (with a worked example, matching the style of every other numbered
   ENGINE_SPEC section) before writing engine code against it -- this session may
   turn out to be "write the spec section" rather than "write the function," and
   that's a legitimate outcome, not a failure to complete the session.
2. Once a rule exists (either already present or newly written), implement a pure
   function that splits the original holding's cost basis between the original
   (post-demerger) security and the new demerged-in security per the cost ratio, as a
   *new* adjustment transaction per docs/TAX_ENGINE.md's "Never mutate history" rule --
   this must never edit the original BUY row's cost.
3. Hand-computed unit test with a real or realistic scheme-document-style cost ratio
   (e.g., a 70:30 cost split) confirming both resulting positions' cost bases sum back
   to the original, and that the original holding's transaction history is untouched.

Run `make test` and `make lint` before claiming done.
```

---

## 7. Schedule 112A generation

```
Read docs/TAX_ENGINE.md in full and docs/FEATURE_BACKLOG.md's Phase 3 table before
doing anything else. Confirm Sessions 2-6 have landed -- this session consumes their
output (classified, grandfathered, indexed realised gains) rather than computing gains
itself.

Context: Schedule 112A is the specific government schedule for long-term capital gains
on listed equity/equity MF above the exemption threshold, required as part of ITR
filing. This is government-form-shaped output, not internal engine logic -- the field
names, grouping, and exemption threshold are defined by the tax authority, not by this
codebase, and CLAUDE.md's "ask, do not guess" rule applies with extra force here:
**verify the current Schedule 112A field layout and exemption threshold against the
live ITR utility/schema for the relevant assessment year before implementing** -- do
not reconstruct the form from memory or from an old sample. If you cannot find an
authoritative current source for the exact field layout, say so plainly and stop rather
than guessing a plausible-looking structure.

Task, once the field layout is confirmed against a real source:
1. Write a pure function that takes a set of realised LTCG lots (already classified,
   grandfathered, and indexed by Sessions 2-6) and produces the Schedule 112A row
   structure -- ISIN, scrip name, sale/purchase details, FMV, cost of acquisition, gain.
2. Apply the exemption threshold correctly (confirm the current amount from the same
   authoritative source used for the field layout -- this number has changed before and
   will change again, so don't hardcode it as a bare literal without a way for a future
   session to find and question it, same discipline as Session 4's CII cutoff date).
3. Hand-computed unit test against a small realistic scenario matching the worked
   example style docs/TAX_ENGINE.md and docs/ENGINE_SPEC.md already use elsewhere.

Run `make test` and `make lint` before claiming done.
```

---

## 8. ITR-format capital gains report / tax software exports

```
Read docs/FEATURE_BACKLOG.md's Phase 3 table rows for "ITR-format capital gains report"
and "Tax software exports (ClearTax, Winman, CompuTax, Spectrum, Genius)" before doing
anything else. Confirm Session 7 (Schedule 112A) has landed.

Context: docs/FEATURE_BACKLOG.md lists these as two separate line items, but they're
closely related output-formatting work over the same underlying data Session 7
produces (classified STCG/LTCG realised gains, indexed and grandfathered where
applicable) -- this session can reasonably be two closely-sequenced commits rather than
strictly one, but keep them as two commits, not one, per CLAUDE.md's one-feature-per-
session rule, since they're genuinely different consumers (a filing report vs. a
third-party import format) even if they share a data source.

Same "ask, do not guess" caveat as Session 7 applies to every one of these formats:
ClearTax, Winman, CompuTax, Spectrum, and Genius each have their own specific import
file shape (column names, sheet structure, encoding). Do not guess any of them from a
plausible-looking CSV -- find and cite an authoritative current spec or sample file for
each format before implementing it. If only some formats have a findable current spec,
implement those and say plainly which ones were skipped and why, rather than shipping a
guessed format that silently fails on import into the real tool.

Task:
1. ITR-format capital gains report: a broader export than Schedule 112A alone --
   confirm from docs/TAX_ENGINE.md and docs/FEATURE_BACKLOG.md whether this means STCG
   too (Schedule 112A is LTCG-specific), and build accordingly. Same sourcing caveat as
   Session 7 for the exact current ITR schema.
2. Tax software exports: pick one format to start with reusing whichever adapter-style
   pattern this codebase already has for structured export (check whether one exists
   under app/ before inventing a new export module shape), and confirm with whoever owns
   product scope which vendor to prioritize rather than guessing -- this is exactly the
   kind of product-scope call CLAUDE.md says to ask about, not one to default silently.
3. Hand-computed / hand-verified test per format actually implemented.

Run `make test` and `make lint` before claiming done.
```

---

## 9. CA reconciliation and sign-off — the gate that actually matters

```
Read docs/TAX_ENGINE.md's "Verification gates" section in full before doing anything
else -- this session exists to satisfy gates #2 and #3 there specifically ("one full FY
reconciled against Zerodha's own Tax P&L report" and "CA sign-off on one full FY before
any client filing").

Context: this is not primarily a coding session, though it may surface bugs in Sessions
1-8 that need fixing. It's the step that turns "built and unit-tested against
hand-computed cases" into something CLAUDE.md would actually let you call "verified."
Note docs/TAX_ENGINE.md's own caution: "legitimate methodological differences exist
between providers -- MProfit itself acknowledges its capital gains can differ from a
broker's without either being wrong." A mismatch against Zerodha's Tax P&L is not
automatically a bug in this system -- it needs investigation, not a reflexive "make our
number match theirs."

Task:
1. Run one full FY of a real (or realistically representative, if real data still
   isn't available per this document's opening section) portfolio through Sessions 1-8's
   pipeline end to end.
2. Reconcile the output against that same period's Zerodha Tax P&L report, line by
   line. Where numbers differ, determine whether it's a bug in this system or a
   legitimate methodological difference (e.g., a FIFO-vs-broker-default lot-matching
   choice, a grandfathering edge case the broker's report handles differently) -- and be
   able to state which, and why, for each difference found.
3. Fix genuine bugs found (this may mean reopening Sessions 2-8's commits with follow-up
   fixes -- that's expected, not a sign this document was wrong to sequence things this
   way).
4. Get an actual CA to review the reconciled full-FY output. This is explicitly outside
   what code can satisfy on its own (docs/TAX_ENGINE.md: "CA sign-off on one full FY
   before any client filing") -- the deliverable of this step is a human sign-off,
   not a passing test suite.
5. Only after both reconciliation and CA sign-off: update this document and
   docs/TAX_ENGINE.md to state plainly that Phase 3 has cleared its own verification
   gates, with the date and what was checked -- mirroring how docs/PHASE2_PROMPTS.md §5
   insists "verified" stays an earned word, not an assumed one.

Nothing from this phase should be presented to a client as informing a real filing
before this session's sign-off step is complete, no matter how many of Sessions 1-8's
tests pass.
```

---

## Not included on purpose

- **Any asset class beyond EQ and, where explicitly named by `docs/TAX_ENGINE.md`
  (indexation), `MF_DEBT`.** Phase 4 (multi-asset) is a separate, later phase per
  `CLAUDE.md`'s MVP scope table. Building STCG/LTCG or grandfathering logic for REIT,
  SGB, or any other class not yet flowing through this system would be building ahead
  of data that doesn't exist, the same mistake `CLAUDE.md`'s scope-discipline section
  names for `schema/asset_classes.json` generally.
- ~~**The "Auto Corporate Actions" tool itself as a user-facing feature.**~~
  **Superseded, twice.** Sessions 5 and 6 build the underlying cost-basis mechanics
  (bonus stripping, demerger cost ratios) correctly; a detection tool that surfaces
  corporate actions for confirmation was, at the time this was written, a separate,
  unscoped feature. It is now built, in two parts: `app.engine.corporate_actions` +
  `app.ingest.corporate_action_matcher` + `app.db.corporate_actions`, matching a
  maintained reference table against `reconcile()`'s output and staging the result
  through the existing review/promote flow; and, added when manual review per affected
  account turned out not to scale to many users and many securities,
  `apply_known_actions_for_account`/`_for_investor`, which applies an
  already-VERIFIED, price-corroborated entry directly with no staging step, triggered
  automatically on every import and on every new VERIFIED table entry. See
  `docs/ENGINE_SPEC.md` §7. Left here, struck through rather than deleted, as the
  record of the scoping decision this superseded.
- **Buyback tax treatment as a settled fact.** `docs/TAX_ENGINE.md` flags this
  explicitly: treatment changed 1 Oct 2024 (deemed dividend, not capital gains) and the
  spec itself says "verify current treatment before implementing." No session above
  builds buyback-specific tax logic — if it's needed, that's a tenth session, written
  only after that verification happens, not assumed into one of the nine above.
- **Anything from `docs/PHASE2_PROMPTS.md`'s own remaining scope.** That document's
  four closeout sessions are independent of this one and unblocked by it — don't let
  "Phase 3 planning" become a reason to defer Phase 2 closeout further.
