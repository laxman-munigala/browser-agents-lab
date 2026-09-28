"""L6 · Baseline for the speed comparison: Browser Use + DeepSeek on the same act-only goal.

    uv run python -m levels.L6_speed.run_baseline

Same goal text as run_jev.py (levels/L6_speed/goal.py), same local Chrome.
Browser Use sends the page state to the LLM every step and the LLM writes the
whole next action; jev picks an operation and a target from a table instead.
"""

from __future__ import annotations

import asyncio

from common import llm
from common.browsers import local_cdp_url
from common.runner import Context, Outcome, run
from common.task import parse_result
from levels.L6_speed.goal import act_goal, expected_rows


def solve(ctx: Context) -> Outcome:
    from browser_use import Agent, Browser
    from browser_use.llm.openrouter.chat import ChatOpenRouter

    rows = expected_rows()
    task = (
        f"Open {ctx.url('/submit', date='text')}\n" + act_goal(rows)
        + '\nFinish by returning JSON: {"receipt": "<the receipt code>"}'
    )

    async def go():
        browser = Browser(cdp_url=local_cdp_url(), keep_alive=True)
        agent = Agent(
            task=task,
            llm=ChatOpenRouter(model=llm.model(), api_key=llm.api_key()),
            browser=browser,
            use_vision=False,
            flash_mode=ctx.args.flash,  # Browser Use's own fast mode: no thinking/eval fields
        )
        try:
            return await agent.run(max_steps=25)
        finally:
            await browser.stop()

    history = asyncio.run(go())
    receipt = (parse_result(history.final_result()) or {}).get("receipt")
    u = history.usage
    return Outcome(
        result={"rows": rows, "receipt": receipt},
        tokens_in=u.total_prompt_tokens if u else None,
        tokens_out=u.total_completion_tokens if u else None,
        cost_usd=llm.estimate_cost(u.total_prompt_tokens, u.total_completion_tokens) if u else None,
        notes=f"act step only; {history.number_of_steps()} steps; flash_mode={ctx.args.flash}",
    )


def add_args(p):
    p.add_argument("--flash", action="store_true", help="Browser Use flash_mode (fewer output tokens per step)")


if __name__ == "__main__":
    import sys

    import levels.L6_speed.goal as goal_mod

    label = "Browser Use flash + DeepSeek (act step)" if "--flash" in sys.argv else "Browser Use + DeepSeek (act step)"
    raise SystemExit(run("L6", label, solve, sources=[__file__, goal_mod.__file__], add_args=add_args))
