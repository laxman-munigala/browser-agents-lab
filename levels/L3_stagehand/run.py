"""L3 · AI-augmented primitives: Stagehand act / extract / observe.

    uv run python -m levels.L3_stagehand.run
    uv run python -m levels.L3_stagehand.run --break --traps late,modal

The *structure* is still ours (L1's steps, in L1's order); only the fragile
parts, which element to click and where the data sits, are handed to a model.
Stagehand drives its own Chrome here and uses DeepSeek V4.1 Flash via OpenRouter
(common/stagehand_llm.py).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re

from pydantic import BaseModel, Field
from stagehand import Stagehand, local_browser

from common import llm, stagehand_llm
from common.runner import Context, Outcome, run
from common.task import TARGETS
from levels.L1_scripted.flow import REPOS


class RepoFacts(BaseModel):
    stars: str = Field(description="The star count exactly as shown, e.g. '96.7k'")
    license: str = Field(description="The license name as shown, e.g. 'Apache-2.0 license'")
    language: str = Field(description="The first (main) language in the Languages list")


def normalize(facts: RepoFacts) -> dict:
    """The model reads text; code turns it into data ("96.7k" → 96700)."""
    m = re.search(r"([\d.,]+)\s*([kKmM]?)", facts.stars)
    scale = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1) if m else 1
    stars = int(float(m.group(1).replace(",", "")) * scale) if m else 0
    license_ = re.sub(r"\s*license$", "", facts.license.strip(), flags=re.I)
    language = re.sub(r"\s*[\d.]+\s*%$", "", facts.language.strip())  # "TypeScript 91.9%"
    return {"stars": stars, "license": license_, "language": language}


class CatalogHit(BaseModel):
    name: str | None = Field(description="The Name cell of the matching row, copied exactly, or null")
    catalog_id: str | None = Field(description="The Catalog ID cell (BA-###) of that same row, or null")


class Receipt(BaseModel):
    receipt: str | None = Field(description="The receipt code shown after submitting, or null if there is none")


async def read_facts(sh: Stagehand, page, ctx: Context) -> dict[str, dict]:
    facts = {}
    for name in TARGETS:
        await page.goto(f"https://github.com/{REPOS[name]}")
        await page.wait_for_timeout(2000)  # let the lazy Languages box render
        r = await sh.extract("the repository's star count, license and main language", RepoFacts)
        facts[name] = normalize(r.data)
        ctx.log(f"extract {name}: {facts[name]}")
    return facts


async def find_ids(sh: Stagehand, page, facts: dict[str, dict], ctx: Context) -> dict[str, str]:
    ids = {}
    for name in TARGETS:
        await page.goto(ctx.url("/items"))
        await sh.act("select %lang% in the Language filter dropdown", variables={"lang": facts[name]["language"]})
        await sh.act("click the Filter button")
        for _ in range(6):
            hit = await sh.extract(
                f"the table row whose Name is exactly '{name}' (not a longer name that contains it)", CatalogHit
            )
            # Trust, but verify: a model can return a plausible ID (even "BA-000")
            # for a row that isn't there. The page text must have that exact ID
            # and name side by side in one table row.
            cid = (hit.data.catalog_id or "").strip()
            row_prefix = json.dumps(f"{cid}|{name}|")
            if cid and (hit.data.name or "").strip() == name and await page.evaluate(
                "document.body.innerText.split('\\n')"
                f".some(line => line.split('\\t').map(s => s.trim()).join('|').startsWith({row_prefix}))"
            ):
                ids[name] = cid
                break
            await sh.act("click the Next link in the pagination")
        ctx.log(f"catalog {name}: {ids.get(name)}")
    return ids


async def submit_form(sh: Stagehand, page, rows: list[dict], ctx: Context) -> str | None:
    await page.goto(ctx.url("/submit"))
    # observe() lists what's actionable; here: anything blocking the page.
    blockers = await sh.observe("a cookie consent or other dialog that covers the page")
    if blockers.data:
        # observe() found the dialog itself; acting on *that* clicks its backdrop.
        # Ask for the button that closes it instead.
        ctx.log(f"found blocker: {blockers.data[0].description}")
        await sh.act("click the button that accepts or closes the cookie consent dialog")
    for i, row in enumerate(rows, start=1):
        for label, key in (("Catalog ID", "catalog_id"), ("Name", "name"),
                           ("GitHub stars", "stars"), ("License", "license")):
            await sh.act(f"type %value% into the {label} field of Framework {i}",
                         variables={"value": str(row[key])})
        await sh.act(f"select %value% in the Language dropdown of Framework {i}",
                     variables={"value": row["language"]})
    # Date pickers are the classic trap: typing "2026-09-27" key by key into a
    # Chrome date input leaves it empty, and the browser then silently refuses
    # to submit. Ask for a fill, verify, and fall back to the picker's key order.
    today = dt.date.today()
    await sh.act("fill the Checked on date field with %value%", variables={"value": today.isoformat()})
    if not await page.evaluate("document.querySelector('input[type=date]')?.value"):
        ctx.log("date empty after fill; typing it in month/day/year order")
        await sh.act("click the Checked on date field and type %value%", variables={"value": today.strftime("%m%d%Y")})
    for _ in range(4):  # the late trap: the button may not exist yet
        # "Submit report" is the form's button; the header also has a "Submit" link.
        res = await sh.act("click the 'Submit report' button at the bottom of the form (not the header link)")
        ctx.log(f"submit click: {res.data.message}")
        if res.data.success:
            break
        await page.wait_for_timeout(2000)
    await page.wait_for_timeout(1500)
    receipt = (await sh.extract("the receipt code", Receipt)).data.receipt
    ctx.log(f"receipt: {receipt}  (page: {await page.title()})")
    return receipt


async def solve_async(ctx: Context) -> Outcome:
    browser = await local_browser.launch(headless=ctx.args.headless)
    try:
        sh = await Stagehand.create(browser=browser, model=stagehand_llm.generate)
        try:
            page = (await browser.context.pages())[0]
            facts = await read_facts(sh, page, ctx)
            ids = await find_ids(sh, page, facts, ctx)
            rows = [{"catalog_id": ids.get(n, ""), "name": n, **facts[n]} for n in TARGETS]
            receipt = await submit_form(sh, page, rows, ctx)
            return Outcome(result={"rows": rows, "receipt": receipt})
        finally:
            await sh.close()
    finally:
        await browser.close()


def solve(ctx: Context) -> Outcome:
    outcome = asyncio.run(solve_async(ctx))
    u = stagehand_llm.usage
    outcome.tokens_in, outcome.tokens_out = u.tokens_in, u.tokens_out
    outcome.cost_usd = llm.estimate_cost(u.tokens_in, u.tokens_out)
    outcome.notes = f"{u.calls} LLM calls to {llm.model()}"
    return outcome


def add_args(p):
    p.add_argument("--headless", action="store_true", help="hide the Stagehand browser window")


if __name__ == "__main__":
    raise SystemExit(run("L3", "Stagehand (act/extract/observe)", solve, sources=[__file__], add_args=add_args))
