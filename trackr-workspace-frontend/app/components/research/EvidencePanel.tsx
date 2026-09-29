"use client";

/**
 * Sources, retained text and sourced facts for one company (FE 16; BE 12-13).
 *
 * PROVENANCE IS SHOWN, NOT SUMMARISED. Every source shows when it was PUBLISHED and when it was
 * RETRIEVED -- two different facts -- and whether any text was actually read: a metadata-only
 * citation says so, an extraction that failed says why. Reading text shows the server-verified
 * page with its hashes' identity, never a cached or re-extracted guess.
 *
 * FACTS ARE WHAT A SOURCE SAID. A new fact is always UNVERIFIED; verification is a separate,
 * explicit act of yours against one exact stored fact. Superseded rows stay listed. When two
 * sources disagree, both are shown with a conflict marker and nothing picks a winner.
 *
 * Numeric values are decimal STRINGS end to end; nothing here parses them into numbers.
 */

import { useState } from "react";
import { api, useFetch } from "@trackr/core";
import {
  SOURCE_TYPES,
  istToday,
  paths,
  write,
  type Fact,
  type FactInput,
  type Page,
  type Source,
  type SourceContent,
  type SourceInput,
  type SourceType,
} from "@/lib/research-api";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { AdvancedEvidence } from "./AdvancedEvidence";

export function EvidencePanel({ isin }: { isin: string }) {
  const { investorId, token } = useResearchAuth();
  const sources = useFetch<Page<Source>>(investorId ? paths.companySources(investorId, isin) : null, { limit: 100 }, token);
  const facts = useFetch<Page<Fact>>(investorId ? paths.companyFacts(investorId, isin) : null, { limit: 100 }, token);
  const [adding, setAdding] = useState<"none" | "citation" | "upload" | "fact">("none");

  return (
    <div className="ws-stack">
      <div className="ws-form-actions">
        <button type="button" className="ws-btn ws-btn--sm" onClick={() => setAdding("citation")}>Cite a source</button>
        <button type="button" className="ws-btn ws-btn--sm" onClick={() => setAdding("upload")}>Upload a document</button>
        <button type="button" className="ws-btn ws-btn--sm" onClick={() => setAdding("fact")} disabled={!sources.data?.items.length}>
          Record a fact
        </button>
      </div>
      {adding === "citation" && (
        <div className="ws-panel"><SourceForm isin={isin} upload={false} onDone={(ok) => { setAdding("none"); if (ok) sources.refetch(); }} /></div>
      )}
      {adding === "upload" && (
        <div className="ws-panel"><SourceForm isin={isin} upload onDone={(ok) => { setAdding("none"); if (ok) sources.refetch(); }} /></div>
      )}
      {adding === "fact" && sources.data && (
        <div className="ws-panel"><FactForm isin={isin} sources={sources.data.items} onDone={(ok) => { setAdding("none"); if (ok) facts.refetch(); }} /></div>
      )}

      <div>
        <div className="ws-sechead">
          <h2>Sources</h2>
          <div className="ws-hint">newest publication first</div>
        </div>
        <div className="ws-panel">
          {sources.loading && <div className="ws-empty">Loading&hellip;</div>}
          {sources.error && <div className="ws-notice ws-notice--error">{describeError(sources.errorDetail) ?? sources.error}</div>}
          {sources.data?.items.length === 0 && <div className="ws-empty">No sources recorded.</div>}
          {sources.data?.items.map((source) => <SourceRow key={source.id} source={source} />)}
        </div>
      </div>

      <div>
        <div className="ws-sechead">
          <h2>Facts</h2>
          <div className="ws-hint">every recorded value, superseded ones included</div>
        </div>
        <div className="ws-panel">
          {facts.loading && <div className="ws-empty">Loading&hellip;</div>}
          {facts.error && <div className="ws-notice ws-notice--error">{facts.error}</div>}
          {facts.data?.items.length === 0 && <div className="ws-empty">No facts recorded.</div>}
          {facts.data?.items.map((fact) => (
            <FactRow key={fact.id} fact={fact} sources={sources.data?.items ?? []} isin={isin} onChanged={facts.refetch} />
          ))}
        </div>
      </div>

      <AdvancedEvidence isin={isin} />
    </div>
  );
}

function SourceRow({ source }: { source: Source }) {
  const { investorId, token } = useResearchAuth();
  const [page, setPage] = useState(1);
  const [content, setContent] = useState<SourceContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const state = source.content.state;

  async function read(target: number) {
    setLoading(true);
    setError(null);
    try {
      setContent(await api.get<SourceContent>(paths.sourceContent(investorId, source.id), { token, query: { page: target } }));
      setPage(target);
    } catch (err) {
      setContent(null);
      setError(describeError(err as Error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ws-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div style={{ display: "flex", gap: 10 }}>
        <span className="ws-row-grow">
          <span className="ws-row-t">{source.source}</span>
          <span className="ws-row-m">
            {source.source_type.toLowerCase().replace(/_/g, " ")} &middot; {source.period} &middot; published{" "}
            <strong>{source.publication_date}</strong> &middot; retrieved {source.retrieved_at.slice(0, 10)} &middot;{" "}
            {source.document_reference}
          </span>
          <span className="ws-row-m ws-mono" style={{ overflowWrap: "anywhere" }}>{source.source_url}</span>
        </span>
        <span className={`ws-chip ${state === "EXTRACTED" ? "ws-chip--pos" : state === "UNAVAILABLE" ? "ws-chip--warn" : "ws-chip--mute"}`}>
          {state === "METADATA_ONLY" ? "Citation only -- not read" : state === "EXTRACTED" ? `Text retained · ${source.content.page_count} p` : `No text: ${source.content.unavailable_reason?.toLowerCase()}`}
        </span>
      </div>
      {state === "EXTRACTED" && (
        <div className="ws-form-actions" style={{ marginTop: 8 }}>
          <button type="button" className="ws-btn ws-btn--sm" disabled={loading} onClick={() => void read(content ? page : 1)}>
            {content ? "Reload page" : "Read text"}
          </button>
          {content && (
            <>
              <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={loading || page <= 1} onClick={() => void read(page - 1)}>Previous page</button>
              <span className="ws-hint">page {page} of {content.page_count}</span>
              <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={loading || page >= content.page_count} onClick={() => void read(page + 1)}>Next page</button>
            </>
          )}
        </div>
      )}
      {error && <div className="ws-notice ws-notice--error">{error}</div>}
      {content && (
        <div style={{ marginTop: 8 }}>
          <p className="ws-verbatim ws-mono" style={{ fontSize: 12, maxHeight: 360, overflow: "auto" }}>{content.text || "(this page has no text)"}</p>
          <span className="ws-row-m ws-mono">
            verified against bytes {content.content_sha256.slice(0, 12)}&hellip; and text {content.text_sha256.slice(0, 12)}&hellip; &middot; {content.extractor_id} {content.extractor_version}
          </span>
        </div>
      )}
    </div>
  );
}

function SourceForm({ isin, upload, onDone }: { isin: string; upload: boolean; onDone: (saved: boolean) => void }) {
  const { investorId, token } = useResearchAuth();
  const [form, setForm] = useState<SourceInput>({
    source: "",
    source_type: upload ? "USER_DOCUMENT" : "EXCHANGE_FILING",
    source_url: "",
    publication_date: "",
    period: "",
    retrieved_at: "",
    document_reference: "",
  });
  const [retrievedLocal, setRetrievedLocal] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const { submit, pending, error } = useSubmit<Source>();
  const set = (patch: Partial<SourceInput>) => setForm((f) => ({ ...f, ...patch }));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    // A datetime-local value has no zone; interpret it as the browser's local time and send an
    // explicit UTC instant. An unknown publication date is never filled in for the person.
    const body: SourceInput = { ...form, retrieved_at: new Date(retrievedLocal).toISOString() };
    const fingerprint = upload ? { ...body, file: file ? [file.name, file.size, file.lastModified] : null } : body;
    const saved = await submit(fingerprint, (key) => {
      const ctx = { investorId, token, idempotencyKey: key };
      return upload && file ? write.uploadSourceDocument(ctx, isin, file, body) : write.createSource(ctx, isin, body);
    });
    if (saved) onDone(true);
  }

  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
      <p className="ws-row-m">
        {upload
          ? "PDF or UTF-8 text, up to 20 MB. Text is extracted locally and kept with its exact version; nothing is fetched from the internet."
          : "A citation records where a claim came from. It does not claim the text was read."}
      </p>
      {upload && (
        <label className="ws-field">
          <span className="ws-field-label">File</span>
          <input className="ws-input" type="file" required accept="application/pdf,text/plain,.pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      )}
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Title</span>
          <input className="ws-input" required value={form.source} onChange={(e) => set({ source: e.target.value })} placeholder="Q4 FY25 results" />
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Type</span>
          <select className="ws-input" value={form.source_type} onChange={(e) => set({ source_type: e.target.value as SourceType })}>
            {SOURCE_TYPES.map((t) => <option key={t} value={t}>{t.toLowerCase().replace(/_/g, " ")}</option>)}
          </select>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Period</span>
          <input className="ws-input" required value={form.period} onChange={(e) => set({ period: e.target.value })} placeholder="Q4FY25" />
        </label>
      </div>
      <label className="ws-field">
        <span className="ws-field-label">Public URL or reference</span>
        <input className="ws-input ws-mono" required value={form.source_url} onChange={(e) => set({ source_url: e.target.value })} placeholder="https://… or isbn:… (never a signed download link)" />
      </label>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Published on (required)</span>
          <input className="ws-input" type="date" required max={istToday()} value={form.publication_date} onChange={(e) => set({ publication_date: e.target.value })} />
          <span className="ws-field-hint">If you do not know it, this is not yet a usable source.</span>
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Retrieved at</span>
          <input className="ws-input" type="datetime-local" required value={retrievedLocal} onChange={(e) => setRetrievedLocal(e.target.value)} />
        </label>
        <label className="ws-field">
          <span className="ws-field-label">Page / section</span>
          <input className="ws-input" required value={form.document_reference} onChange={(e) => set({ document_reference: e.target.value })} placeholder="p. 3, segment table" />
        </label>
      </div>
      {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
      <div className="ws-form-actions">
        <button type="submit" className="ws-btn ws-btn--primary" disabled={pending || (upload && !file)}>
          {pending ? "Saving…" : upload ? "Upload" : "Save citation"}
        </button>
        <button type="button" className="ws-btn ws-btn--ghost" onClick={() => onDone(false)}>Discard</button>
      </div>
    </form>
  );
}

function FactForm({
  isin,
  sources,
  onDone,
  revise,
}: {
  isin: string;
  sources: Source[];
  onDone: (saved: boolean) => void;
  revise?: Fact;
}) {
  const { investorId, token } = useResearchAuth();
  const [form, setForm] = useState({
    source_id: revise?.source_id ?? sources[0]?.id ?? "",
    metric: revise?.metric ?? "",
    basis: revise?.basis ?? "consolidated",
    unit: revise?.unit ?? "",
    period_start: revise?.period_start ?? "",
    period_end: revise?.period_end ?? "",
    cadence: (revise?.cadence as FactInput["cadence"]) ?? "QUARTER",
    valueType: revise?.boolean_value !== null && revise?.boolean_value !== undefined ? "boolean" : revise?.text_value ? "text" : "numeric",
    value: revise?.numeric_value ?? revise?.text_value ?? (revise?.boolean_value === undefined || revise?.boolean_value === null ? "" : String(revise.boolean_value)),
  });
  const { submit, pending, error } = useSubmit<Fact>();
  const set = (key: keyof typeof form, value: string) => setForm((f) => ({ ...f, [key]: value }));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const body: FactInput = {
      source_id: form.source_id,
      metric: form.metric,
      basis: form.basis,
      unit: form.unit,
      period_start: form.period_start,
      period_end: form.period_end,
      cadence: form.cadence,
      // Sent as the exact string typed -- the server checks it fits NUMERIC(20,6).
      numeric_value: form.valueType === "numeric" ? form.value.trim() : null,
      boolean_value: form.valueType === "boolean" ? form.value === "true" : null,
      text_value: form.valueType === "text" ? form.value : null,
    };
    const saved = await submit({ ...body, revise: revise?.id }, (key) => {
      const ctx = { investorId, token, idempotencyKey: key };
      return revise ? write.reviseFact(ctx, revise.id, { ...body, expected_fact_id: revise.id }) : write.createFact(ctx, isin, body);
    });
    if (saved) onDone(true);
  }

  const locked = Boolean(revise);
  return (
    <form className={`ws-form${pending ? " ws-pending" : ""}`} onSubmit={save}>
      <p className="ws-row-m">
        {revise
          ? "A correction from the same source, for the same series. It is saved unverified; the old value stays listed."
          : "Your transcription of what the source says. Saved unverified; verify it separately after rechecking the source."}
      </p>
      <div className="ws-form-row">
        <label className="ws-field">
          <span className="ws-field-label">Source</span>
          <select className="ws-input" value={form.source_id} disabled={locked} onChange={(e) => set("source_id", e.target.value)}>
            {sources.map((s) => <option key={s.id} value={s.id}>{s.source} &middot; {s.period}</option>)}
          </select>
        </label>
        <label className="ws-field"><span className="ws-field-label">Metric</span><input className="ws-input ws-mono" required disabled={locked} value={form.metric} onChange={(e) => set("metric", e.target.value)} /></label>
        <label className="ws-field"><span className="ws-field-label">Basis</span><input className="ws-input" required disabled={locked} value={form.basis} onChange={(e) => set("basis", e.target.value)} /></label>
        <label className="ws-field"><span className="ws-field-label">Unit</span><input className="ws-input" required disabled={locked} value={form.unit} onChange={(e) => set("unit", e.target.value)} /></label>
      </div>
      <div className="ws-form-row">
        <label className="ws-field"><span className="ws-field-label">Cadence</span>
          <select className="ws-input" value={form.cadence} disabled={locked} onChange={(e) => set("cadence", e.target.value)}>
            <option>QUARTER</option><option>YEAR</option><option>POINT</option>
          </select>
        </label>
        <label className="ws-field"><span className="ws-field-label">Period start</span><input className="ws-input" type="date" required disabled={locked} value={form.period_start} onChange={(e) => set("period_start", e.target.value)} /></label>
        <label className="ws-field"><span className="ws-field-label">Period end</span><input className="ws-input" type="date" required disabled={locked} value={form.period_end} onChange={(e) => set("period_end", e.target.value)} /></label>
      </div>
      <div className="ws-form-row">
        <label className="ws-field"><span className="ws-field-label">Value type</span>
          <select className="ws-input" value={form.valueType} onChange={(e) => { set("valueType", e.target.value); set("value", e.target.value === "boolean" ? "true" : ""); }}>
            <option value="numeric">number (as written)</option><option value="boolean">yes / no</option><option value="text">text</option>
          </select>
        </label>
        <label className="ws-field"><span className="ws-field-label">Value</span>
          {form.valueType === "boolean" ? (
            <select className="ws-input" value={form.value} onChange={(e) => set("value", e.target.value)}><option value="true">yes</option><option value="false">no</option></select>
          ) : (
            <input className="ws-input ws-mono" required inputMode={form.valueType === "numeric" ? "decimal" : undefined} value={form.value} onChange={(e) => set("value", e.target.value)} placeholder={form.valueType === "numeric" ? "e.g. 10.1" : ""} />
          )}
        </label>
      </div>
      {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
      <div className="ws-form-actions">
        <button type="submit" className="ws-btn ws-btn--primary" disabled={pending}>{pending ? "Saving…" : revise ? "Save correction" : "Save fact"}</button>
        <button type="button" className="ws-btn ws-btn--ghost" onClick={() => onDone(false)}>Discard</button>
      </div>
    </form>
  );
}

function FactRow({ fact, sources, isin, onChanged }: { fact: Fact; sources: Source[]; isin: string; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [mode, setMode] = useState<"none" | "verify" | "revise">("none");
  const [reference, setReference] = useState("");
  const verify = useSubmit<Fact>();
  const source = sources.find((s) => s.id === fact.source_id);
  const value = fact.numeric_value ?? (fact.boolean_value === null ? fact.text_value : fact.boolean_value ? "yes" : "no");
  const current = fact.superseded_by === null;

  async function doVerify(event: React.FormEvent) {
    event.preventDefault();
    const body = { verification_reference: reference, expected_fact_id: fact.id };
    const saved = await verify.submit(body, (key) => write.verifyFact({ investorId, token, idempotencyKey: key }, fact.id, body));
    if (saved) {
      setMode("none");
      onChanged();
    }
  }

  return (
    <div className={`ws-row${current ? "" : " ws-pending"}`} style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div style={{ display: "flex", gap: 10 }}>
        <span className="ws-row-grow">
          <span className="ws-row-t">
            <span className="ws-mono">{fact.metric}</span> ({fact.basis}) = <span className="ws-mono">{value}</span> {fact.unit}
          </span>
          <span className="ws-row-m">
            {fact.cadence.toLowerCase()} {fact.period_start} to {fact.period_end} &middot; from {source ? `${source.source} (published ${source.publication_date})` : "a source"}
            {fact.verification_reference ? ` · checked: ${fact.verification_reference}` : ""}
            {!current ? " · superseded" : ""}
          </span>
        </span>
        <span className={`ws-chip ${fact.verification === "VERIFIED" ? "ws-chip--pos" : "ws-chip--open"}`}>{fact.verification.toLowerCase()}</span>
        {fact.conflicts_with.length > 0 && <span className="ws-chip ws-chip--warn">Sources disagree</span>}
      </div>
      {fact.conflicts_with.length > 0 && (
        <p className="ws-row-m">Another source reports a different value for the same period and basis. Both are kept; neither is chosen.</p>
      )}
      {current && mode === "none" && (
        <div className="ws-form-actions" style={{ marginTop: 6 }}>
          {fact.verification === "UNVERIFIED" && <button type="button" className="ws-btn ws-btn--sm" onClick={() => setMode("verify")}>I rechecked the source</button>}
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setMode("revise")}>Correct</button>
        </div>
      )}
      {mode === "verify" && (
        <form className={`ws-form${verify.pending ? " ws-pending" : ""}`} style={{ padding: "8px 0 0" }} onSubmit={doVerify}>
          <div className="ws-form-actions">
            <input className="ws-input" required placeholder="Where you checked it, e.g. p.3 table 2" value={reference} onChange={(e) => setReference(e.target.value)} style={{ maxWidth: 360 }} />
            <button type="submit" className="ws-btn ws-btn--sm" disabled={verify.pending || !reference.trim()}>{verify.pending ? "Saving…" : "Mark verified"}</button>
            <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => setMode("none")}>Discard</button>
          </div>
          {verify.error && <div className="ws-notice ws-notice--error">{describeError(verify.error)}</div>}
        </form>
      )}
      {mode === "revise" && <FactForm isin={isin} sources={sources} revise={fact} onDone={(ok) => { setMode("none"); if (ok) onChanged(); }} />}
    </div>
  );
}
