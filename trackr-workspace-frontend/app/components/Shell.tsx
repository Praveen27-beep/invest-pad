"use client";

/**
 * Workspace's shell: the rail, one centre navigation strip, the page, and the research column.
 *
 * ONE STRIP AT A TIME. `docs/PRODUCT_ARCHITECTURE.md` section 2 is explicit that the centre
 * carries exactly one navigation strip -- the Workspace-styled portfolio tabs on a portfolio
 * route, or the research document tabs on a research route -- and never two stacked.
 * `CentreStrip` resolves which from the URL, so Back/Forward, a refresh and a pasted deep link
 * all select the correct one without any stored surface flag to get out of step with the address
 * bar.
 *
 * COMPOSES, DOES NOT NEST. This shell imports nothing from Plus: not its Shell, not its Ribbon,
 * not its layout, not its CSS. Route wrappers below it render shared portfolio content inside
 * Workspace's own chrome. Nesting Plus's application root inside this one -- or reaching it in an
 * iframe -- would give two auth owners, two theme owners and two key handlers, and would make
 * the "same data, own presentation" contract impossible to keep.
 *
 * ONE OWNER OF EACH THING, ALL OF THEM HERE:
 *   auth + capabilities  -> `Providers`, above this component
 *   navigation state     -> `WorkspaceProvider` (this file mounts it once)
 *   the launcher + ⌘K    -> `Launcher`, mounted once in the rail
 *   theme                -> nothing: pitch black is a constant in `globals.css`
 * A second instance of any of them means two states racing over one key or one keystroke.
 *
 * WHAT THE SHELL DOES NOT DO: decide access. It renders a sign-in screen when there is no
 * session, because there is nothing to show; and it lets `/settings` and `/privacy` through for
 * a Plus-only account, because losing Workspace must never take away the ability to see or erase
 * your own data. Everything else is the server's decision, made again on every request.
 */

import { usePathname } from "next/navigation";
import { isPortfolioPath } from "@trackr/portfolio";
import { useAuth, useCapabilities } from "@trackr/core";
import { WorkspaceProvider, useWorkspaceNav } from "@/lib/workspace-context";
import { AIChatDrawer } from "@trackr/portfolio";
import { Rail } from "./Rail";
import { CentreStrip } from "./CentreStrip";
import { ResearchColumn } from "./ResearchColumn";
import { Landing } from "./Landing";
import { SignIn } from "./SignIn";
import { NoWorkspaceAccess } from "./NoWorkspaceAccess";

/**
 * Reachable signed out.
 *
 * `/terms` is here because registration links to it, and nobody can be asked to accept terms
 * they must sign in to read.
 *
 * `/privacy` is deliberately NOT here. In Plus that path carries the public privacy POLICY; in
 * Workspace it is the account's own export and erasure controls, which are meaningless -- and
 * would fire unauthenticated requests -- without a session.
 */
const PUBLIC_PATHS = new Set(["/login", "/terms", "/coming-soon"]);

/**
 * Always reachable with any session, Workspace or not. Settings, Privacy and Terms are what a
 * downgraded account must keep: DPDP export and erasure are rights, and a product tier cannot
 * gate a right.
 */
const CAPABILITY_FREE_PREFIXES = ["/settings", "/privacy", "/terms"];

/** Research surfaces. These need the Workspace capability to render anything. */
const RESEARCH_PREFIXES = ["/monitors", "/skills", "/agents", "/explorer", "/research"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { token, ready } = useAuth();
  const { status, hasWorkspace, error, refresh } = useCapabilities();

  // Nothing at all until the session has been read out of storage. Painting a sign-in form for
  // the half-second before that resolves is how a signed-in user gets told, briefly, that they
  // are signed out -- on every single page load. Also the reason no private fetch can start
  // before this point: the scaffold has no private children to mount yet.
  if (!ready) return null;

  if (!token) {
    // Public routes render OUTSIDE the private chrome -- no rail, no strip, no launcher -- so a
    // signed-out visitor sees a page rather than an empty application frame.
    if (PUBLIC_PATHS.has(pathname)) return <>{children}</>;
    // Signed-out `/` is this app's own marketing with the sign-in beside it. `app/page.tsx` --
    // where the summary and performance reads live -- never mounts, so there is no Dashboard
    // fetch to cancel.
    if (pathname === "/") return <Landing />;
    // A private deep link signed out gets the form on its own: the visitor was trying to reach
    // something specific, and a marketing page would be an odd answer to that.
    return <SignIn />;
  }

  const isResearch = RESEARCH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/")
  );
  const capabilityFree = CAPABILITY_FREE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/")
  );

  // A research route, with the capability answer not yet known, renders nothing rather than
  // guessing. `unknown`/`loading` is not `denied`, and no research request is issued from here
  // in either state -- a denied account must make no private data call at all.
  if (isResearch && !capabilityFree) {
    if (status === "loading" || status === "unknown") return null;
    if (status === "error") {
      return (
        <div className="ws-centred">
          <div className="ws-centred-card">
            <h1 className="ws-h1">Could not check this account&rsquo;s access</h1>
            <p className="ws-sub" style={{ marginBottom: 16 }}>
              {error ?? "The server did not answer."} This is not a refusal &mdash; the
              question could not be asked.
            </p>
            <button type="button" className="ws-btn ws-btn--primary" onClick={refresh}>
              Try again
            </button>
          </div>
        </div>
      );
    }
    if (!hasWorkspace) return <NoWorkspaceAccess />;
  }

  return (
    <WorkspaceProvider>
      <ShellFrame>{children}</ShellFrame>
    </WorkspaceProvider>
  );
}

/**
 * The grid itself. Split from `Shell` so it can read the navigation context that `Shell` mounts
 * -- a provider cannot consume itself.
 */
function ShellFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { onResearch, researchChatOpen, researchChatFits } = useWorkspaceNav();
  const portfolio = isPortfolioPath(pathname);

  /*
    THE THIRD COLUMN EXISTS ONLY WHEN SOMEONE ASKED FOR IT. An always-present 340px track
    sitting empty reads as a panel that failed to load, and costs every portfolio screen 340px
    of table width for nothing. This is the "no empty chat track" rule, expressed as the one
    attribute the grid switches on.

    Three conditions, and each rules out a specific wrong state:
      `onResearch`        -- never beside a portfolio screen. Activating Portfolio also CLOSES
                             it (see the nav context), so this is belt and braces.
      `researchChatOpen`  -- an explicit act, closed by default. Navigation never opens it.
      `researchChatFits`  -- below 1240px there is no room, so the column is not RENDERED at
                             all rather than hidden with CSS: a hidden panel keeps its close
                             button and its composer in the tab order, and keyboard focus
                             would vanish into something nobody can see.
  */
  const researchOpen = onResearch && researchChatOpen && researchChatFits;

  return (
    <div className="ws-shell" data-research={researchOpen ? "open" : "closed"}>
      <Rail />
      <div className="ws-centre">
        <CentreStrip portfolio={portfolio} />
        {/*
          ONE ACTIVE VIEW. `children` is whatever Next has committed for the current route and
          nothing else: no cached previous page kept mounted behind it, no preserved scroll
          container per tab. A closed tab's page is unmounted by the route change, which is what
          keeps one investor's screen from being restorable after a switch.
        */}
        <main className="ws-centre-body">
          <div className="ws-wrap">{children}</div>
        </main>
      </div>
      {researchOpen && <ResearchColumn />}
      {/*
        THE SUPPORT ASSISTANT, mounted once for the whole app.

        The same drawer Plus mounts, from the shared package, so the "Ask AI about this" entry
        point on a structured financial error works on a Workspace portfolio screen exactly as
        it does on a Plus one. It renders nothing until opened, and it is portalled, so it takes
        no grid track and is unaffected by the research column beside it.

        NOT BUTLER. Different endpoint, different context, different rules -- and it must never
        be repointed at research, nor research at it.
      */}
      <AIChatDrawer />
    </div>
  );
}
