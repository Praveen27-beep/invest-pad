"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import type { BenchmarkSeriesResponse, SnapshotOut } from "@/lib/api-types";
// The 1M/3M/6M/1Y/3Y/Max definitions live in lib/ranges.ts so this chart and the
// dividends card cannot end up meaning different things by the same button.
import { HISTORY_START, RANGES, startFor, type RangeKey } from "@/lib/ranges";
import {
  Card,
  EmptyState,
  LinePlotSkeleton,
  SegmentedControl,
  VintageLinePlot,
  type PlotSeries,
} from "./ds";

/**
 * `HISTORY_START` (lib/ranges.ts) is the start date sent to the API: far enough back to
 * cover any ledger.
 *
 * The whole history is fetched ONCE and the ranges slice it here, rather than each range
 * being its own request. Two reasons, and the first is a bug this fixes:
 *
 *  - **The buttons have to be able to say "there is nothing more to show".** Server-side
 *    ranges cannot: a request for 1Y over four months of history returns the same rows a
 *    request for 3Y does, so every button past the data's own age redrew an identical
 *    chart and read as broken. Holding the full series here means the earliest snapshot
 *    date is known, so a range that would not clip anything is disabled and says why.
 *  - Switching range costs no round trip, so the plot redraws on the same frame.
 *
 * One snapshot row per day keeps this small: a decade of history is a few thousand rows.
 */

/**
 * No trading-calendar knowledge on the frontend, so a genuine data gap (a backfill run
 * that hit MissingPriceError) is told apart from routine non-trading days by elapsed
 * calendar days alone. A week covers any weekend plus an adjacent holiday without
 * falsely flagging a normal week, while a real multi-day outage still trips it.
 */
const GAP_THRESHOLD_DAYS = 7;

/** How many x-positions the plot draws. More than this and the axis labels collide. */
const TARGET_POINTS = 9;

const LAKH = 100_000;

/** A range needs at least this many rows to be worth drawing, and to be worth offering. */
const MIN_PLOTTABLE_POINTS = 2;

/** Up to this span, x-labels carry the day; beyond it, month and year. Four months is
 *  where "6 Aug, 20 Aug, 3 Sep" stops being more useful than "Aug 26, Sep 26". */
const SHORT_RANGE_DAYS = 120;

/**
 * The plot's height, fixed here and passed to BOTH the chart and its skeleton.
 *
 * One constant rather than two defaults: the card must be the same height before and
 * after the snapshots land, or the whole page below it jumps on first paint.
 */
const PLOT_HEIGHT = 300;

function monthLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** Day and month, no year: the axis label for a range short enough that every point
 *  shares one. Formatted rather than sliced off `dayLabel`, because the year is not a
 *  fixed number of trailing characters in every locale. */
function dayMonthLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

interface Sampled {
  labels: string[];
  market: (number | null)[];
  benchmark: (number | null)[];
  hasGap: boolean;
}

/**
 * Snapshot rows in, plot series out, in ₹ lakh.
 *
 * Three things happen here and all of them matter for honesty:
 *
 *  - **Gaps are preserved, never bridged.** Where consecutive rows sit more than a
 *    week apart, a null is inserted so the line breaks. The engine does not persist a
 *    row for a day it could not price, and drawing through that absence would show a
 *    value the ledger cannot reproduce.
 *  - **Downsampling picks real rows.** To get from hundreds of daily snapshots to
 *    nine plotted points it selects existing rows at even indices rather than
 *    averaging them. Every drawn point is a figure that genuinely occurred on the
 *    date under it.
 *  - **The benchmark is joined by date, not by position.** `/benchmark-series` omits any
 *    snapshot date whose index level was missing, so its array is not index-aligned with
 *    the snapshots. Looking it up by `as_of` is what keeps a missing index level from
 *    silently shifting the whole benchmark line one point to the left.
 */
function sample(rows: SnapshotOut[], benchmarkByDate: Map<string, number>): Sampled {
  const first = rows[0];
  const last = rows[rows.length - 1];
  if (!first || !last) {
    return { labels: [], market: [], benchmark: [], hasGap: false };
  }
  const firstDate = first.as_of;
  const lastDate = last.as_of;

  const step = Math.max(1, Math.ceil(rows.length / TARGET_POINTS));
  const picked: (SnapshotOut | null)[] = [];
  let hasGap = false;

  for (let i = 0; i < rows.length; i += step) {
    const row = rows[i];
    if (!row) continue;
    const prev = picked.length > 0 ? picked[picked.length - 1] : null;
    if (prev) {
      const dayGap = (new Date(row.as_of).getTime() - new Date(prev.as_of).getTime()) / 86_400_000;
      // Compare against the sampling stride, not the raw threshold: at a wide range
      // consecutive picked rows are legitimately far apart.
      if (dayGap > GAP_THRESHOLD_DAYS * step * 1.5) {
        picked.push(null);
        hasGap = true;
      }
    }
    picked.push(row);
  }

  // Always end on the latest row, since the most recent figure is the one being asked
  // about.
  const lastPicked = picked[picked.length - 1];
  if (lastPicked && lastPicked.as_of !== lastDate) picked.push(last);

  // Short ranges span days, not months, so "Aug 26" repeated nine times labels nothing.
  const spanDays = (new Date(lastDate).getTime() - new Date(firstDate).getTime()) / 86_400_000;
  const label = spanDays > SHORT_RANGE_DAYS ? monthLabel : dayMonthLabel;

  return {
    labels: picked.map((r, i) => (r ? label(r.as_of) : `gap-${i}`)),
    market: picked.map((r) => (r ? Number(r.market_value) / LAKH : null)),
    benchmark: picked.map((r) => {
      if (!r) return null;
      const value = benchmarkByDate.get(r.as_of);
      return value == null ? null : value / LAKH;
    }),
    hasGap,
  };
}

/**
 * Portfolio value against the NIFTY 500 benchmark. TWO lines, deliberately: the question
 * this card answers is "did I beat the index", and a third invested-cost line answered a
 * different question (unrealised P&L) in the same space, which is what the KPI tiles above
 * the chart already say in numbers.
 *
 * The benchmark is not a rebased index line drawn from a single anchor. The backend
 * replicates the portfolio's OWN cash flows into NIFTY 500 TRI and marks them at each
 * snapshot date, so it starts at exactly the amount first contributed, and every later
 * contribution buys index units too. A line anchored once at the start would drift below
 * a portfolio that simply kept saving, and would read as outperformance that never
 * happened. See docs/ENGINE_SPEC.md section 6.
 *
 * If the index source is unreachable the endpoint returns no points, the series is all
 * nulls, and the plot draws nothing for it. The portfolio's own line is unaffected.
 */
export function ValueChartCard() {
  const { investorId, token, asOf } = useAuth();
  const [range, setRange] = useState<RangeKey>("1Y");

  const snapshots = useFetch<SnapshotOut[]>(
    investorId ? `/investors/${investorId}/snapshots` : null,
    { start: HISTORY_START, end: asOf },
    token
  );
  const benchmark = useFetch<BenchmarkSeriesResponse>(
    investorId ? `/investors/${investorId}/benchmark-series` : null,
    { start: HISTORY_START, end: asOf },
    token
  );

  const allRows = useMemo(() => snapshots.data ?? [], [snapshots.data]);

  /**
   * Which ranges have anything of their own to show.
   *
   * A range whose start is at or before the earliest snapshot draws exactly what Max
   * draws, so offering it as a separate button is a promise the data cannot keep. Those
   * are disabled and say why on hover, which is the honest version of what used to
   * happen silently.
   */
  const options = useMemo(() => {
    const earliest = allRows[0]?.as_of;
    return RANGES.map((r) => {
      if (!earliest || r === "Max") return { value: r, label: r };
      const clips = startFor(r, asOf) > earliest;
      const enough =
        allRows.filter((row) => row.as_of >= startFor(r, asOf)).length >= MIN_PLOTTABLE_POINTS;
      const usable = clips && enough;
      return {
        value: r,
        label: r,
        disabled: !usable,
        title: usable
          ? undefined
          : `History starts ${dayLabel(earliest)}, so ${r} shows the same as Max.`,
      };
    });
  }, [allRows, asOf]);

  // A disabled range must still draw something rather than an empty card, and Max is the
  // only range guaranteed to have every row there is.
  const disabledRanges = useMemo(
    () => new Set(options.filter((o) => o.disabled).map((o) => o.value)),
    [options]
  );
  const effectiveRange = disabledRanges.has(range) ? "Max" : range;

  const rows = useMemo(() => {
    const from = startFor(effectiveRange, asOf);
    return allRows.filter((row) => row.as_of >= from);
  }, [allRows, effectiveRange, asOf]);

  const benchmarkByDate = useMemo(
    () => new Map((benchmark.data?.points ?? []).map((p) => [p.as_of, Number(p.value)])),
    [benchmark.data]
  );
  const { labels, market, benchmark: benchmarkPoints, hasGap } = useMemo(
    () => sample(rows, benchmarkByDate),
    [rows, benchmarkByDate]
  );

  const hasBenchmark = benchmarkPoints.some((v) => v != null);

  /** Holdings these lines leave out, because their buy history doesn't reconcile. Taken
   *  from the most recent plotted snapshot: it is the one whose figure the eye lands on,
   *  and an exclusion clears itself as soon as the gap is closed and the next rebuild
   *  replays cleanly. Same posture as the dashboard's SkippedHoldingsNotice -- state it
   *  plainly, don't alarm, and say it's temporary. */
  const excluded = rows[rows.length - 1]?.excluded_isins ?? [];

  /** The span actually drawn, named for the caption so it is read off the plotted rows
   *  rather than restated from the range button, which can disagree with them. */
  const plotted = { from: rows[0]?.as_of ?? asOf, to: rows[rows.length - 1]?.as_of ?? asOf };

  const series: PlotSeries[] = [
    { label: "Portfolio", points: market, color: "var(--ledger-ink)", weight: 2.1, marker: "dot" },
  ];
  if (hasBenchmark) {
    series.push({
      label: "NIFTY 500",
      points: benchmarkPoints,
      color: "var(--alloc-accent)",
      weight: 1.2,
      dash: "1 3.2",
      marker: "square",
    });
  }

  const body = () => {
    if (snapshots.loading) return <LinePlotSkeleton height={PLOT_HEIGHT} />;
    if (snapshots.error) {
      return (
        <p style={{ margin: 0, font: "var(--type-body)", color: "var(--negative)" }}>{snapshots.error}</p>
      );
    }
    if (labels.length < MIN_PLOTTABLE_POINTS) {
      return (
        <EmptyState
          title="Not enough history to plot"
          hint="Value over time needs at least two daily snapshots. They accumulate once the snapshot job has run for a couple of days."
        />
      );
    }
    return (
      <>
        <VintageLinePlot
          height={PLOT_HEIGHT}
          labels={labels}
          series={series}
          gapNote={hasGap ? "no snapshot" : undefined}
          formatTick={(v) => `${v}L`}
        />
        <p style={{ margin: "10px 0 0", font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
          {`Showing ${dayLabel(plotted.from)} to ${dayLabel(plotted.to)}, ${rows.length} daily snapshots. `}
          {hasBenchmark
            ? " The dotted line replicates your own cash flows into NIFTY 500 TRI, so below it is genuine underperformance rather than a difference in timing."
            : " The NIFTY 500 line is absent because the index source returned no levels for these dates."}
          {hasGap ? " A break in the line is a genuine snapshot gap, not an interpolated value." : ""}
          {excluded.length > 0
            ? ` Excludes ${excluded.length} holding${excluded.length > 1 ? "s" : ""} whose older buy history is incomplete — ${excluded.length > 1 ? "they" : "it"} will be included here once that gap is closed.`
            : ""}
        </p>
      </>
    );
  };

  return (
    <Card
      title="Portfolio value vs benchmark"
      subtitle="Daily snapshots in ₹ lakh. Benchmark is NIFTY 500 TRI, replicating your own cash flows."
      action={
        <SegmentedControl size="sm" options={options} value={effectiveRange} onChange={setRange} />
      }
    >
      {/*
        The body is height-locked to the plot plus its caption. Every branch below,
        skeleton, error, empty state and the plot itself, renders into the same box, so
        switching 1Y to 3Y, or a range that turns out to have no history, cannot change
        the card's height and shove the allocation and holdings panels below it up the
        page.

        `opacity` while refreshing is the only thing that moves: the previous range's plot
        stays drawn and dims slightly rather than being replaced by a skeleton.
      */}
      <div
        style={{
          minHeight: PLOT_HEIGHT + 34,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          opacity: snapshots.refreshing ? 0.55 : 1,
          transition: "opacity var(--duration-base) var(--ease-smooth)",
        }}
      >
        {body()}
      </div>
    </Card>
  );
}
