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
