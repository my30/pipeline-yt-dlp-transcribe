"""Interactive entry point: paste a URL, answer a few questions, get files."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from yt_dlp.cookies import CookieLoadError
from yt_dlp.utils import DownloadError, sanitize_filename

from . import __version__, prompts, updater
from .browsers import BROWSER_HINTS, detect_browsers, diagnose, unsupported_installed
from .downloader import AUDIO_FORMATS, AUDIO_QUALITIES, VIDEO_CONTAINERS, Downloader
from .output import Segment, to_simplified, write_markdown, write_srt
from .subtitles import Track, original_language, parse_vtt, pick_track
from .transcribe import BACKENDS, WHISPER_SIZES, default_model, installed, recommendations, transcribe

DEFAULT_DIR = "~/Downloads/yt-dlp"
MODES = [
    ("download", "Download only (audio or video)"),
    ("transcribe", "Transcribe only (temporary audio is deleted afterwards)"),
    ("both", "Download + transcribe (keep the audio/video file)"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ytpipe", description="Download YouTube media and/or transcribe it locally.")
    p.add_argument("url", nargs="*", help="YouTube URL(s). Omit to be prompted (loop until 'q').")
    p.add_argument("--mode", choices=[m for m, _ in MODES], help="Skip the mode question.")
    p.add_argument("-d", "--dir", help=f"Output directory (default {DEFAULT_DIR}).")
    p.add_argument("--browser", default="auto",
                   help="Browser to read YouTube login cookies from (needed for members-only videos). "
                        "'auto' (default) detects installed browsers; or yt-dlp syntax e.g. safari, firefox, brave, "
                        "'chrome:Profile 1'; 'none' to disable.")
    p.add_argument("--cookies", help="Use a Netscape cookies.txt file instead of --browser.")
    p.add_argument("--lang", help="Spoken language: en, zh, ja, ... or 'auto'. Default: ask (1=en, 2=zh).")
    p.add_argument("--backend", choices=list(BACKENDS), help="ASR backend (default: best installed for this machine).")
    p.add_argument("--model", help="ASR model name / HF repo (backend specific).")
    p.add_argument("--subs", choices=["ask", "prefer", "never"], default="ask",
                   help="Use YouTube subtitles when available instead of local ASR (default: ask).")
    p.add_argument("--no-timestamps", action="store_true", help="No [hh:mm:ss] paragraph stamps in the .md transcript.")
    p.add_argument("-y", "--yes", action="store_true", help="Accept every default without prompting.")
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


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_intermixed_args(raw_argv)
    prompts.ASSUME_DEFAULTS = args.yes
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
                return 0
            if url.lower() in ("q", "quit", "exit", ""):
                return 0
            if url.lower() in ("u", "update"):
                old, new = updater.update()
                if new != old:
                    print("Restarting with the new yt-dlp ...")
                    updater.restart(restart_args(raw_argv, args, []))
                continue
        elif urls:
            url = urls.pop(0)
        else:
            return 0
        try:
            while True:
                try:
                    process(url, dl, args)
                    break
                except CookieLoadError as e:
                    print(f"\nCould not load cookies from {dl.cookie_source}: {e}")
                    new = recover_cookies(dl, args)
                    if new is None:
                        break
                    dl = new
        except KeyboardInterrupt:
            print("\nCancelled.")
        except DownloadError as e:
            print(f"\nyt-dlp error: {e}")
            if updater.looks_like_breakage(str(e)) and offer_update_and_retry(url, urls, raw_argv, args):
                continue
            if "members" in str(e).lower() or "sign in" in str(e).lower() or "join this channel" in str(e).lower():
                print(f"Hint: log in to YouTube (with the member account) in the browser used for cookies "
                      f"(currently {dl.cookie_source}), or restart with --browser <name> / --cookies cookies.txt.")
        except Exception as e:  # keep the loop alive for the next URL
            print(f"\nError: {type(e).__name__}: {e}")


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

def process(url: str, dl: Downloader, args: argparse.Namespace) -> None:
    print("Fetching video info ...")
    info = dl.fetch_info(url)
    if info.get("_type") == "playlist":
        raise RuntimeError("Playlists aren't supported yet; pass a single video URL.")
    dur = info.get("duration")
    print(f"\n  {info.get('title')}\n  {info.get('channel') or info.get('uploader')}"
          + (f" | {int(dur // 60)}m{int(dur % 60):02d}s" if dur else "")
          + (f" | {info['availability']}" if info.get("availability") not in (None, "public") else ""))

    mode = args.mode or prompts.choose("\nWhat do you want to do?", MODES, "transcribe")

    # ---- download choices
    media = audio_fmt = quality = container = None
    height = None
    if mode in ("download", "both"):
        media = prompts.choose("\nDownload audio or video?", [("audio", "Audio"), ("video", "Video")], "audio")
        if media == "audio":
            audio_fmt = prompts.choose("Audio format?", [(k, v[0]) for k, v in AUDIO_FORMATS.items()], "original")
            quality = "0"
            if AUDIO_FORMATS[audio_fmt][2]:
                quality = prompts.choose("Audio quality?", AUDIO_QUALITIES, "0")
        else:
            container = prompts.choose("Video container?", list(VIDEO_CONTAINERS.items()), "mp4")
            heights = Downloader.available_heights(info)
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
        if mode == "download":
            return

    stem = sanitize_filename(f"{info.get('title', 'video')[:150]} [{info['id']}]")
    if track is not None:
        segments, source = from_subtitles(dl, url, track)
    elif media_path is not None:
        segments, source = transcribe(media_path, backend, model, lang), f"{backend}:{model}"
    else:
        segments, source = transcribe_temp_audio(dl, url, outdir, backend, model, lang)

    if lang.startswith("zh"):
        segments, converted = to_simplified(segments)
        if not converted and track is None:
            print("Tip: pip install opencc-python-reimplemented  to force Simplified Chinese output.")

    md = write_markdown(segments, info, source, outdir / f"{stem}.md", timestamps=not args.no_timestamps)
    print(f"\nTranscript: {md}")
    if any(s.end > 0 for s in segments):
        print(f"Subtitles:  {write_srt(segments, outdir / f'{stem}.srt')}")


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
        print(f"\nTranscription failed; audio kept at: {audio}")
        raise
    shutil.rmtree(tmp, ignore_errors=True)
    print("Temporary audio removed.")
    return segments, f"{backend}:{model}"


if __name__ == "__main__":
    sys.exit(main())
