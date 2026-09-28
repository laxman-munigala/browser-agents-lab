# L5 · Harnesses: how coding agents drive a browser

**The idea in 60 seconds.** Claude Code, Codex and Cursor are already agents
with a loop, a strong model and a terminal. A *harness* gives them a browser as
a tool. The harnesses differ in **what the agent sees** and **what it can
call**:

| Harness | Maker | Interface | What the agent works with |
|---------|-------|-----------|---------------------------|
| **browser-harness** (featured) | Browser Use | CLI + Python heredocs over one CDP WebSocket | Raw CDP plus helpers (`new_tab`, `js`, `click_at_xy`, `cdp(...)`). The agent writes missing helpers into `agent_helpers.py`, so the harness grows with use. |
| **Playwright MCP** | Microsoft | MCP server | Accessibility snapshots with element refs; `browser_click`, `browser_type`, … |
| **Chrome DevTools MCP** | Google Chrome team | MCP server | DevTools-level tools: snapshots, clicks, fills, plus network, console and performance traces |
| **agent-browser** | Vercel Labs | Rust CLI (not MCP) | `snapshot` with refs like `@e3`, `click @e3`, `fill @e3 "…"`; also discovers WebMCP tools (see L7) |

## Run (score any coding-agent session)

A harness run happens inside the agent's chat, so this level is two commands
around it:

```bash
# 1. Start the clock and print the prompt to paste into the agent
uv run python -m levels.L5_harness.session start --tool "Claude Code + browser-harness"

# 2. Paste the agent's final JSON back; it's checked and scored like every other level
uv run python -m levels.L5_harness.session finish --run-id <id> --result '<the JSON>'
```

`--tool` names containing `browser-harness`, `playwright-mcp`, `devtools-mcp` or
`agent-browser` add a one-line hint about which tools to use.

## Setting up each harness against the lab Chrome

Point every harness at the same debuggable Chrome (`uv run python -m
common.cdp_discovery status` prints its endpoint; usually port 9222 or 9223).

```bash
# Your mock app (see mock-app/README.md), e.g. http://localhost:8787
export MOCK_APP_URL=http://localhost:8787

# browser-harness: attaches to the browser named in BU_CDP_WS
export BU_CDP_WS=$(uv run python -c "from common.browsers import local_cdp_url; print(local_cdp_url())")
uvx --from browser-harness browser-harness --doctor
uvx --from browser-harness browser-harness <<PY
new_tab("$MOCK_APP_URL/items")
print(page_info())
PY

# Playwright MCP, attached to the lab Chrome instead of launching its own
claude mcp add playwright -- npx @playwright/mcp@latest --cdp-endpoint http://127.0.0.1:9223

# Chrome DevTools MCP
claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --browser-url http://127.0.0.1:9223

# agent-browser
npm install -g agent-browser && agent-browser install
agent-browser connect 9223 && agent-browser open "$MOCK_APP_URL/items"
agent-browser snapshot
```

## Expected output: a real session

`transcripts/claude-code-browser-harness.md` is a full run: Claude Code
(Opus 5.5) doing the task through browser-harness while this lab was being
built. It took 5 harness scripts and **70 s** from prompt to checked result, and
passed every check.

| Session | Result | Time | Notes |
|---------|--------|------|-------|
| Claude Code + browser-harness | ✓ | 70 s | Read the page with `js()`, filled via JS, clicked the submit via its box model; the click only worked after `activate_tab()` |

## What to notice

- **The agent picks the cheapest tool for each step.** It read GitHub with one
  `js()` call per page and filled the form in one script. That's L1's speed, with
  the agent writing the "L1 script" on the fly.
- **Harness knowledge matters.** The first clicks landed on a background tab and
  did nothing. browser-harness's SKILL.md says to `activate_tab()` when a page
  seems paused, and that fixed it. The skill file is part of the harness.
- **Snapshot-with-refs vs raw CDP.** Playwright MCP and agent-browser give the
  model a compact tree with `@e3`-style refs (easy to use, more tokens per page).
  browser-harness gives it the protocol (maximum power, and the agent has to know
  what it's doing).
- **This is how you'd debug the other levels.** Chrome DevTools MCP can read the
  console and network log when an L3/L4 run misbehaves.

## Gotchas

- browser-harness pins `websockets==15`, which conflicts with Stagehand in this
  project, so run it with `uvx` (its own environment), not `uv run`.
- One browser, many agents: harnesses sharing the lab Chrome share its tabs. Use
  separate tabs, or separate `BU_NAME` daemons for browser-harness.
- The lab profile is empty on purpose. For logged-in work, see
  `extras/auth_sessions`; think twice before handing a coding agent your real
  sessions.

## Speaker notes

1. **Live demo:** paste the `session start` prompt into Claude Code with
   browser-harness installed. It's the most impressive run in the talk, because
   the audience watches the agent write its own automation.
2. **Show `transcripts/claude-code-browser-harness.md`** as the backup if the live
   demo misbehaves.
3. **Compare the interfaces:** show a Playwright MCP snapshot with refs, then a
   browser-harness `cdp("Accessibility.getFullAXTree")` call. Same information,
   different abstraction.
4. **Transition:** "Every one of these agents clicks through UI built for humans.
   How fast could it be?" → L6.
