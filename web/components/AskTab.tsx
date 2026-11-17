"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Assumption, type Claim, type ModelsInfo, type Question, type Thesis, day, when } from "@/lib/api";

const HEAD = {
  unknown: "Your material does not answer this",
  refused: "Not something Invest-pad answers",
  no_model: "No model connected",
  failed: "Could not answer",
} as const;

export default function AskTab({ subjectId }: { subjectId: string }) {
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [models, setModels] = useState<ModelsInfo | null>(null);
  const [assumptions, setAssumptions] = useState<Assumption[]>([]);
  const [text, setText] = useState("");
  const [modelId, setModelId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => setQuestions(await api<Question[]>(`/questions?subject_id=${subjectId}`)), [subjectId]);
  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
    api<ModelsInfo>("/models").then(setModels).catch(() => {});
    api<Thesis>(`/subjects/${subjectId}/thesis`).then((t) => setAssumptions(t.assumptions)).catch(() => {});
  }, [load, subjectId]);

  // While an answer is being prepared, look again every second and a half.
  useEffect(() => {
    if (!questions?.some((q) => q.status === "queued")) return;
    const timer = setTimeout(() => load().catch(() => {}), 1500);
    return () => clearTimeout(timer);
  }, [questions, load]);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/questions", { method: "POST", body: { body: text, subject_id: subjectId, model_id: modelId || null } });
      setText("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const noModel = models && models.models.length === 0 && !models.included;
  return (
    <>
      <form onSubmit={ask} className="card stack">
        <textarea rows={2} value={text} aria-label="Your question" required minLength={3}
          placeholder="Ask about this company. The answer comes from your notes and documents, with the passages quoted."
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") e.currentTarget.form?.requestSubmit(); }} />
        <div className="row" style={{ flexWrap: "wrap" }}>
          <button className="primary">Ask</button>
          {models && models.models.length > 0 && (
            <select aria-label="Model" value={modelId} onChange={(e) => setModelId(e.target.value)}>
              <option value="">{models.models[0].label} (default)</option>
              {models.models.slice(1).map((m) => (<option key={m.id} value={m.id}>{m.label}</option>))}
            </select>
          )}
          {noModel && <span className="dirty small">No model connected yet — <Link href="/settings">add one in Settings</Link>.</span>}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </form>

      {questions?.length === 0 && <p className="empty">No questions yet. Questions you capture in the browser notepad with “Ask now” appear here too.</p>}
      {questions?.map((q) => (
        <div className="card" key={q.id}>
          <div className="row">
            <strong style={{ flex: 1 }}>{q.body}</strong>
            <span className="snip" style={{ display: "inline" }}>{when(q.created_at)}</span>
            <button className="link small" onClick={async () => { await api(`/questions/${q.id}`, { method: "DELETE" }); await load(); }}>Remove</button>
          </div>
          {!q.answer ? <p className="dirty" role="status">Reading your material…</p> : q.answer.outcome === "answered" ? (
            <>
              {q.answer.claims.map((c) => (<ClaimRow key={c.id} claim={c} assumptions={assumptions} />))}
              <p className="small muted">
                <span className="badge ai">AI</span> {q.answer.model} · every statement above quotes the source it rests on.
                {q.answer.note && <> {q.answer.note}</>}
              </p>
            </>
          ) : (
            <p><strong>{HEAD[q.answer.outcome]}.</strong> {q.answer.note}</p>
          )}
        </div>
      ))}
    </>
  );
}

function ClaimRow({ claim, assumptions }: { claim: Claim; assumptions: Assumption[] }) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState("");
  async function keep(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await api(`/claims/${claim.id}/accept`, { method: "POST", body: { assumption_id: f.get("assumption"), direction: f.get("direction") } });
    setOpen(false);
    setDone("Kept as evidence, marked as AI.");
  }
  return (
    <div className="ev">
      {claim.body}
      <span className="quote" style={{ display: "block" }}>“{claim.quote}”</span>
      <span className="snip">
        {claim.document_id
          ? <Link href={`/d/${claim.document_id}#${claim.chunk_id}`}>{claim.document_title}{claim.document_period ? ` · ${claim.document_period}` : ""} · {claim.page_label}</Link>
          : claim.decision_id
            ? <Link href={`/c/${claim.decision_subject_id}`}>My decision · {day(claim.decision_date ?? "")}</Link>
            : <Link href={`/n/${claim.note_id}`}>My note: {claim.note_title}</Link>}
        {" · "}
        {done || claim.decision_id || <button className="link small" onClick={() => setOpen(!open)}>Keep as evidence</button>}
      </span>
      {open && (assumptions.length === 0 ? <p className="small muted">Add an assumption on the Thesis tab first.</p> : (
        <form className="row" style={{ flexWrap: "wrap", marginTop: ".4rem" }} onSubmit={keep}>
          <select name="direction" aria-label="Direction"><option value="for">Supports</option><option value="against">Goes against</option></select>
          <select name="assumption" aria-label="Assumption" style={{ flex: 1, minWidth: 0 }}>
            {assumptions.map((a) => (<option key={a.id} value={a.id}>{a.body}</option>))}
          </select>
          <button>Keep</button>
        </form>
      ))}
    </div>
  );
}
