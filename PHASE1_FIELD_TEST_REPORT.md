# Phase 1 Field Test — Trackr+

> ### ⚠️ HISTORICAL ARCHIVE — not a specification, and not a to-do list
>
> This is **a Playwright field test of Phase 1, run 2026-08-20**. It describes the repository **as it was on the day it was written**
> and has not been maintained since. Live code and tests cite it for provenance, which is
> why it is kept.
>
> **Do not treat anything here as a requirement, and never open a session by working
> through it.** Where this file and `docs/ARCHITECTURE_INVARIANTS.md`, `docs/ENGINE_SPEC.md`,
> `docs/DATA_MODEL.md` or `docs/INGESTION.md` disagree, **those win**. Where they and the
> code disagree, **the code wins**. Start from `CLAUDE.md`.

**What this is:** a from-scratch account was walked through onboarding, then the three real
broker documents you dropped into the repo root were fed into the running app — driven by
Playwright (Chromium), not by hand — to see whether Phase 1 survives contact with a real
portfolio. Nothing in the app was modified to produce this. All figures below are either
read verbatim from your source files, taken from `trackr-backend/.trackr-logs/backend.log`,
or computed independently with exact-`Decimal` arithmetic against the formulas in
`docs/ENGINE_SPEC.md`.

**One-line version:** Onboarding, consent, and broker-account setup all work cleanly. But
neither of the two paths for getting real trades into the ledger — CSV/tradebook import
*or* manual entry — got a single transaction to actually land for this investor. Manual
entry fails for **any** security the app hasn't seen before, which in a fresh account is
every security. For a brand-new user, that's the whole product not working yet.

---

## Finding 1 — CRITICAL: manual transaction entry crashes for any security not already on file

The **Add transaction** form is the one ingestion path that isn't tied to a broker's export
format — it's supposed to work for anything. It didn't. Five real trades were entered, all
copied from your actual contract notes (two genuine GUJTHEM buys, two genuine RAILTEL buys,
one RAILTEL sell). Every submission failed with the same generic `Failed to fetch` — five
times in a row, five different transactions, one fresh investor.

The backend log shows why: `POST /investors/{id}/transactions` inserts straight into the
`transaction` table, which has a foreign key to `security` — and nothing on this path ever
creates that `security` row first.

```
File "app/routers/transactions.py", line 101, in create_transactions
    summary = save_transactions(connection, transactions)
File "app/db/repository.py", line 73, in save_transactions
    cur.execute(_INSERT, (...))
psycopg.errors.ForeignKeyViolation: insert or update on table "transaction"
  violates foreign key constraint "transaction_isin_fkey"
DETAIL:  Key (isin)=(INE942C01029) is not present in table "security".
POST /investors/8e3fe03d.../transactions HTTP/1.1 500 Internal Server Error
```

The CSV-import path (`app/db/imports.py`) already does the right thing here, deliberately,
with a comment explaining why:

> *"transaction.isin references security, so the master has to know these ISINs before any
> row can land. Requiring it to be pre-populated would mean no import could ever be the
> first thing to mention a security, which is backwards: the import IS how a new holding is
> discovered."*

Manual entry never got the same treatment. It's the exact case that comment warns against.

**Reproduced:** 5/5 attempts, across two separate script runs, both ISINs (INE942C01029,
INE0DD101019). **Impact:** manual entry — one of the two Phase-1 ingestion paths named
explicitly in CLAUDE.md — cannot get a single trade into the ledger for a new investor right
now.

---

## Finding 2 — HIGH: a malformed upload can crash the tradebook adapter instead of being rejected

`YSL473_2022-04-01_2023-03-31.xlsx` isn't a Zerodha Console tradebook CSV, despite the
filename. Opening it shows it's actually **fifteen individual Zerodha contract notes**, one
per sheet, one per trading day (19-10-2022 through 29-03-2023) — a different, legitimate
Zerodha export, with 72 real trades and full brokerage/STT/GST/stamp-duty breakdowns.

Uploading it anyway is a fair thing for a real user to try, and it should come back as a
clean rejection — the same way an unrelated PDF did moments later ("`Row 0: not a Zerodha
tradebook: missing ['isin', 'price', 'quantity', 'trade_date', 'trade_id', 'trade_type']`" —
a good, specific message). Instead, this file crashed the parser outright:

```
File "app/ingest/zerodha_tradebook.py", line 56, in parse
    if reader.fieldnames is None:
File ".../csv.py", line 102, in fieldnames
    self._fieldnames = next(self.reader)
_csv.Error: new-line character seen in unquoted field - do you need
  to open the file with newline=''?
POST /ingest/csv HTTP/1.1 500 Internal Server Error
```

`zerodha_tradebook.py` decodes any upload as UTF-8 text and hands it straight to Python's
`csv.DictReader` before checking anything about its shape. This file's bytes happen to
produce a raw newline inside what `csv` reads as an unquoted field, which the csv module
treats as fatal. The exception is never caught, so it becomes an unhandled 500 — and because
the crash happens after Starlette's CORS middleware has already handed off to the route,
the 500 comes back with no CORS header. Chrome reports that as a CORS failure, which it
isn't — a red herring an engineer could easily chase for an hour before finding this.

**Impact:** lower severity than Finding 1 — some rejection was correct here, since this file
genuinely doesn't fit the one wired adapter. The bug is that it's an ungraceful crash instead
of the graceful, specific rejection the same adapter already knows how to produce for other
malformed input (see the PDF case), plus the misleading CORS symptom on top.

---

## Confirmed working

- **Onboarding end to end** — register → create investor → grant DPDP consent → add a
  broker account → get a real contract-note forwarding address with Gmail filter
  instructions. All six screens worked, no dead ends.
- **File-level de-duplication** — re-uploading the identical PDF bytes in a second session
  correctly returned `409 Conflict — identical file already staged as batch d0ebe7e1...`,
  pointing at the original batch. CLAUDE.md's "re-importing the same file must be a no-op"
  rule holds.
- **The adapter's happy-path rejection message** — when a file parses as CSV-shaped text but
  is missing required columns, the error is exact and useful. It's only the crash case
  (Finding 2) that's worse than this.
- **The empty state on Holdings** — with zero transactions, it reads "No priced holdings —
  Import transactions to see positions here" instead of erroring or showing a blank page.
- **The calculation engine itself, in isolation** — see test results below. The engine
  wasn't what broke this test; the two paths into it were.

## Engine test suite (`make test`, run against this checkout before the UI pass)

| Suite | Result |
|---|---|
| `ENGINE_SPEC.md` hand-computed cases | **13 / 13 passed** |
| Demo-fixture replay through the real engine | **8 / 8 passed** |
| Golden 324-trade portfolio | **13 skipped** — `fixtures/golden_portfolio.json` isn't present in this checkout (gitignored real client data, by design) |
| `ruff` + no-float + no-credential-storage + layering lint | **clean** |

The golden-fixture skip is expected, not a failure — that test module skips by design
without the file. It means CLAUDE.md's specific headline numbers (₹15,79,245.74 invested,
XIRR −0.174361, …) couldn't be independently re-verified in *this* environment — not that
they're wrong.

---

## The three files, and why none of them imported cleanly

**`JUL2026_AA08220794_TXN.pdf`** — never reachable, two independent blockers. It's
password-protected, so its contents couldn't be read at all this session. That turned out
not to matter: the Import page only accepts `.csv`, and more fundamentally there's no HTTP
route for a PDF today. A PDF contract-note adapter (`app/ingest/zerodha_contract_note.py`)
exists in the codebase, but the ingest router only ever registers one adapter —
`_CSV_ADAPTERS = {"zerodha_tradebook": ZerodhaTradebookAdapter}` — so the PDF adapter isn't
wired to anything a browser can call yet.

**`YSL473_2022-04-01_2023-03-31.xlsx`** — real data, wrong shape, triggered Finding 2. Not a
tradebook; fifteen contract notes across GUJTHEM, RAILTEL, NATCAPSUQ, SOUTHBANK, ADANIGREEN,
ADANIENT, ADANIPORTS, ADANITRANS, and GOLDBEES. Genuine, useful data — just not the flat
"Zerodha Console tradebook CSV" shape the one wired adapter expects, and not a CSV at all.

**`pnl-YSL473.xlsx`** — not an import format, and a different period entirely. A Zerodha Tax
P&L summary for April–August 2026 — a different window than the FY2022–23 trades in the
file above, covering an entirely different set of holdings (ABFRL, KDL-SM, WAAREEINDO, …).
It can't cross-check the other two files against each other; it's a snapshot from a later
point in time, not the same data restated.

---

## Verifying the math the app couldn't finish

Because Finding 1 blocked every submission, none of this reached Holdings or Performance in
the app. Presented here as an independent check — hand-derived in Python `Decimal` from your
actual contract notes, following `docs/ENGINE_SPEC.md` §1–3 (BUY: `qty×price + charges`;
SELL proceeds: `qty×price − charges`) — so there's a known-correct answer on record for
whenever Finding 1 is fixed and this gets re-run.

**GUJTHEM · INE942C01029 · both buys, charges read verbatim off single-trade notes**

| Leg | Date | Qty | Price | Charges | Cost basis |
|---|---|---:|---:|---:|---:|
| Buy 1 | 2022-10-19 | 100 | 714.00 | 166.35 | 71,566.35 |
| Buy 2 | 2023-02-10 | 30 | 618.90 | 43.95 | 18,610.95 |
| **Position** | — | **130** | — | — | **90,177.30** (avg **693.671538**) |

**RAILTEL · INE0DD101019 · full round trip, fully closed**

| Leg | Date | Qty | Price | Charges | Net |
|---|---|---:|---:|---:|---:|
| Buy 1 | 2022-11-15 | 50 | 133.60 | 7.728554* | 6,687.728554 |
| Buy 2 | 2022-11-15 | 50 | 133.65 | 7.731446* | 6,690.231446 |
| Sell | 2023-02-01 | 100 | 122.15 | 12.42 | 12,202.58 |
| **Realised P/L** | — | 0 left | — | — | **−1,175.38** |

\* The two RAILTEL buys share one contract note that states brokerage/STT/GST/stamp duty
once for both legs combined (₹15.46). Apportioned here by trade value — a judgement call
made for this test, not something the app or `docs/ENGINE_SPEC.md` prescribes, since real
per-trade apportionment is the contract-note adapter's job, not manual entry's.

---

## How this was run

1. Registered a brand-new account, created a new investor record, granted DPDP consent,
   added a ZERODHA broker account — all through the real UI, driven by Playwright/Chromium.
2. Uploaded your two real `.xlsx` files and the PDF through the Import page exactly as
   given — no reformatting, no relabeling.
3. Read the contract-note workbook's raw XML (Python's stdlib `zipfile` + `ElementTree`, no
   conversion tooling) to recover the 72 real trades it contains, as independent ground
   truth.
4. Entered five of those real trades through the Add Transaction form, one at a time, to
   test the engine path directly.
5. Cross-checked every observed outcome against the backend's own log file, not just the
   message shown in the browser.
6. Ran `make test` against the untouched checkout for a baseline read on the engine itself.

Screenshots from the Playwright run (registration, consent, account onboarding, the "Upload
failed" and "Failed to fetch" states, the empty holdings page) lived in this session's
scratchpad, which was cleared by a sandbox reset before this report could be re-published as
an artifact — hence this file instead. Happy to re-run and re-capture them if you want the
visual evidence too.
