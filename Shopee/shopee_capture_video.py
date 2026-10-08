#!/usr/bin/env python3
"""
Mở trình duyệt thật, bắt link video (.mp4 / .m3u8) giống tab Network (F12),
rồi tải về bằng shopee_video_dl.py (để cùng thư mục với file này).

Cài đặt (một lần):
  py -m pip install playwright requests yt-dlp
  py -m playwright install chromium

Cách dùng (mỗi lần MỘT link sản phẩm):
  py shopee_capture_video.py "https://shopee.vn/..."
  py shopee_capture_video.py "https://shopee.vn/..." --no-download
  py shopee_capture_video.py "https://shopee.vn/..." --wait 90 -o D:\\Shopee\\videos

Trình duyệt hiện lên. Nếu Shopee yêu cầu đăng nhập hoặc xác minh, bạn tự làm
trong cửa sổ đó (phiên đăng nhập được lưu trong thư mục browser_profile).
Nếu video không tự phát, bạn bấm nút phát trên trang.

Chỉ dùng cho video bạn có quyền sử dụng (của bạn, hoặc shop đã đồng ý).
"""
import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright

from shopee_video_dl import download_direct

EXTS = (".mp4", ".m3u8")
# File lưu phiên đăng nhập, nằm cạnh script (chứa cookie đăng nhập: không chia sẻ cho ai)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopee_state.json")


def is_video(url: str, content_type: str) -> bool:
    base = url.split("?")[0].lower()
    return (
        base.endswith(EXTS)
        or "video/" in content_type
        or "mpegurl" in content_type
    )


def capture(url: str, wait: int, profile: str, headless: bool = False,
            hide: bool = False) -> list:
    found = []

    def on_response(resp):
        try:
            ctype = resp.headers.get("content-type", "").lower()
        except Exception:
            ctype = ""
        if is_video(resp.url, ctype) and resp.url not in found:
            found.append(resp.url)
            print("Tìm thấy:", resp.url)

    with sync_playwright() as p:
        launch_args = (
            ["--start-minimized", "--window-position=-32000,-32000"] if hide else []
        )
        browser = p.chromium.launch(headless=headless, args=launch_args)
        state = STATE_FILE if os.path.exists(STATE_FILE) else None
        ctx = browser.new_context(storage_state=state)
        page = ctx.new_page()
        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded")
        print(f"Đang chờ video (tối đa {wait} giây). Nếu video không tự phát, hãy bấm phát trên trang...")

        deadline = time.time() + wait
        last_try = 0.0
        while time.time() < deadline and not found:
            page.wait_for_timeout(500)
            if time.time() - last_try > 5:
                last_try = time.time()
                try:
                    n = page.evaluate(
                        "() => { const v = document.querySelectorAll('video');"
                        " v.forEach(x => { x.muted = true; x.play().catch(() => {}); });"
                        " return v.length; }"
                    )
                    print(f"  (trang hiện có {n} thẻ video)")
                except Exception:
                    pass
        if found:
            page.wait_for_timeout(3000)  # chờ thêm để gom đủ các link
        else:
            try:
                print("Tiêu đề trang:", page.title())
                print("URL hiện tại :", page.url)
            except Exception:
                pass
        try:
            ctx.storage_state(path=STATE_FILE)
        except Exception as e:
            print("Không lưu được phiên đăng nhập:", e)
        ctx.close()
        browser.close()
    return found


def do_login():
    """Mở trình duyệt để bạn đăng nhập thủ công, rồi lưu phiên vào STATE_FILE."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        state = STATE_FILE if os.path.exists(STATE_FILE) else None
        ctx = browser.new_context(storage_state=state)
        page = ctx.new_page()
        page.goto("https://shopee.vn/buyer/login", wait_until="domcontentloaded")
        input("Đăng nhập xong trong cửa sổ trình duyệt, rồi quay lại đây nhấn Enter...")
        ctx.storage_state(path=STATE_FILE)
        print("Đã lưu phiên đăng nhập vào", STATE_FILE)
        ctx.close()
        browser.close()


def pick_best(urls: list) -> str:
    for u in urls:
        if ".mp4" in u.split("?")[0].lower():
            return u
    return urls[0]


def main():
    ap = argparse.ArgumentParser(description="Bắt link video Shopee bằng trình duyệt.")
    ap.add_argument("url", nargs="?", help="Link sản phẩm Shopee (một link mỗi lần)")
    ap.add_argument("--login", action="store_true",
                    help="Mở trình duyệt để đăng nhập một lần và lưu phiên")
    ap.add_argument("--wait", type=int, default=60, help="Số giây chờ video (mặc định 60)")
    ap.add_argument("-o", "--out", default="videos", help="Thư mục lưu video")
    ap.add_argument("--profile", default="browser_profile", help="Thư mục lưu phiên trình duyệt")
    ap.add_argument("--no-download", action="store_true", help="Chỉ in link, không tải")
    ap.add_argument("--headless", action="store_true",
                    help="Chạy ngầm, không hiện cửa sổ trình duyệt")
    ap.add_argument("--hide", action="store_true",
                    help="Mở trình duyệt thật nhưng thu nhỏ và đặt ngoài màn hình")
    args = ap.parse_args()

    if args.login:
        do_login()
        return
    if not args.url:
        ap.error("Cần link sản phẩm Shopee (hoặc dùng --login để đăng nhập một lần)")

    urls = capture(args.url, args.wait, args.profile, args.headless, args.hide)
    if not urls:
        print("\nKhông bắt được link video. Có thể sản phẩm không có video, "
              "hoặc video chưa được phát. Thử tăng --wait hoặc bấm phát thủ công.")
        sys.exit(1)

    best = pick_best(urls)
    print("\nLink chọn:", best)
    if args.no_download:
        return

    import os
    os.makedirs(args.out, exist_ok=True)
    if not download_direct(best, args.out):
        print("\nTải thất bại (link có thể hết hạn hoặc cần ffmpeg cho .m3u8). "
              "Thử chạy lại hoặc dùng --no-download rồi tải bằng shopee_video_dl.py --video-url.")
        sys.exit(1)


if __name__ == "__main__":
    main()
