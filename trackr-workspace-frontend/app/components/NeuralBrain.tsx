"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A live neural network drawn in the shape of a brain. Nodes ignite outward from one point
 * and settle into the outline, and signals travel along the connections. It plays when the
 * page opens, and Replay runs it again. Reduced motion shows the finished network at once.
 *
 * Decorative: the canvas is aria-hidden, and the meaning sits in the text beside it.
 */

const NODE_COUNT = 230;
const LINK_DISTANCE = 0.2;
const LINKS_PER_NODE = 3;
const INTRO_MS = 2600;
const NODE_FADE_MS = 500;

type Node = { x: number; y: number; wave: number; phase: number };
type Edge = { a: number; b: number };
type Pulse = { edge: number; dir: 1 | -1; t: number; speed: number };

/** Seeded PRNG, so the same network is drawn on every visit. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

/** Brain outline in a [-1, 1] box: an oval, a fissure between hemispheres, and a flat underside. */
function inside(x: number, y: number) {
  if ((x / 0.94) ** 2 + (y / 0.64) ** 2 > 1) return false;
  if (Math.abs(x) < 0.04 && y < 0.1) return false;
  if (y > 0.34 && Math.abs(x) > 0.34) return false;
  return true;
}

function buildNetwork(): { nodes: Node[]; edges: Edge[] } {
  const rand = rng(11);
  const pts: { x: number; y: number }[] = [];
  for (let guard = 0; pts.length < NODE_COUNT && guard < 50000; guard++) {
    const x = rand() * 2 - 1;
    const y = rand() * 2 - 1;
    if (inside(x, y)) pts.push({ x, y });
  }

  // The wave starts near the front-left of the brain and spreads outward.
  const origin = { x: -0.35, y: -0.15 };
  const maxDist = Math.max(...pts.map((p) => Math.hypot(p.x - origin.x, p.y - origin.y)));
  const nodes: Node[] = pts.map((p) => ({
    x: p.x,
    y: p.y,
    wave: Math.hypot(p.x - origin.x, p.y - origin.y) / maxDist,
    phase: rand() * Math.PI * 2,
  }));

  const seen = new Set<string>();
  const edges: Edge[] = [];
  nodes.forEach((n, i) => {
    const near = nodes
      .map((m, j) => ({ j, d: Math.hypot(m.x - n.x, m.y - n.y) }))
      .filter((o) => o.j !== i && o.d < LINK_DISTANCE)
      .sort((p, q) => p.d - q.d)
      .slice(0, LINKS_PER_NODE);
    for (const { j } of near) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (!seen.has(key)) {
        seen.add(key);
        edges.push({ a: i, b: j });
      }
    }
  });
  return { nodes, edges };
}

const NETWORK = buildNetwork();

export function NeuralBrain() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [run, setRun] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const { nodes, edges } = NETWORK;
    const pulses: Pulse[] = [];
    const pulseRand = rng(run * 97 + 5);

    let w = 0;
    let h = 0;
    let dpr = 1;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    const project = (n: Node) => {
      const R = Math.min(w * 0.48, h * 0.7);
      return { x: w / 2 + n.x * R, y: h / 2 + n.y * R * 0.92 };
    };

    const nodeAlpha = (n: Node, t: number) => {
      const start = n.wave * INTRO_MS;
      return Math.min(1, Math.max(0, (t - start) / NODE_FADE_MS));
    };

    let t = reduced ? INTRO_MS + NODE_FADE_MS : 0;
    let last = performance.now();
    let frame = 0;

    const draw = (now: number) => {
      const dt = Math.max(0, Math.min(64, now - last));
      last = now;
      t += dt;
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // Edges appear once both ends have lit up.
      ctx.lineWidth = 0.8;
      edges.forEach((e) => {
        const na = nodes[e.a];
        const nb = nodes[e.b];
        if (!na || !nb) return;
        const alpha = Math.min(nodeAlpha(na, t), nodeAlpha(nb, t)) * 0.34;
        if (alpha <= 0) return;
        const pa = project(na);
        const pb = project(nb);
        ctx.strokeStyle = `rgba(77, 116, 255, ${alpha})`;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      });

      // Neurons, breathing gently once lit.
      nodes.forEach((n, i) => {
        const a = nodeAlpha(n, t);
        if (a <= 0) return;
        const p = project(n);
        const breathe = reduced ? 1 : 1 + 0.18 * Math.sin(t / 900 + n.phase);
        ctx.fillStyle = `rgba(21, 36, 90, ${0.55 + 0.45 * a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, (2 + (i % 4 === 0 ? 1.2 : 0)) * breathe * a, 0, Math.PI * 2);
        ctx.fill();
      });

      // Signals: spawn after the intro, then travel along edges.
      if (!reduced && t > INTRO_MS && edges.length) {
        if (pulseRand() < dt * 0.006) {
          pulses.push({
            edge: Math.floor(pulseRand() * edges.length),
            dir: pulseRand() < 0.5 ? 1 : -1,
            t: 0,
            speed: 0.7 + pulseRand() * 0.8,
          });
        }
      }
      for (let k = pulses.length - 1; k >= 0; k--) {
        const pl = pulses[k];
        if (!pl) continue;
        pl.t += (dt / 1000) * pl.speed;
        const e = edges[pl.edge];
        if (pl.t >= 1 || !e) {
          pulses.splice(k, 1);
          continue;
        }
        const from = nodes[pl.dir === 1 ? e.a : e.b];
        const to = nodes[pl.dir === 1 ? e.b : e.a];
        if (!from || !to) continue;
        const pa = project(from);
        const pb = project(to);
        const x = pa.x + (pb.x - pa.x) * pl.t;
        const y = pa.y + (pb.y - pa.y) * pl.t;
        ctx.fillStyle = "rgba(77, 116, 255, 0.18)";
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#4d74ff";
        ctx.beginPath();
        ctx.arc(x, y, 2.6, 0, Math.PI * 2);
        ctx.fill();
      }

      if (!reduced) frame = requestAnimationFrame(draw);
    };

    if (reduced) {
      draw(performance.now());
    } else {
      frame = requestAnimationFrame(draw);
    }

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [run]);

  return (
    <figure className="ip-brain">
      <canvas ref={canvasRef} aria-hidden="true" />
      <figcaption>
        <span>A second brain, always working.</span>
        <button type="button" onClick={() => setRun((r) => r + 1)}>
          Replay
        </button>
      </figcaption>
    </figure>
  );
}
