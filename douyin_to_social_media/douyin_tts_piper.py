"""TTS local Piper — giọng nam miền Bắc (offline, CPU).

Model mặc định: CakeByVPBank piper-v3 multi-speaker, speaker_id=2 (Quang Huy — nam Bắc).
"""

from __future__ import annotations

import wave
from pathlib import Path

import douyin_quality

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "data" / "douyin" / ".piper_models"
DEFAULT_MODEL = MODEL_DIR / "csa-v3" / "vi_VN-csa-voice-piper-v3-medium.onnx"
# 0 Ngọc Lan nữ Bắc, 1 Minh Anh nữ Bắc, 2 Quang Huy NAM Bắc, 3 Thu Hà nữ Bắc, 4 Yến Nhi nữ Nam
DEFAULT_SPEAKER_ID = 2
# >1 = chậm hơn (nhẹ nhàng, truyền cảm). 1.0 ≈ bình thường.
DEFAULT_LENGTH_SCALE = 1.38

_VOICE = None


def configured() -> bool:
    return DEFAULT_MODEL.is_file() and Path(str(DEFAULT_MODEL) + ".json").is_file()


def _load():
    global _VOICE
    if _VOICE is not None:
        return _VOICE
    if not configured():
        raise RuntimeError(
            f"Chưa có model Piper tại {DEFAULT_MODEL}. "
            "Chạy download model trước."
        )
    from piper import PiperVoice

    _VOICE = PiperVoice.load(
        str(DEFAULT_MODEL),
        config_path=str(DEFAULT_MODEL) + ".json",
        use_cuda=False,
    )
    return _VOICE


def synthesize_to_wav(
    text: str,
    out_wav: Path,
    *,
    speaker_id: int = DEFAULT_SPEAKER_ID,
    length_scale: float = DEFAULT_LENGTH_SCALE,
) -> Path:
    """Sinh WAV mono 22050 Hz."""
    from piper.config import SynthesisConfig

    text = (text or "").strip() or "Xin chào."
    voice = _load()
    cfg = SynthesisConfig(
        speaker_id=int(speaker_id),
        length_scale=float(length_scale),
        noise_scale=0.667,
        noise_w_scale=0.8,
        normalize_audio=True,
        volume=1.0,
    )
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=cfg)
    if not out_wav.is_file() or out_wav.stat().st_size < 1000:
        raise RuntimeError("Piper không tạo được file audio.")
    return out_wav


def synthesize_to_mp3(
    text: str,
    out_mp3: Path,
    *,
    speaker_id: int = DEFAULT_SPEAKER_ID,
    length_scale: float = DEFAULT_LENGTH_SCALE,
) -> Path:
    """Sinh mp3 (qua ffmpeg) để tương thích pipeline hiện tại."""
    import subprocess

    tmp = out_mp3.with_suffix(".piper.wav")
    synthesize_to_wav(text, tmp, speaker_id=speaker_id, length_scale=length_scale)
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp),
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            str(douyin_quality.PIPER_MP3_QSCALE),
            str(out_mp3),
        ],
        capture_output=True,
        text=True,
    )
    tmp.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_mp3.is_file():
        raise RuntimeError(f"ffmpeg mp3 lỗi: {(proc.stderr or '')[-400:]}")
    return out_mp3
