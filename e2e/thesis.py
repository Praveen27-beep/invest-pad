"""End-to-end check of the success test in a real browser.

    python e2e/thesis.py http://localhost:3000 INVITE_CODE

"Can an investor reopen an old company and recover the decisive reason they bought,
passed, or stopped researching, without rereading their documents?"

Uploads a document, writes a thesis with an assumption backed by a cited passage, records
a decision, lets things change, then reopens the company and checks what the first screen
shows. No AI is involved anywhere in this flow.
"""

import io
import secrets
import sys

from playwright.sync_api import expect, sync_playwright
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

BASE, INVITE = sys.argv[1], sys.argv[2]
EMAIL, PASSWORD = f"e2e-{secrets.token_hex(4)}@example.com", "a long test password"
REASON = "Downside is limited to part of the day-ahead market; upside is a growing exchange share. Small position."
ASSUMPTION = "Coupling stays limited to the day-ahead market"


def pdf(*pages: str) -> bytes:
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=A4)
    for text in pages:
        sheet.drawString(50, 800, text)
        sheet.showPage()
    sheet.save()
    return buffer.getvalue()


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())

    page.goto(f"{BASE}/login")
    page.get_by_role("button", name="I have an invite code").click()
    page.get_by_placeholder("Email").fill(EMAIL)
    page.get_by_placeholder("Password (10+ characters)").fill(PASSWORD)
    page.get_by_placeholder("Invite code").fill(INVITE)
    page.get_by_role("button", name="Create account").click()
    page.get_by_placeholder("Add a company, e.g. IEX").fill("Northgate Power Exchange")
    page.get_by_role("button", name="Add company").click()
    page.get_by_role("link", name="Northgate Power Exchange").click()
    page.wait_for_url("**/c/*")
    company_url = page.url
    expect(page.get_by_text("No decision recorded yet.")).to_be_visible()

    # --- upload a concall; type and period are guessed from the file name
    page.get_by_role("tab", name="Documents").click()
    page.locator("input[type=file]").set_input_files({
        "name": "Northgate Q4FY26 concall transcript.pdf", "mimeType": "application/pdf",
        "buffer": pdf("Regulator order: round one of coupling covers the day-ahead market only.",
                      "Management: we expect to retain significant share after coupling.")})
    page.get_by_role("button", name="Upload").click()
    row = page.locator("li", has_text="Northgate Q4FY26 concall transcript")
    expect(row).to_contain_text("concall · Q4 FY26")
    expect(row).to_contain_text("2 page(s)", timeout=15000)

    # --- thesis and one assumption
    page.get_by_role("tab", name="Thesis & decisions").click()
    page.get_by_label("Thesis").fill("The incumbent keeps its share after coupling.")
    page.get_by_role("button", name="Save as new version").click()
    expect(page.get_by_role("status").first).to_contain_text("Saved as version 1")
    page.get_by_placeholder("New assumption", exact=False).fill(ASSUMPTION)
    page.get_by_role("button", name="Add assumption").click()
    expect(page.locator(".card", has_text=ASSUMPTION).first).to_contain_text("Holds")

    # --- a fact: a passage from the document, cited
    page.get_by_role("tab", name="Documents").click()
    page.get_by_role("link", name="Northgate Q4FY26 concall transcript").click()
    page.wait_for_url("**/d/*")
    document_url = page.url
    passage = page.locator(".card", has_text="round one of coupling covers the day-ahead market only")
    expect(passage).to_contain_text("p. 1")
    passage.get_by_role("button", name="Use as evidence").click()
    passage.get_by_placeholder("In your words: what does this passage show?").fill("The order itself limits round one to DAM.")
    passage.get_by_role("button", name="Add as a fact").click()
    expect(page.get_by_text("Added as evidence.")).to_be_visible()

    # --- record the decision
    page.goto(company_url)
    page.get_by_role("tab", name="Thesis & decisions").click()
    card = page.locator(".card", has_text=ASSUMPTION).first
    expect(card.locator(".badge.fact")).to_have_text("Fact")
    expect(card).to_contain_text("round one of coupling covers the day-ahead market only")   # the cited passage
    expect(card).to_contain_text("Q4 FY26 · p. 1")
    form = page.locator("form", has_text="The one reason that decided it")
    form.get_by_label("Decision").select_option(label="Bought")
    form.get_by_label("The one reason that decided it").fill(REASON)
    form.get_by_label("What would change your mind?", exact=False).fill("Coupling extended to the real-time market.")
    form.get_by_label(ASSUMPTION).check()
    form.get_by_role("button", name="Record decision").click()
    expect(page.locator(".card", has_text="recorded").first).to_contain_text(REASON)

    # --- time passes: the assumption breaks, the thesis is revised
    card.get_by_label("State").select_option(label="Broken")
    card.get_by_placeholder("Why did this change? (required)").fill("A new order extends coupling to RTM.")
    card.get_by_role("button", name="Record change").click()
    expect(card.locator(".badge.broken")).to_be_visible()
    page.get_by_label("Thesis").fill("The incumbent keeps most of its share after coupling.")
    page.get_by_role("button", name="Save as new version").click()
    expect(page.get_by_role("status").first).to_contain_text("Saved as version 2")
    page.get_by_role("button", name="v1 → v2", exact=False).click()
    diff = page.get_by_label("Thesis changes")
    expect(diff.locator("ins")).to_contain_text("most")

    # --- THE SUCCESS TEST: leave, come back, read the first screen. No document is opened.
    page.goto(BASE)
    page.get_by_role("link", name="Northgate Power Exchange").click()
    first_screen = page.get_by_label("Last decision")
    expect(first_screen).to_contain_text("Bought")
    expect(first_screen.locator(".reason")).to_have_text(REASON)
    expect(first_screen).to_contain_text("Coupling extended to the real-time market.")
    expect(first_screen).to_contain_text(ASSUMPTION)
    expect(first_screen).to_contain_text("Broken now")
    expect(first_screen).to_contain_text("A new order extends coupling to RTM.")
    expect(first_screen).to_contain_text("thesis version 1 (now version 2)")
    box = first_screen.locator(".reason").bounding_box()
    assert box and box["y"] + box["height"] < 720, "the reason must be visible without scrolling"
    since = page.locator(".card", has_text="Since that decision was recorded")
    expect(since).to_contain_text("Thesis revised 1 time(s)")
    expect(since).to_contain_text("Broken")

    # --- search finds the passage, with its page
    page.get_by_label("Search notes").fill("retain share after coupling")
    page.keyboard.press("Enter")
    hit = page.locator("li", has_text="Northgate Q4FY26 concall transcript").first
    expect(hit).to_contain_text("p. 2")

    # --- deleting the document demotes the fact; the investor's own words remain
    page.goto(document_url)
    page.get_by_role("button", name="Delete").click()
    page.wait_for_url("**/c/*")
    page.get_by_role("tab", name="Thesis & decisions").click()
    card = page.locator(".card", has_text=ASSUMPTION).first
    expect(card.locator(".badge.gone")).to_have_text("Source deleted")
    expect(card).to_contain_text("The order itself limits round one to DAM.")
    expect(card).not_to_contain_text("round one of coupling covers")
    # The journal entry is untouched.
    expect(page.locator(".card", has_text="recorded").first).to_contain_text(REASON)

    assert not errors, errors
    browser.close()
    print("thesis e2e (success test): ok")
