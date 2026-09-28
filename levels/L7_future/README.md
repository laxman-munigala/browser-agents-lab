# L7 · Where it's heading: the web meets agents halfway

**The idea in 60 seconds.** Every level so far has agents dealing with UI built
for humans: finding fields, clicking buttons, fighting date pickers. The
alternative is for the site to *tell* the agent what it can do. **WebMCP** lets a
page register tools (name, description, JSON Schema, a JavaScript function) with
`document.modelContext.registerTool()`. An agent in the browser lists the tools
and calls one with JSON: no selectors, no screenshots, no guessing.
**`llms.txt`** is the static version: a plain-text description of a site for
LLMs.

## Run

```bash
uv run python -m levels.L7_future.run_webmcp
```

The script launches its own headless Chrome with WebMCP enabled
(`--enable-features=WebMCPTesting,DevToolsWebMCPSupport`, the command-line form
of `chrome://flags/#enable-webmcp-testing`), then over raw CDP:

1. reads `/llms.txt`
2. opens `/submit`, sends `WebMCP.enable`, gets `WebMCP.toolsAdded` → `['submit_report']`
3. `WebMCP.invokeTool("submit_report", {rows, checked_on})` → `WebMCP.toolResponded` with the receipt

The tool itself is 30 lines in `mock-app/src/index.ts` (`webmcpHead()`): the
form's fields as a JSON Schema, and an `execute` that POSTs JSON to `/submit`.

## Expected output

```
▶ L7 · WebMCP tool call (act step) · mode=normal
  [L7/...] /llms.txt: # Framework Registry (browser-agents-lab mock app) … (952 chars)
  [L7/...] page tools: ['submit_report']
  [L7/...] tool responded (Completed) in 33 ms
  [L7/...] receipt: 6ca16090f72a
  checks : submitted=yes navigated=yes read=yes
  SUCCESS in 0.5s
```

**The act step, compared** (the same 3 rows plus a date, facts supplied):

| How | Time |
|-----|------|
| WebMCP tool call | **33 ms** |
| jev-ultrafast (L6) | 21.8 s |
| Browser Use + DeepSeek (L6) | 80 s |

## What else is on this slide

- **`llms.txt` and Markdown for agents.** `/llms.txt` on the mock app describes
  the pages and the JSON API. Many docs sites now serve Markdown when asked.
- **Signed agents.** Cloudflare's Web Bot Auth lets agents sign requests, so sites
  can tell a known agent from a scraper (and charge it: pay-per-crawl).
- **AI browsers.** Claude for Chrome, Perplexity Comet, ChatGPT Atlas, Gemini in
  Chrome, Dia: the agent lives *in* the browser, with your sessions. That's the
  environment WebMCP is designed for.
- **Agentic credentials and payments.** Password-manager vaults for agents (TinyFish
  and Browser Use both have them), and agent payment protocols.

## Gotchas and honest caveats

- **Chrome's API changed.** Early drafts used `navigator.modelContext`; Chrome
  ships `document.modelContext`. The mock app checks both. Our first L7 run failed
  on exactly this.
- WebMCP is behind a flag or an origin trial (Chrome 149+), and needs an
  origin-isolated document.
- **Tools are untrusted input.** A page can describe a tool as harmless and do
  anything. agent-browser's docs are blunt: page-provided names, descriptions and
  results are untrusted data. The consequential-action rules from
  `extras/prompt_injection` still apply; the mock app marks `submit_report` with
  `consequentialHint: true`.
- This only helps on sites that adopt it. For the rest of the web, L0–L6 remain
  the toolbox.

## Speaker notes

1. **Show `webmcpHead()`**, the whole tool: a schema and a `fetch`.
2. **Run it.** 33 ms gets a laugh after L6's 22 s and L4's 80+ s.
3. **Show agent-browser's `webmcp list`** if you have it installed: coding agents
   already pick these tools up automatically.
4. **Close the talk:** "The fastest browser agent is the one that doesn't have to
   browse. Use the lowest level that works (L0 before L1 before L4), and ask
   sites for tools."
