"""Extra · Auth & sessions: which identity does the lab browser have?

    uv run python -m extras.auth_sessions.check                   # the lab's clean profile
    BU_CDP_PROFILE=~/.config/google-chrome-cdp BU_CDP_SEED=1 \\
        uv run python -m extras.auth_sessions.check               # the seeded profile (your logins)

Read-only: it opens github.com and reports whether that browser is signed in
and how many cookies it holds. It never clicks anything. It also shows the
portable alternative to a profile: Playwright's storage_state (cookies +
localStorage as JSON), saved and loaded into a fresh context.
"""

from __future__ import annotations

import json
import os

from playwright.sync_api import sync_playwright

from common.browsers import local_cdp_url
from common.config import LAB_ROOT, load_env


def main() -> None:
    load_env()
    profile = os.environ.get("BU_CDP_PROFILE", "~/.config/google-chrome-cdp")
    seeded = os.environ.get("BU_CDP_SEED", "1") not in ("0", "false", "no", "off")
    print(f"profile: {profile}  (seeding {'on' if seeded else 'off'})")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(local_cdp_url())
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto("https://github.com/", wait_until="domcontentloaded")
            signed_in = page.evaluate("!!document.querySelector('meta[name=user-login][content]:not([content=\"\"])')")
            user = page.evaluate("document.querySelector('meta[name=user-login]')?.content || null")
            cookies = context.cookies()
            gh = [c for c in cookies if "github.com" in c["domain"]]
            print(f"github.com: {'signed in as ' + user if signed_in else 'not signed in'}")
            print(f"cookies in this browser: {len(cookies)} total, {len(gh)} for github.com")

            # storage_state: a portable snapshot of a session, no profile directory needed.
            state_path = LAB_ROOT / "runs" / "storage_state.example.json"
            state_path.parent.mkdir(exist_ok=True)
            state = context.storage_state(path=str(state_path))
            print(f"storage_state: {len(state['cookies'])} cookies, {len(state['origins'])} origins → {state_path.relative_to(LAB_ROOT)}")
            print("  (load it with browser.new_context(storage_state=...); treat the file like a password)")
        finally:
            page.close()


if __name__ == "__main__":
    main()
