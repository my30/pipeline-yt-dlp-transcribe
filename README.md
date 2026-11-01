<div align="center">

# ytpipe · pipeline-yt-dlp-transcribe

**English** | [简体中文](README.zh-CN.md)

[![CI](https://github.com/my30/pipeline-yt-dlp-transcribe/actions/workflows/ci.yml/badge.svg)](https://github.com/my30/pipeline-yt-dlp-transcribe/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-lightgrey?logo=apple)
[![yt-dlp](https://img.shields.io/pypi/v/yt-dlp?label=yt-dlp&logo=youtube&color=FF0000)](https://github.com/yt-dlp/yt-dlp)
[![License: MIT](https://img.shields.io/github/license/my30/pipeline-yt-dlp-transcribe)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/my30/pipeline-yt-dlp-transcribe)](https://github.com/my30/pipeline-yt-dlp-transcribe/commits)

Paste a YouTube URL (members-only works too), answer a few questions, and get the media file and/or a
clean, timestamped Markdown transcript, ready for an AI to analyse or to land in your Obsidian inbox.

</div>

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Modes](#modes)
- [Command reference](#command-reference)
- [Examples](#examples)
- [Members-only videos and cookies](#members-only-videos-and-cookies)
- [Subtitles first, local ASR second](#subtitles-first-local-asr-second)
- [Transcription engines](#transcription-engines)
- [Output files](#output-files)
- [Markdown templates and Obsidian](#markdown-templates-and-obsidian)
- [Config file](#config-file)
- [Keeping yt-dlp up to date](#keeping-yt-dlp-up-to-date)
- [Scripting and AI agents](#scripting-and-ai-agents)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Features

- **Three modes**: download only · transcribe only (temporary audio is deleted) · download + transcribe.
- **Members-only access** through your browser's YouTube login (`--cookies-from-browser`), with
  auto-detection of installed browsers and a diagnosis when cookies can't be read.
- **Subtitles first**: uses creator subtitles or YouTube's own ASR captions when they exist (no download
  needed), and skips *machine-translated* caption tracks, a common `--sub-langs "zh.*"` trap.
- **Local transcription** on Apple Silicon (mlx-whisper on Metal) or with Alibaba FunASR
  (Paraformer / SenseVoice) for Mandarin, with recommendations for each language.
- **Clean output**: de-duplicated YouTube rolling captions, Simplified Chinese, `[hh:mm:ss]` paragraphs, `.srt`.
- **Your own Markdown template**, including a built-in one that matches the Obsidian Web Clipper.
- **Self-updating yt-dlp**: startup check, `u` command, and an "update and retry" offer when YouTube breaks things.
- **One-line CLI for scripts and AI agents**: every question has a flag, `--json` results, `--info` inspection,
  meaningful exit codes, plus an [agent skill](skills/ytpipe/SKILL.md).

## Requirements

| | |
|---|---|
| OS | macOS on Apple Silicon (recommended) or Linux. Windows is untested. |
| Python | 3.10 – 3.13 |
| System tools | [`ffmpeg`](https://ffmpeg.org) (extract / merge audio) and [`deno`](https://deno.com) (yt-dlp needs a JS runtime for YouTube) |
| Disk | ~1.5 GB for Whisper large-v3-turbo; ~1 GB more for FunASR models (downloaded on first use) |

## Installation

```bash
brew install ffmpeg deno
```

```bash
git clone https://github.com/my30/pipeline-yt-dlp-transcribe.git
cd pipeline-yt-dlp-transcribe
python3 -m venv .venv
source .venv/bin/activate
```

Then pick the extras for your machine:

| Command | Installs | When |
|---|---|---|
| `pip install -e ".[mac]"` | yt-dlp, mlx-whisper, OpenCC | Apple Silicon Mac (recommended) |
| `pip install -e ".[funasr]"` | FunASR, torch, torchaudio | Best Mandarin accuracy (can be added to `mac`) |
| `pip install -e ".[cpu]"` | faster-whisper | Linux / Intel / NVIDIA |
| `pip install -e ".[dev]"` | pytest, pyyaml | Running the tests |

Extras can be combined: `pip install -e ".[mac,funasr]"`. The `ytpipe` command is available whenever the venv is active.

## Quick start

```bash
ytpipe
```

A real session (transcribe a members-only Mandarin interview):

```text
ytpipe 0.1.0 | yt-dlp 2026.10.26 (stable)
Using cookies from chrome.

YouTube URL (q to quit, u to update yt-dlp): https://www.youtube.com/watch?v=abc123
Fetching video info ...

  傅盛：AI 时代的创业
  晚点LatePost | 1h02m05s | subscriber_only

What do you want to do?
  1) Download only (audio or video)
  2) Transcribe only (temporary audio is deleted afterwards) (default)
  3) Download + transcribe (keep the audio/video file)
Select 1-3 [2]: 2

YouTube reports the spoken language as 'zh-Hans'.
Spoken language?
  1) English
  2) 中文 (普通话) (default)
  3) Auto-detect
     or type a code: ja, ko, yue (粤语), fr, de, ...
Select 1-3 [2]:

Found YouTube auto-generated captions (ASR, usually no punctuation) [zh-Hans-orig]
Use these subtitles instead of local transcription? [Y/n]: n

Transcription engine for 'zh'?
  1) funasr-paraformer  ★ 普通话首选: lowest error rate on Mandarin benchmarks, ... (default)
  2) mlx-whisper        Good alternative; better when lots of English is mixed in ...
  3) funasr-sensevoice  Fastest ...; no timestamps/.srt
  4) faster-whisper     Same quality as mlx-whisper but CPU-only on a Mac -> much slower
Select 1-4 [1]:

Save to directory [~/Downloads/yt-dlp]:
[download] 100% of 58.21MiB
Temporary audio removed.

Transcript: ~/Downloads/yt-dlp/傅盛：AI 时代的创业 [abc123].md
Subtitles:  ~/Downloads/yt-dlp/傅盛：AI 时代的创业 [abc123].srt

YouTube URL (q to quit, u to update yt-dlp): q
```

Press **Enter** to accept a default. In menus you can type the number or the value itself (e.g. `zh`).
After each video you're back at the URL prompt; `q` quits, `u` updates yt-dlp.

## Modes

| Mode | What it does | Questions asked | Files kept |
|---|---|---|---|
| `download` | Downloads audio **or** video | audio/video → format → quality / resolution → folder | media |
| `transcribe` | Subtitles if usable, else downloads audio to a temp folder, transcribes, **deletes the audio** | language → use subtitles? → engine → model → folder | `.md`, `.srt` |
| `both` | Downloads media, then transcribes that file | all of the above | media, `.md`, `.srt` |

Audio formats: `original` (no re-encode, best quality), `m4a`, `mp3`, `opus`, `flac`, `wav`; quality for lossy
re-encodes: best VBR / 320K / 192K / 128K. Video: `mp4` (prefers H.264/AAC for QuickTime), `mkv`, `webm`;
only resolutions that actually exist for that video are offered.

> If transcription fails in `transcribe` mode, the temporary audio is **kept** and its path printed, so a 2-hour
> download isn't lost.

## Command reference

```text
ytpipe [options] [URL ...]
```

Without URLs, ytpipe loops on a URL prompt. With URLs, it processes them in order and exits.
Options and URLs can be mixed in any order. A local audio/video **file path** can be given instead of a URL
to transcribe it. **Every interactive question has a flag below**; any question you answer by flag is skipped.

**General**

| Option | Default | Description |
|---|---|---|
| `URL ...` | – | One or more video URLs. Omit to be prompted. |
| `--mode {download,transcribe,both}` | ask | Skip the mode question. |
| `-d, --dir DIR` | ask (`~/Downloads/yt-dlp`) | Output folder for media and `.srt` (and `.md` unless `--md-dir`). |
| `-y, --yes` | off | Accept every default without prompting (good for scripts). |
| `--yt-dlp-arg ARG` | – | Pass a raw yt-dlp flag, repeatable: `--yt-dlp-arg=--limit-rate=5M` |
| `--version` / `-h, --help` | – | |

**Download choices** (download / both modes)

| Option | Default | Description |
|---|---|---|
| `--media {audio,video}` | ask (`audio`) | What to download. Implied by the flags below. |
| `--audio-format FMT` | ask (`original`) | `original` (no re-encode), `m4a`, `mp3`, `opus`, `flac`, `wav`. Implies audio. |
| `--audio-quality Q` | ask (`0`) | For lossy re-encodes: `0` (best VBR), `320K`, `192K`, `128K`, … |
| `--video-format FMT` | ask (`mp4`) | `mp4`, `mkv`, `webm`. Implies video. |
| `--resolution best\|HEIGHT` | ask (`1080` if available) | e.g. `2160`, `1080`, `720p`; the closest available is used. Implies video. |

**Cookies**

| Option | Default | Description |
|---|---|---|
| `--browser NAME` | `auto` | `auto` detects installed browsers. Or `chrome`, `safari`, `firefox`, `brave`, `edge`, `chromium`, `vivaldi`, `opera`, `chrome:Profile 1`; `none` disables cookies. |
| `--cookies FILE` | – | Use a Netscape `cookies.txt` instead of a browser. |

**Transcription**

| Option | Default | Description |
|---|---|---|
| `--lang CODE` | ask (`1`=en, `2`=zh, `3`=auto) | Spoken language: `en`, `zh`, `yue`, `ja`, `ko`, … or `auto`. |
| `--subs {ask,prefer,never}` | `ask` | `prefer`: use YouTube subtitles without asking; `never`: always run local ASR. |
| `--backend NAME` | best installed for the language | `mlx-whisper`, `faster-whisper`, `funasr-paraformer`, `funasr-sensevoice` |
| `--model NAME` | per backend | e.g. `mlx-community/whisper-large-v3-mlx`, `large-v3`, `paraformer-zh` |

**Markdown output**

| Option | Default | Description |
|---|---|---|
| `--frontmatter {suggest,yaml,none}` | `suggest` | `suggest`: generic Markdown with an Obsidian frontmatter code block at the end; `yaml`: real frontmatter at the top; `none`. |
| `--md-template FILE\|NAME` | `~/.config/ytpipe/template.md` if present | A template file, or a built-in name (`clipper-inbox`). |
| `--md-dir DIR` | same as `--dir` | Write the `.md` elsewhere, e.g. your vault's inbox. |
| `--md-name {title-id,title}` | `title-id` | `Title [id].md`, or `Title.md` like Web Clipper. |
| `--no-timestamps` | off | No `[hh:mm:ss]` before paragraphs. |
| `--print-template` | – | Print the active template and all placeholders, then exit. |

**Scripting / agents**

| Option | Default | Description |
|---|---|---|
| `--info` | – | Print video metadata as JSON (spoken language, subtitle tracks, resolutions, duration, availability) and exit. Downloads nothing. |
| `--json` | off | stdout carries one JSON result document only; all progress goes to stderr. |
| `--auto-update` | off | With `-y`: on a "YouTube changed" error, update yt-dlp and retry without asking. |

Exit codes: `0` every URL succeeded · `1` at least one failed · `2` invalid command line.
When stdin is not a terminal (pipes, cron, agents) `-y` is implied.

**yt-dlp updates**

| Option | Default | Description |
|---|---|---|
| `--update` | – | Upgrade yt-dlp (+ yt-dlp-ejs) in this venv and exit. |
| `--channel {stable,nightly}` | current | With `--update`: switch release channel. |
| `--no-update-check` | off | Don't check PyPI at startup (also: env `YTPIPE_NO_UPDATE_CHECK=1`). |

## Examples

Interactive, all questions:

```bash
ytpipe
```

Transcribe a Mandarin video with the best engine, take subtitles if they exist, no questions:

```bash
ytpipe --mode transcribe --lang zh --subs prefer --backend funasr-paraformer -y "https://youtu.be/VIDEO_ID"
```

Always transcribe locally (ignore YouTube captions) with the most accurate Whisper:

```bash
ytpipe --mode transcribe --lang en --subs never --backend mlx-whisper --model mlx-community/whisper-large-v3-mlx "URL"
```

Download audio only, several videos in a row, into a custom folder:

```bash
ytpipe --mode download -d ~/Music/podcasts "URL1" "URL2" "URL3"
```

Keep the video and get a transcript straight into an Obsidian inbox:

```bash
ytpipe --mode both --md-template clipper-inbox --md-dir ~/Vault/00-Inbox --md-name title "URL"
```

Use a non-default Chrome profile, or a cookies file:

```bash
ytpipe --browser "chrome:Profile 1"
```

```bash
ytpipe --cookies ~/yt-cookies.txt
```

Throttle bandwidth or pass any other yt-dlp option:

```bash
ytpipe --yt-dlp-arg=--limit-rate=5M --yt-dlp-arg=--sleep-requests=1 "URL"
```

Fully specified one-liner, never prompts. Keep a 1080p mkv, transcribe Mandarin locally, JSON result:

```bash
ytpipe -y --json --mode both --media video --resolution 1080 --video-format mkv --lang zh --subs never --backend funasr-paraformer "URL"
```

Podcast episodes as 192 kbps mp3:

```bash
ytpipe -y --mode download --audio-format mp3 --audio-quality 192K -d ~/Podcasts "URL1" "URL2"
```

Inspect a video before deciding (downloads nothing):

```bash
ytpipe --info "URL"
```

Transcribe a file that's already on disk:

```bash
ytpipe -y --mode transcribe --lang en ~/Downloads/talk.m4a
```

Update yt-dlp, or switch to nightly when YouTube has just broken something:

```bash
ytpipe --update
```

```bash
ytpipe --update --channel nightly
```

## Members-only videos and cookies

ytpipe reads your logged-in YouTube session from a browser, like `yt-dlp --cookies-from-browser`.
With `--browser auto` it finds installed browsers and asks which one you use if there are several. If reading
cookies fails it tells you **why** (missing folder / macOS privacy block / which profiles exist) and offers:
retry, another browser, a `cookies.txt`, or no cookies.

| Browser | One-time setup |
|---|---|
| **Chrome / Brave / Edge** | Click **Always Allow** on the Keychain prompt. If you get *could not find chrome cookies database*, give your terminal app **Full Disk Access** (System Settings → Privacy & Security), then quit and reopen it. Other profile: `--browser "chrome:Profile 1"`. |
| **Safari** | Full Disk Access for your terminal app (Terminal / iTerm / VS Code), then restart it. |
| **Firefox** | Nothing. |
| **Arc / Orion** | Not readable by yt-dlp. Export with a *Get cookies.txt LOCALLY* extension on youtube.com and use `--cookies`. |

> A `cookies.txt` is as sensitive as a password; don't commit it. YouTube rotates cookies, so re-export
> when it stops working.

## Subtitles first, local ASR second

In `transcribe` and `both` modes ytpipe checks YouTube's tracks before downloading any audio:

1. **Creator-uploaded subtitles** in your language (Simplified Chinese preferred over Traditional). Used by default.
2. **YouTube auto-captions in the video's spoken language** (`<lang>-orig`). Offered; local ASR is usually
   better because auto-captions have no punctuation.
3. **Auto-captions in another language** are a Google Translate of the original ASR. They're flagged and
   not used by default.
4. Nothing usable → local transcription.

YouTube's auto-caption VTT repeats every line (karaoke-style); ytpipe de-duplicates it.

## Transcription engines

The engine menu is ranked for the language you pick; engines that aren't installed are listed with
their `pip install` command, and the default is the best one **installed**.

| Language | Recommended order |
|---|---|
| Mandarin `zh` | `funasr-paraformer` ★ → `mlx-whisper` (better for heavy Chinese–English mixing) → `funasr-sensevoice` (fastest, no `.srt`) |
| Cantonese `yue` | `funasr-sensevoice` ★ → `mlx-whisper` with `large-v3` (turbo is weaker on Cantonese) |
| English `en` | `mlx-whisper` ★ → `faster-whisper` → `funasr-sensevoice` |
| Others / `auto` | `mlx-whisper` ★ (~100 languages) |

| Engine | Install | Notes |
|---|---|---|
| `mlx-whisper` | `.[mac]` | Metal on Apple Silicon. Models: `large-v3-turbo` (default), `large-v3`, `small`. Anti-hallucination settings on. |
| `faster-whisper` | `.[cpu]` | CTranslate2; CPU/CUDA; Silero VAD filter. On a Mac it's CPU-only and slow. |
| `funasr-paraformer` | `.[funasr]` | Paraformer-zh + VAD + punctuation; sentence timestamps. |
| `funasr-sensevoice` | `.[funasr]` | SenseVoiceSmall; zh/yue/en/ja/ko; very fast; no timestamps. |

Whisper output is converted to Simplified Chinese with OpenCC when the language is `zh`.

## Output files

| File | Content |
|---|---|
| `Title [id].<ext>` | Media (`download` / `both` modes). |
| `Title [id].md` | Transcript; see templates below. |
| `Title [id].srt` | Subtitles with timestamps (not for SenseVoice). |

The default Markdown is tool-neutral: title, a metadata table, `[hh:mm:ss]` paragraphs, and at the end an
**Obsidian frontmatter suggestion in a ` ```yaml ` code block** you can copy to the top of a note. Values are
quoted so titles containing `:` `#` `"` stay valid YAML.

## Markdown templates and Obsidian

Templates use `${placeholder}` syntax (Python `string.Template`), so Obsidian / Templater syntax such as
`{{date}}` or `<% %>` passes through untouched. Write `$$` for a literal `$`; unknown placeholders are left as is.

```bash
mkdir -p ~/.config/ytpipe
ytpipe --print-template > ~/.config/ytpipe/template.md
```

The file `~/.config/ytpipe/template.md` is then used automatically (or pass `--md-template FILE`).

| Placeholder | Value |
|---|---|
| `${title}` `${id}` `${url}` | Video title, ID, URL |
| `${channel}` `${channel_url}` | Channel name and URL |
| `${author}` `${author_wikilink}` | Channel name, and `[[Channel]]` |
| `${upload_date}` | `YYYY-MM-DD` |
| `${duration}` `${duration_seconds}` | `hh:mm:ss`, and seconds |
| `${description}` `${description_short}` | Full description; one line, ≤200 chars |
| `${tags}` | YouTube tags, comma-separated |
| `${language}` `${source}` | Spoken language; transcript source (e.g. `mlx-whisper:…`, `youtube-manual-subs:zh-Hans`) |
| `${created}` `${created_datetime}` | `YYYY-MM-DD`; `YYYY-MM-DDTHH:mm:ss` (local) |
| `${transcript}` | The paragraphs |
| `${metadata_table}` | The Channel / URL / … table |
| `${frontmatter_yaml}` | A ready `---` YAML block |
| `${frontmatter_suggestion}` | That block inside a code block, with a heading |
| `${KEY_q}` | Any value above, quoted for YAML. **Use these inside frontmatter**, e.g. `Title: ${title_q}` |

**Built-in `clipper-inbox`** mirrors an Obsidian Web Clipper "Clipping to Inbox" template:

```markdown
---
Title: ${title_q}
Source: ${url_q}
Author:
  - ${author_wikilink_q}
Published: ${upload_date}
Created: ${created_datetime}
Description: ${description_short_q}
tags:
  - raw
  - clipping
---
${metadata_table}

## Transcript

${transcript}
```

## Config file

`~/.config/ytpipe/config.toml` sets defaults for any long option (dashes or underscores). Command-line
flags still win. Unknown keys or invalid values are reported and ignored.

```toml
browser     = "chrome"
dir         = "~/Downloads/yt-dlp"                        # media and .srt
md-dir      = "~/Documents/Obsidian/MyVault/00-Inbox"     # transcripts straight into the vault
md-template = "clipper-inbox"
md-name     = "title"
subs        = "ask"
```

## Keeping yt-dlp up to date

YouTube changes often and old yt-dlp versions stop working. `yt-dlp -U` refuses pip installs, so ytpipe
upgrades the library with **this venv's pip** (including `yt-dlp-ejs`, the JS-challenge solver) and restarts itself.

- **At startup**: a one-line notice if PyPI has a newer version (checked at most once a day; offline-safe).
- **At the URL prompt**: type `u`.
- **On failure**: errors that typically mean "YouTube changed something" (e.g. `nsig extraction failed`,
  `Requested format is not available`) trigger an *update and retry* offer for the same URL with the same
  options. If you already have the latest stable version, it offers nightly.
- Bot-check and members-only errors are cookie / IP problems, so they never trigger an update offer.
- Every update prints the exact command to roll back. Keep `deno` current too: `brew upgrade deno`.

## Scripting and AI agents

ytpipe stays interactive for people, but anything you can answer in the prompts you can also pass as a flag,
so an agent can turn "download this in 4K as mkv" into one command and run it.

```bash
ytpipe -y --json --mode download --media video --resolution 2160 --video-format mkv "URL"
```

```json
{
  "ok": true,
  "results": [
    {"url": "URL", "status": "ok", "id": "ID", "title": "…", "mode": "download",
     "media": "/Users/me/Downloads/yt-dlp/Title [ID].mkv"}
  ]
}
```

Transcribe and both modes add `transcript`, `srt`, `source` (`youtube-manual-subs:…` / `funasr-paraformer:…`)
and `language`. Failed URLs have `"status": "error"` with the yt-dlp message in `error`.

Under `-y`, yt-dlp is **never** updated silently; pass `--auto-update` if you want that.

**Agent skill.** [`skills/ytpipe/SKILL.md`](skills/ytpipe/SKILL.md) teaches an agent the request→flags mapping,
defaults, the JSON contract and what to do for each error. Claude Code picks it up automatically inside this repo
(via `.claude/skills/ytpipe`). To use it everywhere:

```bash
mkdir -p ~/.claude/skills && ln -s "$PWD/skills/ytpipe" ~/.claude/skills/ytpipe
```

## Troubleshooting

| Message | Fix |
|---|---|
| `could not find chrome cookies database` | Full Disk Access for your terminal app, then quit and reopen it. ytpipe prints a diagnosis listing the profiles it finds. |
| `Sign in to confirm you're not a bot` | Use cookies from a logged-in browser; slow down (`--yt-dlp-arg=--sleep-requests=1`). An update won't fix this. |
| `Join this channel to get access to members-only content` | Log in with the *member* account in the browser/profile you pass to `--browser`. |
| `nsig extraction failed` / `Requested format is not available` | Accept the update offer, or `ytpipe --update` (then `--channel nightly`). |
| `deno not found` / JS runtime errors | `brew install deno` |
| `ffmpeg not found` | `brew install ffmpeg` |
| `Backend '…' is not installed` | Install the extra shown, e.g. `pip install -e ".[funasr]"` |
| Chinese output in Traditional characters | `pip install opencc-python-reimplemented` (included in `.[mac]`). |
| Repeated / invented sentences in silent parts | Try `funasr-paraformer` for Mandarin; Whisper already runs with anti-hallucination settings. |

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

CI runs the tests on Python 3.10–3.13 (Ubuntu) and on macOS. The tests don't touch the network: yt-dlp
and the ASR engines are faked.

```text
ytpipe/
  cli.py          interactive flow, options, config file
  downloader.py   yt-dlp wrapper (options built from real yt-dlp CLI flags)
  subtitles.py    subtitle-track choice, VTT parsing / de-duplication
  transcribe.py   ASR engines and per-language recommendations
  output.py       Markdown / SRT rendering, templates
  browsers.py     cookie browser detection and diagnosis
  updater.py      yt-dlp update / restart
  templates/      built-in Markdown templates
skills/ytpipe/SKILL.md   agent skill (symlinked into .claude/skills/)
```

## License

[MIT](LICENSE) © 2026 Ming Yang. Download only content you have the right to access, and respect YouTube's
Terms of Service and creators' copyright.
