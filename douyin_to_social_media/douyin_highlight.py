"""Chọn đoạn highlight theo công thức 7 beat (montage Shorts thuyết minh)."""

from __future__ import annotations

import json
from pathlib import Path

import douyin_llm

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "douyin" / "processed"
TARGET_SECONDS = 150
MAX_SECONDS = 180

# Tỷ lệ beat trên timeline ĐẦU RA (docs/CONG_THUC_SHORTS_THUYET_MINH.md)
BEATS = [
    {"beat": 1, "name": "hook", "frac": 0.08, "role": "Hook — cảnh mở bất ngờ / nguyên liệu lạ"},
    {"beat": 2, "name": "prep", "frac": 0.13, "role": "Chuẩn bị — rửa, chọn, nghiền, chuẩn bị liệu"},
    {"beat": 3, "name": "transform", "frac": 0.17, "role": "Pha & biến đổi — trộn, màu, lò/nhiệt"},
    {"beat": 4, "name": "bridge", "frac": 0.10, "role": "Cầu nối kỹ thuật — kéo thanh / chuẩn bị bước lõi"},
    {"beat": 5, "name": "core", "frac": 0.27, "role": "Lõi nghề — thao tác chính cận cảnh (dài nhất)"},
    {"beat": 6, "name": "meaning", "frac": 0.18, "role": "Ý nghĩa — thành phẩm + giá trị văn hóa"},
    {"beat": 7, "name": "cta", "frac": 0.07, "role": "Kết + CTA — ẩn dụ cảm xúc"},
]

# Vị trí tương đối trên video NGUỒN để lấy cảnh cho từng beat
SOURCE_WINDOWS = [
    (0.00, 0.10),
    (0.08, 0.22),
    (0.20, 0.38),
    (0.35, 0.50),
    (0.48, 0.75),
    (0.72, 0.92),
    (0.88, 1.00),
]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _duration_of(segments: list[dict]) -> float:
    return sum(max(0.0, float(s["end"]) - float(s["start"])) for s in segments)


def _beat_budgets(target: float) -> list[dict]:
    budgets = []
    for spec in BEATS:
        budgets.append({**spec, "seconds": round(float(target) * float(spec["frac"]), 2)})
    # chỉnh tổng cho khớp target
    total = sum(b["seconds"] for b in budgets)
    if budgets and abs(total - target) > 0.5:
        budgets[-1]["seconds"] = round(max(5.0, budgets[-1]["seconds"] + (target - total)), 2)
    return budgets


def _heuristic_pick(
    segments: list[dict],
    *,
    target: float,
    max_seconds: float,
    duration: float = 0.0,
    topic_vi: str = "",
) -> list[dict]:
    """7 cửa sổ theo vị trí nguồn + ngân sách beat."""
    duration = float(duration or 0)
    if duration <= 0 and segments:
        duration = float(segments[-1]["end"])
    if duration <= 0:
        return []
    budgets = _beat_budgets(min(target, max_seconds))
    picked = []
    total = 0.0
    for i, budget in enumerate(budgets):
        lo, hi = SOURCE_WINDOWS[i]
        want = float(budget["seconds"])
        if total + want > max_seconds:
            want = max(5.0, max_seconds - total)
        center = (lo + hi) / 2.0 * duration
        start = max(0.0, center - want / 2.0)
        # neo gần đầu cửa sổ nguồn
        start = max(lo * duration, min(start, max(0.0, hi * duration - want)))
        end = min(duration, start + want)
        if end - start < 4:
            continue
        picked.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": topic_vi or "",
                "score": 70,
                "reason": f"beat_{budget['beat']}_{budget['name']}",
                "beat": budget["beat"],
                "beat_name": budget["name"],
            }
        )
        total += end - start
        if total >= max_seconds * 0.98:
            break
    return picked


def _merge_adjacent(clips: list[dict], gap: float = 0.35) -> list[dict]:
    if not clips:
        return []
    ordered = sorted(clips, key=lambda c: float(c["start"]))
    merged = [dict(ordered[0])]
    for clip in ordered[1:]:
        prev = merged[-1]
        # Không gộp khác beat
        if prev.get("beat") and clip.get("beat") and prev.get("beat") != clip.get("beat"):
            merged.append(dict(clip))
            continue
        if float(clip["start"]) - float(prev["end"]) <= gap:
            prev["end"] = max(float(prev["end"]), float(clip["end"]))
            prev["text"] = f"{prev.get('text', '')} {clip.get('text', '')}".strip()
            prev["score"] = max(float(prev.get("score") or 0), float(clip.get("score") or 0))
        else:
            merged.append(dict(clip))
    return merged


def _normalize_clips(
    raw_clips: list,
    segments: list[dict],
    *,
    max_seconds: float,
    target_seconds: float,
) -> list[dict]:
    by_id = {int(s["id"]): s for s in segments if "id" in s}
    clips = []
    for item in raw_clips or []:
        if not isinstance(item, dict):
            continue
        start = item.get("start")
        end = item.get("end")
        seg_ids = item.get("segment_ids") or item.get("ids") or []
        text = str(item.get("text") or "")
        if seg_ids and (start is None or end is None):
            chosen = [by_id[int(i)] for i in seg_ids if int(i) in by_id]
            if not chosen:
                continue
            start = min(float(s["start"]) for s in chosen)
            end = max(float(s["end"]) for s in chosen)
            if not text:
                text = " ".join(s["text"] for s in chosen)
        else:
            if start is None or end is None:
                continue
            start, end = float(start), float(end)
        if end <= start:
            continue
        beat = item.get("beat")
        try:
            beat_i = int(beat) if beat is not None else 0
        except (TypeError, ValueError):
            beat_i = 0
        clips.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "score": float(item.get("score") or 0),
                "reason": str(item.get("reason") or ""),
                "beat": beat_i or None,
                "beat_name": str(item.get("beat_name") or item.get("name") or ""),
            }
        )
    clips = _merge_adjacent(clips)
    # Giữ thứ tự thời gian (câu chuyện); cắt bớt beat giữa nếu vượt max
    ordered = sorted(clips, key=lambda c: float(c["start"]))
    total = sum(float(c["end"]) - float(c["start"]) for c in ordered)
    if total <= max_seconds:
        return ordered

    # Rút từ beat 2–3 trước, giữ 1,5,6,7
    shrinkable = {2, 3, 4}
    while total > max_seconds and ordered:
        candidates = [
            i
            for i, c in enumerate(ordered)
            if (c.get("beat") in shrinkable) or (c.get("beat") is None and 0 < i < len(ordered) - 1)
        ]
        if not candidates:
            # cắt đuôi clip dài nhất không phải đầu/cuối
            mid = ordered[1:-1] if len(ordered) > 2 else ordered
            if not mid:
                break
            longest = max(mid, key=lambda c: float(c["end"]) - float(c["start"]))
            idx = ordered.index(longest)
            candidates = [idx]
        idx = candidates[0]
        clip = dict(ordered[idx])
        dur = float(clip["end"]) - float(clip["start"])
        overflow = total - max_seconds
        new_dur = max(6.0, dur - overflow)
        clip["end"] = round(float(clip["start"]) + new_dur, 3)
        ordered[idx] = clip
        total = sum(float(c["end"]) - float(c["start"]) for c in ordered)
        if new_dur <= 6.0 and clip.get("beat") in shrinkable and len(ordered) > 4:
            # bỏ hẳn beat phụ nếu vẫn thừa
            removed = ordered.pop(idx)
            total -= float(removed["end"]) - float(removed["start"])
            if 2 in shrinkable:
                shrinkable.discard(2)
            elif 3 in shrinkable:
                shrinkable.discard(3)
            else:
                shrinkable.discard(4)
    return ordered


def _prompt(
    transcript: dict,
    *,
    target: float,
    max_seconds: float,
    topic_vi: str = "",
    topic_zh: str = "",
    title_zh: str = "",
) -> str:
    import douyin_quality

    seg_limit = max(40, douyin_quality.HIGHLIGHT_SEG_LIMIT)
    text_chars = max(40, douyin_quality.HIGHLIGHT_TEXT_CHARS)
    compact = [
        {
            "id": s["id"],
            "start": s["start"],
            "end": s["end"],
            "text": (s.get("text") or "")[:text_chars],
        }
        for s in (transcript.get("segments") or [])[:seg_limit]
    ]
    duration = float(transcript.get("duration") or 0)
    budgets = _beat_budgets(min(target, max_seconds))
    beat_lines = "\n".join(
        f"  - beat {b['beat']} ({b['name']}): ~{b['seconds']}s — {b['role']}" for b in budgets
    )
    return (
        "Bạn là biên tập Shorts thuyết minh di sản/thủ công (kiểu BIẾT HAY CHƯA).\n"
        "CHỦ ĐỀ ĐÚNG (ưu tiên tuyệt đối):\n"
        f"- topic_vi: {topic_vi or '(trống)'}\n"
        f"- topic_zh: {topic_zh or title_zh or '(trống)'}\n"
        f"- title_zh: {title_zh or '(trống)'}\n"
        f"- video_duration_sec: {duration}\n\n"
        "LƯU Ý:\n"
        "- ASR có thể ẢO GIÁC — chỉ dùng làm mốc thời gian, không copy nghĩa đen.\n"
        "- Chọn cảnh theo CHUỖI QUY TRÌNH nghề, không nhảy lung tung theo score.\n"
        "- summary_vi phải khớp topic_vi.\n\n"
        f"Chọn ĐÚNG 7 đoạn (một đoạn / beat), tổng gần {int(target)}s "
        f"(tối thiểu {int(target * 0.75)}s), không vượt {int(max_seconds)}s.\n"
        "Ngân sách từng beat:\n"
        f"{beat_lines}\n"
        "Trả về JSON:\n"
        '{"clips":[{"beat":1,"beat_name":"hook","start":0.0,"end":12.0,"score":0-100,'
        '"reason":"...","text":"mô tả cảnh theo chủ đề"}],'
        '"summary_zh":"...","summary_vi":"..."}\n'
        "start/end trong [0, video_duration_sec], clips sắp theo thời gian tăng dần.\n"
        f"Transcript (tham chiếu thời gian, có thể nhiễu):\n"
        f"{json.dumps(compact, ensure_ascii=False)}"
    )


def select_highlights(
    transcript: dict,
    *,
    target_seconds: float = TARGET_SECONDS,
    max_seconds: float = MAX_SECONDS,
    topic_vi: str = "",
    topic_zh: str = "",
    title_zh: str = "",
    force: bool = False,
) -> dict:
    video_id = str(transcript.get("video_id") or "")
    out_dir = PROCESSED / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "highlights.json"
    if out_path.is_file() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))

    segments = list(transcript.get("segments") or [])
    duration = float(transcript.get("duration") or _duration_of(segments) or 0)
    summary_zh = ""
    summary_vi = ""
    errors: list[str] = []
    provider = "none"
    model = ""

    if duration > 0 and duration <= max_seconds and segments:
        clips = [
            {
                "start": float(segments[0]["start"]),
                "end": float(segments[-1]["end"]),
                "text": transcript.get("text") or "",
                "score": 100,
                "reason": "full_video_within_limit",
                "beat": 1,
                "beat_name": "full",
            }
        ]
    elif not segments:
        clips = [
            {
                "start": 0.0,
                "end": min(duration or target_seconds, max_seconds),
                "text": "",
                "score": 0,
                "reason": "empty_transcript",
                "beat": 1,
                "beat_name": "hook",
            }
        ]
    else:
        try:
            import douyin_quality

            result = douyin_llm.chat_json(
                _prompt(
                    transcript,
                    target=target_seconds,
                    max_seconds=max_seconds,
                    topic_vi=topic_vi,
                    topic_zh=topic_zh,
                    title_zh=title_zh,
                ),
                temperature=douyin_quality.HIGHLIGHT_TEMPERATURE,
            )
            provider = result["provider"]
            model = result["model"]
            errors = list(result.get("errors") or [])
            summary_zh = str(result["data"].get("summary_zh") or "")
            summary_vi = str(result["data"].get("summary_vi") or "")
            clips = _normalize_clips(
                result["data"].get("clips") or [],
                segments,
                max_seconds=max_seconds,
                target_seconds=target_seconds,
            )
            total_picked = sum(float(c["end"]) - float(c["start"]) for c in clips)
            if (not clips) or total_picked < target_seconds * 0.55 or len(clips) < 4:
                clips = _heuristic_pick(
                    segments,
                    target=target_seconds,
                    max_seconds=max_seconds,
                    duration=duration,
                    topic_vi=topic_vi,
                )
                provider = f"{provider}+heuristic"
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc)[:300])
            clips = _heuristic_pick(
                segments,
                target=target_seconds,
                max_seconds=max_seconds,
                duration=duration,
                topic_vi=topic_vi,
            )
            provider = "heuristic"
            model = ""

    total = round(sum(float(c["end"]) - float(c["start"]) for c in clips), 3)
    payload = {
        "video_id": video_id,
        "formula": "cong_thuc_shorts_7beat",
        "target_seconds": target_seconds,
        "max_seconds": max_seconds,
        "source_duration": duration,
        "total_seconds": total,
        "clips": clips,
        "summary_zh": summary_zh,
        "summary_vi": summary_vi,
        "provider": provider,
        "model": model,
        "errors": errors,
    }
    _write_json(out_path, payload)
    return payload
