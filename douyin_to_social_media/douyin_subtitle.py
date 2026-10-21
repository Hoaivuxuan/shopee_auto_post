"""Tạo phụ đề ASS từ script VI và burn-in bằng FFmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import douyin_quality

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "douyin" / "processed"


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise RuntimeError(f"FFmpeg lỗi: {err}")


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", "\\N")
    )


def _karaoke_chunks(text: str, min_words: int = 2, max_words: int = 5) -> list[str]:
    """Tách câu thành cụm ngắn kiểu phụ đề karaoke Shorts."""
    words = [w for w in (text or "").split() if w]
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]
    chunks: list[str] = []
    i = 0
    while i < len(words):
        remain = len(words) - i
        n = max_words if remain > max_words + min_words else remain
        if remain <= max_words:
            n = remain
        elif remain < min_words + max_words:
            n = max(min_words, remain // 2)
        chunks.append(" ".join(words[i : i + n]))
        i += n
    return chunks


def _pick_font() -> str:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    return ""


def build_ass(
    script: dict,
    *,
    video_id: str = "",
    voice_meta: dict | None = None,
    fade_in_ms: int = 250,
    fade_out_ms: int = 550,
    hold_after_sec: float = 0.2,
) -> Path:
    """Tạo ASS: hiện khi TTS nói, đọc xong thì mờ dần rồi ẩn (không giữ hết clip)."""
    vid = str(video_id or script.get("video_id") or "")
    out_dir = PROCESSED / vid
    out_dir.mkdir(parents=True, exist_ok=True)
    ass_path = out_dir / "subs.ass"
    font = "Noto Sans"
    font_file = _pick_font()
    if font_file and "DejaVu" in font_file:
        font = "DejaVu Sans"
    elif font_file and "Liberation" in font_file:
        font = "Liberation Sans"

    # map index → thời lượng TTS thật
    speak_dur: dict[int, float] = {}
    for piece in (voice_meta or {}).get("pieces") or []:
        try:
            speak_dur[int(piece["index"])] = float(piece.get("duration") or 0)
        except (KeyError, TypeError, ValueError):
            continue

    fade_in_ms = max(0, int(fade_in_ms))
    fade_out_ms = max(0, int(fade_out_ms))
    fad_tag = f"{{\\fad({fade_in_ms},{fade_out_ms})}}" if (fade_in_ms or fade_out_ms) else ""

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{douyin_quality.SUB_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0.5,0,1,{douyin_quality.SUB_OUTLINE},1,2,48,48,{douyin_quality.SUB_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    timing_log = []
    for line in script.get("lines") or []:
        raw = str(line.get("text") or "").strip()
        if not raw:
            continue
        idx = int(line.get("index") or 0)
        start_sec = float(line["out_start"])
        clip_end = float(line["out_end"])
        spoken = speak_dur.get(idx) or 0.0
        if spoken > 0.3:
            speak_end = start_sec + spoken + max(0.0, float(hold_after_sec))
        else:
            chars = len(raw)
            speak_end = start_sec + max(2.0, chars / 11.0) + max(0.0, float(hold_after_sec))
        speak_end = min(clip_end, max(start_sec + 0.4, speak_end))
        min_len = (fade_in_ms + fade_out_ms) / 1000.0 + 0.15
        if speak_end - start_sec < min_len:
            speak_end = min(clip_end, start_sec + min_len)

        # Karaoke: tách cụm 2–5 từ, chia đều thời gian đọc
        chunks = _karaoke_chunks(raw)
        span = max(0.35, speak_end - start_sec)
        weights = [max(1, len(c.split())) for c in chunks]
        wsum = float(sum(weights)) or 1.0
        cursor = start_sec
        for ci, chunk in enumerate(chunks):
            piece = span * (weights[ci] / wsum)
            c_end = speak_end if ci == len(chunks) - 1 else min(speak_end, cursor + piece)
            if c_end - cursor < 0.25 and ci < len(chunks) - 1:
                continue
            text = _escape_ass(chunk)
            # fade ngắn hơn cho cụm karaoke
            kfad = f"{{\\fad(120,180)}}" if len(chunks) > 1 else fad_tag
            events.append(
                f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(c_end)},Default,,0,0,0,,{kfad}{text}"
            )
            timing_log.append(
                {
                    "index": idx,
                    "chunk": ci,
                    "start": round(cursor, 3),
                    "end": round(c_end, 3),
                    "text": chunk,
                    "speak_duration": round(spoken, 3),
                }
            )
            cursor = c_end
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    meta = {
        "ass": str(ass_path),
        "font_file": font_file,
        "font": font,
        "fade_in_ms": fade_in_ms,
        "fade_out_ms": fade_out_ms,
        "events": timing_log,
    }
    (out_dir / "subs.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return ass_path


def burn_subtitles(
    video_path: Path,
    ass_path: Path,
    *,
    video_id: str = "",
    force: bool = False,
) -> Path:
    vid = str(video_id or video_path.stem)
    out_dir = PROCESSED / vid
    out_path = out_dir / "output_ai.mp4"
    if out_path.is_file() and not force:
        return out_path

    if not shutil.which("ffmpeg"):
        raise RuntimeError("Chưa cài ffmpeg.")

    # Escape path cho filter subtitles (dấu : và \)
    ass = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    font_file = ""
    meta_path = out_dir / "subs.json"
    if meta_path.is_file():
        try:
            font_file = str(json.loads(meta_path.read_text(encoding="utf-8")).get("font_file") or "")
        except json.JSONDecodeError:
            font_file = ""
    vf = f"subtitles='{ass}'"
    if font_file and Path(font_file).is_file():
        fonts_dir = str(Path(font_file).parent.resolve()).replace("\\", "/").replace(":", "\\:")
        vf = f"subtitles='{ass}':fontsdir='{fonts_dir}'"

    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            vf,
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
            str(out_path),
        ]
    )
    return out_path
