/**
 * Formatting for the analytics screen.
 *
 * Local rather than lib/format.ts because the units differ and guessing is how a screen
 * ends up showing 3000% volatility. The API is explicit about which is which and so is
 * this file:
 *
 *   FRACTIONS  cagr, volatility, var_*, roe, net_margin, growth rates  -> pct()
 *   PERCENTS   weight, allocation pct, factor score, per-holding returns -> pp()
 *   RATIOS     pe, pb, beta, sharpe, interest cover -> ratio()
 *   MONEY      always a string on the wire -> money()
 */

export const EMPTY = "—";

/** Indian grouping: last three digits, then pairs. 51,43,761 — not 5,143,761. */
export function money(value: string | number | null | undefined, withSign = false): string {
  if (value == null || value === "") return EMPTY;
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return EMPTY;
  const negative = n < 0;
  let s = Math.round(Math.abs(n)).toString();
  if (s.length > 3) {
    const last3 = s.slice(-3);
    const rest = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    s = `${rest},${last3}`;
  }
  const sign = negative ? "-" : withSign ? "+" : "";
  return `${sign}₹${s}`;
}

/** A FRACTION (0.0295) rendered as a percentage (2.95%). */
export function pct(value: number | null | undefined, digits = 2, signed = false): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  const v = value * 100;
  return `${signed && v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** An ALREADY-PERCENT value (34.5) rendered as 34.50%. */
export function pp(value: number | null | undefined, digits = 2, signed = false): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${signed && value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function ratio(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return value.toFixed(digits);
}

export function signOf(value: number | string | null | undefined): "pos" | "neg" | null {
  if (value == null || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return null;
  return n >= 0 ? "pos" : "neg";
}

export function toneColor(sign: "pos" | "neg" | null): string | undefined {
  if (sign === "pos") return "var(--positive)";
  if (sign === "neg") return "var(--negative)";
  return undefined;
}
