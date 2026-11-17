"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, day } from "@/lib/api";

type Entry = { id: string; subject_id: string; company: string; label: string; decided_on: string; decisive_reason: string; would_change_mind: string };

export default function JournalPage() {
  const [rows, setRows] = useState<Entry[] | null>(null);
  useEffect(() => { api<Entry[]>("/journal").then(setRows).catch(() => setRows([])); }, []);
  if (!rows) return null;
  return (
    <>
      <h1>Decision journal</h1>
      <p className="empty">Every decision you recorded, across companies, in your own words. Records are never edited.</p>
      {rows.length === 0 ? <p className="empty">No decisions yet. Record one from a company’s “Thesis &amp; decisions” tab.</p> : (
        <ul className="list">
          {rows.map((r) => (
            <li key={r.id} style={{ flexWrap: "wrap" }}>
              <span className="muted small" style={{ minWidth: "6.5rem" }}>{day(r.decided_on)}</span>
              <strong style={{ minWidth: "5rem" }}>{r.label}</strong>
              <Link href={`/c/${r.subject_id}`}>{r.company}</Link>
              <span style={{ flexBasis: "100%" }}>{r.decisive_reason}</span>
              {r.would_change_mind && <span className="small muted" style={{ flexBasis: "100%" }}>Would change my mind: {r.would_change_mind}</span>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
