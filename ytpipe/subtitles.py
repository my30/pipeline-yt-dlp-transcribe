"""Pick the right YouTube subtitle track and turn WebVTT into clean segments.

Track semantics in yt-dlp's info dict:
  * ``info["subtitles"]``           - uploaded by the creator (CC). Best quality.
  * ``info["automatic_captions"]``  - YouTube ASR **plus machine translations into ~100 languages**.
    The real ASR track is the one in the video's spoken language; yt-dlp also exposes it
    under an extra ``<lang>-orig`` key. Every other key is a Google-Translate of that ASR.

So ``--sub-langs "zh.*"`` on an English video gives you a machine translation of an English
ASR transcript, not Chinese speech recognition. We avoid that trap here.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .output import Segment

_SKIP_KEYS = {"live_chat", "rechat"}
# Preference order inside the zh family (Simplified first).
_ZH_ORDER = ["zh-Hans", "zh-CN", "zh", "zh-SG", "zh-Hant", "zh-TW", "zh-HK"]


@dataclass
class Track:
    key: str  # value passed to --sub-langs
    kind: str  # "manual" | "auto" | "auto-translated"
    lang: str
    warnings: list[str] = field(default_factory=list)

    def describe(self) -> str:
        label = {
            "manual": "creator-uploaded subtitles",
            "auto": "YouTube auto-generated captions (ASR, usually no punctuation)",
            "auto-translated": "auto captions MACHINE-TRANSLATED from another language",
        }[self.kind]
        return f"{label} [{self.key}]"


def _base(lang: str) -> str:
    return lang.split("-")[0].lower()


def _matches(key: str, want: str) -> bool:
    return _base(key) == _base(want)


def _rank(key: str, want: str) -> tuple[int, str]:
    if key == want:
        return (0, key)
    if _base(want) == "zh" and key in _ZH_ORDER:
        return (1 + _ZH_ORDER.index(key), key)
    return (50, key)


def original_language(info: dict) -> str | None:
    for key in info.get("automatic_captions") or {}:
        if key.endswith("-orig"):
            return key[: -len("-orig")]
    return info.get("language")


def pick_track(info: dict, want: str = "zh") -> Track | None:
    """Choose a subtitle track for spoken-language ``want`` ('auto' = video's own language)."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k not in _SKIP_KEYS and v}
    auto = {k: v for k, v in (info.get("automatic_captions") or {}).items() if v}
    orig = original_language(info)
    target = orig if want == "auto" else want

    if target:
        cands = sorted((k for k in manual if _matches(k, target)), key=lambda k: _rank(k, target))
        if cands:
            return Track(cands[0], "manual", cands[0])
    elif manual and want == "auto":
        key = sorted(manual)[0]
        return Track(key, "manual", key, ["Video language unknown; picked first uploaded track."])

    if orig and (want == "auto" or _matches(orig, want)):
        key = f"{orig}-orig" if f"{orig}-orig" in auto else orig
        if key in auto:
            return Track(key, "auto", orig)

    if target and orig and not _matches(orig, target):
        cands = sorted((k for k in auto if _matches(k, target) and not k.endswith("-orig")), key=lambda k: _rank(k, target))
        if cands:
            return Track(
                cands[0],
                "auto-translated",
                cands[0],
                [f"The video's spoken language looks like '{orig}', so this '{cands[0]}' track is a machine "
                 f"translation of its ASR. Local transcription in '{orig}' is usually more faithful."],
            )
    return None


# ---------------------------------------------------------------- WebVTT parsing

_TIME = r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
_CUE_RE = re.compile(rf"^{_TIME}\s*-->\s*{_TIME}")
_TAG_RE = re.compile(r"<[^>]+>")


def _secs(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text: str) -> list[Segment]:
    """Parse WebVTT into segments, collapsing YouTube's 'rolling' auto-caption duplicates.

    YouTube ASR VTT repeats the previous line at the top of every cue (karaoke-style),
    so a naive parse doubles every sentence. We emit each distinct line once, timed from
    the first cue where it appears to the last cue that still shows it.
    """
    segments: list[Segment] = []
    open_lines: dict[str, Segment] = {}
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    # Group into cues line-by-line (not by blank lines: YouTube cues may contain blank-ish lines).
    cues: list[tuple[float, float, list[str]]] = []
    for i, raw in enumerate(lines):
        m = _CUE_RE.match(raw.strip())
        if m:
            cues.append((_secs(*m.groups()[:4]), _secs(*m.groups()[4:]), []))
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not cues or _CUE_RE.match(nxt):  # header text, or a cue identifier line
            continue
        clean = html.unescape(_TAG_RE.sub("", raw)).strip()
        if clean:
            cues[-1][2].append(clean)
    for start, end, cue_lines in cues:
        still_open = {}
        for line in cue_lines:
            if line in open_lines:
                seg = open_lines[line]
                seg.end = max(seg.end, end)
            elif segments and segments[-1].text == line:
                seg = segments[-1]
                seg.end = max(seg.end, end)
            else:
                seg = Segment(start, end, line)
                segments.append(seg)
            still_open[line] = seg
        open_lines = still_open
    return segments
