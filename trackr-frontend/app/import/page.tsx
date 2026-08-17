"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { StageResultOut } from "@/lib/api-types";
import { Card, ErrorState, NoInvestorState } from "../components/PageState";
import { StagingBatch } from "../components/StagingBatch";

export default function ImportPage() {
  const { investorId, token } = useAuth();
  const [accountId, setAccountId] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [batches, setBatches] = useState<StageResultOut[]>([]);

  if (!investorId) return <NoInvestorState />;

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!files || files.length === 0) {
      setError("Choose at least one file");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.set("investor_id", investorId);
      formData.set("account_id", accountId);
      formData.set("adapter", "zerodha_tradebook");
      for (const file of Array.from(files)) formData.append("files", file);

      const results = await api.post<StageResultOut[]>("/ingest/csv", { formData, token });
      setBatches((prev) => [...results, ...prev]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Upload a tradebook">
        <form onSubmit={handleUpload} className="space-y-4">
          {error && <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Account ID</label>
              <input
                required
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                placeholder="account UUID"
                className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
              />
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
              type="file"
              multiple
              accept=".csv"
              onChange={(e) => setFiles(e.target.files)}
              className="block w-full text-sm text-navy-600 file:mr-3 file:rounded-lg file:border-0 file:bg-navy-700 file:px-4 file:py-2 file:text-cream-50 file:text-sm"
            />
            <p className="mt-1 text-[11px] text-navy-400">
              Console caps each tradebook export at 365 days — upload several files for a
              longer history; each is staged independently and de-duplicated on promote.
            </p>
          </div>

          <button
            type="submit"
            disabled={uploading}
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

      <p className="text-xs text-navy-400">
        Nothing here writes to the ledger automatically — every row is staged first and
        only reaches the transaction ledger once you promote its batch.
      </p>
    </div>
  );
}
