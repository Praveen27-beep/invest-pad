"use client";

import { useState } from "react";
import Link from "next/link";
import { istToday } from "@/lib/research-api";
import { QuarterlyUpdate } from "./research/CompanyResearchPack";
import { PublishedResearch } from "./research/PublishedResearch";
import { companySections, type ResearchSection } from "@/lib/company-sections";
import { calculations, sources, crore } from "@/lib/pvr-research";
import { CompanySnapshot } from "./research/CompanySnapshot";
const methods: [string, string][] = [
  ["forensic-analysis", "Trace cash conversion, accounting choices and related-party transactions."],
  ["competitive-analysis", "Compare distribution, pricing power and barriers to entry."],
  ["industry-analysis", "Map demand, supply, regulation and the industry cycle."],
  ["pattern-recognition", "Compare periods and test whether a pattern has supporting evidence."],
  ["investment-checklist", "Work through business quality, governance, valuation and risks."],
  ["thesis-validation", "Test each assumption against dated, attributable evidence."],
  ["devils-advocate", "Build the strongest counterargument to your current view."],
  ["capital-allocation", "Examine reinvestment, acquisitions and returns to shareholders."],
];
const outlines: Record<string, string[]> = {
  "Investment Thesis": ["Working hypothesis", "Evidence that supports it", "What would change my mind"],
  "Research Report": ["Business and revenue model", "Industry and competitive position", "Growth drivers", "Risks and open questions", "Bull, base and bear cases"],
  "Valuation Summary": ["Bull case · assumptions to verify", "Base case · assumptions to verify", "Bear case · assumptions to verify"],
  "Valuation Model": ["Cash flow base", "Growth assumptions", "Discount rate", "Terminal value", "Share count and net debt"],
  "Capex Tracker": ["Announced project", "Budget and funding", "Commissioning timeline", "Spend versus commitment", "Expected returns"],
  "Read Between the Lines": ["What management said", "What changed from the previous call", "What was left unanswered", "Evidence to check next"],
  "Forensics": ["Auditor observations", "Profit versus operating cash flow", "Working capital", "Related-party transactions", "Contingent liabilities"],
  "Management Consistency": ["Original commitment and date", "Subsequent updates", "Evidence of delivery", "Unresolved commitments", "Questions for the next call"],
};
const companies = ["PVR INOX", "Asian Paints", "TCS"];
const prompts: Record<string, string> = {
  "PVR INOX": "What drives the economics of a cinema?",
  "Asian Paints": "How durable is the distribution advantage?",
  TCS: "What would change the outlook for IT services?",
};
const notes: Record<string, string> = {
  "PVR INOX": "I want to separate changes in attendance from changes in ticket prices. Before forming a view, I would read the latest annual report and compare operating cash flow with expansion spending.",
  "Asian Paints": "I want to understand whether distribution, brand preference and service create a durable advantage. My next step is to compare management’s claims with the evidence across reporting periods.",
  TCS: "I want to understand the connection between client spending, deal conversion and cash generation. I would look for changes in demand before treating a single quarter as a trend.",
};
type Block = { id: string; kind: "paragraph" | "heading" | "list" | "quote" | "fact"; text: string; source: string };
type Revision = { title: string; blocks: Block[]; date: string };
type DemoNote = { id: string; company: string; title: string; blocks: Block[]; revisions: Revision[] };
type Monitor = { id: number; name: string; prompt: string; scope: string; cadence: string; paused: boolean };
const weeklyPrompt = "Review my Watchlist for the week: biggest movers, news that matters, and any thesis note that's gone stale.";
const blockLabels: Record<Block["kind"], string> = { paragraph: "Paragraph", heading: "Heading", list: "Bullet list", quote: "Quote", fact: "Sourced fact" };
function nextMonday() {
  const today = istToday();
  // UTC midnight belongs to the previous calendar day in India; use noon for weekday.
  const weekday = new Date(`${today}T12:00:00+05:30`).getUTCDay();
  const days = (8 - weekday) % 7;
  const next = new Date(`${today}T08:00:00+05:30`);
  next.setUTCDate(next.getUTCDate() + days);
  if (next.getTime() <= Date.now()) next.setUTCDate(next.getUTCDate() + 7);
  return next.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", month: "short", day: "numeric" });
}

function NoteEditor({ note, onChange, onSave }: { note: DemoNote; onChange: (note: DemoNote) => void; onSave: () => void }) {
  const [history, setHistory] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  function updateBlock(id: string, change: Partial<Block>) {
    onChange({ ...note, blocks: note.blocks.map(block => block.id === id ? { ...block, ...change } : block) });
  }
  function addBlock(kind: Block["kind"]) {
    onChange({ ...note, blocks: [...note.blocks, { id: crypto.randomUUID(), kind, text: "", source: "" }] });
    setMenu(null);
  }
  const saved = note.revisions.at(-1);
  const dirty = !saved || saved.title !== note.title || JSON.stringify(saved.blocks) !== JSON.stringify(note.blocks);
  return <article className="ip-notion" aria-label={`${note.title || "Untitled"} note editor`}>
    <div className="ip-note-breadcrumb">{note.company} / Notes <span>{dirty ? "Unsaved draft" : "Revision saved"} · {istToday()}</span></div>
    <input className="ip-note-title" aria-label="Note title" placeholder="Untitled" value={note.title} onChange={event => onChange({ ...note, title: event.target.value })}/>
    <div className="ip-note-meta">Your interpretation <span>Preview · kept until this page reloads</span></div>
    <div className="ip-note-blocks">{note.blocks.map((block, index) => <div className="ip-note-block" data-kind={block.kind} key={block.id}>
      <select aria-label={`Block ${index + 1} type`} value={block.kind} onChange={event => updateBlock(block.id, { kind: event.target.value as Block["kind"] })}>{Object.entries(blockLabels).map(([kind, label]) => <option value={kind} key={kind}>{label}</option>)}</select>
      {block.kind === "fact" && <label className="ip-note-source">Source & publication date<input aria-label={`Block ${index + 1} source`} placeholder="Document URL · publication date · page" value={block.source} onChange={event => updateBlock(block.id, { source: event.target.value })}/></label>}
      <textarea aria-label={`Note block ${index + 1}`} placeholder={block.kind === "heading" ? "Heading" : "Write your thinking, or type / for a new block…"} rows={Math.max(2, Math.min(14, Math.ceil(block.text.length / 65) + block.text.split("\n").length))} value={block.text} onChange={event => updateBlock(block.id, { text: event.target.value })} onKeyDown={event => { if (event.key === "/" && !block.text) { event.preventDefault(); setMenu(block.id); } if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); if (dirty && note.title.trim() && !note.blocks.some(b => b.kind === "fact" && b.text.trim() && !b.source.trim())) onSave(); } }}/>
    </div>)}</div>
    <button className="ip-note-add" onClick={() => setMenu(menu ? null : "new")} aria-expanded={Boolean(menu)}>+ Add a block</button>
    {menu && <div className="ip-note-block-menu" role="group" aria-label="Add a writing block">{Object.entries(blockLabels).map(([kind, label]) => <button key={kind} onClick={() => addBlock(kind as Block["kind"])}>{label}</button>)}</div>}
    <div className="ip-note-save"><button disabled={!dirty || !note.title.trim() || note.blocks.some(b => b.kind === "fact" && b.text.trim() && !b.source.trim())} onClick={onSave}>Save revision</button><button aria-expanded={history} onClick={() => setHistory(!history)}>History ({note.revisions.length})</button></div>
    {note.blocks.some(b => b.kind === "fact" && b.text.trim() && !b.source.trim()) && <p role="status">Add a source and publication date before saving a fact.</p>}
    {history && <section className="ip-note-history" aria-label="Note revision history"><h4>Earlier thinking stays intact.</h4>{note.revisions.length ? [...note.revisions].reverse().map((revision, index) => <details key={note.revisions.length - index}><summary>Revision {note.revisions.length - index} · {revision.date} · {revision.title}</summary>{revision.blocks.map(block => <div key={block.id}><span>{blockLabels[block.kind]}</span><p>{block.text}</p>{block.source && <small>{block.source}</small>}</div>)}</details>) : <p>No saved revisions yet.</p>}</section>}
  </article>;
}

export function WorkspaceDemo() {
  const [search, setSearch] = useState("");
  const [enabled, setEnabled] = useState<string[]>(["forensic-analysis", "thesis-validation"]);
  const [monitorForm, setMonitorForm] = useState(false);
  const [monitors, setMonitors] = useState<Monitor[]>([
    { id: 1, name: "weekly-portfolio-review", prompt: weeklyPrompt, scope: "Watchlist", cadence: "Every week on Mon", paused: false },
    { id: 2, name: "weekly-holdings-review", prompt: "Review my portfolio for concentration, important company updates, and investment notes that need another look.", scope: "Portfolio", cadence: "Every week on Mon", paused: false },
  ]);
  const [annotations, setAnnotations] = useState<Record<string, string>>({});
  const [company, setCompany] = useState("PVR INOX");
  const [tabs, setTabs] = useState<string[]>(["PVR INOX"]);
  const [view, setView] = useState("Overview");
  const [folder, setFolder] = useState(true);
  const [watchFolder, setWatchFolder] = useState(false);
  const [ideasFolder, setIdeasFolder] = useState(false);
  const [watchlist, setWatchlist] = useState<string[]>(["PVR INOX", "TCS"]);
  const [ideaTitle, setIdeaTitle] = useState("");
  const [ideas, setIdeas] = useState<{ id: string; title: string; text: string }[]>([]);
  const [activeIdea, setActiveIdea] = useState("");
  const [documents, setDocuments] = useState<DemoNote[]>(() => companies.map(name => ({ id: name, company: name, title: "Investment notes", blocks: [{ id: `${name}-opening`, kind: "paragraph", text: notes[name] || "", source: "" }], revisions: [] })));
  const [noteId, setNoteId] = useState("PVR INOX");
  const [connectionDetails, setConnectionDetails] = useState(false);
  const [input, setInput] = useState("");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState(true);
  const sections = companySections({ name: company });
  const activeNote = documents.find(note => note.id === noteId && note.company === company);
  function open(name: string) { setCompany(name); setTabs(current => current.includes(name) ? current : [...current, name]); setView("Overview"); setQuestion(""); }
  function openNotes(name = company) { setCompany(name); setNoteId(documents.find(note => note.company === name)?.id || ""); setView("Notes"); }
  function newNote(name: string, title = "Untitled") { const id = crypto.randomUUID(); setDocuments(current => [...current, { id, company: name, title, blocks: [{ id: crypto.randomUUID(), kind: "paragraph", text: "", source: "" }], revisions: [] }]); setCompany(name); setNoteId(id); setView("Notes"); }
  function updateNote(note: DemoNote) { setDocuments(current => current.map(item => item.id === note.id ? note : item)); }
  function saveNote() { if (!activeNote) return; updateNote({ ...activeNote, revisions: [...activeNote.revisions, { title: activeNote.title, blocks: activeNote.blocks.map(block => ({ ...block })), date: new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) + " IST" }] }); }
  function keepQuestion(text: string) {
    const note = documents.find(item => item.company === company);
    if (note) { updateNote({ ...note, blocks: [...note.blocks, { id: crypto.randomUUID(), kind: "paragraph", text: `Research question · ${istToday()}\n${text}`, source: "" }] }); setNoteId(note.id); setView("Notes"); }
  }
  function close(name: string) { const next = tabs.filter(tab => tab !== name); setTabs(next); if (company === name) { setCompany(next[0] || ""); setView("Overview"); setQuestion(""); } }

  return <section className="ip-demo-backdrop" aria-label="Interactive workspace demo">
    <div className="ip-demo-window" data-chat={chat}>
      <aside className="ip-demo-rail">
        <div className="ip-demo-dots" aria-hidden="true"><i/><i/><i/></div><div className="ip-wordmark"><span className="ip-mark" aria-hidden="true"/>Invest-pad</div>
        <div className="ip-demo-nav">{["Portfolio", "Skills", "Monitors", "MCPs"].map(value => <button key={value} onClick={() => setView(value)} aria-pressed={view === value}>{value}</button>)}</div>
        <div className="ip-tree-heading">EXPLORER</div>
        <button className="ip-demo-folder" aria-expanded={folder} onClick={() => setFolder(!folder)}>{folder ? "⌄" : "›"} Companies</button>
        {folder && companies.map(name => <div key={name}><button className="ip-demo-company" data-active={company === name} onClick={() => open(name)}>{company === name ? "⌄" : "›"} {name}</button>{company === name && <div className="ip-demo-company-notes">{documents.filter(note => note.company === name).map(note => <button key={note.id} className="ip-demo-note" aria-pressed={view === "Notes" && noteId === note.id} onClick={() => { setNoteId(note.id); setView("Notes"); }}>{note.title || "Untitled"}</button>)}<button className="ip-demo-note ip-note-add" onClick={() => newNote(name)}>+ New note</button></div>}</div>)}
        <button className="ip-demo-folder" aria-expanded={watchFolder} onClick={() => { setWatchFolder(!watchFolder); setView("Watchlist"); }}>{watchFolder ? "⌄" : "›"} Watchlist</button>
        {watchFolder && watchlist.map(name => <button className="ip-demo-company" key={name} onClick={() => open(name)}>{name}</button>)}
        <button className="ip-demo-folder" aria-expanded={ideasFolder} onClick={() => { setIdeasFolder(!ideasFolder); setView("Ideas"); }}>{ideasFolder ? "⌄" : "›"} Ideas</button>
        {ideasFolder && ideas.map(idea => <button className="ip-demo-note" key={idea.id} onClick={() => { setActiveIdea(idea.id); setView("Ideas"); }}>{idea.title}</button>)}
        <div className="ip-demo-user">Your workspace</div>
      </aside>
      <div className="ip-demo-center">
        <div className="ip-demo-docs">{tabs.map(name => <div key={name} data-active={company === name}><button onClick={() => open(name)}>{name}</button><button aria-label={`Close preview ${name}`} onClick={() => close(name)}>×</button></div>)}{!chat && <button className="ip-demo-show-chat" onClick={() => setChat(true)}>Chat</button>}</div>
        <div className="ip-demo-content">
          {view === "Skills" ? <>
            <div className="ip-demo-kicker">REUSABLE RESEARCH METHODS</div><h3>Skills</h3><p>Give your research a repeatable process. Choose the methods you want beside your writing.</p>
            <input className="ip-research-search" aria-label="Search skills" placeholder="Search skills…" value={search} onChange={event => setSearch(event.target.value)}/>
            <div className="ip-method-list">{methods.filter(method => method.join(" ").toLowerCase().includes(search.toLowerCase())).map(([name, description]) => <div className="ip-method" key={name}><div><strong>{name}</strong><p>{description}</p><button onClick={() => { setInput(`Use ${name} to research ${company || "a company"}. Start with the evidence needed.`); setChat(true); }}>Use in chat ↗</button></div><button role="switch" aria-label={`Enable ${name}`} aria-checked={enabled.includes(name)} onClick={() => setEnabled(current => current.includes(name) ? current.filter(item => item !== name) : [...current, name])} className="ip-method-switch"><span/></button></div>)}{!methods.some(method => method.join(" ").toLowerCase().includes(search.toLowerCase())) && <p>No matching skills.</p>}</div><small>Demo preferences last while this page is open. No analysis runs automatically.</small>
          </> : view === "Monitors" ? <>
            <div className="ip-demo-kicker">RETURN TO THE IMPORTANT QUESTIONS</div><h3>Monitors</h3><p>A recurring review of your watchlist, portfolio or a company. Keep the question beside its schedule.</p>
            <button className="ip-monitor-new" onClick={() => setMonitorForm(!monitorForm)} aria-expanded={monitorForm}>+ New monitor</button>
            {monitorForm && <form className="ip-monitor-form" onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); setMonitors(current => [...current, { id: Date.now(), name: String(data.get("name")), prompt: String(data.get("prompt")), scope: String(data.get("scope")), cadence: String(data.get("cadence")), paused: false }]); setMonitorForm(false); }}>
              <label>Name<input name="name" required placeholder="weekly-watchlist-review"/></label><label>Research question<textarea name="prompt" required defaultValue={weeklyPrompt}/></label>
              <label>Review scope<select name="scope"><option>Watchlist</option><option>Portfolio</option>{companies.map(name => <option key={name}>{name}</option>)}</select></label>
              <label>Schedule<select name="cadence"><option>Every week on Mon</option><option>Every month on the 1st</option></select></label><button type="submit">Save preview monitor</button>
            </form>}
            {monitors.map(monitor => <article className="ip-monitor-row" key={monitor.id}><h4>{monitor.prompt}</h4><p><code>{monitor.name}</code></p><p>{monitor.cadence} · {monitor.paused ? "paused" : monitor.cadence === "Every week on Mon" ? `next ${nextMonday()}, 8:00 AM IST` : "8:00 AM IST, first day of next month"}</p><div><span>{monitor.scope} · Preview, not scheduled</span><button onClick={() => setMonitors(current => current.map(item => item.id === monitor.id ? { ...item, paused: !item.paused } : item))}>{monitor.paused ? "Resume" : "Pause"}</button><button aria-label={`Delete monitor ${monitor.name}`} onClick={() => setMonitors(current => current.filter(item => item.id !== monitor.id))}>Delete</button></div></article>)}
            {!monitors.length && <div className="ip-demo-empty">No monitors. Add a question to revisit.</div>}<small>Preview schedules only. Background runs and notifications are not connected.</small>
          </> : view === "MCPs" ? <>
            <div className="ip-demo-kicker">YOUR RESEARCH CONNECTIONS</div><h3>MCPs</h3><p>Bring company filings into your research. Your sources stay beside the writing they support.</p>
            <article className="ip-connection-row"><div><strong>Zip Filings</strong><p>Annual reports, exchange filings and earnings-call transcripts for Indian companies.</p><span className="ip-stock-status">Not connected</span></div><button onClick={() => setConnectionDetails(!connectionDetails)} aria-expanded={connectionDetails}>Set up</button></article>
            {connectionDetails && <div className="ip-research-notice"><h4>Connect Zip Filings</h4><p>The extension or service connection still needs to be configured for this workspace. This preview cannot retrieve filings.</p><p>Once connected, use <strong>Get filings</strong> from a company or research chat.</p><button onClick={() => { setChat(true); setInput(`Get filings for ${company || "a company"}. Include publication dates and sources.`); }}>Prepare a filings request →</button></div>}
          </> : view === "Watchlist" ? <>
            <div className="ip-demo-kicker">EXPLORER / WATCHLIST</div><h3>Companies to revisit.</h3><p>Keep your coverage close. Your notes follow the company.</p>
            <div className="ip-watchlist">{companies.map(name => <div key={name}><button onClick={() => open(name)}>{name} →</button><button aria-pressed={watchlist.includes(name)} onClick={() => setWatchlist(current => current.includes(name) ? current.filter(item => item !== name) : [...current, name])}>{watchlist.includes(name) ? "Remove from watchlist" : "Add to watchlist"}</button></div>)}</div><small>Preview watchlist · kept until this page reloads.</small>
          </> : view === "Ideas" ? <>
            <div className="ip-demo-kicker">EXPLORER / IDEAS</div><h3>A place for the next question.</h3><form className="ip-idea-form" onSubmit={event => { event.preventDefault(); if (!ideaTitle.trim()) return; const id = crypto.randomUUID(); setIdeas(current => [...current, { id, title: ideaTitle.trim(), text: "" }]); setActiveIdea(id); setIdeaTitle(""); setIdeasFolder(true); }}><input aria-label="New idea title" placeholder="A theme, a question, a business to explore…" required value={ideaTitle} onChange={event => setIdeaTitle(event.target.value)}/><button>Add idea</button></form>
            {ideas.map(idea => <details className="ip-idea-document" key={idea.id} open={activeIdea === idea.id}><summary onClick={() => setActiveIdea(idea.id)}>{idea.title}</summary><textarea aria-label={`${idea.title} idea`} placeholder="Write before you have a conclusion…" value={idea.text} onChange={event => setIdeas(current => current.map(item => item.id === idea.id ? { ...item, text: event.target.value } : item))}/></details>)}{!ideas.length && <p>No ideas yet. Start with something you want to understand.</p>}<small>Preview ideas · kept until this page reloads.</small>
          </> : view === "Portfolio" ? <>
            <div className="ip-demo-kicker">PORTFOLIO</div><h3>Your holdings, in context.</h3><p>Connect your existing Trackr+ portfolio after signing in. Your holdings and research share one workspace.</p><div className="ip-demo-empty">No portfolio is connected in this public demo.</div><Link className="ip-button" href="/login">Open your portfolio →</Link>
          </> : !company ? <div className="ip-demo-empty"><h3>A place to explore.</h3><p>Choose a company in Explorer to open its workspace.</p></div> : view === "Notes" ? <>
            {activeNote ? <NoteEditor key={activeNote.id} note={activeNote} onChange={updateNote} onSave={saveNote}/> : <button onClick={() => newNote(company)}>Create a note</button>}
          </> : <>
            <header className="ip-demo-company-head"><span className="ip-demo-monogram">{company[0]}</span><div><h3>{company}</h3><span>India · Company research</span></div><button className="ip-company-watch" aria-pressed={watchlist.includes(company)} onClick={() => setWatchlist(current => current.includes(company) ? current.filter(item => item !== company) : [...current, company])}>{watchlist.includes(company) ? "Following" : "+ Watchlist"}</button></header>
            <label className="ip-mobile-company-section">Company section<select aria-label="Company section" value={view} onChange={event => setView(event.target.value)}>{sections.map(section => <option key={section}>{section}</option>)}</select></label>
            <div className="ip-demo-sections" role="tablist" aria-label="Demo company sections">{sections.map(section => <button role="tab" tabIndex={view === section ? 0 : -1} aria-selected={view === section} key={section} onClick={() => setView(section)} onKeyDown={event => { const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0; if (direction || event.key === "Home" || event.key === "End") { event.preventDefault(); const index = event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1 : (sections.indexOf(section) + direction + sections.length) % sections.length; setView(sections[index] || "Overview"); (event.currentTarget.parentElement?.children[index] as HTMLButtonElement)?.focus(); } }}>{section}</button>)}</div>
            {view === "Overview" ? <>
              <CompanySnapshot name={company} symbol={{ "PVR INOX": "PVRINOX", "Asian Paints": "ASIANPAINT", TCS: "TCS" }[company]} statistics={company === "PVR INOX" ? [{ label: "Total income", value: `₹${crore("67426")} cr`, basis: "FY26 · lease-adjusted" }, { label: "EBITDA margin", value: `${calculations.adjustedMargin}%`, basis: "FY26 · lease-adjusted" }, { label: "Net debt", value: `₹${crore("1619")} cr`, basis: "31 Mar 2026 · excludes leases" }] : []} onResearch={() => { setChat(true); setInput(prompts[company] || "What should I research?"); }}/>
              {company === "PVR INOX" && <p className="ip-stock-source">Annual snapshot · published 11 May 2026 · <a href={sources.presentation.url} target="_blank" rel="noreferrer">Issuer presentation ↗</a>. These are filed figures, not live market data.</p>}
              {company === "PVR INOX" && <QuarterlyUpdate/>}
              <div className="ip-demo-writing"><span className="ip-demo-kicker">THE RESEARCH QUESTION</span><h3>{prompts[company]}</h3><button onClick={() => openNotes()}>Open investment notes →</button></div>
              {!sections.includes("Capex Tracker") && <small>No dedicated capex research pack is available for this company. Reinvestment questions can be recorded in Financials and your notes.</small>}
            </> : company === "PVR INOX" && sections.includes(view as ResearchSection) ? <PublishedResearch section={view as ResearchSection} onQuestion={keepQuestion}/> : view === "Financials" ? <div className="ip-demo-writing"><h3>The numbers, with their sources.</h3><p>Financial statements belong here once a source is connected.</p>{["Income statement", "Balance sheet", "Cash flow"].map(title => <div className="ip-demo-data-row" key={title}><span>{title}</span><span>Not connected</span></div>)}<small>No live or invented financial values.</small></div> : outlines[view] ? <div className="ip-research-document"><div className="ip-demo-kicker">{company} · RESEARCH TEMPLATE · NO CONNECTED DATA</div><h3>{view}</h3><p>{prompts[company]}</p>{view === "Forensics" && <div className="ip-research-notice">Not assessed. These are checks to perform, not findings about {company}.</div>}{outlines[view].map((heading, index) => <details key={`${company}-${view}-${heading}`} open={index === 0}><summary>{heading}<span>Source needed</span></summary><div className="ip-research-evidence"><strong>FACTS & SOURCES</strong><p>No source attached. Record the document, period and publication date.</p></div><label className="ip-research-interpretation">YOUR INTERPRETATION<textarea aria-label={`${company} ${heading}`} placeholder="Write a question, assumption or interpretation…" value={annotations[`${company}-${view}-${heading}`] || ""} onChange={event => setAnnotations(current => ({ ...current, [`${company}-${view}-${heading}`]: event.target.value }))}/></label></details>)}<small>Editable template · changes remain in this preview only.</small></div> : null}
          </>}
        </div>
      </div>
      {chat && <aside className="ip-demo-chat" aria-label="Demo AI chat"><header><span>Research chat</span><button aria-label="Close preview chat" onClick={() => setChat(false)}>×</button></header><div className="ip-demo-chat-body"><span className="ip-demo-kicker">SCRIPTED DEMO · NO MODEL CALL</span><div className="ip-demo-chat-human">{question || `Help me think through ${company || "a company"}.`}</div><div className="ip-demo-chat-answer"><p>{question ? "Your connected model would answer using selected sources. This preview does not generate research claims or retrieve filings." : "Start with the question you want to answer. Then bring in the evidence that could change your view."}</p><p>Facts stay separate from interpretation. AI proposes changes for your review; your writing is never silently replaced.</p><button onClick={() => openNotes()}>Open investment notes</button></div></div><form className="ip-demo-composer" onSubmit={event => { event.preventDefault(); if (input.trim()) { setQuestion(input.trim()); setInput(""); } }}><textarea rows={2} aria-label="Demo chat message" placeholder="Try asking a question…" value={input} onChange={event => setInput(event.target.value)}/><div><span>Demo assistant</span><button aria-label="Send demo message" disabled={!input.trim()}>↑</button></div></form></aside>}
    </div><div className="ip-demo-caption"><span>Interactive preview · explore companies, notes, watchlist, ideas and monitors.</span><Link href="/login">Open your workspace →</Link></div>
  </section>;
}
