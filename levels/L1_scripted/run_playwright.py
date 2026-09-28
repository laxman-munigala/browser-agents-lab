"""L1 · Playwright on your local Chrome, over CDP.

    uv run python -m levels.L1_scripted.run_playwright
    uv run python -m levels.L1_scripted.run_playwright --traps late,modal
    uv run python -m levels.L1_scripted.run_playwright --break
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from common.browsers import cdp_endpoint
from common.runner import Context, Outcome, run
from levels.L1_scripted.flow import run_flow


def solve(ctx: Context) -> Outcome:
    with cdp_endpoint("local") as handle, sync_playwright() as p:
        ctx.log(f"attaching to {handle.cdp_url}")
        browser = p.chromium.connect_over_cdp(handle.cdp_url)
        return Outcome(result=run_flow(browser, ctx))


if __name__ == "__main__":
    from levels.L1_scripted import flow

    raise SystemExit(run("L1", "Playwright (local CDP)", solve, sources=[__file__, flow.__file__]))
