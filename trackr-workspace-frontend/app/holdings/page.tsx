"use client";

/**
 * Workspace's Holdings -- the SAME screen Trackr+ serves at `/holdings`.
 *
 * Replaces a Workspace-local five-column grid that read the same endpoint and formatted the
 * same figures itself. Sorting, search, the unpriced and skipped notices, the server-sourced
 * Total row and the links into each security's detail route all come with the shared screen,
 * so Workspace gains the whole Holdings surface rather than a summary of it.
 */

import { HoldingsScreen } from "@trackr/portfolio";
import { PortfolioSurface, WORKSPACE_CHROME } from "../components/portfolio-chrome";

export default function Holdings() {
  return (
    <PortfolioSurface>
      <HoldingsScreen chrome={WORKSPACE_CHROME} />
    </PortfolioSurface>
  );
}
