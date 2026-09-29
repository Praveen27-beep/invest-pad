"use client";

/**
 * One server-validated Butler card.
 *
 * RENDERS WHAT THE SERVER RENDERED, AS TEXT. Title, statements, passages, question and lesson
 * are strings the backend built from reviewed templates and re-read records; every one goes into
 * the DOM as a React text node. There is no `dangerouslySetInnerHTML`, no markdown parser and no
 * link auto-detection, so a filing that contains markup or an instruction is shown as the quoted
 * characters it is. A citation link is clickable only when the SERVER supplied an https `href`
 * from an authorised stored source.
 *
 * A WITHDRAWN card shows its fixed reason and nothing else -- never the text it used to carry.
 */

import { useState } from "react";
import type { Card } from "@/lib/butler-client";
import { WITHDRAWN_LABELS } from "@/lib/butler-client";

const BASIS_LABELS: Record<string, string> = {
  SOURCE_METADATA: "from saved source details",
  RECORDED_ACTIVITY: "count of records saved here",
  ENGINE_EVALUATION: "deterministic evaluation",
  USER_QUOTE: "your own words",
  SYSTEM_COVERAGE: "coverage statement",
  SYSTEM: "system",
  SOURCE_STATEMENT: "what a source states",
};

export interface CardActions {
  pending: boolean;
  onSeen?: () => void;
  onSnooze?: (days: number) => void;
  onDismiss?: () => void;
  onResolve?: () => void;
  onRestore?: () => void;
  onStartReview?: () => void;
}

export function CardView({ card, actions }: { card: Card; actions?: CardActions }) {
  const [showSources, setShowSources] = useState(false);
  const withdrawn = card.state === "WITHDRAWN";
  const company = card.identity.symbol ?? card.identity.name ?? card.isin;
  const closed = card.status.dismissed || card.status.resolved;

  return (
    <article className="ws-butler-card" data-state={card.state} data-priority={card.priority}>
      <header className="ws-butler-card-head">
        <span className="ws-chip ws-chip--mute">{company}</span>
        {card.priority === "REQUIRED" && <span className="ws-chip ws-chip--warn">Due</span>}
        {withdrawn && (
          <span className="ws-chip ws-chip--neg">
            {WITHDRAWN_LABELS[card.withdrawn_reason ?? ""] ?? "Withdrawn"}
          </span>
        )}
        {!card.status.seen && !withdrawn && <span className="ws-chip ws-chip--ink">New</span>}
        {card.superseded_by_item_id && <span className="ws-chip ws-chip--mute">Superseded</span>}
      </header>
      <h3 className="ws-butler-card-title">{card.title}</h3>

      {card.statements.map((s, i) => (
        <p key={i} className="ws-butler-statement">
          {s.text}
          <span className="ws-butler-basis"> &middot; {BASIS_LABELS[s.basis] ?? s.basis}</span>
        </p>
      ))}

      {card.passages.map((p) => (
        <figure key={p.citation_id} className="ws-butler-passage">
          <figcaption className="ws-muted">
            {p.label} &middot; {p.author_kind === "user" ? "you wrote" : p.author_kind} &middot;{" "}
            recorded {p.recorded_at.slice(0, 10)}
          </figcaption>
          <blockquote>
            {p.text}
            {p.truncated ? " … (shortened; open the record for the full text)" : ""}
          </blockquote>
        </figure>
      ))}

      {card.question && (
        <p className="ws-butler-question">
          <span className="ws-butler-label">Question</span>
          {card.question.text}
        </p>
      )}
      {card.lesson && (
        <p className="ws-butler-lesson">
          <span className="ws-butler-label">Note</span>
          {card.lesson.text}
        </p>
      )}

      {!withdrawn && (
        <p className="ws-butler-coverage ws-muted">
          Checked: records saved in this workspace. External sources: not checked. No model
          was involved.
        </p>
      )}

      {card.citations.length > 0 && (
        <div className="ws-butler-citations">
          <button
            type="button"
            className="ws-btn ws-btn--ghost ws-btn--sm"
            aria-expanded={showSources}
            onClick={() => setShowSources((v) => !v)}
          >
            {showSources ? "Hide" : "Show"} evidence ({card.citations.length})
          </button>
          {showSources && (
            <ul className="ws-butler-citation-list">
              {card.citations.map((c) => (
                <li key={c.id}>
                  <strong>{c.label}</strong>
                  <span className="ws-muted">
                    {" "}
                    &middot; {c.kind.toLowerCase()}
                    {c.published_on ? ` · published ${c.published_on}` : ""}
                    {c.retrieved_at ? ` · retrieved ${c.retrieved_at.slice(0, 10)}` : ""}
                    {c.recorded_at ? ` · recorded ${c.recorded_at.slice(0, 10)}` : ""}
                  </span>
                  {c.content_sha256 && (
                    <div className="ws-mono ws-muted ws-butler-hash">sha256 {c.content_sha256.slice(0, 16)}&hellip;</div>
                  )}
                  {c.href && (
                    <div>
                      <a href={c.href} target="_blank" rel="noopener noreferrer nofollow">
                        Open original source
                      </a>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {actions && (
        <footer className="ws-butler-actions">
          {card.template_id === "REVIEW_DUE" && !withdrawn && actions.onStartReview && (
            <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={actions.pending} onClick={actions.onStartReview}>
              Start review
            </button>
          )}
          {closed ? (
            actions.onRestore && (
              <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={actions.pending} onClick={actions.onRestore}>
                Restore
              </button>
            )
          ) : (
            <>
              {!card.status.seen && actions.onSeen && (
                <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={actions.pending} onClick={actions.onSeen}>
                  Mark seen
                </button>
              )}
              {actions.onSnooze && (
                <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={actions.pending} onClick={() => actions.onSnooze?.(7)}>
                  Snooze 7 days
                </button>
              )}
              {actions.onResolve && (
                <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={actions.pending} onClick={actions.onResolve}>
                  Done
                </button>
              )}
              {actions.onDismiss && (
                <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={actions.pending} onClick={actions.onDismiss}>
                  Dismiss
                </button>
              )}
            </>
          )}
        </footer>
      )}
    </article>
  );
}
