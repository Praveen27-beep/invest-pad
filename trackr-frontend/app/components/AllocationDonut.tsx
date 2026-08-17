import type { AllocationGroupOut } from "@/lib/api-types";
import { formatPercent } from "@/lib/format";
import { EmptyState } from "./PageState";

const SLICE_COLORS = ["#1B2A41", "#B08D3E", "#3D5170", "#C9A84C", "#8F7130", "#26374F"];

/**
 * Grouped by asset_class (GET /summary's `allocation`), not sector -- security.sector
 * is null for every row today (docs/DATA_MODEL.md). In Phase 1 (equities only) this
 * renders as a single 100% slice, which is correct, not a bug.
 */
export function AllocationDonut({ groups }: { groups: AllocationGroupOut[] }) {
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
          <li key={g.asset_class} className="flex items-center justify-between gap-3">
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
