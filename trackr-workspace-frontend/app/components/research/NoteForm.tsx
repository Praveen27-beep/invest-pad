"use client";

/**
 * Create a note, or append a revision to one. The same form for both, because a revision is a
 * complete new record (BE 09) rather than a patch: every field is submitted again.
 *
 * THREE STATES ARE KEPT VISIBLY APART. What is typed here is UNSAVED input and is lost on
 * navigation (owner answer Q05 -- no draft store). A click puts it in PENDING. Only the server's
 * response is CONFIRMED, and only that is handed to `onSaved`.
 *
 * An OBSERVATION must cite one of this company's sources -- the server refuses one without --
 * so the source picker lists only this company's real sources and says so when there are none.
 */

import { useState } from "react";
import { useFetch } from "@trackr/core";
import {
  WRITABLE_NOTE_KINDS,
  istToday,
  paths,
  write,
  type Note,
  type NoteInput,
  type Page,
  type Relation,
  type Source,
  type WritableNoteKind,
} from "@/lib/research-api";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

const KIND_HINT: Record<WritableNoteKind, string> = {
  OBSERVATION: "what a source said -- must cite it",
  INTERPRETATION: "your own reasoning",
  THESIS_NOTE: "working towards a thesis",
  LITERATURE: "notes on something you read",
  DECISION: "a decision you made, and why",
};

export function NoteForm({
  isin,
  revise,
  onSaved,
  onCancel,
}: {
  isin: string;
  /** Present when appending a revision: the note and the chain's latest id you last saw. */
  revise?: { note: Note; expectedLatestId: string };
  onSaved: (note: Note) => void;
  onCancel?: () => void;
}) {
  const { investorId, token } = useResearchAuth();
  const base = revise?.note;
  const [kind, setKind] = useState<WritableNoteKind>(
    (base?.kind as WritableNoteKind) ?? "INTERPRETATION"
  );
  const [title, setTitle] = useState(base?.title ?? "");
  const [body, setBody] = useState(base?.body ?? "");
  const [writtenOn, setWrittenOn] = useState(istToday());
  const [sourceId, setSourceId] = useState<string>(base?.primary_source_id ?? "");
  const [linkRelation, setLinkRelation] = useState<Relation | "">("");
  const [linkTarget, setLinkTarget] = useState("");
  const sources = useFetch<Page<Source>>(
    investorId ? paths.companySources(investorId, isin) : null,
    { limit: 100 },
    token
  );
  const { submit, pending, error } = useSubmit<Note>();

  const payload: NoteInput = {
    kind,
    title,
    body,
    written_on: writtenOn,
    primary_source_id: sourceId || null,
    links:
      linkRelation && linkTarget.trim()
        ? [{ relation: linkRelation, to_note_id: linkTarget.trim() }]
        : [],
  };

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const ctx = (key: string) => ({ investorId, token, idempotencyKey: key });
    const saved = revise
      ? await submit({ ...payload, expected: revise.expectedLatestId }, (key) =>
          write.reviseNote(ctx(key), revise.note.id, {
            ...payload,
            expected_latest_id: revise.expectedLatestId,
          })
        )
      : await submit(payload, (key) => write.createNote(ctx(key), isin, payload));
    if (saved) onSaved(saved);
  }

  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Kind</span>
          <select
            className="ws-input"
            value={kind}
            disabled={Boolean(revise)}
            onChange={(e) => setKind(e.target.value as WritableNoteKind)}
          >
            {WRITABLE_NOTE_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.toLowerCase().replace("_", " ")}
              </option>
            ))}
          </select>
          <span className="ws-field-hint">
            {revise ? "a revision keeps the original kind" : KIND_HINT[kind]}
          </span>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Written on</span>
          <input
            className="ws-input"
            type="date"
            required
            value={writtenOn}
            onChange={(e) => setWrittenOn(e.target.value)}
          />
        </label>
        <label className="ws-field">
          <span className="ws-field-label">
            Primary source{kind === "OBSERVATION" ? " (required)" : ""}
          </span>
          <select
            className="ws-input"
            value={sourceId}
            required={kind === "OBSERVATION"}
            onChange={(e) => setSourceId(e.target.value)}
          >
            <option value="">None</option>
            {sources.data?.items.map((source) => (
              <option key={source.id} value={source.id}>
                {source.source} &middot; {source.period} &middot; published {source.publication_date}
              </option>
            ))}
          </select>
          {kind === "OBSERVATION" && sources.data && sources.data.items.length === 0 && (
            <span className="ws-field-hint">
              No sources recorded for this company yet -- add one under Evidence first.
            </span>
          )}
        </label>
      </div>
      <label className="ws-field">
        <span className="ws-field-label">Title</span>
        <input
          className="ws-input"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={500}
        />
      </label>
      <label className="ws-field">
        <span className="ws-field-label">Body</span>
        <textarea className="ws-textarea" value={body} onChange={(e) => setBody(e.target.value)} />
      </label>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Link to another note (optional)</span>
          <select
            className="ws-input"
            value={linkRelation}
            onChange={(e) => setLinkRelation(e.target.value as Relation | "")}
          >
            <option value="">No link</option>
            <option value="SUPPORTS">supports</option>
            <option value="CONTRADICTS">contradicts</option>
            <option value="READS">reads</option>
            <option value="CITES">cites</option>
          </select>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Note id</span>
          <input
            className="ws-input ws-mono"
            value={linkTarget}
            onChange={(e) => setLinkTarget(e.target.value)}
            placeholder="saved note id"
          />
        </label>
      </div>
      {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
      <div className="ws-form-actions">
        <button type="submit" className="ws-btn ws-btn--primary" disabled={pending}>
          {pending ? "Saving…" : revise ? "Save as new revision" : "Save note"}
        </button>
        {onCancel && (
          <button type="button" className="ws-btn ws-btn--ghost" onClick={onCancel}>
            Discard
          </button>
        )}
        <span className="ws-hint">
          {revise
            ? "The earlier text stays exactly as written; this becomes the latest revision."
            : "Unsaved until the server confirms."}
        </span>
      </div>
    </form>
  );
}
