"use client";

/**
 * /analytics — portfolio analysis: what the book is made of and how it behaves.
 *
 * The Dashboard answers "what is it worth". This answers everything after that, from ONE
 * endpoint call: factor exposure, risk statistics, diversification structure, fundamental
 * positioning and per-holding diagnostics.
 *
 * Two conventions carried from the Dashboard because breaking them is visible:
 *   - the header renders in every state, including no-investor, so the page never jumps;
 *   - loading is per card, never a whole-page spinner.
 */

import type { PortfolioScreenProps } from "../chrome";
import { useState } from "react";
import { useAuth } from "@trackr/core";
import { useFetch } from "@trackr/core";
import { usePortfolioRefresh } from "@trackr/core";
import { Figure, usePrivacy } from "@trackr/core";
import type { AnalyticsResponse } from "@trackr/core";
import { ErrorState, NoInvestorState } from "../widgets/PageState";
import {
  Banner,
  Card,
  Gauge,
  IconButton,
  SegmentedControl,
  Skeleton,
  TabBar,
  VintageKpi,
  VintageKpiSkeleton,
} from "@trackr/ui";
import { NarrativeBlock } from "../widgets/NarrativeBlock";
import {
  DiversificationPanel,
  FactorPanel,
  FundamentalsPanel,
  OverviewPanel,
  PerformancePanel,
  RiskPanel,
  ValuationMapPanel,
  type Mode,
} from "../analytics/panels";
import { money, pp, signOf } from "../analytics/format";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "factor", label: "Factor Score" },
  { key: "risk", label: "Risk & Return" },
  { key: "diversification", label: "Diversification" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "performance", label: "Performance" },
  { key: "map", label: "Valuation Map" },
];

/** Which analytics tabs have a generated read-through. Absent = no block, no placeholder. */
const NARRATIVE_SURFACE: Record<string, string | undefined> = {
  overview: "analytics.overview",
  risk: "analytics.risk",
  diversification: "analytics.diversification",
};

export function AnalyticsScreen({ chrome }: PortfolioScreenProps) {
  const { Header, Body } = chrome;
  const { investorId, token, asOf, advisedOnly } = useAuth();
  const { masked, toggleMask } = usePrivacy();
  const [tab, setTab] = useState("overview");
  const [mode, setMode] = useState<Mode>("basic");

  const isToday =
    asOf === new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

  const analytics = useFetch<AnalyticsResponse>(
    investorId ? `/investors/${investorId}/analytics` : null,
    { as_of: asOf, advised_only: advisedOnly || undefined },
    token,
    { refreshMs: isToday ? 120_000 : 0 },
  );
  usePortfolioRefresh(analytics.refetch);

  const data = analytics.data;
  const kpi = data?.kpi;

  // Always present, never conditional: a subtitle that appears once the fetch resolves
  // pushes the headline and the whole page down by its own height.
  // A caption, not a report. The full provenance -- every source and its coverage -- is
  // a hover on this line rather than a wall of body copy under the charts: it matters when
  // a figure looks wrong, and almost never otherwise. The warnings that DO change how a
  // number should be read stay visible, in the banner and the per-section badges.
  const subtitle = analytics.loading
    ? "Computing…"
    : data
      ? `Marked to ${data.as_of} · against ${data.benchmark}`
      : "Factor exposure, risk, diversification and per-holding diagnostics";

  const provenance = data
    ? [
        ...Object.entries(data.sources).map(([k, v]) => `${k.replace(/_/g, " ")} — ${v}`),
        "",
        `Coverage by weight — priced ${pp(data.coverage.priced_pct, 0)}, ` +
          `P/E ${pp(data.coverage.pe_pct, 0)}, P/B ${pp(data.coverage.pb_pct, 0)}, ` +
          `ROE ${pp(data.coverage.roe_pct, 0)} (all derived from statements), ` +
          `D/E ${pp(data.coverage.debt_to_equity_pct, 0)}, sector ${pp(data.coverage.sector_pct, 0)}`,
        `Computed ${new Date(data.generated_at).toLocaleString("en-IN")} · read-only`,
      ].join("\n")
    : undefined;

  const header = (
    <Header
      title="Analytics"
      subtitle={<span title={provenance} style={{ cursor: provenance ? "help" : undefined }}>{subtitle}</span>}
      headline={<Figure>{money(kpi?.market_value)}</Figure>}
      changes={
        kpi
          ? [
              {
                key: "unrealised",
                label: "Unrealised",
                value: (
                  <Figure>
                    {money(kpi.unrealised)} ({pp(kpi.unrealised_pct, 2, true)})
                  </Figure>
                ),
                negative: signOf(kpi.unrealised) === "neg",
              },
              {
                key: "day",
                label: "Today",
                value: (
                  <Figure>
                    {money(kpi.day_change)} ({pp(kpi.day_change_pct, 2, true)})
                  </Figure>
                ),
                negative: signOf(kpi.day_change) === "neg",
              },
            ]
          : []
      }
      action={
        <IconButton
          name="eye"
          label={masked ? "Show amounts" : "Hide amounts"}
          active={masked}
          onClick={toggleMask}
        />
      }
    />
  );

  if (!investorId) {
    return (
      <>
        {header}
        <Body>
          <NoInvestorState />
        </Body>
      </>
    );
  }

  if (analytics.error && !data) {
    return (
      <>
        {header}
        <Body>
          <ErrorState message={analytics.error} />
        </Body>
      </>
    );
  }

  return (
    <>
      {header}
      <Body>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
          {data && <ProvenanceBanner data={data} />}
          {chrome.banners}

          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: "var(--gap-grid)" }}>
            {analytics.loading || !data ? (
              <>
                <VintageKpiSkeleton label="Invested" />
                <VintageKpiSkeleton label="Market value" />
                <VintageKpiSkeleton label="Unrealised" />
                <VintageKpiSkeleton label="Health" />
              </>
            ) : (
              <>
                <VintageKpi
                  label="Invested"
                  value={<Figure>{money(kpi?.invested)}</Figure>}
                  foot="Cost of open lots"
                  footValue={`${data.positions.length} holdings`}
                />
                <VintageKpi
                  label="Market value"
                  value={<Figure>{money(kpi?.market_value)}</Figure>}
                  foot="Marked to"
                  footValue={data.as_of}
                />
                <VintageKpi
                  label="Unrealised"
                  value={<Figure>{money(kpi?.unrealised)}</Figure>}
                  foot="On invested"
                  footValue={pp(kpi?.unrealised_pct, 2, true)}
                  negative={signOf(kpi?.unrealised) === "neg"}
                  footNegative={signOf(kpi?.unrealised_pct) === "neg"}
                />
                <HealthKpi data={data} />
              </>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between",
                        gap: 12, flexWrap: "wrap" }}>
            <TabBar tabs={TABS} active={tab} onChange={setTab} />
            <SegmentedControl
              size="sm"
              value={mode}
              onChange={(v) => setMode(v as Mode)}
              options={[
                { value: "basic", label: "Basic" },
                { value: "advanced", label: "Advanced" },
              ]}
            />
          </div>

          {analytics.loading || !data ? (
            <Card><Skeleton height={260} /></Card>
          ) : (
            <>
              {tab === "overview" && <OverviewPanel data={data} mode={mode} />}
              {tab === "factor" && <FactorPanel data={data} mode={mode} />}
              {tab === "risk" && <RiskPanel data={data} mode={mode} />}
              {tab === "diversification" && <DiversificationPanel data={data} mode={mode} />}
              {tab === "fundamentals" && <FundamentalsPanel data={data} mode={mode} />}
              {tab === "performance" && <PerformancePanel data={data} mode={mode} />}
              {tab === "map" && <ValuationMapPanel data={data} />}
              {/* Only three surfaces are pre-generated by the nightly run, so the block
                  renders nothing on the others rather than showing a placeholder. */}
              {NARRATIVE_SURFACE[tab] && investorId && (
                <NarrativeBlock
                  investorId={investorId}
                  surface={NARRATIVE_SURFACE[tab]!}
                  asOf={asOf ?? undefined}
                />
              )}
            </>
          )}

        </div>
      </Body>
    </>
  );
}

function HealthKpi({ data }: { data: AnalyticsResponse }) {
  const { health } = data;
  return (
    <div
      title={`Published rubric: ${health.components.map((c) => `${c.label} ${(c.weight * 100).toFixed(0)}%`).join(" · ")}. Bands ${health.bands.map(([g, f]) => `${g}≥${f}`).join(" ")}. Rule ${health.rule_version}.`}
      style={{
        flex: "1 1 190px", border: "1px solid var(--border)", borderTop: "1px solid var(--ledger-rule)",
        background: "var(--surface)", padding: "14px 16px", display: "flex", alignItems: "center",
        gap: 12, cursor: "help", boxShadow: "var(--shadow-slip)",
      }}
    >
      <Gauge score={health.score} grade={health.grade} size={78} />
      <div>
        <div style={{ fontFamily: "Archivo, Inter, sans-serif", fontSize: 10, fontWeight: 600,
                      letterSpacing: ".09em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
          Portfolio health
        </div>
        <div style={{ fontFamily: "Newsreader, serif", fontSize: 23, marginTop: 4 }}>
          {health.score}
          <span style={{ fontSize: 13, color: "var(--text-tertiary)" }}>/100</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
          {health.drivers.join(" · ")}
        </div>
      </div>
    </div>
  );
}

/**
 * The caveat that has to be read before the fundamentals are trusted. Rendered as a real
 * banner rather than a footnote because the two facts it carries — a remapped identity and
 * a derived-rather-than-reported ratio — change how every number below it should be read.
 */
function ProvenanceBanner({ data }: { data: AnalyticsResponse }) {
  const { coverage, unresolved } = data;
  const derived = coverage.roe_derived_weight_pct;
  if (derived < 1 && unresolved.length === 0) return null;
  return (
    <Banner tone="warning" title="Read before trusting the fundamentals.">
      {derived >= 1 && (
        <>
          <b>{pp(derived, 1)} of weight</b> has a return-on-equity only because Trackr+ derives it from
          the annual statements — the feed's own field is null. Interest coverage
          ({pp(coverage.interest_cover_pct, 1)} of weight) is always derived. Debt/equity covers{" "}
          {pp(coverage.debt_to_equity_pct, 1)}.
        </>
      )}
      {unresolved.length > 0 && (
        <>
          {" "}
          <b>{unresolved.length} holding(s)</b> could not be priced or replayed and are carried out of
          every total on this page rather than valued at zero: {unresolved.map((u) => u.symbol ?? u.isin).join(", ")}.
        </>
      )}
    </Banner>
  );
}
