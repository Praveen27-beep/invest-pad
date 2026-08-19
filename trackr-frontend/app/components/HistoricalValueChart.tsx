"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { formatDate, formatMoney } from "@/lib/format";
import type { SnapshotOut } from "@/lib/api-types";
import { EmptyState, ErrorState, LoadingState } from "./PageState";

type RangeKey = "1M" | "6M" | "1Y" | "3Y" | "Max";
const RANGES: RangeKey[] = ["1M", "6M", "1Y", "3Y", "Max"];
const RANGE_DAYS: Record<Exclude<RangeKey, "Max">, number> = {
  "1M": 30,
  "6M": 182,
  "1Y": 365,
  "3Y": 365 * 3,
};
// No trading-calendar knowledge on the frontend, so a genuine data gap (a backfill run
// that hit MissingPriceError, or several) is told apart from routine non-trading days
// (weekends, single-day holidays) by elapsed calendar days alone: a week comfortably
// covers any weekend plus one adjacent holiday without falsely flagging a normal week,
// while a real multi-day outage still trips it.
const GAP_THRESHOLD_DAYS = 7;

function startFor(range: RangeKey, end: string): string {
  if (range === "Max") return "2000-01-01";
  const d = new Date(end);
  d.setUTCDate(d.getUTCDate() - RANGE_DAYS[range]);
  return d.toISOString().slice(0, 10);
}

interface ChartPoint {
  as_of: string;
  market_value: number | null;
  invested: number | null;
  market_value_raw: string | null;
  invested_raw: string | null;
}

/**
 * Snapshot rows in, chart points out. A day with no persisted row is simply absent
 * from ``rows`` (app/routers/analytical.py's list_snapshots never fills one) -- when
 * two consecutive real rows are further apart than GAP_THRESHOLD_DAYS, an explicit
 * null point is inserted between them so the line breaks instead of drawing a smooth
 * connector across days nothing was recorded for.
 */
function buildChartData(rows: SnapshotOut[]): ChartPoint[] {
  const points: ChartPoint[] = [];
  rows.forEach((row, i) => {
    const prevRow = i > 0 ? rows[i - 1] : undefined;
    if (prevRow) {
      const prev = new Date(prevRow.as_of);
      const cur = new Date(row.as_of);
      const dayGap = (cur.getTime() - prev.getTime()) / 86_400_000;
      if (dayGap > GAP_THRESHOLD_DAYS) {
        const gapDate = new Date(prev);
        gapDate.setUTCDate(gapDate.getUTCDate() + 1);
        points.push({
          as_of: gapDate.toISOString().slice(0, 10),
          market_value: null,
          invested: null,
          market_value_raw: null,
          invested_raw: null,
        });
      }
    }
    points.push({
      as_of: row.as_of,
      // Number() here only positions the point on a pixel scale, the same purpose
      // lib/format.ts's own formatMoney() already converts a decimal string for --
      // never fed back into a calculation. The tooltip below reads *_raw, the
      // untouched string from the API, through formatMoney for anything actually shown
      // as a value.
      market_value: Number(row.market_value),
      invested: row.invested !== null ? Number(row.invested) : null,
      market_value_raw: row.market_value,
      invested_raw: row.invested,
    });
  });
  return points;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
}) {
  const entry = active ? payload?.[0] : undefined;
  if (!entry) return null;
  const point = entry.payload;
  if (point.market_value_raw === null) return null;
  return (
    <div className="rounded-lg border border-navy-100 bg-surface-raised px-3 py-2 text-xs shadow-glass">
      <p className="font-medium text-navy-700">{formatDate(point.as_of)}</p>
      <p className="mt-1 text-navy-600">
        Market value: <span className="font-medium">{formatMoney(point.market_value_raw)}</span>
      </p>
      {point.invested_raw !== null && (
        <p className="text-navy-400">Invested: {formatMoney(point.invested_raw)}</p>
      )}
    </div>
  );
}

/**
 * The Dashboard's historical-value chart -- backed by persisted portfolio_snapshot
 * rows (docs/trackr_plus_phase2_overview.md section 6), never a live recompute per
 * point. Replaces the honest disabled placeholder this component used to be before
 * daily snapshots were persisted (Phase 2 Session 1).
 */
export function HistoricalValueChart() {
  const { investorId, token, asOf, advisedOnly } = useAuth();
  const [range, setRange] = useState<RangeKey>("1Y");
  const start = startFor(range, asOf);

  const { data, error, loading } = useFetch<SnapshotOut[]>(
    investorId ? `/investors/${investorId}/snapshots` : null,
    { start, end: asOf, advised_only: advisedOnly || undefined },
    token
  );

  const chartData = useMemo(() => buildChartData(data ?? []), [data]);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="font-heading text-base text-navy-900">Value over time</h3>
          <p className="text-xs text-navy-400">Daily snapshots, INR</p>
        </div>
        <div className="flex overflow-hidden rounded-lg border border-navy-100">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 text-xs border-r border-navy-100 last:border-r-0 transition-colors ${
                r === range
                  ? "bg-navy-700 text-cream-50"
                  : "text-navy-500 hover:bg-cream-100"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex h-56 items-center justify-center">
          <LoadingState label="Loading history…" />
        </div>
      ) : error ? (
        <div className="flex h-56 items-center justify-center">
          <ErrorState message={error} />
        </div>
      ) : chartData.length === 0 ? (
        <div className="flex h-56 items-center justify-center">
          <EmptyState
            title="No snapshots for this range yet"
            hint="Daily portfolio snapshots build up going forward; older history fills in as backfill reaches further back."
          />
        </div>
      ) : (
        <div className="h-56 text-navy-400">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="text-navy-100" stroke="currentColor" vertical={false} />
              <XAxis
                dataKey="as_of"
                tickFormatter={(v: string) => formatDate(v)}
                tick={{ fill: "currentColor", fontSize: 11 }}
                stroke="currentColor"
                tickLine={false}
                minTickGap={32}
              />
              <YAxis
                tickFormatter={(v: number) => formatMoney(String(v))}
                tick={{ fill: "currentColor", fontSize: 11 }}
                stroke="currentColor"
                tickLine={false}
                axisLine={false}
                width={72}
              />
              <Tooltip content={<ChartTooltip />} />
              <Line
                type="monotone"
                dataKey="invested"
                className="text-navy-400"
                stroke="currentColor"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="market_value"
                className="text-brass-500"
                stroke="currentColor"
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
