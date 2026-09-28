# Landscape map (as of Sept 2026)

This space changes monthly. Treat versions and product names here as a snapshot, and
re-verify each one when we implement its module.

## The vendors this lab uses

The lab was built with **Browser Use** and **TinyFish** accounts plus OpenRouter.
Browserbase is covered here as landscape, but no level needs it: Stagehand runs
locally.

| | **Browser Use** | **TinyFish** | Browserbase (not used) |
|--|--|--|--|
| Core idea | Open-source agent framework + cloud browsers/agents | Search, Fetch, Browser and Agent APIs | Cloud browser infra + Stagehand SDK |
| In this lab | L2 (cloud browser), L4 (local library + Cloud v4 agent), L5 (`browser-harness`), L6 (`jev-ultrafast`) | L0 (Search + Fetch), L2 (Browser API), L4 (Web Agent) | L3 uses Stagehand, its open-source SDK, locally |
| Speed story | `jev-ultrafast`: indexed action space, one decision per round trip | Fetch renders server-side; the agent streams progress | Stagehand v4: core runs as an in-browser extension |

## 1. Web data without a browser (Search / Fetch / Crawl)

| Tool | Notes |
|------|-------|
| **TinyFish** Search + Fetch | Free tier (≈30 searches/min, 150 fetches/min). Fetch renders in a real browser and returns Markdown/JSON/HTML. REST, MCP, SDKs and CLI. TinyFish also offers a Web Agent API and AgentQL. |
| Jina Reader (`r.jina.ai/<url>`) | Zero-setup URL → Markdown |
| Firecrawl | Scrape, crawl and extract with a schema; open-source core |
| Exa, Tavily, Brave Search API, Perplexity Sonar | Search APIs built for LLMs |
| Model-native tools | Claude web search/fetch tools, OpenAI web search, Gemini grounding |

**Demo point:** most "browse the web" tasks are really search plus fetch. It is cheaper, faster and more reliable.

## 2. Browser control protocols & libraries

| Layer | Examples | Notes |
|-------|----------|-------|
| Protocols | **CDP** (Chrome DevTools Protocol), **WebDriver BiDi** (W3C, cross-browser), classic WebDriver | CDP is Chromium-only, low-level, JSON over WebSocket |
| Libraries | **Playwright** (auto-wait, locators, tracing, multi-browser), **Puppeteer** (thin CDP wrapper), Selenium, chromedp (Go), `pycdp`/raw websockets | Playwright uses CDP for Chromium and patched protocols for Firefox and WebKit |
| Headless engines | Chrome headless (new), **Lightpanda** (Zig; fast and light, CDP-compatible) | Lightpanda is useful for a speed comparison |

**Playwright vs raw CDP, the talking points:**
- Playwright gives auto-waiting, robust locators, contexts, tracing, codegen and cross-browser support.
- Raw CDP gives full power: network interception, performance data, target
  management, attaching to a *running* Chrome, and lower overhead.
- Trend: AI frameworks are moving **off Playwright onto raw CDP** for speed and
  control (Stagehand v3, Browser Use, browser-harness).
- Local Chrome gotcha: recent Chrome versions block `--remote-debugging-port` on the
  default profile, so use `--user-data-dir`. Newer builds add a
  `chrome://inspect/#remote-debugging` toggle for attaching to your real browser.

## 3. Cloud / remote browsers ("browser infra")

| Vendor | Notes |
|--------|-------|
| **Browserbase** | Sessions over CDP, live view, session replay, contexts (persisted auth), proxies, stealth/CAPTCHA, Fetch. Makes Stagehand, Director and Browserbase Agents. |
| Browser Use Cloud | Hosted browsers and agents; home of the ultrafast mode |
| Steel.dev | Open-source browser API; self-hostable |
| Kernel (onkernel) | Fast-boot browsers, unikernel-based |
| Hyperbrowser, Anchor Browser, Airtop, Notte | Other hosted options |
| TinyFish | Also runs remote browsers behind its agent API |

**Demo point:** the same Playwright script connects over CDP to local Chrome or to any
vendor. Only the WebSocket URL changes.

## 4. AI browser SDKs (AI-augmented primitives)

| Tool | Notes |
|------|-------|
| **Stagehand** (Browserbase) | `act`, `extract` (schema-based), `observe`, `agent`. v4 (Python SDK 4.1 as of Sept 2026) runs its core as an in-browser extension; `local_browser.launch()` needs no Browserbase account. Custom LLMs plug in as a callback (see `common/stagehand_llm.py`). Supports action caching. |
| AgentQL (TinyFish) | Query language for elements and data |
| ZeroStep / auto-playwright, Midscene.js | NL steps inside Playwright tests |

## 5. Autonomous browser agents

| Kind | Examples |
|------|----------|
| Open-source frameworks | **Browser Use** (Python), Skyvern, Notte, LaVague, Magentic-UI (Microsoft) |
| Hosted agent APIs | **Browserbase Agents**, Browser Use Cloud, TinyFish Web Agent, Amazon Nova Act |
| Computer-use models | Anthropic **Claude computer use**, OpenAI CUA / ChatGPT agent, Gemini Computer Use, UI-TARS (ByteDance), Fara-7B (Microsoft) |
| Perception styles | DOM / accessibility tree (text) · screenshots (vision) · hybrid (set-of-marks) · indexed action space (jev-ultrafast) |

## 6. Harnesses for coding agents (Claude Code, Codex, Cursor…)

| Tool | Maker | How it controls the browser |
|------|-------|-----------------------------|
| **browser-harness** | Browser Use | Thin CDP WebSocket bridge. The agent writes missing helpers into `agent_helpers.py`, so it gets better with every task. Works with local Chrome or Browser Use Cloud. |
| **Playwright MCP** | Microsoft | MCP server with accessibility-snapshot-based actions |
| **Chrome DevTools MCP** | Google Chrome team | DevTools-level debugging: perf traces, console, network |
| **agent-browser** | Vercel Labs | Rust CLI (not MCP). A11y snapshot with element refs like `@e1`. |
| notte-cli, Stagehand MCP, Browserbase MCP | various | Other options |

## 7. Speed

- **jev-ultrafast** (Browser Use): the DOM becomes a structured table. A text-only model
  outputs an operation (CLICK / TYPE_TEXT / SELECT / SCROLL…) plus a target
  distribution. Reported about 7 s for a Google Flights task, versus 25–30 s for
  screenshot agents.
- Other levers: action caching (Stagehand), fast-boot browsers (Kernel), Lightpanda,
  smaller models for the easy steps, and parallel sessions.

## 8. The web meets agents halfway (L7, mostly slides)

- **WebMCP**: sites expose tools to in-browser agents with
  `document.modelContext.registerTool()`. Chrome origin trial (Chrome 149+) or
  `chrome://flags/#enable-webmcp-testing`; a CDP `WebMCP` domain (`enable`,
  `toolsAdded`, `invokeTool`) and a DevTools panel. agent-browser discovers these
  tools automatically. L7 calls one.
- **llms.txt**, Markdown content negotiation
- **Signed / verified agents**: Cloudflare Web Bot Auth, and pay-per-crawl
- **AI browsers**: Claude for Chrome, Perplexity Comet, ChatGPT Atlas, Gemini in
  Chrome, Dia
- Agentic credentials and payments (password-manager integrations, agent payment protocols)

## 9. Evaluation & benchmarks

WebArena, VisualWebArena, WebVoyager, Mind2Web / Online-Mind2Web, BrowseComp,
REAL (AGI Inc). Plan: our own 10-task mini eval against the mock app.

## Sources

- TinyFish Search & Fetch: https://www.tinyfish.ai/blog/search-and-fetch-are-now-free-for-every-agent-everywhere
- browser-harness: https://github.com/browser-use/browser-harness
- Browserbase harness concept: https://www.browserbase.com/blog/what-is-a-browser-agent-harness
- jev-ultrafast: https://github.com/browser-use/jev-ultrafast
- Stagehand v3: https://www.browserbase.com/blog/stagehand-v3 · v4: https://www.browserbase.com/blog/stagehand-v4
- Chrome DevTools MCP: https://developer.chrome.com/blog/chrome-devtools-mcp
- WebMCP DevTools: https://developer.chrome.com/docs/devtools/application/webmcp
- agent-browser: https://github.com/vercel-labs/agent-browser
