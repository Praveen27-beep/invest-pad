"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { EditorHandle } from "@/components/Editor";
import { api, type Block, type Note, type NoteSummary, type Version, when } from "@/lib/api";

// The editor needs the browser, so it is never rendered on the server.
const Editor = dynamic(() => import("@/components/Editor"), { ssr: false });

export default function NotePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const editor = useRef<EditorHandle>(null);
  const blocks = useRef<Block[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [title, setTitle] = useState("");
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [old, setOld] = useState<{ seq: number; title: string; body: string; created_at: string } | null>(null);

  const load = useCallback(async () => {
    const [n, v] = await Promise.all([api<Note>(`/notes/${id}`), api<Version[]>(`/notes/${id}/versions`)]);
    setNote(n);
    setVersions(v);
    return n;
  }, [id]);

  useEffect(() => {
    load().then((n) => { setTitle(n.title); blocks.current = n.blocks; }).catch((err) => setError((err as Error).message));
  }, [load]);

  const save = useCallback(async () => {
    setError("");
    try {
      const result = await api<{ seq: number; saved: boolean; links_updated_in?: number }>(
        `/notes/${id}`, { method: "PUT", body: { title, blocks: blocks.current } });
      setDirty(false);
      const updated = result.links_updated_in ? ` · links updated in ${result.links_updated_in} other note(s)` : "";
      setStatus(result.saved ? `Saved as version ${result.seq}${updated}` : "No changes to save");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }, [id, title, load]);

  // Ctrl/Cmd+S saves; leaving with unsaved changes asks first.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
    };
    const onLeave = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", onLeave);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("beforeunload", onLeave); };
  }, [save, dirty]);

  async function openMissing(titleKey: string) {
    const created = await api<NoteSummary>("/notes", { method: "POST", body: { title: titleKey, subject_id: note?.subject_id ?? null, blocks: [] } });
    router.push(`/n/${created.id}`);
  }

  async function copyBlockLink() {
    const blockId = editor.current?.currentBlockId();
    if (!blockId) return setStatus("Click inside a block first");
    await navigator.clipboard.writeText(`[[${title}#^${blockId}]]`);
    setStatus("Link to this block copied. Paste it into another note.");
  }

  async function remove() {
    if (!window.confirm(`Delete “${title}” and all ${versions.length} of its versions? This cannot be undone.`)) return;
    await api(`/notes/${id}`, { method: "DELETE" });
    router.replace(note?.subject_id ? `/c/${note.subject_id}` : "/");
  }

  if (error && !note) return <p className="error" role="alert">{error}</p>;
  if (!note) return null;
  return (
    <div className="editor-layout">
      <section>
        {note.subject_id && <Link href={`/c/${note.subject_id}`}>← Company</Link>}
        <input className="title-input" type="text" value={title} aria-label="Note title"
          onChange={(e) => { setTitle(e.target.value); setDirty(true); }} />
        <div className="row" style={{ margin: ".4rem 0 1rem" }}>
          <button className="primary" onClick={save} disabled={!dirty}>Save</button>
          <button onClick={copyBlockLink}>Copy link to this block</button>
          <span className={dirty ? "dirty" : "ok"} role="status">{dirty ? "Unsaved changes" : status}</span>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="editor-box">
          <Editor ref={editor} initial={note.blocks} onChange={(b) => { blocks.current = b; setDirty(true); }} />
        </div>
        <p className="empty">Link to another note by typing its title in double square brackets: [[Note title]].</p>
        {old && (
          <div className="version">
            <div className="row">
              <strong style={{ flex: 1 }}>Version {old.seq} · {when(old.created_at)} · “{old.title}”</strong>
              <button className="link" onClick={() => setOld(null)}>Close</button>
            </div>
            {old.body || <em>(empty)</em>}
          </div>
        )}
      </section>

      <aside className="side">
        <h2>Links from this note</h2>
        {note.links.length === 0 ? <p className="empty">None.</p> : (
          <ul>
            {note.links.map((l) => (
              <li key={l.title_key + (l.block_id ?? "")}>
                {l.id ? <Link href={`/n/${l.id}`}>{l.title}{l.block_id ? " (block)" : ""}</Link>
                  : <button className="link missing" onClick={() => openMissing(l.title_key)}>{l.title_key} — create</button>}
              </li>
            ))}
          </ul>
        )}

        <h2>Linked from</h2>
        {note.backlinks.length === 0 ? <p className="empty">No notes link here yet.</p> : (
          <ul>
            {note.backlinks.map((b, i) => (
              <li key={b.id + i}><Link href={`/n/${b.id}`}>{b.title}</Link><span className="snip">{b.snippet}</span></li>
            ))}
          </ul>
        )}

        <h2>Mentioned without a link</h2>
        {note.unlinked_mentions.length === 0 ? <p className="empty">None.</p> : (
          <ul>
            {note.unlinked_mentions.map((m) => (
              <li key={m.id}><Link href={`/n/${m.id}`}>{m.title}</Link><span className="snip">…{m.snippet}…</span></li>
            ))}
          </ul>
        )}

        <h2>History</h2>
        <ul>
          {versions.map((v) => (
            <li key={v.seq}>
              <button className="link" onClick={async () => setOld(await api(`/notes/${id}/versions/${v.seq}`))}>
                Version {v.seq}
              </button>{" "}
              <span className="snip">{when(v.created_at)}{v.reason ? ` · ${v.reason}` : ""}</span>
            </li>
          ))}
        </ul>

        <h2>Danger</h2>
        <button className="danger" onClick={remove}>Delete note</button>
      </aside>
    </div>
  );
}
