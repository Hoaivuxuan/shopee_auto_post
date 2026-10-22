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

# Vị trí tương đối trên video NGUỒN theo beat.
# Video thủ công dài (Lý Tử Thất…) thường 30–50% đầu = cánh đồng/không khí —
# lệch cửa sổ về nửa SAU để bắt thao tác nghề; hook lấy thành phẩm gần cuối.
SOURCE_WINDOWS = [
    (0.90, 0.99),  # hook — cận cảnh thành phẩm / cắt bánh
    (0.52, 0.62),  # prep — rửa/chọn liệu (sau intro đồng)
    (0.60, 0.72),  # transform
    (0.68, 0.78),  # bridge
    (0.75, 0.90),  # core — thao tác chính
    (0.88, 0.96),  # meaning
    (0.94, 1.00),  # cta
]
# Video ngắn (< ~3 phút): phân bố đều hơn, hook có thể ở đầu
SOURCE_WINDOWS_SHORT = [
    (0.00, 0.12),
    (0.10, 0.28),
    (0.25, 0.45),
    (0.40, 0.55),
    (0.50, 0.75),
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


def _asr_coverage(segments: list[dict], duration: float) -> float:
    """Tỷ lệ thời lượng có lời ASR / độ dài video (0–1)."""
    duration = float(duration or 0)
    if duration <= 1:
        return 0.0
    covered = _duration_of(segments)
    return max(0.0, min(1.0, covered / duration))


def _source_windows_for(duration: float) -> list[tuple[float, float]]:
    """Video dài → lệch nửa sau (tránh intro lan man)."""
    if float(duration or 0) >= 200:
        return list(SOURCE_WINDOWS)
    return list(SOURCE_WINDOWS_SHORT)


def _is_front_loaded(clips: list[dict], duration: float) -> bool:
    """True nếu toàn bộ clip nằm trong ~55% đầu của video dài — thường là intro cánh đồng."""
    duration = float(duration or 0)
    if duration < 200 or not clips:
        return False
    span_end = max(float(c.get("end") or 0) for c in clips)
    span_start = min(float(c.get("start") or 0) for c in clips)
    # Liền mạch từ đầu và không chạm nửa sau
    return span_start < duration * 0.08 and span_end < duration * 0.58


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
    """7 cửa sổ theo vị trí nguồn + ngân sách beat (giữ thứ tự beat, không sort theo start)."""
    duration = float(duration or 0)
    if duration <= 0 and segments:
        duration = float(segments[-1]["end"])
    if duration <= 0:
        return []
    windows = _source_windows_for(duration)
    budgets = _beat_budgets(min(target, max_seconds))
    picked = []
    total = 0.0
    for i, budget in enumerate(budgets):
        lo, hi = windows[i]
        want = float(budget["seconds"])
        if total + want > max_seconds:
            want = max(5.0, max_seconds - total)
        center = (lo + hi) / 2.0 * duration
        start = max(0.0, center - want / 2.0)
        # neo trong cửa sổ nguồn
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
    # Giữ thứ tự BEAT (hook có thể lấy từ cuối nguồn); không sort thuần theo start
    ordered = sorted(
        clips,
        key=lambda c: (
            int(c["beat"]) if c.get("beat") else 99,
            float(c["start"]),
        ),
    )
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
    windows = _source_windows_for(duration)
    window_hint = "\n".join(
        f"  - beat {i + 1}: ưu tiên nguồn ~{int(lo * 100)}–{int(hi * 100)}% "
        f"(≈{lo * duration:.0f}–{hi * duration:.0f}s)"
        for i, (lo, hi) in enumerate(windows)
    )
    return (
        "Bạn là biên tập Shorts thuyết minh di sản/thủ công (kiểu BIẾT HAY CHƯA).\n"
        "CHỦ ĐỀ ĐÚNG (ưu tiên tuyệt đối):\n"
        f"- topic_vi: {topic_vi or '(trống)'}\n"
        f"- topic_zh: {topic_zh or title_zh or '(trống)'}\n"
        f"- title_zh: {title_zh or '(trống)'}\n"
        f"- video_duration_sec: {duration}\n\n"
        "LƯU Ý BẮT BUỘC:\n"
        "- ASR có thể ẢO GIÁC / thiếu — chỉ tham chiếu thời gian, không copy nghĩa đen.\n"
        "- Video dài kiểu thủ công thường 30–50% ĐẦU là cánh đồng / không khí / đi hái.\n"
        "  CẤM lấy gần hết short từ nửa đầu nguồn; CẤM 7 clip liền mạch từ giây 0.\n"
        "- Beat prep→core phải là THAO TÁC NGHỀ (rửa liệu, nghiền, trộn, hấp, cắt bánh…),\n"
        "  không phải đứng vườn / gánh rơm / cảnh quan.\n"
        "- Beat hook: cận cảnh thành phẩm hoặc thao tác lõi (được lấy gần CUỐI nguồn).\n"
        "- Chọn theo CHUỖI QUY TRÌNH nghề; summary_vi khớp topic_vi.\n"
        "- Gợi ý cửa sổ nguồn (có thể lệch nhẹ nếu thấy cảnh nghề rõ hơn):\n"
        f"{window_hint}\n\n"
        f"Chọn ĐÚNG 7 đoạn (một đoạn / beat), tổng gần {int(target)}s "
        f"(tối thiểu {int(target * 0.75)}s), không vượt {int(max_seconds)}s.\n"
        "Ngân sách từng beat:\n"
        f"{beat_lines}\n"
        "Trả về JSON:\n"
        '{"clips":[{"beat":1,"beat_name":"hook","start":0.0,"end":12.0,"score":0-100,'
        '"reason":"...","text":"mô tả cảnh theo chủ đề"}],'
        '"summary_zh":"...","summary_vi":"..."}\n'
        "start/end trong [0, video_duration_sec]; sắp clips theo thứ tự beat 1→7 "
        "(không bắt buộc start tăng dần).\n"
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
        coverage = _asr_coverage(segments, duration)
        sparse_asr = coverage < 0.25
        try:
            import douyin_quality

            # ASR quá nghèo → heuristic lệch nửa sau (tránh LLM bịa quy trình trên intro)
            if sparse_asr and duration >= 200:
                clips = _heuristic_pick(
                    segments,
                    target=target_seconds,
                    max_seconds=max_seconds,
                    duration=duration,
                    topic_vi=topic_vi,
                )
                provider = "heuristic"
                model = ""
                errors.append(
                    f"asr_coverage={coverage:.2f} sparse → heuristic process-bias windows"
                )
            else:
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
                bad = (
                    (not clips)
                    or total_picked < target_seconds * 0.55
                    or len(clips) < 4
                    or _is_front_loaded(clips, duration)
                )
                if bad:
                    reason = "front_loaded" if _is_front_loaded(clips, duration) else "thin"
                    clips = _heuristic_pick(
                        segments,
                        target=target_seconds,
                        max_seconds=max_seconds,
                        duration=duration,
                        topic_vi=topic_vi,
                    )
                    provider = f"{provider}+heuristic"
                    errors.append(f"llm_clips_{reason} → heuristic process-bias")
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
