"""Upload Douyin short → Instagram Reels (Instagram Graph API / Meta).

Ưu tiên tài khoản IG Professional gắn với Facebook Page.
Token: Page Access Token (cùng hệ Meta với Facebook).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

name = "instagram"
GRAPH = "https://graph.facebook.com"


class InstagramError(RuntimeError):
    pass


def _cfg_get(config: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = str(config.get(key) or "").strip()
        if value:
            return value
    return default


def _api_version(config: dict) -> str:
    return _cfg_get(config, "api_version", default="v21.0")


def _check(resp: requests.Response) -> dict:
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        payload = {}
    if resp.status_code >= 400 or payload.get("error"):
        err = payload.get("error") or {}
        message = err.get("message") or resp.text[:400] or f"HTTP {resp.status_code}"
        raise InstagramError(message)
    return payload if isinstance(payload, dict) else {}


def resolve_ig_user(config: dict) -> dict:
    """Lấy ig_user_id từ config hoặc từ Facebook Page đã liên kết."""
    token = _cfg_get(config, "access_token", "token")
    version = _api_version(config)
    ig_user_id = _cfg_get(config, "ig_user_id", "account_id")
    page_id = _cfg_get(config, "page_id")
    if ig_user_id and token:
        # Xác nhận tên
        try:
            info = _check(requests.get(
                f"{GRAPH}/{version}/{ig_user_id}",
                params={"fields": "id,username,name", "access_token": token},
                timeout=30,
            ))
            return {
                "ig_user_id": info.get("id") or ig_user_id,
                "username": info.get("username") or "",
                "name": info.get("name") or info.get("username") or "Instagram",
            }
        except InstagramError:
            pass
    if not token:
        raise InstagramError("Chưa có access_token Instagram / Page Access Token.")
    if not page_id:
        raise InstagramError("Cần page_id Facebook đã liên kết Instagram Professional.")
    page = _check(requests.get(
        f"{GRAPH}/{version}/{page_id}",
        params={"fields": "id,name,instagram_business_account", "access_token": token},
        timeout=30,
    ))
    ig = page.get("instagram_business_account") or {}
    ig_id = str(ig.get("id") or "")
    if not ig_id:
        raise InstagramError(
            "Page này chưa liên kết Instagram Professional. "
            "Vào Meta Business Suite gắn IG với Page rồi thử lại."
        )
    info = _check(requests.get(
        f"{GRAPH}/{version}/{ig_id}",
        params={"fields": "id,username,name", "access_token": token},
        timeout=30,
    ))
    return {
        "ig_user_id": ig_id,
        "username": info.get("username") or "",
        "name": info.get("name") or info.get("username") or page.get("name") or "Instagram",
        "page_id": page.get("id") or page_id,
        "page_name": page.get("name") or "",
    }


def auth_status(config: dict) -> dict:
    token = _cfg_get(config, "access_token", "token")
    info = {
        "has_token": bool(token),
        "has_auth": False,
        "account_id": _cfg_get(config, "ig_user_id", "account_id"),
        "account_name": _cfg_get(config, "account_name"),
        "account_url": _cfg_get(config, "account_url", default="https://www.instagram.com"),
        "page_id": _cfg_get(config, "page_id"),
        "error": "",
    }
    if not token:
        info["error"] = "Chưa lưu Page Access Token / Instagram token."
        return info
    try:
        ig = resolve_ig_user(config)
        info.update({
            "has_auth": True,
            "account_id": ig["ig_user_id"],
            "account_name": ig.get("username") or ig.get("name") or "Instagram",
            "account_url": (
                f"https://www.instagram.com/{ig['username']}/"
                if ig.get("username")
                else "https://www.instagram.com"
            ),
            "page_id": ig.get("page_id") or info["page_id"],
        })
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:300]
    return info


def _create_resumable_session(ig_user_id: str, token: str, version: str, file_size: int, caption: str) -> dict:
    resp = requests.post(
        f"{GRAPH}/{version}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "access_token": token,
        },
        timeout=60,
    )
    payload = _check(resp)
    # Một số phiên bản trả uri trong header / field khác nhau
    uri = payload.get("uri") or payload.get("upload_uri") or ""
    session_id = str(payload.get("id") or "")
    if not session_id:
        raise InstagramError(f"Không tạo được container Reels: {json.dumps(payload)[:300]}")
    return {"creation_id": session_id, "uri": uri, "raw": payload}


def _rupload(uri: str, token: str, path: Path, file_size: int) -> None:
    """Đẩy binary lên rupload.facebook.com."""
    if not uri:
        # Fallback: một số app dùng endpoint rupload với session id
        raise InstagramError(
            "API không trả URI upload resumable. "
            "Thử cấu hình public_base_url để Instagram kéo video qua video_url."
        )
    headers = {
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
    }
    with path.open("rb") as handle:
        resp = requests.post(uri, headers=headers, data=handle, timeout=3600)
    if resp.status_code >= 400:
        raise InstagramError(f"Rupload Instagram lỗi HTTP {resp.status_code}: {resp.text[:300]}")


def _create_from_url(ig_user_id: str, token: str, version: str, video_url: str, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH}/{version}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": "true",
            "access_token": token,
        },
        timeout=60,
    )
    payload = _check(resp)
    creation_id = str(payload.get("id") or "")
    if not creation_id:
        raise InstagramError(f"Không tạo container từ video_url: {json.dumps(payload)[:300]}")
    return creation_id


def _wait_finished(creation_id: str, token: str, version: str, *, timeout_sec: int = 300) -> None:
    deadline = time.time() + timeout_sec
    last = ""
    while time.time() < deadline:
        resp = requests.get(
            f"{GRAPH}/{version}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        payload = _check(resp)
        code = str(payload.get("status_code") or "")
        last = code or str(payload.get("status") or "")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Container Instagram {code}: {payload.get('status') or payload}")
        time.sleep(8)
    raise InstagramError(f"Hết thời gian chờ Instagram xử lý video (last={last}).")


def _publish(ig_user_id: str, token: str, version: str, creation_id: str) -> dict:
    resp = requests.post(
        f"{GRAPH}/{version}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60,
    )
    return _check(resp)


def _permalink(media_id: str, token: str, version: str) -> str:
    try:
        resp = requests.get(
            f"{GRAPH}/{version}/{media_id}",
            params={"fields": "permalink", "access_token": token},
            timeout=30,
        )
        return str(_check(resp).get("permalink") or "")
    except Exception:
        return ""


def upload_reel(
    video_path: str | Path,
    *,
    title: str,
    caption: str,
    config: dict,
    on_step=None,
) -> dict[str, Any]:
    def _step(step_id: str, message: str = "", **kwargs):
        if callable(on_step):
            on_step(step_id, message, **kwargs)

    path = Path(video_path)
    if not path.is_file():
        raise InstagramError(f"Không thấy file: {path}")
    token = _cfg_get(config, "access_token", "token")
    version = _api_version(config)
    ig = resolve_ig_user(config)
    ig_user_id = ig["ig_user_id"]
    text = (caption or title or "").strip()
    file_size = path.stat().st_size

    public_base = _cfg_get(config, "public_base_url").rstrip("/")
    creation_id = ""
    _step("container", "Tạo container Reels")
    if public_base:
        # video_id nằm trong path .../processed/{id}/output_ai.mp4
        video_id = path.parent.name
        video_url = f"{public_base}/api/douyin/ai-media/{video_id}"
        creation_id = _create_from_url(ig_user_id, token, version, video_url, text)
        _step("container", "Container từ video_url", done=True, detail=creation_id)
        _step("transfer", "Instagram kéo video từ URL", done=True, detail=video_url)
    else:
        session = _create_resumable_session(ig_user_id, token, version, file_size, text)
        creation_id = session["creation_id"]
        uri = session.get("uri") or ""
        if not uri:
            raw = session.get("raw") or {}
            uri = str(raw.get("uri") or raw.get("upload_uri") or "")
        _step("container", "Container resumable", done=True, detail=creation_id)
        _step("transfer", "Upload binary lên rupload")
        _rupload(uri, token, path, file_size)
        _step("transfer", "Đã upload", done=True, detail=f"{file_size} bytes")

    _step("process", "Chờ Instagram xử lý video")
    _wait_finished(creation_id, token, version)
    _step("process", "FINISHED", done=True, detail=creation_id)

    _step("publish", "Publish Reels")
    published = _publish(ig_user_id, token, version, creation_id)
    media_id = str(published.get("id") or "")
    _step("publish", "Published", done=True, detail=media_id)

    _step("done", "Lấy permalink")
    link = _permalink(media_id, token, version) if media_id else ""
    _step("done", link or "OK", done=True, detail=link or media_id)
    return {
        "ok": True,
        "platform": name,
        "post_id": media_id,
        "instagram_media_id": media_id,
        "permalink": link,
        "message": "Đã đăng Instagram Reels",
        "account_name": ig.get("username") or ig.get("name") or "",
    }


def publish(video_path: str, *, title: str = "", caption: str = "", **kwargs: Any) -> dict:
    config = kwargs.get("config") or {}
    try:
        return upload_reel(video_path, title=title, caption=caption, config=config)
    except InstagramError as exc:
        return {"ok": False, "platform": name, "message": str(exc)}
