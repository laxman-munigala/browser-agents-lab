# Extra · Auth & sessions: whose browser is the agent using?

Logins are where browser automation gets real, and risky. There are four ways
to give an automated browser a session:

| Approach | How | Used in this lab |
|----------|-----|------------------|
| **Dedicated profile** | Chrome with its own `--user-data-dir`, kept between runs | `cdp_discovery.py`: `~/.config/google-chrome-cdp-lab` (clean), or `~/.config/google-chrome-cdp` (seeded) |
| **Seeded profile** | Copy cookies and logins from your everyday profile into the dedicated one | `cdp_discovery.py sync --profile "<your profile>"`; `BU_CDP_SEED=1` |
| **Portable state** | Playwright `storage_state`: cookies + localStorage as JSON, loaded into any context | `check.py` saves one |
| **Hosted profiles / vaults** | Browser Use Cloud profiles (`profileId`), TinyFish Browser Context Profiles and vault credentials | Mentioned in L2/L4; not used, since our targets are public |

## Run

```bash
# The lab default: clean profile, no logins
uv run python -m extras.auth_sessions.check

# A seeded profile (your logins), read-only check
BU_CDP_PROFILE=~/.config/google-chrome-cdp BU_CDP_SEED=1 uv run python -m extras.auth_sessions.check
```

Output on the lab profile (2026-09-27):

```
profile: ~/.config/google-chrome-cdp-lab  (seeding off)
github.com: not signed in
cookies in this browser: 8 total, 6 for github.com
storage_state: 8 cookies, 1 origins → runs/storage_state.example.json
```

`check.py` only reads. It opens github.com and reports whether that browser is
signed in.

## Why the lab defaults to a clean profile

- **Chrome 136+ refuses remote debugging on your default profile.** Any automated
  Chrome needs its own data dir anyway.
- **A seeded profile is you.** Every agent, harness and injected instruction that
  reaches that browser acts with your GitHub, email and bank sessions.
  `extras/prompt_injection` shows agents reading hostile page text; don't combine
  that with your real cookies.
- **Unmodified, the copied `cdp_discovery.py` seeds any new profile on first
  launch.** The lab adds `BU_CDP_SEED=0` so a new profile stays empty.

## Rules of thumb

1. Use a separate, clean profile per purpose (lab, scraping, personal agent).
2. Seed only the sites a task needs; refresh with `cdp_discovery.py sync`.
3. Treat `storage_state` files and profile directories like passwords (the lab's
   `.gitignore` excludes `runs/`).
4. For logins inside agent runs, prefer vault or secret-binding features (Browser
   Use `secretBindings`, TinyFish vault) that type credentials without the model
   ever seeing them.
5. Stop and ask a human for MFA, consent screens and purchases.

## Speaker notes

1. "Whose browser is it?" Show the two `check.py` outputs side by side: clean vs
   seeded.
2. Tell the Chrome 136 story: remote debugging on the default profile was a real
   attack path (malware stealing cookies over CDP), so Chrome closed it.
3. Tie it to prompt injection: *capability × untrusted input = risk*.
