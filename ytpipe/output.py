"""Transcript data model and writers (Markdown for AI analysis, SRT for timestamps)."""

from __future__ import annotations

import datetime as _dt
import json
import re
from string import Template
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


DEFAULT_TEMPLATE = """# ${title}

${metadata_table}

## Transcript

${transcript}

${frontmatter_suggestion}
"""

TEMPLATE_HELP = """Placeholders (string.Template syntax, unknown ones are left untouched):
  ${title} ${channel} ${channel_url} ${url} ${id} ${upload_date} ${duration} ${duration_seconds}
  ${source} ${language} ${created} ${created_datetime} ${tags} ${description} ${description_short}
  ${author} ${author_wikilink}  (author = channel name; wikilink = [[Channel]])
  ${KEY_q}                    any of the above as a quoted, YAML-safe value - use these inside frontmatter,
                              e.g.  Title: ${title_q}   (titles with ':' or '#' would otherwise break YAML)
  ${transcript}               the paragraphs (with [hh:mm:ss] stamps unless --no-timestamps)
  ${metadata_table}           the Channel/URL/... table from the default template
  ${frontmatter_yaml}         a ready '---' YAML block (values safely quoted)
  ${frontmatter_suggestion}   the same YAML inside a fenced code block, with a heading
Write $$ for a literal dollar sign."""


def _yaml_scalar(v) -> str:
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_yaml_scalar(x) for x in v) + "]"
    s = str(v)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):  # bare ISO date -> YAML/Obsidian date type
        return s
    return json.dumps(s, ensure_ascii=False)  # JSON strings are valid YAML; safe for ':' '#' quotes


def metadata(info: dict, source: str, language: str | None = None) -> dict:
    date = info.get("upload_date") or ""
    if len(date) == 8:
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    dur = info.get("duration")
    return {
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "channel_url": info.get("channel_url") or info.get("uploader_url") or "",
        "url": info.get("webpage_url") or info.get("original_url") or "",
        "id": info.get("id") or "",
        "upload_date": date,
        "duration": _hms(dur) if dur else "",
        "duration_seconds": str(int(dur)) if dur else "",
        "source": source,
        "language": language or "",
        "created": _dt.date.today().isoformat(),
        "created_datetime": _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),  # local time, like Web Clipper
        "author": info.get("channel") or info.get("uploader") or "",
        "author_wikilink": _wikilink(info.get("channel") or info.get("uploader") or ""),
        "tags": ", ".join(info.get("tags") or []),
        "description": (info.get("description") or "").strip(),
        "description_short": _short(info.get("description") or ""),
    }


def _wikilink(name: str) -> str:
    # Obsidian link targets can't contain these; Web Clipper strips them too.
    clean = re.sub(r"[\[\]|#^]", "", name).strip()
    return f"[[{clean}]]" if clean else ""


def _short(text: str, limit: int = 200) -> str:
    """One-line summary ~ what a page's meta description holds (YouTube: start of the description)."""
    one = re.sub(r"\s+", " ", text).strip()
    return one if len(one) <= limit else one[:limit].rstrip() + "…"


_NOT_QUOTED = {"transcript", "metadata_table", "frontmatter_yaml", "frontmatter_suggestion"}


def _add_yaml_quoted(meta: dict) -> None:
    """For every value also offer ${key_q}: the same value as a safe YAML scalar ('' -> "")."""
    for k, v in list(meta.items()):
        if k not in _NOT_QUOTED and isinstance(v, str):
            meta[f"{k}_q"] = _yaml_scalar(v) if v else '""'


def frontmatter_yaml(meta: dict) -> str:
    fields = {
        "title": meta["title"],
        "channel": meta["channel"],
        "url": meta["url"],
        "video_id": meta["id"],
        "upload_date": meta["upload_date"],
        "duration": meta["duration"],
        "transcript_source": meta["source"],
        "language": meta["language"],
        "created": meta["created"],
        "tags": ["youtube", "transcript"],
    }
    lines = [f"{k}: {_yaml_scalar(v)}" for k, v in fields.items() if v]
    return "\n".join(["---", *lines, "---"])


def _cell(v: str) -> str:
    return (v or "-").replace("|", "\\|").replace("\n", " ")


def render_markdown(segments: list[Segment], info: dict, source: str, *, language: str | None = None,
                    timestamps: bool = True, template: str | None = None, frontmatter: str = "suggest") -> str:
    """frontmatter: 'suggest' (code block to copy), 'yaml' (real frontmatter at the top), 'none'."""
    meta = metadata(info, source, language)
    has_times = any(s.end > 0 for s in segments)
    meta["transcript"] = "\n\n".join(
        f"[{_hms(start)}] {text}" if timestamps and has_times else text for start, text in paragraphs(segments))
    rows = [("Channel", meta["channel"]), ("URL", meta["url"]), ("Uploaded", meta["upload_date"]),
            ("Duration", meta["duration"]), ("Transcript source", meta["source"]), ("Transcribed", meta["created"])]
    meta["metadata_table"] = "\n".join(["| | |", "|---|---|", *(f"| {k} | {_cell(v)} |" for k, v in rows)])
    yaml_block = frontmatter_yaml(meta)
    meta["frontmatter_yaml"] = yaml_block if frontmatter != "none" else ""
    _add_yaml_quoted(meta)
    meta["frontmatter_suggestion"] = (
        f"---\n\n## Suggested frontmatter (Obsidian)\n\nCopy to the very top of the note if you want it:\n\n```yaml\n{yaml_block}\n```"
        if frontmatter == "suggest" else "")
    tpl = template if template is not None else DEFAULT_TEMPLATE
    out = Template(tpl).safe_substitute(meta)
    if frontmatter == "yaml" and "${frontmatter_yaml}" not in tpl:
        out = yaml_block + "\n\n" + out
    return re.sub(r"\n{3,}", "\n\n", out).rstrip() + "\n"


def write_markdown(segments: list[Segment], info: dict, source: str, path: Path, **kw) -> Path:
    path.write_text(render_markdown(segments, info, source, **kw), encoding="utf-8")
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
