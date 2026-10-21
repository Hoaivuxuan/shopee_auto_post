"""Cắt / ghép highlight bằng FFmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import douyin_quality

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "douyin" / "processed"
# Montage Shorts: shot ngắn trong mỗi beat (công thức cnJblXj7EUk)
SHOT_SECONDS = 2.6
SHOT_MIN = 1.2


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise RuntimeError(f"FFmpeg lỗi: {err}")


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return 0.0
    try:
        return float((proc.stdout or "").strip() or 0)
    except ValueError:
        return 0.0


def _shot_ranges(start: float, end: float, shot: float = SHOT_SECONDS) -> list[tuple[float, float]]:
    """Chia beat dài thành shot ngắn (montage)."""
    start, end = float(start), float(end)
    if end - start <= shot + 0.5:
        return [(start, end)] if end > start else []
    ranges: list[tuple[float, float]] = []
    t = start
    while t < end - 0.05:
        e = min(end, t + shot)
        if e - t >= SHOT_MIN:
            ranges.append((round(t, 3), round(e, 3)))
        elif ranges:
            # gộp phần dư vào shot trước
            ps, _pe = ranges[-1]
            ranges[-1] = (ps, round(end, 3))
            break
        else:
            ranges.append((round(t, 3), round(end, 3)))
            break
        t = e
    return ranges


def cut_highlights(
    video_path: Path,
    highlights: dict,
    *,
    video_id: str = "",
    force: bool = False,
    montage: bool = True,
) -> dict:
    video_path = Path(video_path)
    vid = str(video_id or highlights.get("video_id") or video_path.stem)
    out_dir = PROCESSED / vid
    clips_dir = out_dir / "clips"
    out_video = out_dir / "cut.mp4"
    meta_path = out_dir / "cut.json"
    if out_video.is_file() and meta_path.is_file() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))

    if not shutil.which("ffmpeg"):
        raise RuntimeError("Chưa cài ffmpeg.")

    clips = list(highlights.get("clips") or [])
    if not clips:
        raise ValueError("highlights không có clips.")

    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Montage: tách mỗi beat thành nhiều shot 1–3s
    work: list[dict] = []
    for clip in clips:
        start = float(clip["start"])
        end = float(clip["end"])
        if end <= start:
            continue
        ranges = _shot_ranges(start, end) if montage else [(start, end)]
        for rs, re in ranges:
            work.append(
                {
                    "start": rs,
                    "end": re,
                    "text": clip.get("text") or "",
                    "beat": clip.get("beat"),
                    "beat_name": clip.get("beat_name") or "",
                }
            )

    piece_paths: list[Path] = []
    timeline = []
    cursor = 0.0
    for i, clip in enumerate(work):
        start = float(clip["start"])
        end = float(clip["end"])
        piece = clips_dir / f"part_{i:03d}.mp4"
        # Re-encode để cắt chính xác (không phụ thuộc keyframe)
        _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(video_path),
                "-c:v",
                "libx264",
                "-preset",
                douyin_quality.FFMPEG_PRESET,
                "-crf",
                douyin_quality.FFMPEG_CRF,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                douyin_quality.FFMPEG_AUDIO_BITRATE,
                "-movflags",
                "+faststart",
                str(piece),
            ]
        )
        dur = probe_duration(piece) or (end - start)
        piece_paths.append(piece)
        timeline.append(
            {
                "index": i,
                "src_start": start,
                "src_end": end,
                "out_start": round(cursor, 3),
                "out_end": round(cursor + dur, 3),
                "duration": round(dur, 3),
                "text": clip.get("text") or "",
                "beat": clip.get("beat"),
                "beat_name": clip.get("beat_name") or "",
                "file": str(piece.name),
            }
        )
        cursor += dur

    if not piece_paths:
        raise RuntimeError("Không cắt được đoạn nào.")

    if len(piece_paths) == 1:
        shutil.copy2(piece_paths[0], out_video)
    else:
        list_file = clips_dir / "concat.txt"
        lines = [f"file '{p.resolve()}'" for p in piece_paths]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if douyin_quality.CUT_REENCODE_CONCAT:
            concat_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c:v",
                "libx264",
                "-preset",
                douyin_quality.FFMPEG_PRESET,
                "-crf",
                douyin_quality.FFMPEG_CRF,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                douyin_quality.FFMPEG_AUDIO_BITRATE,
                "-movflags",
                "+faststart",
                str(out_video),
            ]
        else:
            concat_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out_video),
            ]
        _run(concat_cmd)

    payload = {
        "video_id": vid,
        "source": str(video_path),
        "output": str(out_video),
        "duration": round(probe_duration(out_video) or cursor, 3),
        "montage": bool(montage),
        "shot_seconds": SHOT_SECONDS if montage else None,
        "shots": len(timeline),
        "timeline": timeline,
    }
    _write_json(meta_path, payload)
    return payload
