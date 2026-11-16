"""End-to-end check of the assistant in a real browser, including the notepad.

    python e2e/assistant.py http://localhost:3000 INVITE_CODE

Uses the built-in test model (not an AI; it quotes the best-matching passage), so the run
costs nothing and needs no key. What it proves is the plumbing: a question becomes a cited
answer, advice is refused, a decision is checked against "How I invest", and the notepad
can ask. It proves nothing about how good a real model's answers are.
"""

import io
import json
import os
import secrets
import shutil
import sys
import tempfile

from playwright.sync_api import expect, sync_playwright
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

BASE, INVITE = sys.argv[1], sys.argv[2]
EMAIL, PASSWORD = f"e2e-{secrets.token_hex(4)}@example.com", "a long test password"
RULE = "I avoid companies where promoters have pledged shares."

EXTENSION = shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension"),
                            os.path.join(tempfile.mkdtemp(), "extension"))
with open(os.path.join(EXTENSION, "manifest.json")) as f:
    manifest = json.load(f)
manifest["host_permissions"] = [BASE.rstrip("/") + "/*"]      # see e2e/capture.py for why
with open(os.path.join(EXTENSION, "manifest.json"), "w") as f:
    json.dump(manifest, f)


def pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=A4)
    sheet.drawString(50, 800, text)
    sheet.save()
    return buffer.getvalue()


with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        tempfile.mkdtemp(), channel="chrome", headless=True,
        args=[f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"])
    worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
    page = context.new_page()
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
    page.wait_for_url("**/c/*")
    company_url = page.url

    page.get_by_role("tab", name="Documents").click()
    page.locator("input[type=file]").set_input_files({
        "name": "Northgate Annual Report FY25.pdf", "mimeType": "application/pdf",
        "buffer": pdf("Revenue from operations was 608 crore in FY25. Promoters have pledged no shares.")})
    page.get_by_role("button", name="Upload").click()
    expect(page.locator("li", has_text="Northgate Annual Report FY25")).to_contain_text("1 page(s)", timeout=15000)

    # --- before a model is connected, asking says so and sends nothing
    page.get_by_role("tab", name="Ask").click()
    expect(page.get_by_text("No model connected yet")).to_be_visible()

    # --- settings: rules, the test model, a token that may ask
    page.get_by_role("navigation").get_by_role("link", name="Settings").click()
    page.get_by_label("How I invest").fill(f"{RULE}\nNo position above 10 percent of the portfolio.")
    page.get_by_role("button", name="Save as new version").click()
    expect(page.get_by_text("Saved as version 1")).to_be_visible()
    page.get_by_role("button", name="Use the built-in test model").click()
    expect(page.locator("li", has_text="Built-in test model")).to_be_visible()
    page.get_by_placeholder("Name this browser, e.g. MacBook Chrome").fill("Test Chrome")
    page.get_by_label("Allow this browser to ask questions and read answers").check()
    page.get_by_role("button", name="Create token").click()
    token = page.get_by_label("New token").input_value()
    expect(page.locator("li", has_text="Test Chrome")).to_contain_text("captures and questions")

    # --- ask in the app: a cited answer
    page.goto(company_url)
    page.get_by_role("tab", name="Ask").click()
    page.get_by_label("Your question").fill("What was revenue from operations?")
    page.get_by_role("button", name="Ask", exact=True).click()
    card = page.locator(".card", has_text="What was revenue from operations?")
    expect(card.locator(".quote")).to_have_text("“Revenue from operations was 608 crore in FY25.”", timeout=15000)
    expect(card.get_by_role("link", name="Northgate Annual Report FY25 · FY25 · p. 1")).to_be_visible()
    expect(card.locator(".badge.ai")).to_have_text("AI")

    # --- advice is refused
    page.get_by_label("Your question").fill("Should I buy this stock?")
    page.get_by_role("button", name="Ask", exact=True).click()
    expect(page.locator(".card", has_text="Should I buy this stock?")).to_contain_text(
        "does not give buy, sell or sizing advice", timeout=15000)

    # --- the guardrail: a decision is checked against "How I invest" before it is recorded
    page.get_by_role("tab", name="Thesis & decisions").click()
    form = page.locator("form", has_text="The one reason that decided it")
    form.get_by_label("The one reason that decided it").fill("Cheap after the fall; the business is unchanged.")
    form.get_by_role("button", name="Record decision").click()
    check = page.get_by_label("Check against How I invest")
    expect(check).to_contain_text(RULE)
    expect(page.get_by_text("No entries yet.")).to_be_visible()          # nothing recorded yet
    form.get_by_role("button", name="Record anyway").click()
    entry = page.locator(".card", has_text="recorded").first
    expect(entry).to_contain_text("Recorded after this was raised")
    page.get_by_role("tab", name="Overview").click()
    expect(page.get_by_label("Last decision")).to_contain_text(RULE)

    # --- the notepad asks, and shows the answer with its source
    panel = context.new_page()
    panel.goto(f"chrome-extension://{worker.url.split('/')[2]}/panel.html")
    panel.locator("#server").fill(BASE)
    panel.locator("#token").fill(token)
    panel.get_by_role("button", name="Connect").click()
    panel.get_by_role("radio", name="Ask now").check()
    expect(panel.get_by_role("button", name="Ask")).to_be_visible()
    panel.locator("#subject").select_option(label="Northgate Power Exchange")
    panel.locator("#body").fill("Have promoters pledged shares?")
    panel.locator("#body").press("Control+Enter")
    answer = panel.locator("#answer")
    expect(answer).to_contain_text("From your notes and documents", timeout=20000)
    expect(answer.locator("q")).to_have_text("Revenue from operations was 608 crore in FY25.")
    expect(answer).to_contain_text("Northgate Annual Report FY25 · FY25 · p. 1")
    # The test model quotes the first sentence of the best-matching passage whatever was asked —
    # which is exactly why it is labelled "not an AI".

    # the question asked in the notepad is on the company's Ask tab too
    page.get_by_role("tab", name="Ask").click()
    expect(page.locator(".card", has_text="Have promoters pledged shares?")).to_be_visible()

    assert not errors, errors
    context.close()
    print("assistant e2e: ok")
