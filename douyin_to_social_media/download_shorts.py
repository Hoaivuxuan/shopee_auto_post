#!/usr/bin/env python3
"""Tải YouTube Shorts của một kênh về thư mục data cạnh script này.

Mặc định lấy tab Shorts của https://www.youtube.com/@biet.haychua.
Video đã tải được ghi trong data/archive.txt nên chạy lại sẽ bỏ qua.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import yt_dlp

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
VIDEO_DIR = DATA_DIR / "videos"
ARCHIVE_PATH = DATA_DIR / "archive.txt"
MANIFEST_PATH = DATA_DIR / "manifest.json"
SYNC_AUTO_PATH = DATA_DIR / "sync_auto.json"
COOKIE_PATH = ROOT / "www.youtube.com_cookies.txt"
VN_TZ = timezone(timedelta(hours=7))

DEFAULT_URL = "https://www.youtube.com/@biet.haychua/shorts"
_VIDEO_ID = re.compile(r"(?:shorts/|watch\?v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})")
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


def _load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"channel_url": DEFAULT_URL, "videos": []}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"channel_url": DEFAULT_URL, "videos": []}


def _save_manifest(manifest: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _entry_record(info: dict, filepath: str | None, source: str = "") -> dict:
    video_id = info.get("id") or ""
    raw = source or info.get("channel_url") or info.get("uploader_url") or ""
    channel = channel_key(raw)
    name = str(info.get("channel") or info.get("uploader") or "").strip() or channel_label(channel)
    return {
        "id": video_id,
        "title": info.get("title") or "",
        "url": info.get("webpage_url") or f"https://www.youtube.com/shorts/{video_id}",
        "upload_date": info.get("upload_date") or "",
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "description": info.get("description") or "",
        "channel": channel,
        "channel_name": name if channel else "",
        "file": filepath,
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
    video_id = info.get("id")
    if not video_id:
        return None
    matches = sorted(VIDEO_DIR.glob(f"{video_id}.*"))
    media = [p for p in matches if p.suffix.lower() != ".json"]
    return str(media[0]) if media else None


def _flush(manifest: dict, by_id: dict) -> None:
    videos = sorted(by_id.values(), key=lambda item: item.get("upload_date") or "", reverse=True)
    manifest["videos"] = videos
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_manifest(manifest)


def _remember(manifest: dict, by_id: dict, info: dict, filepath: str | None, source: str = "") -> bool:
    video_id = info.get("id")
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
            record["channel_name"] = previous.get("channel_name") or channel_label(record["channel"])
        elif not record.get("channel_name"):
            record["channel_name"] = previous.get("channel_name") or channel_label(record["channel"])
    by_id[video_id] = record
    _flush(manifest, by_id)
    return is_new


def _progress_hook(manifest: dict, by_id: dict, source: str = ""):
    def hook(status: dict) -> None:
        if status.get("status") != "finished":
            return
        info = status.get("info_dict") or {}
        filename = status.get("filename") or ""
        video_id = info.get("id") or ""
        name = Path(filename).name
        if not video_id or not name.startswith(f"{video_id}."):
            return
        if ".f" in name or name.endswith(".part"):
            return
        if not Path(filename).is_file():
            return
        _remember(manifest, by_id, info, filename, source)

    return hook


def _ydl_opts(limit: int | None, manifest: dict, by_id: dict, source: str = "") -> dict:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(VIDEO_DIR / "%(id)s.%(ext)s"),
        "download_archive": str(ARCHIVE_PATH),
        "nooverwrites": True,
        "ignoreerrors": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "quiet": False,
        "no_warnings": False,
        "progress_hooks": [_progress_hook(manifest, by_id, source)],
    }
    if limit:
        opts["playlistend"] = limit
    return opts


def download(url: str, limit: int | None) -> int:
    manifest = _load_manifest()
    manifest["channel_url"] = url
    by_id = {item["id"]: item for item in manifest.get("videos") or [] if item.get("id")}
    known = set(by_id)

    with yt_dlp.YoutubeDL(_ydl_opts(limit, manifest, by_id, url)) as ydl:
        info = ydl.extract_info(url, download=True)

    if not info:
        print("Không lấy được danh sách video.", file=sys.stderr)
        return 1

    entries = info.get("entries") if info.get("entries") is not None else [info]
    for entry in entries:
        if not entry or not entry.get("id"):
            continue
        path = _downloaded_path(entry)
        if not path and entry.get("id") in by_id:
            continue
        _remember(manifest, by_id, entry, path, url)

    _flush(manifest, by_id)
    new_count = sum(1 for video_id, item in by_id.items() if video_id not in known and item.get("file"))

    print(f"Xong. Mới tải: {new_count}. Tổng trong manifest: {len(manifest['videos'])}.")
    print(f"Video: {VIDEO_DIR}")
    print(f"Danh sách: {MANIFEST_PATH}")
    return 0


def _youtube_host(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return False
    return host in {"youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}


def clean_channel_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    return urlunparse((scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def channel_key(url: str) -> str:
    """Gom /shorts và trang kênh về cùng một địa chỉ."""
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[0].startswith("@"):
        path = "/" + parts[0]
    elif len(parts) >= 2 and parts[0] in {"channel", "c", "user"}:
        path = f"/{parts[0]}/{parts[1]}"
    else:
        path = "/" + "/".join(parts)
    host = parsed.netloc or "www.youtube.com"
    return urlunparse((parsed.scheme or "https", host, path.rstrip("/"), "", "", ""))


def channel_label(url: str) -> str:
    key = channel_key(url)
    parts = [part for part in urlparse(key).path.split("/") if part]
    if parts and parts[0].startswith("@"):
        return parts[0]
    if len(parts) >= 2 and parts[0] in {"channel", "c", "user"}:
        return parts[1]
    return key or "Kênh khác"


def is_video_url(url: str) -> bool:
    return bool(video_id_of(url))


def is_channel_url(url: str) -> bool:
    if not _youtube_host(url) or is_video_url(url):
        return False
    path = urlparse(url).path.lower()
    return (
        path.startswith("/@")
        or path.startswith("/channel/")
        or path.startswith("/c/")
        or path.startswith("/user/")
        or path.startswith("/playlist")
    )


def saved_channels(manifest: dict | None = None) -> list[str]:
    manifest = _load_manifest() if manifest is None else manifest
    urls = []
    for item in manifest.get("channels") or []:
        text = str(item or "").strip()
        if text and text not in urls:
            urls.append(text)
    legacy = str(manifest.get("channel_url") or "").strip()
    if legacy and legacy not in urls:
        urls.insert(0, legacy)
    if not urls:
        urls.append(DEFAULT_URL)
    return urls


def remember_channel(url: str) -> list[str]:
    manifest = _load_manifest()
    channels = saved_channels(manifest)
    if url not in channels:
        channels.append(url)
    manifest["channels"] = channels
    manifest["channel_url"] = url
    _save_manifest(manifest)
    return channels


def video_id_of(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    match = _VIDEO_ID.search(text)
    return match.group(1) if match else ""


def link_keys(url: str, video_id: str = "") -> set[str]:
    """Các dạng link của cùng một video, dùng để lọc trùng."""
    found = video_id_of(video_id) or video_id_of(url)
    if not found:
        return set()
    return {
        f"https://www.youtube.com/shorts/{found}",
        f"https://www.youtube.com/watch?v={found}",
        f"https://youtu.be/{found}",
    }


def known_links(manifest: dict) -> set[str]:
    found = set()
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict):
            continue
        found |= link_keys(str(item.get("url") or ""), str(item.get("id") or ""))
    return found


def _cookie_opts() -> dict:
    if COOKIE_PATH.is_file():
        return {"cookiefile": str(COOKIE_PATH)}
    return {}


def _has_file(video_id: str) -> bool:
    path = VIDEO_DIR / f"{video_id}.mp4"
    return path.is_file()


def _sync_set(**kwargs) -> None:
    with _SYNC_LOCK:
        _SYNC.update(kwargs)


def channel_catalog(manifest: dict | None = None) -> list[dict]:
    manifest = _load_manifest() if manifest is None else manifest
    names: dict[str, str] = {}
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("channel") or "")
        if key and key not in names:
            names[key] = str(item.get("channel_name") or "") or channel_label(key)
    for url in saved_channels(manifest):
        key = channel_key(url)
        if key:
            names.setdefault(key, channel_label(key))
    return [{"url": url, "name": name} for url, name in names.items()]


def ensure_channel_tags() -> int:
    """Video tải trước khi có phân loại được gắn vào kênh đã đồng bộ lúc đó."""
    manifest = _load_manifest()
    fallback = channel_key(str(manifest.get("channel_url") or DEFAULT_URL))
    label = channel_label(fallback)
    changed = 0
    for item in manifest.get("videos") or []:
        if not isinstance(item, dict):
            continue
        if item.get("channel"):
            if not item.get("channel_name"):
                item["channel_name"] = channel_label(str(item.get("channel") or ""))
                changed += 1
            continue
        item["channel"] = fallback
        item["channel_name"] = label
        changed += 1
    if changed:
        _save_manifest(manifest)
    return changed


def sync_status() -> dict:
    with _SYNC_LOCK:
        data = dict(_SYNC)
    data["channels"] = channel_catalog()
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
    if not cfg.get("enabled"):
        return ""
    last = str(cfg.get("last_at") or "")
    if not last:
        return ""
    try:
        stamp = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
    except ValueError:
        return _now_str()
    minutes = _interval_minutes(cfg.get("interval_minutes"))
    return (stamp + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


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
    if not next_at:
        return False
    return _now_str() >= next_at


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
    threading.Thread(target=_sync_scheduler, name="yt-sync-auto", daemon=True).start()


def _drop_archive(video_id: str) -> None:
    if not video_id or not ARCHIVE_PATH.is_file():
        return
    lines = ARCHIVE_PATH.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip() != f"youtube {video_id}"]
    if len(kept) == len(lines):
        return
    text = "\n".join(kept)
    ARCHIVE_PATH.write_text(f"{text}\n" if text else "", encoding="utf-8")


def list_channel(url: str) -> list[dict]:
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
        **_cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return []
    return [entry for entry in (info.get("entries") or []) if entry]


def _download_one(url: str, manifest: dict, by_id: dict, source: str = "") -> bool:
    video_id = video_id_of(url)
    if video_id and not _has_file(video_id):
        _drop_archive(video_id)
    opts = _ydl_opts(None, manifest, by_id, source)
    opts.update(_cookie_opts())
    opts["quiet"] = True
    opts["no_warnings"] = True
    opts["ignore_no_formats_error"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
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
        fresh.append((video_id, video_url or f"https://www.youtube.com/watch?v={video_id}"))
        known |= keys
    return fresh, skipped


def _run_sync(urls: list[str] | None = None) -> None:
    skipped = 0
    downloaded = 0
    failed = 0
    seen = 0
    try:
        manifest = _load_manifest()
        targets = urls or saved_channels(manifest)
        known = known_links(manifest)
        by_id = {item["id"]: item for item in manifest.get("videos") or [] if item.get("id")}
        for url in targets:
            _sync_set(message=f"Đang đọc danh sách video: {url}")
            try:
                entries = list_channel(url)
            except Exception as exc:
                failed += 1
                _sync_set(message=f"Không đọc được kênh: {exc}"[:180])
                continue
            if not entries:
                _sync_set(message=f"Không thấy video tại {url}")
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
                except Exception:
                    ok = False
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
    except Exception as exc:
        _sync_set(message=f"Đồng bộ lỗi: {exc}"[:180])
    finally:
        _sync_set(running=False)


def _run_one(url: str) -> None:
    try:
        manifest = _load_manifest()
        by_id = {item["id"]: item for item in manifest.get("videos") or [] if item.get("id")}
        _sync_set(message="Đang tải video")
        ok = _download_one(url, manifest, by_id)
        if ok:
            _sync_set(message="Đã tải video về.", downloaded=1, seen=1, failed=0)
        else:
            _sync_set(message="Không tải được video này.", failed=1, downloaded=0)
    except Exception as exc:
        _sync_set(message=f"Tải video lỗi: {exc}"[:180], failed=1)
    finally:
        _sync_set(running=False)


def start_sync(url: str = "") -> dict:
    target = str(url or "").strip()
    clean = ""
    if target:
        if not _youtube_host(target):
            raise RuntimeError("Chỉ nhận link YouTube.")
        if is_video_url(target):
            raise RuntimeError("Đây là link một video. Hãy dán vào ô tải video.")
        if not is_channel_url(target):
            raise RuntimeError("Không nhận ra link kênh. Hãy dán link dạng @tênkênh hoặc tab Shorts.")
        clean = clean_channel_url(target)
    with _SYNC_LOCK:
        if _SYNC["running"]:
            raise RuntimeError("Đang đồng bộ. Hãy đợi lần này xong.")
        urls = [remember_channel(clean)[-1]] if clean else None
        _SYNC.update(running=True, message="Đang bắt đầu đồng bộ", seen=0, skipped=0, downloaded=0, failed=0)
    if not clean:
        _mark_saved_sync()
    threading.Thread(target=_run_sync, args=(urls,), name="yt-sync", daemon=True).start()
    return sync_status()


def start_download(url: str) -> dict:
    target = str(url or "").strip()
    if not target:
        raise RuntimeError("Hãy dán link video YouTube.")
    if not _youtube_host(target):
        raise RuntimeError("Chỉ nhận link YouTube.")
    if is_channel_url(target):
        raise RuntimeError("Đây là link kênh. Hãy dán vào ô đồng bộ kênh.")
    video_id = video_id_of(target)
    if not video_id:
        raise RuntimeError("Không nhận ra link video. Hãy dán link Shorts hoặc watch.")
    manifest = _load_manifest()
    already = bool(link_keys(target, video_id) & known_links(manifest)) and _has_file(video_id)
    with _SYNC_LOCK:
        if _SYNC["running"]:
            raise RuntimeError("Đang đồng bộ. Hãy đợi lần này xong.")
        if already:
            _SYNC["message"] = "Video này đã có, không tải lại."
            return dict(_SYNC)
        _SYNC.update(running=True, message="Đang tải video", seen=0, skipped=0, downloaded=0, failed=0)
    threading.Thread(target=_run_one, args=(target,), name="yt-one", daemon=True).start()
    return sync_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tải YouTube Shorts về thư mục data.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL tab Shorts hoặc video đơn.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Số video tối đa (0 = tải hết).",
    )
    args = parser.parse_args()
    limit = args.limit if args.limit and args.limit > 0 else None
    return download(args.url, limit)


if __name__ == "__main__":
    raise SystemExit(main())
