# Data Model

Six tables. That is the whole MVP.

```
investor ──< account ──< transaction >── security
                              │
security ──< price            │
                              │
                    (derived, never stored)
                              ▼
                    holdings, lots, performance
```

## `investor`

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `code` | text unique | `C001`. Use this in files and logs, **never the name or PAN.** |
| `display_name` | text | |
| `family_group_id` | uuid null | HNI portfolios are family units: self, spouse, HUF, kids. Model it now; retrofitting is a migration. |
| `owner_user_id` | uuid null FK→`app_user` | The login authorised to read this ledger (015). Every `/investors/{id}` scope checks it: another login gets 403; unowned rows are unreachable until claimed via `app.db.assign_owner`. |
| `onboarding_date` | date null | Adviser-onboarding anchor for `period_xirr` (009, ENGINE_SPEC section 4's "What `xirr_all` actually covers"). `null` until set; `period_xirr`/`period_start` are `null` right alongside it, never defaulted. |
| `created_at` | timestamptz | |

**Do not store PAN in this table.** If you need it (contract-note passwords), store a
hash plus an encrypted blob in a separate `investor_secret` table with its own access
path and audit log.

## `account`

One row per demat/broker account. The CAS reveals accounts you did not know existed —
in real data, a client's statement surfaced Groww and Axis alongside Zerodha.

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `investor_id` | uuid FK | |
| `broker` | text | `ZERODHA`, `GROWW`, `AXIS` |
| `dp_id` | text null | `DP00000000` |
| `client_id` | text null | `CL00000000` |
| `is_advised` | boolean | **Key flag.** False = client's own punting; exclude from advisory performance. |
| `label` | text | |

`is_advised` exists so a SEBI-registered adviser can report on the mandated account
only, cleanly, without arguing later about which trades were theirs.

## `security`

| column | type | notes |
|---|---|---|
| `isin` | text PK | **The identity.** 12 chars, `INE...`/`INF...` |
| `symbol` | text | display only — may change over time |
| `name` | text | |
| `exchange` | text | `NSE`, `BSE`, `BOTH` |
| `asset_class` | enum | `EQ` in MVP. The extension point. Codes come from `schema/asset_classes.json`. |
| `sector` | text null | NSE Industry classification, refreshed by `app/db/load_sectors.py` |
| `market_cap_bucket` | text null | `Large Cap`/`Mid Cap`/`Small Cap`, AMFI/SEBI classification, refreshed by `app/db/load_market_cap.py` (migration `012_market_cap.sql`) |
| `fmv_31jan2018` | numeric(20,6) null | Equity grandfathering constant (`docs/TAX_ENGINE.md` §Grandfathering), migration `013_grandfathering_indexation.sql`. Sourced once from exchange archives; NULL for anything listed after 31 Jan 2018 or not yet sourced. Loader is `app/db/load_fmv_31jan2018.py` (reads a locally-sourced CSV — see `app/prices/fmv_31jan2018_source.py` for why this one is file-based, not a live URL like `sector`/`market_cap_bucket`'s); no real values are seeded yet, that remains data-acquisition work. |

`asset_class` is the discriminator that lets mutual funds, bonds and SGBs join later
without a schema change. Every engine function must switch on it rather than assume
equity.

**Seed all 30 codes from `schema/asset_classes.json`. Build exactly one (`EQ`).** That
file also carries `long_term_days` per class — holding-period thresholds differ by asset
and change with the annual budget, so they live in data, never in code.

## `transaction` — the heart

**APPEND-ONLY. No UPDATE. No DELETE. Ever.**

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `account_id` | uuid FK | |
| `isin` | text FK | |
| `txn_date` | date | trade date, not settlement date |
| `txn_type` | enum | see below |
| `quantity` | numeric(20,6) | always positive; sign comes from `txn_type` |
| `price` | numeric(20,6) | per unit, excluding charges |
| `charges` | numeric(20,6) | brokerage + STT + GST + stamp, default 0 |
| `stt` | numeric(20,6) | Securities Transaction Tax, ALREADY INCLUDED inside `charges` (a subset, not additive), default 0. Tracked separately because Income Tax Act Section 48 disallows STT as a deductible expense for capital gains, on both the buy and sell leg — see `docs/TAX_ENGINE.md`'s Session 10 status note. Populated only by the contract-note adapter. |
| `source` | enum | `MANUAL`, `CSV`, `TRADEBOOK`, `CONTRACT_NOTE`, `EMAIL`, `CORP_ACTION` |
| `source_ref` | text | contract-note number, trade id |
| `dedupe_key` | text unique | **enforced at DB level** |
| `raw_payload` | jsonb null | the original row, for forensics |
| `created_at` | timestamptz | |

### `txn_type` enum

| value | qty effect | cash effect | notes |
|---|---|---|---|
| `BUY` | + | − (qty×price + charges) | |
| `SELL` | − | + (qty×price − charges) | |
| `BONUS` | + | 0 | free shares; dilutes average cost |
| `SPLIT_ADJ` | + | 0 | the *additional* shares from a split |
| `DEMERGER_IN` | + | 0 | new ISIN appears; see `ENGINE_SPEC` §11 for the cost ratio |
| `DEMERGER_COST_OUT` | 0 | 0 | cost basis leaving the original security; `ENGINE_SPEC` §11 |
| `DEMERGER_COST_IN` | 0 | 0 | cost basis arriving on the demerged security; `ENGINE_SPEC` §11 |
| `TRANSFER_IN` | + | 0 | **must carry the original cost** or the position looks free |
| `TRANSFER_OUT` | − | 0 | |
| `IPO_ALLOT` | + | − | |
| `BUYBACK` | − | + | |
| `DIVIDEND` | 0 | + | qty = 0, price = 0, `charges` unused; amount in `dividend_amount` |

For `DIVIDEND`, add a `dividend_amount numeric(20,6)` column rather than overloading
`price` — dividends are per-holding cash events, not per-unit trades.

For `DEMERGER_COST_OUT`/`DEMERGER_COST_IN`, add a `cost_transfer numeric(20,6)` column
for the same reason: the amount moving between the original and demerged security is a
capital-basis movement, not a per-unit trade, on a row whose `quantity` and `price` are
both zero. The two rows always arrive as a pair — same `cost_transfer`, same `txn_date`
(the demerger's ex-date, not whenever the scheme document is confirmed) — produced by
`engine/demerger.py`'s `demerger_cost_split`. See `ENGINE_SPEC` §11.

### `dedupe_key`

```
sha256(account_id | source | source_ref | isin | txn_date | txn_type | quantity | price)
```

A unique index on this column is what makes re-importing safe. Gmail forwarding
**will** deliver the same contract note twice; the database must be the thing that
refuses it, not application logic that someone later forgets to call.

> ### TODO — the key does not collide across sources
>
> **This key catches the same file imported twice. It does NOT catch the same TRADE
> described by two different documents.** A tradebook export and a contract note cover the
> same trades, and their keys differ for two independent reasons:
>
> 1. **`source` is part of the key** — one row is `TRADEBOOK`, the other `CONTRACT_NOTE`;
> 2. **prices differ in precision** — the tradebook exports `43.119999` where the note
>    prints `43.12`, the same fill rendered by two systems.
>
> Both would have to change for the keys to collide. Measured on real data: **146 of 259
> tradebook trades are also described by a contract note**, so importing both would insert
> every one of them twice.
>
> **Interim measure in place:** `db/precedence.py` arbitrates at the ingestion layer — a
> contract note outranks a tradebook, exclusions are recorded and audited. See
> `docs/INGESTION.md` § "The current rule".
>
> **Why that is not the real fix:** it puts cross-source knowledge in a policy every future
> adapter must know about, rather than in the key, which is the one place that cannot be
> forgotten. The proper change is a source-agnostic key over a normalised price — a schema
> change with a data migration, since every stored `dedupe_key` would need recomputing.
> `tests/test_zerodha_contract_note.py::test_the_same_trade_from_two_sources_does_not_currently_dedupe`
> pins the current behaviour and says to invert it when this lands.

### Corrections

Never edit. To fix a wrong row: insert a reversing transaction (`quantity` negated via
opposite `txn_type`), then insert the correct one. Both carry `source = MANUAL` and a
note in `raw_payload`. History stays immutable and auditable — which is what makes any
number reproducible on demand.

## `client_consent` — required before any client data lands

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `investor_id` | uuid FK | |
| `notice_version` | text | which privacy notice they agreed to |
| `purpose` | text | |
| `lawful_basis` | text | |
| `consent_given_at` | timestamptz | |
| `withdrawn_at` | timestamptz null | |
| `evidence_ref` | text | email message-id, signed PDF path |

DPDP is consent-first with withdrawal and erasure rights. Build the export and erasure
routines alongside this table, not later. See `docs/COMPLIANCE.md`.

## `audit_log` — DPDP access log and SEBI record

| column | type |
|---|---|
| `id` | uuid PK |
| `actor_uid` | uuid |
| `action` | text |
| `entity_type` | text |
| `entity_id` | uuid |
| `ts` | timestamptz |
| `diff_json` | jsonb |

Retention: **5 years** (SEBI Reg. 19 governs and exceeds DPDP's 1-year log minimum),
with a legal-hold flag that suspends deletion during a dispute.

## `app_user` — login, not referenced elsewhere in this doc

Documented here only for the two columns every `investor.owner_user_id` FK points at
and that nothing else names: migration `021_terms_acceptance.sql` adds

| column | type | notes |
|---|---|---|
| `tos_version` | text null | Which published terms-of-service version this login accepted |
| `tos_accepted_at` | timestamptz null | When. Both null until acceptance; neither is backfilled for existing logins. |

The rest of `app_user` (credentials, session handling) lives in the auth layer's own
code, not in this doc's "six tables plus later additions" scope.

## `investor_secret` — separate table, separate access path

| column | type |
|---|---|
| `investor_id` | uuid FK |
| `pan_hash` | text |
| `pan_enc` | bytea |
| `demat_enc` | bytea |

Field-level encrypted. **No broker tokens, ever** — there is no such column in this
system. See `docs/BLUEPRINT_REVIEW.md` §Corrected-1.

## `price`

| column | type | notes |
|---|---|---|
| `isin` | text | |
| `price_date` | date | |
| `close` | numeric(20,6) | |
| `source` | text | `NSE_BHAVCOPY`, `BSE_BHAVCOPY`, `MANUAL` |

PK: `(isin, price_date)`. NSE wins on conflict (deeper liquidity).

## `price_absent` — "fetched, not present", not a missing fetch

| column | type | notes |
|---|---|---|
| `isin` | text | FK -> `security.isin` |
| `price_date` | date | |
| `recorded_at` | timestamptz | Diagnostic only; nothing reads it to decide anything |

PK: `(isin, price_date)`, added by migration `022_price_absent.sql`. One row per
(security, date) where the bhavcopy WAS fetched and genuinely did not contain that
security — as opposed to the fetch itself never having happened, which is a different,
retryable condition this table says nothing about. Fixes a real bug: the backfill used
to infer "have we fetched this day?" from "does *some* security have a price row on
this day?", which silently stops being true the moment a new holding is bought —
`price_dates_present`'s old check saw every historical date as "present" (thanks to
other holdings) and never re-fetched bhavcopy for the new one, so it acquired no price
history at all and every snapshot from the purchase date onward failed with a logged
traceback on every `./start.sh` (observed live on GSMFOILS, ORIRAIL). Not a cache and
nothing is derived from it — it is a log of what an external archive said on a date,
which cannot be recomputed later. Never consulted for valuation: `MissingPriceError`
(CLAUDE.md rule 4) still fires exactly as before for a held ISIN with no usable price.

## `live_price` — intraday cache, not a ledger

| column | type | notes |
|---|---|---|
| `isin` | text | FK -> `security.isin` |
| `last_price` | numeric(20,6) | |
| `fetched_at` | timestamptz | |

PK: `isin` (one row per ISIN, no history — overwritten in place). Populated from Yahoo
Finance (`app/prices/yfinance_live.py`) via `app/prices/live.py::refresh_and_get`, and
consulted only for `as_of == today (IST)`, and only for the ISINs `price` has no row dated
*exactly* today for — the narrower exact-date question, not the carry-forward one, since on
any trading morning the newest `price` row is yesterday's and a carry-forward lookup would
report nothing missing. See `docs/ENGINE_SPEC.md` §2. Never a substitute for `price`: once tonight's bhavcopy lands,
that date is served from `price` exclusively and this table stops being read for it. A row
older than its TTL (`app/db/live_prices.py::DEFAULT_MAX_AGE_SECONDS`) is treated as absent,
the same posture `price`'s own staleness window takes, just on a minutes-not-days clock.

## `index_level` — published index levels

| column | type | notes |
|---|---|---|
| `index_name` | text | CHECK: `NIFTY50_TRI`, `NIFTY500_TRI`, `SENSEX_TRI` |
| `level_date` | date | |
| `close` | numeric(20,6) | |
| `source` | text | `NIFTYINDICES_TRI` |

PK: `(index_name, level_date)`. No ISIN and no FK into `security` — an index level cannot
be joined against a security by construction, so it can never be mistaken for a price.
`index_name` is a checked enum rather than a free-text symbol, which is why admitting a new
index is a migration (`019_nifty500_index_name.sql`) and not a code-only change.

NIFTY50_TRI backs `docs/ENGINE_SPEC.md` §6's single-figure benchmark XIRR; NIFTY500_TRI
backs the Dashboard's benchmark line. TRI in both cases, never a price index. SENSEX_TRI is
a valid value with no adapter behind it — no reliable free, machine-fetchable source
exists, so the router refuses it with a 400 rather than this table ever holding a guess.

## `holding_snapshot` — reconciliation only

CAS/broker-declared quantities, used to check the engine. **Not** a source of truth
for display.

| column | type |
|---|---|
| `account_id` | uuid FK |
| `isin` | text FK |
| `snap_date` | date |
| `quantity` | numeric(20,6) |
| `source` | text |

The reconciliation job compares this against `compute_holdings()`. A mismatch means
exactly one of: a corporate action, an off-market transfer, a missed contract note, or
a bug. All four need a human; all four are invisible without this check.

## `corporate_action` — verified reference data

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `isin` | text FK | |
| `action_type` | enum | `BONUS`, `SPLIT`, `DEMERGER` — see note below |
| `ex_date` | date | |
| `bonus_new` / `bonus_for` | integer null | BONUS: "N new shares for every M held" |
| `face_value_before` / `face_value_after` | numeric(20,6) null | SPLIT: printed on every exchange notice, not order-ambiguous like a ratio string |
| `resulting_isin` | text FK null | DEMERGER: the new company's ISIN |
| `demerger_new` / `demerger_for` | integer null | DEMERGER: quantity leg only — the cost-ratio leg is the existing, separate, manual `app.engine.demerger.demerger_cost_split` step |
| `price_cum` / `price_ex` | numeric(20,6) null | Mandatory for BONUS/SPLIT — the only automatic defence against an inverted ratio, see below |
| `source` / `source_url` | text NOT NULL | Provenance. Required, never optional |
| `verification` | enum | `DRAFT`, `VERIFIED`, `DISPUTED` — only `VERIFIED` rows can match a `Discrepancy` |
| `notes` | text null | |

Unique on `(isin, action_type, ex_date)`. Added by migration
`023_corporate_actions.sql`. **No ratio strings** — each row stores the primitive facts
off the exchange notice, the same reason `transaction` never stores a ratio: Indian
sources disagree on notation order for the same event, and a ledger that guesses wrong
is off by 5x with no error raised.

**CONSOLIDATION (reverse split) and MERGER are deliberately absent from `action_type`.**
`transaction.txn_type`'s free-share group (`BONUS`/`SPLIT_ADJ`/`DEMERGER_IN`) is
additive-only — quantity up, pool unchanged — and nothing in `app.engine.holdings`/
`lots` can remove quantity while leaving the cost pool untouched, or land a merged-into
security with no `TxnType` to do it. Representing either is a separate engine/schema
decision this table does not make.

This table is never written to by a FILE adapter, and never read by `compute_holdings()`
or anything that values a portfolio. It IS written to by one automated process --
`app.db.corporate_actions.refresh_corporate_action_feed`, which inserts a row `VERIFIED`
only when it independently passes the same `check_sourced`/`check_price_consistency`
guards every other path here enforces, `DRAFT` otherwise -- see `docs/ENGINE_SPEC.md`
§7's "Automated ingestion" for the full trust-model writeup and why that isn't a
weakened bar.

It is read by two consumers, not one:
`app.ingest.corporate_action_matcher.stage_corporate_actions`, which proposes a staged
`transaction` row against a real declared-holdings statement the same way a file upload
does; and `app.db.corporate_actions.apply_known_actions_for_account`/`_for_investor`,
which applies a `VERIFIED` row directly to an eligible account's own ledger with no
staging step, triggered automatically on every import and on every new `VERIFIED` row
added here (by a human, or by the automated feed above). See `docs/ENGINE_SPEC.md` §7,
"Matching against verified corporate actions", for all three paths and the safety
argument for each.

## `cost_inflation_index`

Static CBDT reference table for indexation (`docs/TAX_ENGINE.md` §Indexation), added by
migration `013_grandfathering_indexation.sql`. One row per Indian financial year.

| column | type | notes |
|---|---|---|
| `financial_year` | text PK | `"YYYY-YY"`, e.g. `"2023-24"` — same string convention as `app/routers/transactions.py`'s `_financial_year_bounds` and `schema/dividend.schema.json`'s `by_fy` keys |
| `cii_value` | numeric(10,2) | CBDT-published index number for the year, e.g. `348` for FY2023-24 |
| `source` | text | provenance, e.g. `CBDT` |

Modelled on `index_level`, not on `price`: a CII value has no ISIN and is never
joinable against `security`. Schema only as of this migration — no real CBDT values are
seeded and no loader exists yet; that is sourcing work for a later Phase 3 session
(`docs/PHASE3_PROMPTS.md` §4).

## Derived — computed, never stored

```
Holding   { isin, quantity, avg_cost, invested, last_price, market_value,
            unrealised, unrealised_pct, weight_pct, first_buy_date }
Lot       { isin, open_date, quantity_open, cost_per_unit }   # FIFO
Realised  { isin, sell_date, quantity, proceeds, cost, gain, holding_days,
            term }                                             # SHORT | LONG
Snapshot  { as_of, invested, market_value, unrealised, realised_to_date }
```

If any of these appear as a table in a migration, the architecture has been broken.

## Indexes

```sql
CREATE UNIQUE INDEX ON transaction (dedupe_key);
CREATE INDEX ON transaction (account_id, isin, txn_date);
CREATE INDEX ON transaction (txn_date);
CREATE INDEX ON price (isin, price_date DESC);
```

## Adding an asset class later

1. Add the value to the `asset_class` enum.
2. Add any class-specific `txn_type` values (e.g. `SIP`, `SWITCH_IN` for MF).
3. Teach `compute_holdings` and `compute_realised` to switch on `asset_class`.

No new tables. No migration of existing rows. That is the test of whether the model
was designed correctly.
