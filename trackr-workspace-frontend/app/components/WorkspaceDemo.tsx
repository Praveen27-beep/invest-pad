"use client";

import { useState } from "react";
import Link from "next/link";

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
export function WorkspaceDemo() {
  const [company, setCompany] = useState("PVR INOX");
  const [tabs, setTabs] = useState<string[]>(["PVR INOX"]);
  const [view, setView] = useState("Overview");
  const [folder, setFolder] = useState(true);
  const [drafts, setDrafts] = useState(notes);
  const [input, setInput] = useState("");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState(true);
  function open(name: string) { setCompany(name); setTabs(t => t.includes(name) ? t : [...t, name]); setView("Overview"); setQuestion(""); }
  function close(name: string) { const next = tabs.filter(t => t !== name); setTabs(next); if(company === name) { setCompany(next[0] ?? ""); setQuestion(""); } }
  return <section className="ip-demo-backdrop" aria-label="Interactive workspace demo">
    <div className="ip-demo-window" data-chat={chat}>
      <aside className="ip-demo-rail"><div className="ip-demo-dots" aria-hidden="true"><i/><i/><i/></div><div className="ip-wordmark">Invest-pad</div><div className="ip-demo-nav">{["Portfolio", "Skills"].map(v => <button key={v} onClick={() => setView(v)} aria-pressed={view === v}><span>{v === "Portfolio" ? "◷" : "◇"}</span>{v}</button>)}</div><div className="ip-tree-heading">EXPLORER</div><button className="ip-demo-folder" aria-expanded={folder} onClick={() => setFolder(!folder)}>{folder ? "⌄" : "›"} ▱ Companies</button>{folder && companies.map(c => <div key={c}><button className="ip-demo-company" data-active={company === c} onClick={() => open(c)}>⌄ <span>▥</span> {c}</button>{company === c && <button className="ip-demo-note" onClick={() => setView("Notes")}>▤ Investment notes</button>}</div>)}<div className="ip-demo-user"><span>Y</span> Your workspace</div></aside>
      <div className="ip-demo-center"><div className="ip-demo-docs">{tabs.map(c => <div key={c} data-active={company === c}><button onClick={() => { setCompany(c); setView("Overview"); setQuestion(""); }}>▥ {c}</button><button aria-label={`Close preview ${c}`} onClick={() => close(c)}>×</button></div>)}{!chat && <button className="ip-demo-show-chat" onClick={() => setChat(true)}>✧ Chat</button>}</div>
        <div className="ip-demo-content">
          {view === "Skills" ? <><div className="ip-demo-kicker">YOUR PROCESS</div><h3>A method for every question.</h3><p>Choose a way to explore the company.</p>{["Understand the business", "Challenge a thesis", "Read the financials", "Review the evidence"].map(s => <button className="ip-demo-skill" key={s} onClick={() => { setInput(s); setChat(true); }}>{s}<span>↗</span></button>)}</> : view === "Portfolio" ? <><div className="ip-demo-kicker">PORTFOLIO</div><h3>Your holdings, in context.</h3><p>Connect your existing Trackr+ portfolio after signing in. Your holdings and research share one workspace.</p><div className="ip-demo-empty">No portfolio is connected in this public demo.</div><Link className="ip-button" href="/login">Open your portfolio →</Link></> : !company ? <div className="ip-demo-empty"><h3>A place to explore.</h3><p>Choose a company in Explorer to open its workspace.</p></div> : <>
            <header className="ip-demo-company-head"><span className="ip-demo-monogram">{company[0]}</span><div><h3>{company}</h3><span>India · Company research</span></div></header>
            <div className="ip-demo-sections" role="tablist" aria-label="Demo company sections">{["Overview", "Financials", "Notes", "Sources"].map(v => <button role="tab" aria-selected={view === v} key={v} onClick={() => setView(v)}>{v}</button>)}</div>
            {view === "Overview" ? <><div className="ip-demo-overview"><div className="ip-demo-question-card"><span>START WITH A QUESTION</span><h3>{prompts[company]}</h3><button onClick={() => { setChat(true); setInput(prompts[company] ?? "What should I research?"); }}>Explore with AI ↗</button></div><dl><dt>Company</dt><dd>{company}</dd><dt>Market</dt><dd>India</dd><dt>Research</dt><dd>Personal workspace</dd><dt>Market data</dt><dd>Not connected</dd></dl></div><div className="ip-demo-writing"><span className="ip-demo-kicker">YOUR THINKING</span><h3>The work behind the decision.</h3><p>{drafts[company]}</p><button onClick={() => setView("Notes")}>Open investment notes →</button></div></> : view === "Notes" ? <div className="ip-demo-writing"><div className="ip-demo-kicker">EXAMPLE NOTE · EDITABLE PREVIEW</div><h3>Investment notes</h3><textarea aria-label="Preview investment notes" value={drafts[company]} onChange={e => setDrafts({...drafts, [company]:e.target.value})} /><small>Try editing. Demo changes last only while this page is open.</small></div> : view === "Financials" ? <div className="ip-demo-writing"><h3>The numbers, with their sources.</h3><p>Financial statements belong here once a source is connected.</p>{["Income statement", "Balance sheet", "Cash flow"].map(t => <div className="ip-demo-data-row" key={t}><span>{t}</span><span>Not connected</span></div>)}<small>This demo contains no live or invented financial values.</small></div> : <div className="ip-demo-writing"><h3>Keep the evidence close.</h3><p>Annual reports, filings and your observations sit beside the questions they help answer.</p><div className="ip-demo-empty">No source documents are connected in this preview.</div><button onClick={() => { setInput("What sources should I read first?"); setChat(true); }}>Plan my reading ↗</button></div>}
          </>}
        </div>
      </div>
      {chat && <aside className="ip-demo-chat" aria-label="Demo AI chat"><header><span>✧ Research chat</span><button aria-label="Close preview chat" onClick={() => setChat(false)}>×</button></header><div className="ip-demo-chat-body"><span className="ip-demo-kicker">SCRIPTED DEMO · NO MODEL CALL</span><div className="ip-demo-chat-human">{question || `Help me think through ${company || "a company"}.`}</div><div className="ip-demo-chat-answer"><span>✧</span><p>{question ? "In the full workspace, your connected model answers using the sources you select. This demo shows the conversation flow, without generating research claims." : "Start with the question you want to answer. Then bring in the evidence that could change your view."}</p><p>Keep three things beside your research:</p><ol><li>What the source actually says.</li><li>What you think it means.</li><li>What you still need to check.</li></ol><button onClick={() => setView("Notes")}>▤ Open investment notes</button></div></div><form className="ip-demo-composer" onSubmit={e => {e.preventDefault(); if(input.trim()) { setQuestion(input.trim()); setInput(""); }}}><textarea rows={2} aria-label="Demo chat message" placeholder="Try asking a question…" value={input} onChange={e => setInput(e.target.value)} /><div><span>Demo assistant</span><button aria-label="Send demo message" disabled={!input.trim()}>↑</button></div></form></aside>}
    </div><div className="ip-demo-caption"><span>Try it: open a company, edit a note, explore the chat.</span><Link href="/login">Open your workspace →</Link></div>
  </section>;
}
