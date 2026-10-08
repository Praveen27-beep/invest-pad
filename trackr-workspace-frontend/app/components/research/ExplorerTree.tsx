"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useFetch } from "@trackr/core";
import { companyDescriptor, noteHref } from "@trackr/portfolio";
import { useWorkspaceNav } from "@/lib/workspace-context";
import { paths, type CompanyListItem, type Note, type Page } from "@/lib/research-api";
import { useResearchAuth } from "@/lib/research-hooks";

export function ExplorerTree() {
  const { investorId, token } = useResearchAuth();
  const pathname = usePathname();
  const companies = useFetch<Page<CompanyListItem>>(investorId ? paths.companies(investorId) : null, { limit: 100 }, token);
  useEffect(() => { companies.refetch(); }, [pathname, companies.refetch]);
  const [filter, setFilter] = useState("");
  const items = companies.data?.items.filter(c => `${c.symbol} ${c.name} ${c.isin}`.toLowerCase().includes(filter.toLowerCase())) ?? [];
  return <section className="ip-tree" aria-label="Explorer">
    <div className="ip-tree-heading"><Link href="/explorer">EXPLORER</Link><Link href="/explorer?add=1" aria-label="Add company" title="Add company">+</Link></div>
    <input className="ip-tree-filter" placeholder="Find a company…" aria-label="Filter Explorer" value={filter} onChange={e => setFilter(e.target.value)} />
    <details open className="ip-tree-folder"><summary>Companies <span>{companies.data?.items.length ?? ""}</span></summary>
      {companies.loading && <p className="ip-tree-status">Loading companies…</p>}
      {companies.error && <div className="ip-tree-status">Could not load companies. <button onClick={companies.refetch}>Retry</button></div>}
      {!companies.loading && !companies.error && items.length === 0 && <p className="ip-tree-status">{filter ? "No matching companies." : "Your research starts here."}</p>}
      {items.map(c => <TreeCompany key={c.isin} company={c} pathname={pathname} />)}
      {companies.data?.next_cursor && <Link className="ip-tree-status" href="/explorer">View more companies →</Link>}
    </details>
  </section>;
}

function TreeCompany({ company, pathname }: { company: CompanyListItem; pathname: string }) {
  const { investorId, token } = useResearchAuth();
  const { openDocument } = useWorkspaceNav();
  const href = `/research/companies/${encodeURIComponent(company.isin)}`;
  const [expanded, setExpanded] = useState(pathname === href);
  const notes = useFetch<Page<Note>>(expanded && company.ritual_complete ? paths.companyNotes(investorId, company.isin) : null, { limit: 100 }, token);
  const label = company.symbol ?? company.name ?? company.isin;
  return <div className="ip-tree-company">
    <div className="ip-tree-row" data-active={pathname === href}>
      <button aria-label={`${expanded ? "Collapse" : "Expand"} ${label}`} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "⌄" : "›"}</button>
      <button className="ip-tree-name" onClick={() => { const d = companyDescriptor(company.isin, label); if(d) openDocument(d); }}><span aria-hidden="true">▥</span> {label}</button>
    </div>
    {expanded && <div className="ip-tree-notes">
      {!company.ritual_complete ? <Link href={href}>Start with a question →</Link> : <>
        {notes.loading && <p>Loading notes…</p>}
        {notes.error && <button onClick={notes.refetch}>Retry loading notes</button>}
        {notes.data?.items.length === 0 && <Link href={`${href}?mode=notes`}>+ Write a note</Link>}
        {[...new Set(notes.data?.items.map(n => n.kind) ?? [])].map(kind => <details key={kind} open><summary>{kind.toLowerCase().replaceAll("_", " ")}</summary>{notes.data?.items.filter(n => n.kind === kind).map(n => <Link key={n.id} href={noteHref(n.id) ?? href} aria-current={pathname === noteHref(n.id) ? "page" : undefined} title={n.title}><span aria-hidden="true">▤</span> {n.title}</Link>)}</details>)}
        {notes.data?.next_cursor && <Link href={`${href}?mode=notes`}>More notes →</Link>}
      </>}
    </div>}
  </div>;
}
