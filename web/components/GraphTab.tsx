"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Graph } from "@/lib/api";

const COLOR: Record<string, string> = { company: "#1c1d1f", note: "#2f5d50", document: "#1d4e89", assumption: "#9a5b13", decision: "#6a3d8a" };
const RING: Record<string, number> = { company: 0, assumption: 1, decision: 1, document: 2, note: 2 };
const LINK: Record<string, (ref: string) => string | null> = {
  note: (r) => `/n/${r}`, document: (r) => `/d/${r}`, company: (r) => `/c/${r}`, assumption: () => null, decision: () => null,
};

/** How this company's notes, documents, assumptions and decisions connect. The company
 *  sits in the middle; the thesis around it; sources on the outside. Positions are
 *  computed, not stored, so the picture is the same every time for the same record. */
export default function GraphTab({ subjectId }: { subjectId?: string }) {
  const router = useRouter();
  const [graph, setGraph] = useState<Graph | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => { api<Graph>(subjectId ? `/graph?subject_id=${subjectId}` : "/graph").then(setGraph).catch(() => {}); }, [subjectId]);
  if (!graph) return null;

  const companies = graph.nodes.filter((n) => n.kind === "company").length;
  const W = 900, H = companies > 1 ? 760 : 620, cx = W / 2, cy = H / 2;
  const pos: Record<string, { x: number; y: number }> = {};
  for (const ring of [0, 1, 2]) {
    const members = graph.nodes.filter((n) => RING[n.kind] === ring).sort((a, b) => a.kind.localeCompare(b.kind) || a.label.localeCompare(b.label));
    members.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(members.length, 1) - Math.PI / 2 + ring * 0.3;
      const radius = companies > 1 ? [110, 220, 330][ring] : [0, 150, 270][ring];
      pos[n.id] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
    });
  }
  const near = focus ? new Set(graph.edges.filter((e) => e.from === focus || e.to === focus).flatMap((e) => [e.from, e.to])) : null;
  const linkCount = graph.edges.filter((e) => e.kind !== "filed under" && e.kind !== "thesis of" && e.kind !== "decision on").length;

  return (
    <>
      <p className="empty">
        {graph.nodes.length - companies} item(s){companies > 1 ? ` across ${companies} companies` : ""}, {linkCount} connection(s) between them. Hover to see what an item touches; click a note
        or document to open it. Notes connect when one links to another with [[Title]]; a document connects to an
        assumption when you use a passage as evidence.
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Connection graph" style={{ width: "100%", background: "var(--card)", border: "1px solid var(--line)", borderRadius: 10 }}>
        {graph.edges.map((e, i) => {
          const a = pos[e.from], b = pos[e.to];
          const lit = focus && (e.from === focus || e.to === focus);
          const structural = e.kind === "filed under" || e.kind === "thesis of" || e.kind === "decision on";
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={lit ? "#1c1d1f" : e.kind.startsWith("evidence against") ? "#a33a2c" : "#b9bcc2"}
            strokeWidth={lit ? 2 : structural ? 0.6 : 1.4} strokeDasharray={structural ? "3 4" : undefined} opacity={focus && !lit ? 0.25 : 1}><title>{e.kind}</title></line>;
        })}
        {graph.nodes.map((n) => {
          const p = pos[n.id];
          const dim = near && !near.has(n.id) && n.id !== focus;
          const href = LINK[n.kind](n.ref);
          return (
            <g key={n.id} opacity={dim ? 0.25 : 1} style={{ cursor: href && (n.kind !== "company" || !subjectId) ? "pointer" : "default" }}
              onMouseEnter={() => setFocus(n.id)} onMouseLeave={() => setFocus(null)}
              onClick={() => { if (href && (n.kind !== "company" || !subjectId)) router.push(href); }}>
              <circle cx={p.x} cy={p.y} r={n.kind === "company" ? 13 : 8} fill={n.state === "broken" ? "#a33a2c" : COLOR[n.kind]} />
              <text x={p.x} y={p.y + (n.kind === "company" ? 30 : 22)} textAnchor="middle" fontSize="11" fill="#1c1d1f">
                {n.label.length > 34 ? `${n.label.slice(0, 33)}…` : n.label}
              </text>
              <title>{`${n.kind}: ${n.label}`}</title>
            </g>
          );
        })}
      </svg>
      <p className="small muted">
        {Object.entries(COLOR).map(([kind, color]) => (<span key={kind} style={{ marginRight: "1rem" }}><span style={{ color }}>●</span> {kind}</span>))}
        <span style={{ color: "#a33a2c" }}>●</span> broken assumption
      </p>
    </>
  );
}
