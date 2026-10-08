"use client";

/**
 * The centre's single navigation strip.
 *
 * Two views of navigation, never two stacked document strips
 * (`docs/PRODUCT_ARCHITECTURE.md` section 2):
 *
 *   Portfolio surface -> Workspace-styled tabs built from the SHARED destination definitions,
 *                        so this app cannot silently offer fewer portfolio screens than Plus.
 *   Research surface  -> the demo's 38px document tabs.
 *
 * Which one shows is resolved from the URL, not from a stored flag. That is what makes Back,
 * Forward, a refresh and a pasted link all land on the right strip: there is no second source of
 * truth to fall out of step with the address bar.
 *
 * Local controls -- chart ranges, as-of dates, company modes, analytical subviews -- are not tabs
 * and never appear here.
 *
 * ── THE DOCUMENT STRIP'S KEYBOARD AND MOUSE CONTRACT ───────────────────────────────────────
 *
 * Each tab is TWO controls: a real `<a href>` for the label and a separate `<button>` to close.
 * Nesting a button inside an anchor is invalid HTML and makes "close this tab" indistinguishable
 * from "open this tab" for a keyboard or screen-reader user. Real hrefs also mean cmd/ctrl/middle
 * click open a new browser tab natively, which is impossible if a tab is a div with an onClick.
 *
 * Left/Right/Home/End MOVE FOCUS WITHOUT NAVIGATING. Activation is Enter, Space or a click. This
 * is the `tablist` convention and it matters here more than usual: arrowing through eight
 * documents that each navigated on focus would fire eight route changes and eight page mounts to
 * reach the ninth.
 */

import Link from "next/link";
import { useRef } from "react";
import { usePathname } from "next/navigation";
import { PORTFOLIO_GROUPS, locatePortfolio } from "@trackr/portfolio";
import { useWorkspaceNav } from "@/lib/workspace-context";
import { Icon, PORTFOLIO_ICON } from "./Icon";
import { isBuiltInWorkspace } from "../portfolio-routes";

export function CentreStrip({ portfolio }: { portfolio: boolean }) {
  if (portfolio) return <PortfolioStrip />;
  return <DocumentStrip />;
}

function PortfolioStrip() {
  const pathname = usePathname();
  const here = locatePortfolio(pathname);
  // Siblings of the current group, matching how Plus's ribbon behaves -- the full map is never
  // more than the rail plus this strip plus the launcher, and neither app hides a destination.
  const siblings = here.siblings;

  return (
    <div className="ws-strip" role="navigation" aria-label="Portfolio">
      {PORTFOLIO_GROUPS.map((group) => (
        <span key={group.group} style={{ display: "contents" }}>
          {group.items
            .filter((item) => isBuiltInWorkspace(item.href))
            .map((item) => {
              const current = item.href === here.item.href;
              const inGroup = siblings.some((sibling) => sibling.href === item.href);
              // Everything listed is reachable -- unbuilt destinations are filtered out above
              // rather than rendered as tabs that 404. The current group is simply drawn brighter.
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="ws-tab"
                  aria-current={current ? "page" : undefined}
                  style={inGroup ? undefined : { opacity: 0.62 }}
                  title={item.summary}
                >
                  <span className="ws-tab-icon">
                    <Icon name={PORTFOLIO_ICON[item.icon]} size={12} />
                  </span>
                  {item.label}
                </Link>
              );
            })}
        </span>
      ))}
    </div>
  );
}

function DocumentStrip() {
  const {
    documents,
    activeId,
    closeDocument,
    goToPortfolio,
    researchChatOpen,
    openResearchChat,
    closeResearchChat,
  } = useWorkspaceNav();
  const stripRef = useRef<HTMLDivElement | null>(null);

  /**
   * Roving focus. Left/Right/Home/End move between tab labels and navigate nothing; the browser's
   * own Enter/Space on the focused link does the activating.
   */
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(event.key)) return;
    const strip = stripRef.current;
    if (!strip) return;
    const labels = Array.from(strip.querySelectorAll<HTMLElement>(".ws-doc-tab-label"));
    if (labels.length === 0) return;
    const index = labels.indexOf(document.activeElement as HTMLElement);
    event.preventDefault();
    let next: number;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = labels.length - 1;
    else if (event.key === "ArrowLeft") next = index <= 0 ? labels.length - 1 : index - 1;
    else next = index === -1 || index === labels.length - 1 ? 0 : index + 1;
    labels[next]?.focus();
  }

  return (
    <div
      ref={stripRef}
      className="ws-strip ws-strip--research"
      role="navigation"
      aria-label="Research documents"
      onKeyDown={onKeyDown}
    >
      {documents.map((doc) => {
        const active = doc.id === activeId;
        return (
          <span key={doc.id} className="ws-doc-tab" data-active={active}>
            {/*
              `href` is non-null for every OPEN document: the store refuses to open a reserved
              descriptor that has none, so there is no case here where a tab cannot navigate.
              The fallback keeps TypeScript honest without inventing a route.
            */}
            <Link
              href={doc.href ?? "#"}
              className="ws-doc-tab-label"
              aria-current={active ? "page" : undefined}
              title={doc.label}
            >
              {doc.label}
            </Link>
            <button
              type="button"
              className="ws-doc-tab-close"
              // Names the document, so a screen-reader user hears which tab they are closing
              // rather than eight identical "Close" buttons.
              aria-label={`Close ${doc.label}`}
              onClick={() => closeDocument(doc.id)}
            >
              &times;
            </button>
          </span>
        );
      })}

      {/*
        THE TRAILING CONTROL SWITCHES TO PORTFOLIO. In the demo this reads as a plus, and the
        tempting interpretation is "new note" -- which would create an empty unsaved document with
        no identity, no dedupe key and nothing to restore. It goes to Portfolio instead, which is
        the surface switch the rail also offers, and is labelled as exactly that.
      */}
      <button
        type="button"
        className="ws-strip-add"
        aria-label="Switch to Portfolio"
        title="Switch to Portfolio"
        onClick={goToPortfolio}
      >
        <Icon name="portfolio" size={13} />
      </button>

      {/* Available at every width; smaller screens use an overlay. */}
      <button
        type="button"
        className="ws-strip-add"

        aria-pressed={researchChatOpen}
        aria-label={researchChatOpen ? "Close research chat" : "Open research chat"}
        title={researchChatOpen ? "Close research chat" : "Open research chat"}
        onClick={researchChatOpen ? closeResearchChat : openResearchChat}
      >
        <Icon name="chat" size={13} />
      </button>
    </div>
  );
}
