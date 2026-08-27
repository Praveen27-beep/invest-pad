import type { ContributionOut } from "@/lib/api-types";
import { formatMoney, formatPercent, signClass } from "@/lib/format";
import { EmptyState } from "./PageState";

/**
 * Ranked best/worst contributors -- docs/ENGINE_SPEC.md section 10. The API already
 * sorts by `gain` descending (app/routers/analytical.py's `contribution`), so this is a
 * straight render: best contributor first, biggest detractor last. A fully-exited
 * holding (end_value "0") still gets a row here -- that is deliberate, not a bug, per
 * section 10's "which investments destroyed value?" decision.
 */
export function ContributionTable({ contributions }: { contributions: ContributionOut[] }) {
  if (contributions.length === 0) {
    return (
      <EmptyState
        title="No activity in this period"
        hint="No holding was held, bought, or sold during the selected window."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-100 text-left text-[11px] uppercase tracking-wide text-navy-400">
            <th className="py-3 pr-3 font-medium">Security</th>
            <th className="py-3 pr-3 font-medium text-right">Start value</th>
            <th className="py-3 pr-3 font-medium text-right">End value</th>
            <th className="py-3 pr-3 font-medium text-right">Gain</th>
            <th className="py-3 font-medium text-right">Contribution</th>
          </tr>
        </thead>
        <tbody>
          {contributions.map((c) => (
            <tr
              key={c.isin}
              className="border-b border-navy-50 last:border-0 transition-colors hover:bg-cream-50"
            >
              <td className="py-3 pr-3">
                <span className="font-medium text-navy-900">{c.symbol ?? c.isin}</span>
                {c.end_value === "0" && (
                  <span className="ml-2 rounded bg-navy-50 px-1.5 py-0.5 text-[10px] font-medium text-navy-500">
                    Exited
                  </span>
                )}
              </td>
              <td className="py-3 pr-3 text-right tabular-nums">{formatMoney(c.start_value)}</td>
              <td className="py-3 pr-3 text-right tabular-nums">{formatMoney(c.end_value)}</td>
              <td className={`py-3 pr-3 text-right tabular-nums font-medium ${signClass(c.gain)}`}>
                {formatMoney(c.gain)}
              </td>
              <td className={`py-3 text-right tabular-nums ${signClass(c.pct_of_total)}`}>
                {formatPercent(c.pct_of_total, 1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
