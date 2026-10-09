/** Research coverage is a company capability, not a blanket sector exclusion.
 * Unknown companies keep the core views; specialised trackers require explicit coverage.
 * These local profiles describe Invest-pad's coverage, not InvestorStack's private rules.
 */
export const RESEARCH_SECTIONS = ["Overview", "Financials", "Investment Thesis", "Research Report", "Valuation Summary", "Valuation Model", "Capex Tracker", "Read Between the Lines", "Forensics", "Management Consistency"] as const;
export type ResearchSection = typeof RESEARCH_SECTIONS[number];
const CAPEX_COVERAGE = new Set(["INE191H01014", "PVR INOX", "PVRINOX", "INE021A01026", "Asian Paints", "ASIANPAINT", "INE758T01015", "Eternal", "ETERNAL"]);
export function companySections(identity: { isin?: string; symbol?: string | null; name?: string | null; research_sections?: readonly ResearchSection[] }, coverage: readonly ResearchSection[] | undefined = identity.research_sections): readonly ResearchSection[] {
  if (coverage) return RESEARCH_SECTIONS.filter(section => section === "Overview" || coverage.includes(section));
  const capex = [identity.isin, identity.symbol, identity.name].some(value => value && CAPEX_COVERAGE.has(value));
  return RESEARCH_SECTIONS.filter(section => section !== "Capex Tracker" || capex);
}
