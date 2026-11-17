"""Calculations with the formula shown. Deterministic, tested, no model involved.

Every calculation takes named Decimal inputs and returns the value, the formula in words,
the inputs it used and each intermediate step, so the user can redo it by hand. When a
denominator is zero or negative the answer is "not meaningful", never a number: a ratio
over negative equity or negative EBITDA reads as a result but means nothing.

Sources for the published models:
- Beneish, M. D. (1999). "The Detection of Earnings Manipulation." Financial Analysts
  Journal 55(5): 24–36. Eight-variable model and coefficients; −1.78 is the cut-off used
  there. https://doi.org/10.2469/faj.v55.n5.2296
- Sloan, R. G. (1996). "Do Stock Prices Fully Reflect Information in Accruals and Cash
  Flows about Future Earnings?" The Accounting Review 71(3): 289–315. Here the cash-flow
  form of accruals is used: (net income − cash from operations) / average total assets.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth

router = APIRouter()

PLACES = Decimal("0.0001")


class NotMeaningful(Exception):
    """A denominator was zero or negative, so the ratio has no useful reading."""


def _div(a: Decimal, b: Decimal, what: str) -> Decimal:
    if b <= 0:
        raise NotMeaningful(f"{what} is zero or negative")
    return a / b


@dataclass(frozen=True)
class Calc:
    key: str
    label: str
    inputs: tuple[str, ...]
    formula: str
    unit: str          # "%", "x", "days", "₹" (same currency as the inputs) or "score"
    fn: object


def cagr(v):
    if v["years"] <= 0:
        raise NotMeaningful("years must be above zero")
    ratio = _div(v["end_value"], v["start_value"], "start value")
    if ratio <= 0:
        raise NotMeaningful("end value is zero or negative")
    with localcontext() as ctx:
        ctx.prec = 28
        growth = (ratio.ln() / v["years"]).exp() - 1
    return growth * 100, {"end ÷ start": ratio}


def margin(v):
    return _div(v["numerator"], v["revenue"], "revenue") * 100, {}


def roe(v):
    return _div(v["net_income"], v["average_equity"], "average equity") * 100, {}


def roce(v):
    return _div(v["ebit"], v["capital_employed"], "capital employed") * 100, {}


def dupont(v):
    m = _div(v["net_income"], v["revenue"], "revenue")
    t = _div(v["revenue"], v["average_assets"], "average assets")
    lev = _div(v["average_assets"], v["average_equity"], "average equity")
    return m * t * lev * 100, {"net margin %": m * 100, "asset turnover x": t, "equity multiplier x": lev}


def working_capital(v):
    dso = _div(v["receivables"], v["revenue"], "revenue") * 365
    dio = _div(v["inventory"], v["cost_of_goods_sold"], "cost of goods sold") * 365
    dpo = _div(v["payables"], v["cost_of_goods_sold"], "cost of goods sold") * 365
    return dso + dio - dpo, {"receivable days": dso, "inventory days": dio, "payable days": dpo}


def net_debt_ebitda(v):
    net_debt = v["total_debt"] - v["cash_and_investments"]
    return _div(net_debt, v["ebitda"], "EBITDA"), {"net debt": net_debt}


def interest_cover(v):
    return _div(v["ebit"], v["interest_expense"], "interest expense"), {}


def fcf(v):
    value = v["cash_from_operations"] - v["capex"]
    steps = {}
    if v["net_income"] > 0:
        steps["FCF ÷ net income %"] = value / v["net_income"] * 100
    return value, steps


def sloan(v):
    accruals = v["net_income"] - v["cash_from_operations"]
    return _div(accruals, v["average_total_assets"], "average total assets") * 100, {"accruals": accruals}


BENEISH = {"DSRI": Decimal("0.920"), "GMI": Decimal("0.528"), "AQI": Decimal("0.404"), "SGI": Decimal("0.892"),
           "DEPI": Decimal("0.115"), "SGAI": Decimal("-0.172"), "TATA": Decimal("4.679"), "LVGI": Decimal("-0.327")}
BENEISH_INTERCEPT = Decimal("-4.84")
BENEISH_YEAR = ("revenue", "cost_of_goods_sold", "receivables", "current_assets", "net_ppe", "securities", "total_assets",
                "depreciation", "sga", "current_liabilities", "long_term_debt")


def beneish(v):
    t = {k: v[f"{k}_t"] for k in BENEISH_YEAR}
    p = {k: v[f"{k}_prior"] for k in BENEISH_YEAR}

    def gross_margin(y, which):
        return _div(y["revenue"] - y["cost_of_goods_sold"], y["revenue"], f"revenue ({which})")

    def soft_assets(y, which):
        return 1 - _div(y["current_assets"] + y["net_ppe"] + y["securities"], y["total_assets"], f"total assets ({which})")

    def dep_rate(y, which):
        return _div(y["depreciation"], y["depreciation"] + y["net_ppe"], f"depreciation + net PPE ({which})")

    def leverage(y, which):
        return _div(y["current_liabilities"] + y["long_term_debt"], y["total_assets"], f"total assets ({which})")

    idx = {
        "DSRI": _div(_div(t["receivables"], t["revenue"], "revenue (t)"),
                     _div(p["receivables"], p["revenue"], "revenue (prior)"), "prior receivables ÷ revenue"),
        "GMI": _div(gross_margin(p, "prior"), gross_margin(t, "t"), "gross margin (t)"),
        "AQI": _div(soft_assets(t, "t"), soft_assets(p, "prior"), "prior soft-asset share"),
        "SGI": _div(t["revenue"], p["revenue"], "revenue (prior)"),
        "DEPI": _div(dep_rate(p, "prior"), dep_rate(t, "t"), "depreciation rate (t)"),
        "SGAI": _div(_div(t["sga"], t["revenue"], "revenue (t)"),
                     _div(p["sga"], p["revenue"], "revenue (prior)"), "prior SG&A ÷ revenue"),
        "LVGI": _div(leverage(t, "t"), leverage(p, "prior"), "prior leverage"),
        "TATA": _div(v["net_income_t"] - v["cash_from_operations_t"], t["total_assets"], "total assets (t)"),
    }
    score = BENEISH_INTERCEPT + sum(BENEISH[k] * idx[k] for k in BENEISH)
    return score, idx


CALCS = {c.key: c for c in [
    Calc("cagr", "Compound annual growth", ("start_value", "end_value", "years"),
         "(end value ÷ start value) ^ (1 ÷ years) − 1", "%", cagr),
    Calc("margin", "Margin", ("numerator", "revenue"),
         "numerator ÷ revenue × 100 (numerator is EBITDA, EBIT, net income, gross profit…)", "%", margin),
    Calc("roe", "Return on equity", ("net_income", "average_equity"),
         "net income ÷ average shareholders' equity × 100", "%", roe),
    Calc("roce", "Return on capital employed", ("ebit", "capital_employed"),
         "EBIT ÷ capital employed × 100 (capital employed = equity + debt, or total assets − current liabilities)",
         "%", roce),
    Calc("dupont", "DuPont (3-step) return on equity", ("net_income", "revenue", "average_assets", "average_equity"),
         "(net income ÷ revenue) × (revenue ÷ average assets) × (average assets ÷ average equity) × 100", "%", dupont),
    Calc("working_capital", "Cash conversion cycle",
         ("receivables", "inventory", "payables", "revenue", "cost_of_goods_sold"),
         "receivables ÷ revenue × 365 + inventory ÷ COGS × 365 − payables ÷ COGS × 365", "days", working_capital),
    Calc("net_debt_ebitda", "Net debt to EBITDA", ("total_debt", "cash_and_investments", "ebitda"),
         "(total debt − cash and liquid investments) ÷ EBITDA", "x", net_debt_ebitda),
    Calc("interest_cover", "Interest cover", ("ebit", "interest_expense"), "EBIT ÷ interest expense", "x",
         interest_cover),
    Calc("fcf", "Free cash flow", ("cash_from_operations", "capex", "net_income"),
         "cash from operations − capital expenditure; conversion = FCF ÷ net income × 100", "₹", fcf),
    Calc("sloan", "Accruals ratio (Sloan, cash-flow form)", ("net_income", "cash_from_operations", "average_total_assets"),
         "(net income − cash from operations) ÷ average total assets × 100", "%", sloan),
    Calc("beneish", "Beneish M-score (8 variables)",
         tuple(f"{k}_{y}" for y in ("t", "prior") for k in BENEISH_YEAR) + ("net_income_t", "cash_from_operations_t"),
         "−4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI "
         "(Beneish 1999; scores above −1.78 resembled the manipulators in that study's sample)", "score", beneish),
]}


def run(key: str, raw: dict) -> dict:
    calc = CALCS.get(key)
    if not calc:
        raise KeyError(key)
    missing = [k for k in calc.inputs if raw.get(k) in (None, "")]
    if missing:
        raise ValueError("Missing: " + ", ".join(missing))
    try:
        values = {k: Decimal(str(raw[k]).replace(",", "").strip()) for k in calc.inputs}
    except InvalidOperation as e:
        raise ValueError("Every input must be a number") from e
    result = {"key": key, "label": calc.label, "formula": calc.formula, "unit": calc.unit,
              "inputs": {k: str(values[k]) for k in calc.inputs}}
    try:
        value, steps = calc.fn(values)
    except NotMeaningful as e:
        return {**result, "value": None, "not_meaningful": str(e), "steps": {}}
    return {**result, "value": str(value.quantize(PLACES)), "not_meaningful": None,
            "steps": {k: str(s.quantize(PLACES)) for k, s in steps.items()}}


@router.get("/calc")
def list_calcs(user: dict = Depends(auth.current_user)):
    return [{"key": c.key, "label": c.label, "inputs": list(c.inputs), "formula": c.formula, "unit": c.unit}
            for c in CALCS.values()]


class CalcIn(BaseModel):
    inputs: dict[str, str | int | float]


@router.post("/calc/{key}")
def calculate(key: str, body: CalcIn, user: dict = Depends(auth.current_user)):
    try:
        return run(key, body.inputs)
    except KeyError as e:
        raise HTTPException(404, "Unknown calculation") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
