"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Token, when } from "@/lib/api";

export default function Settings() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [label, setLabel] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => setTokens(await api<Token[]>("/tokens")), []);
  useEffect(() => { load().catch((err) => setError((err as Error).message)); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const created = await api<{ token: string }>("/tokens", { method: "POST", body: { label } });
      setFresh(created.token);
      setLabel("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <h1>Settings</h1>
      <h2>Browser extension</h2>
      <p className="empty">
        The extension signs in with a token. A token can only add captures to your inbox and read your company
        names. It cannot read your notes. Revoke one here and it stops working at once.
      </p>
      <form onSubmit={create} className="row">
        <input type="text" placeholder="Name this browser, e.g. MacBook Chrome" value={label} maxLength={80}
          onChange={(e) => setLabel(e.target.value)} required />
        <button className="primary">Create token</button>
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
      <h2>Tokens</h2>
      {tokens.length === 0 ? <p className="empty">No tokens yet.</p> : (
        <ul className="list">
          {tokens.map((t) => (
            <li key={t.id}>
              <span>{t.label}</span>
              <small>
                {t.revoked_at ? `revoked ${when(t.revoked_at)}`
                  : t.last_used_at ? `last used ${when(t.last_used_at)}` : `created ${when(t.created_at)}, never used`}
              </small>
              {!t.revoked_at && (
                <button className="danger" onClick={async () => {
                  if (!window.confirm(`Revoke “${t.label}”? That browser will stop sending captures.`)) return;
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
