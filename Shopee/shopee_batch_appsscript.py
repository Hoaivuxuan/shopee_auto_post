#!/usr/bin/env python3
"""
Tải video hàng loạt từ danh sách link trong GOOGLE SHEET, ghi kết quả vào lại sheet.
Bản này dùng Google Apps Script (miễn phí, không cần Google Cloud, không cần file khóa).

Chuẩn bị (một lần):
  - Dán apps_script_Code.gs vào Apps Script của sheet, đổi TOKEN, triển khai Web app
    (xem hướng dẫn kèm theo) và lấy "Web app URL".
  - (đã cài playwright, requests, yt-dlp và đã chạy `shopee_capture_video.py --login`)

Cách dùng:
  1) Tạo tiêu đề cột:
       py shopee_batch_appsscript.py --url "WEB_APP_URL" --token "TOKEN" --init
  2) Dán link sản phẩm vào cột A của sheet (từ dòng 2).
  3) Chạy:
       py shopee_batch_appsscript.py --url "WEB_APP_URL" --token "TOKEN"

Có thể đặt sẵn biến môi trường SHEET_URL và SHEET_TOKEN để khỏi gõ mỗi lần.

Cột trong sheet: Link sản phẩm | Trạng thái | Thời gian | File video | Ghi chú
  - Dòng chưa có trạng thái sẽ được xử lý; "Thành công" thì bỏ qua.
  - Dòng "Lỗi" chỉ chạy lại khi thêm --retry.

Tùy chọn: --out, --limit (mặc định 10), --min-delay/--max-delay (30-90 giây),
          --wait (60), --show (hiện cửa sổ trình duyệt), --retry, --init

Chỉ dùng cho video bạn có quyền sử dụng (của bạn, hoặc shop đã đồng ý).
"""
import argparse
import os
import random
import re
import sys
import time
from datetime import datetime

import requests

from shopee_capture_video import capture, pick_best
from shopee_video_dl import download_direct

HEADERS = ["Link sản phẩm", "Trạng thái", "Thời gian", "File video", "Ghi chú"]


class SheetClient:
    """Gọi Google Apps Script Web app để đọc/ghi sheet."""

    def __init__(self, url, token):
        self.url = url
        self.token = token

    def call(self, action, **payload):
        body = {"token": self.token, "action": action, **payload}
        last_error = None
        data = None
        for attempt in range(4):
            try:
                r = requests.post(self.url, json=body, timeout=90)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                last_error = e
                time.sleep(5 * (attempt + 1))
        if data is None:
            raise RuntimeError(
                f"Không gọi được Apps Script ({last_error}). Kiểm tra lại Web app URL và "
                "mục 'Who has access' phải là 'Anyone'."
            )
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Apps Script báo lỗi"))
        return data


def product_id(link, row):
    m = re.search(r"i\.(\d+)\.(\d+)", link) or re.search(r"/product/(\d+)/(\d+)", link)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return f"row{row}"


def write_row(client, link, hint, status, file="", note="", with_time=True):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if with_time else ""
    res = client.call("update", link=link, hint=hint, status=status,
                      time=stamp, file=file, note=note)
    if not res.get("found"):
        print("  (không tìm thấy lại dòng của link này trong sheet, bỏ qua ghi kết quả)")


def process_link(link, row, args):
    fname = product_id(link, row) + ".mp4"
    out_path = os.path.join(args.out, fname)

    if os.path.exists(out_path):
        return "Thành công", out_path, "File đã có sẵn, bỏ qua tải lại"

    urls = capture(link, args.wait, "browser_profile", headless=False, hide=not args.show)
    if not urls:
        return "Lỗi", "", "Không bắt được link video (sản phẩm có thể không có video)"

    best = pick_best(urls)
    if download_direct(best, args.out, fname):
        return "Thành công", out_path, ""
    return "Lỗi", "", "Tải thất bại (link hết hạn hoặc thiếu ffmpeg cho .m3u8)"


def main():
    ap = argparse.ArgumentParser(description="Tải video Shopee hàng loạt từ Google Sheet (Apps Script).")
    ap.add_argument("--url", default=os.environ.get("SHEET_URL"), help="Web app URL của Apps Script")
    ap.add_argument("--token", default=os.environ.get("SHEET_TOKEN"), help="TOKEN đã đặt trong Code.gs")
    ap.add_argument("--out", default="videos")
    ap.add_argument("--wait", type=int, default=60)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--min-delay", type=int, default=30)
    ap.add_argument("--max-delay", type=int, default=90)
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--init", action="store_true")
    args = ap.parse_args()

    if not args.url or not args.token:
        ap.error("Cần --url và --token (hoặc đặt biến môi trường SHEET_URL, SHEET_TOKEN)")
    if args.max_delay < args.min_delay:
        args.max_delay = args.min_delay

    client = SheetClient(args.url, args.token)

    try:
        if args.init:
            res = client.call("init", headers=HEADERS)
            if res.get("existed"):
                print("Sheet đã có dòng tiêu đề, không ghi đè.")
            else:
                print("Đã tạo dòng tiêu đề. Dán link sản phẩm vào cột A từ dòng 2.")
            return
        values = client.call("list")["values"]
    except RuntimeError as e:
        print("Lỗi:", e)
        sys.exit(1)

    todo = []
    for idx, cells in enumerate(values[1:], start=2):
        link = cells[0].strip() if len(cells) > 0 else ""
        status = cells[1].strip() if len(cells) > 1 else ""
        if not link.lower().startswith("http"):
            continue
        if status == "Thành công":
            continue
        if status.startswith("Lỗi") and not args.retry:
            continue
        todo.append((idx, link))

    if not todo:
        print("Không có link nào cần xử lý (thêm link mới, hoặc dùng --retry để chạy lại dòng lỗi).")
        return

    todo = todo[: args.limit]
    print(f"Sẽ xử lý {len(todo)} link.\n")
    os.makedirs(args.out, exist_ok=True)

    ok = fail = 0
    current = None
    try:
        for i, (row, link) in enumerate(todo, 1):
            current = (row, link)
            print(f"[{i}/{len(todo)}] Dòng {row}: {link}")
            write_row(client, link, row, "Đang xử lý", with_time=False)
            try:
                status, file, note = process_link(link, row, args)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                status, file, note = "Lỗi", "", str(e)[:200]
            write_row(client, link, row, status, file, note)
            current = None
            ok += status == "Thành công"
            fail += status != "Thành công"
            print("  ->", status, "|", note)

            if i < len(todo):
                pause = random.randint(args.min_delay, args.max_delay)
                print(f"  Nghỉ {pause} giây trước link tiếp theo...\n")
                time.sleep(pause)
    except KeyboardInterrupt:
        print("\nĐã dừng theo yêu cầu (Ctrl+C).")
        if current:
            row, link = current
            try:
                write_row(client, link, row, "", with_time=False)
            except Exception:  # noqa: BLE001
                pass

    print(f"\nXong. Thành công: {ok} | Lỗi: {fail}. Kết quả đã ghi vào Google Sheet.")


if __name__ == "__main__":
    main()
