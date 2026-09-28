"""The shared L6 goal: submit the form with facts supplied up front.

Every L6 engine gets exactly this text, so the stopwatch measures the act step
(find fields, type, select, pick a date, click submit) and nothing else.
"""

from __future__ import annotations

import datetime as dt

from common.task import TARGETS, expected_ids, github_truth


def expected_rows() -> list[dict]:
    truth, ids = github_truth(), expected_ids()
    return [{"catalog_id": ids[n], "name": n, **truth[n]} for n in TARGETS]


def act_goal(rows: list[dict]) -> str:
    lines = "\n".join(
        f"- Framework {i}: catalog ID {r['catalog_id']}, name {r['name']}, "
        f"GitHub stars {r['stars']}, license {r['license']}, language {r['language']}"
        for i, r in enumerate(rows, start=1)
    )
    return (
        "Fill in the report form on this page with exactly these values:\n"
        f"{lines}\n"
        f"- Checked on: {dt.date.today():%B %-d, %Y} ({dt.date.today().isoformat()})\n"
        "Then click the 'Submit report' button. Stop when the page shows a receipt code."
    )
