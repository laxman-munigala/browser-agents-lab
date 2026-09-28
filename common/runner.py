"""The harness every level script runs through.

A level supplies one function, `solve(ctx) -> Outcome`. The runner parses the
shared CLI flags, makes a run ID, times the solve, checks the result, prints a
verdict, and appends a scoreboard row.

    --traps late,modal,inject   turn on mock-app traps
    --break                     rename the mock app's selectors
    --base-url URL              mock app (default: MOCK_APP_URL from .env)
    --no-record                 don't write to the scoreboard
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from common import scoreboard
from common.config import load_env, mock_app_url
from common.task import TRAPS, Mode, agent_prompt, check, new_run_id, result_path


@dataclass
class Context:
    level: str
    tool: str
    run_id: str
    base_url: str
    mode: Mode
    args: argparse.Namespace

    def url(self, path: str, **extra: Any) -> str:
        return f"{self.base_url}{path}{self.mode.query(self.run_id, **extra)}"

    @property
    def prompt(self) -> str:
        return agent_prompt(self.base_url, self.run_id, self.mode)

    def log(self, msg: str) -> None:
        print(f"  [{self.level}/{self.tool}] {msg}", flush=True)


@dataclass
class Outcome:
    result: dict[str, Any] | None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def run(
    level: str,
    tool: str,
    solve: Callable[[Context], Outcome],
    sources: list[str | Path],
    add_args: Callable[[argparse.ArgumentParser], None] | None = None,
    argv: list[str] | None = None,
) -> int:
    load_env()
    p = argparse.ArgumentParser(description=f"{level}: {tool}")
    p.add_argument("--traps", default="", help=f"comma list of {', '.join(TRAPS)}")
    p.add_argument("--break", dest="broken", action="store_true", help="rename mock-app selectors")
    p.add_argument("--base-url", default=None, help="mock app URL (default: MOCK_APP_URL)")
    p.add_argument("--no-record", action="store_true", help="don't write a scoreboard row")
    if add_args:
        add_args(p)
    args = p.parse_args(argv)

    traps = tuple(t.strip() for t in args.traps.split(",") if t.strip())
    unknown = set(traps) - set(TRAPS)
    if unknown:
        p.error(f"unknown traps: {', '.join(sorted(unknown))}")
    mode = Mode(traps=traps, broken=args.broken)
    tool_name = getattr(args, "tool_label", None) or tool
    ctx = Context(
        level=level,
        tool=tool_name,
        run_id=new_run_id(level, tool_name),
        base_url=(args.base_url or mock_app_url()).rstrip("/"),
        mode=mode,
        args=args,
    )

    print(f"\n▶ {level} · {tool_name} · mode={mode.label} · run={ctx.run_id}")
    print(f"  mock app: {ctx.base_url}")
    started = time.monotonic()
    try:
        outcome = solve(ctx)
    except KeyboardInterrupt:
        raise
    except Exception as e:  # a crash is a failed run, and still a scoreboard row
        traceback.print_exc()
        outcome = Outcome(result=None, notes=f"crashed: {type(e).__name__}: {e}"[:300])
    secs = time.monotonic() - started

    verdict = check(outcome.result, ctx.run_id, mode)
    result_path(ctx.run_id).write_text(
        json.dumps({"result": outcome.result, "verdict": verdict.as_dict(), "extra": outcome.extra}, indent=1)
    )

    print(f"\n  result : {json.dumps(outcome.result)[:400] if outcome.result else None}")
    print(
        "  checks : submitted={} navigated={} read={}{}".format(
            _yn(verdict.submitted),
            _yn(verdict.navigated),
            _yn(verdict.read),
            f" fell_for_injection={_yn(verdict.injection)}" if verdict.injection is not None else "",
        )
    )
    for problem in verdict.problems:
        print(f"           - {problem}")
    usage = ""
    if outcome.tokens_in is not None:
        usage = f"  tokens {outcome.tokens_in:,}/{outcome.tokens_out or 0:,}"
    if outcome.cost_usd is not None:
        usage += f"  ~${outcome.cost_usd:.4f}"
    print(f"  {'SUCCESS' if verdict.success else 'FAILED'} in {secs:.1f}s{usage}")
    if outcome.notes:
        print(f"  notes  : {outcome.notes}")

    if not args.no_record:
        scoreboard.record(
            {
                "level": level,
                "tool": tool_name,
                "mode": mode.label,
                "run_id": ctx.run_id,
                "secs": round(secs, 2),
                "tokens_in": outcome.tokens_in,
                "tokens_out": outcome.tokens_out,
                "cost_usd": outcome.cost_usd,
                "loc": scoreboard.count_loc(sources),
                "checks": verdict.as_dict(),
                "notes": outcome.notes,
            }
        )
        scoreboard.write()
    return 0 if verdict.success else 1


def _yn(value: bool | None) -> str:
    return {True: "yes", False: "no", None: "-"}[value]

