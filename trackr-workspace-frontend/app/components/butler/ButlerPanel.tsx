"use client";

/**
 * Butler's column content: Inbox, Memory and Reviews.
 *
 * DETERMINISTIC ONLY, AND SAYS SO. At this phase no model is connected (BT 08 onward). Every card
 * is a server-validated template; reviews record the person's own answers; the worker status line
 * states when the inbox was last built and that nothing ran a model. There is no simulated answer
 * anywhere to make the column look busier than it is.
 *
 * HONEST STATES. Loading, empty, server-refused and "not installed" are distinct messages. A
 * pending action disables its buttons; only a confirmed server response changes what is shown.
 *
 * LATE RESPONSES ARE DROPPED. Every write remembers which investor it was made for; if the
 * signed-in user or investor has changed by the time it returns, the result is discarded rather
 * than painted into someone else's column.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useFetch } from "@trackr/core";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";
import {
  ATTRIBUTION_LABELS,
  butlerPaths,
  butlerWrite,
  type Card,
  type InboxPage,
  type Memory,
  type Page,
  type Preference,
  type Review,
  type ReviewSummary,
} from "@/lib/butler-client";
import { CardView } from "./CardView";
import { ButlerSettings, ModelReview } from "./ModelReview";
import { ReviewView } from "./ReviewView";

type Tab = "inbox" | "memory" | "reviews" | "ask" | "settings";

/** Guards a write's result against an investor switch while it was in flight. */
function useScopeGuard(investorId: string | null) {
  const current = useRef(investorId);
  useEffect(() => {
    current.current = investorId;
  }, [investorId]);
  return useCallback((startedFor: string | null) => startedFor === current.current, []);
}

export function ButlerPanel() {
  const [tab, setTab] = useState<Tab>("inbox");
  const [openReview, setOpenReview] = useState<string | null>(null);
  const { investorId } = useResearchAuth();

  // An investor switch closes an open review: it belongs to the previous investor.
  useEffect(() => setOpenReview(null), [investorId]);

  return (
    <div className="ws-butler">
      <div className="ws-modes ws-butler-tabs" role="tablist" aria-label="Butler views">
        {(
          [
            ["inbox", "Inbox"],
            ["memory", "Memory"],
            ["reviews", "Reviews"],
            ["ask", "Ask"],
            ["settings", "Settings"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            className="ws-mode"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key);
              if (key !== "reviews") setOpenReview(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "inbox" && (
        <InboxView
          onReviewStarted={(id) => {
            setOpenReview(id);
            setTab("reviews");
          }}
        />
      )}
      {tab === "memory" && <MemoryView />}
      {tab === "reviews" &&
        (openReview ? (
          <ReviewView reviewId={openReview} onBack={() => setOpenReview(null)} />
        ) : (
          <ReviewList onOpen={setOpenReview} />
        ))}
      {tab === "ask" && <ModelReview />}
      {tab === "settings" && <ButlerSettings />}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Inbox
// ------------------------------------------------------------------------------------

function unavailable(error: { status?: number; code?: string } | null | undefined): string | null {
  if (!error) return null;
  if (error.code === "BUTLER_UNAVAILABLE") return "Butler is not installed on this server yet.";
  return null;
}

function InboxView({ onReviewStarted }: { onReviewStarted: (reviewId: string) => void }) {
  const { investorId, token } = useResearchAuth();
  const [view, setView] = useState<"current" | "all">("current");
  const inbox = useFetch<InboxPage>(
    investorId ? butlerPaths.inbox(investorId) : null,
    { view },
    token
  );
  const act = useSubmit<unknown>();
  const inScope = useScopeGuard(investorId);

  async function event(card: Card, action: "SEEN" | "SNOOZE" | "DISMISS" | "RESOLVE" | "RESTORE", days?: number) {
    if (!investorId) return;
    const startedFor = investorId;
    const snooze = days ? new Date(Date.now() + days * 86_400_000).toISOString() : null;
    const body = { action, expected_version: card.status.version, snooze_until: snooze };
    const result = await act.submit({ card: card.id, ...body, snooze_until: days ?? null }, (key) =>
      butlerWrite.inboxEvent({ investorId, token, idempotencyKey: key }, card.id, body)
    );
    if (result && inScope(startedFor)) inbox.refetch();
  }

  async function startReview(card: Card) {
    if (!investorId) return;
    const startedFor = investorId;
    const body = { isin: card.isin, decision_kind: "RESEARCH_CHECKPOINT" as const, trigger_item_id: card.id };
    const review = (await act.submit(body, (key) =>
      butlerWrite.startReview({ investorId, token, idempotencyKey: key }, body)
    )) as Review | null;
    if (review && inScope(startedFor)) onReviewStarted(review.id);
  }

  if (inbox.loading) return <div className="ws-empty">Loading&hellip;</div>;
  if (inbox.error || !inbox.data) {
    return (
      <div className="ws-notice ws-notice--error">
        {unavailable(inbox.errorDetail) ?? describeError(inbox.errorDetail) ?? inbox.error}
      </div>
    );
  }
  const data = inbox.data;
  const w = data.worker;
  return (
    <div>
      {data.preference.state === "NOT_SET" && (
        <PreferenceForm preference={data.preference} onSaved={inbox.refetch} />
      )}
      <p className="ws-muted ws-butler-status" role="status">
        {w.last_success_at
          ? `Inbox last built ${new Date(w.last_success_at).toLocaleString()}.`
          : "The inbox has not been built yet."}
        {w.pending_events > 0 ? ` ${w.pending_events} saved change(s) still waiting.` : ""}{" "}
        In-app only. A model runs only when you click Review in the Ask tab.
      </p>
      <div className="ws-butler-toolbar">
        <button
          type="button"
          className="ws-btn ws-btn--ghost ws-btn--sm"
          aria-pressed={view === "all"}
          onClick={() => setView(view === "current" ? "all" : "current")}
        >
          {view === "current" ? "Show history" : "Show current"}
        </button>
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={inbox.refetch}>
          Refresh
        </button>
      </div>
      {act.error && <div className="ws-notice ws-notice--error">{describeError(act.error)}</div>}
      {data.items.length === 0 ? (
        <div className="ws-notice">
          {view === "current"
            ? "Nothing new. This is not an all-clear: only documents saved in this workspace are checked, and only for companies you follow."
            : "No Butler cards yet."}
        </div>
      ) : (
        data.items.map((card) => (
          <CardView
            key={card.id}
            card={card}
            actions={{
              pending: act.pending,
              onSeen: () => event(card, "SEEN"),
              onSnooze: (days) => event(card, "SNOOZE", days),
              onDismiss: () => event(card, "DISMISS"),
              onResolve: () => event(card, "RESOLVE"),
              onRestore: () => event(card, "RESTORE"),
              onStartReview: () => startReview(card),
            }}
          />
        ))
      )}
    </div>
  );
}

const ZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "UTC"];

function PreferenceForm({ preference, onSaved }: { preference: Preference; onSaved: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [timezone, setTimezone] = useState("");
  const save = useSubmit<Preference>();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!investorId || !timezone) return;
    const body = {
      timezone,
      quiet_start: preference.quiet_start,
      quiet_end: preference.quiet_end,
      digest_limit: preference.digest_limit,
      expected_version: preference.version,
    };
    const saved = await save.submit(body, (key) =>
      butlerWrite.setPreferences({ investorId, token, idempotencyKey: key }, body)
    );
    if (saved) onSaved();
  }
  return (
    <form className="ws-notice ws-butler-pref" onSubmit={submit}>
      <strong>Choose your timezone</strong>
      <p className="ws-muted">
        Butler does not guess it. It is needed before any review checkpoint is scheduled; quiet
        hours ({preference.quiet_start}&ndash;{preference.quiet_end}) and a daily limit of{" "}
        {preference.digest_limit} new cards then apply.
      </p>
      <label className="ws-field">
        <span>Timezone</span>
        <select value={timezone} onChange={(e) => setTimezone(e.target.value)} required>
          <option value="">Select&hellip;</option>
          {ZONES.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
      </label>
      {save.error && <div className="ws-notice ws-notice--error">{describeError(save.error)}</div>}
      <button type="submit" className="ws-btn ws-btn--primary ws-btn--sm" disabled={save.pending || !timezone}>
        {save.pending ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

// ------------------------------------------------------------------------------------
// Memory
// ------------------------------------------------------------------------------------

function MemoryView() {
  const { investorId, token } = useResearchAuth();
  const [ended, setEnded] = useState(false);
  const list = useFetch<Page<Memory>>(
    investorId ? butlerPaths.memories(investorId) : null,
    { include_ended: ended },
    token
  );
  const forget = useSubmit<Memory>();
  const inScope = useScopeGuard(investorId);

  async function doForget(memory: Memory) {
    if (!investorId) return;
    const startedFor = investorId;
    const result = await forget.submit({ forget: memory.id }, (key) =>
      butlerWrite.forget({ investorId, token, idempotencyKey: key }, memory.id)
    );
    if (result && inScope(startedFor)) list.refetch();
  }

  if (list.loading) return <div className="ws-empty">Loading&hellip;</div>;
  if (list.error || !list.data) {
    return <div className="ws-notice ws-notice--error">{unavailable(list.errorDetail) ?? describeError(list.errorDetail) ?? list.error}</div>;
  }
  return (
    <div>
      <p className="ws-muted ws-butler-status">
        Butler remembers only records you chose, exactly as saved. Forgetting removes a record
        from Butler; it does not delete your note.
      </p>
      <div className="ws-butler-toolbar">
        <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" aria-pressed={ended} onClick={() => setEnded(!ended)}>
          {ended ? "Hide forgotten" : "Show forgotten"}
        </button>
      </div>
      {forget.error && <div className="ws-notice ws-notice--error">{describeError(forget.error)}</div>}
      {list.data.items.length === 0 ? (
        <div className="ws-notice">Nothing remembered. Use &ldquo;Remember in Butler&rdquo; on a saved note.</div>
      ) : (
        <ul className="ws-butler-memories">
          {list.data.items.map((m) => (
            <li key={m.id} className="ws-butler-card">
              <header className="ws-butler-card-head">
                <span className="ws-chip ws-chip--mute">{ATTRIBUTION_LABELS[m.attribution] ?? m.attribution}</span>
                {m.status !== "ACTIVE" && <span className="ws-chip ws-chip--neg">{m.status.toLowerCase()}</span>}
                {m.record.is_latest_version === false && <span className="ws-chip ws-chip--warn">Older version</span>}
              </header>
              <strong>{m.record.title ?? "Record not available"}</strong>
              {m.record.preview && <blockquote className="ws-butler-passage">{m.record.preview}</blockquote>}
              <p className="ws-muted">
                {m.isin} &middot; remembered {m.recorded_at.slice(0, 10)}
              </p>
              {m.status === "ACTIVE" && (
                <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={forget.pending} onClick={() => doForget(m)}>
                  Forget in Butler
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------
// Reviews
// ------------------------------------------------------------------------------------

const STATUS_LABELS: Record<Review["status"], string> = {
  DRAFT: "Not started",
  AWAITING_INPUT: "In progress",
  DOCUMENTED: "Review documented",
  SUPERSEDED: "Superseded",
};

function ReviewList({ onOpen }: { onOpen: (id: string) => void }) {
  const { investorId, token } = useResearchAuth();
  const list = useFetch<ReviewSummary[]>(investorId ? butlerPaths.reviews(investorId) : null, undefined, token);
  if (list.loading) return <div className="ws-empty">Loading&hellip;</div>;
  if (list.error || !list.data) {
    return <div className="ws-notice ws-notice--error">{unavailable(list.errorDetail) ?? describeError(list.errorDetail) ?? list.error}</div>;
  }
  if (list.data.length === 0) {
    return (
      <div className="ws-notice">
        No reviews yet. Start one from a company page or from a due checkpoint. A review records
        your own answers; it never approves a decision.
      </div>
    );
  }
  return (
    <ul className="ws-butler-memories">
      {list.data.map((r) => (
        <li key={r.id} className="ws-butler-card">
          <header className="ws-butler-card-head">
            <span className="ws-chip ws-chip--mute">{r.identity?.symbol ?? r.isin}</span>
            <span className="ws-chip">{STATUS_LABELS[r.status]}</span>
            {r.stale && <span className="ws-chip ws-chip--warn">Changed since started</span>}
          </header>
          <p className="ws-muted">
            {r.decision_kind.replaceAll("_", " ").toLowerCase()} &middot; {r.recorded_at.slice(0, 10)}
            {r.unresolved.length ? ` · ${r.unresolved.length} unresolved` : ""}
          </p>
          <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" onClick={() => onOpen(r.id)}>
            Open
          </button>
        </li>
      ))}
    </ul>
  );
}
