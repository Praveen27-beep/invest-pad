"use client";

/**
 * Thesis versions, events and evaluations for one company (FE 16; BE 11, 14, 15).
 *
 * NOTHING IS CALCULATED HERE. Status and draft reasons come from the server's classifier, the
 * commitment in force from its selector, and every trigger state from its deterministic
 * engine. UNKNOWN and CONFLICT are shown as themselves, with reason codes, and never styled
 * like success. No date, window or threshold is computed in the browser.
 *
 * VERSIONS, NOT EDITS. "New version" submits a complete snapshot against the version you are
 * looking at; if someone saved first the server answers 409 and nothing is overwritten.
 * Every earlier version stays readable and can be compared side by side.
 *
 * AN OVERRIDE NEEDS A REASON AND ERASES NOTHING. It is recorded against one exact TRIGGERED
 * receipt, which stays TRIGGERED. No trade, sale, recommendation or price target exists here.
 */

import { useState } from "react";
import { useFetch } from "@trackr/core";
import {
  evaluateNow,
  istToday,
  paths,
  write,
  type Evaluation,
  type Page,
  type Rule,
  type RuleResult,
  type Thesis,
  type ThesisInput,
} from "@/lib/research-api";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

const PROSE: { key: "argument" | "anti_thesis" | "pre_mortem" | "intended_holding_period"; label: string }[] = [
  { key: "argument", label: "Argument" },
  { key: "anti_thesis", label: "Anti-thesis" },
  { key: "pre_mortem", label: "Pre-mortem" },
  { key: "intended_holding_period", label: "Intended holding period" },
];

const STATE_CHIP: Record<string, string> = {
  ACTIVE: "ws-chip--pos",
  DRAFT: "ws-chip--mute",
  RETIRED: "ws-chip--mute",
  NEEDS_REVIEW: "ws-chip--warn",
  TRIGGERED: "ws-chip--neg",
  NOT_TRIGGERED: "ws-chip--pos",
  UNKNOWN: "ws-chip--open",
  CONFLICT: "ws-chip--warn",
  MET: "ws-chip--neg",
  NOT_MET: "ws-chip--pos",
};

export function ThesisPanel({ isin, onChanged }: { isin: string; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const theses = useFetch<Page<Thesis>>(
    investorId ? paths.companyTheses(investorId, isin) : null,
    { limit: 100 },
    token
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string>("");
  const [editing, setEditing] = useState(false);

  const versions = theses.data?.items ?? [];
  // This company's own branch (other verified-alias branches are listed but not extended here).
  const ownBranch = versions.filter((t) => t.isin === isin);
  const latest = ownBranch.find((t) => t.is_latest) ?? null;
  const selected = versions.find((t) => t.id === selectedId) ?? latest ?? versions[0] ?? null;
  const compare = versions.find((t) => t.id === compareId) ?? null;

  function refresh() {
    theses.refetch();
    onChanged();
  }

  if (theses.loading) return <div className="ws-empty">Loading&hellip;</div>;
  if (theses.error) return <div className="ws-notice ws-notice--error">{theses.error}</div>;

  return (
    <div className="ws-stack">
      <div className="ws-panel">
        <div className="ws-panel-head">
          <h3>Versions</h3>
          <span className="ws-hint">newest first; every version kept as written</span>
        </div>
        {versions.length === 0 && <div className="ws-empty">No thesis yet.</div>}
        {versions.map((thesis) => (
          <button
            key={thesis.id}
            type="button"
            className="ws-row"
            style={{ border: 0, textAlign: "left", cursor: "pointer" }}
            aria-current={selected?.id === thesis.id ? "page" : undefined}
            onClick={() => {
              setSelectedId(thesis.id);
              setEditing(false);
            }}
          >
            <span className="ws-row-grow">
              <span className="ws-row-t">
                Version {thesis.version}
                {thesis.isin !== isin ? ` (branch ${thesis.isin})` : ""}
              </span>
              <span className="ws-row-m">
                formed {thesis.formed_on} &middot; this version {thesis.version_on} &middot; saved{" "}
                {thesis.recorded_at.slice(0, 10)}
              </span>
            </span>
            <span className={`ws-chip ${STATE_CHIP[thesis.display_status] ?? ""}`}>
              {thesis.display_status.replace("_", " ")}
            </span>
          </button>
        ))}
      </div>

      <div className="ws-form-actions">
        <button type="button" className="ws-btn ws-btn--primary" onClick={() => setEditing(true)} disabled={editing}>
          {latest ? `New version (from v${latest.version})` : "Write a thesis"}
        </button>
        {versions.length > 1 && selected && (
          <label className="ws-field" style={{ minWidth: 220 }}>
            <span className="ws-field-label">Compare with</span>
            <select className="ws-input" value={compareId} onChange={(e) => setCompareId(e.target.value)}>
              <option value="">No comparison</option>
              {versions
                .filter((t) => t.id !== selected.id)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    Version {t.version} ({t.isin})
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>

      {editing && (
        <div className="ws-panel">
          <ThesisForm isin={isin} base={latest} onCancel={() => setEditing(false)} onSaved={(saved) => { setEditing(false); setSelectedId(saved.id); refresh(); }} />
        </div>
      )}

      {selected && !editing && (
        compare ? (
          <div className="ws-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <ThesisVersion thesis={compare} />
            <ThesisVersion thesis={selected} />
          </div>
        ) : (
          <>
            <ThesisVersion thesis={selected} />
            {selected.is_latest && <EventForm thesis={selected} onSaved={refresh} />}
            {selected.status === "ACTIVE" && <Evaluations thesis={selected} onChanged={refresh} />}
          </>
        )
      )}
    </div>
  );
}

function RuleTable({ rules, title }: { rules: Rule[]; title: string }) {
  return (
    <div>
      <div className="ws-sechead">
        <h2>{title}</h2>
      </div>
      {rules.length === 0 ? (
        <div className="ws-empty">None stated.</div>
      ) : (
        <div className="ws-scroll-x">
          <table className="ws-rules">
            <thead>
              <tr>
                <th>Condition</th>
                <th>Metric</th>
                <th>Basis</th>
                <th>Test</th>
                <th>Periods</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.label}</td>
                  <td className="ws-mono">{rule.metric}</td>
                  <td>{rule.basis}</td>
                  <td className="ws-mono">
                    {rule.op} {rule.op.startsWith("IS_") ? "" : `${rule.threshold} ${rule.unit}`}
                  </td>
                  <td>
                    {rule.periods} &times; {rule.cadence.toLowerCase()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ThesisVersion({ thesis }: { thesis: Thesis }) {
  return (
    <div className="ws-panel" style={{ padding: "16px 18px" }}>
      <div className="ws-form-actions" style={{ marginBottom: 10 }}>
        <strong>Version {thesis.version}</strong>
        <span className={`ws-chip ${STATE_CHIP[thesis.display_status] ?? ""}`}>{thesis.display_status.replace("_", " ")}</span>
        <span className="ws-hint">
          formed {thesis.formed_on} &middot; version dated {thesis.version_on}
        </span>
      </div>
      {thesis.draft_reasons.length > 0 && (
        <div className="ws-notice ws-notice--open">
          Saved as a draft because:{" "}
          {thesis.draft_reasons.map((r) => `${r.field.replace(/_/g, " ")} ${r.code.toLowerCase()}`).join(", ")}
        </div>
      )}
      {PROSE.map(({ key, label }) => (
        <div key={key} style={{ marginTop: 12 }}>
          <div className="ws-field-label">{label}</div>
          {thesis[key].trim() ? <p className="ws-verbatim">{thesis[key]}</p> : <p className="ws-muted">Not written.</p>}
        </div>
      ))}
      <RuleTable rules={thesis.variables} title="Variables to watch" />
      <RuleTable rules={thesis.exits} title="Exit conditions" />
      {thesis.events.length > 0 && (
        <>
          <div className="ws-sechead">
            <h2>Decisions and reviews</h2>
          </div>
          {thesis.events.map((event) => (
            <div key={event.id} className="ws-row">
              <span className="ws-row-grow">
                <span className="ws-row-t">
                  {event.kind === "OVERRIDE_EXIT_TRIGGER"
                    ? "Held through a triggered exit"
                    : event.kind === "CONVICTION"
                      ? `Conviction: ${event.conviction?.toLowerCase().replace("_", " ")}`
                      : "Reviewed"}
                </span>
                <p className="ws-verbatim ws-row-m">{event.reason}</p>
                <span className="ws-row-m">
                  {event.occurred_on} &middot; recorded {event.recorded_at.slice(0, 10)}
                </span>
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

const EMPTY_RULE: Rule = {
  id: "",
  label: "",
  metric: "",
  basis: "consolidated",
  unit: "",
  op: "LT",
  threshold: "",
  cadence: "QUARTER",
  periods: "1",
};

function RuleEditor({ rules, onChange, label }: { rules: Rule[]; onChange: (rules: Rule[]) => void; label: string }) {
  const set = (i: number, patch: Partial<Rule>) => onChange(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div>
      <div className="ws-field-label" style={{ marginBottom: 6 }}>{label}</div>
      {rules.map((rule, i) => (
        <div key={i} className="ws-form-row" style={{ marginBottom: 8 }}>
          <input className="ws-input ws-mono" placeholder="id" value={rule.id} onChange={(e) => set(i, { id: e.target.value })} />
          <input className="ws-input" placeholder="label" value={rule.label} onChange={(e) => set(i, { label: e.target.value })} />
          <input className="ws-input ws-mono" placeholder="metric" value={rule.metric} onChange={(e) => set(i, { metric: e.target.value })} />
          <input className="ws-input" placeholder="basis" value={rule.basis} onChange={(e) => set(i, { basis: e.target.value })} />
          <input className="ws-input" placeholder="unit" value={rule.unit} onChange={(e) => set(i, { unit: e.target.value })} />
          <select className="ws-input" value={rule.op} onChange={(e) => {
            const op = e.target.value as Rule["op"];
            set(i, { op, threshold: op.startsWith("IS_") ? "boolean" : rule.threshold === "boolean" ? "" : rule.threshold });
          }}>
            {["LT", "LE", "EQ", "GE", "GT", "IS_TRUE", "IS_FALSE"].map((op) => <option key={op}>{op}</option>)}
          </select>
          <input className="ws-input ws-mono" placeholder="threshold, e.g. 10.5" value={rule.threshold} disabled={rule.op.startsWith("IS_")} onChange={(e) => set(i, { threshold: e.target.value })} />
          <select className="ws-input" value={rule.cadence} onChange={(e) => set(i, { cadence: e.target.value as Rule["cadence"], periods: e.target.value === "POINT" ? "1" : rule.periods })}>
            <option>QUARTER</option>
            <option>YEAR</option>
            <option>POINT</option>
          </select>
          <input className="ws-input" placeholder="periods" value={rule.periods} disabled={rule.cadence === "POINT"} onChange={(e) => set(i, { periods: e.target.value })} />
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => onChange(rules.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => onChange([...rules, { ...EMPTY_RULE }])}>
        Add condition
      </button>
    </div>
  );
}

function ThesisForm({
  isin,
  base,
  onSaved,
  onCancel,
}: {
  isin: string;
  base: Thesis | null;
  onSaved: (thesis: Thesis) => void;
  onCancel: () => void;
}) {
  const { investorId, token } = useResearchAuth();
  const [prose, setProse] = useState({
    argument: base?.argument ?? "",
    anti_thesis: base?.anti_thesis ?? "",
    pre_mortem: base?.pre_mortem ?? "",
    intended_holding_period: base?.intended_holding_period ?? "",
  });
  const [variables, setVariables] = useState<Rule[]>(base?.variables ?? []);
  const [exits, setExits] = useState<Rule[]>(base?.exits ?? []);
  const [formedOn, setFormedOn] = useState(base?.formed_on ?? istToday());
  const [versionOn, setVersionOn] = useState(istToday());
  const { submit, pending, error } = useSubmit<{ thesis: Thesis }>();

  const body = (intent: "SAVE" | "RETIRE"): ThesisInput => ({
    intent,
    expected_version: base?.version ?? 0,
    formed_on: formedOn,
    version_on: versionOn,
    ...prose,
    variables,
    exits,
  });

  async function save(intent: "SAVE" | "RETIRE") {
    const payload = body(intent);
    const saved = await submit(payload, (key) => {
      const ctx = { investorId, token, idempotencyKey: key };
      return base ? write.createThesisVersion(ctx, base.id, payload) : write.createThesis(ctx, isin, payload);
    });
    if (saved) onSaved(saved.thesis);
  }

  const fields = error && "fields" in error ? (error as { fields?: Record<string, unknown> }).fields : undefined;
  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={(e) => { e.preventDefault(); void save("SAVE"); }}>
      <p className="ws-row-m">
        {base
          ? `A complete new version after v${base.version}. Version ${base.version} stays exactly as it is.`
          : "Your own words. Anything left blank is saved as a draft with the reason stated."}
      </p>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Formed on</span>
          <input className="ws-input" type="date" value={formedOn} disabled={Boolean(base)} onChange={(e) => setFormedOn(e.target.value)} />
          {base && <span className="ws-field-hint">fixed by the first version</span>}
        </label>
        <label className="ws-field">
          <span className="ws-field-label">This version dated</span>
          <input className="ws-input" type="date" value={versionOn} onChange={(e) => setVersionOn(e.target.value)} />
        </label>
      </div>
      {PROSE.map(({ key, label }) => (
        <label key={key} className="ws-field">
          <span className="ws-field-label">{label}</span>
          <textarea className="ws-textarea" value={prose[key]} onChange={(e) => setProse((p) => ({ ...p, [key]: e.target.value }))} />
        </label>
      ))}
      <RuleEditor label="Variables to watch" rules={variables} onChange={setVariables} />
      <RuleEditor label="Exit conditions" rules={exits} onChange={setExits} />
      {error && (
        <div className="ws-notice ws-notice--error">
          {describeError(error)}
          {fields && Object.keys(fields).length > 0 && (
            <ul>
              {Object.entries(fields).map(([k, v]) => (
                <li key={k} className="ws-mono">{k}: {String(v)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="ws-form-actions">
        <button type="submit" className="ws-btn ws-btn--primary" disabled={pending}>
          {pending ? "Saving…" : "Save version"}
        </button>
        {base && base.status !== "RETIRED" && (
          <button type="button" className="ws-btn" disabled={pending} onClick={() => void save("RETIRE")}>
            Retire this thesis
          </button>
        )}
        <button type="button" className="ws-btn ws-btn--ghost" onClick={onCancel}>Discard</button>
        <span className="ws-hint">Retiring records a decision; it does not sell anything.</span>
      </div>
    </form>
  );
}

function EventForm({ thesis, onSaved }: { thesis: Thesis; onSaved: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [kind, setKind] = useState<"CONVICTION" | "REVIEWED">("REVIEWED");
  const [conviction, setConviction] = useState("MEDIUM");
  const [reason, setReason] = useState("");
  const [occurredOn, setOccurredOn] = useState(istToday());
  const { submit, pending, error } = useSubmit<unknown>();

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = { kind, conviction: kind === "CONVICTION" ? conviction : null, reason, occurred_on: occurredOn };
    const saved = await submit(body, (key) => write.thesisEvent({ investorId, token, idempotencyKey: key }, thesis.id, body));
    if (saved) {
      setReason("");
      onSaved();
    }
  }

  return (
    <div className="ws-panel">
      <div className="ws-panel-head">
        <h3>Record a review or your conviction</h3>
        <span className="ws-hint">stated by you, with a reason; never computed</span>
      </div>
      <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
        <div className="ws-form-row">
          <select className="ws-input" value={kind} onChange={(e) => setKind(e.target.value as "CONVICTION" | "REVIEWED")}>
            <option value="REVIEWED">Reviewed</option>
            <option value="CONVICTION">Conviction</option>
          </select>
          {kind === "CONVICTION" && (
            <select className="ws-input" value={conviction} onChange={(e) => setConviction(e.target.value)}>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
              <option value="UNDER_REVIEW">Under review</option>
            </select>
          )}
          <input className="ws-input" type="date" value={occurredOn} onChange={(e) => setOccurredOn(e.target.value)} />
        </div>
        <textarea className="ws-textarea" required placeholder="Why" value={reason} onChange={(e) => setReason(e.target.value)} />
        {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
        <div className="ws-form-actions">
          <button type="submit" className="ws-btn ws-btn--sm" disabled={pending || !reason.trim()}>
            {pending ? "Saving…" : "Record"}
          </button>
        </div>
      </form>
    </div>
  );
}

function RuleResults({ results, title }: { results: RuleResult[]; title: string }) {
  if (results.length === 0) return null;
  return (
    <div>
      <div className="ws-field-label" style={{ margin: "10px 0 4px" }}>{title}</div>
      <div className="ws-scroll-x">
        <table className="ws-rules">
          <thead>
            <tr>
              <th>Condition</th>
              <th>State</th>
              <th>Latest value</th>
              <th>Windows</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={`${r.kind}:${r.rule_id}`}>
                <td className="ws-mono">{r.rule_id}</td>
                <td>
                  <span className={`ws-chip ${STATE_CHIP[r.state] ?? ""}`}>{r.state.replace("_", " ")}</span>
                  {r.met_on && <div className="ws-row-m">met on {r.met_on}</div>}
                </td>
                <td className="ws-mono">{r.latest === null ? "--" : String(r.latest)}</td>
                <td>
                  {r.windows.length === 0
                    ? "--"
                    : r.windows.map((w) => (
                        <div key={w.period_start} className="ws-row-m">
                          {w.period_start}&ndash;{w.period_end}: {w.state === "VALUE" ? String(w.value) : w.state.toLowerCase()}
                          {w.reason ? ` (${w.reason.toLowerCase().replace(/_/g, " ")})` : ""}
                        </div>
                      ))}
                </td>
                <td className="ws-row-m">{r.reason_codes.map((c) => c.toLowerCase().replace(/_/g, " ")).join(", ") || "--"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EvaluationView({ evaluation }: { evaluation: Evaluation }) {
  return (
    <div style={{ padding: "12px 18px" }}>
      <div className="ws-form-actions">
        <span className={`ws-chip ${STATE_CHIP[evaluation.state] ?? ""}`}>{evaluation.state.replace("_", " ")}</span>
        <span className="ws-hint">
          evidence known by {evaluation.evidence_cutoff.slice(0, 16).replace("T", " ")} UTC
          {evaluation.evaluated_at ? ` · recorded ${evaluation.evaluated_at.slice(0, 10)}` : " · not stored"}
        </span>
      </div>
      {evaluation.state === "UNKNOWN" && (
        <p className="ws-row-m">
          Not enough approved, verified evidence to decide. This is not a pass: see the reasons below.
        </p>
      )}
      <RuleResults title="Exit conditions" results={evaluation.exits} />
      <RuleResults title="Variables" results={evaluation.variables} />
      {evaluation.replay && (
        <p className="ws-row-m">Replay from pinned inputs: {evaluation.replay.status.toLowerCase()} {evaluation.replay.reasons.join(", ")}</p>
      )}
    </div>
  );
}

function Evaluations({ thesis, onChanged }: { thesis: Thesis; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const history = useFetch<Page<Evaluation>>(investorId ? paths.thesisEvaluations(investorId, thesis.id) : null, { limit: 20 }, token);
  const [preview, setPreview] = useState<Evaluation | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const record = useSubmit<Evaluation>();

  async function check() {
    setChecking(true);
    setPreviewError(null);
    try {
      setPreview(await evaluateNow(investorId, token, thesis.id, new Date().toISOString()));
    } catch (err) {
      setPreviewError(describeError(err as Error));
    } finally {
      setChecking(false);
    }
  }

  async function store() {
    // Record the SAME cutoff that was just checked, so the receipt is the result shown.
    if (!preview) return;
    const at = preview.evidence_cutoff;
    const saved = await record.submit({ thesis: thesis.id, at }, (key) =>
      write.recordEvaluation({ investorId, token, idempotencyKey: key }, thesis.id, at)
    );
    if (saved) {
      setPreview(null);
      history.refetch();
      onChanged();
    }
  }

  return (
    <div className="ws-panel">
      <div className="ws-panel-head">
        <h3>Your exit conditions, checked</h3>
        <span className="ws-hint">computed by the server from verified facts only</span>
      </div>
      <div className="ws-form">
        <div className="ws-form-actions">
          <button type="button" className="ws-btn" onClick={() => void check()} disabled={checking}>
            {checking ? "Checking…" : "Check now"}
          </button>
          {preview && (
            <button type="button" className="ws-btn ws-btn--primary" onClick={() => void store()} disabled={record.pending}>
              {record.pending ? "Recording…" : "Record this result"}
            </button>
          )}
          <span className="ws-hint">checking stores nothing; recording keeps a replayable receipt</span>
        </div>
        {previewError && <div className="ws-notice ws-notice--error">{previewError}</div>}
        {record.error && <div className="ws-notice ws-notice--error">{describeError(record.error)}</div>}
      </div>
      {preview && <EvaluationView evaluation={preview} />}
      <div className="ws-panel-head">
        <h3>Recorded evaluations</h3>
        <span className="ws-hint">kept whatever they said, including unknown and conflicting</span>
      </div>
      {history.data?.items.length === 0 && <div className="ws-empty">None recorded.</div>}
      {history.data?.items.map((evaluation) => (
        <div key={evaluation.id ?? evaluation.input_digest}>
          <EvaluationView evaluation={evaluation} />
          {evaluation.state === "TRIGGERED" && evaluation.id && (
            <OverrideForm thesis={thesis} evaluationId={evaluation.id} onSaved={() => { history.refetch(); onChanged(); }} />
          )}
        </div>
      ))}
    </div>
  );
}

function OverrideForm({ thesis, evaluationId, onSaved }: { thesis: Thesis; evaluationId: string; onSaved: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [reason, setReason] = useState("");
  const [occurredOn, setOccurredOn] = useState(istToday());
  const [open, setOpen] = useState(false);
  const { submit, pending, error } = useSubmit<unknown>();
  const already = thesis.events.some((e) => e.kind === "OVERRIDE_EXIT_TRIGGER" && e.evaluation_id === evaluationId);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = { evaluation_id: evaluationId, reason, occurred_on: occurredOn };
    const saved = await submit(body, (key) => write.overrideTrigger({ investorId, token, idempotencyKey: key }, thesis.id, body));
    if (saved) {
      setOpen(false);
      onSaved();
    }
  }

  if (already) return <p className="ws-hint" style={{ padding: "0 18px 12px" }}>You recorded an override for this trigger; it remains triggered.</p>;
  if (!open) {
    return (
      <div className="ws-form-actions" style={{ padding: "0 18px 12px" }}>
        <button type="button" className="ws-btn ws-btn--sm" onClick={() => setOpen(true)}>Hold through this trigger&hellip;</button>
      </div>
    );
  }
  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
      <textarea className="ws-textarea" required placeholder="Why you are holding despite your own exit condition" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="ws-form-actions">
        <input className="ws-input" type="date" value={occurredOn} onChange={(e) => setOccurredOn(e.target.value)} style={{ maxWidth: 170 }} />
        <button type="submit" className="ws-btn ws-btn--sm" disabled={pending || !reason.trim()}>
          {pending ? "Recording…" : "Record override"}
        </button>
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setOpen(false)}>Discard</button>
        <span className="ws-hint">The trigger stays on record; this adds your decision beside it.</span>
      </div>
      {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
    </form>
  );
}
