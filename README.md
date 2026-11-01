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

Outputs: `Title [id].<ext>` media, `Title [id].md`, `Title [id].srt`.

### Markdown format / your own template

By default the `.md` is plain, tool-neutral Markdown: title, a metadata table, the transcript
(`[hh:mm:ss]` per paragraph), and at the end an **Obsidian frontmatter suggestion in a ```yaml code block**
that you can copy to the top of a note. Values are quoted so titles with `:` `#` `"` stay valid YAML.

- `--frontmatter yaml` puts real frontmatter at the top; `--frontmatter none` drops it.
- Use your own template: save it as `~/.config/ytpipe/template.md` (picked up automatically) or pass `--md-template FILE`.
  `ytpipe --print-template` shows the built-in one and all placeholders (`${title}`, `${url}`, `${transcript}`,
  `${frontmatter_yaml}`, ...). Obsidian/Templater syntax like `{{date}}` or `<% %>` passes through untouched;
  write `$$` for a literal `$`.

```bash
ytpipe --print-template > ~/.config/ytpipe/template.md   # then edit
```

Non-interactive examples:

```bash
ytpipe --mode transcribe --subs prefer -y "https://youtu.be/XXXX"
ytpipe --mode both --backend funasr-paraformer -d ~/Notes/yt "URL1" "URL2"
ytpipe --browser "chrome:Profile 1" ...      # a non-default Chrome profile
ytpipe --browser safari ...                  # needs Full Disk Access for the terminal
```

## Cookies / members-only videos

`--browser auto` (default) detects installed browsers and asks which one you are logged in with.
If loading cookies fails you get a menu: retry, another browser, a `cookies.txt` file, or no cookies.

- **Safari**: System Settings → Privacy & Security → Full Disk Access → enable your terminal app (Terminal/iTerm/VS Code), then restart it.
- **Chrome/Brave/Edge**: click "Always Allow" on the Keychain prompt. Non-default profile: `--browser "chrome:Profile 1"`.
- **Firefox**: works without extra permissions.
- **Arc / Orion / others**: yt-dlp can't read them. Export with a "Get cookies.txt LOCALLY" extension while on youtube.com, then `--cookies ~/yt-cookies.txt`.
  Treat that file like a password. YouTube rotates cookies, so export from a private window that you then close, or re-export when it stops working.

## Keeping yt-dlp current

YouTube changes often; old yt-dlp versions break. `yt-dlp -U` doesn't work for pip installs, so ytpipe
upgrades the library with this venv's pip (including `yt-dlp-ejs`, the JS-challenge solver) and restarts itself.

- Startup: one-line notice if PyPI has a newer version (checked at most once a day; `--no-update-check` to skip).
- At the URL prompt type `u` to update now.
- If a download fails with a typical "YouTube changed" error, ytpipe offers *update and retry* (same URL, same options).
  Bot-check / members-only errors are cookie or IP problems and are not treated as update-worthy.
- `ytpipe --update` · `ytpipe --update --channel nightly` (fixes land days earlier) · `--channel stable` to go back.
- Every update prints the exact pip command to roll back.
- Also keep deno current: `brew upgrade deno`.

## ASR backends

The engine menu is ranked for the spoken language you pick (1 = en, 2 = zh, 3 = auto, or type a code).
Engines that aren't installed are shown with their install command.

| language | recommended order |
|---|---|
| zh (普通话) | `funasr-paraformer` ★ → `mlx-whisper` (better for heavy 中英混杂) → `funasr-sensevoice` (fastest, no .srt) |
| yue (粤语) | `funasr-sensevoice` ★ → `mlx-whisper` large-v3 |
| en | `mlx-whisper` ★ → `faster-whisper` → `funasr-sensevoice` |
| others / auto | `mlx-whisper` ★ (~100 languages) |

Whisper models: `large-v3-turbo` (default, fast) / `large-v3` (most accurate) / `small` (drafts).
On non-Apple machines `faster-whisper` replaces `mlx-whisper`.

## Tests

```bash
pip install -e ".[dev]" && pytest -q
```
