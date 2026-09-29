"use client";

/**
 * The Workspace rail: the four destinations in the order the product contract fixes --
 * Portfolio, Monitors, Skills, Agents -- then Explorer, then the bottom gear.
 *
 * ── WHY THE NAV ROWS HAVE NO ICONS ────────────────────────────────────────────────────
 *
 * They did, and demo.html's rail does not: its `railHTML()` emits a label and an optional
 * mono count, and nothing else. The glyphs are not missing from that design, they are
 * spent elsewhere -- the EXPLORER rows below carry them, which is what separates "a
 * destination" from "a thing you have collected" at a glance. Adding a glyph to every row
 * flattens that distinction and is how this rail came to look like a generic app sidebar.
 *
 * PORTFOLIO IS A SURFACE SWITCH, NOT A DOCUMENT. Selecting it moves the centre to the
 * portfolio surface and restores the last portfolio URL visited in this session,
 * including its query, per `docs/PRODUCT_ARCHITECTURE.md` section 2. It is not closable
 * and it never navigates off this origin: same Next router, same React root, no iframe,
 * no `window.open`, no full-page reload.
 *
 * WHAT THE RAIL DOES NOT DO: authorise anything. Research entries are hidden from an
 * account without the Workspace capability because showing a door that cannot open is
 * unkind, not because hiding it protects anything. The server refuses those routes on
 * its own -- see `require_workspace_access` -- and typing the URL directly lands on the
 * same refusal.
 */

import Link from "next/link";
import { isPortfolioPath } from "@trackr/portfolio";
import { useAuth, useCapabilities } from "@trackr/core";
import { usePathname } from "next/navigation";
import { useWorkspaceNav } from "@/lib/workspace-context";
import { Icon } from "./Icon";
import { Launcher } from "./Launcher";
import { ButlerInboxEntry } from "./butler/ButlerControls";
import { RAIL_ENTRIES } from "./nav";

export function Rail() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { hasWorkspace, status } = useCapabilities();
  const { lastPortfolioUrl, navigate } = useWorkspaceNav();

  const onPortfolio = isPortfolioPath(pathname);

  return (
    <nav className="ws-rail" aria-label="Workspace">
      {/*
        The wordmark IS the brand -- demo.html draws no logo tile, so `.ws-mark` is
        `display: none` in the stylesheet and the two words carry it: the product name in
        the serif, the surface name in brass small-caps, sharing one baseline.
      */}
      <div className="ws-rail-head">
        <span className="ws-wordmark">
          <span className="ws-wordmark-name">Trackr</span>
          <span className="ws-wordmark-sub">Workspace</span>
        </span>
      </div>

      <div className="ws-rail-scroll">
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

        {hasWorkspace && (
          <>
            {/*
              THE EXPLORER HEADER'S "+" IS NOT RENDERED, because there is nothing behind it
              yet. In demo.html it adds a company; here that record type does not exist, and
              a control that opens nothing is worse than an absent one. The header keeps its
              geometry so the row lands where the design puts it.
            */}
            <div className="ws-exhead">
              <span className="ws-exhead-label">Explorer</span>
            </div>
            <div className="ws-explorer">
              <Link
                href="/explorer"
                className="ws-exrow ws-exrow--company"
                aria-current={pathname.startsWith("/explorer") ? "page" : undefined}
              >
                <span className="ws-exrow-chev" aria-hidden="true">
                  &#9656;
                </span>
                <span className="ws-exrow-icon">
                  <Icon name="company" size={12} />
                </span>
                <span className="ws-exrow-label">Companies</span>
              </Link>
              {/*
                NO CHILDREN UNDER "COMPANIES" YET, AND THE OPEN DOCUMENTS ARE NOT THEM.
                demo.html nests each company's notes here, populated from its own fixture.
                Two things rule out reproducing that: copying those names in would put
                invented research on the screen, and the obvious substitute -- the list of
                open documents -- is wrong, because an open screen such as Agents is not a
                note belonging to a company. The document strip already shows what is open.
              */}
            </div>
          </>
        )}

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
          <span className="ws-meter-value">{hasWorkspace ? "Workspace" : "Trackr+"}</span>
        </div>
        {/*
          A plan badge, not a usage meter. There is no quota, no storage limit and no
          billing in this product, so a filled bar would be decoration pretending to be
          data -- the full width simply marks which tier this account is on.
        */}
        <div className="ws-meter-track" aria-hidden="true">
          <div className="ws-meter-fill" style={{ width: hasWorkspace ? "100%" : "50%" }} />
        </div>
        {/*
          THE BOTTOM GEAR. One launcher owner for the whole application, mounted here because
          this is where its trigger lives -- and it registers the single ⌘K handler, so a second
          instance anywhere would toggle the panel open and closed on one keypress.

          `navigate` comes from the workspace navigation context, not from the router directly: a
          portfolio row has to move the shell's surface as well as the address bar, and a menu
          does not own tab state.
        */}
        <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
          <Launcher onNavigate={navigate} activeHref={pathname} />
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
