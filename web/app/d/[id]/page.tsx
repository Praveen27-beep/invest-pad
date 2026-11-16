"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Doc, type Passage, type Thesis, day } from "@/lib/api";

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [doc, setDoc] = useState<Doc | null>(null);
  const [passages, setPassages] = useState<Passage[]>([]);
  const [thesis, setThesis] = useState<Thesis | null>(null);
  const [using, setUsing] = useState<string | null>(null);   // the passage being turned into evidence
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api<Doc>(`/documents/${id}`).then(async (d) => {
      setDoc(d);
      setPassages(await api<Passage[]>(`/documents/${id}/passages`));
      setThesis(await api<Thesis>(`/subjects/${d.subject_id}/thesis`));
    }).catch((e) => setError((e as Error).message));
  }, [id]);

  async function remove() {
    if (!doc || !window.confirm(`Delete “${doc.title}”? Its text and every passage taken from it are removed. Evidence that cited it stays as your own words, no longer marked as a fact.`)) return;
    await api(`/documents/${id}`, { method: "DELETE" });
    router.replace(`/c/${doc.subject_id}`);
  }

  async function addEvidence(e: React.FormEvent<HTMLFormElement>, passageId: string) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setError("");
    try {
      await api(`/assumptions/${f.get("assumption")}/evidence`, {
        method: "POST", body: { direction: f.get("direction"), kind: "fact", body: f.get("body"), chunk_id: passageId } });
      setUsing(null);
      setStatus("Added as evidence. It is on the Thesis tab.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (error && !doc) return <p className="error" role="alert">{error}</p>;
  if (!doc) return null;
  return (
    <>
      <Link href={`/c/${doc.subject_id}`}>← Company</Link>
      <div className="row">
        <h1 style={{ flex: 1 }}>{doc.title}</h1>
        <a href={`/api/documents/${id}/file`}>Download original</a>
        <button className="danger" onClick={remove}>Delete</button>
      </div>
      <p className="muted">
        {doc.doc_type}{doc.period ? ` · ${doc.period}` : ""}{doc.doc_date ? ` · ${day(doc.doc_date)}` : ""} · {doc.filename} · {doc.pages} page(s) · {passages.length} passage(s)
      </p>
      {doc.status !== "ready" && <p className={doc.status === "processing" ? "dirty" : "error"} role="status">
        {doc.status === "processing" ? "Still reading this document. Reload in a moment." : doc.status_note}</p>}
      {status && <p className="ok" role="status">{status}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {passages.map((p) => (
        <div className="card" key={p.id} id={p.id}>
          <div className="row">
            <strong className="small muted" style={{ flex: 1 }}>{p.label || `Section ${p.page}`}</strong>
            <button className="link small" onClick={() => setUsing(using === p.id ? null : p.id)}>Use as evidence</button>
          </div>
          <div style={{ whiteSpace: "pre-wrap" }}>{p.body}</div>
          {using === p.id && (
            !thesis?.assumptions.length ? <p className="muted small">Add an assumption on the Thesis tab first; evidence attaches to an assumption.</p> : (
              <form className="stack" style={{ marginTop: ".6rem" }} onSubmit={(e) => addEvidence(e, p.id)}>
                <div className="row" style={{ flexWrap: "wrap" }}>
                  <select name="direction" aria-label="Direction"><option value="for">Supports</option><option value="against">Goes against</option></select>
                  <select name="assumption" aria-label="Assumption" style={{ flex: 1, minWidth: 0 }}>
                    {thesis.assumptions.map((a) => (<option key={a.id} value={a.id}>{a.body}</option>))}
                  </select>
                </div>
                <input type="text" name="body" placeholder="In your words: what does this passage show?" required />
                <div><button className="primary">Add as a fact</button></div>
              </form>
            )
          )}
        </div>
      ))}
    </>
  );
}
