"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { formatDate, formatMoney, formatPercent, signClass } from "@/lib/format";
import type { PerformanceResponse } from "@/lib/api-types";
import { Card, ErrorState, LoadingState, NoInvestorState } from "../PageState";
import { KpiCard } from "../KpiCard";
import { DualXirrCard } from "../DualXirrCard";
import { MissingPriceNotice } from "../MissingPriceNotice";
import { NegativeHoldingNotice } from "../NegativeHoldingNotice";

// Only NIFTY50_TRI has a real adapter (app.prices.index_sources) -- SENSEX_TRI is a
// valid contract enum value with no reliable free, machine-fetchable TRI source behind
// it yet (docs/ENGINE_SPEC.md section 6 / Plan Mode decision this session). Selecting it
// here would just round-trip into the backend's explicit 400, so it stays disabled
// rather than the UI ever triggering that error.
type BenchmarkChoice = "NIFTY50_TRI" | "SENSEX_TRI";

export function PerformanceTab() {
  const { investorId, token, asOf, advisedOnly } = useAuth();
  const [benchmark, setBenchmark] = useState<BenchmarkChoice>("NIFTY50_TRI");

  const performance = useFetch<PerformanceResponse>(
    investorId ? `/investors/${investorId}/performance` : null,
    { as_of: asOf, advised_only: advisedOnly || undefined, benchmark },
    token
  );

  if (!investorId) return <NoInvestorState />;
  if (performance.error) {
    const isins = performance.errorDetail?.isins;
    if (isins && isins.length > 0) {
      return <MissingPriceNotice isins={isins} names={performance.errorDetail?.securityNames} />;
    }
    const negIsin = performance.errorDetail?.isin;
    if (negIsin) {
      return (
        <NegativeHoldingNotice
          isin={negIsin}
          name={performance.errorDetail?.securityName}
          deficit={performance.errorDetail?.deficit}
          asOf={performance.errorDetail?.asOf}
        />
      );
    }
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
          xirr1y={p?.xirr_1y ?? null}
          xirr3y={p?.xirr_3y ?? null}
          xirr5y={p?.xirr_5y ?? null}
          fyTwrr={p?.fy_twrr ?? null}
          twrr1y={p?.twrr_1y ?? null}
          twrr3y={p?.twrr_3y ?? null}
          twrr5y={p?.twrr_5y ?? null}
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
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-navy-600">Compare against</label>
            <select
              value={benchmark}
              onChange={(e) => setBenchmark(e.target.value as BenchmarkChoice)}
              className="w-full rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
            >
              <option value="NIFTY50_TRI">NIFTY 50 TRI</option>
              <option value="SENSEX_TRI" disabled>
                SENSEX TRI — not yet available
              </option>
            </select>
          </div>

          {p?.benchmark && p.benchmark.xirr !== null ? (
            <div>
              <p className="text-xs uppercase tracking-wide text-navy-400">{p.benchmark.name}</p>
              <p className={`font-heading text-2xl tabular-nums ${signClass(p.benchmark.xirr)}`}>
                {formatPercent(p.benchmark.xirr)}
              </p>
              {p.benchmark.terminal_value && (
                <p className="mt-1 text-xs text-navy-500">
                  Replicated terminal value: {formatMoney(p.benchmark.terminal_value)}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-navy-500">
              No usable index level for one or more of this portfolio&apos;s cash-flow dates,
              so nothing is shown rather than an approximation. Comparing your XIRR against a
              headline index CAGR wouldn&apos;t be valid either way — this is always the
              cash-flow-replicated figure, apples to apples with your own buy/sell dates.
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
