"use client";

import { useState } from "react";
import { Reveal } from "./Reveal";
import { Chevron } from "./icons";

const FAQS = [
  {
    q: "Do I have to hand over my broker login?",
    a: "No — and there is nowhere to put one if you wanted to. No passwords, no API tokens, no OTP secrets. You bring a file or forward an email, and that is the whole integration surface.",
  },
  {
    q: "What happens to my cost basis after a split or bonus?",
    a: "It carries across at the original lot cost, so the pool is unchanged and your holding period is never reset. The action is verified against your own ledger before it is trusted, and quarantined for review if it does not reconcile.",
  },
  {
    q: "Which assets does Trackr+ cover?",
    a: "Indian listed equities on NSE and BSE — deliberately one asset class, done properly. Mutual funds, bonds and the rest are out of scope today; the data model leaves room for them without a migration.",
  },
  {
    q: "Is Trackr+ a broker or an adviser?",
    a: "Neither. Trackr+ is portfolio analytics. It does not place orders, hold your money, or tell you what to buy. It tells you — precisely and reproducibly — what your own history already amounts to.",
  },
  {
    q: "Can I get my data out again?",
    a: "Yes. Your ledger exports in full, and erasure removes it rather than hiding it. Everything the engine computes is derived from that export, so nothing of yours is locked inside the product.",
  },
];

export function LandingFaq() {
  const [open, setOpen] = useState(0);

  return (
    <section id="faq" className="l-section">
      <div className="l-container l-split">
        <Reveal className="l-split-text">
          <h2 className="l-h2" style={{ marginTop: 0 }}>Questions worth asking.</h2>
          <p style={{ margin: "16px 0 0", fontSize: 15, lineHeight: 1.6, color: "var(--l-text-3)" }}>
            Still unsure about something? <a href="#contact" style={{ color: "var(--l-accent)" }}>Talk to us</a> — a person replies.
          </p>
        </Reveal>

        <Reveal className="l-split-rest" delay={80}>
          {FAQS.map((item, i) => {
            const expanded = open === i;
            return (
              <div key={item.q} className="l-faq-row">
                <button
                  type="button"
                  className="l-faq-btn"
                  aria-expanded={expanded}
                  aria-controls={`l-faq-a-${i}`}
                  onClick={() => setOpen(expanded ? -1 : i)}
                >
                  {item.q}
                  <Chevron className="l-faq-chev" />
                </button>
                {expanded && (
                  <p id={`l-faq-a-${i}`} className="l-faq-answer">{item.a}</p>
                )}
              </div>
            );
          })}
        </Reveal>
      </div>
    </section>
  );
}
