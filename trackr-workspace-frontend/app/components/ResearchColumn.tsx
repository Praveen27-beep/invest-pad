"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth, useFetch } from "@trackr/core";
import { useWorkspaceNav } from "@/lib/workspace-context";
import { paths, type CompanyListItem, type CompanyView, type Note, type Page } from "@/lib/research-api";
import { useResearchAuth } from "@/lib/research-hooks";
import { ResearchChat } from "./research/ResearchChat";
import { ButlerPanel } from "./butler/ButlerPanel";

export function ResearchColumn() {
  const { user, investorId } = useAuth();
  return <ScopedColumn key={`${user?.id}:${investorId}`} />;
}
function ScopedColumn() {
  const { closeResearchChat, researchChatFits } = useWorkspaceNav();
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if(researchChatFits) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLButtonElement>(".ws-research-close")?.focus();
    return () => { if(previous?.isConnected) previous.focus(); };
  }, [researchChatFits]);
  const { investorId, token } = useResearchAuth();
  const pathname = usePathname();
  const routeIsin = pathname.match(/^\/research\/companies\/([^/]+)/)?.[1];
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<"chat" | "activity">("chat");
  const noteId = pathname.match(/^\/research\/notes\/([^/]+)/)?.[1];
  const note = useFetch<Note>(investorId && noteId ? paths.note(investorId, decodeURIComponent(noteId)) : null, undefined, token);
  const isin = routeIsin ? decodeURIComponent(routeIsin) : noteId ? note.data?.isin ?? "" : selected;
  const companies = useFetch<Page<CompanyListItem>>(investorId ? paths.companies(investorId) : null, { limit: 100 }, token);
  const company = useFetch<CompanyView>(investorId && isin ? paths.company(investorId, isin) : null, undefined, token);
  return <aside ref={panel} className="ws-research-column" aria-label="AI research chat" role={researchChatFits ? undefined : "dialog"} aria-modal={researchChatFits ? undefined : true} onKeyDown={e => {
    if(e.key === "Escape") { e.preventDefault(); closeResearchChat(); }
    if(e.key === "Tab" && !researchChatFits) {
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], select:not(:disabled), textarea:not(:disabled), input:not(:disabled), summary') ?? []).filter(el => el.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if(e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if(!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    }
  }}>
    <header className="ws-research-head"><div className="ip-chat-modes"><button aria-pressed={mode === "chat"} onClick={() => setMode("chat")}>✧ Chat</button><button aria-pressed={mode === "activity"} onClick={() => setMode("activity")}>Activity</button></div><button className="ws-research-close" aria-label="Close research chat" onClick={closeResearchChat}>×</button></header>
    {mode === "activity" ? <div className="ws-research-log"><ButlerPanel /></div> : <>
      <div className="ip-chat-context">{routeIsin || noteId ? <span>▥ {company.data?.identity.symbol ?? company.data?.identity.name ?? isin}</span> : <select aria-label="Chat company" value={selected} onChange={e => setSelected(e.target.value)}><option value="">Choose a company…</option>{companies.data?.items.map(c => <option key={c.isin} value={c.isin}>{c.symbol ?? c.name ?? c.isin}</option>)}</select>}<Link onClick={() => { if(!researchChatFits) closeResearchChat(); }} href="/agents" title="Configure your model">Model settings</Link></div>
      {!isin ? <div className="ip-chat-welcome"><span>✧</span><h2>Your research partner</h2><p>Choose a company to explore a question with your notes and sources beside you.</p><Link className="ws-btn" onClick={() => { if(!researchChatFits) closeResearchChat(); }} href="/explorer?add=1">Find a company →</Link>{companies.error && <p role="alert">Companies could not be loaded. <button onClick={companies.refetch}>Retry</button></p>}</div> : company.loading ? <p className="ws-empty" role="status">Opening company…</p> : company.error ? <div className="ws-notice" role="alert">Could not open this company. <button onClick={company.refetch}>Try again</button></div> : company.data?.state === "RITUAL_REQUIRED" ? <div className="ip-chat-welcome"><h2>Start with your question</h2><p>Save what you want to understand about this company to open research chat.</p><Link className="ws-btn" onClick={() => { if(!researchChatFits) closeResearchChat(); }} href={`/research/companies/${encodeURIComponent(isin)}`}>Open company →</Link></div> : company.data?.state === "READY" ? <ResearchChat key={isin} isin={isin} label={company.data.identity.symbol ?? company.data.identity.name ?? isin} thesisId={company.data.thesis?.id ?? null} /> : null}
    </>}
  </aside>;
}
