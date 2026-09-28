"""L0 · No browser at all: TinyFish Search + Fetch, then plain HTTP to the mock app.

    uv run python -m levels.L0_search_fetch.run

1. Search: TinyFish Search finds each framework's GitHub repository.
2. Read:   TinyFish Fetch renders the repository page (in TinyFish's browser) and
           returns Markdown; regexes pull out stars and license. The Languages box
           is loaded by JavaScript after the page, so no fetch snapshot has it:
           we ask the endpoint behind it (GitHub's REST API) instead.
3. Navigate + act: the mock app is plain server-rendered HTML with a form POST,
           so httpx does both. No JavaScript runs, so none of the traps apply.
"""

from __future__ import annotations

import datetime as dt
import html
import re

import httpx

from common.config import require
from common.runner import Context, Outcome, run
from common.task import TARGETS

SEARCH_URL = "https://api.search.tinyfish.ai"
FETCH_URL = "https://api.fetch.tinyfish.ai"
REPO_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/?$", re.I)


def search_repo(client: httpx.Client, name: str, ctx: Context) -> str:
    """Search: the first result that is a repository root (not a topic or file)."""
    data = client.get(
        SEARCH_URL,
        params={
            "query": f"{name} browser automation GitHub repository",
            "include_domains": "github.com",
            "purpose": f"Find the official GitHub repository of {name}",
        },
    ).raise_for_status().json()
    for hit in data["results"]:
        m = REPO_URL.match(hit["url"])
        if m and m.group(1).lower() not in ("topics", "orgs", "collections"):
            ctx.log(f"search {name}: {hit['url']}")
            return hit["url"]
    raise LookupError(f"no repository result for {name}")


def read_repo(client: httpx.Client, web: httpx.Client, url: str, ctx: Context) -> dict:
    """Read: fetch the page as Markdown (ttl=0 skips TinyFish's cache) and parse it."""
    data = client.post(FETCH_URL, json={"urls": [url], "format": "markdown", "ttl": 0}).raise_for_status().json()
    if data.get("errors"):
        raise RuntimeError(f"fetch failed: {data['errors']}")
    text = data["results"][0]["text"]
    stars = re.search(r"\*\*([\d.,]+)(k?)\*\* stars", text) or re.search(r"Star\s*\n?\s*([\d.,]+)\s*(k?)", text)
    license_ = re.search(r"([A-Za-z0-9.\-]+) license", text)
    count = float(stars.group(1).replace(",", "")) * (1000 if stars.group(2) else 1)
    owner_repo = REPO_URL.match(url)
    api = web.get(f"https://api.github.com/repos/{owner_repo.group(1)}/{owner_repo.group(2)}")
    facts = {
        "stars": int(count),  # "96.7k" → 96700: rounded, but within the checker's ±5%
        "license": license_.group(1) if license_ else "",
        "language": api.raise_for_status().json().get("language") or "",
    }
    ctx.log(f"fetch {url}: {facts}")
    return facts


ROW = re.compile(r"<tr[^>]*>\s*<td[^>]*>(BA-\d{3})</td>\s*<td[^>]*>([^<]+)</td>", re.I)


def find_catalog_id(client: httpx.Client, name: str, language: str, ctx: Context) -> str:
    """Navigate: GET the filtered catalog page by page. It's just HTML."""
    for page in range(1, 20):
        body = client.get(ctx.url("/items", lang=language, page=page)).raise_for_status().text
        for cid, row_name in ROW.findall(body):
            if html.unescape(row_name).strip() == name:
                ctx.log(f"catalog {name}: {cid}")
                return cid
        if 'rel="next"' not in body:
            break
    raise LookupError(f"{name} not in catalog")


def submit(client: httpx.Client, rows: list[dict], ctx: Context) -> str:
    """Act: POST the form fields directly; the receipt is in the response HTML."""
    form = {"run": ctx.run_id, "checked_on": dt.date.today().isoformat()}
    for i, row in enumerate(rows, start=1):
        for key, value in row.items():
            form[f"row{i}_{key}"] = str(value)
    body = client.post(ctx.url("/submit"), data=form).raise_for_status().text
    receipt = re.search(r'id="receipt"[^>]*>([0-9a-f]+)<', body).group(1)
    ctx.log(f"receipt: {receipt}")
    return receipt


def solve(ctx: Context) -> Outcome:
    tinyfish = httpx.Client(headers={"X-API-Key": require("TINYFISH_API_KEY")}, timeout=150)
    web = httpx.Client(timeout=30, follow_redirects=True)
    with tinyfish, web:
        facts = {name: read_repo(tinyfish, web, search_repo(tinyfish, name, ctx), ctx) for name in TARGETS}
        ids = {name: find_catalog_id(web, name, facts[name]["language"], ctx) for name in TARGETS}
        rows = [{"catalog_id": ids[n], "name": n, **facts[n]} for n in TARGETS]
        return Outcome(
            result={"rows": rows, "receipt": submit(web, rows, ctx)},
            cost_usd=0.0,
            notes="TinyFish Search/Fetch free tier; traps are browser-only, so they never fire here",
        )


if __name__ == "__main__":
    raise SystemExit(run("L0", "TinyFish Search+Fetch + HTTP", solve, sources=[__file__]))
