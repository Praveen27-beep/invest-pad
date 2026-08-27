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
Section 112A grandfathering and bonus stripping are Phase 2. Demerger cost ratios are
specified in §11 and implemented in `engine/demerger.py`.

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
| `CapitalGainsNotApplicableError` | `classify_term` (Phase 3, `engine/tax_classification.py`) called for an asset class whose `long_term_days` is `null` | raise; never return a guessed SHORT/LONG |
| `DemergerAdjustmentError` | `DEMERGER_COST_OUT`/`DEMERGER_COST_IN` (§11) replays against an ISIN with no current position | raise; the paired `DEMERGER_IN`/`BUY` history is missing or the rows are mis-ordered or mis-dated |

`NegativeHoldingError` is the signal that a tradebook was downloaded with a date
filter. Console caps each download at 365 days; the fix is to pull one file per
financial year going back until a download returns empty.

---

## 10. Contribution analysis

```
compute_contribution(transactions, start_prices, end_prices, start_date, as_of) -> Contribution[]
```

The first Intelligence-layer feature per `docs/PRODUCT_VISION.md` — "which holdings
contributed most?" This section did not exist before this decision (confirmed by
product decision, 2026-08-20): three genuinely open questions had no answer anywhere in
this file, and per this repo's own rule ("never invent financial logic... if a case is
not covered here, ask"), they were put to the product owner rather than guessed. All
three are pinned below.

### The formula

Per ISIN, over the window `(start_date, as_of]`:

```
net_flow  = + (qty * price + charges)   for BUY, IPO_ALLOT, TRANSFER_IN   dated in the window
            - (qty * price - charges)   for SELL, TRANSFER_OUT, BUYBACK   dated in the window
            - dividend_amount           for DIVIDEND                     dated in the window

gain      = (end_value - start_value) - net_flow
```

`start_value` and `end_value` are the ISIN's `market_value` (§2) at `start_date` and
`as_of` respectively — `0` if the ISIN was not held on that date, never omitted.

This is **not a new formula invented for this feature** — it is section 5's TWRR
flow-adjustment (`_period_flow` / `sub_return`'s numerator), applied per-holding instead
of portfolio-wide, expressed as a rupee amount instead of a ratio, and not chained or
annualised because contribution answers "how many rupees did this holding add," not
"at what rate." The acquiring/disposing type grouping is `ACQUIRING_TYPES` /
`DISPOSING_TYPES` from `engine/types.py` — the same grouping `compute_holdings` uses for
the cost pool — **not** TWRR's `PORTFOLIO_IN_TYPES` / `PORTFOLIO_OUT_TYPES`, which
deliberately omit transfers. That is a required divergence, not an inconsistency: a
`TRANSFER_IN` moves `market_value_i` (shares appear) without being gain, so leaving it
out of `net_flow` here would misattribute a transfer as if it were 100% price
appreciation. `BONUS` / `SPLIT_ADJ` / `DEMERGER_IN` correctly stay at zero flow, matching
every other section in this file: a bonus does not, by itself, change what the position
is worth (quantity rises, price adjusts down), so there is nothing to back out.

**Dividends count as part of a holding's contribution (confirmed 2026-08-20).** Signed
identically to how §5's TWRR treats them: an outflow that *increases* the gain figure —
`- dividend_amount` inside `net_flow`, which is then subtracted, so a dividend paid adds
to `gain` the same way it inflates a TWRR sub-period's numerator. This is the
total-return convention, matching TWRR's own Candidate B decision rather than
`net_invested`'s capital-only one (§5): a high-yield, flat-price holding must show real
contribution, not zero, or the feature would misreport exactly the holdings a dividend
strategy is built around.

`pct_of_total = gain_i / total_gain`, where `total_gain = Σ gain_i` over every ISIN in
the result (not computed independently — see below). `None` only when `total_gain == 0`
exactly; defined and shown for any nonzero `total_gain`, **including negative** — a
portfolio-wide loss still produces meaningful percentages (see the worked example).

### Which ISINs appear

Every ISIN held (`quantity > 0`) at `start_date`, held at `as_of`, or carrying at least
one transaction dated in `(start_date, as_of]` — **including a position fully exited
during the window** (confirmed 2026-08-20). `docs/PRODUCT_VISION.md` asks "which
investments destroyed value?" as its own headline question; a holding dumped at a large
loss mid-period is exactly that answer, and dropping it from the list because it is no
longer held would hide the worst offender rather than surface it. There is no
"holdings-only" companion variant the way §4 pairs `xirr_all` with `xirr_holdings` —
every ISIN touched in the window is already in the one list, `end_value = 0` marking the
ones no longer held.

### Percentages are shown as-is, never capped (confirmed 2026-08-20)

Two holdings can have contributions bigger in magnitude than the portfolio's total gain
when they offset — one very positive, one very negative — producing percentages like
`+69%` / `+41%` / `−10%` (the worked example below) or, in a more extreme real
portfolio, figures further from a tidy 0–100% range. This is mathematically correct, not
a bug to hide: it is the same "show both, don't flatter" posture §4 already takes with
`xirr_all` vs `xirr_holdings` — normalizing or capping the percentage would misrepresent
which holding actually helped or hurt more, and there is no way to rescale it that
preserves that meaning.

### What this needs that §4/§5's other windows don't

`start_prices` must cover every ISIN **held at `start_date`**, and `end_prices` every
ISIN **held at `as_of`** — two separate priced-holdings valuations, not one. Both go
through `value_holdings` (§2) exactly as any other valuation does, so a missing price at
either end raises `MissingPriceError` naming the ISIN — never a substituted zero. This
also means the persisted `portfolio_snapshot` row (§8) **cannot** shortcut the
`start_date` valuation the way it does for `_window_xirr` / `_window_twrr`: a snapshot
row carries only portfolio-level totals, not a per-ISIN breakdown, and contribution
needs the latter. The router resolves `start_prices` the same way `_window_xirr`'s live
fallback already does — `compute_holdings` at `start_date` against prices looked up for
that date — every time, not only on a snapshot cache miss.

### Worked example

Also `fixtures/engine_cases.json`'s `contribution_mid_period_buy_sell_and_dividend`
case. Period `2025-01-01` (`start_date`) to `2025-12-31` (`as_of`).

```
ISIN A — held throughout, pays a dividend mid-period
  start_value  100 @ 1,000 = 100,000
  2025-06-15   DIVIDEND 4,000
  end_value    100 @ 1,300 = 130,000
  net_flow  = -4,000
  gain      = (130,000 - 100,000) - (-4,000) = 34,000

ISIN B — bought mid-period, still held
  start_value  0 (not held)
  2025-04-01   BUY 50 @ 2,000  ->  net_flow contribution +100,000
  end_value    50 @ 2,400 = 120,000
  net_flow  = 100,000
  gain      = (120,000 - 0) - 100,000 = 20,000

ISIN C — held at start, fully exited mid-period
  start_value  100 @ 500 = 50,000
  2025-07-01   SELL 100 @ 450  ->  net_flow contribution -45,000
  end_value    0 (no longer held)
  net_flow  = -45,000
  gain      = (0 - 50,000) - (-45,000) = -5,000

total_gain = 34,000 + 20,000 - 5,000 = 49,000

pct_A =  34,000 / 49,000 =  0.693878   (69.39%)
pct_B =  20,000 / 49,000 =  0.408163   (40.82%)
pct_C =  -5,000 / 49,000 = -0.102041  (-10.20%)
                                        sum = 1.000000 exactly
```

ISIN C answers the mid-period-full-exit question: its `gain` counts only the loss from
`start_date`'s value (`50,000`, since it was already held then) to the sale, `-5,000` —
not the position's entire lifetime realised gain, which could include cost from a
purchase long before `start_date` and would double-count into an earlier period's
contribution if included here. ISIN B answers the mid-period-buy question the same way
in the other direction: its `gain` counts only from its own purchase date, because
`start_value = 0` naturally excludes any period before it existed.

### What is still undefined, and why

`compute_contribution` returns a **single-period** breakdown, not an annualised rate —
there is no "contribution IRR." Chaining rupee contributions across multiple sub-periods
the way §5 chains TWRR ratios has no defined meaning here (rupee amounts don't compound
the way ratios do), so a caller wanting a trailing-window contribution (FY, 1Y) simply
calls this once with that window's `start_date` and `as_of` — there is no multi-snapshot
variant to build, unlike TWRR.

---

## 11. Demerger cost ratio

```
demerger_cost_split(original_isin, new_isin, txn_date, original_cost_basis,
                     cost_ratio_retained, source_ref=None) -> (Transaction, Transaction)
```

This section did not exist before this decision (confirmed with the user, 2026-08-20):
`§1` and `§3` already flagged `DEMERGER_IN`'s cost ratio as a later phase, and per this
repo's own rule ("never invent financial logic... if a case is not covered here, ask"),
the two open design questions below were put to the user rather than guessed. Both are
pinned here.

### The problem

Per `docs/TAX_ENGINE.md` "Corporate action tax nuances": a demerger carries **two**
ratios — a *quantity* ratio (how many new shares per old share) and a *cost* ratio (how
much of the original cost basis moves to the new company). Brokers routinely have only
the first. `DEMERGER_IN` (§1, §3) already records the quantity ratio's effect and — by
design, for the common case where the cost ratio isn't yet known — leaves the cost pool
alone: the new security enters at zero cost, 100% of cost stays with the original. That
is a deliberate placeholder, not a rule; this section is what corrects it once the
company's scheme document supplies the actual cost ratio, and it does so **without ever
touching `DEMERGER_IN` or any historical `BUY`/`SELL` row** — a scheme document can
surface months after the corporate action itself, and `docs/TAX_ENGINE.md`'s "Never
mutate history" rule means the correction can only ever be new rows.

### The mechanism — two new paired txn_types

| txn_type | isin | qty effect | cash effect | cost-pool effect |
|---|---|---|---|---|
| `DEMERGER_COST_OUT` | original (post-demerger) security | 0 | 0 | `− cost_transfer` |
| `DEMERGER_COST_IN` | new demerged-in security | 0 | 0 | `+ cost_transfer` |

`cost_transfer` is a new `Transaction` field, carried at full precision (Rule B applies
only at emission, same as every other pool-affecting field). It exists for the same
reason `dividend_amount` exists rather than overloading `price`: this is a capital-basis
movement, not a per-unit trade, on a row whose `quantity` and `price` are both zero.

Both rows are always produced as a pair: same `cost_transfer`, same `txn_date`,
`source=CORP_ACTION`, and a shared `source_ref` (the scheme-document reference) for
audit trail.

**Dating — the demerger's ex-date**, i.e. the same date as the existing `DEMERGER_IN`
row, never the (often much later) date the scheme document is actually confirmed.
Holdings and lots are *never stored* — every read is a full replay of the whole ledger —
so dating the correction at the ex-date makes it retroactive for free: any `SELL` that
happened between the ex-date and confirmation is correctly priced the next time anything
replays the ledger, with no need to touch that `SELL` row. Dating it at the confirmation
date instead would leave those interim sells permanently wrong. This falls directly out
of the "recompute on every read" architecture; it is not a preference.

**Ordering — `DEMERGER_COST_IN` must be inserted after the existing `DEMERGER_IN` row.**
`engine/ledger.py`'s `ordered()` sorts by `txn_date` alone and relies on Python's stable
sort to break same-date ties by insertion order — there is no `id` tiebreak. Since
`DEMERGER_COST_IN` shares `DEMERGER_IN`'s date, it must come after it in the list the
caller assembles, or the FIFO replay (below) tries to spread cost across a lot that does
not exist yet. `demerger_cost_split` cannot enforce this itself — it is a pure function
over two already-extracted values, not the ledger, the same shape as
`grandfathering.grandfathered_cost_of_acquisition(lot, fmv_31jan2018, sell_price)` — so
it is a documented precondition on the caller instead.

### Weighted-average effect (§1)

Quantity is untouched on both ISINs. `pools[original_isin] -= cost_transfer`,
`pools[new_isin] += cost_transfer`. `DEMERGER_IN`'s own row is untouched — it still
enters the new ISIN at cost 0; `DEMERGER_COST_IN` is what corrects that afterward.

### FIFO effect (§3) — proportional by quantity

A scheme document gives one aggregate cost-ratio number for the whole position; it does
not say which of several open lots loses (or gains) how much. Confirmed with the user:
spread the change **proportionally by quantity** across every lot currently open on that
ISIN — the FIFO analogue of §1's disposal rule (`pool × qty / held`), rather than
consuming the delta oldest-lot-first the way a `SELL` consumes quantity.

Distributing `delta = ±cost_transfer` across lots weighted by each lot's own quantity,
then re-expressing as a per-unit change, cancels the lot's own quantity out of the
formula — every open lot moves by the same flat **per-unit** amount:

```
per_unit_shift = delta / total_open_quantity
new_cost_per_unit = old_cost_per_unit + per_unit_shift          # for every open lot
```

### Worked example

```
2023-01-15  BUY  1000 @ 100                     -> pool 100,000 (Company A, ISIN A)
2024-06-01  DEMERGER_IN  500 shares Company B    -> already recorded, cost_transfer=0
                                                     (today's zero-cost placeholder)

Scheme document, sourced later: A retains 70% of cost, B receives 30%.
cost_transfer = 100,000 × (1 − 0.70) = 30,000

2024-06-01  DEMERGER_COST_OUT  ISIN A  cost_transfer=30,000
2024-06-01  DEMERGER_COST_IN   ISIN B  cost_transfer=30,000

Weighted average:
  A: qty 1000 (unchanged), pool 100,000 − 30,000 = 70,000, avg_cost 70.00
  B: qty  500 (unchanged), pool       0 + 30,000 = 30,000, avg_cost 60.00
  70,000 + 30,000 = 100,000  ==  original pool. Sums back exactly.
```

FIFO spread, if A's 1000 shares were instead two open lots (600 @ 100, 400 @ 100 —
same 100,000 pool):

```
delta = −30,000, total_open_quantity = 1000
per_unit_shift = −30,000 / 1000 = −30

lot 1 (qty 600): cost_per_unit 100 -> 70    (600 x 70 = 42,000)
lot 2 (qty 400): cost_per_unit 100 -> 70    (400 x 70 = 28,000)
42,000 + 28,000 = 70,000  ==  pool after the cost-out.
```

### Failure mode

`DEMERGER_COST_OUT`/`DEMERGER_COST_IN` replaying against an ISIN with no current
position (§9, `DemergerAdjustmentError`) means the paired `DEMERGER_IN`/`BUY` history is
missing, or the two adjustment rows are mis-dated or mis-ordered relative to it. Raise —
silently dropping the cost transfer would be a confidently wrong pool, the same failure
mode `NegativeHoldingError` guards against on the quantity side.
