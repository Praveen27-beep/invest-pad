import Link from "next/link";
import {
  CURRENT_TOS_VERSION,
  TERMS_INTRO,
  TERMS_SECTIONS,
  type LegalBlock,
  type LegalRun,
} from "@trackr/core";

/**
 * Terms of Service and Privacy Policy, in Workspace's own visual language.
 *
 * THE WORDS ARE SHARED, THE APPEARANCE IS NOT. Every sentence comes from
 * `@trackr/core`'s `legal.ts`, so there is exactly one copy of the legal text for one
 * backend and one `app_user.tos_version`. Two hand-maintained copies would mean two accounts
 * agreed to different text under the same version string, and the acceptance records would be
 * wrong for one of them. What this file owns is the rendering: Workspace tokens, Workspace
 * spacing, Workspace panels.
 *
 * PUBLIC. Reachable with no session -- it has to be, because it is linked from registration,
 * and nobody can be asked to accept terms they must sign in to read. Signed in, it renders
 * inside this app's own chrome via the shell, which is what "signed-in legal pages use that
 * app's portfolio hosting" means: the same route, hosted two ways, and no link to the other
 * product's domain in either case.
 *
 * A server component. There is nothing interactive here, so there is no reason to ship it to
 * the browser as one.
 */
export default function Terms() {
  return (
    <main className="ws-legal">
      <p className="ws-eyebrow">Trackr Workspace &middot; version {CURRENT_TOS_VERSION}</p>
      <h1 className="ws-h1" style={{ fontSize: 26, marginTop: 8 }}>
        Terms of Service &amp; Privacy Policy
      </h1>
      <p className="ws-sub" style={{ marginTop: 12 }}>
        {TERMS_INTRO.map((run, index) => (
          <Run key={index} run={run} />
        ))}
      </p>

      {TERMS_SECTIONS.map((section) => (
        <section key={section.title} className="ws-legal-section">
          <h2 className="ws-legal-heading">{section.title}</h2>
          {section.blocks.map((block, index) => (
            <Block key={index} block={block} />
          ))}
        </section>
      ))}

      <p className="ws-sub" style={{ marginTop: 32 }}>
        <Link href="/">&larr; Back to Portfolio</Link>
      </p>
    </main>
  );
}

function Block({ block }: { block: LegalBlock }) {
  if (block.kind === "list") {
    return (
      <ul className="ws-legal-list">
        {block.runs.map((item, index) => (
          <li key={index}>
            {item.map((run, runIndex) => (
              <Run key={runIndex} run={run} />
            ))}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p className="ws-legal-body">
      {block.runs[0]?.map((run, index) => (
        <Run key={index} run={run} />
      ))}
    </p>
  );
}

/**
 * One run of text.
 *
 * `link` is always an internal path -- the shared content carries no external or
 * cross-product URLs -- so it is safe to hand straight to `next/link` and stays on this origin.
 */
function Run({ run }: { run: LegalRun }) {
  if (run.link) return <Link href={run.link}>{run.text}</Link>;
  if (run.code) return <code className="ws-mono">{run.text}</code>;
  if (run.emphasis) return <strong>{run.text}</strong>;
  return <>{run.text}</>;
}
