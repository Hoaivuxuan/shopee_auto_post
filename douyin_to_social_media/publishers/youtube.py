"""Upload Douyin short → YouTube Shorts (Data API v3).

Cần file OAuth client (Desktop) từ Google Cloud Console + bật YouTube Data API v3.
Token lưu tại data/douyin/youtube_token.json sau lần ủy quyền đầu.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

name = "youtube"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
_TITLE_TAG = re.compile(r"#\S+", re.UNICODE)


class YouTubeError(RuntimeError):
    pass


def _import_google():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise YouTubeError(
            "Thiếu thư viện Google. Cài: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload


def clean_title(title: str, limit: int = 100) -> str:
    """Làm sạch tiêu đề và luôn kết thúc bằng #Shorts (giới hạn 100 ký tự YouTube)."""
    tag = "#Shorts"
    # Bỏ hashtag cũ (kể cả #shorts/#Shorts) rồi gắn lại ở cuối
    text = " ".join(_TITLE_TAG.sub(" ", title or "").split()).strip()
    if not text:
        text = "Short"
    room = limit - len(tag) - 1  # khoảng trắng trước #Shorts
    if room < 8:
        return tag[:limit]
    if len(text) > room:
        text = text[: max(room - 1, 1)].rstrip(" .,:;") + "…"
    return f"{text} {tag}"


def shorts_description(caption: str) -> str:
    body = (caption or "").strip()
    if "#shorts" not in body.lower():
        body = (body + "\n\n#Shorts").strip() if body else "#Shorts"
    return body[:5000]


def resolve_secrets_path(base: Path, configured: str) -> Path:
    raw = (configured or "client_secrets.json").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    return path


def load_credentials(token_path: Path, secrets_path: Path):
    Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload = _import_google()
    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    if creds and creds.valid:
        return creds
    raise YouTubeError(
        "Chưa ủy quyền YouTube. Đặt client_secrets.json rồi chạy OAuth "
        "(Cấu hình → Ủy quyền YouTube) để tạo youtube_token.json."
    )


def save_credentials(token_path: Path, creds) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")


def start_oauth(secrets_path: Path, token_path: Path, *, port: int = 8767) -> dict:
    """Chạy OAuth local server (host network). Trả về thông tin kênh sau khi xong."""
    Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload = _import_google()
    if not secrets_path.is_file():
        raise YouTubeError(
            f"Không thấy client secrets: {secrets_path}. "
            "Tải JSON OAuth Desktop từ Google Cloud Console, đổi tên thành client_secrets.json."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    # select_account buộc hiện chọn Google account + Brand Account (kênh YouTube).
    # Token gắn với đúng kênh đã chọn lúc OAuth — không đổi được bằng channel_id lúc upload.
    creds = flow.run_local_server(
        port=port,
        open_browser=True,
        prompt="consent select_account",
    )
    save_credentials(token_path, creds)
    channel = channel_info(token_path, secrets_path)
    title = channel.get("channel_title") or "(không rõ)"
    return {
        "ok": True,
        "message": f"Đã ủy quyền kênh: {title}. Mọi video sẽ đăng lên kênh này.",
        **channel,
    }


def channel_info(token_path: Path, secrets_path: Path) -> dict:
    Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload = _import_google()
    creds = load_credentials(token_path, secrets_path)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        return {"channel_id": "", "channel_title": "", "has_auth": True}
    item = items[0]
    snippet = item.get("snippet") or {}
    return {
        "channel_id": item.get("id") or "",
        "channel_title": snippet.get("title") or "",
        "has_auth": True,
    }


def auth_status(token_path: Path, secrets_path: Path) -> dict:
    has_secrets = secrets_path.is_file()
    has_token = token_path.is_file()
    info = {
        "has_secrets": has_secrets,
        "has_token": has_token,
        "has_auth": False,
        "channel_id": "",
        "channel_title": "",
        "secrets_path": str(secrets_path),
        "token_path": str(token_path),
    }
    if not has_token:
        return info
    try:
        info.update(channel_info(token_path, secrets_path))
        info["has_auth"] = True
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:300]
    return info


def upload_short(
    video_path: str | Path,
    *,
    title: str,
    description: str,
    token_path: Path,
    secrets_path: Path,
    privacy_status: str = "public",
    category_id: str = "22",
) -> dict[str, Any]:
    """Upload 1 file mp4; YouTube tự nhận Shorts nếu 9:16 + #Shorts."""
    Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload = _import_google()
    path = Path(video_path)
    if not path.is_file():
        raise YouTubeError(f"Không thấy file video: {path}")

    creds = load_credentials(token_path, secrets_path)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    snippet_title = clean_title(title)

    body = {
        "snippet": {
            "title": snippet_title,
            "description": shorts_description(description),
            "tags": ["Shorts"],
            "categoryId": str(category_id or "22"),
        },
        "status": {
            "privacyStatus": privacy_status if privacy_status in ("public", "unlisted", "private") else "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    last_error = None
    for attempt in range(6):
        try:
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pass
            break
        except HttpError as exc:
            last_error = exc
            code = getattr(exc.resp, "status", None)
            if code in (500, 502, 503, 504) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            raise YouTubeError(_http_message(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 5:
                time.sleep(2 ** attempt)
                continue
            raise YouTubeError(str(exc)[:400]) from exc
    if not response or "id" not in response:
        raise YouTubeError(f"Upload YouTube thất bại: {last_error}")

    video_id = response["id"]
    return {
        "ok": True,
        "platform": name,
        "youtube_video_id": video_id,
        "permalink": f"https://www.youtube.com/shorts/{video_id}",
        "title": snippet_title,
        "message": "Đã đăng YouTube Shorts",
    }


def _http_message(exc) -> str:
    try:
        payload = json.loads(exc.content.decode("utf-8"))
        err = (payload.get("error") or {}).get("message") or ""
        if err:
            return err[:400]
    except Exception:
        pass
    return str(exc)[:400]


def publish(video_path: str, *, title: str = "", caption: str = "", **kwargs: Any) -> dict:
    token_path = Path(kwargs.get("token_path") or "")
    secrets_path = Path(kwargs.get("secrets_path") or "")
    if not token_path or not secrets_path:
        return {
            "ok": False,
            "platform": name,
            "message": "Thiếu token_path / secrets_path",
        }
    try:
        return upload_short(
            video_path,
            title=title,
            description=caption or title,
            token_path=token_path,
            secrets_path=secrets_path,
            privacy_status=str(kwargs.get("privacy_status") or "public"),
            category_id=str(kwargs.get("category_id") or "22"),
        )
    except YouTubeError as exc:
        return {"ok": False, "platform": name, "message": str(exc)}
