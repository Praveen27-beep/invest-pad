"use client";

/**
 * The seven analytics panels, each in Basic and Advanced.
 *
 * ONE RULE GOVERNS EVERY PANEL: a Basic bullet is generated from the SAME field the
 * Advanced view renders. No number exists only in prose. The reference product this
 * screen is modelled on violates that and ends up telling the user their book is
 * "0.9x more expensive" on one view and "cheaper than benchmark" on the other, from
 * the same two numbers — because the two strings were templated independently.
 */

import { useState } from "react";
import type { ReactNode } from "react";
import {
  ALLOC_RAMP,
  Badge,
  BarSeries,
  Banner,
  Card,
  CORRELATION_BANDS,
  DataTable,
  DistributionBar,
  DonutChart,
  Gauge,
  HeatMap,
  MeterRow,
  ScatterPlot,
  VintageLinePlot,
  type BubblePoint,
  type DataColumn,
  type PlotSeries,
} from "@trackr/ui";
import { Figure } from "@trackr/core";
import type {
  AnalyticsPosition,
  AnalyticsResponse,
  RiskWindow,
} from "@trackr/core";
import { Dec, parseDecimal, sumDecimals } from "@trackr/core";
import { EMPTY, money, pct, pp, ratio, signOf, toneColor } from "./format";

export type Mode = "basic" | "advanced";

/**
 * One bucket's share of portfolio worth, as display text.
 *
 * Divided in Decimal, then rounded once. `EMPTY` when either side is unavailable -- the
 * old expression printed `0.0%` whenever worth was missing, which reads as "this bucket
 * holds none of the portfolio" rather than "the portfolio's worth is not known".
 */
function bucketShare(bucket: string | null | undefined, worth: Dec | null): string {
  const amount = parseDecimal(bucket);
  if (amount === null || worth === null || worth.isZero()) return EMPTY;
  return `${amount.dividedBy(worth).times(100).toFixed(1, Dec.ROUND_HALF_UP)}%`;
}


/* ------------------------------------------------------------------ shared pieces */

type Severity = "good" | "watch" | "bad";

const DOT: Record<Severity, string> = {
  good: "var(--positive)",
  watch: "var(--warning)",
  bad: "var(--negative)",
};


function Na({ reason }: { reason: string }) {
  return (
    <span title={reason} style={{ color: "var(--text-tertiary)", fontStyle: "italic", fontSize: 12 }}>
      n/a
    </span>
  );
}

function Coverage({ pctValue, what }: { pctValue: number; what: string }) {
  if (pctValue >= 95) return null;
  return (
    <span
      title={`${what} is available for ${pctValue.toFixed(1)}% of the book by weight. Coverage below 95% is flagged rather than hidden.`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, cursor: "help",
        color: "var(--warning)", background: "var(--warning-tint)", borderRadius: 5, padding: "2px 8px",
      }}
    >
      coverage {pctValue.toFixed(0)}%
    </span>
  );
}

/**
 * ``align`` is ``start`` almost everywhere: a short card beside a tall chart is meant to
 * stop where its content stops. Rows pairing two cards of the same kind pass ``"stretch"``
 * so the pair shares a baseline instead of reading as a layout bug.
 */
const grid = (cols: string, align: "start" | "stretch" = "start"): React.CSSProperties => ({
  display: "grid", gridTemplateColumns: cols, gap: "var(--gap-grid)", alignItems: align,
});

/** One entry in a chart's colour key — a square of the series colour and its wording. */
function LegendSwatch({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <i style={{ width: 9, height: 9, borderRadius: 2, display: "inline-block", background: color }} />
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------- 1. Overview */

/**
 * INTERIM. Renders a component's or chip's `evidence` map as labelled figures.
 *
 * The prose that used to sit here was a hand-written sentence with these same numbers
 * formatted into it ("Effective holdings 4.2 of a 20-name target"). The sentence is gone;
 * `app/narrative/` generates the interpretation instead, and until it lands this shows
 * the evidence without pretending to interpret it.
 *
 * The labels below are DATA LABELS, not explanations -- the same category as a column
 * header. `unit` picks the formatter, because `format.ts` is explicit that guessing
 * between a fraction and an already-percent is how a screen shows 3000% volatility.
 * Supersede this whole map with the fact registry when Phase 1 lands.
 */
const EVIDENCE_META: Record<string, { label: string; unit: "ratio" | "pp" | "count" }> = {
  effective_holdings: { label: "Effective holdings", unit: "ratio" },
  target: { label: "Target", unit: "count" },
  coverage_pct: { label: "Coverage", unit: "pp" },
  relative_1y_pp: { label: "vs index 1Y", unit: "pp" },
  gap_pp: { label: "Gap", unit: "pp" },
  factors_scored: { label: "Factors scored", unit: "count" },
  factors_offered: { label: "Factors offered", unit: "count" },
  top1_pct: { label: "Largest", unit: "pp" },
  top2_pct: { label: "Second", unit: "pp" },
  combined_pct: { label: "Top two", unit: "pp" },
  single_name_threshold: { label: "Single-name rule", unit: "pp" },
  top_two_threshold: { label: "Top-two rule", unit: "pp" },
  gain_share_top2_pct: { label: "Share of gain", unit: "pp" },
  beta: { label: "Beta", unit: "ratio" },
  band_low: { label: "Band low", unit: "ratio" },
  band_high: { label: "Band high", unit: "ratio" },
  count: { label: "Count", unit: "count" },
  roe_floor_pct: { label: "ROE floor", unit: "pp" },
  sector_pct: { label: "Share of book", unit: "pp" },
};

/** One evidence entry as text. Null is "no reading", never zero. */
function evidenceText(key: string, value: number | null): string {
  const meta = EVIDENCE_META[key];
  const label = meta?.label ?? key;
  if (value == null) return `${label} ${EMPTY}`;
  if (meta?.unit === "pp") return `${label} ${pp(value, 1)}`;
  if (meta?.unit === "count") return `${label} ${ratio(value, 0)}`;
  return `${label} ${ratio(value, 1)}`;
}

/** The figure alone. `Reading` supplies the label, so repeating it here would double it. */
function evidenceValue(key: string, value: number | null): string {
  const meta = EVIDENCE_META[key];
  if (value == null) return EMPTY;
  if (meta?.unit === "pp") return pp(value, 1);
  if (meta?.unit === "count") return ratio(value, 0);
  return ratio(value, 1);
}

function evidenceLine(of: Record<string, number | null>, subjects: string[] = []): string {
  const parts = Object.entries(of).map(([k, v]) => evidenceText(k, v));
  if (subjects.length) parts.unshift(subjects.join(", "));
  return parts.join(" · ");
}

/**
 * A FIGURE AND ITS LABEL. Deliberately not a sentence.
 *
 * WHAT REMAINS HARDCODED IN THIS FILE, AND WHY, since "replace the hardcoded
 * explanations" needs a line drawn somewhere:
 *
 *   - Card titles and subtitles say what a card CONTAINS. A label is not a finding.
 *   - Advanced-mode methodology notes ("weighted harmonic mean", "covariance ÷ index
 *     variance") define the MEASURE, not this portfolio. They are identical for every
 *     book, which is what makes them a definition rather than an analysis, and they must
 *     not vanish because a model was unreachable. They overlap with
 *     app/narrative/cards.py by design; if one is edited the other should follow.
 *   - Disclosures — the fixed-weight backtest caveat, the missing index ratios, the
 *     unpriced-holdings banner — stay hardcoded ON PURPOSE. Invariant 16 requires a
 *     total that excludes something to say so, and a disclosure delegated to a model
 *     that might not emit it is not a disclosure.
 *
 * What left is the templated interpretation: sentences that read as analysis but were
 * the same words for every portfolio with the numbers swapped.
 *
 * This replaced `Bullet`, which rendered templated interpretation — "Concentration
 * scores 21/100 and carries 20% of the grade", "You are being well paid for the risk you
 * carry". Those read as analysis and were string templates: the same words for every
 * portfolio, with the numbers swapped. Interpretation now comes from `NarrativeBlock`,
 * where every claim is checked against the data before it is shown.
 *
 * What stays here is DATA. A label is not an explanation, so "Weight 40%" belongs on the
 * page whether or not a model is available; "carries 40% of the grade" is the same fact
 * dressed as a finding, and does not.
 */
function Reading({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: ReactNode;
  tone?: Severity;
  sub?: [string, ReactNode][];
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: 16,
        padding: "11px 0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
          {tone && (
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: DOT[tone],
                flex: "0 0 auto",
              }}
            />
          )}
          {label}
        </div>
        {sub && sub.length > 0 && (
          <div style={{ fontSize: 11.5, color: "var(--text-tertiary)", marginTop: 3 }}>
            {sub.map(([k, v], i) => (
              <span key={k}>
                {i > 0 && " · "}
                {k} {v}
              </span>
            ))}
          </div>
        )}
      </div>
      <div
        style={{
          fontFamily: "Newsreader, serif",
          fontSize: 17,
          fontVariantNumeric: "tabular-nums",
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </div>
    </div>
  );
}

export function OverviewPanel({ data, mode }: { data: AnalyticsResponse; mode: Mode }) {
  const { health, coverage, capital_state: buckets, insights } = data;
  // Exact sums, and null the moment a bucket cannot be read -- a reconciliation check
  // that silently skipped a bucket would report agreement it has not established.
  const total = sumDecimals(Object.values(buckets));
  const worth = parseDecimal(data.kpi.market_value);
  /** Does Sigma(buckets) meet portfolio worth, to within a rupee? Unknown if either side is. */
  const bucketsReconcile =
    total !== null && worth !== null ? total.minus(worth).abs().lessThan(1) : null;

  if (mode === "basic") {
    return (
      <Card
        title={`Grade ${health.grade} · ${health.score} of 100`}
        subtitle="The four components the grade is computed from, and their published weights."
      >
        {health.components.map((c) => {
          const score = c.score ?? 50;
          return (
            <Reading
              key={c.key}
              label={c.label}
              tone={score >= 65 ? "good" : score >= 40 ? "watch" : "bad"}
              value={
                <>
                  {score.toFixed(0)}
                  <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}> / 100</span>
                </>
              }
              sub={[
                ["Weight", `${(c.weight * 100).toFixed(0)}%`],
                ["Points", c.points.toFixed(1)],
                ...Object.entries(c.evidence).map(
                  ([k, v]) => [EVIDENCE_META[k]?.label ?? k, evidenceValue(k, v)] as [string, ReactNode],
                ),
              ]}
            />
          );
        })}
      </Card>
    );
  }

  const bucketMeta: [string, string, Severity][] = [
    ["STRONG", "In profit, trending up", "good"],
    ["WEAKENING", "In profit, trending down", "watch"],
    ["CAUTION", "In loss, trending down", "bad"],
    ["RECOVERY", "In loss, trending up", "watch"],
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-grid)" }}>
      <div style={grid("minmax(320px, 1fr) minmax(0, 1.1fr)", "stretch")}>
        <Card title={`Portfolio health · ${health.grade} · ${health.score}/100`}
              subtitle="Every component\u2019s contribution in points, and the rubric behind it.">
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: -46 }}>
            <Gauge score={health.score} grade={health.grade} />
          </div>
          <DataTable
            dense
            columns={[
              { key: "label", label: "Component" },
              { key: "weight", label: "Weight", align: "right", numeric: true },
              { key: "score", label: "Score", align: "right", numeric: true },
              { key: "points", label: "Points", align: "right", numeric: true },
            ] as DataColumn<Record<string, unknown>>[]}
            rows={health.components.map((c) => ({
              id: c.key,
              label: (
                <div>
                  <div style={{ fontWeight: 500 }}>{c.label}</div>
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                    {Object.entries(c.evidence)
                      .map(([k, v]) => `${EVIDENCE_META[k]?.label ?? k} ${evidenceValue(k, v)}`)
                      .join(" · ")}
                  </div>
                </div>
              ),
              weight: `${(c.weight * 100).toFixed(0)}%`,
              score: (
                <Badge tone={(c.score ?? 50) >= 65 ? "positive" : (c.score ?? 50) >= 40 ? "warning" : "negative"}>
                  {(c.score ?? 50).toFixed(0)}
                </Badge>
              ),
              points: <b>{c.points.toFixed(1)}</b>,
            }))}
          />
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 12 }}>
            Bands {health.bands.map(([g, floor]) => `${g} ≥ ${floor}`).join(" · ")}. Recomputed daily;
            a band change must hold three consecutive sessions before the letter moves. Rule {health.rule_version}.
          </div>
        </Card>

        <Card title="Capital state"
              subtitle="Profit or loss against the 50-day trend. The four buckets sum to portfolio worth.">
          <div style={grid("repeat(2, 1fr)")}>
            {bucketMeta.map(([key, meaning, tone]) => (
              <div key={key} style={{ border: "1px solid var(--border)", padding: 11 }}>
                <Badge tone={tone === "good" ? "positive" : tone === "bad" ? "negative" : "warning"}>{key}</Badge>
                <div style={{ fontFamily: "Newsreader, serif", fontSize: 18, marginTop: 8, fontVariantNumeric: "tabular-nums" }}>
                  <Figure>{money(buckets[key])}</Figure>
                </div>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>
                  {bucketShare(buckets[key], worth)} of worth
                </div>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 5 }}>{meaning}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 13 }}>
            Σ buckets <Figure>{money(total?.toString() ?? null)}</Figure> = portfolio worth{" "}
            <Figure>{money(worth?.toString() ?? null)}</Figure>
            {bucketsReconcile === null ? " — NOT CHECKED" : bucketsReconcile ? " ✓" : " — MISMATCH"}
          </div>
        </Card>
      </div>

      <Card title="Core portfolio insight"
            subtitle="Hover a chip for the figure that triggered it and the threshold it crossed.">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {insights.length === 0 && (
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              No rule fired on this portfolio today.
            </span>
          )}
          {insights.map((i) => (
            <span key={i.key} title={`${evidenceLine(i.evidence, i.subjects)}\n\nrule_version ${i.rule_version}`} style={{ cursor: "help" }}>
              <Badge
                tone={
                  i.severity === "strength" ? "positive"
                    : i.severity === "threat" ? "negative"
                    : i.severity === "watch" ? "warning"
                    : "info"
                }
              >
                {i.title}
              </Badge>
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------------- 2. Factor */

const FACTOR_META: [string, string][] = [
  ["momentum", "Momentum"],
  ["value", "Value"],
  ["quality", "Quality"],
  ["low_volatility", "Low volatility"],
];

export function FactorPanel({ data, mode }: { data: AnalyticsResponse; mode: Mode }) {
  const [selected, setSelected] = useState("momentum");
  const factors = data.factors;

  if (mode === "basic") {
    return (
      <Card title="How the book is tilted"
            subtitle="Percentile ranks within a stated universe, not absolute scores.">
        {FACTOR_META.map(([key, label]) => {
          const f = factors[key];
          const score = f?.score;
          return (
            <Reading
              key={key}
              label={label}
              tone={score == null ? "watch" : score >= 65 ? "good" : score >= 40 ? "watch" : "bad"}
              value={
                score == null ? (
                  EMPTY
                ) : (
                  <>
                    {score.toFixed(0)}
                    <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}> / 100</span>
                  </>
                )
              }
              sub={
                f
                  ? [
                      ["Universe", `${f.universe} (${f.universe_size})`],
                      ["Coverage", pp(f.coverage_pct, 1)],
                    ]
                  : undefined
              }
            />
          );
        })}
      </Card>
    );
  }

  const bars = data.positions
    .filter((p) => p.factors?.[selected] != null)
    .sort((a, b) => (b.factors[selected] ?? 0) - (a.factors[selected] ?? 0))
    .map((p) => {
      const v = p.factors[selected] as number;
      return {
        label: p.symbol ?? p.isin,
        value: v,
        tone: v >= 70 ? "var(--positive)" : v >= 35 ? "var(--warning)" : "var(--negative)",
        title: `${p.symbol ?? p.isin} — ${v.toFixed(1)}/100 · weight ${(p.weight ?? 0).toFixed(1)}%`,
      };
    });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-grid)" }}>
      <Card title="Combined factor score"
            subtitle="Weight-weighted mean of each holding's percentile rank. The universe travels with the number, because a percentile without a stated population is a decoration.">
        {FACTOR_META.map(([key, label]) => {
          const f = factors[key];
          return (
            <MeterRow
              key={key}
              label={label}
              score={f?.score ?? null}
              caption={
                <>
                  <span>Universe <b>{f?.universe ?? EMPTY}</b> ({f?.universe_size ?? 0} names)</span>
                  <span>As of {data.as_of}</span>
                  <span>Coverage {(f?.coverage_pct ?? 0).toFixed(0)}% of weight</span>
                </>
              }
            />
          );
        })}
      </Card>

      <Card
        title="Per-holding scores"
        subtitle="Green ≥ 70 · amber 35–69 · red < 35."
        action={
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {FACTOR_META.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setSelected(key)}
                style={{
                  background: key === selected ? "var(--ink-900)" : "var(--surface)",
                  color: key === selected ? "var(--text-inverse)" : "var(--text-secondary)",
                  border: "1px solid var(--border)", borderRadius: 7, padding: "5px 11px",
                  font: "inherit", fontSize: 12, cursor: "pointer",
                }}
              >
                {label}
              </button>
            ))}
          </div>
        }
      >
        {bars.length ? <BarSeries bars={bars} /> : (
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            No holding has a {selected.replace("_", " ")} score yet — the ranking universe is too small
            or the inputs are missing. Coverage is reported above rather than a zero being invented.
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------------ 3. Risk */

export function RiskPanel({ data, mode }: { data: AnalyticsResponse; mode: Mode }) {
  const available = Object.keys(data.risk);
  const [window, setWindow] = useState(available[0] ?? "1y");
  const fallback = available[0];
  const r: RiskWindow | undefined =
    data.risk[window] ?? (fallback ? data.risk[fallback] : undefined);

  if (!r) {
    return (
      <Card title="Risk and return">
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Not enough price history yet to compute a risk window. Nothing is estimated in its place.
        </div>
      </Card>
    );
  }

  if (mode === "basic") {
    const volRatio = data.derived.vol_ratio_1y;
    return (
      <Card
        title="Risk readings"
        subtitle={`Window ${window.toUpperCase()} · benchmark ${data.benchmark} · as of ${data.as_of}`}
      >
        <Reading
          label="Sharpe"
          tone={(r.sharpe ?? -1) >= 1 ? "good" : (r.sharpe ?? -1) >= 0 ? "watch" : "bad"}
          value={ratio(r.sharpe)}
          sub={[
            ["Index", ratio(r.bench_sharpe)],
            ["Risk-free", pct(r.risk_free_rate)],
          ]}
        />
        <Reading
          label="Annualised volatility"
          tone={volRatio == null ? "watch" : volRatio > 1.2 ? "bad" : volRatio > 1 ? "watch" : "good"}
          value={pct(r.volatility)}
          sub={[
            ["Index", pct(r.bench_volatility)],
            ["Ratio", volRatio ? `${volRatio.toFixed(2)}x` : EMPTY],
            ["Beta", ratio(r.beta)],
          ]}
        />
        <Reading
          label="1-day 95% VaR"
          tone={(r.var_1d_95 ?? 0) > 0.02 ? "watch" : "good"}
          value={<Figure>{money(r.var_1d_95_value)}</Figure>}
          sub={[
            ["Of worth", pct(r.var_1d_95)],
            ["CVaR", pct(r.cvar_1d_95)],
            ["Method", r.var_method],
            ["Sessions", String(r.observations)],
          ]}
        />
        <Reading
          label="Maximum drawdown"
          tone={Math.abs(r.max_drawdown ?? 0) > 0.2 ? "bad" : "watch"}
          value={pct(r.max_drawdown)}
        />
      </Card>
    );
  }

  const cards: [string, string, string | null, boolean | null, string][] = [
    ["CAGR", pct(r.cagr), pct(r.bench_cagr), r.cagr != null && r.bench_cagr != null ? r.cagr > r.bench_cagr : null,
      "Time-weighted, NOT money-weighted. Trackr+ also reports XIRR from the ledger and the two differ whenever contributions are uneven — which one is on screen is always labelled."],
    ["Volatility", pct(r.volatility), pct(r.bench_volatility), r.volatility != null && r.bench_volatility != null ? r.volatility < r.bench_volatility : null,
      "Standard deviation of daily returns × √252."],
    ["Sharpe ratio", ratio(r.sharpe), ratio(r.bench_sharpe), r.sharpe != null && r.bench_sharpe != null ? r.sharpe > r.bench_sharpe : null,
      `(Return − Rf) ÷ volatility, annualised. Rf = ${pct(r.risk_free_rate)}, 91-day T-bill. A Sharpe with an unstated risk-free rate is not comparable to anything.`],
    ["Sortino ratio", ratio(r.sortino), null, null,
      "Downside deviation only, measured against a target of Rf — not zero. Stated because the choice changes the number."],
    ["Beta", ratio(r.beta), "market = 1.00", r.beta != null ? Math.abs(r.beta - 1) < 0.2 : null,
      "Covariance with the benchmark ÷ index variance, from daily returns. Computed here — the vendor's own beta field is unusable for Indian scrips."],
    ["Value at risk (1d, 95%)", pct(r.var_1d_95), null, null,
      `${r.var_method === "historical" ? "Historical" : r.var_method} method — the 5th percentile of realised daily returns over ${r.observations} sessions.`],
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-grid)" }}>
      <Card
        title="Risk and return"
        subtitle={`Against ${data.benchmark}, over ${window.toUpperCase()}.`}
        action={
          <div style={{ display: "flex", gap: 6 }}>
            {available.map((w) => (
              <button
                key={w}
                onClick={() => setWindow(w)}
                style={{
                  background: w === window ? "var(--ink-900)" : "var(--surface)",
                  color: w === window ? "var(--text-inverse)" : "var(--text-secondary)",
                  border: "1px solid var(--border)", borderRadius: 7, padding: "5px 11px",
                  font: "inherit", fontSize: 12, cursor: "pointer",
                }}
              >
                {w.toUpperCase()}
              </button>
            ))}
          </div>
        }
      >
        <div style={grid("repeat(auto-fit, minmax(230px, 1fr))")}>
          {cards.map(([label, value, bench, better, tip]) => (
            <div key={label} title={tip} style={{ border: "1px solid var(--border)", padding: 13, cursor: "help" }}>
              <div style={{ fontFamily: "Archivo, Inter, sans-serif", fontSize: 10, fontWeight: 600,
                            letterSpacing: ".09em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                {label} ⓘ
              </div>
              <div style={{ fontFamily: "Newsreader, serif", fontSize: 22, marginTop: 6, fontVariantNumeric: "tabular-nums" }}>
                {value}
              </div>
              <div style={{ fontSize: 11.5, marginTop: 4 }}>
                {bench == null ? (
                  <Badge tone="neutral">no index comparator</Badge>
                ) : (
                  <>
                    <Badge tone={better ? "positive" : "warning"}>
                      {better ? "better than index" : "worse than index"}
                    </Badge>{" "}
                    <span style={{ color: "var(--text-tertiary)" }}>{bench}</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 14 }}>
          Maximum drawdown <b>{pct(r.max_drawdown)}</b> · CVaR 95% <b>{pct(r.cvar_1d_95)}</b> ·
          99% VaR <b>{pct(r.var_1d_99)}</b> · {r.observations} sessions.
        </div>
      </Card>

    </div>
  );
}

/* -------------------------------------------------------------- 4. Diversification */

const RETURN_COLUMNS: [string, string][] = [
  ["1w", "1W"], ["1m", "1M"], ["3m", "3M"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"],
];

/**
 * Cell tint for an ALREADY-PERCENT return.
 *
 * Opacity is |return| / 60, capped at 0.4: a +60% year is the point where the tint is as
 * strong as it gets, and the cap is what keeps a +300% multibagger from drawing a solid
 * block that hides its own figure. Green and red are the same greens and reds the
 * correlation heatmap uses, so the two tables on this tab read as one instrument.
 */
function heatTint(value: number): string {
  const weight = Math.min(Math.abs(value) / 60, 0.4).toFixed(3);
  return value >= 0 ? `rgb(30 122 76 / ${weight})` : `rgb(179 38 30 / ${weight})`;
}

export function DiversificationPanel({ data, mode }: { data: AnalyticsResponse; mode: Mode }) {
  const { allocation, correlation, coverage } = data;
  const sectors = allocation.sector;
  const caps = allocation.market_cap;
  // READ, never recompute. The local version divided by a hard-coded 100, which matched
  // the server only while every weight was in the denominator -- see AnalyticsDerived.
  const effectiveN = data.derived.effective_holdings;

  if (mode === "basic") {
    return (
      <Card
        title="Diversification readings"
        subtitle="Weight, sector, market cap and correlation."
      >
        <Reading
          label={`Largest sector — ${sectors[0]?.label ?? EMPTY}`}
          tone={(sectors[0]?.pct ?? 0) > 25 ? "watch" : "good"}
          value={pp(sectors[0]?.pct ?? 0, 1)}
          sub={[
            ["Sectors", String(sectors.length)],
            ...(sectors[1]
              ? ([["Next", `${sectors[1].label} ${pp(sectors[1].pct, 1)}`]] as [string, ReactNode][])
              : []),
          ]}
        />
        <Reading
          label="Market cap"
          value={caps.map((c) => `${pp(c.pct, 0)} ${c.label.toLowerCase()}`).join(", ") || EMPTY}
        />
        <Reading
          label="Average pairwise correlation"
          tone={(correlation.average ?? 0) > 0.5 ? "watch" : "good"}
          value={ratio(correlation.average)}
          sub={
            correlation.tightest && correlation.loosest
              ? [
                  [
                    "Tightest",
                    `${correlation.tightest[0]} / ${correlation.tightest[1]} ${correlation.tightest[2].toFixed(2)}`,
                  ],
                  [
                    "Loosest",
                    `${correlation.loosest[0]} / ${correlation.loosest[1]} ${correlation.loosest[2].toFixed(2)}`,
                  ],
                ]
              : undefined
          }
        />
        <Reading
          label="Effective holdings"
          tone={effectiveN != null && effectiveN < 5 ? "bad" : "good"}
          value={ratio(effectiveN, 1)}
          sub={[["Actual", String(data.derived.position_count)]]}
        />
      </Card>
    );
  }

  const heatLabels = correlation.symbols;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-grid)" }}>
      <div style={grid("repeat(auto-fit, minmax(330px, 1fr))")}>
        <Card title="Market capitalisation"
              subtitle="AMFI half-yearly list, ISIN-keyed. Bands are the SEBI Oct-2017 circular —
                        top 100 large, 101–250 mid, 251+ small. Not from the fundamentals feed.">
          <DonutChart
            slices={caps.map((c, i) => ({
              label: c.label,
              value: c.pct,
              display: pp(c.pct, 2),
              // The rupee figure beside the weight. A band at 8% of a ₹1.4cr book and a
              // band at 8% of a ₹40,000 one are the same slice and not the same fact.
              sub: <Figure>{money(c.value)}</Figure>,
              // The Dashboard's allocation language: weight reads as depth of colour,
              // ink through brass. Categorical chart colours would make this screen look
              // like a different product from the one next to it.
              color: ALLOC_RAMP[i % ALLOC_RAMP.length],
            }))}
            size={200}
            thickness={26}
            legendRuled
            centerValue={caps.length}
            centerLabel="BANDS"
          />
        </Card>
        <Card title="Sectors"
              subtitle={`Top ${sectors.length} by weight, no “Others” catch-all — a 33% Others bucket makes a
                         donut useless. Classification is NSE/NIC two-level, ISIN-keyed.`}
              action={<Coverage pctValue={coverage.sector_pct} what="Sector classification" />}>
          <DonutChart
            slices={sectors.map((sector, i) => ({
              label: sector.label,
              value: sector.pct,
              display: pp(sector.pct, 2),
              color: ALLOC_RAMP[i % ALLOC_RAMP.length],
            }))}
            size={200}
            thickness={26}
            legendRuled
            // Sectors run past a dozen on a diversified book. Scrolling the legend keeps
            // the card the same height as the market-cap one beside it instead of
            // stretching the row to whatever the longest list happens to be.
            legendMaxHeight={210}
            centerValue={sectors.length}
            centerLabel="SECTORS"
          />
        </Card>
      </div>

      <Card title="Asset correlations"
            subtitle={`Pairwise correlation of daily returns, trailing one year. In a concentrated book this is
                       the most load-bearing chart in the module — it is what separates real diversification
                       from the appearance of it. Top ${Math.min(heatLabels.length, 14)} holdings by weight shown.`}>
        {heatLabels.length >= 2 ? (
          <>
            <HeatMap labels={heatLabels} matrix={correlation.matrix} />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: 11.5,
                          color: "var(--text-secondary)", marginTop: 10 }}>
              {CORRELATION_BANDS.slice().reverse().map((b) => (
                <span key={b.label}>
                  <i style={{ width: 9, height: 9, borderRadius: 2, display: "inline-block",
                              marginRight: 5, background: b.color }} />
                  {b.label}
                </span>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 11 }}>
              Average pairwise {ratio(correlation.average, 3)}
              {correlation.tightest && ` · tightest ${correlation.tightest[0]}/${correlation.tightest[1]} ${correlation.tightest[2].toFixed(3)}`}
              {correlation.loosest && ` · loosest ${correlation.loosest[0]}/${correlation.loosest[1]} ${correlation.loosest[2].toFixed(3)}`}
            </div>
          </>
        ) : (
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            At least two holdings with overlapping price history are needed for a correlation matrix.
          </div>
        )}
      </Card>

      <Card title="Asset returns"
            subtitle="Consolidated by ISIN — a scrip held across two exchanges or two folios is one row here,
                      never two. Portfolio and benchmark are pinned at the top so every row reads as a comparison.">
        <DataTable
          dense
          // Pinned reference rows read as a different KIND of row, not just a bolder one.
          rowStyle={(row) =>
            String(row.id).startsWith("__")
              ? { background: "var(--surface-sunken)", borderBottom: "2px solid var(--border-strong)" }
              : undefined
          }
          // Magnitude as tint, so a column scans as a column. Colour alone says only
          // which way a number went; the depth says how far, which is the comparison
          // the eye is actually making when it runs down a 1Y column.
          cellStyle={(row, column) => {
            const v = (row as Record<string, unknown>)[`${column.key}__heat`];
            return typeof v === "number"
              ? { background: heatTint(v), padding: "8px", textAlign: "right" }
              : undefined;
          }}
          columns={[
            { key: "asset", label: "Holding" },
            { key: "weight", label: "Weight", align: "right", numeric: true },
            ...RETURN_COLUMNS.map(([k, l]) => ({ key: k, label: l, align: "right" as const, numeric: true })),
          ] as DataColumn<Record<string, unknown>>[]}
          rows={[
            {
              id: "__portfolio",
              asset: <b>Your portfolio</b>,
              weight: <b>100.0%</b>,
              ...Object.fromEntries(RETURN_COLUMNS.map(([k]) => {
                // Only the trailing windows the risk engine computes have a portfolio
                // figure; 1W/1M/3M are per-holding only and stay blank rather than being
                // back-filled with something that means a different thing.
                const w = data.risk[k];
                return [k, w?.cum_return != null
                  ? <b style={{ color: toneColor(signOf(w.cum_return)) }}>{pct(w.cum_return, 1, true)}</b>
                  : <span style={{ color: "var(--text-tertiary)" }}>{EMPTY}</span>];
              })),
            },
            {
              id: "__benchmark",
              asset: <b>{data.benchmark}</b>,
              weight: <span style={{ color: "var(--text-tertiary)" }}>{EMPTY}</span>,
              ...Object.fromEntries(RETURN_COLUMNS.map(([k]) => {
                const w = data.risk[k];
                return [k, w?.bench_cum_return != null
                  ? <b style={{ color: toneColor(signOf(w.bench_cum_return)) }}>{pct(w.bench_cum_return, 1, true)}</b>
                  : <span style={{ color: "var(--text-tertiary)" }}>{EMPTY}</span>];
              })),
            },
            ...data.positions.map((p) => ({
              id: p.isin,
              asset: <AssetCell position={p} />,
              weight: pp(p.weight, 1),
              ...Object.fromEntries(RETURN_COLUMNS.flatMap(([k]) => {
                const v = p.returns?.[k];
                return [
                  [k, v == null
                    ? <Na reason="Not enough price history for this window." />
                    : <span style={{ color: toneColor(signOf(v)) }}>{pp(v, 1, true)}</span>],
                  // Sidecar key read by cellStyle. The cell's CONTENT and the cell's
                  // TINT are set in two different places, so the raw figure has to
                  // survive the trip -- pulling it back out of the rendered node would
                  // mean parsing a string this file just formatted.
                  [`${k}__heat`, v],
                ];
              })),
            })),
          ]}
        />
        <ReturnsCoverageNote data={data} />
      </Card>
    </div>
  );
}

/**
 * Why a whole column can be empty.
 *
 * Without this the table looks broken rather than honest. The price archive currently
 * starts in 2024, so 3Y and 5Y have nothing to compute from and every cell in those two
 * columns is n/a; separately, 1W/1M/3M exist per holding but NOT for the portfolio row,
 * because the risk engine only emits 1Y/3Y/5Y windows and back-filling the short ones
 * from the fixed-weight series would put a different measure under the same heading.
 * Both are facts about the data, and a reader who is told which is which stops hunting
 * for a bug that is not there.
 */
function ReturnsCoverageNote({ data }: { data: AnalyticsResponse }) {
  const empty = RETURN_COLUMNS.filter(
    ([k]) => !data.positions.some((p) => p.returns?.[k] != null),
  ).map(([, label]) => label);
  const noPortfolio = RETURN_COLUMNS.filter(([k]) => data.risk[k]?.cum_return == null)
    .map(([, label]) => label);

  if (empty.length === 0 && noPortfolio.length === 0) return null;
  return (
    <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 11 }}>
      {empty.length > 0 && (
        <>
          <b>{empty.join(", ")}</b> {empty.length > 1 ? "are" : "is"} blank for every holding: no
          priced session reaches back that far. The archive is not padded to fill the column.{" "}
        </>
      )}
      {noPortfolio.length > 0 && (
        <>
          The portfolio and benchmark rows carry no <b>{noPortfolio.join(", ")}</b> figure — the risk
          engine emits 1Y, 3Y and 5Y windows only, and a shorter window computed a different way
          does not belong under the same heading.
        </>
      )}
    </div>
  );
}

function AssetCell({ position }: { position: AnalyticsPosition }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <span style={{ fontWeight: 500, fontSize: 13 }}>{position.name ?? position.symbol ?? position.isin}</span>
      <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, color: "var(--text-tertiary)" }}>
        {position.symbol ?? "—"} · {position.isin}
      </span>
    </div>
  );
}

/* ---------------------------------------------------------------- 5. Fundamentals */

export function FundamentalsPanel({ data, mode }: { data: AnalyticsResponse; mode: Mode }) {
  const f = data.fundamentals;
  const rows: [string, typeof f.pe, boolean, string][] = [
    ["P/E", f.pe, true, "Weighted HARMONIC mean — equivalently, weight the earnings yields arithmetically and invert. An arithmetic mean of P/Es is dominated by the most expensive holding."],
    ["P/B", f.pb, true, "Same harmonic construction."],
    ["Dividend yield", f.dividend_yield, false, "Weighted arithmetic mean — yields add, unlike ratios."],
  ];

  if (mode === "basic") {
    return (
      <Card
        title="Portfolio ratios"
        subtitle="Weighted across holdings. P/E and P/B are harmonic means; yield is arithmetic."
      >
        {rows.map(([label, agg]) => (
          <Reading
            key={label}
            label={label}
            tone={agg.value == null ? "watch" : "good"}
            value={agg.value == null ? EMPTY : ratio(agg.value)}
            sub={[["Weight excluded", pp(agg.excluded_weight_pct, 1)]]}
          />
        ))}
      </Card>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-grid)" }}>
      <Card title="Portfolio fundamentals"
            subtitle="Weighted across holdings. Each badge says which direction is better."
            action={<Coverage pctValue={data.coverage.pe_pct} what="P/E" />}>
        <div style={grid("repeat(auto-fit, minmax(240px, 1fr))")}>
          {rows.map(([label, agg, lowerIsBetter, detail]) => (
            <div key={label} style={{ border: "1px solid var(--border)", padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <div style={{ fontFamily: "Archivo, Inter, sans-serif", fontSize: 10, fontWeight: 600,
                              letterSpacing: ".09em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                  {label}
                </div>
                <Badge tone="neutral">{lowerIsBetter ? "↓ lower is better" : "↑ higher is better"}</Badge>
              </div>
              <div style={{ fontFamily: "Newsreader, serif", fontSize: 26, margin: "12px 0 4px",
                            fontVariantNumeric: "tabular-nums" }}>
                {ratio(agg.value)}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-tertiary)" }}>
                {agg.excluded_weight_pct > 0
                  ? `${agg.excluded_weight_pct.toFixed(1)}% of weight excluded`
                  : "All holdings included"}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-tertiary)", marginTop: 8 }}>{detail}</div>
            </div>
          ))}
        </div>
      </Card>

      <Banner tone="info" title="The benchmark's own ratios do not come from the price feed.">
        {f.benchmark_source ?? "Index P/E, P/B and yield are published by NSE and are not ingested yet."}
        {" "}A query for the index returns levels and nothing else, so no benchmark comparison is shown
        here rather than a placeholder being presented as data.
      </Banner>
    </div>
  );
}

/* ----------------------------------------------------------------- 6. Performance */

export function PerformancePanel({ data, mode }: { data: AnalyticsResponse; mode: Mode }) {
  const g = data.growth_of_100k;
  const r = data.risk["1y"];

  if (!g) {
    return (
      <Card title="Performance">
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Not enough aligned price history to draw a growth series. Nothing is interpolated to fill it.
        </div>
      </Card>
    );
  }

  // The series' last values, kept as the exact strings the wire carried.
  const endPortfolio = g.portfolio[g.portfolio.length - 1] ?? null;
  const endBench = g.benchmark ? (g.benchmark[g.benchmark.length - 1] ?? null) : null;
  // Signed, and computed server-side so the sign and the wording cannot disagree.
  const delta = data.derived.growth_delta_vs_benchmark;
  const deltaSign = parseDecimal(delta);

  if (mode === "basic") {
    return (
      <Card title="₹1,00,000 invested one year ago would be"
            subtitle="Your portfolio against the benchmark, in rupees.">
        <div style={{ ...grid("repeat(auto-fit, minmax(220px, 1fr))"), margin: "16px 0" }}>
          <div style={{ border: "1px solid var(--border)", padding: 16 }}>
            <div style={{ fontFamily: "Archivo, Inter, sans-serif", fontSize: 10, fontWeight: 600,
                          letterSpacing: ".09em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
              Your portfolio
            </div>
            <div style={{ fontFamily: "Newsreader, serif", fontSize: 30, margin: "7px 0 2px" }}>
              <Figure>{money(endPortfolio)}</Figure>
            </div>
            <div style={{ color: toneColor(signOf(r?.cagr ?? null)) }}>{pct(r?.cagr, 2, true)} CAGR</div>
          </div>
          {endBench != null && (
            <div style={{ border: "1px solid var(--border)", padding: 16, background: "var(--surface-sunken)" }}>
              <div style={{ fontFamily: "Archivo, Inter, sans-serif", fontSize: 10, fontWeight: 600,
                            letterSpacing: ".09em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                {data.benchmark}
              </div>
              <div style={{ fontFamily: "Newsreader, serif", fontSize: 30, margin: "7px 0 2px" }}>
                <Figure>{money(endBench)}</Figure>
              </div>
              <div style={{ color: toneColor(signOf(r?.bench_cagr ?? null)) }}>{pct(r?.bench_cagr, 2, true)} CAGR</div>
            </div>
          )}
        </div>
        {delta != null && (
          <Reading
            label="Against the index"
            tone={deltaSign !== null && !deltaSign.isNegative() ? "good" : "bad"}
            value={
              <span style={{ color: toneColor(signOf(delta)) }}>
                <Figure>{money(delta, true)}</Figure>
              </span>
            }
          />
        )}
        <Reading
          label="Sharpe"
          tone={(r?.sharpe ?? -1) >= 1 ? "good" : "watch"}
          value={ratio(r?.sharpe)}
          sub={[["Index", ratio(r?.bench_sharpe)]]}
        />
      </Card>
    );
  }

  // The exact strings go straight to the plot, which converts each one to a coordinate
  // itself. Nothing is parsed into a number on the way there.
  const series: PlotSeries[] = [
    {
      label: "Your portfolio",
      points: g.portfolio,
      color: "var(--chart-1)",
      weight: 2.2,
    },
    ...(g.benchmark
      ? [{ label: data.benchmark, points: g.benchmark, color: "var(--ink-300)", weight: 1.8 }]
      : []),
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-grid)" }}>
      <Card title="Cumulative returns — growth of ₹1,00,000"
            subtitle="Trailing one year, daily. Both lines start from the same ₹1,00,000, so the
                      vertical gap between them at any date is what the choice was worth in rupees.">
        <VintageLinePlot
          labels={g.dates}
          series={series}
          height={300}
          // The Y axis is rupees and the X axis is dates. This passed the DATE formatter
          // as formatTick, which is the Y axis, so the money axis was labelled by
          // slicing a number to seven characters and the date axis printed all ~250
          // full ISO dates on top of each other.
          // The Y axis is rupees and the X axis is dates. `formatTick` receives the
          // axis's own EXACT tick string, so the money label is formatted from it rather
          // than reconstructed from a coordinate.
          formatTick={(v) => money(v)}
          formatLabel={(d) => d.slice(0, 7)}
          baseline={{ value: "100000", label: "₹1,00,000" }}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 10,
                      fontSize: 11.5, color: "var(--text-secondary)" }}>
          <LegendSwatch color="var(--chart-1)">
            Your portfolio — <Figure>{money(endPortfolio)}</Figure>
          </LegendSwatch>
          {endBench != null && (
            <LegendSwatch color="var(--ink-300)">
              {data.benchmark} — <Figure>{money(endBench)}</Figure>
            </LegendSwatch>
          )}
          <LegendSwatch color="var(--text-tertiary)">₹1,00,000 starting line</LegendSwatch>
        </div>
      </Card>
      <Banner tone="info" title="This series is a fixed-weight backtest of today's holdings, and says so.">
        It applies current weights backwards. It is <b>not</b> what the portfolio actually returned — that
        is TWRR and XIRR from the ledger, which Trackr+ already computes. Presenting a backtest as realised
        history would be inventing financial history.
      </Banner>
    </div>
  );
}

/* -------------------------------------------------------------- 7. Valuation Map */

const LENSES: Record<string, {
  label: string; caption: string;
  x: [keyof AnalyticsPosition, string, boolean];
  y: [keyof AnalyticsPosition, string, boolean];
  statuses: [string, string, string];
}> = {
  valuation: {
    label: "Valuation", caption: "How cheap or expensive each holding is against the market",
    x: ["pe", "P/E", true], y: ["pb", "P/B", true], statuses: ["Attractive", "Fair", "Expensive"],
  },
  growth: {
    label: "Growth", caption: "How fast each holding is growing year on year",
    x: ["profit_growth_1y", "Profit 1Y", false], y: ["sales_growth_1y", "Sales 1Y", false],
    statuses: ["Strong", "Avg", "Weak"],
  },
  profitability: {
    label: "Profitability", caption: "How efficiently each business turns capital into profit",
    x: ["roe", "ROE", false], y: ["net_margin", "Net margin", false],
    statuses: ["Efficient", "Stable", "Poor"],
  },
  quality: {
    label: "Quality", caption: "Financial strength and balance-sheet health",
    x: ["debt_to_equity", "Debt / equity", true], y: ["interest_cover", "Interest cover", false],
    statuses: ["Solid", "Avg", "Risky"],
  },
};

const FRACTION_FIELDS = new Set(["roe", "net_margin", "sales_growth_1y", "profit_growth_1y"]);

export function ValuationMapPanel({ data }: { data: AnalyticsResponse }) {
  const [lensKey, setLensKey] = useState("valuation");
  const [view, setView] = useState<"table" | "bubble">("table");
  // Indexed access is `| undefined` under strict mode; valuation is the declared default.
  const lens = LENSES[lensKey] ?? LENSES.valuation!;
  const positions = data.positions;

  const num = (p: AnalyticsPosition, field: keyof AnalyticsPosition) => {
    const v = p[field];
    return typeof v === "number" ? v : null;
  };
  const fmt = (v: number | null, field: string) =>
    v == null ? EMPTY : FRACTION_FIELDS.has(field) ? pct(v, 1) : ratio(v, field === "debt_to_equity" ? 1 : 2);

  const avg = (field: keyof AnalyticsPosition) => {
    const vals = positions.map((p) => num(p, field)).filter((v): v is number => v != null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };
  const xAvg = avg(lens.x[0]);
  const yAvg = avg(lens.y[0]);

  const status = (p: AnalyticsPosition): number | null => {
    let hits = 0, counted = 0;
    for (const [field, , lowerIsBetter] of [lens.x, lens.y]) {
      const v = num(p, field);
      const a = field === lens.x[0] ? xAvg : yAvg;
      if (v == null || a == null) continue;
      counted++;
      if (lowerIsBetter ? v < a : v > a) hits++;
    }
    if (!counted) return null;
    const r = hits / counted;
    return r >= 0.75 ? 0 : r >= 0.35 ? 1 : 2;
  };

  const counts: [number, number, number] = [0, 0, 0];
  let unrated = 0;
  positions.forEach((p) => {
    const s = status(p);
    if (s == null) unrated++;
    else counts[s] = (counts[s] ?? 0) + 1;
  });

  const plotted = positions.filter((p) => num(p, lens.x[0]) != null && num(p, lens.y[0]) != null);
  const range = (field: keyof AnalyticsPosition): [number, number] => {
    const vals = positions.map((p) => num(p, field)).filter((v): v is number => v != null);
    return vals.length ? [Math.min(...vals), Math.max(...vals)] : [0, 1];
  };
  const [xMin, xMax] = range(lens.x[0]);
  const [yMin, yMax] = range(lens.y[0]);

  const tones = ["var(--positive)", "var(--warning)", "var(--negative)"];
  const bubbles: BubblePoint[] = plotted.map((p) => ({
    key: p.isin,
    label: p.symbol ?? p.isin,
    x: num(p, lens.x[0]) as number,
    y: num(p, lens.y[0]) as number,
    weight: p.weight ?? 0,
    tone: tones[status(p) ?? 1] ?? "var(--warning)",
  }));

  const metricCell = (p: AnalyticsPosition, which: "x" | "y") => {
    const [field, , lowerIsBetter] = lens[which];
    const v = num(p, field);
    if (v == null) return <Na reason="Not published by the fundamentals feed for this scrip." />;
    const a = which === "x" ? xAvg : yAvg;
    const [lo, hi] = which === "x" ? [xMin, xMax] : [yMin, yMax];
    return (
      <div>
        {fmt(v, field as string)}
        <DistributionBar value={v} min={lo} max={hi} avg={a}
                         better={a == null ? false : lowerIsBetter ? v < a : v > a} />
      </div>
    );
  };

  const button = (active: boolean): React.CSSProperties => ({
    background: active ? "var(--ink-900)" : "var(--surface)",
    color: active ? "var(--text-inverse)" : "var(--text-secondary)",
    border: "1px solid var(--border)", borderRadius: 7, padding: "5px 12px",
    font: "inherit", fontSize: 12, cursor: "pointer",
  });

  return (
    <Card
      title="Portfolio valuation map"
      subtitle={lens.caption}
      action={
        <div style={{ display: "flex", gap: 6 }}>
          <button style={button(view === "table")} onClick={() => setView("table")}>Table</button>
          <button style={button(view === "bubble")} onClick={() => setView("bubble")}>Bubble</button>
        </div>
      }
    >
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "0 0 14px" }}>
        {Object.entries(LENSES).map(([key, l]) => (
          <button key={key} style={button(key === lensKey)} onClick={() => setLensKey(key)}>
            {l.label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
        {counts.map((c, i) => (
          <Badge key={i} tone={i === 0 ? "positive" : i === 1 ? "warning" : "negative"}>
            {c} {lens.statuses[i]}
          </Badge>
        ))}
        {unrated > 0 && <Badge tone="neutral">{unrated} not rated</Badge>}
        <Coverage pctValue={(plotted.length / Math.max(positions.length, 1)) * 100} what="Both metrics on this lens" />
      </div>

      {view === "table" ? (
        <DataTable
          dense
          columns={[
            { key: "asset", label: "Asset", sortable: true },
            { key: "weight", label: "Weight", align: "right", numeric: true, sortable: true },
            { key: "x", label: `${lens.x[1]} ${lens.x[2] ? "↓" : "↑"}`, align: "right", numeric: true },
            { key: "y", label: `${lens.y[1]} ${lens.y[2] ? "↓" : "↑"}`, align: "right", numeric: true },
            { key: "status", label: "Status", align: "right" },
          ] as DataColumn<Record<string, unknown>>[]}
          rows={[
            {
              id: "__avg",
              asset: <b>Portfolio average</b>,
              weight: <b>100.0%</b>,
              x: <b>{fmt(xAvg, lens.x[0] as string)}</b>,
              y: <b>{fmt(yAvg, lens.y[0] as string)}</b>,
              status: <span style={{ color: "var(--text-tertiary)" }}>reference</span>,
            },
            ...positions.map((p) => {
              const s = status(p);
              return {
                id: p.isin,
                asset: <AssetCell position={p} />,
                weight: (
                  <>
                    {pp(p.weight, 1)}
                    {(p.weight ?? 0) > 15 && (
                      <span title="Above a conventional 15% single-name marker. Not a recommendation — a factual flag.">
                        {" "}<Badge tone="warning">⚠</Badge>
                      </span>
                    )}
                  </>
                ),
                x: metricCell(p, "x"),
                y: metricCell(p, "y"),
                status: s == null
                  ? <Na reason="Insufficient data to rate on this lens." />
                  : <Badge tone={s === 0 ? "positive" : s === 1 ? "warning" : "negative"}>{lens.statuses[s]}</Badge>,
              };
            }),
          ]}
        />
      ) : bubbles.length ? (
        <>
          <ScatterPlot
            points={bubbles}
            xLabel={lens.x[1]}
            yLabel={lens.y[1]}
            xAvg={xAvg}
            yAvg={yAvg}
            xLowerIsBetter={lens.x[2]}
            yLowerIsBetter={lens.y[2]}
            format={(v, axis) => fmt(v, (axis === "x" ? lens.x[0] : lens.y[0]) as string)}
          />
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 8 }}>
            Radius ∝ portfolio weight, minimum 7px so a small position is never invisible. Labels are
            de-collided and joined by a leader line when they move; none is dropped.{" "}
            {positions.length - plotted.length} holding(s) cannot be plotted on this lens for want of data
            and are listed in the table as n/a.
          </div>
        </>
      ) : (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          No holding has both {lens.x[1]} and {lens.y[1]} yet, so there is nothing to plot. The table
          shows which figures are missing rather than substituting zeros.
        </div>
      )}
    </Card>
  );
}
