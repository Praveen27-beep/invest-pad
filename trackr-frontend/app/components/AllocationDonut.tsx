import { formatPercent } from "@/lib/format";
import { useTheme } from "@/lib/theme-context";
import { EmptyState } from "./PageState";

// Grayscale-first, per the Notion Charts block: identity is carried by a lightness
// ramp off the text colour rather than a categorical hue set, so the chart never needs
// more than one accent (reserved for links/focus, not data series) and is
// colour-vision-safe by construction. Two ramps, not one -- each is calibrated against
// its own surface (near-white vs. near-black), so the lightest step never washes out.
const SLICE_COLORS_LIGHT = ["#2C2C2B", "#5F5D59", "#8E8B86", "#ADA9A3", "#C7C6C4", "#E3E2E0"];
const SLICE_COLORS_DARK = ["#F0EFED", "#D4D3CF", "#ADA9A3", "#8E8B86", "#5F5E59", "#3D3D3D"];

/**
 * Grouping-agnostic: renders whichever slices it's handed, whether that's GET
 * /summary's `allocation` (by asset_class) or `allocation_by_sector`. `key` is the raw
 * grouping value (may be `null` -- an "Unclassified" sector group carries a real
 * `label` but a `null` key) and only ever used for React's list key, never displayed;
 * `label` is what's shown. The caller (app/page.tsx) adapts either response array into
 * this shape.
 */
export interface AllocationSlice {
  key: string | null;
  label: string;
  weight_pct: number | null;
}

export function AllocationDonut({
  groups,
  centerLabel,
  centerValue,
}: {
  groups: AllocationSlice[];
  /** e.g. "Current value" / "Amount invested" -- shown under the centre figure. */
  centerLabel?: string;
  /** Pre-formatted (formatMoney'd) total shown in the donut's hollow centre. */
  centerValue?: string;
}) {
  const { theme } = useTheme();
  const SLICE_COLORS = theme === "dark" ? SLICE_COLORS_DARK : SLICE_COLORS_LIGHT;
  const priced = groups.filter((g) => g.weight_pct !== null && g.weight_pct > 0);

  if (priced.length === 0) {
    return <EmptyState title="No priced allocation yet" />;
  }

  let cursor = 0;
  const stops = priced.map((g, i) => {
    const pct = (g.weight_pct ?? 0) * 100;
    const start = cursor;
    cursor += pct;
    return `${SLICE_COLORS[i % SLICE_COLORS.length]} ${start}% ${cursor}%`;
  });

  return (
    <div className="flex items-center gap-6">
      <div className="relative h-32 w-32 shrink-0">
        <div
          className="h-32 w-32 rounded-full"
          style={{
            background: `conic-gradient(${stops.join(", ")})`,
            maskImage: "radial-gradient(transparent 58%, black 59%)",
            WebkitMaskImage: "radial-gradient(transparent 58%, black 59%)",
          }}
        />
        {centerValue && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-sm font-medium leading-tight text-navy-900 tabular-nums">
              {centerValue}
            </span>
            {centerLabel && <span className="mt-0.5 text-[10px] text-navy-400">{centerLabel}</span>}
          </div>
        )}
      </div>
      <ul className="flex-1 space-y-2 text-sm">
        {priced.map((g, i) => (
          <li key={g.key ?? "__unclassified__"} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-navy-600">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: SLICE_COLORS[i % SLICE_COLORS.length] }}
              />
              {g.label}
            </span>
            <span className="tabular-nums text-navy-900">{formatPercent(g.weight_pct)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
