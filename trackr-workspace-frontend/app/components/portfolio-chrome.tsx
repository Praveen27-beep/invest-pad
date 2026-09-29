"use client";

/**
 * Trackr Workspace's frame for the shared portfolio screens.
 *
 * SAME SCREENS, WORKSPACE'S OWN PRESENTATION. The Dashboard, Holdings, holding detail and
 * Analytics bodies come from `@trackr/portfolio` -- one implementation, so the same owned
 * portfolio cannot produce two different figures in the two products
 * (`docs/PRODUCT_ARCHITECTURE.md` acceptance item 5). What this file supplies is everything
 * the contract says each app owns separately: the heading, the page measure, and the
 * stylesheet scope the shared components read their tokens from.
 *
 * THE `trackr-portfolio` CLASS IS LOAD-BEARING. `globals.css` defines the package's whole
 * semantic token contract inside that one selector, mapped onto Workspace's `--ws-*`
 * palette. Without the class the shared components render with every colour, font and
 * radius unset -- so it wraps the body ONCE, here, rather than being remembered per route.
 *
 * WHAT IS DELIBERATELY ABSENT. No setup checklist and no reference-sync banner: those are
 * Plus's onboarding chrome, and `chrome.banners` is optional precisely so Workspace does not
 * have to claim the same import wiring. And no metric strip of its own -- the screens carry
 * the KPI rows, and a second Workspace-local set of headline figures beside them is exactly
 * the duplicate financial rendering this extraction removed.
 */

import type { ReactNode } from "react";
import { useAuth } from "@trackr/core";
import type {
  PortfolioBodyProps,
  PortfolioChrome,
  PortfolioHeaderProps,
} from "@trackr/portfolio";

/**
 * Workspace's screen heading: crumb, serif title, one-line subject, then the screen's
 * headline figure and its changes in the `.ws-metrics` strip.
 *
 * The strip is Workspace's own layout for figures the SCREEN computed. It renders whatever
 * it is handed and calculates nothing, which is the line that keeps this presentation rather
 * than a second opinion about the portfolio.
 */
function WorkspaceHeader({ title, subtitle, headline, changes = [], action }: PortfolioHeaderProps) {
  const { asOf } = useAuth();
  return (
    <header style={{ marginBottom: 4 }}>
      <div className="ws-crumb">
        Portfolio &middot; {title} &middot; as of <span className="ws-mono">{asOf}</span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h1 className="ws-h1">{title}</h1>
          {subtitle ? <p className="ws-sub">{subtitle}</p> : null}
        </div>
        {action}
      </div>

      {headline ? (
        <div className="ws-metrics" style={{ marginTop: 22 }}>
          <div className="ws-metric">
            <div className="ws-metric-k">{title}</div>
            <div className="ws-metric-v">{headline}</div>
          </div>
          {changes.map((change) => (
            <div className="ws-metric" key={change.key}>
              <div className="ws-metric-k">{change.label}</div>
              <div
                className={
                  // Tri-state: `null` means there is no figure to colour, which is not the
                  // same as a gain of nothing.
                  change.negative === true
                    ? "ws-metric-v ws-neg"
                    : change.negative === false
                      ? "ws-metric-v ws-pos"
                      : "ws-metric-v"
                }
              >
                {change.value}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </header>
  );
}

/** The centre measure. `column` narrows it for a form-shaped screen, as in Plus. */
function WorkspaceBody({ children, column = false }: PortfolioBodyProps) {
  return (
    <div
      style={{
        marginTop: 22,
        width: "100%",
        maxWidth: column ? 720 : undefined,
        display: "flex",
        flexDirection: "column",
        gap: 20,
      }}
    >
      {children}
    </div>
  );
}

export const WORKSPACE_CHROME: PortfolioChrome = {
  Header: WorkspaceHeader,
  Body: WorkspaceBody,
};

/**
 * The one place the portfolio token scope is opened.
 *
 * Every Workspace portfolio route wraps its screen in this, so a new route cannot forget the
 * class and ship an unstyled screen.
 */
export function PortfolioSurface({ children }: { children: ReactNode }) {
  return <div className="trackr-portfolio">{children}</div>;
}
