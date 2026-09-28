# L6 · Speed: why action-space design matters

**The idea in 60 seconds.** A typical browser agent (L4) sends the whole page
state to an LLM every step, and the LLM *writes* the next action: its
reasoning, the element index, the text. That's slow: seconds per step and
thousands of tokens. Browser Use's **jev-ultrafast** turns the page into a
table of numbered controls and asks a small policy model (TypeSafe's *Jev*) to
*choose* an operation (`CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL`, `DONE`,
`BLOCKED`) and a target in **one round trip**, with target questions answered
speculatively in parallel. A small text model writes only the text to type.
Choosing is faster than generating.

## Run

L6 times only the **act** step: fill the form and submit it, with the facts
supplied in the goal (`goal.py`). jev only acts; it doesn't extract data. Both
engines get the identical goal on the same local Chrome.

```bash
# jev-ultrafast: its browser-harness dependency pins websockets 15 (Stagehand
# needs 16), so it runs in a throwaway environment:
uv run --no-project --with "jev-ultrafast @ git+https://github.com/browser-use/jev-ultrafast" \
    --with python-dotenv python -m levels.L6_speed.run_jev

# Baselines: open-source Browser Use with DeepSeek, normal and flash mode
uv run python -m levels.L6_speed.run_baseline
uv run python -m levels.L6_speed.run_baseline --flash
```

Needs `TYPESAFE_API_KEY` (Jev policy) and `OPENROUTER_API_KEY` (text via
DeepSeek V4.1 Flash; jev's own demo uses `inception/mercury-2.5`, a diffusion
model that types faster).

## Expected output

Measured on 2026-09-27, act step only (17 inputs: 15 row fields, a date, a submit):

| Engine | Result | Time | Model calls | Tokens (in/out) | Cost |
|--------|--------|------|-------------|-----------------|------|
| **jev-ultrafast** + DeepSeek for text | ✓ | **21.8 s** | 17 decisions (~0.2 s each) + 16 text calls (~0.6–1.3 s) | n/a (TypeSafe) | TypeSafe credits |
| Browser Use + DeepSeek | ✓ | 80.2 s | 12 steps | 132k / 4.8k | ~$0.006 |
| Browser Use `flash_mode` + DeepSeek | ✓ | 80.9 s | 11 steps | 64k / 3.3k | ~$0.003 |

jev spends most of its time in the *text* model: each `TYPE_TEXT` waits for
DeepSeek to produce a value like `BA-664`. With a faster text model the decision
loop, at ~0.2 s per action, dominates. `flash_mode` halves Browser Use's tokens
but not its time, because each step is still a full LLM generation.

## The native date picker

On the normal form, jev filled all 15 row fields in ~15 s and then reported
`BLOCKED`. Its snapshot (`snapshot.js`) gives roles only to text, number, search
and similar inputs; **`<input type="date">` isn't in its action space**, so it
never saw the field. The mock app has a `?date=text` variant (plain text box),
used by both engines here so the comparison is fair.

That's the trade-off in one example: an agent is fast because it offers the
model only the actions it understands. Anything outside that set (date pickers,
canvas, shadow roots, uploads) is invisible, not just harder.

## What to notice

- **Choose vs generate.** A decision is ~0.2 s; an LLM step is 5–7 s.
- **Where the time goes.** In jev, the text helper. In Browser Use, every step's
  full generation over a large page state (~11k tokens in per step).
- **Speed levers elsewhere in the lab:** L1 scripts (no model), L3 action caching
  (model only on a cache miss), fast-boot cloud browsers, smaller models for easy
  steps, parallel sessions.

## Gotchas

- jev connects through browser-harness, which attaches to the browser named in
  `BU_CDP_WS`. `run_jev.py` points it at the lab Chrome from `cdp_discovery` and
  uses its own daemon name (`BU_NAME=lab`).
- jev's `DONE` means "I think the goal is met". `run_jev.py` reads the receipt
  itself and the checker verifies it.
- The README's 7 s Google Flights demo is one task on one profile. The authors say
  so too; measure your own tasks.

## Speaker notes

1. **Show the element table** from jev's README (`[1] button …`, `[2] combobox …`).
   "This is all the model sees, and it picks a number."
2. **Run jev live with its inspector** (`uv run jev` in a clone of the repo) or
   this script. The ~1 action/second rhythm is visible.
3. **Show the scoreboard lines:** 22 s vs 80 s for the same 17 inputs.
4. **Tell the date-picker story.** It's the most honest slide in the talk: a fast
   agent can't see what isn't in its action space.
5. **Transition:** "What if the site simply *told* the agent what it can do?" → L7.
