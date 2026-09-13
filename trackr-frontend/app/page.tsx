"use client";

import { useCallback, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { usePortfolioRefresh } from "@/lib/onboarding";
import { formatDate, formatMoney, formatPercent, formatTimeIST } from "@/lib/format";
import type {
  HoldingOut,
  HoldingsResponse,
  PerformanceResponse,
  SummaryResponse,
} from "@/lib/api-types";
import { ErrorState, NoInvestorState } from "./components/PageState";
import { MissingPriceNotice } from "./components/MissingPriceNotice";
import { NegativeHoldingNotice } from "./components/NegativeHoldingNotice";
import { UnpricedBanner } from "./components/UnpricedBanner";
import { SkippedHoldingsNotice } from "./components/SkippedHoldingsBanner";
import { PageHeader } from "./components/PageHeader";
import { PageBody } from "./components/Shell";
import { SetupBanner } from "./components/SetupBanner";
import { ValueChartCard } from "./components/ValueChartCard";
import { DividendCard } from "./components/DividendCard";
import {
  ALLOC_RAMP,
  AllocationArcs,
  AllocationArcsSkeleton,
  Banner,
  Card,
  LedgerGrid,
  LedgerGridSkeleton,
  LedgerSecurity,
  LedgerSigned,
  LinkAction,
  SegmentedControl,
  VintageKpi,
  VintageKpiSkeleton,
  VintageXirr,
  ledgerFig,
  type ArcSlice,
  type LedgerColumn,
} from "./components/ds";

type GroupBy = "asset_class" | "sector" | "market_cap";
type ValueBasis = "current" | "invested";
type XirrWindowKey = "fy" | "1y" | "3y";

const GROUP_BY_LABEL: Record<GroupBy, string> = {
  asset_class: "Asset class",
  sector: "Sector",
  market_cap: "Market cap",
};

/** Sum of `invested` across a group's holdings — real per-security figures already on
 *  the wire, aggregated at display time for the "Invested" basis. Never fabricated. */
function sumInvested(children: { invested: string }[]): number {
  return children.reduce((sum, h) => sum + (Number(h.invested) || 0), 0);
}

interface GroupRow {
  key: string;
  label: string;
  invested: number;
  marketValue: number;
  weightPct: number | null;
}

/** ₹ in lakh, to two decimals — the scale the ledger cards read at. */
const lakh = (n: number) => `₹${(n / 100_000).toFixed(2)}L`;

export default function DashboardPage() {
  const { investorId, token, asOf, advisedOnly } = useAuth();
  // Sector, not asset class. Phase 1 builds exactly one asset class (CLAUDE.md: "Phase 1
  // builds exactly one: EQ"), so grouping by it is guaranteed to produce a single 100%
  // "Stocks" ring for EVERY user -- a chart that is technically correct and tells nobody
  // anything, and reads as broken rather than as "you hold only equities". Sector is the
  // first grouping that actually divides an equity portfolio. Asset class stays available
  // in the control, and becomes the right default the moment a second asset class ships.
  const [groupBy, setGroupBy] = useState<GroupBy>("sector");
  const [basis, setBasis] = useState<ValueBasis>("current");
  const [xirrWindow, setXirrWindow] = useState<XirrWindowKey>("fy");

  const query = { as_of: asOf, advised_only: advisedOnly || undefined };

  /**
   * How often the valued figures re-fetch while the dashboard is open.
   *
   * Polling only means anything for TODAY: an earlier `as_of` is served from bhavcopy,
   * which cannot change under a viewer. Two minutes sits just above the server's own
   * 180-second quote cache, so a poll usually costs one cheap cached read and only
   * occasionally an actual upstream fetch — the cache, not this interval, is what bounds
   * how hard the quote source is hit.
   *
   * `/snapshots` and the dividend card's ledger read are deliberately NOT polled: a daily
   * snapshot row and a transaction ledger do not move during a session.
   */
  const isToday = asOf === new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const live = { refreshMs: isToday ? 120_000 : 0 };

  const summary = useFetch<SummaryResponse>(
    investorId ? `/investors/${investorId}/summary` : null,
    query,
    token,
    live
  );
  const performance = useFetch<PerformanceResponse>(
    investorId ? `/investors/${investorId}/performance` : null,
    { as_of: asOf },
    token,
    live
  );
  const holdings = useFetch<HoldingsResponse>(
    investorId ? `/investors/${investorId}/holdings` : null,
    query,
    token,
    live
  );

  /**
   * Re-read everything the moment an import finishes, without a page reload.
   *
   * Every figure on this screen is derived from the transaction ledger on read
   * (CLAUDE.md's one architectural rule), so a promoted batch invalidates all three
   * responses at once and there is nothing to patch locally — re-fetching IS the update.
   * `useFetch` keeps the current numbers on screen until the new ones land, so this
   * repaints in place rather than blanking the dashboard.
   *
   * ValueChartCard and DividendCard own their own reads and subscribe to the same signal
   * themselves, so they are not listed here.
   */
  const refreshAll = useCallback(() => {
    summary.refetch();
    performance.refetch();
    holdings.refetch();
  }, [summary, performance, holdings]);
  usePortfolioRefresh(refreshAll);

  if (!investorId) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Holdings, performance and XIRR, replayed from your ledger." />
        <PageBody>
          <NoInvestorState />
        </PageBody>
      </>
    );
  }

  // performance.error is deliberately excluded from the blocking check: /performance
  // can 409 with MissingPriceError (XIRR needs every held ISIN priced) even when
  // /summary and /holdings succeed by partitioning that same holding out via
  // UnpricedBanner. Blocking the whole dashboard on it would make the banner
  // unreachable in exactly the case it exists for.
  const blockingErrorDetail = summary.errorDetail ?? holdings.errorDetail;
  const blockingError = summary.error ?? holdings.error;

  if (blockingErrorDetail?.isin) {
    return (
      <PageBody>
        <NegativeHoldingNotice
          isin={blockingErrorDetail.isin}
          name={blockingErrorDetail.securityName}
          deficit={blockingErrorDetail.deficit}
          asOf={blockingErrorDetail.asOf}
        />
      </PageBody>
    );
  }
  if (blockingError) {
    return (
      <PageBody>
        <ErrorState message={blockingError} />
      </PageBody>
    );
  }
  const s = summary.data;
  const p = performance.data;
  const allHoldings = holdings.data?.holdings ?? [];
  const topHoldings = allHoldings.slice(0, 5);

  // One normalised row shape from whichever of the three /summary allocation arrays is
  // selected, adapted at the call site so the arcs and the table stay grouping-agnostic.
  const groupRows: GroupRow[] =
    groupBy === "sector"
      ? (s?.allocation_by_sector ?? []).map((g) => ({
          key: g.sector ?? g.label,
          label: g.label,
          invested: sumInvested(g.children),
          marketValue: g.market_value ? Number(g.market_value) : 0,
          weightPct: g.weight_pct,
        }))
      : groupBy === "market_cap"
        ? (s?.allocation_by_market_cap ?? []).map((g) => ({
            key: g.market_cap_bucket ?? g.label,
            label: g.label,
            invested: sumInvested(g.children),
            marketValue: g.market_value ? Number(g.market_value) : 0,
            weightPct: g.weight_pct,
          }))
        : (s?.allocation ?? []).map((g) => ({
            key: g.asset_class,
            label: g.label,
            invested: sumInvested(g.children),
            marketValue: g.market_value ? Number(g.market_value) : 0,
            weightPct: g.weight_pct,
          }));

  const totalInvested = s?.invested ? Number(s.invested) : 0;

  const arcSlices: ArcSlice[] = groupRows.map((r) => ({
    label: r.label,
    value:
      basis === "invested"
        ? totalInvested > 0
          ? (r.invested / totalInvested) * 100
          : 0
        : (r.weightPct ?? 0) * 100,
  }));

  const maxWeight = Math.max(...arcSlices.map((a) => a.value), 1);

  const groupTableRows = groupRows.map((r, i) => {
    const gain = r.marketValue - r.invested;
    const weight = basis === "invested" ? (totalInvested > 0 ? (r.invested / totalInvested) * 100 : 0) : (r.weightPct ?? 0) * 100;
    return {
      id: r.key,
      label: r.label,
      color: ALLOC_RAMP[i % ALLOC_RAMP.length] as string,
      invested: lakh(r.invested),
      gain: `${gain < 0 ? "−" : "+"}₹${Math.abs(gain / 100_000).toFixed(2)}L`,
      current: lakh(r.marketValue),
      weight: `${weight.toFixed(1)}%`,
      weightPct: Math.min(100, (weight / maxWeight) * 100),
    };
  });

  const totalMarketValue = groupRows.reduce((a, r) => a + r.marketValue, 0);
  const totalGain = totalMarketValue - groupRows.reduce((a, r) => a + r.invested, 0);

  // Column definitions are hoisted so the skeletons can be handed the identical array.
  // A skeleton that guesses at the column widths is a skeleton that resizes the table
  // the moment real data lands, which is the shift it exists to prevent.
  const groupColumns: LedgerColumn[] = [
    {
      key: "label",
      label: GROUP_BY_LABEL[groupBy],
      figure: false,
      render: (r) => (
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: 9, minWidth: 0 }}>
          <span
            aria-hidden="true"
            style={{
              flexShrink: 0,
              width: 3,
              height: 11,
              background: r.color as string,
              transform: "translateY(1px)",
            }}
          />
          <span
            style={{
              minWidth: 0,
              fontFamily: "var(--font-label)",
              fontSize: 12.5,
              fontWeight: 500,
              lineHeight: 1.35,
              color: "var(--ledger-ink)",
              textWrap: "pretty",
            }}
          >
            {r.label as string}
          </span>
        </span>
      ),
    },
    { key: "invested", label: "Invested", align: "right" },
    {
      key: "gain",
      label: "Unrealised",
      align: "right",
      figure: false,
      render: (r) => <LedgerSigned value={r.gain as string} />,
    },
    { key: "current", label: "Current", align: "right" },
    {
      key: "weight",
      label: "Holding",
      align: "right",
      figure: false,
      render: (r) => (
        <span style={{ textAlign: "right" }}>
          <span style={{ ...ledgerFig, display: "block" }}>{r.weight as string}</span>
          <span
            aria-hidden="true"
            style={{
              display: "block",
              marginTop: 4,
              marginLeft: "auto",
              height: 2,
              width: `${r.weightPct as number}%`,
              maxWidth: "100%",
              background: r.color as string,
              opacity: 0.85,
            }}
          />
        </span>
      ),
    },
  ];

  const topHoldingsColumns: LedgerColumn[] = [
    {
      key: "symbol",
      label: "Security",
      figure: false,
      render: (r) => (
        <LedgerSecurity
          symbol={(r.symbol as string) ?? (r.isin as string)}
          name={r.name as string}
          flag={r.cost_estimated as boolean}
        />
      ),
    },
    {
      key: "market_value",
      label: "Current",
      align: "right",
      render: (r) => formatMoney(r.market_value as string | null),
    },
    {
      // Today's move, not the holding-period return beside it. Two different questions
      // that look alike, so they sit in separate columns rather than one stacked cell.
      key: "day_change_pct",
      label: "Day",
      align: "right",
      figure: false,
      render: (r) => <LedgerSigned value={formatPercent(r.day_change_pct as number | null)} />,
    },
    {
      key: "unrealised",
      label: "Unrealised",
      align: "right",
      figure: false,
      render: (r) => (
        <LedgerSigned
          value={formatMoney(r.unrealised as string | null)}
          sub={formatPercent(r.unrealised_pct as number | null)}
        />
      ),
    },
    {
      // Annualised since the first buy -- see ENGINE_SPEC section 5. Null for a position
      // built entirely from corporate actions (no acquisition to anchor a start date),
      // which formatPercent already renders as a dash rather than 0%.
      key: "cagr",
      label: "CAGR",
      align: "right",
      figure: false,
      render: (r) => <LedgerSigned value={formatPercent(r.cagr as number | null)} />,
    },
    {
      key: "weight_pct",
      label: "Weight",
      align: "right",
      render: (r) => formatPercent(r.weight_pct as number | null),
    },
  ];

  const xirrByWindow: Record<XirrWindowKey, number | null | undefined> = {
    fy: p?.fy_xirr,
    "1y": p?.xirr_1y,
    "3y": p?.xirr_3y,
  };
  const activeXirr = xirrByWindow[xirrWindow];

  return (
    <>
      <PageHeader
        title="Dashboard"
        // Always a subtitle, never sometimes one: a line that appears once the summary
        // resolves pushes the headline figure and the whole page down by its own height,
        // which is the single most visible shift on this screen.
        subtitle={
          summary.loading
            ? "Fetching prices…"
            : s?.live_as_of
              ? `Live · updated ${formatTimeIST(s.live_as_of)} IST`
              : "Marked to the last published bhavcopy close"
        }
        headline={formatMoney(s?.market_value)}
        changes={[
          {
            key: "unrealised",
            label: "Unrealised",
            value: `${formatMoney(s?.unrealised)} (${formatPercent(s?.unrealised_pct)})`,
            negative: s?.unrealised_pct == null ? null : s.unrealised_pct < 0,
          },
          {
            key: "realised",
            label: "Realised · since inception",
            value: formatMoney(p?.realised_to_date),
            negative: p?.realised_to_date == null ? null : Number(p.realised_to_date) < 0,
          },
        ]}
      />

      <PageBody>
        <SetupBanner />
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: "var(--gap-grid)" }}>
            {summary.loading ? (
              <>
                <VintageKpiSkeleton label="Invested" />
                <VintageKpiSkeleton label="Current value" />
                <VintageKpiSkeleton label="Unrealised P&L" />
              </>
            ) : (
              <>
                <VintageKpi
                  label="Invested"
                  value={formatMoney(s?.invested)}
                  foot="Principal"
                  footValue={`${allHoldings.length} holdings`}
                />
                <VintageKpi
                  label="Current value"
                  value={formatMoney(s?.market_value)}
                  foot="Marked to market"
                  footValue={formatDate(s?.as_of)}
                />
                <VintageKpi
                  label="Unrealised P&L"
                  value={formatMoney(s?.unrealised)}
                  foot="On invested"
                  footValue={formatPercent(s?.unrealised_pct)}
                  negative={(s?.unrealised_pct ?? 0) < 0}
                />
              </>
            )}
            {performance.loading ? (
              <VintageKpiSkeleton label="XIRR · since inception" />
            ) : p ? (
              /*
                The two CANONICAL XIRR figures, which the windowed slip beside this one
                does not carry: fy/1y/3y are the same measure over recent spans, and
                neither answers "how has this portfolio done, in total".

                Paired in one slip deliberately, because the GAP BETWEEN THEM is the
                insight rather than either number alone. `xirr_all` replays every
                transaction ever made, so it includes the realised outcome of positions
                already closed; `xirr_holdings` replays only what is still held. A wide
                divergence says the closed trades and the open book have behaved quite
                differently -- which is a fact about the portfolio no single return figure
                states. These are also the two values fixtures/golden_portfolio.json pins
                as acceptance criteria (CLAUDE.md's table), so they are the figures a user
                can check this system against.
              */
              <VintageKpi
                label="XIRR · since inception"
                value={formatPercent(p.xirr_all)}
                foot="Current holdings only"
                footValue={formatPercent(p.xirr_holdings)}
                negative={(p.xirr_all ?? 0) < 0}
              />
            ) : null}
            {performance.loading ? (
              <VintageKpiSkeleton label="Return · XIRR" wide />
            ) : p ? (
              <VintageXirr
                windows={[
                  { key: "fy", label: "FY" },
                  { key: "1y", label: "1Y" },
                  { key: "3y", label: "3Y" },
                ]}
                activeWindow={xirrWindow}
                onWindowChange={(k) => setXirrWindow(k as XirrWindowKey)}
                value={formatPercent(activeXirr)}
                caption={
                  activeXirr == null
                    ? "Not enough history for this window"
                    : "Cash-flow · all external flows"
                }
                negative={(activeXirr ?? 0) < 0}
              />
            ) : performance.errorDetail?.isins?.length ? (
              <MissingPriceNotice
                isins={performance.errorDetail.isins}
                names={performance.errorDetail.securityNames}
                compact
              />
            ) : null}
          </div>

          {p?.warning && <Banner tone="warning" title="Engine warning">{p.warning}</Banner>}
          {s && <UnpricedBanner unpriced={s.unpriced} />}
          {s && <SkippedHoldingsNotice skipped={s.skipped} />}

          <ValueChartCard />

          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
            <span style={{ font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>View by</span>
            <SegmentedControl
              options={(Object.keys(GROUP_BY_LABEL) as GroupBy[]).map((k) => ({ value: k, label: GROUP_BY_LABEL[k] }))}
              value={groupBy}
              onChange={setGroupBy}
            />
          </div>

          {/*
            Both panels are stretched to a shared minimum height and the grid tracks are
            fixed, so switching Asset class → Sector → Market cap (which changes the row
            COUNT) cannot resize the row and reflow the donut beside it. The two panels
            move together or not at all.
          */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(300px, 1fr) minmax(0, 1.6fr)",
              gap: "var(--gap-grid)",
              alignItems: "stretch",
              // The arcs are 216px plus a legend row per category; the table is a header
              // plus rows plus a total. Both settle around this, so pinning it stops the
              // row growing and shrinking as the grouping changes the category COUNT --
              // asset class has two, sector has a dozen.
              minHeight: 430,
            }}
          >
            <Card
              title="Portfolio allocation"
              subtitle={`As on ${formatDate(s?.as_of)}`}
              action={
                <SegmentedControl
                  size="sm"
                  options={[
                    { value: "current", label: "Current" },
                    { value: "invested", label: "Invested" },
                  ]}
                  value={basis}
                  onChange={setBasis}
                />
              }
            >
              {summary.loading ? (
                <AllocationArcsSkeleton rings={5} />
              ) : (
                <AllocationArcs
                  slices={arcSlices}
                  centerValue={formatMoney(basis === "invested" ? s?.invested : s?.market_value)}
                  centerLabel={basis === "invested" ? "Amount invested" : "Current value"}
                />
              )}
            </Card>

            {/* A column flex so the grid below the header can claim the card's leftover
                height and hold its Total line against the bottom edge -- see LedgerGrid's
                `fillHeight`. The row's height is set by whichever panel is taller, so
                without it the summary floats mid-card under two asset-class rows. */}
            <Card
              title="Current holdings"
              subtitle={`By ${GROUP_BY_LABEL[groupBy].toLowerCase()}`}
              action={<LinkAction href="/holdings">View all</LinkAction>}
              style={{ display: "flex", flexDirection: "column" }}
            >
              {summary.loading ? (
                <LedgerGridSkeleton columns={groupColumns} rows={4} total fillHeight />
              ) : (
                <LedgerGrid
                  fillHeight
                  rows={groupTableRows}
                  total={{
                    id: "total",
                    label: "Total",
                    color: "var(--ledger-ink)",
                    invested: lakh(groupRows.reduce((a, r) => a + r.invested, 0)),
                    gain: `${totalGain < 0 ? "−" : "+"}₹${Math.abs(totalGain / 100_000).toFixed(2)}L`,
                    current: lakh(totalMarketValue),
                    weight: "100.0%",
                    weightPct: 100,
                  }}
                  columns={groupColumns}
                />
              )}
            </Card>
          </div>

          {/* Bar labels: the ticker where this screen already knows it, ISIN otherwise.
              A dividend can come from a security that has since been sold, which is why
              the map is a fallback and not a lookup that has to succeed. */}
          <DividendCard
            names={Object.fromEntries(allHoldings.map((h) => [h.isin, h.symbol ?? h.isin]))}
          />

          <Card title="Top holdings" action={<LinkAction href="/holdings">View all</LinkAction>}>
            {holdings.loading ? (
              <LedgerGridSkeleton columns={topHoldingsColumns} rows={5} />
            ) : (
              <LedgerGrid
                rows={topHoldings.map((h: HoldingOut) => ({ ...h, id: h.isin }))}
                columns={topHoldingsColumns}
              />
            )}
          </Card>
        </div>
      </PageBody>
    </>
  );
}
