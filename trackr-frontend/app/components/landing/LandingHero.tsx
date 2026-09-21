"use client";

import { Fragment } from "react";
import Link from "next/link";
import { ArrowRight, BrandMark, Lock } from "./icons";

/** Sample figures only — see the disclaimer in LandingFooter. Nothing here is wired to
 *  the real engine, and it must not be: the golden fixture is a losing portfolio. */
const HOLDINGS = [
  { name: "HDFC Bank", invested: "1,25,000", current: "1,68,450", pl: "+34.76%", weight: "14.2%" },
  { name: "ICICI Bank", invested: "1,10,000", current: "1,52,320", pl: "+38.47%", weight: "12.8%" },
  { name: "Persistent Systems", invested: "85,000", current: "1,18,750", pl: "+39.71%", weight: "10.0%" },
  { name: "Tata Motors", invested: "60,000", current: "79,800", pl: "+33.00%", weight: "6.7%" },
];

const SECTORS = [
  { label: "Financials", pct: "30.7%", value: 30.7, colour: "#e6e3dc", offset: 25 },
  { label: "IT", pct: "19.9%", value: 19.9, colour: "#d3c8ad", offset: -5.7 },
  { label: "Energy", pct: "14.1%", value: 14.1, colour: "#dcb069", offset: -25.6 },
  { label: "Industrials", pct: "12.0%", value: 12.0, colour: "#cf9d42", offset: -39.7 },
  { label: "Others", pct: "23.3%", value: 23.3, colour: "#ad8235", offset: -51.7 },
];

const CURVE =
  "M0 132 L26 127 L53 130 L79 116 L106 120 L132 106 L159 110 L185 93 L212 98 L238 82 L264 88 L291 70 L317 76 L344 58 L370 52 L397 60 L423 40 L450 33 L476 27 L502 18 L528 12";
// The benchmark: same x-grid as CURVE, but a chopped path with real drawdowns —
// an index never climbs in a straight line — ending above where it started but
// well below the portfolio curve, since the whole point of the panel is showing
// the portfolio ahead of Nifty 50, not tracking it.
const INVESTED_LINE =
  "M0 140 L26 133 L53 138 L79 128 L106 133 L132 140 L159 130 L185 120 L212 126 L238 108 L264 118 L291 100 L317 108 L344 90 L370 96 L397 80 L423 88 L450 70 L476 76 L502 64 L528 68";

const NAV = ["Overview", "Performance", "Holdings", "Corporate actions", "Tax & ITR"];

export function LandingHero() {
  return (
    <section id="top" className="l-hero">
      <div className="l-container l-center">
        <h1 className="l-h1 l-rise" style={{ animationDelay: "60ms", maxWidth: 920 }}>
          Every number, traced back to the trade that made it.
        </h1>

        <p className="l-lede l-rise" style={{ animationDelay: "220ms", maxWidth: 660 }}>
          Trackr+ replays your entire transaction ledger to compute holdings, XIRR and
          capital gains — on every read. Nothing is cached, so nothing can quietly drift
          out of sync.
        </p>

        <div className="l-cta-row l-rise" style={{ animationDelay: "300ms" }}>
          <Link href="/register" className="l-btn l-btn-solid">
            Get started <ArrowRight />
          </Link>
          <a href="#security" className="l-btn l-btn-ghost">
            See how we protect your data
          </a>
        </div>

        <div className="l-trust l-rise" style={{ animationDelay: "380ms" }}>
          <Lock />
          We never ask for your broker password. Just upload a file or forward an email.
        </div>
      </div>

      <div className="l-container">
        <div className="l-mock-wrap l-rise" style={{ animationDelay: "500ms" }}>
          <div className="l-mock-glow l-breathe" />
          <ProductMockup />
        </div>
      </div>
    </section>
  );
}

function ProductMockup() {
  return (
    <div className="l-mock">
      <div className="l-mock-chrome">
        <span className="l-mock-dot" />
        <span className="l-mock-dot" />
        <span className="l-mock-dot" />
        <span style={{ flexGrow: 1, display: "flex", justifyContent: "center" }}>
          <span className="l-mock-url">
            <Lock size={10} />
            app.trackrplus.in/portfolio
          </span>
        </span>
      </div>

      <div className="l-mock-body">
        <div className="l-mock-side">
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 10px 16px" }}>
            <span className="l-mark" style={{ width: 20, height: 20, borderRadius: 5 }}><BrandMark size={12} /></span>
            <span style={{ fontFamily: "Newsreader, Georgia, serif", fontSize: 15 }}>Trackr+</span>
          </div>
          {NAV.map((item, i) => (
            <span key={item} className={`l-mock-navitem${i === 0 ? " l-mock-navitem-on" : ""}`}>
              {item}
            </span>
          ))}
        </div>

        <div className="l-mock-main">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <span style={{ fontFamily: "Newsreader, Georgia, serif", fontSize: 22 }}>Portfolio</span>
            <span
              style={{
                display: "inline-flex", alignItems: "center", gap: 7,
                height: 28, padding: "0 12px",
                border: "1px solid var(--l-border)", borderRadius: 7,
                background: "var(--l-surface)", fontSize: 11, color: "var(--l-text-3)",
                whiteSpace: "nowrap",
              }}
            >
              <span className="l-dot l-blink" style={{ width: 5, height: 5 }} />
              Priced to 20 Sep 2026 close
            </span>
          </div>

          <div className="l-kpis">
            <Kpi label="Invested" figure="₹8.18 L" note="Net of brokerage & STT" />
            <Kpi label="Current value" figure="₹11.89 L" note="Day +0.74%" noteColour="var(--l-pos)" />
            <Kpi label="Unrealised P&L" figure="₹3.71 L" figureColour="var(--l-pos)" note="+45.29%" noteColour="var(--l-pos)" />
            <Kpi
              accent
              label="XIRR · since inception"
              figure="+14.09%"
              figureColour="var(--l-accent)"
              note="Annualised, computed on every read"
              noteColour="var(--l-text-2)"
            />
          </div>

          <div className="l-panels">
            <div className="l-panel" style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <span className="l-panel-title">Portfolio value vs Nifty 50</span>
                <span style={{ display: "flex", gap: 3 }}>
                  <span style={{ padding: "3px 8px", fontSize: 10, color: "var(--l-text-3)" }}>1Y</span>
                  <span style={{ padding: "3px 8px", borderRadius: 5, background: "var(--l-accent)", color: "var(--l-page)", fontSize: 10, fontWeight: 600 }}>3Y</span>
                  <span style={{ padding: "3px 8px", fontSize: 10, color: "var(--l-text-3)" }}>Max</span>
                </span>
              </div>

              <svg viewBox="0 0 528 152" fill="none" style={{ width: "100%", height: "auto" }} aria-hidden="true">
                <defs>
                  <linearGradient id="l-curve-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#dcb069" stopOpacity="0.28" />
                    <stop offset="100%" stopColor="#dcb069" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {[18, 52, 86, 120].map((y) => (
                  <line key={y} x1="0" y1={y} x2="528" y2={y} stroke="var(--l-border)" strokeWidth="1" />
                ))}
                <path d={`${CURVE} L528 152 L0 152 Z`} fill="url(#l-curve-fill)" />
                <path className="l-draw" d={CURVE} stroke="#dcb069" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d={INVESTED_LINE} stroke="#8e8b86" strokeWidth="1.5" strokeDasharray="3 4" strokeLinecap="round" />
              </svg>

              <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 16, fontSize: 10, color: "var(--l-text-3)" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 14, height: 2, background: "#dcb069" }} />Portfolio value
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 14, borderTop: "1.5px dashed #8e8b86" }} />Nifty 50
                </span>
              </div>
            </div>

            <div className="l-panel">
              <span className="l-panel-title">Allocation by sector</span>
              <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 16 }}>
                <svg width="96" height="96" viewBox="0 0 42 42" style={{ flexShrink: 0 }} aria-hidden="true">
                  <circle cx="21" cy="21" r="15.9" fill="none" stroke="var(--l-raised)" strokeWidth="7" />
                  {SECTORS.map((s) => (
                    <circle
                      key={s.label}
                      cx="21" cy="21" r="15.9" fill="none"
                      stroke={s.colour} strokeWidth="7"
                      strokeDasharray={`${s.value} ${100 - s.value}`}
                      strokeDashoffset={s.offset}
                    />
                  ))}
                </svg>
                <div style={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 7 }}>
                  {SECTORS.map((s) => (
                    <span key={s.label} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 10.5, color: "var(--l-text-2)" }}>
                      <span style={{ width: 7, height: 7, borderRadius: 2, background: s.colour, flexShrink: 0 }} />
                      {s.label}
                      <span className="l-num" style={{ flexGrow: 1, color: "var(--l-text-3)" }}>{s.pct}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="l-panel">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, gap: 12 }}>
              <span className="l-panel-title">Top holdings</span>
              <span style={{ fontSize: 10, color: "var(--l-text-3)", whiteSpace: "nowrap" }}>Computed on read · never stored</span>
            </div>
            <div className="l-ledger">
              <span className="l-ledger-head">Security</span>
              <span className="l-ledger-head l-num l-ledger-col-hide">Invested</span>
              <span className="l-ledger-head l-num l-ledger-col-hide">Current</span>
              <span className="l-ledger-head l-num">P&amp;L</span>
              <span className="l-ledger-head l-num">Weight</span>

              {HOLDINGS.map((h) => (
                <Fragment key={h.name}>
                  <span className="l-ledger-cell" style={{ color: "var(--l-text)" }}>{h.name}</span>
                  <span className="l-ledger-cell l-num l-ledger-col-hide">{h.invested}</span>
                  <span className="l-ledger-cell l-num l-ledger-col-hide">{h.current}</span>
                  <span className="l-ledger-cell l-num" style={{ color: "var(--l-pos)" }}>{h.pl}</span>
                  <span className="l-ledger-cell l-num">{h.weight}</span>
                </Fragment>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({
  label, figure, note, accent, figureColour, noteColour,
}: {
  label: string;
  figure: string;
  note: string;
  accent?: boolean;
  figureColour?: string;
  noteColour?: string;
}) {
  return (
    <div className={`l-kpi${accent ? " l-kpi-accent" : ""}`}>
      <span className="l-kpi-label" style={accent ? { color: "var(--l-accent-dim)" } : undefined}>{label}</span>
      <span className="l-kpi-fig" style={figureColour ? { color: figureColour } : undefined}>{figure}</span>
      <span className="l-kpi-note" style={noteColour ? { color: noteColour } : undefined}>{note}</span>
    </div>
  );
}
