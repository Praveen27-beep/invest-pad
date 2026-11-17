"""Calculations: hand-worked values, and "not meaningful" instead of a misleading number."""

from decimal import Decimal

import pytest

from app import calc


def value(key, **inputs):
    r = calc.run(key, inputs)
    assert r["not_meaningful"] is None, r
    return Decimal(r["value"]), {k: Decimal(v) for k, v in r["steps"].items()}


def test_cagr():
    assert value("cagr", start_value=100, end_value=121, years=2)[0] == Decimal("10.0000")
    assert value("cagr", start_value=200, end_value=100, years=1)[0] == Decimal("-50.0000")
    assert value("cagr", start_value="1,000", end_value="1,610.51", years=5)[0] == Decimal("10.0000")


def test_simple_ratios():
    assert value("margin", numerator=25, revenue=200)[0] == Decimal("12.5000")
    assert value("roe", net_income=15, average_equity=100)[0] == Decimal("15.0000")
    assert value("roce", ebit=30, capital_employed=150)[0] == Decimal("20.0000")
    assert value("interest_cover", ebit=50, interest_expense=10)[0] == Decimal("5.0000")
    nd, steps = value("net_debt_ebitda", total_debt=300, cash_and_investments=100, ebitda=80)
    assert nd == Decimal("2.5000") and steps["net debt"] == Decimal("200.0000")
    assert value("net_debt_ebitda", total_debt=50, cash_and_investments=150, ebitda=80)[0] == Decimal("-1.2500")


def test_dupont_multiplies_back_to_roe():
    roe, steps = value("dupont", net_income=10, revenue=100, average_assets=200, average_equity=50)
    assert steps == {"net margin %": Decimal("10.0000"), "asset turnover x": Decimal("0.5000"),
                     "equity multiplier x": Decimal("4.0000")}
    assert roe == Decimal("20.0000") == value("roe", net_income=10, average_equity=50)[0]


def test_working_capital_days():
    ccc, steps = value("working_capital", receivables=100, inventory=50, payables=73, revenue=365, cost_of_goods_sold=365)
    assert steps == {"receivable days": Decimal("100.0000"), "inventory days": Decimal("50.0000"),
                     "payable days": Decimal("73.0000")}
    assert ccc == Decimal("77.0000")


def test_fcf_and_sloan():
    f, steps = value("fcf", cash_from_operations=120, capex=40, net_income=100)
    assert f == Decimal("80.0000") and steps["FCF ÷ net income %"] == Decimal("80.0000")
    assert value("fcf", cash_from_operations=120, capex=40, net_income=-5)[1] == {}   # conversion has no meaning
    s, steps = value("sloan", net_income=100, cash_from_operations=60, average_total_assets=1000)
    assert s == Decimal("4.0000") and steps["accruals"] == Decimal("40.0000")


BENEISH_SAME = {f"{k}_{y}": v for y in ("t", "prior") for k, v in {
    "revenue": 1000, "cost_of_goods_sold": 600, "receivables": 100, "current_assets": 400, "net_ppe": 300,
    "securities": 0, "total_assets": 1000, "depreciation": 50, "sga": 100, "current_liabilities": 200,
    "long_term_debt": 100}.items()}


def test_beneish_a_flat_year_gives_the_intercept_plus_coefficients():
    """If nothing changed between years every index is 1 and TATA is 0, so M is the sum of
    the intercept and the seven index coefficients: −4.84 + .920 + .528 + .404 + .892 +
    .115 − .172 − .327 = −2.480."""
    m, idx = value("beneish", **BENEISH_SAME, net_income_t=80, cash_from_operations_t=80)
    assert m == Decimal("-2.4800")
    assert all(idx[k] == 1 for k in ("DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI")) and idx["TATA"] == 0


def test_beneish_receivables_jump_and_accruals():
    """Receivables double on flat sales (DSRI 2) and profit is 100 above cash on assets of
    1000 (TATA 0.1): M = −2.480 + 0.920 × (2 − 1) + 4.679 × 0.1 = −1.0921."""
    m, idx = value("beneish", **{**BENEISH_SAME, "receivables_t": 200}, net_income_t=180, cash_from_operations_t=80)
    assert idx["DSRI"] == 2 and idx["TATA"] == Decimal("0.1000")
    assert m == Decimal("-1.0921")


@pytest.mark.parametrize("key,inputs,why", [
    ("roe", {"net_income": 10, "average_equity": -5}, "average equity"),
    ("roe", {"net_income": 10, "average_equity": 0}, "average equity"),
    ("net_debt_ebitda", {"total_debt": 100, "cash_and_investments": 0, "ebitda": -20}, "EBITDA"),
    ("interest_cover", {"ebit": 10, "interest_expense": 0}, "interest expense"),
    ("cagr", {"start_value": -10, "end_value": 50, "years": 3}, "start value"),
    ("cagr", {"start_value": 10, "end_value": -5, "years": 3}, "end value"),
    ("cagr", {"start_value": 10, "end_value": 20, "years": 0}, "years"),
    ("beneish", {**BENEISH_SAME, "revenue_prior": 0, "net_income_t": 1, "cash_from_operations_t": 1}, "revenue (prior)"),
])
def test_not_meaningful(key, inputs, why):
    r = calc.run(key, inputs)
    assert r["value"] is None and why in r["not_meaningful"]


def test_bad_input_and_api(new_user):
    with pytest.raises(ValueError, match="Missing: revenue"):
        calc.run("margin", {"numerator": 1})
    with pytest.raises(ValueError):
        calc.run("margin", {"numerator": "lots", "revenue": 1})
    c = new_user()
    listed = c.get("/calc").json()
    assert {x["key"] for x in listed} == set(calc.CALCS) and all(x["formula"] for x in listed)
    r = c.post("/calc/roe", json={"inputs": {"net_income": "15", "average_equity": "100"}}).json()
    assert r["value"] == "15.0000" and "average shareholders' equity" in r["formula"]
    assert c.post("/calc/nope", json={"inputs": {}}).status_code == 404
    assert c.post("/calc/roe", json={"inputs": {"net_income": "x", "average_equity": "1"}}).status_code == 422
