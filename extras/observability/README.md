# Extra · Observability: see what a run actually did

When an agent says "done" or a script times out, you need to see what happened.
Four layers, from the cheapest up:

| Layer | Where | What you get |
|-------|-------|--------------|
| Run log + result file | every level: stdout, `runs/<run-id>.json` | Steps, the result, the checker's verdict and problems |
| Network log | `extras/observability/run.py` → `traces/<run-id>.network.jsonl` | Every request the page made (method, URL, type) |
| Playwright trace | same → `traces/<run-id>.zip` | A replayable timeline: each action, DOM snapshots before and after, screenshots, network, console |
| Live view / recordings | L2 prints Browser Use's `liveUrl`; L4 TinyFish prints a `streaming_url` | Watch the remote browser live; cloud providers can also record sessions |

## Run

```bash
uv run python -m extras.observability.run
uv run playwright show-trace traces/<run-id>.zip
```

Measured on 2026-09-27: the L1 flow with tracing took 4.6 s and captured **558
requests**, 436 of them from `github.githubassets.com` and only 8 to the mock
app. The trace zip is ~8 MB.

## What to notice

- **Real pages are heavy.** Hundreds of requests to read three numbers. That's the
  hidden cost behind "just use a browser", and a reason L0 (fetch APIs) exists.
- **Traces answer "why did it fail?"** Run `L1 --traps modal` with tracing and the
  trace shows the overlay intercepting the click at the exact step.
- **For agents, record the reasoning too.** Browser Use logs its eval / memory /
  next-goal per step (see the L4 logs). Stagehand logs each inference with its
  token counts. Keep them: they're how the L3 failures in its README were found.

## Speaker notes

1. Open a trace in `show-trace` and scrub through the timeline. People haven't
   usually seen DOM-snapshot replay.
2. Show the request counts per host. "558 requests for three star counts."
3. Point at observability in the cloud products: live view plus recordings are a
   big part of what L2's providers sell.
