import { formatPercent } from "@/lib/format";
import { EmptyState } from "./PageState";

const SLICE_COLORS = ["#1B2A41", "#B08D3E", "#3D5170", "#C9A84C", "#8F7130", "#26374F"];

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

export function AllocationDonut({ groups }: { groups: AllocationSlice[] }) {
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
      <div
        className="h-32 w-32 shrink-0 rounded-full"
        style={{
          background: `conic-gradient(${stops.join(", ")})`,
          maskImage: "radial-gradient(transparent 58%, black 59%)",
          WebkitMaskImage: "radial-gradient(transparent 58%, black 59%)",
        }}
      />
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
