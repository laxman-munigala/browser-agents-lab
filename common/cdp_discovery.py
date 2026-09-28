"""CDP endpoint discovery — and on-demand launch — for connecting Playwright to Chrome.

Lets any script drive a real Chrome via the Chrome DevTools Protocol, with no
bundled Chromium. BU_CDP_SEED=0 turns off cookie seeding, so a new profile
starts empty (the lab's default; see README.md "Local browser (CDP)").

Two Chrome facts shape this module:
  * Chrome >= 136 refuses --remote-debugging-port while running on the default
    user-data-dir ("DevTools remote debugging requires a non-default data
    directory"), so the debuggable browser cannot be your everyday profile.
  * One profile is held by one Chrome process, so a second launch against a
    profile already in use just hands a window to the running instance.

Hence a dedicated persistent data dir (BU_CDP_PROFILE, default
~/.config/google-chrome-cdp). When seeding is on, it is seeded once from ONE of
your everyday Chrome profiles (SOURCE_PROFILE, by the display name Chrome shows
in its profile menu, or its directory name) so that profile's logins carry over.
The launched window is left running between runs; close it when done.

Usage:
    from cdp_discovery import discover_cdp
    endpoint = discover_cdp()                     # attach, launching Chrome if needed
    endpoint = discover_cdp(auto_launch=False)    # attach only, never launch
    endpoint = discover_cdp("http://localhost:9223")

The copy does not track the original: refresh it with `sync` whenever the source
profile has picked up cookies your scripts need.

CLI:
    python cdp_discovery.py status
    python cdp_discovery.py profiles
    python cdp_discovery.py sync [--no-launch] [--profile "Work"]
    python cdp_discovery.py launch [--reseed] [--profile "Work"]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

# Lab addition: load the lab's .env before reading BU_CDP_PROFILE / BU_CDP_SEED
# below, so the CLI (`python -m common.cdp_discovery launch`) gets the clean lab
# profile too, not the seeded default.
try:
    from common.config import load_env as _load_lab_env

    _load_lab_env()
except ImportError:
    pass

DEFAULT_CDP_PORTS = (9222, 9223)
LAUNCH_PORT = 9222
LAUNCH_TIMEOUT_S = 30.0

CDP_PROFILE_DIR = Path(
    os.environ.get("BU_CDP_PROFILE") or Path.home() / ".config/google-chrome-cdp"
).expanduser()

# Lab addition: with BU_CDP_SEED=0 a new profile is never seeded from your
# everyday Chrome, so agents and injection traps run without your logins.
SEED_ENABLED = os.environ.get("BU_CDP_SEED", "1").strip().lower() not in ("0", "false", "no", "off")
UNSEEDED_PROFILE_DIRNAME = "Default"
EVERYDAY_PROFILES = (
    Path.home() / ".config/google-chrome",
    Path.home() / ".config/chromium",
)

# Which of your everyday Chrome profiles seeding copies from. Accepts the display
# name shown in Chrome's profile menu (e.g. "Work") or the on-disk directory name
# (e.g. "Profile 2"). Defaults to Chrome's first profile, "Default";
# BU_CDP_SOURCE_PROFILE overrides it.
SOURCE_PROFILE = os.environ.get("BU_CDP_SOURCE_PROFILE") or "Default"

# Records which profile directory a seeded CDP dir actually holds, so a later
# launch uses the same one without having to re-resolve the display name.
SOURCE_MARKER = ".cdp-source-profile"
CHROME_BINARIES = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
)

# Seeded into a fresh CDP profile. "Local State" carries the os_crypt key wrapper
# that the cookie store is encrypted against — without it the copied cookies are
# undecryptable noise. The stores themselves are SQLite and are copied with the
# backup API so a live Chrome's WAL cannot hand us a torn read.
SEED_PLAIN = ("Local State",)          # relative to the user-data-dir
SEED_SQLITE = ("Cookies", "Login Data")  # relative to the profile directory inside it


def _windows_host_ip() -> Optional[str]:
    """On WSL2 (NAT mode), the Windows host is the DNS nameserver in /etc/resolv.conf."""
    try:
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            if line.startswith("nameserver"):
                ip = line.split()[1]
                if not ip.startswith("127."):
                    return ip
    except Exception:
        pass
    return None


def _endpoint_for_port(host: str, port: int, timeout: float = 2.0) -> Optional[str]:
    """Return a usable CDP endpoint for a listening port, or None if nothing is there.

    Chrome 152 only writes DevToolsActivePort when it picks the port itself, so an
    explicit --remote-debugging-port leaves no file — /json/version is what tells
    us the browser is actually up. On the profiles where Chrome 147+ answers 404
    there, the bare HTTP endpoint is still enough for connect_over_cdp.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return None
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/json/version", timeout=timeout
        ) as resp:
            if ws := json.load(resp).get("webSocketDebuggerUrl"):
                return ws
    except Exception:
        pass
    return f"http://{host}:{port}"


def _read_port_file(path: Path) -> tuple[Optional[int], Optional[str]]:
    """Parse DevToolsActivePort: port on line 1, browser WS path on line 2."""
    try:
        lines = path.read_text().strip().splitlines()
    except OSError:
        return None, None
    try:
        port = int(lines[0].strip())
    except (IndexError, ValueError):
        return None, None
    ws = f"ws://127.0.0.1:{port}{lines[1].strip()}" if len(lines) >= 2 else None
    return port, ws


def _endpoint_from_port_file(path: Path, accept=None) -> Optional[str]:
    """Resolve a profile's DevToolsActivePort file to a *currently valid* endpoint.

    The file outlives the browser that wrote it, and its recorded browser UUID
    dies with it — while the port itself may well have been reclaimed by a
    different Chrome. So the port is the only part worth trusting: /json/version
    on it is authoritative, and the file's recorded path is the fallback for the
    profiles where Chrome 147+ answers that with a 404.
    """
    port, ws = _read_port_file(path)
    if port is None or (accept is not None and not accept(port)):
        return None
    endpoint = _endpoint_for_port("127.0.0.1", port)
    if endpoint is None:
        return None
    if endpoint.startswith("ws://") or ws is None:
        return endpoint
    return ws


def _profile_search_path() -> list[Path]:
    """Profile dirs that might hold a live DevToolsActivePort, ours first."""
    dirs = [CDP_PROFILE_DIR, *EVERYDAY_PROFILES, Path.home() / ".config/google-chrome/User Data"]

    # Windows Chrome accessible via WSL2 /mnt/c mount
    mnt = Path("/mnt/c/Users")
    if mnt.is_dir():
        try:
            for user_dir in mnt.iterdir():
                dirs.append(user_dir / "AppData/Local/Google/Chrome/User Data")
        except OSError:
            pass
    return dirs


def _read_devtools_active_port(accept=None) -> Optional[str]:
    """Return a live ws:// URL from any known profile's DevToolsActivePort file."""
    for base in _profile_search_path():
        if endpoint := _endpoint_from_port_file(base / "DevToolsActivePort", accept):
            return endpoint
    return None


def _parse_env_file() -> dict[str, str]:
    """Walk up from CWD (max 5 levels) looking for a .env file."""
    path = Path.cwd()
    for _ in range(5):
        candidate = path / ".env"
        if candidate.exists():
            result: dict[str, str] = {}
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip()
            return result
        parent = path.parent
        if parent == path:
            break
        path = parent
    return {}


def _find_chrome() -> str:
    if override := os.environ.get("BU_CHROME_BIN"):
        return override
    for name in CHROME_BINARIES:
        if found := shutil.which(name):
            return found
    raise RuntimeError(
        "no Chrome binary on PATH (looked for: "
        + ", ".join(CHROME_BINARIES)
        + ") — set BU_CHROME_BIN to its full path"
    )


def _proc_cmdlines() -> list[tuple[int, bytes]]:
    """(pid, flattened command line) for every readable process.

    Chrome rewrites its own process title, so its cmdline arrives as one blob
    rather than the NUL-separated argv every other process gives us — flattening
    is what makes both shapes searchable.
    """
    out: list[tuple[int, bytes]] = []
    try:
        pids = [d for d in os.listdir("/proc") if d.isdigit()]
    except OSError:
        return out
    for pid in pids:
        try:
            out.append((int(pid), Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")))
        except (OSError, ValueError):
            continue
    return out


def _flag_value(flat: bytes, flag: str) -> Optional[str]:
    """Value of `--flag=…` in a flattened command line, stopping at the next ` --`.

    The lookahead is what lets a path containing spaces survive.
    """
    m = re.search(rb"--" + re.escape(flag.encode()) + rb"=(.*?)(?= --|\s*$)", flat)
    if not m:
        return None
    try:
        return m.group(1).decode()
    except UnicodeDecodeError:
        return None


def _chrome_user_data_dir_on_port(port: int) -> Optional[Path]:
    """Best effort: the --user-data-dir of the Chrome serving `port`, or None.

    Scans /proc rather than shelling out, and stays optional — on any platform or
    permission setup where this cannot be answered, callers fall back to reusing
    whatever endpoint is live.
    """
    want = f"--remote-debugging-port={port}".encode()
    for _pid, flat in _proc_cmdlines():
        if want in flat and (value := _flag_value(flat, "user-data-dir")):
            return Path(value)
    return None


def chrome_pids_on_data_dir(profile: Path) -> list[int]:
    """Browser (not renderer/GPU) process ids running on `profile`."""
    pids = []
    for pid, flat in _proc_cmdlines():
        if b"--type=" in flat:  # a child process, not the browser itself
            continue
        if (value := _flag_value(flat, "user-data-dir")) and Path(value) == profile:
            pids.append(pid)
    return pids


def stop_chrome(profile: Path, timeout: float = 20.0) -> list[int]:
    """Ask the Chrome on `profile` to quit, and wait for it. Returns the pids stopped.

    SIGTERM rather than SIGKILL on purpose: Chrome flushes its cookie store on a
    clean exit, and a killed browser can leave the copy we are about to overwrite
    mid-write anyway.
    """
    pids = chrome_pids_on_data_dir(profile)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not chrome_pids_on_data_dir(profile):
            return pids
        time.sleep(0.25)
    for pid in chrome_pids_on_data_dir(profile):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(1.0)
    return pids


def _everyday_root() -> Optional[Path]:
    return next((p for p in EVERYDAY_PROFILES if p.is_dir()), None)


def list_profiles(root: Optional[Path] = None) -> dict[str, str]:
    """Map profile directory name -> display name, from the root's Local State."""
    root = root or _everyday_root()
    if root is None:
        return {}
    try:
        state = json.loads((root / "Local State").read_text())
    except (OSError, ValueError):
        return {}
    cache = state.get("profile", {}).get("info_cache", {})
    return {d: meta.get("name", d) for d, meta in cache.items()}


def resolve_profile(name: str, root: Optional[Path] = None) -> str:
    """Resolve a profile display name to its directory name ('Work' -> 'Profile 2').

    A directory name that already exists is passed straight through, so both
    forms work wherever a profile is named.
    """
    root = root or _everyday_root()
    if root is not None and (root / name).is_dir():
        return name
    profiles = list_profiles(root)
    for dirname, display in profiles.items():
        if display == name:
            return dirname
    known = ", ".join(f"{d} ({n})" for d, n in sorted(profiles.items())) or "none found"
    raise RuntimeError(f"no Chrome profile named {name!r} — known profiles: {known}")


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _copy_sqlite(src: Path, dst: Path) -> None:
    """Consistent copy of a live SQLite store via the backup API."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def seed_profile(
    dst: Path, source: Optional[str] = None, src_root: Optional[Path] = None
) -> tuple[str, list[str]]:
    """Copy one everyday Chrome profile's cookies and logins into the CDP data dir.

    `source` is a display name or a profile directory name; the copy keeps the
    same directory name inside `dst` so Chrome can be pointed at it with
    --profile-directory. Best-effort: anything that fails to copy just means
    logging in once inside the CDP window. Returns (profile dirname, files copied).
    """
    root = src_root or _everyday_root()
    profile_dirname = resolve_profile(source or SOURCE_PROFILE, root)
    if root is None:
        return profile_dirname, []

    dst.mkdir(parents=True, exist_ok=True)
    (dst / profile_dirname).mkdir(exist_ok=True)
    copied: list[str] = []
    for rel in SEED_PLAIN:
        try:
            shutil.copy2(root / rel, dst / rel)
            copied.append(rel)
        except OSError:
            pass
    for rel in SEED_SQLITE:
        try:
            _copy_sqlite(root / profile_dirname / rel, dst / profile_dirname / rel)
            copied.append(f"{profile_dirname}/{rel}")
        except (OSError, sqlite3.Error):
            pass
    try:
        (dst / SOURCE_MARKER).write_text(profile_dirname + "\n")
    except OSError:
        pass
    return profile_dirname, copied


def seeded_profile_dirname(profile: Path) -> str:
    """Which profile directory a CDP data dir holds — the marker, else resolve afresh."""
    if not SEED_ENABLED:
        return UNSEEDED_PROFILE_DIRNAME
    try:
        if marker := (profile / SOURCE_MARKER).read_text().strip():
            return marker
    except OSError:
        pass
    return resolve_profile(SOURCE_PROFILE)


def sync_cookies(
    profile: Optional[Path] = None,
    source: Optional[str] = None,
    relaunch: bool = True,
) -> dict:
    """Re-copy the source profile's cookies into the CDP data dir.

    The CDP Chrome must be stopped first: it holds its cookie store open and
    rewrites it from memory on exit, so a copy made underneath a live browser is
    simply undone. That is why this is a command you run rather than something
    that can happen while the scrapers work.

    Cookies the source Chrome has not flushed to disk yet (recent logins, and
    anything still session-only) will not be in the copy — close that window
    first if a just-completed login has to come across.
    """
    profile = profile or CDP_PROFILE_DIR
    stopped = stop_chrome(profile)
    profile_dirname, copied = seed_profile(profile, source)
    result = {
        "profile_dir": profile_dirname,
        "copied": copied,
        "stopped": stopped,
        "endpoint": None,
    }
    if relaunch:
        result["endpoint"] = launch_chrome_cdp(profile, source=source)
    return result


def launch_chrome_cdp(
    profile_dir: Optional[Path] = None,
    port: Optional[int] = None,
    timeout: float = LAUNCH_TIMEOUT_S,
    reseed: bool = False,
    source: Optional[str] = None,
) -> str:
    """Start a debuggable Chrome window on the dedicated profile; return its endpoint.

    The window opens on the everyday profile named by SOURCE_PROFILE (copied into
    the CDP data dir, not shared with it) and is left running so the next scrape
    attaches to a warm session.
    """
    profile = Path(profile_dir) if profile_dir else CDP_PROFILE_DIR
    # BU_CDP_SYNC_ON_LAUNCH re-copies the cookies every time we start cold. Off by
    # default because it also discards any login done inside the CDP window.
    always = os.environ.get("BU_CDP_SYNC_ON_LAUNCH", "").strip().lower() in ("1", "true", "yes", "on")
    if not SEED_ENABLED:
        profile.mkdir(parents=True, exist_ok=True)
        profile_dirname = UNSEEDED_PROFILE_DIRNAME
    elif reseed or always or not profile.exists():
        profile_dirname, _ = seed_profile(profile, source)
    else:
        profile_dirname = seeded_profile_dirname(profile)

    if port is None:
        port = next(
            (p for p in DEFAULT_CDP_PORTS if _endpoint_for_port("127.0.0.1", p) is None),
            LAUNCH_PORT,
        )

    # A leftover port file from the last run would satisfy the poll below before
    # the new Chrome has even bound its port.
    port_file = profile / "DevToolsActivePort"
    try:
        port_file.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass

    cmd = [
        _find_chrome(),
        f"--user-data-dir={profile}",
        f"--profile-directory={profile_dirname}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if endpoint := _endpoint_for_port("127.0.0.1", port):
            return endpoint
        if endpoint := _endpoint_from_port_file(port_file):
            return endpoint
        time.sleep(0.25)

    raise RuntimeError(
        f"launched Chrome on {profile} ({profile_dirname}) but no debug port appeared "
        f"on {port} within {timeout:.0f}s.\n"
        "Most likely a Chrome is already running on that data dir without "
        "--remote-debugging-port; close those windows and retry."
    )


def discover_cdp(cdp_url: Optional[str] = None, auto_launch: Optional[bool] = None) -> str:
    """Return a CDP endpoint (HTTP or WS) for connect_over_cdp.

    Priority:
      1. `cdp_url` argument
      2. BU_CDP_WS env var or .env  (WS URL, as written by browser-harness)
      3. BU_CDP_URL env var or .env (HTTP URL)
      4. A live DevToolsActivePort file in any known profile
      5. HTTP probe on ports 9222 / 9223 (skipping a Chrome we can see is running
         on someone else's user-data-dir, when we are free to launch our own)
      6. Launch a debuggable Chrome on the dedicated CDP profile

    `auto_launch` defaults to on, unless BU_CDP_AUTOLAUNCH says otherwise or
    there is no display to open a window on.
    """
    if cdp_url:
        return cdp_url

    env = {**_parse_env_file(), **os.environ}  # env vars win over .env file

    if ws := env.get("BU_CDP_WS"):
        return ws
    if url := env.get("BU_CDP_URL"):
        return url.rstrip("/")

    if auto_launch is None:
        auto_launch = env.get("BU_CDP_AUTOLAUNCH", "1").strip().lower() not in (
            "0", "false", "no", "off",
        )

    def ours(port: int) -> bool:
        """A debug port answering locally is not necessarily OUR browser.

        A Chrome opened for something else would silently hand the scrapers the
        wrong profile's session. When we can tell whose it is and are free to
        start our own, skip it; otherwise take what is there.
        """
        if not auto_launch:
            return True
        owner = _chrome_user_data_dir_on_port(port)
        return owner is None or owner == CDP_PROFILE_DIR

    # Chrome 147+ blocks /json/version; read DevToolsActivePort for the exact ws:// URL.
    if found := _read_devtools_active_port(accept=ours):
        return found

    # Probe localhost and, on WSL2 NAT mode, the Windows host IP.
    hosts = ["127.0.0.1"]
    if win_ip := _windows_host_ip():
        hosts.append(win_ip)

    for host in hosts:
        for port in DEFAULT_CDP_PORTS:
            if host == "127.0.0.1" and not ours(port):
                continue
            if endpoint := _endpoint_for_port(host, port):
                return endpoint

    if auto_launch and _has_display():
        return launch_chrome_cdp()

    why = "auto-launch disabled" if not auto_launch else "no DISPLAY/WAYLAND_DISPLAY to open a window on"
    raise RuntimeError(
        f"no debuggable Chrome found on ports {DEFAULT_CDP_PORTS} "
        f"(tried hosts: {', '.join(hosts)}) and {why}.\n"
        "Options:\n"
        "  1. python common/browser/cdp_discovery.py launch\n"
        "  2. Set BU_CDP_WS in .env (browser-harness does this automatically)\n"
        "  3. Pass cdp_url=<http://HOST:9222>\n"
        f"  4. google-chrome --user-data-dir={CDP_PROFILE_DIR} --remote-debugging-port=9222\n"
        "     (Chrome >= 136 refuses remote debugging on the default profile)"
    )


def _cmd_status(_args: argparse.Namespace) -> int:
    try:
        dirname = seeded_profile_dirname(CDP_PROFILE_DIR)
        display = list_profiles().get(dirname, "?")
        source = f"{dirname} ({display})" if SEED_ENABLED else f"{dirname} (unseeded: BU_CDP_SEED=0)"
    except RuntimeError as e:
        source = f"unresolved — {e}"
    print(f"CDP profile : {CDP_PROFILE_DIR}"
          f"{'' if CDP_PROFILE_DIR.exists() else '  (not created yet)'}")
    print(f"source      : {source}   [BU_CDP_SOURCE_PROFILE={SOURCE_PROFILE!r}]")
    for port in DEFAULT_CDP_PORTS:
        if endpoint := _endpoint_for_port("127.0.0.1", port):
            owner = _chrome_user_data_dir_on_port(port)
            whose = "ours" if owner == CDP_PROFILE_DIR else (str(owner) if owner else "unknown")
            print(f"LIVE   port {port}  [{whose}]  {endpoint}")
    # A port file only records which port some past Chrome asked for; it says
    # nothing about whether that Chrome, or this profile, is the one answering.
    for base in _profile_search_path():
        port, _ = _read_port_file(base / "DevToolsActivePort")
        if port is not None:
            state = "live" if _endpoint_for_port("127.0.0.1", port) else "dead"
            print(f"port-file   {base} -> port {port} ({state})")
    ours = next(
        (e for p in DEFAULT_CDP_PORTS
         if _chrome_user_data_dir_on_port(p) == CDP_PROFILE_DIR
         and (e := _endpoint_for_port("127.0.0.1", p))),
        None,
    )
    print()
    if ours:
        print(f"a scraper would use : {ours}")
    else:
        print("a scraper would     : launch Chrome on the CDP profile "
              "(or, with auto-launch off, attach to whatever is live)")
    try:
        print(f"attach-only would   : {discover_cdp(auto_launch=False)}")
    except RuntimeError as e:
        print(f"attach-only would   : fail — {e.args[0].splitlines()[0]}")
        return 0 if ours else 1
    return 0


def _cmd_launch(args: argparse.Namespace) -> int:
    if args.reseed:
        dirname, copied = seed_profile(CDP_PROFILE_DIR, args.profile)
        print(f"seeded {dirname}: {', '.join(copied) if copied else '(nothing)'}")
    print(launch_chrome_cdp(port=args.port, source=args.profile))
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    result = sync_cookies(source=args.profile, relaunch=not args.no_launch)
    if result["stopped"]:
        print(f"stopped Chrome: {', '.join(str(p) for p in result['stopped'])}")
    copied = result["copied"]
    print(f"synced {result['profile_dir']}: {', '.join(copied) if copied else '(nothing)'}")
    if result["endpoint"]:
        print(result["endpoint"])
    return 0


def _cmd_profiles(_args: argparse.Namespace) -> int:
    for dirname, display in sorted(list_profiles().items()):
        mark = " <- source" if display == SOURCE_PROFILE or dirname == SOURCE_PROFILE else ""
        print(f"{dirname:12} {display}{mark}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="show known CDP endpoints and liveness")
    p_status.set_defaults(func=_cmd_status)

    p_launch = sub.add_parser("launch", help="start a debuggable Chrome on the CDP profile")
    p_launch.add_argument("--reseed", action="store_true",
                          help="re-copy cookies/logins from the everyday Chrome profile first")
    p_launch.add_argument("--profile", default=None, metavar="NAME",
                          help=f"profile display or directory name (default: {SOURCE_PROFILE!r})")
    p_launch.add_argument("--port", type=int, default=None,
                          help="debug port (default: first free of 9222/9223)")
    p_launch.set_defaults(func=_cmd_launch)

    p_sync = sub.add_parser(
        "sync", help="re-copy the source profile's cookies into the CDP profile")
    p_sync.add_argument("--profile", default=None, metavar="NAME",
                        help=f"profile display or directory name (default: {SOURCE_PROFILE!r})")
    p_sync.add_argument("--no-launch", action="store_true",
                        help="stop and re-copy, but do not reopen the browser")
    p_sync.set_defaults(func=_cmd_sync)

    p_profiles = sub.add_parser("profiles", help="list your Chrome profiles and their names")
    p_profiles.set_defaults(func=_cmd_profiles)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
