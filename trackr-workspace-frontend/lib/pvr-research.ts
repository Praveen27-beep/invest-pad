/** Public, dated research snapshot. Money stays decimal strings, keyed by ISIN.
 * Issuer filings on NSE are the same origin as the issuer presentation, not
 * independent corroboration. This never writes into investor facts or the ledger.
 */
import Decimal from "decimal.js-light";

export const PVR_ISIN = "INE191H01014";
export const sources = {
  presentation: { title: "FY26 investor presentation", date: "11 May 2026", url: "https://nsearchives.nseindia.com/corporate/PVRINOXLTD_11052026140830_PVRINOXInvestorPresentation11052026.pdf" },
  results: { title: "FY26 audited consolidated filing", date: "11 May 2026", url: "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_156765_11052026210236_iXBRL_WEB.html" },
  call: { title: "Q4 FY26 earnings call", date: "11 May 2026 · filed 18 May", url: "https://nsearchives.nseindia.com/corporate/PVRINOXLTD_18052026133452_PVRINOXEarningsCallTranscript11052026.pdf" },
} as const;
export type SourceKey = keyof typeof sources;
export type Basis = "reported" | "adjusted";
export type FinancialRow = { label: string; reported: readonly [string, string]; adjusted: readonly [string, string] };
// INR millions as printed in presentation slide 31 (PDF page 32), FY25 then FY26.
export const financials: FinancialRow[] = [
  { label: "Total income", reported: ["58708", "68297"], adjusted: ["57918", "67426"] },
  { label: "EBITDA before exceptional items", reported: ["17282", "22789"], adjusted: ["4848", "9680"] },
  { label: "Depreciation & amortisation", reported: ["12774", "12704"], adjusted: ["4826", "4688"] },
  { label: "EBIT", reported: ["4508", "10085"], adjusted: ["22", "4992"] },
  { label: "Finance costs", reported: ["8087", "7328"], adjusted: ["1880", "1507"] },
  { label: "Joint venture loss", reported: ["3", "5"], adjusted: ["3", "5"] },
  { label: "PBT before exceptional items", reported: ["-3582", "2752"], adjusted: ["-1861", "3480"] },
  { label: "Exceptional charge", reported: ["0", "483"], adjusted: ["0", "483"] },
  { label: "Profit before tax", reported: ["-3582", "2269"], adjusted: ["-1861", "2997"] },
  { label: "Tax expense / (credit)", reported: ["-934", "508"], adjusted: ["-501", "691"] },
  { label: "PAT · continuing operations", reported: ["-2648", "1761"], adjusted: ["-1360", "2306"] },
  { label: "PAT · discontinued operations", reported: ["-161", "1567"], adjusted: ["-163", "1562"] },
  { label: "Total PAT", reported: ["-2809", "3328"], adjusted: ["-1523", "3868"] },
];
export const balance = [
  ["Borrowings · excluding leases", "14908", "7586"],
  ["Cash, deposits & investments¹", "5386", "5967"],
  ["Net debt · excluding leases", "9522", "1619"],
  ["Lease liabilities", "62838", "60205"],
  ["Goodwill", "57431", "57367"],
  ["Right-of-use assets", "49923", "46329"],
] as const;
export const operations = [
  ["Screens at period end", "1,723", "1,798"],
  ["Admissions · million", "136.9", "150.1"],
  ["Occupancy", "23.0%", "26.2%"],
  ["Average ticket price · ₹", "259", "280"],
  ["Food & beverage spend / head · ₹", "134", "147"],
] as const;
export function crore(million: string): string { return new Decimal(million).div(10).toFixed(2); }
export function percent(numerator: string, denominator: string): string | null {
  if (new Decimal(denominator).lte(0)) return null;
  return new Decimal(numerator).div(denominator).times(100).toFixed(2);
}
export function growth(current: string, prior: string): string | null {
  if (new Decimal(prior).lte(0)) return null;
  return new Decimal(current).minus(prior).div(prior).times(100).toFixed(2);
}
export const calculations = {
  incomeGrowth: growth("67426", "57918")!,
  adjustedMargin: percent("9680", "67426")!,
  reportedMargin: percent("22789", "68297")!,
  discontinuedShare: percent("1567", "3328")!,
  netDebtReduction: new Decimal("9522").minus("1619").div(10).toFixed(2),
  leaseInclusiveNetDebt: new Decimal("7586").plus("60205").minus("5967").div(10).toFixed(2),
  fcfExDisposal: new Decimal("7901").minus("2221").div(10).toFixed(2),
  currentRatio: new Decimal("111220").div("235200").toFixed(2),
};

export type ScenarioInputs = { growth: string; margin: string; depreciation: string; interest: string; tax: string; multiple: string; netDebt: string };
export const initialScenario: ScenarioInputs = { growth: "0", margin: "14.4", depreciation: "468.8", interest: "150.7", tax: "25", multiple: "8", netDebt: "161.9" };
export type Projection = { year: string; income: string; ebitda: string; ebit: string; pbt: string; tax: string; pat: string };
/** Exploratory amounts only: no fair-value, share-price or buy/sell recommendation.
 * Total income already includes other income: never add it twice. Lease-adjusted
 * EBITDA includes cash rent; pair it with net debt excluding lease liabilities.
 */
export function projectScenario(input: ScenarioInputs): { error: string } | { rows: Projection[]; enterpriseValue: string; equityValue: string } {
  const bounds: Record<keyof ScenarioInputs, [string, string]> = { growth: ["-100", "100"], margin: ["0", "100"], depreciation: ["0", "100000"], interest: ["0", "100000"], tax: ["0", "100"], multiple: ["0", "100"], netDebt: ["-100000", "100000"] };
  for (const key of Object.keys(bounds) as (keyof ScenarioInputs)[]) {
    const raw = input[key];
    if (!/^-?\d+(\.\d+)?$/.test(raw) || raw.length > 20) return { error: "Enter a valid decimal in every assumption field." };
    const value = new Decimal(raw);
    if (value.lt(bounds[key][0]) || value.gt(bounds[key][1])) return { error: `${key}: use a value between ${bounds[key][0]} and ${bounds[key][1]}.` };
  }
  let income = new Decimal("6742.6");
  let finalEbitda = new Decimal(0);
  const rows: Projection[] = [];
  for (const year of ["FY27 scenario", "FY28 scenario", "FY29 scenario"]) {
    income = income.times(new Decimal(1).plus(new Decimal(input.growth).div(100)));
    const ebitda = income.times(input.margin).div(100);
    const ebit = ebitda.minus(input.depreciation);
    const pbt = ebit.minus(input.interest).minus("0.5"); // FY26 JV loss held constant; no exceptional item assumed.
    const tax = pbt.gt(0) ? pbt.times(input.tax).div(100) : new Decimal(0); // no automatic deferred-tax credit.
    rows.push({ year, income: income.toFixed(2), ebitda: ebitda.toFixed(2), ebit: ebit.toFixed(2), pbt: pbt.toFixed(2), tax: tax.toFixed(2), pat: pbt.minus(tax).toFixed(2) });
    finalEbitda = ebitda;
  }
  const enterpriseValue = finalEbitda.times(input.multiple);
  return { rows, enterpriseValue: enterpriseValue.toFixed(2), equityValue: enterpriseValue.minus(input.netDebt).toFixed(2) };
}

export interface Finding { title: string; fact: string; interpretation: string; question: string; source: SourceKey; page?: number; status?: string }
export const forensicFindings: Finding[] = [
  { title: "Profit quality", fact: "FY26 reported PAT: ₹332.80 cr; discontinued operations: ₹156.70 cr.", interpretation: `${calculations.discontinuedShare}% of total reported PAT comes from discontinued operations. A continuing-earnings multiple should use continuing PAT, not the total.`, question: "What is sustainable profit after removing disposal effects?", source: "results", status: "Reconcile" },
  { title: "Lease accounting", fact: "FY26 EBITDA: ₹2,278.90 cr reported; ₹968.00 cr excluding Ind AS 116 effects.", interpretation: "Lease accounting moves rent out of operating expenses and into depreciation and interest. Use a consistent EBITDA and debt definition when comparing companies.", question: "Does the comparison multiple include leases in both numerator and denominator?", source: "presentation", page: 32, status: "Basis matters" },
  { title: "Cash generation", fact: "The company cash bridge includes ₹222.10 cr of disposal proceeds in ₹790.10 cr free cash flow.", interpretation: `Removing that inflow leaves ₹${calculations.fcfExDisposal} cr on the same bridge definition. This is a limited adjustment, not audited recurring free cash flow.`, question: "What maintenance spending and other one-off flows remain?", source: "presentation", page: 27, status: "One-off inflow" },
  { title: "Liquidity", fact: "Reported current assets: ₹1,112.20 cr; current liabilities: ₹2,352.00 cr.", interpretation: `The current ratio is ${calculations.currentRatio}×. Advance ticket collections and lease obligations make the composition important; the ratio alone does not establish distress.`, question: "Which current obligations require cash in the coming year?", source: "results", status: "Review maturity" },
  { title: "Audit scope", fact: "The annual results filing declares an unmodified audit opinion.", interpretation: "That does not establish absence of fraud. The expanded annual-report panel reviews selected notes; full related-party detail and auditor history still require a dedicated review.", question: "Do the annual-report notes reveal related-party or contingent exposures?", source: "results", status: "Coverage gap" },
];
export const callFindings: Finding[] = [
  { title: "Expansion is conditional on site economics", fact: "Management described roughly 120 screens of FY27 opening visibility and 55–60% capital-light additions.", interpretation: "Visibility is a pipeline statement, not completed commissioning. Track openings, closures and developer funding separately.", question: "How many signed screens actually opened, and when?", source: "call", page: 5 },
  { title: "Capital-light does not remove demand risk", fact: "The call explains a mix of company-funded, developer-funded and franchise sites.", interpretation: "Less capital on PVR’s balance sheet can improve its returns while weak catchment economics still hurt the operator and developer. Screen count alone will miss that distinction.", question: "What are mature-site returns and revenue shares by funding model?", source: "call", page: 10 },
  { title: "Cash-positive is an aspiration, not a distribution promise", fact: "Management sought a net-cash position and left use of future accruals to the board.", interpretation: "Do not convert that statement into a dividend forecast. Capital spending, working capital and formal board decisions need their own evidence.", question: "Has the board announced a capital-allocation decision since this call?", source: "call", page: 5 },
];
