"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { api, ApiError } from "@/lib/api-client";
import type { PromoteResultOut, ReviewBatchOut, StageResultOut } from "@/lib/api-types";
import { LoadingState } from "./PageState";

export function StagingBatch({ stageResult }: { stageResult: StageResultOut }) {
  const { token } = useAuth();
  const review = useFetch<ReviewBatchOut>(`/ingest/stage/${stageResult.batch_id}`, undefined, token);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function promote() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.post<PromoteResultOut>(`/ingest/stage/${stageResult.batch_id}/promote`, { token });
      setMessage(`Promoted: ${res.inserted} inserted, ${res.skipped_duplicates} duplicates skipped.`);
      review.refetch();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Promote failed");
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    setBusy(true);
    setMessage(null);
    try {
      await api.post(`/ingest/stage/${stageResult.batch_id}/discard`, {
        json: { reason: "discarded from Import review screen" },
        token,
      });
      setMessage("Batch discarded.");
      review.refetch();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Discard failed");
    } finally {
      setBusy(false);
    }
  }

  const b = review.data;

  return (
    <div className="glass-card animate-fade-in-up rounded-lg border border-navy-100 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-navy-900">{b?.filename ?? stageResult.batch_id}</p>
          <p className="text-xs text-navy-400 font-mono">{stageResult.batch_id}</p>
        </div>
        {b && (
          <span className="rounded bg-cream-200 px-2 py-1 text-xs font-medium text-navy-700">
            {b.status}
          </span>
        )}
      </div>

      {review.loading && <LoadingState label="Loading review…" />}
      {review.error && <p className="mt-2 text-xs text-negative">{review.error}</p>}

      {b && (
        <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-navy-400 text-xs">Will insert</p>
            <p className="tabular-nums text-navy-900">{b.will_insert}</p>
          </div>
          <div>
            <p className="text-navy-400 text-xs">Will skip (duplicate)</p>
            <p className="tabular-nums text-navy-900">{b.will_skip_as_duplicate}</p>
          </div>
          <div>
            <p className="text-navy-400 text-xs">Rejected</p>
            <p className="tabular-nums text-navy-900">{b.rejected_count}</p>
          </div>
        </div>
      )}

      {b && b.needs_review.length > 0 && (
        <p className="mt-2 text-xs text-brass-600">
          {b.needs_review.length} row(s) need review before promoting.
        </p>
      )}
      {b && b.rejections.length > 0 && (
        <ul className="mt-2 text-xs text-negative list-disc list-inside">
          {b.rejections.slice(0, 5).map((r) => (
            <li key={r.row_number}>
              Row {r.row_number}: {r.reason}
            </li>
          ))}
        </ul>
      )}

      {b && b.status === "STAGED" && (
        <div className="mt-4 flex gap-3">
          <button
            onClick={promote}
            disabled={busy}
            className="press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-xs font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
          >
            Promote to ledger
          </button>
          <button
            onClick={discard}
            disabled={busy}
            className="press-scale rounded-lg border border-navy-100 px-4 py-2 text-xs text-navy-600 transition-colors hover:bg-cream-50 disabled:opacity-60"
          >
            Discard
          </button>
        </div>
      )}

      {message && <p className="mt-2 text-xs text-navy-600">{message}</p>}
    </div>
  );
}
