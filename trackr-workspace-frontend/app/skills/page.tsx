"use client";

import Link from "next/link";
import { useFetch } from "@trackr/core";
import {
  rpaths,
  rwrite,
  type Catalogue,
  type Page,
  type Skill,
} from "@/lib/research-client";
import {
  describeError,
  useResearchAuth,
  useSubmit,
} from "@/lib/research-hooks";

/** Same versioned catalogue and publish contract, with implementation details kept off the reading surface. */
export default function Skills() {
  const { investorId, token } = useResearchAuth();
  const catalogue = useFetch<Catalogue>(
    investorId ? rpaths.catalogue(investorId) : null,
    undefined,
    token,
  );
  const skills = useFetch<Page<Skill>>(
    investorId ? rpaths.skills(investorId) : null,
    { limit: 100 },
    token,
  );
  const { submit, pending, error } = useSubmit<Skill>();
  const published = new Map((skills.data?.items ?? []).map((s) => [s.id, s]));
  async function publish(skillId: string, enabled: boolean) {
    const method = catalogue.data?.methods.find((m) => m.skill_id === skillId);
    if (!method) return;
    const current = published.get(skillId);
    const body = {
      ...method.default,
      enabled,
      expected_version: current?.version ?? 0,
    };
    if (
      await submit(body, (key) =>
        rwrite.publishSkill(
          { investorId, token, idempotencyKey: key },
          skillId,
          body,
        ),
      )
    )
      skills.refetch();
  }
  const methods =
    catalogue.data?.methods.filter((m) => m.task_route === "TASKS") ?? [];
  return (
    <article className="ip-research-section">
      <div className="ws-crumb">Research / Skills</div>
      <h1 className="ws-h1">Your methods, ready to return to.</h1>
      <p className="ws-sub">
        A checklist for the first reading. Forensics for the numbers. Thesis
        validation and counterarguments for the conviction. Each method keeps
        its sources and leaves the decision to you.
      </p>
      {(catalogue.loading || skills.loading) && (
        <p role="status">Loading research methods…</p>
      )}
      {(catalogue.errorDetail || skills.errorDetail || error) && (
        <p className="ws-notice ws-notice--error">
          {describeError(error ?? catalogue.errorDetail ?? skills.errorDetail)}
        </p>
      )}
      {methods.map((m, i) => {
        const current = published.get(m.skill_id);
        const availability = current?.availability ?? m.availability;
        return (
          <section className="ip-skill" key={m.skill_id}>
            <div>
              <span className="ws-mono ws-muted">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h2>{m.default.name}</h2>
              <span className="ws-hint">
                {current?.enabled
                  ? `In your practice · v${current.version}`
                  : "Not enabled"}
              </span>
            </div>
            <p>{m.default.summary}</p>
            <details>
              <summary>Read the method</summary>
              <p className="ws-verbatim">{m.default.method}</p>
              <h3>Source discipline</h3>
              <ul>
                {m.default.citation_rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              <p>
                Research only. This method cannot make a decision, change a
                commitment, or issue a recommendation for you.
              </p>
            </details>
            {availability.state !== "READY" && (
              <p className="ws-hint">
                Not ready to run. Required evidence or research access is
                unavailable; no result will be invented.
              </p>
            )}
            <div className="ws-form-actions">
              <button
                className="ws-btn ws-btn--sm"
                disabled={pending || skills.loading || Boolean(skills.error)}
                onClick={() => publish(m.skill_id, !current?.enabled)}
              >
                {current?.enabled
                  ? "Remove from my practice"
                  : "Add to my practice"}
              </button>
              {current?.enabled && (
                <Link
                  className="ws-btn ws-btn--ghost ws-btn--sm"
                  href="/explorer"
                >
                  Choose a company
                </Link>
              )}
            </div>
          </section>
        );
      })}
      {catalogue.data && !methods.length && (
        <p className="ws-empty">No research methods are available yet.</p>
      )}
      <p className="ws-muted">
        Past research keeps the version of the method it used. Changes apply to
        future work.
      </p>
    </article>
  );
}
