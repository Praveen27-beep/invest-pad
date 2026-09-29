"use client";

/**
 * Agents (FE 17 over BE 19 + BE 23): which model, at which endpoint, running which method.
 *
 * TWO DIFFERENT THINGS ON ONE SCREEN, AND THEY ARE KEPT APART.
 *   - The CONFIGURATION is saved to Trackr+: name, provider, model, endpoint, role and the exact
 *     method version. It has no key and no "connected" field, because the server cannot know.
 *     Every change is a new version; old tasks keep citing the version they ran.
 *   - The KEY is held only in this browser tab's memory, for this login, investor, configuration
 *     version and endpoint. It is never sent to Trackr+, never persisted, and is gone on reload
 *     or logout. "Test connection" is a request from THIS browser straight to the endpoint; its
 *     result is shown here and stored nowhere.
 */

import { useState } from "react";
import { useAuth, useFetch } from "@trackr/core";
import {
  rpaths,
  rwrite,
  type Agent,
  type AgentInput,
  type Page,
  type Provider,
  type Skill,
} from "@/lib/research-client";
import {
  clearKey,
  destinationAllowed,
  hasKey,
  scopeFor,
  setKey,
  testConnection,
  type ConnectionResult,
} from "@/lib/research-agent";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

const DEFAULT_URL: Record<Provider, string> = {
  ANTHROPIC: "https://api.anthropic.com",
  OPENAI_COMPATIBLE: "https://api.openai.com/v1",
};

function AgentForm({
  skills,
  base,
  onSaved,
}: {
  skills: Skill[];
  base?: Agent;
  onSaved: () => void;
}) {
  const { investorId, token } = useResearchAuth();
  const [input, setInput] = useState<AgentInput>(
    base
      ? {
          name: base.name,
          provider: base.provider,
          model: base.model,
          base_url: base.base_url,
          role_description: base.role_description,
          skill_id: base.skill_id,
          skill_version: base.skill_version,
          enabled: base.enabled,
        }
      : {
          name: "",
          provider: "ANTHROPIC",
          model: "",
          base_url: DEFAULT_URL.ANTHROPIC,
          role_description: "",
          skill_id: "",
          skill_version: 0,
          enabled: true,
        }
  );
  const { submit, pending, error } = useSubmit<Agent>();
  const set = (patch: Partial<AgentInput>) => setInput({ ...input, ...patch });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const ctx = (key: string) => ({ investorId, token, idempotencyKey: key });
    const saved = base
      ? await submit({ ...input, v: base.version }, (key) => rwrite.appendAgentVersion(ctx(key), base.id, input, base.version))
      : await submit(input, (key) => rwrite.createAgent(ctx(key), input));
    if (saved) onSaved();
  }

  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Name</span>
          <input className="ws-input" value={input.name} onChange={(e) => set({ name: e.target.value })} required />
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Protocol</span>
          <select
            className="ws-input"
            value={input.provider}
            onChange={(e) => {
              const provider = e.target.value as Provider;
              set({ provider, base_url: DEFAULT_URL[provider] });
            }}
          >
            <option value="ANTHROPIC">Anthropic Messages</option>
            <option value="OPENAI_COMPATIBLE">OpenAI-compatible chat completions</option>
          </select>
        </label>
      </div>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Model id (exactly as your provider names it)</span>
          <input className="ws-input ws-mono" value={input.model} onChange={(e) => set({ model: e.target.value })} required />
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Endpoint (https, no key, no query)</span>
          <input className="ws-input ws-mono" value={input.base_url} onChange={(e) => set({ base_url: e.target.value })} required />
          {!destinationAllowed(input.base_url) && (
            <span className="ws-field-hint">This app&apos;s content policy does not allow this origin; runs will be blocked.</span>
          )}
        </label>
      </div>
      <label className="ws-field">
        <span className="ws-field-label">Method (exact published version)</span>
        <select
          className="ws-input"
          value={input.skill_id ? `${input.skill_id}:${input.skill_version}` : ""}
          onChange={(e) => {
            const [id, v] = e.target.value.split(":");
            set({ skill_id: id ?? "", skill_version: Number(v) });
          }}
          required
        >
          <option value="">choose…</option>
          {skills
            .filter((s) => s.enabled)
            .map((s) => (
              <option key={`${s.id}:${s.version}`} value={`${s.id}:${s.version}`}>
                {s.name} v{s.version}
              </option>
            ))}
        </select>
      </label>
      <label className="ws-field">
        <span className="ws-field-label">Role description</span>
        <textarea className="ws-input" rows={2} value={input.role_description} onChange={(e) => set({ role_description: e.target.value })} required />
      </label>
      <label className="ws-check">
        <input type="checkbox" checked={input.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> Enabled
        (your choice; it says nothing about whether a key works)
      </label>
      <button type="submit" className="ws-btn ws-btn--primary" disabled={pending}>
        {base ? `Save as version ${base.version + 1}` : "Save configuration"}
      </button>
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
    </form>
  );
}

function LocalKey({ agent }: { agent: Agent }) {
  const { investorId } = useResearchAuth();
  const { user } = useAuth();
  const [value, setValue] = useState("");
  const [held, setHeld] = useState(false);
  const [result, setResult] = useState<ConnectionResult | null>(null);
  const [testing, setTesting] = useState(false);
  if (!user) return null;
  const scope = scopeFor(String(user.id), investorId, agent);
  const present = held || hasKey(scope);

  return (
    <div className="ws-local-key">
      <div className="ws-field-label">Key in this browser (memory only, this tab)</div>
      {present ? (
        <div className="ws-form-row">
          <span className="ws-chip">held locally</span>
          <button
            type="button"
            className="ws-btn ws-btn--ghost ws-btn--sm"
            disabled={testing}
            onClick={async () => {
              setTesting(true);
              setResult(await testConnection(scope, agent));
              setTesting(false);
            }}
          >
            {testing ? "Testing…" : "Test connection"}
          </button>
          <button
            type="button"
            className="ws-btn ws-btn--ghost ws-btn--sm"
            onClick={() => {
              clearKey(scope);
              setHeld(false);
              setResult(null);
            }}
          >
            Forget key
          </button>
        </div>
      ) : (
        <form
          className="ws-form-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!value.trim()) return;
            setKey(scope, value.trim());
            setValue("");
            setHeld(true);
          }}
        >
          <input
            className="ws-input ws-mono"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="Paste your provider key"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <button type="submit" className="ws-btn ws-btn--ghost ws-btn--sm">
            Hold for this tab
          </button>
        </form>
      )}
      {result && (
        <p className={result.ok ? "ws-muted" : "ws-notice ws-notice--error"}>
          {result.message} (checked {new Date(result.checkedAt).toLocaleTimeString()}, this browser only)
        </p>
      )}
    </div>
  );
}

export default function Agents() {
  const { investorId, token } = useResearchAuth();
  const agents = useFetch<Page<Agent>>(investorId ? rpaths.agents(investorId) : null, { limit: 100 }, token);
  const skills = useFetch<Page<Skill>>(investorId ? rpaths.skills(investorId) : null, { history: true, limit: 100 }, token);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div>
      <div className="ws-crumb">Research &middot; Agents</div>
      <h1 className="ws-h1">Agents</h1>
      <p className="ws-sub">
        Model configurations you run from this browser with your own key. The key never reaches Trackr+;
        runs go straight from this browser to the endpoint you name.
      </p>
      {agents.errorDetail && <p className="ws-notice ws-notice--error">{describeError(agents.errorDetail)}</p>}
      <div className="ws-sechead">
        <h2>Configurations</h2>
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setCreating(!creating)}>
          {creating ? "Close" : "New agent"}
        </button>
      </div>
      {creating && (
        <AgentForm
          skills={skills.data?.items ?? []}
          onSaved={() => {
            setCreating(false);
            agents.refetch();
          }}
        />
      )}
      {(agents.data?.items ?? []).length === 0 && !creating && (
        <div className="ws-empty">No agents configured. Publish a method on the Skills page first.</div>
      )}
      {(agents.data?.items ?? []).map((a) => (
        <div key={a.id} className="ws-panel">
          <div className="ws-row">
            <span className="ws-row-grow">
              <span className="ws-row-t">
                {a.name} <span className="ws-muted">v{a.version}</span>
              </span>
              <span className="ws-row-m ws-mono">
                {a.provider.toLowerCase()} · {a.model} · {a.base_url}
              </span>
            </span>
            <span className="ws-chip">{a.enabled ? "enabled" : "disabled"}</span>
          </div>
          <LocalKey agent={a} />
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setEditing(editing === a.id ? null : a.id)}>
            {editing === a.id ? "Close" : "New version"}
          </button>
          {editing === a.id && (
            <AgentForm
              base={a}
              skills={skills.data?.items ?? []}
              onSaved={() => {
                setEditing(null);
                agents.refetch();
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
