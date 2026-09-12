# Architecture Invariants

**Read this before planning or implementing any change to financial data. If a proposed
implementation conflicts with an invariant here, stop and flag the conflict rather than
improvising around it.**

These are the non-negotiable rules, not a history of how they were arrived at. Each names
where it is actually enforced, so a rule and its enforcement cannot drift apart silently.
Where an invariant is aspirational rather than enforced, it says so.

---

## The rules

**1. Never invent financial history.** No quantity, price, ratio or date is ever derived
from what would make the arithmetic balance. `CLAUDE.md`'s "never invent financial logic".

**2. Original broker transactions are immutable.** The `transaction` table is append-only;
a correction is a new row, never an edit. Rows keep the ISIN, price and date the broker
actually reported, even when the system later understands them differently.

**3. Detection may use inference. Resolution may not.** Finding a candidate can be
aggressive and heuristic; applying a transformation cannot. Enforced by the split between
`security_alias.detect_candidates` (free to guess) and `add_alias`/`verify_alias` (demand
evidence), and by `reconcile()` producing a `likely_cause` string that no code consumes as
an instruction.

**4. Every transformation requires verified evidence.** `screen()` — `check_sourced`,
`check_verified`, `check_price_consistency` — gates every corporate action, on every path.
There is no relaxed variant for any source.

**5. Failed verification is an unresolved exception, never a guess.** Missing evidence
lands the record `DRAFT` in `Exceptions` with the specific guard failure recorded. An
`Exceptions` entry is never converted into an adjustment, by a human or by the system.

**6. Unresolved exceptions retry automatically.** `refresh_corporate_action_feed`
re-evaluates every pending `DRAFT` row on every run with freshly looked-up prices, so a
record blocked only by absent data self-promotes the moment the data lands. No human step,
no new notice needed. `DISPUTED` is the one state retry never revisits.

**7. An ISIN change is an identity alias, not a transaction.** An ISIN identifies a
security; it is not the economic identity of the investment. Superseded identifiers are
recorded in `security_alias` and resolved at the ledger READ boundary
(`repository.load_transactions`). Never as `TRANSFER_OUT`/`TRANSFER_IN`, and never by
rewriting stored rows.

**8. An identity change never resets acquisition dates.** `app/engine/lots.py` opens a lot
at `txn_date` and derives `holding_days` from it, so a synthetic transfer pair would turn a
long-term holding short-term. Read-boundary normalisation is what preserves the original
dates. Pinned by
`tests/test_db_security_alias.py::test_the_acquisition_date_survives_an_isin_change`.

**9. Identity and quantity are separate facts.** An ISIN change carries no ratio. Any
quantity effect is a separate, price-corroborated corporate action. An identity mapping
must never smuggle in a quantity or cost transformation.

**10. Structural checks reject; they never vouch.** Same-issuer (ISIN characters 4–7) and
same-country-and-type (characters 1–3) can REFUSE an alias. Passing them proves nothing —
one issuer legitimately has several securities, distinguished at characters 8–9. Only
verified external evidence creates an alias.

**11. Post-transformation reconciliation is mandatory, and failure quarantines.** An alias
is finished when the ledger it produces still holds its invariants, not when it is
verified. `security_alias.reconcile_after_alias` asserts transaction count, no new negative
holding, unchanged lot dates and a preserved cost pool; failure disables the alias into
`Exceptions` rather than leaving it applied with a warning.

**12. Processing is idempotent.** Re-running any import, fetch, verification or application
changes nothing the second time — `dedupe_key` on the ledger, `ON CONFLICT` upserts on
prices and snapshots, content checks in `apply_known_actions_for_account`.

**13. The user never fixes a system or reference-data error.** A gap in our data is our
problem: it retries itself or waits in `Exceptions`. The user is only ever asked for
information that genuinely only they hold — what they paid, what they subscribed to.

**14. Complex corporate actions require authoritative inputs.** A demerger's cost
allocation comes from the prescribed ratio in the scheme document
(`engine/demerger.py` takes it as a required argument) and is never inferred from
arithmetic. A rights issue's subscribed quantity is investor-specific and unknowable from
any feed.

**15. The ledger is the source of truth; nothing downstream mutates it.** Holdings,
snapshots and allocations are derivations, recomputable at any time. A number shown to a
user must be reproducible by replaying the ledger — now also given `price`,
`corporate_action` and `security_alias` as reference inputs.

**16. A total that excludes something must say what it excluded.** Excluding a
non-reconciling holding is permitted; excluding it SILENTLY is not.
`portfolio_snapshot.excluded_isins` and the holdings API's `skipped` list carry the names,
so every reader can caveat the figure.

---

## Status of what these govern

Honest separation, so nobody reads an intention as a guarantee.

### Implemented and verified against real data
- ISIN aliases end to end — `security_alias`, read-boundary resolution, cycle safety,
  post-alias reconciliation, quarantine. **SKMEGGPROD** (`INE411D01015 → INE411D01023`)
  resolves automatically into one 12-share position with its original 2025-04-25
  acquisition date intact.
- Snapshots partition and record exclusions (`excluded_isins`), so one broken holding no
  longer blanks an entire value history.
- BONUS/SPLIT auto-verification with price corroboration, and self-correcting retry.
  **GUJTHEM's 2023 5:1 split** (ex 2023-10-10) self-promoted `DRAFT → VERIFIED` and applied
  with no human step once BSE evidence landed — cum ₹1047.80 on the retired ISIN, ex
  ₹225.15 on its replacement. **GUJTHEM's August 2024 event is now also resolved**: an
  independent capital-structure figure (paid-up equity ₹7,26,43,510 → ₹10,89,65,265, a
  confirmed 1:2 bonus, record date 2024-08-09) corroborated separately by a real price
  move (₹506.55 → ₹364.05) — two independent findings agreeing, never arithmetic on the
  account's own ledger. GUJTHEM now carries a real 0.5-share residual (325 × 1.5 = 487.5
  against 487 sold) rather than staying excluded.
- Historical price coverage on both exchanges via legacy archive tiers behind the existing
  `BhavcopySource` abstraction.
- `waive_price_evidence` gated on a POSITIVE FINDING (a confirmed archive absence, or an
  ex-date the archive was never asked about at all), never on a date range. The earlier
  version assumed "within the archive floor ⇒ obtainable", which GUJTHEM's own August 2023
  window disproved before the August 2024 event above was resolved. The basis
  (`ABSENCE_CONFIRMED` / `BELOW_ARCHIVE_FLOOR`) is now structured, not free text, and a
  `BELOW_ARCHIVE_FLOOR` waiver records the floor it rested on so it can be re-examined —
  `stale_price_waivers`/`revoke_stale_price_waivers` — if that floor is later lowered.

### Implemented, not yet exercised on real data
- yfinance discovery as a second free candidate source. Demonstrably incomplete — it found
  GENSOL's split exactly and missed KAMAHOLD's and GUJTHEM's entirely.

### Unresolved, deliberately visible
- **SOUTHBANK** — a rights-issue allotment gap, not an identity or ratio problem. The
  1-for-4 entitlement at ₹22 (record date 2024-02-27) is public; how many additional
  shares were applied for and allotted is not, and no feed can supply it.
- **SULA** — missing historical trades, no corporate action involved in any source. The
  usual cause is a tradebook export capped at 365 days.

### Future work
- Dividend ingestion. The read path is complete (`engine/dividends.py`, the dividends
  endpoint, the UI, and XIRR/TWRR/contribution all consume it) but **no write path exists
  beyond manual entry** — NSE's feed carries dividend notices and the parser deliberately
  skips them. A dividend does meet the auto-apply criterion (paid to every holder of
  record, unconditionally); TDS treatment is the open question.
- Rights, mergers and consolidations under the same fail-closed framework.
- A licensed market-data vendor behind `BhavcopySource`, for redistribution rights and for
  historical corporate-action NOTICES (as distinct from prices).

### Deliberately excluded
- CONSOLIDATION and MERGER as corporate-action types — `TxnType`'s free-share group is
  additive-only and cannot remove quantity while leaving the cost pool untouched. Adding
  either needs a new ledger mechanism, which is a separate decision.
- DEMERGER in the automated feed — `check_price_consistency` has no expected price ratio
  for one, and the cost ratio must come from the scheme document regardless.
- Inferring any ratio from quantity arithmetic, however well it fits.

---

## A note on external products

Where another product's behaviour informed a decision, this repository records **what is
publicly documented** and **what is inference**, separately. In particular: MProfit
publicly documents that a split leaves the purchase date unchanged, that a merger retains
the original acquisition date, and that a demerger uses the tax-prescribed cost ratio. Its
internal security-master design is **not** publicly established and no design here rests on
a claim about it. Its own terms disclaim report accuracy. Useful as a UX reference; never
ground truth.
