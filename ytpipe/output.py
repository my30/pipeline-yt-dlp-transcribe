"""Transcript data model and writers (Markdown for AI analysis, SRT for timestamps)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_CJK = re.compile(r"[㐀-鿿豈-﫿　-〿＀-￯]")


@dataclass
class Segment:
    start: float  # seconds
    end: float
    text: str


def _ts(seconds: float, sep: str = ",") -> str:
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _hms(seconds: float) -> str:
    return _ts(seconds).split(",")[0]


def _join(a: str, b: str) -> str:
    """Join two text pieces; no space between CJK characters, a space otherwise."""
    if not a:
        return b
    if _CJK.match(a[-1]) or _CJK.match(b[:1] or " "):
        return a + b
    return f"{a} {b}"


def paragraphs(segments: list[Segment], gap: float = 2.0, max_chars: int = 400) -> list[tuple[float, str]]:
    """Group segments into paragraphs, breaking on silences or when a paragraph gets long."""
    out: list[tuple[float, str]] = []
    cur, cur_start, last_end = "", 0.0, None
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if cur and ((last_end is not None and seg.start - last_end >= gap) or len(cur) >= max_chars):
            out.append((cur_start, cur))
            cur = ""
        if not cur:
            cur_start = seg.start
        cur = _join(cur, text)
        last_end = seg.end
    if cur:
        out.append((cur_start, cur))
    return out


def write_srt(segments: list[Segment], path: Path) -> Path:
    lines = []
    for i, seg in enumerate((s for s in segments if s.text.strip()), 1):
        lines += [str(i), f"{_ts(seg.start)} --> {_ts(seg.end)}", seg.text.strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_markdown(segments: list[Segment], info: dict, source: str, path: Path, timestamps: bool = True) -> Path:
    """Markdown with a metadata header: convenient to paste/feed into an LLM."""
    date = info.get("upload_date") or ""
    if len(date) == 8:
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    meta = {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "url": info.get("webpage_url") or info.get("original_url"),
        "upload_date": date,
        "duration": _hms(info["duration"]) if info.get("duration") else None,
        "transcript_source": source,
    }
    head = ["---"] + [f"{k}: {v}" for k, v in meta.items() if v] + ["---", "", f"# {info.get('title', '')}", ""]
    has_times = any(s.end > 0 for s in segments)
    body = []
    for start, text in paragraphs(segments):
        body.append(f"[{_hms(start)}] {text}" if timestamps and has_times else text)
        body.append("")
    path.write_text("\n".join(head + body), encoding="utf-8")
    return path


_opencc = None


def to_simplified(segments: list[Segment]) -> tuple[list[Segment], bool]:
    """Convert Traditional -> Simplified Chinese if OpenCC is installed. Returns (segments, converted?)."""
    global _opencc
    if _opencc is None:
        try:
            import opencc  # type: ignore

            try:
                _opencc = opencc.OpenCC("t2s")
            except Exception:  # opencc-python-reimplemented wants 't2s', official wants 't2s.json'
                _opencc = opencc.OpenCC("t2s.json")
        except Exception:
            _opencc = False
    if not _opencc:
        return segments, False
    return [Segment(s.start, s.end, _opencc.convert(s.text)) for s in segments], True
