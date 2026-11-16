"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type NoteSummary, when } from "@/lib/api";

/** A list of notes with a "new note" box. Used on the home page and on company pages. */
export default function NoteList({ notes, subjectId }: { notes: NoteSummary[]; subjectId?: string }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const note = await api<NoteSummary>("/notes", { method: "POST", body: { title, subject_id: subjectId ?? null, blocks: [] } });
      router.push(`/n/${note.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="stack">
      <form onSubmit={create} className="row">
        <input type="text" placeholder="New note title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        <button className="primary">New note</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {notes.length === 0 ? (
        <p className="empty">No notes yet.</p>
      ) : (
        <ul className="list">
          {notes.map((n) => (
            <li key={n.id}>
              <Link href={`/n/${n.id}`}>{n.title}</Link>
              <small>version {n.seq} · {when(n.updated_at)}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
