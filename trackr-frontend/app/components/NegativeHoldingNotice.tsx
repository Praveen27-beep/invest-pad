import Link from "next/link";

/**
 * NegativeHoldingError (409): a SELL/BUYBACK/TRANSFER_OUT for this ISIN exceeds what
 * the ledger shows as bought, as of a specific date -- app/engine/errors.py. That means
 * buy history is missing, not that the investor is short, so this names the ISIN and
 * the date rather than showing the raw "buy history is incomplete" string as a dead
 * end (the same posture as MissingPriceNotice for MissingPriceError).
 */
export function NegativeHoldingNotice({
  isin,
  deficit,
  asOf,
  compact = false,
}: {
  isin: string;
  deficit?: string;
  asOf?: string;
  compact?: boolean;
}) {
  const short = deficit ? `${deficit} unit${deficit === "1" ? "" : "s"}` : "some units";
  const when = asOf ? ` as of ${asOf}` : "";

  if (compact) {
    return (
      <div className="rounded-xl border border-negative/30 bg-negative/10 p-5 sm:col-span-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-negative">
          Holdings unavailable
        </p>
        <p className="mt-2 text-sm text-navy-700">
          {isin} is short {short}{when}.
        </p>
        <p className="mt-1 text-xs text-navy-500">
          See{" "}
          <Link href="/portfolio?tab=import" className="text-brass-600 underline">
            Import
          </Link>{" "}
          to add the missing history.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-negative/30 bg-negative/10 px-4 py-3">
      <p className="text-sm font-medium text-negative">
        Portfolio can&apos;t be computed — {isin} is short {short}{when}.
      </p>
      <p className="mt-1 text-xs text-navy-500">
        This means a sale for {isin} was recorded before enough buys to cover it, not
        that the position actually went short. The usual cause: Zerodha Console caps a
        tradebook export at 365 days, so an earlier year&apos;s buys never got uploaded.
        A less common cause is a merger, demerger, or symbol change that changed the
        ISIN&apos;s quantity without a matching transaction.
      </p>
      <p className="mt-2 text-xs text-navy-500">
        <Link href="/portfolio?tab=import" className="text-brass-600 underline">
          Import
        </Link>{" "}
        the missing contract note (one file per financial year, going back further),
        or check{" "}
        <Link href="/portfolio?tab=transactions" className="text-brass-600 underline">
          Transactions
        </Link>{" "}
        for {isin} to find and fix the gap by hand.
      </p>
    </div>
  );
}
