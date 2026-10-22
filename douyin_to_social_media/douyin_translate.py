"""Dịch nội dung Douyin từ tiếng Trung sang tiếng Việt.

Dùng Alibaba Translate qua thư viện translators vì bản dịch giữ đúng
thuật ngữ (hoa văn, quốc phong, di sản phi vật thể). MyMemory chỉ là
phương án dự phòng khi Alibaba không trả lời.
"""

from __future__ import annotations

import html
import re
import threading
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
_CJK = re.compile(r"[\u4e00-\u9fff]")
_TAG = re.compile(r"#([^\s#]+)")
_LOCK = threading.RLock()
# Cache translations.json trong RAM — tránh đọc/parse lại cho từng video khi load state.
_MEM: dict = {"mtime": None, "data": {}}

# Hashtag cố định cho mô tả YouTube Shorts (không lấy tag dịch từ Douyin).
YOUTUBE_FIXED_TAGS = "#shortviral #kienthucthuvi #khampha #vuive"


def _cache_path():
    from pathlib import Path

    import douyin_poster

    override = globals().get("CACHE_PATH")
    if override:
        return Path(override)
    return douyin_poster.DATA / "translations.json"


def looks_chinese(text: str) -> bool:
    return bool(_CJK.search(text or ""))


def hashtag(text: str) -> str:
    words = []
    for raw in (text or "").replace("-", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if word:
            words.append(word[:1].upper() + word[1:])
    return f"#{''.join(words)}" if words else ""


def _parts(text: str) -> tuple[str, list[str]]:
    tags = _TAG.findall(text or "")
    body = _TAG.sub(" ", text or "")
    body = re.sub(r"[ \t]+", " ", body).strip()
    return body, tags


def _usable(source: str, result: str) -> bool:
    result = (result or "").strip()
    if not result:
        return False
    if looks_chinese(source) and result == source.strip():
        return False
    return True


def _chunks(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    buf = ""
    for piece in re.split(r"(?<=[。！？.!?])", text):
        if buf and len(buf) + len(piece) > limit:
            parts.append(buf)
            buf = piece
        else:
            buf += piece
    if buf:
        parts.append(buf)
    return [part for part in parts if part.strip()]


def _alibaba(text: str) -> str:
    import translators as ts

    return ts.translate_text(text, translator="alibaba", from_language="zh", to_language="vi")


def _mymemory(text: str) -> str:
    from deep_translator import MyMemoryTranslator

    translator = MyMemoryTranslator(source="zh-CN", target="vi-VN")
    pieces = []
    for chunk in _chunks(text, 450):
        pieces.append(translator.translate(chunk))
    return "".join(pieces)


def _translate_text(text: str) -> tuple[str, str]:
    source = (text or "").strip()
    if not source:
        return "", ""
    if not looks_chinese(source):
        return source, ""
    errors = []
    for name, fn, limit in (("alibaba", _alibaba, 1800), ("mymemory", _mymemory, 450)):
        try:
            out = "".join(fn(chunk) for chunk in _chunks(source, limit))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if _usable(source, out):
            return html.unescape(out).strip(), name
        errors.append(f"{name}: bản dịch trống")
    detail = errors[-1] if errors else "không có kết quả"
    raise RuntimeError(f"Không dịch được sang tiếng Việt ({detail})")


def _translate_tags(tags: list[str]) -> list[str]:
    chinese = [tag for tag in tags if looks_chinese(tag)]
    mapped = {}
    if chinese:
        blob = "\n".join(chinese)
        translated, _engine = _translate_text(blob)
        lines = [line.strip() for line in translated.splitlines() if line.strip()]
        if len(lines) != len(chinese):
            lines = []
            for tag in chinese:
                line, _engine = _translate_text(tag)
                lines.append(line)
        mapped = dict(zip(chinese, lines))
    ready = []
    for tag in tags:
        if tag in mapped:
            hashed = hashtag(mapped[tag])
            if hashed:
                ready.append(hashed)
        else:
            ready.append(f"#{tag}")
    return ready


def _join(prose: str, tags: list[str]) -> str:
    body = (prose or "").strip()
    tail = " ".join(tag for tag in tags if tag)
    if body and tail:
        return f"{body}\n\n{tail}"
    return body or tail


def _prepare(text: str) -> str:
    """Đổi cụm Alibaba hay dịch lệch trước khi gửi."""
    return (text or "").replace("微纪录片", "短篇纪录片")


def _one_text(title: str, description: str) -> bool:
    title = title.strip()
    description = description.strip()
    if not description or description == title:
        return True
    head = title.replace("...", "").replace("…", "").strip()
    return len(head) >= 4 and description.startswith(head[:12])


def compose_caption(title: str, description: str) -> tuple[str, str]:
    """Trả về (caption tiếng Việt, tên máy dịch)."""
    title = _prepare((title or "").strip())
    description = _prepare((description or "").strip())
    if _one_text(title, description):
        source = description if len(description) >= len(title) else title
        body, tags = _parts(source)
        prose, engine = _translate_text(body)
        return _join(prose, _translate_tags(tags)).strip(), engine
    title_body, title_tags = _parts(title)
    head, engine = _translate_text(title_body)
    desc_body, desc_tags = _parts(description)
    prose, desc_engine = _translate_text(desc_body)
    blocks = [part for part in (head.strip(), prose.strip()) if part]
    caption = _join("\n\n".join(blocks), _translate_tags(desc_tags or title_tags))
    return caption.strip(), engine or desc_engine


def _read() -> dict:
    path = _cache_path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        _MEM["mtime"] = None
        _MEM["data"] = {}
        return {}
    if _MEM.get("mtime") == mtime and isinstance(_MEM.get("data"), dict):
        return _MEM["data"]
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    _MEM["mtime"] = mtime
    _MEM["data"] = data
    return data


def _write(data: dict) -> None:
    import json

    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        _MEM["mtime"] = path.stat().st_mtime_ns
    except OSError:
        _MEM["mtime"] = None
    _MEM["data"] = data if isinstance(data, dict) else {}


def lookup(video_id: str) -> dict:
    row = _read().get(str(video_id or "")) or {}
    return row if isinstance(row, dict) else {}


def _stamp() -> str:
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _split_caption(caption: str) -> tuple[str, str]:
    """Tách caption thành (tiêu đề, mô tả)."""
    text = (caption or "").strip()
    if not text:
        return "", ""
    lines = [ln.strip() for ln in text.splitlines()]
    title = next((ln for ln in lines if ln), "")
    # Phần còn lại (bỏ dòng tiêu đề đầu) làm mô tả
    rest_lines = []
    seen_title = False
    for ln in lines:
        if not seen_title and ln == title:
            seen_title = True
            continue
        rest_lines.append(ln)
    description = "\n".join(rest_lines).strip()
    return title, description


def _curated_description_from_ai(video_id: str) -> str:
    """Chọn lọc mô tả từ kịch bản / highlight AI nếu có."""
    from pathlib import Path

    import douyin_poster

    root = Path(douyin_poster.DATA) / "processed" / str(video_id)
    parts: list[str] = []
    script_path = root / "script_vi.json"
    if script_path.is_file():
        try:
            import json

            script = json.loads(script_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            script = {}
        topic = str(script.get("topic_vi") or script.get("theme_check") or "").strip()
        if topic:
            parts.append(topic)
        lines = script.get("lines") or []
        picks = []
        for row in lines:
            text = str((row or {}).get("text") or "").strip()
            beat = str((row or {}).get("beat_name") or "")
            if not text:
                continue
            # Ưu tiên hook / insight / payoff — bỏ câu quá dài trùng topic
            if beat in ("hook", "insight", "payoff", "cta") or len(picks) < 3:
                if topic and text.startswith(topic[:20]):
                    continue
                picks.append(text)
            if len(picks) >= 4:
                break
        if picks:
            parts.append("\n".join(picks))
        # Không gắn tag dịch từ Douyin — tag YouTube cố định gắn ở youtube_copy.
    if parts:
        return "\n\n".join(p for p in parts if p).strip()
    hi_path = root / "highlights.json"
    if hi_path.is_file():
        try:
            import json

            hi = json.loads(hi_path.read_text(encoding="utf-8"))
            summary = str(hi.get("summary_vi") or "").strip()
            if summary:
                return _prose_only(summary)
        except (OSError, ValueError):
            pass
    return ""


def _prose_only(text: str) -> str:
    body, _tags = _parts(text or "")
    return body.strip()


def _with_youtube_tags(description: str) -> str:
    """Giữ phần chữ, thay mọi hashtag bằng bộ tag cố định."""
    prose = _prose_only(description)
    if prose:
        return f"{prose}\n\n{YOUTUBE_FIXED_TAGS}"
    return YOUTUBE_FIXED_TAGS


def youtube_copy(video: dict, saved: dict | None = None) -> dict:
    """Trả về title_vi + description_vi sẵn sàng đăng YouTube."""
    video_id = str(video.get("id") or "")
    saved = saved if saved is not None else lookup(video_id)
    title = _prose_only(str(saved.get("title_vi") or ""))
    description = str(saved.get("description_vi") or "").strip()
    caption = str(saved.get("caption_vi") or "").strip()
    if not title and caption:
        raw_title, desc_from_cap = _split_caption(caption)
        title = _prose_only(raw_title)
        if not description:
            description = desc_from_cap
    # Mô tả chỉ có hashtag / quá ngắn → lấy nội dung chọn lọc từ AI (không lấy tag dịch)
    if not _prose_only(description):
        curated = _curated_description_from_ai(video_id)
        if curated:
            description = curated
    if not _prose_only(description) and caption:
        _, desc_from_cap = _split_caption(caption)
        prose = _prose_only(desc_from_cap)
        if prose and prose != title:
            description = prose
        else:
            description = ""
    if not title:
        title = _prose_only(str(video.get("title") or video_id or "Short")) or "Short"
    description = _with_youtube_tags(description)
    return {
        "title_vi": title,
        "description_vi": description,
        "caption_vi": caption or (f"{title}\n\n{description}".strip() if description else title),
    }


def ensure_video(video: dict, force: bool = False) -> dict:
    video_id = str(video.get("id") or "")
    if not video_id:
        raise RuntimeError("Không thấy video để dịch.")
    with _LOCK:
        current = lookup(video_id)
        if current.get("caption_vi") and current.get("edited") and not force:
            return {**current, **youtube_copy(video, current)}
        if current.get("caption_vi") and not force:
            # Bổ sung title/description nếu bản cũ chưa có
            if not current.get("title_vi") or not current.get("description_vi"):
                derived = youtube_copy(video, current)
                row = {
                    **current,
                    "title_vi": current.get("title_vi") or derived["title_vi"],
                    "description_vi": current.get("description_vi") or derived["description_vi"],
                    "updated_at": _stamp(),
                }
                data = _read()
                data[video_id] = row
                _write(data)
                return row
            return {**current, **youtube_copy(video, current)}
        caption, engine = compose_caption(
            str(video.get("title") or ""),
            str(video.get("description") or ""),
        )
        if not caption:
            raise RuntimeError("Video không có nội dung để dịch.")
        title_vi = _prose_only(_split_caption(caption)[0])
        curated = _curated_description_from_ai(video_id)
        description_vi = _with_youtube_tags(curated or _prose_only(_split_caption(caption)[1]))
        row = {
            "caption_vi": caption,
            "title_vi": title_vi,
            "description_vi": description_vi,
            "engine": engine or "giữ nguyên",
            "edited": False,
            "updated_at": _stamp(),
        }
        data = _read()
        data[video_id] = row
        _write(data)
        return row


def save_caption(
    video_id: str,
    caption: str = "",
    *,
    title_vi: str | None = None,
    description_vi: str | None = None,
) -> dict:
    video_id = str(video_id or "").strip()
    if not video_id:
        raise RuntimeError("Không thấy video để lưu bản dịch.")
    with _LOCK:
        current = lookup(video_id)
        # YouTube: lưu title + description tách riêng
        if title_vi is not None or description_vi is not None:
            title = _prose_only(title_vi if title_vi is not None else current.get("title_vi") or "")
            raw_desc = (
                description_vi if description_vi is not None else current.get("description_vi") or ""
            )
            description = _with_youtube_tags(raw_desc)
            if not title and not _prose_only(description) and not (caption or "").strip():
                raise RuntimeError("Tiêu đề / mô tả đang trống.")
            if not title:
                title = _prose_only((caption or "").splitlines()[0] if caption else "")
            composed = caption.strip() if (caption or "").strip() else (
                f"{title}\n\n{description}".strip() if description else title
            )
            if not composed:
                raise RuntimeError("Bản tiếng Việt đang trống.")
            row = {
                "caption_vi": composed,
                "title_vi": title,
                "description_vi": description,
                "engine": current.get("engine") or "sửa tay",
                "edited": True,
                "updated_at": _stamp(),
            }
        else:
            caption = (caption or "").strip()
            if not caption:
                raise RuntimeError("Bản tiếng Việt đang trống.")
            title, description = _split_caption(caption)
            row = {
                "caption_vi": caption,
                "title_vi": _prose_only(title),
                "description_vi": _with_youtube_tags(
                    description or current.get("description_vi") or ""
                ),
                "engine": current.get("engine") or "sửa tay",
                "edited": True,
                "updated_at": _stamp(),
            }
        data = _read()
        data[video_id] = row
        _write(data)
        return row


_BATCH = {
    "running": False,
    "video_id": "",
    "title": "",
    "message": "",
    "done": 0,
    "failed": 0,
    "total": 0,
    "pending": 0,
}
_BATCH_LOCK = threading.Lock()


def needs_translation(video: dict) -> bool:
    video_id = str(video.get("id") or "")
    if not video_id:
        return False
    if str(lookup(video_id).get("caption_vi") or "").strip():
        return False
    blob = f"{video.get('title') or ''}\n{video.get('description') or ''}"
    return looks_chinese(blob)


def pending_videos(videos: list[dict] | None = None) -> list[dict]:
    if videos is None:
        import douyin_poster

        videos = douyin_poster.load_videos()
    return [video for video in videos if needs_translation(video)]


def batch_status() -> dict:
    with _BATCH_LOCK:
        status = dict(_BATCH)
    status["pending"] = len(pending_videos())
    return status


def _batch_set(**kwargs) -> None:
    with _BATCH_LOCK:
        _BATCH.update(kwargs)


def _run_batch(videos: list[dict]) -> None:
    done = 0
    failed = 0
    total = len(videos)
    try:
        _batch_set(
            running=True,
            done=0,
            failed=0,
            total=total,
            message=f"Đang dịch 0/{total} tiêu đề sang tiếng Việt",
        )
        for video in videos:
            title = str(video.get("title") or video.get("id") or "")
            _batch_set(
                video_id=str(video.get("id") or ""),
                title=title[:120],
                message=f"Đang dịch {done + failed + 1}/{total}: {title[:80]}",
            )
            try:
                ensure_video(video, force=False)
                done += 1
            except Exception as exc:
                failed += 1
                _batch_set(message=f"Lỗi dịch {video.get('id')}: {exc}"[:220])
            _batch_set(done=done, failed=failed)
        if total == 0:
            message = "Không còn tiêu đề tiếng Trung cần dịch."
        elif failed == 0:
            message = f"Đã dịch xong {done} tiêu đề sang tiếng Việt."
        else:
            message = f"Xong. Dịch được {done}, lỗi {failed}."
        _batch_set(message=message, video_id="", title="")
    finally:
        _batch_set(running=False)


def start_batch(videos: list[dict] | None = None) -> dict:
    """Dịch nền mọi video Douyin còn tiêu đề/mô tả tiếng Trung."""
    queue = pending_videos(videos)
    with _BATCH_LOCK:
        if _BATCH["running"]:
            return dict(_BATCH)
        if not queue:
            _BATCH.update(
                running=False,
                video_id="",
                title="",
                message="Không còn tiêu đề tiếng Trung cần dịch.",
                done=0,
                failed=0,
                total=0,
                pending=0,
            )
            return dict(_BATCH)
        _BATCH.update(
            running=True,
            video_id="",
            title="",
            message=f"Bắt đầu dịch {len(queue)} tiêu đề",
            done=0,
            failed=0,
            total=len(queue),
            pending=len(queue),
        )
    threading.Thread(target=_run_batch, args=(queue,), name="dy-translate", daemon=True).start()
    return batch_status()


def kick_batch() -> dict:
    """Gọi sau khi tải video mới: chỉ chạy nếu có mục chưa dịch và chưa có job."""
    with _BATCH_LOCK:
        if _BATCH["running"]:
            return dict(_BATCH)
    return start_batch()
