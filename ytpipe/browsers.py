"""Find which browsers on this machine actually have a cookie store yt-dlp can read."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_MAC = "~/Library/Application Support"
# yt-dlp browser name -> candidate profile roots (first existing wins)
_PATHS = {
    "darwin": {
        "chrome": [f"{_MAC}/Google/Chrome"],
        "safari": ["~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies",
                   "~/Library/Cookies/Cookies.binarycookies"],
        "firefox": [f"{_MAC}/Firefox/Profiles"],
        "brave": [f"{_MAC}/BraveSoftware/Brave-Browser"],
        "edge": [f"{_MAC}/Microsoft Edge"],
        "chromium": [f"{_MAC}/Chromium"],
        "vivaldi": [f"{_MAC}/Vivaldi"],
        "opera": [f"{_MAC}/com.operasoftware.Opera"],
    },
    "linux": {
        "chrome": ["~/.config/google-chrome"],
        "firefox": ["~/.mozilla/firefox", "~/snap/firefox/common/.mozilla/firefox"],
        "brave": ["~/.config/BraveSoftware/Brave-Browser"],
        "edge": ["~/.config/microsoft-edge"],
        "chromium": ["~/.config/chromium", "~/snap/chromium/common/chromium"],
        "vivaldi": ["~/.config/vivaldi"],
        "opera": ["~/.config/opera"],
    },
}

# Installed but NOT readable by yt-dlp's --cookies-from-browser (own keychain key / format).
_UNSUPPORTED_MAC = {"Arc": f"{_MAC}/Arc/User Data", "Orion": f"{_MAC}/Orion"}

BROWSER_HINTS = {
    "safari": "Safari: give your terminal app Full Disk Access (System Settings > Privacy & Security).",
    "chrome": "Chrome: allow the Keychain prompt ('Always Allow'). Non-default profile: chrome:'Profile 1'.",
}


def detect_browsers() -> list[str]:
    mac = sys.platform == "darwin"
    table = _PATHS["darwin" if mac else "linux"]
    found = [name for name, paths in table.items() if any(Path(p).expanduser().exists() for p in paths)]
    # Safari ships with every Mac, but its cookie file is invisible without Full Disk Access.
    if mac and "safari" not in found:
        found.append("safari")
    return found


def unsupported_installed() -> list[str]:
    if sys.platform != "darwin":
        return []
    return [name for name, p in _UNSUPPORTED_MAC.items() if Path(p).expanduser().exists()]


# ---------------------------------------------------------------- diagnosis after a failure

_CHROMIUM_FAMILY = {"chrome", "chromium", "brave", "edge", "vivaldi", "opera"}
_CHROME_VARIANTS_MAC = ["Google/Chrome Beta", "Google/Chrome Dev", "Google/Chrome Canary", "Google/Chrome for Testing"]


def _scan(root: Path) -> tuple[list[Path], list[str]]:
    """Find Cookies DBs under a Chromium user-data dir, *recording* permission errors
    (yt-dlp's os.walk silently skips them, which turns 'access denied' into 'not found')."""
    found, errors = [], []
    for cur, dirs, files in os.walk(root, onerror=lambda e: errors.append(f"{e.filename}: {e.strerror}")):
        dirs[:] = [d for d in dirs if d not in ("Cache", "Code Cache", "GPUCache", "Service Worker", "IndexedDB")]
        if "Cookies" in files:
            found.append(Path(cur) / "Cookies")
    return found, errors


def diagnose(browser: str | None) -> list[str]:
    """Human-readable findings + concrete fixes for a failed --cookies-from-browser."""
    name = (browser or "").split(":")[0].split("+")[0]
    if name not in _CHROMIUM_FAMILY or sys.platform != "darwin":
        return []
    root = Path(_PATHS["darwin"][name][0]).expanduser()
    out = []
    if not root.exists():
        out.append(f"{root} does not exist.")
        for v in _CHROME_VARIANTS_MAC if name == "chrome" else []:
            alt = Path(_MAC, v).expanduser()
            if alt.exists():
                cookies, _ = _scan(alt)
                if cookies:
                    out.append(f"Found {v}: try  --browser \"chrome:{alt}\"")
        return out
    try:
        next(root.iterdir(), None)
    except PermissionError:
        out.append(f"Permission denied reading {root} - macOS privacy protection is blocking your terminal.")
        out.append("Fix: System Settings > Privacy & Security > Full Disk Access > enable your terminal app "
                   "(Terminal / iTerm / VS Code / PyCharm), then quit and reopen it.")
        return out
    cookies, errors = _scan(root)
    if errors:
        out.append(f"{len(errors)} folder(s) could not be read, e.g. {errors[0]}")
        out.append("Fix: give your terminal app Full Disk Access (System Settings > Privacy & Security), then reopen it.")
    if cookies:
        profiles = sorted({(c.parent.parent if c.parent.name == "Network" else c.parent).name for c in cookies})
        out.append(f"Cookie databases found in profile(s): {', '.join(profiles)}.")
        out.append("If the member account is not in the most recently used one, pick it: "
                   + "  ".join(f"--browser \"{name}:{p}\"" for p in profiles))
    elif not errors:
        out.append(f"No 'Cookies' file anywhere under {root}. Open Chrome, visit youtube.com logged in, quit Chrome, retry.")
    return out
