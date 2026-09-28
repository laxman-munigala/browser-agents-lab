"""L5 · Score a coding-agent session (Claude Code, Codex, …) driving a browser harness.

A harness run happens inside the coding agent's chat, not in a script, so this
level is two commands around it:

    # 1. Start: prints the prompt to paste into the agent, and starts the clock.
    uv run python -m levels.L5_harness.session start --tool "Claude Code + browser-harness"

    # 2. Finish: paste the agent's final JSON; checks it and writes a scoreboard row.
    uv run python -m levels.L5_harness.session finish --run-id <id> --result '{"rows": [...], "receipt": "..."}'
    uv run python -m levels.L5_harness.session finish --run-id <id> --result-file answer.json

Both take the usual --traps / --break flags on `start`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from common import scoreboard
from common.config import RUNS_DIR, load_env, mock_app_url
from common.task import TRAPS, Mode, agent_prompt, check, new_run_id, parse_result, result_path

HINTS = {
    "browser-harness": "Use the browser-harness skill (`browser-harness <<'PY' ... PY`) to control the browser.",
    "playwright-mcp": "Use the Playwright MCP tools (browser_navigate, browser_snapshot, browser_click, browser_type, ...).",
    "devtools-mcp": "Use the Chrome DevTools MCP tools (navigate_page, take_snapshot, click, fill, ...).",
    "agent-browser": "Use the agent-browser CLI (`agent-browser open <url>`, `agent-browser snapshot`, `agent-browser click @e1`, ...).",
}


def _pending(run_id: str) -> Path:
    return RUNS_DIR / f"pending-{run_id}.json"


def start(args: argparse.Namespace) -> int:
    traps = tuple(t for t in args.traps.split(",") if t)
    if set(traps) - set(TRAPS):
        sys.exit(f"unknown traps: {traps}")
    mode = Mode(traps=traps, broken=args.broken)
    run_id = new_run_id("L5", args.tool)
    prompt = agent_prompt(args.base_url or mock_app_url(), run_id, mode)
    hint = next((h for k, h in HINTS.items() if k in args.tool.lower().replace(" ", "-")), "")
    RUNS_DIR.mkdir(exist_ok=True)
    _pending(run_id).write_text(json.dumps({
        "run_id": run_id, "tool": args.tool, "traps": traps, "broken": args.broken, "started": time.time(),
    }))
    print(f"run id: {run_id}\n\n----- paste into the coding agent -----\n")
    print((hint + "\n\n" if hint else "") + prompt)
    print("\n----- then: -----")
    print(f"uv run python -m levels.L5_harness.session finish --run-id {run_id} --result '<the JSON>'")
    return 0


def finish(args: argparse.Namespace) -> int:
    meta = json.loads(_pending(args.run_id).read_text())
    raw = Path(args.result_file).read_text() if args.result_file else args.result
    result = parse_result(raw)
    mode = Mode(traps=tuple(meta["traps"]), broken=meta["broken"])
    secs = args.secs if args.secs is not None else time.time() - meta["started"]
    verdict = check(result, args.run_id, mode)
    result_path(args.run_id).write_text(json.dumps({"result": result, "verdict": verdict.as_dict()}, indent=1))
    scoreboard.record({
        "level": "L5",
        "tool": meta["tool"],
        "mode": mode.label,
        "run_id": args.run_id,
        "secs": round(secs, 2),
        "tokens_in": args.tokens_in,
        "tokens_out": args.tokens_out,
        "cost_usd": args.cost,
        "loc": 0,  # the agent wrote the code during the session
        "checks": verdict.as_dict(),
        "notes": args.notes or "coding-agent session; time includes the agent's thinking",
    })
    scoreboard.write()
    _pending(args.run_id).unlink()
    print(json.dumps(verdict.as_dict(), indent=1))
    print("SUCCESS" if verdict.success else "FAILED", f"in {secs:.0f}s")
    return 0 if verdict.success else 1


def main() -> int:
    load_env()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--tool", required=True, help='e.g. "Claude Code + browser-harness"')
    s.add_argument("--traps", default="")
    s.add_argument("--break", dest="broken", action="store_true")
    s.add_argument("--base-url")
    s.set_defaults(func=start)
    f = sub.add_parser("finish")
    f.add_argument("--run-id", required=True)
    f.add_argument("--result", help="the agent's final JSON (or text containing it)")
    f.add_argument("--result-file")
    f.add_argument("--secs", type=float, help="override the measured wall time")
    f.add_argument("--tokens-in", type=int)
    f.add_argument("--tokens-out", type=int)
    f.add_argument("--cost", type=float)
    f.add_argument("--notes")
    f.set_defaults(func=finish)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
