"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import { useFetch } from "@/lib/use-fetch";
import type { AccountOut, ConsentStatusOut, StageResultOut } from "@/lib/api-types";
import { ConsentCapture } from "../ConsentCapture";

/** MProfit's "Historical trade file" step (Mprofit files to import.png) -- the
 * one-time backfill path. Trackr's equivalent is a Zerodha Contract Note XLSX
 * export (POST /ingest/xlsx): the only source that carries both price AND charges,
 * unlike a plain tradebook CSV. */
export function HistoricalImportStep({ onUploaded }: { onUploaded: () => void }) {
  const { investorId, token } = useAuth();
  const [accountId, setAccountId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StageResultOut | null>(null);
  const [hasLiveConsent, setHasLiveConsent] = useState<boolean | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const accounts = useFetch<AccountOut[]>(
    investorId ? `/investors/${investorId}/accounts` : null,
    undefined,
    token
  );
  const accountList = accounts.data ?? [];

  useEffect(() => {
    const first = accountList[0];
    if (first && !accountId) setAccountId(first.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountList.length]);

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

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0 || !accountId) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.set("investor_id", investorId);
      formData.set("account_id", accountId);
      formData.set("adapter", "zerodha_contract_note_xlsx");
      for (const file of files) formData.append("files", file);

      const results = await api.post<StageResultOut[]>("/ingest/xlsx", { formData, token });
      const first = results[0];
      if (first) setResult(first);
      // Promote immediately -- this is the guided first-run path, not the power-user
      // review screen, so getting straight to "it's in your ledger" matters more than
      // a manual review step here.
      if (first && first.parsed > 0) {
        await api.post(`/ingest/stage/${first.batch_id}/promote`, { token });
        onUploaded();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  if (!investorId) return null;

  return (
    <div className="space-y-4">
      {hasLiveConsent === false && (
        <ConsentCapture investorId={investorId} token={token} onStatusChange={setHasLiveConsent} />
      )}

      {hasLiveConsent && (
        <form onSubmit={handleUpload} className="space-y-4">
          {error && (
            <p className="rounded-lg bg-brass-50 border border-brass-200 px-3 py-2 text-sm text-brass-700">{error}</p>
          )}
          {result && result.parsed > 0 && (
            <p className="rounded-lg border border-positive/30 bg-positive/10 px-3 py-2 text-sm text-navy-900">
              {result.parsed} trade{result.parsed === 1 ? "" : "s"} imported.
            </p>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-navy-600">Account</label>
            {accountList.length === 0 ? (
              <p className="text-sm text-navy-400">Add a broker account in Settings first.</p>
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
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-navy-600">
              Contract note (XLSX) from Zerodha Console
            </label>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".xlsx"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="block w-full text-sm text-navy-600 file:mr-3 file:rounded-lg file:border-0 file:bg-navy-700 file:px-4 file:py-2 file:text-sm file:text-cream-50"
            />
            <p className="mt-1 text-[11px] text-navy-400">
              This carries both trade price AND charges (brokerage, STT, GST) — a plain
              tradebook CSV has no charges. One file per financial year is normal;
              upload as many as you have.
            </p>
          </div>

          <button
            type="submit"
            disabled={uploading || files.length === 0 || !accountId}
            className="press-scale w-full rounded-lg bg-navy-700 px-5 py-2.5 text-sm font-medium text-cream-50 transition-colors hover:bg-navy-600 disabled:opacity-50"
          >
            {uploading ? "Importing…" : "Import trades"}
          </button>
        </form>
      )}
    </div>
  );
}
