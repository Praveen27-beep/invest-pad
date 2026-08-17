const RANGES = ["1M", "6M", "1Y", "3Y", "Max"];

/**
 * No backing data: compute_snapshot runs live but nothing persists a daily row
 * (docs/FULL_VISION_BACKEND_ROADMAP.md D1). Rather than invent monthly marks, this is
 * an honest empty state that keeps the layout slot the reference design gives it.
 */
export function HistoricalChartPlaceholder() {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="font-heading text-base text-navy-900">Value over time</h3>
          <p className="text-xs text-navy-400">Daily snapshots, INR</p>
        </div>
        <div className="flex overflow-hidden rounded-lg border border-navy-100">
          {RANGES.map((r) => (
            <button
              key={r}
              disabled
              className="px-3 py-1 text-xs text-navy-300 cursor-not-allowed border-r border-navy-100 last:border-r-0"
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-navy-100 bg-cream-50">
        <div className="text-center">
          <p className="text-sm font-medium text-navy-600">Historical value isn&apos;t tracked yet</p>
          <p className="mt-1 text-xs text-navy-400 max-w-xs">
            Available once daily portfolio snapshots are persisted (Phase 2).
          </p>
        </div>
      </div>
    </div>
  );
}
