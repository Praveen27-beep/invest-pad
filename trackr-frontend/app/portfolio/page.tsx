"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { TabBar } from "../components/TabBar";
import { TransactionsTab } from "../components/tabs/TransactionsTab";
import { ImportTab } from "../components/tabs/ImportTab";
import { ReconcileTab } from "../components/tabs/ReconcileTab";

const PORTFOLIO_TABS = [
  { key: "transactions", label: "Transactions" },
  { key: "import", label: "Import" },
  { key: "reconcile", label: "Reconcile" },
];

export default function PortfolioPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") ?? "transactions";

  function setActiveTab(key: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", key);
    router.push(`/portfolio?${params.toString()}`);
  }

  return (
    <div className="space-y-6">
      <TabBar tabs={PORTFOLIO_TABS} active={activeTab} onChange={setActiveTab} />
      {activeTab === "import" ? (
        <ImportTab />
      ) : activeTab === "reconcile" ? (
        <ReconcileTab />
      ) : (
        <TransactionsTab />
      )}
    </div>
  );
}
