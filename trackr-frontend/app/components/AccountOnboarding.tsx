"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { AccountIn, AccountOut } from "@/lib/api-types";
import { EmailForwardingSetup } from "./EmailForwardingSetup";

const EMPTY: AccountIn = { broker: "", dp_id: null, client_id: null, is_advised: true, label: null };

/** There is no GET /investors/{id}/accounts (contracts/openapi.yaml only defines the
 * POST) so an already-onboarded account can't be re-fetched -- this caches the exact
 * AccountOut responses this browser has already received from the backend, keyed per
 * investor. It is a cache of real server responses, never a fabricated address, and it
 * naturally clears if the investor ID (Settings, above) changes. */
function storageKey(investorId: string): string {
  return `trackr.accounts.${investorId}`;
}

function loadCached(investorId: string): AccountOut[] {
  try {
    const raw = localStorage.getItem(storageKey(investorId));
    return raw ? (JSON.parse(raw) as AccountOut[]) : [];
  } catch {
    return [];
  }
}

export function AccountOnboarding({ investorId, token }: { investorId: string; token: string | null }) {
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [form, setForm] = useState<AccountIn>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAccounts(investorId ? loadCached(investorId) : []);
  }, [investorId]);

  function set<K extends keyof AccountIn>(key: K, value: AccountIn[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!investorId) return;
    setSubmitting(true);
    setError(null);
    try {
      const account = await api.post<AccountOut>(`/investors/${investorId}/accounts`, {
        json: { ...form, broker: form.broker.trim().toUpperCase() },
        token,
      });
      setAccounts((prev) => {
        const next = [account, ...prev];
        localStorage.setItem(storageKey(investorId), JSON.stringify(next));
        return next;
      });
      setForm(EMPTY);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add account");
    } finally {
      setSubmitting(false);
    }
  }

  if (!investorId) {
    return <p className="text-sm text-navy-400">Save an investor ID above before adding a broker account.</p>;
  }

  const ingestDomain = process.env.NEXT_PUBLIC_INGEST_DOMAIN;

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Broker</label>
            <input
              required
              value={form.broker}
              onChange={(e) => set("broker", e.target.value)}
              placeholder="ZERODHA"
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm uppercase focus:border-brass-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Label (optional)</label>
            <input
              value={form.label ?? ""}
              onChange={(e) => set("label", e.target.value || null)}
              placeholder="Primary Zerodha"
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">DP ID (optional)</label>
            <input
              value={form.dp_id ?? ""}
              onChange={(e) => set("dp_id", e.target.value || null)}
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Client ID (optional)</label>
            <input
              value={form.client_id ?? ""}
              onChange={(e) => set("client_id", e.target.value || null)}
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
        >
          {submitting ? "Adding…" : "Add account"}
        </button>
      </form>

      {accounts.length === 0 ? (
        <p className="text-sm text-navy-400">
          No accounts added yet in this browser. Add one above — its real forwarding address will
          appear here{ingestDomain ? ` (e.g. c001-zerodha-contractnote@${ingestDomain})` : ""}.
        </p>
      ) : (
        <div className="space-y-4">
          {accounts.map((a) => (
            <div key={a.id} className="rounded-xl border border-navy-100 p-4">
              <div className="mb-3">
                <p className="text-sm font-medium text-navy-900">
                  {a.label ?? a.broker} <span className="font-normal text-navy-400">({a.broker})</span>
                </p>
                <p className="text-xs text-navy-400 font-mono">{a.id}</p>
              </div>
              <EmailForwardingSetup account={a} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
