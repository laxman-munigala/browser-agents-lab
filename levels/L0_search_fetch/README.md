# L0 · Search & Fetch APIs: often you need no browser at all

**The idea in 60 seconds.** Most "let the AI browse the web" tasks are really
*search, then read a page*. Search APIs built for LLMs (TinyFish, Exa, Tavily,
Brave, Perplexity Sonar) return ranked URLs; fetch APIs (TinyFish Fetch, Jina
Reader, Firecrawl) render the page in *their* browser and hand you clean
Markdown. And when the site you need to act on is plain HTML with a form, a
`POST` is all it takes. No browser, no LLM, no selectors.

## Run

```bash
uv run python -m levels.L0_search_fetch.run
uv run python -m levels.L0_search_fetch.run --break --traps late,modal,inject   # still passes
```

Needs `TINYFISH_API_KEY` (Search and Fetch are on TinyFish's free tier).

## How each step is done

| Step | How | Why this works |
|------|-----|----------------|
| Search | `GET api.search.tinyfish.ai?query=...&include_domains=github.com` | First result that is a repository root |
| Read | `POST api.fetch.tinyfish.ai {"urls": [...], "format": "markdown", "ttl": 0}` → regex for `**96.7k** stars` and `Apache-2.0 license` | Fetch renders the page in TinyFish's browser |
| Read (language) | `GET api.github.com/repos/{owner}/{repo}` | GitHub fills the Languages box with JavaScript *after* load, so no fetch snapshot contains it. Use the API behind it. |
| Navigate | `GET /items?lang=...&page=N` + a regex over the table | The catalog is server-rendered HTML |
| Act | `POST /submit` with form fields; receipt read from the HTML | The form is a plain HTML form |

## Expected output

```
▶ L0 · TinyFish Search+Fetch + HTTP · mode=normal · run=L0-...
  [L0/...] search Playwright: https://github.com/microsoft/playwright
  [L0/...] fetch https://github.com/microsoft/playwright: {'stars': 96700, 'license': 'Apache-2.0', 'language': 'TypeScript'}
  ...
  checks : submitted=yes navigated=yes read=yes
  SUCCESS in 7.3s
```

Measured on 2026-09-27: 7.3 s normal, 6.9 s with every trap plus `--break`.

## What to notice

- **Traps don't exist for HTTP clients.** The late button, the modal and the
  injection text are all things a *browser* renders. `--break` renames the page's
  selectors, but the server still accepts the same form fields: an HTTP client
  targets the server's contract, not the page.
- **Stars are rounded** ("96.7k"). Fetch gives you what the page *shows*; the
  checker allows ±5%, so it passes. Exact numbers need the API or a browser.
- **Lazy-loaded content is invisible to a snapshot.** That's the Languages box.
  When a fetch misses data, the page's own XHR endpoint usually has it.
- **This level would fail on a real SPA** that needs clicks, logins or client-side
  state. That's where L1+ earn their cost.

## Gotchas

- `ttl: 0` forces a live fetch. Without it TinyFish may return a cached copy
  (fine for most research, stale for live counts).
- Fetch rejects `localhost` and private IPs. That's one reason the mock app is
  deployed publicly.
- Unauthenticated GitHub API calls are limited to 60/hour per IP. Set
  `GITHUB_TOKEN` if you run this in a loop.

## Speaker notes

1. **Open with the question:** "Does this task need a browser?" Most don't.
2. **Run it live.** About 7 s, $0, no LLM. Show the Markdown TinyFish returned
   (print `text[:500]`) so people see what an LLM would be fed.
3. **Run it with every trap on.** It still passes. Ask why. (No JavaScript runs, and
   the POST targets the server, not the page.)
4. **Show the one crack:** the language comes from GitHub's API because the page
   loads it later. That's the bridge to L1: "when you need what JavaScript
   renders, or you need to click, you need a browser."
