"""Orchestrate pipeline: ASR → highlight → cut → script/TTS → subtitle → output_ai.mp4."""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import douyin_asr
import douyin_context
import douyin_cut
import douyin_highlight
import douyin_poster
import douyin_quality
import douyin_subtitle
import douyin_voice
import progress

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "douyin"
PROCESSED = DATA / "processed"
VN_TZ = timezone(timedelta(hours=7))
# Tham chiếu Shorts mẫu ~2.5 phút (vd. cnJblXj7EUk); hard cap 3 phút.
TARGET_SECONDS = 150
MAX_SECONDS = 180
DEFAULT_VOICE = douyin_voice.DEFAULT_VOICE


def now_str() -> str:
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def resolve_video(video_id: str) -> Path:
    path = douyin_poster.media_path(video_id)
    if path:
        return Path(path)
    preferred = DATA / "videos" / f"{video_id}.mp4"
    if preferred.is_file():
        return preferred
    matches = sorted((DATA / "videos").glob(f"{video_id}.*"))
    for item in matches:
        if item.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            return item
    raise FileNotFoundError(f"Không tìm thấy video id={video_id}")


def process_video(
    video_id: str,
    *,
    model: str = douyin_quality.WHISPER_MODEL,
    target_seconds: float = TARGET_SECONDS,
    max_seconds: float = MAX_SECONDS,
    voice: str = "",
    pitch: str = douyin_voice.DEFAULT_PITCH,
    provider: str = douyin_quality.TTS_PROVIDER,
    bgm_volume: float = douyin_quality.MUX_BGM_VOLUME,
    force: bool = False,
) -> dict:
    video_id = str(video_id).strip()
    out_dir = PROCESSED / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    steps = progress.empty_steps(progress.AI_STEP_DEFS)
    meta = {
        "video_id": video_id,
        "status": "running",
        "started_at": now_str(),
        "message": "Đang xử lý",
        "current_step": "",
        "steps": steps,
    }
    _write_json(meta_path, meta)

    def _go(step_id: str, message: str) -> None:
        meta["current_step"] = step_id
        meta["message"] = message
        progress.begin_step(meta["steps"], step_id, detail=message)
        _write_json(meta_path, meta)

    def _ok(step_id: str, detail: dict | str = "") -> None:
        text = detail if isinstance(detail, str) else progress._brief(detail if isinstance(detail, dict) else {})
        extra = detail if isinstance(detail, dict) else {}
        progress.finish_step(meta["steps"], step_id, detail=text)
        if isinstance(extra, dict):
            meta["steps"][step_id].update({k: v for k, v in extra.items() if k not in ("status", "label", "error")})
        _write_json(meta_path, meta)

    try:
        source = resolve_video(video_id)
        meta["source"] = str(source)

        topic = douyin_context.load_topic(video_id)
        meta["topic"] = {
            "topic_vi": topic.get("topic_vi"),
            "topic_zh": topic.get("topic_zh"),
            "has_caption_vi": bool(topic.get("caption_vi")),
        }

        _go("asr", f"ASR (faster-whisper {model})")
        transcript = douyin_asr.transcribe(
            source,
            video_id=video_id,
            model_size=model,
            initial_prompt=topic.get("asr_prompt") or "",
            force=force,
        )
        _ok("asr", {
            "model": transcript.get("model"),
            "duration": transcript.get("duration"),
            "segments": len(transcript.get("segments") or []),
            "initial_prompt": bool(topic.get("asr_prompt")),
        })

        _go("highlight", "Chọn highlight")
        highlights = douyin_highlight.select_highlights(
            transcript,
            target_seconds=target_seconds,
            max_seconds=max_seconds,
            topic_vi=topic.get("topic_vi") or "",
            topic_zh=topic.get("topic_zh") or "",
            title_zh=topic.get("title_zh") or "",
            force=force,
        )
        _ok("highlight", {
            "provider": highlights.get("provider"),
            "model": highlights.get("model"),
            "total_seconds": highlights.get("total_seconds"),
            "clips": len(highlights.get("clips") or []),
            "summary_vi": highlights.get("summary_vi") or "",
        })

        _go("cut", "Cắt video")
        cut = douyin_cut.cut_highlights(source, highlights, video_id=video_id, force=force)
        _ok("cut", {"duration": cut.get("duration"), "parts": len(cut.get("timeline") or [])})

        _go("script", "Viết kịch bản VI")
        script = douyin_voice.generate_script(
            cut,
            highlights,
            title=topic.get("title_zh") or "",
            description=topic.get("description_zh") or "",
            caption_vi=topic.get("caption_vi") or "",
            topic_vi=topic.get("topic_vi") or "",
            force=force,
        )
        _ok("script", {
            "provider": script.get("provider"),
            "model": script.get("model"),
            "lines": len(script.get("lines") or []),
            "theme_check": script.get("theme_check") or "",
        })

        _go("voice", "TTS lồng tiếng")
        resolved = douyin_voice._resolve_provider(provider)
        # Mặc định luôn nam miền Bắc: Piper speaker 2 / FPT leminh
        if voice and str(voice).strip():
            tts_voice = str(voice).strip()
        elif resolved == "piper":
            tts_voice = douyin_voice.DEFAULT_PIPER_SPEAKER
        elif resolved == "fpt":
            tts_voice = douyin_voice.DEFAULT_FPT_VOICE
        else:
            tts_voice = douyin_voice.DEFAULT_EDGE_VOICE
        voice_meta = douyin_voice.synthesize_voice(
            script,
            voice=tts_voice,
            pitch=pitch,
            provider=resolved if provider == "auto" else provider,
            force=force,
        )
        _ok("voice", {
            "provider": voice_meta.get("provider"),
            "voice": voice_meta.get("voice"),
            "accent": voice_meta.get("accent"),
            "pitch": voice_meta.get("pitch"),
            "duration": voice_meta.get("duration"),
        })

        _go("mux", "Ghép audio vào video")
        voiced = douyin_voice.mux_voice(
            Path(cut["output"]),
            voice_meta,
            video_id=video_id,
            bgm_volume=bgm_volume,
            force=force,
        )
        _ok("mux", {"output": Path(voiced).name if voiced else ""})

        _go("subtitle", "Burn phụ đề")
        ass = douyin_subtitle.build_ass(script, video_id=video_id, voice_meta=voice_meta)
        output = douyin_subtitle.burn_subtitles(voiced, ass, video_id=video_id, force=force)
        _ok("subtitle", {"output": Path(output).name})

        meta.update(
            {
                "status": "done",
                "message": "Đã tạo xong video ngắn",
                "current_step": "",
                "finished_at": now_str(),
                "output": str(output),
                "providers": {
                    "highlight": highlights.get("provider"),
                    "script": script.get("provider"),
                    "asr": transcript.get("model"),
                    "tts": voice_meta.get("provider") or voice,
                },
            }
        )
        _write_json(meta_path, meta)
        return meta
    except Exception as exc:  # noqa: BLE001
        step = meta.get("current_step") or ""
        if step:
            progress.fail_step(meta["steps"], step, error=str(exc)[:400])
        meta.update(
            {
                "status": "error",
                "message": str(exc)[:500],
                "finished_at": now_str(),
                "traceback": traceback.format_exc()[-2000:],
            }
        )
        _write_json(meta_path, meta)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline Douyin AI: cắt + TTS + phụ đề")
    parser.add_argument("--video-id", required=True, help="ID video trong data/douyin/videos")
    parser.add_argument(
        "--model",
        default=douyin_quality.WHISPER_MODEL,
        help="faster-whisper model (mặc định large-v3 — chất lượng cao)",
    )
    parser.add_argument("--target", type=float, default=TARGET_SECONDS, help="Mục tiêu giây")
    parser.add_argument("--max", type=float, default=MAX_SECONDS, help="Trần giây")
    parser.add_argument(
        "--provider",
        default=douyin_quality.TTS_PROVIDER,
        choices=["auto", "piper", "fpt", "edge"],
        help="Mặc định auto (FPT→Edge neural, ưu tiên chất lượng)",
    )
    parser.add_argument(
        "--voice",
        default="",
        help="Để trống = tự chọn theo provider. FPT: leminh | Edge: vi-VN-NamMinhNeural | Piper: 2",
    )
    parser.add_argument(
        "--pitch",
        default=douyin_voice.DEFAULT_PITCH,
        help='Chỉ dùng với Edge, vd. "-18Hz"',
    )
    parser.add_argument(
        "--bgm",
        type=float,
        default=douyin_quality.MUX_BGM_VOLUME,
        help="Volume BGM gốc 0..1 (mặc định thấp hơn để lời TTS rõ)",
    )
    parser.add_argument("--force", action="store_true", help="Chạy lại bỏ cache bước")
    args = parser.parse_args()
    meta = process_video(
        args.video_id,
        model=args.model,
        target_seconds=args.target,
        max_seconds=args.max,
        voice=args.voice,
        pitch=args.pitch,
        provider=args.provider,
        bgm_volume=args.bgm,
        force=args.force,
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
