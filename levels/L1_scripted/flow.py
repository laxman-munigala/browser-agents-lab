"""The scripted Playwright flow: every step is a selector someone wrote by hand.

Shared by L1 (local Chrome) and L2 (cloud browsers): both pass in a connected
Playwright `Browser`, and nothing below knows where that browser runs.
"""

from __future__ import annotations

import datetime as dt
import re

from playwright.sync_api import Browser, Page

from common.runner import Context
from common.task import TARGETS

# A script can't "search": it hard-codes what an agent would have looked up.
REPOS = {
    "Playwright": "microsoft/playwright",
    "Selenium": "SeleniumHQ/selenium",
    "Puppeteer": "puppeteer/puppeteer",
}

STEP_TIMEOUT_MS = 15_000


def run_flow(browser: Browser, ctx: Context) -> dict:
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.set_default_timeout(STEP_TIMEOUT_MS)
    try:
        facts = {name: read_repo(page, REPOS[name], ctx) for name in TARGETS}
        ids = {name: find_catalog_id(page, name, facts[name]["language"], ctx) for name in TARGETS}
        rows = [{"catalog_id": ids[n], "name": n, **facts[n]} for n in TARGETS]
        receipt = submit(page, rows, ctx)
        return {"rows": rows, "receipt": receipt}
    finally:
        page.close()


def read_repo(page: Page, repo: str, ctx: Context) -> dict:
    """Search + read: stars, license and main language from the GitHub page."""
    page.goto(f"https://github.com/{repo}", wait_until="domcontentloaded")
    # The star counter's title attribute holds the exact count ("96,717").
    stars = page.locator("#repo-stars-counter-star").first.get_attribute("title") or ""
    # The Languages box renders after load, so wait until it has percentages.
    page.wait_for_function(
        """() => [...document.querySelectorAll('h2')]
             .some(h => h.textContent.trim() === 'Languages'
                     && /%/.test(h.parentElement.parentElement.innerText))"""
    )
    sidebar = page.evaluate(
        """() => {
          const text = t => {
            const h = [...document.querySelectorAll('h2')].find(h => h.textContent.trim() === t);
            return h ? h.parentElement.parentElement.innerText.replace(/\\s+/g, ' ') : '';
          };
          return {about: text('About'), languages: text('Languages')};
        }"""
    )
    license_m = re.search(r"(\S+) license", sidebar["about"])
    lang_m = re.search(r"Languages\s+(.+?)\s+[\d.]+%", sidebar["languages"])
    facts = {
        "stars": int(stars.replace(",", "")),
        "license": license_m.group(1) if license_m else "",
        "language": lang_m.group(1) if lang_m else "",
    }
    ctx.log(f"github {repo}: {facts}")
    return facts


def find_catalog_id(page: Page, name: str, language: str, ctx: Context) -> str:
    """Navigate: filter the catalog by language, then page until the exact name."""
    page.goto(ctx.url("/items"))
    page.select_option("#lang-filter", language)
    page.click("#apply-filter")
    while True:
        page.wait_for_selector("#catalog")
        for row in page.locator("tr.item-row").all():
            if row.locator(".item-name").inner_text().strip() == name:
                cid = row.locator(".item-id").inner_text().strip()
                ctx.log(f"catalog {name}: {cid}")
                return cid
        next_link = page.locator("#next-page")
        if next_link.count() == 0:
            raise LookupError(f"{name} not found in the catalog")
        next_link.click()


def submit(page: Page, rows: list[dict], ctx: Context) -> str:
    """Act: fill the form and read the receipt off the confirmation page."""
    page.goto(ctx.url("/submit"))
    for i, row in enumerate(rows, start=1):
        page.fill(f"#row{i}_catalog_id", row["catalog_id"])
        page.fill(f"#row{i}_name", row["name"])
        page.fill(f"#row{i}_stars", str(row["stars"]))
        page.fill(f"#row{i}_license", row["license"])
        page.select_option(f"#row{i}_language", row["language"])
    page.fill("#checked_on", dt.date.today().isoformat())
    # Playwright waits for the button to exist, be visible and receive clicks:
    # that absorbs the late-loading button, but not a modal covering it.
    page.click("#submit-btn")
    receipt = page.locator("#receipt").inner_text().strip()
    ctx.log(f"receipt: {receipt}")
    return receipt
