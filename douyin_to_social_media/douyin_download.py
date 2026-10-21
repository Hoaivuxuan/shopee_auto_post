#!/usr/bin/env python3
"""Tải video Douyin về data/douyin — nguồn chính của douyin_to_social_media."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "douyin"
VIDEO_DIR = DATA_DIR / "videos"
ARCHIVE_PATH = DATA_DIR / "archive.txt"
MANIFEST_PATH = DATA_DIR / "manifest.json"
SYNC_AUTO_PATH = DATA_DIR / "sync_auto.json"
COOKIE_CANDIDATES = (
    ROOT / "douyin_cookies.txt",
    ROOT / "www.douyin.com_cookies.txt",
)
VN_TZ = timezone(timedelta(hours=7))
_HOSTS = {"douyin.com", "v.douyin.com", "iesdouyin.com"}
_VIDEO_PATH = re.compile(r"/(?:share/)?(?:video|note|slides)/(\d{6,})", re.I)
_MODAL_ID = re.compile(r"(?:^|[?&#])modal_id=(\d{6,})")
_USER_PATH = re.compile(r"/user/([^/?#]+)", re.I)
_AWEME_ID = re.compile(r'["\']aweme_id["\']\s*:\s*["\'](\d{6,})["\']')
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_SEC_SALT = "A96D855A08C0A9707F8BEF0D9A527E4E"

_SYNC_LOCK = threading.Lock()
_SYNC_AUTO_LOCK = threading.Lock()
_SYNC = {
    "running": False,
    "message": "",
    "seen": 0,
    "skipped": 0,
    "downloaded": 0,
    "failed": 0,
}


def host_of(url: str) -> str:
    try:
        return urlparse(str(url or "").strip()).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def is_douyin_url(url: str) -> bool:
    return host_of(url) in _HOSTS


def video_id_of(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{6,}", text):
        return text
    match = _VIDEO_PATH.search(text) or _MODAL_ID.search(text)
    return match.group(1) if match else ""


def user_id_of(url: str) -> str:
    match = _USER_PATH.search(str(url or ""))
    return match.group(1) if match else ""


def is_video_url(url: str) -> bool:
    if not is_douyin_url(url):
        return False
    if video_id_of(url):
        return True
    return host_of(url) == "v.douyin.com" and not user_id_of(url)


def is_user_url(url: str) -> bool:
    return bool(is_douyin_url(url) and user_id_of(url) and not video_id_of(url))


def clean_user_url(url: str) -> str:
    return f"https://www.douyin.com/user/{user_id_of(url)}"


def account_label(url: str) -> str:
    uid = user_id_of(url)
    if len(uid) > 18:
        return f"{uid[:8]}…{uid[-4:]}"
    return uid or "Tài khoản"


def canonical_video_url(video_id: str) -> str:
    return f"https://www.douyin.com/video/{video_id}"


def link_keys(url: str, video_id: str = "") -> set[str]:
    found = video_id_of(video_id) or video_id_of(url)
    if not found:
        return set()
    keys = {canonical_video_url(found), found}
    text = str(url or "").strip()
    if text:
        keys.add(text.split("#")[0])
    return keys


def friendly_error(exc: BaseException) -> str:
    text = str(exc or "").strip()
    lowered = text.lower()
    if "fresh cookies" in lowered or "cookie" in lowered:
        return (
            "Douyin yêu cầu cookie mới. Hãy xuất cookie douyin.com "
            "(không cần đăng nhập) vào file douyin_cookies.txt rồi thử lại."
        )
    if "unsupported url" in lowered:
        return "Không nhận ra link Douyin này."
    return (text or "Không tải được video Douyin.")[:180]


def cookie_file() -> str:
    for path in COOKIE_CANDIDATES:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        if any(line.strip() and not line.lstrip().startswith("#") for line in lines):
            return str(path)
    return ""


def _cookie_jar():
    path = cookie_file()
    if not path:
        return None
    jar = MozillaCookieJar()
    try:
        jar.load(path, ignore_discard=True, ignore_expires=True)
    except OSError:
        return None
    return jar


def _load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"accounts": [], "videos": []}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"accounts": [], "videos": []}
    if not isinstance(data, dict):
        return {"accounts": [], "videos": []}
    return data


def _save_manifest(manifest: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def saved_accounts(manifest: dict | None = None) -> list[str]:
    manifest = _load_manifest() if manifest is None else manifest
    urls = []
    for item in manifest.get("accounts") or []:
        text = str(item or "").strip()
        if text and text not in urls:
            urls.append(text)
    return urls


def remember_account(url: str) -> list[str]:
    manifest = _load_manifest()
    accounts = saved_accounts(manifest)
    if url not in accounts:
        accounts.append(url)
    manifest["accounts"] = accounts
    _save_manifest(manifest)
    return accounts


def known_links(manifest: dict) -> set[str]:
    found = set()
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict):
            continue
        found |= link_keys(str(item.get("url") or ""), str(item.get("id") or ""))
    return found


def _entry_record(info: dict, filepath: str | None, source: str = "") -> dict:
    video_id = str(info.get("id") or "")
    raw = source or info.get("channel_url") or info.get("uploader_url") or ""
    account = clean_user_url(raw) if user_id_of(raw) else ""
    name = str(info.get("channel") or info.get("uploader") or info.get("creator") or "").strip()
    return {
        "id": video_id,
        "title": info.get("title") or info.get("description") or video_id,
        "url": info.get("webpage_url") or canonical_video_url(video_id),
        "upload_date": info.get("upload_date") or "",
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "description": info.get("description") or "",
        "channel": account,
        "channel_name": name or (account_label(account) if account else ""),
        "file": filepath,
        "source": "douyin",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _downloaded_path(info: dict) -> str | None:
    requested = info.get("requested_downloads") or []
    for item in requested:
        path = item.get("filepath")
        if path and Path(path).is_file():
            return path
    path = info.get("filepath") or info.get("_filename")
    if path and Path(path).is_file():
        return path
    video_id = str(info.get("id") or "")
    if not video_id:
        return None
    matches = sorted(VIDEO_DIR.glob(f"{video_id}.*"))
    media = [item for item in matches if item.suffix.lower() not in {".json", ".part", ".jpg", ".jpeg", ".webp", ".png"}]
    return str(media[0]) if media else None


def _flush(manifest: dict, by_id: dict) -> None:
    videos = sorted(by_id.values(), key=lambda item: item.get("upload_date") or "", reverse=True)
    manifest["videos"] = videos
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_manifest(manifest)


def _remember(manifest: dict, by_id: dict, info: dict, filepath: str | None, source: str = "") -> bool:
    video_id = str(info.get("id") or "")
    if not video_id:
        return False
    is_new = bool(filepath) and video_id not in by_id
    record = _entry_record(info, filepath, source)
    if video_id in by_id:
        previous = by_id[video_id]
        if filepath:
            record["downloaded_at"] = previous.get("downloaded_at") or record["downloaded_at"]
        if not record.get("description"):
            record["description"] = previous.get("description") or ""
        if not record.get("channel"):
            record["channel"] = previous.get("channel") or ""
            record["channel_name"] = previous.get("channel_name") or account_label(record["channel"])
        elif not record.get("channel_name"):
            record["channel_name"] = previous.get("channel_name") or account_label(record["channel"])
    by_id[video_id] = record
    _flush(manifest, by_id)
    return is_new


def _progress_hook(manifest: dict, by_id: dict, source: str = ""):
    def hook(status: dict) -> None:
        if status.get("status") != "finished":
            return
        info = status.get("info_dict") or {}
        filename = status.get("filename") or ""
        video_id = str(info.get("id") or "")
        name = Path(filename).name
        if not video_id or not name.startswith(f"{video_id}."):
            return
        if ".f" in name or name.endswith(".part"):
            return
        if not Path(filename).is_file():
            return
        _remember(manifest, by_id, info, filename, source)

    return hook


def _cookie_value(*names: str) -> str:
    jar = _cookie_jar()
    if not jar:
        return ""
    found = {cookie.name: cookie.value for cookie in jar if cookie.value}
    for name in names:
        if found.get(name):
            return found[name]
    return ""


def _signed_get(path: str, query: dict, referer: str) -> dict:
    uifid = _cookie_value("UIFID", "UIFID_TEMP")
    if not uifid:
        raise RuntimeError("Fresh cookies (not necessarily logged in) are needed")
    payload = dict(query)
    fp = _cookie_value("s_v_web_id")
    if fp:
        payload.setdefault("verifyFp", fp)
        payload.setdefault("fp", fp)
    payload["uifid"] = uifid
    payload["timestamp"] = str(int(time.time()))
    encoded = urlencode(payload)
    signature = hashlib.md5(f"{uifid}_{payload['timestamp']}_{_SEC_SALT}_{encoded}".encode()).hexdigest()
    url = "https://www.douyin.com" + path + "?" + encoded + "&x-secsdk-web-signature=" + signature
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _UA, "Referer": referer},
            cookies=_cookie_jar(),
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Không kết nối được Douyin.") from exc
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError("Douyin không trả danh sách video.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Douyin không trả danh sách video.")
    return data


def _entries_from_posts(data: dict) -> list[dict]:
    found = []
    for item in data.get("aweme_list") or []:
        if not isinstance(item, dict):
            continue
        video_id = video_id_of(str(item.get("aweme_id") or ""))
        if not video_id:
            continue
        found.append({
            "id": video_id,
            "url": canonical_video_url(video_id),
            "title": str(item.get("desc") or ""),
        })
    return found


def _list_user_posts(sec_user_id: str) -> list[dict]:
    referer = f"https://www.douyin.com/user/{sec_user_id}"
    cursor = "0"
    found = []
    seen = set()
    for _ in range(50):
        data = _signed_get("/aweme/v1/web/aweme/post/", {
            "sec_user_id": sec_user_id,
            "count": "18",
            "max_cursor": cursor,
            "locate_query": "false",
            "publish_video_strategy_type": "2",
            "aid": "6383",
            "device_platform": "webapp",
            "channel": "channel_pc_web",
        }, referer)
        if data.get("status_code") not in (0, None):
            break
        added = 0
        for entry in _entries_from_posts(data):
            if entry["id"] in seen:
                continue
            seen.add(entry["id"])
            found.append(entry)
            added += 1
        if not added or not data.get("has_more"):
            break
        nxt = str(data.get("max_cursor") or "")
        if not nxt or nxt == cursor:
            break
        cursor = nxt
    return found


def _install_douyin_sign() -> None:
    """Douyin từ chối API chi tiết nếu thiếu uifid và x-secsdk-web-signature."""
    import hashlib
    import time
    from urllib.parse import urlencode

    from yt_dlp.extractor.tiktok import DouyinIE
    from yt_dlp.utils import ExtractorError, traverse_obj

    if getattr(DouyinIE, "_secsdk_patched", False):
        return

    salt = _SEC_SALT
    names = ("UIFID", "uifid", "UIFID_TEMP", "uifid_temp")

    def _real_extract(self, url):
        video_id = self._match_id(url)
        cookies = self._get_cookies(self._WEBPAGE_HOST)
        uifid = ""
        for name in names:
            cookie = cookies.get(name)
            value = getattr(cookie, "value", "") if cookie else ""
            if value:
                uifid = value
                break
        if not uifid:
            raise ExtractorError(
                "Fresh cookies (not necessarily logged in) are needed",
                expected=True,
            )
        timestamp = str(int(time.time()))
        query = {"aweme_id": video_id, "uifid": uifid, "timestamp": timestamp}
        encoded = urlencode(query)
        signature = hashlib.md5(
            f"{uifid}_{timestamp}_{salt}_{encoded}".encode()
        ).hexdigest()
        detail_url = (
            "https://www.douyin.com/aweme/v1/web/aweme/detail/?"
            + encoded
            + "&x-secsdk-web-signature="
            + signature
        )
        detail = traverse_obj(
            self._download_json(
                detail_url,
                video_id,
                "Downloading web detail JSON",
                "Failed to download web detail JSON",
                fatal=False,
            ),
            ("aweme_detail", {dict}),
        )
        if not detail:
            raise ExtractorError(
                "Fresh cookies (not necessarily logged in) are needed",
                expected=not cookies.get("s_v_web_id"),
            )
        return self._parse_aweme_video_app(detail)

    DouyinIE._real_extract = _real_extract
    DouyinIE._secsdk_patched = True


def _ydl_opts(manifest: dict, by_id: dict, source: str = "") -> dict:
    import yt_dlp

    _install_douyin_sign()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(VIDEO_DIR / "%(id)s.%(ext)s"),
        "download_archive": str(ARCHIVE_PATH),
        "nooverwrites": True,
        "ignoreerrors": False,
        "retries": 5,
        "fragment_retries": 5,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "http_headers": {"Referer": "https://www.douyin.com/", "User-Agent": _UA},
        "progress_hooks": [_progress_hook(manifest, by_id, source)],
    }
    cookie = cookie_file()
    if cookie:
        opts["cookiefile"] = cookie
    opts["_ydl_cls"] = yt_dlp.YoutubeDL
    return opts


def _has_file(video_id: str) -> bool:
    return (VIDEO_DIR / f"{video_id}.mp4").is_file()


def _drop_archive(video_id: str) -> None:
    if not video_id or not ARCHIVE_PATH.is_file():
        return
    lines = ARCHIVE_PATH.read_text(encoding="utf-8").splitlines()
    kept = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == video_id and "douyin" in parts[0].lower():
            continue
        kept.append(line)
    if len(kept) == len(lines):
        return
    text = "\n".join(kept)
    ARCHIVE_PATH.write_text(f"{text}\n" if text else "", encoding="utf-8")


def _flat_entries(url: str) -> list[dict]:
    import yt_dlp

    _install_douyin_sign()
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
        "http_headers": {"Referer": "https://www.douyin.com/", "User-Agent": _UA},
    }
    cookie = cookie_file()
    if cookie:
        opts["cookiefile"] = cookie
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return []
    if info.get("entries") is None:
        if info.get("id"):
            return [info]
        return []
    return [entry for entry in info.get("entries") or [] if entry]


def _scrape_user_ids(url: str) -> list[dict]:
    headers = {"User-Agent": _UA, "Referer": "https://www.douyin.com/"}
    try:
        resp = requests.get(url, headers=headers, cookies=_cookie_jar(), timeout=30)
    except requests.RequestException:
        return []
    text = resp.text or ""
    found = []
    seen = set()
    for match in list(_AWEME_ID.finditer(text)) + list(_VIDEO_PATH.finditer(text)):
        video_id = match.group(1)
        if video_id in seen:
            continue
        seen.add(video_id)
        found.append({"id": video_id, "url": canonical_video_url(video_id)})
    return found


def list_account(url: str) -> list[dict]:
    uid = user_id_of(url)
    if uid:
        posts = _list_user_posts(uid)
        if posts:
            return posts
    scraped_error = ""
    try:
        entries = _flat_entries(url)
    except Exception as exc:
        entries = []
        scraped_error = friendly_error(exc)
    if entries:
        return entries
    scraped = _scrape_user_ids(url)
    if scraped:
        return scraped
    if scraped_error and "cookie" in scraped_error.lower():
        raise RuntimeError(scraped_error)
    raise RuntimeError(
        "Không lấy được danh sách video của tài khoản. "
        "Hãy xuất cookie douyin.com vào douyin_cookies.txt, hoặc dán từng link video."
    )


def _download_one(url: str, manifest: dict, by_id: dict, source: str = "") -> bool:
    video_id = video_id_of(url)
    if video_id and not _has_file(video_id):
        _drop_archive(video_id)
    opts = _ydl_opts(manifest, by_id, source)
    ydl_cls = opts.pop("_ydl_cls")
    with ydl_cls(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if not info or not info.get("id"):
        return False
    path = _downloaded_path(info)
    if not path:
        return False
    _remember(manifest, by_id, info, path, source)
    return True


def _fresh_entries(entries: list[dict], known: set[str]) -> tuple[list[tuple[str, str]], int]:
    fresh = []
    skipped = 0
    for entry in entries:
        video_id = video_id_of(entry.get("id") or "") or video_id_of(entry.get("url") or "")
        video_url = str(entry.get("url") or entry.get("webpage_url") or "")
        if not video_id:
            continue
        keys = link_keys(video_url, video_id)
        if keys & known or _has_file(video_id):
            skipped += 1
            known |= keys
            continue
        fresh.append((video_id, video_url or canonical_video_url(video_id)))
        known |= keys
    return fresh, skipped


def _sync_set(**kwargs) -> None:
    with _SYNC_LOCK:
        _SYNC.update(kwargs)


def account_catalog(manifest: dict | None = None) -> list[dict]:
    manifest = _load_manifest() if manifest is None else manifest
    names: dict[str, str] = {}
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("channel") or "")
        if key and key not in names:
            names[key] = str(item.get("channel_name") or "") or account_label(key)
    for url in saved_accounts(manifest):
        key = clean_user_url(url) if user_id_of(url) else url
        if key:
            names.setdefault(key, account_label(key))
    return [{"url": url, "name": name} for url, name in names.items()]


def ensure_account_tags() -> int:
    manifest = _load_manifest()
    changed = 0
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict) or not item.get("channel") or item.get("channel_name"):
            continue
        item["channel_name"] = account_label(str(item.get("channel") or ""))
        changed += 1
    if changed:
        _save_manifest(manifest)
    return changed


def sync_status() -> dict:
    with _SYNC_LOCK:
        data = dict(_SYNC)
    data["channels"] = account_catalog()
    data["has_cookies"] = bool(cookie_file())
    return data


def _now_str() -> str:
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _interval_minutes(value, default: int = 60) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(1440, max(1, number))


def _read_sync_auto() -> dict:
    raw = {}
    if SYNC_AUTO_PATH.is_file():
        try:
            loaded = json.loads(SYNC_AUTO_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, json.JSONDecodeError):
            raw = {}
    return {
        "enabled": bool(raw.get("enabled")),
        "interval_minutes": _interval_minutes(raw.get("interval_minutes")),
        "last_at": str(raw.get("last_at") or ""),
    }


def _write_sync_auto(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stored = {
        "enabled": bool(cfg.get("enabled")),
        "interval_minutes": _interval_minutes(cfg.get("interval_minutes")),
        "last_at": str(cfg.get("last_at") or ""),
    }
    tmp = SYNC_AUTO_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(SYNC_AUTO_PATH)


def _next_sync_at(cfg: dict) -> str:
    if not cfg.get("enabled") or not cfg.get("last_at"):
        return ""
    try:
        stamp = datetime.strptime(str(cfg.get("last_at") or ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
    except ValueError:
        return _now_str()
    return (stamp + timedelta(minutes=_interval_minutes(cfg.get("interval_minutes")))).strftime("%Y-%m-%d %H:%M:%S")


def _sync_auto_public(cfg: dict) -> dict:
    next_at = _next_sync_at(cfg)
    if cfg.get("enabled") and next_at:
        message = f"Lần kế: {next_at}"
    elif cfg.get("enabled"):
        message = "Đồng bộ tự động đang bật"
    else:
        message = ""
    return {
        "enabled": bool(cfg.get("enabled")),
        "interval_minutes": _interval_minutes(cfg.get("interval_minutes")),
        "last_at": str(cfg.get("last_at") or ""),
        "next_at": next_at,
        "message": message,
    }


def sync_auto_status() -> dict:
    with _SYNC_AUTO_LOCK:
        return _sync_auto_public(_read_sync_auto())


def set_sync_auto(payload: dict) -> dict:
    with _SYNC_AUTO_LOCK:
        cfg = _read_sync_auto()
        if "interval_minutes" in payload:
            cfg["interval_minutes"] = _interval_minutes(payload.get("interval_minutes"), cfg["interval_minutes"])
        if "enabled" in payload:
            enabled = bool(payload.get("enabled"))
            if enabled and not cfg["enabled"]:
                cfg["last_at"] = _now_str()
            cfg["enabled"] = enabled
        _write_sync_auto(cfg)
        return _sync_auto_public(cfg)


def _mark_saved_sync() -> None:
    with _SYNC_AUTO_LOCK:
        cfg = _read_sync_auto()
        cfg["last_at"] = _now_str()
        _write_sync_auto(cfg)


def _sync_auto_due(cfg: dict) -> bool:
    if not cfg.get("enabled") or not cfg.get("last_at"):
        return False
    next_at = _next_sync_at(cfg)
    return bool(next_at) and _now_str() >= next_at


def _run_sync(urls: list[str] | None = None) -> None:
    skipped = 0
    downloaded = 0
    failed = 0
    seen = 0
    try:
        manifest = _load_manifest()
        targets = urls or saved_accounts(manifest)
        if not targets:
            _sync_set(message="Chưa có tài khoản Douyin nào. Hãy dán link trang cá nhân.")
            return
        known = known_links(manifest)
        by_id = {item["id"]: item for item in manifest.get("videos") or [] if item.get("id")}
        for url in targets:
            _sync_set(message=f"Đang đọc danh sách video: {account_label(url)}")
            try:
                entries = list_account(url)
            except Exception as exc:
                failed += 1
                _sync_set(message=friendly_error(exc), failed=failed)
                continue
            seen += len(entries)
            fresh, skipped_here = _fresh_entries(entries, known)
            skipped += skipped_here
            _sync_set(
                seen=seen,
                skipped=skipped,
                downloaded=downloaded,
                failed=failed,
                message=f"Có {len(fresh)} video mới. Đã bỏ qua {skipped} link trùng.",
            )
            for video_id, video_url in fresh:
                _sync_set(message=f"Đang tải video mới {downloaded + failed + 1}/{len(fresh)}")
                try:
                    ok = _download_one(video_url, manifest, by_id, url)
                except Exception as exc:
                    ok = False
                    _sync_set(message=friendly_error(exc))
                if ok:
                    downloaded += 1
                    known |= link_keys(video_url, video_id)
                else:
                    failed += 1
                _sync_set(downloaded=downloaded, failed=failed, skipped=skipped)
        if downloaded == 0 and failed == 0:
            message = f"Không có video mới. Đã bỏ qua {skipped} link đã có."
        else:
            message = f"Xong. Mới tải {downloaded}, bỏ qua {skipped} link trùng, lỗi {failed}."
        _sync_set(message=message, seen=seen, skipped=skipped, downloaded=downloaded, failed=failed)
        if downloaded:
            _kick_translate()
    except Exception as exc:
        _sync_set(message=friendly_error(exc))
    finally:
        _sync_set(running=False)


def _kick_translate() -> None:
    try:
        import douyin_translate

        douyin_translate.kick_batch()
    except Exception:
        pass


def _run_one(url: str) -> None:
    try:
        manifest = _load_manifest()
        by_id = {item["id"]: item for item in manifest.get("videos") or [] if item.get("id")}
        _sync_set(message="Đang tải video Douyin")
        ok = _download_one(url, manifest, by_id)
        if ok:
            _sync_set(message="Đã tải video Douyin về.", downloaded=1, seen=1, failed=0)
            _kick_translate()
        else:
            _sync_set(message="Không tải được video này.", failed=1, downloaded=0)
    except Exception as exc:
        _sync_set(message=friendly_error(exc), failed=1)
    finally:
        _sync_set(running=False)


def start_sync(url: str = "") -> dict:
    target = str(url or "").strip()
    clean = ""
    if target:
        if not is_douyin_url(target):
            raise RuntimeError("Chỉ nhận link Douyin.")
        if is_video_url(target):
            raise RuntimeError("Đây là link một video. Hãy dán vào ô tải video.")
        if not is_user_url(target):
            raise RuntimeError("Không nhận ra trang cá nhân. Hãy dán link dạng douyin.com/user/...")
        clean = clean_user_url(target)
    with _SYNC_LOCK:
        if _SYNC["running"]:
            raise RuntimeError("Đang đồng bộ Douyin. Hãy đợi lần này xong.")
        if clean:
            remember_account(clean)
            urls = [clean]
        else:
            urls = None
            if not saved_accounts():
                _SYNC["message"] = "Chưa có tài khoản Douyin nào. Hãy dán link trang cá nhân."
                return dict(_SYNC)
        _SYNC.update(running=True, message="Đang bắt đầu đồng bộ Douyin", seen=0, skipped=0, downloaded=0, failed=0)
    if not clean:
        _mark_saved_sync()
    threading.Thread(target=_run_sync, args=(urls,), name="dy-sync", daemon=True).start()
    return sync_status()


def start_download(url: str) -> dict:
    target = str(url or "").strip()
    if not target:
        raise RuntimeError("Hãy dán link video Douyin.")
    if not is_douyin_url(target):
        raise RuntimeError("Chỉ nhận link Douyin.")
    if is_user_url(target):
        raise RuntimeError("Đây là link trang cá nhân. Hãy dán vào ô đồng bộ tài khoản.")
    if not is_video_url(target):
        raise RuntimeError("Không nhận ra link video. Hãy dán link video, note hoặc link rút gọn v.douyin.com.")
    video_id = video_id_of(target)
    manifest = _load_manifest()
    already = bool(video_id and link_keys(target, video_id) & known_links(manifest) and _has_file(video_id))
    with _SYNC_LOCK:
        if _SYNC["running"]:
            raise RuntimeError("Đang đồng bộ Douyin. Hãy đợi lần này xong.")
        if already:
            _SYNC["message"] = "Video này đã có, không tải lại."
            return dict(_SYNC)
        _SYNC.update(running=True, message="Đang tải video Douyin", seen=0, skipped=0, downloaded=0, failed=0)
    threading.Thread(target=_run_one, args=(target,), name="dy-one", daemon=True).start()
    return sync_status()


def _maybe_auto_sync() -> None:
    with _SYNC_AUTO_LOCK:
        cfg = _read_sync_auto()
        if not _sync_auto_due(cfg):
            return
    try:
        start_sync("")
    except RuntimeError:
        return


def _sync_scheduler() -> None:
    while True:
        try:
            _maybe_auto_sync()
        except Exception:
            pass
        threading.Event().wait(15)


def start_sync_scheduler() -> None:
    with _SYNC_AUTO_LOCK:
        started = getattr(start_sync_scheduler, "_started", False)
        start_sync_scheduler._started = True
    if started:
        return
    threading.Thread(target=_sync_scheduler, name="dy-sync-auto", daemon=True).start()


def _unlink_glob(folder: Path, pattern: str) -> list[str]:
    removed = []
    if not folder.is_dir():
        return removed
    for path in folder.glob(pattern):
        if not path.is_file():
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except OSError:
            pass
    return removed


def _rmtree(path: Path) -> bool:
    import shutil

    if not path.exists():
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except OSError:
        return False


def _drop_posts_item(posts_path: Path, video_id: str) -> bool:
    if not posts_path.is_file():
        return False
    try:
        data = json.loads(posts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if not isinstance(items, dict) or video_id not in items:
        return False
    items.pop(video_id, None)
    data["items"] = items
    posts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _drop_translation(video_id: str) -> bool:
    path = DATA_DIR / "translations.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or video_id not in data:
        return False
    data.pop(video_id, None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def delete_video(video_id: str) -> dict:
    """Xóa video Douyin khỏi kho: file gốc, bản AI, manifest, archive, dịch, lịch sử đăng."""
    video_id = str(video_id or "").strip()
    if not re.fullmatch(r"\d{6,}", video_id):
        raise RuntimeError("ID video Douyin không hợp lệ.")

    # Chặn xóa khi đang xử lý / đang đăng video này
    try:
        import douyin_ai_job

        job = douyin_ai_job.job_status()
        if job.get("running") and str(job.get("video_id") or "") == video_id:
            raise RuntimeError("Đang tạo video ngắn cho video này. Đợi xong rồi xóa.")
    except ImportError:
        pass

    for module_name in (
        "douyin_poster",
        "douyin_youtube_poster",
        "douyin_tiktok_poster",
        "douyin_instagram_poster",
    ):
        try:
            mod = __import__(module_name)
            job = getattr(mod, "_JOB", None) or getattr(getattr(mod, "poster", None), "_job", None)
            if isinstance(job, dict) and job.get("running") and str(job.get("video_id") or "") == video_id:
                raise RuntimeError("Đang đăng video này. Đợi xong rồi xóa.")
            poster = getattr(mod, "poster", None)
            if poster is not None:
                live = getattr(poster, "_job", None)
                if isinstance(live, dict) and live.get("running") and str(live.get("video_id") or "") == video_id:
                    raise RuntimeError("Đang đăng video này. Đợi xong rồi xóa.")
        except ImportError:
            continue

    with _SYNC_LOCK:
        if _SYNC.get("running"):
            # Cho phép xóa khi sync đang chạy, miễn không đụng cùng file — vẫn an toàn hơn báo rõ
            pass

        manifest = _load_manifest()
        videos = [item for item in (manifest.get("videos") or []) if isinstance(item, dict)]
        found = next((item for item in videos if str(item.get("id") or "") == video_id), None)
        if not found and not _has_file(video_id) and not (DATA_DIR / "processed" / video_id).exists():
            raise RuntimeError("Không thấy video này trong kho Douyin.")

        removed_files = []
        removed_files.extend(_unlink_glob(VIDEO_DIR, f"{video_id}.*"))
        # File đặt tên khác nhưng ghi trong manifest
        stored = str((found or {}).get("file") or "")
        if stored:
            direct = Path(stored)
            candidates = [direct, VIDEO_DIR / direct.name]
            for path in candidates:
                if path.is_file():
                    try:
                        path.unlink()
                        removed_files.append(str(path))
                    except OSError:
                        pass

        processed = DATA_DIR / "processed" / video_id
        removed_processed = _rmtree(processed)

        _drop_archive(video_id)
        _drop_translation(video_id)
        posts_removed = []
        for name in ("posts.json", "youtube_posts.json", "tiktok_posts.json", "instagram_posts.json"):
            if _drop_posts_item(DATA_DIR / name, video_id):
                posts_removed.append(name)

        manifest["videos"] = [item for item in videos if str(item.get("id") or "") != video_id]
        manifest["updated_at"] = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
        _save_manifest(manifest)

    return {
        "ok": True,
        "id": video_id,
        "removed_files": sorted(set(removed_files)),
        "removed_processed": removed_processed,
        "removed_posts": posts_removed,
        "message": f"Đã xóa video {video_id}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tải một video Douyin về data/douyin.")
    parser.add_argument("--url", required=True, help="Link video Douyin.")
    args = parser.parse_args()
    if not is_video_url(args.url):
        print(friendly_error(RuntimeError("Không nhận ra link video Douyin.")))
        return 1
    manifest = _load_manifest()
    by_id = {item["id"]: item for item in manifest.get("videos") or [] if item.get("id")}
    try:
        ok = _download_one(args.url, manifest, by_id)
    except Exception as exc:
        print(friendly_error(exc))
        return 1
    print("Đã tải." if ok else "Không tải được.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
