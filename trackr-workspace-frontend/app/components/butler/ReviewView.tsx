"use client";

/**
 * A decision review: one question at a time, the person's own answers, field-level states.
 *
 * THE ANSWER BOX IS NEVER PREFILLED. Not by a model, not by a template, not by a previous answer
 * -- a revision starts from the person's own saved text only when they choose to revise it. The
 * state shown beside each question is computed by the server from recorded facts; "Checked by
 * code" appears only for an approved date check, and attached evidence is labelled as attached,
 * never as sufficient.
 *
 * COMPLETION SAYS "REVIEW DOCUMENTED", never "approved". Every unresolved check has to be ticked
 * explicitly before the person can document the review with it open, and the server refuses the
 * completion if the pinned thesis or evidence changed underneath it (the person then starts a
 * superseding review that shows the differences).
 */

import { useEffect, useMemo, useState } from "react";
import { useFetch } from "@trackr/core";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { whyQuestion, type WhyQuestion } from "@/lib/notebook-client";
import { PatternCard } from "./UnderstandingYou";
import { paths, type Note, type Page as RPage, type Source } from "@/lib/research-api";
import {
  FIELD_STATE_LABELS,
  butlerPaths,
  butlerWrite,
  type Review,
  type ReviewChoice,
  type ReviewField,
} from "@/lib/butler-client";

const CHOICES: { value: ReviewChoice; label: string }[] = [
  { value: "CONTINUE", label: "Continue the research" },
  { value: "PAUSE", label: "Pause" },
  { value: "REVISE", label: "Revise my thesis" },
  { value: "MORE_INFORMATION", label: "Need more information" },
];

export function ReviewView({ reviewId, onBack }: { reviewId: string; onBack: () => void }) {
  const { investorId, token } = useResearchAuth();
  const review = useFetch<Review>(investorId ? butlerPaths.review(investorId, reviewId) : null, undefined, token);
  const [current, setCurrent] = useState<Review | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const supersede = useSubmit<Review>();

  useEffect(() => setCurrent(review.data ?? null), [review.data]);

  if (review.loading && !current) return <div className="ws-empty">Loading&hellip;</div>;
  if (review.error || !current) {
    return <div className="ws-notice ws-notice--error">{describeError(review.errorDetail) ?? review.error}</div>;
  }
  const r = current;
  const closed = r.status === "DOCUMENTED" || r.status === "SUPERSEDED";
  const target = focus ?? r.next?.question_id ?? null;

  async function startSuperseding() {
    if (!investorId) return;
    const body = { isin: r.isin, decision_kind: r.decision_kind, supersedes_review_id: r.id };
    const next = await supersede.submit(body, (key) =>
      butlerWrite.startReview({ investorId, token, idempotencyKey: key }, body)
    );
    if (next) setCurrent(next);
  }

  return (
    <div className="ws-butler-review">
      <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={onBack}>
        &larr; All reviews
      </button>
      <h3 className="ws-butler-card-title">
        {r.identity?.symbol ?? r.isin} &middot; {r.decision_kind.replaceAll("_", " ").toLowerCase()}
      </h3>
      <p className="ws-muted">
        Started {r.recorded_at.slice(0, 10)} &middot; checklist {r.checklist.version}
      </p>
      {r.pinned_thesis ? (
        <figure className="ws-butler-passage">
          <figcaption className="ws-muted">
            Your thesis version {r.pinned_thesis.version} ({r.pinned_thesis.version_on}), pinned for this review
            {r.pinned_thesis.intended_holding_period ? ` · holding period: ${r.pinned_thesis.intended_holding_period}` : ""}
          </figcaption>
          <blockquote>{r.pinned_thesis.argument_excerpt}</blockquote>
        </figure>
      ) : (
        <p className="ws-muted">No thesis is recorded for this company, so belief questions are not asked.</p>
      )}

      {r.stale && (
        <div className="ws-notice ws-notice--warn">
          <strong>Something changed since this review started.</strong>
          <ul>
            {r.differences.map((d, i) => (
              <li key={i}>
                {d.code === "THESIS_CHANGED"
                  ? `Your thesis moved from version ${d.from_version} to ${d.to_version}.`
                  : d.code === "SOURCE_RETRACTED"
                    ? "An attached source was marked retracted or corrected."
                    : d.code === "MEMORY_FORGOTTEN"
                      ? "An attached note was forgotten in Butler."
                      : d.code === "THESIS_ADDED"
                        ? "A thesis was recorded after this review started."
                        : "Attached evidence is no longer available."}
              </li>
            ))}
          </ul>
          <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={supersede.pending} onClick={startSuperseding}>
            Start a new review with the current records
          </button>
          {supersede.error && <div className="ws-notice ws-notice--error">{describeError(supersede.error)}</div>}
        </div>
      )}

      <ol className="ws-butler-fields">
        {r.fields.map((f) => (
          <li key={f.question_id} data-state={f.state}>
            <button
              type="button"
              className="ws-butler-field-head"
              aria-expanded={target === f.question_id}
              onClick={() => setFocus(target === f.question_id ? null : f.question_id)}
            >
              <span>{f.question_text}</span>
              <span className={`ws-chip ${f.resolved ? "ws-chip--pos" : f.state === "UNKNOWN" ? "ws-chip--neg" : "ws-chip--mute"}`}>
                {FIELD_STATE_LABELS[f.state]}
              </span>
            </button>
            {f.personalised && <WhyLink reviewId={r.id} questionId={f.question_id} />}
            {f.response && (
              <div className="ws-butler-answer">
                <blockquote>{f.response.answer || f.response.not_applicable_reason}</blockquote>
                <p className="ws-muted">
                  Your answer, recorded {f.response.recorded_at.slice(0, 10)}
                  {f.response.revision_ids.length > 1 ? ` · ${f.response.revision_ids.length} versions kept` : ""}
                  {f.response.milestone_on ? ` · milestone ${f.response.milestone_on}` : ""}
                  {f.code_check ? ` · date check ${f.code_check.result.toLowerCase().replace("_", " ")}` : ""}
                </p>
                {f.evidence.length > 0 && (
                  <ul className="ws-muted">
                    {f.evidence.map((e) => (
                      <li key={e.id}>
                        {e.available ? e.label ?? e.kind.toLowerCase() : `Unavailable (${(e.reason ?? "").toLowerCase().replaceAll("_", " ")})`}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {!closed && target === f.question_id && (
              <ResponseForm review={r} field={f} onSaved={(next) => { setCurrent(next); setFocus(null); }} />
            )}
          </li>
        ))}
      </ol>

      {r.next?.follow_up_text && !closed && <p className="ws-butler-question">{r.next.follow_up_text}</p>}

      {r.completion ? (
        <div className="ws-notice">
          <strong>{r.completion.statement}</strong>
          <p>
            Your choice: {CHOICES.find((c) => c.value === r.completion?.choice)?.label}
            {r.completion.reason ? ` — “${r.completion.reason}”` : ""}
          </p>
          {r.completion.unresolved.length > 0 && (
            <p className="ws-muted">Still unresolved: {r.completion.unresolved.join(", ").replaceAll("_", " ").toLowerCase()}</p>
          )}
        </div>
      ) : (
        !closed && !r.stale && <CompleteForm review={r} onSaved={setCurrent} />
      )}
    </div>
  );
}

function ResponseForm({ review, field, onSaved }: { review: Review; field: ReviewField; onSaved: (r: Review) => void }) {
  const { investorId, token } = useResearchAuth();
  // Never prefilled: an empty box, always. The saved answer is shown above, verbatim.
  const [answer, setAnswer] = useState("");
  const [attested, setAttested] = useState(false);
  const [notApplicable, setNotApplicable] = useState("");
  const [milestone, setMilestone] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const save = useSubmit<Review>();
  const sources = useFetch<RPage<Source>>(investorId ? paths.companySources(investorId, review.isin) : null, undefined, token);
  const notes = useFetch<RPage<Note>>(investorId ? paths.companyNotes(investorId, review.isin) : null, undefined, token);
  const options = useMemo(
    () => [
      ...(sources.data?.items ?? []).slice(0, 20).map((s) => ({ key: `s:${s.id}`, label: `${s.source} (${s.publication_date})` })),
      ...(notes.data?.items ?? []).slice(0, 20).map((n) => ({ key: `n:${n.id}`, label: `Note: ${n.title}` })),
    ],
    [sources.data, notes.data]
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!investorId) return;
    const body = {
      question_id: field.question_id,
      answer,
      attested,
      not_applicable_reason: notApplicable.trim() ? notApplicable : null,
      milestone_on: milestone || null,
      evidence: picked.map((k) => (k.startsWith("s:") ? { source_id: k.slice(2) } : { note_id: k.slice(2) })),
      expected_latest_response_id: field.response?.id ?? null,
    };
    const next = await save.submit(body, (key) =>
      butlerWrite.respond({ investorId, token, idempotencyKey: key }, review.id, body)
    );
    if (next) onSaved(next);
  }

  return (
    <form className="ws-butler-form" onSubmit={submit}>
      <label className="ws-field">
        <span>{field.response ? "Revise your answer (the earlier version is kept)" : "Your answer"}</span>
        <textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} />
      </label>
      {field.question_id === "NEXT_EVIDENCE_MILESTONE" && (
        <label className="ws-field">
          <span>Expected by (optional; lets the date be checked)</span>
          <input type="date" value={milestone} onChange={(e) => setMilestone(e.target.value)} />
        </label>
      )}
      {options.length > 0 && (
        <fieldset className="ws-field">
          <legend>Attach saved evidence (optional)</legend>
          {options.map((o) => (
            <label key={o.key} className="ws-check">
              <input
                type="checkbox"
                checked={picked.includes(o.key)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, o.key] : picked.filter((k) => k !== o.key))}
              />
              {o.label}
            </label>
          ))}
        </fieldset>
      )}
      <label className="ws-check">
        <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
        I stand behind this answer without further evidence (recorded as your attestation, not a check)
      </label>
      <label className="ws-field">
        <span>Or: why this question does not apply (optional)</span>
        <input type="text" value={notApplicable} onChange={(e) => setNotApplicable(e.target.value)} />
      </label>
      {save.error && <div className="ws-notice ws-notice--error">{describeError(save.error)}</div>}
      <button type="submit" className="ws-btn ws-btn--primary ws-btn--sm" disabled={save.pending || (!answer.trim() && !notApplicable.trim())}>
        {save.pending ? "Saving…" : "Save answer"}
      </button>
    </form>
  );
}

function CompleteForm({ review, onSaved }: { review: Review; onSaved: (r: Review) => void }) {
  const { investorId, token } = useResearchAuth();
  const [choice, setChoice] = useState<ReviewChoice | "">("");
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const save = useSubmit<Review>();
  const all = review.unresolved.every((q) => acknowledged.includes(q));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!investorId || !choice) return;
    const body = { choice, reason, acknowledged_unresolved: acknowledged.filter((q) => review.unresolved.includes(q)) };
    const next = await save.submit(body, (key) =>
      butlerWrite.complete({ investorId, token, idempotencyKey: key }, review.id, body)
    );
    if (next) onSaved(next);
  }

  return (
    <form className="ws-butler-form" onSubmit={submit}>
      <strong>Document this review</strong>
      <p className="ws-muted">
        This records your own choice. It is not an approval, creates no trade and does not change
        your thesis.
      </p>
      {review.unresolved.length > 0 && (
        <fieldset className="ws-field">
          <legend>These checks remain unresolved. Tick each to document the review with it open:</legend>
          {review.unresolved.map((q) => (
            <label key={q} className="ws-check">
              <input
                type="checkbox"
                checked={acknowledged.includes(q)}
                onChange={(e) => setAcknowledged(e.target.checked ? [...acknowledged, q] : acknowledged.filter((x) => x !== q))}
              />
              {review.fields.find((f) => f.question_id === q)?.question_text ?? q}
            </label>
          ))}
        </fieldset>
      )}
      <label className="ws-field">
        <span>Your choice</span>
        <select value={choice} onChange={(e) => setChoice(e.target.value as ReviewChoice)} required>
          <option value="">Select&hellip;</option>
          {CHOICES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className="ws-field">
        <span>Reason{review.unresolved.length ? " (required while checks are unresolved)" : " (optional)"}</span>
        <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {save.error && <div className="ws-notice ws-notice--error">{describeError(save.error)}</div>}
      <button
        type="submit"
        className="ws-btn ws-btn--primary ws-btn--sm"
        disabled={save.pending || !choice || !all || (review.unresolved.length > 0 && !reason.trim())}
      >
        {save.pending ? "Saving…" : "Document review"}
      </button>
    </form>
  );
}


/** "Why this question?" -- the exact notebook observation and records behind a personalised
 * question, in their CURRENT state, with the same correct/disagree/disable/delete controls. */
function WhyLink({ reviewId, questionId }: { reviewId: string; questionId: string }) {
  const { investorId, token } = useResearchAuth();
  const [why, setWhy] = useState<WhyQuestion | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function load() {
    try {
      setWhy(await whyQuestion(investorId, token, reviewId, questionId));
    } catch (e) {
      setErr(describeError(e instanceof Error ? e : new Error(String(e))));
    }
  }
  return (
    <div className="ws-butler-why">
      <button type="button" className="ws-btn ws-btn--sm ws-btn--link" aria-expanded={why !== null} onClick={() => (why ? setWhy(null) : load())}>
        Why this question?
      </button>
      {err && <p className="ws-notice ws-notice--error">{err}</p>}
      {why && (
        <div>
          <p className="ws-muted">{why.statement}</p>
          {why.pattern && <PatternCard p={why.pattern} onChanged={load} />}
          <p className="ws-muted">You can answer, mark it not applicable with a reason, or leave it open. Only attached evidence moves it past “answer recorded”.</p>
        </div>
      )}
    </div>
  );
}
