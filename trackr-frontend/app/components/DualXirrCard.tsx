import { formatDate, formatPercent, signClass } from "@/lib/format";

/**
 * app/schemas/analytical.py's PerformanceResponse comment: "Both variants together,
 * always -- reporting one alone leaves a choice about which number flatters the
 * portfolio." One card, two numbers, so the pair can't be split apart later.
 */
export function DualXirrCard({
  xirrAll,
  xirrHoldings,
  fyXirr,
  periodXirr,
  periodStart,
}: {
  xirrAll: number | null;
  xirrHoldings: number | null;
  fyXirr: number | null;
  periodXirr: number | null;
  periodStart: string | null;
}) {
  return (
    <div className="glass-card glass-card-hover animate-fade-in-up rounded-xl border border-navy-100 p-5 sm:col-span-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-navy-400">XIRR</p>
      <div className="mt-2 grid grid-cols-2 gap-6">
        <div>
          <p className={`font-heading text-2xl tabular-nums ${signClass(xirrAll)}`}>
            {formatPercent(xirrAll)}
          </p>
          <p className="mt-1 text-xs text-navy-400">Cash-flow — all external flows</p>
        </div>
        <div>
          <p className={`font-heading text-2xl tabular-nums ${signClass(xirrHoldings)}`}>
            {formatPercent(xirrHoldings)}
          </p>
          <p className="mt-1 text-xs text-navy-400">Holding period — excl. idle cash drag</p>
        </div>
      </div>
      {fyXirr !== null && (
        <p className="mt-3 border-t border-navy-100 pt-2 text-xs text-navy-600">
          This FY: <span className="font-medium tabular-nums">{formatPercent(fyXirr)}</span>
        </p>
      )}
      {periodXirr !== null && (
        <p className="mt-1 text-xs text-navy-600">
          Since {formatDate(periodStart)}:{" "}
          <span className="font-medium tabular-nums">{formatPercent(periodXirr)}</span>
        </p>
      )}
    </div>
  );
}
