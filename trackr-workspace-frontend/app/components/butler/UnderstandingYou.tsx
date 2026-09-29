"use client";

/**
 * Settings -> Butler -> Understanding you (BT 15; docs/BUTLER_INVESTOR_MEMORY.md sections 1-7).
 *
 * NEVER CONCEAL THAT PROFILING OCCURS. When learning is on, this view says so first, then lists
 * every stored observation with where it came from (you / code / model), its exact records,
 * its counterexamples and limits, and what it has been used for. When it is off, it says that
 * too, and nothing is being recorded.
 *
 * EVERY CONTROL IS HERE: turn on (with the full disclosure), change sources and the earliest
 * included date, pause, resume, turn off, dispute, disable, delete one observation, correct or
 * exclude one record, add your own description, export everything and delete the notebook.
 * None of them removes access to notes, theses, reviews or the portfolio.
 *
 * Product language: evolving, evidence-backed notes about saved research PROCESS. Never mind
 * reading, lie detection, a diagnosis or a judgement of the person.
 */

import { useState } from "react";
import { useFetch } from "@trackr/core";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import {
  CORRECTION_CODES,
  POLARITY_LABELS,
  STATUS_LABELS,
  exportNotebook,
  notebookPaths,
  notebookWrite,
  type Episode,
  type Notebook,
  type NotebookCatalogue,
  type Pattern,
  type SourceCategory,
} from "@/lib/notebook-client";

function EpisodeRow({ e, onChanged }: { e: Episode; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending, error } = useSubmit<unknown>();
  const [code, setCode] = useState("");
  async function act(action: "CORRECT_EPISODE" | "EXCLUDE_EPISODE") {
    const body = { action, target_id: e.id, correction_code: action === "CORRECT_EPISODE" ? code : null, note: null };
    if (await submit(body, (key) => notebookWrite.control({ investorId, token, idempotencyKey: key }, body))) onChanged();
  }
  return (
    <li className="ws-notebook-episode">
      <span className="ws-mono">{e.occurred_on}</span> · {e.anchor_kind.toLowerCase()} record · {POLARITY_LABELS[e.polarity]}
      <span className="ws-muted"> ({e.observation_code.toLowerCase().replace(/_/g, " ")}; built by code)</span>
      {e.corrected && <span className="ws-chip ws-chip--mute"> you corrected this: {e.correction_code?.toLowerCase().replace(/_/g, " ")}</span>}
      {!e.corrected && (
        <span className="ws-notebook-actions">
          <label>
            <span className="sr-only">Correction reason</span>
            <select className="ws-input ws-input--sm" value={code} onChange={(ev) => setCode(ev.target.value)} disabled={pending}>
              <option value="">Correct this record…</option>
              {CORRECTION_CODES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ws-btn ws-btn--sm" disabled={pending || !code} onClick={() => act("CORRECT_EPISODE")}>
            Save correction
          </button>
          <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => act("EXCLUDE_EPISODE")}>
            Exclude
          </button>
        </span>
      )}
      {error && <span className="ws-notice ws-notice--error">{describeError(error)}</span>}
    </li>
  );
}

export function PatternCard({ p, onChanged }: { p: Pattern; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending, error } = useSubmit<unknown>();
  const [note, setNote] = useState("");
  async function act(action: "DISPUTE" | "WITHDRAW_DISPUTE" | "DISABLE" | "ENABLE" | "DELETE") {
    if (action === "DELETE" && !window.confirm("Delete this observation? It cannot be rebuilt from the same records.")) return;
    const body = { action, target_id: p.pattern_id, correction_code: null, note: note.trim() || null };
    if (await submit(body, (key) => notebookWrite.control({ investorId, token, idempotencyKey: key }, body))) {
      setNote("");
      onChanged();
    }
  }
  return (
    <article className="ws-card ws-notebook-pattern" aria-label={p.text}>
      <p>{p.text}</p>
      <p className="ws-muted">
        {STATUS_LABELS[p.status] ?? p.status} · from {p.origin === "MODEL" ? "a model proposal checked by code" : "code"} · revision{" "}
        {p.revision} · checked {p.last_evaluated_at.slice(0, 10)}
        {p.positive ? " · an improvement" : ""}
        {p.used_for_coaching ? " · currently shapes one review question" : " · not used for questions"}
      </p>
      <p className="ws-muted">
        {p.counts.supporting} fitting, {p.counts.counter} counterexample{p.counts.counter === 1 ? "" : "s"}, {p.counts.undetermined} undecided, across{" "}
        {p.counts.distinct_dates} date{p.counts.distinct_dates === 1 ? "" : "s"} ({p.window.start} to {p.window.end}).
        {p.counts.denominator_known ? "" : " Not every opportunity is recorded, so no rate is stated."}
      </p>
      <details>
        <summary>Exact records ({p.supporting.length + p.counterexamples.length})</summary>
        <ul>
          {[...p.supporting, ...p.counterexamples].map((e) => (
            <EpisodeRow key={e.id} e={e} onChanged={onChanged} />
          ))}
        </ul>
      </details>
      {p.alternatives.length > 0 && (
        <details>
          <summary>Other explanations</summary>
          <ul>
            {p.alternatives.map((a) => (
              <li key={a.id}>{a.text}</li>
            ))}
          </ul>
        </details>
      )}
      {p.limitations.length > 0 && (
        <details>
          <summary>Limits</summary>
          <ul>
            {p.limitations.map((l) => (
              <li key={l.id}>{l.text}</li>
            ))}
          </ul>
        </details>
      )}
      {p.influence.length > 0 && (
        <details>
          <summary>Where it was used ({p.influence.length})</summary>
          <ul>
            {p.influence.map((u, i) => (
              <li key={i}>
                {u.recorded_at.slice(0, 10)} · question {u.question_id.toLowerCase().replace(/_/g, " ")} in a review
              </li>
            ))}
          </ul>
        </details>
      )}
      {p.user_notes.length > 0 && (
        <ul className="ws-muted">
          {p.user_notes.map((n, i) => (
            <li key={i}>
              You: {n.action.toLowerCase().replace(/_/g, " ")} {n.note ? `— “${n.note}”` : ""} ({n.recorded_at.slice(0, 10)})
            </li>
          ))}
        </ul>
      )}
      <label className="ws-field">
        <span className="ws-field-label">Your note (optional; never read as evidence about you)</span>
        <input className="ws-input" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} disabled={pending} />
      </label>
      <div className="ws-notebook-actions">
        {p.user_state.disputed ? (
          <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => act("WITHDRAW_DISPUTE")}>
            Withdraw disagreement
          </button>
        ) : (
          <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => act("DISPUTE")}>
            I disagree
          </button>
        )}
        <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => act(p.user_state.disabled ? "ENABLE" : "DISABLE")}>
          {p.user_state.disabled ? "Use for questions again" : "Don’t use for questions"}
        </button>
        <button type="button" className="ws-btn ws-btn--sm ws-btn--danger" disabled={pending} onClick={() => act("DELETE")}>
          Delete
        </button>
      </div>
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
    </article>
  );
}

function ConsentForm({ nb, cat, onChanged }: { nb: Notebook; cat: NotebookCatalogue; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending, error } = useSubmit<unknown>();
  const c = nb.consent;
  const [sources, setSources] = useState<SourceCategory[]>(c.sources.length ? c.sources : ["REVIEW_RESPONSES", "DECISION_RECEIPTS"]);
  const [backfill, setBackfill] = useState<string>(c.include_from ?? "");
  const [reflection, setReflection] = useState<boolean>(c.reflection_enabled);
  const [read, setRead] = useState(false);

  async function send(action: "OPT_IN" | "UPDATE_SCOPE" | "PAUSE" | "RESUME" | "REVOKE") {
    const scoped = action === "OPT_IN" || action === "UPDATE_SCOPE";
    const body = {
      action,
      expected_version: c.version,
      ...(scoped
        ? { disclosure_version: cat.disclosure_version, sources, include_from: backfill || null, reflection_enabled: reflection }
        : {}),
    };
    if (await submit(body, (key) => notebookWrite.consent({ investorId, token, idempotencyKey: key }, body))) onChanged();
  }
  const on = c.state === "ACTIVE" || c.state === "PAUSED";
  return (
    <section aria-labelledby="nb-consent">
      <h4 id="nb-consent" className="ws-field-label">
        Learning is {c.state === "ACTIVE" ? "on" : c.state === "PAUSED" ? "paused" : "off"}
      </h4>
      {c.state === "ACTIVE" && (
        <p>
          Butler is keeping private notes about your saved research process from {c.effective_include_from ?? "your opt-in"}. They can be
          wrong. Everything it keeps is listed below.
        </p>
      )}
      {!on && <p className="ws-muted">Nothing is being recorded. Your research and portfolio work the same either way.</p>}
      <blockquote className="ws-notebook-disclosure">{cat.disclosure_text}</blockquote>
      <fieldset className="ws-form" disabled={pending}>
        <legend className="ws-field-label">Include</legend>
        {cat.source_categories.map((s) => (
          <label key={s.id} className="ws-check">
            <input
              type="checkbox"
              checked={sources.includes(s.id)}
              onChange={(e) => setSources(e.target.checked ? [...sources, s.id] : sources.filter((x) => x !== s.id))}
            />{" "}
            {s.label}
          </label>
        ))}
        <label className="ws-field">
          <span className="ws-field-label">Also include records saved since (optional; leave empty to start from now)</span>
          <input className="ws-input" type="date" value={backfill} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setBackfill(e.target.value)} />
        </label>
        <label className="ws-check">
          <input type="checkbox" checked={reflection} onChange={(e) => setReflection(e.target.checked)} /> Also allow one bounded daily
          reflection by a hosted model (separate choice; within a fixed budget)
        </label>
        {!on && (
          <label className="ws-check">
            <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} /> I have read what Butler will keep
          </label>
        )}
      </fieldset>
      <div className="ws-notebook-actions">
        {!on && (
          <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={pending || !read || sources.length === 0} onClick={() => send("OPT_IN")}>
            Turn on learning
          </button>
        )}
        {c.state === "ACTIVE" && (
          <>
            <button type="button" className="ws-btn ws-btn--sm" disabled={pending || sources.length === 0} onClick={() => send("UPDATE_SCOPE")}>
              Save sources
            </button>
            <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => send("PAUSE")}>
              Pause learning
            </button>
          </>
        )}
        {c.state === "PAUSED" && (
          <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => send("RESUME")}>
            Resume learning
          </button>
        )}
        {on && (
          <button type="button" className="ws-btn ws-btn--sm" disabled={pending} onClick={() => send("REVOKE")}>
            Turn off learning
          </button>
        )}
      </div>
      {on && <p className="ws-muted">{cat.revocation_limit_text}</p>}
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
    </section>
  );
}

export function UnderstandingYou() {
  const { investorId, token } = useResearchAuth();
  const nbq = useFetch<Notebook>(investorId ? notebookPaths.view(investorId) : null, undefined, token);
  const catq = useFetch<NotebookCatalogue>(investorId ? notebookPaths.catalogue(investorId) : null, undefined, token);
  const selfSubmit = useSubmit<unknown>();
  const delSubmit = useSubmit<unknown>();
  const refreshSubmit = useSubmit<unknown>();
  const [statement, setStatement] = useState("");
  const [deleted, setDeleted] = useState<string | null>(null);
  const nb = nbq.data;
  const cat = catq.data;
  const reload = () => nbq.refetch();

  if (!nb || !cat) return <p className="ws-muted">{nbq.error ?? catq.error ?? "Loading…"}</p>;

  async function addSelf() {
    const body = { statement: statement.trim() };
    if (!body.statement) return;
    if (await selfSubmit.submit(body, (key) => notebookWrite.selfDescription({ investorId, token, idempotencyKey: key }, body))) {
      setStatement("");
      reload();
    }
  }
  async function download() {
    const data = await exportNotebook(investorId, token);
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "butler-notebook-export.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  async function deleteAll() {
    if (!window.confirm("Delete Butler's notebook? Learning turns off and every observation is removed. Your notes, theses, reviews and portfolio are not affected.")) return;
    const r = (await delSubmit.submit({ del: true }, (key) => notebookWrite.deleteAll({ investorId, token, idempotencyKey: key }))) as
      | { purge: { status: string }; note: string }
      | null;
    if (r) {
      setDeleted(r.purge.status === "HELD" ? "Hidden now; physical deletion is blocked by a legal hold. " + r.note : r.note);
      reload();
    }
  }
  async function refresh() {
    if (await refreshSubmit.submit({ refresh: true }, (key) => notebookWrite.refresh({ investorId, token, idempotencyKey: key }))) reload();
  }

  return (
    <section aria-labelledby="nb-title" className="ws-notebook">
      <h3 id="nb-title">Understanding you</h3>
      <p className="ws-muted">
        Private notes about how your saved research went — not about who you are. Butler is not a mind reader or a lie detector, and these
        notes never appear in company reports or anything you share.
      </p>
      <ConsentForm nb={nb} cat={cat} onChanged={reload} />

      <section aria-labelledby="nb-self">
        <h4 id="nb-self" className="ws-field-label">In your words</h4>
        <ul>
          {nb.self_descriptions.filter((d) => !d.superseded).map((d) => (
            <li key={d.id}>
              “{d.statement}” <span className="ws-muted">({d.recorded_at.slice(0, 10)}, you)</span>
            </li>
          ))}
        </ul>
        {nb.consent.state !== "NOT_SET" && (
          <div className="ws-form">
            <label className="ws-field">
              <span className="ws-field-label">Describe how you like to research (optional)</span>
              <input className="ws-input" value={statement} maxLength={1000} onChange={(e) => setStatement(e.target.value)} />
            </label>
            <button type="button" className="ws-btn ws-btn--sm" disabled={selfSubmit.pending || !statement.trim()} onClick={addSelf}>
              Save
            </button>
          </div>
        )}
      </section>

      <section aria-labelledby="nb-obs">
        <h4 id="nb-obs" className="ws-field-label">
          Observations ({nb.patterns.length}) · records looked at: {nb.episode_counts.total} ({nb.episode_counts.counters} counterexamples)
        </h4>
        <p className="ws-muted">{cat.heuristics.note}</p>
        {nb.patterns.length === 0 && <p className="ws-muted">No observations yet.</p>}
        {nb.patterns.map((p) => (
          <PatternCard key={p.pattern_id} p={p} onChanged={reload} />
        ))}
      </section>

      {nb.consent.reflection_enabled && (
        <section aria-labelledby="nb-refl">
          <h4 id="nb-refl" className="ws-field-label">Daily reflection</h4>
          {nb.reflection ? (
            <p className="ws-muted">
              Last: {nb.reflection.state.toLowerCase().replace(/_/g, " ")} ({nb.reflection.state_reason.toLowerCase().replace(/_/g, " ")}),{" "}
              {nb.reflection.recorded_at.slice(0, 10)}; spent at most {nb.reflection.spent_worst_case} of {nb.reflection.budget_limit}{" "}
              {nb.reflection.currency}.
            </p>
          ) : (
            <p className="ws-muted">No reflection has run.</p>
          )}
          <button type="button" className="ws-btn ws-btn--sm" disabled={refreshSubmit.pending} onClick={refresh}>
            Refresh understanding (once a day)
          </button>
          {refreshSubmit.error && <p className="ws-notice ws-notice--error">{describeError(refreshSubmit.error)}</p>}
        </section>
      )}

      <section aria-labelledby="nb-data">
        <h4 id="nb-data" className="ws-field-label">Your data</h4>
        <p className="ws-muted">{nb.retention.statement}</p>
        <div className="ws-notebook-actions">
          <button type="button" className="ws-btn ws-btn--sm" onClick={download}>
            Export notebook
          </button>
          <button type="button" className="ws-btn ws-btn--sm ws-btn--danger" disabled={delSubmit.pending} onClick={deleteAll}>
            Delete notebook
          </button>
        </div>
        {deleted && <p className="ws-notice">{deleted}</p>}
        {delSubmit.error && <p className="ws-notice ws-notice--error">{describeError(delSubmit.error)}</p>}
      </section>
    </section>
  );
}
