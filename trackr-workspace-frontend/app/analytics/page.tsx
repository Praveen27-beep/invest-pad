"use client";

/**
 * Workspace's Analytics -- the SAME screen Trackr+ serves at `/analytics`.
 *
 * Every inventoried panel, its Basic/Advanced mode, its coverage notices and its single
 * endpoint call come from the shared implementation. Analytics is the destination a
 * hand-maintained second navigation list always loses, which is why the contract names it
 * explicitly and why it sits here rather than behind a Workspace setting.
 */

import { AnalyticsScreen } from "@trackr/portfolio";
import { PortfolioSurface, WORKSPACE_CHROME } from "../components/portfolio-chrome";

export default function Analytics() {
  return (
    <PortfolioSurface>
      <AnalyticsScreen chrome={WORKSPACE_CHROME} />
    </PortfolioSurface>
  );
}
