"""Interactive entry point: paste a URL, answer a few questions, get files."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from yt_dlp.cookies import CookieLoadError
from yt_dlp.utils import DownloadError, sanitize_filename

from . import __version__, prompts, updater
from .browsers import BROWSER_HINTS, detect_browsers, diagnose, unsupported_installed
from .downloader import AUDIO_FORMATS, AUDIO_QUALITIES, VIDEO_CONTAINERS, Downloader
from .output import DEFAULT_TEMPLATE, TEMPLATE_HELP, Segment, to_simplified, write_markdown, write_srt
from .subtitles import Track, original_language, parse_vtt, pick_track
from .transcribe import BACKENDS, WHISPER_SIZES, default_model, installed, recommendations, transcribe

DEFAULT_DIR = "~/Downloads/yt-dlp"
CONFIG_DIR = Path("~/.config/ytpipe").expanduser()
USER_TEMPLATE = CONFIG_DIR / "template.md"
CONFIG_FILE = CONFIG_DIR / "config.toml"
BUILTIN_TEMPLATES = Path(__file__).parent / "templates"
MODES = [
    ("download", "Download only (audio or video)"),
    ("transcribe", "Transcribe only (temporary audio is deleted afterwards)"),
    ("both", "Download + transcribe (keep the audio/video file)"),
]


def _resolution(value: str) -> str:
    v = value.lower().removesuffix("p")
    if v == "best" or v.isdigit():
        return v
    raise argparse.ArgumentTypeError("use 'best' or a height such as 1080")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ytpipe", description="Download YouTube media and/or transcribe it locally.")
    p.add_argument("url", nargs="*",
                   help="YouTube URL(s), or local audio/video file(s) to transcribe. Omit to be prompted (loop until 'q').")
    p.add_argument("--mode", choices=[m for m, _ in MODES], help="Skip the mode question.")
    p.add_argument("-d", "--dir", help=f"Output directory (default {DEFAULT_DIR}).")
    p.add_argument("--browser", default="auto",
                   help="Browser to read YouTube login cookies from (needed for members-only videos). "
                        "'auto' (default) detects installed browsers; or yt-dlp syntax e.g. safari, firefox, brave, "
                        "'chrome:Profile 1'; 'none' to disable.")
    p.add_argument("--cookies", help="Use a Netscape cookies.txt file instead of --browser.")
    dg = p.add_argument_group("download choices (each one skips a question)")
    dg.add_argument("--media", choices=["audio", "video"], help="Download audio or video (download/both modes).")
    dg.add_argument("--audio-format", choices=list(AUDIO_FORMATS),
                    help="original (no re-encode, default), m4a, mp3, opus, flac, wav. Implies --media audio.")
    dg.add_argument("--audio-quality", metavar="Q",
                    help="For lossy re-encodes: 0 (best VBR, default), 320K, 192K, 128K, ...")
    dg.add_argument("--video-format", choices=list(VIDEO_CONTAINERS),
                    help="Container: mp4 (default), mkv, webm. Implies --media video.")
    dg.add_argument("--resolution", type=_resolution, metavar="best|HEIGHT",
                    help="best, or a height like 2160 / 1080 / 720p (closest available is used). Implies --media video.")
    p.add_argument("--lang", help="Spoken language: en, zh, ja, ... or 'auto'. Default: ask (1=en, 2=zh).")
    p.add_argument("--backend", choices=list(BACKENDS), help="ASR backend (default: best installed for this machine).")
    p.add_argument("--model", help="ASR model name / HF repo (backend specific).")
    p.add_argument("--subs", choices=["ask", "prefer", "never"], default="ask",
                   help="Use YouTube subtitles when available instead of local ASR (default: ask).")
    p.add_argument("--no-timestamps", action="store_true", help="No [hh:mm:ss] paragraph stamps in the .md transcript.")
    md = p.add_argument_group("markdown output")
    md.add_argument("--frontmatter", choices=["suggest", "yaml", "none"], default="suggest",
                    help="suggest (default): generic Markdown + an Obsidian frontmatter code block to copy; "
                         "yaml: real frontmatter at the top; none.")
    md.add_argument("--md-template", metavar="FILE|NAME",
                    help=f"Your own Markdown template file, or a built-in name ({', '.join(builtin_templates())}). "
                         "Default: ~/.config/ytpipe/template.md if it exists. See --print-template.")
    md.add_argument("--md-dir", metavar="DIR",
                    help="Write the .md transcript here (e.g. your vault's inbox) instead of next to the media.")
    md.add_argument("--md-name", choices=["title-id", "title"], default="title-id",
                    help="Transcript file name: 'Title [id].md' (default) or 'Title.md' like Web Clipper "
                         "(falls back to adding [id] if that name is taken).")
    md.add_argument("--print-template", action="store_true",
                    help="Print the built-in template and its placeholders, then exit.")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Never prompt: unanswered questions take their defaults. Automatic when stdin is not a terminal.")
    ag = p.add_argument_group("scripting / agents")
    ag.add_argument("--info", action="store_true",
                    help="Print the video's metadata as JSON (languages, subtitle tracks, resolutions, ...) and exit; "
                         "downloads nothing.")
    ag.add_argument("--json", action="store_true",
                    help="stdout carries only one JSON result document; all progress goes to stderr.")
    ag.add_argument("--auto-update", action="store_true",
                    help="With -y: on a 'YouTube changed' error, update yt-dlp and retry without asking.")
    p.add_argument("--yt-dlp-arg", action="append", default=[], metavar="ARG",
                   help="Extra raw yt-dlp flag(s), repeatable, e.g. --yt-dlp-arg=--limit-rate=5M")
    g = p.add_argument_group("yt-dlp updates")
    g.add_argument("--update", action="store_true", help="Upgrade the yt-dlp library (+ yt-dlp-ejs) and exit.")
    g.add_argument("--channel", choices=["stable", "nightly"],
                   help="With --update: switch channel. Nightly gets YouTube fixes days earlier; stable is safer.")
    g.add_argument("--no-update-check", action="store_true", help="Don't check PyPI for a newer yt-dlp at startup.")
    p.add_argument("--resume-url", help=argparse.SUPPRESS)  # used internally after an update+restart
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def load_config(parser: argparse.ArgumentParser, path: Path = CONFIG_FILE) -> dict:
    """~/.config/ytpipe/config.toml: keys are long option names (dashes or underscores), CLI wins."""
    if not path.is_file():
        return {}
    try:
        import tomllib
    except ImportError:  # Python 3.10
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            print(f"NOTE: ignoring {path} (needs Python 3.11+ or `pip install tomli`)")
            return {}
    with path.open("rb") as f:
        raw = tomllib.load(f)
    known = {a.dest: a for a in parser._actions}
    cfg = {}
    for key, value in raw.items():
        dest = key.replace("-", "_")
        action = known.get(dest)
        if action is None or dest in ("url", "help", "version", "update", "resume_url", "print_template"):
            print(f"NOTE: unknown key '{key}' in {path}, ignored")
            continue
        if action.choices and value not in action.choices:
            print(f"NOTE: '{key} = {value!r}' in {path} must be one of {list(action.choices)}, ignored")
            continue
        cfg[dest] = value
    parser.set_defaults(**cfg)
    return cfg


def main(argv: list[str] | None = None) -> int:
    """Exit codes: 0 = every URL succeeded, 1 = at least one failed, 2 = bad command line."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    load_config(parser)
    args = parser.parse_intermixed_args(raw_argv)
    if not args.yes and not sys.stdin.isatty() and args.url:
        args.yes = True  # agent / pipe / cron: nobody can answer prompts
    prompts.ASSUME_DEFAULTS = args.yes
    results: list[dict] = []
    if not args.json:
        return _run(args, raw_argv, results)
    real_stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):  # yt-dlp & our logs -> stderr, stdout = JSON only
        try:
            code = _run(args, raw_argv, results)
        except Exception as e:
            code, results = 1, results + [{"status": "error", "error": f"{type(e).__name__}: {e}"}]
    payload = results if args.info else {"ok": code == 0, "results": results}
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=real_stdout)
    return code


def _run(args: argparse.Namespace, raw_argv: list[str], results: list[dict]) -> int:
    if args.print_template:
        print(load_template(args) or DEFAULT_TEMPLATE)
        print("<!--\n" + TEMPLATE_HELP + "\n-->")
        return 0
    load_template(args)  # fail now, not after a 20-minute transcription
    print(f"ytpipe {__version__} | yt-dlp {updater.installed_version()} ({updater.channel()})")
    if args.update:
        updater.update(args.channel)
        return 0
    if not (args.no_update_check or args.yes or os.environ.get("YTPIPE_NO_UPDATE_CHECK")):
        notice = updater.startup_notice()
        if notice:
            print(f"NOTE: {notice}")
    if not shutil.which("ffmpeg"):
        print("WARNING: ffmpeg not found - audio extraction/merging will fail. Install: brew install ffmpeg")
    if not shutil.which("deno"):
        print("NOTE: deno not found. Recent yt-dlp needs a JS runtime for YouTube. Install: brew install deno")

    if args.cookies:
        browser = None
    elif (args.browser or "").lower() == "auto":
        browser = auto_browser()
    else:
        browser = None if (args.browser or "").lower() == "none" else args.browser
    dl = Downloader(browser=browser, cookies_file=args.cookies, extra_args=args.yt_dlp_arg)

    if args.info:
        if not args.url:
            print("--info needs at least one URL")
            return 2
        failed = False
        for url in args.url:
            try:
                results.append(info_summary(dl.fetch_info(url)))
            except Exception as e:
                failed = True
                results.append({"url": url, "status": "error", "error": str(e)})
        if not args.json:
            print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
        return 1 if failed else 0

    urls = list(args.url)
    interactive = not urls
    pending = args.resume_url
    while True:
        if pending:
            url, pending = pending, None
        elif interactive:
            try:
                url = input("\nYouTube URL (q to quit, u to update yt-dlp): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return exit_code(results)
            if url.lower() in ("q", "quit", "exit", ""):
                return exit_code(results)
            if url.lower() in ("u", "update"):
                old, new = updater.update()
                if new != old:
                    print("Restarting with the new yt-dlp ...")
                    updater.restart(restart_args(raw_argv, args, []))
                continue
        elif urls:
            url = urls.pop(0)
        else:
            return exit_code(results)
        result = {"url": url, "status": "error"}
        results.append(result)
        try:
            while True:
                try:
                    process(url, dl, args, result)
                    result["status"] = "ok"
                    break
                except CookieLoadError as e:
                    print(f"\nCould not load cookies from {dl.cookie_source}: {e}")
                    new = recover_cookies(dl, args)
                    if new is None:
                        result["error"] = f"CookieLoadError: {e}"
                        break
                    dl = new
        except KeyboardInterrupt:
            print("\nCancelled.")
            result["error"] = "cancelled"
        except DownloadError as e:
            print(f"\nyt-dlp error: {e}")
            result["error"] = str(e)
            if updater.looks_like_breakage(str(e)) and offer_update_and_retry(url, urls, raw_argv, args):
                continue
            if "members" in str(e).lower() or "sign in" in str(e).lower() or "join this channel" in str(e).lower():
                print(f"Hint: log in to YouTube (with the member account) in the browser used for cookies "
                      f"(currently {dl.cookie_source}), or restart with --browser <name> / --cookies cookies.txt.")
        except Exception as e:  # keep the loop alive for the next URL
            print(f"\nError: {type(e).__name__}: {e}")
            result["error"] = f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------- updates

def restart_args(raw_argv: list[str], args: argparse.Namespace, remaining_urls: list[str], retry: str | None = None) -> list[str]:
    """Original options (minus URLs / one-shot flags) + what is still to do."""
    drop = set(args.url) | {"--update"}
    out, skip = [], False
    for tok in raw_argv:
        if skip:
            skip = False
            continue
        if tok in ("--resume-url", "--channel"):
            skip = True
            continue
        if tok in drop or tok.startswith(("--resume-url=", "--channel=")):
            continue
        out.append(tok)
    if retry:
        out += ["--resume-url", retry]
    return out + remaining_urls


def offer_update_and_retry(url: str, remaining: list[str], raw_argv: list[str], args: argparse.Namespace) -> bool:
    if prompts.ASSUME_DEFAULTS and not args.auto_update:
        print("Looks like yt-dlp may be outdated. Re-run with --auto-update, or run: ytpipe --update")
        return False
    cur = updater.installed_version()
    latest = updater.latest_on_pypi(nightly=updater.channel() == "nightly", use_cache=False)
    if latest and not updater.is_newer(latest, cur):
        nightly = updater.latest_on_pypi(nightly=True)
        print(f"This looks like YouTube changed something. You already have the latest {updater.channel()} yt-dlp ({cur}).")
        if updater.channel() == "stable" and updater.is_newer(nightly, cur) and \
                prompts.confirm(f"Try the nightly build {nightly}? (fixes often land there first)", False):
            updater.update("nightly")
        else:
            print("Check https://github.com/yt-dlp/yt-dlp/issues for this error; a fix usually lands within days.")
            return False
    else:
        newer = f" ({latest} is available)" if latest else ""
        if not prompts.confirm(f"This often means yt-dlp is out of date{newer}. Update yt-dlp and retry?", True):
            return False
        old, new = updater.update()
        if new == old:
            return False
    print("Restarting with the new yt-dlp ...")
    updater.restart(restart_args(raw_argv, args, remaining, retry=url))
    return True  # not reached


# ---------------------------------------------------------------------------- cookies

def auto_browser() -> str | None:
    found = detect_browsers()
    for name in unsupported_installed():
        print(f"NOTE: {name} is installed but yt-dlp cannot read its cookies; "
              "export a cookies.txt from it and use --cookies (see README).")
    if not found:
        print("NOTE: no supported browser found - continuing without cookies (public videos only).")
        return None
    if len(found) == 1:
        print(f"Using cookies from {found[0]}.")
        return found[0]
    pick = prompts.choose("Which browser are you logged in to YouTube with?",
                          [(b, b) for b in found] + [("none", "No cookies (public videos only)")], found[0])
    return None if pick == "none" else pick


def recover_cookies(dl: Downloader, args: argparse.Namespace) -> Downloader | None:
    """After a CookieLoadError: let the user pick another source and retry."""
    findings = diagnose(dl.browser)
    for line in findings:
        print(f"  > {line}")
    hint = BROWSER_HINTS.get((dl.browser or "").split(":")[0])
    if hint and not findings:
        print(f"  {hint}")
    if prompts.ASSUME_DEFAULTS:
        return None
    others = [b for b in detect_browsers() if b != dl.browser]
    opts = ([("retry", f"Retry {dl.cookie_source} (after fixing permissions)")] if dl.browser else []) \
        + [(b, f"Use {b}") for b in others] \
        + [("file", "Use a cookies.txt file"), ("none", "Continue without cookies (public videos only)"), ("skip", "Skip this URL")]
    pick = prompts.choose("How should I get YouTube cookies?", opts, opts[0][0])
    if pick == "skip":
        return None
    if pick == "retry":
        return Downloader(browser=dl.browser, extra_args=args.yt_dlp_arg)
    if pick == "file":
        path = Path(prompts.ask("Path to cookies.txt")).expanduser()
        return Downloader(browser=None, cookies_file=str(path), extra_args=args.yt_dlp_arg)
    return Downloader(browser=None if pick == "none" else pick, extra_args=args.yt_dlp_arg)


# ---------------------------------------------------------------------------- one URL

def process(url: str, dl: Downloader, args: argparse.Namespace, result: dict | None = None) -> dict:
    result = {} if result is None else result
    local = Path(url).expanduser()
    if local.is_file():
        return process_local_file(local, args, result)
    print("Fetching video info ...")
    info = dl.fetch_info(url)
    result.update(id=info.get("id"), title=info.get("title"))
    if info.get("_type") == "playlist":
        raise RuntimeError("Playlists aren't supported yet; pass a single video URL.")
    dur = info.get("duration")
    print(f"\n  {info.get('title')}\n  {info.get('channel') or info.get('uploader')}"
          + (f" | {fmt_duration(dur)}" if dur else "")
          + (f" | {info['availability']}" if info.get("availability") not in (None, "public") else ""))

    mode = args.mode or prompts.choose("\nWhat do you want to do?", MODES, "transcribe")
    result["mode"] = mode

    # ---- download choices
    media = audio_fmt = quality = container = None
    height = None
    if mode in ("download", "both"):
        media = implied_media(args) or prompts.choose(
            "\nDownload audio or video?", [("audio", "Audio"), ("video", "Video")], "audio")
        if media == "audio":
            audio_fmt = args.audio_format or prompts.choose(
                "Audio format?", [(k, v[0]) for k, v in AUDIO_FORMATS.items()], "original")
            quality = "0"
            if AUDIO_FORMATS[audio_fmt][2]:
                quality = args.audio_quality or prompts.choose("Audio quality?", AUDIO_QUALITIES, "0")
        else:
            container = args.video_format or prompts.choose("Video container?", list(VIDEO_CONTAINERS.items()), "mp4")
            heights = Downloader.available_heights(info)
            if args.resolution:
                pick = args.resolution
                if pick != "best" and heights and int(pick) not in heights:
                    print(f"NOTE: {pick}p not offered (have {', '.join(map(str, heights))}); yt-dlp picks the closest.")
            else:
                opts = [("best", "Best available")] + [(str(h), f"{h}p") for h in heights]
                pick = prompts.choose("Resolution?", opts, "1080" if 1080 in heights else "best")
            height = None if pick == "best" else int(pick)

    # ---- transcription choices
    track: Track | None = None
    backend = model = None
    lang = args.lang or "zh"
    if mode in ("transcribe", "both"):
        lang = args.lang or choose_language(info)
        track = choose_subtitle_track(info, lang, args.subs)
        if track is None:
            backend, model = choose_asr(lang, args)

    outdir = Path(args.dir or prompts.ask("\nSave to directory", DEFAULT_DIR)).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- execute
    media_path = None
    if mode in ("download", "both"):
        if media == "audio":
            media_path = dl.download_audio(url, outdir, audio_fmt, quality)
        else:
            media_path = dl.download_video(url, outdir, height, container)
        print(f"\nSaved: {media_path}")
        result["media"] = str(media_path)
        if mode == "download":
            return result

    stem = sanitize_filename(f"{info.get('title', 'video')[:150]} [{info['id']}]")
    if track is not None:
        segments, source = from_subtitles(dl, url, track)
    elif media_path is not None:
        segments, source = transcribe(media_path, backend, model, lang), f"{backend}:{model}"
    else:
        segments, source = transcribe_temp_audio(dl, url, outdir, backend, model, lang)

    if lang.startswith("zh"):
        segments, converted = to_simplified(segments)
        if not converted and track is None and backend in WHISPER_SIZES:
            print("Tip: pip install opencc-python-reimplemented  to force Simplified Chinese output.")

    md = write_markdown(segments, info, source, transcript_path(info, stem, outdir, args), language=lang,
                        timestamps=not args.no_timestamps, template=load_template(args),
                        frontmatter=args.frontmatter)
    print(f"\nTranscript: {md}")
    result.update(transcript=str(md), source=source, language=lang)
    if any(s.end > 0 for s in segments):
        srt = write_srt(segments, outdir / f"{stem}.srt")
        print(f"Subtitles:  {srt}")
        result["srt"] = str(srt)
    return result


def process_local_file(path: Path, args: argparse.Namespace, result: dict) -> dict:
    """Transcribe an audio/video file that is already on disk (e.g. audio kept after a failed run)."""
    if args.mode == "download":
        raise RuntimeError("A local file can only be transcribed (--mode transcribe).")
    path = path.resolve()
    info = {"id": path.stem, "title": re.sub(r"\s*\[[\w-]{11}\]$", "", path.stem), "webpage_url": str(path)}
    result.update(id=info["id"], title=info["title"], mode="transcribe", media=str(path))
    lang = args.lang or choose_language({})
    backend, model = choose_asr(lang, args)
    outdir = Path(args.dir).expanduser().resolve() if args.dir else path.parent
    outdir.mkdir(parents=True, exist_ok=True)
    segments, source = transcribe(path, backend, model, lang), f"{backend}:{model}"
    if lang.startswith("zh"):
        segments, _ = to_simplified(segments)
    md = write_markdown(segments, info, source, transcript_path(info, path.stem, outdir, args), language=lang,
                        timestamps=not args.no_timestamps, template=load_template(args), frontmatter=args.frontmatter)
    print(f"\nTranscript: {md}")
    result.update(transcript=str(md), source=source, language=lang)
    if any(s.end > 0 for s in segments):
        srt = write_srt(segments, outdir / f"{path.stem}.srt")
        print(f"Subtitles:  {srt}")
        result["srt"] = str(srt)
    return result


def exit_code(results: list[dict]) -> int:
    return 1 if any(r.get("status") != "ok" for r in results) else 0


def implied_media(args: argparse.Namespace) -> str | None:
    if args.media:
        return args.media
    if args.video_format or args.resolution:
        return "video"
    if args.audio_format or args.audio_quality:
        return "audio"
    return None


def info_summary(info: dict) -> dict:
    """What an agent needs to decide on flags, without downloading anything."""
    track = pick_track(info, "auto")
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "url": info.get("webpage_url"),
        "duration_seconds": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "availability": info.get("availability"),
        "is_live": info.get("is_live"),
        "spoken_language": original_language(info),
        "manual_subtitles": sorted(k for k in (info.get("subtitles") or {}) if k != "live_chat"),
        "auto_caption_original": [k for k in (info.get("automatic_captions") or {}) if k.endswith("-orig")],
        "best_subtitle_track": {"key": track.key, "kind": track.kind} if track else None,
        "video_heights": Downloader.available_heights(info),
        "has_audio": any(f.get("acodec") not in (None, "none") for f in info.get("formats") or []),
    }


LANGS = [("en", "English"), ("zh", "中文 (普通话)"), ("auto", "Auto-detect")]


def choose_language(info: dict) -> str:
    orig = (original_language(info) or "").split("-")[0].lower()
    default = orig if orig in ("en", "zh") else ("auto" if orig else "zh")
    if orig:
        print(f"\nYouTube reports the spoken language as '{original_language(info)}'.")
    return prompts.choose("Spoken language?", LANGS, default,
                          free_text="or type a code: ja, ko, yue (粤语), fr, de, ...").strip().lower()


def choose_asr(lang: str, args: argparse.Namespace) -> tuple[str, str]:
    ranked = recommendations(lang)
    if args.backend:
        backend = args.backend
    else:
        default = next((b for b, _ in ranked if installed(b)), ranked[0][0])
        opts = []
        for b, note in ranked:
            missing = "" if installed(b) else f"   [not installed: {BACKENDS[b][2]}]"
            opts.append((b, f"{b:<18} {note}{missing}"))
        backend = prompts.choose(f"\nTranscription engine for '{lang}'?", opts, default)
    if not installed(backend):
        raise RuntimeError(f"Backend '{backend}' not installed. Run: {BACKENDS[backend][2]}")
    if args.model:
        return backend, args.model
    if backend in WHISPER_SIZES:
        sizes = WHISPER_SIZES[backend]
        default = sizes[1][0] if lang.startswith("yue") else sizes[0][0]
        return backend, prompts.choose("Whisper model size?", sizes, default)
    return backend, default_model(backend)


def fmt_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def transcript_path(info: dict, stem: str, outdir: Path, args: argparse.Namespace) -> Path:
    folder = Path(args.md_dir).expanduser() if args.md_dir else outdir
    folder.mkdir(parents=True, exist_ok=True)
    if args.md_name == "title":
        # Obsidian can't link to names containing # ^ [ ] |  (Web Clipper strips them as well)
        name = re.sub(r"[#^\[\]|]", "", sanitize_filename(info.get("title") or info["id"])).strip()[:150] or info["id"]
        target = folder / f"{name}.md"
        # Free, or a previous transcript of this same video (re-run) -> use it; else disambiguate.
        if not target.exists() or info["id"] in target.read_text(encoding="utf-8", errors="ignore"):
            return target
    return folder / f"{stem}.md"


def builtin_templates() -> list[str]:
    return sorted(p.stem for p in BUILTIN_TEMPLATES.glob("*.md"))


def load_template(args: argparse.Namespace) -> str | None:
    path = Path(args.md_template).expanduser() if args.md_template else USER_TEMPLATE
    if args.md_template and not path.is_file() and (BUILTIN_TEMPLATES / f"{args.md_template}.md").is_file():
        path = BUILTIN_TEMPLATES / f"{args.md_template}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    if args.md_template:
        raise FileNotFoundError(f"Template not found: {path}")
    return None


def choose_subtitle_track(info: dict, lang: str, policy: str) -> Track | None:
    if policy == "never":
        return None
    track = pick_track(info, lang)
    if track is None:
        print("No usable YouTube subtitles for this language -> local transcription.")
        return None
    print(f"\nFound {track.describe()}")
    for w in track.warnings:
        print(f"  ! {w}")
    if policy == "prefer" and track.kind != "auto-translated":
        return track
    default = track.kind != "auto-translated"
    hint = "" if track.kind == "manual" else " (local ASR is slower but adds punctuation and is often more accurate)"
    return track if prompts.confirm(f"Use these subtitles instead of local transcription?{hint}", default) else None


def from_subtitles(dl: Downloader, url: str, track: Track) -> tuple[list[Segment], str]:
    with tempfile.TemporaryDirectory(prefix="ytpipe-subs-") as tmp:
        vtt = dl.download_subtitle(url, Path(tmp), track.key, auto=track.kind != "manual")
        segments = parse_vtt(vtt.read_text(encoding="utf-8"))
    if not segments:
        raise RuntimeError("Subtitle file was empty")
    return segments, f"youtube-{track.kind}-subs:{track.key}"


def transcribe_temp_audio(dl: Downloader, url: str, outdir: Path, backend: str, model: str, lang: str):
    """Download audio into a scratch folder, transcribe, and delete it.

    The audio is deleted only on success: if the ASR step crashes on a 2-hour video you
    don't want to download it again. The leftover path is printed so you can rerun on it.
    """
    tmp = Path(tempfile.mkdtemp(prefix=".ytpipe-tmp-", dir=outdir))
    try:
        audio = dl.download_audio(url, tmp, "original")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:
        segments = transcribe(audio, backend, model, lang)
    except BaseException:
        print(f"\nTranscription failed; audio kept at: {audio}\n"
              f"Retry without re-downloading:  ytpipe --mode transcribe \"{audio}\"")
        raise
    shutil.rmtree(tmp, ignore_errors=True)
    print("Temporary audio removed.")
    return segments, f"{backend}:{model}"


if __name__ == "__main__":
    sys.exit(main())
