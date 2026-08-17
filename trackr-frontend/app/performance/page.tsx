"use client";

import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { formatDate, formatMoney, formatPercent, signClass } from "@/lib/format";
import type { PerformanceResponse } from "@/lib/api-types";
import { Card, ErrorState, LoadingState, NoInvestorState } from "../components/PageState";
import { KpiCard } from "../components/KpiCard";
import { DualXirrCard } from "../components/DualXirrCard";
import { MissingPriceNotice } from "../components/MissingPriceNotice";

export default function PerformancePage() {
  const { investorId, token, asOf, advisedOnly } = useAuth();

  const performance = useFetch<PerformanceResponse>(
    investorId ? `/investors/${investorId}/performance` : null,
    { as_of: asOf, advised_only: advisedOnly || undefined },
    token
  );

  if (!investorId) return <NoInvestorState />;
  if (performance.error) {
    const isins = performance.errorDetail?.isins;
    if (isins && isins.length > 0) return <MissingPriceNotice isins={isins} />;
    return <ErrorState message={performance.error} />;
  }
  if (performance.loading) return <LoadingState label="Loading performance…" />;

  const p = performance.data;

  return (
    <div className="space-y-6">
      {/* Both XIRR variants together, always — schema/performance.schema.json: "the gap
          between them is itself the insight." DualXirrCard also folds in fy_xirr. */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <DualXirrCard
          xirrAll={p?.xirr_all ?? null}
          xirrHoldings={p?.xirr_holdings ?? null}
          fyXirr={p?.fy_xirr ?? null}
          periodXirr={p?.period_xirr ?? null}
          periodStart={p?.period_start ?? null}
        />
        <KpiCard
          label="Absolute return"
          value={formatPercent(p?.absolute_return)}
          sublabel="All-in, non-annualised"
          subClass={signClass(p?.absolute_return)}
        />
        <KpiCard label="Invested" value={formatMoney(p?.invested)} sublabel="Net lifetime contribution" />
        <KpiCard
          label="Current value"
          value={formatMoney(p?.market_value)}
          sublabel={`As of ${formatDate(p?.as_of)}`}
        />
        <KpiCard
          label="Unrealised P&L"
          value={formatMoney(p?.unrealised)}
          subClass={signClass(p?.unrealised)}
        />
        <KpiCard label="Realised P&L" value={formatMoney(p?.realised_to_date)} sublabel="Since inception" />
      </div>

      {p?.warning && (
        <p className="rounded-lg bg-brass-50 px-4 py-2 text-xs text-navy-600">{p.warning}</p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Benchmark comparison">
          {p?.benchmark ? (
            <div>
              <p className="text-xs uppercase tracking-wide text-navy-400">{p.benchmark.name}</p>
              <p className={`font-heading text-2xl tabular-nums ${signClass(p.benchmark.xirr)}`}>
                {formatPercent(p.benchmark.xirr)}
              </p>
            </div>
          ) : (
            <p className="text-sm text-navy-500">
              Cash-flow-replicated NIFTY 50 / SENSEX TRI comparison isn&apos;t wired yet — it
              needs an index-level price feed this system doesn&apos;t have. Comparing your XIRR
              against a headline index CAGR wouldn&apos;t be valid, so nothing is shown rather
              than an approximation (roadmap D2).
            </p>
          )}
        </Card>

        <Card title="Why no portfolio CAGR">
          <p className="text-sm text-navy-500">
            CAGR assumes a single lump-sum investment held for a fixed period — that breaks
            down for a portfolio built from staggered trades. It isn&apos;t shown at the
            portfolio level for that reason; XIRR above (both variants) is the correct
            annualised measure here. CAGR still applies per holding.
          </p>
        </Card>
      </div>
    </div>
  );
}
