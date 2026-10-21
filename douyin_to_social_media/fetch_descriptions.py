#!/usr/bin/env python3
"""Lấy phần mô tả YouTube của các Shorts đã tải và ghi vào data/manifest.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yt_dlp

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MANIFEST = DATA / "manifest.json"
COOKIE = ROOT / "www.youtube.com_cookies.txt"


def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save(manifest: dict) -> None:
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(MANIFEST)


def fetch_one(ydl: yt_dlp.YoutubeDL, video_id: str) -> str:
    info = ydl.extract_info(f"https://www.youtube.com/shorts/{video_id}", download=False, process=False)
    if not isinstance(info, dict):
        return ""
    return str(info.get("description") or "").strip()


def main() -> int:
    if not COOKIE.is_file():
        print(f"Không thấy file cookie: {COOKIE}", file=sys.stderr)
        return 1
    manifest = load()
    videos = manifest.get("videos") or []
    pending = [item for item in videos if not str(item.get("description") or "").strip()]
    print(f"Cần lấy mô tả: {len(pending)} / {len(videos)}", flush=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "cookiefile": str(COOKIE),
        "ignore_no_formats_error": True,
    }
    done = 0
    failed = 0
    with yt_dlp.YoutubeDL(opts) as ydl:
        for index, item in enumerate(pending, start=1):
            video_id = item.get("id") or ""
            try:
                item["description"] = fetch_one(ydl, video_id)
                done += 1
            except Exception as exc:
                failed += 1
                print(f"[{index}/{len(pending)}] {video_id} lỗi: {exc}", file=sys.stderr, flush=True)
                time.sleep(2)
                continue
            if index % 10 == 0 or index == len(pending):
                save(manifest)
                print(f"[{index}/{len(pending)}] đã lưu", flush=True)
            time.sleep(0.3)
    save(manifest)
    filled = sum(1 for item in videos if str(item.get("description") or "").strip())
    print(f"Xong. Có mô tả: {filled}/{len(videos)}. Lỗi lần này: {failed}.", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
