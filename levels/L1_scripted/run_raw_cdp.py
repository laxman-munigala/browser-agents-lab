"""L1 · The same flow over raw CDP: JSON messages on a WebSocket, no library.

    uv run python -m levels.L1_scripted.run_raw_cdp

Everything Playwright gave us for free is written by hand here: opening a tab,
waiting for load, waiting for elements, filling inputs, clicking at real
coordinates. Compare the line count on the scoreboard.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re
import time
from typing import Any

import httpx
from websockets.sync.client import connect

from common.browsers import local_cdp_url
from common.runner import Context, Outcome, run
from common.task import TARGETS
from levels.L1_scripted.flow import REPOS


class CDP:
    """A minimal CDP client: send a command, wait for the reply with the same id."""

    def __init__(self, ws_url: str):
        self.ws = connect(ws_url, max_size=None)
        self.ids = itertools.count(1)
        self.session: str | None = None

    def send(self, method: str, params: dict | None = None, session: bool = True) -> dict:
        msg: dict[str, Any] = {"id": next(self.ids), "method": method, "params": params or {}}
        if session and self.session:
            msg["sessionId"] = self.session
        self.ws.send(json.dumps(msg))
        while True:  # skip events until our reply arrives
            reply = json.loads(self.ws.recv())
            if reply.get("id") == msg["id"]:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def eval(self, expression: str) -> Any:
        r = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", "JS error"))
        return r["result"].get("value")

    def wait_for(self, expression: str, timeout: float = 15.0) -> Any:
        """Our own auto-wait: poll a JS expression until it is truthy."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.eval(expression)
            if value:
                return value
            time.sleep(0.2)
        raise TimeoutError(f"timed out waiting for: {expression[:80]}")

    def goto(self, url: str) -> None:
        self.send("Page.navigate", {"url": url})
        time.sleep(0.3)  # let the old document unload before polling the new one
        self.wait_for("document.readyState === 'complete'", timeout=30)

    def click(self, selector: str) -> None:
        """A real mouse click at the element's centre, like a user (and Playwright)."""
        box = self.wait_for(
            f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
                 if (!el) return null; el.scrollIntoView({{block: 'center'}});
                 const r = el.getBoundingClientRect();
                 return r.width ? {{x: r.x + r.width / 2, y: r.y + r.height / 2}} : null; }})()"""
        )
        for kind in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent",
                      {"type": kind, "x": box["x"], "y": box["y"], "button": "left", "clickCount": 1})

    def fill(self, selector: str, value: str) -> None:
        """Set an input's value and fire the events a framework would listen for."""
        self.wait_for(f"!!document.querySelector({json.dumps(selector)})")
        self.eval(
            f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
                 el.value = {json.dumps(value)};
                 el.dispatchEvent(new Event('input', {{bubbles: true}}));
                 el.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"""
        )


def browser_ws_url() -> str:
    url = local_cdp_url()
    if url.startswith("ws"):
        return url
    return httpx.get(f"{url}/json/version").json()["webSocketDebuggerUrl"]


def solve(ctx: Context) -> Outcome:
    cdp = CDP(browser_ws_url())
    target = cdp.send("Target.createTarget", {"url": "about:blank"}, session=False)["targetId"]
    cdp.session = cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}, session=False)["sessionId"]
    try:
        cdp.send("Page.enable")
        facts = {}
        for name in TARGETS:
            cdp.goto(f"https://github.com/{REPOS[name]}")
            stars = cdp.wait_for("document.querySelector('#repo-stars-counter-star')?.getAttribute('title')")
            side = cdp.wait_for(
                """(() => { const t = s => { const h = [...document.querySelectorAll('h2')]
                     .find(h => h.textContent.trim() === s);
                     return h ? h.parentElement.parentElement.innerText.replace(/\\s+/g, ' ') : ''; };
                   const langs = t('Languages');
                   return /%/.test(langs) ? {about: t('About'), langs} : null; })()"""
            )
            facts[name] = {
                "stars": int(stars.replace(",", "")),
                "license": re.search(r"(\S+) license", side["about"]).group(1),
                "language": re.search(r"Languages\s+(.+?)\s+[\d.]+%", side["langs"]).group(1),
            }
            ctx.log(f"github {name}: {facts[name]}")

        ids = {}
        for name in TARGETS:
            cdp.goto(ctx.url("/items", lang=facts[name]["language"]))
            while name not in ids:
                found = cdp.eval(
                    f"""[...document.querySelectorAll('tr.item-row')]
                        .filter(r => r.querySelector('.item-name').textContent.trim() === {json.dumps(name)})
                        .map(r => r.querySelector('.item-id').textContent.trim())[0] || null"""
                )
                if found:
                    ids[name] = found
                elif cdp.eval("!!document.querySelector('#next-page')"):
                    cdp.click("#next-page")
                    time.sleep(0.3)
                    cdp.wait_for("document.readyState === 'complete'")
                else:
                    raise LookupError(f"{name} not in catalog")
            ctx.log(f"catalog {name}: {ids[name]}")

        rows = [{"catalog_id": ids[n], "name": n, **facts[n]} for n in TARGETS]
        cdp.goto(ctx.url("/submit"))
        for i, row in enumerate(rows, start=1):
            for key in ("catalog_id", "name", "stars", "license", "language"):
                cdp.fill(f"#row{i}_{key}", str(row[key]))
        cdp.fill("#checked_on", dt.date.today().isoformat())
        cdp.click("#submit-btn")
        time.sleep(0.3)
        receipt = cdp.wait_for("document.querySelector('#receipt')?.textContent.trim()")
        ctx.log(f"receipt: {receipt}")
        return Outcome(result={"rows": rows, "receipt": receipt})
    finally:
        cdp.send("Target.closeTarget", {"targetId": target}, session=False)
        cdp.ws.close()


if __name__ == "__main__":
    raise SystemExit(run("L1", "Raw CDP (websockets)", solve, sources=[__file__]))
