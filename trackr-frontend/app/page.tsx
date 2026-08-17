"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { formatMoney, formatDate } from "@/lib/format";
import type { HoldingsResponse, PerformanceResponse, SummaryResponse, TransactionOut } from "@/lib/api-types";
import { Card, ErrorState, LoadingState, NoInvestorState } from "./components/PageState";
import { KpiCard } from "./components/KpiCard";
import { DualXirrCard } from "./components/DualXirrCard";
import { MissingPriceNotice } from "./components/MissingPriceNotice";
import { AllocationDonut } from "./components/AllocationDonut";
import { HistoricalChartPlaceholder } from "./components/HistoricalChartPlaceholder";
import { HoldingsTable } from "./components/HoldingsTable";
import { UnpricedBanner } from "./components/UnpricedBanner";

export default function DashboardPage() {
  const { investorId, token, asOf, advisedOnly } = useAuth();
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
  const blockingError = summary.error ?? holdings.error;
  if (blockingError) return <ErrorState message={blockingError} />;

  if (summary.loading || performance.loading) return <LoadingState label="Loading portfolio…" />;

  const s = summary.data;
  const p = performance.data;
  const recentTxns = (transactions.data ?? [])
    .slice()
    .sort((a, b) => (a.txn_date < b.txn_date ? 1 : -1))
    .slice(0, 6);
  const topHoldings = (holdings.data?.holdings ?? []).slice(0, 5);

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
            periodXirr={p.period_xirr}
            periodStart={p.period_start}
          />
        ) : performance.errorDetail?.isins?.length ? (
          <MissingPriceNotice isins={performance.errorDetail.isins} compact />
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <HistoricalChartPlaceholder />
        </Card>
        <Card title="Allocation by asset class">
          {s && <AllocationDonut groups={s.allocation} />}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Top holdings" action={<Link href="/holdings" className="text-xs text-brass-600 underline">View all</Link>} className="lg:col-span-2">
          {holdings.loading ? <LoadingState /> : <HoldingsTable holdings={topHoldings} dense />}
        </Card>

        <Card title="Reconciliation" action={<Link href="/reconcile" className="text-xs text-brass-600 underline">Open</Link>}>
          <p className="text-sm text-navy-600">
            Compare your computed holdings against a broker/depository statement to catch
            missed corporate actions or drift.
          </p>
          <Link
            href="/reconcile"
            className="mt-4 inline-block press-scale rounded-lg bg-navy-700 transition-colors px-4 py-2 text-xs font-medium text-cream-50 hover:bg-navy-600"
          >
            Run reconciliation
          </Link>
        </Card>
      </div>

      <Card title="Recent ledger entries" action={<Link href="/transactions" className="text-xs text-brass-600 underline">View all</Link>}>
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
