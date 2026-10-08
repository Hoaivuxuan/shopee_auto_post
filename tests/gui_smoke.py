"""Kiểm tra giao diện bằng màn hình ảo (Xvfb) + Sheet/Facebook giả, có chụp ảnh màn hình.
Chạy:  xvfb-run -a -s "-screen 0 1280x820x24" python3 tests/gui_smoke.py <thư mục ảnh>"""
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(OUT, exist_ok=True)

import requests  # noqa: E402
import tkinter.messagebox as mb  # noqa: E402
from shopeetool import config, jobs, paths  # noqa: E402

paths._DATA_DIR = tempfile.mkdtemp(prefix="sfb_gui_")
URL, TOKEN = "https://script.google.com/macros/s/FAKE/exec", "tok"
rows = []
popups = []
for name in ("showinfo", "showwarning", "showerror", "askyesno"):
    setattr(mb, name, lambda *a, _n=name, **k: (popups.append((_n, a)) or True))


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
        return Resp({"ok": True, "name": "Danh sách sản phẩm", "tab": "Sheet1", "rows": len(rows)})
    if a == "tab_init":
        return Resp({"ok": True, "existed": True})
    if a == "tab_set_header":
        return Resp({"ok": True})
    if a == "tab_list":
        return Resp({"ok": True, "values": [r[:b["ncols"]] for r in rows]})
    if a == "tab_update":
        keyof = lambda r: "|".join(rows[r][c - 1].strip() for c in b["key_cols"])
        h, row = b["hint"], -1
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
    if url.endswith("/videos"):
        if data["access_token"] == "BAD":
            return Resp({"error": {"message": "Invalid OAuth access token.", "code": 190}}, 400)
        return Resp({"id": "vid_" + url.split("/")[-2]})
    return Resp({"id": "c1"})


def fake_get(url, params=None, timeout=None, **kw):
    if url.endswith("/oauth/access_token"):
        return Resp({"access_token": "LONG", "expires_in": 5184000})
    if url.endswith("/me/accounts"):
        return Resp({"data": [{"id": "111", "name": "Tiện ích thông minh", "access_token": "EAAxxxxxxxxxxxxxxxxxxxxxxxx1"},
                              {"id": "222", "name": "Săn Sales xuyên lục địa", "access_token": "EAAxxxxxxxxxxxxxxxxxxxxxxxx2"}]})
    return Resp({"id": "111", "name": "Tiện ích thông minh"})


class FakeSession:
    def __init__(self, cfg, ctx):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def capture(self, url, wait):
        return ([], "Trang Shopee | https://shopee.vn/buyer/login") if "novideo" in url else (["https://cdn/a.mp4"], "")


def fake_download(url, dest, ctx):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(b"x" * 100)


requests.post, requests.get = fake_post, fake_get
jobs.ShopeeSession, jobs.download_file = FakeSession, fake_download

from shopeetool import gui  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  LỖI  ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


def shot(app, name):
    app.update_idletasks()
    app.update()
    time.sleep(0.4)
    app.update()
    path = os.path.join(OUT, name + ".png")
    subprocess.run(["import", "-window", "root", path], check=False)
    return path


def pump(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


app = gui.App()
app.geometry("1200x790+0+0")
pump(app, 0.8)
check("mở được giao diện, có 4 tab", len(app.nb.tabs()) == 4)

# --- cấu hình qua giao diện
app.v["sheet.url"].set(URL)
app.v["sheet.token"].set(TOKEN)
app.v["shopee.min_delay"].set("0")
app.v["shopee.max_delay"].set("0")
app.v["facebook.min_delay"].set("0")
app.v["facebook.max_delay"].set("0")
app.v["facebook.schedule_mode"].set("Nhờ Facebook hẹn giờ (máy tắt vẫn đăng)")
app.save_config()
saved = config.load()
check("lưu cấu hình ra file", saved["sheet"]["token"] == TOKEN and saved["facebook"]["schedule_mode"] == "facebook")

app.test_sheet()
pump(app, 1.0)
check("kiểm tra kết nối sheet báo thành công", "Kết nối thành công" in app.sheet_msg.cget("text"), app.sheet_msg.cget("text"))
app.gen_token()
check("tạo token ngẫu nhiên", len(app.v["sheet.token"].get()) >= 20)
app.v["sheet.token"].set(TOKEN)
app.copy_appscript()
clip = app.clipboard_get()
check("sao chép mã Apps Script có chèn token", f'const TOKEN = "{TOKEN}";' in clip and "__TOKEN__" not in clip)

app.fb_user_token.set("SHORT")
app.v["facebook.app_id"].set("123")
app.v["facebook.app_secret"].set("secret")
app.fb_fetch_pages()
pump(app, 1.0)
check("lấy Page từ token: 2 Page", len(app.cfg["pages"]) == 2, app.fb_msg.cget("text"))
app.cfg["pages"].append({"name": "Page Hỏng", "id": "333", "token": "BAD", "enabled": True})
app.refresh_pages_tree()
app.page_check()
pump(app, 1.0)
check("kiểm tra token Page: có kết quả cho cả 3 Page", len(app.fb_status) == 3 and all(v.startswith("OK") for v in app.fb_status.values()),
      str(app.fb_status))
app.pages_tree.selection_set("333")
app.page_toggle()
check("tắt một Page", [p for p in app.cfg["pages"] if p["id"] == "333"][0]["enabled"] is False)
app.pages_tree.selection_set("111")
shot_cfg_fb = None

# --- dữ liệu sheet
vdir = config.videos_dir(app.cfg)
os.makedirs(vdir, exist_ok=True)
now = datetime.now()
HDR = ["Link sản phẩm", "Trạng thái", "Thời gian", "File video", "Ghi chú", "Page", "Link affiliate", "Nội dung", "Tag",
       "Giờ đăng", "Trạng thái đăng", "Đã xử lý lúc", "ID bài đăng", "Ghi chú đăng"]
def R(link, pg="", aff="", txt="", tag="", when=""):
    return [link, "", "", "", "", pg, aff, txt, tag, when, "", "", "", ""]
rows[:] = [HDR[:],
           R("https://shopee.vn/may-say-i.1.1", "Tiện ích thông minh, Săn Sales xuyên lục địa", "https://s.shopee.vn/AAA", "Máy sấy gọn nhẹ", "#giadung #sale"),
           R("https://shopee.vn/novideo-i.2.2", "Tiện ích thông minh", "https://s.shopee.vn/BBB", "Sản phẩm không có video"),
           R("https://shopee.vn/man-chup-i.3.3", "Săn Sales xuyên lục địa", "https://s.shopee.vn/CCC", "Màn chụp tự bung",
             "mới", (now + timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")),
           R("https://shopee.vn/can-i.4.4", "Page Hỏng", "https://s.shopee.vn/DDD", "Cân tiểu ly")]

# --- chạy "Tải và đăng song song" thử trước (chạy thử)
app.v["run.mode"].set("download_post")
app.v["run.dry_run"].set(True)
app.start_run()
for _ in range(200):
    pump(app, 0.1)
    if not app.running:
        break
check("chạy thử kết thúc, không ghi vào sheet", not app.running and all(r[10] == "" for r in rows[1:]))
app.v["run.dry_run"].set(False)
popups.clear()

app.start_run()
check("nút Bắt đầu bị khóa, nút Dừng mở khi đang chạy", str(app.btn_start.cget("state")) == "disabled" and str(app.btn_stop.cget("state")) == "normal")
for _ in range(300):
    pump(app, 0.1)
    if not app.running:
        break
check("chạy thật kết thúc", not app.running)
check("tải: dòng 1,3,4 Thành công; dòng 2 Lỗi", [r[1] for r in rows[1:]] == ["Thành công", "Lỗi", "Thành công", "Thành công"], str([r[1] for r in rows[1:]]))
check("đăng: dòng 1 Thành công (2 Page)", rows[1][10] == "Thành công" and rows[1][12].count("::") == 2, str(rows[1][10:]))
check("đăng: dòng 3 hẹn giờ Facebook => Đã lên lịch", rows[3][10] == "Đã lên lịch", rows[3][10])
check("đăng: dòng 4 Page tắt => Lỗi có ghi chú", rows[4][10] == "Lỗi" and "đang bị tắt" in rows[4][13], rows[4][13])
check("có popup tổng kết có cảnh báo", any(n == "showwarning" for n, _ in popups), str(popups))
check("tab Cảnh báo & lỗi có mục", app.alert_count >= 2, str(app.alert_count))
check("bảng kết quả có dòng", len(app.res_tree.get_children()) >= 4)
check("bộ đếm cập nhật", app.stat_vars["dl_ok"].get() == "3" and app.stat_vars["post_sched"].get() == "1", str({k: v.get() for k, v in app.stat_vars.items()}))
shot(app, "01_chay_ket_qua")
app.rnb.select(1)
shot(app, "02_ket_qua_tung_dong")
app.rnb.select(2)
shot(app, "03_canh_bao_loi")

# --- các tab cấu hình
app.nb.select(app.tab_cfg)
for i, name in enumerate(("04_cau_hinh_sheet", "05_cau_hinh_shopee", "06_cau_hinh_facebook", "07_cau_hinh_chung")):
    app.cnb.select(i)
    app.refresh_status_labels()
    shot(app, name)

# --- hướng dẫn & hệ thống
app.nb.select(app.tab_help)
for i in range(3):
    app.show_doc(i)
    shot(app, f"0{8 + i}_huong_dan_{i + 1}")
    txt = app.doc_text.get("1.0", "end")
    check(f"tài liệu {i + 1} hiển thị nội dung", len(txt) > 500 and "Không tìm thấy tài liệu" not in txt)
app.nb.select(app.tab_sys)
app.refresh_sys()
shot(app, "11_he_thong")

# --- dừng giữa chừng
app.nb.select(app.tab_run)
rows[:] = [HDR[:]] + [R(f"https://shopee.vn/x-i.{i}.{i}", "Tiện ích thông minh", "https://s.shopee.vn/Z", "Bài", "") for i in range(5, 11)]
app.v["shopee.min_delay"].set("5"); app.v["shopee.max_delay"].set("5")
app.v["run.mode"].set("download")
popups.clear()
app.start_run()
pump(app, 1.5)
app.stop_run()
for _ in range(100):
    pump(app, 0.1)
    if not app.running:
        break
check("bấm Dừng: dừng nhanh, không kẹt 'Đang xử lý'", not app.running and all(r[1] != "Đang xử lý" for r in rows[1:]), str([r[1] for r in rows[1:]]))
check("popup 'Đã dừng'", any(n == "showinfo" and a and "Đã dừng" in str(a) for n, a in popups), str(popups))

# --- thiếu cấu hình: cảnh báo, không chạy
app.v["sheet.token"].set("")
popups.clear()
app.start_run()
check("thiếu token: hiện cảnh báo và không chạy", not app.running and any(n == "showwarning" for n, _ in popups))

app.v["sheet.token"].set(TOKEN)
app.save_config()
print()
print("TẤT CẢ ĐẠT" if not fails else f"CÓ {len(fails)} LỖI: {fails}")
print("Ảnh chụp:", OUT)
app.destroy()
sys.exit(1 if fails else 0)
