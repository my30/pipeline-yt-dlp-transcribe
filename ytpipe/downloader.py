"""Thin wrapper over the yt-dlp Python API.

Options are expressed as ordinary yt-dlp CLI flags and converted with ``yt_dlp.parse_options``,
so every call here maps 1:1 to a ``yt-dlp ...`` command you could run by hand, and we don't
depend on yt-dlp's (less stable) internal option dict names.
"""

from __future__ import annotations

from pathlib import Path

import yt_dlp

OUTTMPL = "%(title).150B [%(id)s].%(ext)s"

AUDIO_FORMATS = {
    # value: (label, extra yt-dlp args, lossy re-encode?)
    "original": ("Original stream, no re-encode (usually m4a/AAC or webm/Opus) - best quality", ["-f", "bestaudio/best", "-x"], False),
    "m4a": ("m4a (AAC) - native on YouTube, normally no re-encode", ["-f", "bestaudio[ext=m4a]/bestaudio/best", "-x", "--audio-format", "m4a"], True),
    "mp3": ("mp3 - maximum compatibility (re-encoded)", ["-f", "bestaudio/best", "-x", "--audio-format", "mp3"], True),
    "opus": ("opus - smallest at a given quality", ["-f", "bestaudio[acodec=opus]/bestaudio/best", "-x", "--audio-format", "opus"], True),
    "flac": ("flac - lossless container (cannot add quality back)", ["-f", "bestaudio/best", "-x", "--audio-format", "flac"], False),
    "wav": ("wav - uncompressed PCM", ["-f", "bestaudio/best", "-x", "--audio-format", "wav"], False),
}

AUDIO_QUALITIES = [
    ("0", "Best VBR (recommended)"),
    ("320K", "320 kbps"),
    ("192K", "192 kbps"),
    ("128K", "128 kbps"),
]

VIDEO_CONTAINERS = {
    "mp4": "mp4 - plays everywhere (prefers H.264/AAC; >1080p is VP9/AV1 only on YouTube)",
    "mkv": "mkv - any codec, best quality at every resolution",
    "webm": "webm - VP9/AV1 + Opus",
}


class Downloader:
    def __init__(self, browser: str | None = "chrome", cookies_file: str | None = None, extra_args: list[str] | None = None):
        self.browser = None if cookies_file else browser
        self.cookies_file = cookies_file
        self.cookie_source = f"cookies file {cookies_file}" if cookies_file else (f"browser '{browser}'" if browser else "no cookies")
        # --abort-on-error: yt-dlp's default ignoreerrors='only_download' makes a failed single video
        # return None instead of raising, which hides the real reason.
        base = ["--no-playlist", "--abort-on-error"]
        if cookies_file:
            base += ["--cookies", cookies_file]
        elif browser:
            base += ["--cookies-from-browser", browser]
        self.base = base + list(extra_args or [])

    def _opts(self, args: list[str]) -> dict:
        return yt_dlp.parse_options(self.base + args).ydl_opts

    def _run(self, url: str, args: list[str]) -> dict:
        with yt_dlp.YoutubeDL(self._opts(args)) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise yt_dlp.utils.DownloadError(f"yt-dlp returned no information for {url}")
            return ydl.sanitize_info(info)

    # ------------------------------------------------------------------ metadata
    def fetch_info(self, url: str) -> dict:
        with yt_dlp.YoutubeDL(self._opts(["-q", "--skip-download"])) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise yt_dlp.utils.DownloadError(f"yt-dlp returned no information for {url}")
            return ydl.sanitize_info(info)

    @staticmethod
    def available_heights(info: dict) -> list[int]:
        return sorted(
            {f["height"] for f in info.get("formats") or [] if f.get("height") and f.get("vcodec") not in (None, "none")},
            reverse=True,
        )

    # ------------------------------------------------------------------ downloads
    def download_audio(self, url: str, outdir: Path, fmt: str = "original", quality: str = "0") -> Path:
        args = ["-P", str(outdir), "-o", OUTTMPL] + AUDIO_FORMATS[fmt][1]
        if AUDIO_FORMATS[fmt][2]:
            args += ["--audio-quality", quality]
        return _final_path(self._run(url, args))

    def download_video(self, url: str, outdir: Path, height: int | None = None, container: str = "mp4") -> Path:
        sort = [f"res:{height}"] if height else ["res"]
        if container == "mp4":
            sort += ["vcodec:h264", "acodec:aac"]  # QuickTime/iOS friendly when available
        args = ["-P", str(outdir), "-o", OUTTMPL, "-f", "bv*+ba/b", "-S", ",".join(sort), "--merge-output-format", container]
        return _final_path(self._run(url, args))

    def download_subtitle(self, url: str, outdir: Path, track_key: str, auto: bool) -> Path:
        args = [
            "-P", str(outdir), "-o", OUTTMPL, "--skip-download",
            "--write-auto-subs" if auto else "--write-subs",
            "--sub-langs", track_key, "--sub-format", "vtt/best", "--convert-subs", "vtt",
        ]
        info = self._run(url, args)
        subs = info.get("requested_subtitles") or {}
        for sub in subs.values():
            if sub.get("filepath"):
                return Path(sub["filepath"])
        hits = sorted(outdir.glob(f"*[[]{info['id']}[]]*.vtt"))
        if hits:
            return hits[0]
        raise RuntimeError(f"yt-dlp did not produce a subtitle file for '{track_key}'")


def _final_path(info: dict) -> Path:
    """Path of the file after post-processing (e.g. after audio extraction / merging)."""
    for d in reversed(info.get("requested_downloads") or []):
        if d.get("filepath"):
            return Path(d["filepath"])
    if info.get("filepath"):
        return Path(info["filepath"])
    raise RuntimeError("Could not determine downloaded file path")
