"""Kiểm tra logic lõi bằng Google Sheet giả và Facebook giả (không cần mạng/trình duyệt).
Chạy:  py tests/test_core.py"""
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402

from shopeetool import config, jobs, paths  # noqa: E402
from shopeetool.logger import RunContext  # noqa: E402

paths._DATA_DIR = tempfile.mkdtemp(prefix="sfb_test_")
TOKEN = "tok"
URL = "https://script.google.com/macros/s/FAKE/exec"
rows = []
fb_calls = []
bad_tokens = set()


class Resp:
    def __init__(self, d, code=200):
        self.d, self.status_code = d, code

    def raise_for_status(self):
        pass

    def json(self):
        return self.d


def server(b):
    if b["token"] != TOKEN:
        return Resp({"ok": False, "error": "Sai token"})
    a = b["action"]
    if a == "ping":
        return Resp({"ok": True, "name": "Sheet thử", "tab": "Sheet1", "rows": len(rows)})
    if a == "tab_list":
        return Resp({"ok": True, "values": [r[:b["ncols"]] for r in rows]})
    if a == "tab_update":
        keyof = lambda r: "|".join(rows[r][c - 1].strip() for c in b["key_cols"])
        h = b["hint"]
        row = -1
        if 2 <= h <= len(rows) and keyof(h - 1) == b["key"]:
            row = h
        else:
            for i in range(1, len(rows)):
                if keyof(i) == b["key"]:
                    row = i + 1
                    break
        if row == -1:
            return Resp({"ok": True, "found": False})
        s = b["start_col"] - 1
        rows[row - 1][s:s + len(b["values"])] = b["values"]
        return Resp({"ok": True, "found": True})
    return Resp({"ok": False, "error": "Hành động không hợp lệ: " + a})


def fake_post(url, json=None, data=None, files=None, timeout=None, **kw):
    if json is not None:
        return server(json)
    fb_calls.append((url, dict(data or {})))
    if url.endswith("/videos"):
        tok = data["access_token"]
        if tok in bad_tokens:
            return Resp({"error": {"message": "Invalid OAuth access token.", "code": 190}}, 400)
        if tok == "RATE":
            return Resp({"error": {"message": "rate", "code": 4}}, 400)
        return Resp({"id": "vid_" + url.split("/")[-2]})
    return Resp({"id": "c1"})


requests.post = fake_post
time.sleep_real = time.sleep


class FakeSession:
    def __init__(self, cfg, ctx):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def capture(self, url, wait):
        if "novideo" in url:
            return [], "Trang không có video | https://shopee.vn/x"
        return ["https://cdn.example/a.mp4"], ""


def fake_download(url, dest, ctx):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(b"x" * 100)


jobs.ShopeeSession = FakeSession
jobs.download_file = fake_download

fails = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  LỖI  ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


def new_cfg():
    cfg = config.load()
    cfg["sheet"].update(url=URL, token=TOKEN)
    cfg["shopee"].update(min_delay=0, max_delay=0, limit=20)
    cfg["facebook"].update(min_delay=0, max_delay=0, limit=20)
    cfg["pages"] = [
        {"name": "Page Một", "id": "P1", "token": "T1", "enabled": True},
        {"name": "Page Hai", "id": "P2", "token": "T2", "enabled": True},
        {"name": "Page Hỏng", "id": "P9", "token": "BAD", "enabled": True},
        {"name": "Page Tắt", "id": "P7", "token": "T7", "enabled": False},
        {"name": "Page Giới Hạn", "id": "P8", "token": "RATE", "enabled": True},
    ]
    return cfg


def new_ctx():
    events = []
    return RunContext(emit=events.append), events


HDR = ["Link sản phẩm", "Trạng thái", "Thời gian", "File video", "Ghi chú", "Page", "Link affiliate",
       "Nội dung", "Tag", "Giờ đăng", "Trạng thái đăng", "Đã xử lý lúc", "ID bài đăng", "Ghi chú đăng"]


def dl_row(link):
    return [link] + [""] * 13


def post_row(link, f, pg="Page Một", aff="https://s.shopee.vn/X", txt="Nội dung", tag="", when="", st="", dl="Thành công"):
    return [link, dl, "", f, "", pg, aff, txt, tag, when, st, "", "", ""]


# ------------------------------------------------------------------ TẢI
print("== Tải video")
cfg = new_cfg()
vdir = config.videos_dir(cfg)
os.makedirs(vdir, exist_ok=True)
open(os.path.join(vdir, "3_3.mp4"), "wb").write(b"x")
rows[:] = [HDR[:], dl_row("https://shopee.vn/a-i.1.1"), dl_row("https://shopee.vn/novideo-i.2.2"),
           dl_row("https://shopee.vn/c-i.3.3"), dl_row("không phải link")]
ctx, ev = new_ctx()
jobs.run_download(cfg, ctx)
check("dòng có video: Thành công + đường dẫn file", rows[1][1] == "Thành công" and rows[1][3].endswith("1_1.mp4"))
check("dòng không có video: Lỗi + ghi chú rõ", rows[2][1] == "Lỗi" and "Không bắt được link video" in rows[2][4], rows[2][4])
check("file đã có: bỏ qua tải lại", rows[3][1] == "Thành công" and "đã có sẵn" in rows[3][4])
check("dòng không phải link bị bỏ qua", rows[4][1] == "")
check("thống kê dl_ok=2, dl_fail=1", ctx.stats.get("dl_ok") == 2 and ctx.stats.get("dl_fail") == 1, str(ctx.stats))
ctx2, _ = new_ctx()
jobs.run_download(cfg, ctx2)
check("chạy lại: không tải lại dòng đã xong/lỗi", not ctx2.stats)
ctx3, _ = new_ctx()
jobs.run_download(cfg, ctx3, retry=True)
check("retry: chạy lại dòng lỗi", ctx3.stats.get("dl_fail") == 1)

# ------------------------------------------------------------------ ĐĂNG
print("== Đăng Facebook")
for n in ("111_222", "555_666"):
    open(os.path.join(vdir, n + ".mp4"), "wb").write(b"x")
now = datetime.now()
fmt = lambda d: d.strftime("%Y-%m-%d %H:%M:%S")
rows[:] = [HDR[:],
           post_row("https://shopee.vn/L1", "videos\\111_222.mp4", pg="page một, Page Hai", tag="#giadung, sale #giadung"),
           post_row("https://shopee.vn/L2", "111_222", pg="Page Một", when=fmt(now - timedelta(hours=1))),
           post_row("https://shopee.vn/L3", "111_222.mp4", when=fmt(now + timedelta(hours=3))),
           post_row("https://shopee.vn/L4", "111_222.mp4", when="không phải giờ"),
           post_row("https://shopee.vn/L5", "nofile.mp4"),
           post_row("https://shopee.vn/L6", "555_666.mp4", pg="Page Một; Page Hỏng"),
           post_row("https://shopee.vn/L7", "555_666.mp4", pg="Page Tắt"),
           post_row("https://shopee.vn/L8", "555_666.mp4", pg="Không có page"),
           post_row("https://shopee.vn/L9", "555_666.mp4", dl="Lỗi"),
           post_row("https://shopee.vn/L10", "555_666.mp4", st="Đang xử lý"),
           post_row("https://shopee.vn/L11", "555_666.mp4", pg=""),
           post_row("https://shopee.vn/L12", "555_666.mp4", aff="", txt="")]
cfg = new_cfg()
bad_tokens.add("BAD")
ctx, ev = new_ctx()
jobs.run_post(cfg, ctx, dry_run=True)
check("dry-run không gọi Facebook và không ghi sheet", not fb_calls and rows[1][10] == "")
ctx, ev = new_ctx()
jobs.run_post(cfg, ctx)
S = lambda i: rows[i][10]
check("L1 đăng 2 Page: Thành công", S(1) == "Thành công" and rows[1][12].count("::") == 2, rows[1][12])
msgs = [d["description"] for u, d in fb_calls if u.endswith("/videos")]
check("nội dung: text + link + tag duy nhất", msgs[0] == "Nội dung\n\nMua tại: https://s.shopee.vn/X\n\n#giadung #sale", repr(msgs[0]))
check("L2 giờ đã qua: đăng ngay", S(2) == "Thành công")
check("L3 3 giờ nữa (local): chờ, chưa đăng", S(3) == "")
check("L4 giờ sai: Lỗi + hướng dẫn", S(4) == "Lỗi" and "không đọc được" in rows[4][13])
check("L5 thiếu file: Lỗi", S(5) == "Lỗi" and "Không thấy file video" in rows[5][13])
check("L6 một Page lỗi token: Một phần", S(6) == "Một phần" and "190" in rows[6][13], rows[6][13])
check("L7 Page bị tắt: Lỗi", S(7) == "Lỗi" and "đang bị tắt" in rows[7][13], rows[7][13])
check("L8 Page không tồn tại: Lỗi", S(8) == "Lỗi" and "Không thấy Page" in rows[8][13])
check("L9 tải lỗi: bỏ qua", S(9) == "")
check("L10 'Đang xử lý': không đăng lại", S(10) == "Đang xử lý" and not rows[10][12])
check("L11 chưa điền Page: bỏ qua", S(11) == "")
check("L12 không có link affiliate: dùng link cột A + ghi chú", S(12) == "Thành công" and "Cột G" in rows[12][13])
check("thống kê đăng", ctx.stats.get("post_ok") == 3 and ctx.stats.get("post_part") == 1 and ctx.stats.get("post_fail") == 4,
      str(ctx.stats))
warn_ev = [e for e in ev if e["type"] == "log" and e["level"] in ("warn", "error")]
check("có cảnh báo/lỗi được phát ra cho giao diện", len(warn_ev) >= 5)

n0 = len(fb_calls)
bad_tokens.clear()
ctx, _ = new_ctx()
jobs.run_post(cfg, ctx)
check("chạy lại thường: không đăng gì thêm", len(fb_calls) == n0)
ctx, _ = new_ctx()
jobs.run_post(cfg, ctx, retry=True)
posted = [u.split("/")[-2] for u, d in fb_calls[n0:] if u.endswith("/videos")]
check("retry: chỉ đăng nốt Page chưa xong của L6 (P9) và dòng lỗi khác", "P9" in posted and posted.count("P1") <= 2, str(posted))
check("L6 hoàn tất sau retry", S(6) == "Thành công" and rows[6][12].count("::") == 2, rows[6][12])

print("== Hẹn giờ trên Facebook")
fb_calls.clear()
rows[:] = [HDR[:],
           post_row("https://shopee.vn/S1", "111_222.mp4", when=fmt(now + timedelta(hours=3))),
           post_row("https://shopee.vn/S2", "111_222.mp4", when=fmt(now + timedelta(minutes=5))),
           post_row("https://shopee.vn/S3", "111_222.mp4", when=fmt(now + timedelta(days=40))),
           post_row("https://shopee.vn/S4", "111_222.mp4", when=(now + timedelta(hours=2)).strftime("%d/%m/%Y %H:%M"), pg="Page Một, Page Hai")]
cfg = new_cfg()
cfg["facebook"].update(schedule_mode="facebook", link_in_comment=True)
ctx, ev = new_ctx()
jobs.run_post(cfg, ctx)
check("S1 hẹn giờ: Đã lên lịch", rows[1][10] == "Đã lên lịch")
check("S2 (5 phút) và S3 (40 ngày) chờ", rows[2][10] == "" and rows[3][10] == "")
check("S4 nhiều Page, dd/mm/yyyy: Đã lên lịch", rows[4][10] == "Đã lên lịch" and rows[4][12].count("::") == 2)
sched = [d for u, d in fb_calls if u.endswith("/videos")]
check("gửi published=false và scheduled_publish_time", all(d.get("published") == "false" and d.get("scheduled_publish_time") for d in sched))
check("link nằm trong nội dung (không bình luận) khi hẹn giờ", all("Mua tại" in d["description"] for d in sched) and not any(u.endswith("/comments") for u, _ in fb_calls))
check("thống kê post_wait=2", ctx.stats.get("post_wait") == 2, str(ctx.stats))

print("== Bình luận khi đăng ngay")
fb_calls.clear()
rows[:] = [HDR[:], post_row("https://shopee.vn/C1", "111_222.mp4")]
cfg = new_cfg()
cfg["facebook"]["link_in_comment"] = True
jobs.run_post(cfg, new_ctx()[0])
check("đăng ngay + link_in_comment: link trong bình luận, không trong nội dung",
      any(u.endswith("/comments") for u, _ in fb_calls) and "Mua tại" not in fb_calls[0][1]["description"])

print("== Giới hạn tốc độ của Facebook")
rows[:] = [HDR[:], post_row("https://shopee.vn/R1", "111_222.mp4", pg="Page Giới Hạn, Page Một"),
           post_row("https://shopee.vn/R2", "111_222.mp4")]
cfg = new_cfg()
ctx, _ = new_ctx()
jobs.run_post(cfg, ctx)
check("lỗi mã 4: dừng cả lượt, dòng sau không bị đụng tới", rows[1][10] == "Lỗi" and rows[2][10] == "", f"{rows[1][10]!r} {rows[2][10]!r}")

print("== Hủy giữa chừng")
rows[:] = [HDR[:]] + [post_row(f"https://shopee.vn/K{i}", "111_222.mp4") for i in range(1, 5)]
cfg = new_cfg()
cfg["facebook"].update(min_delay=3, max_delay=3)
ctx, ev = new_ctx()
t = threading.Thread(target=lambda: jobs.run_all(cfg, ctx, "post"))
t.start()
time.sleep_real(1.0)
ctx.cancel()
t.join(10)
check("hủy: luồng kết thúc nhanh", not t.is_alive())
check("hủy: có sự kiện done(cancelled)", any(e["type"] == "done" and e.get("cancelled") for e in ev))
check("hủy: không dòng nào kẹt 'Đang xử lý'", all(r[10] != "Đang xử lý" for r in rows[1:]), str([r[10] for r in rows[1:]]))

print("== Chạy song song")
fb_calls.clear()
rows[:] = [HDR[:], dl_row("https://shopee.vn/a-i.111.222"), dl_row("https://shopee.vn/b-i.555.666")]
cfg = new_cfg()
cfg["pages"] = cfg["pages"][:2]
for r in rows[1:]:
    r[5] = "Page Một"
ctx, ev = new_ctx()
jobs.run_all(cfg, ctx, "parallel")
check("song song: tải xong rồi đăng cả 2", all(r[1] == "Thành công" and r[10] == "Thành công" for r in rows[1:]),
      str([(r[1], r[10]) for r in rows[1:]]))
check("có sự kiện done", any(e["type"] == "done" for e in ev))

print("== Lỗi cấu hình")
cfg = new_cfg()
cfg["sheet"]["token"] = "sai"
ctx, ev = new_ctx()
jobs.run_all(cfg, ctx, "post")
errs = [e["msg"] for e in ev if e["type"] == "log" and e["level"] == "error"]
check("sai token: báo lỗi tiếng Việt rõ ràng, không sập", errs and "Token không khớp" in errs[0], str(errs))
cfg["sheet"]["url"] = ""
ctx, ev = new_ctx()
jobs.run_all(cfg, ctx, "download")
errs = [e["msg"] for e in ev if e["type"] == "log" and e["level"] == "error"]
check("thiếu URL: báo lỗi rõ ràng", errs and "Chưa nhập URL" in errs[0], str(errs))

print()
print("TẤT CẢ ĐẠT" if not fails else f"CÓ {len(fails)} LỖI: {fails}")
sys.exit(1 if fails else 0)
