"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ModelsInfo, type Profile, type Token, when } from "@/lib/api";

export default function Settings() {
  return (
    <>
      <h1>Settings</h1>
      <HowIInvest />
      <Models />
      <Tokens />
      <h2>Use your workspace from Claude or another MCP client</h2>
      <p className="empty">
        Read-only: search your documents and notes, list companies, read a company’s record. Nothing can be changed
        or deleted this way. Create a token above that can ask questions, then add a remote MCP server with:
      </p>
      <pre className="card small" style={{ whiteSpace: "pre-wrap" }}>{`URL:    <this site’s address>/api/mcp   (for example http://localhost:3000/api/mcp)
Header: Authorization: Bearer <your token>`}</pre>
      <h2>Export everything</h2>
      <p className="empty">
        One ZIP with every note and version, thesis, decision, document you uploaded, answer with its sources,
        holdings import and review — as readable files plus the full record as JSON. Model keys are not included.
      </p>
      <a className="button" href="/api/export" download>Download my data</a>
    </>
  );
}

function HowIInvest() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => { api<Profile>("/profile").then((p) => { setProfile(p); setBody(p.body); }).catch(() => {}); }, []);
  if (!profile) return null;
  return (
    <>
      <h2>How I invest</h2>
      <p className="empty">
        Your rules and style, in your own words: what you buy, what you avoid, position-size limits, what makes you
        sell. One rule per line works best. The assistant reads this for every answer, and checks each decision against
        it before you record one. Only you can change it.
      </p>
      <textarea rows={8} value={body} aria-label="How I invest" onChange={(e) => { setBody(e.target.value); setStatus(""); }}
        placeholder={"e.g.\nNo single position above 10% of the portfolio.\nI avoid companies where promoters have pledged shares.\nI sell when an assumption I marked decisive is broken."} />
      <div className="row" style={{ marginTop: ".5rem" }}>
        <button className="primary" disabled={body.trim() === profile.body} onClick={async () => {
          const r = await api<{ seq: number }>("/profile", { method: "PUT", body: { body } });
          setProfile(await api<Profile>("/profile"));
          setStatus(`Saved as version ${r.seq}`);
        }}>Save as new version</button>
        <span className="ok" role="status">{status}</span>
        {profile.seq > 0 && <span className="muted small">version {profile.seq}, {when(profile.versions[0].created_at)}</span>}
      </div>
    </>
  );
}

function Models() {
  const [info, setInfo] = useState<ModelsInfo | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => setInfo(await api<ModelsInfo>("/models")), []);
  useEffect(() => { load().catch(() => {}); }, [load]);

  async function add(body: object) {
    setError("");
    try { await api("/models", { method: "POST", body }); await load(); } catch (e) { setError((e as Error).message); }
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    await add({ ...f, price_in: f.price_in || 0, price_out: f.price_out || 0 });
    (e.target as HTMLFormElement).reset();
  }

  if (!info) return null;
  return (
    <>
      <h2>AI model</h2>
      <p className="empty">
        Connect any model that speaks the OpenAI chat format, with your own key: a hosted provider, or one running on
        your machine. The key is stored encrypted and is never shown again. Only the passages relevant to a question
        are sent to the model, and only when you ask.
        {info.included ? ` An included model is available up to $${info.caps.monthly_credit} a month.` : " No included model is set up on this server."}
      </p>
      {info.models.length === 0 ? <p className="empty">No model connected.</p> : (
        <ul className="list">
          {info.models.map((m, i) => (
            <li key={m.id}>
              <span>{m.label}{i === 0 ? " (default)" : ""}</span>
              <span className="muted small">{m.model} · {m.base_url}{m.key_last4 ? ` · key ending ${m.key_last4}` : ""}</span>
              <button className="danger" onClick={async () => { await api(`/models/${m.id}`, { method: "DELETE" }); await load(); }}>Remove</button>
            </li>
          ))}
        </ul>
      )}
      <p className="small muted">
        This month: {info.month.calls} call(s), ${Number(info.month.own).toFixed(4)} on your own key
        {info.included ? `, $${Number(info.month.platform).toFixed(4)} of included credit` : ""}. A single question is refused
        if it would cost more than ${info.caps.per_task}.
      </p>
      <form onSubmit={submit} className="card stack">
        <strong>Connect a model</strong>
        <div className="cols">
          <label className="field">Name <input type="text" name="label" placeholder="e.g. DeepSeek on DeepInfra" required /></label>
          <label className="field">Model id <input type="text" name="model" placeholder="as your provider names it" required /></label>
        </div>
        <label className="field">Address (ends in /v1 for most providers) <input type="text" name="base_url" placeholder="https://…/v1  or  http://localhost:11434/v1" required /></label>
        <label className="field">API key (leave empty for a local model) <input type="password" name="api_key" autoComplete="off" /></label>
        <div className="cols">
          <label className="field">Price per 1M input tokens, USD <input type="text" name="price_in" inputMode="decimal" placeholder="0" /></label>
          <label className="field">Price per 1M output tokens, USD <input type="text" name="price_out" inputMode="decimal" placeholder="0" /></label>
        </div>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <button className="primary">Connect</button>
          <button type="button" onClick={() => add({ label: "Built-in test model (not an AI)", base_url: info.test_model_url, model: "extractive" })}>
            Use the built-in test model
          </button>
        </div>
        <p className="small muted">
          Prices are used to show what you spent and to enforce the per-question limit; enter what your provider charges.
          The built-in test model is not an AI: it quotes the first sentence of the best-matching passage, so you can try
          the flow at no cost before adding a key.
        </p>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </>
  );
}

function Tokens() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [label, setLabel] = useState("");
  const [canAsk, setCanAsk] = useState(false);
  const [fresh, setFresh] = useState<string | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => setTokens(await api<Token[]>("/tokens")), []);
  useEffect(() => { load().catch((err) => setError((err as Error).message)); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const created = await api<{ token: string }>("/tokens", { method: "POST", body: { label, can_ask: canAsk } });
      setFresh(created.token);
      setLabel("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <h2>Browser extension</h2>
      <p className="empty">
        The notepad signs in with a token. By default a token can only add captures to your inbox and read your company
        names. Tick the box to let that browser also ask questions and show the answers, which quote your notes and
        documents. Revoke a token here and it stops working at once.
      </p>
      <form onSubmit={create} className="stack">
        <div className="row">
          <input type="text" placeholder="Name this browser, e.g. MacBook Chrome" value={label} maxLength={80}
            onChange={(e) => setLabel(e.target.value)} required />
          <button className="primary">Create token</button>
        </div>
        <label><input type="checkbox" checked={canAsk} onChange={(e) => setCanAsk(e.target.checked)} /> Allow this browser to ask questions and read answers</label>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {fresh && (
        <div className="version" role="status">
          <strong>Copy this token now. It will not be shown again.</strong>
          <div className="row" style={{ marginTop: ".5rem" }}>
            <input type="text" readOnly value={fresh} aria-label="New token" onFocus={(e) => e.target.select()} />
            <button onClick={() => navigator.clipboard.writeText(fresh)}>Copy</button>
            <button className="link" onClick={() => setFresh(null)}>Done</button>
          </div>
        </div>
      )}
      {tokens.length === 0 ? <p className="empty">No tokens yet.</p> : (
        <ul className="list" style={{ marginTop: ".8rem" }}>
          {tokens.map((t) => (
            <li key={t.id}>
              <span>{t.label}</span>
              <span className="muted small">{t.can_ask ? "captures and questions" : "captures only"}</span>
              <small>
                {t.revoked_at ? `revoked ${when(t.revoked_at)}`
                  : t.last_used_at ? `last used ${when(t.last_used_at)}` : `created ${when(t.created_at)}, never used`}
              </small>
              {!t.revoked_at && (
                <button className="danger" onClick={async () => {
                  if (!window.confirm(`Revoke “${t.label}”? That browser will stop working with Invest-pad.`)) return;
                  await api(`/tokens/${t.id}`, { method: "DELETE" });
                  await load();
                }}>Revoke</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
