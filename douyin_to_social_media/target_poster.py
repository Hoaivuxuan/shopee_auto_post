"""Hàng đợi đăng chung cho các đích (YouTube / TikTok / Instagram).

Mỗi đích có config + posts riêng; dùng chung kho Douyin + video ngắn AI.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import douyin_poster as fb
import progress
from poster import VN_TZ, _interval

UploadFn = Callable[..., dict]
AuthStatusFn = Callable[[dict], dict]


class TargetPoster:
    def __init__(
        self,
        *,
        target: str,
        label: str,
        data_dir: Path,
        config_name: str,
        posts_name: str,
        empty_config: dict,
        upload: UploadFn,
        auth_status: AuthStatusFn | None = None,
        id_field: str = "remote_id",
        scheduler_name: str = "dy-target-auto",
    ) -> None:
        self.target = target
        self.label = label
        self.data_dir = data_dir
        self.config_path = data_dir / config_name
        self.posts_path = data_dir / posts_name
        self.empty_config = empty_config
        self.upload = upload
        self.auth_status = auth_status or (lambda _cfg: {"has_auth": True})
        self.id_field = id_field
        self.scheduler_name = scheduler_name
        self._lock = threading.RLock()
        self._job = {
            "running": False,
            "video_id": "",
            "title": "",
            "message": "",
            "status": "",
            "current_step": "",
            "error": "",
            "steps": {},
            "progress": progress.progress_payload(kind="publish", target=target, status="idle"),
        }
        self._auth_job = {"running": False, "message": ""}
        self._started = False

    def now(self) -> datetime:
        return datetime.now(VN_TZ)

    def now_str(self) -> str:
        return self.now().strftime("%Y-%m-%d %H:%M:%S")

    def _read_json(self, path: Path, fallback):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def load_config(self) -> dict:
        base = dict(self.empty_config)
        base["auto"] = dict(base.get("auto") or {"enabled": False, "interval_minutes": 60, "order": "oldest"})
        if not self.config_path.is_file():
            self.save_config(base)
            return base
        cfg = self._read_json(self.config_path, {})
        if not isinstance(cfg, dict):
            cfg = {}
        merged = {**base, **cfg}
        auto = merged.get("auto") if isinstance(merged.get("auto"), dict) else {}
        merged["auto"] = {
            "enabled": bool(auto.get("enabled")),
            "interval_minutes": _interval(auto.get("interval_minutes"), 60),
            "order": auto.get("order") if auto.get("order") in ("oldest", "newest") else "oldest",
        }
        return merged

    def save_config(self, cfg: dict) -> None:
        stored = {key: cfg.get(key, self.empty_config.get(key)) for key in self.empty_config}
        stored["auto"] = cfg.get("auto") or self.empty_config.get("auto") or {}
        self._write_json(self.config_path, stored)

    def load_posts(self) -> dict:
        data = self._read_json(self.posts_path, {})
        if not isinstance(data, dict):
            data = {}
        items = data.get("items") if isinstance(data.get("items"), dict) else {}
        log = data.get("log") if isinstance(data.get("log"), list) else []
        return {
            "last_posted_at": str(data.get("last_posted_at") or ""),
            "items": items,
            "log": log[:100],
        }

    def save_posts(self, posts: dict) -> None:
        posts["log"] = (posts.get("log") or [])[:100]
        self._write_json(self.posts_path, posts)

    def _status_of(self, video: dict, posts: dict) -> str:
        if self._job["running"] and self._job["video_id"] == video["id"]:
            return "posting"
        record = (posts.get("items") or {}).get(video["id"]) or {}
        status = record.get("status") or ""
        if status in ("published", "error"):
            return status
        if not video["has_file"]:
            return "missing"
        return "pending"

    def queue(self, videos: list[dict], posts: dict, order: str) -> list[dict]:
        pending = [
            video
            for video in videos
            if self._status_of(video, posts) == "pending" and fb.ai_short_path(video["id"])
        ]
        pending.sort(key=lambda video: (video.get("upload_date") or "", video["id"]))
        if order == "newest":
            pending.reverse()
        return pending

    def _public_video(self, video: dict, posts: dict) -> dict:
        import douyin_translate

        record = (posts.get("items") or {}).get(video["id"]) or {}
        saved = douyin_translate.lookup(video["id"])
        row = fb._public_video(video, {"items": {}})
        status = self._status_of(video, posts)
        live = dict(self._job)
        if live.get("running") and live.get("video_id") == video["id"]:
            pub = live.get("progress") or progress.progress_payload(
                kind="publish",
                target=self.target,
                status="running",
                message=live.get("message") or "",
                current_step=live.get("current_step") or "",
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
                kind="publish",
                target=self.target,
                status="done",
                message="Đã đăng thành công",
                permalink=record.get("permalink") or "",
                remote_id=record.get(self.id_field) or "",
                finished_at=record.get("posted_at") or "",
                steps={k: {"status": "done", "label": lab} for k, lab in progress.defs_for("publish", self.target)},
            )
        elif status == "error":
            pub = progress.progress_payload(
                kind="publish",
                target=self.target,
                status="error",
                message=record.get("error") or "Lỗi đăng",
                error=record.get("error") or "",
            )
        else:
            pub = progress.progress_payload(kind="publish", target=self.target, status="idle")

        row.update({
            "caption": fb._caption(video),
            "caption_vi": str(saved.get("caption_vi") or ""),
            "translated": bool(str(saved.get("caption_vi") or "").strip()),
            "translation_engine": str(saved.get("engine") or ""),
            "has_ai_short": bool(fb.ai_short_path(video["id"])),
            "status": status,
            "facebook_video_id": "",
            "youtube_video_id": "",
            self.id_field: record.get(self.id_field) or record.get("remote_id") or "",
            "permalink": record.get("permalink") or "",
            "error": record.get("error") or "",
            "posted_at": record.get("posted_at") or "",
            "target": self.target,
            "publish": pub,
        })
        return row

    def _next_at(self, posts: dict, auto: dict) -> str:
        if not auto.get("enabled"):
            return ""
        last = posts.get("last_posted_at") or ""
        if not last:
            return self.now_str()
        try:
            stamp = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
        except ValueError:
            return self.now_str()
        return (stamp + timedelta(minutes=int(auto["interval_minutes"]))).strftime("%Y-%m-%d %H:%M:%S")

    def page_info(self, cfg: dict, auth: dict) -> dict:
        return {
            "id": str(auth.get("account_id") or cfg.get("account_id") or ""),
            "name": str(auth.get("account_name") or cfg.get("account_name") or self.label),
            "url": str(auth.get("account_url") or cfg.get("account_url") or ""),
            "has_token": bool(auth.get("has_auth")),
        }

    def public_state(self) -> dict:
        with self._lock:
            cfg = self.load_config()
            posts = self.load_posts()
            videos = fb.load_videos()
            listed = [self._public_video(video, posts) for video in videos]
            pending = self.queue(videos, posts, cfg["auto"]["order"])
            counts = {"total": len(listed), "pending": 0, "published": 0, "error": 0, "missing": 0, "posting": 0}
            for item in listed:
                counts[item["status"]] = counts.get(item["status"], 0) + 1
            nxt = pending[0] if pending else None
            next_row = None
            if nxt:
                shown = self._public_video(nxt, posts)
                next_row = {
                    "id": nxt["id"],
                    "title": (shown.get("caption") or nxt["title"] or "").splitlines()[0][:160],
                }
            auth = self.auth_status(cfg)
            if auth.get("account_name") and auth["account_name"] != cfg.get("account_name"):
                cfg["account_name"] = auth["account_name"]
                if auth.get("account_id"):
                    cfg["account_id"] = auth["account_id"]
                if auth.get("account_url"):
                    cfg["account_url"] = auth["account_url"]
                self.save_config(cfg)
            return {
                "ok": True,
                "source": "douyin",
                "target": self.target,
                "page": self.page_info(cfg, auth),
                self.target: {
                    **auth,
                    "auth_job": dict(self._auth_job),
                    **{k: cfg.get(k) for k in self.empty_config if k != "auto"},
                },
                "auto": {
                    **cfg["auto"],
                    "next_at": self._next_at(posts, cfg["auto"]),
                    "last_posted_at": posts.get("last_posted_at") or "",
                },
            "job": {
                **dict(self._job),
                "progress": self._job.get("progress")
                or progress.progress_payload(kind="publish", target=self.target, status="idle"),
            },
            "counts": counts,
            "next": next_row,
            "log": posts.get("log") or [],
            "videos": listed,
        }

    def update_settings(self, payload: dict) -> dict:
        with self._lock:
            cfg = self.load_config()
            auto = cfg["auto"]
            if "enabled" in payload:
                auto["enabled"] = bool(payload.get("enabled"))
            if "interval_minutes" in payload:
                auto["interval_minutes"] = _interval(payload.get("interval_minutes"), auto["interval_minutes"])
            if "order" in payload and payload.get("order") in ("oldest", "newest"):
                auto["order"] = payload["order"]
            for key in self.empty_config:
                if key == "auto":
                    continue
                if key in payload and payload.get(key) is not None:
                    cfg[key] = payload[key]
            # token shortcut for Meta-style configs
            token = str(payload.get("token") or "").strip()
            if token and "access_token" in self.empty_config:
                cfg["access_token"] = token
            cfg["auto"] = auto
            self.save_config(cfg)
        return self.public_state()

    def _append_log(self, posts: dict, video: dict, ok: bool, message: str) -> None:
        posts.setdefault("log", []).insert(0, {
            "at": self.now_str(),
            "video_id": video["id"],
            "title": video["title"],
            "ok": ok,
            "message": message,
        })
        posts["log"] = posts["log"][:100]

    def _finish_job(self) -> None:
        self._job.update(running=False, video_id="", title="", message="")

    def _save_progress_record(self, video_id: str, payload: dict) -> None:
        posts = self.load_posts()
        item = dict(posts.setdefault("items", {}).get(video_id) or {})
        item.update(payload)
        if payload.get("remote_id"):
            item[self.id_field] = payload["remote_id"]
        if payload.get("status") == "published":
            posts["last_posted_at"] = payload.get("posted_at") or self.now_str()
            item["posted_at"] = posts["last_posted_at"]
        posts["items"][video_id] = item
        self.save_posts(posts)

    def _fail(self, video: dict, message: str, tracker: progress.PublishTracker | None = None) -> None:
        if tracker:
            tracker.fail(tracker.current_step or "check", message)
        posts = self.load_posts()
        posts["last_posted_at"] = self.now_str()
        prev = dict(posts.setdefault("items", {}).get(video["id"]) or {})
        posts["items"][video["id"]] = {
            **prev,
            "status": "error",
            self.id_field: prev.get(self.id_field) or "",
            "permalink": "",
            "error": message,
            "posted_at": "",
            "progress": (tracker.snapshot(status="error", message=message, error=message) if tracker else prev.get("progress")),
        }
        self._append_log(posts, video, False, message)
        self.save_posts(posts)
        self._finish_job()

    def post_video(self, video_id: str) -> None:
        tracker = progress.PublishTracker(
            target=self.target,
            lock=self._lock,
            job=self._job,
            save_record=self._save_progress_record,
        )
        with self._lock:
            cfg = self.load_config()
            videos = {video["id"]: video for video in fb.load_videos()}
            video = videos.get(video_id)
            if not video:
                self._finish_job()
                return
            tracker.reset(video["id"], title=video["title"], message=f"Chuẩn bị đăng {self.label}")

        tracker.begin("check", f"Kiểm tra ủy quyền & video ngắn AI ({self.label})")
        auth = self.auth_status(cfg)
        if not auth.get("has_auth"):
            self._fail(video, auth.get("error") or f"Chưa cấu hình / ủy quyền {self.label}.", tracker)
            return
        short = fb.ai_short_path(video["id"])
        if not short:
            self._fail(video, f"Chưa có video ngắn AI. Tạo video ngắn rồi mới đăng {self.label}.", tracker)
            return
        tracker.ok("check", "Sẵn sàng")

        tracker.begin("caption", "Chuẩn bị nội dung tiếng Việt")
        try:
            caption = fb.caption_for_post(video)
        except Exception as exc:
            self._fail(video, f"Không dịch được sang tiếng Việt: {exc}"[:400], tracker)
            return
        if not caption:
            self._fail(video, "Chưa có nội dung tiếng Việt để đăng.", tracker)
            return
        title = caption.splitlines()[0].strip() or video.get("title") or video["id"]
        tracker.ok("caption", title[:120])

        # Các bước upload theo nền tảng (map vào defs còn lại)
        upload_steps = [k for k, _ in progress.defs_for("publish", self.target) if k not in ("check", "caption")]
        first_upload = upload_steps[0] if upload_steps else "upload"
        tracker.begin(first_upload, f"Đang tải lên {self.label}")

        def on_step(step_id: str, message: str = "", *, done: bool = False, detail: str = "") -> None:
            if step_id not in dict(progress.defs_for("publish", self.target)):
                return
            if done:
                if tracker.current_step and tracker.current_step != step_id:
                    tracker.ok(tracker.current_step)
                tracker.begin(step_id, message or step_id)
                tracker.ok(step_id, detail or message)
            else:
                if tracker.current_step and tracker.current_step != step_id:
                    st = (tracker.steps.get(tracker.current_step) or {}).get("status")
                    if st == "running":
                        tracker.ok(tracker.current_step)
                tracker.begin(step_id, message or step_id)

        try:
            result = self.upload(
                str(short),
                title=title,
                caption=caption,
                config=self.load_config(),
                on_step=on_step,
            )
            if not result.get("ok"):
                raise RuntimeError(result.get("message") or f"Đăng {self.label} thất bại")
        except TypeError:
            # upload() chưa nhận on_step
            try:
                result = self.upload(
                    str(short),
                    title=title,
                    caption=caption,
                    config=self.load_config(),
                )
                if not result.get("ok"):
                    raise RuntimeError(result.get("message") or f"Đăng {self.label} thất bại")
            except Exception as exc:
                self._fail(video, str(exc)[:400], tracker)
                return
        except Exception as exc:
            self._fail(video, str(exc)[:400], tracker)
            return

        remote_id = result.get(self.id_field) or result.get("post_id") or ""
        link = result.get("permalink") or ""
        for step_id in upload_steps:
            st = (tracker.steps.get(step_id) or {}).get("status")
            if st in ("pending", "running"):
                tracker.ok(step_id, "OK")
        tracker.succeed(
            message=result.get("message") or f"Đã đăng lên {self.label}",
            permalink=link,
            remote_id=remote_id,
        )
        with self._lock:
            posts = self.load_posts()
            posts["last_posted_at"] = self.now_str()
            posts.setdefault("items", {})[video["id"]] = {
                **dict(posts.get("items", {}).get(video["id"]) or {}),
                "status": "published",
                self.id_field: remote_id,
                "permalink": link,
                "error": "",
                "posted_at": posts["last_posted_at"],
                "progress": tracker.snapshot(
                    status="done",
                    message=f"Đã đăng lên {self.label}",
                    permalink=link,
                    remote_id=remote_id,
                ),
            }
            self._append_log(posts, video, True, f"Đã đăng video ngắn AI lên {self.label}")
            self.save_posts(posts)
            self._finish_job()

    def start_post(self, video_id: str) -> dict:
        with self._lock:
            if self._job["running"]:
                raise RuntimeError(f"Đang đăng một video lên {self.label}. Hãy đợi xong.")
            videos = {video["id"]: video for video in fb.load_videos()}
            posts = self.load_posts()
            video = videos.get(str(video_id or ""))
            if video_id == "next" or not video_id:
                order = self.load_config()["auto"]["order"]
                pending = self.queue(list(videos.values()), posts, order)
                if not pending:
                    raise RuntimeError(f"Không còn video ngắn AI chưa đăng {self.label}.")
                video = pending[0]
            if not video:
                raise RuntimeError("Không thấy video này trong kho Douyin.")
            # Cho phép đăng lại thủ công; hàng đợi auto vẫn chỉ lấy pending.
            if not fb.ai_short_path(video["id"]):
                raise RuntimeError("Chưa có video ngắn AI. Mở Xem trước → Tạo video ngắn rồi đăng.")
            self._job.update(
                running=True,
                video_id=video["id"],
                title=video["title"],
                message=f"Chuẩn bị đăng {self.label}",
            )
            chosen = video["id"]
        threading.Thread(target=self.post_video, args=(chosen,), daemon=True).start()
        return self.public_state()

    def _due(self, posts: dict, auto: dict) -> bool:
        if not auto.get("enabled"):
            return False
        last = posts.get("last_posted_at") or ""
        if not last:
            return True
        try:
            stamp = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
        except ValueError:
            return True
        return self.now() >= stamp + timedelta(minutes=int(auto["interval_minutes"]))

    def maybe_auto_post(self) -> None:
        with self._lock:
            if self._job["running"]:
                return
            cfg = self.load_config()
            posts = self.load_posts()
            if not self._due(posts, cfg["auto"]):
                return
            pending = self.queue(fb.load_videos(), posts, cfg["auto"]["order"])
            if not pending:
                return
            video_id = pending[0]["id"]
            self._job.update(
                running=True,
                video_id=video_id,
                title=pending[0]["title"],
                message=f"Tự động đăng {self.label}",
            )
        self.post_video(video_id)

    def scheduler(self) -> None:
        while True:
            try:
                self.maybe_auto_post()
            except Exception:
                with self._lock:
                    self._finish_job()
            threading.Event().wait(15)

    def start_scheduler(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self.scheduler, name=self.scheduler_name, daemon=True).start()

    def run_auth_job(self, runner: Callable[[], dict]) -> dict:
        with self._lock:
            if self._auth_job["running"]:
                raise RuntimeError(f"Đang chạy OAuth {self.label}.")
            if self._job["running"]:
                raise RuntimeError("Đang đăng video. Đợi xong rồi mới ủy quyền.")
            self._auth_job.update(running=True, message=f"Đang ủy quyền {self.label}…")

        def _run() -> None:
            try:
                result = runner()
                with self._lock:
                    cfg = self.load_config()
                    for key in ("account_id", "account_name", "account_url", "open_id", "access_token", "refresh_token"):
                        if result.get(key):
                            cfg[key] = result[key]
                    self.save_config(cfg)
                    self._auth_job.update(running=False, message=result.get("message") or "Đã ủy quyền")
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._auth_job.update(running=False, message=str(exc)[:400])

        threading.Thread(target=_run, name=f"{self.target}-oauth", daemon=True).start()
        return self.public_state()
