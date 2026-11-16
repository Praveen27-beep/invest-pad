"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, when } from "@/lib/api";

type Found = {
  passages: { id: string; document_id: string; label: string; title: string; period: string; doc_type: string; snippet: string }[];
};
type Results = {
  notes: { id: string; title: string; snippet: string; updated_at: string }[];
  subjects: { id: string; name: string }[];
};

/** The server marks matches as <<word>>. Render those as highlights without using raw HTML. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/<<|>>/);
  return <span className="snip">{parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : p))}</span>;
}

function SearchResults() {
  const q = useSearchParams().get("q") ?? "";
  const [results, setResults] = useState<Results | null>(null);
  const [found, setFound] = useState<Found>({ passages: [] });
  useEffect(() => {
    api<Found>(`/retrieve?q=${encodeURIComponent(q)}&limit=12`).then(setFound).catch(() => setFound({ passages: [] }));
    api<Results>(`/search?q=${encodeURIComponent(q)}`).then(setResults).catch(() => setResults({ notes: [], subjects: [] }));
  }, [q]);

  if (!results) return null;
  return (
    <>
      <h1>Search: {q}</h1>
      {results.subjects.length > 0 && (
        <>
          <h2>Companies</h2>
          <ul className="list">{results.subjects.map((s) => (<li key={s.id}><Link href={`/c/${s.id}`}>{s.name}</Link></li>))}</ul>
        </>
      )}
      <h2>Passages in your documents</h2>
      {found.passages.length === 0 ? <p className="empty">Nothing found in your documents.</p> : (
        <ul className="list side">
          {found.passages.map((p) => (
            <li key={p.id} style={{ display: "block" }}>
              <Link href={`/d/${p.document_id}#${p.id}`}>{p.title}</Link>{" "}
              <small>{p.doc_type}{p.period ? ` · ${p.period}` : ""} · {p.label}</small>
              <Snippet text={p.snippet} />
            </li>
          ))}
        </ul>
      )}
      <h2>Notes</h2>
      {results.notes.length === 0 ? <p className="empty">Nothing found in your notes.</p> : (
        <ul className="list side">
          {results.notes.map((n) => (
            <li key={n.id} style={{ display: "block" }}>
              <Link href={`/n/${n.id}`}>{n.title}</Link> <small>{when(n.updated_at)}</small>
              <Snippet text={n.snippet} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function Search() {
  return <Suspense><SearchResults /></Suspense>;
}
