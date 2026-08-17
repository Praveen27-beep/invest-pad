"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api-client";
import type { InvestorIn, InvestorOut } from "@/lib/api-types";
import { AccountOnboarding } from "../components/AccountOnboarding";
import { ConsentCapture } from "../components/ConsentCapture";

const EMPTY_INVESTOR: InvestorIn = { code: "", display_name: "", family_group_id: null, onboarding_date: null };

export default function SettingsPage() {
  const { user, investorId, setInvestorId, token } = useAuth();
  const [draft, setDraft] = useState(investorId);
  const [saved, setSaved] = useState(false);

  const [newInvestor, setNewInvestor] = useState<InvestorIn>(EMPTY_INVESTOR);
  const [creatingInvestor, setCreatingInvestor] = useState(false);
  const [investorError, setInvestorError] = useState<string | null>(null);
  const [investorCreated, setInvestorCreated] = useState(false);

  function setInvestorField<K extends keyof InvestorIn>(key: K, value: InvestorIn[K]) {
    setNewInvestor((f) => ({ ...f, [key]: value }));
  }

  async function handleCreateInvestor(e: React.FormEvent) {
    e.preventDefault();
    setCreatingInvestor(true);
    setInvestorError(null);
    try {
      const investor = await api.post<InvestorOut>("/investors", {
        json: {
          ...newInvestor,
          code: newInvestor.code.trim(),
          display_name: newInvestor.display_name.trim(),
          family_group_id: newInvestor.family_group_id?.trim() || null,
        },
        token,
      });
      setInvestorId(investor.id);
      setDraft(investor.id);
      setNewInvestor(EMPTY_INVESTOR);
      setInvestorCreated(true);
      setTimeout(() => setInvestorCreated(false), 2000);
    } catch (err) {
      setInvestorError(err instanceof ApiError ? err.message : "Could not create investor");
    } finally {
      setCreatingInvestor(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <section className="glass-card rounded-xl border border-navy-100 p-6">
        <h2 className="font-heading text-lg text-navy-900 mb-4">Account</h2>
        <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-sm">
          <dt className="text-navy-400">Email</dt>
          <dd className="text-navy-700">{user?.email}</dd>
          <dt className="text-navy-400">Name</dt>
          <dd className="text-navy-700">{user?.display_name ?? "—"}</dd>
        </dl>
      </section>

      <section className="glass-card rounded-xl border border-navy-100 p-6">
        <h2 className="font-heading text-lg text-navy-900 mb-1">Investor</h2>
        <p className="text-sm text-navy-400 mb-4">
          There is currently no link between your login and a specific investor record.
          Paste the investor ID whose portfolio you want this browser to show.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setInvestorId(draft.trim());
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
          }}
          className="flex items-center gap-3"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            className="flex-1 rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
          />
          <button
            type="submit"
            className="press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600"
          >
            Save
          </button>
        </form>
        {saved && <p className="mt-2 text-xs text-positive">Saved.</p>}
      </section>

      <section className="glass-card rounded-xl border border-navy-100 p-6">
        <h2 className="font-heading text-lg text-navy-900 mb-1">Onboarding</h2>
        <p className="text-sm text-navy-400 mb-4">
          Create a new investor record. It becomes the active investor above as soon as
          it&apos;s created.
        </p>
        <form onSubmit={handleCreateInvestor} className="space-y-3">
          {investorError && (
            <p className="rounded-lg bg-negative/10 px-3 py-2 text-sm text-negative">{investorError}</p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Code</label>
              <input
                required
                value={newInvestor.code}
                onChange={(e) => setInvestorField("code", e.target.value)}
                placeholder="C001"
                className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Display name</label>
              <input
                required
                value={newInvestor.display_name}
                onChange={(e) => setInvestorField("display_name", e.target.value)}
                placeholder="Jane Doe"
                className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Family group ID (optional)</label>
              <input
                value={newInvestor.family_group_id ?? ""}
                onChange={(e) => setInvestorField("family_group_id", e.target.value || null)}
                className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm font-mono focus:border-brass-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-navy-600 mb-1">Onboarding date (optional)</label>
              <input
                type="date"
                value={newInvestor.onboarding_date ?? ""}
                onChange={(e) => setInvestorField("onboarding_date", e.target.value || null)}
                className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={creatingInvestor}
            className="press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-sm font-medium text-cream-50 hover:bg-navy-600 disabled:opacity-60"
          >
            {creatingInvestor ? "Adding…" : "Add investor"}
          </button>
          {investorCreated && <p className="text-xs text-positive">Created — set as the active investor above.</p>}
        </form>
      </section>

      <section className="glass-card rounded-xl border border-navy-100 p-6">
        <h2 className="font-heading text-lg text-navy-900 mb-1">Consent</h2>
        <p className="text-sm text-navy-400 mb-4">
          Required under the DPDP Act, 2023, before any of this investor&apos;s data can be
          imported, forwarded or entered — see docs/COMPLIANCE.md.
        </p>
        <ConsentCapture investorId={investorId} token={token} />
      </section>

      <section className="glass-card rounded-xl border border-navy-100 p-6">
        <h2 className="font-heading text-lg text-navy-900 mb-1">Broker accounts &amp; email forwarding</h2>
        <p className="text-sm text-navy-400 mb-4">
          Add a broker account to get its own forwarding address, then set up a filter in
          your email provider so future contract notes land here automatically.
        </p>
        <AccountOnboarding investorId={investorId} token={token} />
      </section>

      <section className="glass-card rounded-xl border border-navy-100 p-6">
        <h2 className="font-heading text-lg text-navy-900 mb-1">Privacy &amp; your data</h2>
        <p className="text-sm text-navy-400 mb-4">
          Export everything held about this investor, or permanently delete their record —
          your rights under the DPDP Act, 2023.
        </p>
        <a
          href="/privacy"
          className="press-scale inline-block rounded-lg border border-navy-100 px-4 py-2 text-sm font-medium text-navy-700 hover:bg-cream-200"
        >
          Go to Privacy &amp; data →
        </a>
      </section>
    </div>
  );
}
