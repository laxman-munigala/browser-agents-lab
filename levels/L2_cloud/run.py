"""L2 · The L1 Playwright flow on a cloud browser. Only the CDP URL changes.

    uv run python -m levels.L2_cloud.run --provider browser-use
    uv run python -m levels.L2_cloud.run --provider tinyfish
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from common.browsers import cdp_endpoint
from common.runner import Context, Outcome, run
from levels.L1_scripted.flow import run_flow

LABELS = {"browser-use": "Browser Use Cloud browser", "tinyfish": "TinyFish Browser API"}


def solve(ctx: Context) -> Outcome:
    with cdp_endpoint(ctx.args.provider) as handle, sync_playwright() as p:
        if handle.live_url:
            ctx.log(f"watch live: {handle.live_url}")
        browser = p.chromium.connect_over_cdp(handle.cdp_url)  # ← the only change from L1
        result = run_flow(browser, ctx)
    # The handle's cost is filled in after the session is stopped (on exit).
    return Outcome(result=result, cost_usd=handle.cost_usd, extra={"session": handle.session_id, **handle.info})


def add_args(p):
    p.add_argument("--provider", choices=sorted(LABELS), default="browser-use")


if __name__ == "__main__":
    import argparse

    pre = argparse.ArgumentParser(add_help=False)
    add_args(pre)
    provider = pre.parse_known_args()[0].provider
    raise SystemExit(run("L2", LABELS[provider], solve, sources=[__file__], add_args=add_args))
