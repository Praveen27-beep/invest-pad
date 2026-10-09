/**
 * Workspace's navigation model: the shared portfolio definitions, plus this app's own
 * research destinations.
 *
 * COMPOSES, NEVER RESTATES. The portfolio side comes wholly from `@trackr/portfolio`. There is
 * no second list of portfolio routes in this app, which is what makes "Workspace reaches the
 * complete Plus surface" checkable instead of aspirational -- a destination added to the
 * package appears here with no edit.
 *
 * THE RESEARCH SIDE IS WORKSPACE-ONLY AND LIVES IN THIS APP. Plus must not be able to render
 * a link to a research route, so these definitions are deliberately NOT in a shared package:
 * there is nothing for Plus to import even by accident, and no research module reaches its
 * bundle.
 *
 * FIVE RAIL ENTRIES, with Skills preceding Monitors in the Invest-pad surface:
 * Portfolio, Skills, Monitors, MCPs, Research settings. Portfolio is a surface switch with a default of `/`,
 * not a closable document -- it is the one entry that restores where you were rather than
 * going to a fixed place.
 */

import {
  PORTFOLIO_GROUPS,
  descriptorId,
  type PortfolioGroup,
  type ResearchKind,
} from "@trackr/portfolio";

export interface RailEntry {
  key: string;
  /** Where clicking goes. Portfolio overrides this at render time with the remembered URL. */
  href: string;
  label: string;
  /** Portfolio is a surface switch; the rest are ordinary destinations. */
  surfaceSwitch: boolean;
  /** Needs the Workspace capability. Portfolio does not. */
  research: boolean;
}

/** The workspace destinations. */
export const RAIL_ENTRIES: readonly RailEntry[] = [
  { key: "portfolio", href: "/", label: "Portfolio", surfaceSwitch: true, research: false },
  { key: "skills", href: "/skills", label: "Skills", surfaceSwitch: false, research: true },
  { key: "monitors", href: "/monitors", label: "Monitors", surfaceSwitch: false, research: true },
  { key: "connections", href: "/settings#research-connections", label: "MCPs", surfaceSwitch: false, research: true },
  { key: "agents", href: "/agents", label: "Research settings", surfaceSwitch: false, research: true },
];

export interface ResearchScreen {
  kind: ResearchKind;
  href: string;
  label: string;
  /** One line a shell can show instead of pretending the screen works. */
  summary: string;
  /**
   * True until a real backend exists for it. A `pending` screen renders a truthful
   * unavailable page: no fake collections, no disabled buttons implying a feature is
   * moments away, no sample rows.
   */
  pending: boolean;
}

/**
 * Research screens with routes today.
 *
 * Explorer is not pending: it lists the investor's real research companies and notes
 * (BE 08-10, FE 15). The other three are marked pending because their whole point is a
 * collection -- monitors, skills, agents -- and a collection page with no API behind it can
 * only be furniture.
 */
export const RESEARCH_SCREENS: readonly ResearchScreen[] = [
  {
    kind: "explorer",
    href: "/explorer",
    label: "Explorer",
    summary: "Companies you have opened a research file on",
    pending: false,
  },
  {
    kind: "monitors",
    href: "/monitors",
    label: "Monitors",
    summary: "Scheduled checks against a thesis you committed to",
    pending: true,
  },
  {
    kind: "skills",
    href: "/skills",
    label: "Skills",
    summary: "Research methods, with their scope and citation rules written down",
    pending: true,
  },
  {
    kind: "agents",
    href: "/agents",
    label: "Research settings",
    summary: "Which model runs which method, from your browser",
    pending: true,
  },
];

export function researchScreen(kind: ResearchKind): ResearchScreen | undefined {
  return RESEARCH_SCREENS.find((screen) => screen.kind === kind);
}

/**
 * Research kinds with an identity but no route. EMPTY since FE 15: company and note documents
 * are routable (`/research/companies/{ISIN}`, `/research/notes/{id}`) through the shared
 * resolver. Kept so a future kind can be reserved the same way -- `href: null` on its
 * descriptor, which a shell cannot render a link to.
 */
export const RESERVED_RESEARCH_KINDS: readonly ResearchKind[] = [];

export function isReservedKind(kind: ResearchKind): boolean {
  return RESERVED_RESEARCH_KINDS.includes(kind);
}

/** Stable tab identity for a research screen, matching the shared resolver's. */
export function screenId(kind: ResearchKind): string {
  return descriptorId(kind, null);
}

/**
 * The portfolio groups, verbatim from the package.
 *
 * Re-exported rather than copied so a reader of this file can see that Workspace's portfolio
 * navigation has no local additions or omissions -- including Analytics, which is the one a
 * hand-maintained second list always loses.
 */
export const PORTFOLIO: readonly PortfolioGroup[] = PORTFOLIO_GROUPS;
