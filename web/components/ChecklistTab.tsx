"use client";

import { useCallback, useEffect, useState } from "react";
import { api, when } from "@/lib/api";

type Answer = { id: string; answer: "yes" | "no" | "unknown"; note: string };
type Item = { id: string; text: string };
type Checklist = { key: string; seq: number; title: string; intro: string; items: Item[]; builtin: boolean; edited: boolean };

export default function ChecklistTab({ subjectId }: { subjectId: string }) {
  const [lists, setLists] = useState<Checklist[]>([]);
  const [key, setKey] = useState("red-flags");
  const [editing, setEditing] = useState<Checklist | null>(null);
  const load = useCallback(async () => setLists(await api<Checklist[]>("/checklists")), []);
  useEffect(() => { load().catch(() => {}); }, [load]);
  const checklist = lists.find((c) => c.key === key);
  if (!checklist) return null;

  return (
    <>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <select aria-label="Checklist" value={key} onChange={(e) => { setKey(e.target.value); setEditing(null); }}>
          {lists.map((c) => (<option key={c.key} value={c.key}>{c.title}{c.edited ? " (edited)" : ""}</option>))}
        </select>
        <button onClick={() => setEditing(checklist)}>Edit this checklist</button>
        <button onClick={() => setEditing({ key: "new", seq: 0, title: "", intro: "", items: [{ id: "", text: "" }], builtin: false, edited: false })}>
          New checklist
        </button>
      </div>
      {editing ? (
        <Editor list={editing} onDone={async (saved) => { await load(); if (saved) setKey(saved); setEditing(null); }} />
      ) : (
        <Run key={`${checklist.key}:${checklist.seq}`} subjectId={subjectId} checklist={checklist} />
      )}
    </>
  );
}

function Run({ subjectId, checklist }: { subjectId: string; checklist: Checklist }) {
  const url = `/subjects/${subjectId}/checklists/${checklist.key}`;
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [last, setLast] = useState<{ created_at: string | null; runs: number }>({ created_at: null, runs: 0 });
  const [status, setStatus] = useState("");

  useEffect(() => {
    api<{ items: Answer[]; created_at: string | null; runs: number }>(url).then((run) => {
      setAnswers(Object.fromEntries(run.items.map((i) => [i.id, i])));
      setLast(run);
    }).catch(() => {});
  }, [url]);

  const get = (id: string): Answer => answers[id] ?? { id, answer: "unknown", note: "" };
  const set = (id: string, patch: Partial<Answer>) => { setAnswers({ ...answers, [id]: { ...get(id), ...patch } }); setStatus(""); };
  const flags = checklist.items.filter((i) => get(i.id).answer === "yes").length;
  const unknown = checklist.items.filter((i) => get(i.id).answer === "unknown").length;

  async function save() {
    const run = await api<{ created_at: string }>(url, { method: "POST", body: { items: checklist.items.map((i) => get(i.id)) } });
    setLast({ created_at: run.created_at, runs: last.runs + 1 });
    setStatus("Saved as a new run");
  }

  return (
    <>
      {checklist.intro && <p className="muted">{checklist.intro}</p>}
      <p><strong>{flags}</strong> flagged · <strong>{unknown}</strong> not known yet
        {last.created_at && <span className="muted"> · last saved {when(last.created_at)} ({last.runs} run{last.runs === 1 ? "" : "s"} kept)</span>}</p>
      {checklist.items.map((item) => (
        <div className="card" key={item.id}>
          <div>{item.text}</div>
          <div className="row" style={{ marginTop: ".4rem", flexWrap: "wrap" }}>
            <select aria-label={item.text} value={get(item.id).answer} onChange={(e) => set(item.id, { answer: e.target.value as Answer["answer"] })}>
              <option value="unknown">Don’t know yet</option><option value="no">No</option><option value="yes">Yes — a flag</option>
            </select>
            <input type="text" placeholder="Where did you check? What did you find?" value={get(item.id).note} onChange={(e) => set(item.id, { note: e.target.value })} />
          </div>
        </div>
      ))}
      <div className="row" style={{ marginTop: "1rem" }}><button className="primary" onClick={save}>Save checklist</button><span className="ok" role="status">{status}</span></div>
    </>
  );
}

function Editor({ list, onDone }: { list: Checklist; onDone: (savedKey?: string) => void }) {
  const [title, setTitle] = useState(list.title);
  const [intro, setIntro] = useState(list.intro);
  const [items, setItems] = useState<Item[]>(list.items);
  const [error, setError] = useState("");
  const setItem = (i: number, text: string) => setItems(items.map((it, j) => (j === i ? { ...it, text } : it)));

  return (
    <div className="card stack" style={{ marginTop: "1rem" }}>
      <p className="small muted">
        {list.key === "new" ? "Write your own checklist." : "Saving keeps the old version; past runs keep the wording they were answered against."}
        {list.builtin && " This changes your copy only."}
      </p>
      <label className="field">Title<input type="text" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="field">Instructions (optional)<textarea rows={2} value={intro} onChange={(e) => setIntro(e.target.value)} /></label>
      {items.map((it, i) => (
        <div className="row" key={i}>
          <input type="text" aria-label={`Question ${i + 1}`} value={it.text} placeholder="A yes/no question" onChange={(e) => setItem(i, e.target.value)} />
          <button className="link danger" aria-label={`Remove question ${i + 1}`} onClick={() => setItems(items.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <div className="row">
        <button onClick={() => setItems([...items, { id: "", text: "" }])}>Add a question</button>
        <button className="primary" onClick={async () => {
          setError("");
          try {
            const saved = await api<Checklist>(`/checklists/${list.key}`, { method: "PUT",
              body: { title, intro, items: items.filter((i) => i.text.trim()) } });
            onDone(saved.key);
          } catch (e) { setError((e as Error).message); }
        }}>Save checklist</button>
        <button className="link" onClick={() => onDone()}>Cancel</button>
        {error && <span className="error" role="alert">{error}</span>}
      </div>
    </div>
  );
}
