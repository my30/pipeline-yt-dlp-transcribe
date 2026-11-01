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
