"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useFetch } from "@/lib/use-fetch";
import { usePortfolioRefresh } from "@/lib/onboarding";
import type { ExpectedDividendsOut, TransactionOut } from "@/lib/api-types";
import { EMPTY_VALUE, formatDate } from "@/lib/format";
import { RANGES, RANGE_SPAN_LABEL, startFor, type RangeKey } from "@/lib/ranges";
import { Card, EmptyState, SegmentedControl, Skeleton } from "./ds";

const fmtINR = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

const figureLabel = {
  display: "block",
  fontFamily: "var(--font-label)",
  fontSize: 9,
  fontWeight: 600,
  textTransform: "uppercase" as const,
  letterSpacing: ".2em",
  color: "var(--ledger-ink-soft)",
};

const figureValue = (soft?: boolean) => ({
  display: "block" as const,
  marginTop: 6,
  fontFamily: "var(--font-slip)",
  fontSize: 30,
  lineHeight: 1,
  letterSpacing: "-.014em",
  color: soft ? "var(--ledger-ink-soft)" : "var(--ledger-ink)",
});

/** The plot band's height, shared by the loaded card and its skeleton so the panel does
 *  not grow into place under the holdings grid above it. */
const PLOT_H = 168;

/** Most bars worth drawing. Past this the per-security labels collide. */
const MAX_BARS = 12;

/**
 * Dividends received, over the selected timeframe.
 *
 * **Why this reads the ledger rather than `/dividends`.** That endpoint aggregates
 * DIVIDEND rows per ISIN per FINANCIAL YEAR, which cannot answer "the last 3 months" —
 * splitting an FY total across a shorter window would mean inventing a shape for a real
 * number, exactly the failure mode CLAUDE.md rule 4 exists to stop. The dated rows are
 * the only honest basis for a calendar range, and they are the same rows the FY figure is
 * computed from, so nothing new is being calculated here: the whole ledger is read once
 * (CLAUDE.md's one architectural rule — everything derives from transactions) and the
 * DIVIDEND rows are summed for display.
 *
 * The bars are per-security within the window, not per-month, because that is the
 * resolution the rows carry.
 *
 * **"Announced" is a PROJECTION and is kept visually subordinate for that reason.** It is
 * `/dividends/expected` — a declared amount per share times the quantity the ledger says
 * was held at each ex-date — and it is NEVER added to Received. One is money that arrived
 * and feeds XIRR, TWRR and contribution; the other is money a company said it would pay.
 * A single figure containing both would be a number that means nothing, so the two are
 * fetched from separate endpoints and rendered as separate figures with different weight.
 *
 * A dash still appears where there is genuinely nothing to show — no verified declaration
 * covering a security held at its ex-date — which is a true zero rather than a missing
 * value. Declarations that could not be sized are counted in a footnote instead of being
 * folded silently into the figure or dropped.
 */
export function DividendCard({ names }: { names?: Record<string, string> }) {
  const { investorId, token, asOf } = useAuth();
  const [range, setRange] = useState<RangeKey>("1Y");

  // No `from`: the earliest dividend has to be known to say which ranges have anything of
  // their own to show, and switching range must not cost a round trip. `to` is the
  // dashboard's as-of date, so the card never counts a payout the rest of the screen is
  // not valuing yet. The ledger is not polled — it does not move on its own.
  const ledger = useFetch<TransactionOut[]>(
    investorId ? `/investors/${investorId}/transactions` : null,
    { to: asOf },
    token
  );

  // Declared dividends, sized to this ledger. A SEPARATE request on purpose, matching the
  // separate endpoint: nothing in this component may end up in a position to sum the two.
  // `as_of` bounds it to dividends whose ex-date has passed, so the card never projects a
  // payout the rest of the screen is not valuing yet.
  const expected = useFetch<ExpectedDividendsOut>(
    investorId ? `/investors/${investorId}/dividends/expected` : null,
    { as_of: asOf },
    token
  );

  // An import appends DIVIDEND rows like any other; holdings are recomputed on read, and
  // so is this. See lib/onboarding.ts.
  usePortfolioRefresh(ledger.refetch);
  usePortfolioRefresh(expected.refetch);

  /** Every DIVIDEND row, oldest first. Amounts stay strings until they are summed for
   *  display — no figure computed here is ever fed back into a calculation. */
  const dividendRows = useMemo(
    () =>
      (ledger.data ?? [])
        .filter((t) => t.txn_type === "DIVIDEND")
        .slice()
        .sort((a, b) => a.txn_date.localeCompare(b.txn_date)),
    [ledger.data]
  );

  const earliest = dividendRows[0]?.txn_date;

  /**
   * Which ranges have anything of their own to show.
   *
   * A range whose start is at or before the first dividend ever received draws exactly
   * what Max draws, so offering it as a separate button is a promise the data cannot
   * keep. Those are disabled and say why on hover — the same rule the value chart applies
   * to its snapshot history.
   */
  const options = useMemo(
    () =>
      RANGES.map((r) => {
        if (!earliest || r === "Max") return { value: r, label: r };
        const clips = startFor(r, asOf) > earliest;
        return {
          value: r,
          label: r,
          disabled: !clips,
          title: clips
            ? undefined
            : `First dividend received ${formatDate(earliest)}, so ${r} shows the same as Max.`,
        };
      }),
    [earliest, asOf]
  );

  // A disabled range must still draw something rather than an empty card, and Max is the
  // only range guaranteed to cover every row there is.
  const effectiveRange = options.find((o) => o.value === range)?.disabled ? "Max" : range;

  const windowRows = useMemo(() => {
    const from = startFor(effectiveRange, asOf);
    return dividendRows.filter((t) => t.txn_date >= from);
  }, [dividendRows, effectiveRange, asOf]);

  /** Per-security totals inside the window, largest first. */
  const bars = useMemo(() => {
    const byIsin = new Map<string, number>();
    for (const t of windowRows) {
      byIsin.set(t.isin, (byIsin.get(t.isin) ?? 0) + Number(t.dividend_amount));
    }
    return Array.from(byIsin, ([isin, amount]) => ({ isin, amount }))
      .filter((b) => b.amount > 0)
      .sort((a, b) => b.amount - a.amount)
      .slice(0, MAX_BARS);
  }, [windowRows]);

  const received = windowRows.reduce((sum, t) => sum + Number(t.dividend_amount), 0);
  const max = Math.max(...bars.map((b) => b.amount), 1);

  /** Declared but not yet received, across the whole ledger -- NOT windowed like Received.
   *
   *  Deliberately not filtered to the selected range: an outstanding declaration is
   *  outstanding whatever window is on screen, and a "3 months" filter on it would suggest
   *  the older ones had been paid. `null` rather than 0 when there is nothing projected, so
   *  the figure reads as a dash -- a true "nothing is outstanding", distinct from a sized
   *  projection that happens to total zero.
   *
   *  This value and `received` are never added. See the component docstring. */
  const announced =
    expected.data && expected.data.expected.length > 0
      ? Number(expected.data.total_gross_expected)
      : null;

  /** Declarations that could not be sized -- surfaced as a count, never folded into the
   *  figure. Mostly single-sourced declarations awaiting corroboration, which is a normal
   *  resting state, so this is a footnote rather than a warning. */
  const unsized = expected.data?.unprojectable.length ?? 0;

  const label = (isin: string) => names?.[isin] ?? isin;

  /** Never claims a receipt the ledger cannot show. With declarations on file but no
   *  DIVIDEND row yet, the card is genuinely reporting the announced side only, and
   *  saying "Received since ..." there would name a date that does not exist. */
  const subtitle = !earliest
    ? announced === null
      ? "Dividend income from the ledger"
      : "Announced, not yet received"
    : effectiveRange === "Max"
      ? `Received since ${formatDate(earliest)}`
      : `Received in ${RANGE_SPAN_LABEL[effectiveRange]}`;

  return (
    <Card
      title="Dividends"
      subtitle={subtitle}
      action={
        <SegmentedControl size="sm" options={options} value={range} onChange={setRange} />
      }
    >
      {ledger.loading || expected.loading ? (
        // Waits for BOTH requests, because "no dividends recorded yet" is a claim about
        // the ledger AND the declarations. Showing it the moment the ledger alone
        // resolves flashes that message on screen and then replaces it with a populated
        // card, which reads as the figure having been wrong.
        // The same two figures and the same plot band the loaded card draws.
        <>
          <div style={{ display: "flex", gap: 40 }}>
            <div>
              <span style={figureLabel}>Received</span>
              <Skeleton width={132} height={26} style={{ marginTop: 6 }} />
            </div>
            <div>
              <span style={figureLabel}>Announced</span>
              <Skeleton width={92} height={26} style={{ marginTop: 6 }} />
            </div>
          </div>
          <div
            style={{
              marginTop: 20,
              display: "flex",
              alignItems: "flex-end",
              gap: 10,
              height: PLOT_H,
              borderBottom: "1px solid var(--ledger-ink)",
            }}
          >
            {[0.58, 0.83, 0.41, 0.7, 0.52].map((fraction, i) => (
              <div key={i} style={{ flex: 1, display: "flex", justifyContent: "center" }}>
                <Skeleton width="100%" height={(PLOT_H - 26) * fraction} style={{ maxWidth: 38 }} />
              </div>
            ))}
          </div>
        </>
      ) : ledger.error ? (
        <p style={{ margin: 0, font: "var(--type-body)", color: "var(--negative)" }}>{ledger.error}</p>
      ) : !earliest && announced === null ? (
        // BOTH halves empty -- nothing received AND nothing declared. Gating this on
        // `earliest` alone (the first DIVIDEND *ledger* row) was a bug: it hid a fully
        // computed Announced figure behind "no dividends recorded yet" whenever the
        // ledger had no receipts, which is the normal state of this product. Declared
        // dividends are automated; receipt is not (CLAUDE.md's four states), so "no
        // DIVIDEND rows" and "no dividends" are different claims and only the first is
        // what an empty ledger proves.
        <EmptyState
          title="No dividends recorded yet"
          hint="DIVIDEND rows in your ledger are aggregated here. Import a contract note or add one manually to see them."
        />
      ) : (
        <>
          <div style={{ display: "flex", gap: 40 }}>
            <div>
              <span style={figureLabel}>Received</span>
              <span className="tabular-nums" style={figureValue()}>
                {fmtINR(received)}
              </span>
            </div>
            <div>
              <span style={figureLabel}>Announced</span>
              <span className="tabular-nums" style={figureValue(true)}>
                {announced === null ? EMPTY_VALUE : fmtINR(announced)}
              </span>
            </div>
          </div>

          {bars.length === 0 ? (
            // A window with no DIVIDEND rows is a true, known zero -- nothing was paid in
            // it -- so the figure above stays ₹0 and only the plot goes away. Reserving
            // the band's height keeps the card from resizing as ranges are switched.
            <div style={{ marginTop: 20, minHeight: PLOT_H }}>
              <EmptyState
                title={`No dividends received in ${
                  effectiveRange === "Max" ? "your ledger" : RANGE_SPAN_LABEL[effectiveRange]
                }`}
                hint={
                  earliest
                    ? `The first one on record was ${formatDate(earliest)}. Widen the range to see it.`
                    : // Declarations exist, no receipt does. Says why rather than
                      // suggesting a wider range, which would find nothing either --
                      // and never implies the announced figure was paid.
                      "The Announced figure is what companies declared on shares you held. Receipt is not automated: add the credit or import a funds statement to record it."
                }
              />
            </div>
          ) : (
            <>
              <div
                style={{
                  marginTop: 20,
                  display: "flex",
                  alignItems: "flex-end",
                  gap: 10,
                  height: PLOT_H,
                  borderBottom: "1px solid var(--ledger-ink)",
                }}
              >
                {bars.map((b) => {
                  const h = (b.amount / max) * (PLOT_H - 26);
                  return (
                    <div
                      key={b.isin}
                      title={`${label(b.isin)} · ${fmtINR(b.amount)}`}
                      style={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "flex-end",
                        gap: 5,
                        height: "100%",
                      }}
                    >
                      <span
                        className="tabular-nums"
                        style={{ fontFamily: "var(--font-slip)", fontSize: 12, color: "var(--ledger-ink-soft)" }}
                      >
                        {fmtINR(b.amount)}
                      </span>
                      <div
                        style={{
                          width: "100%",
                          maxWidth: 38,
                          height: Math.max(3, h),
                          background: "var(--data-received)",
                          borderRadius: "var(--radius-xs) var(--radius-xs) 0 0",
                        }}
                      />
                    </div>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                {bars.map((b) => (
                  <span
                    key={b.isin}
                    style={{
                      flex: 1,
                      textAlign: "center",
                      font: "var(--type-label)",
                      color: "var(--chart-axis-text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {label(b.isin)}
                  </span>
                ))}
              </div>
            </>
          )}

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
              marginTop: 14,
            }}
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                font: "var(--type-body-sm)",
                color: "var(--text-secondary)",
              }}
            >
              <span style={{ width: 11, height: 11, borderRadius: 2, background: "var(--data-received)" }} />
              Received, per security
            </span>
            <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
              {announced === null
                ? "Announced is declared-but-unpaid, projected from your holdings at each ex-date. Nothing is outstanding."
                : "Announced is declared-but-unpaid, projected from your holdings at each ex-date — not income, and not counted in returns."}
              {unsized > 0
                ? ` ${unsized} declaration${unsized === 1 ? "" : "s"} could not be sized; see Exceptions.`
                : ""}
            </p>
          </div>
        </>
      )}
    </Card>
  );
}
