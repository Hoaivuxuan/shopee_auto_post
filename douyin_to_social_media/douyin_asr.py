"""Speech-to-text Douyin bằng faster-whisper (ưu tiên độ chính xác)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import douyin_quality

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "douyin"
PROCESSED = DATA / "processed"
WHISPER_CACHE = Path(
    os.environ.get("WHISPER_CACHE", str(DATA / ".whisper_cache"))
)
DEFAULT_MODEL = douyin_quality.WHISPER_MODEL


def work_dir(video_id: str) -> Path:
    path = PROCESSED / str(video_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _extract_wav(video_path: Path, wav_path: Path) -> Path:
    """Tách audio 16k mono bằng ffmpeg — tránh lỗi PyAV/metadata_errors."""
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not wav_path.is_file():
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"Không tách được audio: {err}")
    return wav_path


def transcribe(
    video_path: Path,
    *,
    video_id: str = "",
    model_size: str = DEFAULT_MODEL,
    language: str = "zh",
    initial_prompt: str = "",
    force: bool = False,
) -> dict:
    """Transcribe video → transcript.json (segments có start/end/text)."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Không thấy video: {video_path}")
    vid = str(video_id or video_path.stem)
    out_dir = work_dir(vid)
    out_path = out_dir / "transcript.json"
    if out_path.is_file() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))

    WHISPER_CACHE.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "audio_16k.wav"
    _extract_wav(video_path, wav_path)

    import numpy as np
    from faster_whisper import WhisperModel

    # Đọc WAV thủ công — tránh PyAV mới bỏ tham số metadata_errors
    import wave

    with wave.open(str(wav_path), "rb") as wf:
        audio = (
            np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
            / 32768.0
        )

    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type=douyin_quality.WHISPER_COMPUTE,
        download_root=str(WHISPER_CACHE),
        cpu_threads=max(1, (os.cpu_count() or 4) - 1),
    )
    # initial_prompt giúp Whisper bám chủ đề (vd.琉璃/灯工) thay vì ảo giác nấu ăn
    prompt = (initial_prompt or "").strip()[:400]

    def _collect(vad: bool):
        kwargs = {
            "language": language or None,
            "vad_filter": vad,
            "beam_size": max(1, douyin_quality.WHISPER_BEAM_SIZE),
            "best_of": max(1, douyin_quality.WHISPER_BEST_OF),
            "patience": max(0.0, douyin_quality.WHISPER_PATIENCE),
            "temperature": 0.0,
            "condition_on_previous_text": True,
            "word_timestamps": True,
            "vad_parameters": {
                "min_silence_duration_ms": 400,
                "speech_pad_ms": 320,
            },
        }
        if prompt:
            kwargs["initial_prompt"] = prompt
        segs_iter, inf = model.transcribe(audio, **kwargs)
        rows = []
        for i, seg in enumerate(segs_iter):
            text = (seg.text or "").strip()
            if not text:
                continue
            rows.append(
                {
                    "id": i,
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": text,
                }
            )
        return rows, inf

    # VAD đôi khi nuốt hết đoạn nhạc/voice nhẹ → fallback tắt VAD
    segments, info = _collect(True)
    vad_used = True
    if not segments:
        segments, info = _collect(False)
        vad_used = False
    for i, row in enumerate(segments):
        row["id"] = i
    payload = {
        "video_id": vid,
        "source": str(video_path),
        "model": model_size,
        "language": getattr(info, "language", language) or language,
        "duration": round(float(getattr(info, "duration", 0) or 0), 3),
        "vad_filter": vad_used,
        "segments": segments,
        "text": " ".join(s["text"] for s in segments),
    }
    _write_json(out_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="ASR Douyin bằng faster-whisper")
    parser.add_argument("--video", required=True, help="Đường dẫn file video")
    parser.add_argument("--video-id", default="", help="ID lưu processed/")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="tiny|base|small|...")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = transcribe(
        Path(args.video),
        video_id=args.video_id,
        model_size=args.model,
        language=args.language,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "video_id": result["video_id"],
                "duration": result["duration"],
                "segments": len(result["segments"]),
                "model": result["model"],
                "out": str(work_dir(result["video_id"]) / "transcript.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
