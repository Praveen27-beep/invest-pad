"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, type Capture, type Subject, when } from "@/lib/api";

/** Only http(s) addresses become links; anything else a page claimed as its URL stays plain text. */
function Source({ capture }: { capture: Capture }) {
  if (!capture.url) return null;
  const label = capture.page_title || capture.url;
  return /^https?:\/\//i.test(capture.url)
    ? <a href={capture.url} target="_blank" rel="noopener noreferrer">{label}</a>
    : <span>{label}</span>;
}

export default function Inbox() {
  const router = useRouter();
  const [items, setItems] = useState<Capture[] | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [c, s] = await Promise.all([api<Capture[]>("/captures"), api<Subject[]>("/subjects")]);
    setItems(c);
    setSubjects(s);
  }, []);
  useEffect(() => { load().catch((err) => setError((err as Error).message)); }, [load]);

  async function act(run: () => Promise<unknown>) {
    setError("");
    try { await run(); await load(); } catch (err) { setError((err as Error).message); }
  }

  if (!items) return error ? <p className="error" role="alert">{error}</p> : null;
  return (
    <>
      <h1>Inbox</h1>
      <p className="empty">Notes and questions you captured while reading. File each under a company, turn it into a note, or dismiss it.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {items.length === 0 ? (
        <p className="empty">Nothing waiting. Captures from the browser extension appear here — set it up in <Link href="/settings">Settings</Link>.</p>
      ) : (
        <ul className="list">
          {items.map((c) => (
            <li key={c.id} style={{ display: "block" }}>
              <div className="row">
                <strong className={c.kind === "question" ? "dirty" : ""}>{c.kind === "question" ? "Question" : "Note"}</strong>
                <small style={{ marginLeft: 0 }}>{when(c.captured_at)}</small>
              </div>
              <p style={{ margin: ".3rem 0", whiteSpace: "pre-wrap" }}>{c.body}</p>
              {c.selection && <blockquote className="quote">{c.selection}</blockquote>}
              <div className="snip"><Source capture={c} /></div>
              <div className="row" style={{ marginTop: ".6rem", flexWrap: "wrap" }}>
                <select aria-label="Company" value={c.subject_id ?? ""}
                  onChange={(e) => act(() => api(`/captures/${c.id}`, { method: "PATCH", body: { subject_id: e.target.value || null } }))}>
                  <option value="">No company yet</option>
                  {subjects.map((s) => (<option key={s.id} value={s.id}>{s.name}</option>))}
                </select>
                <button className="primary" onClick={() => act(async () => {
                  const { note_id } = await api<{ note_id: string }>(`/captures/${c.id}/note`, { method: "POST" });
                  router.push(`/n/${note_id}`);
                })}>Make a note</button>
                <button onClick={() => act(() => api(`/captures/${c.id}`, { method: "PATCH", body: { status: "dismissed" } }))}>Dismiss</button>
                <button className="danger" onClick={() => {
                  if (window.confirm("Delete this capture for good?")) act(() => api(`/captures/${c.id}`, { method: "DELETE" }));
                }}>Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
