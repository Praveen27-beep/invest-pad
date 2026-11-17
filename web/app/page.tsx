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
          <div className="card">
            <strong>Getting started</strong>
            <ol className="small" style={{ margin: ".5rem 0 0", paddingLeft: "1.2rem", lineHeight: 1.7 }}>
              <li>Add the first company you are researching, above.</li>
              <li>On its page, upload an annual report or concall transcript, and write notes as you read.</li>
              <li>Write your thesis and the assumptions it rests on. Mark which rest on a source and which are your judgement.</li>
              <li>When you buy, pass or stop, record the decision and the one reason that decided it. That reason is what you will see when you come back.</li>
              <li>Optional: in <Link href="/settings">Settings</Link>, write “How I invest”, connect a model to ask questions with cited answers, and set up the Chrome side panel. On <Link href="/portfolio">Portfolio</Link>, import holdings and set your own limits.</li>
            </ol>
          </div>
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
