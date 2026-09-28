# L1 · Scripted browser: Playwright vs raw CDP

**The idea in 60 seconds.** Chrome exposes the *Chrome DevTools Protocol* (CDP):
JSON messages over a WebSocket (`Page.navigate`, `Runtime.evaluate`,
`Input.dispatchMouseEvent`, …). Every browser tool in this lab, from Playwright
to autonomous agents, ends up sending these messages. Playwright is a library
on top of CDP that adds the things you'd otherwise write yourself: waiting for
pages and elements, locators, real clicks that check the element can receive
them, tracing. Here we run the same task both ways against a real Chrome on
your machine, with every step a selector a human wrote.

## Run

```bash
uv run python -m levels.L1_scripted.run_playwright           # Playwright over CDP
uv run python -m levels.L1_scripted.run_raw_cdp              # raw CDP, no library
uv run python -m levels.L1_scripted.run_playwright --traps late
uv run python -m levels.L1_scripted.run_playwright --traps modal
uv run python -m levels.L1_scripted.run_playwright --break
```

Both scripts attach to the lab's Chrome through `common/cdp_discovery.py`. If no
debuggable Chrome is running it launches one on the clean lab profile
(`~/.config/google-chrome-cdp-lab`, port 9222 or 9223) and leaves it open.

| File | What it is |
|------|------------|
| `flow.py` | The Playwright flow (GitHub → catalog → form). L2 reuses it unchanged. |
| `run_playwright.py` | Attaches to local Chrome and runs `flow.py`. |
| `run_raw_cdp.py` | The same flow as raw CDP messages, with a ~40-line CDP client. |

## Expected output

```
▶ L1 · Playwright (local CDP) · mode=normal · run=L1-playwright--local-cdp--...
  [L1/...] github microsoft/playwright: {'stars': 96717, 'license': 'Apache-2.0', 'language': 'TypeScript'}
  ...
  [L1/...] catalog Puppeteer: BA-381
  [L1/...] receipt: 61ba26a67266
  checks : submitted=yes navigated=yes read=yes
  SUCCESS in 3.0s
```

Measured on 2026-09-27:

| Run | Result | Time |
|-----|--------|------|
| Playwright, normal | ✓ | 3.0 s |
| Playwright, `--traps late` | ✓ (auto-wait absorbs it) | 5.9 s |
| Playwright, `--traps modal` | ✗ `Page.click` timeout: the overlay intercepts the click | 17.5 s |
| Playwright, `--break` | ✗ `#lang-filter` no longer exists | 16.8 s |
| Raw CDP, normal | ✓ | 4.6 s |
| Raw CDP, `--traps late` | ✓ (only because we wrote `wait_for` ourselves) | 6.3 s |
| Raw CDP, `--break` | ✗ `tr.item-row` no longer exists | 2.2 s |

## What to notice

- **Speed and cost.** Seconds, zero tokens, zero dollars. Nothing later in the
  ladder beats this on a site that doesn't change.
- **Brittleness.** One renamed id (`--break`) or one pop-up (`--traps modal`) and the
  run dies. The script only knows the site as it was when someone wrote it.
- **The "search" step is fake.** `flow.py` hard-codes the three repository URLs.
  A script can't search; an agent can.
- **GitHub's Languages box loads after the page does.** Both versions have to wait
  for it explicitly. Playwright's `wait_for_function` is one line; in raw CDP it's
  a polling loop.
- **Raw CDP is not hard, just long.** Compare *Lines of code* on the scoreboard.
  What you get in return: no dependency, and direct access to everything
  (network interception, performance data, attaching to a running browser).
  That's why AI frameworks (Stagehand v3, Browser Use, browser-harness) moved from
  Playwright to raw CDP.

## Gotchas

- Chrome 136+ refuses `--remote-debugging-port` on your default profile. That's
  why `cdp_discovery.py` uses a dedicated `--user-data-dir`.
- `connect_over_cdp` attaches to an existing browser. Closing the Playwright
  connection doesn't close Chrome; the window stays open for the next run.
- The lab profile is empty on purpose (`BU_CDP_SEED=0`). To attach with your real
  logins, see `extras/auth_sessions`.

## Speaker notes

1. **Open with the protocol, not the library.** Show one CDP message in the
   terminal: `{"id":1,"method":"Page.navigate","params":{"url":"..."}}`. "Every
   tool today ends up sending this."
2. **Run Playwright live** with the Chrome window visible. It finishes in about
   3 s, which gets a reaction. Point at the scoreboard row: 0 tokens, $0.
3. **Show `run_raw_cdp.py` side by side with `flow.py`.** Same steps. Point at
   `wait_for` and `click` in the CDP class: "this is what Playwright's auto-wait
   and actionability checks are."
4. **Break it.** Run `--traps modal`, then `--break`. Let the 15 s timeout play
   out; the audience feels the brittleness.
5. **Transition:** "Our code doesn't care where Chrome runs. What if it ran in
   someone else's data centre?" → L2.
