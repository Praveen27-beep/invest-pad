import Link from "next/link";

/**
 * MissingPriceError (409): CLAUDE.md rule 4, "a missing price raises, never defaults to
 * zero" -- XIRR needs a current value for every held position, unlike /summary and
 * /holdings, which partition an unpriced holding out (UnpricedBanner) and still total
 * the rest. The exception carries the ISINs precisely so this can name them instead of
 * a generic failure (docs/BUILD_PLAN.md definition of done).
 */
export function MissingPriceNotice({
  isins,
  compact = false,
}: {
  isins: string[];
  compact?: boolean;
}) {
  const plural = isins.length > 1;

  if (compact) {
    return (
      <div className="rounded-xl border border-negative/30 bg-negative/10 p-5 sm:col-span-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-negative">
          XIRR unavailable
        </p>
        <p className="mt-2 text-sm text-navy-700">
          {isins.length} held security{plural ? "ies" : ""} {plural ? "have" : "has"} no
          usable price.
        </p>
        <p className="mt-1 text-xs text-navy-500">
          See{" "}
          <Link href="/performance" className="text-brass-600 underline">
            Performance
          </Link>{" "}
          for which ISIN{plural ? "s" : ""}.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-negative/30 bg-negative/10 px-4 py-3">
      <p className="text-sm font-medium text-negative">
        Performance can&apos;t be computed — {isins.length} held security
        {plural ? "ies" : ""} {plural ? "have" : "has"} no usable price.
      </p>
      <p className="mt-1 text-xs text-navy-500">
        XIRR needs a current value for every held position; valuing a missing one at
        zero would understate returns. Add a price for the ISIN{plural ? "s" : ""}{" "}
        below, or check{" "}
        <Link href="/holdings" className="text-brass-600 underline">
          Holdings
        </Link>{" "}
        for the unpriced banner.
      </p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-navy-600">
        {isins.map((isin) => (
          <li key={isin} className="font-medium tabular-nums">
            {isin}
          </li>
        ))}
      </ul>
    </div>
  );
}
