"""Find which browsers on this machine actually have a cookie store yt-dlp can read."""

from __future__ import annotations

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
