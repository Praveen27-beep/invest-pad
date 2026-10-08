"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkspaceDemo } from "./WorkspaceDemo";

export type PublicPage = "features" | "pricing" | "blog" | "manifesto" | "docs";
const nav: [string, string][] = [
  ["Features", "/features"],
  ["Pricing", "/pricing"],
  ["Blog", "/blog"],
  ["Manifesto", "/manifesto"],
  ["Docs", "/docs"],
];

export function PublicHeader() {
  const pathname = usePathname();
  return (
    <header className="ip-header">
      <div className="ip-header-inner">
        <Link className="ip-wordmark" href="/">
          <span className="ip-mark" aria-hidden="true" />
          Invest-pad
        </Link>
        <nav aria-label="Main navigation">
          {nav.map(([label, href]) => (
            <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}>
              {label}
            </Link>
          ))}
        </nav>
        <div className="ip-header-actions">
          <Link className="ip-signin" href="/login">
            Sign in
          </Link>
          <details className="ip-mobile-nav">
            <summary aria-label="Open menu">
              <span aria-hidden="true" />
            </summary>
            <nav aria-label="Mobile navigation">
              {nav.map(([label, href]) => (
                <Link key={href} href={href}>
                  {label}
                </Link>
              ))}
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="ip-footer">
      <div className="ip-footer-inner">
        <div className="ip-footer-brand">
          <Link className="ip-wordmark" href="/">
            <span className="ip-mark" aria-hidden="true" />
            Invest-pad
          </Link>
          <p>A place for the work behind your conviction.</p>
        </div>
        <div className="ip-footer-cols">
          <div>
            <h4>Product</h4>
            <Link href="/features">Features</Link>
            <Link href="/pricing">Pricing</Link>
            <Link href="/docs">Docs</Link>
          </div>
          <div>
            <h4>Company</h4>
            <Link href="/manifesto">Manifesto</Link>
            <Link href="/blog">Blog</Link>
          </div>
          <div>
            <h4>Legal</h4>
            <Link href="/terms">Terms</Link>
            <Link href="/privacy">Privacy</Link>
          </div>
        </div>
      </div>
      <div className="ip-footer-legal">
        <span>Built for Indian listed equities.</span>
        <span>Research and information, not investment advice.</span>
      </div>
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

const featureList = [
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
];

function Features({ linkAll = true }: { linkAll?: boolean }) {
  return (
    <section className="ip-features" id="features">
      <div className="ip-section-head">
        <div>
          <div className="ip-section-label">The workspace</div>
          <h2>
            Keep the company.
            <br />
            Keep your thinking.
          </h2>
        </div>
        {linkAll && (
          <Link className="ip-text-link" href="/features">
            All features <span aria-hidden="true">→</span>
          </Link>
        )}
      </div>
      <div className="ip-feature-grid">
        {featureList.map(([n, title, body]) => (
          <article className="ip-feature" key={n}>
            <span>{n}</span>
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

const sources = [
  "CSV import",
  "Broker tradebooks",
  "Contract-note PDFs",
  "Gmail forwarding",
  "Manual entry",
];

const steps = [
  [
    "Ask",
    "Write the question first.",
    "Before research opens, save what you need to know. Blocking questions keep a thesis in draft until they are answered.",
  ],
  [
    "Gather",
    "Bring evidence with its source.",
    "Cite filings and annual reports with their dates. Observations carry sources; interpretations stay visibly yours.",
  ],
  [
    "Return",
    "Keep every version.",
    "A revision adds to the record and never erases it. Reopen a company and meet the reasoning you actually had.",
  ],
];

export function Landing({ page }: { page?: PublicPage }) {
  return (
    <div className="ip-public">
      <PublicHeader />
      <main id="main-content">
        {!page ? (
          <>
            <section className="ip-hero">
              <span className="ip-eyebrow">
                <i aria-hidden="true" /> A research workspace for Indian equities
              </span>
              <h1>
                Your investment research, <em>all together.</em>
              </h1>
              <p className="ip-lede">
                Explore companies, keep your notes close, and work through questions
                with AI. One place to understand what you own, and why.
              </p>
              <div className="ip-actions">
                <Link className="ip-button" href="/login">
                  Start your research <span aria-hidden="true">→</span>
                </Link>
                <a className="ip-button ip-button--ghost" href="#preview">
                  Explore the workspace
                </a>
              </div>
              <ul className="ip-hero-facts" aria-label="Principles">
                <li>Securities keyed by ISIN</li>
                <li>Revisions never overwrite</li>
                <li>No buy or sell calls</li>
                <li>No broker passwords stored</li>
              </ul>
            </section>
            <div id="preview" className="ip-preview-wrap">
              <WorkspaceDemo />
            </div>
            <section className="ip-sources" aria-label="Ways to bring your portfolio">
              <p>
                Bring the record you already keep.
                <span>File and email based. Read only, always.</span>
              </p>
              <ul>
                {sources.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </section>
            <Features />
            <section className="ip-steps">
              <div className="ip-section-label">How it works</div>
              <h2>A method you can return to.</h2>
              <ol>
                {steps.map(([k, h, p], i) => (
                  <li key={k}>
                    <span>
                      0{i + 1} · {k}
                    </span>
                    <h3>{h}</h3>
                    <p>{p}</p>
                  </li>
                ))}
              </ol>
            </section>
            <section className="ip-manifesto-teaser">
              <span className="ip-section-label">Our philosophy</span>
              <h2>
                Good research deserves
                <br />a second reading.
              </h2>
              <p>
                The hardest part is often remembering what you believed, and
                being honest when it changes.
              </p>
              <Link className="ip-button ip-button--light" href="/manifesto">
                Read the manifesto <span aria-hidden="true">→</span>
              </Link>
            </section>
            <section className="ip-faq">
              <div>
                <div className="ip-section-label">FAQ</div>
                <h2>A few things to know.</h2>
                <p>
                  More in the <Link href="/docs">documentation</Link>.
                </p>
              </div>
              <div className="ip-faq-list">
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
                    <span className="ip-faq-icon" aria-hidden="true" />
                  </summary>
                  <p>{a}</p>
                </details>
              ))}
              </div>
            </section>
            <section className="ip-cta">
              <h2>Start with a question.</h2>
              <p>Open a company, write what you need to know, and keep the answer.</p>
              <Link className="ip-button" href="/login">
                Start your research <span aria-hidden="true">→</span>
              </Link>
            </section>
          </>
        ) : page === "features" ? (
          <>
            <div className="ip-page-intro">
              <span className="ip-section-label">Features</span>
              <h1>A place to do the work.</h1>
              <p>
                Writing, evidence and the portfolio, connected around a company.
              </p>
            </div>
            <WorkspaceDemo />
            <Features linkAll={false} />
          </>
        ) : page === "pricing" || page === "blog" ? (
          <section className="ip-coming">
            <span className="ip-section-label">{page}</span>
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
            <span className="ip-section-label">The Invest-pad manifesto</span>
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
            <span className="ip-section-label">Docs · Getting started</span>
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
