import type { IconName } from "./ds/Icon";

export interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  /** Right-hand annotation in the section map — a count, a status, a nudge. */
  meta?: string;
}

export interface NavGroup {
  group: string;
  items: NavItem[];
}

/**
 * The whole app, in three groups.
 *
 * The grouping is the navigation model: the ribbon shows only the SIBLINGS of wherever
 * you are, and the section map (⌘K) is how you cross between groups. That keeps the
 * top bar to four or five tabs instead of eleven, without hiding anything behind a
 * hamburger — the full map is one keystroke away and always shows every destination.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    group: "Portfolio",
    items: [
      { href: "/", label: "Dashboard", icon: "dashboard" },
      // Analytics sits immediately after the Dashboard because it answers the next
      // question the Dashboard raises: the Dashboard says what the portfolio is
      // worth, this says what it is made of and how it behaves.
      { href: "/analytics", label: "Analytics", icon: "performance" },
      { href: "/holdings", label: "Holdings", icon: "holdings" },
      // Performance is NOT listed, deliberately (2026-09-08). Every figure it showed —
      // XIRR, benchmark comparison, absolute return — is already on the Dashboard, and
      // its screen never got the ds/ redesign the rest of the app did, so it read as a
      // different product bolted onto this one. The route itself now redirects to "/"
      // (app/performance/page.tsx) rather than 404ing for anyone with the URL saved.
      // Put this line back if the screen is ever redesigned into something the
      // Dashboard doesn't already cover.
      // { href: "/performance", label: "Performance", icon: "performance" },
      { href: "/contribution", label: "Contribution", icon: "contribution" },
    ],
  },
  {
    group: "Records",
    items: [
      { href: "/transactions", label: "Transactions", icon: "transactions" },
      // Notes is NOT listed, deliberately. The screen is a design proposal with no table
      // behind it — nothing typed into it is saved (see app/notes/page.tsx's own
      // docstring, which says so). A navigation entry is a promise that a screen works,
      // and this product's whole argument is that it does not make promises it cannot
      // keep: a broker picker may not imply parsers that do not exist, a forwarding
      // address may not be shown where mail cannot arrive, and an editor may not be
      // offered where nothing persists. The route still resolves for anyone developing
      // it; put this line back the day there is somewhere for a note to go.
      //
      // Contribution IS listed and stays listed: it reads a real endpoint and returns
      // real, ledger-derived numbers. It is empty on a new account for the same reason
      // every other screen is, which the setup checklist explains — that is not the
      // same thing as being unbuilt.
    ],
  },
  {
    group: "Data",
    items: [
      { href: "/import", label: "Import", icon: "import" },
      { href: "/reconcile", label: "Reconcile", icon: "reconcile" },
      { href: "/settings", label: "Settings", icon: "settings" },
      { href: "/privacy", label: "Privacy", icon: "privacy" },
    ],
  },
];

export interface NavLocation {
  group: string;
  item: NavItem;
  siblings: NavItem[];
}

/** Where an unrecognised route resolves to. Declared as a literal rather than read
 *  back out of NAV_GROUPS so it is statically known to exist. */
const DASHBOARD: NavItem = { href: "/", label: "Dashboard", icon: "dashboard" };
const DEFAULT_LOCATION: NavLocation = {
  group: "Portfolio",
  item: DASHBOARD,
  siblings: NAV_GROUPS[0]?.items ?? [DASHBOARD],
};

/**
 * Resolve a pathname to its place in the map. Falls back to the Dashboard entry so the
 * ribbon always has a coherent set of tabs, even on a route that predates the map
 * (a per-ISIN detail page, say) — those resolve to their closest prefix instead.
 */
export function locate(pathname: string): NavLocation {
  let best: NavLocation | null = null;
  for (const g of NAV_GROUPS) {
    for (const item of g.items) {
      const exact = item.href === pathname;
      const prefix = item.href !== "/" && pathname.startsWith(item.href + "/");
      if (!exact && !prefix) continue;
      // Prefer the longest matching href, so /holdings/INE... lands on Holdings
      // rather than on the root Dashboard entry.
      if (!best || item.href.length > best.item.href.length) {
        best = { group: g.group, item, siblings: g.items };
      }
    }
  }
  if (best) return best;
  return DEFAULT_LOCATION;
}
