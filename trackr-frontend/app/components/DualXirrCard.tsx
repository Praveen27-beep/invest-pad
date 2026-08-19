"use client";

import { useState } from "react";
import { formatDate, formatPercent, signClass } from "@/lib/format";

type TrailingWindow = { key: string; label: string; value: number | null; twrr: number | null };

/**
 * app/schemas/analytical.py's PerformanceResponse comment: "Both variants together,
 * always -- reporting one alone leaves a choice about which number flatters the
 * portfolio." One card, two numbers, so the pair can't be split apart later.
 *
 * fy/1y/3y/5y XIRR sit below as a period selector -- each independently null (a
 * portfolio younger than 5 years has no xirr_5y without affecting the others; see
 * app.routers.analytical._window_xirr), so only windows with a real value get a tab.
 * period_xirr (adviser onboarding) is NOT part of this selector: it is anchored to
 * investor.onboarding_date rather than a fixed calendar span, and already discloses
 * its own opening date via the "Since {periodStart}" line below.
 *
 * TWRR (fy_twrr/twrr_1y/twrr_3y/twrr_5y, docs/ENGINE_SPEC.md section 5) rides beside
 * the active window's XIRR figure rather than getting its own tab -- it answers a
 * different question over the SAME window (did the adviser's strategy work, vs. did
 * the client's actual money-weighted experience work), so the two numbers are meant to
 * be read together, not switched between. Omitted (not just blank) when null, since a
 * portfolio younger than the window's own snapshot history legitimately has no TWRR
 * yet without that affecting whether xirr_all/xirr_holdings show.
 */
export function DualXirrCard({
  xirrAll,
  xirrHoldings,
  fyXirr,
  xirr1y,
  xirr3y,
  xirr5y,
  fyTwrr,
  twrr1y,
  twrr3y,
  twrr5y,
  periodXirr,
  periodStart,
}: {
  xirrAll: number | null;
  xirrHoldings: number | null;
  fyXirr: number | null;
  xirr1y: number | null;
  xirr3y: number | null;
  xirr5y: number | null;
  fyTwrr: number | null;
  twrr1y: number | null;
  twrr3y: number | null;
  twrr5y: number | null;
  periodXirr: number | null;
  periodStart: string | null;
}) {
  const windows: TrailingWindow[] = [
    { key: "fy", label: "FY", value: fyXirr, twrr: fyTwrr },
    { key: "1y", label: "1Y", value: xirr1y, twrr: twrr1y },
    { key: "3y", label: "3Y", value: xirr3y, twrr: twrr3y },
    { key: "5y", label: "5Y", value: xirr5y, twrr: twrr5y },
  ].filter((w) => w.value !== null);

  const [selectedKey, setSelectedKey] = useState("fy");
  const active = windows.find((w) => w.key === selectedKey) ?? windows[0];

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
      {active && (
        <div className="mt-3 border-t border-navy-100 pt-2">
          <div className="flex gap-1">
            {windows.map((w) => (
              <button
                key={w.key}
                type="button"
                onClick={() => setSelectedKey(w.key)}
                className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                  w.key === active.key
                    ? "bg-brass-100 text-navy-700"
                    : "text-navy-400 hover:text-navy-600"
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-navy-600">
            {active.label} XIRR:{" "}
            <span className={`font-medium tabular-nums ${signClass(active.value)}`}>
              {formatPercent(active.value)}
            </span>
            {active.twrr !== null && (
              <>
                {" · "}TWRR:{" "}
                <span className={`font-medium tabular-nums ${signClass(active.twrr)}`}>
                  {formatPercent(active.twrr)}
                </span>
              </>
            )}
          </p>
        </div>
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
