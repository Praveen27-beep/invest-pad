"use client";

import { useEffect, useState } from "react";
import { api, type Pack, when } from "@/lib/api";

type Answer = { id: string; answer: "yes" | "no" | "unknown"; note: string };

export default function ChecklistTab({ subjectId, pack }: { subjectId: string; pack: Pack }) {
  const checklist = pack.checklists["red-flags"];
  const url = `/subjects/${subjectId}/checklists/red-flags`;
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
      <p className="muted">{checklist.intro}</p>
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
