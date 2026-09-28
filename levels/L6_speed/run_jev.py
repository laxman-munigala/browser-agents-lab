"""L6 · Speed: jev-ultrafast on the "act" step (fill the form and submit).

jev is an action agent: it clicks, types and selects, but doesn't extract data.
So L6 isolates the step every agent has to do, filling and submitting the form,
and gives each engine the same goal with the facts already supplied. Compare
with run_baseline.py (Browser Use + DeepSeek on the identical goal).

browser-harness (jev's browser layer) pins websockets 15, Stagehand needs 16,
so this runs in a throwaway environment instead of the lab's:

    uv run --no-project --with "jev-ultrafast @ git+https://github.com/browser-use/jev-ultrafast" \
        --with python-dotenv python -m levels.L6_speed.run_jev

Needs TYPESAFE_API_KEY (the Jev policy model) and OPENROUTER_API_KEY (for
TYPE_TEXT, via DeepSeek V4.1 Flash).
"""

from __future__ import annotations

import json
import os
import time

from common.browsers import local_cdp_url
from common.config import env, require
from common.runner import Context, Outcome, run
from levels.L6_speed.goal import act_goal, expected_rows


def solve(ctx: Context) -> Outcome:
    # jev's browser layer (browser-harness) attaches to the browser named in
    # BU_CDP_WS; point it at the lab's Chrome and give it its own daemon name.
    os.environ["BU_CDP_WS"] = local_cdp_url()
    os.environ.setdefault("BU_NAME", "lab")
    os.environ["TYPESAFE_API_KEY"] = require("TYPESAFE_API_KEY")
    os.environ["TEXT_MODEL_API_KEY"] = require("OPENROUTER_API_KEY")
    os.environ["TEXT_MODEL_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["TEXT_MODEL"] = env("LAB_LLM_MODEL") or "deepseek/deepseek-v4.1-flash"
    os.environ["TEXT_MODEL_REASONING"] = "none"

    from jev_ultrafast import Agent  # imported after the env is set

    rows = expected_rows()
    goal = act_goal(rows)
    started = time.monotonic()
    with Agent(ctx.url("/submit", date="text"), goal) as agent:
        state = None
        for state in agent.run():
            ctx.log(f"{state['elapsed_ms']:>6} ms  {len(state['history']):>2} actions  {state['status']}")
        agent_ms = state["elapsed_ms"] if state else None
        # jev reports DONE but returns no data: read the receipt ourselves.
        receipt = agent.browser.call(
            "Runtime.evaluate",
            expression="document.querySelector('#receipt')?.textContent.trim() || null",
            returnByValue=True,
        )["result"].get("value")
        status = state["status"] if state else "?"
        actions = len(state["history"]) if state else 0
    ctx.log(f"receipt: {receipt}")
    return Outcome(
        result={"rows": rows, "receipt": receipt},
        notes=f"act step only; jev status={status}, {actions} actions, agent loop {agent_ms} ms "
              f"(total incl. setup {time.monotonic() - started:.1f}s); text model {os.environ['TEXT_MODEL']}",
        extra={"history": json.loads(json.dumps(state["history"], default=str)) if state else None},
    )


if __name__ == "__main__":
    import levels.L6_speed.goal as goal_mod

    raise SystemExit(run("L6", "jev-ultrafast (act step)", solve, sources=[__file__, goal_mod.__file__]))
