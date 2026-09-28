"""L7 · The web meets agents halfway: call the form as a WebMCP tool.

    uv run python -m levels.L7_future.run_webmcp

The mock app's form page registers a tool, `submit_report`, with
document.modelContext.registerTool() (see webmcpHead() in mock-app/src/index.ts). An agent
that speaks WebMCP doesn't look for fields or buttons at all: it lists the
page's tools and calls one with JSON. This script is that agent, in raw CDP:

  1. read /llms.txt, the site's plain-text self-description
  2. launch Chrome with WebMCP turned on (--enable-features=WebMCPTesting,...)
  3. open /submit, send WebMCP.enable, receive WebMCP.toolsAdded
  4. WebMCP.invokeTool("submit_report", {rows, checked_on}) → WebMCP.toolResponded

Like L6, the facts are supplied (goal.py): this measures the act step.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import shutil
import subprocess
import tempfile
import time
from typing import Any

import httpx
from websockets.sync.client import connect

from common.runner import Context, Outcome, run
from common.task import parse_result
from levels.L6_speed.goal import expected_rows

# chrome://flags/#enable-webmcp-testing, plus the DevTools protocol domain.
WEBMCP_FLAGS = "--enable-features=WebMCPTesting,DevToolsWebMCPSupport"
PORT = 9231


class CDP:
    """Commands plus an event inbox (L1's client only needed replies)."""

    def __init__(self, ws_url: str):
        self.ws = connect(ws_url, max_size=None)
        self.ids = itertools.count(1)
        self.events: list[dict] = []
        self.session: str | None = None

    def send(self, method: str, params: dict | None = None, session: bool = True) -> dict:
        msg: dict[str, Any] = {"id": next(self.ids), "method": method, "params": params or {}}
        if session and self.session:
            msg["sessionId"] = self.session
        self.ws.send(json.dumps(msg))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == msg["id"]:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})
            if "method" in reply:
                self.events.append(reply)

    def wait_event(self, method: str, pred=lambda e: True, timeout: float = 15) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for e in self.events:
                if e["method"] == method and pred(e["params"]):
                    self.events.remove(e)
                    return e["params"]
            try:
                msg = json.loads(self.ws.recv(timeout=max(0.1, deadline - time.monotonic())))
            except TimeoutError:
                break
            if "method" in msg:
                self.events.append(msg)
        raise TimeoutError(f"no {method} event")


def launch_chrome() -> tuple[subprocess.Popen, str, str]:
    profile = tempfile.mkdtemp(prefix="lab-webmcp-")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    proc = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={PORT}", WEBMCP_FLAGS,
         "--headless=new", "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            return proc, httpx.get(f"http://127.0.0.1:{PORT}/json/version").json()["webSocketDebuggerUrl"], profile
        except httpx.HTTPError:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("Chrome with WebMCP did not start")


def solve(ctx: Context) -> Outcome:
    llms = httpx.get(f"{ctx.base_url}/llms.txt").text
    ctx.log(f"/llms.txt: {llms.splitlines()[0]} … ({len(llms)} chars)")

    proc, ws_url, profile = launch_chrome()
    cdp = CDP(ws_url)
    try:
        target = cdp.send("Target.createTarget", {"url": "about:blank"}, session=False)["targetId"]
        cdp.session = cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}, session=False)["sessionId"]
        cdp.send("Page.enable")
        cdp.send("Page.navigate", {"url": ctx.url("/submit")})
        cdp.wait_event("Page.loadEventFired", timeout=30)

        started = time.monotonic()
        cdp.send("WebMCP.enable")
        added = cdp.wait_event("WebMCP.toolsAdded", lambda p: bool(p.get("tools")))
        tools = {t["name"]: t for t in added["tools"]}
        ctx.log(f"page tools: {list(tools)}")
        tool = tools["submit_report"]

        rows = expected_rows()
        invoked = cdp.send("WebMCP.invokeTool", {
            "frameId": tool["frameId"],
            "toolName": "submit_report",
            "input": {"rows": rows, "checked_on": dt.date.today().isoformat()},
        })
        resp = cdp.wait_event("WebMCP.toolResponded", lambda p: p.get("invocationId") == invoked["invocationId"])
        act_ms = (time.monotonic() - started) * 1000
        ctx.log(f"tool responded ({resp.get('status')}) in {act_ms:.0f} ms")
        output = resp.get("output")
        text = json.dumps(output)
        # execute() returns the POST reply as a JSON string.
        data = parse_result(output if isinstance(output, (str, dict)) else text) or {}
        receipt = data.get("receipt")
        ctx.log(f"receipt: {receipt}")
        return Outcome(
            result={"rows": rows, "receipt": receipt},
            notes=f"act step via WebMCP tool call in {act_ms:.0f} ms; 0 LLM tokens (a WebMCP-aware agent would pick the tool)",
            extra={"tool": tool, "raw_output": text[:500]},
        )
    finally:
        cdp.ws.close()
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run("L7", "WebMCP tool call (act step)", solve, sources=[__file__]))
