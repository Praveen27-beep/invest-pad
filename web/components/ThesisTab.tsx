"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Assumption, type Decision, type Pack, STATES, type Thesis, day, when } from "@/lib/api";

type Change = { op: "equal" | "insert" | "delete"; text: string };

export default function ThesisTab({ subjectId, pack, onChange }: { subjectId: string; pack: Pack; onChange: () => void }) {
  const base = `/subjects/${subjectId}`;
  const [thesis, setThesis] = useState<Thesis | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [diff, setDiff] = useState<{ a: number; b: number; changes: Change[] } | null>(null);

  const load = useCallback(async () => {
    const [t, d] = await Promise.all([api<Thesis>(`${base}/thesis`), api<Decision[]>(`${base}/decisions`)]);
    setThesis(t);
    setDecisions(d);
    return t;
  }, [base]);
  useEffect(() => { load().then((t) => setBody(t.body)).catch((e) => setError((e as Error).message)); }, [load]);

  async function run(action: () => Promise<unknown>, done = "") {
    setError("");
    setStatus("");
    try { await action(); if (done) setStatus(done); await load(); onChange(); } catch (e) { setError((e as Error).message); }
  }

  if (!thesis) return error ? <p className="error" role="alert">{error}</p> : null;
  const labels = Object.fromEntries(pack.decision_types.map((t) => [t.key, t.label]));
  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      <h2 style={{ marginTop: 0 }}>Thesis {thesis.seq > 0 && <span className="muted">· version {thesis.seq}</span>}</h2>
      <textarea rows={7} value={body} aria-label="Thesis" placeholder="What must be true for this to work? Write it in your own words."
        onChange={(e) => setBody(e.target.value)} />
      <div className="row" style={{ marginTop: ".5rem" }}>
        <button className="primary" disabled={body.trim() === thesis.body}
          onClick={() => run(async () => { const r = await api<{ seq: number }>(`${base}/thesis`, { method: "PUT", body: { body } }); setStatus(`Saved as version ${r.seq}`); })}>
          Save as new version
        </button>
        <span className="ok" role="status">{status}</span>
      </div>
      {thesis.versions.length > 1 && (
        <p className="small">
          Earlier versions are never changed. Compare:{" "}
          {thesis.versions.slice(0, -1).map((v) => (
            <button key={v.seq} className="link" style={{ marginRight: ".8rem" }}
              onClick={async () => setDiff({ a: v.seq - 1, b: v.seq, ...(await api<{ changes: Change[] }>(`${base}/thesis/diff?a=${v.seq - 1}&b=${v.seq}`)) })}>
              v{v.seq - 1} → v{v.seq} ({day(v.created_at)})
            </button>
          ))}
        </p>
      )}
      {diff && (
        <div className="card diff" aria-label="Thesis changes">
          <div className="row"><strong style={{ flex: 1 }}>Version {diff.a} → {diff.b}</strong><button className="link" onClick={() => setDiff(null)}>Close</button></div>
          {diff.changes.map((c, i) => c.op === "insert" ? <ins key={i}>{c.text}</ins> : c.op === "delete" ? <del key={i}>{c.text}</del> : <span key={i}>{c.text}</span>)}
        </div>
      )}

      <h2>Assumptions the thesis rests on</h2>
      {thesis.assumptions.length === 0 && <p className="muted">None yet. Add the few statements that, if wrong, would break the thesis.</p>}
      {thesis.assumptions.map((a) => (<AssumptionCard key={a.id} a={a} run={run} />))}
      <NewAssumption onAdd={(text, basis) => run(() => api(`${base}/assumptions`, { method: "POST", body: { body: text, basis } }))} />

      <h2>Record a decision</h2>
      <DecisionForm pack={pack} assumptions={thesis.assumptions}
        onSave={(d) => run(() => api(`${base}/decisions`, { method: "POST", body: d }), "Decision recorded")} />

      <h2>Decision journal</h2>
      {decisions.length === 0 ? <p className="muted">No entries yet.</p> : decisions.map((d) => (
        <div className="card" key={d.id}>
          <strong>{labels[d.type] ?? d.type}</strong> <span className="muted">on {day(d.decided_on)} · recorded {when(d.created_at)}{d.position_seq ? ` · thesis v${d.position_seq}` : ""}</span>
          <p className="reason" style={{ fontSize: "1rem" }}>{d.decisive_reason}</p>
          {d.would_change_mind && <p className="small"><span className="muted">Would change my mind:</span> {d.would_change_mind}</p>}
          {d.assumptions.map((x) => (<div className="small muted" key={x.id}>Rested on: {x.body} ({x.state} at the time)</div>))}
        </div>
      ))}
    </>
  );
}

function AssumptionCard({ a, run }: { a: Assumption; run: (action: () => Promise<unknown>, done?: string) => Promise<void> }) {
  const [state, setState] = useState(a.state);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [direction, setDirection] = useState<"for" | "against">("for");
  const [history, setHistory] = useState<{ seq: number; body: string; state: string; reason: string; created_at: string }[] | null>(null);
  const side = (dir: "for" | "against") => a.evidence.filter((e) => e.direction === dir);

  return (
    <div className="card">
      <div><span className={`badge ${a.state}`}>{STATES[a.state]}</span> <span className="badge">{a.basis === "fact" ? "Rests on a source" : "My judgement"}</span> {a.body}</div>
      {a.reason && <div className="snip">Last change: {a.reason}</div>}
      <div className="cols" style={{ marginTop: ".6rem" }}>
        {(["for", "against"] as const).map((dir) => (
          <div key={dir}>
            <h2 style={{ marginTop: 0 }}>Evidence {dir}</h2>
            {side(dir).length === 0 && <p className="muted small">None.</p>}
            {side(dir).map((e) => (
              <div className="ev" key={e.id}>
                {e.is_sourced_fact ? <span className="badge fact">Fact</span>
                  : e.kind === "fact" ? <span className="badge gone">Source deleted</span>
                  : e.kind === "ai" ? <span className="badge ai">AI, accepted</span> : <span className="badge opinion">My opinion</span>}{" "}
                {e.body}
                {e.is_sourced_fact && e.document_id && (
                  <span className="snip">
                    <Link href={`/d/${e.document_id}`}>{e.document_title}</Link>{e.document_period ? ` · ${e.document_period}` : ""} · {e.page_label}
                    <span className="quote" style={{ display: "block" }}>{e.passage}</span>
                  </span>
                )}
                {e.kind === "fact" && !e.is_sourced_fact && <span className="snip">The document this cited was deleted, so it is no longer shown as a fact.</span>}
                <button className="link small" onClick={() => { if (window.confirm("Withdraw this evidence?")) run(() => api(`/evidence/${e.id}`, { method: "DELETE" })); }}>Withdraw</button>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: ".6rem", flexWrap: "wrap" }}>
        <select aria-label="Evidence direction" value={direction} onChange={(e) => setDirection(e.target.value as "for" | "against")}>
          <option value="for">For</option><option value="against">Against</option>
        </select>
        <input type="text" placeholder="Add your own opinion as evidence" value={text} onChange={(e) => setText(e.target.value)} />
        <button disabled={!text.trim()} onClick={() => run(async () => { await api(`/assumptions/${a.id}/evidence`, { method: "POST", body: { direction, kind: "opinion", body: text } }); setText(""); })}>Add opinion</button>
      </div>
      <p className="small muted">To add a fact, open a document, find the passage, and choose “Use as evidence”.</p>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <select aria-label="State" value={state} onChange={(e) => setState(e.target.value as Assumption["state"])}>
          {Object.entries(STATES).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
        </select>
        {state !== a.state && <input type="text" placeholder="Why did this change? (required)" value={reason} onChange={(e) => setReason(e.target.value)} />}
        {state !== a.state && (
          <button className="primary" disabled={!reason.trim()}
            onClick={() => run(async () => { await api(`/assumptions/${a.id}`, { method: "PUT", body: { body: a.body, basis: a.basis, state, reason } }); setReason(""); })}>
            Record change
          </button>
        )}
        <button className="link" onClick={async () => setHistory(history ? null : await api(`/assumptions/${a.id}/versions`))}>
          {history ? "Hide history" : `History (${a.seq})`}
        </button>
      </div>
      {history?.map((h) => (
        <div className="small muted" key={h.seq}>v{h.seq} · {when(h.created_at)} · {STATES[h.state as keyof typeof STATES]}{h.reason ? ` · ${h.reason}` : ""} — {h.body}</div>
      ))}
    </div>
  );
}

function NewAssumption({ onAdd }: { onAdd: (text: string, basis: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [basis, setBasis] = useState("judgement");
  return (
    <form className="row" style={{ marginTop: ".8rem", flexWrap: "wrap" }} onSubmit={async (e) => { e.preventDefault(); await onAdd(text, basis); setText(""); }}>
      <input type="text" placeholder="New assumption, e.g. Coupling stays limited to the day-ahead market" value={text} onChange={(e) => setText(e.target.value)} required />
      <select aria-label="Basis" value={basis} onChange={(e) => setBasis(e.target.value)}>
        <option value="judgement">My judgement</option><option value="fact">Rests on a source</option>
      </select>
      <button>Add assumption</button>
    </form>
  );
}

function DecisionForm({ pack, assumptions, onSave }: { pack: Pack; assumptions: Assumption[]; onSave: (d: object) => Promise<void> }) {
  const today = new Date().toISOString().slice(0, 10);
  const [type, setType] = useState(pack.decision_types[0].key);
  const [on, setOn] = useState(today);
  const [reason, setReason] = useState("");
  const [mind, setMind] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  return (
    <form className="card stack" onSubmit={async (e) => {
      e.preventDefault();
      await onSave({ type, decided_on: on, decisive_reason: reason, would_change_mind: mind, assumption_ids: picked });
      setReason(""); setMind(""); setPicked([]);
    }}>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <label className="field">Decision <select value={type} onChange={(e) => setType(e.target.value)}>
          {pack.decision_types.map((t) => (<option key={t.key} value={t.key}>{t.label}</option>))}</select></label>
        <label className="field">Date <input type="date" value={on} max={today} onChange={(e) => setOn(e.target.value)} required /></label>
      </div>
      <label className="field">The one reason that decided it
        <textarea rows={3} value={reason} minLength={10} required onChange={(e) => setReason(e.target.value)}
          placeholder="One or two sentences, in your own words. This is what you will be shown when you come back." /></label>
      <label className="field">What would change your mind? (optional)
        <textarea rows={2} value={mind} onChange={(e) => setMind(e.target.value)} /></label>
      {assumptions.length > 0 && (
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field">Which assumptions did it rest on?</legend>
          {assumptions.map((a) => (
            <label key={a.id} style={{ display: "block" }}>
              <input type="checkbox" checked={picked.includes(a.id)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, a.id] : picked.filter((x) => x !== a.id))} /> {a.body}
            </label>
          ))}
        </fieldset>
      )}
      <div><button className="primary">Record decision</button> <span className="small muted">A journal entry cannot be edited afterwards.</span></div>
    </form>
  );
}
