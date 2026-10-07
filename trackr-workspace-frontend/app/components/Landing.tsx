"use client";

import Link from "next/link";
import { useState } from "react";

export type PublicPage = "features" | "pricing" | "blog" | "manifesto" | "docs";
const nav: [string, string][] = [
  ["Features", "/features"],
  ["Pricing", "/pricing"],
  ["Blog", "/blog"],
  ["Manifesto", "/manifesto"],
  ["Docs", "/docs"],
];

export function PublicHeader() {
  return (
    <header className="ip-header">
      <Link className="ip-wordmark" href="/">
        Invest-pad<span aria-hidden="true">_</span>
      </Link>
      <nav aria-label="Main navigation">
        {nav.map(([label, href]) => (
          <Link key={href} href={href}>
            {label}
          </Link>
        ))}
      </nav>
      <Link className="ip-signin" href="/login">
        Sign in
      </Link>
    </header>
  );
}

function Footer() {
  return (
    <footer className="ip-footer">
      <div>
        <Link className="ip-wordmark" href="/">
          Invest-pad
        </Link>
        <p>A place for the work behind your conviction.</p>
      </div>
      <div>
        <Link href="/manifesto">Our manifesto</Link>
        <Link href="/docs">Documentation</Link>
        <Link href="/terms">Terms & privacy policy</Link>
      </div>
      <p>
        Built for Indian equities.
        <br />
        Research and information, not investment advice.
      </p>
    </footer>
  );
}

const principles = [
  [
    "Start with your own questions.",
    "Before the annual report, the earnings call, or anyone else’s opinion, write what you need to know. Unanswered questions stay in view. A blocking question keeps a thesis in draft.",
  ],
  [
    "Read the source. Test the earnings.",
    "Start with annual reports, notes to accounts, auditor reports and exchange filings. Test earnings against cash flow and governance before valuation. A reported number and what you think it means are different kinds of knowledge. Observations carry sources and dates. Interpretations remain visibly yours. Conflicting evidence stays visible.",
  ],
  [
    "Let your earlier self speak.",
    "A revision should add to the record. It should never erase what you believed. Notes, thesis changes and decisions keep their history, so you can return to the reasoning you actually had at the time.",
  ],
  [
    "Make room for being wrong.",
    "A thesis needs something that would disprove it. Record measurable conditions and a pre-mortem. When evidence is missing, unknown is a useful answer.",
  ],
  [
    "Keep the decision yours.",
    "AI can question an assumption and propose a change. You review the difference before accepting it. Your words, commitments and decisions cannot be silently rewritten.",
  ],
  [
    "Research should return.",
    "Writing is only the beginning. Open a company and meet your unanswered questions. Revisit a thesis and see the original argument. Bring old notes back when new evidence makes them relevant.",
  ],
];

function Features() {
  return (
    <section className="ip-features" id="features">
      <div className="ip-section-label">THE WORKSPACE</div>
      <h2>
        Keep the company.
        <br />
        Keep your thinking.
      </h2>
      {[
        [
          "01",
          "Room to think in your own words",
          "Company-linked notes, long-form drafts and a dated research history. Group ideas by kind, connect related notes, and find the argument you wrote last quarter.",
        ],
        [
          "02",
          "Evidence beside the argument",
          "Move from company overview to financials, valuation, management and forensics. Keep source material separate from your interpretation, with uncertainty in view.",
        ],
        [
          "03",
          "A repeatable research practice",
          "Skills bring structure to a checklist, a forensic review or a thesis challenge. The method is reusable; the conclusion remains yours.",
        ],
        [
          "04",
          "Connected to what you own",
          "Trackr+ brings your portfolio into the same workspace. Research sits beside the transaction-derived record, without changing it.",
        ],
      ].map(([n, title, body]) => (
        <div className="ip-feature" key={n}>
          <span>{n}</span>
          <h3>{title}</h3>
          <p>{body}</p>
        </div>
      ))}
    </section>
  );
}

/** Public, read-only product illustration. Never reads or writes investor data. */
function ProductPreview() {
  const [view, setView] = useState("Research notes");
  const [company, setCompany] = useState("PVR INOX");
  const tabs = ["Overview", "Research notes", "Skills"];
  return (
    <section className="ip-preview" aria-label="Interactive product preview">
      <div className="ip-preview-bar">
        <span>INVEST-PAD / WORKSPACE</span>
        <span>Illustrative preview · no live market data</span>
      </div>
      <div className="ip-preview-grid">
        <aside>
          <div className="ip-wordmark">Invest-pad</div>
          <p>Portfolio</p>
          <p>Skills</p>
          <div className="ip-section-label">YOUR RESEARCH</div>
          {["PVR INOX", "Asian Paints", "TCS"].map((c) => (
            <button
              key={c}
              aria-pressed={company === c}
              onClick={() => setCompany(c)}
            >
              {c}
            </button>
          ))}
          <small>
            Linked notes
            <br />
            Open questions
            <br />
            Thesis history
          </small>
        </aside>
        <div className="ip-preview-main">
          <div className="ip-preview-company">
            <span className="ip-monogram">{company.slice(0, 1)}</span>
            <div>
              <h3>{company}</h3>
              <span>Indian equities / Research workspace</span>
            </div>
          </div>
          <div className="ip-preview-tabs" aria-label="Preview views">
            {tabs.map((t) => (
              <button
                key={t}
                aria-pressed={view === t}
                onClick={() => setView(t)}
              >
                {t}
              </button>
            ))}
          </div>
          {view === "Research notes" ? (
            <div className="ip-preview-writing">
              <div className="ip-preview-note-nav">
                <span>NOTES BY KIND</span>
                <p>Questions</p>
                <p className="ip-selected">Interpretations</p>
                <p>Observations</p>
                <p>Thesis notes</p>
              </div>
              <article>
                <div className="ip-section-label">
                  EXAMPLE INTERPRETATION · 07 OCT 2026
                </div>
                <h3>What would change my mind?</h3>
                <p>
                  I want to understand the business before I form a view on{" "}
                  {company}. What evidence would separate a temporary setback
                  from a structural change?
                </p>
                <p>Start with the economics. Then test the assumptions.</p>
                <div className="ip-preview-question">
                  <span>OPEN QUESTION</span>
                  <p>Which part of this argument can I verify?</p>
                </div>
                <small>Written by you. Earlier versions stay readable.</small>
              </article>
            </div>
          ) : view === "Overview" ? (
            <article className="ip-preview-overview">
              <div>
                <div className="ip-section-label">MARKET SNAPSHOT</div>
                <h3>Price unavailable</h3>
                <p>
                  A quote appears only when a dated source is connected. Missing
                  data stays missing.
                </p>
              </div>
              <dl>
                <dt>Company</dt>
                <dd>{company}</dd>
                <dt>Market</dt>
                <dd>India</dd>
                <dt>Financials</dt>
                <dd>Awaiting sourced evidence</dd>
                <dt>Research</dt>
                <dd>Your notes and questions</dd>
              </dl>
            </article>
          ) : (
            <article className="ip-preview-skills">
              <h3>A method for the question at hand.</h3>
              {[
                "Investment checklist",
                "Red flags & forensics",
                "Thesis validation",
                "Devil’s advocate",
                "Competitive analysis",
              ].map((s, i) => (
                <div key={s}>
                  <span>0{i + 1}</span>
                  <strong>{s}</strong>
                  <span>Research method</span>
                </div>
              ))}
            </article>
          )}
        </div>
      </div>
      <div className="ip-preview-foot">
        <span>Questions first. Sources attached. History preserved.</span>
        <Link href="/login">Open your workspace →</Link>
      </div>
    </section>
  );
}

export function Landing({ page }: { page?: PublicPage }) {
  return (
    <div className="ip-public">
      <PublicHeader />
      <main id="main-content">
        {!page ? (
          <>
            <section className="ip-hero">
              <div className="ip-section-label">
                AN INVESTMENT RESEARCH WORKSPACE / INDIA
              </div>
              <h1>
                Your research.
                <br />A memory that lasts.
              </h1>
              <p className="ip-lede">For the work behind every investment.</p>
              <p>
                Write what you believe. Keep the evidence close.
                <br className="ip-desktop" /> Come back knowing where your
                thinking left off.
              </p>
              <div className="ip-actions">
                <Link className="ip-button" href="/login">
                  Start your research <span aria-hidden="true">→</span>
                </Link>
                <a href="#preview">Explore the workspace</a>
              </div>
            </section>
            <div id="preview">
              <ProductPreview />
            </div>
            <Features />
            <section className="ip-manifesto-teaser">
              <span className="ip-section-label">OUR PHILOSOPHY</span>
              <h2>
                Good research deserves
                <br />a second reading.
              </h2>
              <p>
                The hardest part is often remembering what you believed, and
                being honest when it changes.
              </p>
              <Link href="/manifesto">Read the manifesto →</Link>
            </section>
            <section className="ip-faq">
              <h2>A few things to know.</h2>
              {[
                [
                  "Who is Invest-pad for?",
                  "Investors researching Indian listed equities who want their questions, source material and written thinking in one place.",
                ],
                [
                  "Does it tell me what to buy?",
                  "No. The workspace supports research and records your reasoning. It does not issue buy, sell or hold recommendations, price targets, or conviction scores.",
                ],
                [
                  "What happens to my earlier notes?",
                  "Saved revisions create a new record. Earlier versions remain readable, alongside their original dates. AI proposals require your review.",
                ],
                [
                  "Where do the portfolio and filings come from?",
                  "Portfolio views use Trackr+ and its existing transaction ledger. Filings can be recorded or uploaded with sources. Automated Zip Filings retrieval and a market quote feed still need an approved connection.",
                ],
                [
                  "What does it cost?",
                  "Pricing is coming soon. No pricing plans or billing are offered on this page.",
                ],
              ].map(([q, a]) => (
                <details key={q}>
                  <summary>
                    {q}
                    <span aria-hidden="true">+</span>
                  </summary>
                  <p>{a}</p>
                </details>
              ))}
            </section>
          </>
        ) : page === "features" ? (
          <>
            <div className="ip-page-intro">
              <span className="ip-section-label">FEATURES</span>
              <h1>A place to do the work.</h1>
              <p>
                Writing, evidence and the portfolio, connected around a company.
              </p>
            </div>
            <ProductPreview />
            <Features />
          </>
        ) : page === "pricing" || page === "blog" ? (
          <section className="ip-coming">
            <span className="ip-section-label">{page.toUpperCase()}</span>
            <h1>Coming soon.</h1>
            <p>
              {page === "pricing"
                ? "We’re shaping a plan around the way you research. Pricing will be published here when it’s ready."
                : "Notes on research, investor memory and the discipline of changing your mind. We’ll share them here."}
            </p>
            <Link href="/">Back to Invest-pad →</Link>
          </section>
        ) : page === "manifesto" ? (
          <article className="ip-essay">
            <span className="ip-section-label">THE INVEST-PAD MANIFESTO</span>
            <h1>
              Remember why.
              <br />
              Be willing to reconsider.
            </h1>
            <p className="ip-lede">
              For investors who do the work, and want it to stay useful.
            </p>
            <p>
              Research accumulates in documents, notebooks and conversations.
              The reasoning gets harder to find just when it becomes most
              important. Invest-pad starts with a simple conviction: what you
              wrote should meet you again.
            </p>
            {principles.map(([h, p], i) => (
              <section key={h}>
                <span className="ip-section-label">0{i + 1}</span>
                <h2>{h}</h2>
                <p>{p}</p>
              </section>
            ))}
            <Link className="ip-button" href="/login">
              Start with a question →
            </Link>
          </article>
        ) : (
          <article className="ip-essay">
            <span className="ip-section-label">DOCS / GETTING STARTED</span>
            <h1>Your first research file.</h1>
            {[
              [
                "1. Open a company",
                "Sign in with your existing Trackr+ account. Open Companies and find a security by name, symbol or ISIN. Company identity is shared with the portfolio.",
              ],
              [
                "2. Write your questions",
                "Before research opens, save at least one question. Mark questions that must be answered before committing to a thesis as blocking.",
              ],
              [
                "3. Collect evidence and write",
                "Use Get filings to open the sources area. Cite or upload a document with its date and reference. Create an observation for a sourced fact, or an interpretation for your reasoning. Search notes and browse their kind to return to an idea.",
              ],
              [
                "4. Keep a history",
                "Save a revision to add to a note. Earlier versions remain readable. A thesis stays in draft until its measurable conditions and pre-mortem are present and blocking questions are answered.",
              ],
              [
                "5. Review a proposal",
                "A research method can propose writing. Compare the proposal, accept it as a new note, or discard it. A proposal does not change your commitments.",
              ],
              [
                "Connections and availability",
                "Portfolio screens use the existing Trackr+ ledger. Company facts come from recorded evidence, never invented quotes. The portfolio price path includes yfinance when available. A standalone company quote feed and automated Zip Filings retrieval are not connected in this build. Unavailable values are labelled. Pricing and Blog are coming soon.",
              ],
            ].map(([h, p]) => (
              <section key={h}>
                <h2>{h}</h2>
                <p>{p}</p>
              </section>
            ))}
            <Link className="ip-button" href="/login">
              Sign in →
            </Link>
          </article>
        )}
      </main>
      <Footer />
    </div>
  );
}
