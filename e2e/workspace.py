"""End-to-end check of the workspace in a real browser.

    python e2e/workspace.py http://localhost:3000 INVITE_CODE

Needs the API and the web app running, an unused invite code, and
`pip install playwright` with Chrome installed. Not part of CI yet.
"""

import secrets
import sys

from playwright.sync_api import expect, sync_playwright

BASE, INVITE = sys.argv[1], sys.argv[2]
EMAIL, PASSWORD = f"e2e-{secrets.token_hex(4)}@example.com", "a long test password"


def new_note(page, title: str, text: str) -> None:
    page.get_by_placeholder("New note title").fill(title)
    page.get_by_role("button", name="New note").click()
    page.wait_for_url("**/n/*")
    editor = page.locator(".bn-editor")
    editor.click()
    page.keyboard.type(text)
    expect(page.get_by_text("Unsaved changes")).to_be_visible()
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("Saved as version 2")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # Signed out: the home page sends you to login.
    page.goto(BASE)
    page.wait_for_url("**/login")

    # Sign up with the invite.
    page.get_by_role("button", name="I have an invite code").click()
    page.get_by_placeholder("Email").fill(EMAIL)
    page.get_by_placeholder("Password (10+ characters)").fill(PASSWORD)
    page.get_by_placeholder("Invite code").fill(INVITE)
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Companies")).to_be_visible()
    expect(page.get_by_text(EMAIL)).to_be_visible()

    # Add a company and open it.
    page.get_by_placeholder("Add a company, e.g. IEX").fill("IEX")
    page.get_by_role("button", name="Add company").click()
    page.get_by_role("link", name="IEX").click()
    page.wait_for_url("**/c/*")
    company_url = page.url

    # Two notes: the second links to the first and to one that does not exist.
    new_note(page, "Market coupling", "Coupling removes the liquidity edge in DAM.")
    page.goto(company_url)
    new_note(page, "IEX thesis", "Rests on [[Market coupling]] and [[Switching costs]]. Zebrafish marker.")

    # Outgoing links: one resolves, one offers to be created.
    side = page.locator("aside")
    expect(side.get_by_role("link", name="Market coupling")).to_be_visible()
    expect(side.get_by_role("button", name="switching costs — create")).to_be_visible()

    # Reload: the text came back from the server.
    page.reload()
    expect(page.locator(".bn-editor")).to_contain_text("Zebrafish marker")

    # Follow the link; the target shows the backlink with its surrounding text.
    page.locator("aside").get_by_role("link", name="Market coupling").click()
    expect(page.get_by_label("Note title")).to_have_value("Market coupling")
    back = page.locator("aside")
    expect(back.get_by_role("link", name="IEX thesis")).to_be_visible()
    expect(back).to_contain_text("Rests on [[Market coupling]]")

    # Rename the target; the linking note is updated and says why.
    page.get_by_label("Note title").fill("Coupling of DAM")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("links updated in 1 other note")
    page.locator("aside").get_by_role("link", name="IEX thesis").click()
    expect(page.locator(".bn-editor")).to_contain_text("[[Coupling of DAM]]")
    expect(page.locator("aside")).to_contain_text("a note was renamed")

    # History: version 2 still shows the old link text.
    page.locator("aside").get_by_role("button", name="Version 2").click()
    expect(page.locator(".version")).to_contain_text("[[Market coupling]]")

    # Search finds the note and highlights the word.
    page.get_by_label("Search notes").fill("zebrafish")
    page.keyboard.press("Enter")
    page.wait_for_url("**/search?q=zebrafish")
    expect(page.locator("mark")).to_have_text("Zebrafish")
    expect(page.get_by_role("link", name="IEX thesis")).to_be_visible()

    # Sign out; the session is gone.
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url("**/login")
    page.goto(company_url)
    page.wait_for_url("**/login")

    assert not errors, errors
    browser.close()
    print("workspace e2e: ok")
