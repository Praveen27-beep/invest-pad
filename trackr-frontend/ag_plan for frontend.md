# Trackr+ Phase 1 Frontend Implementation Plan (`trackr-frontend/`)

This implementation plan details the full frontend web application build for **Trackr+** inside `trackr-frontend/`, scanning `trackr-frontend/reference_ui.png` while strictly removing all out-of-scope fluff items and implementing 100% of Phase 1 backend capabilities.

---

## 🚫 Explicit Scope Exclusions (Items Removed from UI Image)

Per design audit, the following 4 fluff / out-of-scope items present in the reference image are **strictly removed**:
1. ❌ **No Marketing Left Nav Links**: Removed `Approach`, `Team`, `Contact`, `Schedule a Call`, and agency banners. Replaced strictly with app navigation routes.
2. ❌ **No Gold or Foreign Currency Tickers**: Removed `USD/INR` and `GOLD` tickers (Trackr+ is strictly Indian equities & mutual funds).
3. ❌ **No Market-Cap Concentration Breakdown**: Removed Large/Mid/Small-Cap breakdown (no market-cap data feed exists in schema).
4. ❌ **No Intraday "Day Movers" Live Ticks**: Removed live intraday ticking movers (backend executes EOD daily price pipeline, not live streaming tick data).

---

## 🟢 Phase 1 Frontend Features to Build (`trackr-frontend/`)

### 1. Design System & Layout Shell
- **Theme**: Dark Terminal Emerald & Obsidian Slate (`#064e3b`, `#0b0e14`, `#121721`) with Champagne Gold highlights (`#c9a84c`, `#f3c969`) and warm cream typography (`#f5f0e0`).
- **Typography**: Tabular monospace numbers (`JetBrains Mono` / `tabular-nums`) paired with clean body text (`Work Sans` / `Inter`).
- **Sidebar**: Collapsible sidebar with real app routes:
  - 🏠 **Dashboard** (`/`)
  - 📊 **Holdings & FIFO Lots** (`/holdings`)
  - 📜 **Ledger Transactions** (`/transactions`)
  - ⚠️ **Reconciliation Queue** (`/corporate-actions`)
  - 🛡️ **Settings & Compliance** (`/settings`)
- **Header Tools**:
  - ISIN-first search bar ("Search symbol, ISIN or transaction ID").
  - Date selector (`as_of`).
  - **"Advised Accounts Only"** toggle switch (SEBI compliance filter).
  - **"Minimize Panel"** widget focus mode button (collapses dashboard into a single compact widget).

### 2. Main Dashboard Page (`app/page.tsx`)
- **6 Top KPI Cards**:
  1. *Total Invested*: Net of brokerage & STT (`₹8,18,000`).
  2. *Current Value*: Market value (`₹11,89,000`).
  3. *Unrealised P&L*: Absolute & % (`₹3,71,000`, `+45.29%`).
  4. *Realised P&L*: Since inception (`₹7,77,000`).
  5. *XIRR (Cash-Flow)*: All external flows (`+14.09%`).
  6. *XIRR (Holding Period)*: Excl. idle cash drag (`+12.49%`).
  *(Mandatory: Cash-Flow XIRR and Holding Period XIRR displayed side-by-side as a dual pair).*
- **Performance Chart**: Equity curve vs. invested capital with timeframe toggles (1M, 6M, 1Y, 3Y, Max).
- **Pending Corporate Actions Panel**: Callout card for detected stock splits/dividends linking to `/corporate-actions`.
- **Market Ticker**: Bottom ticker with NIFTY 50 and SENSEX indices.

### 3. Holdings Page (`app/holdings/page.tsx`)
- Dense data table: Ticker, Name, Qty, Weighted Avg Cost, LTP, Invested Value, Current Value, Unrealised P&L, Weight %, XIRR %.
- Features: Sortable columns, ISIN search filter, sticky header, spacing density toggle.
- **Amber Warning Badge**: Display `Cost Estimated` badge for holdings where historical cost is estimated.

### 4. Position Detail Page (`app/holdings/[symbol]/page.tsx`)
- Open FIFO Lot Table: Buy Date, Quantity, Cost Per Unit, Holding Days, Tax Term Classification (`STCG` vs `LTCG`).
- Symbol transaction ledger & position performance summary.

### 5. Ledger Transactions Page (`app/transactions/page.tsx`)
- Append-only transaction table covering all 10 transaction types (BUY, SELL, BONUS, SPLIT, DIVIDEND, DEMERGER, etc.).
- Manual Entry Drawer Form (mock/API submit).
- Immutability notice footer explaining reversal-entry accounting rules.

### 6. Reconciliation Queue Page (`app/corporate-actions/page.tsx`)
- Table/Cards displaying corporate action detection (Splits, Bonuses, Dividends) and depository discrepancies with "Apply Reconciliation Entry" action.

---

## 🛠️ Proposed Tech Stack & File Structure

```
trackr-frontend/
├── reference_ui.png                # Reference layout image
├── package.json                    # Dependencies (Next.js, React, Tailwind, Lucide Icons, TanStack Query)
├── tailwind.config.js              # Theme tokens (Emerald, Obsidian, Champagne Gold)
├── app/
│   ├── layout.tsx                  # Global shell & typography
│   ├── page.tsx                    # Dashboard (/)
│   ├── holdings/
│   │   ├── page.tsx                # Holdings table (/holdings)
│   │   └── [symbol]/
│   │       └── page.tsx            # Position detail & FIFO lots (/holdings/$symbol)
│   ├── transactions/
│   │   └── page.tsx                # Append-only transaction ledger (/transactions)
│   ├── corporate-actions/
│   │   └── page.tsx                # Reconciliation queue (/corporate-actions)
│   └── components/
│       ├── Sidebar.tsx             # Collapsible app navigation
│       ├── Header.tsx              # Search, Advised filter, Minimize toggle
│       ├── KPICard.tsx             # Metric card with sparkline & dual XIRR
│       ├── PerformanceChart.tsx    # Dual line chart (Current Value vs Invested)
│       └── ReconcileBanner.tsx     # Corporate action callout
```

---

## Verification Plan

### Automated Build Verification
1. Run `npm run build` inside `trackr-frontend/` to confirm zero TypeScript / build errors.
2. Run `npm run dev` and launch the dev server to test routes interactively.

### Manual UI Audit
1. Verify all 4 out-of-scope fluff items are absent.
2. Verify Dual XIRR pair is displayed side-by-side.
3. Verify "Advised Accounts Only" filter and "Minimize Panel" focus mode toggles work seamlessly.
