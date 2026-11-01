# pipeline-yt-dlp-transcribe

A semi-automated pipeline that downloads YouTube media with yt-dlp (members-only videos too, via your
browser's login cookies) and transcribes it locally, producing a Markdown transcript ready to feed to an AI.

## Install (macOS, Apple Silicon)

```bash
brew install ffmpeg deno          # ffmpeg: extract/merge; deno: yt-dlp needs a JS runtime for YouTube
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[mac]"           # yt-dlp + mlx-whisper + OpenCC
# optional, often better for Mandarin:
pip install -e ".[funasr]"
```

On Linux/Intel use `pip install -e ".[cpu]"` (faster-whisper) instead of `.[mac]`.

## Use

```bash
ytpipe                 # interactive: paste URLs one after another, 'q' to quit
```

Flow for each URL:

1. Fetch metadata (checks login/membership up front).
2. **Mode**: download only / transcribe only (temporary audio deleted afterwards) / download + transcribe.
3. Download options: audio or video → format → quality/resolution (offers only the resolutions that exist).
4. Transcription: spoken language → checks YouTube subtitles first:
   creator-uploaded subtitles → auto-generated ASR captions in the *spoken* language → otherwise local ASR.
   Machine-translated caption tracks are flagged and not used by default.
5. Output directory (default `~/Downloads/yt-dlp`).

Outputs: `Title [id].<ext>` media, `Title [id].md` (metadata header + paragraphs with `[hh:mm:ss]` stamps),
`Title [id].srt`.

Non-interactive examples:

```bash
ytpipe --mode transcribe --subs prefer -y "https://youtu.be/XXXX"
ytpipe --mode both --backend funasr-paraformer -d ~/Notes/yt "URL1" "URL2"
ytpipe --browser "chrome:Profile 1" ...      # a non-default Chrome profile
ytpipe --browser safari ...                  # needs Full Disk Access for the terminal
```

## ASR backends

| backend | best for | notes |
|---|---|---|
| `mlx-whisper` (default on M-series) | multilingual, good all-rounder | `whisper-large-v3-turbo` on Metal; anti-hallucination settings on |
| `faster-whisper` | non-Mac / CUDA | Silero VAD filter on |
| `funasr-paraformer` | Mandarin | natural punctuation, sentence timestamps, fewer hallucinations on silence |
| `funasr-sensevoice` | very fast zh/yue/en/ja/ko | no timestamps → no .srt |

## Tests

```bash
pip install -e ".[dev]" && pytest -q
```
