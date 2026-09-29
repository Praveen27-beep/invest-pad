"use client";

/**
 * Skills (FE 17 core + advanced over BE 16-17 and 27-35): the eight research methods, as
 * versioned contracts.
 *
 * A method is published from the code-owned catalogue, never invented here. Publishing is an
 * explicit click that appends a version; disabling is another version, and old tasks keep the
 * version they ran. DECLARED IS NOT AVAILABLE: each method shows its availability truthfully,
 * and while no formula (BE-Q03) or source (BE-Q04) is approved, the methods that need them say
 * UNKNOWN with the exact gate -- "not approved" is shown differently from "no data". The
 * cross-method audit (BE 35) is shown as findings per method, never as one pass/fail.
 */

import { useFetch } from "@trackr/core";
import { rpaths, rwrite, type Catalogue, type Page, type Skill } from "@/lib/research-client";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

export default function Skills() {
  const { investorId, token } = useResearchAuth();
  const catalogue = useFetch<Catalogue>(investorId ? rpaths.catalogue(investorId) : null, undefined, token);
  const skills = useFetch<Page<Skill>>(investorId ? rpaths.skills(investorId) : null, { limit: 100 }, token);
  const { submit, pending, error } = useSubmit<Skill>();
  const published = new Map((skills.data?.items ?? []).map((s) => [s.id, s]));

  async function publish(skillId: string, enabled: boolean) {
    const method = catalogue.data?.methods.find((m) => m.skill_id === skillId);
    if (!method) return;
    const current = published.get(skillId);
    const body = { ...method.default, enabled, expected_version: current?.version ?? 0 };
    const saved = await submit(body, (key) =>
      rwrite.publishSkill({ investorId, token, idempotencyKey: key }, skillId, body)
    );
    if (saved) skills.refetch();
  }

  const c = catalogue.data;
  return (
    <div>
      <div className="ws-crumb">Research &middot; Skills</div>
      <h1 className="ws-h1">Skills</h1>
      <p className="ws-sub">
        Versioned research methods, each with inputs it requires, tools it may read with, and conclusions it
        is forbidden to reach. {c ? `Catalogue ${c.catalogue_version}, house rules ${c.house_rules_version}.` : ""}
      </p>
      {(catalogue.errorDetail || skills.errorDetail || error) && (
        <p className="ws-notice ws-notice--error">
          {describeError(error ?? catalogue.errorDetail ?? skills.errorDetail)}
        </p>
      )}
      {c?.methods.map((m) => {
        const current = published.get(m.skill_id);
        const availability = current?.availability ?? m.availability;
        return (
          <div key={m.skill_id} className="ws-panel">
            <div className="ws-row">
              <span className="ws-row-grow">
                <span className="ws-row-t">{m.default.name}</span>
                <span className="ws-row-m">
                  {m.task_route === "BUTLER_ONLY" ? "Butler selector (not a research method) · " : ""}
                  {current ? `published v${current.version}${current.enabled ? "" : " (disabled)"}` : "not published"}
                </span>
              </span>
              <span className="ws-chip">{availability.state === "READY" ? "inputs available" : "UNKNOWN — gaps below"}</span>
            </div>
            <p>{m.default.summary}</p>
            <details>
              <summary className="ws-field-label">Contract</summary>
              <div className="ws-field-label">Reads</div>
              <ul>
                {m.reads.map((r) => (
                  <li key={r.id}>
                    <span className="ws-mono">{r.id}</span>
                    {r.required ? " (required)" : ""} — {r.obligation}
                  </li>
                ))}
              </ul>
              <div className="ws-field-label">May read with</div>
              <p className="ws-mono">{m.default.permitted_tools.join(", ") || "only its pinned context"}</p>
              <div className="ws-field-label">Forbidden conclusions</div>
              <p className="ws-mono">{m.default.forbidden_conclusions.join(", ")}</p>
              {m.dependencies.length > 0 && (
                <>
                  <div className="ws-field-label">Dependencies</div>
                  <ul>
                    {m.dependencies.map((d) => (
                      <li key={d.id}>
                        <span className="ws-mono">{d.id}</span> — {d.status.toLowerCase()}
                        {d.gate ? ` (${d.gate})` : ""}: {d.description}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </details>
            {availability.missing.length > 0 && (
              <ul className="ws-reasons">
                {availability.missing.map((x) => (
                  <li key={`${x.kind}-${x.id}`} className="ws-mono">
                    {x.id}: {x.code}
                    {x.gate ? ` (${x.gate})` : ""}
                  </li>
                ))}
              </ul>
            )}
            <div className="ws-form-row">
              {(!current || !current.enabled) && (
                <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={pending} onClick={() => publish(m.skill_id, true)}>
                  {current ? `Re-enable as v${current.version + 1}` : "Publish v1"}
                </button>
              )}
              {current?.enabled && (
                <button type="button" className="ws-btn ws-btn--ghost ws-btn--sm" disabled={pending} onClick={() => publish(m.skill_id, false)}>
                  Disable as v{current.version + 1}
                </button>
              )}
            </div>
          </div>
        );
      })}
      {c && (
        <>
          {c.undeclared_methods.length > 0 && (
            <>
              <div className="ws-sechead">
                <h2>Not declared yet</h2>
                <div className="ws-hint">no contract, so nothing to run</div>
              </div>
              <p className="ws-mono ws-muted">{c.undeclared_methods.join(", ")}</p>
            </>
          )}
          <div className="ws-sechead">
            <h2>Calculators</h2>
            <div className="ws-hint">approved formulas only (BE-Q03)</div>
          </div>
          {(c.formulas?.approved.length ?? 0) === 0 ? (
            <p className="ws-muted">
              No formula is approved (registry <span className="ws-mono">{c.formulas?.registry_version ?? "unknown"}</span>).
              Every calculation answers “not approved” — nothing is estimated.
            </p>
          ) : (
            <ul>
              {c.formulas?.approved.map((f) => (
                <li key={`${f.formula_id}@${f.version}`} className="ws-mono">
                  {f.formula_id} v{f.version} — {f.title}
                  {f.kind === "SCENARIO" && !f.output_contract_approved ? " (output shape not approved)" : ""}
                </li>
              ))}
            </ul>
          )}
          <p className="ws-muted">
            Source adapters:{" "}
            {(c.source_adapters?.length ?? 0) === 0
              ? "none approved (BE-Q04) — nothing is fetched automatically."
              : c.source_adapters?.map((a) => `${a.adapter_id}${a.synthetic ? " (synthetic)" : ""}`).join(", ")}
          </p>
          {c.audit && (
            <>
              <div className="ws-sechead">
                <h2>Method audit</h2>
                <div className="ws-hint">each method against the shared house rules {c.house_rules_version}</div>
              </div>
              <ul>
                {c.audit.map((a) => (
                  <li key={a.method_key}>
                    <span className="ws-mono">{a.method_key}</span>:{" "}
                    {a.findings.length === 0 ? "no drift found in the structural checks" : a.findings.join(", ")}
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="ws-sechead">
            <h2>Tools</h2>
          </div>
          <p className="ws-muted">
            Available: <span className="ws-mono">{c.tools.available.join(", ")}</span>
          </p>
          <p className="ws-muted">
            Unavailable:{" "}
            <span className="ws-mono">
              {c.tools.unavailable.map((t) => `${t.name} (${t.code}, ${t.gate})`).join(", ")}
            </span>
          </p>
        </>
      )}
    </div>
  );
}
