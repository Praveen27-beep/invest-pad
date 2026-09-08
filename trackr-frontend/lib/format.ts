/**
 * Display-only formatting. Every value here is already computed server-side in the
 * Decimal domain (CLAUDE.md rule 1) -- these helpers never feed a result back into a
 * calculation, they only render one for a human to read.
 */

/**
 * What a table cell shows when there is genuinely no value for it.
 *
 * One exported constant rather than a literal repeated down every table component: the
 * glyph was hardcoded in nine places, so changing it meant finding all nine, and any one
 * of them drifting out of step would look like a rendering bug rather than a typo.
 *
 * It is deliberately NOT a zero. A blank cell says "nothing here"; a zero is a figure,
 * and printing one for an absent value is the display-layer version of the mistake
 * CLAUDE.md rule 4 forbids in the engine.
 */
export const EMPTY_VALUE = "\u2014";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const inrPrecise = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

export function formatMoney(value: string | null | undefined, precise = false): string {
  if (value === null || value === undefined) return EMPTY_VALUE;
  const n = Number(value);
  if (Number.isNaN(n)) return EMPTY_VALUE;
  return (precise ? inrPrecise : inr).format(n);
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return EMPTY_VALUE;
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined) return EMPTY_VALUE;
  const n = Number(value);
  if (Number.isNaN(n)) return EMPTY_VALUE;
  return n.toLocaleString("en-IN", { maximumFractionDigits: 4 });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return EMPTY_VALUE;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

// IST explicitly, not the viewer's locale timezone -- the badge is describing NSE's
// trading clock ("last quote pulled at HH:MM"), which means the same thing for every
// viewer regardless of where they are.
const istTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatTimeIST(value: string | null | undefined): string {
  if (!value) return EMPTY_VALUE;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return EMPTY_VALUE;
  return istTime.format(d);
}

export function signClass(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "text-navy-400";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n) || n === 0) return "text-navy-400";
  return n > 0 ? "text-positive" : "text-negative";
}
