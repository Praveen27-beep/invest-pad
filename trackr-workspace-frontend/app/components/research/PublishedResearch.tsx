"use client";

import { useState } from "react";
import {
  sources, financials, balance, operations, calculations, crore, growth,
  initialScenario, projectScenario, forensicFindings, callFindings,
  type SourceKey, type Basis, type ScenarioInputs, type Finding,
} from "@/lib/pvr-research";

import type { ResearchSection } from "@/lib/company-sections";

function Source({ id, page, children }: { id: SourceKey; page?: number; children?: React.ReactNode }) {
  const source = sources[id];
  return <a className="ip-source-link" href={`${source.url}${page ? `#page=${page}` : ""}`} target="_blank" rel="noreferrer">{children || source.title}{page ? ` · PDF p. ${page}` : ""} ↗</a>;
}
function Table({ caption, headings, rows }: { caption: string; headings: string[]; rows: React.ReactNode[][] }) {
  return <div className="ip-result-table-wrap" tabIndex={0} role="region" aria-label={caption}><table className="ip-result-table"><caption>{caption}</caption><thead><tr>{headings.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{rows.map((row,i) => <tr key={i}>{row.map((cell,j) => j === 0 ? <th scope="row" key={j}>{cell}</th> : <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>;
}
function Insight({ item, onQuestion }: { item: Finding; onQuestion: (text: string) => void }) {
  return <article className="ip-finding"><header><h4>{item.title}</h4>{item.status && <span className="ip-research-status">{item.status}</span>}</header><div className="ip-finding-fact"><span>ISSUER-REPORTED</span><p>{item.fact}</p><Source id={item.source} page={item.page}/></div><div className="ip-finding-view"><span>INVEST-PAD INTERPRETATION</span><p>{item.interpretation}</p></div><button className="ip-research-question" onClick={() => onQuestion(`${item.question}\nSource: ${sources[item.source].url}${item.page ? `#page=${item.page}` : ""}`)}>+ Keep this question: {item.question}</button></article>;
}

/** Read-only public research. Investor-owned notes, facts and thesis history remain separate. */
export function PublishedResearch({ section, onQuestion }: { section: ResearchSection; onQuestion: (text: string) => void }) {
  const [basis, setBasis] = useState<Basis>("adjusted");
  const [statement, setStatement] = useState("Profit & loss");
  const [inputs, setInputs] = useState<ScenarioInputs>(initialScenario);
  const result = projectScenario(inputs);
  const isModel = section === "Valuation Model" || section === "Valuation Summary";
  return <div className="ip-published-research">
    <div className="ip-research-dateline"><span>FILED RESEARCH · PVR INOX</span><span>FY ended 31 Mar 2026</span></div>
    <h3>{section === "Overview" ? "A recovery worth unpacking." : section}</h3>
    <p className="ip-research-scope">Source-backed snapshot · published May 2026 · reviewed 8 Oct 2026. Later quarters and live prices are outside this pack.</p>

    {section === "Overview" && <>
      <div className="ip-research-metrics">
        <div><span>Total income</span><strong>₹6,742.60 cr</strong><small>Lease-adjusted · FY26</small></div>
        <div><span>EBITDA margin</span><strong>{calculations.adjustedMargin}%</strong><small>Calculated · lease-adjusted</small></div>
        <div><span>Net debt</span><strong>₹161.90 cr</strong><small>Company definition · excludes leases</small></div>
      </div>
      <Source id="presentation" page={32}/><Source id="presentation" page={28}/>
      <div className="ip-result-summary"><span>THE RESEARCH QUESTION</span><h4>How much of the recovery can repeat without disposal gains?</h4><p>Higher attendance and spending support the operating recovery. The harder test is whether cash generation remains strong through a weaker film slate, after rent and maintenance spending.</p></div>
      <Table caption="Operating evidence · issuer-reported" headings={["Measure", "FY25", "FY26"]} rows={operations.map(r => [...r])}/>
      <Source id="presentation" page={13}/><p className="ip-result-footnote">Screen counts include managed properties; operating KPIs exclude management properties, as defined in the source.</p>
      <div className="ip-result-summary"><span>ACCOUNTING CHECK</span><p>Reported EBITDA margin is {calculations.reportedMargin}%; lease-adjusted margin is {calculations.adjustedMargin}%. These use different cost treatments. Both appear in Financials with their source definitions.</p></div>
      <button className="ip-research-question" onClick={() => onQuestion("What portion of PVR INOX’s FY26 cash generation is repeatable after rent, maintenance capex and disposal proceeds?")}>+ Add the question to my notes</button>
    </>}

    {section === "Financials" && <>
      <div className="ip-result-controls" aria-label="Statement selection">{["Profit & loss", "Balance sheet", "Cash bridge"].map(s => <button key={s} aria-pressed={statement === s} onClick={() => setStatement(s)}>{s}</button>)}</div>
      {statement === "Profit & loss" && <>
        <label className="ip-result-select">Accounting basis<select aria-label="Accounting basis" value={basis} onChange={e => setBasis(e.target.value as Basis)}><option value="adjusted">Excluding Ind AS 116 effects</option><option value="reported">Reported Ind AS</option></select></label>
        <Table caption="Consolidated · ₹ crore · FY25 restated comparator" headings={["Line item", "FY25", "FY26", "Change"]} rows={financials.map(r => [r.label, crore(r[basis][0]), crore(r[basis][1]), growth(r[basis][1],r[basis][0]) === null ? "Not meaningful¹" : `${growth(r[basis][1],r[basis][0])}%`])}/>
        <p className="ip-result-footnote">¹ Percentage growth is omitted for zero or negative bases. Expenses are shown as positive charges. Total income includes other income. EBITDA is before exceptional items.</p>
        <Source id="presentation" page={32}/>
      </>}
      {statement === "Balance sheet" && <>
        <Table caption="Consolidated balance-sheet extracts · ₹ crore" headings={["Item", "31 Mar 2025", "31 Mar 2026"]} rows={balance.map(r => [r[0],crore(r[1]),crore(r[2])])}/>
        <p className="ip-result-footnote">¹ Company cash definition includes investments, other bank balances and deposits. Adding lease liabilities gives ₹{calculations.leaseInclusiveNetDebt} cr of net obligations on that same cash definition. This is not the lease-excluding net-debt figure.</p>
        <Source id="presentation" page={33}/>
      </>}
      {statement === "Cash bridge" && <>
        <Table caption="Management cash bridge · FY26 · ₹ crore" headings={["Component", "Amount"]} rows={[["Lease-adjusted EBITDA", "968.00"],["Working capital movement", "15.20"],["Net disposal proceeds", "222.10"],["Discontinued operations cash flow", "−15.40"],["Interest paid", "−145.60"],["Capex", "−254.20"],["Company free cash flow", "790.10"],["Less disposal proceeds · analytical adjustment", calculations.fcfExDisposal]]}/>
        <p className="ip-result-footnote">This reproduces management’s bridge before debt/equity changes. It is not a substitute for the statutory cash-flow statement. Interest paid differs from the P&L finance-cost charge.</p><Source id="presentation" page={27}/>
      </>}
    </>}

    {section === "Investment Thesis" && <>
      <div className="ip-result-summary"><span>WORKING HYPOTHESIS · INVEST-PAD ANALYSIS</span><h4>Operating leverage can improve cash generation, if the content cycle and site economics hold.</h4><p>A larger share of developer-funded openings could reduce PVR’s capital needs. That benefit needs to survive lower admissions and the economic cost of partner revenue shares.</p></div>
      <Table caption="Test the argument" headings={["Pillar", "Supporting evidence", "What would weaken it"]} rows={[
        ["Demand recovery", "Admissions: 136.9m → 150.1m", "More screens without stronger attendance per operating screen"],
        ["Monetisation", "ATP: ₹259 → ₹280; SPH: ₹134 → ₹147", "Discounting or an unfavourable film/format mix"],
        ["Capital discipline", "FY26 capex ₹254.2 cr; developer-funded pipeline", "Renovation needs or weaker partner economics offset savings"],
        ["Earnings quality", "Continuing PAT turns positive", "Disposal gains mistaken for recurring earnings"],
      ]}/><Source id="presentation" page={13}/><Source id="presentation" page={23}/>
      <p className="ip-result-footnote">This is an authored hypothesis, not your committed thesis. Keep, challenge or discard it in your own notes.</p>
      <button className="ip-research-question" onClick={() => onQuestion("Thesis challenge: does capital-light expansion improve returns after partner revenue shares, maintenance capex and a weaker content year?")}>+ Challenge this hypothesis in my notes</button>
    </>}

    {section === "Research Report" && <>
      <div className="ip-result-summary"><span>INVEST-PAD RESEARCH · V1 · 8 OCT 2026</span><h4>Read the recovery through three lenses: demand, leases and cash.</h4><p>This report uses the FY26 filing set. It is an original synthesis of the linked issuer documents; forecasts and more recent developments are not included.</p></div>
      <article className="ip-report-prose">
        <h4>01 · The business engine</h4><p>Cinema economics combine admissions, ticket pricing, food spending and advertising with a substantial fixed-cost base. Improved utilisation can lift profit faster than revenue; a weak release slate can reverse that effect. Track the operating drivers alongside the accounting totals.</p>
        <h4>02 · What changed</h4><p>Lease-adjusted total income increased {calculations.incomeGrowth}% and EBITDA margin reached {calculations.adjustedMargin}%. Admissions, ticket pricing and spend per head all increased. That is stronger evidence than looking at headline profit alone.</p><Source id="presentation" page={13}/>
        <h4>03 · What headline earnings conceal</h4><p>The audited filing records ₹176.10 cr of continuing PAT and ₹156.70 cr from discontinued operations. Valuing all ₹332.80 cr as a repeatable stream would hide a material distinction. Lease adjustments create a second, separate bridge; they should never be used interchangeably with disposal adjustments.</p><Source id="results"/>
        <h4>04 · Where the cash went</h4><p>Management reports lower borrowing net of its cash definition. Its free-cash-flow bridge also includes a disposal inflow. The relevant follow-up is whether operating cash after rent, interest and reinvestment can sustain the improvement without further asset sales.</p><Source id="presentation" page={27}/>
        <h4>05 · Competitive position and limits</h4><p>Locations, programming, brand and access to developer capital are plausible advantages. This pack does not establish a peer-adjusted moat score. A useful comparison needs matched cities, comparable formats, lease terms and mature-site economics.</p>
        <h4>06 · What to watch next</h4><p>Track commissioned screens against the pipeline, rent against revenue, admissions against price changes, and the operating cash bridge excluding disposals. Revisit the hypothesis when any of these diverges from management’s explanation.</p>
      </article>
      <button className="ip-research-question" onClick={() => onQuestion("Report follow-up: compare the next quarterly filing with this FY26 baseline on admissions, rent, capex, recurring cash and screen openings.")}>+ Keep the follow-up question</button>
    </>}

    {isModel && <>
      <div className="ip-result-summary"><span>ILLUSTRATIVE SCENARIO · EDITABLE ASSUMPTIONS</span><p>Start from FY26 lease-adjusted total income of ₹6,742.60 cr. The defaults below are an illustration, not management guidance or an InvestorStack forecast. All model amounts are ₹ crore.</p></div>
      <div className="ip-scenario-inputs">{([
        ["growth", "Annual income growth", "%"], ["margin", "EBITDA margin", "%"], ["depreciation", "Annual depreciation", "₹ cr"], ["interest", "Annual finance costs", "₹ cr"], ["tax", "Tax on positive PBT", "%"], ["multiple", "Exit EV / EBITDA", "×"], ["netDebt", "Exit net debt · ex leases", "₹ cr"],
      ] as [keyof ScenarioInputs,string,string][]).map(([key,label,unit]) => <label key={key}>{label}<div><input aria-label={label} inputMode="decimal" value={inputs[key]} onChange={e => setInputs(v => ({...v,[key]:e.target.value}))}/><span>{unit}</span></div></label>)}</div>
      <button className="ip-research-question" onClick={() => setInputs({...initialScenario})}>Reset illustration</button>
      {"error" in result ? <p className="ip-result-error" role="alert">{result.error}</p> : <>
        <Table caption="Conditional projection · no exceptional gain assumed" headings={["₹ crore",...result.rows.map(r => r.year)]} rows={([['Total income','income'],['EBITDA','ebitda'],['EBIT','ebit'],['Profit before tax','pbt'],['Tax expense','tax'],['Continuing PAT','pat']] as const).map(([label,key]) => [label,...result.rows.map(r=>r[key])])}/>
        <div className="ip-research-metrics"><div><span>FY29 enterprise value</span><strong>₹{result.enterpriseValue} cr</strong><small>Conditional on selected multiple</small></div><div><span>Equity bridge</span><strong>₹{result.equityValue} cr</strong><small>Enterprise value − assumed net debt</small></div></div>
        {section === "Valuation Summary" && <Table caption="Multiple sensitivity · same operating assumptions" headings={["Illustrative exit multiple", "Enterprise value · ₹ cr", "Equity bridge · ₹ cr"]} rows={["6","8","10"].map(m => {const scenario = projectScenario({...inputs,multiple:m}); return [m+"×", "error" in scenario ? "—" : scenario.enterpriseValue,"error" in scenario ? "—" : scenario.equityValue];})}/>}
      </>}
      <details className="ip-result-method"><summary>Show formulas and limits</summary><p>Income = prior-year income × (1 + growth / 100). EBITDA = income × margin / 100. EBIT = EBITDA − depreciation. PBT = EBIT − finance costs − ₹0.50 cr JV loss. Tax = positive PBT × tax rate / 100; no tax credit is assumed for losses. PAT = PBT − tax.</p><p>Exit enterprise value = FY29 EBITDA × selected multiple. Equity bridge = enterprise value − assumed exit net debt. Other income is already in total income. Depreciation, finance costs and JV loss are held constant. The model does not forecast working capital, debt paydown, dilution or maintenance capex, and does not discount the exit amount to today. It produces no per-share target.</p><p>Money uses decimal arithmetic; displayed results are rounded to two places. Lease-adjusted EBITDA must be paired with lease-excluding net debt.</p></details><Source id="presentation" page={32}/>
    </>}

    {section === "Capex Tracker" && <>
      <Table caption="FY26 deployment · company disclosures" headings={["Measure", "Result", "Status"]} rows={[["Gross screen openings", "93", "Reported FY26"],["Screen closures", "18", "Reported FY26"],["Net additions", "75", "93 − 18"],["Capex", "₹254.20 cr", "FY26 cash bridge"],["Signed FOCO pipeline", "52 screens", "Signed, not commissioned"],["Signed asset-light pipeline", "86 screens", "Signed, not commissioned"]]}/><Source id="presentation" page={22}/><Source id="presentation" page={23}/>
      <Table caption="FY27 commitment register · baseline at 11 May 2026" headings={["Commitment", "Evidence", "Next verification"]} rows={[["About 120 screens visible", "Management call", "Actual openings and delays"],["55–60% capital-light mix", "Management expectation", "Funding mix of commissioned screens"],["Positive net cash aspiration", "No completion date promised", "Balance sheet and cash bridge"]]}/><Source id="call" page={5}/>
      <p className="ip-result-footnote">No site-level budget or commissioning dates are inferred. Signed pipeline is not counted as operating capacity. Later FY27 updates require a new source review.</p>
    </>}
    {section === "Read Between the Lines" && <><p className="ip-result-intro">Management statements are paraphrased. Interpretations and unanswered questions are kept separate.</p>{callFindings.map(item => <Insight key={item.title} item={item} onQuestion={onQuestion}/>)}</>}
    {section === "Forensics" && <><p className="ip-result-intro">Accounting and disclosure checks from the available filing set. Flags are review prompts, not allegations or a fraud score.</p>{forensicFindings.map(item => <Insight key={item.title} item={item} onQuestion={onQuestion}/>)}</>}
    {section === "Management Consistency" && <>
      <div className="ip-result-summary"><span>BASELINE ESTABLISHED · FOLLOW-UP NOT YET REVIEWED</span><p>One call cannot establish a delivery record. The dated commitments below are ready for comparison with later filings; no delivered/failed verdict has been invented.</p></div>
      <Table caption="Commitment → evidence → outcome" headings={["11 May 2026 statement", "Evidence to compare", "Current assessment"]} rows={[["Roughly 120 screens of FY27 visibility", "FY27 gross openings, closures and timing", "Awaiting later-period review"],["55–60% capital-light additions", "Commissioned screen funding mix", "Awaiting later-period review"],["Move towards positive net cash", "Later net debt on the same cash/lease basis", "Aspiration; no firm deadline"]]}/><Source id="call" page={5}/>
      <h4>Consistency within the FY26 filing set</h4><p>The company’s balance-sheet bridge reconciles borrowings of ₹758.60 cr less cash and related balances of ₹596.70 cr to net debt of ₹161.90 cr. This is internal arithmetic consistency, not independent verification of management’s broader claims.</p><Source id="presentation" page={28}/>
      <button className="ip-research-question" onClick={() => onQuestion("Management follow-up: retrieve the next FY27 call and compare openings, capital-light mix and net debt with the 11 May 2026 commitments. Preserve both dates and definitions.")}>+ Add the next-call question</button>
    </>}

    <details className="ip-result-sources"><summary>Sources, dates & research coverage</summary><p>Security: INE191H01014 · Consolidated. Presentation figures are in ₹ million; this view divides by 10 for ₹ crore. The audited HTML filing is in ₹ lakh; relevant figures divide by 100. Issuer disclosures are not independent corroboration of one another.</p>{Object.entries(sources).map(([id,s]) => <div key={id}><Source id={id as SourceKey}/><small>{s.date}</small></div>)}<p>Coverage ends with the May 2026 filing set. No current market quote, subsequent quarter, related-party review or full auditor-history assessment is claimed. Original analysis: Invest-pad, 8 Oct 2026. This snapshot does not overwrite your research.</p></details>
  </div>;
}
