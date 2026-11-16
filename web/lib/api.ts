// One small wrapper around fetch. Every call goes to /api/*, which Next passes to the backend.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: options.method ?? "GET",
    headers: options.body === undefined ? undefined : { "content-type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (response.status === 401 && !path.startsWith("/auth/")) {
    window.location.href = "/login";
    throw new ApiError(401, "Not signed in");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {}
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export type Subject = { id: string; name: string; created_at: string };
export type NoteSummary = { id: string; subject_id: string | null; title: string; seq: number; updated_at: string };
export type Block = Record<string, unknown>;
export type Note = NoteSummary & {
  blocks: Block[];
  links: { title_key: string; block_id: string | null; id: string | null; title: string | null }[];
  backlinks: { id: string; title: string; block_id: string | null; target_block_id: string | null; snippet: string }[];
  unlinked_mentions: { id: string; title: string; snippet: string }[];
};
export type Capture = {
  id: string; kind: "note" | "question"; body: string; selection: string; url: string; page_title: string;
  captured_at: string; status: "inbox" | "filed" | "dismissed"; subject_id: string | null; note_id: string | null;
};
export type Token = { id: string; label: string; created_at: string; last_used_at: string | null; revoked_at: string | null };
export type Version = { seq: number; title: string; reason: string | null; created_at: string; chars: number };

export const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** Upload a file with form fields (the JSON helper above cannot carry files). */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`/api${path}`, { method: "POST", body: form });
  if (!response.ok) {
    let message = `Upload failed (${response.status})`;
    try { const data = await response.json(); if (typeof data.detail === "string") message = data.detail; } catch {}
    throw new ApiError(response.status, message);
  }
  return response.json();
}

export const day = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export type Doc = {
  id: string; subject_id: string; title: string; filename: string; format: string; doc_type: string; period: string;
  doc_date: string | null; status: "processing" | "ready" | "no_text" | "failed"; status_note: string; pages: number;
  created_at: string; passages?: number;
};
export type Passage = { id: string; ordinal: number; page: number; label: string; body: string };
export type Evidence = {
  id: string; direction: "for" | "against"; kind: "fact" | "opinion" | "ai"; body: string; source_deleted: boolean;
  is_sourced_fact: boolean; passage: string | null; page_label: string | null; document_id: string | null;
  document_title: string | null; document_period: string | null; note_id: string | null; note_title: string | null;
  created_at: string;
};
export type Assumption = {
  id: string; seq: number; body: string; basis: "fact" | "judgement";
  state: "holds" | "challenged" | "broken" | "outdated"; reason: string; updated_at: string; evidence: Evidence[];
};
export type Thesis = { seq: number; body: string; versions: { seq: number; created_at: string }[]; assumptions: Assumption[] };
export type Decision = {
  id: string; type: string; type_label?: string; decided_on: string; decisive_reason: string; would_change_mind: string;
  position_seq: number | null; created_at: string; thesis_changed?: boolean;
  assumptions: { id: string; seq: number; body: string; state: string;
    now?: { seq: number; body: string; state: string; reason: string; changed: boolean } | null }[];
};
export type Overview = {
  subject: Subject; decision: Decision | null; thesis_seq: number; assumptions: Assumption[];
  open_questions: { id: string; body: string; captured_at: string }[];
  changes: { since: string | null; notes: { id: string; title: string; updated_at: string }[];
    documents: { id: string; title: string; doc_type: string; period: string; created_at: string }[];
    assumptions: { id: string; seq: number; body: string; state: string; reason: string; created_at: string }[];
    thesis_versions: number };
};
export type Pack = {
  decision_types: { key: string; label: string }[]; document_types: string[];
  checklists: Record<string, { title: string; intro: string; items: { id: string; text: string }[] }>;
};
export const STATES = { holds: "Holds", challenged: "Challenged", broken: "Broken", outdated: "Outdated" } as const;
