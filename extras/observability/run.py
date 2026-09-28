"""Extra · Observability: watch what a run actually did.

    uv run python -m extras.observability.run             # L1 flow with a Playwright trace + network log
    uv run playwright show-trace traces/<run-id>.zip       # step-by-step replay: DOM, screenshots, network

Three layers, from the cheapest up:
  1. The lab's own logs and runs/<run-id>.json (every level writes one)
  2. A network log: every request the pages made (Playwright's request
     events, which are CDP Network.requestWillBeSent underneath)
  3. A Playwright trace: a replayable timeline of actions, DOM snapshots, screenshots
Cloud providers add a fourth: live view and session recordings (L2/L4 print the URLs).
"""

from __future__ import annotations

import json
from collections import Counter

from playwright.sync_api import sync_playwright

from common.browsers import cdp_endpoint
from common.config import LAB_ROOT
from common.runner import Context, Outcome, run
from levels.L1_scripted.flow import run_flow

TRACES = LAB_ROOT / "traces"


def solve(ctx: Context) -> Outcome:
    TRACES.mkdir(exist_ok=True)
    with cdp_endpoint("local") as handle, sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(handle.cdp_url)
        context = browser.contexts[0]

        # 2. Network log for every tab the flow opens in this context.
        requests: list[dict] = []
        context.on("request", lambda r: requests.append({"method": r.method, "url": r.url, "type": r.resource_type}))

        # 3. Playwright trace.
        context.tracing.start(screenshots=True, snapshots=True, sources=False, title=ctx.run_id)
        try:
            result = run_flow(browser, ctx)
        finally:
            trace = TRACES / f"{ctx.run_id}.zip"
            context.tracing.stop(path=str(trace))

    netlog = TRACES / f"{ctx.run_id}.network.jsonl"
    netlog.write_text("\n".join(json.dumps(r) for r in requests))
    by_host = Counter(r["url"].split("/")[2] for r in requests if "://" in r["url"])
    by_type = Counter(r["type"] for r in requests)
    ctx.log(f"trace:   {trace.relative_to(LAB_ROOT)}  (uv run playwright show-trace {trace.relative_to(LAB_ROOT)})")
    ctx.log(f"network: {len(requests)} requests → {netlog.relative_to(LAB_ROOT)}")
    ctx.log(f"  by type: {dict(by_type.most_common(6))}")
    ctx.log(f"  top hosts: {dict(by_host.most_common(5))}")
    return Outcome(result=result, notes=f"trace + {len(requests)} network requests captured")


if __name__ == "__main__":
    raise SystemExit(run("X", "Playwright + trace (observability)", solve, sources=[__file__]))
