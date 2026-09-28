# L4 · Autonomous browser agents: say *what*, not *how*

**The idea in 60 seconds.** An agent runs a loop: **observe** the page (DOM /
accessibility tree, screenshot, or both), ask an LLM **what to do next**, **act**
(click, type, navigate), repeat until it decides it's done. There are no steps
and no selectors; the only input is the goal. Every agent here gets the same
prompt (`common/task.py: agent_prompt()`) and must return the same JSON. The
checker then verifies it, because **an agent saying "success" means nothing
until it's checked**.

## Run

```bash
uv run python -m levels.L4_agents.run --agent bu-local   # open-source Browser Use, lab Chrome, DeepSeek V4.1 Flash
uv run python -m levels.L4_agents.run --agent bu-cloud   # Browser Use Cloud agent (API v4, gpt-5.6-luna)
uv run python -m levels.L4_agents.run --agent tinyfish   # TinyFish Web Agent (SSE stream)
uv run python -m levels.L4_agents.run --agent bu-cloud --traps inject   # see extras/prompt_injection
```

| Agent | Where the loop runs | Browser | Model | Perception |
|-------|--------------------|---------|-------|------------|
| `bu-local` | your machine (`browser-use` library) | lab Chrome via `cdp_discovery` | DeepSeek V4.1 Flash via OpenRouter | DOM text (`use_vision=False`) |
| `bu-cloud` | Browser Use Cloud (`POST /api/v4/runs`) | their cloud browser | `gpt-5.6-luna` (their pick) | hybrid |
| `tinyfish` | TinyFish (`/v1/automation/run-sse`) | their cloud browser | theirs | theirs |

Keys: `OPENROUTER_API_KEY`, `BROWSER_USE_API_KEY`, `TINYFISH_API_KEY`.
Each cloud run is capped (`maxCostUsd: 1.0` for Browser Use).

## Expected output

Measured on 2026-09-27, full task (search → read → navigate → act):

| Agent | Result | Time | Steps | Tokens (in/out) | Cost |
|-------|--------|------|-------|-----------------|------|
| Browser Use (local) + DeepSeek V4.1 Flash | ✓ | 440 s | 21 | 298k / 25k | ~$0.018 |
| Browser Use Cloud agent (gpt-5.6-luna) | ✓ | 78 s | – | 346k / 3.8k | $0.020 |
| TinyFish Web Agent | ✓ | 627 s | 86 progress events | – | TinyFish credits |

For comparison: L1 took 3 s for $0, and L3 took ~175 s for ~$0.007.

With traps:

| Agent | Mode | Result | Time | Cost |
|-------|------|--------|------|------|
| Browser Use Cloud | `--break --traps late,modal` | ✓ | 78 s | $0.021 |
| Browser Use Cloud | `--traps inject` / `inject-visible` | ✓, did not fall for it | 67 s / 94 s | ~$0.02 each |
| Browser Use local + DeepSeek | `--traps inject-visible` | ✓, spotted and ignored it | 517 s | ~$0.017 |
| TinyFish Web Agent | `--traps inject` | ✗ ignored the injection, but submitted Pyppeteer's ID (BA-143) for Puppeteer | 941 s | credits |

The TinyFish miss is the catalog's decoy doing its job: "Pyppeteer" sits next to
"Puppeteer". Its own status was `COMPLETED`; only the checker knew it was wrong.

## What happened inside (read the logs; this is the talk)

- **The local DeepSeek agent went looking for a shadow DOM that doesn't exist.**
  Its first fills were partial, so it concluded the fields must be in shadow roots,
  wrote a recursive shadow-DOM walker in `evaluate`, set values that way, and then
  submitted successfully. It was creative, wasteful and correct.
- **TinyFish spent many steps on the native date picker** ("Click date field to
  open calendar", twice) before getting past it. Date inputs trip up every level
  of this lab; see L3 and L6.
- **Browser Use Cloud was fastest and cheapest per success.** A stronger model
  takes fewer, better steps. The low per-token price of the local model didn't win
  on total cost, because it used far more tokens.

## What to notice

- **No task-specific code.** `run.py` is mostly API plumbing. The "program" is the
  prompt.
- **`--break` doesn't matter** to an agent; it never knew the selectors.
- **Verification is on you.** Browser Use's docs say it too: `is_successful` is
  the agent's own opinion. Our receipt check can't be faked by the agent.
- **Prompt injection is the new attack surface.** The same page text the agent
  reads can carry instructions. See `extras/prompt_injection`.

## Gotchas

- The open-source `browser-use` package and the hosted Browser Use Cloud SDK are
  different products with different APIs. The pinned `browser-use` bundles an old
  Cloud SDK, so `bu-cloud` calls the v4 REST API with httpx.
- A client timeout doesn't cancel a cloud run. Cancel explicitly
  (`POST /runs/{id}/cancel`) if you abort.
- TinyFish's structured-output subset rejects `additionalProperties`; `run.py`
  strips it from the shared schema.
- `bu-local` attaches to the lab Chrome with `keep_alive=True` and calls
  `browser.stop()` at the end, which disconnects without closing your window.

## Speaker notes

1. **Show the prompt**, then `run.py`: no selectors, no steps.
2. **Start `bu-cloud` live**, and open cloud.browser-use.com to watch it. It
   finishes in a talk-friendly ~80 s.
3. **Tell the shadow-DOM story** from the local run's log. It shows exactly what
   "agentic" means, good and bad.
4. **Put three rows on screen side by side:** L1 (3 s, $0, brittle), L3 (~3 min,
   ~$0.007, robust steps), L4 (80–600 s, ~$0.02, no steps at all).
5. **Transition:** "Your coding agent can do this too, with the browser as a
   tool." → L5.
