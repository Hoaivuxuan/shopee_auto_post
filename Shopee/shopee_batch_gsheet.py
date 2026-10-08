#!/usr/bin/env python3
"""
Tải video hàng loạt từ danh sách link trong GOOGLE SHEET, rồi ghi kết quả vào lại sheet.

Chuẩn bị (một lần):
  py -m pip install gspread
  (đã cài playwright, requests, yt-dlp và đã chạy `shopee_capture_video.py --login`)
  + tạo tài khoản dịch vụ Google và file khóa service_account.json (xem hướng dẫn kèm theo)

Cách dùng:
  1) Tạo tiêu đề cột:  py shopee_batch_gsheet.py --sheet "LINK_SHEET" --init
  2) Dán link sản phẩm vào cột A của sheet (từ dòng 2).
  3) Chạy:             py shopee_batch_gsheet.py --sheet "LINK_SHEET"

Cột trong sheet: Link sản phẩm | Trạng thái | Thời gian | File video | Ghi chú
  - Dòng chưa có trạng thái sẽ được xử lý; "Thành công" thì bỏ qua.
  - Dòng "Lỗi" chỉ chạy lại khi thêm --retry.

Các tùy chọn:
  --sheet     link hoặc ID của Google Sheet (bắt buộc)
  --creds     file khóa tài khoản dịch vụ (mặc định service_account.json)
  --tab       tên tab (mặc định: tab đầu tiên)
  --out       thư mục lưu video (mặc định videos)
  --limit     số link tối đa mỗi lần chạy (mặc định 10)
  --min-delay / --max-delay   nghỉ ngẫu nhiên giữa 2 link, tính bằng giây (30-90)
  --wait      số giây chờ video của mỗi link (mặc định 60)
  --show      hiện cửa sổ trình duyệt (mặc định thu nhỏ/ẩn)
  --retry     chạy lại cả các dòng "Lỗi"

Chỉ dùng cho video bạn có quyền sử dụng (của bạn, hoặc shop đã đồng ý).
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime

import gspread
import requests

from shopee_capture_video import capture, pick_best
from shopee_video_dl import download_direct

HEADERS = ["Link sản phẩm", "Trạng thái", "Thời gian", "File video", "Ghi chú"]
NET_ERRORS = (gspread.exceptions.APIError, requests.exceptions.RequestException)


def with_retry(fn, *args, **kwargs):
    """Gọi API Google, thử lại vài lần nếu lỗi mạng hoặc bị giới hạn tốc độ."""
    for attempt in range(4):
        try:
            return fn(*args, **kwargs)
        except NET_ERRORS:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def service_email(creds):
    try:
        with open(creds, encoding="utf-8") as f:
            return json.load(f).get("client_email", "(không đọc được email)")
    except Exception:  # noqa: BLE001
        return "(không đọc được email)"


def open_sheet(creds, sheet, tab):
    gc = gspread.service_account(filename=creds)
    sh = gc.open_by_url(sheet) if sheet.lower().startswith("http") else gc.open_by_key(sheet)
    return sh.worksheet(tab) if tab else sh.sheet1


def product_id(link, row):
    m = re.search(r"i\.(\d+)\.(\d+)", link) or re.search(r"/product/(\d+)/(\d+)", link)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return f"row{row}"


def locate(ws, link, hint):
    """Tìm lại số dòng của link (phòng khi bạn thêm/xóa dòng trong lúc chương trình chạy)."""
    col = with_retry(ws.col_values, 1)
    if hint <= len(col) and col[hint - 1].strip() == link:
        return hint
    for i, v in enumerate(col, 1):
        if i > 1 and v.strip() == link:
            return i
    return None


def write_row(ws, link, hint, status, file="", note="", with_time=True):
    row = locate(ws, link, hint)
    if row is None:
        print("  (không tìm thấy lại dòng của link này trong sheet, bỏ qua ghi kết quả)")
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if with_time else ""
    with_retry(ws.update, values=[[status, stamp, file, note]], range_name=f"B{row}:E{row}")


def process_link(ws, link, row, args):
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


def init_headers(ws):
    first = with_retry(ws.get, "A1:E1")
    if first and first[0] and any(str(c).strip() for c in first[0]):
        print("Sheet đã có dòng tiêu đề, không ghi đè.")
        return
    with_retry(ws.update, values=[HEADERS], range_name="A1:E1")
    print("Đã tạo dòng tiêu đề. Dán link sản phẩm vào cột A từ dòng 2.")


def main():
    ap = argparse.ArgumentParser(description="Tải video Shopee hàng loạt từ Google Sheet.")
    ap.add_argument("--sheet", required=True, help="Link hoặc ID của Google Sheet")
    ap.add_argument("--creds", default="service_account.json")
    ap.add_argument("--tab", default=None)
    ap.add_argument("--out", default="videos")
    ap.add_argument("--wait", type=int, default=60)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--min-delay", type=int, default=30)
    ap.add_argument("--max-delay", type=int, default=90)
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--init", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.creds):
        print(f"Không thấy file khóa {args.creds}. Hãy đặt service_account.json vào thư mục này.")
        sys.exit(1)
    if args.max_delay < args.min_delay:
        args.max_delay = args.min_delay

    try:
        ws = open_sheet(args.creds, args.sheet, args.tab)
        if args.init:
            init_headers(ws)
            return
        values = with_retry(ws.get_all_values)
    except (gspread.exceptions.SpreadsheetNotFound, gspread.exceptions.APIError) as e:
        print("Không mở được Google Sheet:", e)
        print("Kiểm tra: (1) đã bật Google Sheets API, (2) đã chia sẻ sheet với quyền Editor cho:",
              service_email(args.creds))
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
            write_row(ws, link, row, "Đang xử lý", with_time=False)
            try:
                status, file, note = process_link(ws, link, row, args)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                status, file, note = "Lỗi", "", str(e)[:200]
            write_row(ws, link, row, status, file, note)
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
                write_row(ws, link, row, "", with_time=False)
            except Exception:  # noqa: BLE001
                pass

    print(f"\nXong. Thành công: {ok} | Lỗi: {fail}. Kết quả đã ghi vào Google Sheet.")


if __name__ == "__main__":
    main()
