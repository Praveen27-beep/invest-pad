/**
 * Workspace's own icon set.
 *
 * Deliberately not shared with Plus. The two applications draw at different weights and
 * sizes, and an icon set is presentation -- exactly the layer the product contract says
 * each app owns. What IS shared is the semantic `PortfolioIcon` key that names which
 * concept a destination stands for; `PORTFOLIO_ICON` below binds those keys to these
 * glyphs, so adding a shared destination with a new key is a TypeScript error here
 * rather than a blank square at runtime.
 *
 * One stroke weight, one 24-grid, `currentColor` throughout, so a glyph takes the colour
 * of whatever it sits in and the rail's active state needs no icon variant.
 */

import type { PortfolioIcon } from "@trackr/portfolio";

const PATHS = {
  portfolio: "M3 13h6V3H3v10Zm0 8h6v-6H3v6Zm8 0h10V11H11v10Zm0-18v6h10V3H11Z",
  monitors: "M3 5h18v11H3zM8 20h8M12 16v4",
  skills: "M12 3l2.6 5.6 6.4.9-4.6 4.4 1.1 6.1L12 17l-5.5 3 1.1-6.1L3 9.5l6.4-.9L12 3Z",
  agents: "M7 8h10a3 3 0 0 1 3 3v4a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3v-4a3 3 0 0 1 3-3Zm5-5v5M9 13h.01M15 13h.01",
  explorer: "M4 6a2 2 0 0 1 2-2h3.6l1.7 2H18a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Z",
  settings:
    "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8.4-2.6.9.7-1.6 2.8-1.1-.4a6.9 6.9 0 0 1-1.7 1l-.2 1.2h-3.4l-.2-1.2a6.9 6.9 0 0 1-1.7-1l-1.1.4-1.6-2.8.9-.7a6.6 6.6 0 0 1 0-2l-.9-.7 1.6-2.8 1.1.4a6.9 6.9 0 0 1 1.7-1L13.3 3h3.4",
  dashboard: "M3 13h6V3H3v10Zm0 8h6v-6H3v6Zm8 0h10V11H11v10Zm0-18v6h10V3H11Z",
  performance: "M3 17l5.5-5.5 3.5 3.5L21 6M21 6h-5M21 6v5",
  holdings: "M4 7h16M4 12h16M4 17h10",
  contribution: "M12 3v9l7 4M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z",
  transactions: "M4 8h13l-3-3M20 16H7l3 3",
  import: "M12 3v11m0 0 4-4m-4 4-4-4M4 19h16",
  reconcile: "M4 12l5 5L20 6M4 6h8",
  privacy: "M12 3l7 3v5.5c0 4.2-2.9 7.6-7 8.5-4.1-.9-7-4.3-7-8.5V6l7-3Z",
  search: "M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16Zm10 2-4.5-4.5",
  logout: "M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 16l4-4-4-4M20 12H9",
  lock: "M6 11h12v9H6v-9Zm3 0V7a3 3 0 0 1 6 0v4",
  plus: "M12 5v14M5 12h14",
  // The research chat toggle. A speech bubble, not a robot: the column shows checked
  // cards and attributed passages, and an AI glyph would promise prose it never renders.
  chat: "M4 5h16v10H9l-4 4V5Z",
  /** Legal text. A document with ruled lines -- distinct from `transactions`, which is arrows. */
  terms: "M7 3h7l4 4v14H7V3Zm7 0v4h4M10 12h8M10 16h5",
  /** A company research file. */
  company: "M4 20V7l7-4 7 4v13M9 20v-5h6v5M8 11h.01M12 11h.01M16 11h.01",
  /** A research note. */
  note: "M5 4h10l4 4v12H5V4Zm10 0v4h4M9 13h6M9 17h4",
} as const;

export type IconName = keyof typeof PATHS;

/**
 * Shared semantic key -> Workspace glyph. Exhaustive by type: `Record` over
 * `PortfolioIcon` means a new shared destination cannot ship without a glyph here.
 */
export const PORTFOLIO_ICON: Record<PortfolioIcon, IconName> = {
  dashboard: "dashboard",
  performance: "performance",
  holdings: "holdings",
  contribution: "contribution",
  transactions: "transactions",
  import: "import",
  reconcile: "reconcile",
  settings: "settings",
  privacy: "privacy",
  terms: "terms",
};

export function Icon({ name, size = 17 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
