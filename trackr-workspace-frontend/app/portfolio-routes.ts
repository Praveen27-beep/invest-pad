/**
 * Which shared portfolio destinations Trackr Workspace serves TODAY.
 *
 * WHY THIS EXISTS. `@trackr/portfolio` defines the complete portfolio surface, and the
 * product contract requires Workspace to reach all of it. That is the target; this is
 * the honest record of how far the extraction has actually got.
 *
 * Dashboard, Holdings, holding detail and Analytics are now the SHARED screens, rendered
 * here inside Workspace chrome. `/contribution`, `/transactions`, `/import` and
 * `/reconcile` are still Plus-only route bodies and are deliberately absent below, so no
 * Workspace launcher or tab offers a link to a screen this app does not serve yet.
 * `/holdings/[isin]` is a route, not a destination, so it is not listed: nothing links to
 * it except a holdings row.
 *
 * The rule this set enforces: **Workspace never renders a link to a route it does not
 * serve.** A tab that 404s is worse than a tab that says where the screen is. When a
 * later session adds a route, it adds the href here in the same change, and the launcher
 * and centre strip pick it up with no other edit.
 *
 * This is presentation bookkeeping, not authorization. It says what is BUILT, never what
 * a user is allowed to see -- that is the server's decision, made per request.
 */

/** Portfolio hrefs with a working Workspace route. Keep in step with `app/`. */
export const WORKSPACE_PORTFOLIO_ROUTES: ReadonlySet<string> = new Set([
  "/",
  "/analytics",
  "/holdings",
  "/settings",
  "/privacy",
  "/terms",
]);

export function isBuiltInWorkspace(href: string): boolean {
  return WORKSPACE_PORTFOLIO_ROUTES.has(href);
}
