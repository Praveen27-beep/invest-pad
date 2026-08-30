"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { formatMoney, signClass } from "@/lib/format";
import type { ContributionResponse } from "@/lib/api-types";
import { Card, ErrorState, LoadingState, NoInvestorState } from "../PageState";
import { KpiCard } from "../KpiCard";
import { ContributionTable } from "../ContributionTable";
import { MissingPriceNotice } from "../MissingPriceNotice";
import { NegativeHoldingNotice } from "../NegativeHoldingNotice";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// financial_year_start (app/engine/xirr.py): 1 April of the FY containing `d` --
// April-to-March, so Jan-Mar belongs to the FY that began the previous April. Used only
// as this page's default window; the date inputs below let the user pick any other.
function financialYearStart(d: Date): Date {
  const year = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
  return new Date(year, 3, 1);
}

function yearsBefore(d: Date, n: number): Date {
  const out = new Date(d);
  out.setFullYear(out.getFullYear() - n);
  return out;
}

type Preset = "FY" | "1Y" | "3Y";

export function ContributionTab() {
  const { investorId, token, advisedOnly } = useAuth();
  const today = useMemo(() => new Date(), []);
  const [periodStart, setPeriodStart] = useState(() => isoDate(financialYearStart(today)));
  const [asOf, setAsOf] = useState(() => isoDate(today));

  function applyPreset(preset: Preset) {
    const start =
      preset === "FY" ? financialYearStart(today) : yearsBefore(today, preset === "1Y" ? 1 : 3);
    setPeriodStart(isoDate(start));
    setAsOf(isoDate(today));
  }

  const contribution = useFetch<ContributionResponse>(
    investorId ? `/investors/${investorId}/contribution` : null,
    { period_start: periodStart, as_of: asOf, advised_only: advisedOnly || undefined },
    token
  );

  if (!investorId) return <NoInvestorState />;

  return (
    <div className="space-y-6">
      <Card title="Which holdings contributed most?">
        <p className="mb-4 text-sm text-navy-500">
          Each holding&apos;s rupee share of the portfolio&apos;s total gain over the selected
          period (docs/ENGINE_SPEC.md section 10) — price appreciation plus dividends, net of
          any buying or selling done in the window. A position sold entirely during the window
          still appears, marked <span className="font-medium">Exited</span>, because it is
          often exactly the answer to &quot;which investments destroyed value?&quot;
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-navy-600">
            <span className="mb-1 block font-medium">From</span>
            <input
              type="date"
              value={periodStart}
              max={asOf}
              onChange={(e) => setPeriodStart(e.target.value)}
              className="rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
            />
          </label>
          <label className="text-xs text-navy-600">
            <span className="mb-1 block font-medium">To</span>
            <input
              type="date"
              value={asOf}
              min={periodStart}
              onChange={(e) => setAsOf(e.target.value)}
              className="rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
            />
          </label>
          <div className="flex gap-1.5 pb-0.5">
            <button
              type="button"
              onClick={() => applyPreset("FY")}
              className="press-scale rounded-lg border border-navy-100 px-3 py-2 text-xs font-medium text-navy-600 hover:bg-cream-50"
            >
              This FY
            </button>
            <button
              type="button"
              onClick={() => applyPreset("1Y")}
              className="press-scale rounded-lg border border-navy-100 px-3 py-2 text-xs font-medium text-navy-600 hover:bg-cream-50"
            >
              1Y
            </button>
            <button
              type="button"
              onClick={() => applyPreset("3Y")}
              className="press-scale rounded-lg border border-navy-100 px-3 py-2 text-xs font-medium text-navy-600 hover:bg-cream-50"
            >
              3Y
            </button>
          </div>
        </div>
      </Card>

      {contribution.error ? (
        contribution.errorDetail?.isins && contribution.errorDetail.isins.length > 0 ? (
          <MissingPriceNotice isins={contribution.errorDetail.isins} />
        ) : contribution.errorDetail?.isin ? (
          <NegativeHoldingNotice
            isin={contribution.errorDetail.isin}
            deficit={contribution.errorDetail.deficit}
            asOf={contribution.errorDetail.asOf}
          />
        ) : (
          <ErrorState message={contribution.error} />
        )
      ) : contribution.loading ? (
        <LoadingState label="Computing contribution…" />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <KpiCard
              label="Total gain, this period"
              value={formatMoney(contribution.data?.total_gain)}
              subClass={signClass(contribution.data?.total_gain)}
              sublabel={`${periodStart} → ${asOf}`}
            />
            <KpiCard
              label="Holdings with activity"
              value={String(contribution.data?.contributions.length ?? 0)}
              sublabel="Held, bought, or sold in the window"
            />
            <KpiCard
              label="Top contributor"
              value={
                contribution.data?.contributions[0]
                  ? (contribution.data.contributions[0].symbol ??
                    contribution.data.contributions[0].isin)
                  : "—"
              }
              subValue={
                contribution.data?.contributions[0]
                  ? formatMoney(contribution.data.contributions[0].gain)
                  : undefined
              }
              subClass={signClass(contribution.data?.contributions[0]?.gain)}
            />
          </div>

          <Card title="Ranked by contribution">
            <ContributionTable contributions={contribution.data?.contributions ?? []} />
          </Card>
        </>
      )}
    </div>
  );
}
