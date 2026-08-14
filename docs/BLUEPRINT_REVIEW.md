# Review of the Three Stack Blueprints

Your developer's three documents (Django/Postgres, Firebase, Next.js+Supabase) were
reverse-engineered from a 69-page MProfit capture. This file records what was merged
into this spec, what was corrected, and what was rejected — with reasons.

**Overall: strong work.** The feature archaeology and the regulatory section are the
two most valuable things in it, and both are now folded in. Three items would have
caused real damage and have been changed.

---

## ADOPTED — merged in as-is or lightly edited

| From the blueprints | Where it now lives |
|---|---|
| Full MProfit feature taxonomy (Reports / Tools / Actions / Preferences) | `docs/FEATURE_BACKLOG.md` |
| 24-code asset-class list with `is_taxable` / `supports_xirr` flags | `schema/asset_classes.json` |
| Client consent model (notice version, timestamp, withdrawal, lawful basis) | `docs/COMPLIANCE.md` + `DATA_MODEL.md` |
| Audit log doubling as DPDP access log | `docs/COMPLIANCE.md` |
| Import **review-before-commit** with a confidence score | `docs/INGESTION.md` — **this was better than my original** |
| Corporate actions insert *new adjustment transactions*, never mutate history | already matched; now cross-referenced |
| Grandfathering formula `cost = max(buy, min(fmv_31Jan2018, sell))` | `docs/TAX_ENGINE.md` |
| Tax-software export formats (ClearTax, Winman, CompuTax, Spectrum, Genius) | `docs/FEATURE_BACKLOG.md` Phase 4 |
| Cost "meters" framing — where surprise bills actually come from | `docs/STACK_DECISION.md` |
| Stack verdict: **Django + Postgres over Firebase** | `docs/STACK_DECISION.md` — agreed, with reasons extended |

The import review flow deserves a specific mention: my original spec auto-committed
parsed rows. Theirs stages them with a confidence score for human confirmation. That
is correct and is now the specified behaviour.

---

## CORRECTED — three things that would have hurt you

### 1. The broker-API and MF-CAS-API tables must be deleted

All three blueprints include:

```
broker_api_credentials  (provider ZERODHA|DHAN|MF_CAS, encrypted_token, refresh_token)
MF CAS API (PAN + OTP, metered refresh)
```

**Delete both.** This is the single most consequential correction.

- **MF CAS API via PAN + OTP no longer exists.** AMFI directed MF Central to stop
  sharing investor data with third-party platforms in September 2025 after
  distributors complained of client poaching. Building against it is building against
  a closed door.
- **Storing a broker token means storing an order-capable credential.** Kite Connect's
  login flow has no read-only scope; the token can place, modify and cancel trades.
  For a SEBI-registered adviser with no discretionary authority, having that in a
  database is the fact that hurts at an inspection — independent of whether it is ever
  used.
- **Kite tokens expire at 6 AM daily** and the refresh token is reserved for
  exchange-approved platforms. Every client would log in every morning, forever.

The blueprints' own Section 8 says the platform must stay "portfolio accounting
software, not an advice engine." Storing credentials pulls in the opposite direction —
toward being a regulated data intermediary. `docs/INGESTION.md` states the boundary:
**the investor obtains their own document and gives it to us.** There is no
`credentials` table anywhere in this spec, and `make lint` fails the build if one
appears.

### 2. Phase 1 must not seed 24 asset classes as buildable scope

All three roadmaps open Phase 1 with *"do not simplify the asset-class list — it must
support EQ, MF_EQUITY, MF_DEBT, SIF, BNK, NPS_ULIP, INS, PPF_EPF, PO, GLD, SLV, JWL,
PR, ART, AIF, LN, PE, FD, BND, NCD, CD, STOCK_FNO, OTHER_FNO, US_EQ."*

That is 24 asset classes with different tax treatments, different holding-period
thresholds, different data sources and different corporate-action semantics — before a
single XIRR is verified.

**The correction is a distinction, not a deletion.** The list is retained in full as a
**lookup table** (`schema/asset_classes.json`) so the enum never needs migrating. But
Phase 1 *builds* exactly one: `EQ`. Your own stated MVP says "Indian listed equities
only… the objective is to build the best equity portfolio tracking engine possible."
That instinct was right; the blueprints quietly reverse it.

### 3. `holdings_snapshot` is a cache, and must be labelled as one

The blueprints define `holdings_snapshot` and `capital_gains_ledger` as tables, noting
they are "rebuilt from transactions, never hand-edited." Correct in intent — but a
table that exists is a table someone eventually writes to.

**Rule as specified here:** holdings are computed on read. A materialised snapshot is
permitted *only* as a performance cache, must be reproducible from the ledger at any
time, and must never be the source of a number shown to a client. At 20 holdings and
324 transactions the recompute is milliseconds; do not add the cache until profiling
proves you need it.

---

## REJECTED

**Option B (Firebase).** The blueprint diagnoses this correctly itself — Firestore has
no joins or server-side aggregation, which is precisely the FIFO and cross-portfolio
XIRR workload, so all the real work lands in a bolt-on Python Cloud Run service. That
is Option A with extra network hops and per-document read billing. Agreed: **Django +
Postgres.**

**Option C (Next.js + Supabase + separate FastAPI).** Splitting the API from the calc
service adds a serialisation boundary in the middle of the one thing that must be
correct. Same conclusion.

**`verify_against_mprofit.py` as the primary correctness gate.** All three blueprints
make correctness depend on diffing against a live MProfit subscription. That is a
dependency on a competitor's product, and it validates against *their* accounting
choices — which MProfit itself acknowledges differ legitimately between providers.

**Replaced by** `fixtures/golden_portfolio.json`: your real 324-trade portfolio,
verified independently twice (Excel and Python), reconciled against Zerodha's own
holdings export (17/20 exact) and across two consecutive CDSL CAS statements (17/17,
zero mismatches). No subscription needed, and it tests against reality rather than
against another vendor.

Keep the MProfit diff as a *secondary* check if you have access. It is a good
tie-breaker, not a foundation.

---

## MISSING from the blueprints — added here

- **Two XIRR variants.** All three specify "XIRR" as one number. Your own data shows
  why that is insufficient: all-time −17.44% versus current-holdings −34.81%. A single
  figure lets whoever reports it choose the flattering one.
- **A price pipe separate from ingestion.** The blueprints treat prices as an
  afterthought inside import. Prices are public data on a daily schedule; transactions
  are client data on an event schedule. Different pipes, different failure modes.
- **BSE bhavcopy alongside NSE.** Two ISINs in your real portfolio have no NSE symbol
  at all. NSE-only pricing silently breaks XIRR.
- **The reconciliation loop as a first-class feature.** The blueprints list "Reconcile
  Holdings" as a menu item. It is the corporate-action detector and the parser-drift
  alarm — build it in week one, not as a tool in month six.
