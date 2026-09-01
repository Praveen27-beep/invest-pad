"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { formatMoney, formatDate } from "@/lib/format";
import type { HoldingsResponse, PerformanceResponse, SummaryResponse, TransactionOut } from "@/lib/api-types";
import { Card, ErrorState, LoadingState, NoInvestorState } from "./components/PageState";
import { KpiCard } from "./components/KpiCard";
import { DualXirrCard } from "./components/DualXirrCard";
import { MissingPriceNotice } from "./components/MissingPriceNotice";
import { NegativeHoldingNotice } from "./components/NegativeHoldingNotice";
import { AllocationDonut, type AllocationSlice } from "./components/AllocationDonut";
import { AllocationGroupsTable, type AllocationGroupRow } from "./components/AllocationGroupsTable";
import { HistoricalValueChart } from "./components/HistoricalValueChart";
import { HoldingsTable } from "./components/HoldingsTable";
import { UnpricedBanner } from "./components/UnpricedBanner";
import { SkippedHoldingsBanner } from "./components/SkippedHoldingsBanner";
import { TabBar } from "./components/TabBar";
import { HoldingsTab } from "./components/tabs/HoldingsTab";
import { PerformanceTab } from "./components/tabs/PerformanceTab";
import { ContributionTab } from "./components/tabs/ContributionTab";

const DASHBOARD_TABS = [
  { key: "overview", label: "Overview" },
  { key: "holdings", label: "Holdings" },
  { key: "performance", label: "Performance" },
  { key: "contribution", label: "Contribution" },
];

type AllocationGroupBy = "asset_class" | "sector" | "market_cap_bucket";
type ValueBasis = "current" | "invested";

const GROUP_BY_LABEL: Record<AllocationGroupBy, string> = {
  asset_class: "Asset class",
  sector: "Sector",
  market_cap_bucket: "Market cap",
};

const PercentIcon = (
  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
    <path d="M14.5 5.5 5.5 14.5M6.4 6.9a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8ZM13.6 16.3a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8Z" />
  </svg>
);

/** Sum of `invested` across a group's holdings -- real per-security data already on
 * the wire (HoldingOut.invested), just aggregated at display time for the "Invested"
 * basis toggle and the current-holdings table. Never a fabricated figure. */
function sumInvested(children: { invested: string }[]): number {
  return children.reduce((sum, h) => sum + (Number(h.invested) || 0), 0);
}

function OverviewTab() {
  const { investorId, token, asOf, advisedOnly } = useAuth();
  const [allocationGroupBy, setAllocationGroupBy] = useState<AllocationGroupBy>("asset_class");
  const [valueBasis, setValueBasis] = useState<ValueBasis>("current");
  const query = { as_of: asOf, advised_only: advisedOnly || undefined };

  const summary = useFetch<SummaryResponse>(
    investorId ? `/investors/${investorId}/summary` : null,
    query,
    token
  );
  const performance = useFetch<PerformanceResponse>(
    investorId ? `/investors/${investorId}/performance` : null,
    { as_of: asOf },
    token
  );
  const holdings = useFetch<HoldingsResponse>(
    investorId ? `/investors/${investorId}/holdings` : null,
    query,
    token
  );
  const transactions = useFetch<TransactionOut[]>(
    investorId ? `/investors/${investorId}/transactions` : null,
    undefined,
    token
  );

  if (!investorId) return <NoInvestorState />;

  // performance.error is deliberately excluded here: /performance can 409 with
  // MissingPriceError (XIRR needs every held ISIN priced) even when /summary and
  // /holdings succeed by partitioning the same unpriced holding out via UnpricedBanner.
  // Blocking the whole dashboard on that would make UnpricedBanner unreachable in
  // exactly the case it exists for -- so only a summary/holdings failure is fatal here.
  const blockingErrorDetail = summary.errorDetail ?? holdings.errorDetail;
  const blockingError = summary.error ?? holdings.error;
  if (blockingErrorDetail?.isin) {
    return (
      <NegativeHoldingNotice
        isin={blockingErrorDetail.isin}
        name={blockingErrorDetail.securityName}
        deficit={blockingErrorDetail.deficit}
        asOf={blockingErrorDetail.asOf}
      />
    );
  }
  if (blockingError) return <ErrorState message={blockingError} />;

  if (summary.loading || performance.loading) return <LoadingState label="Loading portfolio…" />;

  const s = summary.data;
  const p = performance.data;
  const recentTxns = (transactions.data ?? [])
    .slice()
    .sort((a, b) => (a.txn_date < b.txn_date ? 1 : -1))
    .slice(0, 6);
  const topHoldings = (holdings.data?.holdings ?? []).slice(0, 5);

  // AllocationDonut/AllocationGroupsTable are grouping-agnostic; adapt whichever of the
  // three /summary arrays is currently selected into one normalised row shape here, at
  // the call site. `invested` is summed from each group's real per-holding figures
  // (never fabricated) so the "Invested" value-basis toggle and the holdings table's
  // Invested column both have something real to show.
  const groupRows: AllocationGroupRow[] =
    allocationGroupBy === "sector"
      ? (s?.allocation_by_sector ?? []).map((g) => ({
          key: g.sector,
          label: g.label,
          invested: sumInvested(g.children),
          marketValue: g.market_value ? Number(g.market_value) : 0,
          weightPct: g.weight_pct,
        }))
      : allocationGroupBy === "market_cap_bucket"
        ? (s?.allocation_by_market_cap ?? []).map((g) => ({
            key: g.market_cap_bucket,
            label: g.label,
            invested: sumInvested(g.children),
            marketValue: g.market_value ? Number(g.market_value) : 0,
            weightPct: g.weight_pct,
          }))
        : (s?.allocation ?? []).map((g) => ({
            key: g.asset_class,
            label: g.label,
            invested: sumInvested(g.children),
            marketValue: g.market_value ? Number(g.market_value) : 0,
            weightPct: g.weight_pct,
          }));

  const totalInvested = s?.invested ? Number(s.invested) : 0;
  const allocationSlices: AllocationSlice[] =
    valueBasis === "invested"
      ? groupRows.map((r) => ({
          key: r.key,
          label: r.label,
          weight_pct: totalInvested > 0 ? r.invested / totalInvested : null,
        }))
      : groupRows.map((r) => ({ key: r.key, label: r.label, weight_pct: r.weightPct }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <KpiCard label="Invested" value={formatMoney(s?.invested)} sublabel="Net of brokerage & STT" />
        <KpiCard label="Current value" value={formatMoney(s?.market_value)} sublabel={`As of ${formatDate(s?.as_of)}`} />
        <KpiCard
          label="Unrealised P&L"
          value={formatMoney(s?.unrealised)}
          sublabel={s?.unrealised_pct != null ? `${(s.unrealised_pct * 100).toFixed(2)}%` : undefined}
          subClass={(s?.unrealised_pct ?? 0) >= 0 ? "text-positive" : "text-negative"}
          icon={PercentIcon}
          trend={s?.unrealised_pct == null ? null : s.unrealised_pct >= 0 ? "up" : "down"}
        />
        <KpiCard
          label="Realised P&L"
          value={formatMoney(p?.realised_to_date)}
          sublabel="Since inception"
        />
        {p ? (
          <DualXirrCard
            xirrAll={p.xirr_all}
            xirrHoldings={p.xirr_holdings}
            fyXirr={p.fy_xirr}
            xirr1y={p.xirr_1y}
            xirr3y={p.xirr_3y}
            xirr5y={p.xirr_5y}
            fyTwrr={p.fy_twrr}
            twrr1y={p.twrr_1y}
            twrr3y={p.twrr_3y}
            twrr5y={p.twrr_5y}
            periodXirr={p.period_xirr}
            periodStart={p.period_start}
          />
        ) : performance.errorDetail?.isins?.length ? (
          <MissingPriceNotice
            isins={performance.errorDetail.isins}
            names={performance.errorDetail.securityNames}
            compact
          />
        ) : performance.error ? (
          <div className="rounded-xl border border-navy-100 bg-cream-50 p-5 sm:col-span-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-navy-400">XIRR</p>
            <p className="mt-2 text-sm text-navy-500">Performance is temporarily unavailable.</p>
          </div>
        ) : null}
      </div>

      {p?.warning && (
        <p className="rounded-lg bg-brass-50 px-4 py-2 text-xs text-navy-600">{p.warning}</p>
      )}

      {s && <UnpricedBanner unpriced={s.unpriced} />}
      {s && <SkippedHoldingsBanner skipped={s.skipped} onFixed={() => { summary.refetch(); holdings.refetch(); }} />}

      <div className="flex items-center justify-end gap-2 text-xs">
        <span className="text-navy-400">View by</span>
        <div className="flex overflow-hidden rounded-lg border border-navy-100">
          {(Object.keys(GROUP_BY_LABEL) as AllocationGroupBy[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setAllocationGroupBy(key)}
              className={`press-scale px-3 py-1.5 font-medium border-r border-navy-100 last:border-r-0 transition-colors ${
                allocationGroupBy === key
                  ? "bg-navy-900 text-cream-50"
                  : "text-navy-500 hover:bg-cream-200"
              }`}
            >
              {GROUP_BY_LABEL[key]}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <div className="mb-4 flex items-start justify-between gap-2">
            <div>
              <h3 className="font-heading text-base text-navy-900">Portfolio allocation</h3>
              <p className="text-xs text-navy-400">As on {formatDate(s?.as_of)}</p>
            </div>
            <select
              value={valueBasis}
              onChange={(e) => setValueBasis(e.target.value as ValueBasis)}
              className="rounded-md border border-navy-100 bg-surface px-2 py-1 text-xs text-navy-700 transition-colors focus:border-brass-500 focus:outline-none"
            >
              <option value="current">Current value</option>
              <option value="invested">Amount invested</option>
            </select>
          </div>
          {s && (
            <AllocationDonut
              groups={allocationSlices}
              centerValue={formatMoney(valueBasis === "invested" ? s.invested : s.market_value)}
              centerLabel={valueBasis === "invested" ? "Amount invested" : "Current value"}
            />
          )}
        </Card>

        <Card className="lg:col-span-2">
          <AllocationGroupsTable rows={groupRows} groupLabel={GROUP_BY_LABEL[allocationGroupBy]} />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <HistoricalValueChart />
        </Card>
        <Card title="Reconciliation" action={<Link href="/portfolio?tab=reconcile" className="text-xs text-brass-600 underline">Open</Link>}>
          <p className="text-sm text-navy-600">
            Compare your computed holdings against a broker/depository statement to catch
            missed corporate actions or drift.
          </p>
          <Link
            href="/portfolio?tab=reconcile"
            className="mt-4 inline-block press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-xs font-medium text-cream-50 hover:bg-navy-600"
          >
            Run reconciliation
          </Link>
        </Card>
      </div>

      <Card title="Top holdings" action={<Link href="/?tab=holdings" className="text-xs text-brass-600 underline">View all</Link>}>
        {holdings.loading ? <LoadingState /> : <HoldingsTable holdings={topHoldings} dense />}
      </Card>

      <Card title="Recent ledger entries" action={<Link href="/portfolio?tab=transactions" className="text-xs text-brass-600 underline">View all</Link>}>
        {transactions.loading ? (
          <LoadingState />
        ) : recentTxns.length === 0 ? (
          <p className="text-sm text-navy-400">No transactions yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-navy-100 text-left text-[11px] uppercase tracking-wide text-navy-400">
                <th className="py-2 pr-3 font-medium">Date</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">ISIN</th>
                <th className="py-2 pr-3 font-medium text-right">Qty</th>
                <th className="py-2 font-medium text-right">Price</th>
              </tr>
            </thead>
            <tbody>
              {recentTxns.map((t) => (
                <tr key={t.id ?? `${t.isin}-${t.txn_date}`} className="border-b border-navy-50 last:border-0">
                  <td className="py-2 pr-3">{formatDate(t.txn_date)}</td>
                  <td className="py-2 pr-3">
                    <span className="rounded bg-cream-200 px-1.5 py-0.5 text-xs font-medium text-navy-700">
                      {t.txn_type}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-navy-600">{t.isin}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{t.quantity}</td>
                  <td className="py-2 text-right tabular-nums">{formatMoney(t.price, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") ?? "overview";

  function setActiveTab(key: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (key === "overview") params.delete("tab");
    else params.set("tab", key);
    const qs = params.toString();
    router.push(qs ? `/?${qs}` : "/");
  }

  return (
    <div className="space-y-6">
      <TabBar tabs={DASHBOARD_TABS} active={activeTab} onChange={setActiveTab} />
      {activeTab === "holdings" ? (
        <HoldingsTab />
      ) : activeTab === "performance" ? (
        <PerformanceTab />
      ) : activeTab === "contribution" ? (
        <ContributionTab />
      ) : (
        <OverviewTab />
      )}
    </div>
  );
}
