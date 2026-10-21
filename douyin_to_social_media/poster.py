"""Hàng đợi đăng Shorts đã tải lên Facebook Page."""

from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA = ROOT / "data"
VIDEO_DIR = DATA / "videos"
CONFIG_PATH = DATA / "config.json"
MANIFEST_PATH = DATA / "manifest.json"
POSTS_PATH = DATA / "posts.json"
_SKIP_SUFFIX = {".json", ".part", ".ytdl", ".temp", ".jpg", ".jpeg", ".webp", ".png"}
VN_TZ = timezone(timedelta(hours=7))

if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from shopeetool.facebook import FBError, fb_check, hint_for, upload_video  # noqa: E402
import requests  # noqa: E402

_TITLE_TAG = re.compile(r"#\S+", re.UNICODE)
_LOCK = threading.RLock()
_JOB = {"running": False, "video_id": "", "title": "", "message": ""}


def clean_title(title: str) -> str:
    """Bỏ mọi hashtag khỏi tiêu đề. Tag chỉ giữ ở phần mô tả."""
    return " ".join(_TITLE_TAG.sub(" ", title or "").split())


def facebook_caption(title: str, description: str) -> str:
    """Tiêu đề đã bỏ tag, rồi đến nguyên văn mô tả (kể cả hashtag)."""
    head = clean_title(title)
    body = (description or "").strip()
    if head and body:
        return f"{head}\n\n{body}"
    return head or body


def now() -> datetime:
    return datetime.now(VN_TZ)


def now_str() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_config() -> dict:
    cfg = _read_json(CONFIG_PATH, {})
    auto = cfg.get("auto") if isinstance(cfg.get("auto"), dict) else {}
    cfg["auto"] = {
        "enabled": bool(auto.get("enabled")),
        "interval_minutes": _interval(auto.get("interval_minutes"), 60),
        "order": auto.get("order") if auto.get("order") in ("oldest", "newest") else "oldest",
    }
    cfg["page_id"] = str(cfg.get("page_id") or "")
    cfg["page_name"] = str(cfg.get("page_name") or "")
    cfg["page_url"] = str(cfg.get("page_url") or "")
    cfg["token"] = str(cfg.get("token") or "")
    cfg["api_version"] = str(cfg.get("api_version") or "v21.0")
    return cfg


def save_config(cfg: dict) -> None:
    stored = {
        "page_id": cfg.get("page_id") or "",
        "page_name": cfg.get("page_name") or "",
        "page_url": cfg.get("page_url") or "",
        "token": cfg.get("token") or "",
        "api_version": cfg.get("api_version") or "v21.0",
        "auto": cfg.get("auto") or {},
    }
    _write_json(CONFIG_PATH, stored)


def load_posts() -> dict:
    data = _read_json(POSTS_PATH, {})
    items = data.get("items") if isinstance(data.get("items"), dict) else {}
    log = data.get("log") if isinstance(data.get("log"), list) else []
    return {
        "last_posted_at": str(data.get("last_posted_at") or ""),
        "items": items,
        "log": log[:100],
    }


def save_posts(posts: dict) -> None:
    posts["log"] = (posts.get("log") or [])[:100]
    _write_json(POSTS_PATH, posts)


def _interval(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(1440, max(1, number))


def _show_date(raw: str) -> str:
    text = str(raw or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[6:8]}/{text[4:6]}/{text[0:4]}"
    return text


def _resolve_media(video_id: str, stored: str) -> str:
    """Tìm file video dù manifest ghi đường dẫn của máy khác.

    File được mount vào data/videos. Đường dẫn tuyệt đối lưu lúc tải trên host
    (ví dụ /mnt/data1/...) không tồn tại khi app chạy trong container.
    """
    if stored:
        direct = Path(stored)
        if direct.is_file():
            return str(direct)
        named = VIDEO_DIR / direct.name
        if named.is_file():
            return str(named)
        relative = (DATA / stored).resolve()
        if relative.is_file() and DATA.resolve() in relative.parents:
            return str(relative)
    preferred = VIDEO_DIR / f"{video_id}.mp4"
    if preferred.is_file():
        return str(preferred)
    matches = sorted(
        path for path in VIDEO_DIR.glob(f"{video_id}.*")
        if path.is_file() and path.suffix.lower() not in _SKIP_SUFFIX and ".part" not in path.name
    )
    return str(matches[0]) if matches else stored


def load_videos() -> list[dict]:
    manifest = _read_json(MANIFEST_PATH, {})
    videos = []
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        video_id = str(item["id"])
        path = _resolve_media(video_id, str(item.get("file") or ""))
        videos.append({
            "id": video_id,
            "title": str(item.get("title") or video_id),
            "url": str(item.get("url") or ""),
            "upload_date": str(item.get("upload_date") or ""),
            "upload_label": _show_date(item.get("upload_date") or ""),
            "duration": item.get("duration"),
            "description": str(item.get("description") or ""),
            "channel": str(item.get("channel") or ""),
            "channel_name": str(item.get("channel_name") or ""),
            "file": path,
            "has_file": bool(path) and Path(path).is_file(),
        })
    return videos


def _status_of(video: dict, posts: dict) -> str:
    if _JOB["running"] and _JOB["video_id"] == video["id"]:
        return "posting"
    record = (posts.get("items") or {}).get(video["id"]) or {}
    status = record.get("status") or ""
    if status in ("published", "error"):
        return status
    if not video["has_file"]:
        return "missing"
    return "pending"


def queue(videos: list[dict], posts: dict, order: str) -> list[dict]:
    pending = [video for video in videos if _status_of(video, posts) == "pending"]
    pending.sort(key=lambda video: (video.get("upload_date") or "", video["id"]))
    if order == "newest":
        pending.reverse()
    return pending


def _public_video(video: dict, posts: dict) -> dict:
    record = (posts.get("items") or {}).get(video["id"]) or {}
    return {
        "id": video["id"],
        "title": video["title"],
        "url": video["url"],
        "upload_date": video["upload_date"],
        "upload_label": video["upload_label"],
        "duration": video["duration"],
        "description": video.get("description") or "",
        "channel": video.get("channel") or "",
        "channel_name": video.get("channel_name") or "",
        "caption": facebook_caption(video["title"], video.get("description") or ""),
        "has_file": video["has_file"],
        "status": _status_of(video, posts),
        "facebook_video_id": record.get("facebook_video_id") or "",
        "permalink": record.get("permalink") or "",
        "error": record.get("error") or "",
        "posted_at": record.get("posted_at") or "",
    }


def _next_at(posts: dict, auto: dict) -> str:
    if not auto.get("enabled"):
        return ""
    last = posts.get("last_posted_at") or ""
    if not last:
        return now_str()
    try:
        stamp = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
    except ValueError:
        return now_str()
    return (stamp + timedelta(minutes=int(auto["interval_minutes"]))).strftime("%Y-%m-%d %H:%M:%S")


def public_state() -> dict:
    with _LOCK:
        cfg = load_config()
        posts = load_posts()
        videos = load_videos()
        listed = [_public_video(video, posts) for video in videos]
        pending = queue(videos, posts, cfg["auto"]["order"])
        counts = {"total": len(listed), "pending": 0, "published": 0, "error": 0, "missing": 0, "posting": 0}
        for item in listed:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        nxt = pending[0] if pending else None
        return {
            "ok": True,
            "page": {
                "id": cfg["page_id"],
                "name": cfg["page_name"],
                "url": cfg["page_url"],
                "has_token": bool(cfg["token"]),
            },
            "auto": {
                **cfg["auto"],
                "next_at": _next_at(posts, cfg["auto"]),
                "last_posted_at": posts.get("last_posted_at") or "",
            },
            "job": dict(_JOB),
            "counts": counts,
            "next": {"id": nxt["id"], "title": nxt["title"]} if nxt else None,
            "log": posts.get("log") or [],
            "videos": listed,
        }


def update_settings(payload: dict) -> dict:
    with _LOCK:
        cfg = load_config()
        auto = cfg["auto"]
        if "enabled" in payload:
            auto["enabled"] = bool(payload.get("enabled"))
        if "interval_minutes" in payload:
            auto["interval_minutes"] = _interval(payload.get("interval_minutes"), auto["interval_minutes"])
        if "order" in payload and payload.get("order") in ("oldest", "newest"):
            auto["order"] = payload["order"]
        token = str(payload.get("token") or "").strip()
        if token:
            page_token, name = _page_token(cfg["page_id"], token, cfg["api_version"])
            cfg["token"] = page_token
            if name:
                cfg["page_name"] = name
        cfg["auto"] = auto
        save_config(cfg)
    return public_state()


def _page_token(page_id: str, token: str, version: str) -> tuple[str, str]:
    from shopeetool.facebook import resolve_page_token
    return resolve_page_token(token, page_id, version)


def _permalink(video_id: str, token: str, version: str) -> str:
    resp = requests.get(
        f"https://graph.facebook.com/{version}/{video_id}",
        params={"fields": "permalink_url", "access_token": token},
        timeout=30,
    )
    try:
        link = fb_check(resp).get("permalink_url") or ""
    except FBError:
        return ""
    if link.startswith("/"):
        return "https://www.facebook.com" + link
    return link


def _append_log(posts: dict, video: dict, ok: bool, message: str) -> None:
    posts.setdefault("log", []).insert(0, {
        "at": now_str(),
        "video_id": video["id"],
        "title": video["title"],
        "ok": ok,
        "message": message,
    })
    posts["log"] = posts["log"][:100]


def _finish_job() -> None:
    _JOB.update(running=False, video_id="", title="", message="")


def post_video(video_id: str) -> None:
    """Đăng một video. Gọi từ luồng nền; lỗi được ghi vào posts.json."""
    with _LOCK:
        cfg = load_config()
        videos = {video["id"]: video for video in load_videos()}
        video = videos.get(video_id)
        if not video:
            _finish_job()
            return
        if not cfg["token"] or not cfg["page_id"]:
            _fail(cfg, video, "Chưa có Page Access Token.")
            return
        if not video["has_file"]:
            _fail(cfg, video, "Không thấy file video trên máy.")
            return
        _JOB.update(running=True, video_id=video["id"], title=video["title"], message="Đang chọn sản phẩm Shopee")
        version = cfg["api_version"]
        path = video["file"]
        caption = facebook_caption(video["title"], video.get("description") or "")
        chosen_id = video["id"]
        page_id = cfg["page_id"]
        raw_token = cfg["token"]

    try:
        token, name = _page_token(page_id, raw_token, version)
    except FBError as exc:
        with _LOCK:
            _fail(load_config(), video, str(exc)[:400])
        return
    page = {"id": page_id, "token": token}
    with _LOCK:
        cfg = load_config()
        if cfg.get("token") != token or (name and cfg.get("page_name") != name):
            cfg["token"] = token
            if name:
                cfg["page_name"] = name
            save_config(cfg)

    try:
        import suggest
        extra = suggest.offer_suffix(chosen_id)
        if extra:
            caption = f"{caption}\n\n{extra}" if caption else extra
        with _LOCK:
            if _JOB.get("video_id") == chosen_id:
                _JOB["message"] = "Đang tải lên Facebook"
        fb_id = upload_video(page, path, caption, version)
        link = _permalink(fb_id, token, version)
    except FBError as exc:
        message = str(exc)
        if getattr(exc, "code", None) == 190:
            message = "Token hết hạn hoặc không hợp lệ. Mở tab Config, dán Page Access Token rồi bấm Lưu token."
        else:
            hint = hint_for(exc)
            if hint:
                message = f"{message} {hint}"
        with _LOCK:
            _fail(load_config(), video, message[:400])
        return
    except OSError as exc:
        with _LOCK:
            _fail(load_config(), video, f"Không đọc được file: {exc}"[:400])
        return
    except Exception as exc:
        with _LOCK:
            _fail(load_config(), video, f"Lỗi không xác định: {exc}"[:400])
        return

    with _LOCK:
        posts = load_posts()
        posts["last_posted_at"] = now_str()
        posts.setdefault("items", {})[video["id"]] = {
            "status": "published",
            "facebook_video_id": fb_id,
            "permalink": link,
            "error": "",
            "posted_at": posts["last_posted_at"],
        }
        _append_log(posts, video, True, "Đã đăng lên Page")
        save_posts(posts)
        _finish_job()


def _fail(cfg: dict, video: dict, message: str) -> None:
    posts = load_posts()
    posts["last_posted_at"] = now_str()
    posts.setdefault("items", {})[video["id"]] = {
        "status": "error",
        "facebook_video_id": "",
        "permalink": "",
        "error": message,
        "posted_at": "",
    }
    _append_log(posts, video, False, message)
    save_posts(posts)
    _finish_job()


def start_post(video_id: str) -> dict:
    with _LOCK:
        if _JOB["running"]:
            raise RuntimeError("Đang đăng một video khác. Hãy đợi video hiện tại xong.")
        videos = {video["id"]: video for video in load_videos()}
        posts = load_posts()
        video = videos.get(str(video_id or ""))
        if video_id == "next" or not video_id:
            order = load_config()["auto"]["order"]
            pending = queue(list(videos.values()), posts, order)
            if not pending:
                raise RuntimeError("Không còn video chưa đăng.")
            video = pending[0]
        if not video:
            raise RuntimeError("Không thấy video này trong danh sách đã tải.")
        # Cho phép đăng lại thủ công; hàng đợi auto vẫn chỉ lấy pending.
        if not video["has_file"]:
            raise RuntimeError("File video không còn trên máy.")
        _JOB.update(running=True, video_id=video["id"], title=video["title"], message="Chuẩn bị đăng")
        chosen = video["id"]
    threading.Thread(target=post_video, args=(chosen,), daemon=True).start()
    return public_state()


def _due(posts: dict, auto: dict) -> bool:
    if not auto.get("enabled"):
        return False
    last = posts.get("last_posted_at") or ""
    if not last:
        return True
    try:
        stamp = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
    except ValueError:
        return True
    return now() >= stamp + timedelta(minutes=int(auto["interval_minutes"]))


def maybe_auto_post() -> None:
    with _LOCK:
        if _JOB["running"]:
            return
        cfg = load_config()
        posts = load_posts()
        if not _due(posts, cfg["auto"]):
            return
        pending = queue(load_videos(), posts, cfg["auto"]["order"])
        if not pending:
            return
        video_id = pending[0]["id"]
        _JOB.update(running=True, video_id=video_id, title=pending[0]["title"], message="Tự động đăng")
    post_video(video_id)


def scheduler() -> None:
    while True:
        try:
            maybe_auto_post()
        except Exception:
            with _LOCK:
                _finish_job()
        threading.Event().wait(15)


def start_scheduler() -> None:
    threading.Thread(target=scheduler, name="yt-fb-auto", daemon=True).start()
