"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkspaceDemo } from "./WorkspaceDemo";
import { NeuralBrain } from "./NeuralBrain";

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
          <p>Your entire investment routine, in one place. Everything you need to make better investment decisions.</p>
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
    "An army of specialists.",
    "Orchestrate agents that each do one job well: an initial report on a new name, a forensic pass through the accounts, a map of the competition, a review of management and governance. Each works from sources, shows its reasoning and hands the result back to you. You run the desk. They do the legwork.",
  ],
  [
    "Built for breadth.",
    "Active investors follow tens of names, sometimes hundreds. Nobody can hold all of that in their head, and nobody should try. Invest-pad brings the same depth of work to your whole watchlist, not just the two companies you found time for this month.",
  ],
  [
    "A second brain.",
    "Your mind is for thinking, not for remembering. Every question, source, note and change of view is kept, dated and linked to the company it belongs to. When you open a name, the research you did and the reasoning you had at the time are already waiting.",
  ],
  [
    "A guardian on your portfolio.",
    "Invest-pad keeps watching what you own and what you are considering. When a filing, a result or a change in the facts touches your thesis, it asks the question you might not: does the reason you bought still hold? It never tells you what to buy or sell. It makes sure you never decide without asking.",
  ],
  [
    "Close the gaps.",
    "Most investing mistakes are not failures of intelligence. They come from what you did not know: the note to the accounts you skipped, the competitor you never studied, the risk nobody wrote down. Invest-pad is built to find those gaps and fill them before they cost you.",
  ],
  [
    "The decision stays yours.",
    "Agents gather, analyse and challenge. They propose, and you review before anything is accepted. Sources stay separate from interpretation, and nothing you wrote is silently rewritten. The judgement, and the conviction, remain your own.",
  ],
];

const featureList = [
  [
    "01",
    "Every company, one workspace",
    "Open any of thousands of companies and get live price, fundamentals, earnings, and initial research one click apart. Track your portfolio and watchlists alongside your research.",
  ],
  [
    "02",
    "An AI analyst that shows its work",
    "Ask a real question and watch it pull the actual numbers, reason in the open, and answer in seconds.",
  ],
  [
    "03",
    "Research that runs on a schedule",
    "Set a monitor and the analyst reruns your question on time. The earnings recap, the filing watch, the weekly portfolio check: they run whether or not you remember to.",
  ],
  [
    "04",
    "Your process, not ours",
    "No philosophy baked in. Organize coverage like a codebase, in watchlists, themes, and folders, and teach the analyst your way of working with skills.",
  ],
];

function Features({ linkAll = true }: { linkAll?: boolean }) {
  return (
    <section className="ip-features" id="features">
      <div className="ip-section-head">
        <div>
          <div className="ip-section-label">Capabilities</div>
          <h2>Everything you need to build conviction</h2>
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

export function Landing({ page }: { page?: PublicPage }) {
  return (
    <div className="ip-public">
      <PublicHeader />
      <main id="main-content">
        {!page ? (
          <>
            <section className="ip-hero">
              <span className="ip-eyebrow">
                <i aria-hidden="true" /> The AI Investment Studio for Indian equities.
              </span>
              <h1>
                Built to make you a <em>dramatically better investor.</em>
              </h1>
              <p className="ip-lede">
                Your entire investment routine, in one place. Track portfolios and
                watchlists, get company reports and updates, research with AI, and
                build a second brain that remembers your investment thinking and
                way more.
              </p>
              <div className="ip-actions">
                <Link className="ip-button" href="/login">
                  Start your research <span aria-hidden="true">→</span>
                </Link>
                <a className="ip-button ip-button--ghost" href="#preview">
                  Explore the workspace
                </a>
              </div>
            </section>
            <div id="preview" className="ip-preview-wrap">
              <WorkspaceDemo />
            </div>
            <Features />
            <section className="ip-manifesto-teaser">
              <span className="ip-section-label">Our philosophy</span>
              <h2>
                Every investor deserves institutional-grade research capabilities.
              </h2>
              <p>
                Great investment research shouldn't be limited to institutions.
                With Invest-pad, you get specialised AI analysts to help you
                research deeper, challenge your thinking, and make better-informed
                investment decisions.
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
              Raise an army.
              <br />
              Keep your mind for thinking.
            </h1>
            <p className="ip-lede">
              Institutional-grade research, built for the individual investor.
            </p>
            <NeuralBrain />
            <p>
              For decades, deep research belonged to institutions. A fund could
              put a whole team on one company: one analyst on the accounts,
              another on the competition, another on management and governance,
              each doing one specialised job. The individual investor had
              evenings, a handful of filings and their own memory.
            </p>
            <p>
              Frontier models change who can do this work. A model can read an
              annual report, follow an earnings call and reason through a
              business. But a powerful engine is not yet a research desk. It
              needs a harness: a method for each task, the right sources, a
              memory of what came before, and a way to bring the work to the
              person who decides.
            </p>
            <p>That harness is Invest-pad.</p>
            {principles.map(([h, p], i) => (
              <section key={h}>
                <span className="ip-section-label">0{i + 1}</span>
                <h2>{h}</h2>
                <p>{p}</p>
              </section>
            ))}
            <p className="ip-lede ip-essay-close">
              Institutions had the analysts. Now you have the harness.
            </p>
            <Link className="ip-button" href="/login">
              Raise your research desk <span aria-hidden="true">→</span>
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
