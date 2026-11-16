"""End-to-end check of the browser extension against a running Invest-pad.

    python e2e/capture.py http://localhost:3000 INVITE_CODE

Loads the real extension into Chrome, connects it with a token made in Settings, saves a
question with page context, and follows it through the inbox into a note. Also checks that
a capture made while Invest-pad is unreachable is kept and sent later.

One difference from a real install: Chrome's "allow this extension to reach <address>?"
prompt cannot be answered in an automated browser, so the test loads a copy of the
extension whose manifest already grants the test address. The code under test is the same.

What this cannot drive, and so does not check: the toolbar button, the keyboard shortcut,
the right-click menu and the side panel frame itself. Those are browser chrome. The panel
is opened here as an ordinary extension page, and the page context is planted the way the
background script would store it.
"""

import json
import os
import re
import secrets
import shutil
import sys
import tempfile

from playwright.sync_api import expect, sync_playwright

BASE, INVITE = sys.argv[1], sys.argv[2]
EXTENSION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension")
EMAIL, PASSWORD = f"e2e-{secrets.token_hex(4)}@example.com", "a long test password"

# A copy of the extension with the test address pre-granted (see the note above).
EXTENSION = shutil.copytree(EXTENSION, os.path.join(tempfile.mkdtemp(), "extension"))
with open(os.path.join(EXTENSION, "manifest.json")) as f:
    manifest = json.load(f)
manifest["host_permissions"] = [BASE.rstrip("/") + "/*"]
with open(os.path.join(EXTENSION, "manifest.json"), "w") as f:
    json.dump(manifest, f)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        tempfile.mkdtemp(), channel="chrome", headless=True,
        args=[f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"])
    worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
    extension_id = worker.url.split("/")[2]

    # --- in the web app: sign up, add a company, create a token
    app = context.new_page()
    app.goto(f"{BASE}/login")
    app.get_by_role("button", name="I have an invite code").click()
    app.get_by_placeholder("Email").fill(EMAIL)
    app.get_by_placeholder("Password (10+ characters)").fill(PASSWORD)
    app.get_by_placeholder("Invite code").fill(INVITE)
    app.get_by_role("button", name="Create account").click()
    app.get_by_placeholder("Add a company, e.g. IEX").fill("IEX")
    app.get_by_role("button", name="Add company").click()
    expect(app.get_by_role("link", name="IEX")).to_be_visible()

    app.get_by_role("link", name="Settings").click()
    app.get_by_placeholder("Name this browser, e.g. MacBook Chrome").fill("Test Chrome")
    app.get_by_role("button", name="Create token").click()
    token = app.get_by_label("New token").input_value()
    assert token.startswith("ipx_")

    # --- in the extension: connect
    panel = context.new_page()
    panel.goto(f"chrome-extension://{extension_id}/panel.html")
    expect(panel.get_by_role("heading", name="Connect to Invest-pad")).to_be_visible()
    panel.locator("#server").fill(BASE.replace("http://", ""))       # typed without the scheme
    panel.locator("#token").fill("ipx_wrong")
    panel.get_by_role("button", name="Connect").click()
    expect(panel.locator("#setup-status")).to_have_text("That token was not accepted.")
    panel.locator("#token").fill(token)
    panel.get_by_role("button", name="Connect").click()
    expect(panel.locator("#body")).to_be_visible()
    expect(panel.locator("#subject option")).to_have_text(["Decide later", "IEX"])

    # --- the background script would store this when the notepad is opened on a page
    worker.evaluate("""() => chrome.storage.session.set({context: {
        url: "https://example.com/coupling", title: "Coupling explained",
        selection: "Round one covers the day-ahead market only.", at: Date.now()}})""")
    expect(panel.locator("#selection")).to_have_text("Round one covers the day-ahead market only.")
    expect(panel.locator("#page")).to_contain_text("Coupling explained — https://example.com/coupling")

    # --- save a question
    panel.get_by_role("radio", name="Question").check()
    panel.locator("#body").fill("Does coupling reach the real-time market?")
    panel.locator("#subject").select_option(label="IEX")
    panel.locator("#body").press("Control+Enter")
    expect(panel.locator("#status")).to_have_text("Saved to your inbox.")
    expect(panel.locator("#body")).to_have_value("")

    # --- unreachable server: the note is kept, then sent when the connection returns
    panel.route("**/api/ext/captures", lambda route: route.abort())
    panel.get_by_role("radio", name="Note").check()
    panel.locator("#body").fill("Written while offline.")
    panel.get_by_role("button", name="Save to inbox").click()
    expect(panel.locator("#status")).to_contain_text("Can’t reach Invest-pad. Saved here")
    queued = panel.evaluate("() => chrome.storage.local.get('queue')")["queue"]
    assert [c["body"] for c in queued] == ["Written while offline."]
    panel.unroute("**/api/ext/captures")
    panel.evaluate("() => window.dispatchEvent(new Event('online'))")
    expect(panel.locator("#status")).to_have_text("Saved to your inbox.")
    assert panel.evaluate("() => chrome.storage.local.get('queue')")["queue"] == []

    # --- back in the web app: both are in the inbox; the question becomes a note
    app.get_by_role("link", name=re.compile("^Inbox")).click()
    expect(app.get_by_role("link", name="Inbox (2)")).to_be_visible()
    question = app.locator("li", has_text="Does coupling reach the real-time market?")
    expect(question).to_contain_text("Round one covers the day-ahead market only.")
    expect(question.get_by_role("link", name="Coupling explained")).to_have_attribute("href", "https://example.com/coupling")
    expect(question.get_by_label("Company").locator("option:checked")).to_have_text("IEX")
    expect(app.locator("li", has_text="Written while offline.")).to_be_visible()

    question.get_by_role("button", name="Make a note").click()
    app.wait_for_url("**/n/*")
    expect(app.get_by_label("Note title")).to_have_value("Does coupling reach the real-time market?")
    expect(app.locator(".bn-editor")).to_contain_text("Round one covers the day-ahead market only.")
    expect(app.locator(".bn-editor")).to_contain_text("Source: Coupling explained")
    expect(app.get_by_role("link", name="← Company")).to_be_visible()      # filed under IEX

    # --- revoke the token: the extension is told, and nothing is lost
    app.get_by_role("link", name="Settings").click()
    app.once("dialog", lambda d: d.accept())
    app.get_by_role("button", name="Revoke").click()
    expect(app.get_by_text("revoked")).to_be_visible()
    panel.locator("#body").fill("After revoke.")
    panel.get_by_role("button", name="Save to inbox").click()
    expect(panel.locator("#status")).to_contain_text("no longer accepts this token")
    assert len(panel.evaluate("() => chrome.storage.local.get('queue')")["queue"]) == 1

    context.close()
    print("capture e2e: ok")
