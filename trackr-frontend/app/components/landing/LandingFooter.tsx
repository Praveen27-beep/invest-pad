"use client";

import Link from "next/link";
import { Reveal } from "./Reveal";
import { ArrowRight, BrandMark, Instagram, LinkedIn, XMark } from "./icons";

const COLUMNS = [
  {
    head: "Product",
    links: [
      { label: "Overview", href: "#top" },
      { label: "Security", href: "#security" },
      { label: "Pricing", href: "/coming-soon?feature=Pricing" },
    ],
  },
  {
    head: "Company",
    links: [
      { label: "About", href: "/coming-soon?feature=About" },
      { label: "Blog", href: "/coming-soon?feature=Blog" },
      { label: "Contact", href: "/coming-soon?feature=Contact" },
      { label: "Status", href: "/coming-soon?feature=Status" },
    ],
  },
  {
    head: "Legal",
    links: [
      { label: "Terms", href: "/terms" },
      { label: "Privacy", href: "/privacy" },
      { label: "Compliance", href: "/coming-soon?feature=Compliance" },
      { label: "Data & DPDP", href: "/privacy" },
    ],
  },
];

export function LandingFooter() {
  return (
    <footer className="l-footer">
      <div className="l-container">
        <Reveal>
          <div className="l-footer-statement">
            <h2 className="l-h2" style={{ marginTop: 0 }}>The ledger is the source of truth.</h2>
            <Link href="/register" className="l-btn l-btn-ghost" style={{ height: 48, flexShrink: 0 }}>
              Get started <ArrowRight size={15} />
            </Link>
          </div>
        </Reveal>

        <Reveal>
          <div className="l-footer-cols">
            <div className="l-footer-brand">
              <span className="l-brand">
                <span className="l-mark"><BrandMark /></span>
                <span className="l-wordmark">Trackr+</span>
              </span>
              <p style={{ margin: "16px 0 0", fontSize: 13.5, lineHeight: 1.6, color: "var(--l-text-3)" }}>
                Portfolio intelligence for Indian equity investors. Every number
                reproducible from your own ledger.
              </p>
            </div>

            <div className="l-footer-links">
              {COLUMNS.map((col) => (
                <div key={col.head} className="l-footer-col">
                  <span className="l-footer-head">{col.head}</span>
                  {col.links.map((link) =>
                    link.href.startsWith("/") ? (
                      <Link key={link.label} href={link.href} className="l-flink">{link.label}</Link>
                    ) : (
                      <a key={link.label} href={link.href} className="l-flink">{link.label}</a>
                    )
                  )}
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        <Reveal>
          <div className="l-social">
            <a href="#linkedin" aria-label="Trackr+ on LinkedIn"><LinkedIn /></a>
            <a href="#x" aria-label="Trackr+ on X"><XMark /></a>
            <a href="#instagram" aria-label="Trackr+ on Instagram"><Instagram /></a>
          </div>
        </Reveal>

        <div className="l-bigmark" aria-hidden="true">
          <span>Trackr+</span>
        </div>

        <div className="l-footer-legal">
          <p>
            Trackr+ is a portfolio analytics product. It is not a broker, an investment
            adviser or an execution venue, it does not provide investment advice, and it
            does not place orders or hold client funds. Indian listed equities only.
            Figures shown throughout this page are illustrative sample data.
          </p>
          <span>© {new Date().getFullYear()} Trackr+</span>
        </div>
      </div>
    </footer>
  );
}
