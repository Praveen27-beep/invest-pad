"""End-to-end check of holdings, own limits, alerts, watchlist, monthly review and the graph.

    python e2e/portfolio.py http://localhost:3000 INVITE_CODE

Synthetic holdings only. Proves the screens work together; costs nothing.
"""

import secrets
import sys

from playwright.sync_api import expect, sync_playwright

BASE, INVITE = sys.argv[1], sys.argv[2]
EMAIL, PASSWORD = f"e2e-{secrets.token_hex(4)}@example.com", "a long test password"
CSV = b"Instrument,Qty.,Avg. cost,LTP,Cur. val\nNORTHGATE,1000,150,170,170000\nALPHA,500,100,120,60000\nBETA,100,1500,1000,100000\n"
BANNED = ("you should", "buy more", "sell ", "trim", "reduce", "rebalance", "we recommend")   # questions may ask why you bought

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE}/login")
    page.get_by_role("button", name="I have an invite code").click()
    page.get_by_placeholder("Email").fill(EMAIL)
    page.get_by_placeholder("Password (10+ characters)").fill(PASSWORD)
    page.get_by_placeholder("Invite code").fill(INVITE)
    page.get_by_role("button", name="Create account").click()
    page.get_by_placeholder("Add a company, e.g. IEX").fill("Northgate Power Exchange")
    page.get_by_role("button", name="Add company").click()
    page.get_by_role("link", name="Northgate Power Exchange").click()
    page.get_by_role("button", name="Add to watchlist").click()
    expect(page.get_by_role("button", name="On watchlist ✓")).to_be_visible()
    page.get_by_role("tab", name="Connections").click()
    expect(page.get_by_role("img", name="Connection graph")).to_be_visible()

    page.get_by_role("link", name="Portfolio").click()
    expect(page.get_by_text("watching since")).to_be_visible()
    page.get_by_label("Holdings file").set_input_files({"name": "holdings.csv", "mimeType": "text/csv", "buffer": CSV})
    page.get_by_role("button", name="Import").click()
    expect(page.get_by_text("51.52%")).to_be_visible()
    expect(page.get_by_text("Limits crossed")).to_have_count(0)          # nothing is on until the user turns it on

    limit = page.locator(".card", has_text="single").first
    limit.get_by_role("textbox").fill("10")
    limit.get_by_role("button", name="Save").click()
    page.locator(".card", has_text="single").first.get_by_role("checkbox").click()
    expect(page.get_by_text("Limits crossed")).to_be_visible()
    alert = page.get_by_role("alert").filter(has_text="NORTHGATE").first
    expect(alert).to_be_visible()
    alert.get_by_placeholder("Why does this stand?").fill("Sized on purpose; revisit after results.")
    alert.get_by_role("button", name="I’ve seen this").click()
    expect(page.get_by_text("Sized on purpose")).to_be_visible()
    page.reload()
    expect(page.get_by_role("link", name="Portfolio (2)")).to_be_visible()  # three crossed 10%; one is acknowledged

    page.get_by_label("Company page for NORTHGATE").select_option(label="Northgate Power Exchange")
    expect(page.get_by_role("link", name="Open")).to_be_visible()

    page.get_by_role("link", name="Review").click()
    expect(page.get_by_role("heading", name="Monthly review")).to_be_visible()
    first = page.get_by_role("textbox").first
    first.fill("Because the thesis has not changed.")
    page.get_by_role("button", name="Save answer").first.click()
    expect(page.get_by_text("Saved")).to_be_visible()
    text = page.locator("main").inner_text().lower()
    assert not [w for w in BANNED if w in text], [w for w in BANNED if w in text]

    page.get_by_role("link", name="Settings").click()
    with page.expect_download() as dl:
        page.get_by_role("link", name="Download my data").click()
    import io
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(open(dl.value.path(), "rb").read())).namelist()
    assert "data/holding.json" in names and "companies/Northgate Power Exchange/thesis.md" in names, names
    assert not errors, errors
    browser.close()
print("portfolio e2e passed")
