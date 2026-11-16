"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Portfolio, type Subject, money, upload, when } from "@/lib/api";

export default function PortfolioPage() {
  const [p, setP] = useState<Portfolio | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setP(await api<Portfolio>("/portfolio"));
    setSubjects(await api<Subject[]>("/subjects"));
  }, []);
  useEffect(() => { load().catch((e) => setError((e as Error).message)); }, [load]);

  async function run(action: () => Promise<Portfolio | void>) {
    setError("");
    try { const next = await action(); if (next) setP(next); else await load(); } catch (e) { setError((e as Error).message); }
  }

  if (!p) return error ? <p className="error" role="alert">{error}</p> : null;
  return (
    <>
      <h1>Portfolio</h1>
      <p className="empty">
        Your holdings, measured against limits you set yourself. Invest-pad tells you when a number you chose is
        crossed and asks you about it. It does not say what to buy or sell.
      </p>
      {error && <p className="error" role="alert">{error}</p>}

      {p.alerts.length > 0 && (
        <>
          <h2>Limits crossed</h2>
          {p.alerts.map((a) => (
            <div className="card" key={a.id} role="alert">
              <div>{a.message}</div>
              {a.status === "acknowledged" ? (
                <div className="snip">Seen{a.note ? ` — you wrote: “${a.note}”` : ""}. Stays listed while it is still true.</div>
              ) : (
                <form className="row" style={{ marginTop: ".5rem" }} onSubmit={(e) => {
                  e.preventDefault();
                  const note = new FormData(e.currentTarget).get("note");
                  run(() => api<Portfolio>(`/alerts/${a.id}/acknowledge`, { method: "POST", body: { note } }));
                }}>
                  <input type="text" name="note" placeholder="Why does this stand? (optional — your note is kept)" />
                  <button>I’ve seen this</button>
                </form>
              )}
            </div>
          ))}
        </>
      )}

      <h2>Holdings</h2>
      <div className="card stack">
        <label className="field">Upload a holdings CSV (for example the Holdings export from your broker or tracker)
          <input ref={file} type="file" accept=".csv,text/csv" aria-label="Holdings file" /></label>
        <div className="row">
          <button className="primary" onClick={() => run(async () => {
            const chosen = file.current?.files?.[0];
            if (!chosen) throw new Error("Choose a file first.");
            const form = new FormData();
            form.set("file", chosen);
            const next = await upload<Portfolio>("/portfolio/import", form);
            if (file.current) file.current.value = "";
            return next;
          })}>Import</button>
          {p.snapshot && <span className="muted small">Last import {when(p.snapshot.created_at)} · total ₹{money(p.snapshot.total_value)}</span>}
          {p.snapshot && <button className="link danger" onClick={() => { if (window.confirm("Remove all imported holdings and their alerts?")) run(() => api("/portfolio", { method: "DELETE" })); }}>Remove holdings</button>}
        </div>
        <p className="small muted">Each import replaces the picture of the portfolio; earlier imports are kept. A live link to Trackr+ is planned and is connected separately.</p>
      </div>
      {p.holdings.length > 0 && (
        <ul className="list" style={{ marginTop: "1rem" }}>
          {p.holdings.map((h) => (
            <li key={h.symbol}>
              <strong style={{ minWidth: "8rem" }}>{h.symbol}</strong>
              <span style={{ minWidth: "4.5rem" }}>{Number(h.weight_pct).toFixed(2)}%</span>
              <span className="muted small" style={{ minWidth: "7rem" }}>₹{money(h.value)}</span>
              <select aria-label={`Company page for ${h.symbol}`} value={h.subject_id ?? ""}
                onChange={(e) => run(() => api<Portfolio>("/portfolio/link", { method: "PUT", body: { symbol: h.symbol, subject_id: e.target.value || null } }))}>
                <option value="">No company page</option>
                {subjects.map((s) => (<option key={s.id} value={s.id}>{s.name}</option>))}
              </select>
              {h.subject_id && <Link href={`/c/${h.subject_id}`}>Open</Link>}
              <small>{h.has_thesis ? (h.decisions ? "thesis · decision recorded" : "thesis · no decision") : "no thesis"}</small>
            </li>
          ))}
        </ul>
      )}

      <h2>My limits</h2>
      <p className="empty">Off until you turn one on. Change them whenever your approach changes.</p>
      {p.limits.map((l) => (<LimitRow key={l.key + l.value + l.enabled} limit={l} save={(body) => run(() => api<Portfolio>("/portfolio/limits", { method: "PUT", body }))} />))}

      <h2>Watchlist</h2>
      {p.watchlist.length === 0 ? <p className="empty">Nothing on your watchlist. Add a company from its page.</p> : (
        <ul className="list">
          {p.watchlist.map((w) => (
            <li key={w.id}>
              <Link href={`/c/${w.id}`}>{w.name}</Link>
              <span className="muted small">{w.held ? "held" : "not held"} · {w.notes} note(s) · {w.documents} document(s)</span>
              <small>watching since {when(w.watch_since)}</small>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function LimitRow({ limit, save }: { limit: Portfolio["limits"][number]; save: (body: object) => void }) {
  const [value, setValue] = useState(String(Number(limit.value) || ""));
  const needsNumber = limit.key !== "thesis_required";
  return (
    <div className="card row" style={{ flexWrap: "wrap" }}>
      <label style={{ flex: 1 }}>
        <input type="checkbox" checked={limit.enabled} aria-label={limit.label}
          onChange={(e) => save({ key: limit.key, value: Number(value) || 0, enabled: e.target.checked })} /> {limit.label}
      </label>
      {needsNumber && (
        <>
          <input type="text" inputMode="decimal" value={value} style={{ width: "6rem" }} aria-label={`${limit.label} — number`}
            onChange={(e) => setValue(e.target.value)} />
          <button disabled={Number(value) === Number(limit.value)} onClick={() => save({ key: limit.key, value: Number(value) || 0, enabled: limit.enabled })}>Save</button>
        </>
      )}
    </div>
  );
}
