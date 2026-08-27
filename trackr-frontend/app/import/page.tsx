"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type {
  AccountOut,
  BatchSummaryOut,
  ConsentStatusOut,
  StageResultOut,
} from "@/lib/api-types";
import { useFetch } from "@/lib/use-fetch";
import { Card, NoInvestorState } from "../components/PageState";
import { ConsentCapture } from "../components/ConsentCapture";
import { StagingBatch } from "../components/StagingBatch";

function summaryFromBatchRow(row: BatchSummaryOut): StageResultOut {
  return {
    batch_id: row.batch_id,
    parsed: row.row_count,
    rejected: row.rejected_count,
    sha256: "",
    document_id: null,
    notes: [],
  };
}

export default function ImportPage() {
  const { investorId, token } = useAuth();
  const [accountId, setAccountId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [stagedSummary, setStagedSummary] = useState<string | null>(null);
  const [batches, setBatches] = useState<StageResultOut[]>([]);
  const [searchBatchId, setSearchBatchId] = useState("");
  const [hasLiveConsent, setHasLiveConsent] = useState<boolean | null>(null);

  // The staged-batch list lives on the SERVER, not in this component's state -- a
  // refresh used to orphan every staged batch behind a UUID nobody could see anywhere.
  const refreshBatches = useCallback(async () => {
    if (!token || !investorId) return;
    try {
      const rows = await api.get<BatchSummaryOut[]>("/ingest/batches", {
        query: { investor_id: investorId, status: "STAGED" },
        token,
      });
      setBatches(rows.map(summaryFromBatchRow));
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }, [investorId, token]);

  useEffect(() => {
    void refreshBatches();
  }, [refreshBatches]);

  // Real GET endpoints now exist for both; no more localStorage caching or pasted IDs.
  const accounts = useFetch<AccountOut[]>(
    investorId ? `/investors/${investorId}/accounts` : null,
    undefined,
    token
  );

  useEffect(() => {
    if (!investorId) return;
    let cancelled = false;
    api
      .get<ConsentStatusOut>(`/investors/${investorId}/consent`, { token })
      .then((s) => {
        if (!cancelled) setHasLiveConsent(s.has_live_consent);
      })
      .catch(() => {
        if (!cancelled) setHasLiveConsent(null);
      });
    return () => {
      cancelled = true;
    };
  }, [investorId, token]);

  // Exactly one account selects itself -- the common case is one broker, one login.
  useEffect(() => {
    const first = accounts.data?.[0];
    if (first && !accountId) {
      setAccountId(first.id);
    }
  }, [accounts.data, accountId]);

  if (!investorId) return <NoInvestorState />;

  const accountList = accounts.data ?? [];

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0) {
      setError("Choose at least one file");
      return;
    }
    if (!accountId) {
      setError("Choose the account these trades belong to");
      return;
    }
    setUploading(true);
    setError(null);
    setStagedSummary(null);
    try {
      const formData = new FormData();
      formData.set("investor_id", investorId);
      formData.set("account_id", accountId);
      formData.set("adapter", "zerodha_tradebook");
      for (const file of files) formData.append("files", file);

      const results = await api.post<StageResultOut[]>("/ingest/csv", { formData, token });
      // Re-read the server's list rather than splicing local state -- a duplicate
      // comes back pointing at its existing batch, and the server list is the truth.
      await refreshBatches();
      const parsed = results.reduce((n, r) => n + r.parsed, 0);
      const rejected = results.reduce((n, r) => n + r.rejected, 0);
      const notes = results.flatMap((r) => r.notes);
      setStagedSummary(
        `${files.length} file(s) uploaded — ${parsed} row(s) staged` +
          (rejected ? `, ${rejected} rejected` : "") +
          ". Review " +
          (batches.length ? "the batch(es) below." : "below — the staged batch card is under this form.") +
          (notes.length ? ` Server notes: ${notes.join("; ")}` : "")
      );
      setFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function handleLoadBatch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = searchBatchId.trim();
    if (!trimmed) return;
    setBatches((prev) => {
      if (prev.some((b) => b.batch_id === trimmed)) return prev;
      return [
        {
          batch_id: trimmed,
          parsed: 0,
          rejected: 0,
          sha256: "",
          document_id: null,
          notes: [],
        },
        ...prev,
      ];
    });
    setSearchBatchId("");
    setError(null);
  }

  return (
    <div className="space-y-6">
      <Card title="Upload a tradebook">
        <form onSubmit={handleUpload} className="space-y-4">
          {error && <p className="rounded-lg bg-brass-50 border border-brass-200 px-3 py-2 text-sm text-brass-700">{error}</p>}
          {stagedSummary && (
            <p className="rounded-lg border border-positive/30 bg-positive/10 px-3 py-2 text-sm text-navy-900">
              {stagedSummary}
            </p>
          )}

          {hasLiveConsent === false && (
            <div className="rounded-lg border border-brass-300 bg-cream-50 p-4">
              <p className="text-sm font-medium text-navy-900 mb-2">
                One step first: record consent for this investor
              </p>
              <p className="text-xs text-navy-500 mb-3">
                Indian data-protection law (DPDP) requires an explicit OK before this app
                processes anyone&apos;s statements — including your own. It&apos;s a
                one-time click per investor.
              </p>
              <ConsentCapture
                investorId={investorId}
                token={token}
                onStatusChange={(live) => setHasLiveConsent(live)}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Account</label>
              {accounts.loading ? (
                <select disabled className="w-full rounded-lg border border-navy-100 bg-cream-50 px-3 py-2 text-sm text-navy-400">
                  <option>Loading accounts…</option>
                </select>
              ) : accountList.length === 0 ? (
                <div className="rounded-lg border border-brass-200 bg-cream-50 px-3 py-2 text-sm text-brass-700">
                  No broker account yet.{" "}
                  <Link href="/settings" className="underline font-medium">
                    Add one in Settings
                  </Link>{" "}
                  (takes a few seconds), then come back.
                </div>
              ) : (
                <select
                  required
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm text-navy-700 focus:border-brass-500 focus:outline-none"
                >
                  {accountList.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.broker}
                      {a.label ? ` — ${a.label}` : ""}
                      {a.client_id ? ` (${a.client_id})` : ""}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Adapter</label>
              <select
                disabled
                value="zerodha_tradebook"
                className="w-full rounded-lg border border-navy-100 bg-cream-50 px-3 py-2 text-sm text-navy-700"
              >
                <option value="zerodha_tradebook">Zerodha tradebook (CSV)</option>
                <option value="generic_csv" disabled>
                  Generic CSV — not implemented yet
                </option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Files</label>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".csv"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="block w-full text-sm text-navy-600 file:mr-3 file:rounded-lg file:border-0 file:bg-navy-700 file:px-4 file:py-2 file:text-cream-50 file:text-sm"
            />
            {files.length > 0 && (
              <p className="mt-1 text-xs font-medium text-navy-700">
                {files.length === 1 ? files[0]?.name : `${files.length} files selected`}
              </p>
            )}
            <p className="mt-1 text-[11px] text-navy-400">
              Console caps each tradebook export at 365 days — upload several files at
              once for a longer history. A re-uploaded file is simply matched to its
              existing batch; nothing is uploaded twice.
            </p>
          </div>

          <button
            type="submit"
            disabled={uploading || accountList.length === 0 || hasLiveConsent === false}
            title={
              hasLiveConsent === false
                ? "Record consent above first"
                : accountList.length === 0
                  ? "Add a broker account in Settings first"
                  : undefined
            }
            className="press-scale rounded-lg bg-navy-700 transition-colors px-5 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
          >
            {uploading ? "Uploading…" : "Upload & stage"}
          </button>
        </form>
      </Card>

      {batches.length > 0 && (
        <Card title="Review staged batches">
          <div className="space-y-4">
            {batches.map((b) => (
              <StagingBatch key={b.batch_id} stageResult={b} />
            ))}
          </div>
        </Card>
      )}

      <Card title="Review existing batch by ID">
        <form onSubmit={handleLoadBatch} className="flex gap-3">
          <input
            type="text"
            value={searchBatchId}
            onChange={(e) => setSearchBatchId(e.target.value)}
            placeholder="e.g. c195c00f-264c-4fae-ad45-d1135da22ed2"
            className="flex-1 rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
          />
          <button
            type="submit"
            className="press-scale rounded-lg border border-navy-200 bg-cream-100 px-4 py-2 text-sm font-medium text-navy-700 hover:bg-cream-200"
          >
            Load Batch
          </button>
        </form>
      </Card>

      <p className="text-xs text-navy-400">
        Nothing here writes to the ledger automatically — every row is staged first and
        only reaches the transaction ledger once you promote its batch.
      </p>
    </div>
  );
}
