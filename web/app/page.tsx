"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import NoteList from "@/components/NoteList";
import { api, type NoteSummary, type Subject } from "@/lib/api";

export default function Home() {
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [s, n] = await Promise.all([api<Subject[]>("/subjects"), api<NoteSummary[]>("/notes")]);
    setSubjects(s);
    setNotes(n.filter((note) => !note.subject_id));
  }, []);
  useEffect(() => { load().catch(() => {}); }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/subjects", { method: "POST", body: { name } });
      setName("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!subjects) return null;
  return (
    <>
      <h1>Companies</h1>
      <div className="stack">
        <form onSubmit={add} className="row">
          <input type="text" placeholder="Add a company, e.g. IEX" value={name} onChange={(e) => setName(e.target.value)} required />
          <button className="primary">Add company</button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {subjects.length === 0 ? (
          <p className="empty">Add the first company you are researching.</p>
        ) : (
          <ul className="list">
            {subjects.map((s) => (<li key={s.id}><Link href={`/c/${s.id}`}>{s.name}</Link></li>))}
          </ul>
        )}
      </div>
      <h2>Notes not filed under a company</h2>
      <NoteList notes={notes} />
    </>
  );
}
