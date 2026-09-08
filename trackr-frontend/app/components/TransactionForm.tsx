"use client";

import { useState } from "react";
import { TXN_TYPES, type TransactionIn, type TxnType } from "@/lib/api-types";

const EMPTY: TransactionIn = {
  account_id: "",
  isin: "",
  txn_date: new Date().toISOString().slice(0, 10),
  txn_type: "BUY",
  quantity: "",
  price: "",
  charges: "0",
  dividend_amount: "0",
  source: "MANUAL",
};

export function TransactionForm({
  knownAccountIds,
  initialIsin,
  onSubmit,
}: {
  knownAccountIds: string[];
  initialIsin?: string;
  onSubmit: (txn: TransactionIn) => Promise<void>;
}) {
  const [form, setForm] = useState<TransactionIn>({ ...EMPTY, isin: initialIsin ?? "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function set<K extends keyof TransactionIn>(key: K, value: TransactionIn[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await onSubmit(form);
      setSuccess(true);
      setForm({ ...EMPTY, account_id: form.account_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save transaction");
    } finally {
      setSubmitting(false);
    }
  }

  const isDividend = form.txn_type === "DIVIDEND";

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>}
      {success && <p className="rounded-lg bg-positive/10 px-3 py-2 text-sm text-positive">Transaction saved.</p>}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">Account ID</label>
          <input
            required
            list="known-accounts"
            value={form.account_id}
            onChange={(e) => set("account_id", e.target.value)}
            placeholder="account UUID"
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
          />
          <datalist id="known-accounts">
            {knownAccountIds.map((id) => (
              <option key={id} value={id} />
            ))}
          </datalist>
          <p className="mt-1 text-[11px] text-navy-400">
            Onboarding a new account isn&apos;t wired yet. Pick an account already seen on
            this investor&apos;s ledger.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">ISIN</label>
          <input
            required
            pattern="IN[A-Z0-9]{10}"
            value={form.isin}
            onChange={(e) => set("isin", e.target.value.toUpperCase())}
            placeholder="INE000A00000"
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono uppercase focus:border-brass-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">Date</label>
          <input
            type="date"
            required
            value={form.txn_date}
            onChange={(e) => set("txn_date", e.target.value)}
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">Type</label>
          <select
            value={form.txn_type}
            onChange={(e) => set("txn_type", e.target.value as TxnType)}
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
          >
            {TXN_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">Quantity</label>
          <input
            required
            inputMode="decimal"
            value={form.quantity}
            onChange={(e) => set("quantity", e.target.value)}
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm tabular-nums focus:border-brass-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">Price / unit</label>
          <input
            required
            inputMode="decimal"
            value={form.price}
            onChange={(e) => set("price", e.target.value)}
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm tabular-nums focus:border-brass-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-navy-600 mb-1">Charges</label>
          <input
            inputMode="decimal"
            value={form.charges}
            onChange={(e) => set("charges", e.target.value)}
            className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm tabular-nums focus:border-brass-500 focus:outline-none"
          />
        </div>

        {isDividend && (
          <div>
            <label className="block text-xs font-medium text-navy-600 mb-1">Dividend amount</label>
            <input
              inputMode="decimal"
              value={form.dividend_amount}
              onChange={(e) => set("dividend_amount", e.target.value)}
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm tabular-nums focus:border-brass-500 focus:outline-none"
            />
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="press-scale rounded-lg bg-navy-700 transition-colors px-5 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
      >
        {submitting ? "Saving…" : "Add transaction"}
      </button>
    </form>
  );
}
