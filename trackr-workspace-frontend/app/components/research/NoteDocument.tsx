"use client";

/**
 * A note research document: `/research/notes/{id}` (FE 15).
 *
 * THE URL NAMES AN EXACT, IMMUTABLE RECORD. An older revision's URL keeps showing that older
 * text, labelled as superseded, with a link to the latest. Editing never overwrites: "Revise"
 * appends a new record naming the chain's latest id the reader last saw, and a stale view is
 * refused by the server (409) rather than silently forking the history.
 *
 * Links are shown with their dates exactly as recorded; a CONTRADICTS link shows both notes,
 * and nothing here reconciles them. Links whose other end belongs to a locked or foreign
 * company never reach this page -- the server drops them.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { descriptorId, noteHref } from "@trackr/portfolio";
import { useFetch } from "@trackr/core";
import { useWorkspaceNav } from "@/lib/workspace-context";
import { paths, write, type Note, type NoteLink, type Relation } from "@/lib/research-api";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { NoteForm } from "./NoteForm";
import { RememberControl } from "../butler/ButlerControls";

export function NoteDocument({ noteId }: { noteId: string }) {
  const { investorId, token } = useResearchAuth();
  const { labelDocument } = useWorkspaceNav();
  const router = useRouter();
  const note = useFetch<Note>(investorId ? paths.note(investorId, noteId) : null, undefined, token);
  const [revising, setRevising] = useState(false);

  useEffect(() => {
    if (note.data) labelDocument(descriptorId("note", noteId), note.data.title);
  }, [note.data, noteId, labelDocument]);

  if (note.loading) return <div className="ws-empty">Loading&hellip;</div>;
  if (note.error || !note.data) {
    return (
      <div>
        <div className="ws-crumb">Research &middot; Note</div>
        <div className="ws-notice ws-notice--error">
          {note.errorDetail?.status === 404
            ? "This note does not exist here."
            : describeError(note.errorDetail) ?? note.error}
        </div>
      </div>
    );
  }

  const data = note.data;
  const position = data.revision_ids.indexOf(data.id) + 1;
  return (
    <div>
      <div className="ws-crumb">
        Research &middot;{" "}
        <Link href={`/research/companies/${data.isin}?mode=notes`} className="ws-mono">
          {data.isin}
        </Link>{" "}
        &middot; Note
      </div>
      <h1 className="ws-h1">{data.title}</h1>
      <p className="ws-sub">
        {data.kind.toLowerCase().replace("_", " ")} &middot; written {data.written_on} &middot;
        saved {data.recorded_at.slice(0, 10)}
        {data.authorship === "ACCEPTED_AGENT"
          ? " · accepted from an agent proposal by you"
          : " · your writing"}
      </p>
      {/* Remembers THIS saved version only, and only when asked. */}
      <RememberControl noteId={data.id} isin={data.isin} />

      {!data.is_latest && (
        <div className="ws-notice ws-notice--warn">
          This is revision {position} of {data.revision_ids.length}, kept exactly as written.{" "}
          <Link href={noteHref(data.latest_id) ?? "#"}>Read the latest revision</Link>.
        </div>
      )}

      <div className="ip-note-body" data-kind={data.kind}><div className="ip-note-kind">{data.kind === "OBSERVATION" ? "Sourced observation" : data.kind.toLowerCase().replace("_", " ")}</div>
        {data.body ? <p className="ws-verbatim">{data.body}</p> : <p className="ws-muted">No body text.</p>}
      </div>

      {data.source && (
        <>
          <div className="ws-sechead">
            <h2>Source</h2>
          </div>
          <div className="ws-panel">
            <div className="ws-row">
              <span className="ws-row-grow">
                <span className="ws-row-t">{data.source.source}</span>
                <span className="ws-row-m">
                  {data.source.source_type.toLowerCase().replace("_", " ")} &middot; {data.source.period} &middot;
                  published {data.source.publication_date} &middot; retrieved{" "}
                  {data.source.retrieved_at.slice(0, 10)} &middot; {data.source.document_reference}
                </span>
                <span className="ws-row-m ws-mono">{data.source.source_url}</span>
              </span>
              <span className="ws-chip ws-chip--mute">
                {data.source.content.state === "METADATA_ONLY" ? "Citation only" : data.source.content.state.toLowerCase()}
              </span>
            </div>
          </div>
        </>
      )}

      <div className="ws-sechead">
        <h2>Links</h2>
        <div className="ws-hint">dated relationships; neither side is ever edited</div>
      </div>
      <div className="ws-panel">
        {data.links.length === 0 ? (
          <div className="ws-empty">No links.</div>
        ) : (
          data.links.map((link) => <LinkRow key={`${link.id}:${link.direction}`} link={link} />)
        )}
      </div>
      {data.is_latest && data.kind !== "QUESTION" && <AddLink noteId={data.id} onSaved={note.refetch} />}

      <div className="ws-sechead">
        <h2>History</h2>
        <div className="ws-hint">{data.revision_ids.length} revision{data.revision_ids.length === 1 ? "" : "s"}, oldest first</div>
      </div>
      <div className="ws-panel">
        {data.revision_ids.map((id, index) => (
          <Link key={id} className="ws-row" href={noteHref(id) ?? "#"} aria-current={id === data.id ? "page" : undefined}>
            <span className="ws-row-grow">
              <span className="ws-row-t">Revision {index + 1}</span>
              <span className="ws-row-m ws-mono">{id}</span>
            </span>
            {id === data.latest_id && <span className="ws-chip ws-chip--pos">Latest</span>}
            {id === data.id && <span className="ws-chip ws-chip--ink">Showing</span>}
          </Link>
        ))}
      </div>

      {data.kind === "QUESTION" ? (
        <p className="ws-hint">A question is never reworded. Ask a new one from the company page.</p>
      ) : revising ? (
        <div className="ws-panel" style={{ marginTop: 16 }}>
          <NoteForm
            isin={data.isin}
            revise={{ note: data, expectedLatestId: data.latest_id }}
            onCancel={() => setRevising(false)}
            onSaved={(saved) => {
              setRevising(false);
              const href = noteHref(saved.id);
              if (href) router.push(href);
            }}
          />
        </div>
      ) : (
        <div className="ws-form-actions" style={{ marginTop: 16 }}>
          <button type="button" className="ws-btn" onClick={() => setRevising(true)}>
            Revise
          </button>
          <span className="ws-hint">appends a new revision; this text stays readable</span>
        </div>
      )}
    </div>
  );
}

function LinkRow({ link }: { link: NoteLink }) {
  const otherNote = link.direction === "OUT" ? link.to_note_id : link.from_note_id;
  const verb =
    link.direction === "OUT"
      ? `This note ${link.relation.toLowerCase()}`
      : `Another note ${link.relation.toLowerCase()} this one`;
  return (
    <div className="ws-row">
      <span className="ws-row-grow">
        <span className="ws-row-t">
          {verb}
          {link.relation === "CONTRADICTS" ? " -- both are kept as written" : ""}
        </span>
        <span className="ws-row-m">
          recorded {link.recorded_at.slice(0, 10)} &middot;{" "}
          {otherNote ? (
            <Link href={noteHref(otherNote) ?? "#"} className="ws-mono">
              note {otherNote.slice(0, 8)}
            </Link>
          ) : link.source_id ? (
            <span className="ws-mono">source {link.source_id.slice(0, 8)}</span>
          ) : (
            <span className="ws-mono">thesis {link.thesis_id?.slice(0, 8)}</span>
          )}
        </span>
      </span>
      {link.relation === "CONTRADICTS" && <span className="ws-chip ws-chip--neg">Contradicts</span>}
    </div>
  );
}

function AddLink({ noteId, onSaved }: { noteId: string; onSaved: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [relation, setRelation] = useState<Relation>("SUPPORTS");
  const [target, setTarget] = useState("");
  const { submit, pending, error } = useSubmit<NoteLink>();

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body = { relation, to_note_id: target.trim() };
    const saved = await submit(body, (key) =>
      write.linkNote({ investorId, token, idempotencyKey: key }, noteId, body)
    );
    if (saved) {
      setTarget("");
      onSaved();
    }
  }

  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} style={{ padding: "12px 0" }} onSubmit={save}>
      <div className="ws-form-actions">
        <select className="ws-input" value={relation} onChange={(e) => setRelation(e.target.value as Relation)} style={{ maxWidth: 170 }}>
          <option value="SUPPORTS">supports</option>
          <option value="CONTRADICTS">contradicts</option>
          <option value="READS">reads</option>
          <option value="CITES">cites</option>
        </select>
        <input className="ws-input ws-mono" required placeholder="other note id" value={target} onChange={(e) => setTarget(e.target.value)} style={{ maxWidth: 340 }} />
        <button type="submit" className="ws-btn ws-btn--sm" disabled={pending || !target.trim()}>
          {pending ? "Linking…" : "Add link"}
        </button>
      </div>
      {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
    </form>
  );
}
