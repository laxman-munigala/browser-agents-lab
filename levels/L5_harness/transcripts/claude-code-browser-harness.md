# Transcript: Claude Code + browser-harness

A real session from 2026-09-27. Claude Code (Opus 5.5) was building this lab
and ran the L5 task itself through browser-harness 0.1.13, attached to the lab
Chrome (`BU_CDP_WS` from `cdp_discovery`, daemon `BU_NAME=lab-l5`).

Run ID: `L5-claude-code---browser-harness-0927-012056-3f82`
Result: **✓ submitted, navigated, read, all checks passed**, 70 s wall time.

The commands below are shown as the agent ran them, with their output.

## 1. Read GitHub (stars and languages)

```bash
BU_CDP_WS="$WS" BU_NAME=lab-l5 BH_TAB_MARKER=0 uvx --from browser-harness==0.1.13 browser-harness <<'PY'
new_tab("https://github.com/microsoft/playwright")
wait_for_load()
import time
out = {}
for repo in ["microsoft/playwright", "SeleniumHQ/selenium", "puppeteer/puppeteer"]:
    goto_url(f"https://github.com/{repo}")
    wait_for_load()
    for _ in range(20):          # the Languages box renders late
        info = js("""(() => {
          const s = document.querySelector('#repo-stars-counter-star')?.getAttribute('title');
          const sec = t => { const h=[...document.querySelectorAll('h2')].find(h=>h.textContent.trim()===t);
                             return h ? h.parentElement.parentElement.innerText.replace(/\\s+/g,' ') : ''; };
          return {stars: s, about: sec('About'), langs: sec('Languages')};
        })()""")
        if info and '%' in (info.get('langs') or ''):
            break
        time.sleep(0.5)
    out[repo] = {"stars": info["stars"], "about_tail": info["about"][-160:]}
print(out)
PY
```

```
{'microsoft/playwright': {'stars': '96,717', 'about_tail': '... Languages TypeScript 91.9% HTML 3.6% ...'},
 'SeleniumHQ/selenium': {'stars': '34,511', 'about_tail': '... Languages Java 33.5% C# 15.1% ...'},
 'puppeteer/puppeteer': {'stars': '95,622', 'about_tail': '... Languages TypeScript 94.8% JavaScript 3.8% ...'}}
```

## 2. Licenses and catalog IDs

```bash
... browser-harness <<'PY'
import os, re
lic = {}
for repo in [...]:
    goto_url(f"https://github.com/{repo}"); wait_for_load()
    lic[repo] = re.findall(r"(\S+) license", js("document.body.innerText"))[:2]
print("licenses:", lic)
rows = {}
for lang in ["TypeScript", "Java"]:
    page = 1
    while True:
        goto_url(f"{base}/items?run={run}&lang={lang}&page={page}"); wait_for_load()
        text = js("document.querySelector('table').innerText")
        rows.update({l.split('\t')[1].strip(): l.split('\t')[0].strip() for l in text.splitlines()[1:] if '\t' in l})
        if not js("!!document.querySelector('a[rel=next]')"): break
        page += 1
print({k: rows.get(k) for k in ["Playwright", "Selenium", "Puppeteer"]})
PY
```

```
licenses: {'microsoft/playwright': ['Apache-2.0', 'Apache-2.0'], 'SeleniumHQ/selenium': ['Apache-2.0', 'Apache-2.0'], 'puppeteer/puppeteer': ['for', 'Apache-2.0']}
{'Playwright': 'BA-664', 'Selenium': 'BA-475', 'Puppeteer': 'BA-381'}
```

## 3. Fill and submit: the first click does nothing

The form was filled with one `js()` call (the skill says: *"find a faster
page-appropriate input method, then verify the page kept the exact value"*),
then the submit button was clicked at its centre.

```
form valid: True
receipt: None | {'url': '.../submit?run=...', 'title': 'Submit · Framework Registry', ...}
```

The skill's preferred path (accessibility tree → `DOM.getBoxModel` →
`click_at_xy`) found the right node and still didn't submit:

```
ax buttons: [('Submit report', 137)]
click at 218.5 652.1
receipt: None | Submit · Framework Registry
```

## 4. Bring the tab to the front, click again

SKILL.md: *"A timed-out scroll(...) on an attached background tab is evidence
that the page needs to be visible. Call activate_tab(current_tab()) ..."* The same
applied to this click:

```python
activate_tab(current_tab())
# ... same AX-tree lookup and click_at_xy ...
```

```
receipt: d9b1823f5d48 | Submitted · Framework Registry
```

## 5. Score it

```bash
uv run python -m levels.L5_harness.session finish --run-id L5-claude-code---browser-harness-0927-012056-3f82 \
  --result '{"rows": [...], "receipt": "d9b1823f5d48"}'
```

```
{"success": true, "submitted": true, "navigated": true, "read": true, "problems": []}
SUCCESS in 70s
```

## Takeaways

- The agent used the harness as a programmable browser, not a click-by-click
  remote: 5 scripts in total.
- The one failure was a harness-level detail (background tab input), and the
  harness's own SKILL.md had the fix. Skills are part of the tool.
