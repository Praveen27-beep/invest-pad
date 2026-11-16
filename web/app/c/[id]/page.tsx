"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AskTab from "@/components/AskTab";
import ChecklistTab from "@/components/ChecklistTab";
import DocumentsTab from "@/components/DocumentsTab";
import GraphTab from "@/components/GraphTab";
import NoteList from "@/components/NoteList";
import OverviewPanel from "@/components/Overview";
import ThesisTab from "@/components/ThesisTab";
import { api, type NoteSummary, type Overview, type Pack } from "@/lib/api";

const TABS = [["overview", "Overview"], ["ask", "Ask"], ["thesis", "Thesis & decisions"], ["documents", "Documents"], ["notes", "Notes"], ["checklist", "Red flags"], ["graph", "Connections"]];

export default function Company() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [pack, setPack] = useState<Pack | null>(null);
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [o, n] = await Promise.all([api<Overview>(`/subjects/${id}/overview`), api<NoteSummary[]>(`/notes?subject_id=${id}`)]);
    setOverview(o);
    setNotes(n);
  }, [id]);
  useEffect(() => {
    load().catch((err) => setError((err as Error).message));
    api<Pack>("/pack").then(setPack).catch(() => {});
  }, [load]);

  async function remove() {
    if (!overview) return;
    const name = overview.subject.name;
    const typed = window.prompt(
      `Delete ${name} with its notes, documents, thesis and decision journal? This cannot be undone.\n\nType the company name to confirm.`);
    if (typed?.trim().toLowerCase() !== name.toLowerCase()) return;
    await api(`/subjects/${id}`, { method: "DELETE" });
    router.replace("/");
  }

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!overview || !pack) return null;
  return (
    <>
      <div className="row">
        <h1 style={{ flex: 1, margin: 0 }}>{overview.subject.name}</h1>
        <button onClick={async () => {
          await api(`/subjects/${id}/watch`, { method: "PUT", body: { watching: !overview.subject.watch_since } });
          await load();
        }}>{overview.subject.watch_since ? "On watchlist ✓" : "Add to watchlist"}</button>
        <button className="danger" onClick={remove}>Delete company</button>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>
      {tab === "overview" && <OverviewPanel data={overview} goTo={setTab} />}
      {tab === "ask" && <AskTab subjectId={id} />}
      {tab === "thesis" && <ThesisTab subjectId={id} pack={pack} onChange={load} />}
      {tab === "documents" && <DocumentsTab subjectId={id} pack={pack} onChange={load} />}
      {tab === "notes" && <NoteList notes={notes} subjectId={id} />}
      {tab === "checklist" && <ChecklistTab subjectId={id} pack={pack} />}
      {tab === "graph" && <GraphTab subjectId={id} />}
    </>
  );
}
