---
name: ytpipe
description: Download YouTube audio/video (including members-only videos via browser cookies) and/or turn a YouTube video into a timestamped Markdown + SRT transcript, using the local `ytpipe` CLI (yt-dlp + mlx-whisper / FunASR). Use when the user gives a YouTube URL and wants it downloaded, transcribed, summarised from its speech, saved to Obsidian, or asks things like "下载这个视频", "转写/转录这个视频", "把这期播客转成文字", "get the transcript of this YouTube video", "save this talk as mp3".
---

# ytpipe: YouTube download and transcription in one command

`ytpipe` is interactive for humans, but **every question has a flag**. As an agent, always run it as
**one non-interactive command** and read the JSON result. Never drive the interactive prompts.

## Golden rules

1. Always pass `-y --json`. `-y` means no prompts (it is also automatic when stdin isn't a TTY), and
   `--json` means stdout is exactly one JSON document, with all progress going to stderr.
2. Always pass `--mode` explicitly. Under `-y` the default mode is `transcribe`, so a download request
   **must** say `--mode download`.
3. Quote URLs. Run several URLs in one command; they are processed in order.
4. Check the exit code: `0` all succeeded · `1` at least one URL failed (see `results[].error`) · `2` bad flags.
5. It can be slow: local transcription takes minutes per hour of audio on Apple Silicon (much more with
   `large-v3` or on CPU), and model downloads (~1–1.5 GB) happen on first use. Use a generous timeout
   (≥ 30 min for long videos) or run it in the background; `duration_seconds` from `--info` helps you estimate.
6. Don't update yt-dlp, change the user's browser permissions, or export cookies without the user's consent.

## Preflight (once per session)

```bash
command -v ytpipe && ytpipe --version
```

If the command isn't found, it is usually installed in the repo's venv:
`source <repo>/.venv/bin/activate` (or call `<repo>/.venv/bin/ytpipe`). Install from scratch:
`brew install ffmpeg deno && pip install -e "<repo>[mac]"` (add `,funasr` for best Mandarin).

`~/.config/ytpipe/config.toml` may set defaults (e.g. `md-dir`, `md-template`, `browser`). Flags you pass
override it. If the user's request implies a specific location or format, pass it explicitly.

## Step 1: inspect when the request depends on the video (optional, fast, downloads nothing)

```bash
ytpipe --info --json "URL"
```

It returns `spoken_language`, `manual_subtitles`, `auto_caption_original`, `best_subtitle_track`,
`video_heights`, `duration_seconds`, `availability` (`subscriber_only` = members-only), `is_live`.
Use it to pick `--lang`, `--resolution`, and whether subtitles are good enough, and to warn about long runtimes.

## Step 2: map the request to flags

| User intent | Flags |
|---|---|
| download the video / 下载视频 | `--mode download --media video` |
| …in 1080p / 4K / best | `--resolution 1080` · `--resolution 2160` · `--resolution best` |
| …as mkv / webm (default mp4, H.264 preferred) | `--video-format mkv` |
| download audio only / 只要音频 / podcast | `--mode download --media audio` |
| …as mp3 / m4a / flac / wav / opus | `--audio-format mp3` (default `original`: no re-encode, best quality) |
| …mp3 at 192 kbps | `--audio-format mp3 --audio-quality 192K` (`0` = best VBR) |
| transcript only / 只要文字 / 转写 | `--mode transcribe` (temporary audio is deleted) |
| keep the file **and** transcribe | `--mode both` plus the download flags above |
| transcribe a file already on disk | pass its path instead of a URL: `--mode transcribe "/path/file.m4a"` (output next to it, or `-d`) |
| language is Chinese / English / Cantonese / … | `--lang zh` · `--lang en` · `--lang yue` · `--lang ja` · `--lang auto` |
| fast, YouTube subtitles are fine | `--subs prefer` |
| best quality / accurate / with punctuation | `--subs never` (always local ASR) |
| Mandarin, best accuracy | `--backend funasr-paraformer` |
| lots of English mixed into Chinese | `--backend mlx-whisper` |
| fastest possible (no timestamps / .srt) | `--backend funasr-sensevoice` |
| most accurate Whisper | `--backend mlx-whisper --model mlx-community/whisper-large-v3-mlx` |
| save to folder X | `-d X` (media + .srt; also .md unless `--md-dir`) |
| put the note in Obsidian / my vault inbox | `--md-dir "<vault>/00-Inbox" --md-template clipper-inbox --md-name title` |
| no timestamps in the text | `--no-timestamps` |
| real YAML frontmatter at top / none | `--frontmatter yaml` · `--frontmatter none` |
| members-only / use Safari / Firefox / a profile | `--browser chrome` · `safari` · `firefox` · `"chrome:Profile 1"` |
| user has a cookies.txt | `--cookies /path/cookies.txt` |
| public video, skip cookies (avoids Keychain prompt) | `--browser none` |
| be gentle / rate-limit | `--yt-dlp-arg=--limit-rate=5M --yt-dlp-arg=--sleep-requests=1` |

Defaults under `-y` when you don't pass a flag: `--mode transcribe`; language = YouTube's reported
language if it is `en`/`zh`, `auto` for other known languages, `zh` if unknown; subtitles used if they are
creator-made **or** original-language auto-captions (machine-translated tracks are never used); backend =
best installed for the language (zh: Paraformer > mlx-whisper; en/others: mlx-whisper); Whisper model
`large-v3-turbo` (`large-v3` for Cantonese); media audio, format `original`; video mp4 at 1080p if available,
else best; folder `~/Downloads/yt-dlp`; browser auto-detected.

**Prefer explicit flags over defaults** for anything the user said. If the user only said "transcribe", the
defaults are good. Auto-captions have no punctuation: when the transcript is for reading or for an LLM to
analyse, prefer `--subs never` unless the user wants speed.

## Step 3: run

```bash
ytpipe -y --json --mode transcribe --lang zh --subs never --backend funasr-paraformer "https://www.youtube.com/watch?v=ID"
```

More one-liners:

```bash
# 4K video as mkv into ~/Movies
ytpipe -y --json --mode download --media video --resolution 2160 --video-format mkv -d ~/Movies "URL"

# podcast as 192k mp3, three episodes
ytpipe -y --json --mode download --audio-format mp3 --audio-quality 192K -d ~/Podcasts "URL1" "URL2" "URL3"

# keep the m4a and transcribe English, Obsidian-ready
ytpipe -y --json --mode both --audio-format m4a --lang en --md-dir ~/Vault/00-Inbox --md-template clipper-inbox --md-name title "URL"

# quick transcript from YouTube subtitles if available
ytpipe -y --json --mode transcribe --subs prefer "URL"
```

## Step 4: read the result

```json
{
  "ok": true,
  "results": [
    {
      "url": "https://www.youtube.com/watch?v=ID",
      "status": "ok",
      "id": "ID",
      "title": "…",
      "mode": "both",
      "media": "/Users/me/Downloads/yt-dlp/Title [ID].m4a",
      "transcript": "/Users/me/Vault/00-Inbox/Title.md",
      "srt": "/Users/me/Downloads/yt-dlp/Title [ID].srt",
      "source": "funasr-paraformer:paraformer-zh",
      "language": "zh"
    }
  ]
}
```

`media` appears for download/both, `transcript`/`srt`/`source`/`language` for transcribe/both (`srt` is missing
for SenseVoice). `source` tells you whether the text came from YouTube (`youtube-manual-subs:…`,
`youtube-auto-subs:…`) or local ASR. If the user asked for a summary or analysis, **read the `transcript`
file** and work from it. Report the file paths to the user.

## Errors (`status: "error"`, exit code 1)

| `error` contains | What to do |
|---|---|
| `could not find chrome cookies database`, `CookieLoadError` | macOS privacy block. Ask the user to give their terminal/agent host app **Full Disk Access** (System Settings → Privacy & Security), quit and reopen it. Or ask which browser/profile they use (`--browser "chrome:Profile 1"`). Don't retry blindly. |
| `Join this channel`, `members-only`, `Sign in` (not bot check) | The browser profile isn't logged in with the member account. Ask the user; try `--browser` with the right profile. |
| `Sign in to confirm you're not a bot` | IP/cookie throttling. Retry once with cookies and `--yt-dlp-arg=--sleep-requests=1`; an update won't help. Don't loop. |
| `nsig extraction failed`, `Requested format is not available`, `Unable to extract`, `Please report this issue` | yt-dlp is probably outdated. **With the user's OK**, run `ytpipe --update` (or add `--auto-update` to the command) and retry; if still failing, `ytpipe --update --channel nightly`. |
| `deno not found`, JS runtime / challenge errors | `brew install deno` (ask first). |
| `ffmpeg not found` | `brew install ffmpeg` (ask first). |
| `Backend '…' is not installed. Run: …` | Either rerun with an installed backend (e.g. `--backend mlx-whisper`), or install the shown package with consent. |
| `Video unavailable`, `Private video`, `This live event` | Not fixable by flags; tell the user. Live streams must finish first. |
| `Transcription failed; audio kept at: <path>` (stderr) | The audio is still there. Fix the cause, then transcribe the file directly: `ytpipe -y --json --mode transcribe --lang zh "<path>"`. |

Playlists are rejected; expand them yourself (e.g. `yt-dlp --flat-playlist --print url "PLAYLIST"`) and pass
the video URLs.

## Don'ts

- Don't run `ytpipe` without `-y` in an agent context, or pipe answers into prompts.
- Don't use bare `yt-dlp --sub-langs "zh.*"` to get Chinese text: on non-Chinese videos that's a machine
  translation. ytpipe already chooses tracks correctly.
- Don't delete or move the user's media files; in `--mode transcribe` ytpipe cleans up its own temp audio.
- Don't commit or print cookies files.
