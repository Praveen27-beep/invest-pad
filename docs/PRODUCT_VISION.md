# Product Vision

## What this is

A portfolio intelligence platform for Indian investors — the single source of truth
for an investor's complete financial portfolio.

## What this is not

- **Not a brokerage.** No custody, no client funds.
- **Not an execution platform.** No orders, ever. No order-capable credential is
  stored anywhere in the system.
- **Not just a portfolio tracker.** Tracking is table stakes; explanation is the product.
- **Not a PDF parser.** Parsing is a feature. Anyone can parse. The engine and the
  insight are the moat.

## Core philosophy

**Everything is derived from transactions.**

```
Transactions -> Holdings -> Portfolio -> Performance -> Analytics -> Insights
```

The platform never stores manually calculated holdings. Every metric is reproducible
from transaction history. This is not an aesthetic preference — it is what makes the
numbers defensible under scrutiny, replayable at any historical date, and correct after
a bug fix without a data migration.

## MVP — Phase 1

Indian listed equities only.

**In:** manual entry, CSV import, transaction editing (via reversing rows), holdings,
FIFO positions, average cost, realised gains, unrealised gains, dividends, XIRR,
absolute return, CAGR, allocation, benchmark comparison, historical portfolio value,
daily performance.

**Out:** mutual funds, bonds, CAS parsing, derivatives, execution.

The objective is narrow and deliberate: **build the best equity portfolio tracking
engine possible.** Breadth before depth produces a product that does twelve things
badly.

## Long-term

One common portfolio model spanning Indian equities, mutual funds, ETFs, bonds,
G-secs, SGBs, NPS, PMS, AIF, REITs, InvITs, international equities, and optionally
crypto. New asset classes plug into the existing engine via the `asset_class`
discriminator — no new tables, no migration of existing rows.

## The intelligence layer

The competitive advantage is not storing portfolios. It is **explaining** them.

Questions the system should answer:

- Why did my portfolio outperform?
- Which holdings contributed most?
- Which investments destroyed value?
- Am I beating the benchmark, on my actual cash flows?
- Which sectors am I overexposed to?
- How concentrated am I?
- What dividends should I expect?
- How has my allocation drifted?
- Which specific decisions helped or hurt?

A concrete example this system already surfaces, from real data: lifetime XIRR of
−17.44% against current-holdings XIRR of −34.81%. The gap says the positions that were
sold outperformed those retained — the opposite of the usual sell-winners bias. No
tracker that reports a single number can tell you that.

## Product principles

1. Transaction-first architecture.
2. Source-agnostic ingestion.
3. Every calculation reproducible.
4. Historical data immutable.
5. Analytics update automatically.
6. New asset classes plug in, not bolt on.
7. Parsing is a feature, not the product.
8. Insights beat raw data.

## Ultimate goal

Instead of helping people buy investments, help them understand, measure, optimise and
learn from every investment across a lifetime — the permanent financial memory and
intelligence layer for an investor.
