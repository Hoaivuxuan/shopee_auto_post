#!/usr/bin/env python3
"""
Tải video từ MỘT link Shopee về máy.

Cách dùng:
  1) Link sản phẩm / link video / link rút gọn shope.ee:
       python shopee_video_dl.py "https://shopee.vn/..."
  2) Nếu cách 1 không được, lấy link file video từ trình duyệt
     (F12 > Network > lọc "mp4" hoặc "m3u8" > phát video > copy URL):
       python shopee_video_dl.py --video-url "https://.../abc.mp4"
       python shopee_video_dl.py --video-url "https://.../index.m3u8"

Yêu cầu:
  pip install requests yt-dlp
  ffmpeg (cần khi tải luồng .m3u8): https://ffmpeg.org/download.html

Lưu ý: chỉ dùng cho video bạn có quyền sử dụng (của bạn, hoặc shop đã đồng ý).
"""
import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def resolve_url(url: str) -> str:
    """Theo dõi chuyển hướng (vd: shope.ee -> shopee.vn/...)."""
    try:
        r = requests.get(
            url, allow_redirects=True, timeout=20,
            headers={"User-Agent": UA}, stream=True,
        )
        final = r.url
        r.close()
        return final
    except requests.RequestException:
        return url


def download_with_ytdlp(url: str, out_dir: str) -> bool:
    if importlib.util.find_spec("yt_dlp") is None:
        print("Chưa cài yt-dlp. Chạy: pip install yt-dlp")
        return False
    template = os.path.join(out_dir, "%(title).80s_%(id)s.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "-o", template, url]
    print("Đang thử yt-dlp...")
    return subprocess.run(cmd).returncode == 0


def download_direct(video_url: str, out_dir: str, filename: str = None) -> bool:
    """Tải link trực tiếp .mp4 hoặc luồng .m3u8."""
    name = re.sub(r"[^\w.-]", "_", video_url.split("?")[0].rstrip("/").split("/")[-1])
    if not name:
        name = "video"
    if filename:
        name = filename

    if ".m3u8" in video_url:
        if shutil.which("ffmpeg") is None:
            print("Cần cài ffmpeg để tải luồng .m3u8.")
            return False
        path = os.path.join(out_dir, os.path.splitext(name)[0] + ".mp4")
        cmd = ["ffmpeg", "-y", "-user_agent", UA, "-i", video_url, "-c", "copy", path]
        ok = subprocess.run(cmd).returncode == 0
        if ok:
            print("Đã lưu:", path)
        return ok

    if not name.lower().endswith((".mp4", ".mov", ".webm")):
        name += ".mp4"
    path = os.path.join(out_dir, name)
    try:
        with requests.get(
            video_url, stream=True, timeout=60, headers={"User-Agent": UA}
        ) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
    except requests.RequestException as e:
        print("Lỗi tải:", e)
        return False
    print("Đã lưu:", path)
    return True


def main():
    ap = argparse.ArgumentParser(description="Tải video Shopee từ một link.")
    ap.add_argument("url", nargs="?", help="Link sản phẩm / video Shopee")
    ap.add_argument("--video-url", help="Link trực tiếp tới file .mp4 / .m3u8")
    ap.add_argument("-o", "--out", default="videos", help="Thư mục lưu (mặc định: videos)")
    args = ap.parse_args()

    if not args.url and not args.video_url:
        ap.error("Cần link Shopee hoặc --video-url")

    os.makedirs(args.out, exist_ok=True)

    if args.video_url:
        sys.exit(0 if download_direct(args.video_url, args.out) else 1)

    url = resolve_url(args.url)
    print("Link sau khi chuyển hướng:", url)
    if download_with_ytdlp(url, args.out):
        print("Xong. Video nằm trong thư mục:", os.path.abspath(args.out))
        return

    print(
        "\nKhông tải tự động được từ link này (Shopee không có API công khai "
        "và hay đổi cấu trúc trang).\n"
        "Hãy lấy link file video bằng F12 > Network rồi chạy lại với --video-url."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
