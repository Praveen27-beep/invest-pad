"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Review, type ReviewItem, when } from "@/lib/api";

export default function ReviewPage() {
  const [review, setReview] = useState<Review | null>(null);
  const [past, setPast] = useState<Review | null>(null);
  const load = useCallback(async () => setReview(await api<Review>("/review")), []);
  useEffect(() => { load().catch(() => {}); }, [load]);
  if (!review) return null;
  const month = new Date(`${review.period}-01`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  return (
    <>
      <h1>Monthly review · {month}</h1>
      <p className="empty">
        A short list of questions built from what you have recorded: your holdings, your limits, your theses and your
        watchlist. Each shows the fact it rests on. They are questions, not advice. Your answers are kept.
      </p>
      {review.items.length === 0 ? (
        <p className="empty">Nothing to ask yet. Import your holdings on the <Link href="/portfolio">Portfolio</Link> page, or add companies to your watchlist.</p>
      ) : review.items.map((item) => (<Item key={item.id} item={item} onSaved={load} />))}

      {(review.past?.length ?? 0) > 0 && (
        <>
          <h2>Earlier reviews</h2>
          <ul className="list">
            {review.past!.map((r) => (
              <li key={r.id}>
                <button className="link" onClick={async () => setPast(await api<Review>(`/review/${r.id}`))}>{r.period}</button>
                <small>{r.answered} of {r.questions} answered</small>
              </li>
            ))}
          </ul>
          {past && past.items.map((i) => (
            <div className="card" key={i.id}><strong>{i.question}</strong><div className="snip">{i.basis}</div>
              <p style={{ whiteSpace: "pre-wrap" }}>{i.answer || <em className="muted">Not answered.</em>}</p></div>
          ))}
        </>
      )}
    </>
  );
}

function Item({ item, onSaved }: { item: ReviewItem; onSaved: () => Promise<void> }) {
  const [answer, setAnswer] = useState(item.answer);
  const [status, setStatus] = useState("");
  return (
    <div className="card">
      <div className="snip">{item.basis}</div>
      <p style={{ fontSize: "1.1rem", margin: ".3rem 0 .6rem" }}>{item.question}</p>
      <textarea rows={3} value={answer} aria-label={item.question} placeholder="Your answer, for the record."
        onChange={(e) => { setAnswer(e.target.value); setStatus(""); }} />
      <div className="row" style={{ marginTop: ".4rem" }}>
        <button className="primary" disabled={!answer.trim() || answer.trim() === item.answer} onClick={async () => {
          await api(`/review/items/${item.id}`, { method: "PUT", body: { answer } });
          setStatus("Saved");
          await onSaved();
        }}>Save answer</button>
        <span className="ok" role="status">{status}</span>
        {item.answered_at && <span className="muted small">answered {when(item.answered_at)}</span>}
        {item.subject_id && <Link href={`/c/${item.subject_id}`}>Open company</Link>}
      </div>
    </div>
  );
}
