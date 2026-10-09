"use client";

import { useState } from "react";

/** Shared quote presentation over the existing data layer. No invented price series. */
export function CompanySnapshot({ name, symbol, price, asOf, statistics = [], onResearch }: {
  name: string; symbol?: string | null; price?: string | null; asOf?: string | null;
  statistics?: readonly { label: string; value: string; basis?: string }[];
  onResearch?: () => void;
}) {
  const [period, setPeriod] = useState("1Y");
  return <section className="ip-stock-overview" aria-label={`${name} company overview`}>
    <div className="ip-stock-price"><div><span className="ip-demo-kicker">{symbol || name} · INDIA · INR</span><h2>{price ? `₹${price}` : "Price unavailable"}</h2><p>{price ? `Recorded price · ${asOf || "date unavailable"}` : "Connect market data to see a dated quote."}</p></div><span className="ip-stock-status">{price ? "Recorded snapshot" : "Market data not connected"}</span></div>
    <div className="ip-stock-periods" role="group" aria-label="Price history period">{["1D","1W","1M","3M","6M","1Y","5Y"].map(value => <button key={value} aria-pressed={period === value} onClick={() => setPeriod(value)}>{value}</button>)}</div>
    <div className="ip-stock-chart-empty" role="status"><span>Price history unavailable</span><p>No sourced prices for {period}. A chart will appear when a price-history source is connected.</p></div>
    <dl className="ip-stock-statistics">{[{label:"Market cap",value:"Unavailable"},{label:"P/E (TTM)",value:"Unavailable"},{label:"52-week range",value:"Unavailable"},...statistics].map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd>{"basis" in row && row.basis && <small>{row.basis}</small>}</div>)}</dl>
    {onResearch && <button className="ip-stock-research" onClick={onResearch}>Research this company →</button>}
  </section>;
}
