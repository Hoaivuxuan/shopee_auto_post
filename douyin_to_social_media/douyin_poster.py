"""Hàng đợi đăng video Douyin lên Facebook (publisher P0 của douyin_to_social_media).

YouTube Shorts / TikTok sẽ đi qua publishers/ — không trộn hàng YouTube legacy.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA = ROOT / "data" / "douyin"
VIDEO_DIR = DATA / "videos"
CONFIG_PATH = DATA / "config.json"
MANIFEST_PATH = DATA / "manifest.json"
POSTS_PATH = DATA / "posts.json"
_SKIP_SUFFIX = {".json", ".part", ".ytdl", ".temp", ".jpg", ".jpeg", ".webp", ".png"}

if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from shopeetool.facebook import FBError, fb_check, hint_for, upload_video  # noqa: E402

from poster import VN_TZ, _interval, _page_token, facebook_caption, load_config as load_youtube_config  # noqa: E402
import progress  # noqa: E402

_LOCK = threading.RLock()
_JOB = {
    "running": False,
    "video_id": "",
    "title": "",
    "message": "",
    "status": "",
    "current_step": "",
    "error": "",
    "steps": {},
    "progress": progress.progress_payload(kind="publish", target="facebook", status="idle"),
}


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


def _empty_config() -> dict:
    shared = {}
    try:
        shared = load_youtube_config()
    except Exception:
        shared = {}
    return {
        "page_id": str(shared.get("page_id") or ""),
        "page_name": str(shared.get("page_name") or ""),
        "page_url": str(shared.get("page_url") or ""),
        "token": str(shared.get("token") or ""),
        "api_version": str(shared.get("api_version") or "v21.0"),
        "auto": {"enabled": False, "interval_minutes": 60, "order": "oldest"},
    }


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        cfg = _empty_config()
        save_config(cfg)
        return cfg
    cfg = _read_json(CONFIG_PATH, {})
    if not isinstance(cfg, dict):
        cfg = _empty_config()
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
    if not isinstance(data, dict):
        data = {}
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


def _show_date(raw: str) -> str:
    text = str(raw or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[6:8]}/{text[4:6]}/{text[0:4]}"
    return text


def _list_video_names() -> set[str]:
    try:
        return {path.name for path in VIDEO_DIR.iterdir() if path.is_file()}
    except OSError:
        return set()


def _ai_short_ids() -> set[str]:
    root = DATA / "processed"
    found: set[str] = set()
    if not root.is_dir():
        return found
    try:
        for folder in root.iterdir():
            if folder.is_dir() and (folder / "output_ai.mp4").is_file():
                found.add(folder.name)
    except OSError:
        return found
    return found


def _resolve_media(video_id: str, stored: str, names: set[str] | None = None) -> str:
    known = names if names is not None else _list_video_names()
    if stored:
        direct = Path(stored)
        if direct.name in known and (VIDEO_DIR / direct.name).is_file():
            return str(VIDEO_DIR / direct.name)
        if direct.is_file():
            return str(direct)
        named = VIDEO_DIR / direct.name
        if named.name in known or named.is_file():
            return str(named)
    preferred = f"{video_id}.mp4"
    if preferred in known:
        return str(VIDEO_DIR / preferred)
    prefix = f"{video_id}."
    matches = sorted(
        name for name in known
        if name.startswith(prefix)
        and Path(name).suffix.lower() not in _SKIP_SUFFIX
        and ".part" not in name
    )
    if matches:
        return str(VIDEO_DIR / matches[0])
    return stored


def load_videos() -> list[dict]:
    manifest = _read_json(MANIFEST_PATH, {})
    if not isinstance(manifest, dict):
        return []
    names = _list_video_names()
    videos = []
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        video_id = str(item["id"])
        path = _resolve_media(video_id, str(item.get("file") or ""), names)
        has_file = bool(path) and Path(path).name in names
        if not has_file and path:
            has_file = Path(path).is_file()
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
            "has_file": has_file,
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


def queue(videos: list[dict], posts: dict, order: str, ai_ids: set[str] | None = None) -> list[dict]:
    # Chỉ xếp hàng video đã có bản ngắn AI — không đăng file Douyin gốc
    ready = ai_ids if ai_ids is not None else _ai_short_ids()
    pending = [
        video
        for video in videos
        if _status_of(video, posts) == "pending" and video["id"] in ready
    ]
    pending.sort(key=lambda video: (video.get("upload_date") or "", video["id"]))
    if order == "newest":
        pending.reverse()
    return pending


def media_path(video_id: str):
    if not re.fullmatch(r"\d{6,}", str(video_id or "")):
        return None
    root = VIDEO_DIR.resolve()
    matches = sorted(
        path for path in root.glob(f"{video_id}.*")
        if path.is_file() and path.suffix.lower() not in _SKIP_SUFFIX and ".part" not in path.name
    )
    if not matches:
        return None
    chosen = matches[0].resolve()
    if chosen.parent != root:
        return None
    return chosen


def ai_short_path(video_id: str):
    """File video ngắn AI (output_ai.mp4) — bắt buộc khi đăng Facebook."""
    if not re.fullmatch(r"\d{6,}", str(video_id or "")):
        return None
    path = DATA / "processed" / str(video_id) / "output_ai.mp4"
    if not path.is_file():
        return None
    return path


def _caption(video: dict) -> str:
    import douyin_translate

    saved = douyin_translate.lookup(video["id"])
    text = str(saved.get("caption_vi") or "").strip()
    if text:
        return text
    title = video.get("title") or ""
    description = video.get("description") or ""
    if description.strip() == title.strip():
        description = ""
    return facebook_caption(title, description)


def caption_for_post(video: dict) -> str:
    import douyin_translate

    saved = douyin_translate.lookup(video["id"])
    if str(saved.get("caption_vi") or "").strip():
        return str(saved["caption_vi"]).strip()
    blob = f"{video.get('title') or ''}\n{video.get('description') or ''}"
    if douyin_translate.looks_chinese(blob):
        row = douyin_translate.ensure_video(video, force=False)
        return str(row.get("caption_vi") or "").strip()
    return _caption(video)


def _publish_info(video: dict, posts: dict) -> dict:
    """Payload gọn cho danh sách — chỉ kèm steps khi đang đăng."""
    record = (posts.get("items") or {}).get(video["id"]) or {}
    status = _status_of(video, posts)
    live = dict(_JOB)
    if live.get("running") and live.get("video_id") == video["id"]:
        return live.get("progress") or progress.progress_payload(
            kind="publish",
            target="facebook",
            status="running",
            message=live.get("message") or "",
            current_step=live.get("current_step") or "",
            steps=live.get("steps") if isinstance(live.get("steps"), dict) else {},
        )
    if status == "published":
        return {"status": "done"}
    if status == "error":
        return {"status": "error", "error": record.get("error") or "Lỗi đăng"}
    if isinstance(record.get("progress"), dict) and record["progress"].get("status") == "running":
        return dict(record["progress"])
    return {"status": "idle"}


def _public_video(video: dict, posts: dict, ai_ids: set[str] | None = None) -> dict:
    import douyin_translate

    record = (posts.get("items") or {}).get(video["id"]) or {}
    saved = douyin_translate.lookup(video["id"])
    caption = _caption(video)
    caption_vi = str(saved.get("caption_vi") or "")
    title = video["title"]
    description = video.get("description") or ""
    has_ai = video["id"] in ai_ids if ai_ids is not None else bool(ai_short_path(video["id"]))
    row = {
        "id": video["id"],
        "title": title,
        "url": video["url"],
        "upload_date": video["upload_date"],
        "upload_label": video["upload_label"],
        "duration": video["duration"],
        "channel": video.get("channel") or "",
        "channel_name": video.get("channel_name") or "",
        "caption": caption,
        "translated": bool(caption_vi.strip()),
        "has_file": video["has_file"],
        "has_ai_short": has_ai,
        "status": _status_of(video, posts),
        "source": "douyin",
        "publish": _publish_info(video, posts),
    }
    # Bỏ field trùng/rỗng để JSON nhỏ hơn với 900+ video.
    if description and description.strip() != title.strip():
        row["description"] = description
    # caption_vi chỉ gửi khi khác caption (UI fallback sang caption).
    if caption_vi and caption_vi != caption:
        row["caption_vi"] = caption_vi
    engine = str(saved.get("engine") or "")
    if engine:
        row["translation_engine"] = engine
    fb_id = record.get("facebook_video_id") or ""
    if fb_id:
        row["facebook_video_id"] = fb_id
    permalink = record.get("permalink") or ""
    if permalink:
        row["permalink"] = permalink
    err = record.get("error") or ""
    if err:
        row["error"] = err
    posted = record.get("posted_at") or ""
    if posted:
        row["posted_at"] = posted
    return row


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
    # Giữ lock ngắn: chỉ đọc config/posts/job. Build danh sách video ngoài lock
    # để nhiều request /api/douyin/state không xếp hàng hàng chục giây.
    with _LOCK:
        cfg = load_config()
        posts = load_posts()
        job = dict(_JOB)
        auto = dict(cfg["auto"])
        page = {
            "id": cfg["page_id"],
            "name": cfg["page_name"],
            "url": cfg["page_url"],
            "has_token": bool(cfg["token"]),
        }
    videos = load_videos()
    ai_ids = _ai_short_ids()
    listed = [_public_video(video, posts, ai_ids) for video in videos]
    pending = queue(videos, posts, auto["order"], ai_ids)
    counts = {"total": len(listed), "pending": 0, "published": 0, "error": 0, "missing": 0, "posting": 0}
    for item in listed:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    nxt = pending[0] if pending else None
    next_row = None
    if nxt:
        shown = _public_video(nxt, posts, ai_ids)
        next_row = {
            "id": nxt["id"],
            "title": (shown.get("caption") or nxt["title"] or "").splitlines()[0][:160],
        }
    return {
        "ok": True,
        "source": "douyin",
        "target": "facebook",
        "page": page,
        "auto": {
            **auto,
            "next_at": _next_at(posts, auto),
            "last_posted_at": posts.get("last_posted_at") or "",
        },
        "job": job,
        "counts": counts,
        "next": next_row,
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


def _save_progress_record(video_id: str, payload: dict) -> None:
    posts = load_posts()
    item = dict(posts.setdefault("items", {}).get(video_id) or {})
    item.update(payload)
    if payload.get("remote_id"):
        item["facebook_video_id"] = payload["remote_id"]
    if payload.get("status") == "published":
        posts["last_posted_at"] = payload.get("posted_at") or now_str()
        item["posted_at"] = posts["last_posted_at"]
    posts["items"][video_id] = item
    save_posts(posts)


def _fail(video: dict, message: str, tracker: progress.PublishTracker | None = None) -> None:
    if tracker:
        tracker.fail(tracker.current_step or "check", message)
    posts = load_posts()
    posts["last_posted_at"] = now_str()
    prev = dict(posts.setdefault("items", {}).get(video["id"]) or {})
    posts["items"][video["id"]] = {
        **prev,
        "status": "error",
        "facebook_video_id": prev.get("facebook_video_id") or "",
        "permalink": "",
        "error": message,
        "posted_at": "",
        "progress": (tracker.snapshot(status="error", message=message, error=message) if tracker else prev.get("progress")),
    }
    _append_log(posts, video, False, message)
    save_posts(posts)
    _finish_job()


def post_video(video_id: str) -> None:
    tracker = progress.PublishTracker(
        target="facebook",
        lock=_LOCK,
        job=_JOB,
        save_record=_save_progress_record,
    )
    with _LOCK:
        cfg = load_config()
        videos = {video["id"]: video for video in load_videos()}
        video = videos.get(video_id)
        if not video:
            _finish_job()
            return
        tracker.reset(video["id"], title=video["title"], message="Chuẩn bị đăng Facebook")
        version = cfg["api_version"]
        page_id = cfg["page_id"]
        raw_token = cfg["token"]

    tracker.begin("check", "Kiểm tra token & video ngắn AI")
    if not raw_token or not page_id:
        _fail(video, "Chưa có Page Access Token cho hàng Douyin.", tracker)
        return
    short = ai_short_path(video["id"])
    if not short:
        _fail(video, "Chưa có video ngắn AI. Tạo video ngắn rồi mới đăng Facebook.", tracker)
        return
    path = str(short)
    tracker.ok("check", "Sẵn sàng")

    tracker.begin("caption", "Chuẩn bị nội dung tiếng Việt")
    try:
        caption = caption_for_post(video)
    except Exception as exc:
        _fail(video, f"Không dịch được sang tiếng Việt: {exc}"[:400], tracker)
        return
    if not caption:
        _fail(video, "Chưa có nội dung tiếng Việt để đăng.", tracker)
        return
    tracker.ok("caption", caption.splitlines()[0][:120])

    tracker.begin("auth", "Xác thực Page Access Token")
    try:
        token, name = _page_token(page_id, raw_token, version)
    except FBError as exc:
        _fail(video, str(exc)[:400], tracker)
        return
    page = {"id": page_id, "token": token}
    with _LOCK:
        cfg = load_config()
        if cfg.get("token") != token or (name and cfg.get("page_name") != name):
            cfg["token"] = token
            if name:
                cfg["page_name"] = name
            save_config(cfg)
    tracker.ok("auth", name or page_id)

    tracker.begin("upload", "Tải video lên Facebook")
    try:
        fb_id = upload_video(page, path, caption, version)
    except FBError as exc:
        message = str(exc)
        if getattr(exc, "code", None) == 190:
            message = "Token hết hạn hoặc không hợp lệ. Mở Config, dán Page Access Token rồi bấm Lưu token."
        else:
            tip = hint_for(exc)
            if tip:
                message = f"{message} {tip}"
        _fail(video, message[:400], tracker)
        return
    except OSError as exc:
        _fail(video, f"Không đọc được file: {exc}"[:400], tracker)
        return
    except Exception as exc:
        _fail(video, f"Lỗi không xác định: {exc}"[:400], tracker)
        return
    tracker.ok("upload", f"fb_id={fb_id}")

    tracker.begin("permalink", "Lấy link bài đăng")
    link = _permalink(fb_id, token, version)
    tracker.ok("permalink", link or "(không có permalink)")
    tracker.succeed(message="Đã đăng video ngắn AI lên Page", permalink=link, remote_id=fb_id)

    with _LOCK:
        posts = load_posts()
        posts["last_posted_at"] = now_str()
        posts.setdefault("items", {})[video["id"]] = {
            "status": "published",
            "facebook_video_id": fb_id,
            "permalink": link,
            "error": "",
            "posted_at": posts["last_posted_at"],
            "progress": tracker.snapshot(
                status="done",
                message="Đã đăng video ngắn AI lên Page",
                permalink=link,
                remote_id=fb_id,
            ),
        }
        _append_log(posts, video, True, "Đã đăng video ngắn AI lên Page")
        save_posts(posts)
        _finish_job()


def start_post(video_id: str) -> dict:
    with _LOCK:
        if _JOB["running"]:
            raise RuntimeError("Đang đăng một video Douyin khác. Hãy đợi video hiện tại xong.")
        videos = {video["id"]: video for video in load_videos()}
        posts = load_posts()
        video = videos.get(str(video_id or ""))
        if video_id == "next" or not video_id:
            order = load_config()["auto"]["order"]
            pending = queue(list(videos.values()), posts, order)
            if not pending:
                raise RuntimeError("Không còn video ngắn AI chưa đăng. Hãy tạo video ngắn trước.")
            video = pending[0]
        if not video:
            raise RuntimeError("Không thấy video này trong kho Douyin.")
        # Cho phép đăng lại thủ công; hàng đợi auto vẫn chỉ lấy pending.
        if not ai_short_path(video["id"]):
            raise RuntimeError("Chưa có video ngắn AI. Mở Xem trước → Tạo video ngắn rồi đăng.")
        _JOB.update(running=True, video_id=video["id"], title=video["title"], message="Chuẩn bị đăng video ngắn")
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
        order = cfg["auto"]["order"]
    pending = queue(load_videos(), posts, order)
    if not pending:
        return
    video_id = pending[0]["id"]
    with _LOCK:
        if _JOB["running"]:
            return
        _JOB.update(running=True, video_id=video_id, title=pending[0]["title"], message="Tự động đăng Douyin")
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
    with _LOCK:
        started = getattr(start_scheduler, "_started", False)
        start_scheduler._started = True
    if started:
        return
    threading.Thread(target=scheduler, name="dy-fb-auto", daemon=True).start()
