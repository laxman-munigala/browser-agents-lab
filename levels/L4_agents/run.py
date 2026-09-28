"""L4 · Autonomous browser agents: give a goal, get a result.

    uv run python -m levels.L4_agents.run --agent bu-local     # open-source Browser Use, local Chrome, DeepSeek
    uv run python -m levels.L4_agents.run --agent bu-cloud     # Browser Use Cloud agent (API v4)
    uv run python -m levels.L4_agents.run --agent tinyfish     # TinyFish Web Agent

No steps, no selectors: every agent gets the same prompt (common/task.py
agent_prompt) and returns the same JSON. The checker then verifies it; an
agent's own "success" is never trusted.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from pydantic import BaseModel

from common import llm
from common.browsers import BROWSER_USE_API, local_cdp_url
from common.config import require
from common.runner import Context, Outcome, run
from common.task import RESULT_JSON_SCHEMA, parse_result

AGENTS = {
    "bu-local": "Browser Use (open source, local Chrome)",
    "bu-cloud": "Browser Use Cloud agent",
    "tinyfish": "TinyFish Web Agent",
}

BU_CLOUD_MODEL = "gpt-5.6-luna"  # Browser Use's recommended, cheapest hosted model
MAX_COST_USD = 1.0               # hard stop for a runaway cloud run


# ---------- open-source Browser Use on the lab's local Chrome ----------


class Row(BaseModel):
    catalog_id: str
    name: str
    stars: int
    license: str
    language: str


class Result(BaseModel):
    rows: list[Row]
    receipt: str


def solve_bu_local(ctx: Context) -> Outcome:
    from browser_use import Agent, Browser
    from browser_use.llm.openrouter.chat import ChatOpenRouter

    async def go():
        browser = Browser(cdp_url=local_cdp_url(), keep_alive=True)
        agent = Agent(
            task=ctx.prompt,
            llm=ChatOpenRouter(model=llm.model(), api_key=llm.api_key()),
            browser=browser,
            output_model_schema=Result,
            use_vision=False,  # DOM/accessibility text only: cheaper and faster
        )
        try:
            return await agent.run(max_steps=60)
        finally:
            await browser.stop()  # disconnect cleanly; the lab Chrome stays open

    history = asyncio.run(go())
    out = history.structured_output
    result = out.model_dump() if out else parse_result(history.final_result())
    u = history.usage
    tokens_in = u.total_prompt_tokens if u else None
    tokens_out = u.total_completion_tokens if u else None
    return Outcome(
        result=result,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=llm.estimate_cost(tokens_in or 0, tokens_out or 0),
        notes=f"{history.number_of_steps()} steps with {llm.model()}; agent said success={history.is_successful()}",
    )


# ---------- Browser Use Cloud (API v4) ----------


def solve_bu_cloud(ctx: Context) -> Outcome:
    headers = {"X-Browser-Use-API-Key": require("BROWSER_USE_API_KEY")}
    with httpx.Client(base_url=BROWSER_USE_API, headers=headers, timeout=60) as client:
        created = client.post("/runs", json={
            "task": ctx.prompt,
            "model": BU_CLOUD_MODEL,
            "outputSchema": RESULT_JSON_SCHEMA,
            "maxCostUsd": MAX_COST_USD,
            "browserSettings": {"proxyCountryCode": None},  # public sites; skip the paid proxy
        }).raise_for_status().json()
        run_id = created["id"]
        ctx.log(f"run {run_id} ({created['model']}); watch at https://cloud.browser-use.com")
        status, last = created["status"], None
        while status not in ("completed", "failed", "cancelled"):
            time.sleep(5)
            status = client.get(f"/runs/{run_id}/status").raise_for_status().json()["status"]
            if status != last:
                ctx.log(f"status: {status}")
                last = status
        final = client.get(f"/runs/{run_id}").raise_for_status().json()
    result = final.get("output") if isinstance(final.get("output"), dict) else parse_result(final.get("result"))
    return Outcome(
        result=result,
        tokens_in=final.get("totalInputTokens"),
        tokens_out=final.get("totalOutputTokens"),
        cost_usd=float(final.get("totalCostUsd") or 0),
        notes=f"status={final['status']} model={final['model']}" + (f" error={final['error']}" if final.get("error") else ""),
        extra={"bu_run_id": run_id},
    )


# ---------- TinyFish Web Agent ----------


def solve_tinyfish(ctx: Context) -> Outcome:
    # TinyFish's structured-output subset rejects additionalProperties.
    schema = json.loads(json.dumps(RESULT_JSON_SCHEMA).replace(', "additionalProperties": false', ""))
    body = {"url": ctx.url("/items"), "goal": ctx.prompt, "output_schema": schema}
    headers = {"X-API-Key": require("TINYFISH_API_KEY")}
    final: dict[str, Any] = {}
    with httpx.stream("POST", "https://agent.tinyfish.ai/v1/automation/run-sse",
                      headers=headers, json=body, timeout=httpx.Timeout(900, connect=30)) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            kind = event.get("type")
            if kind == "STREAMING_URL":
                ctx.log(f"watch live: {event['streaming_url']}")
            elif kind == "PROGRESS":
                ctx.log(f"· {event.get('purpose')}")
            elif kind == "COMPLETE":
                final = event
                break
    return Outcome(
        result=parse_result(final.get("result")),
        notes=f"status={final.get('status')}" + (f" error={final.get('error')}" if final.get("error") else ""),
        extra={"tinyfish_run_id": final.get("run_id")},
    )


SOLVERS = {"bu-local": solve_bu_local, "bu-cloud": solve_bu_cloud, "tinyfish": solve_tinyfish}


def solve(ctx: Context) -> Outcome:
    return SOLVERS[ctx.args.agent](ctx)


def add_args(p):
    p.add_argument("--agent", choices=sorted(AGENTS), default="bu-local")


if __name__ == "__main__":
    import argparse

    pre = argparse.ArgumentParser(add_help=False)
    add_args(pre)
    agent = pre.parse_known_args()[0].agent
    raise SystemExit(run("L4", AGENTS[agent], solve, sources=[__file__], add_args=add_args))
