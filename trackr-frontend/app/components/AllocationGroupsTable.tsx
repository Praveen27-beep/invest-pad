"use client";

import { useMemo, useState } from "react";
import { formatMoney, formatPercent, signClass } from "@/lib/format";
import { EmptyState } from "./PageState";

export interface AllocationGroupRow {
  key: string | null;
  label: string;
  invested: number;
  marketValue: number;
  weightPct: number | null;
}

type SortKey = "label" | "invested" | "unrealised" | "marketValue" | "weightPct";

const COLUMNS: { key: SortKey; label: string; groupLabel?: string }[] = [
  { key: "label", label: "Group" },
  { key: "invested", label: "Invested" },
  { key: "unrealised", label: "Unrealised gain" },
  { key: "marketValue", label: "Current value" },
  { key: "weightPct", label: "Holding" },
];

/**
 * The grouped counterpart to HoldingsTable's per-security rows: one row per
 * allocation group (whichever grouping app/page.tsx currently has selected --
 * asset class, sector or market cap), aggregated from the same GET /summary arrays
 * that already feed the allocation rings. Unrealised gain isn't in AllocationGroupOut
 * itself; it's `marketValue - invested`, both of which are -- so this stays a
 * display-time derivation of real server numbers, never a fabricated one.
 */
export function AllocationGroupsTable({ rows, groupLabel = "Group" }: { rows: AllocationGroupRow[]; groupLabel?: string }) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("weightPct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const filtered = useMemo(
    () => rows.filter((r) => r.label.toLowerCase().includes(query.trim().toLowerCase())),
    [rows, query]
  );

  const sorted = useMemo(() => {
    const withGain = filtered.map((r) => ({ ...r, unrealised: r.marketValue - r.invested }));
    const dir = sortDir === "asc" ? 1 : -1;
    return withGain.sort((a, b) => {
      if (sortKey === "label") return dir * a.label.localeCompare(b.label);
      const av = (a[sortKey] ?? -Infinity) as number;
      const bv = (b[sortKey] ?? -Infinity) as number;
      return dir * (av - bv);
    });
  }, [filtered, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="font-heading text-base text-navy-900">Current holdings</h3>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search"
          className="w-48 rounded-lg border border-navy-100 bg-surface px-3 py-1.5 text-xs text-navy-700 placeholder:text-navy-400 transition-colors focus:border-brass-500 focus:outline-none"
        />
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No priced allocation yet" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-navy-100 text-left text-[11px] uppercase tracking-wide text-navy-400">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={`py-2 ${col.key === "label" ? "pr-3" : "px-3 text-right"} font-medium`}
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className={`inline-flex items-center gap-1 transition-colors hover:text-navy-700 ${
                        col.key === "label" ? "" : "flex-row-reverse"
                      }`}
                    >
                      {col.key === "label" ? groupLabel : col.label}
                      <svg
                        viewBox="0 0 12 12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.4"
                        strokeLinecap="round"
                        className={`h-2.5 w-2.5 shrink-0 ${sortKey === col.key ? "text-navy-700" : "text-navy-200"}`}
                      >
                        {sortKey === col.key && sortDir === "asc" ? (
                          <path d="M3 7.5 6 4.5 9 7.5" />
                        ) : (
                          <path d="M3 4.5 6 7.5 9 4.5" />
                        )}
                      </svg>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="py-6 text-center text-sm text-navy-400">
                    No groups match &ldquo;{query}&rdquo;.
                  </td>
                </tr>
              ) : (
                sorted.map((r) => (
                  <tr key={r.key ?? r.label} className="border-b border-navy-50 last:border-0">
                    <td className="py-2.5 pr-3 font-medium text-navy-900">{r.label}</td>
                    <td className="py-2.5 px-3 text-right tabular-nums">{formatMoney(String(r.invested))}</td>
                    <td className={`py-2.5 px-3 text-right tabular-nums ${signClass(r.unrealised)}`}>
                      {formatMoney(String(r.unrealised))}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums">{formatMoney(String(r.marketValue))}</td>
                    <td className="py-2.5 px-3 text-right tabular-nums">{formatPercent(r.weightPct, 1)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
