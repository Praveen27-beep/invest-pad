"use client";

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { CURRENT_TOS_VERSION } from "@/lib/terms";

/**
 * The Terms of Service and Privacy Policy a login accepts at registration.
 *
 * ⚠️ NOT LEGALLY REVIEWED. Every statement below is drawn from what this codebase
 * actually does — docs/COMPLIANCE.md, docs/INGESTION.md, and the architectural rules in
 * CLAUDE.md — and is accurate as a description of the software. It is NOT a substitute
 * for a lawyer reading it before real clients are onboarded, and docs/COMPLIANCE.md §4
 * lists that as a go-live gate. Do not treat this file as the compliance work being done.
 *
 * WHY IT IS SHORT AND CONCRETE. The commitments that carry weight here are technical
 * facts enforced by the code — no broker credentials are stored because there is no table
 * to store them in and `make lint` fails the build if one appears; the ledger is
 * append-only because a database trigger refuses UPDATE and DELETE. Terms that describe
 * things the software genuinely cannot do are worth more than terms that promise
 * restraint.
 *
 * VERSIONED, and the version is the point. `CURRENT_TOS_VERSION` is sent with the
 * registration and stamped onto `app_user.tos_version`, so an account records which text
 * it agreed to rather than a bare boolean. Change the text, bump the version — in
 * lib/terms.ts AND trackr-backend/app/terms.py, which the server checks against.
 */
export default function TermsPage() {
  return (
    <main
      style={{
        maxWidth: 720,
        margin: "0 auto",
        padding: "48px 24px 72px",
        background: "var(--page)",
        minHeight: "100vh",
      }}
    >
      <p style={eyebrowStyle}>Trackr+ · version {CURRENT_TOS_VERSION}</p>
      <h1
        style={{
          margin: "8px 0 0",
          font: "var(--type-h1)",
          color: "var(--text-primary)",
          letterSpacing: "var(--tracking-tight)",
        }}
      >
        Terms of Service &amp; Privacy Policy
      </h1>
      <p style={{ ...bodyStyle, marginTop: 12, color: "var(--text-secondary)" }}>
        This is the agreement between you and Trackr+ about the software. It is separate
        from the processing permission you are asked for inside the app — that one is
        about a specific portfolio, and you can withdraw it at any time.
      </p>

      <Section title="1 · What this software is">
        <p style={bodyStyle}>
          Trackr+ is portfolio accounting and reporting software for Indian listed
          equities. It records what you bought and sold, computes what you hold and how it
          has performed, and shows you the result.
        </p>
        <p style={bodyStyle}>
          <strong>It is not advice.</strong> Nothing it produces is a recommendation to
          buy or sell anything. It does not place orders, and it has no ability to.
          Everything it shows is a record of holdings and performance.
        </p>
        <p style={bodyStyle}>
          <strong>It is not a broker and not an execution venue.</strong> It never
          connects to your broker, depository or registrar.
        </p>
      </Section>

      <Section title="2 · How your data gets in">
        <p style={bodyStyle}>
          You provide your own account statements — contract notes, tradebooks, broker
          exports — by uploading them or by forwarding them from your email. That is the
          only way data enters this system.
        </p>
        <p style={bodyStyle}>
          <strong>We never ask for your broker password.</strong> No login, no OTP, no API
          key. This is not a policy we could quietly relax: there is nowhere in the
          database to put a broker credential, and the build fails if such a field is ever
          added.
        </p>
      </Section>

      <Section title="3 · What we hold, and for how long">
        <List
          items={[
            <>
              <strong>Your transactions and the documents you send.</strong> Kept while
              your account is open. Records of advisory activity are retained for five
              years, as SEBI requires of an investment adviser.
            </>,
            <>
              <strong>Your PAN, if you give us one.</strong> Encrypted at rest and used
              for one purpose: unlocking password-protected contract-note PDFs, which
              brokers lock with it. Never shown back to you in full, never logged.
            </>,
            <>
              <strong>An audit trail</strong> of what was imported, promoted and changed —
              which is what makes every number on screen reproducible.
            </>,
            <>
              <strong>Never your broker credentials</strong>, because they are never
              collected.
            </>,
          ]}
        />
      </Section>

      <Section title="4 · Your rights over it">
        <p style={bodyStyle}>
          Under the Digital Personal Data Protection Act, 2023, you can export everything
          held about a portfolio, or permanently delete it, from the{" "}
          <Link href="/privacy">Privacy &amp; data</Link> page inside the app. Deletion is
          irreversible and we do not keep a shadow copy — except where a legal hold or the
          five-year retention obligation above requires a record to be kept, in which case
          the app tells you so rather than silently declining.
        </p>
        <p style={bodyStyle}>
          You can withdraw processing permission for a portfolio at any time in Settings.
          Processing stops immediately; erasing what is already stored is the separate
          action above.
        </p>
      </Section>

      <Section title="5 · Accuracy, and what it depends on">
        <p style={bodyStyle}>
          Every figure is computed from the transactions in your ledger, every time it is
          shown. That means it is exactly as accurate as what you gave us: a missing
          contract note is a missing cost, and a missing year is a missing history.
        </p>
        <p style={bodyStyle}>
          Where a price is unavailable we say so and refuse to value that holding, rather
          than treating it as worth nothing. Nothing here is a valuation for tax, audit or
          regulatory filing, and you should check figures against your broker&apos;s own
          statements before relying on them.
        </p>
      </Section>

      <Section title="6 · Changes">
        <p style={bodyStyle}>
          If these terms change materially, you will be asked to accept the new version.
          Your account records which version you accepted — currently{" "}
          <code style={{ font: "var(--type-mono)", color: "var(--text-primary)" }}>
            {CURRENT_TOS_VERSION}
          </code>
          .
        </p>
      </Section>

      <p style={{ ...bodyStyle, marginTop: 32, color: "var(--text-tertiary)" }}>
        <Link href="/register">← Back to sign up</Link>
      </p>
    </main>
  );
}

const eyebrowStyle: CSSProperties = {
  margin: 0,
  font: "var(--type-label)",
  textTransform: "uppercase",
  letterSpacing: "var(--tracking-label)",
  color: "var(--text-tertiary)",
};

const bodyStyle: CSSProperties = {
  margin: "0 0 12px",
  font: "var(--type-body)",
  color: "var(--text-secondary)",
  lineHeight: 1.65,
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: 32, borderTop: "1px solid var(--border)", paddingTop: 20 }}>
      <h2
        style={{
          margin: "0 0 12px",
          font: "var(--type-h2)",
          color: "var(--text-primary)",
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function List({ items }: { items: ReactNode[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 10 }}>
      {items.map((item, index) => (
        <li key={index} style={{ ...bodyStyle, margin: 0 }}>
          {item}
        </li>
      ))}
    </ul>
  );
}
