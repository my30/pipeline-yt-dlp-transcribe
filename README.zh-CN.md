<div align="center">

# ytpipe · pipeline-yt-dlp-transcribe

[English](README.md) | **简体中文**

[![CI](https://github.com/my30/pipeline-yt-dlp-transcribe/actions/workflows/ci.yml/badge.svg)](https://github.com/my30/pipeline-yt-dlp-transcribe/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-lightgrey?logo=apple)
[![yt-dlp](https://img.shields.io/pypi/v/yt-dlp?label=yt-dlp&logo=youtube&color=FF0000)](https://github.com/yt-dlp/yt-dlp)
[![License: MIT](https://img.shields.io/github/license/my30/pipeline-yt-dlp-transcribe)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/my30/pipeline-yt-dlp-transcribe)](https://github.com/my30/pipeline-yt-dlp-transcribe/commits)

粘贴一个 YouTube 链接（会员视频也可以），回答几个问题，就能得到音视频文件和/或一份干净、带时间戳的
Markdown 转写稿，可以直接交给 AI 分析，或放进你的 Obsidian 收件箱。

</div>

---

## 目录

- [功能特性](#功能特性)
- [环境要求](#环境要求)
- [安装](#安装)
- [快速开始](#快速开始)
- [三种模式](#三种模式)
- [命令参考](#命令参考)
- [使用示例](#使用示例)
- [会员视频与 cookies](#会员视频与-cookies)
- [字幕优先，本地转写兜底](#字幕优先本地转写兜底)
- [转写引擎](#转写引擎)
- [输出文件](#输出文件)
- [Markdown 模版与 Obsidian](#markdown-模版与-obsidian)
- [配置文件](#配置文件)
- [保持 yt-dlp 最新](#保持-yt-dlp-最新)
- [脚本与 AI agent](#脚本与-ai-agent)
- [常见问题](#常见问题)
- [开发](#开发)

## 功能特性

- **三种模式**：只下载 · 只转写（临时音频用完即删）· 下载 + 转写。
- **支持会员视频**：读取浏览器里已登录的 YouTube 会话（`--cookies-from-browser`）。自动识别已安装的浏览器，
  读取失败时会诊断原因。
- **字幕优先**：有创作者上传的字幕或 YouTube 自动字幕时直接用，不用下载音频；并且会避开
  **机器翻译**出来的字幕轨道（`--sub-langs "zh.*"` 的常见坑）。
- **本地转写**：Apple Silicon 上用 mlx-whisper（Metal 加速）；普通话可用阿里 FunASR（Paraformer / SenseVoice）。
  按语言给出推荐。
- **干净的输出**：去掉 YouTube 滚动字幕的重复行，统一转成简体中文，段落带 `[hh:mm:ss]`，同时生成 `.srt`。
- **自定义 Markdown 模版**，内置一个和 Obsidian Web Clipper 属性一致的模版。
- **yt-dlp 自更新**：启动时检查、`u` 命令一键更新，YouTube 改版导致出错时提示"更新并重试"。
- **一行命令搞定，方便脚本和 AI agent 调用**：每个交互问题都有对应参数，支持 `--json` 结果、`--info` 预查、
  有意义的退出码，并附带一份 [agent skill](skills/ytpipe/SKILL.md)。

## 环境要求

| | |
|---|---|
| 系统 | Apple Silicon 的 macOS（推荐）或 Linux。Windows 未测试。 |
| Python | 3.10 – 3.13 |
| 系统工具 | [`ffmpeg`](https://ffmpeg.org)（提取、合并音视频）和 [`deno`](https://deno.com)（yt-dlp 访问 YouTube 需要 JS 运行时） |
| 磁盘 | Whisper large-v3-turbo 约 1.5 GB；FunASR 模型另需约 1 GB（首次使用时下载） |

## 安装

```bash
brew install ffmpeg deno
```

```bash
git clone https://github.com/my30/pipeline-yt-dlp-transcribe.git
cd pipeline-yt-dlp-transcribe
python3 -m venv .venv
source .venv/bin/activate
```

然后按机器选择要装的组件：

| 命令 | 安装内容 | 适用场景 |
|---|---|---|
| `pip install -e ".[mac]"` | yt-dlp、mlx-whisper、OpenCC | Apple Silicon Mac（推荐） |
| `pip install -e ".[funasr]"` | FunASR、torch、torchaudio | 普通话准确率最高（可与 `mac` 一起装） |
| `pip install -e ".[cpu]"` | faster-whisper | Linux / Intel / NVIDIA |
| `pip install -e ".[dev]"` | pytest、pyyaml | 跑测试 |

可以组合安装：`pip install -e ".[mac,funasr]"`。激活 venv 后即可使用 `ytpipe` 命令。

## 快速开始

```bash
ytpipe
```

一次真实会话（转写一期会员专属的普通话访谈）。程序界面是英文的，下面的注释说明每一步：

```text
ytpipe 0.1.0 | yt-dlp 2026.10.26 (stable)
Using cookies from chrome.                         ← 自动识别到 Chrome

YouTube URL (q to quit, u to update yt-dlp): https://www.youtube.com/watch?v=abc123
Fetching video info ...

  傅盛：AI 时代的创业
  晚点LatePost | 1h02m05s | subscriber_only        ← 会员视频，cookies 生效

What do you want to do?                            ← 选模式
  1) Download only (audio or video)
  2) Transcribe only (temporary audio is deleted afterwards) (default)
  3) Download + transcribe (keep the audio/video file)
Select 1-3 [2]: 2

YouTube reports the spoken language as 'zh-Hans'.
Spoken language?                                   ← 1=英文，2=中文，直接回车用默认
  1) English
  2) 中文 (普通话) (default)
  3) Auto-detect
     or type a code: ja, ko, yue (粤语), fr, de, ...
Select 1-3 [2]:

Found YouTube auto-generated captions (ASR, usually no punctuation) [zh-Hans-orig]
Use these subtitles instead of local transcription? [Y/n]: n   ← 自动字幕没标点，选本地转写

Transcription engine for 'zh'?                     ← 按语言排序的推荐
  1) funasr-paraformer  ★ 普通话首选: lowest error rate on Mandarin benchmarks, ... (default)
  2) mlx-whisper        Good alternative; better when lots of English is mixed in ...
  3) funasr-sensevoice  Fastest ...; no timestamps/.srt
  4) faster-whisper     Same quality as mlx-whisper but CPU-only on a Mac -> much slower
Select 1-4 [1]:

Save to directory [~/Downloads/yt-dlp]:
[download] 100% of 58.21MiB
Temporary audio removed.                           ← 临时音频已删除

Transcript: ~/Downloads/yt-dlp/傅盛：AI 时代的创业 [abc123].md
Subtitles:  ~/Downloads/yt-dlp/傅盛：AI 时代的创业 [abc123].srt

YouTube URL (q to quit, u to update yt-dlp): q
```

直接按**回车**就是选默认项。菜单里可以输入序号，也可以直接输入值（比如 `zh`）。
处理完一个视频会回到输入网址的地方：`q` 退出，`u` 更新 yt-dlp。

## 三种模式

| 模式 | 做什么 | 会问的问题 | 保留的文件 |
|---|---|---|---|
| `download` | 下载音频**或**视频 | 音频/视频 → 格式 → 音质/分辨率 → 目录 | 音视频 |
| `transcribe` | 有可用字幕就用字幕；否则把音频下到临时目录，转写后**删除音频** | 语言 → 是否用字幕 → 引擎 → 模型 → 目录 | `.md`、`.srt` |
| `both` | 先下载音视频，再转写这个文件 | 以上全部 | 音视频、`.md`、`.srt` |

音频格式：`original`（不转码，音质最好）、`m4a`、`mp3`、`opus`、`flac`、`wav`；有损转码时可选
最佳 VBR / 320K / 192K / 128K。视频：`mp4`（优先 H.264/AAC，QuickTime 能直接播放）、`mkv`、`webm`；
只列出这个视频实际有的分辨率。

> `transcribe` 模式下如果转写失败，临时音频会**保留**并打印路径，不用重新下载 2 小时的视频。

## 命令参考

```text
ytpipe [选项] [URL ...]
```

不带 URL 时，程序循环提示输入网址；带 URL 时依次处理完就退出。选项和 URL 的先后顺序随意。
也可以把本地音视频**文件路径**当作 URL 传入，直接转写。**每个交互问题都有下面对应的参数**，用参数回答过的问题就不会再问。

**通用**

| 选项 | 默认值 | 说明 |
|---|---|---|
| `URL ...` | – | 一个或多个视频网址。省略则交互输入。 |
| `--mode {download,transcribe,both}` | 询问 | 跳过模式选择。 |
| `-d, --dir DIR` | 询问（`~/Downloads/yt-dlp`） | 音视频和 `.srt` 的保存目录（未设 `--md-dir` 时 `.md` 也在这里）。 |
| `-y, --yes` | 关 | 所有问题都用默认值，不再提问（适合脚本）。 |
| `--yt-dlp-arg ARG` | – | 透传任意 yt-dlp 参数，可重复：`--yt-dlp-arg=--limit-rate=5M` |
| `--version` / `-h, --help` | – | |

**下载选项**（download / both 模式）

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--media {audio,video}` | 询问（`audio`） | 下载音频还是视频。用了下面的参数时会自动推断。 |
| `--audio-format FMT` | 询问（`original`） | `original`（不转码）、`m4a`、`mp3`、`opus`、`flac`、`wav`。隐含音频。 |
| `--audio-quality Q` | 询问（`0`） | 有损转码的音质：`0`（最佳 VBR）、`320K`、`192K`、`128K`…… |
| `--video-format FMT` | 询问（`mp4`） | `mp4`、`mkv`、`webm`。隐含视频。 |
| `--resolution best\|高度` | 询问（有 1080 就选 1080） | 如 `2160`、`1080`、`720p`；没有该分辨率时用最接近的。隐含视频。 |

**Cookies**

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--browser NAME` | `auto` | `auto` 自动识别已安装的浏览器。也可指定 `chrome`、`safari`、`firefox`、`brave`、`edge`、`chromium`、`vivaldi`、`opera`、`chrome:Profile 1`；`none` 表示不用 cookies。 |
| `--cookies FILE` | – | 用 Netscape 格式的 `cookies.txt` 文件代替浏览器。 |

**转写**

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--lang CODE` | 询问（`1`=en，`2`=zh，`3`=auto） | 视频里说的语言：`en`、`zh`、`yue`、`ja`、`ko`…… 或 `auto`。 |
| `--subs {ask,prefer,never}` | `ask` | `prefer`：有 YouTube 字幕就直接用，不问；`never`：总是本地转写。 |
| `--backend NAME` | 该语言下已安装的最佳引擎 | `mlx-whisper`、`faster-whisper`、`funasr-paraformer`、`funasr-sensevoice` |
| `--model NAME` | 各引擎的默认模型 | 例如 `mlx-community/whisper-large-v3-mlx`、`large-v3`、`paraformer-zh` |

**Markdown 输出**

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--frontmatter {suggest,yaml,none}` | `suggest` | `suggest`：通用 Markdown，文末附 Obsidian frontmatter 代码块；`yaml`：顶部直接写 frontmatter；`none`：不要。 |
| `--md-template FILE\|NAME` | 存在则用 `~/.config/ytpipe/template.md` | 模版文件路径，或内置模版名（`clipper-inbox`）。 |
| `--md-dir DIR` | 同 `--dir` | `.md` 单独写到别处，比如 vault 的收件箱。 |
| `--md-name {title-id,title}` | `title-id` | 文件名用 `标题 [id].md`，或像 Web Clipper 一样用 `标题.md`。 |
| `--no-timestamps` | 关 | 段落前不加 `[hh:mm:ss]`。 |
| `--print-template` | – | 打印当前模版和所有占位符后退出。 |

**脚本 / agent**

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--info` | – | 以 JSON 打印视频信息（语言、字幕轨道、可用分辨率、时长、是否会员专属）后退出，不下载任何东西。 |
| `--json` | 关 | stdout 只输出一份 JSON 结果，所有进度信息都走 stderr。 |
| `--auto-update` | 关 | 配合 `-y`：遇到"YouTube 改版"类错误时，不询问直接更新 yt-dlp 并重试。 |

退出码：`0` 全部成功 · `1` 至少一个失败 · `2` 命令行参数有误。
stdin 不是终端时（管道、cron、agent），自动视为加了 `-y`。

**yt-dlp 更新**

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--update` | – | 在当前 venv 里升级 yt-dlp（含 yt-dlp-ejs）后退出。 |
| `--channel {stable,nightly}` | 当前通道 | 配合 `--update` 切换发布通道。 |
| `--no-update-check` | 关 | 启动时不查 PyPI（也可设环境变量 `YTPIPE_NO_UPDATE_CHECK=1`）。 |

## 使用示例

交互模式，逐项提问：

```bash
ytpipe
```

用最适合中文的引擎转写普通话视频；有字幕就用字幕，全程不提问：

```bash
ytpipe --mode transcribe --lang zh --subs prefer --backend funasr-paraformer -y "https://youtu.be/VIDEO_ID"
```

忽略 YouTube 字幕，总是用最准的 Whisper 本地转写：

```bash
ytpipe --mode transcribe --lang en --subs never --backend mlx-whisper --model mlx-community/whisper-large-v3-mlx "URL"
```

连续下载几个视频的音频到指定目录：

```bash
ytpipe --mode download -d ~/Music/podcasts "URL1" "URL2" "URL3"
```

保留视频，转写稿直接写进 Obsidian 收件箱：

```bash
ytpipe --mode both --md-template clipper-inbox --md-dir ~/Vault/00-Inbox --md-name title "URL"
```

使用 Chrome 的其他 profile，或使用 cookies 文件：

```bash
ytpipe --browser "chrome:Profile 1"
```

```bash
ytpipe --cookies ~/yt-cookies.txt
```

限速，或传入任意 yt-dlp 参数：

```bash
ytpipe --yt-dlp-arg=--limit-rate=5M --yt-dlp-arg=--sleep-requests=1 "URL"
```

所有选项一次写全、全程不提问：保留 1080p 的 mkv，本地转写普通话，输出 JSON 结果：

```bash
ytpipe -y --json --mode both --media video --resolution 1080 --video-format mkv --lang zh --subs never --backend funasr-paraformer "URL"
```

把几期播客下载成 192 kbps 的 mp3：

```bash
ytpipe -y --mode download --audio-format mp3 --audio-quality 192K -d ~/Podcasts "URL1" "URL2"
```

先查看视频信息再决定（不下载）：

```bash
ytpipe --info "URL"
```

转写本地已有的文件：

```bash
ytpipe -y --mode transcribe --lang en ~/Downloads/talk.m4a
```

更新 yt-dlp；YouTube 刚改版导致出错时切到 nightly：

```bash
ytpipe --update
```

```bash
ytpipe --update --channel nightly
```

## 会员视频与 cookies

ytpipe 和 `yt-dlp --cookies-from-browser` 一样，从浏览器读取你已登录的 YouTube 会话。
`--browser auto` 会找出已安装的浏览器，有多个时问你用哪个。读取失败时会说明**原因**
（目录不存在 / 被 macOS 隐私保护拦截 / 有哪些 profile），并让你选择：重试、换浏览器、用 `cookies.txt`、或不用 cookies。

| 浏览器 | 一次性设置 |
|---|---|
| **Chrome / Brave / Edge** | 钥匙串弹窗点**始终允许**。如果报 *could not find chrome cookies database*，在"系统设置 → 隐私与安全性 → 完全磁盘访问权限"里加入你的终端程序，然后完全退出再重新打开。其他 profile：`--browser "chrome:Profile 1"`。 |
| **Safari** | 给终端程序（Terminal / iTerm / VS Code）开完全磁盘访问权限，然后重启。 |
| **Firefox** | 无需设置。 |
| **Arc / Orion** | yt-dlp 读不了。在 youtube.com 上用 *Get cookies.txt LOCALLY* 扩展导出，然后用 `--cookies`。 |

> `cookies.txt` 和密码一样敏感，不要提交到 git。YouTube 会定期更换 cookies，失效了就重新导出。

## 字幕优先，本地转写兜底

在 `transcribe` 和 `both` 模式下，ytpipe 会先检查 YouTube 的字幕轨道，再决定要不要下载音频：

1. **创作者上传的字幕**（简体优先于繁体）：默认直接使用。
2. **视频原语言的 YouTube 自动字幕**（`<语言>-orig`）：会询问你；通常本地转写更好，因为自动字幕没有标点。
3. **其他语言的自动字幕**：这是原语言识别结果的谷歌机翻。会标出警告，默认不用。
4. 都没有 → 本地转写。

YouTube 自动字幕的 VTT 文件是滚动显示的，每行会重复出现，ytpipe 会去重。

## 转写引擎

引擎菜单按你选的语言排序；未安装的引擎会附上 `pip install` 命令，默认选中**已安装**里最好的那个。

| 语言 | 推荐顺序 |
|---|---|
| 普通话 `zh` | `funasr-paraformer` ★ → `mlx-whisper`（中英混杂多时更好）→ `funasr-sensevoice`（最快，不出 `.srt`） |
| 粤语 `yue` | `funasr-sensevoice` ★ → `mlx-whisper` 配 `large-v3`（turbo 对粤语偏弱） |
| 英语 `en` | `mlx-whisper` ★ → `faster-whisper` → `funasr-sensevoice` |
| 其他 / `auto` | `mlx-whisper` ★（约 100 种语言） |

| 引擎 | 安装 | 说明 |
|---|---|---|
| `mlx-whisper` | `.[mac]` | Apple Silicon 上用 Metal 加速。模型：`large-v3-turbo`（默认）、`large-v3`、`small`。已开启防"幻觉"设置。 |
| `faster-whisper` | `.[cpu]` | CTranslate2；CPU/CUDA；带 Silero VAD 静音过滤。在 Mac 上只能用 CPU，很慢。 |
| `funasr-paraformer` | `.[funasr]` | Paraformer-zh + VAD + 标点模型；有句级时间戳。 |
| `funasr-sensevoice` | `.[funasr]` | SenseVoiceSmall；支持中/粤/英/日/韩；非常快；没有时间戳。 |

语言为 `zh` 时，Whisper 的输出会经 OpenCC 转成简体。

## 输出文件

| 文件 | 内容 |
|---|---|
| `标题 [id].<扩展名>` | 音视频（`download` / `both` 模式）。 |
| `标题 [id].md` | 转写稿，格式见下方模版说明。 |
| `标题 [id].srt` | 带时间戳的字幕（SenseVoice 不生成）。 |

默认的 Markdown 不依赖任何工具：标题、元数据表格、带 `[hh:mm:ss]` 的段落；文末附一个
**放在 ` ```yaml ` 代码块里的 Obsidian frontmatter 建议**，需要时复制到笔记顶部。值都加了引号，
标题里有 `:`、`#`、`"` 也不会破坏 YAML。

## Markdown 模版与 Obsidian

模版用 `${占位符}` 语法（Python `string.Template`），所以 Obsidian / Templater 的 `{{date}}`、`<% %>`
会原样保留。要输出字面的 `$` 写成 `$$`；不认识的占位符保持原样。

```bash
mkdir -p ~/.config/ytpipe
ytpipe --print-template > ~/.config/ytpipe/template.md
```

之后程序会自动使用 `~/.config/ytpipe/template.md`（也可以用 `--md-template 文件` 临时指定）。

| 占位符 | 值 |
|---|---|
| `${title}` `${id}` `${url}` | 视频标题、ID、网址 |
| `${channel}` `${channel_url}` | 频道名和频道网址 |
| `${author}` `${author_wikilink}` | 频道名，以及 `[[频道名]]` |
| `${upload_date}` | `YYYY-MM-DD` |
| `${duration}` `${duration_seconds}` | `hh:mm:ss`，以及秒数 |
| `${description}` `${description_short}` | 完整简介；压成一行、不超过 200 字的摘要 |
| `${tags}` | YouTube 标签，逗号分隔 |
| `${language}` `${source}` | 语言；转写来源（如 `mlx-whisper:…`、`youtube-manual-subs:zh-Hans`） |
| `${created}` `${created_datetime}` | `YYYY-MM-DD`；`YYYY-MM-DDTHH:mm:ss`（本地时间） |
| `${transcript}` | 转写正文段落 |
| `${metadata_table}` | 频道、网址等元数据表格 |
| `${frontmatter_yaml}` | 现成的 `---` YAML 块 |
| `${frontmatter_suggestion}` | 上面那块放进代码块，带小标题 |
| `${KEY_q}` | 上面任意字段加引号后的 YAML 安全版本。**写在 frontmatter 里时请用它**，如 `Title: ${title_q}` |

**内置模版 `clipper-inbox`**，和 Obsidian Web Clipper 的 "Clipping to Inbox" 模版属性一致：

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

## 配置文件

`~/.config/ytpipe/config.toml` 可以为任意长选项设置默认值（连字符或下划线都行），命令行参数优先。
未知的键或非法的值会提示并忽略。

```toml
browser     = "chrome"
dir         = "~/Downloads/yt-dlp"                        # 音视频和 .srt
md-dir      = "~/Documents/Obsidian/MyVault/00-Inbox"     # 转写稿直接进 vault
md-template = "clipper-inbox"
md-name     = "title"
subs        = "ask"
```

## 保持 yt-dlp 最新

YouTube 经常改版，旧版 yt-dlp 会失效。`yt-dlp -U` 拒绝更新 pip 安装的版本，所以 ytpipe 用
**当前 venv 的 pip** 来升级（连同负责解 JS 校验的 `yt-dlp-ejs`），然后自动重启。

- **启动时**：PyPI 有新版本时提示一行（每天最多查一次；断网也不会卡住）。
- **输入网址处**：输入 `u`。
- **出错时**：像是"YouTube 改了东西"的报错（如 `nsig extraction failed`、`Requested format is not available`）
  会提示"更新并重试"，用同一个网址、同样的选项。如果已经是最新稳定版，会提议试 nightly。
- 人机验证和会员权限的报错是 cookies / IP 的问题，不会触发更新提示。
- 每次更新都会打印回退命令。`deno` 也要定期更新：`brew upgrade deno`。

## 脚本与 AI agent

ytpipe 对人保持交互式，但交互里能回答的问题都能用参数传入。所以 agent 可以把"把这个视频下成 4K 的 mkv"
直接翻译成一行命令执行：

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

transcribe 和 both 模式还会返回 `transcript`、`srt`、`source`（如 `youtube-manual-subs:…` / `funasr-paraformer:…`）
和 `language`。失败的 URL 为 `"status": "error"`，`error` 字段里是 yt-dlp 的原始报错。

在 `-y` 模式下，yt-dlp **永远不会**被静默更新；需要自动更新时请加 `--auto-update`。

**Agent skill。** [`skills/ytpipe/SKILL.md`](skills/ytpipe/SKILL.md) 告诉 agent：用户需求怎么对应到参数、各项默认值、
JSON 输出格式、每种错误该怎么处理。在本仓库里 Claude Code 会自动加载它（通过 `.claude/skills/ytpipe`）。
想在任何目录都能用：

```bash
mkdir -p ~/.claude/skills && ln -s "$PWD/skills/ytpipe" ~/.claude/skills/ytpipe
```

## 常见问题

| 报错 | 解决办法 |
|---|---|
| `could not find chrome cookies database` | 给终端程序开完全磁盘访问权限，完全退出后重开。ytpipe 会打印诊断结果，列出找到的 profile。 |
| `Sign in to confirm you're not a bot` | 用已登录浏览器的 cookies；放慢请求（`--yt-dlp-arg=--sleep-requests=1`）。更新解决不了这个问题。 |
| `Join this channel to get access to members-only content` | 在 `--browser` 指定的浏览器/profile 里登录**有会员**的账号。 |
| `nsig extraction failed` / `Requested format is not available` | 接受更新提示，或运行 `ytpipe --update`（不行再加 `--channel nightly`）。 |
| `deno not found` / JS 运行时报错 | `brew install deno` |
| `ffmpeg not found` | `brew install ffmpeg` |
| `Backend '…' is not installed` | 安装提示里的组件，如 `pip install -e ".[funasr]"` |
| 中文输出是繁体 | `pip install opencc-python-reimplemented`（`.[mac]` 已包含）。 |
| 静音段出现重复、编造的句子 | 普通话换用 `funasr-paraformer`；Whisper 已默认开启防幻觉设置。 |

## 开发

```bash
pip install -e ".[dev]"
pytest -q
```

CI 会在 Ubuntu 的 Python 3.10–3.13 和 macOS 上跑测试。测试不联网：yt-dlp 和转写引擎都用假对象代替。

```text
ytpipe/
  cli.py          交互流程、命令行选项、配置文件
  downloader.py   yt-dlp 封装（选项由真实的 yt-dlp 命令行参数生成）
  subtitles.py    字幕轨道选择、VTT 解析与去重
  transcribe.py   转写引擎与按语言的推荐
  output.py       Markdown / SRT 渲染、模版
  browsers.py     cookies 浏览器识别与诊断
  updater.py      yt-dlp 更新与重启
  templates/      内置 Markdown 模版
skills/ytpipe/SKILL.md   agent skill（软链接到 .claude/skills/）
```

## 许可证

[MIT](LICENSE) © 2026 Ming Yang。请只下载你有权访问的内容，并遵守 YouTube 服务条款和创作者的版权。
