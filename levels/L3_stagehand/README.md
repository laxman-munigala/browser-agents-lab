# L3 · AI-augmented primitives: Stagehand `act` / `extract` / `observe`

**The idea in 60 seconds.** Keep the script, and replace only its fragile
parts with a model. You still decide the steps and their order (L1's flow); for
each step you describe *what* in plain language instead of writing *where* as a
selector:

| Primitive | Replaces | Example from `run.py` |
|-----------|----------|------------------------|
| `act("...")` | `page.click("#submit-btn")` | `act("click the 'Submit report' button at the bottom of the form")` |
| `extract("...", Schema)` | a selector + regex | `extract("the repository's star count, license and main language", RepoFacts)` |
| `observe("...")` | "is there a pop-up?" checks | `observe("a cookie consent or other dialog that covers the page")` |

Stagehand reads the page's accessibility tree, asks the model which element
matches, and performs the action with CDP. When `--break` renames every id,
the description still matches, so the run survives.

## Run

```bash
uv run python -m levels.L3_stagehand.run                          # normal
uv run python -m levels.L3_stagehand.run --break --traps late,modal
uv run python -m levels.L3_stagehand.run --headless
```

Needs `OPENROUTER_API_KEY`. The model is `LAB_LLM_MODEL` (default
`deepseek/deepseek-v4.1-flash`).

- **The model plugs in through a callback.** Stagehand's built-in providers are
  OpenAI, Anthropic, Google, Groq and Cerebras. `common/stagehand_llm.py` passes
  a callback that translates Stagehand's requests to OpenRouter's
  OpenAI-compatible API and counts tokens.
- **Stagehand launches its own Chrome.** Stagehand v4 runs its core as an
  in-browser extension that opens its own CDP WebSocket. The lab's
  `cdp_discovery` Chrome rejects that, and allowing it needs
  `--remote-allow-origins=*`, which would let any web page talk to your debug
  port. So `run.py` uses `local_browser.launch()`.

## Expected output

Measured on 2026-09-27 with DeepSeek V4.1 Flash:

| Run | Result | Time | Tokens (in/out) | Cost |
|-----|--------|------|-----------------|------|
| normal | ✓ | ~175 s | ~130k / ~10k | ~$0.007 |
| `--break --traps late,modal` | ✓ | ~200 s | ~133k / ~8k | ~$0.007 |

About 48 model calls per run: 3 extracts, 3 filter/paging rounds, 16 form
fields, the dialog, the date and the submit.

## What we had to fix to get there (the real lessons)

Every failure below happened while this level was being built, and each fix is
still in `run.py`:

1. **Plausible but wrong answers.** `extract` returned `BA-522` for Puppeteer (that's
   Splinter), and on another run `BA-000`. *Fix:* make the model also return the
   name it read, then check in code that exactly that ID and name sit side by side
   in the page's text.
2. **The dialog vs. its button.** `observe` found "the cookie dialog", and acting on
   that result clicked its backdrop. The overlay stayed, and the submit click hit it
   silently. *Fix:* observe to *detect*, then act on "the button that accepts it".
3. **Date pickers.** Typing `2026-09-27` key by key into a Chrome date input leaves
   it empty, and the browser then refuses to submit without an error the agent can
   see. *Fix:* ask for a *fill*, check the value, and fall back to month/day/year
   keystrokes.
4. **Text is not data.** The model returned stars as `96`, the license as
   `Apache-2.0 license`, the language as `TypeScript 91.9%`. *Fix:* extract the
   text as shown and normalize it in code (`normalize()`).

The pattern: **let the model find things, let code check them.**

## What to notice

- **It survives `--break`.** Compare L1: same steps, and no selectors to rename.
- **Cost and speed.** About 60× slower than L1, and about $0.007 instead of $0. Each
  `act` is a model round trip (~2–4 s).
- **Header "Submit" vs "Submit report".** Natural language has its own ambiguity;
  the instruction names the exact button and says "not the header link".
- **Caching** (not used here): Stagehand can cache resolved actions so a repeat
  run replays selectors without calling the model (`cache=` on `act`). That gives
  L1 speed on the happy path and AI only when the page changed.

## Gotchas

- `extract` works on an accessibility snapshot taken *now*. Lazy content (GitHub's
  Languages box) needs a wait first.
- `page.evaluate()` in Stagehand takes an expression string, not a function plus
  arguments as in Playwright.
- A cheap, fast model makes more of the mistakes listed above. That's the trade-off
  you're choosing; the code checks are what make it safe.

## Speaker notes

1. **Show one `act()` line next to its L1 equivalent.** "Same step, no selector."
2. **Run with `--break --traps late,modal` live.** It takes about 3 minutes, so
   start it before you talk. Let the audience watch it find and dismiss the cookie
   dialog on its own.
3. **Tell the four failure stories.** They're the most useful part of this level.
   The model was *confidently wrong* twice; code checks caught it.
4. **Put the costs next to each other:** L1 3 s / $0, L3 ~3 min / ~$0.007. "Worth
   it when the page changes under you, not for every run" → caching.
5. **Transition:** "We still wrote every step. What if we only said *what* we
   want?" → L4.
