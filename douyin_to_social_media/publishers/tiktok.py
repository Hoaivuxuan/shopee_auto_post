"""Upload Douyin short → TikTok (Content Posting API — Direct Post / FILE_UPLOAD)."""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests

name = "tiktok"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Direct post scopes (app phải được duyệt video.publish)
SCOPES = "user.info.basic,video.publish"


class TikTokError(RuntimeError):
    pass


def _cfg_get(config: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = str(config.get(key) or "").strip()
        if value:
            return value
    return default


def token_path(data_dir: Path) -> Path:
    return data_dir / "tiktok_token.json"


def load_token(data_dir: Path) -> dict:
    path = token_path(data_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_token(data_dir: Path, payload: dict) -> None:
    path = token_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_access_token(config: dict, data_dir: Path) -> dict:
    client_key = _cfg_get(config, "client_key")
    client_secret = _cfg_get(config, "client_secret")
    stored = load_token(data_dir)
    refresh = stored.get("refresh_token") or config.get("refresh_token") or ""
    if not client_key or not client_secret or not refresh:
        raise TikTokError("Thiếu client_key / client_secret / refresh_token TikTok.")
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("error"):
        raise TikTokError(
            data.get("error_description")
            or data.get("error")
            or f"Làm mới token TikTok thất bại ({resp.status_code})"
        )
    save_token(data_dir, data)
    return data


def ensure_access_token(config: dict, data_dir: Path) -> str:
    stored = load_token(data_dir)
    token = stored.get("access_token") or config.get("access_token") or ""
    if token:
        return str(token)
    refreshed = refresh_access_token(config, data_dir)
    return str(refreshed.get("access_token") or "")


def auth_status(config: dict, data_dir: Path) -> dict:
    client_key = _cfg_get(config, "client_key")
    client_secret = _cfg_get(config, "client_secret")
    stored = load_token(data_dir)
    has_token = bool(stored.get("access_token") or stored.get("refresh_token") or config.get("access_token"))
    info = {
        "has_client": bool(client_key and client_secret),
        "has_token": has_token,
        "has_auth": False,
        "account_id": str(config.get("account_id") or stored.get("open_id") or ""),
        "account_name": str(config.get("account_name") or ""),
        "account_url": str(config.get("account_url") or "https://www.tiktok.com"),
        "open_id": str(stored.get("open_id") or config.get("open_id") or ""),
        "error": "",
    }
    if not info["has_client"]:
        info["error"] = "Chưa nhập client_key / client_secret TikTok Developer."
        return info
    if not has_token:
        info["error"] = "Chưa ủy quyền TikTok."
        return info
    try:
        token = ensure_access_token(config, data_dir)
        resp = requests.get(
            USER_INFO_URL,
            params={"fields": "open_id,display_name,avatar_url"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        payload = resp.json() if resp.content else {}
        user = ((payload.get("data") or {}).get("user") or {})
        if user.get("display_name"):
            info["account_name"] = user["display_name"]
        if user.get("open_id"):
            info["account_id"] = user["open_id"]
            info["open_id"] = user["open_id"]
        info["has_auth"] = True
    except Exception as exc:  # noqa: BLE001
        # Token có thể hết hạn — vẫn coi là đã cấu hình nếu có refresh
        if stored.get("refresh_token"):
            try:
                refresh_access_token(config, data_dir)
                info["has_auth"] = True
                info["error"] = ""
            except Exception as refresh_exc:  # noqa: BLE001
                info["error"] = str(refresh_exc)[:300]
        else:
            info["error"] = str(exc)[:300]
    return info


def build_auth_url(config: dict, *, state: str) -> str:
    client_key = _cfg_get(config, "client_key")
    redirect_uri = _cfg_get(config, "redirect_uri", default="http://127.0.0.1:8768/callback")
    if not client_key:
        raise TikTokError("Thiếu client_key.")
    query = urllib.parse.urlencode({
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    })
    return f"{AUTH_URL}?{query}"


def exchange_code(config: dict, data_dir: Path, code: str) -> dict:
    client_key = _cfg_get(config, "client_key")
    client_secret = _cfg_get(config, "client_secret")
    redirect_uri = _cfg_get(config, "redirect_uri", default="http://127.0.0.1:8768/callback")
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("error"):
        raise TikTokError(
            data.get("error_description")
            or data.get("error")
            or f"Đổi code TikTok thất bại ({resp.status_code})"
        )
    save_token(data_dir, data)
    status = auth_status(config, data_dir)
    return {
        "ok": True,
        "message": "Đã lưu tiktok_token.json",
        "open_id": data.get("open_id") or "",
        "account_id": status.get("account_id") or data.get("open_id") or "",
        "account_name": status.get("account_name") or "",
        "account_url": "https://www.tiktok.com",
        "access_token": data.get("access_token") or "",
        "refresh_token": data.get("refresh_token") or "",
    }


def start_oauth(config: dict, data_dir: Path, *, port: int = 8768) -> dict:
    """Chạy HTTP server nhận callback OAuth TikTok (network_mode: host)."""
    state = secrets.token_urlsafe(16)
    code_box: dict[str, str] = {}
    event = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path not in ("/callback", "/"):
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid state")
                return
            code = qs.get("code", [""])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code")
                return
            code_box["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h3>TikTok OK</h3><p>Co the dong tab nay.</p></body></html>")
            event.set()

    redirect_uri = _cfg_get(config, "redirect_uri", default=f"http://127.0.0.1:{port}/callback")
    config = {**config, "redirect_uri": redirect_uri}
    url = build_auth_url(config, state=state)
    server = HTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(f"[tiktok-oauth] Mo URL: {url}", flush=True)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
        if not event.wait(timeout=300):
            raise TikTokError("Hết thời gian chờ OAuth TikTok (5 phút).")
    finally:
        server.shutdown()
    return exchange_code(config, data_dir, code_box["code"])


def upload_video(
    video_path: str | Path,
    *,
    title: str,
    caption: str,
    config: dict,
    data_dir: Path,
    on_step=None,
) -> dict[str, Any]:
    def _step(step_id: str, message: str = "", **kwargs):
        if callable(on_step):
            on_step(step_id, message, **kwargs)

    path = Path(video_path)
    if not path.is_file():
        raise TikTokError(f"Không thấy file: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise TikTokError("File video rỗng.")

    token = ensure_access_token(config, data_dir)
    _step("init", "Khởi tạo Direct Post")
    # Một chunk nếu < 64MB; TikTok yêu cầu chunk_size * total_chunk_count ≈ video_size
    chunk_size = size
    total_chunk_count = 1
    privacy = _cfg_get(config, "privacy_level", default="PUBLIC_TO_EVERYONE")
    if privacy not in (
        "PUBLIC_TO_EVERYONE",
        "MUTUAL_FOLLOW_FRIENDS",
        "FOLLOWER_OF_CREATOR",
        "SELF_ONLY",
    ):
        privacy = "PUBLIC_TO_EVERYONE"

    body = {
        "post_info": {
            "title": (title or caption or "Short")[:150],
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        },
    }
    init = requests.post(
        INIT_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=body,
        timeout=60,
    )
    init_payload = init.json() if init.content else {}
    err = (init_payload.get("error") or {})
    if init.status_code >= 400 or err.get("code", "ok") not in ("ok", "", None):
        raise TikTokError(err.get("message") or json.dumps(init_payload)[:400])
    data = init_payload.get("data") or {}
    upload_url = data.get("upload_url") or ""
    publish_id = data.get("publish_id") or ""
    if not upload_url:
        raise TikTokError("TikTok không trả upload_url (app cần quyền Direct Post / video.publish).")
    _step("init", "Đã có upload_url", done=True, detail=publish_id)

    _step("upload", "Gửi file lên TikTok")
    with path.open("rb") as handle:
        raw = handle.read()
    put = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        },
        data=raw,
        timeout=3600,
    )
    if put.status_code >= 400:
        raise TikTokError(f"Upload binary TikTok lỗi HTTP {put.status_code}: {put.text[:300]}")
    _step("upload", "Đã gửi file", done=True, detail=f"{size} bytes")

    # Poll nhẹ trạng thái
    _step("status", "Kiểm tra trạng thái publish")
    status_msg = "Đã gửi video lên TikTok"
    try:
        st = requests.post(
            STATUS_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
            timeout=30,
        )
        st_payload = st.json() if st.content else {}
        status = ((st_payload.get("data") or {}).get("status") or "")
        if status:
            status_msg = f"TikTok status: {status}"
    except Exception:
        pass
    _step("status", status_msg, done=True, detail=status_msg)
    _step("done", "Hoàn tất", done=True, detail=publish_id)

    return {
        "ok": True,
        "platform": name,
        "post_id": publish_id,
        "tiktok_publish_id": publish_id,
        "permalink": "",
        "message": status_msg,
        "title": title,
    }


def publish(video_path: str, *, title: str = "", caption: str = "", **kwargs: Any) -> dict:
    config = kwargs.get("config") or {}
    data_dir = Path(kwargs.get("data_dir") or "")
    try:
        return upload_video(video_path, title=title, caption=caption, config=config, data_dir=data_dir)
    except TikTokError as exc:
        return {"ok": False, "platform": name, "message": str(exc)}
