/**
 * Typed client for company research reports (RP 00-07; `/investors/{id}/reports`).
 *
 * WORKSPACE ONLY. Plus never imports this file and never fetches report or notebook data.
 * Nothing here carries a provider key or an operator credential: the report worker uses the
 * platform's own purpose-bound credential on the server, and this client only asks for a job,
 * reads its durable progress, cancels it and downloads the private artifacts through the
 * authenticated route. Numbers are decimal STRINGS end to end.
 */

import { api } from "@trackr/core";

const enc = encodeURIComponent;
export const reportsBase = (inv: string) => `/investors/${enc(inv)}/reports`;

export type ReportMode = "CURRENT_WITH_HISTORY" | "POINT_IN_TIME";
export type ReportScope = "ISSUER_ONLY" | "ISSUER_PLUS_PRIVATE_RESEARCH";
export type Statement = "INCOME_STATEMENT" | "BALANCE_SHEET" | "CASH_FLOW" | "SEGMENTS" | "SHAREHOLDING" | "AUDITOR_REPORT";
export type JobState =
  | "QUEUED" | "RUNNING" | "WAITING_FOR_SOURCE" | "BUDGET_PAUSED" | "NEEDS_REVIEW"
  | "READY_WITH_LIMITATIONS" | "READY_CHECKED_SCOPE" | "FAILED" | "CANCEL_REQUESTED" | "CANCELLED" | "EXPIRED";

export const TERMINAL: JobState[] = ["READY_WITH_LIMITATIONS", "READY_CHECKED_SCOPE", "FAILED", "CANCELLED", "EXPIRED"];

export interface ReportRequest {
  isin: string;
  question: string;
  mode: ReportMode;
  cutoff: string | null;
  window_years: number;
  statements: Statement[];
  basis: "CONSOLIDATED" | "STANDALONE";
  scope: ReportScope;
  budget: string;
  deadline_minutes: number;
}

export interface ReportJob {
  id: string;
  purpose: "COMPANY_REPORT";
  isin: string;
  request: Record<string, unknown>;
  state: JobState;
  state_reason: string;
  stage: string | null;
  revision_of: string | null;
  provider: string;
  model: string;
  currency: string;
  budget_limit: string;
  spent_worst_case: string;
  deadline_at: string;
  recorded_at: string;
  completed_stages: string[];
  coverage: { requested_years: string; latest_fiscal_year: string; basis: string; cells: { period: string; statement: string; status: string }[] } | null;
}

export interface JobEvent {
  version: number;
  state: JobState;
  stage: string | null;
  reason_code: string;
  detail: Record<string, string>;
  recorded_at: string;
}

export interface ReportClaim {
  claim_id: string;
  section_id: string;
  claim_class: "SOURCE_STATEMENT" | "CALCULATED_VALUE" | "INTERPRETATION" | "HYPOTHETICAL_RISK" | "UNKNOWN";
  text: string;
  source_refs?: { source_id: string; source_version: string; locator: string }[];
  excerpt?: string | null;
  value?: { value: string; unit: string; scale: string; period_label: string; basis: string; version_shown: string } | null;
  calculation_ref?: string | null;
  calculation_version?: string | null;
  input_claim_ids?: string[];
  premise_claim_ids?: string[];
  verification: string;
  unknown_reason?: string | null;
}

export interface ReportDocumentBody {
  report_id: string;
  report_version: number;
  isin: string;
  question: string;
  mode: ReportMode;
  scope: ReportScope;
  as_of: string;
  cutoff: string | null;
  status: "READY_WITH_LIMITATIONS" | "READY_CHECKED_SCOPE";
  decision_notice: string;
  coverage: {
    isin: string;
    requested_years: number;
    basis: string;
    cells: { cell_id: string; period: { label: string; months: number }; statement: string; basis: string; status: string; gap_code: string | null }[];
  };
  sections: { section_id: string; status: "COVERED" | "PARTIAL" | "UNKNOWN"; claim_ids: string[]; limitations: { code: string; applies_to: string }[] }[];
  claims: ReportClaim[];
  sources: { source_id: string; title: string; origin: string; attribution: string; published_on: string | null; retrieved_at: string; rights: Record<string, string>; link: string | null }[];
  limitations: { code: string; applies_to: string }[];
}

export interface ReportDocumentOut {
  report_id: string;
  report_document_id: string;
  status: "READY_WITH_LIMITATIONS" | "READY_CHECKED_SCOPE";
  document_sha256: string;
  retracted: boolean;
  retractions: { id: string; reason: string; detail: string | null; recorded_at: string }[];
  rights_changed: string[];
  document: ReportDocumentBody;
  artifacts: { id: string; format: "HTML" | "PDF"; sha256: string; byte_size: number; page_count: number | null; renderer: string; recorded_at: string }[];
  withheld: Record<string, string[]>;
}

interface Ctx {
  investorId: string;
  token: string | null;
  idempotencyKey: string;
}

export const reports = {
  list: (inv: string, token: string | null) => api.get<ReportJob[]>(reportsBase(inv), { token }),
  get: (inv: string, token: string | null, id: string) => api.get<ReportJob>(`${reportsBase(inv)}/${enc(id)}`, { token }),
  events: (inv: string, token: string | null, id: string, after: number) =>
    api.get<{ items: JobEvent[]; next_cursor: number }>(`${reportsBase(inv)}/${enc(id)}/events?after=${after}`, { token }),
  document: (inv: string, token: string | null, id: string) =>
    api.get<ReportDocumentOut>(`${reportsBase(inv)}/${enc(id)}/document`, { token }),
  create: (ctx: Ctx, body: ReportRequest) =>
    api.post<ReportJob>(reportsBase(ctx.investorId), { token: ctx.token, json: body, headers: { "Idempotency-Key": ctx.idempotencyKey } }),
  cancel: (ctx: Ctx, id: string) =>
    api.post<ReportJob>(`${reportsBase(ctx.investorId)}/${enc(id)}/cancel`, { token: ctx.token, json: {}, headers: { "Idempotency-Key": ctx.idempotencyKey } }),
  revise: (ctx: Ctx, id: string, body: { question?: string; window_years?: number; budget: string; deadline_minutes: number }) =>
    api.post<ReportJob>(`${reportsBase(ctx.investorId)}/${enc(id)}/revisions`, { token: ctx.token, json: body, headers: { "Idempotency-Key": ctx.idempotencyKey } }),
  retract: (ctx: Ctx, id: string, detail: string | null) =>
    api.post<Record<string, string>>(`${reportsBase(ctx.investorId)}/${enc(id)}/retractions`, {
      token: ctx.token,
      json: detail ? { detail } : {},
      headers: { "Idempotency-Key": ctx.idempotencyKey },
    }),
};

/**
 * Download a private artifact through the AUTHENTICATED route (never a public or signed link)
 * and hand it to the browser as a file. The server rechecks ownership, retraction, export
 * rights and the stored hash on every request.
 */
export async function downloadArtifact(
  investorId: string,
  token: string | null,
  reportId: string,
  artifactId: string,
  filename: string
): Promise<void> {
  // Same resolution as @trackr/core's api-client (which only parses JSON, so a binary
  // download cannot go through it). A production build without a base URL refuses.
  const base =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");
  if (!base) throw new Error("NEXT_PUBLIC_API_BASE_URL is not set for this build.");
  const url = new URL(`${reportsBase(investorId)}/${enc(reportId)}/artifacts/${enc(artifactId)}`, base);
  const res = await fetch(url.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (!res.ok) {
    let message = `download refused (${res.status})`;
    try {
      const body = await res.json();
      message = body?.detail?.message ?? body?.message ?? message;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
}
