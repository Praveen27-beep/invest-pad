"use client";

import Link from "next/link";
import "./landing.css";
import { Reveal } from "./Reveal";
import { LandingHeader } from "./LandingHeader";
import { LandingHero } from "./LandingHero";
import { LandingFaq } from "./LandingFaq";
import { LandingFooter } from "./LandingFooter";
import { ArrowRight, Doc, Mail, Shield, Table } from "./icons";

const INGESTION = [
  { icon: <Table />, title: "Upload a file", body: "Drop in the CSV or tradebook your broker already gives you. Uploading the same file twice never creates duplicates." },
  { icon: <Mail />, title: "Forward an email", body: "Send us your contract notes and we'll read the trades out of them automatically." },
  { icon: <Doc />, title: "Share a PDF", body: "We read your contract notes and turn them into a clean transaction history — nothing more." },
  { icon: <Shield />, title: "Delete anytime", body: "One click removes everything — your trades, your history, all of it. Not just your login." },
];

export function Landing() {
  return (
    <div className="l-root">
      <LandingHeader />
      <LandingHero />

      <section id="security" className="l-section l-section-alt">
        <div className="l-container l-split">
          <Reveal className="l-split-text">
            <span className="l-eyebrow">Security</span>
            <h2 className="l-h2">We never store your information.</h2>
            <p className="l-body" style={{ marginTop: 18 }}>
              We never ask for your broker password, and we couldn't store one even if we
              wanted to — that option simply doesn't exist in our system. All we ever need is
              a file you upload or an email you forward us. Nothing more.
            </p>
            <Link href="/coming-soon?feature=Compliance" className="l-navlink" style={{ marginTop: 22, display: "inline-flex", alignItems: "center", gap: 8, fontWeight: 500 }}>
              Learn more about how we handle your data <ArrowRight size={15} />
            </Link>
          </Reveal>

          <div className="l-split-rest l-grid-2">
            {INGESTION.map((item, i) => (
              <Reveal key={item.title} delay={i * 70}>
                <div className="l-card" style={{ height: "100%" }}>
                  <span style={{ color: "var(--l-accent)", display: "block" }}>{item.icon}</span>
                  <span className="l-card-title" style={{ display: "block", marginTop: 12, fontSize: 15 }}>{item.title}</span>
                  <p className="l-card-body" style={{ marginTop: 6, fontSize: 12.5 }}>{item.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <LandingFaq />

      <LandingFooter />
    </div>
  );
}
