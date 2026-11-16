"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import NoteList from "@/components/NoteList";
import { api, type NoteSummary, type Subject } from "@/lib/api";

export default function Company() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [subject, setSubject] = useState<Subject | null>(null);
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api<Subject>(`/subjects/${id}`), api<NoteSummary[]>(`/notes?subject_id=${id}`)])
      .then(([s, n]) => { setSubject(s); setNotes(n); })
      .catch((err) => setError((err as Error).message));
  }, [id]);

  async function remove() {
    if (!subject) return;
    const typed = window.prompt(
      `Delete ${subject.name} and all ${notes.length} of its notes, including their history? This cannot be undone.\n\nType the company name to confirm.`);
    if (typed?.trim().toLowerCase() !== subject.name.toLowerCase()) return;
    await api(`/subjects/${id}`, { method: "DELETE" });
    router.replace("/");
  }

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!subject) return null;
  return (
    <>
      <div className="row">
        <h1 style={{ flex: 1 }}>{subject.name}</h1>
        <button className="danger" onClick={remove}>Delete company</button>
      </div>
      <h2>Notes</h2>
      <NoteList notes={notes} subjectId={id} />
    </>
  );
}
