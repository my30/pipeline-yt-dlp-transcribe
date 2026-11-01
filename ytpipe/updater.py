"""Keep the yt-dlp library current.

Why not ``yt-dlp -U``: yt-dlp refuses to self-update when installed with pip ("installed with a
package manager; use that to update"). We are a pip install inside a venv, so we update with
*this interpreter's* pip, which also upgrades yt-dlp-ejs (the YouTube JS-challenge solver) via the
``[default]`` extra. Because yt_dlp is already imported in this process, the program re-executes
itself afterwards so the new code is actually used.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "ytpipe" / "pypi-yt-dlp.json"
CHECK_EVERY = 24 * 3600  # query PyPI at most once a day
STALE_DAYS = 30  # warn (offline) when the installed release is older than this

# yt-dlp error fragments that usually mean "YouTube changed something; a newer yt-dlp fixes it".
# Deliberately NOT included: "Sign in to confirm you're not a bot", members-only / private errors -
# those are cookie / IP problems that an update does not fix.
BREAKAGE_HINTS = (
    "nsig extraction failed",
    "n challenge",
    "signature extraction failed",
    "unable to extract",
    "requested format is not available",
    "only images are available",
    "challenge solving failed",
    "http error 403",
    "please report this issue",
)


def installed_version() -> str:
    """pip's view of the version (nightlies carry a 'dev' suffix there, unlike yt_dlp.version)."""
    try:
        from importlib.metadata import version

        return version("yt-dlp")
    except Exception:
        from yt_dlp.version import __version__

        return __version__


def channel() -> str:
    try:
        from yt_dlp.version import CHANNEL

        if "nightly" in (CHANNEL or ""):
            return "nightly"
    except ImportError:
        pass
    return "nightly" if "dev" in installed_version() else "stable"


def release_date(version: str) -> dt.date | None:
    try:
        y, m, d = (int(x) for x in version.split(".")[:3])
        return dt.date(y, m, d)
    except (ValueError, TypeError):
        return None


def age_days(version: str | None = None) -> int | None:
    d = release_date(version or installed_version())
    return (dt.date.today() - d).days if d else None


def _vkey(v: str):
    try:
        from packaging.version import Version

        return Version(v)
    except Exception:
        return tuple(int(p) if p.isdigit() else 0 for p in v.replace(".dev", ".").split("."))


def latest_on_pypi(nightly: bool = False, use_cache: bool = True, timeout: float = 3.0) -> str | None:
    """Newest version on PyPI (stable or nightly pre-release). Cached for a day; None if offline."""
    data = None
    if use_cache and CACHE.exists() and time.time() - CACHE.stat().st_mtime < CHECK_EVERY:
        try:
            data = json.loads(CACHE.read_text())
        except Exception:
            data = None
    if data is None:
        try:
            with urllib.request.urlopen(PYPI_URL, timeout=timeout) as r:
                raw = json.load(r)
            data = {"stable": raw["info"]["version"],
                    "all": [v for v, files in raw["releases"].items() if files]}
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data))
        except Exception:
            return None
    if not nightly:
        return data["stable"]
    return max(data["all"], key=_vkey, default=None)


def is_newer(candidate: str | None, current: str) -> bool:
    return bool(candidate) and _vkey(candidate) > _vkey(current)


def startup_notice() -> str | None:
    """One-line nudge, or None. Never blocks for more than the PyPI timeout, never raises."""
    try:
        cur = installed_version()
        latest = latest_on_pypi(nightly=channel() == "nightly")
        if is_newer(latest, cur):
            return f"yt-dlp {latest} is available (you have {cur}). Type 'u' at the URL prompt or run: ytpipe --update"
        age = age_days(cur)
        if latest is None and age is not None and age > STALE_DAYS:
            return f"yt-dlp {cur} is {age} days old; YouTube breaks old versions. Consider: ytpipe --update"
    except Exception:
        pass
    return None


def looks_like_breakage(message: str) -> bool:
    m = message.lower()
    return any(h in m for h in BREAKAGE_HINTS)


def pip_command(nightly: bool, pin: str | None = None) -> list[str]:
    pkg = f"yt-dlp[default]=={pin}" if pin else "yt-dlp[default]"
    try:
        import pip  # noqa: F401

        cmd = [sys.executable, "-m", "pip", "install", "-q", "-U"]
    except ImportError:  # venvs created by `uv venv` have no pip
        uv = shutil.which("uv")
        if not uv:
            raise RuntimeError("Neither pip nor uv is available for this Python; cannot update yt-dlp.")
        cmd = [uv, "pip", "install", "-q", "--python", sys.executable, "-U"]
    if nightly:
        cmd.append("--pre")
    return cmd + [pkg]


def update(target: str | None = None) -> tuple[str, str]:
    """Upgrade yt-dlp in this interpreter's environment. Returns (old, new) versions.

    ``target``: 'stable' | 'nightly' | None (= stay on the currently installed channel).
    Going nightly -> stable needs an explicit pin, because pip never downgrades on -U.
    """
    old = installed_version()
    target = target or channel()
    nightly = target == "nightly"
    pin = None
    if not nightly and channel() == "nightly":
        pin = latest_on_pypi(nightly=False, use_cache=False)
        if not pin:
            raise RuntimeError("Can't reach PyPI to find the latest stable version.")
    cmd = pip_command(nightly, pin)
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    out = subprocess.run([sys.executable, "-c", "from importlib.metadata import version; print(version('yt-dlp'))"],
                         capture_output=True, text=True, check=True)
    new = out.stdout.strip()
    if new == old:
        print(f"yt-dlp is already the newest {target} version ({old}).")
    else:
        print(f"yt-dlp updated {old} -> {new}.  Roll back with:  {sys.executable} -m pip install 'yt-dlp[default]=={old}'")
    try:
        CACHE.unlink()
    except FileNotFoundError:
        pass
    return old, new


def restart(extra_args: list[str]) -> None:
    """Replace this process with a fresh one so the new yt_dlp code is imported."""
    argv = [sys.executable, "-m", "ytpipe", *extra_args]
    sys.stdout.flush()
    os.execv(sys.executable, argv)
