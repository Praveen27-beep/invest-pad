"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useAIChat } from "@/lib/ai-chat-context";
import { api, ApiError } from "@/lib/api-client";
import { useFetch } from "@/lib/use-fetch";
import type { AccountOut, SkippedHoldingOut } from "@/lib/api-types";

/** One day before an ISO date string -- the synthetic opening BUY must predate the
 * disposal that ran short, or it does nothing to close the gap. */
function dayBefore(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function QuickFixRow({ skipped, onFixed }: { skipped: SkippedHoldingOut; onFixed: () => void }) {
  const { investorId, token } = useAuth();
  const { openChat } = useAIChat();
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState(skipped.deficit ?? "");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(skipped.as_of ? dayBefore(skipped.as_of) : "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const accounts = useFetch<AccountOut[]>(
    open && investorId ? `/investors/${investorId}/accounts` : null,
    undefined,
    token
  );
  const [accountId, setAccountId] = useState("");
  const accountList = accounts.data ?? [];
  useEffect(() => {
    const first = accountList[0];
    if (first && !accountId) setAccountId(first.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountList.length]);

  const label = skipped.name || skipped.isin;

  function askAI() {
    openChat({
      context: `Trackr+ is showing a "negative holding" error for ${label} (ISIN ${skipped.isin}): ${skipped.message}`,
      initialQuestion: `Why is ${label} showing this error, and what should I do to fix it?`,
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!investorId || !accountId || !quantity || !price || !date) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/investors/${investorId}/transactions`, {
        json: [
          {
            account_id: accountId,
            isin: skipped.isin,
            txn_date: date,
            txn_type: "BUY",
            quantity,
            price,
            charges: "0",
            raw_payload: {
              cost_estimated: true,
              note: "Backfilled to close a negative-holding gap -- exact cost unknown, average price entered by hand.",
            },
          },
        ],
        token,
      });
      setDone(true);
      onFixed();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add this transaction");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <li className="rounded-lg border border-negative/20 bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-navy-700">
          <span className="font-medium">{label}</span> — {skipped.message}
        </span>
        {!done && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={askAI}
              className="press-scale rounded-lg border border-navy-100 px-3 py-1 text-xs font-medium text-navy-600 hover:bg-cream-50"
            >
              Ask AI
            </button>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="press-scale rounded-lg bg-navy-700 px-3 py-1 text-xs font-medium text-cream-50 transition-colors hover:bg-navy-600"
            >
              {open ? "Cancel" : "Enter average price"}
            </button>
          </div>
        )}
        {done && <span className="text-xs font-medium text-positive">Added — recomputing…</span>}
      </div>

      {open && !done && (
        <form onSubmit={submit} className="mt-3 space-y-2 border-t border-navy-50 pt-3">
          <p className="text-xs text-navy-500">
            Don&apos;t have the original contract note? Enter what you know — quantity, an
            average buy price, and roughly when. This is recorded as an estimated cost
            (flagged as such everywhere it&apos;s shown) so the gap closes without
            pretending to be an exact broker record.
          </p>
          {error && (
            <p className="rounded-lg bg-negative/10 px-2 py-1.5 text-xs text-negative">{error}</p>
          )}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <label className="text-xs text-navy-600">
              <span className="mb-1 block font-medium">Quantity</span>
              <input
                required
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="w-full rounded-lg border border-navy-100 bg-surface px-2 py-1.5 text-sm focus:border-brass-500 focus:outline-none"
              />
            </label>
            <label className="text-xs text-navy-600">
              <span className="mb-1 block font-medium">Avg. price</span>
              <input
                required
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="e.g. 245.50"
                className="w-full rounded-lg border border-navy-100 bg-surface px-2 py-1.5 text-sm focus:border-brass-500 focus:outline-none"
              />
            </label>
            <label className="text-xs text-navy-600">
              <span className="mb-1 block font-medium">Date</span>
              <input
                required
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-lg border border-navy-100 bg-surface px-2 py-1.5 text-sm focus:border-brass-500 focus:outline-none"
              />
            </label>
            <label className="text-xs text-navy-600">
              <span className="mb-1 block font-medium">Account</span>
              {accountList.length === 0 ? (
                <span className="block py-1.5 text-navy-400">None yet</span>
              ) : (
                <select
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  className="w-full rounded-lg border border-navy-100 bg-surface px-2 py-1.5 text-sm focus:border-brass-500 focus:outline-none"
                >
                  {accountList.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.broker}
                      {a.label ? ` — ${a.label}` : ""}
                    </option>
                  ))}
                </select>
              )}
            </label>
          </div>
          <button
            type="submit"
            disabled={submitting || accountList.length === 0}
            className="press-scale rounded-lg bg-navy-700 px-4 py-1.5 text-xs font-medium text-cream-50 transition-colors hover:bg-navy-600 disabled:opacity-50"
          >
            {submitting ? "Adding…" : "Add and recompute"}
          </button>
        </form>
      )}
    </li>
  );
}

/**
 * compute_holdings_partitioned's `skipped` list (app/engine/holdings.py) -- an ISIN
 * whose own ledger segment didn't reconcile, excluded from the dashboard's totals
 * rather than blocking every other holding. Same "actionable, not a dead end" posture
 * as UnpricedBanner, plus a quick way out: enter a remembered average price instead of
 * hunting down the original contract note, or ask the AI assistant what's going on.
 */
export function SkippedHoldingsBanner({
  skipped,
  onFixed,
}: {
  skipped: SkippedHoldingOut[];
  onFixed: () => void;
}) {
  if (skipped.length === 0) return null;

  return (
    <div className="rounded-lg border border-negative/30 bg-negative/10 px-4 py-3">
      <p className="text-sm font-medium text-negative">
        {skipped.length} holding{skipped.length > 1 ? "s" : ""} excluded — buy history is
        incomplete
      </p>
      <p className="mt-1 text-xs text-navy-500">
        Everything else below is unaffected. These specific ISINs are left out until the
        gap is closed, either by importing the missing contract note or entering an
        average price below.
      </p>
      <ul className="mt-3 space-y-2 text-xs">
        {skipped.map((s) => (
          <QuickFixRow key={s.isin} skipped={s} onFixed={onFixed} />
        ))}
      </ul>
    </div>
  );
}
