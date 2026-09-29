"use client";

/**
 * The third column: Butler (BT 07).
 *
 * THE DEMO GEOMETRY, UNCHANGED -- 340px beside the rail and the centre, a 38px header, a
 * scrollable log, a two-row composer, an explicit close. Closed by default; opened only by the
 * research strip's toggle or the Butler inbox entry by the gear. Switching to Portfolio closes
 * it (the nav context), and coming back restores the research documents without posting
 * anything.
 *
 * WHAT THE LOG SHOWS NOW. Server-VALIDATED items only: deterministic template cards with
 * their citations and coverage, the investor's explicit memory references, and decision reviews
 * holding their own answers. Everything is rendered as text from what the server returned
 * (`butler/CardView.tsx`); there is no message-bubble component that could print a completion.
 *
 * WHAT IT STILL DOES NOT DO. Butler's model (BT 08) is a SELECTOR over checked items, run from
 * the Ask tab on an explicit click -- free text typed here is never sent to a model, so the
 * composer stays DISABLED with the reason stated. No simulated answers, no samples, no
 * placeholder citations, no streamed prose.
 *
 * NOT THE SUPPORT ASSISTANT. Plus's support drawer is a different surface with a different
 * endpoint and different context; it keeps working on the portfolio surface in both products
 * and is never wired to research context or used as a Butler fallback (BE-Q02).
 */

import { useWorkspaceNav } from "@/lib/workspace-context";
import { ButlerPanel } from "./butler/ButlerPanel";

export function ResearchColumn() {
  const { closeResearchChat } = useWorkspaceNav();

  return (
    <aside className="ws-research-column" aria-label="Butler">
      {/* 38px header, matching the document strip's height so the three columns line up. */}
      <div className="ws-research-head">
        <span className="ws-research-title">Butler</span>
        <button
          type="button"
          className="ws-research-close"
          onClick={closeResearchChat}
          aria-label="Close research chat"
          title="Close research chat"
        >
          &times;
        </button>
      </div>

      {/* Not a live region: it holds forms. The worker status line inside is role="status". */}
      <div className="ws-research-log">
        <ButlerPanel />
      </div>

      {/*
        THE COMPOSER IS PRESENT AND DISABLED, not absent.

        Absent would hide the shape of the feature; enabled would accept input it then threw
        away, which is the worse of the two by a distance. Disabled with the reason stated is
        the honest third option. `form` with an explicit submit rather than Enter-to-send: a
        research question is not a chat line, and the submit has to be a deliberate act.
      */}
      <form
        className="ws-research-composer"
        onSubmit={(event) => {
          // Cannot fire while the control is disabled; kept so that enabling it later is one
          // change in one place rather than a new handler that forgets this guard.
          event.preventDefault();
        }}
      >
        <textarea
          rows={2}
          disabled
          className="ws-research-input"
          placeholder="Free text is not sent to a model. Use the Ask tab: your model may only choose checked items"
          aria-label="Ask Butler"
        />
        <button type="submit" className="ws-btn ws-btn--primary" disabled>
          Ask
        </button>
      </form>
    </aside>
  );
}
