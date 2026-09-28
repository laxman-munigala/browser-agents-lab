"""Where a level gets its browser: one CDP endpoint, whatever the provider.

    with cdp_endpoint("local") as b:            # real Chrome via cdp_discovery
    with cdp_endpoint("browser-use") as b:      # Browser Use Cloud (API v4)
    with cdp_endpoint("tinyfish") as b:         # TinyFish Browser API
        browser = playwright.chromium.connect_over_cdp(b.cdp_url)

This is the whole point of L2: the automation code doesn't change, only the
WebSocket URL does. Cloud sessions are stopped on exit, because closing the
CDP connection does *not* stop (or stop billing for) a cloud browser.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

from common.config import load_env, require

PROVIDERS = ("local", "browser-use", "tinyfish")

BROWSER_USE_API = "https://api.browser-use.com/api/v4"
TINYFISH_BROWSER_API = "https://api.browser.tinyfish.ai"


@dataclass
class BrowserHandle:
    provider: str
    cdp_url: str
    live_url: str | None = None
    session_id: str | None = None
    # Filled in after the session stops, when the provider reports it.
    cost_usd: float | None = None
    info: dict[str, Any] = field(default_factory=dict)


def local_cdp_url(auto_launch: bool | None = None) -> str:
    """The lab's local Chrome. Env must be loaded before cdp_discovery is imported,
    because it reads BU_CDP_PROFILE / BU_CDP_SEED at import time."""
    load_env()
    from common.cdp_discovery import discover_cdp

    return discover_cdp(auto_launch=auto_launch)


@contextlib.contextmanager
def cdp_endpoint(provider: str = "local", **kwargs: Any) -> Iterator[BrowserHandle]:
    load_env()
    if provider == "local":
        yield BrowserHandle("local", local_cdp_url())
    elif provider == "browser-use":
        yield from _browser_use(**kwargs)
    elif provider == "tinyfish":
        yield from _tinyfish(**kwargs)
    else:
        raise ValueError(f"unknown provider {provider!r}; expected one of {PROVIDERS}")


def _browser_use(proxy_country_code: str | None = None, timeout_min: int = 15) -> Iterator[BrowserHandle]:
    headers = {"X-Browser-Use-API-Key": require("BROWSER_USE_API_KEY")}
    with httpx.Client(base_url=BROWSER_USE_API, headers=headers, timeout=90) as client:
        # proxyCountryCode=None runs without the residential proxy: our targets
        # (GitHub, the mock app) don't need one, and proxy traffic costs extra.
        body = {"proxyCountryCode": proxy_country_code, "timeout": timeout_min}
        session = client.post("/browsers", json=body).raise_for_status().json()
        handle = BrowserHandle(
            "browser-use", session["cdpUrl"], live_url=session.get("liveUrl"), session_id=session["id"]
        )
        try:
            yield handle
        finally:
            with contextlib.suppress(httpx.HTTPError):
                client.patch(f"/browsers/{handle.session_id}", json={"action": "stop"}).raise_for_status()
            with contextlib.suppress(httpx.HTTPError, KeyError, ValueError):
                final = client.get(f"/browsers/{handle.session_id}").raise_for_status().json()
                handle.info = {k: final.get(k) for k in ("browserCost", "proxyCost", "proxyUsedMb")}
                handle.cost_usd = float(final.get("browserCost") or 0) + float(final.get("proxyCost") or 0)


def _tinyfish(start_url: str | None = None, timeout_seconds: int = 600) -> Iterator[BrowserHandle]:
    headers = {"X-API-Key": require("TINYFISH_API_KEY")}
    with httpx.Client(headers=headers, timeout=90) as client:
        body: dict[str, Any] = {"timeout_seconds": timeout_seconds}
        if start_url:
            body["url"] = start_url
        session = client.post(TINYFISH_BROWSER_API, json=body).raise_for_status().json()
        handle = BrowserHandle(
            "tinyfish", session["cdp_url"], session_id=session["session_id"],
            info={"base_url": session.get("base_url")},
        )
        try:
            yield handle
        finally:
            with contextlib.suppress(httpx.HTTPError):
                client.delete(f"{TINYFISH_BROWSER_API}/{handle.session_id}")
