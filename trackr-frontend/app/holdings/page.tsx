"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { usePortfolioRefresh } from "@/lib/onboarding";
import { formatMoney, formatPercent, formatQuantity } from "@/lib/format";
import type { HoldingOut, HoldingsResponse } from "@/lib/api-types";
import { ErrorState, NoInvestorState } from "../components/PageState";
import { UnpricedBanner } from "../components/UnpricedBanner";
import { SkippedHoldingsBanner } from "../components/SkippedHoldingsBanner";
import { PageHeader } from "../components/PageHeader";
import { PageBody } from "../components/Shell";
import {
  Card,
  EmptyState,
  Input,
  LedgerGrid,
  LedgerGridSkeleton,
  LedgerSecurity,
  LedgerSigned,
  type LedgerColumn,
} from "../components/ds";

type SortKey = "symbol" | "invested" | "market_value" | "unrealised" | "weight_pct";

interface Row extends HoldingOut {
  id: string;
  [key: string]: unknown;
}

export default function HoldingsPage() {
  const { investorId, token, asOf, advisedOnly } = useAuth();
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("weight_pct");

  // Same live cadence as the Dashboard, and for the same reason: these are marked-to-market
  // figures, and only today's move. See lib/use-fetch.ts's FetchOptions.
  const isToday = asOf === new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const holdings = useFetch<HoldingsResponse>(
    investorId ? `/investors/${investorId}/holdings` : null,
    { as_of: asOf, advised_only: advisedOnly || undefined },
    token,
    { refreshMs: isToday ? 120_000 : 0 }
  );

  // A finished import changes what is held, and holdings are recomputed from the ledger
  // on every read -- so the correct response to "new transactions exist" is simply to
  // read again. See lib/onboarding.ts.
  usePortfolioRefresh(holdings.refetch);

  const rows = useMemo<Row[]>(() => {
    const all = (holdings.data?.holdings ?? []).map((h) => ({ ...h, id: h.isin }) as Row);
    const needle = q.trim().toLowerCase();
    const filtered = needle
      ? all.filter((h) =>
          `${h.symbol ?? ""} ${h.name ?? ""} ${h.isin}`.toLowerCase().includes(needle)
        )
      : all;
    // Sort descending on figures, ascending on the label — the useful default for each.
    return filtered.slice().sort((a, b) => {
      if (sortKey === "symbol") return (a.symbol ?? a.isin).localeCompare(b.symbol ?? b.isin);
      const av = Number(a[sortKey] ?? 0);
      const bv = Number(b[sortKey] ?? 0);
      return bv - av;
    });
  }, [holdings.data, q, sortKey]);

  const totals = holdings.data?.totals;

  /**
   * The Total line under the table — the portfolio's own figures, straight off the wire.
   *
   * `/holdings.totals` is computed server-side in the Decimal domain over the PRICED
   * holdings (routers/holdings.py::_totals), which is exactly the set listed here, so
   * nothing is summed in JS: CLAUDE.md rule 1 forbids money arithmetic in a float, and a
   * display-layer sum of the same rows would be a second, less exact answer to a question
   * the API already answered.
   *
   * That is also why a search suppresses it. The wire figures describe the whole
   * portfolio, and printing them under a filtered subset would read as that subset's
   * total. Qty, avg cost and LTP stay blank because summing them across securities is
   * meaningless, and CAGR stays blank because a portfolio-level CAGR is not a figure this
   * product publishes at all (docs/ENGINE_SPEC.md section 5).
   */
  const totalRow =
    totals && !q.trim()
      ? ({
          id: "total",
          invested: totals.invested,
          market_value: totals.market_value,
          unrealised: totals.unrealised,
          unrealised_pct: totals.unrealised_pct,
          // A fraction, like every other row's weight_pct: the priced book is 100% of itself.
          weight_pct: 1,
        } as unknown as Row)
      : null;

  const columns: LedgerColumn<Row>[] = [
    {
      key: "symbol",
      label: "Security",
      figure: false,
      render: (r) => (
        <Link href={`/holdings/${r.isin}`} style={{ textDecoration: "none" }}>
          <LedgerSecurity symbol={r.symbol ?? r.isin} name={r.name ?? undefined} flag={r.cost_estimated} />
        </Link>
      ),
    },
    { key: "quantity", label: "Qty", align: "right", render: (r) => formatQuantity(r.quantity) },
    { key: "avg_cost", label: "Avg cost", align: "right", render: (r) => formatMoney(r.avg_cost, true) },
    { key: "last_price", label: "LTP", align: "right", render: (r) => formatMoney(r.last_price, true) },
    { key: "invested", label: "Invested", align: "right", render: (r) => formatMoney(r.invested) },
    { key: "market_value", label: "Current", align: "right", render: (r) => formatMoney(r.market_value) },
    {
      key: "unrealised",
      label: "Unrealised",
      align: "right",
      figure: false,
      render: (r) => <LedgerSigned value={formatMoney(r.unrealised)} sub={formatPercent(r.unrealised_pct)} />,
    },
    {
      key: "cagr",
      label: "CAGR",
      align: "right",
      figure: false,
      render: (r) => <LedgerSigned value={formatPercent(r.cagr)} />,
    },
    { key: "weight_pct", label: "Weight", align: "right", render: (r) => formatPercent(r.weight_pct) },
  ];

  if (!investorId) {
    return (
      <>
        <PageHeader title="Holdings" subtitle="Computed on read from the transaction ledger." />
        <PageBody>
          <NoInvestorState />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Holdings"
        subtitle="FIFO cost basis, computed on read from the ledger and never stored."
        headline={formatMoney(totals?.market_value)}
        changes={[
          {
            key: "unrealised",
            label: "Unrealised",
            value: `${formatMoney(totals?.unrealised)} (${formatPercent(totals?.unrealised_pct)})`,
            negative: totals?.unrealised_pct == null ? null : totals.unrealised_pct < 0,
          },
          { key: "invested", label: "Invested", value: formatMoney(totals?.invested), negative: null },
        ]}
      />

      <PageBody>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
          {holdings.data && <UnpricedBanner unpriced={holdings.data.unpriced} />}
          {holdings.data && <SkippedHoldingsBanner skipped={holdings.data.skipped} onFixed={holdings.refetch} />}

          <Card
            title="Holdings"
            subtitle={`${rows.length} priced position${rows.length === 1 ? "" : "s"} · FIFO cost basis`}
            action={
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>Sort</span>
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  style={{
                    appearance: "none",
                    padding: "5px 10px",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border)",
                    background: "var(--surface)",
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-body)",
                    fontSize: "var(--text-xs)",
                    cursor: "pointer",
                  }}
                >
                  <option value="weight_pct">Weight</option>
                  <option value="market_value">Current value</option>
                  <option value="invested">Invested</option>
                  <option value="unrealised">Unrealised</option>
                  <option value="symbol">Security</option>
                </select>
                <div style={{ width: 200 }}>
                  <Input icon="search" placeholder="Search" value={q} onChange={setQ} />
                </div>
              </div>
            }
          >
            {holdings.loading ? (
              // The real column array, so the loading table's tracks are the loaded
              // table's tracks and nothing resizes when the rows arrive.
              <LedgerGridSkeleton columns={columns} rows={8} gap={18} />
            ) : holdings.error ? (
              <ErrorState message={holdings.error} />
            ) : rows.length === 0 ? (
              <EmptyState
                title={q ? `No holdings match "${q}"` : "No holdings yet"}
                hint={
                  q
                    ? "Search by symbol, company name or ISIN."
                    : "Import a tradebook or add a transaction. Holdings are derived from the ledger."
                }
              />
            ) : (
              <LedgerGrid gap={18} rows={rows} columns={columns} total={totalRow} />
            )}
          </Card>
        </div>
      </PageBody>
    </>
  );
}
