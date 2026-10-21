"""Viết kịch bản VI (LLM) + TTS edge-tts + mux vào video cắt."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import douyin_llm
import douyin_quality

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "douyin" / "processed"
# Edge TTS neural — chất lượng cao, luôn sẵn (không cần API key).
DEFAULT_EDGE_VOICE = "vi-VN-NamMinhNeural"
DEFAULT_PITCH = "-18Hz"
DEFAULT_RATE = "-15%"  # chậm vừa — rõ chữ, truyền cảm
# FPT leminh = nam miền Bắc (cần fpt_api_key) — ưu tiên khi auto.
DEFAULT_FPT_VOICE = "leminh"
DEFAULT_FPT_SPEED = "-1"  # FPT: -3..3, số âm = chậm hơn
# Piper local: speaker 2 = Quang Huy nam Bắc (CakeByVPBank v3) — fallback offline.
DEFAULT_PIPER_SPEAKER = "2"
DEFAULT_PROVIDER = douyin_quality.TTS_PROVIDER  # auto | piper | fpt | edge
# Piper speaker 2 @ length_scale 1.38 ≈ ~20 ký tự/giây audio (đo thực tế)
CHARS_PER_SEC = 20.0
NARRATION_SLOT_SEC = 5.5  # gộp shot ngắn thành mốc lời ~5–7s
DEFAULT_VOICE = DEFAULT_EDGE_VOICE


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
    try:
        return float((proc.stdout or "").strip() or 0)
    except ValueError:
        return 0.0


def _narration_slots(timeline: list[dict], slot_sec: float = NARRATION_SLOT_SEC) -> list[dict]:
    """Gộp shot montage thành mốc lời ~6s (VO liên tục, ~20–30 câu / 2.5 phút)."""
    if not timeline:
        return []
    slots: list[dict] = []
    buf: list[dict] = []
    acc = 0.0
    for item in timeline:
        buf.append(item)
        acc += float(item.get("duration") or 0)
        if acc >= slot_sec:
            slots.append(_slot_from_buf(buf, len(slots)))
            buf, acc = [], 0.0
    if buf:
        if slots and acc < slot_sec * 0.45:
            # gộp phần dư ngắn vào slot cuối
            prev = slots[-1]
            merged = list(prev["_items"]) + buf
            slots[-1] = _slot_from_buf(merged, prev["index"])
        else:
            slots.append(_slot_from_buf(buf, len(slots)))
    for slot in slots:
        slot.pop("_items", None)
    return slots


def _slot_from_buf(buf: list[dict], index: int) -> dict:
    start = float(buf[0]["out_start"])
    end = float(buf[-1]["out_end"])
    beats = [b.get("beat_name") or b.get("beat") for b in buf if b.get("beat_name") or b.get("beat")]
    beat_name = str(beats[0] if beats else "")
    role = "thao tác chính"
    if index == 0 or beat_name in {"hook", "1"}:
        role = "hook phản trực giác"
    elif beat_name in {"bridge", "4"}:
        role = "câu cầu nối + định nghĩa nghề"
    elif beat_name in {"core", "5"}:
        role = "giải thích thao tác lõi khớp hình"
    elif beat_name in {"meaning", "6"}:
        role = "ý nghĩa văn hóa / cảm xúc"
    elif beat_name in {"cta", "7"}:
        role = "kết ẩn dụ + CTA ngắn (không hashtag)"
    dur = max(0.5, end - start)
    return {
        "index": index,
        "out_start": round(start, 3),
        "out_end": round(end, 3),
        "duration": round(dur, 3),
        "max_chars": max(24, int(dur * CHARS_PER_SEC)),
        "beat_name": beat_name,
        "role_hint": role,
        "visual_hint": (buf[0].get("text") or "")[:120],
        "_items": buf,
    }


def _script_prompt(
    cut: dict,
    highlights: dict,
    *,
    title: str = "",
    description: str = "",
    caption_vi: str = "",
    topic_vi: str = "",
    slots: list[dict] | None = None,
) -> str:
    parts = []
    source = slots if slots is not None else _narration_slots(list(cut.get("timeline") or []))
    for item in source:
        parts.append(
            {
                "index": item["index"],
                "duration_sec": item["duration"],
                "max_chars": item.get("max_chars") or max(24, int(float(item["duration"]) * CHARS_PER_SEC)),
                "beat_name": item.get("beat_name") or "",
                "role_hint": item.get("role_hint") or "",
                "visual_hint": item.get("visual_hint") or item.get("text") or "",
            }
        )
    summary = highlights.get("summary_vi") or highlights.get("summary_zh") or ""
    return (
        "Bạn viết LỜI THUYẾT MINH tiếng Việt cho Shorts di sản/thủ công "
        "(công thức BIẾT HAY CHƯA / cnJblXj7EUk).\n"
        "NGUỒN SỰ THẬT (bắt buộc bám theo):\n"
        f"1) caption_vi đã dịch: {caption_vi or topic_vi or '(trống)'}\n"
        f"2) topic_vi: {topic_vi or '(trống)'}\n"
        f"3) title_zh: {title or '(trống)'}\n"
        f"4) description_zh: {description or '(trống)'}\n"
        f"5) summary biên tập: {summary or '(trống)'}\n\n"
        "CẤU TRÚC BẮT BUỘC (6 lớp, trải theo các index):\n"
        "1) Hook phản trực giác (index đầu)\n"
        "2) Giải thích từng bước khớp hình\n"
        "3) Một câu cầu nối trước đoạn kỹ thuật lõi\n"
        "4) Định nghĩa tên nghề + biệt danh cảm xúc\n"
        "5) Kết cảm xúc (ẩn dụ)\n"
        "6) CTA ngắn — không hashtag, không emoji\n\n"
        "QUY TẮC:\n"
        "- Giọng MIỀN BẮC, chậm, truyền cảm; phủ lời gần như liên tục (≥90% thời lượng).\n"
        "- Mỗi dòng đúng 1 index; độ dài GẦN max_chars (không viết câu quá ngắn — "
        "phải đủ để đọc gần hết duration_sec giây).\n"
        "- 1–2 ý / câu, giàu hình ảnh, khớp thao tác đang chiếu.\n"
        "- Khớp CHỦ ĐỀ caption_vi; cấm bịa lệch chủ đề dù visual_hint nhiễu.\n"
        "- Các dòng nối thành câu chuyện liền mạch; CTA không gắn sai quốc gia.\n"
        "Trả về JSON:\n"
        '{"lines":[{"index":0,"text":"..."}],"theme_check":"một câu xác nhận chủ đề"}\n'
        f"Các mốc cần viết lời:\n{json.dumps(parts, ensure_ascii=False)}"
    )


def generate_script(
    cut: dict,
    highlights: dict,
    *,
    title: str = "",
    description: str = "",
    caption_vi: str = "",
    topic_vi: str = "",
    force: bool = False,
) -> dict:
    video_id = str(cut.get("video_id") or highlights.get("video_id") or "")
    out_dir = PROCESSED / video_id
    out_path = out_dir / "script_vi.json"
    if out_path.is_file() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))

    timeline = list(cut.get("timeline") or [])
    slots = _narration_slots(timeline)
    provider = "heuristic"
    model = ""
    errors: list[str] = []
    by_index: dict[int, str] = {}

    theme_check = ""
    try:
        result = douyin_llm.chat_json(
            _script_prompt(
                cut,
                highlights,
                title=title,
                description=description,
                caption_vi=caption_vi,
                topic_vi=topic_vi,
                slots=slots,
            ),
            temperature=douyin_quality.SCRIPT_TEMPERATURE,
        )
        provider = result["provider"]
        model = result["model"]
        errors = list(result.get("errors") or [])
        theme_check = str(result["data"].get("theme_check") or "")
        for row in result["data"].get("lines") or []:
            if isinstance(row, dict) and "index" in row:
                by_index[int(row["index"])] = str(row.get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc)[:300])

    lines = []
    for item in slots:
        idx = int(item["index"])
        text = by_index.get(idx) or ""
        if not text:
            text = (
                topic_vi
                or caption_vi
                or highlights.get("summary_vi")
                or title
                or "Khám phá nghề thủ công truyền thống."
            ).strip()
            text = text[: max(12, int(float(item["duration"]) * CHARS_PER_SEC))]
        lines.append(
            {
                "index": idx,
                "text": text,
                "out_start": item["out_start"],
                "out_end": item["out_end"],
                "duration": item["duration"],
                "beat_name": item.get("beat_name") or "",
                "role_hint": item.get("role_hint") or "",
            }
        )

    payload = {
        "video_id": video_id,
        "formula": "cong_thuc_shorts_6lop_vo",
        "voice": DEFAULT_VOICE,
        "provider": provider,
        "model": model,
        "theme_check": theme_check,
        "topic_vi": topic_vi,
        "caption_vi": caption_vi,
        "errors": errors,
        "slots": len(slots),
        "lines": lines,
    }
    _write_json(out_path, payload)
    return payload


async def _synthesize_one(
    text: str,
    out_mp3: Path,
    voice: str,
    *,
    pitch: str = DEFAULT_PITCH,
    rate: str = DEFAULT_RATE,
) -> None:
    import edge_tts

    last_exc: Exception | None = None
    # Một số pitch/câu dài đôi khi Edge trả NoAudio — thử lại và hạ pitch dần
    pitches = [pitch, "-10Hz", "+0Hz"]
    seen = []
    for p in pitches:
        if p in seen:
            continue
        seen.append(p)
        try:
            communicate = edge_tts.Communicate(text, voice=voice, pitch=p, rate=rate)
            await communicate.save(str(out_mp3))
            if out_mp3.is_file() and out_mp3.stat().st_size > 0:
                return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    raise RuntimeError(f"edge-tts không tạo được audio: {last_exc}")


def _resolve_provider(provider: str) -> str:
    import douyin_tts_fpt
    import douyin_tts_piper

    name = (provider or DEFAULT_PROVIDER).strip().lower() or "auto"
    if name == "auto":
        # Ưu tiên chất lượng giọng: FPT (nam Bắc) → Edge neural → Piper local
        if douyin_tts_fpt.configured():
            return "fpt"
        return "edge"
    if name == "piper" and not douyin_tts_piper.configured():
        if douyin_tts_fpt.configured():
            return "fpt"
        return "edge"
    return name


def synthesize_voice(
    script: dict,
    *,
    voice: str = DEFAULT_VOICE,
    pitch: str = DEFAULT_PITCH,
    rate: str = DEFAULT_RATE,
    provider: str = DEFAULT_PROVIDER,
    force: bool = False,
) -> dict:
    import douyin_tts_fpt
    import douyin_tts_piper

    video_id = str(script.get("video_id") or "")
    out_dir = PROCESSED / video_id
    voice_dir = out_dir / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "voice.json"
    if meta_path.is_file() and not force:
        return json.loads(meta_path.read_text(encoding="utf-8"))

    used_provider = _resolve_provider(provider)
    piper_speaker = DEFAULT_PIPER_SPEAKER
    rate = rate or DEFAULT_RATE
    # FPT: leminh = nam Bắc; Piper: speaker id; Edge: NamMinh
    if used_provider == "fpt":
        tts_voice = voice if voice in {
            "leminh", "banmai", "thuminh", "lannhi", "myan", "giahuy", "linhsan", "minhquang", "ngoclam"
        } else DEFAULT_FPT_VOICE
    elif used_provider == "piper":
        tts_voice = f"piper-speaker-{voice if str(voice).isdigit() else piper_speaker}"
        piper_speaker = voice if str(voice).isdigit() else DEFAULT_PIPER_SPEAKER
    else:
        tts_voice = voice if str(voice).startswith("vi-VN-") else DEFAULT_EDGE_VOICE

    pieces = []
    for line in script.get("lines") or []:
        idx = int(line["index"])
        mp3 = voice_dir / f"line_{idx:03d}.mp3"
        wav = voice_dir / f"line_{idx:03d}.wav"
        text = (line.get("text") or "").strip() or " "
        if force or not mp3.is_file():
            if used_provider == "piper":
                douyin_tts_piper.synthesize_to_mp3(
                    text,
                    mp3,
                    speaker_id=int(piper_speaker),
                    length_scale=douyin_tts_piper.DEFAULT_LENGTH_SCALE,
                )
            elif used_provider == "fpt":
                douyin_tts_fpt.synthesize_to_mp3(
                    text, mp3, voice=tts_voice, speed=DEFAULT_FPT_SPEED
                )
            else:
                asyncio.run(_synthesize_one(text, mp3, tts_voice, pitch=pitch, rate=rate))
        # Chuẩn hóa wav + chỉ tăng tốc nhẹ nếu dài hơn clip (giữ nhịp chậm)
        target = max(0.8, float(line.get("duration") or 1))
        raw_dur = probe_duration(mp3) or target
        tempo = 1.0
        if raw_dur > target * 1.12:
            tempo = min(1.08, raw_dur / target)
        af = f"atempo={tempo:.3f}" if abs(tempo - 1.0) > 0.02 else "anull"
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3),
                "-af",
                af,
                "-ar",
                "44100",
                "-ac",
                "2",
                str(wav),
            ]
        )
        dur = probe_duration(wav) or (raw_dur / tempo)
        pieces.append(
            {
                "index": idx,
                "text": text,
                "file": str(wav),
                "duration": round(dur, 3),
                "out_start": line["out_start"],
                "out_end": line["out_end"],
                "tempo": round(tempo, 3),
            }
        )

    # Ghép TTS theo timeline: silence pad + concat
    total = float((script.get("lines") or [{}])[-1].get("out_end") or 0) if script.get("lines") else 0
    if not total and pieces:
        total = max(float(p["out_end"]) for p in pieces)
    concat_list = voice_dir / "tts_concat.txt"
    built: list[Path] = []
    cursor = 0.0
    for piece in pieces:
        start = float(piece["out_start"])
        gap = start - cursor
        if gap > 0.05:
            silence = voice_dir / f"silence_{len(built):03d}.wav"
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=stereo",
                    "-t",
                    f"{gap:.3f}",
                    str(silence),
                ]
            )
            built.append(silence)
            cursor += gap
        built.append(Path(piece["file"]))
        cursor = start + float(piece["duration"])

    tts_wav = voice_dir / "tts_full.wav"
    if len(built) == 1:
        shutil.copy2(built[0], tts_wav)
    else:
        concat_list.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in built) + "\n",
            encoding="utf-8",
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(tts_wav),
            ]
        )

    payload = {
        "video_id": video_id,
        "provider": used_provider,
        "voice": tts_voice,
        "pitch": pitch if used_provider == "edge" else "",
        "rate": rate if used_provider == "edge" else "",
        "length_scale": (
            douyin_tts_piper.DEFAULT_LENGTH_SCALE if used_provider == "piper" else None
        ),
        "fpt_speed": DEFAULT_FPT_SPEED if used_provider == "fpt" else None,
        "accent": (
            "bac"
            if used_provider == "piper"
            or (used_provider == "fpt" and tts_voice == "leminh")
            else "general"
        ),
        "tts_wav": str(tts_wav),
        "duration": round(probe_duration(tts_wav) or cursor, 3),
        "pieces": pieces,
    }
    _write_json(meta_path, payload)
    return payload


def _has_audio(path: Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return bool((proc.stdout or "").strip())


def mux_voice(
    cut_video: Path,
    voice_meta: dict,
    *,
    video_id: str = "",
    bgm_volume: float = douyin_quality.MUX_BGM_VOLUME,
    tts_volume: float = douyin_quality.MUX_TTS_VOLUME,
    force: bool = False,
) -> Path:
    """Trộn TTS với BGM gốc.

    TTS nổi hơn BGM (ưu tiên nghe rõ lời); sidechain duck BGM khi có giọng.
    """
    vid = str(video_id or voice_meta.get("video_id") or cut_video.stem)
    out_dir = PROCESSED / vid
    out_path = out_dir / "voiced.mp4"
    if out_path.is_file() and not force:
        return out_path

    tts = Path(voice_meta["tts_wav"])
    bgm = max(0.0, min(1.0, float(bgm_volume)))
    tts_vol = max(0.0, min(1.5, float(tts_volume)))
    use_bgm = bgm > 0.001 and _has_audio(cut_video)
    video_dur = probe_duration(cut_video)
    # Giữ đủ độ dài video; pad TTS bằng silence nếu ngắn hơn
    if use_bgm:
        # sidechaincompress: lúc có giọng thì BGM hạ nhẹ, hết giọng thì BGM trồi lại
        filt = (
            f"[0:a]volume={bgm}[bg];"
            f"[1:a]volume={tts_vol},apad[voice];"
            f"[voice]asplit=2[sc][vox];"
            f"[bg][sc]sidechaincompress="
            f"threshold=0.012:ratio=3.5:attack=40:release=420:makeup=1[ducked];"
            f"[ducked][vox]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(cut_video),
            "-i",
            str(tts),
            "-filter_complex",
            filt,
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            douyin_quality.MUX_AUDIO_BITRATE,
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(cut_video),
            "-i",
            str(tts),
            "-filter_complex",
            f"[1:a]volume={tts_vol},apad[a]",
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            douyin_quality.MUX_AUDIO_BITRATE,
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
        ]
    if video_dur > 0:
        cmd.extend(["-t", f"{video_dur:.3f}"])
    cmd.append(str(out_path))
    _run(cmd)
    return out_path
