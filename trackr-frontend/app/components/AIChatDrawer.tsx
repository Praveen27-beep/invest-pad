/**
 * Compatibility re-export -- the SUPPORT assistant drawer now lives in
 * `packages/trackr-portfolio/src/widgets/`.
 *
 * Shared because both portfolio surfaces keep it: a structured financial error on a shared
 * screen offers "Ask AI about this", and that entry point has to work wherever the screen is
 * rendered. It is NOT Butler. Research chat is a separate Workspace-only surface with its own
 * transport and its own validated-card presentation, and this drawer must never be wired to
 * it (`docs/BUTLER_ARCHITECTURE.md`; BE-Q02 still gates retiring this one).
 */
export { AIChatDrawer } from "@trackr/portfolio";
