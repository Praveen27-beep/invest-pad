"use client";
import { auditCoverage, COMPANY_METHOD_VERSION, reportOutline, researchWorkflow } from "@/lib/company-research-method";
import { annualForensicChecks, commitmentHistory, businessReport, evidenceRequirements, reportSources, reportVersion, researchConflicts } from "@/lib/pvr-company-report";
import s from "./CompanyResearchPack.module.css";

export function ReportCitation({ id, location }: { id: string; location?: string }) {
  const source = reportSources.find(source => source.id === id);
  if (!source) return <span className={s.citation}>Source unavailable</span>;
  const label = `${source.title}${source.eventDate ? ` · ${source.eventDate}` : ""}${location ? ` · ${location}` : ""}`;
  const page = location?.match(/PDF pp?\. (\d+)/)?.[1];
  return source.url ? <a className={s.citation} href={`${source.url}${page ? `#page=${page}` : ""}`} target="_blank" rel="noreferrer">{label} ↗</a> : <span className={s.citation}>{label} · original pending</span>;
}
export function ResearchCoverage() {
  const audit = auditCoverage(reportSources, evidenceRequirements);
  const complete = audit.filter(item => item.complete).length;
  return <details className={s.method}>
    <summary>Evidence audit · {complete} of {audit.length} required source slots reviewed</summary>
    <p>As of {reportVersion.cutoff} · {reportVersion.id} · {reportVersion.status}. A located link or pasted report does not count as reviewed issuer evidence. Four consecutive quarterly calls are required; annual results do not replace the annual report.</p>
    <div className={s.coverage}>{audit.map(item => <div className={s.coverageItem} data-complete={item.complete} key={item.label}><strong>{item.label}</strong><span>{item.complete ? "Reviewed" : "Review gap"} · {item.reason}</span>{item.sources.map(source => <ReportCitation key={source.id} id={source.id}/>)}</div>)}</div>
    <h4>How this research is assembled</h4><ol>{researchWorkflow.map(([title, text]) => <li key={title}><strong>{title}.</strong> {text}</li>)}</ol>
    <p>Method {COMPANY_METHOD_VERSION}. This dated research is an original Invest-pad synthesis. Review its sources and keep the questions that matter to your own thesis.</p>
  </details>;
}
export function BusinessDiagram() {
  return <figure className={s.diagram}><figcaption>One cinema visit, several connected economics</figcaption><div className={s.flow}>
    <div className={s.node}><span>01 / CONTENT & LOCATION</span><strong>Make the visit possible</strong><p>Distributors provide films. Developers provide sites. PVR INOX programmes and operates the cinema.</p></div>
    <div className={s.node}><span>02 / THE CUSTOMER</span><strong>Fill a show, serve a visit</strong><p>Tickets bring the audience. Refreshments add a separate purchase. Advertisers pay to reach the audience.</p></div>
    <div className={s.node}><span>03 / CASH & REINVESTMENT</span><strong>Pay the economic costs</strong><p>Film share, rent, people and upkeep come before repeatable cash. New openings compete with maintenance for capital.</p></div>
  </div><p className={s.diagramFoot}>Invest-pad explanatory model, not a scaled revenue chart. A capital-light contract changes who funds the site and who earns its revenue; it does not remove the need for attendance.</p><ReportCitation id="q426" location="Operating and capital-light discussion"/></figure>;
}
export function LongFormCompanyReport({ onQuestion }: { onQuestion: (text: string) => void }) {
  return <>
    <div className="ip-result-summary"><span>BUSINESS UNDERSTANDING · {reportVersion.id.toUpperCase()}</span><h4>What has to work, from the cinema seat to the balance sheet.</h4><p>An original reading of PVR INOX’s business mechanics. Financial amounts and assumptions live in Financials and Valuation Model. Evidence, interpretation and missing information remain distinct throughout.</p></div>
    <nav className={s.outline} aria-label="Report chapters">{reportOutline.map((item,i) => <a key={item.id} href={`#pvr-report-${item.id}`}>{String(i+1).padStart(2,"0")} {item.title}</a>)}</nav>
    {reportOutline.map((item,i) => {
      const chapter = businessReport.find(chapter => chapter.id === item.id);
      return <article key={item.id} id={`pvr-report-${item.id}`} className={s.chapter}><h4><span>{String(i+1).padStart(2,"0")}</span>{item.title}</h4>
        {chapter?.paragraphs.map((paragraph,index) => <div key={index} className={`${s.paragraph} ${paragraph.label === "Gap" ? s.gap : ""}`}><span className={s.label}>{paragraph.label === "Evidence" ? "Source-backed account" : paragraph.label === "Interpretation" ? "Invest-pad interpretation" : paragraph.label}</span><p>{paragraph.text}</p>{paragraph.citations.map((citation,j) => <ReportCitation key={j} id={citation.source} location={citation.location}/>)}</div>)}
        {item.id === "operations" && <BusinessDiagram/>}
      </article>;
    })}
    <button className="ip-research-question" onClick={() => onQuestion("Business-understanding follow-up: which evidence would show that PVR INOX’s capital-light growth produces repeatable cash after rent, maintenance and partner revenue shares? Review the four-call source audit before accepting the narrative.")}>+ Keep the central research question</button>
  </>;
}
export function ReconciliationReview() {
  return <section><h4>Claims held out of the financial model</h4><p className="ip-result-footnote">Supplied reference research is a set of leads to reconcile, not a replacement for filed evidence.</p>{researchConflicts.map(conflict => <article className={s.review} key={conflict.title}><h4>{conflict.title}</h4><p><strong>Supplied:</strong> {conflict.supplied}</p><p><strong>Assessment:</strong> {conflict.finding}</p><p><strong>Next check:</strong> {conflict.next}</p></article>)}</section>;
}
export function FullSourceRegister() {
  return <details className={s.method}><summary>Full source register, scope and origin</summary>{reportSources.map(source => <div className={s.sources} key={source.id}><h4>{source.title} · {source.status.replaceAll("_", " ")}</h4><p>Period: {source.period} · published: {source.published ?? "not established"}{source.eventDate ? ` · event: ${source.eventDate}` : ""}</p><p>{source.scope}</p><p>Origin: {source.origin}. {source.note}</p><ReportCitation id={source.id}/></div>)}<p>Published research versions are dated artifacts. A later review appends a new interpretation and retains earlier commitments. This pack does not overwrite private facts, notes or thesis history.</p></details>;
}

export function QuarterlyUpdate() {
  return <section className={s.review}><h4>Latest reviewed call · Q1 FY27 · 24 July 2026</h4><p>Management reports 36.6 million guests, ATP ₹273 and food spend per head ₹161. On its Ind AS 116-adjusted basis: revenue ₹1,642 cr, EBITDA ₹230 cr and PAT ₹71 cr. These rounded quarterly figures are separate from the FY26 consolidated baseline and are not live data.</p><ReportCitation id="q127" location="PDF pp. 3–4 / printed pp. 2–3"/></section>;
}
export function ManagementHistory({ onQuestion }: { onQuestion: (text: string) => void }) {
  return <section className={s.register} aria-label="Dated management commitment history"><h4>Promises, revisions and observed outcomes</h4><p>Four calls, read chronologically. Assessments below are Invest-pad interpretations of dated issuer statements.</p>{commitmentHistory.map((event,index) => <article className={s.event} key={`${event.date}-${index}`}><time dateTime={event.date}>{event.date}</time><h4>{event.title}</h4><span className={s.label}>Issuer statement</span><p>{event.fact}</p><ReportCitation id={event.source} location={event.location}/><p><strong>{event.assessment}.</strong> {event.interpretation}</p></article>)}<button className="ip-research-question" onClick={() => onQuestion("Next-call review: compare FY27 openings with the February, May and July guidance. Reconcile net cash on the same basis, preserve each original statement and distinguish revised guidance from final delivery.")}>+ Keep the next-call question</button></section>;
}
export function AnnualForensics({ onQuestion }: { onQuestion: (text: string) => void }) {
  return <section><h4>Annual-report checks · standalone FY26</h4><p>Audit signed 11 May 2026; annual report filed 19 August 2026. S.R. Batliboi & Co. LLP gives an unmodified opinion. That opinion does not remove the need to investigate individual exposures.</p>{annualForensicChecks.map(item => <article className="ip-finding" key={item.title}><h4>{item.title}</h4><div className="ip-finding-fact"><span>STANDALONE · SOURCE AND CALCULATION</span><p>{item.fact}</p><ReportCitation id="annual26" location={item.location}/></div><div className="ip-finding-view"><span>INVEST-PAD INTERPRETATION</span><p>{item.interpretation}</p></div><button className="ip-research-question" onClick={() => onQuestion(`${item.question}\nSource: FY26 annual report, ${item.location}\n${reportSources.find(source => source.id === "annual26")?.url}`)}>+ Keep this question: {item.question}</button></article>)}</section>;
}
