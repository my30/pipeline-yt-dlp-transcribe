"""Local speech-to-text backends. Each one is optional and imported lazily.

  mlx-whisper        Apple Silicon (Metal). Default on M-series Macs.
  faster-whisper     CTranslate2; CPU/CUDA. Default elsewhere.
  funasr-paraformer  Alibaba Paraformer-zh + VAD + punctuation. Strong for Mandarin, sentence timestamps.
  funasr-sensevoice  Alibaba SenseVoiceSmall. Very fast, multilingual (zh/yue/en/ja/ko), no timestamps.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .output import Segment

BACKENDS = {
    "mlx-whisper": ("mlx_whisper", "mlx-community/whisper-large-v3-turbo", "pip install mlx-whisper"),
    "faster-whisper": ("faster_whisper", "large-v3-turbo", "pip install faster-whisper"),
    "funasr-paraformer": ("funasr", "paraformer-zh", "pip install funasr torch torchaudio"),
    "funasr-sensevoice": ("funasr", "iic/SenseVoiceSmall", "pip install funasr torch torchaudio"),
}

# Nudges Whisper towards Simplified Chinese with punctuation (it otherwise often emits Traditional / none).
ZH_PROMPT = "以下是普通话的句子，使用简体中文，并带有标点符号。"


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def installed(backend: str) -> bool:
    return importlib.util.find_spec(BACKENDS[backend][0]) is not None


def default_backend() -> str:
    order = ["mlx-whisper", "faster-whisper", "funasr-paraformer"] if is_apple_silicon() else ["faster-whisper", "funasr-paraformer"]
    for b in order:
        if installed(b):
            return b
    return order[0]


def default_model(backend: str) -> str:
    return BACKENDS[backend][1]


def transcribe(path: Path, backend: str, model: str | None = None, language: str | None = "zh") -> list[Segment]:
    if not installed(backend):
        raise RuntimeError(f"Backend '{backend}' is not installed. Run: {BACKENDS[backend][2]}")
    model = model or default_model(backend)
    language = None if language in (None, "", "auto") else language
    print(f"Transcribing with {backend} ({model}), language={language or 'auto-detect'} ...")
    fn = {
        "mlx-whisper": _mlx,
        "faster-whisper": _faster,
        "funasr-paraformer": _paraformer,
        "funasr-sensevoice": _sensevoice,
    }[backend]
    return fn(Path(path), model, language)


# ------------------------------------------------------------------ Whisper family

def _whisper_prompt(language: str | None) -> str | None:
    return ZH_PROMPT if language and language.startswith("zh") else None


def _mlx(path: Path, model: str, language: str | None) -> list[Segment]:
    import mlx_whisper  # type: ignore

    result = mlx_whisper.transcribe(
        str(path),
        path_or_hf_repo=model,
        language=language,
        initial_prompt=_whisper_prompt(language),
        # Anti-hallucination: don't let a bad window poison the next one, and skip
        # silent stretches where Whisper tends to invent repeated sentences.
        condition_on_previous_text=False,
        word_timestamps=True,
        hallucination_silence_threshold=2.0,
        verbose=False,  # shows a progress bar
    )
    return [Segment(s["start"], s["end"], s["text"].strip()) for s in result.get("segments", [])]


def _faster(path: Path, model: str, language: str | None) -> list[Segment]:
    from faster_whisper import WhisperModel  # type: ignore

    wm = WhisperModel(model, device="auto", compute_type="auto")
    segments, info = wm.transcribe(
        str(path),
        language=language,
        initial_prompt=_whisper_prompt(language),
        condition_on_previous_text=False,
        vad_filter=True,  # Silero VAD - removes silence, the main hallucination trigger
    )
    out = []
    for s in segments:
        out.append(Segment(s.start, s.end, s.text.strip()))
        print(f"\r  {s.end / max(info.duration, 1):6.1%}", end="", flush=True)
    print()
    return out


# ------------------------------------------------------------------ FunASR family

def _to_wav16k(src: Path, tmpdir: str) -> str:
    """FunASR is happiest with 16 kHz mono WAV; m4a/webm loading depends on torchaudio backends."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found (brew install ffmpeg)")
    dst = str(Path(tmpdir) / "audio16k.wav")
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", dst], check=True)
    return dst


def _funasr_device() -> str:
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"  # MPS support in FunASR is patchy; CPU is still fast for these models


def _paraformer(path: Path, model: str, language: str | None) -> list[Segment]:
    from funasr import AutoModel  # type: ignore

    am = AutoModel(model=model, vad_model="fsmn-vad", punc_model="ct-punc", device=_funasr_device(), disable_update=True)
    with tempfile.TemporaryDirectory() as tmp:
        res = am.generate(input=_to_wav16k(path, tmp), batch_size_s=300, sentence_timestamp=True)
    r = res[0] if res else {}
    sentences = r.get("sentence_info") or []
    if sentences:
        return [Segment(s["start"] / 1000, s["end"] / 1000, s["text"].strip()) for s in sentences]
    return [Segment(0.0, 0.0, r.get("text", "").strip())]


def _sensevoice(path: Path, model: str, language: str | None) -> list[Segment]:
    from funasr import AutoModel  # type: ignore
    from funasr.utils.postprocess_utils import rich_transcription_postprocess  # type: ignore

    am = AutoModel(
        model=model,
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},
        device=_funasr_device(),
        disable_update=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        res = am.generate(
            input=_to_wav16k(path, tmp),
            language=language or "auto",
            use_itn=True,  # punctuation + inverse text normalisation
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
    text = "".join(rich_transcription_postprocess(r["text"]) for r in res)
    return [Segment(0.0, 0.0, text.strip())]  # SenseVoice gives no timestamps
