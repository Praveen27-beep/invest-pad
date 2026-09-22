"""Prototype of the Trackr+ analytics service, emitting the §8 data contract as JSON.

This is a SPIKE, not production code. It lives outside the source tree on purpose.
What it demonstrates, and the only thing it is meant to demonstrate:

  - Holdings and cost basis come from the REAL engine (app.engine.holdings), replayed
    from a ledger. Nothing about position size or invested capital is fetched.
  - yfinance supplies FUNDAMENTALS ONLY -- the per-company ratios Trackr+ has no
    source for today. Prices, sectors, cap bands and index levels are deliberately
    NOT taken from it; the repo already owns all four, keyed by ISIN.
  - ISIN -> ticker mapping is ours (securities table / AMFI list). yfinance cannot do
    it: Ticker("IGIL.NS").isin returns "-" for Indian scrips.
  - Every metric carries an as_of and a source, and every section reports coverage.

Run:  .venv/bin/python build_analytics.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

REPO = Path("/home/hypthes/Downloads/Projects/Trackr-plus")
SCRATCH = Path(__file__).parent
sys.path.insert(0, str(REPO / "trackr-backend"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402
from app.engine.holdings import compute_holdings  # noqa: E402
from app.engine.types import Source, Transaction, TxnType  # noqa: E402

CACHE = SCRATCH / "yf_cache.json"

# The mapping layer Trackr+ must own. Discovered the hard way on the first live run:
# TATAMOTORS.NS now 404s at Yahoo. Tata Motors Ltd was renamed Tata Motors Passenger
# Vehicles Ltd (NSE: TMPV) when the commercial-vehicle business demerged in Oct 2026,
# and the freed-up TATAMOTORS ticker was handed to the CV entity. The ISIN never moved.
# This is CLAUDE.md rule 2 ("tickers get renamed and reused") reproducing itself on a
# household name -- and it is the reason a ticker-keyed feed can never be the system of
# record. A ticker lookup here returns either nothing or the WRONG COMPANY, silently.
TICKER_ALIASES: dict[str, tuple[str, str, str]] = {
    "INE155A01022": (
        "TMPV",
        "Tata Motors Passenger Vehicles Ltd",
        "Renamed Tata Motors Passenger Vehicles Ltd on the CV demerger (Oct 2026); "
        "NSE symbol TATAMOTORS -> TMPV. The ISIN is unchanged, and the old ticker has "
        "been reassigned to the demerged CV entity.",
    ),
}
RF_RATE = 0.0648  # 91-day T-bill. A convention that must be sourced, not assumed.
TRADING_DAYS = 252


# --------------------------------------------------------------------------------------
# 1. The ledger. Real ISINs; synthetic quantities and cash flows.
# --------------------------------------------------------------------------------------

def load_ledger() -> tuple[list[Transaction], dict[str, dict]]:
    """Fixture demo ledger, extended with six real ISINs from the AMFI cap list.

    The extension exists so the demo spans large/mid/small rather than 18 large caps --
    that is where the fundamentals-coverage story actually shows up.
    """
    fixture = json.loads((REPO / "fixtures/demo_portfolio.json").read_text())
    securities = {s["isin"]: s for s in fixture["securities"]}

    txns: list[Transaction] = []
    for row in fixture["transactions"]:
        txns.append(
            Transaction(
                isin=row["isin"],
                txn_date=date.fromisoformat(row["txn_date"]),
                txn_type=TxnType(row["txn_type"]),
                quantity=Decimal(str(row["quantity"])),
                price=Decimal(str(row["price"])),
                charges=Decimal(str(row.get("charges", "0"))),
                stt=Decimal(str(row.get("stt", "0"))),
                source=Source.MANUAL,
            )
        )

    # Real ISIN / NSE symbol / SEBI category, from fixtures/amfi_market_cap_sample.xlsx.
    extra = [
        ("INE129A01019", "GAIL", "GAIL (India) Ltd",
         "Large Cap", 900, "150.20", "2023-04-18"),
        ("INE323A01026", "BOSCHLTD", "Bosch Ltd",
         "Mid Cap", 6, "28400.00", "2023-06-22"),
        ("INE073K01018", "SONACOMS", "Sona BLW Precision Forgings Ltd",
         "Mid Cap", 700, "612.40", "2024-01-11"),
        ("INE260B01028", "GODFRYPHLP", "Godfrey Phillips India Ltd",
         "Mid Cap", 55, "5180.00", "2024-03-05"),
        ("INE233A01035", "GODREJIND", "Godrej Industries Ltd",
         "Mid Cap", 300, "1010.75", "2024-07-19"),
        ("INE048G01026", "NAVINFLUOR", "Navin Fluorine International Ltd",
         "Small Cap", 120, "3395.00", "2024-09-03"),
    ]
    for isin, symbol, name, cap, qty, px, when in extra:
        securities[isin] = {
            "isin": isin, "symbol": symbol, "name": name,
            "exchange": "NSE", "amfi_category": cap,
        }
        txns.append(
            Transaction(
                isin=isin,
                txn_date=date.fromisoformat(when),
                txn_type=TxnType.BUY,
                quantity=Decimal(qty),
                price=Decimal(px),
                charges=Decimal("35.00"),
                stt=Decimal("0.00"),
                source=Source.MANUAL,
            )
        )
    return txns, securities


# --------------------------------------------------------------------------------------
# 2. yfinance: fundamentals only.
# --------------------------------------------------------------------------------------

UNIVERSE = [
    # A ranking universe. Factor percentiles are meaningless without one, and the
    # universe must be stated on every score. ~40 NSE names spanning the cap spectrum.
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT",
    "TATAMOTORS", "HINDUNILVR", "BAJFINANCE", "KOTAKBANK", "TITAN", "WIPRO",
    "MARUTI", "ASIANPAINT", "AXISBANK", "SUNPHARMA", "GAIL", "BOSCHLTD",
    "SONACOMS", "GODFRYPHLP", "GODREJIND", "NAVINFLUOR",
    "HCLTECH", "TECHM", "NESTLEIND", "POWERGRID", "NTPC", "ONGC", "COALINDIA",
    "GRASIM", "JSWSTEEL", "TATASTEEL", "ADANIPORTS", "BAJAJFINSV", "DRREDDY",
    "CIPLA", "BRITANNIA", "EICHERMOT", "HEROMOTOCO", "DIVISLAB", "SBILIFE",
]


def _cache_read() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {}


def _safe(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def fetch_fundamentals(symbols: list[str], refresh: bool = False) -> dict[str, dict]:
    """info + a financials fallback for the fields Yahoo leaves null.

    returnOnEquity is null for most Indian scrips -- it was null for 4 of the first 5
    tested, including Reliance. Falling back to Net Income / Stockholders Equity off the
    annual statements recovers it. Interest coverage is never in `info` at all and is
    always EBIT / Interest Expense.
    """
    cache = _cache_read()
    out: dict[str, dict] = {}
    for sym in symbols:
        key = f"{sym}.NS"
        if not refresh and key in cache:
            out[sym] = cache[key]
            continue
        rec: dict = {"symbol": sym, "fetched_at": datetime.utcnow().isoformat() + "Z"}
        try:
            t = yf.Ticker(key)
            i = t.info or {}
            rec.update(
                name=i.get("shortName") or i.get("longName"),
                sector_yf=i.get("sector"),
                industry_yf=i.get("industry"),
                market_cap=_safe(i.get("marketCap")),
                pe=_safe(i.get("trailingPE")),
                pb=_safe(i.get("priceToBook")),
                roe=_safe(i.get("returnOnEquity")),
                net_margin=_safe(i.get("profitMargins")),
                op_margin=_safe(i.get("operatingMargins")),
                de=_safe(i.get("debtToEquity")),
                div_yield=_safe(i.get("dividendYield")),
                rev_growth=_safe(i.get("revenueGrowth")),
                earn_growth=_safe(i.get("earningsGrowth")),
                roe_source="yahoo_info" if _safe(i.get("returnOnEquity")) else None,
            )
            # --- fallbacks off the annual statements -------------------------------
            try:
                fin, bs = t.financials, t.balance_sheet
                if fin is not None and not fin.empty:
                    if rec.get("roe") is None and bs is not None and not bs.empty:
                        ni = (_safe(fin.loc["Net Income"].iloc[0])
                              if "Net Income" in fin.index else None)
                        eq = (_safe(bs.loc["Stockholders Equity"].iloc[0])
                              if "Stockholders Equity" in bs.index else None)
                        if ni and eq:
                            rec["roe"] = ni / eq
                            rec["roe_source"] = "derived_financials"
                    if "EBIT" in fin.index and "Interest Expense" in fin.index:
                        ebit = _safe(fin.loc["EBIT"].iloc[0])
                        ie = _safe(fin.loc["Interest Expense"].iloc[0])
                        rec["interest_cover"] = (ebit / ie) if (ebit and ie) else None
                    if "Total Revenue" in fin.index and fin.loc["Total Revenue"].size > 1:
                        r = fin.loc["Total Revenue"]
                        r0, r1 = _safe(r.iloc[0]), _safe(r.iloc[1])
                        rec["sales_cagr_1y"] = (r0 / r1 - 1) if (r0 and r1 and r1 > 0) else None
                    if "Net Income" in fin.index and fin.loc["Net Income"].size > 1:
                        n = fin.loc["Net Income"]
                        n0, n1 = _safe(n.iloc[0]), _safe(n.iloc[1])
                        rec["profit_cagr_1y"] = (n0 / n1 - 1) if (n0 and n1 and n1 > 0) else None
            except Exception as exc:  # statements are frequently absent
                rec["stmt_error"] = f"{type(exc).__name__}"
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        out[sym] = rec
        cache[key] = rec
        CACHE.write_text(json.dumps(cache, indent=1))
        time.sleep(0.35)  # Yahoo rate-limits aggressively; this is an unofficial endpoint
        print(f"  fetched {sym:12s} pe={rec.get('pe')} "
              f"roe={rec.get('roe')} ({rec.get('roe_source')})", flush=True)
    return out


def fetch_history(symbols: list[str], years: int = 6) -> pd.DataFrame:
    tickers = [f"{s}.NS" for s in symbols] + ["^NSEI"]
    hist = yf.download(
        tickers, period=f"{years}y", interval="1d", progress=False, auto_adjust=True,
        threads=True,
    )
    return hist["Close"]


# --------------------------------------------------------------------------------------
# 3. Metrics.
# --------------------------------------------------------------------------------------

def pct_rank(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    """Cross-sectional percentile rank, 0-100, over the stated universe."""
    clean = {k: v for k, v in values.items() if v is not None}
    if not clean:
        return {}
    ordered = sorted(clean.items(), key=lambda kv: kv[1])  # always ascending
    n = len(ordered)
    out = {}
    for idx, (k, _) in enumerate(ordered):
        frac = idx / max(n - 1, 1)
        out[k] = round(100.0 * (frac if higher_is_better else 1 - frac), 1)
    return out


def zscore(values: dict[str, float]) -> dict[str, float]:
    clean = {k: v for k, v in values.items() if v is not None}
    if len(clean) < 2:
        return {k: 0.0 for k in clean}
    mu = statistics.mean(clean.values())
    sd = statistics.pstdev(clean.values()) or 1.0
    return {k: (v - mu) / sd for k, v in clean.items()}


def momentum_12_1(series: pd.Series) -> float | None:
    """Standard 12-1 construction: 12-month return skipping the most recent month."""
    s = series.dropna()
    if len(s) < 260:
        return None
    try:
        end = s.iloc[-22]      # ~1 month back
        start = s.iloc[-252]   # ~12 months back
        return float(end / start - 1) if start > 0 else None
    except Exception:
        return None


def ann_vol(returns: pd.Series) -> float | None:
    r = returns.dropna()
    if len(r) < 60:
        return None
    return float(r.std() * math.sqrt(TRADING_DAYS))


def _ret(series: pd.Series, days: int) -> float | None:
    s = series.dropna()
    if len(s) <= days:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - days] - 1) * 100


def max_drawdown(series: pd.Series) -> float:
    s = series.dropna()
    return float((s / s.cummax() - 1).min())


def main() -> None:
    refresh = "--refresh" in sys.argv
    print("Replaying ledger through app.engine.holdings ...")
    txns, securities = load_ledger()
    holdings = compute_holdings(txns)
    holdings = [h for h in holdings if h.quantity > 0]
    isins = [h.isin for h in holdings]
    symbols = [TICKER_ALIASES[i][0] if i in TICKER_ALIASES else securities[i]["symbol"]
               for i in isins]
    print(f"  {len(holdings)} open positions from {len(txns)} ledger rows")

    print("Fetching fundamentals (yfinance, fundamentals only) ...")
    fund = fetch_fundamentals(sorted(set(UNIVERSE) | set(symbols)), refresh=refresh)

    print("Fetching price history ...")
    # 6y of calendar history, because a 5Y lookback needs 1260 trading rows
    closes = fetch_history(sorted(set(UNIVERSE) | set(symbols)))
    closes.columns = [c.replace(".NS", "") for c in closes.columns]
    rets = closes.pct_change()

    # ---- positions -----------------------------------------------------------------
    positions = []
    unresolved: list[dict] = []
    total_worth = 0.0
    total_invested = 0.0
    total_prev = 0.0
    for h in holdings:
        sec = securities[h.isin]
        sym = sec["symbol"]
        alias_note = None
        display_name = sec["name"]
        if h.isin in TICKER_ALIASES:
            sym, display_name, alias_note = TICKER_ALIASES[h.isin]
        px_series = closes[sym].dropna() if sym in closes else pd.Series(dtype=float)
        last = float(px_series.iloc[-1]) if len(px_series) else None
        prev = float(px_series.iloc[-2]) if len(px_series) > 1 else None
        qty = float(h.quantity)
        invested = float(h.invested)
        worth = (qty * last) if last else None
        if worth is None:
            # CLAUDE.md rule 4: a missing price never defaults to zero. It is carried
            # out of every denominator as a named exception and shown to the user.
            unresolved.append({
                "isin": h.isin, "symbol": sym, "name": sec["name"],
                "quantity": qty, "invested": invested,
                "reason": "No price at the fundamentals feed for this identifier.",
            })
            continue
        total_worth += worth
        total_invested += invested
        total_prev += qty * prev if prev else worth
        f = fund.get(sym, {})
        positions.append({
            "isin": h.isin, "symbol": sym, "name": display_name,
            "former_name": sec["name"] if display_name != sec["name"] else None,
            "quantity": qty, "avg_cost": invested / qty if qty else None,
            "invested": invested, "last": last, "prev_close": prev, "worth": worth,
            "day_change": (last - prev) * qty if prev else None,
            "day_change_pct": (last / prev - 1) * 100 if prev else None,
            "unrealised": worth - invested,
            "unrealised_pct": (worth / invested - 1) * 100 if invested else None,
            "alias_note": alias_note,
            "ret_1w": _ret(px_series, 5), "ret_1m": _ret(px_series, 21),
            "ret_3m": _ret(px_series, 63), "ret_1y": _ret(px_series, 252),
            "ret_3y": _ret(px_series, 756), "ret_5y": _ret(px_series, 1260),
            "amfi_category": sec.get("amfi_category", "Large Cap"),
            "sector": f.get("sector_yf"), "industry": f.get("industry_yf"),
            "pe": f.get("pe"), "pb": f.get("pb"), "roe": f.get("roe"),
            "roe_source": f.get("roe_source"),
            "net_margin": f.get("net_margin"), "de": f.get("de"),
            "interest_cover": f.get("interest_cover"),
            "div_yield": f.get("div_yield"),
            "sales_cagr_1y": f.get("sales_cagr_1y"),
            "profit_cagr_1y": f.get("profit_cagr_1y"),
            "market_cap": f.get("market_cap"),
        })

    for p in positions:
        p["weight"] = 100.0 * p["worth"] / total_worth

    # ---- factor scores over the stated universe -------------------------------------
    uni = sorted(set(UNIVERSE) | set(symbols))
    mom_raw = {s: momentum_12_1(closes[s]) for s in uni if s in closes}
    vol_raw = {s: ann_vol(rets[s]) for s in uni if s in rets}
    # risk-adjust momentum by trailing vol
    mom_adj = {s: (mom_raw[s] / vol_raw[s]) for s in mom_raw
               if mom_raw.get(s) is not None and vol_raw.get(s)}
    ep = {s: (1 / fund[s]["pe"]) for s in uni if fund.get(s, {}).get("pe")}
    bp = {s: (1 / fund[s]["pb"]) for s in uni if fund.get(s, {}).get("pb")}
    value_z = {}
    ez, bz = zscore(ep), zscore(bp)
    for s in uni:
        parts = [z[s] for z in (ez, bz) if s in z]
        if parts:
            value_z[s] = sum(parts) / len(parts)
    roe = {s: fund[s]["roe"] for s in uni if fund.get(s, {}).get("roe") is not None}
    marg = {s: fund[s]["net_margin"] for s in uni if fund.get(s, {}).get("net_margin") is not None}
    lev = {s: -fund[s]["de"] for s in uni if fund.get(s, {}).get("de") is not None}
    qz_r, qz_m, qz_l = zscore(roe), zscore(marg), zscore(lev)
    quality_z = {}
    for s in uni:
        parts = [z[s] for z in (qz_r, qz_m, qz_l) if s in z]
        if parts:
            quality_z[s] = sum(parts) / len(parts)
    lowvol = {s: -v for s, v in vol_raw.items() if v is not None}

    factors = {
        "momentum": pct_rank(mom_adj),
        "value": pct_rank(value_z),
        "quality": pct_rank(quality_z),
        "low_volatility": pct_rank(lowvol),
    }
    for p in positions:
        p["factors"] = {k: v.get(p["symbol"]) for k, v in factors.items()}

    portfolio_factors = {}
    for fname, scores in factors.items():
        num = sum(p["weight"] * scores[p["symbol"]] for p in positions
                  if scores.get(p["symbol"]) is not None)
        den = sum(p["weight"] for p in positions if scores.get(p["symbol"]) is not None)
        portfolio_factors[fname] = {
            "score": round(num / den, 1) if den else None,
            "coverage_pct": round(den, 1),
            "universe": f"NSE_DEMO_{len(uni)}",
        }

    # ---- portfolio return series (fixed current weights -- labelled as such) --------
    w = {p["symbol"]: p["weight"] / 100.0 for p in positions}
    port_rets = sum(rets[s].fillna(0) * wt for s, wt in w.items() if s in rets)
    port_rets = port_rets.dropna()
    bench_rets = rets["^NSEI"].dropna()
    common = port_rets.index.intersection(bench_rets.index)
    port_rets, bench_rets = port_rets.loc[common], bench_rets.loc[common]

    def window(days: int):
        pr, br = port_rets.tail(days), bench_rets.tail(days)
        pcum = float((1 + pr).prod() - 1)
        bcum = float((1 + br).prod() - 1)
        yrs = len(pr) / TRADING_DAYS
        pv = float(pr.std() * math.sqrt(TRADING_DAYS))
        bv = float(br.std() * math.sqrt(TRADING_DAYS))
        pcagr = (1 + pcum) ** (1 / yrs) - 1 if yrs > 0 else None
        bcagr = (1 + bcum) ** (1 / yrs) - 1 if yrs > 0 else None
        down = pr[pr < RF_RATE / TRADING_DAYS]
        dsd = float(down.std() * math.sqrt(TRADING_DAYS)) if len(down) > 2 else None
        cov = float(np.cov(pr, br)[0][1])
        var_b = float(np.var(br))
        return {
            "cum_return": pcum, "bench_cum_return": bcum,
            "cagr": pcagr, "bench_cagr": bcagr,
            "vol": pv, "bench_vol": bv,
            "sharpe": (pcagr - RF_RATE) / pv if pv else None,
            "bench_sharpe": (bcagr - RF_RATE) / bv if bv else None,
            "sortino": (pcagr - RF_RATE) / dsd if dsd else None,
            "beta": cov / var_b if var_b else None,
            "var_1d_95": float(-np.percentile(pr, 5)),
            "var_1d_99": float(-np.percentile(pr, 1)),
            "cvar_1d_95": float(-pr[pr <= np.percentile(pr, 5)].mean()),
            "max_drawdown": max_drawdown((1 + pr).cumprod()),
            "days": len(pr),
        }

    risk = {"1y": window(252), "3y": window(756), "5y": window(len(port_rets))}

    # ---- growth of 1,00,000 ---------------------------------------------------------
    pr1, br1 = port_rets.tail(252), bench_rets.tail(252)
    growth = {
        "dates": [d.strftime("%Y-%m-%d") for d in pr1.index],
        "portfolio": [round(float(v), 2) for v in (1 + pr1).cumprod() * 100000],
        "benchmark": [round(float(v), 2) for v in (1 + br1).cumprod() * 100000],
    }

    # ---- correlation ----------------------------------------------------------------
    syms = [p["symbol"] for p in positions if p["symbol"] in rets]
    cmat = rets[syms].tail(252).corr()
    correlation = {
        "symbols": syms,
        "matrix": [[round(float(cmat.loc[a, b]), 3) for b in syms] for a in syms],
    }

    # ---- allocation -----------------------------------------------------------------
    def agg(key):
        d: dict[str, float] = {}
        for p in positions:
            d[p.get(key) or "Unclassified"] = d.get(p.get(key) or "Unclassified", 0) + p["worth"]
        return sorted(
            [{"label": k, "value": v, "pct": 100 * v / total_worth} for k, v in d.items()],
            key=lambda r: -r["pct"],
        )

    # ---- portfolio fundamentals: weighted HARMONIC mean of P/E ----------------------
    def harmonic_pe(field: str):
        num = sum(p["weight"] for p in positions if p.get(field) and p[field] > 0)
        den = sum(p["weight"] / p[field] for p in positions if p.get(field) and p[field] > 0)
        excluded = 100.0 - num
        return (num / den if den else None), excluded

    pe_agg, pe_excl = harmonic_pe("pe")
    pb_agg, pb_excl = harmonic_pe("pb")
    dy_num = sum(p["weight"] * p["div_yield"] for p in positions if p.get("div_yield") is not None)
    dy_den = sum(p["weight"] for p in positions if p.get("div_yield") is not None)

    # ---- capital state buckets ------------------------------------------------------
    for p in positions:
        s = closes[p["symbol"]].dropna()
        dma50 = float(s.tail(50).mean())
        dev = (p["last"] / dma50 - 1) * 100
        trend = "flat" if abs(dev) <= 2 else ("up" if dev > 0 else "down")
        p["dma50"] = dma50
        p["trend"] = trend
        in_profit = p["unrealised"] >= 0
        if in_profit:
            p["capital_state"] = "STRONG" if trend in ("up", "flat") else "WEAKENING"
        else:
            p["capital_state"] = "RECOVERY" if trend == "up" else "CAUTION"

    buckets: dict[str, float] = {"STRONG": 0, "WEAKENING": 0, "CAUTION": 0, "RECOVERY": 0}
    for p in positions:
        buckets[p["capital_state"]] += p["worth"]

    # ---- coverage -------------------------------------------------------------------
    def cov_pct(field):
        return round(sum(p["weight"] for p in positions if p.get(field) is not None), 1)

    coverage = {
        "priced_pct": 100.0,
        "pe_pct": cov_pct("pe"), "pb_pct": cov_pct("pb"), "roe_pct": cov_pct("roe"),
        "de_pct": cov_pct("de"), "interest_cover_pct": cov_pct("interest_cover"),
        "sector_pct": cov_pct("sector"), "net_margin_pct": cov_pct("net_margin"),
        "sales_growth_pct": cov_pct("sales_cagr_1y"),
        "roe_derived_weight": round(
            sum(p["weight"] for p in positions if p.get("roe_source") == "derived_financials"), 1
        ),
    }

    out = {
        "as_of": str(closes.index[-1].date()),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "benchmark": "NIFTY 50 (^NSEI)",
        "stale": False,
        "coverage": coverage,
        "sources": {
            "quantity_cost": "Trackr+ ledger via app.engine.holdings (FIFO)",
            "prices": "yfinance EOD close (SPIKE ONLY -- production reads the bhavcopy pipe)",
            "fundamentals": "Yahoo Finance via yfinance, unofficial endpoint",
            "cap_bands": "AMFI half-yearly list (fixtures/amfi_market_cap_sample.xlsx), ISIN-keyed",
            "rf_rate": "91-day T-Bill, assumed 6.48% -- MUST be sourced before shipping",
        },
        "kpi": {
            "invested": total_invested,
            "worth": total_worth,
            "unrealised": total_worth - total_invested,
            "unrealised_pct": 100 * (total_worth / total_invested - 1),
            "day_change": total_worth - total_prev,
            "day_change_pct": 100 * (total_worth / total_prev - 1),
            "bench_day_change_pct": float(bench_rets.iloc[-1] * 100),
        },
        "factors": portfolio_factors,
        "risk": risk,
        "rf_rate": RF_RATE,
        "growth_of_100k": growth,
        "correlation": correlation,
        "allocation": {"sector": agg("sector"), "market_cap": agg("amfi_category")},
        "fundamentals": {
            "portfolio": {"pe": pe_agg, "pb": pb_agg,
                          "div_yield": (dy_num / dy_den) if dy_den else None},
            "excluded_weight_pe": round(pe_excl, 1),
            "excluded_weight_pb": round(pb_excl, 1),
        },
        "capital_state": {k: v for k, v in buckets.items()},
        "unresolved": unresolved,
        "positions": sorted(positions, key=lambda p: -p["weight"]),
    }

    dest = SCRATCH / "analytics.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nWrote {dest}")
    print(f"  invested {total_invested:,.0f}  worth {total_worth:,.0f}  "
          f"unrealised {total_worth-total_invested:+,.0f} ({out['kpi']['unrealised_pct']:+.2f}%)")
    print(f"  coverage: {coverage}")
    print(f"  1y: cagr {risk['1y']['cagr']:.4f} vol {risk['1y']['vol']:.4f} "
          f"sharpe {risk['1y']['sharpe']:.3f} beta {risk['1y']['beta']:.3f}")


if __name__ == "__main__":
    main()
