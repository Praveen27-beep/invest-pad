"use client";

/**
 * Workspace's destination launcher: the gear at the bottom of the rail, and the panel it opens.
 *
 * SAME BEHAVIOUR AS PLUS, DIFFERENT PANEL. Everything a keyboard or screen-reader user depends
 * on -- dialog role and name, focus containment, Escape and backdrop close, returning focus to
 * the actual invoker, ⌘K registered exactly once -- comes from `@trackr/core`'s `useLauncher`,
 * so there is one implementation of the focus trap rather than two of differing quality. What
 * this file owns is the appearance: Workspace tokens, Workspace spacing, the demo's rows.
 *
 * THE GEAR IS NOT THE ONLY WAY ANYWHERE. The rail has Portfolio, Monitors, Skills and Agents;
 * the centre strip has the portfolio tabs; Settings and Privacy are rail entries in their own
 * right. This is the complete map for people who want one, not a hamburger hiding the product.
 *
 * SELECTING A PORTFOLIO ROW SWITCHES THE SURFACE, NOT JUST THE URL. `onNavigate` is handed
 * down from the shell, which pushes the route AND selects the Portfolio surface. A modal that
 * called the router itself would move the address bar and leave the shell on a research tab.
 * The rows are real `<a href>`s either way, so modifier-click still opens a new tab.
 *
 * NO PLUS DOMAIN LINK, EVER. Every row is a local route. A launcher that sent someone to the
 * other product's origin to read their own holdings would make Workspace a menu in front of
 * Plus rather than an application that serves the portfolio itself.
 */

import Link from "next/link";
import { useLauncher } from "@trackr/core";
import { PORTFOLIO_DESTINATIONS } from "@trackr/portfolio";
import { Icon, PORTFOLIO_ICON } from "./Icon";
import { PORTFOLIO } from "./nav";
import { isBuiltInWorkspace } from "../portfolio-routes";

export function Launcher({
  onNavigate,
  activeHref,
  blocked = false,
}: {
  /** Pushes the route and selects the Portfolio surface. Owned by the shell. */
  onNavigate: (href: string) => void;
  activeHref: string;
  /** True while another dialog owns the screen: onboarding, help, a confirmation. */
  blocked?: boolean;
}) {
  const launcher = useLauncher({
    label: "Go to a portfolio destination",
    blocked,
    onNavigate,
  });
  const { open, openLauncher, closeLauncher, panelProps, backdropProps, rowProps } = launcher;

  // How many shared destinations this app does not serve yet. Stated rather than hidden: a
  // panel showing four rows where Plus shows ten looks complete and is not, and the honest
  // line costs one sentence. `portfolio-routes.ts` is the single record of what is built.
  const pending = PORTFOLIO_DESTINATIONS.filter((d) => !isBuiltInWorkspace(d.href)).length;

  return (
    <>
      <button
        type="button"
        className="ws-gear"
        onClick={open ? closeLauncher : openLauncher}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="All portfolio destinations"
        title="All destinations (⌘K)"
      >
        <Icon name="settings" size={13} />
        <span className="ws-gear-text">All destinations</span>
        <kbd className="ws-kbd">⌘K</kbd>
      </button>

      {open && <div className="ws-launcher-scrim" {...backdropProps} />}

      <div
        {...panelProps}
        tabIndex={-1}
        className="ws-launcher"
        data-open={open}
        // `display: none` when closed rather than opacity, so its links are genuinely out of the
        // tab order. A visually hidden panel whose rows are still tabbable is the classic way a
        // keyboard user ends up focused on something they cannot see.
        style={{ display: open ? "block" : "none" }}
      >
        <p className="ws-launcher-title">Destinations</p>
        <div className="ws-launcher-groups">
          {PORTFOLIO.map((group) => {
            const items = group.items.filter((item) => isBuiltInWorkspace(item.href));
            if (items.length === 0) return null;
            return (
              <div key={group.group}>
                <h5 className="ws-launcher-group">{group.group}</h5>
                {items.map((item) => (
                  <Link
                    key={item.href}
                    {...rowProps(item.href)}
                    className="ws-launcher-row"
                    data-active={item.href === activeHref}
                    aria-current={item.href === activeHref ? "page" : undefined}
                  >
                    <span className="ws-launcher-row-main">
                      <Icon name={PORTFOLIO_ICON[item.icon]} size={14} />
                      {item.label}
                    </span>
                    <span className="ws-launcher-row-sub">{item.summary}</span>
                  </Link>
                ))}
              </div>
            );
          })}
        </div>

        {pending > 0 && (
          <p className="ws-launcher-note">
            {pending} more portfolio {pending === 1 ? "screen" : "screens"} &mdash; including
            Analytics, Contribution and Transactions &mdash; are served by Trackr+ today and
            land here in FE&nbsp;11&ndash;14. They are left out rather than shown as rows that
            would 404.
          </p>
        )}
      </div>
    </>
  );
}
