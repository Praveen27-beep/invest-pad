# ISIN Automation

**Point-in-time snapshot: 2026-09-22.** This describes the system as it stands today, not
how it was built. Where a stated fact depends on a one-time manual step still pending as
of this date, that is called out explicitly rather than assumed complete. As of this
revision nothing here is pending: the one gate the 2026-09-20 version carried
(`demerger_watch_enabled`) is discharged and recorded in §4.

## 1. The core principle: identity is not ratio

Two different facts get confused if this document says nothing else. **Identity** is the
question "is ISIN A the same security as ISIN B, just under a different code?" **Ratio**
is the separate question "how much does quantity and cost per unit change when that
happens?" This system answers them with two different trust models, on purpose, because
they have two different evidence profiles:

- **Identity is machine-verifiable.** NSE's own "Change in ISIN" circular is a
  structured, narrow-vocabulary notice — symbol, new ISIN, a short Remarks phrase, two
  dates. A regex over it is a legitimate read of a fact NSE stated, not a guess.
- **Ratio requires reading prose, except where the exchange publishes a fixed template.**
  A stock split's ratio ("Sub-Division from Rs. 10/- to Rs. 2/-") is also a fixed,
  narrow-vocabulary NSE phrasing — machine-readable for the same reason identity is. A
  merger or demerger's swap ratio and cost apportionment is not: it lives in a
  company-specific scheme document or apportionment letter, worded however that
  company's lawyers worded it, and there is no fixed template to parse.

That distinction is why splits/bonuses/consolidations can run fully unattended while
mergers/demergers cannot (§2), and it is why the safety property in this codebase is
never "trust the source," but "trust the source only where its own format constrains
what it can say."

`app/db/security_alias.py`'s own header states the corollary this principle implies for
resolution specifically: **an alias is an identity assertion, never an inference** —
detection may guess, `add_alias`/`verify_alias` never do.

## 2. What is automated, and what is permanently manual

### Fully automated, end to end

For an ISIN change (split, sub-division, consolidation, face-value change) affecting a
symbol already tracked:

```
NSE "Change in ISIN" circular
  -> app.ingest.isin_change_feed (parse: symbol, new ISIN, remarks, ex-date)
  -> app.db.isin_change_circulars.refresh_isin_change_feed (symbol join -> old ISIN;
     writes a DRAFT security_alias row)
  -> app.db.security_alias.promote_draft_aliases (reconcile_after_alias against every
     account holding either ISIN)
  -> VERIFIED (all accounts reconcile cleanly) or DISPUTED (any account fails)
  -> app.db.repository.load_transactions applies a VERIFIED alias at the read boundary
     on every subsequent replay, immediately
```

No human step in the clean-reconcile case. `reconcile_after_alias` (`app/db/
security_alias.py`) is the actual safety gate, not `verify_alias` — it checks, per
affected account: transaction count unchanged, no new negative holding, no invented FIFO
acquisition dates, and cost pool stable within Rule B's own rounding tolerance
(`app.engine.holdings.AVG_COST_PLACES`). Any one check failing on any one account
quarantines the alias immediately — see §4 for what a quarantined row looks like.

### Permanently manual, by design — not a gap

**Merger and demerger apportionment is never auto-applied, and this is not scheduled to
change.** Per §1, the ratio and cost-split for these events lives in prose with no fixed
template, so there is no safe way to extract it mechanically. Concretely in this
codebase:

- `security_alias._assert_same_identity` structurally **refuses** to let a cross-issuer
  ISIN pair (a merger/amalgamation) enter through the identity-alias path at all —
  characters 1–7 (country, type, issuer) must match, or the write is rejected outright.
- `app.ingest.demerger_watch` exists specifically because this gap is permanent: rather
  than trying to close it, the system surfaces the notice as a same-day log line so a
  human reads the actual scheme document promptly (§4).
- If a future change proposes parsing a merger/demerger ratio from NSE's free-text
  subject line the way splits are parsed, that proposal contradicts this section and
  should be rejected, not implemented around. The failure mode being prevented is a
  silently wrong cost basis, and no parser accuracy improvement changes that a
  company-specific prose document is not a fixed format.

## 3. `_DISQUALIFYING_TERMS`: two jobs, one list, needs periodic re-audit

`app.ingest.corporate_action_feed._DISQUALIFYING_TERMS` does two jobs at once, and both
depend on it staying current with NSE's actual phrasing:

1. **Ratio-parser safety gate.** A subject containing one of these terms is never
   classified as a plain BONUS/SPLIT, regardless of whether it also matches the ratio
   regex — this is what stops "Scheme Of Arrangement - Bonus Ncrps 46:1" (a real,
   confirmed-live notice) from being misread as a 46:1 equity bonus.
2. **Demerger-watch detection surface.** `app.ingest.demerger_watch` reads a narrower
   subset of the same list (demerger/merger/amalgamation/scheme of arrangement/capital
   reduction) to decide what to notify on.

A term missing from this list fails both jobs simultaneously: a notice goes
un-notified, *and*, if it happens to also be ratio-shaped, it risks being misclassified
as a genuine bonus/split. That combination — silent miss plus possible miscost — is why
this list is not "add a term when someone remembers to" but needs a standing audit
cadence.

**Baseline established 2026-09-20**: a full audit against 14,223 real NSE
corporate-action notices across two independent 3-year windows (2020–2022, 2023–2025),
267 distinct normalized subject shapes. Zero coverage gaps found for demerger,
amalgamation, scheme of arrangement, or merger phrasing; every ratio-shaped subject in
both windows was individually verified to be a genuine plain bonus/split, never a
disguised restructuring. One gap found and closed: "capital reduction"/"reduction of
capital" (confirmed live in both windows, added to both the disqualification list and
the demerger-watch regex).

**Recommended cadence: annual**, re-running the same audit method (pull the trailing
3-year window from NSE's `corporates-corporateActions` feed, normalize subjects, diff
against the current term list) against a fresh pull. NSE's phrasing has been observed
stable over the 6-year sample checked, but "stable so far" is not "will always be" —
this is a cheap check to repeat, not a one-time proof.

## 4. Architecture map

### Scheduled jobs

| Job | Cadence | Route | Does |
|---|---|---|---|
| Security-alias refresh + promotion | Weekly, Sundays | `POST/GET /ops/security-alias/refresh[-cron]` | `refresh_isin_change_feed` then `promote_draft_aliases`, back to back, one call — so a freshly-created DRAFT alias is promoted within minutes, not left for an independent schedule to eventually notice. |
| Demerger watch | Daily | `POST/GET /ops/demerger-watch/check[-cron]` | Re-reads the same NSE payload `corporate-actions/refresh-cron` already fetches; logs a warning per demerger/merger/amalgamation/scheme/capital-reduction notice touching a tracked symbol. Writes nothing. |

Both follow the same `X-Ops-Key` POST (human/non-Vercel trigger) + `CRON_SECRET` GET
(Vercel Cron) shape every ops job in this codebase uses (`app/auth/ops.py`). Declared in
`trackr-backend/vercel.json`; the full cron rationale, including why security-alias runs
as one combined job rather than two independently-scheduled ones, is in
`docs/DEPLOYMENT.md`.

### Feature flags — current state

| Flag | Value as of 2026-09-22 | Notes |
|---|---|---|
| `demerger_watch_enabled` | **`True`** (default, `app/config.py`) | Enabled 2026-09-22. Both gates the 2026-09-20 version of this table named are discharged — see "Why this flag flipped" immediately below. The flag itself stays rather than being deleted: a deployment that does not want the warnings sets `DEMERGER_WATCH_ENABLED=false` with no code change, and `tests/test_demerger_watch.py` pins both the default and that it can still be turned off. |

#### Why this flag flipped, and on what evidence

Two things gated it, neither of them a code defect, and both are now closed.

**1. A first look at real output.** Run 2026-09-22 against the live NSE
corporates-corporateActions feed over a 90-day window (2026-06-24 → 2026-09-22), reading
the same payload `corporate-actions/refresh-cron` already fetches:

| Measure | Result |
|---|---|
| Feed reachable, payload size | yes, 361,565 bytes |
| Notices matching `_DEMERGER_SUBJECT_RE` market-wide | **8** (≈ one every 11 days) |
| Of those, naming a symbol this database tracks | **0** |
| What `/ops/demerger-watch/check` would therefore have returned | `{"skipped": false, "logged": 0}` |

The 8 were `GUJENERGY`, `TRIVENI`, `INOXGREEN`, `SIYSIL` (×2, "Scheme Of Arrangement -
Bonus Ncrps"), `INDIAGLYCO`, `HEGAM`, `TVSHLTD` — all genuine company restructurings, no
false positives in the sample, and the two NCRPS rows are exactly the kind of notice
`_DISQUALIFYING_TERMS` is right to refuse to classify and this watch is right to mention.
**The steady state of this feature is silence**, against a 62-symbol tracked universe.
That is the measurement behind calling it a log line rather than a queue, and the reason
enabling it by default cannot bury anything.

**2. Independent verification of the database incident from this build's review.** Done
2026-09-22, against the real local database rather than from a report, and the finding
differs from what the report claimed — it is written up in full at the end of this
section because a correction is more useful than a tick.

> **Checked:** the `audit_log` of the configured database (`localhost:5433/portfolio`,
> 929 rows spanning 2026-08-26 → 2026-09-21) holds **exactly one** `ERASURE` row, dated
> **2026-09-05 11:45 UTC**, attributed to an actor uid, recording
> `{transactions_deleted: 70, investors_deleted: 1, documents_deleted: 0}`. There is **no
> `erase_investor` call from 2026-09-21**; that day's audit activity is 785
> `DIVIDEND_EVENT_ADDED`, 32 `DIVIDEND_EVENT_CORROBORATED` and 1
> `DIVIDEND_EVENT_DISPUTED`, and nothing else. The claimed event is not in this database's
> record.
>
> **Why that is the expected answer rather than a missing audit row.** The `C001` /
> `ZERODHA` / `INE411D01015`→`INE411D01023` combination is `tests/conftest_db.py`'s
> `investor` fixture plus `tests/test_db_ops_wiring.py`'s `OLD`/`NEW` constants, and those
> only ever exist inside the **`portfolio_test`** database the suite drops and recreates
> per session (`conftest_db.py`, `_existing_server_admin_url` path) — never in
> `portfolio`. `portfolio_test` does not currently exist on the cluster, so the rows in
> question were destroyed with it, exactly as designed, and are not queryable after the
> fact by anyone.
>
> **What was independently confirmed instead, which answers the question the gate was
> actually asking.** No client data was at risk, because there is none: all 22 investors
> in `portfolio` are self-evidently test accounts (`SMOKETES-*`, `BUGCHECK-*`, `TESTSEPT-*`,
> `FLOW*`, `DUPCSV-*`). `security_alias` in `portfolio` is **empty** — so the quarantine
> example quoted later in this section is illustrative, built from the test fixture's own
> identifiers, and not the record of a real quarantine. `isin_change_circular` is **empty**
> too: the circular feed has never been run against this database. The six real
> transactions carrying `INE411D01015`/`INE411D01023` (SKM Egg Products — **not** Indosolar,
> whose ISIN is unrelated) belong to six test investors, were created 2026-08-26 →
> 2026-09-08 by import and smoke-test flows, and are dev residue in the dev database rather
> than anything the erasure path touched.
>
> **The one thing that could not be confirmed, stated as such:** whether the reported
> erasure happened at all. It left no trace in the only durable record, and the database
> it would have run against no longer exists. Absence of a trace is not proof it did not
> happen; it is proof the report cannot be checked. The gate is discharged on the second
> finding — nothing real was exposed and nothing real could have been — not on the first.

**What that verification changed in the code**, because "nobody will make that mistake
again" is not a safeguard: `app/db/scratch.py` now exists. An ad hoc or one-off script
that wants a database gets `connect_scratch()`, which refuses anything but a database
explicitly tagged as disposable and never falls back to `DATABASE_URL`; five guards, of
which only the in-database tag vouches and the rest merely reject, in the same shape as
`docs/ARCHITECTURE_INVARIANTS.md` rule 10. `make lint` carries the matching rule — no `.py`
outside `trackr-backend/app/` or `tests/` may open its own connection, with
`scripts/check_migration_drift.py` the one named, read-only exception. That module's
docstring states what it cannot do: a script in `/tmp` that calls `psycopg.connect`
directly is outside every lint's reach, so this makes the safe path the easy path rather
than making the unsafe path impossible.

There is no flag gating the security-alias job — `refresh_isin_change_feed` and
`promote_draft_aliases` run unconditionally once the cron fires, because nothing in that
path writes without passing `reconcile_after_alias`'s own gate first.

### Where a reconcile failure lands

A `security_alias` row that fails `reconcile_after_alias` for any affected account is
set `DISPUTED` (`quarantine_alias`) with `notes` naming every failing account and the
specific check it failed, e.g.:

```
QUARANTINED: ZERODHA/C001 (account 8f0a10e3-...): INE411D01023 still does not
reconcile once merged -- a quantity-changing corporate action is probably missing
and must be entered first
```

The label leads with `broker/investor.code` (the human-readable identifier
`app.db.repository.list_accounts` already exists to show instead of a raw UUID), with
the UUID kept alongside for an exact lookup. `DISPUTED` is terminal — `verify_alias`
refuses to promote a disputed row — so recovering from a quarantine (typically: a
missing corporate action needs to be entered first) requires a person to notice the row,
fix the underlying gap, and re-open it by hand; there is no automated retry-from-DISPUTED
path today.

An unexpected exception during reconcile (a transport or database fault, not a failed
check) leaves the alias `DRAFT` rather than quarantining it — an unrelated failure is not
evidence the identity claim is wrong, and quarantining on it would be a one-way door.

## 5. Why merger/demerger will not become automatic

This will come up again — worth stating once, plainly, for whoever asks next.

The system already resolves the two things that make an ISIN change look automatable:
detecting that a company's ISIN changed (the NSE circular), and confirming the mapping
does not corrupt an account's ledger (`reconcile_after_alias`). What it cannot resolve
is the number a merger or demerger actually requires — the swap ratio, and for a
demerger, the percentage of cost basis apportioned to each resulting entity. Those
numbers are set by a scheme of arrangement specific to that transaction and published as
prose, not as data in a fixed field anywhere NSE, BSE, or a depository exposes
programmatically. There is no phrasing-robustness improvement that changes this: the
information genuinely is not in machine-readable form at the source, so an automated
parser would not be reading a fact NSE stated, it would be guessing one — exactly the
category of risk `docs/ARCHITECTURE_INVARIANTS.md`'s "never invent financial history"
rule exists to forbid.

`app.ingest.demerger_watch` is the considered answer to this limit: not an attempt to
close it, but to shrink the human half of it — the gap between a company filing the
apportionment letter and someone knowing to go read it, down to the same day.
