"use client";

import Link from "next/link";
import { type Overview as Data, STATES, day, when } from "@/lib/api";

/** The first thing shown when a company is reopened: what you decided, and why, in your words. */
export default function Overview({ data, goTo }: { data: Data; goTo: (tab: string) => void }) {
  const d = data.decision;
  const c = data.changes;
  const changed = c.notes.length + c.documents.length + c.assumptions.length + c.thesis_versions;
  return (
    <>
      {!d ? (
        <div className="card">
          <strong>No decision recorded yet.</strong>
          <p className="muted">
            When you buy, pass, or stop researching, record it with the one reason that decided it. That reason is
            what this page will show you the next time you open this company.
          </p>
          <button className="primary" onClick={() => goTo("thesis")}>Go to thesis and decisions</button>
        </div>
      ) : (
        <div className="card" aria-label="Last decision">
          <div className="row">
            <strong style={{ fontSize: "1.1rem" }}>{d.type_label}</strong>
            <span className="muted">on {day(d.decided_on)}</span>
            {d.position_seq && <span className="muted small">· thesis version {d.position_seq}{d.thesis_changed ? ` (now version ${data.thesis_seq})` : ""}</span>}
          </div>
          <h2>The reason that decided it</h2>
          <p className="reason">{d.decisive_reason}</p>
          {d.would_change_mind && (<><h2>What would change my mind</h2><p style={{ whiteSpace: "pre-wrap" }}>{d.would_change_mind}</p></>)}
          {d.flags.length > 0 && (
            <>
              <h2>Raised against your own rules when you recorded it</h2>
              {d.flags.map((f, i) => (<div className="ev" key={i}><span className="quote" style={{ display: "block" }}>“{f.rule}”</span>{f.question}</div>))}
            </>
          )}
          {d.assumptions.length > 0 && (
            <>
              <h2>It rested on</h2>
              {d.assumptions.map((a) => (
                <div className="ev" key={a.id}>
                  {a.body}{" "}
                  {!a.now ? <span className="badge gone">removed</span>
                    : <span className={`badge ${a.now.state}`}>{STATES[a.now.state as keyof typeof STATES]} now</span>}
                  {a.now?.changed && (
                    <span className="snip">
                      Changed since the decision{a.now.reason ? `: ${a.now.reason}` : ""}
                      {a.now.body !== a.body ? ` — now reads: “${a.now.body}”` : ""}
                    </span>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {data.open_questions.length > 0 && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Open questions</h2>
          {data.open_questions.map((q) => (<div className="ev" key={q.id}>{q.body} <span className="snip">{when(q.captured_at)}</span></div>))}
          <p className="small"><Link href="/inbox">Open the inbox</Link></p>
        </div>
      )}

      {d && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Since that decision was recorded</h2>
          {changed === 0 ? <p className="muted">Nothing has changed.</p> : (
            <>
              {c.thesis_versions > 0 && <div className="ev">Thesis revised {c.thesis_versions} time(s). <button className="link" onClick={() => goTo("thesis")}>See what changed</button></div>}
              {c.assumptions.map((a) => (
                <div className="ev" key={a.id + a.seq}>
                  Assumption <span className={`badge ${a.state}`}>{STATES[a.state as keyof typeof STATES]}</span> {a.body}
                  <span className="snip">{when(a.created_at)}{a.reason ? ` · ${a.reason}` : ""}</span>
                </div>
              ))}
              {c.documents.map((x) => (
                <div className="ev" key={x.id}>New document: <Link href={`/d/${x.id}`}>{x.title}</Link> <span className="snip">{x.doc_type}{x.period ? ` · ${x.period}` : ""} · {when(x.created_at)}</span></div>
              ))}
              {c.notes.map((n) => (
                <div className="ev" key={n.id}>Note written or edited: <Link href={`/n/${n.id}`}>{n.title}</Link> <span className="snip">{when(n.updated_at)}</span></div>
              ))}
            </>
          )}
        </div>
      )}
    </>
  );
}
