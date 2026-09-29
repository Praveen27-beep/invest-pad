"use client";

/**
 * Workspace's navigation state: which research documents are open, which is active, and where
 * the Portfolio surface should return to.
 *
 * WORKSPACE ONLY. This provider lives in this application and is not exported from any shared
 * package. Plus has sibling tabs in its ribbon and must keep them exactly as they are; it has no
 * research documents, no document strip and nothing to put in one. A shared provider would put
 * the concept of a research tab inside Plus's bundle, which the product contract forbids, and
 * Plus must keep working with no `WorkspaceProvider` anywhere in its tree.
 *
 * ── THE ONE RULE THAT MAKES HISTORY WORK ────────────────────────────────────────────────────
 *
 * **The committed URL decides the active surface. This store never fights it.**
 *
 * There is deliberately no `activeSurface` flag. `usePathname` is the single source of truth for
 * "am I on portfolio or research", which is what makes Back, Forward, a refresh and a pasted
 * deep link all land correctly with nothing to fall out of step. A second flag would need
 * reconciling with the address bar on every transition, and the reconciliation is where the bugs
 * live.
 *
 * **The route observer records; it never pushes.** It watches the committed URL and updates the
 * remembered portfolio href and the open-document set. If it also pushed, Back would restore a
 * URL, the observer would push a correction, and Forward/Back would bounce -- a loop that is
 * miserable to debug because every individual step looks right.
 *
 * ── WHAT IS KEYED TO IDENTITY, AND WHAT IS NOT ──────────────────────────────────────────────
 *
 * Keyed by user id + investor id. Not pathname, not the date, not the theme, and NOT the token:
 * a token refresh is the same person in the same session, and clearing their open tabs every
 * hour because a JWT rotated would be indefensible. Switching either the user or the investor
 * makes every remembered URL and document belong to someone else's context, so all of it is
 * dropped.
 *
 * ── IN MEMORY, AND THIS IS NOT A DRAFT CACHE ────────────────────────────────────────────────
 *
 * Nothing here is persisted. `localStorage` would leave one investor's research titles readable
 * on a shared machine after sign-out, and a tab label is the name of a company someone is
 * studying. The store holds descriptors -- kind, ref, label, href -- and never page content,
 * scroll position or form input. Closing a tab discards navigation metadata; it never deletes a
 * server-saved note or a staged import, and unsaved input follows the existing rule (owner
 * answer Q05): it is discarded on navigation, exactly as today. Remembering where someone was
 * is not the same as remembering what they had typed, and conflating the two is how a "helpful"
 * draft store gets built by accident.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  descriptorId,
  isPortfolioPath,
  resolveRoute,
  type ResearchDescriptor,
  type ResearchKind,
} from "@trackr/portfolio";
import { useAuth } from "@trackr/core";
import { RESEARCH_SCREENS, researchScreen } from "../app/components/nav";

/** An open research document. `href` is null for a reserved kind with no route yet. */
export interface OpenDocument {
  id: string;
  kind: ResearchKind;
  ref: string | null;
  label: string;
  href: string | null;
}

interface WorkspaceNav {
  /** Open documents, in the order they were opened. */
  documents: OpenDocument[];
  /** The active document's id, or null when the portfolio surface is committed. */
  activeId: string | null;
  /** Where the rail's Portfolio entry goes. Always a portfolio route, with its query. */
  lastPortfolioUrl: string;
  /** True when the committed URL is a research route. Derived, never stored. */
  onResearch: boolean;
  /** Open or focus a document and navigate to it. A reserved kind with no href is ignored. */
  openDocument: (descriptor: ResearchDescriptor) => void;
  /** Close one. Selects right, then left, then the remembered Portfolio route. */
  closeDocument: (id: string) => void;
  /** Switch to the Portfolio surface at the remembered URL. */
  goToPortfolio: () => void;
  /** The launcher's navigation callback: push a portfolio route and select that surface. */
  navigate: (href: string) => void;
  /**
   * Set an open document's label from its AUTHORISED record (a company name, a note title).
   * Called by the document page after a successful load; never from anything else, so a
   * denied, foreign or deleted record cannot label a tab.
   */
  labelDocument: (id: string, label: string) => void;

  /**
   * Is the research chat column open?
   *
   * CLOSED BY DEFAULT, and opened only by an explicit action. Never by navigating to a
   * research route, never by opening a document, never by widening the window. A panel that
   * appeared on its own would take 340px from whatever you were reading and would imply
   * something was waiting there.
   */
  researchChatOpen: boolean;
  /**
   * Is the viewport wide enough for a third column at all?
   *
   * Below 1240px the shell is two columns (see `globals.css`), so the answer is no and the
   * column is DROPPED rather than shrunk. Exposed as state rather than left to CSS because the
   * action that opens it has to be able to say WHY it is unavailable instead of doing nothing
   * when clicked.
   */
  researchChatFits: boolean;
  openResearchChat: () => void;
  closeResearchChat: () => void;
}

const EMPTY: WorkspaceNav = {
  documents: [],
  activeId: null,
  lastPortfolioUrl: "/",
  onResearch: false,
  openDocument: () => {},
  closeDocument: () => {},
  goToPortfolio: () => {},
  navigate: () => {},
  labelDocument: () => {},
  researchChatOpen: false,
  researchChatFits: false,
  openResearchChat: () => {},
  closeResearchChat: () => {},
};

const WorkspaceContext = createContext<WorkspaceNav>(EMPTY);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, investorId } = useAuth();

  const [documents, setDocuments] = useState<OpenDocument[]>([]);
  const [researchChatOpen, setResearchChatOpen] = useState(false);
  /**
   * Starts FALSE and is corrected after mount.
   *
   * There is no viewport on the server, and guessing "wide" would render the column into the
   * first paint and then remove it -- a 340px layout shift on every load for anyone on a
   * laptop. Guessing "narrow" costs nothing: the column is closed by default anyway.
   */
  const [researchChatFits, setResearchChatFits] = useState(false);
  const [lastPortfolioUrl, setLastPortfolioUrl] = useState("/");

  const identity = `${user?.id ?? ""}:${investorId}`;
  const knownIdentity = useRef(identity);

  const search = searchParams.toString();
  const resolved = resolveRoute(pathname, search ? `?${search}` : "");
  const onResearch = resolved.surface === "research";

  /**
   * THE OBSERVER. Records what the committed URL means, and pushes nothing.
   *
   * Identity change is handled first and returns early, so a sign-out or investor switch clears
   * everything in the same pass rather than clearing and then immediately re-recording the URL
   * that is still on screen.
   */
  useEffect(() => {
    if (knownIdentity.current !== identity) {
      knownIdentity.current = identity;
      setDocuments([]);
      setLastPortfolioUrl("/");
      // A sign-out or investor switch closes the research column too. Private UI state must
      // not survive an identity change (`docs/PRODUCT_ARCHITECTURE.md` acceptance item 6):
      // the next account must not be able to see the previous one's conversation.
      setResearchChatOpen(false);
      return;
    }

    if (isPortfolioPath(pathname)) {
      // The COMPLETE query, so returning to Portfolio restores the filtered Transactions view
      // the user actually left rather than an unfiltered one.
      setLastPortfolioUrl(search ? `${pathname}?${search}` : pathname);
      return;
    }

    // A research URL reached directly -- pasted, refreshed, or Back into one -- opens its tab, so
    // a deep link establishes the same state as a click.
    //
    // A company or note DOCUMENT opens with its bare ref (ISIN / saved id) as the label. The
    // readable label arrives only from the authorised record the page loads (`labelDocument`),
    // so a denied or deleted record never puts a title from somewhere else into the strip.
    if ((resolved.kind === "company" || resolved.kind === "note") && resolved.ref && resolved.id) {
      const docId = resolved.id;
      const kind = resolved.kind;
      const ref = resolved.ref;
      setDocuments((current) =>
        current.some((doc) => doc.id === docId)
          ? current
          : [...current, { id: docId, kind, ref, label: ref, href: resolved.href }]
      );
      return;
    }
    if (resolved.kind) {
      const screen = researchScreen(resolved.kind);
      if (!screen) return;
      setDocuments((current) =>
        current.some((doc) => doc.id === resolved.id)
          ? current
          : [
              ...current,
              {
                id: descriptorId(screen.kind, null),
                kind: screen.kind,
                ref: null,
                label: screen.label,
                href: screen.href,
              },
            ]
      );
    }
  }, [pathname, search, identity, resolved.id, resolved.kind, resolved.ref, resolved.href]);

  /**
   * The active document is DERIVED from the URL, not stored.
   *
   * On a portfolio route this is null even while documents stay open -- switching to Portfolio
   * retains their metadata, so coming back finds the same strip. That is the whole reason
   * `documents` and `activeId` are separate concerns.
   */
  const activeId = onResearch ? resolved.id : null;

  const openDocument = useCallback(
    (descriptor: ResearchDescriptor) => {
      // A RESERVED KIND HAS NO HREF AND DOES NOT OPEN. Company and note descriptors are
      // routable since FE 15; a future reserved kind stays unopenable, because a tab that
      // cannot navigate would be a tab that shows nothing.
      if (!descriptor.href) return;
      const id = descriptorId(descriptor.kind, descriptor.ref);
      setDocuments((current) =>
        // DEDUPLICATED BY kind + ref. Two clicks on the same company focus one tab; a company
        // document and a holding detail page for the same ISIN stay distinct, because a holding
        // is a portfolio page and never becomes a research document at all.
        current.some((doc) => doc.id === id)
          ? current
          : [...current, { id, kind: descriptor.kind, ref: descriptor.ref, label: descriptor.label, href: descriptor.href }]
      );
      router.push(descriptor.href);
    },
    [router]
  );

  const closeDocument = useCallback(
    (id: string) => {
      setDocuments((current) => {
        const index = current.findIndex((doc) => doc.id === id);
        if (index === -1) return current;
        const next = current.filter((doc) => doc.id !== id);

        // CLOSING AN INACTIVE TAB CHANGES NO URL. Tidying the strip is not navigation, and
        // moving someone off the page they are reading because they closed a different tab is
        // the most irritating possible interpretation of a close button.
        if (id !== activeId) return next;

        // The active one closed: select the tab to the RIGHT, then the left if there is none --
        // the order every editor uses, and the one that keeps a rapid sequence of closes moving
        // in one direction instead of ping-ponging.
        const successor = next[index] ?? next[index - 1];
        // Last document closed: back to the remembered Portfolio route, never to a blank centre
        // and never to an invented empty note.
        router.push(successor?.href ?? lastPortfolioUrl);
        return next;
      });
    },
    [activeId, lastPortfolioUrl, router]
  );

  const goToPortfolio = useCallback(() => {
    router.push(lastPortfolioUrl);
  }, [router, lastPortfolioUrl]);

  /**
   * The launcher's callback. One of these, at the shell level, per FE 04 -- a menu reports the
   * choice and does not own tab state.
   *
   * A portfolio href pushes and thereby selects the portfolio surface, because the observer will
   * see a portfolio path. Anything else is pushed as-is and the observer works it out. There is
   * no branch here that sets a surface flag, because there is no surface flag.
   */
  const navigate = useCallback(
    (href: string) => {
      router.push(href);
    },
    [router]
  );

  const labelDocument = useCallback((id: string, label: string) => {
    setDocuments((current) =>
      current.map((doc) => (doc.id === id && doc.label !== label ? { ...doc, label } : doc))
    );
  }, []);

  /**
   * PORTFOLIO ACTIVATION CLOSES THE RESEARCH COLUMN.
   *
   * Switching to Portfolio is switching subject, and a research conversation hanging beside a
   * holdings table is both a distraction and 340px the table needs. Closing rather than hiding,
   * so coming back to research does not silently reopen it -- reopening is an explicit act every
   * time. The portfolio surface's own SUPPORT drawer is unaffected and keeps its normal behaviour:
   * it is a different thing, about this screen's errors rather than about a company.
   */
  useEffect(() => {
    if (!onResearch) setResearchChatOpen(false);
  }, [onResearch]);

  /**
   * Whether a third column fits, kept in step with the shell's own breakpoint.
   *
   * WIDENING THE WINDOW NEVER OPENS IT. This only records whether the column COULD be shown;
   * `researchChatOpen` is untouched here, so dragging a window wider cannot make a panel appear
   * and cannot submit anything.
   */
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1241px)");
    const sync = () => setResearchChatFits(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  const openResearchChat = useCallback(() => setResearchChatOpen(true), []);
  const closeResearchChat = useCallback(() => setResearchChatOpen(false), []);

  const value = useMemo<WorkspaceNav>(
    () => ({
      documents,
      activeId,
      lastPortfolioUrl,
      onResearch,
      openDocument,
      closeDocument,
      goToPortfolio,
      navigate,
      labelDocument,
      researchChatOpen,
      researchChatFits,
      openResearchChat,
      closeResearchChat,
    }),
    [
      documents,
      activeId,
      lastPortfolioUrl,
      onResearch,
      openDocument,
      closeDocument,
      goToPortfolio,
      navigate,
      labelDocument,
      researchChatOpen,
      researchChatFits,
      openResearchChat,
      closeResearchChat,
    ]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaceNav(): WorkspaceNav {
  return useContext(WorkspaceContext);
}

/**
 * Descriptors for the research screens that exist today, for the strip's initial state and for
 * the rail.
 *
 * Company and note documents are absent by construction: they are opened per record (ISIN /
 * saved note id), not listed as fixed screens.
 */
export function screenDescriptors(): ResearchDescriptor[] {
  return RESEARCH_SCREENS.map((screen) => ({
    kind: screen.kind,
    ref: null,
    label: screen.label,
    href: screen.href,
  }));
}
