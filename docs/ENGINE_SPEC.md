# Engine Specification

Every rule needed to compute correct numbers. If a case is not here, **ask** — do not
invent financial logic.

All examples are hand-computed and appear as tests in `fixtures/engine_cases.json`.

---

## 1. Holdings

```
compute_holdings(transactions, as_of=None) -> Holding[]
```

Replay transactions in `(txn_date, id)` order. Positions with `quantity <= 0` are
closed and excluded from output.

### Two cost conventions, both computed

`compute_holdings` returns **both**:

| field | convention | answers |
|---|---|---|
| `invested`, `avg_cost` | **weighted average** — the display default | "what did the shares I still hold cost me, on average?" |
| `fifo_cost`, `fifo_avg` | **FIFO** — surviving lots | "which specific lots survived, and what did *those* cost?" |

They are identical unless a position has been **partly sold**, and then they can differ a
lot. In `fixtures/golden_portfolio.json`, KDL-SM: weighted average 383,378.18, FIFO
391,522.50 — a gap of **8,144.32** on one holding.

**Why both.** Weighted average is the honest display number: a sale removes cost
proportionally, so selling never changes what the shares you kept cost you. That property
is what the worked examples below rely on and what case 2 pins. But **brokers report FIFO**
— Zerodha's holdings statement gives KDL-SM an average price of 174.01, which is the FIFO
figure — so a portfolio that only computed the weighted average could never be reconciled
against the statement it came from, and the difference would look like a bug forever.

Computing both makes reconciliation a comparison rather than an investigation. `fifo_cost`
is also the basis capital-gains reporting needs, so it is not carried solely for display.

**The display default is the weighted average, and it does not change.** Nothing in §1's
worked examples or `engine_cases.json` moves.

### Weighted-average cost

MVP display uses weighted average. FIFO lots run alongside for tax (§3).

| txn_type | quantity | cost pool |
|---|---|---|
| `BUY`, `IPO_ALLOT`, `TRANSFER_IN` | `+qty` | `+ (qty × price) + charges` |
| `SELL`, `TRANSFER_OUT`, `BUYBACK` | `−qty` | `− pool × (qty ÷ held_before)` |
| `BONUS`, `SPLIT_ADJ`, `DEMERGER_IN` | `+qty` | **unchanged** |
| `DIVIDEND` | 0 | unchanged |

`avg_cost = pool ÷ quantity`

**Worked example — two buys**
```
BUY 100 @ 200  ->  qty 100, pool  20,000
BUY 100 @ 300  ->  qty 200, pool  50,000, avg 250
```

**Worked example — selling half leaves average untouched**
```
from above:      qty 200, pool 50,000, avg 250
SELL 100 @ 400   qty 100, pool 25,000, avg 250   <- avg does NOT move
```
Selling removes cost *proportionally*. A sale never changes what the remaining shares
cost you.

**Worked example — a 1:1 bonus halves the average**
```
holding:         qty 200, pool 50,000, avg 250
BONUS 200        qty 400, pool 50,000, avg 125   <- pool unchanged
```
This is the mechanism that automatically corrects cost basis after a corporate action.
No ratio arithmetic is needed anywhere in the code.

### Corporate actions are transactions, not an engine

The depository has already applied every split, bonus and demerger to the client's
actual holding. The system's job is to **notice the quantity changed** and record a
matching transaction — not to compute ratios.

Detection: see §7 Reconciliation.

---

## 2. Valuation

```
market_value    = quantity × last_price
unrealised      = market_value − invested
unrealised_pct  = unrealised ÷ invested        (undefined if invested = 0)
weight_pct      = market_value ÷ Σ market_value
```

**A missing price raises `MissingPriceError`.** Never substitute zero, never carry
forward silently beyond `MAX_PRICE_STALENESS_DAYS = 5`. A stale price shown as current
is worse than no price.

---

## 3. FIFO lots and realised gains

```
compute_lots(transactions)     -> Lot[]        # open lots, oldest first
compute_realised(transactions) -> Realised[]
```

Maintain a FIFO queue per ISIN. A `BUY` pushes a lot. A `SELL` consumes from the front,
splitting the oldest lot if the sale is smaller.

`BONUS` / `SPLIT_ADJ` push a lot at **cost 0** dated the corporate-action date — this
is what makes bonus-stripping rules computable later.

```
Realised = {
  isin, sell_date, quantity, proceeds, cost, gain,
  holding_days = sell_date − lot.open_date,
  term = LONG if holding_days > 365 else SHORT
}
```

**Worked example**
```
2024-01-10  BUY  100 @ 200
2024-06-10  BUY  100 @ 300
2025-03-01  SELL 150 @ 400

FIFO consumption:
  100 from lot 1 @ 200 -> cost 20,000, proceeds 40,000, gain 20,000, LONG  (416 d)
   50 from lot 2 @ 300 -> cost 15,000, proceeds 20,000, gain  5,000, SHORT (264 d)

remaining open: 50 @ 300
```

MVP computes and displays realised gains. It does **not** produce a tax return —
Section 112A grandfathering, bonus stripping and demerger cost ratios are Phase 2.

---

## 4. XIRR

```
compute_xirr(transactions, prices, as_of) -> Decimal | None
```

Build a dated cash-flow series:

| event | sign | amount |
|---|---|---|
| `BUY` / `IPO_ALLOT` | − | `qty × price + charges` |
| `SELL` / `BUYBACK` | + | `qty × price − charges` |
| `DIVIDEND` | + | `dividend_amount` |
| corporate actions | 0 | omitted — shares moved, not cash |
| **terminal, dated `as_of`** | + | **market value of everything still held** |

Solve for the rate where the NPV of that series is zero. Use `pyxirr` (or equivalent);
do not hand-roll Newton-Raphson.

**The terminal flow is why a tradebook alone cannot produce XIRR.** Trade files record
what already happened; they have no idea what an unsold position is worth today. That
number comes from the price pipe.

Return `None` when: fewer than 2 flows, or no sign change, or the solver fails. Raise
`MissingPriceError` if any held position lacks a price — never silently value it at 0.

### The two required variants

Both must be exposed. They answer different questions and the gap between them is
itself the insight.

| variant | transaction filter | question answered |
|---|---|---|
| `xirr_all` | every transaction ever | "what has my investing returned, all in?" |
| `xirr_holdings` | only ISINs currently held | "how is the live book performing?" |

### What `xirr_all` actually covers

`xirr_all` runs **from the earliest date with a verified holdings snapshot — not from
literal account inception — wherever a reconciling entry exists.**

Real ledgers do not always reach back to the first trade. Corporate actions live in
depository statements, not contract notes, and those statements are typically only
retrievable for a few years. When the corporate-action history behind a position cannot
be recovered, the honest repair is a dated `TRANSFER_IN` reconciling entry carrying the
quantity from a verified snapshot, and the ledger for that ISIN then begins there.

Two consequences that must never be glossed:

- **`xirr_all` is then a period return, not a lifetime return.** It is bounded below by
  the anchor date. Presenting it as "since inception" would overstate what is known.
- **`xirr_holdings` is unaffected**, because it depends only on the current positions'
  actual cost, which a holdings statement supplies directly and independently of any
  reconstructed history.

Any reconciling entry carries `cost_estimated` in its `raw_payload` when the cost is a
valuation rather than an actual purchase price. A UI showing `xirr_all` over an anchored
ledger must surface the anchor date beside it. See `fixtures/golden_portfolio.json`,
key `_ledger_anchor`, for a worked example.

**Never report only one.** In the golden fixture `xirr_all = −17.44%` while
`xirr_holdings = −34.81%` — the current book is *worse*, meaning positions that were
sold outperformed those retained. Most portfolios show the opposite bias (sell losers,
keep winners), which flatters a holdings-only number. Showing both removes the choice
to present whichever looks better.

### Period XIRR (advisor onboarding)

```
compute_period_xirr(transactions, prices, start_date, opening_value, as_of)
```

```
flow 1     : (start_date, −opening_value)      portfolio value at onboarding
flows 2..n : every transaction after start_date
final flow : (as_of, +current market value)
```

`opening_value` must be the **market value** on `start_date`, not cost. Sources: a CAS
month-end table, or a stored `Snapshot`.

**Every transaction between `start_date` and `as_of` must appear as its own dated cash
flow** — deposits, buys, withdrawals, all of them. Never aggregate them into the opening
value or the closing value.

The failure mode is specific and silent. An implementation that uses only the opening
value and the terminal value, dropping the intermediate transactions, **will inflate the
return whenever a deposit occurs mid-period**: money the client *added* gets counted as
money the portfolio *earned*. Nothing about the output looks wrong — it is a plausible
number, in the right units, with the right sign.

Worked example, and the tenth case in `fixtures/engine_cases.json`
(`period_xirr_mid_period_deposit_not_inflated`):

```
2025-08-11  opening value   1,000,000
2026-08-10  BUY                        cash out 2,000,000
2026-08-11  market value    3,050,000

correct  : flows -1,000,000 / -2,000,000 / +3,050,000  ->  ~5%
buggy    : flows -1,000,000 /             +3,050,000  ->  ~205%
```

The two answers are forty times apart, which is why that case needs no fine tolerance to
catch the bug.

**Guard:** if `as_of − start_date < 90 days`, still compute but set
`result.warning = "period too short to annualise meaningfully"`. Annualising a six-day
return is arithmetically valid and practically nonsense.

---

## 5. Other return measures

```
absolute_return = (market_value + realised_to_date − net_invested) ÷ net_invested
cagr            = (end_value ÷ start_value)^(365.25 ÷ days) − 1
```

`net_invested` — **net lifetime cash contributed**: every `BUY`/`IPO_ALLOT` cash
outflow minus every `SELL`/`BUYBACK` cash inflow, summed across the *entire*
transaction history, not just currently-held positions. This is the same cash-flow
universe `xirr_all` solves over (§4's `_transaction_flows`, summed instead of dated),
so `absolute_return` is the non-annualised sibling of `xirr_all` — both answer "what has
my investing returned, all in?", one as a ratio, one as a rate. `DIVIDEND` flows and the
terminal market-value flow are excluded, matching how `_transaction_flows` scopes cash
movement (dividends are not capital contributed).

`absolute_return` is **undefined when `net_invested <= 0`** — a portfolio with heavy net
withdrawals can drive lifetime net contributions to zero or negative even while
positions remain open. Return `None` in that case rather than raising or dividing by
zero; same convention `unrealised_pct` uses in §2.

CAGR assumes a single lump sum and no flows — only valid on a position basis or where
there were genuinely no contributions. **XIRR is the default headline metric**; CAGR is
shown per-holding only and is **never computed at the portfolio level, permanently, not
provisionally.** A portfolio is by construction a series of staggered dated
contributions — exactly the condition that breaks CAGR's lump-sum assumption, and
unlike `net_invested` above this is not a gap to fill in: there is no portfolio-level
`start_value`/`days` pair that isn't itself invented. In the one case where a
portfolio-level CAGR would be mathematically valid — a single funding date, no
subsequent flows — it coincides exactly with `xirr_all`, so there is no case where it is
both valid and not already covered by XIRR.

TWRR (time-weighted) is Phase 2. TWRR removes the effect of *when* the client added
money, so it measures the adviser; XIRR includes it, so it measures the client's
experience. Store dated snapshots from day one and both become computable.

**Chaining convention (pinned, confirmed by product decision on 2026-08-20 -- see
`docs/trackr_plus_phase2_overview.md` section 4, which flagged this as the one Phase 2
formula genuinely absent from this spec before now):**

```
compute_twrr(snapshot_series, transactions) -> Decimal | None
```

Sub-periods are consecutive PERSISTED snapshot rows -- not necessarily daily-adjacent; a
gap in the persisted series (a missed backfill day) simply widens that one sub-period
rather than being filled or interpolated, matching how `list_snapshots_range` already
treats a missing date as absent, never filled.

For each consecutive pair `(prev, curr)` in the series:

```
flow  = net external flow INTO the portfolio, transactions dated in (prev.as_of, curr.as_of]
        BUY / IPO_ALLOT   +   qty * price + charges
        SELL / BUYBACK    -   qty * price - charges
        DIVIDEND          -   dividend_amount
        corporate actions  0  omitted -- shares moved, not cash

r     = (curr.market_value - flow) / prev.market_value - 1
```

This is the mirror image of section 4's `_transaction_flows` sign table: XIRR signs
every flow from the INVESTOR's side (a BUY leaves their pocket, so it's negative; a SELL
or DIVIDEND enters it, so it's positive). TWRR needs the same events signed from the
PORTFOLIO's side instead, and this system has no cash sleeve (`compute_snapshot`'s
`market_value` is holdings-only) -- so a SELL or a DIVIDEND both remove value from the
tracked portfolio the same way, and the sign table above is just section 4's negated.
This is forced by the existing data model, not a free choice.

**Dividends are counted as return, not excluded (Candidate B of the product decision).**
Backing the dividend out of `flow` (as a negative, i.e. an outflow) is mathematically
equivalent to crediting it back into the sub-period's numerator -- so TWRR here is a
TOTAL-RETURN figure (price + income), matching how an adviser's skill is judged, and
symmetric with how `DIVIDEND` is already a positive flow to the investor in section 4's
own table. The rejected alternative (excluding dividends, matching this section's
`net_invested` treatment) would make dividend income invisible to TWRR entirely, since
`market_value` never reflects it either.

A sub-period with `prev.market_value == 0` (the account held nothing yet, or emptied out
completely) makes the ratio undefined -- return `None` for the whole computation rather
than a number computed from a division that doesn't mean anything, same posture as
`unrealised_pct`'s zero-invested guard above.

**Chaining and annualising:**

```
twrr_cumulative   = product(1 + r_i for each sub-period) - 1
twrr              = twrr_cumulative ** (365.25 / total_days) - 1
                    where total_days = (series[-1].as_of - series[0].as_of).days
```

Annualised the same way CAGR is (`DAYS_PER_YEAR = 365.25`, same fractional-power pattern
`app/engine/valuation.py`'s `_cagr` already uses in Decimal) so it stays directly
comparable to XIRR on the performance page -- the whole point of showing them together
per `docs/PRODUCT_VISION.md` is a client reading "1Y XIRR: -5%, 1Y TWRR: +3%" and
immediately seeing bad entry timing rather than a bad strategy. `None` when fewer than
two snapshot rows exist, or `total_days <= 0`, or the chained product is non-positive (a
total wipeout has no well-defined annualised rate, same reasoning `_cagr` uses for a
non-positive base).

**Worked example** (also `fixtures/engine_cases.json`'s
`twrr_dividend_and_contribution_sub_periods` case):

```
snapshots: 2024-01-01 market_value=100000  (anchor)
           2024-07-01 market_value=118000
           2025-01-01 market_value=121900
transactions: BUY 50 @ 200 on 2024-03-01 (cash +10,000)
              DIVIDEND 2,000 on 2024-12-15

sub-period 1 (2024-01-01 -> 2024-07-01): flow = +10,000
  r1 = (118000 - 10000) / 100000 - 1 = 0.08

sub-period 2 (2024-07-01 -> 2025-01-01): flow = -2,000 (dividend, outflow)
  r2 = (121900 - (-2000)) / 118000 - 1 = 0.05

twrr_cumulative = 1.08 * 1.05 - 1 = 0.134             (13.40%)
total_days      = 366                                  (2024 is a leap year)
twrr            = 1.134 ** (365.25/366) - 1 = 0.1337078...   (13.3708%)
```

No root-finding anywhere in this computation -- only `compute_period_xirr`'s
already-annualised siblings need `pyxirr`; TWRR chains via plain Decimal multiplication
and one fractional power at the very end.

---

## 6. Benchmark comparison

The honest method — replicate the portfolio's own cash flows into the index:

```
for each portfolio cash flow (date, amount):
      units = amount ÷ index_level(date)
      accumulate units
benchmark_terminal = total_units × index_level(as_of)
benchmark_xirr     = xirr(same dates, same amounts, benchmark_terminal)
```

This answers "what if I had bought the index on exactly the days I bought stocks" —
apples to apples. Comparing portfolio XIRR against a headline index CAGR is not a
valid comparison and must not be shown.

MVP benchmarks: NIFTY 50 TRI, SENSEX TRI. Use **TRI** (total return) not price index —
price indices exclude dividends and understate the benchmark.

---

## 7. Reconciliation — the corporate-action detector

```
reconcile(transactions, declared_holdings, as_of) -> Discrepancy[]
```

Compare `compute_holdings()` against a CAS or broker-declared quantity.

```
Discrepancy = { isin, computed_qty, declared_qty, difference, likely_cause }
```

Cause heuristics from the ratio `declared ÷ computed`:

| ratio | likely cause |
|---|---|
| ≈ 2 | 1:1 bonus or 1:2 split |
| ≈ 3 | 1:2 bonus or 1:3 split |
| ≈ 5, 10 | split |
| computed = 0 | transfer-in never recorded, or a new account |
| declared = 0 | full exit or transfer-out not recorded |
| other > 1 | missed buy contract note |
| other < 1 | transfer-out, buyback, or missed sell |

This single check catches corporate actions, off-market transfers, missed contract
notes, and parser bugs. It is the cheapest high-value component in the system — build
it early.

**Validated in production data:** June CAS + tradebook movements reproduced the July
CAS across all 17 positions with zero mismatches, including correctly excluding three
trades dated 31-Jul that settled 3-Aug. Settlement timing matters: reconcile on
**trade date**, and expect the last 1–2 days before a statement date to differ.

---

## 8. Snapshots

```
compute_snapshot(transactions, prices, on_date) -> Snapshot
```

Same functions, historical `as_of`, historical prices. Persisting a daily snapshot
enables the portfolio-value chart and TWRR later. Backfill requires historical
bhavcopy for every ISIN ever held.

Snapshots are a **cache of a derivation**, not a source of truth — they must always be
recomputable from the ledger.

---

## 9. Error taxonomy

| error | when | handling |
|---|---|---|
| `MissingPriceError` | held ISIN has no price within staleness window | raise; surface the ISIN list in the UI |
| `DuplicateTransactionError` | `dedupe_key` collision | skip silently, count, report in import summary |
| `UnparseableRowError` | ingestion cannot map a row | reject that row with row number; import the rest |
| `NegativeHoldingError` | sells exceed buys for an ISIN | flag loudly — indicates missing buy history |

`NegativeHoldingError` is the signal that a tradebook was downloaded with a date
filter. Console caps each download at 365 days; the fix is to pull one file per
financial year going back until a download returns empty.
