# L2 · Cloud browsers: same script, different WebSocket URL

**The idea in 60 seconds.** A cloud browser is Chrome running in someone
else's data centre that you drive over the same CDP WebSocket. L1's Playwright
flow runs unchanged: `run.py` asks a provider for a session, passes its
`cdp_url` to `connect_over_cdp`, and calls the same `run_flow()` from
`levels/L1_scripted/flow.py`. What you buy is everything around the browser:
scale (hundreds in parallel), stealth and residential proxies, CAPTCHA
solving, persisted logins (profiles), live view and session recordings, and not
running Chrome on your laptop or server.

## Run

```bash
uv run python -m levels.L2_cloud.run --provider browser-use   # Browser Use Cloud (API v4)
uv run python -m levels.L2_cloud.run --provider tinyfish      # TinyFish Browser API
```

The whole difference from L1, in `run.py`:

```python
with cdp_endpoint(ctx.args.provider) as handle, sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(handle.cdp_url)   # ← the only change from L1
    result = run_flow(browser, ctx)
```

`common/browsers.py` holds the provider calls:

| Provider | Create | Stop |
|----------|--------|------|
| Browser Use Cloud | `POST https://api.browser-use.com/api/v4/browsers` → `cdpUrl`, `liveUrl` | `PATCH /browsers/{id}` `{"action": "stop"}` |
| TinyFish | `POST https://api.browser.tinyfish.ai` → `cdp_url`, `session_id` | `DELETE /{session_id}` |

## Expected output

Measured on 2026-09-27:

| Provider | Result | Time | Cost |
|----------|--------|------|------|
| Local Chrome (L1, for comparison) | ✓ | 3.0 s | $0 |
| Browser Use Cloud browser | ✓ | 14.8 s | ~$0.0003 (browser time; proxy off) |
| TinyFish Browser API | ✓ | 36.4 s | on TinyFish credits |

Most of the extra time is session start-up (TinyFish documents 10–30 s) and the
round trips between your script and a remote browser.

## What to notice

- **Zero automation code changed.** The scoreboard's lines-of-code column counts
  only `run.py`; the flow is L1's.
- **The live view.** Browser Use prints a `liveUrl`. Open it and watch the cloud
  browser work.
- **Traps behave exactly as in L1.** A cloud browser doesn't make a script smarter:
  `--break` still fails. The browser moved, the brittleness didn't.
- **Stop your sessions.** Closing the CDP connection does *not* stop a cloud
  browser or its billing. `browsers.py` stops it in a `finally`, then reads the
  final cost back.

## Gotchas

- Cloud browsers can't reach `localhost`. The mock app is deployed to
  `*.workers.dev` for this reason.
- Browser Use enables a residential proxy by default (billed per GB). We pass
  `proxyCountryCode: null` because GitHub and the mock app don't need one.
- Browser Use Cloud and the open-source `browser-use` package are different
  products. The pinned `browser-use` library ships an old Cloud SDK, so we call
  the v4 REST API with httpx.

## Speaker notes

1. **Put `run.py` next to L1's `run_playwright.py`.** One line differs.
2. **Run Browser Use with the live URL open** on the projector. People like seeing
   a browser they don't own do the clicking.
3. **Talk about what you're paying for:** parallelism, proxies and stealth, CAPTCHAs,
   saved logins, recordings. Mention the ethics line: stealth is for sites you're
   allowed to automate.
4. **Run `--break` on the cloud browser.** It fails the same way. "Moving the browser
   didn't fix brittleness. For that we need the browser to *understand* the page."
   → L3.
