"""The scoreboard: every run appends one JSON line; `render()` builds scoreboard.md.

    uv run python -m common.scoreboard          # regenerate scoreboard.md
    uv run python -m common.scoreboard --all    # also list every run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from common.config import LAB_ROOT, RUNS_DIR

RESULTS = RUNS_DIR / "results.jsonl"
SCOREBOARD_MD = LAB_ROOT / "scoreboard.md"


def record(entry: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    entry = {"ts": dt.datetime.now().isoformat(timespec="seconds"), **entry}
    with RESULTS.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def load() -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]
    except OSError:
        return []


def count_loc(paths: list[str | Path]) -> int:
    """Non-blank, non-comment lines: a rough 'how much code did this take'."""
    total = 0
    for p in paths:
        in_doc = False
        for line in Path(p).read_text().splitlines():
            s = line.strip()
            if s.startswith(('"""', "'''")):
                if not (len(s) > 3 and s.endswith(('"""', "'''"))):
                    in_doc = not in_doc
                continue
            if in_doc or not s or s.startswith("#"):
                continue
            total += 1
    return total


def _latest(runs: list[dict[str, Any]], pred) -> dict[str, Any] | None:
    hits = [r for r in runs if pred(r)]
    return hits[-1] if hits else None


def _mark(value: bool | None) -> str:
    return {True: "✓", False: "✗", None: "–"}[value]


# Levels whose runs call no LLM: their token count is 0, not unknown, and
# prompt injection can't apply to them.
NO_LLM_LEVELS = {"L0", "L1", "L2", "L7"}
# Levels that run entirely on your machine with no paid API: $0, not unknown.
FREE_LEVELS = {"L1", "L7", "X"}


def _tokens(run: dict[str, Any]) -> str:
    if run.get("tokens_in") is not None:
        return f"{run['tokens_in']:,} / {run.get('tokens_out') or 0:,}"
    return "0" if run["level"] in NO_LLM_LEVELS else "–"


def _cost(run: dict[str, Any]) -> str:
    cost = run.get("cost_usd")
    if cost is not None:
        return f"${cost:.4f}"
    return "$0" if run["level"] in FREE_LEVELS else "–"


def _secs(secs: float) -> str:
    return f"{secs:.1f}s" if secs < 10 else f"{secs:.0f}s"


def render() -> str:
    runs = load()
    keys: list[tuple[str, str]] = []
    for r in runs:
        k = (r["level"], r["tool"])
        if k not in keys:
            keys.append(k)
    keys.sort()

    lines = [
        "# Scoreboard",
        "",
        f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} from `runs/results.jsonl` "
        f"({len(runs)} runs). Each row is the latest normal-mode run of that tool; the last "
        "two columns come from its latest `--break` and `--traps inject` runs.",
        "",
        "| Level | Tool | Success | Time | LLM tokens (in/out) | Est. $ | Lines of code | Survives `break=1`? | Fell for injection? |",
        "|-------|------|---------|------|---------------------|--------|---------------|---------------------|---------------------|",
    ]
    for level, tool in keys:
        mine = [r for r in runs if r["level"] == level and r["tool"] == tool]
        normal = _latest(mine, lambda r: r["mode"] == "normal") or mine[-1]
        broken = _latest(mine, lambda r: "break" in r["mode"])
        injected = _latest(mine, lambda r: "inject" in r["mode"])
        if level in NO_LLM_LEVELS:
            inj = "n/a"
        elif injected and injected["checks"]["fell_for_injection"] is not None:
            inj = "yes ✗" if injected["checks"]["fell_for_injection"] else "no ✓"
        else:
            inj = "not run"
        lines.append(
            "| {level} | {tool} | {ok} | {secs} | {tokens} | {cost} | {loc} | {brk} | {inj} |".format(
                level=level,
                tool=tool,
                ok=_mark(normal["checks"]["success"]),
                secs=_secs(normal["secs"]),
                tokens=_tokens(normal),
                cost=_cost(normal),
                loc=normal.get("loc") or "–",
                brk=_mark(broken["checks"]["success"]) if broken else "not run",
                inj=inj,
            )
        )
    lines += [
        "",
        "✓ = passed all checks (submitted, navigated, read); see README.md \"How runs are checked\".",
        "Tokens `0` = no LLM involved; `–` = not reported (hosted agent, TypeSafe, or a coding-agent session).",
        "Cost `–` = billed as provider credits we don't read back. L6/L7 rows time only the act step.",
        "Lines of code `–` = the agent wrote the code during the session (L5).",
    ]
    return "\n".join(lines) + "\n"


def write() -> Path:
    SCOREBOARD_MD.write_text(render())
    return SCOREBOARD_MD


def main() -> None:
    p = argparse.ArgumentParser(description="Regenerate scoreboard.md from runs/results.jsonl")
    p.add_argument("--all", action="store_true", help="also print every run")
    args = p.parse_args()
    path = write()
    print(path.read_text())
    if args.all:
        for r in load():
            print(f"{r['ts']}  {r['level']:3} {r['tool']:28} {r['mode']:14} "
                  f"{'ok' if r['checks']['success'] else 'FAIL':4} {r['secs']:6.1f}s  {r['run_id']}")


if __name__ == "__main__":
    main()
