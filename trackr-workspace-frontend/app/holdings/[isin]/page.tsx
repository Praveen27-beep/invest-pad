"use client";

/**
 * Workspace's holding detail -- the SAME screen Trackr+ serves at `/holdings/[isin]`.
 *
 * A HOLDING, NOT A COMPANY. This route and the eventual `/research/companies/[isin]` are
 * separate identities on purpose (`docs/PRODUCT_ARCHITECTURE.md` section 3): the same ISIN
 * has a position with lots, realised gains and a ledger, and -- separately, and only if
 * someone chose to open one -- a research file. Clicking a holding stays on the Portfolio
 * surface and opens this; it never becomes research entry, which FE 15 adds through Explorer.
 */

import { HoldingDetailScreen } from "@trackr/portfolio";
import { PortfolioSurface, WORKSPACE_CHROME } from "../../components/portfolio-chrome";

export default function HoldingDetail() {
  return (
    <PortfolioSurface>
      <HoldingDetailScreen chrome={WORKSPACE_CHROME} />
    </PortfolioSurface>
  );
}
