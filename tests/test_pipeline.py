from pathlib import Path

import pytest

from ytpipe import cli, prompts
from ytpipe.output import Segment, paragraphs, write_markdown, write_srt
from ytpipe.subtitles import parse_vtt, pick_track

# Shape of a real YouTube auto-caption VTT: each cue repeats the previous line, plus 10ms "flash" cues.
ROLLING_VTT = """WEBVTT
Kind: captions
Language: zh

00:00:00.160 --> 00:00:02.310 align:start position:0%

大家好<00:00:00.560><c>今天</c><00:00:01.000><c>我们</c>

00:00:02.310 --> 00:00:02.320 align:start position:0%
大家好今天我们


00:00:02.320 --> 00:00:04.950 align:start position:0%
大家好今天我们
聊聊<00:00:02.800><c>量子</c><00:00:03.300><c>跃迁</c>

00:00:04.950 --> 00:00:04.960 align:start position:0%
聊聊量子跃迁


00:00:04.960 --> 00:00:07.000 align:start position:0%
聊聊量子跃迁
这个&amp;话题
"""

MANUAL_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
Hello world

2
00:01:03.500 --> 00:01:05.000
<i>Second</i> line
"""


def test_parse_vtt_collapses_rolling_duplicates():
    segs = parse_vtt(ROLLING_VTT)
    assert [s.text for s in segs] == ["大家好今天我们", "聊聊量子跃迁", "这个&话题"]
    assert segs[0].start == pytest.approx(0.16)
    assert segs[1].start == pytest.approx(2.32) and segs[1].end == pytest.approx(7.0)


def test_parse_vtt_manual():
    segs = parse_vtt(MANUAL_VTT)
    assert [s.text for s in segs] == ["Hello world", "Second line"]
    assert segs[1].start == pytest.approx(63.5)


def _info(subs=None, auto=None, language=None):
    return {"id": "abc123", "title": "T", "subtitles": subs or {}, "automatic_captions": auto or {}, "language": language}


def test_pick_prefers_manual_simplified():
    t = pick_track(_info(subs={"zh-Hant": [1], "zh-Hans": [1], "en": [1]}), "zh")
    assert (t.key, t.kind) == ("zh-Hans", "manual")


def test_pick_auto_original_language():
    t = pick_track(_info(auto={"zh-Hans-orig": [1], "zh-Hans": [1], "en": [1]}, language="zh-Hans"), "zh")
    assert (t.key, t.kind) == ("zh-Hans-orig", "auto")


def test_pick_flags_machine_translation():
    # English video: the 'zh-Hans' auto track is a translation of the English ASR.
    t = pick_track(_info(auto={"en-orig": [1], "en": [1], "zh-Hans": [1]}, language="en"), "zh")
    assert t.kind == "auto-translated" and t.warnings


def test_pick_none_when_captions_disabled():
    assert pick_track(_info(), "zh") is None


def test_pick_auto_lang():
    t = pick_track(_info(auto={"ja-orig": [1], "ja": [1]}, language="ja"), "auto")
    assert (t.key, t.kind) == ("ja-orig", "auto")


def test_writers(tmp_path):
    segs = [Segment(0, 2, "第一句。"), Segment(2.1, 4, "第二句。"), Segment(10, 12, "Third.")]
    assert paragraphs(segs) == [(0, "第一句。第二句。"), (10, "Third.")]
    srt = write_srt(segs, tmp_path / "a.srt").read_text()
    assert "00:00:10,000 --> 00:00:12,000" in srt
    md = write_markdown(segs, {"title": "T", "upload_date": "20260102", "duration": 75}, "x", tmp_path / "a.md").read_text()
    assert "upload_date: 2026-01-02" in md and "[00:00:10] Third." in md


# ------------------------------------------------------------------ end-to-end CLI flow with a fake yt-dlp

class FakeDL:
    def __init__(self, info):
        self.info, self.calls = info, []

    def fetch_info(self, url):
        return self.info

    def download_audio(self, url, outdir, fmt="original", quality="0"):
        self.calls.append(("audio", fmt, quality))
        p = Path(outdir) / "T [abc123].m4a"
        p.write_bytes(b"x")
        return p

    def download_video(self, url, outdir, height=None, container="mp4"):
        self.calls.append(("video", height, container))
        p = Path(outdir) / f"T [abc123].{container}"
        p.write_bytes(b"x")
        return p

    def download_subtitle(self, url, outdir, key, auto):
        self.calls.append(("subs", key, auto))
        p = Path(outdir) / "T.vtt"
        p.write_text(ROLLING_VTT, encoding="utf-8")
        return p


def _run(monkeypatch, tmp_path, info, answers, extra=()):
    fake = FakeDL(info)
    monkeypatch.setattr(cli, "Downloader", type("D", (), {"__new__": lambda cls, **kw: fake,
                                                          "available_heights": staticmethod(lambda i: [1080, 720])}))
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_: next(it))
    monkeypatch.setattr(cli, "installed", lambda b: True)
    monkeypatch.setattr(cli, "transcribe", lambda *a, **k: [Segment(0, 1, "本地转写")])
    prompts.ASSUME_DEFAULTS = False
    rc = cli.main(["--dir", str(tmp_path), "https://youtu.be/abc123", *extra])
    return rc, fake


def test_transcribe_only_uses_auto_subs(monkeypatch, tmp_path):
    info = {**_info(auto={"zh-Hans-orig": [1], "zh-Hans": [1]}, language="zh-Hans"), "duration": 9}
    # mode=2 (transcribe), language default, use subs = yes
    rc, fake = _run(monkeypatch, tmp_path, info, ["2", "", "y"])
    assert rc == 0 and fake.calls == [("subs", "zh-Hans-orig", True)]
    md = (tmp_path / "T [abc123].md").read_text()
    assert "聊聊量子跃迁" in md and "youtube-auto-subs" in md


def test_transcribe_only_asr_deletes_audio(monkeypatch, tmp_path):
    rc, fake = _run(monkeypatch, tmp_path, _info(), ["2", "", "1"])  # no subs -> ASR, backend #1
    assert fake.calls == [("audio", "original", "0")]
    assert not list(tmp_path.rglob("*.m4a")), "temporary audio should be removed"
    assert "本地转写" in (tmp_path / "T [abc123].md").read_text()


def test_download_plus_transcribe_keeps_video(monkeypatch, tmp_path):
    # mode=3, video, mp4, 720p, language default, decline subs? (none available) -> backend #1
    rc, fake = _run(monkeypatch, tmp_path, _info(), ["3", "2", "1", "3", "", "1"])
    assert fake.calls == [("video", 720, "mp4")]
    assert (tmp_path / "T [abc123].mp4").exists() and (tmp_path / "T [abc123].srt").exists()


def test_download_only_mp3(monkeypatch, tmp_path):
    rc, fake = _run(monkeypatch, tmp_path, _info(), ["1", "1", "3", "3"])  # download, audio, mp3, 192K
    assert fake.calls == [("audio", "mp3", "192K")]
    assert not list(tmp_path.glob("*.md"))


def test_parse_vtt_with_space_only_lines():
    # Real YouTube files keep a line containing a single space inside cues.
    vtt = ROLLING_VTT.replace("0%\n\n大家好<", "0%\n \n大家好<").replace("跃迁\n\n\n", "跃迁\n \n\n")
    assert " \n" in vtt
    assert [s.text for s in parse_vtt(vtt)] == ["大家好今天我们", "聊聊量子跃迁", "这个&话题"]


def test_cookie_failure_offers_other_browser(monkeypatch, tmp_path):
    from yt_dlp.cookies import CookieLoadError

    made = []

    class D:
        available_heights = staticmethod(lambda i: [])

        def __init__(self, browser=None, cookies_file=None, extra_args=None):
            self.browser, self.cookie_source = browser, f"browser '{browser}'"
            self.calls = []
            made.append(self)

        def fetch_info(self, url):
            if self.browser == "chrome":
                raise CookieLoadError("could not find chrome cookies database")
            return _info(subs={"zh-Hans": [1]})

        download_subtitle = FakeDL.download_subtitle

    monkeypatch.setattr(cli, "Downloader", D)
    monkeypatch.setattr(cli, "detect_browsers", lambda: ["chrome", "safari"])
    # recovery menu: 1 retry chrome, 2 safari, ... -> "2"; then mode 2, lang default, use subs
    it = iter(["2", "2", "", "y"])
    monkeypatch.setattr("builtins.input", lambda *_: next(it))
    prompts.ASSUME_DEFAULTS = False
    assert cli.main(["--browser", "chrome", "--dir", str(tmp_path), "https://youtu.be/abc123"]) == 0
    assert [d.browser for d in made] == ["chrome", "safari"]
    assert (tmp_path / "T [abc123].md").exists()


def test_detect_browsers_runs():
    from ytpipe.browsers import detect_browsers

    assert isinstance(detect_browsers(), list)


def _fake_mac_chrome(monkeypatch, root):
    from ytpipe import browsers

    monkeypatch.setattr(browsers.sys, "platform", "darwin")
    monkeypatch.setitem(browsers._PATHS["darwin"], "chrome", [str(root)])
    return browsers


def test_diagnose_lists_profiles(monkeypatch, tmp_path):
    (tmp_path / "Default" / "Network").mkdir(parents=True)
    (tmp_path / "Default" / "Network" / "Cookies").write_bytes(b"")
    (tmp_path / "Profile 2").mkdir()
    (tmp_path / "Profile 2" / "Cookies").write_bytes(b"")
    out = " ".join(_fake_mac_chrome(monkeypatch, tmp_path).diagnose("chrome"))
    assert "Default, Profile 2" in out and '--browser "chrome:Profile 2"' in out


def test_diagnose_permission_denied(monkeypatch, tmp_path):
    browsers = _fake_mac_chrome(monkeypatch, tmp_path)

    def deny(self):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(browsers.Path, "iterdir", deny)
    assert "Full Disk Access" in " ".join(browsers.diagnose("chrome"))


def test_diagnose_missing_dir(monkeypatch, tmp_path):
    out = _fake_mac_chrome(monkeypatch, tmp_path / "nope").diagnose("chrome")
    assert "does not exist" in out[0]


def test_language_shortcuts(monkeypatch):
    for answer, want in [("1", "en"), ("2", "zh"), ("3", "auto"), ("ja", "ja"), ("YUE", "yue"), ("", "en")]:
        monkeypatch.setattr("builtins.input", lambda *_: answer)
        prompts.ASSUME_DEFAULTS = False
        assert cli.choose_language(_info(auto={"en-orig": [1]})) == want


def test_recommendations(monkeypatch):
    from ytpipe import transcribe as tr

    monkeypatch.setattr(tr, "is_apple_silicon", lambda: True)
    assert tr.recommendations("zh")[0][0] == "funasr-paraformer"
    assert tr.recommendations("en")[0][0] == "mlx-whisper"
    assert "funasr-paraformer" not in [b for b, _ in tr.recommendations("en")]
    assert tr.recommendations("ja")[0][0] == "mlx-whisper"
    monkeypatch.setattr(tr, "is_apple_silicon", lambda: False)
    assert "mlx-whisper" not in [b for b, _ in tr.recommendations("ja")]


def test_choose_asr_defaults_to_installed_recommendation(monkeypatch):
    import argparse
    from ytpipe import transcribe as tr

    monkeypatch.setattr(tr, "is_apple_silicon", lambda: True)
    monkeypatch.setattr(cli, "installed", lambda b: b == "mlx-whisper")  # FunASR not installed
    monkeypatch.setattr("builtins.input", lambda *_: "")
    prompts.ASSUME_DEFAULTS = False
    args = argparse.Namespace(backend=None, model=None)
    assert cli.choose_asr("zh", args) == ("mlx-whisper", "mlx-community/whisper-large-v3-turbo")


# ------------------------------------------------------------------ yt-dlp updates

def test_breakage_detection():
    from ytpipe.updater import looks_like_breakage

    assert looks_like_breakage("ERROR: [youtube] x: nsig extraction failed: Some formats may be missing")
    assert looks_like_breakage("Requested format is not available. Use --list-formats")
    assert not looks_like_breakage("Sign in to confirm you're not a bot")  # cookies/IP, not an update
    assert not looks_like_breakage("Join this channel to get access to members-only content")


def test_version_compare():
    from ytpipe.updater import age_days, is_newer

    assert is_newer("2026.10.29.232701.dev0", "2026.10.26")
    assert not is_newer("2026.10.26", "2026.10.26") and not is_newer(None, "2026.10.26")
    assert age_days("2000.01.01") > 9000


def test_restart_args_keeps_options_drops_urls():
    raw = ["--browser", "chrome", "--update", "--channel", "nightly", "https://a", "-d", "/x", "https://b"]
    args = cli.build_parser().parse_intermixed_args(raw)
    assert cli.restart_args(raw, args, ["https://b"], retry="https://a") == \
        ["--browser", "chrome", "-d", "/x", "--resume-url", "https://a", "https://b"]


def test_breakage_offers_update_and_restarts(monkeypatch, tmp_path):
    from yt_dlp.utils import DownloadError
    from ytpipe import updater

    class D:
        cookie_source = "x"

        def __init__(self, **kw):
            pass

        def fetch_info(self, url):
            raise DownloadError("ERROR: [youtube] abc: nsig extraction failed")

    restarted = {}
    monkeypatch.setattr(cli, "Downloader", D)
    monkeypatch.setattr(updater, "installed_version", lambda: "2026.01.01")
    monkeypatch.setattr(updater, "latest_on_pypi", lambda **kw: "2026.10.26")
    monkeypatch.setattr(updater, "update", lambda target=None: ("2026.01.01", "2026.10.26"))
    monkeypatch.setattr(updater, "restart", lambda a: restarted.setdefault("argv", a))
    it = iter(["https://youtu.be/abc", "y", "q"])
    monkeypatch.setattr("builtins.input", lambda *_: next(it))
    prompts.ASSUME_DEFAULTS = False
    cli.main(["--browser", "none", "-d", str(tmp_path)])  # real restart would exec; mocked here
    assert restarted["argv"] == ["--browser", "none", "-d", str(tmp_path), "--resume-url", "https://youtu.be/abc"]


# ------------------------------------------------------------------ markdown templates

from ytpipe.output import render_markdown  # noqa: E402

_SEGS = [Segment(0, 2, "第一句。"), Segment(10, 12, "第二段。")]
_INFO = {"title": 'AI: "未来" | #1', "channel": "$HOME Channel", "id": "abc", "upload_date": "20260102",
         "duration": 3725, "webpage_url": "https://youtu.be/abc"}


def _yaml_from_codeblock(md):
    import re
    import yaml

    block = re.search(r"```yaml\n---\n(.*?)\n---\n```", md, re.S).group(1)
    return yaml.safe_load(block)


def test_default_is_generic_markdown_with_suggested_frontmatter():
    md = render_markdown(_SEGS, _INFO, "src", language="zh")
    assert not md.startswith("---")  # no real frontmatter
    assert md.startswith('# AI: "未来" | #1')
    assert "| Channel | $HOME Channel |" in md  # '$' in values is not re-substituted
    assert "[00:00:10] 第二段。" in md
    fm = _yaml_from_codeblock(md)  # tricky title must survive as valid YAML
    assert fm["title"] == 'AI: "未来" | #1' and str(fm["upload_date"]) == "2026-01-02" and fm["language"] == "zh"


def test_frontmatter_yaml_and_none_modes():
    md = render_markdown(_SEGS, _INFO, "src", frontmatter="yaml")
    assert md.startswith("---\ntitle:") and "```yaml" not in md
    md = render_markdown(_SEGS, _INFO, "src", frontmatter="none")
    assert "```" not in md and not md.rstrip().endswith("---")


def test_custom_template_keeps_obsidian_syntax():
    tpl = "---\naliases: [${id}]\nsource: ${url}\ncreated: {{date}}\n---\n# ${title}\nCost $$5 ${unknown}\n\n${transcript}\n"
    md = render_markdown(_SEGS, _INFO, "src", template=tpl, timestamps=False)
    assert md.startswith("---\naliases: [abc]\nsource: https://youtu.be/abc\ncreated: {{date}}")
    assert "Cost $5 ${unknown}" in md and "第一句。第二段。" not in md and "第二段。" in md and "[00:" not in md


def test_missing_template_fails_fast(tmp_path):
    with pytest.raises(FileNotFoundError):
        cli.main(["--md-template", str(tmp_path / "nope.md"), "https://youtu.be/x"])


def test_clipper_inbox_template_matches_web_clipper_properties():
    import re
    import yaml

    tpl = (Path(cli.__file__).parent / "templates" / "clipper-inbox.md").read_text()
    info = {**_INFO, "description": "第一行: 介绍\n\n第二行 #tag " + "长" * 300}
    md = render_markdown(_SEGS, info, "src", template=tpl)
    fm = yaml.safe_load(re.match(r"---\n(.*?)\n---\n", md, re.S).group(1))
    assert list(fm) == ["Title", "Source", "Author", "Published", "Created", "Description", "tags"]
    assert fm["Title"] == _INFO["title"] and fm["Source"] == "https://youtu.be/abc"
    assert fm["Author"] == ["[[$HOME Channel]]"] and str(fm["Published"]) == "2026-01-02"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", str(fm["Created"]).replace(" ", "T"))
    assert fm["Description"].startswith("第一行: 介绍 第二行 #tag") and fm["Description"].endswith("…")
    assert fm["tags"] == ["raw", "clipping"] and "## Transcript" in md


def test_builtin_template_by_name_and_md_dir_naming(tmp_path):
    args = cli.build_parser().parse_args(["--md-template", "clipper-inbox", "--md-dir", str(tmp_path / "Inbox"),
                                          "--md-name", "title"])
    assert cli.load_template(args).startswith("---\nTitle:")
    info = {"id": "abc", "title": "A/B: #1 [x]"}
    p = cli.transcript_path(info, "stem", tmp_path, args)
    assert p.parent == tmp_path / "Inbox" and not set("#[]|^") & set(p.stem)
    p.write_text("other note")  # name taken by an unrelated note -> fall back to the id stem
    assert cli.transcript_path(info, "stem", tmp_path, args).name == "stem.md"
    p.write_text("url: https://youtu.be/abc")  # same video re-run -> overwrite
    assert cli.transcript_path(info, "stem", tmp_path, args) == p


def test_config_file_sets_defaults_cli_wins(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('md-template = "clipper-inbox"\nmd_dir = "~/Vault/00-Inbox"\nmd-name = "title"\n'
                   'frontmatter = "bogus"\nnot_an_option = 1\n')
    parser = cli.build_parser()
    loaded = cli.load_config(parser, cfg)
    assert loaded == {"md_template": "clipper-inbox", "md_dir": "~/Vault/00-Inbox", "md_name": "title"}
    args = parser.parse_intermixed_args(["--md-name", "title-id", "https://x"])
    assert args.md_name == "title-id" and args.md_dir == "~/Vault/00-Inbox" and args.frontmatter == "suggest"


def test_fmt_duration():
    assert cli.fmt_duration(3725) == "1h02m05s" and cli.fmt_duration(605) == "10m05s"


# ------------------------------------------------------------------ one-line CLI for agents

def _no_prompts(monkeypatch):
    def boom(*a):
        raise AssertionError(f"prompted: {a}")
    monkeypatch.setattr("builtins.input", boom)


def _fake(monkeypatch, info):
    fake = FakeDL(info)
    monkeypatch.setattr(cli, "Downloader", type("D", (), {"__new__": lambda cls, **kw: fake,
                                                          "available_heights": staticmethod(lambda i: [1080, 720])}))
    monkeypatch.setattr(cli, "installed", lambda b: True)
    monkeypatch.setattr(cli, "transcribe", lambda *a, **k: [Segment(0, 1, "本地转写")])
    return fake


def test_one_line_video_download_never_prompts(monkeypatch, tmp_path):
    fake = _fake(monkeypatch, _info())
    _no_prompts(monkeypatch)
    rc = cli.main(["--browser", "none", "--mode", "download", "--resolution", "720p", "--video-format", "mkv",
                   "-d", str(tmp_path), "https://youtu.be/abc123"])
    assert rc == 0 and fake.calls == [("video", 720, "mkv")]


def test_one_line_audio_flags_imply_media(monkeypatch, tmp_path):
    fake = _fake(monkeypatch, _info())
    _no_prompts(monkeypatch)
    cli.main(["--browser", "none", "--mode", "download", "--audio-format", "mp3", "--audio-quality", "192K",
              "-d", str(tmp_path), "https://youtu.be/abc123"])
    assert fake.calls == [("audio", "mp3", "192K")]


def test_one_line_transcribe_json(monkeypatch, tmp_path, capsys):
    import json

    fake = _fake(monkeypatch, _info(subs={"zh-Hans": [1]}))
    _no_prompts(monkeypatch)
    rc = cli.main(["--browser", "none", "--mode", "transcribe", "--lang", "zh", "--subs", "prefer", "-y",
                   "--json", "-d", str(tmp_path), "https://youtu.be/abc123"])
    out, err = capsys.readouterr()
    doc = json.loads(out)  # stdout must be pure JSON
    assert rc == 0 and doc["ok"] is True
    r = doc["results"][0]
    assert r["status"] == "ok" and r["source"] == "youtube-manual-subs:zh-Hans" and Path(r["transcript"]).exists()
    assert "Fetching video info" in err and fake.calls == [("subs", "zh-Hans", False)]


def test_failure_sets_exit_code_and_json_error(monkeypatch, tmp_path, capsys):
    import json
    from yt_dlp.utils import DownloadError

    fake = _fake(monkeypatch, _info())
    monkeypatch.setattr(fake, "fetch_info", lambda u: (_ for _ in ()).throw(DownloadError("Video unavailable")))
    rc = cli.main(["--browser", "none", "-y", "--json", "--mode", "download", "https://youtu.be/x"])
    doc = json.loads(capsys.readouterr().out)
    assert rc == 1 and doc["ok"] is False and "Video unavailable" in doc["results"][0]["error"]


def test_info_prints_decision_data(monkeypatch, capsys):
    import json

    info = {**_info(subs={"en": [1]}, auto={"zh-Hans-orig": [1], "zh-Hans": [1]}, language="zh-Hans"),
            "duration": 100, "formats": [{"height": 1080, "vcodec": "avc1", "acodec": "none"},
                                         {"acodec": "mp4a", "vcodec": "none"}]}
    _fake(monkeypatch, info)
    monkeypatch.setattr(cli.Downloader, "available_heights", staticmethod(lambda i: [1080]), raising=False)
    _no_prompts(monkeypatch)
    assert cli.main(["--browser", "none", "--info", "https://youtu.be/abc123"]) == 0
    out = capsys.readouterr().out
    doc = json.loads(out[out.index("{"):])
    assert doc["spoken_language"] == "zh-Hans" and doc["manual_subtitles"] == ["en"]
    assert doc["best_subtitle_track"] == {"key": "zh-Hans-orig", "kind": "auto"} and doc["has_audio"]


def test_non_tty_implies_yes(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    fake = _fake(monkeypatch, _info())
    _no_prompts(monkeypatch)
    assert cli.main(["--browser", "none", "-d", str(tmp_path), "https://youtu.be/abc123"]) == 0
    assert fake.calls == [("audio", "original", "0")]  # defaults: transcribe mode -> temp audio


def test_yes_mode_does_not_update_silently(monkeypatch, tmp_path):
    from yt_dlp.utils import DownloadError
    from ytpipe import updater

    fake = _fake(monkeypatch, _info())
    monkeypatch.setattr(fake, "fetch_info", lambda u: (_ for _ in ()).throw(DownloadError("nsig extraction failed")))
    monkeypatch.setattr(updater, "update", lambda *a: (_ for _ in ()).throw(AssertionError("updated")))
    assert cli.main(["--browser", "none", "-y", "https://youtu.be/x"]) == 1


def test_resolution_validation():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--resolution", "hd"])
    assert cli.build_parser().parse_args(["--resolution", "1080p"]).resolution == "1080"


def test_local_file_is_transcribed_in_place(monkeypatch, tmp_path, capsys):
    import json

    f = tmp_path / "Talk [abcdefghijk].m4a"
    f.write_bytes(b"")
    fake = _fake(monkeypatch, _info())
    _no_prompts(monkeypatch)
    rc = cli.main(["--browser", "none", "-y", "--json", "--lang", "zh", "--backend", "mlx-whisper", str(f)])
    r = json.loads(capsys.readouterr().out)["results"][0]
    assert rc == 0 and fake.calls == [] and r["transcript"] == str(tmp_path / "Talk [abcdefghijk].md")
    assert (tmp_path / "Talk [abcdefghijk].md").read_text().startswith("# Talk\n")
