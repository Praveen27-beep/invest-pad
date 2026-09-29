"use client";

/**
 * Workspace's Portfolio home -- the SAME Dashboard Trackr+ serves at `/`.
 *
 * IT USED TO BE A SEPARATE SCREEN, and that was the problem. This file rendered its own
 * four-cell metric strip reading `/summary` and `/performance` directly, plus a grid of
 * tiles linking to whichever portfolio routes Workspace happened to have built. Two
 * consequences, both of which the product contract rules out:
 *
 *   TWO IMPLEMENTATIONS OF THE SAME FIGURES. Invested, market value, unrealised and XIRR
 *   were formatted and sign-coloured here as well as on Plus's Dashboard. Acceptance item 5
 *   is that the same owned portfolio yields identical financial displays in both builds, and
 *   two renderers of one number is how that stops being true without anyone noticing.
 *
 *   A SMALLER SURFACE PRESENTED AS THE WHOLE. The strip showed four figures where the
 *   Dashboard shows the KPI row, the XIRR pair, the value/benchmark chart, the allocation
 *   rings, the grouped holdings grid, dividends and the top-five table -- and the tiles
 *   listed only the routes that existed, so the missing screens read as "not part of
 *   Workspace" rather than "not extracted yet".
 *
 * The tiles are gone rather than kept: the rail and the centre strip already compose
 * `PORTFOLIO_GROUPS` from the shared package, so navigation to every portfolio destination
 * exists without a second list on this page to drift out of step with it.
 */

import { DashboardScreen } from "@trackr/portfolio";
import { PortfolioSurface, WORKSPACE_CHROME } from "./components/portfolio-chrome";

export default function PortfolioHome() {
  return (
    <PortfolioSurface>
      <DashboardScreen chrome={WORKSPACE_CHROME} />
    </PortfolioSurface>
  );
}
