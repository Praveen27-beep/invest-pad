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
 * unlike a plain tradebook CSV.
 *
 * Phase 1 only supports one broker (see CLAUDE.md), so there's nothing for the
 * investor to choose here: the first account is auto-selected, and if they have
 * none yet one is created silently. Surfacing an account picker in a two-click
 * "upload a file" flow was a dead end -- an investor with zero accounts saw a
 * permanently disabled Import button and no way out short of leaving the modal. */
export function HistoricalImportStep({ onUploaded }: { onUploaded: () => void }) {
  const { investorId, token } = useAuth();
  const [accountId, setAccountId] = useState("");
  const [settingUpAccount, setSettingUpAccount] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StageResultOut | null>(null);
  const [showHelp, setShowHelp] = useState(false);
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

  // Zero accounts is the common case for a brand-new investor -- create a
  // default one instead of sending them to Settings mid-import.
  useEffect(() => {
    if (!investorId || accounts.loading || settingUpAccount || accountError) return;
    if (accounts.data && accounts.data.length === 0) {
      setSettingUpAccount(true);
      api
        .post<AccountOut>(`/investors/${investorId}/accounts`, { json: { broker: "ZERODHA" }, token })
        .then(() => accounts.refetch())
        .catch((err) => setAccountError(err instanceof ApiError ? err.message : "Could not set up your account"))
        .finally(() => setSettingUpAccount(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investorId, accounts.loading, accounts.data, token]);

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

  const accountReady = Boolean(accountId) && !settingUpAccount;

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
          {accountError && (
            <p className="rounded-lg bg-brass-50 border border-brass-200 px-3 py-2 text-sm text-brass-700">
              {accountError}
            </p>
          )}
          {result && result.parsed > 0 && (
            <p className="rounded-lg border border-positive/30 bg-positive/10 px-3 py-2 text-sm text-navy-900">
              {result.parsed} trade{result.parsed === 1 ? "" : "s"} imported.
            </p>
          )}

          <div className="flex justify-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brass-50">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-7 w-7 text-brass-600"
              >
                <path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
                <path d="M14 3v4h4" />
                <path d="M8.5 13 10.5 15 15 10.5" />
              </svg>
            </div>
          </div>

          <p className="text-center text-sm text-navy-600">
            This adds your past trades so we can calculate XIRR. Pick a date range when
            you download the contract note. You can add more files to cover more years.
          </p>

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
              Download this from Zerodha Console under Reports → Contract notes.
            </p>
          </div>

          <button
            type="submit"
            disabled={uploading || files.length === 0 || !accountReady}
            className="press-scale w-full rounded-lg bg-navy-700 px-5 py-2.5 text-sm font-medium text-cream-50 transition-colors hover:bg-navy-600 disabled:opacity-50"
          >
            {uploading ? "Importing…" : settingUpAccount ? "Preparing…" : "Import trades"}
          </button>

          <div className="text-center">
            <button
              type="button"
              onClick={() => setShowHelp((v) => !v)}
              className="text-xs text-brass-600 underline hover:text-brass-700"
            >
              How do I import my stock investments to Trackr+?
            </button>
            {showHelp && (
              <ol className="mt-2 list-decimal space-y-1 rounded-lg border border-navy-100 bg-cream-50 px-4 py-3 text-left text-xs text-navy-600 [&>li]:ml-3">
                <li>Log in to Zerodha Console.</li>
                <li>Go to Reports → Contract notes.</li>
                <li>Download the XLSX for the period you want — one file per financial year works well.</li>
                <li>Upload it above. Add more files for a longer history.</li>
              </ol>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
