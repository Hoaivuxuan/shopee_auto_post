#!/usr/bin/env python3
"""Admin douyin_to_social_media: Douyin → video ngắn → FB / YT / TikTok / IG.

Chạy:  .venv/bin/python douyin_to_social_media/admin_web.py
Mở:    http://127.0.0.1:8766 hoặc http://<ip-máy>:8766
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import douyin_ai_job  # noqa: E402
import douyin_download  # noqa: E402
import douyin_instagram_poster  # noqa: E402
import douyin_poster  # noqa: E402
import douyin_tiktok_poster  # noqa: E402
import douyin_translate  # noqa: E402
import douyin_youtube_poster  # noqa: E402

_TARGETS = {
    "facebook": douyin_poster,
    "youtube": douyin_youtube_poster,
    "tiktok": douyin_tiktok_poster,
    "instagram": douyin_instagram_poster,
}

HOST = os.environ.get("DTS_HOST") or os.environ.get("YT_FB_HOST", "0.0.0.0")
PORT = int(os.environ.get("DTS_PORT") or os.environ.get("YT_FB_PORT", "8766"))
WEB = ROOT / "web"
_STATIC_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".map": "application/json",
}
# Cache state ngắn — poll UI 4–10s tái sử dụng kết quả vừa build.
_STATE_TTL = 0.9
_STATE_CACHE: dict[str, tuple[float, dict]] = {}
_STATE_LOCK = threading.Lock()


def _invalidate_state_cache() -> None:
    with _STATE_LOCK:
        _STATE_CACHE.clear()


def _state_for(target: str) -> dict:
    now = time.monotonic()
    with _STATE_LOCK:
        hit = _STATE_CACHE.get(target)
        if hit and now - hit[0] < _STATE_TTL:
            return hit[1]
    payload = _decorate_douyin(_poster(target).public_state())
    with _STATE_LOCK:
        _STATE_CACHE[target] = (time.monotonic(), payload)
    return payload


def _web_file(url_path: str) -> Path | None:
    """Chỉ phục vụ file tĩnh trong thư mục web do bản build React tạo."""
    rel = unquote(url_path).lstrip("/")
    if not rel or rel == "index.html" or ".." in rel.split("/"):
        return None
    root = WEB.resolve()
    path = (WEB / rel).resolve()
    if path != root and root not in path.parents:
        return None
    if not path.is_file():
        return None
    return path


def _stream_media(handler: BaseHTTPRequestHandler, path: Path) -> None:
    size = path.stat().st_size
    start, end = 0, max(size - 1, 0)
    status = 200
    header = handler.headers.get("Range") or ""
    if header.startswith("bytes=") and size:
        piece = header.split("=", 1)[1].split(",", 1)[0].strip()
        left, _, right = piece.partition("-")
        try:
            if left == "" and right:
                start = max(size - int(right), 0)
            elif left:
                start = int(left)
                if right:
                    end = int(right)
        except ValueError:
            start, end = 0, size - 1
        if start >= size:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.end_headers()
            return
        end = min(end, size - 1)
        status = 206
    length = 0 if size == 0 else end - start + 1
    kind = "video/mp4" if path.suffix.lower() == ".mp4" else "application/octet-stream"
    handler.send_response(status)
    handler.send_header("Content-Type", kind)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if handler.command == "HEAD" or length <= 0:
        return
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(256 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


def _target_of(raw: str | None) -> str:
    value = str(raw or "facebook").strip().lower()
    return value if value in _TARGETS else "facebook"


def _poster(target: str):
    return _TARGETS[_target_of(target)]


def _decorate_douyin(payload: dict) -> dict:
    payload["sync"] = douyin_download.sync_status()
    payload["sync_auto"] = douyin_download.sync_auto_status()
    payload["translate"] = douyin_translate.batch_status()
    payload["ai_job"] = douyin_ai_job.job_status()
    douyin_ai_job.enrich_videos(payload.get("videos") or [])
    payload["source"] = "douyin"
    payload.setdefault("target", "facebook")
    return payload


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code: int, body, content_type: str) -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        encode = "gzip" in (self.headers.get("Accept-Encoding") or "") and len(data) > 2048
        if encode:
            data = gzip.compress(data, compresslevel=4)
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if encode:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu không hợp lệ")
        return data

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            page = WEB / "index.html"
            self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            return
        static = _web_file(path)
        if static is not None:
            kind = _STATIC_TYPES.get(static.suffix.lower(), "application/octet-stream")
            self._send(200, static.read_bytes(), kind)
            return
        if path == "/api/douyin/state":
            target = _target_of((query.get("target") or ["facebook"])[0])
            self._json(200, _state_for(target))
            return
        if path.startswith("/api/douyin/media/"):
            video_id = path.removeprefix("/api/douyin/media/").split("/", 1)[0]
            media = douyin_poster.media_path(video_id)
            if media is None:
                self._json(404, {"ok": False, "error": "Không thấy file video"})
                return
            try:
                _stream_media(self, media)
            except (BrokenPipeError, ConnectionResetError):
                return
            return
        if path.startswith("/api/douyin/ai-media/"):
            video_id = path.removeprefix("/api/douyin/ai-media/").split("/", 1)[0]
            media = douyin_ai_job.ai_output_path(video_id)
            if media is None:
                self._json(404, {"ok": False, "error": "Chưa có video ngắn AI"})
                return
            try:
                _stream_media(self, media)
            except (BrokenPipeError, ConnectionResetError):
                return
            return
        self._json(404, {"ok": False, "error": "Không thấy trang"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"ok": False, "error": "Dữ liệu gửi lên không đọc được"})
            return
        try:
            target = _target_of(body.get("target"))
            poster = _poster(target)
            _invalidate_state_cache()

            if path == "/api/douyin/settings":
                self._json(200, _decorate_douyin(poster.update_settings(body)))
                return
            if path == "/api/douyin/post":
                self._json(200, _decorate_douyin(poster.start_post(str(body.get("id") or "next"))))
                return
            if path == "/api/douyin/youtube/auth":
                self._json(200, _decorate_douyin(douyin_youtube_poster.start_oauth()))
                return
            if path == "/api/douyin/tiktok/auth":
                self._json(200, _decorate_douyin(douyin_tiktok_poster.start_oauth()))
                return
            if path == "/api/douyin/sync":
                payload = poster.public_state()
                payload["sync"] = douyin_download.start_sync(str(body.get("url") or ""))
                self._json(200, _decorate_douyin(payload))
                return
            if path == "/api/douyin/download":
                payload = poster.public_state()
                payload["sync"] = douyin_download.start_download(str(body.get("url") or ""))
                self._json(200, _decorate_douyin(payload))
                return
            if path == "/api/douyin/sync-auto":
                douyin_download.set_sync_auto(body)
                self._json(200, _decorate_douyin(poster.public_state()))
                return
            if path == "/api/douyin/translate":
                video_id = str(body.get("id") or "")
                videos = {item["id"]: item for item in douyin_poster.load_videos()}
                video = videos.get(video_id)
                if not video:
                    raise RuntimeError("Không thấy video này trong kho Douyin.")
                douyin_translate.ensure_video(video, force=bool(body.get("force")))
                self._json(200, _decorate_douyin(poster.public_state()))
                return
            if path == "/api/douyin/translate-all":
                douyin_translate.start_batch(douyin_poster.load_videos())
                self._json(200, _decorate_douyin(poster.public_state()))
                return
            if path == "/api/douyin/caption":
                caption = str(body.get("caption") or "")
                title_vi = body.get("title_vi")
                description_vi = body.get("description_vi")
                douyin_translate.save_caption(
                    str(body.get("id") or ""),
                    caption,
                    title_vi=None if title_vi is None else str(title_vi),
                    description_vi=None if description_vi is None else str(description_vi),
                )
                self._json(200, _decorate_douyin(poster.public_state()))
                return
            if path == "/api/douyin/ai-process":
                douyin_ai_job.start_process(
                    str(body.get("id") or ""),
                    force=bool(body.get("force")),
                )
                self._json(200, _decorate_douyin(poster.public_state()))
                return
            if path == "/api/douyin/delete":
                result = douyin_download.delete_video(str(body.get("id") or ""))
                payload = _decorate_douyin(poster.public_state())
                payload["delete"] = result
                self._json(200, payload)
                return
        except RuntimeError as exc:
            self._json(409, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(404, {"ok": False, "error": "Không thấy trang"})


def main() -> None:
    douyin_download.ensure_account_tags()
    for module in _TARGETS.values():
        module.start_scheduler()
    douyin_download.start_sync_scheduler()
    douyin_translate.kick_batch()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Douyin → Social: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
