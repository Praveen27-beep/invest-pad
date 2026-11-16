"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Doc, type Pack, day, upload } from "@/lib/api";

const STATUS = { processing: "Reading…", ready: "", no_text: "No text found", failed: "Could not be read" } as const;

export default function DocumentsTab({ subjectId, pack, onChange }: { subjectId: string; pack: Pack; onChange: () => void }) {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  const load = useCallback(async () => {
    const list = await api<Doc[]>(`/documents?subject_id=${subjectId}`);
    setDocs(list);
    return list;
  }, [subjectId]);
  useEffect(() => { load().catch((e) => setError((e as Error).message)); }, [load]);

  // While a document is still being read, check again every couple of seconds.
  useEffect(() => {
    if (!docs?.some((d) => d.status === "processing")) return;
    const timer = setTimeout(() => load().catch(() => {}), 2000);
    return () => clearTimeout(timer);
  }, [docs, load]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = new FormData(e.currentTarget);
      data.set("subject_id", subjectId);
      if (!data.get("doc_date")) data.delete("doc_date");
      await upload("/documents", data);
      form.current?.reset();
      await load();
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form ref={form} onSubmit={submit} className="card stack">
        <label className="field">PDF, Excel (.xlsx) or Word (.docx)
          <input type="file" name="file" accept=".pdf,.xlsx,.docx" required /></label>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <label className="field">Type <select name="doc_type" defaultValue="">
            <option value="">Guess from file name</option>
            {pack.document_types.map((t) => (<option key={t} value={t}>{t}</option>))}</select></label>
          <label className="field">Period <input type="text" name="period" placeholder="e.g. FY25 or Q2 FY26" style={{ width: "11rem" }} /></label>
          <label className="field">Document date <input type="date" name="doc_date" /></label>
        </div>
        <div><button className="primary" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button></div>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
      <h2>Documents</h2>
      {!docs ? null : docs.length === 0 ? <p className="empty">No documents yet.</p> : (
        <ul className="list">
          {docs.map((d) => (
            <li key={d.id}>
              <Link href={`/d/${d.id}`}>{d.title}</Link>
              <span className="muted small">{d.doc_type}{d.period ? ` · ${d.period}` : ""}{d.doc_date ? ` · ${day(d.doc_date)}` : ""}</span>
              {STATUS[d.status] && <span className={d.status === "processing" ? "dirty" : "error"}>{STATUS[d.status]}</span>}
              <small>{d.pages ? `${d.pages} page(s)` : ""}</small>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
