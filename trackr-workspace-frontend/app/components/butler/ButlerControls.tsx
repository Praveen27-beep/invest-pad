"use client";

/**
 * Butler's explicit controls on research documents: follow a company, remember a saved note,
 * start a decision review, and the small inbox entry beside the gear.
 *
 * EXPLICIT OR NOT AT ALL. Opening a company, saving a note or holding a stock never follows or
 * remembers anything; each of these is a button the person presses, and each shows the saved
 * server state rather than an optimistic guess. The 30-day checkpoint is OFFERED as an unticked
 * option -- it is never switched on for anyone.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useFetch } from "@trackr/core";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import { useWorkspaceNav } from "@/lib/workspace-context";
import {
  butlerPaths,
  butlerWrite,
  type DecisionKind,
  type InboxPage,
  type Memory,
  type Page,
  type Review,
  type Subscription,
} from "@/lib/butler-client";
import { Icon } from "../Icon";

// ------------------------------------------------------------------------------------
// Follow a company
// ------------------------------------------------------------------------------------

export function FollowControl({ isin }: { isin: string }) {
  const { investorId, token } = useResearchAuth();
  const { openResearchChat, researchChatFits } = useWorkspaceNav();
  const subs = useFetch<Page<Subscription>>(investorId ? butlerPaths.subscriptions(investorId) : null, undefined, token);
  const [checkpoint, setCheckpoint] = useState(false);
  const [kind, setKind] = useState<DecisionKind>("RESEARCH_CHECKPOINT");
  const act = useSubmit<Subscription | Review>();

  if (subs.errorDetail && (subs.errorDetail as { code?: string }).code === "BUTLER_UNAVAILABLE") return null;
  const sub = subs.data?.items.find(
    (s) => s.subject_kind === "COMPANY" && (s.isin === isin || s.identity?.canonical_isin === isin)
  );

  async function follow() {
    if (!investorId) return;
    const days = checkpoint && sub === undefined ? 30 : null;
    const result = await act.submit({ follow: isin, days }, (key) =>
      butlerWrite.followCompany({ investorId, token, idempotencyKey: key }, isin, days)
    );
    if (result) subs.refetch();
  }

  async function change(action: "PAUSE" | "RESUME" | "UNFOLLOW") {
    if (!investorId || !sub) return;
    const body = { action, expected_version: sub.version };
    const result = await act.submit({ sub: sub.id, ...body }, (key) =>
      butlerWrite.subscriptionEvent({ investorId, token, idempotencyKey: key }, sub.id, body)
    );
    if (result) subs.refetch();
  }

  async function startReview() {
    if (!investorId) return;
    const body = { isin, decision_kind: kind };
    const result = await act.submit(body, (key) =>
      butlerWrite.startReview({ investorId, token, idempotencyKey: key }, body)
    );
    // The review opens in the Butler column's Reviews tab; nothing here navigates away.
    if (result && researchChatFits) openResearchChat();
  }

  return (
    <div className="ws-butler-follow" aria-label="Butler">
      {subs.loading ? (
        <span className="ws-muted">Butler&hellip;</span>
      ) : sub ? (
        <>
          <span className="ws-chip ws-chip--ink">
            {sub.state === "PAUSED" ? "Following (paused)" : "Following in Butler"}
          </span>
          <span className="ws-muted">
            {sub.checkpoint.state === "SCHEDULED" && sub.checkpoint.next_due_on
              ? `Next checkpoint ${sub.checkpoint.next_due_on}`
              : sub.checkpoint.state === "TIMEZONE_REQUIRED"
                ? "Checkpoint needs your timezone (Butler inbox)"
                : "No checkpoint set"}
          </span>
          {sub.state === "PAUSED" ? (
            <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending} onClick={() => change("RESUME")}>Resume</button>
          ) : (
            <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending} onClick={() => change("PAUSE")}>Pause</button>
          )}
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending} onClick={() => change("UNFOLLOW")}>Unfollow</button>
        </>
      ) : (
        <>
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending || !subs.data} onClick={follow}>
            Follow in Butler
          </button>
          <label className="ws-check">
            <input type="checkbox" checked={checkpoint} onChange={(e) => setCheckpoint(e.target.checked)} />
            Add a 30-day research checkpoint
          </label>
        </>
      )}
      <span className="ws-butler-follow-sep" aria-hidden="true" />
      <select aria-label="Review type" value={kind} onChange={(e) => setKind(e.target.value as DecisionKind)}>
        <option value="RESEARCH_CHECKPOINT">Research checkpoint</option>
        <option value="THESIS_CHANGE">Thesis change</option>
        <option value="POSITION_DECISION">Position decision</option>
      </select>
      <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending} onClick={startReview}>
        Start review
      </button>
      {act.error && <div className="ws-notice ws-notice--error">{describeError(act.error)}</div>}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Remember a saved note version
// ------------------------------------------------------------------------------------

export function RememberControl({ noteId, isin }: { noteId: string; isin: string }) {
  const { investorId, token } = useResearchAuth();
  const list = useFetch<Page<Memory>>(investorId ? butlerPaths.memories(investorId) : null, { isin }, token);
  const act = useSubmit<Memory>();
  if (list.errorDetail && (list.errorDetail as { code?: string }).code === "BUTLER_UNAVAILABLE") return null;
  const memory = list.data?.items.find((m) => m.ref_kind === "NOTE" && m.ref_id === noteId && m.status === "ACTIVE");

  async function remember() {
    if (!investorId) return;
    const result = await act.submit({ remember: noteId }, (key) =>
      butlerWrite.remember({ investorId, token, idempotencyKey: key }, "NOTE", noteId)
    );
    if (result) list.refetch();
  }
  async function forget() {
    if (!investorId || !memory) return;
    const result = await act.submit({ forget: memory.id }, (key) =>
      butlerWrite.forget({ investorId, token, idempotencyKey: key }, memory.id)
    );
    if (result) list.refetch();
  }

  return (
    <div className="ws-butler-follow">
      {memory ? (
        <>
          <span className="ws-chip ws-chip--ink">Remembered in Butler (this exact version)</span>
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending} onClick={forget}>
            Forget in Butler
          </button>
        </>
      ) : (
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={act.pending || !list.data} onClick={remember}>
          Remember in Butler
        </button>
      )}
      <span className="ws-muted">Forgetting never deletes the note.</span>
      {act.error && <div className="ws-notice ws-notice--error">{describeError(act.error)}</div>}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// The inbox entry beside the gear
// ------------------------------------------------------------------------------------

/**
 * One read when the rail mounts or the investor changes, plus an explicit refresh on click.
 * NOT a poll: the browser is never Butler's scheduler, and a closed tab misses nothing because
 * the worker keeps building the inbox server-side.
 */
export function ButlerInboxEntry() {
  const { investorId, token } = useResearchAuth();
  const { onResearch, openResearchChat, researchChatFits } = useWorkspaceNav();
  const router = useRouter();
  const inbox = useFetch<InboxPage>(investorId ? butlerPaths.inbox(investorId) : null, { limit: 20 }, token);
  const [pendingOpen, setPendingOpen] = useState(false);

  useEffect(() => {
    if (pendingOpen && onResearch) {
      openResearchChat();
      setPendingOpen(false);
    }
  }, [pendingOpen, onResearch, openResearchChat]);

  if (inbox.errorDetail && (inbox.errorDetail as { code?: string }).code === "BUTLER_UNAVAILABLE") return null;
  const count = inbox.data?.new_count ?? 0;

  function open() {
    inbox.refetch();
    if (!researchChatFits) return;
    if (onResearch) openResearchChat();
    else {
      setPendingOpen(true);
      router.push("/explorer");
    }
  }

  return (
    <button
      type="button"
      className="ws-gear"
      onClick={open}
      disabled={!researchChatFits}
      title={researchChatFits ? "Open the Butler inbox" : "The Butler column needs a window wider than 1240px"}
      aria-label={count ? `Butler inbox, ${count} new` : "Butler inbox"}
    >
      <Icon name="chat" size={13} />
      <span className="ws-gear-text">Butler{count ? ` · ${count} new` : ""}</span>
    </button>
  );
}
