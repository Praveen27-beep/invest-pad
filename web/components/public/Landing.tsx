"use client";

/**
 * Invest-pad's public pages: landing, features, manifesto, docs, pricing and blog.
 *
 * Ported from the earlier draft on the codex/invest-pad-ui branch (Landing.tsx, 16 Oct 2026)
 * and corrected against docs/00-inventory.md §4: only features that exist in this build,
 * Invest-pad's own login, no live prices or filings feed, no advice or regulatory claims.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NeuralBrain } from "./NeuralBrain";
import "./public.css";

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
        <Link className="ip-wordmark" href="/welcome">
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
          <Link className="ip-wordmark" href="/welcome">
            <span className="ip-mark" aria-hidden="true" />
            Invest-pad
          </Link>
          <p>Your research. Your thinking. Your AI.</p>
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
            {/* Published once the drafts in docs/legal/ have been reviewed by a lawyer. */}
            <span>Terms (coming soon)</span>
            <span>Privacy (coming soon)</span>
          </div>
        </div>
      </div>
      <div className="ip-footer-legal">
        <span>Built for Indian investors.</span>
        <span>Research and information, not investment advice.</span>
      </div>
    </footer>
  );
}

const principles = [
  [
    "A second brain.",
    "Your mind is for thinking, not for remembering. Every note, source, question and change of view is kept, dated and linked to the company it belongs to. When you open a name, the reasoning you had at the time is already waiting.",
  ],
  [
    "The decisive point, not the pile.",
    "Weeks of reading usually come down to one point: the governance worry, the share that held, the debt that didn't add up. Invest-pad asks you to write that point down when you decide, and puts it first when you come back.",
  ],
  [
    "Memory first, analysis second.",
    "Any model can summarise an annual report. Few know what you believed last March and why. Answers come from your own notes, documents and decisions, each statement tied to the passage it rests on.",
  ],
  [
    "A guardian on your own rules.",
    "Write how you invest and the limits you hold yourself to. When a decision or a holding cuts against them, Invest-pad asks the question you might not. It never tells you what to buy or sell.",
  ],
  [
    "Close the gaps.",
    "Most investing mistakes come from what you did not check: the note to the accounts you skipped, the risk nobody wrote down. Checklists you can edit, and a scan of new documents against your assumptions, are built to find those gaps.",
  ],
  [
    "The decision stays yours.",
    "AI suggests; you accept or dismiss. Facts stay separate from opinions and AI statements, and nothing you wrote is silently rewritten. The judgement, and the conviction, remain your own.",
  ],
];

const featureList = [
  [
    "01",
    "Remember why you decided",
    "Record each decision with the one reason that decided it and what would change your mind. Reopen the company months later and see the reason, what it rested on, and how each assumption stands now.",
  ],
  [
    "02",
    "Answers from your own research",
    "Ask a question and get an answer from your notes, documents and decisions, every statement quoting its source. If the quote isn't in the source, the statement is dropped. Ask from the Chrome side panel while you read.",
  ],
  [
    "03",
    "A thesis you can trace",
    "Thesis and assumptions with versions you can compare, evidence for and against, sourced facts kept apart from your judgement, and a check of new documents against what you assumed.",
  ],
  [
    "04",
    "Your rules, your portfolio",
    "Write how you invest and set your own limits, such as no position above 10%. Import holdings, see when a limit is crossed, and answer a monthly set of hard questions about your portfolio and watchlist.",
  ],
];

const moreFeatures = [
  "Linked notes with backlinks and a graph of how notes, documents and assumptions connect",
  "Upload annual reports, transcripts and spreadsheets (PDF, Excel, Word) and search every passage",
  "Red-flag and forensic-accounting checklists you can edit or write from scratch",
  "Ratios with the formula on screen: DuPont, cash conversion cycle, Beneish M-score, accruals and more",
  "A decision journal across every company",
  "Use your own model and key, including a local endpoint, with cost caps",
  "Read-only access from Claude and other MCP clients",
  "Export everything in one ZIP; delete a document or your account and it is gone",
];

function Features({ linkAll = true }: { linkAll?: boolean }) {
  return (
    <section className="ip-features" id="features">
      <div className="ip-section-head">
        <div>
          <div className="ip-section-label">Capabilities</div>
          <h2>Research that compounds instead of decaying</h2>
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

/** A still picture of the company overview. Fictional company, labelled as such. */
function ReopenCard() {
  return (
    <div className="ip-reopen" aria-label="Example of the company overview">
      <div className="ip-reopen-k">Last decision · Bought · 2 Mar 2026</div>
      <p className="ip-reopen-reason">“Market share held at ninety percent even after the coupling announcement.”</p>
      <div className="ip-reopen-k">It rested on</div>
      <div className="ip-reopen-row"><span className="ip-pill ok">Holds</span>Share stays above 80% of the day-ahead market</div>
      <div className="ip-reopen-row"><span className="ip-pill warn">Challenged</span>Coupling is delayed beyond FY27 <em>— new evidence against, 14 Oct</em></div>
      <div className="ip-reopen-k">Would change my mind</div>
      <div className="ip-reopen-row">Share below 80% for two quarters.</div>
      <div className="ip-reopen-note">Illustration with a fictional company.</div>
    </div>
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
                <i aria-hidden="true" /> The AI Investment Studio for Indian investors.
              </span>
              <h1>
                Remember why you bought, passed or <em>walked away.</em>
              </h1>
              <p className="ip-lede">
                Invest-pad remembers why you bought, passed, or walked away from a stock, so you don’t research
                it all over again. Your notes, documents, thesis and decisions in one place, with an AI that
                answers from your own research.
              </p>
              <div className="ip-actions">
                <Link className="ip-button" href="/login">
                  Sign in with an invite <span aria-hidden="true">→</span>
                </Link>
                <a className="ip-button ip-button--ghost" href="#preview">
                  See the overview
                </a>
              </div>
            </section>
            <div id="preview" className="ip-preview-wrap">
              <ReopenCard />
            </div>
            <Features />
            <section className="ip-manifesto-teaser">
              <span className="ip-section-label">Our philosophy</span>
              <h2>Your research. Your thinking. Your AI.</h2>
              <p>
                Research tools help you analyse. Very few help you remember. Invest-pad keeps the reasoning behind
                every decision, so your research compounds instead of being redone.
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
                    "Investors researching Indian listed companies who want their notes, source documents, reasoning and decisions in one place.",
                  ],
                  [
                    "Does it tell me what to buy?",
                    "No. It supports research and records your reasoning. It does not give buy, sell or hold recommendations, position sizes, price targets or conviction scores.",
                  ],
                  [
                    "What happens to my earlier notes and theses?",
                    "Every save is a new version. Earlier versions stay readable with their dates, and you can compare any two. AI suggestions need your acceptance.",
                  ],
                  [
                    "Where do documents and holdings come from?",
                    "You upload them: annual reports, transcripts and spreadsheets, and a holdings CSV from your broker or tracker. There is no live price feed or automatic filings download in this build.",
                  ],
                  [
                    "Which AI does it use?",
                    "The model you connect: your own key for an OpenAI-compatible service, or a local endpoint. Each answer quotes its sources, and cost caps apply.",
                  ],
                  [
                    "Can I take my data out?",
                    "Yes. Export everything as one ZIP at any time. Deleting a document removes its text and anything derived from it; deleting your account removes everything.",
                  ],
                  [
                    "What does it cost?",
                    "Pricing is coming soon. The beta is invite-only.",
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
              <h2>Start with a company you already know.</h2>
              <p>Upload what you read, write what you think, and record why you decided.</p>
              <Link className="ip-button" href="/login">
                Sign in with an invite <span aria-hidden="true">→</span>
              </Link>
            </section>
          </>
        ) : page === "features" ? (
          <>
            <div className="ip-page-intro">
              <span className="ip-section-label">Features</span>
              <h1>A place to do the work, and remember it.</h1>
              <p>Notes, documents, thesis, decisions and your portfolio, connected around each company.</p>
            </div>
            <ReopenCard />
            <Features linkAll={false} />
            <section className="ip-features" style={{ paddingTop: 32 }}>
              <div className="ip-section-label">Also in the box</div>
              <ul className="ip-more">
                {moreFeatures.map((f) => (<li key={f}>{f}</li>))}
              </ul>
            </section>
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
            <Link href="/welcome">Back to Invest-pad →</Link>
          </section>
        ) : page === "manifesto" ? (
          <article className="ip-essay">
            <span className="ip-section-label">The Invest-pad manifesto</span>
            <h1>
              Keep your mind
              <br />
              for thinking.
            </h1>
            <p className="ip-lede">Your research. Your thinking. Your AI.</p>
            <NeuralBrain />
            <p>
              An investor reads hundreds of pages on a company, writes notes in three places, and decides. Months
              later the price moves, a result lands, a friend asks why you own it, and the one point that decided
              it is gone. So the research is done again.
            </p>
            <p>
              Frontier models can read an annual report and follow an earnings call. They do not know how you think,
              what you assumed, or why you walked away last time. That memory is the part worth keeping, and it is
              yours.
            </p>
            <p>Invest-pad is built to keep it.</p>
            {principles.map(([h, p], i) => (
              <section key={h}>
                <span className="ip-section-label">0{i + 1}</span>
                <h2>{h}</h2>
                <p>{p}</p>
              </section>
            ))}
            <p className="ip-lede ip-essay-close">Research that compounds instead of decaying.</p>
            <Link className="ip-button" href="/login">
              Sign in with an invite →
            </Link>
          </article>
        ) : (
          <article className="ip-essay">
            <span className="ip-section-label">Docs · Getting started</span>
            <h1>Your first research file.</h1>
            {[
              [
                "1. Add a company",
                "Sign in with your Invest-pad account (invite-only during the beta) and add the company you are researching.",
              ],
              [
                "2. Bring in what you read",
                "Upload annual reports, transcripts and spreadsheets. Write notes and link them with [[Title]]. Save passages from any web page with the Chrome side panel.",
              ],
              [
                "3. Write the thesis",
                "Write your thesis and the assumptions it rests on. Mark which rest on a source and which are your judgement, and attach evidence for and against.",
              ],
              [
                "4. Record the decision",
                "When you buy, pass or stop, record the one reason that decided it and what would change your mind. Records are never edited; changes are new versions you can compare.",
              ],
              [
                "5. Ask, check, review",
                "Connect a model in Settings to ask questions answered from your own material, with every statement quoting its source. Run the checklists, use the Numbers tab, and import holdings to set your own limits.",
              ],
              [
                "What is not connected",
                "There is no live price feed and no automatic download of exchange filings in this build: documents and holdings come from your uploads. Pricing and Blog are coming soon.",
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
