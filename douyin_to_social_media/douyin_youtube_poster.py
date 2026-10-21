"""Hàng đợi đăng video ngắn Douyin lên YouTube Shorts."""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA = ROOT / "data" / "douyin"
CONFIG_PATH = DATA / "youtube_config.json"
POSTS_PATH = DATA / "youtube_posts.json"
TOKEN_PATH = DATA / "youtube_token.json"
DEFAULT_SECRETS = DATA / "client_secrets.json"

if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import douyin_poster as fb  # noqa: E402
import progress  # noqa: E402
from poster import VN_TZ, _interval  # noqa: E402
from publishers import youtube as yt  # noqa: E402

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
    "progress": progress.progress_payload(kind="publish", target="youtube", status="idle"),
}
_AUTH_JOB = {"running": False, "message": ""}


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
    return {
        "client_secrets": "client_secrets.json",
        "privacy_status": "public",
        "category_id": "22",
        "channel_id": "",
        "channel_title": "",
        "oauth_port": 8767,
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
    base = _empty_config()
    auto = cfg.get("auto") if isinstance(cfg.get("auto"), dict) else {}
    cfg["auto"] = {
        "enabled": bool(auto.get("enabled")),
        "interval_minutes": _interval(auto.get("interval_minutes"), 60),
        "order": auto.get("order") if auto.get("order") in ("oldest", "newest") else "oldest",
    }
    for key in ("client_secrets", "privacy_status", "category_id", "channel_id", "channel_title"):
        cfg[key] = str(cfg.get(key) or base[key])
    try:
        cfg["oauth_port"] = int(cfg.get("oauth_port") or 8767)
    except (TypeError, ValueError):
        cfg["oauth_port"] = 8767
    return cfg


def save_config(cfg: dict) -> None:
    stored = {
        "client_secrets": cfg.get("client_secrets") or "client_secrets.json",
        "privacy_status": cfg.get("privacy_status") or "public",
        "category_id": cfg.get("category_id") or "22",
        "channel_id": cfg.get("channel_id") or "",
        "channel_title": cfg.get("channel_title") or "",
        "oauth_port": int(cfg.get("oauth_port") or 8767),
        "auto": cfg.get("auto") or {},
    }
    _write_json(CONFIG_PATH, stored)


def secrets_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    return yt.resolve_secrets_path(DATA, cfg.get("client_secrets") or "client_secrets.json")


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
    pending = [
        video
        for video in videos
        if _status_of(video, posts) == "pending" and fb.ai_short_path(video["id"])
    ]
    pending.sort(key=lambda video: (video.get("upload_date") or "", video["id"]))
    if order == "newest":
        pending.reverse()
    return pending


def _public_video(video: dict, posts: dict) -> dict:
    import douyin_translate

    record = (posts.get("items") or {}).get(video["id"]) or {}
    saved = douyin_translate.lookup(video["id"])
    status = _status_of(video, posts)
    live = dict(_JOB)
    if live.get("running") and live.get("video_id") == video["id"]:
        pub = live.get("progress") or progress.progress_payload(
            kind="publish", target="youtube", status="running",
            message=live.get("message") or "", current_step=live.get("current_step") or "",
            steps=live.get("steps") if isinstance(live.get("steps"), dict) else {},
        )
    elif isinstance(record.get("progress"), dict):
        pub = dict(record["progress"])
        if status == "published":
            pub["status"] = "done"
            pub["permalink"] = record.get("permalink") or pub.get("permalink") or ""
        if status == "error":
            pub["status"] = "error"
            pub["error"] = record.get("error") or pub.get("error") or ""
    elif status == "published":
        pub = progress.progress_payload(
            kind="publish", target="youtube", status="done", message="Đã đăng thành công",
            permalink=record.get("permalink") or "", remote_id=record.get("youtube_video_id") or "",
            finished_at=record.get("posted_at") or "",
            steps={k: {"status": "done", "label": lab} for k, lab in progress.defs_for("publish", "youtube")},
        )
    elif status == "error":
        pub = progress.progress_payload(
            kind="publish", target="youtube", status="error",
            message=record.get("error") or "Lỗi đăng", error=record.get("error") or "",
        )
    else:
        pub = progress.progress_payload(kind="publish", target="youtube", status="idle")

    row = fb._public_video(video, {"items": {}})  # base fields, ignore FB posts
    yt_copy = douyin_translate.youtube_copy(video, saved)
    row.update({
        "caption": fb._caption(video),
        "caption_vi": yt_copy.get("caption_vi") or str(saved.get("caption_vi") or ""),
        "title_vi": yt_copy.get("title_vi") or "",
        "description_vi": yt_copy.get("description_vi") or "",
        "translated": bool(str(saved.get("caption_vi") or yt_copy.get("title_vi") or "").strip()),
        "translation_engine": str(saved.get("engine") or ""),
        "has_ai_short": bool(fb.ai_short_path(video["id"])),
        "status": status,
        "facebook_video_id": "",
        "youtube_video_id": record.get("youtube_video_id") or "",
        "permalink": record.get("permalink") or "",
        "error": record.get("error") or "",
        "posted_at": record.get("posted_at") or "",
        "target": "youtube",
        "publish": pub,
    })
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
    with _LOCK:
        cfg = load_config()
        posts = load_posts()
        videos = fb.load_videos()
        listed = [_public_video(video, posts) for video in videos]
        pending = queue(videos, posts, cfg["auto"]["order"])
        counts = {"total": len(listed), "pending": 0, "published": 0, "error": 0, "missing": 0, "posting": 0}
        for item in listed:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        nxt = pending[0] if pending else None
        next_row = None
        if nxt:
            shown = _public_video(nxt, posts)
            next_row = {
                "id": nxt["id"],
                "title": (shown.get("caption") or nxt["title"] or "").splitlines()[0][:160],
            }
        auth = yt.auth_status(TOKEN_PATH, secrets_path(cfg))
        if auth.get("channel_title") and auth["channel_title"] != cfg.get("channel_title"):
            cfg["channel_title"] = auth["channel_title"]
            cfg["channel_id"] = auth.get("channel_id") or cfg.get("channel_id") or ""
            save_config(cfg)
        return {
            "ok": True,
            "source": "douyin",
            "target": "youtube",
            "page": {
                "id": cfg.get("channel_id") or auth.get("channel_id") or "",
                "name": cfg.get("channel_title") or auth.get("channel_title") or "YouTube",
                "url": (
                    f"https://www.youtube.com/channel/{cfg['channel_id']}"
                    if cfg.get("channel_id")
                    else "https://www.youtube.com"
                ),
                "has_token": bool(auth.get("has_auth")),
            },
            "youtube": {
                **auth,
                "privacy_status": cfg.get("privacy_status") or "public",
                "category_id": cfg.get("category_id") or "22",
                "auth_job": dict(_AUTH_JOB),
            },
            "auto": {
                **cfg["auto"],
                "next_at": _next_at(posts, cfg["auto"]),
                "last_posted_at": posts.get("last_posted_at") or "",
            },
            "job": dict(_JOB),
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
        if "privacy_status" in payload and payload.get("privacy_status") in ("public", "unlisted", "private"):
            cfg["privacy_status"] = payload["privacy_status"]
        if "category_id" in payload and str(payload.get("category_id") or "").strip():
            cfg["category_id"] = str(payload["category_id"]).strip()
        if "client_secrets" in payload and str(payload.get("client_secrets") or "").strip():
            cfg["client_secrets"] = str(payload["client_secrets"]).strip()
        cfg["auto"] = auto
        save_config(cfg)
    return public_state()


def start_oauth() -> dict:
    with _LOCK:
        if _AUTH_JOB["running"]:
            raise RuntimeError("Đang chạy OAuth YouTube. Hãy hoàn tất cửa sổ trình duyệt hiện tại.")
        if _JOB["running"]:
            raise RuntimeError("Đang đăng video. Đợi xong rồi mới ủy quyền.")
        cfg = load_config()
        secrets = secrets_path(cfg)
        if not secrets.is_file():
            raise RuntimeError(
                f"Chưa có {secrets.name}. Tải OAuth Client (Desktop) từ Google Cloud, "
                f"lưu vào {secrets}"
            )
        _AUTH_JOB.update(running=True, message="Mở trình duyệt để đăng nhập Google…")
        port = int(cfg.get("oauth_port") or 8767)

    def _run() -> None:
        try:
            result = yt.start_oauth(secrets, TOKEN_PATH, port=port)
            with _LOCK:
                cfg = load_config()
                cfg["channel_id"] = result.get("channel_id") or cfg.get("channel_id") or ""
                cfg["channel_title"] = result.get("channel_title") or cfg.get("channel_title") or ""
                save_config(cfg)
                _AUTH_JOB.update(running=False, message=result.get("message") or "Đã ủy quyền")
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                _AUTH_JOB.update(running=False, message=str(exc)[:400])

    threading.Thread(target=_run, name="yt-oauth", daemon=True).start()
    return public_state()


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
        item["youtube_video_id"] = payload["remote_id"]
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
        "youtube_video_id": prev.get("youtube_video_id") or "",
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
        target="youtube",
        lock=_LOCK,
        job=_JOB,
        save_record=_save_progress_record,
    )
    with _LOCK:
        cfg = load_config()
        videos = {video["id"]: video for video in fb.load_videos()}
        video = videos.get(video_id)
        if not video:
            _finish_job()
            return
        tracker.reset(video["id"], title=video["title"], message="Chuẩn bị đăng YouTube")
        privacy = cfg.get("privacy_status") or "public"
        category = cfg.get("category_id") or "22"
        secrets = secrets_path(cfg)

    tracker.begin("check", "Kiểm tra OAuth & video ngắn AI")
    auth = yt.auth_status(TOKEN_PATH, secrets)
    if not auth.get("has_auth"):
        _fail(video, auth.get("error") or "Chưa ủy quyền YouTube. Vào Cấu hình → Ủy quyền YouTube.", tracker)
        return
    short = fb.ai_short_path(video["id"])
    if not short:
        _fail(video, "Chưa có video ngắn AI. Tạo video ngắn rồi mới đăng YouTube.", tracker)
        return
    tracker.ok("check", auth.get("channel_title") or "OK")

    tracker.begin("caption", "Chuẩn bị tiêu đề / mô tả")
    try:
        import douyin_translate

        saved = douyin_translate.lookup(video["id"])
        if not str(saved.get("caption_vi") or saved.get("title_vi") or "").strip():
            blob = f"{video.get('title') or ''}\n{video.get('description') or ''}"
            if douyin_translate.looks_chinese(blob):
                saved = douyin_translate.ensure_video(video, force=False)
        yt_copy = douyin_translate.youtube_copy(video, saved)
        title = yt_copy.get("title_vi") or video.get("title") or video["id"]
        description = yt_copy.get("description_vi") or yt_copy.get("caption_vi") or title
    except Exception as exc:
        _fail(video, f"Không dịch được sang tiếng Việt: {exc}"[:400], tracker)
        return
    if not str(title or "").strip():
        _fail(video, "Chưa có tiêu đề tiếng Việt để đăng YouTube.", tracker)
        return
    tracker.ok("caption", f"{str(title)[:80]} · mô tả {len(str(description or ''))} ký tự")

    tracker.begin("upload", "Upload YouTube Shorts")
    try:
        result = yt.upload_short(
            short,
            title=title,
            description=description,
            token_path=TOKEN_PATH,
            secrets_path=secrets,
            privacy_status=privacy,
            category_id=category,
        )
    except yt.YouTubeError as exc:
        _fail(video, str(exc)[:400], tracker)
        return
    except Exception as exc:
        _fail(video, f"Lỗi không xác định: {exc}"[:400], tracker)
        return
    yt_id = result.get("youtube_video_id") or ""
    link = result.get("permalink") or ""
    tracker.ok("upload", yt_id or "OK")
    tracker.begin("done", "Xác nhận đã đăng")
    tracker.ok("done", link or yt_id)
    tracker.succeed(message="Đã đăng video ngắn AI lên YouTube Shorts", permalink=link, remote_id=yt_id)

    with _LOCK:
        posts = load_posts()
        posts["last_posted_at"] = now_str()
        posts.setdefault("items", {})[video["id"]] = {
            "status": "published",
            "youtube_video_id": yt_id,
            "permalink": link,
            "error": "",
            "posted_at": posts["last_posted_at"],
            "progress": tracker.snapshot(
                status="done",
                message="Đã đăng video ngắn AI lên YouTube Shorts",
                permalink=link,
                remote_id=yt_id,
            ),
        }
        _append_log(posts, video, True, "Đã đăng video ngắn AI lên YouTube Shorts")
        save_posts(posts)
        _finish_job()


def start_post(video_id: str) -> dict:
    with _LOCK:
        if _JOB["running"]:
            raise RuntimeError("Đang đăng một video Douyin khác lên YouTube. Hãy đợi xong.")
        videos = {video["id"]: video for video in fb.load_videos()}
        posts = load_posts()
        video = videos.get(str(video_id or ""))
        if video_id == "next" or not video_id:
            order = load_config()["auto"]["order"]
            pending = queue(list(videos.values()), posts, order)
            if not pending:
                raise RuntimeError("Không còn video ngắn AI chưa đăng YouTube. Hãy tạo video ngắn trước.")
            video = pending[0]
        if not video:
            raise RuntimeError("Không thấy video này trong kho Douyin.")
        # Cho phép đăng lại thủ công (đã đăng trước đó); hàng đợi auto vẫn chỉ lấy pending.
        if not fb.ai_short_path(video["id"]):
            raise RuntimeError("Chưa có video ngắn AI. Mở Xem trước → Tạo video ngắn rồi đăng.")
        _JOB.update(running=True, video_id=video["id"], title=video["title"], message="Chuẩn bị đăng YouTube")
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
        pending = queue(fb.load_videos(), posts, cfg["auto"]["order"])
        if not pending:
            return
        video_id = pending[0]["id"]
        _JOB.update(running=True, video_id=video_id, title=pending[0]["title"], message="Tự động đăng YouTube")
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
    threading.Thread(target=scheduler, name="dy-yt-auto", daemon=True).start()
