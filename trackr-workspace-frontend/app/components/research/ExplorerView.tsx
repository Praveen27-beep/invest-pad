"use client";

/**
 * Explorer: the authenticated investor's real research companies and notes (FE 15).
 *
 * EVERYTHING HERE COMES FROM THE RESEARCH API. No company is derived from holdings, no note is
 * sampled, and no returned writing is composed client-side: Home's returns and open questions
 * are the server's deterministic feed (BE 10). A locked company shows its identity and the
 * fact that it is locked -- never a count, title or preview of what is behind the ritual.
 *
 * Adding a company links an EXISTING listed security by ISIN (BE 08). The search is over the
 * security master, not the portfolio.
 */

import Link from "next/link";
import { useState } from "react";
import { companyDescriptor, noteHref } from "@trackr/portfolio";
import { useFetch } from "@trackr/core";
import { useWorkspaceNav } from "@/lib/workspace-context";
import {
  paths,
  write,
  type CompanyListItem,
  type Home,
  type Identity,
  type Note,
  type Page,
} from "@/lib/research-api";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

const REASON_LABEL: Record<string, string> = {
  MONTH_6: "6 months ago",
  MONTH_12: "a year ago",
  MONTH_24: "two years ago",
  CONTRADICTION: "recorded contradiction",
};

export function ExplorerView() {
  const { investorId, token } = useResearchAuth();
  const [q, setQ] = useState("");
  const companies = useFetch<Page<CompanyListItem>>(
    investorId ? paths.companies(investorId) : null,
    { q: q.trim() || undefined },
    token
  );
  const home = useFetch<Home>(investorId ? paths.home(investorId) : null, undefined, token);

  return (
    <div>
      <div className="ws-crumb">Research &middot; Explorer</div>
      <h1 className="ws-h1">Companies &amp; notes</h1>
      <p className="ws-sub">
        Companies you have opened a research file on. A company unlocks once you have written
        down your own questions about it.
      </p>

      <HomeFeed home={home.data} error={home.error} loading={home.loading} />

      <div className="ws-sechead">
        <h2>Companies</h2>
        <div className="ws-hint">
          {companies.data ? `${companies.data.items.length} shown` : " "}
        </div>
      </div>
      <div className="ws-stack">
        <label className="ws-field" style={{ maxWidth: 360 }}>
          <span className="ws-field-label">Filter your companies</span>
          <input
            className="ws-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="ISIN, symbol or name"
            maxLength={64}
          />
        </label>
        <div className="ws-panel">
          {companies.loading && <div className="ws-empty">Loading&hellip;</div>}
          {companies.error && (
            <div className="ws-notice ws-notice--error">
              {describeError(companies.errorDetail) ?? companies.error}
            </div>
          )}
          {companies.data && companies.data.items.length === 0 && (
            <div className="ws-empty">
              {q.trim()
                ? "No company in your research matches that."
                : "No companies yet. Add one below to start a research file."}
            </div>
          )}
          {companies.data?.items.map((company) => (
            <CompanyRow key={company.isin} company={company} />
          ))}
        </div>
        <AddCompany onAdded={companies.refetch} />
      </div>
    </div>
  );
}

function HomeFeed({
  home,
  error,
  loading,
}: {
  home: Home | null;
  error: string | null;
  loading: boolean;
}) {
  if (loading) return null;
  if (error) return <div className="ws-notice ws-notice--warn">Home feed unavailable: {error}</div>;
  if (!home) return null;
  const open = home.open_questions.items;
  return (
    <>
      <div className="ws-sechead">
        <h2>Open questions</h2>
        <div className="ws-hint">as of {home.as_of}</div>
      </div>
      <div className="ws-panel">
        {open.length === 0 ? (
          <div className="ws-empty">No unanswered questions.</div>
        ) : (
          open.map((question) => (
            <Link
              key={question.id}
              className="ws-row"
              href={`/research/companies/${question.isin}?mode=questions`}
            >
              <span className="ws-row-grow">
                <span className="ws-row-t">{question.text}</span>
                <span className="ws-row-m ws-mono">
                  {question.isin} &middot; asked {question.written_on}
                </span>
              </span>
              {question.blocking && <span className="ws-chip ws-chip--warn">Blocks thesis</span>}
            </Link>
          ))
        )}
        {home.open_questions.next_cursor && (
          <div className="ws-empty">More open questions exist; open a company to see them all.</div>
        )}
      </div>

      <div className="ws-sechead">
        <h2>Returning today</h2>
        <div className="ws-hint">your own earlier writing, unchanged</div>
      </div>
      <div className="ws-panel">
        {home.returns.length === 0 ? (
          <div className="ws-empty">Nothing you wrote reaches an anniversary today.</div>
        ) : (
          home.returns.map((item) => {
            const target =
              item.kind === "NOTE" || item.kind === "CONTRADICTION"
                ? item.note_id
                  ? noteHref(item.note_id)
                  : null
                : `/research/companies/${item.isin}?mode=thesis`;
            return (
              <Link key={`${item.kind}:${item.content_ref}`} className="ws-row" href={target ?? "#"}>
                <span className="ws-row-grow">
                  <span className="ws-row-t">
                    {item.kind === "CONTRADICTION"
                      ? "Two of your notes contradict each other"
                      : item.kind === "THESIS"
                        ? "Your thesis was formed"
                        : item.kind === "OVERRIDE"
                          ? "You overrode an exit condition"
                          : "You wrote a note"}{" "}
                    &middot; {REASON_LABEL[item.reason] ?? item.reason}
                  </span>
                  <span className="ws-row-m ws-mono">
                    {item.isin} &middot; {item.original_date}
                    {item.other_date ? ` and ${item.other_date}` : ""}
                  </span>
                </span>
              </Link>
            );
          })
        )}
      </div>
      {home.notices.map((notice) => (
        <p key={notice.code} className="ws-hint">
          {notice.message}
        </p>
      ))}
    </>
  );
}

function CompanyRow({ company }: { company: CompanyListItem }) {
  const { investorId, token } = useResearchAuth();
  const { openDocument } = useWorkspaceNav();
  const [open, setOpen] = useState(false);
  // Only an UNLOCKED company's notes are ever requested -- the server would refuse a locked
  // one anyway, and not asking means no request whose failure could be mistaken for "empty".
  const notes = useFetch<Page<Note>>(
    open && company.ritual_complete ? paths.companyNotes(investorId, company.isin) : null,
    { limit: 20 },
    token
  );
  const label = company.symbol ?? company.name ?? company.isin;

  return (
    <div>
      <div className="ws-row">
        <button
          type="button"
          className="ws-exrow-chev"
          data-open={open}
          aria-expanded={open}
          aria-label={open ? `Collapse ${label}` : `Expand ${label}`}
          onClick={() => setOpen((v) => !v)}
          style={{ border: 0, background: "none", cursor: "pointer" }}
        >
          &#9654;
        </button>
        <span className="ws-row-grow">
          <button
            type="button"
            className="ws-row-t"
            style={{ border: 0, background: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
            onClick={() => {
              const descriptor = companyDescriptor(company.isin, label);
              if (descriptor) openDocument(descriptor);
            }}
          >
            {label}
          </button>
          <span className="ws-row-m ws-mono">
            {company.isin}
            {company.canonical_isin !== company.isin ? ` → ${company.canonical_isin}` : ""}
            {company.name && company.symbol ? ` · ${company.name}` : ""}
          </span>
        </span>
        {company.ritual_complete ? (
          <span className="ws-chip ws-chip--pos">Open</span>
        ) : (
          <span className="ws-chip ws-chip--open">Questions first</span>
        )}
      </div>
      {open && (
        <div style={{ paddingLeft: 24 }}>
          {!company.ritual_complete && (
            <div className="ws-empty">Locked until you record your questions.</div>
          )}
          {notes.loading && company.ritual_complete && <div className="ws-empty">Loading&hellip;</div>}
          {notes.error && <div className="ws-notice ws-notice--error">{notes.error}</div>}
          {notes.data && notes.data.items.length === 0 && (
            <div className="ws-empty">No notes yet.</div>
          )}
          {notes.data?.items.map((note) => (
            <Link key={note.id} className="ws-exrow ws-exrow--sub" href={noteHref(note.id) ?? "#"}>
              <span className="ws-exrow-label">
                {note.title} <span className="ws-muted">&middot; {note.kind.toLowerCase()} &middot; {note.written_on}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function AddCompany({ onAdded }: { onAdded: () => void }) {
  const { investorId, token } = useResearchAuth();
  const [q, setQ] = useState("");
  const results = useFetch<Page<Identity>>(
    investorId && q.trim().length >= 2 ? paths.securities(investorId) : null,
    { q: q.trim(), limit: 10 },
    token
  );
  const { submit, pending, error } = useSubmit<Identity>();
  const { openDocument } = useWorkspaceNav();

  async function add(security: Identity) {
    const linked = await submit({ isin: security.isin }, (key) =>
      write.linkCompany({ investorId, token, idempotencyKey: key }, security.isin)
    );
    if (!linked) return;
    onAdded();
    const descriptor = companyDescriptor(linked.isin, linked.symbol ?? linked.name ?? linked.isin);
    if (descriptor) openDocument(descriptor);
  }

  return (
    <div className="ws-panel">
      <div className="ws-panel-head">
        <h3>Add a company</h3>
        <span className="ws-hint">listed equities known to the system, by ISIN</span>
      </div>
      <div className="ws-form">
        <label className="ws-field">
          <span className="ws-field-label">Search securities</span>
          <input
            className="ws-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="At least 2 characters"
            maxLength={64}
          />
        </label>
        {error && <div className="ws-notice ws-notice--error">{describeError(error)}</div>}
        {results.error && <div className="ws-notice ws-notice--error">{results.error}</div>}
        {results.data && results.data.items.length === 0 && (
          <div className="ws-empty">No listed equity matches.</div>
        )}
        {results.data?.items.map((security) => (
          <div key={security.isin} className="ws-row">
            <span className="ws-row-grow">
              <span className="ws-row-t">{security.symbol ?? security.isin}</span>
              <span className="ws-row-m ws-mono">
                {security.isin}
                {security.name ? ` · ${security.name}` : ""}
              </span>
            </span>
            <button
              type="button"
              className="ws-btn ws-btn--sm"
              disabled={pending}
              onClick={() => void add(security)}
            >
              {pending ? "Adding…" : "Add"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
