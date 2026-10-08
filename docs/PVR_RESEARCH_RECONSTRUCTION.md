# PVR INOX research reconstruction

Reviewed 8 October 2026. Security: INE191H01014. Visible locally in the existing
landing-page workspace: PVR INOX → the ten company sections.

## What was inspected

InvestorStack's public company navigation and the user's accessible company screens
were used to understand the output contracts. No private API, source code, model
prompt or proprietary forecast was recovered. The visible valuation summary exposes
editable forward income-statement assumptions and exit multiples; capex is a dated
project/commitment narrative; forensics separates auditor information, flags, numbers
and follow-up checks. These patterns informed an original implementation.

The reference screen can mix periods and bases across modules. In particular, its
forensics numbers observed on 8 October were different from consolidated FY26 figures.
Our pack is explicitly consolidated. Some displayed percentage fields in the reference
valuation summary appeared inconsistent with its absolute numbers. We calculate our
own percentages and test their scale rather than preserving that display behaviour.

## Result contracts

| Section | Local result | Reproduction boundary |
|---|---|---|
| Overview | Filed operating KPIs, lease-adjusted income, calculated EBITDA margin, company net debt | Reproducible from cited filings; current quote and price history not attached |
| Financials | Two annual periods, both lease bases, selected balance-sheet extracts, management cash bridge | Reproducible; presentation cash bridge is not labelled statutory cash flow |
| Investment Thesis | Evidence, hypothesis and disconfirming conditions | Original interpretation, not InvestorStack's text or investor's committed thesis |
| Research Report | Original business, earnings-quality and cash-flow synthesis | Based on reviewed FY26 documents; no claimed exhaustive peer research |
| Valuation Summary | Conditional model and multiple sensitivity | Method inferred from visible output; assumptions independently chosen and labelled illustrative |
| Valuation Model | Editable three-year income/EBITDA/EBIT/PBT/tax/PAT and exit amount bridge | Deterministic decimal arithmetic; no per-share target or live market comparison |
| Capex Tracker | Openings, closures, deployed capital, signed pipeline and FY27 commitments | Filed values; signed screens are not commissioned screens |
| Read Between the Lines | Management paraphrase, separate interpretation, next question | Qualitative inference is explicit; no invented quotes |
| Forensics | Earnings quality, leases, disposal cash, liquidity, audit-scope checks | Arithmetic reproducible; assessment limited by source coverage, no fraud score |
| Management Consistency | Dated commitment baseline and internal debt reconciliation | Later call review still needed to establish delivered/failed outcomes |

## Source set and provenance

1. [FY26 presentation, filed 11 May 2026](https://nsearchives.nseindia.com/corporate/PVRINOXLTD_11052026140830_PVRINOXInvestorPresentation11052026.pdf).
   Printed slide 12 / PDF p13: operating KPIs; slide 21 / PDF p22: openings;
   slide 22 / PDF p23: capex/pipeline; slide 26 / PDF p27: cash bridge;
   slide 27 / PDF p28: debt; slide 31 / PDF p32: reported and lease-adjusted P&L;
   slide 32 / PDF p33: balance-sheet extracts.
2. [Audited consolidated exchange filing, 11 May 2026](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_156765_11052026210236_iXBRL_WEB.html).
   General information, P&L, notes, current assets/liabilities and audit declaration.
3. [11 May earnings call, filed 18 May 2026](https://nsearchives.nseindia.com/corporate/PVRINOXLTD_18052026133452_PVRINOXEarningsCallTranscript11052026.pdf).
   PDF p5: FY27 screen visibility, capital-light mix and cash aspiration;
   PDF p10: funding model and site economics.

These are issuer-originated documents, even where NSE hosts them. Agreement between
them is not independent-origin corroboration. Files were read through the web PDF/text
reader. Direct shell PDF download did not complete; no local raw-PDF bundle is shipped.
The dataset contains transcribed factual extracts, citations and original analysis.

## Units and accounting boundaries

- Presentation: INR million → divide by 10 to show crore.
- Exchange HTML: INR lakh → divide by 100 to show crore.
- P&L comparator is the FY25 column restated in the FY26 presentation.
- Total income includes other income; it is not labelled revenue from operations.
- Lease-adjusted EBITDA includes the cash-rent treatment. Pair it with debt excluding
  leases; reported EBITDA and lease-inclusive debt are a different analytical basis.
- Company cash includes investments/deposits/other bank balances; it exceeds the
  narrow statutory cash-and-cash-equivalents line.
- Management's free-cash-flow bridge includes disposal proceeds. Subtracting that one
  inflow does not establish comprehensive recurring free cash flow.
- No positive percentage growth is shown off a zero/negative base.

## Scenario specification

This is an exploratory projection in the public research snapshot, not a replacement
for the authenticated, versioned backend calculation registry. No result is persisted
as a user fact, portfolio entry, price target or approved research calculation.

All financial arithmetic uses decimal.js-light, with string inputs. Default assumptions
are an illustration: flat annual total income, 14.4% margin, FY26 depreciation/finance
costs/JV loss carried forward, 25% tax on positive profit, 8x exit multiple and unchanged
lease-excluding net debt. They are not a valuation opinion or management guidance.

Annual income compounds. EBITDA is income times margin. EBIT deducts depreciation;
PBT deducts finance costs and the fixed JV loss; tax is charged on positive PBT only.
The exit amount is the FY29 EBITDA times the user multiple, with assumed net debt
subtracted for an equity bridge. This is not a present value, share-price target or
cash-flow forecast. No exceptional/disposal profit is assumed. Negative equity bridges
remain negative rather than being silently clamped to zero.

## Integration and remaining coverage

The existing WorkspaceDemo renders PublishedResearch only for PVR INOX. Other company
previews retain their own empty templates; no PVR figures leak into them. The user can
explicitly append a research question and source to their demo notes. Reload semantics
remain those of the existing public demo. Authenticated investor data is untouched.

The next data work is a reviewed subsequent-quarter pack, the full annual report and
related-party/auditor-history evidence. The existing Yahoo fundamentals cron and
research evidence pipeline remain the appropriate routes for continuous data; no
parallel request-time Yahoo scraper was introduced. Current prices, autonomous report
generation and persistent scheduling are not claimed by this snapshot.

## Validation

Run `node --test trackr-workspace-frontend/tests/pvr-research.test.cjs` for source-unit,
P&L reconciliation, lease/disposal, decimal scenario, compounding and invalid-input tests.
Run `npm run typecheck:workspace` and the workspace production build. Browser checks
cover all sections, accounting-basis switch, scenario recomputation/error handling,
source links, question-to-notes append and company isolation.

Validation completed on 8 October 2026: seven calculation tests passed; workspace
TypeScript and isolated production build passed; `make lint` passed using temporary
Ruff tooling. The database migration check was skipped because DATABASE_URL was not
configured; no database changes were made. Desktop and 390px browser checks confirmed
all ten result sections, reported/adjusted switching, scenario recalculation and blank
input errors, cash-bridge values, note append and cross-company isolation. Mobile
section navigation uses a compact selector to preserve reading space.
