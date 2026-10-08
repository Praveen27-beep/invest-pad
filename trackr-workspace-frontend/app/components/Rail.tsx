"use client";

/** One navigation owner; portfolio restores its last route and research access remains server-authorized. */

import Link from "next/link";
import { useEffect, useState } from "react";
import { isPortfolioPath } from "@trackr/portfolio";
import { useAuth, useCapabilities } from "@trackr/core";
import { usePathname } from "next/navigation";
import { useWorkspaceNav } from "@/lib/workspace-context";
import { Icon } from "./Icon";
import { Launcher } from "./Launcher";
import { ButlerInboxEntry } from "./butler/ButlerControls";
import { ExplorerTree } from "./research/ExplorerTree";
import { RAIL_ENTRIES } from "./nav";

export function Rail() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);
  const { user, logout } = useAuth();
  const { hasWorkspace, status } = useCapabilities();
  const { lastPortfolioUrl, navigate } = useWorkspaceNav();

  const onPortfolio = isPortfolioPath(pathname);

  return (
    <nav className="ws-rail" aria-label="Workspace" data-menu-open={menuOpen}>
      {/*
        The wordmark IS the brand -- demo.html draws no logo tile, so `.ws-mark` is
        `display: none` in the stylesheet and the two words carry it: the product name in
        the serif, the surface name in brass small-caps, sharing one baseline.
      */}
      <div className="ws-rail-head">
        <span className="ws-wordmark">
          <span className="ws-wordmark-name">Invest-pad<span className="ip-brand-cursor">_</span></span>

        </span>
        <button className="ip-mobile-menu" aria-label="Toggle Explorer navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? "×" : "☰"}</button>
      </div>

      <div className="ws-rail-scroll">
        <div className="ip-rail-search"><Launcher onNavigate={navigate} activeHref={pathname} /></div>
        {hasWorkspace && <Link href="/explorer" className="ws-rail-item ip-library-link" data-active={pathname.startsWith("/explorer")} aria-current={pathname.startsWith("/explorer") ? "page" : undefined}>Explorer</Link>}
        <div className="ws-rail-group">
          {RAIL_ENTRIES.map((entry) => {
            // Research entries stay out of the rail until the answer is known AND
            // positive. While it is still loading nothing is shown rather than a
            // guess -- flashing four entries that then vanish reads as a bug.
            if (entry.research && !hasWorkspace) return null;

            // Portfolio highlights for EVERY portfolio URL, including the redirect-only
            // compatibility routes, so the rail does not flicker to a research state while one
            // resolves.
            const active = entry.surfaceSwitch ? onPortfolio : pathname.startsWith(entry.href);
            // Portfolio returns to where you were, including its query. The other entries are
            // ordinary destinations.
            const href = entry.surfaceSwitch ? lastPortfolioUrl : entry.href;

            return (
              <Link
                key={entry.key}
                href={href}
                className="ws-rail-item"
                data-active={active}
                aria-current={active ? "page" : undefined}
              >
                <span className="ws-rail-text">{entry.label}</span>
              </Link>
            );
          })}
        </div>

        {hasWorkspace && <ExplorerTree />}

        {status === "ready" && !hasWorkspace && (
          <div className="ws-rail-group">
            <div className="ws-rail-label">Research</div>
            <div className="ws-rail-item" aria-disabled="true">
              <span className="ws-rail-icon">
                <Icon name="lock" size={13} />
              </span>
              <span className="ws-rail-text">Not on this account</span>
            </div>
          </div>
        )}

        <div className="ws-rail-group">
          <div className="ws-rail-label">System</div>
          <Link
            href="/settings"
            className="ws-rail-item"
            data-active={pathname.startsWith("/settings")}
          >
            <span className="ws-rail-text">Settings</span>
          </Link>
          <Link
            href="/privacy"
            className="ws-rail-item"
            data-active={pathname.startsWith("/privacy")}
          >
            <span className="ws-rail-text">Privacy &amp; data</span>
          </Link>
        </div>
      </div>

      <div className="ws-rail-foot">
        <div className="ws-meter-head">
          <span className="ws-meter-label">{user?.display_name ?? user?.email ?? "Signed in"}</span>
          <span className="ws-meter-value">{hasWorkspace ? "Personal" : "Portfolio"}</span>
        </div>
        <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
          {/* Butler's inbox entry: Workspace accounts only, one read, never a poll. */}
          {hasWorkspace && <ButlerInboxEntry />}
          <button type="button" className="ws-gear" onClick={logout}>
            <Icon name="logout" size={13} />
            <span className="ws-gear-text">Sign out</span>
          </button>
        </div>
      </div>
    </nav>
  );
}
