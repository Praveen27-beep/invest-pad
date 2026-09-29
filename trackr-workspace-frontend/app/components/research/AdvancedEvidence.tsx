"use client";

/**
 * FE 17 advanced pass over BE 27-29: approved calculators, approved external sources and dated
 * events, for one company.
 *
 * WHAT IS NOT APPROVED IS SAID, NOT HIDDEN. With no approved formula (BE-Q03) the calculator
 * says so and offers nothing to click; with no approved source adapter (BE-Q04) the refresh
 * control says so. Nothing here fabricates a value, a source or a date to fill the space.
 *
 * NUMBERS COME FROM THE SERVER. A calculation's value is the decimal string the engine returned,
 * shown verbatim with its expression and every input -- never parsed, rounded or restated here.
 * Scenario assumptions are YOURS: each needs a value, a unit and your reason, and none is
 * prefilled. There is no default rate, multiple or horizon.
 *
 * EVENTS: scheduled, observed, claimed and cancelled are shown as distinct states. A claimed
 * (rumoured) event has no date. Only a person's recheck makes an event VERIFIED.
 */

import { useState } from "react";
import { useFetch } from "@trackr/core";
import type { Fact, Page } from "@/lib/research-api";
import { paths } from "@/lib/research-api";
import {
  callTool,
  rpaths,
  rwrite,
  type ApprovedFormula,
  type AssumptionInput,
  type Catalogue,
  type RefreshSummary,
  type ResearchEvent,
  type ToolResponse,
} from "@/lib/research-client";
import { describeError, useResearchAuth, useSubmit } from "@/lib/research-hooks";

export function AdvancedEvidence({ isin }: { isin: string }) {
  const { investorId, token } = useResearchAuth();
  const catalogue = useFetch<Catalogue>(investorId ? rpaths.catalogue(investorId) : null, undefined, token);
  const facts = useFetch<Page<Fact>>(investorId ? paths.companyFacts(investorId, isin) : null, { limit: 100 }, token);
  const events = useFetch<ResearchEvent[]>(investorId ? rpaths.events(investorId, isin) : null, undefined, token);
  const c = catalogue.data;

  return (
    <div className="ws-stack">
      <div className="ws-sechead">
        <h2>Approved calculations</h2>
        <div className="ws-hint">computed by the server from verified facts; never estimated</div>
      </div>
      {c && <Calculator isin={isin} formulas={c.formulas?.approved ?? []} registry={c.formulas?.registry_version ?? "unknown"} facts={facts.data?.items ?? []} />}

      <div className="ws-sechead">
        <h2>External sources</h2>
        <div className="ws-hint">retrieved only through an approved adapter</div>
      </div>
      {c && <Refresh isin={isin} adapters={c.source_adapters ?? []} onDone={() => { facts.refetch(); events.refetch(); }} />}

      <div className="ws-sechead">
        <h2>Dated events</h2>
        <div className="ws-hint">published events only — not a feed</div>
      </div>
      {events.errorDetail ? (
        <p className="ws-muted">{describeError(events.errorDetail)}</p>
      ) : (
        <EventList events={events.data ?? []} onChanged={events.refetch} />
      )}
    </div>
  );
}

// --- calculator -------------------------------------------------------------------------------

function Calculator({ isin, formulas, registry, facts }: { isin: string; formulas: ApprovedFormula[]; registry: string; facts: Fact[] }) {
  const { investorId, token } = useResearchAuth();
  const usable = formulas.filter((f) => f.kind === "METRIC" || f.output_contract_approved);
  const [chosen, setChosen] = useState<string>("");
  const [factIds, setFactIds] = useState<string[]>([]);
  const [assumptions, setAssumptions] = useState<Record<string, AssumptionInput>>({});
  const [result, setResult] = useState<ToolResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  if (usable.length === 0) {
    return (
      <p className="ws-notice">
        No formula is approved on this server (registry <span className="ws-mono">{registry}</span>, BE-Q03). Nothing can
        be calculated, and nothing is estimated in its place.
      </p>
    );
  }
  const formula = usable.find((f) => `${f.formula_id}@${f.version}` === chosen) ?? null;
  const verified = facts.filter((f) => f.verification === "VERIFIED" && !f.superseded_by);

  async function run() {
    if (!formula || !investorId) return;
    setBusy(true);
    setError(null);
    try {
      const args: Record<string, unknown> = {
        formula_id: formula.formula_id,
        formula_version: formula.version,
        fact_ids: factIds,
      };
      if (formula.kind === "SCENARIO") {
        args.assumptions = formula.assumptions.map((a) => ({
          name: a.name,
          value: assumptions[a.name]?.value ?? "",
          unit: a.unit,
          reason: assumptions[a.name]?.reason ?? "",
        }));
      }
      setResult(await callTool(investorId, token, formula.kind === "SCENARIO" ? "calculate_valuation" : "calculate_financial_metrics", isin, args));
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ws-panel">
      <label className="ws-field">
        <span className="ws-field-label">Approved formula (id and version — there is no “latest”)</span>
        <select className="ws-input" value={chosen} onChange={(e) => { setChosen(e.target.value); setResult(null); }}>
          <option value="">Choose…</option>
          {usable.map((f) => (
            <option key={`${f.formula_id}@${f.version}`} value={`${f.formula_id}@${f.version}`}>
              {f.title} — {f.formula_id} v{f.version} ({f.kind.toLowerCase()})
            </option>
          ))}
        </select>
      </label>
      {formula && (
        <>
          <div className="ws-field-label">Inputs it requires</div>
          <ul>
            {formula.inputs.map((i) => (
              <li key={i.name} className="ws-mono">
                {i.name}: {i.metric} · {i.basis} · {i.unit} · {i.cadence} · {i.period_role.toLowerCase()} period
              </li>
            ))}
          </ul>
          <div className="ws-field-label">Verified facts to use</div>
          {verified.length === 0 ? (
            <p className="ws-muted">No verified, current fact is held for this company. Record and verify one first.</p>
          ) : (
            <ul>
              {verified.map((f) => (
                <li key={f.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={factIds.includes(f.id)}
                      onChange={(e) => setFactIds(e.target.checked ? [...factIds, f.id] : factIds.filter((x) => x !== f.id))}
                    />{" "}
                    <span className="ws-mono">
                      {f.metric} {f.basis} {f.unit} {f.period_start}..{f.period_end} = {f.numeric_value ?? f.text_value ?? String(f.boolean_value)}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {formula.kind === "SCENARIO" && (
            <>
              <div className="ws-field-label">Your assumptions (each required; nothing is defaulted)</div>
              {formula.assumptions.map((a) => (
                <div key={a.name} className="ws-form-row">
                  <span className="ws-mono">{a.name} ({a.unit}{a.minimum !== null || a.maximum !== null ? `, ${a.minimum ?? "−∞"}…${a.maximum ?? "∞"}` : ""})</span>
                  <input
                    className="ws-input"
                    inputMode="decimal"
                    placeholder="value"
                    value={assumptions[a.name]?.value ?? ""}
                    onChange={(e) => setAssumptions({ ...assumptions, [a.name]: { name: a.name, unit: a.unit, reason: assumptions[a.name]?.reason ?? "", value: e.target.value } })}
                  />
                  <input
                    className="ws-input"
                    placeholder="your reason"
                    value={assumptions[a.name]?.reason ?? ""}
                    onChange={(e) => setAssumptions({ ...assumptions, [a.name]: { name: a.name, unit: a.unit, value: assumptions[a.name]?.value ?? "", reason: e.target.value } })}
                  />
                </div>
              ))}
              <p className="ws-muted">A scenario is arithmetic on your assumptions — not a target, a fair value or advice.</p>
            </>
          )}
          <div className="ws-form-row">
            <button type="button" className="ws-btn ws-btn--primary ws-btn--sm" disabled={busy || factIds.length === 0} onClick={run}>
              Calculate
            </button>
          </div>
        </>
      )}
      {error && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
      {result && <CalculationView response={result} />}
    </div>
  );
}

export function CalculationView({ response }: { response: ToolResponse }) {
  const t = response.calculation;
  return (
    <div className="ws-rendered">
      <p className="ws-row-t">
        {response.status === "OK" && t?.value != null
          ? <>Result: <span className="ws-mono">{t.value}</span> {t.unit}</>
          : response.status === "CONFLICT"
            ? "Conflicting verified inputs — nothing was computed, both are cited."
            : "Not computed (UNKNOWN)."}
      </p>
      {t?.expression && <p className="ws-mono">{t.expression}</p>}
      {t?.period && <p className="ws-muted">Period {t.period.period_start} … {t.period.period_end} ({t.period.cadence.toLowerCase()})</p>}
      {t && t.assumptions.length > 0 && (
        <ul>
          {t.assumptions.map((a) => (
            <li key={a.operand}>
              <span className="ws-chip">assumption</span> <span className="ws-mono">{a.operand} = {a.value} {a.unit}</span> — “{a.reason}”
            </li>
          ))}
        </ul>
      )}
      {response.notices.length > 0 && (
        <ul className="ws-reasons">
          {response.notices.map((n, i) => (
            <li key={i} className="ws-mono">{n.message}</li>
          ))}
        </ul>
      )}
      {response.conflicts.map((c, i) => (
        <p key={i} className="ws-notice">{c.claim}: {c.description} (sources {c.source_ids.map((s) => s.slice(0, 8)).join(", ")})</p>
      ))}
      {t && (
        <p className="ws-muted ws-mono">
          {t.formula_id} v{t.formula_version} · registry {t.registry_version} · {t.engine_version}
        </p>
      )}
    </div>
  );
}

// --- refresh ----------------------------------------------------------------------------------

function Refresh({ isin, adapters, onDone }: { isin: string; adapters: { adapter_id: string; synthetic: boolean; source_types: string[] }[]; onDone: () => void }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending, error } = useSubmit<RefreshSummary>();
  const [adapterId, setAdapterId] = useState("");
  const [periods, setPeriods] = useState("");
  const [summary, setSummary] = useState<RefreshSummary | null>(null);

  if (adapters.length === 0) {
    return (
      <p className="ws-notice">
        No source adapter is approved on this server (BE-Q04). Nothing is fetched automatically; cite or upload a
        source yourself above.
      </p>
    );
  }
  async function go() {
    const body = { adapter_id: adapterId, periods: periods.split(",").map((p) => p.trim()).filter(Boolean) };
    const out = await submit(body, (key) => rwrite.refreshSources({ investorId, token, idempotencyKey: key }, isin, body));
    if (out) {
      setSummary(out);
      onDone();
    }
  }
  return (
    <div className="ws-panel">
      <div className="ws-form-row">
        <select className="ws-input" value={adapterId} onChange={(e) => setAdapterId(e.target.value)}>
          <option value="">Adapter…</option>
          {adapters.map((a) => (
            <option key={a.adapter_id} value={a.adapter_id}>
              {a.adapter_id}{a.synthetic ? " (synthetic test data)" : ""}
            </option>
          ))}
        </select>
        <input className="ws-input" placeholder="periods, e.g. FY2024, FY2023 (at most ten)" value={periods} onChange={(e) => setPeriods(e.target.value)} />
        <button type="button" className="ws-btn ws-btn--sm" disabled={pending || !adapterId || !periods.trim()} onClick={go}>
          Refresh
        </button>
      </div>
      {error != null && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
      {summary && (
        <div className="ws-rendered">
          {summary.synthetic && <p className="ws-chip">synthetic test data — not a real source</p>}
          <p>
            {summary.replayed ? "Already recorded (retry). " : ""}
            {summary.sources.length} new source(s), {summary.duplicates.length} unchanged, {summary.revisions.length} revision(s),{" "}
            {summary.facts.length} unverified fact(s), {summary.events.length} event(s).
          </p>
          {summary.unknowns.length > 0 && (
            <>
              <div className="ws-field-label">Not recorded, and why</div>
              <ul className="ws-reasons">
                {summary.unknowns.map((u, i) => (
                  <li key={i} className="ws-mono">{u.code}{u.origin_item_id ? ` · ${String(u.origin_item_id)}` : ""}{u.metric ? ` · ${String(u.metric)}` : ""}</li>
                ))}
              </ul>
            </>
          )}
          {summary.conflicts.length > 0 && <p className="ws-notice">Sources disagree on {summary.conflicts.length} value(s); both are kept and neither is preferred.</p>}
          <p className="ws-muted">Extracted values are unverified until you recheck each one against its source.</p>
        </div>
      )}
    </div>
  );
}

// --- events -----------------------------------------------------------------------------------

const STATUS_LABEL: Record<ResearchEvent["status"], string> = {
  SCHEDULED: "scheduled (published future date)",
  OBSERVED: "observed (happened, filed)",
  CLAIMED: "claimed by a third party — not an event, no date",
  CANCELLED: "cancelled",
};

function EventList({ events, onChanged }: { events: ResearchEvent[]; onChanged: () => void }) {
  const { investorId, token } = useResearchAuth();
  const { submit, pending, error } = useSubmit<ResearchEvent>();
  const [reference, setReference] = useState<Record<string, string>>({});
  if (events.length === 0) return <p className="ws-muted">No event is held for this company.</p>;

  async function verify(e: ResearchEvent) {
    const body = { verification_reference: reference[e.id] ?? "", expected_event_id: e.id };
    const out = await submit(body, (key) => rwrite.verifyEvent({ investorId, token, idempotencyKey: key }, e.id, body));
    if (out) onChanged();
  }
  return (
    <div>
      {error != null && <p className="ws-notice ws-notice--error">{describeError(error)}</p>}
      {events.map((e) => (
        <div key={e.id} className="ws-row">
          <span className="ws-row-grow">
            <span className="ws-row-t">
              {e.event_type.replace(/_/g, " ").toLowerCase()} — {STATUS_LABEL[e.status]}
            </span>
            <span className="ws-row-m">
              {e.event_date ? `date ${e.event_date}` : `date ${e.date_precision.toLowerCase()}`}
              {e.period_start ? ` · period ${e.period_start}…${e.period_end}` : ""} · published {e.publication_date} · retrieved{" "}
              {e.retrieved_at.slice(0, 10)} · {e.locator}
              {e.reschedules_id ? ` · moves ${e.reschedules_id.slice(0, 8)}` : ""}
              {e.rescheduled_by.length ? ` · moved by ${e.rescheduled_by.map((x) => x.slice(0, 8)).join(", ")}` : ""}
              {e.superseded_by ? " · rechecked copy exists" : ""}
            </span>
            <span className="ws-muted">“{e.description}”</span>
          </span>
          <span className="ws-chip">{e.verification.toLowerCase()}</span>
          {e.verification === "UNVERIFIED" && !e.superseded_by && e.status !== "CLAIMED" && (e.date_precision === "EXACT" || e.status === "CANCELLED") && (
            <span className="ws-form-row">
              <input
                className="ws-input"
                placeholder="where you checked it"
                value={reference[e.id] ?? ""}
                onChange={(x) => setReference({ ...reference, [e.id]: x.target.value })}
              />
              <button type="button" className="ws-btn ws-btn--sm" disabled={pending || !(reference[e.id] ?? "").trim()} onClick={() => verify(e)}>
                I rechecked this
              </button>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
