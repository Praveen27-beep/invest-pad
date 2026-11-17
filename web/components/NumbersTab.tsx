"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type CalcInfo = { key: string; label: string; inputs: string[]; formula: string; unit: string };
type Result = {
  label: string; formula: string; unit: string; value: string | null; not_meaningful: string | null;
  inputs: Record<string, string>; steps: Record<string, string>;
};

const words = (k: string) => k.replace(/_t$/, " (this year)").replace(/_prior$/, " (prior year)").replaceAll("_", " ");
const show = (v: string, unit: string) => {
  const n = Number(v).toLocaleString("en-IN", { maximumFractionDigits: unit === "score" ? 3 : 2 });
  return unit === "%" ? `${n}%` : unit === "x" ? `${n}x` : unit === "days" ? `${n} days` : n;
};

/** Ratios with the formula on screen. The arithmetic is done by tested code on the server,
 *  never by the model; inputs are whatever the user reads off the filings. */
export default function NumbersTab() {
  const [calcs, setCalcs] = useState<CalcInfo[]>([]);
  const [key, setKey] = useState("roe");
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<CalcInfo[]>("/calc").then(setCalcs).catch(() => {}); }, []);
  const calc = calcs.find((c) => c.key === key);
  if (!calc) return null;

  return (
    <>
      <p className="empty">
        Type numbers from the annual report (any one currency unit, used consistently). The formula is shown with
        the result so you can check it by hand. A ratio over a zero or negative base is reported as not meaningful.
      </p>
      <div className="card stack">
        <label className="field">Calculation
          <select value={key} onChange={(e) => { setKey(e.target.value); setResult(null); setError(""); }}>
            {calcs.map((c) => (<option key={c.key} value={c.key}>{c.label}</option>))}
          </select>
        </label>
        <div className="small muted">{calc.formula}</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(14rem, 1fr))", gap: ".6rem" }}>
          {calc.inputs.map((i) => (
            <label className="field" key={i}>{words(i)}
              <input type="text" inputMode="decimal" value={values[i] ?? ""} aria-label={words(i)}
                onChange={(e) => setValues({ ...values, [i]: e.target.value })} />
            </label>
          ))}
        </div>
        <div className="row">
          <button className="primary" onClick={async () => {
            setError("");
            try {
              const inputs = Object.fromEntries(calc.inputs.map((i) => [i, values[i] ?? ""]));
              setResult(await api<Result>(`/calc/${key}`, { method: "POST", body: { inputs } }));
            } catch (e) { setResult(null); setError((e as Error).message); }
          }}>Calculate</button>
          {error && <span className="error" role="alert">{error}</span>}
        </div>
      </div>
      {result && (
        <div className="card" role="status" style={{ marginTop: "1rem" }}>
          <div className="snip">{result.label}</div>
          <p style={{ fontSize: "1.4rem", margin: ".3rem 0" }}>
            {result.value === null ? `Not meaningful — ${result.not_meaningful}` : show(result.value, result.unit)}
          </p>
          {Object.keys(result.steps).length > 0 && (
            <ul className="small">{Object.entries(result.steps).map(([k, v]) => (<li key={k}>{k}: {Number(v).toLocaleString("en-IN", { maximumFractionDigits: 4 })}</li>))}</ul>
          )}
          <div className="small muted">Formula: {result.formula}</div>
        </div>
      )}
    </>
  );
}
