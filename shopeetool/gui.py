"""Giao diện chính (Tkinter) của Shopee → Facebook Tool."""
import copy
import os
import queue
import secrets
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from . import APP_TITLE, VERSION, config as cfgmod, facebook as fb, mdview, shopee, syscheck
from .appscript import CODE as APPSCRIPT_CODE
from .jobs import MODES, make_client, run_all
from .logger import Cancelled, RunContext, mask
from .paths import data_dir, logs_dir, resource_path
from .platforms import (BROWSER_LABELS, BROWSER_MISSING_HINT, DEFAULT_BROWSER, MONO_FONTS, UI_FONTS,
                        enable_dpi_awareness, open_path)

SCHEDULE_LABELS = {"Tự đăng khi đến giờ (máy phải bật)": "local",
                   "Nhờ Facebook hẹn giờ (máy tắt vẫn đăng)": "facebook"}
DOCS = [("1. Hướng dẫn dùng bằng Command", "HUONG_DAN_COMMAND.md"),
        ("2. Hướng dẫn sử dụng (giao diện)", "HUONG_DAN_SU_DUNG.md"),
        ("3. Kết nối Google Sheet & Facebook Page", "HUONG_DAN_KET_NOI.md"),
        ("4. Cài đặt và chạy trên Ubuntu", "HUONG_DAN_UBUNTU.md")]
STAT_LABELS = [("dl_ok", "Tải thành công"), ("dl_fail", "Tải lỗi"),
               ("post_ok", "Đăng thành công"), ("post_sched", "Đã lên lịch"),
               ("post_part", "Đăng một phần"), ("post_fail", "Đăng lỗi"),
               ("post_wait", "Chờ đến giờ đăng")]
# khóa -> (mặc định, nhỏ nhất)
INT_FIELDS = {
    "shopee.wait_seconds": (60, 10), "shopee.limit": (10, 1), "shopee.min_delay": (30, 0),
    "shopee.max_delay": (90, 0), "facebook.limit": (5, 1), "facebook.min_delay": (10, 0),
    "facebook.max_delay": (30, 0), "run.auto_minutes": (30, 1),
}
OK_STATUS = ("Thành công", "Đã lên lịch", "Hợp lệ")


def label_of(mapping, code):
    for k, v in mapping.items():
        if v == code:
            return k
    return next(iter(mapping))


class AddPageDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Thêm Page thủ công")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        self.vars = {k: tk.StringVar() for k in ("name", "id", "token")}
        f = ttk.Frame(self, padding=14)
        f.pack()
        for r, (k, label) in enumerate((("name", "Tên Page (tên ngắn dùng trong sheet)"),
                                        ("id", "Page ID"), ("token", "Page Access Token"))):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            ttk.Entry(f, textvariable=self.vars[k], width=52,
                      show="•" if k == "token" else "").grid(row=r, column=1, pady=4)
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(b, text="Lưu", command=self.ok).pack(side="left", padx=4)
        ttk.Button(b, text="Hủy", command=self.destroy).pack(side="left")
        self.grab_set()
        self.wait_visibility()

    def ok(self):
        r = {k: v.get().strip() for k, v in self.vars.items()}
        if not all(r.values()):
            messagebox.showwarning("Thiếu thông tin", "Cần nhập đủ Tên, Page ID và Page Access Token.", parent=self)
            return
        self.result = r
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  {VERSION}")
        self.geometry("1200x790")
        self.minsize(1000, 660)
        self.cfg = cfgmod.load()
        self.q = queue.Queue()
        self.ctx = None
        self.running = False
        self.next_run_at = None
        self.last_auto = False
        self.alert_count = 0
        self.fb_status = {}
        self.dirty = False
        self._style()
        self._make_vars()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.report_callback_exception = self._on_tk_error
        self.after(100, self._poll)
        self.after(1000, self._tick)
        self.refresh_pages_tree()
        self.refresh_status_labels()
        self.log_line("info", f"{APP_TITLE} {VERSION}. Dữ liệu lưu tại: {data_dir()}")
        if not (self.cfg["sheet"]["url"] and self.cfg["sheet"]["token"]):
            self.log_line("warn", "Chưa cấu hình Google Sheet: vào tab Cấu hình > Google Sheet (xem tab Hướng dẫn).")

    # ------------------------------------------------------------------ giao diện chung
    def _style(self):
        st = ttk.Style(self)
        names = st.theme_names()
        st.theme_use("vista" if "vista" in names else ("clam" if "clam" in names else st.theme_use()))
        fams = set(tkfont.families(self))
        fam = next((f for f in UI_FONTS if f in fams), "TkDefaultFont")
        self.mono_font = next((f for f in MONO_FONTS if f in fams), None)
        self.base_font = (fam, 10)
        self.option_add("*Font", self.base_font)
        st.configure("TNotebook.Tab", padding=(16, 7))
        st.configure("Hint.TLabel", foreground="#666666")
        st.configure("Ok.TLabel", foreground="#2e7d32")
        st.configure("Err.TLabel", foreground="#c62828")
        st.configure("Warn.TLabel", foreground="#e65100")
        st.configure("Big.TLabel", font=(fam, 16, "bold"))
        st.configure("Count.TLabel", font=(fam, 13, "bold"))
        st.configure("Treeview", rowheight=24)

    def _make_vars(self):
        c = self.cfg
        S = lambda v: tk.StringVar(value=str(v))
        B = lambda v: tk.BooleanVar(value=bool(v))
        self.v = {
            "sheet.url": S(c["sheet"]["url"]), "sheet.token": S(c["sheet"]["token"]),
            "sheet.tab": S(c["sheet"]["tab"]),
            "shopee.videos_dir": S(c["shopee"]["videos_dir"] or cfgmod.default_videos_dir()),
            "shopee.browser": S(label_of(BROWSER_LABELS, c["shopee"]["browser"])),
            "shopee.show_browser": B(c["shopee"]["show_browser"]),
            "shopee.wait_seconds": S(c["shopee"]["wait_seconds"]), "shopee.limit": S(c["shopee"]["limit"]),
            "shopee.min_delay": S(c["shopee"]["min_delay"]), "shopee.max_delay": S(c["shopee"]["max_delay"]),
            "facebook.app_id": S(c["facebook"]["app_id"]), "facebook.app_secret": S(c["facebook"]["app_secret"]),
            "facebook.api_version": S(c["facebook"]["api_version"]),
            "facebook.limit": S(c["facebook"]["limit"]),
            "facebook.min_delay": S(c["facebook"]["min_delay"]), "facebook.max_delay": S(c["facebook"]["max_delay"]),
            "facebook.schedule_mode": S(label_of(SCHEDULE_LABELS, c["facebook"]["schedule_mode"])),
            "facebook.link_in_comment": B(c["facebook"]["link_in_comment"]),
            "facebook.link_prefix": S(c["facebook"]["link_prefix"]),
            "run.mode": S(c["run"]["mode"]), "run.dry_run": B(c["run"]["dry_run"]),
            "run.retry": B(c["run"]["retry"]), "run.auto": B(c["run"]["auto"]),
            "run.auto_minutes": S(c["run"]["auto_minutes"]),
        }
        self.fb_user_token = tk.StringVar()
        self.fb_token_is_long = tk.BooleanVar(value=False)
        self.stat_vars = {k: tk.StringVar(value="0") for k, _ in STAT_LABELS}
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.auto_info = tk.StringVar(value="")
        self.saved_var = tk.StringVar(value="")
        for var in self.v.values():
            var.trace_add("write", lambda *_: setattr(self, "dirty", True))

    def collect_cfg(self):
        for key, var in self.v.items():
            sec, k = key.split(".")
            val = var.get()
            if key in INT_FIELDS:
                val = cfgmod.to_int(val, *INT_FIELDS[key])
            elif isinstance(var, tk.BooleanVar):
                val = bool(val)
            elif key == "shopee.browser":
                val = BROWSER_LABELS.get(val, DEFAULT_BROWSER)
            elif key == "facebook.schedule_mode":
                val = SCHEDULE_LABELS.get(val, "local")
            elif key == "facebook.link_prefix":
                val = str(val)
            elif key == "shopee.videos_dir":
                val = str(val).strip()
                if os.path.normpath(val) == os.path.normpath(cfgmod.default_videos_dir()):
                    val = ""
            else:
                val = str(val).strip()
            self.cfg[sec][k] = val
        for sec in ("shopee", "facebook"):
            if self.cfg[sec]["max_delay"] < self.cfg[sec]["min_delay"]:
                self.cfg[sec]["max_delay"] = self.cfg[sec]["min_delay"]
                self.v[f"{sec}.max_delay"].set(self.cfg[sec]["max_delay"])
        for key in INT_FIELDS:   # hiển thị lại giá trị đã chuẩn hóa
            sec, k = key.split(".")
            if self.v[key].get() != str(self.cfg[sec][k]):
                self.v[key].set(str(self.cfg[sec][k]))

    def save_config(self, quiet=False):
        self.collect_cfg()
        try:
            cfgmod.save(self.cfg)
        except OSError as e:
            messagebox.showerror("Không lưu được cấu hình", str(e))
            return False
        self.dirty = False
        self.saved_var.set(f"Đã lưu lúc {datetime.now():%H:%M:%S}")
        if not quiet:
            self.status_var.set("Đã lưu cấu hình.")
        return True

    def bg(self, func, on_ok=None, on_err=None):
        """Chạy func ở luồng nền; kết quả được chuyển về luồng giao diện."""
        def work():
            try:
                res = func()
            except Exception as e:  # noqa: BLE001
                self.q.put({"type": "call", "fn": lambda e=e: (on_err or self._default_err)(e)})
            else:
                if on_ok:
                    self.q.put({"type": "call", "fn": lambda: on_ok(res)})
        threading.Thread(target=work, daemon=True).start()

    def _default_err(self, e):
        messagebox.showerror("Lỗi", self.explain(e))

    @staticmethod
    def explain(e):
        if isinstance(e, fb.FBError):
            h = fb.hint_for(e)
            return f"Facebook báo lỗi {e.code}: {e}" + (f"\n\n{h}" if h else "")
        return mask(str(e))

    def clip(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _on_tk_error(self, exc, val, tb):
        msg = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(logs_dir(), "gui_errors.log"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{mask(msg)}\n")
        except OSError:
            pass
        self.log_line("error", f"Lỗi giao diện: {val}")

    # ------------------------------------------------------------------ dựng giao diện
    def _build(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.tab_run = ttk.Frame(self.nb)
        self.tab_cfg = ttk.Frame(self.nb)
        self.tab_help = ttk.Frame(self.nb)
        self.tab_sys = ttk.Frame(self.nb)
        self.nb.add(self.tab_run, text="  Chạy  ")
        self.nb.add(self.tab_cfg, text="  Cấu hình  ")
        self.nb.add(self.tab_help, text="  Hướng dẫn  ")
        self.nb.add(self.tab_sys, text="  Hệ thống  ")
        self._build_run(self.tab_run)
        self._build_cfg(self.tab_cfg)
        self._build_help(self.tab_help)
        self._build_sys(self.tab_sys)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=180)
        self.progress.pack(side="right")
        ttk.Label(bar, textvariable=self.saved_var, style="Hint.TLabel").pack(side="right", padx=14)

    # ----- tab Chạy
    def _build_run(self, tab):
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = ttk.Frame(tab, padding=10)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(tab, padding=(0, 10, 10, 10))
        right.grid(row=0, column=1, sticky="nsew")

        box = ttk.LabelFrame(left, text=" Chức năng ", padding=10)
        box.pack(fill="x")
        for code, label in MODES.items():
            ttk.Radiobutton(box, text=label, value=code, variable=self.v["run.mode"]).pack(anchor="w", pady=2)

        opt = ttk.LabelFrame(left, text=" Tùy chọn lượt chạy ", padding=10)
        opt.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(opt, text="Chạy thử (không tải/đăng thật)", variable=self.v["run.dry_run"]).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="Chạy lại các dòng Lỗi / Một phần", variable=self.v["run.retry"]).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))
        ttk.Label(opt, text="Tải tối đa (link):").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(opt, from_=1, to=500, width=6, textvariable=self.v["shopee.limit"]).grid(row=2, column=1, sticky="w")
        ttk.Label(opt, text="Đăng tối đa (dòng):").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Spinbox(opt, from_=1, to=500, width=6, textvariable=self.v["facebook.limit"]).grid(
            row=3, column=1, sticky="w", pady=(4, 0))

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=12)
        self.btn_start = tk.Button(btns, text="▶  BẮT ĐẦU", bg="#2e7d32", fg="white", activebackground="#1b5e20",
                                   activeforeground="white", font=(self.base_font[0], 12, "bold"), relief="flat",
                                   padx=14, pady=8, command=lambda: self.start_run(auto=False))
        self.btn_start.pack(fill="x")
        self.btn_stop = tk.Button(btns, text="■  DỪNG", bg="#c62828", fg="white", activebackground="#8e0000",
                                  activeforeground="white", font=(self.base_font[0], 11, "bold"), relief="flat",
                                  padx=14, pady=6, state="disabled", command=self.stop_run)
        self.btn_stop.pack(fill="x", pady=(6, 0))

        auto = ttk.LabelFrame(left, text=" Tự động lặp lại ", padding=10)
        auto.pack(fill="x")
        row = ttk.Frame(auto)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Tự chạy lại mỗi", variable=self.v["run.auto"],
                        command=self._on_auto_toggle).pack(side="left")
        ttk.Spinbox(row, from_=1, to=1440, width=5, textvariable=self.v["run.auto_minutes"]).pack(side="left", padx=4)
        ttk.Label(row, text="phút").pack(side="left")
        ttk.Label(auto, textvariable=self.auto_info, style="Hint.TLabel", wraplength=230).pack(anchor="w", pady=(6, 0))

        cnt = ttk.LabelFrame(left, text=" Kết quả lượt chạy ", padding=10)
        cnt.pack(fill="x", pady=(10, 0))
        for r, (k, label) in enumerate(STAT_LABELS):
            ttk.Label(cnt, text=label).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Label(cnt, textvariable=self.stat_vars[k], style="Count.TLabel", width=5, anchor="e").grid(
                row=r, column=1, sticky="e", padx=(14, 0))

        # ---- bên phải: nhật ký / kết quả / cảnh báo
        self.rnb = ttk.Notebook(right)
        self.rnb.pack(fill="both", expand=True)
        log_tab, res_tab, alert_tab = ttk.Frame(self.rnb), ttk.Frame(self.rnb), ttk.Frame(self.rnb)
        self.rnb.add(log_tab, text="  Nhật ký  ")
        self.rnb.add(res_tab, text="  Kết quả từng dòng  ")
        self.rnb.add(alert_tab, text="  Cảnh báo & lỗi (0)  ")
        self.alert_tab = alert_tab

        tb = ttk.Frame(log_tab)
        tb.pack(fill="x", pady=(6, 4), padx=6)
        ttk.Button(tb, text="Xóa nhật ký", command=self.clear_log).pack(side="left")
        ttk.Button(tb, text="Lưu ra file...", command=self.save_log).pack(side="left", padx=6)
        ttk.Button(tb, text="Mở thư mục nhật ký", command=lambda: self.open_path(logs_dir())).pack(side="left")
        ttk.Button(tb, text="Mở thư mục video", command=self.open_videos).pack(side="left", padx=6)
        wrap = ttk.Frame(log_tab)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.log_text = tk.Text(wrap, wrap="word", state="disabled", font=(self.mono_font, 10) if self.mono_font else None,
                                background="#fcfcfc", relief="solid", borderwidth=1)
        sb = ttk.Scrollbar(wrap, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        for tag, color in (("info", "#222222"), ("ok", "#1b5e20"),
                           ("warn", "#e65100"), ("error", "#b71c1c"), ("time", "#888888")):
            self.log_text.tag_configure(tag, foreground=color)
        self.log_text.tag_configure("error", font=(self.base_font[0], 10, "bold"))

        self.res_tree = self._make_tree(res_tab, ("time", "job", "row", "status", "note"),
                                        ("Giờ", "Việc", "Dòng", "Kết quả", "Ghi chú"), (70, 90, 55, 110, 700))
        self.alert_tree = self._make_tree(alert_tab, ("time", "level", "msg"), ("Giờ", "Mức", "Nội dung"),
                                          (70, 80, 900))
        for tree in (self.res_tree, self.alert_tree):
            tree.tag_configure("ok", foreground="#1b5e20")
            tree.tag_configure("warn", foreground="#e65100")
            tree.tag_configure("error", foreground="#b71c1c")
        self.alert_tree.bind("<Double-1>", self._show_alert)
        ab = ttk.Frame(alert_tab)
        ab.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(ab, text="Bấm đúp vào một dòng để xem đầy đủ.", style="Hint.TLabel").pack(side="left")
        ttk.Button(ab, text="Xóa danh sách", command=self.clear_alerts).pack(side="right")
        ttk.Button(ab, text="Sao chép tất cả", command=self.copy_alerts).pack(side="right", padx=6)

    def _make_tree(self, parent, cols, heads, widths):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=6, pady=6)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths, strict=False):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w", stretch=(c == cols[-1]))
        sb = ttk.Scrollbar(wrap, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    # ----- tab Cấu hình
    def _build_cfg(self, tab):
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)
        self.cnb = ttk.Notebook(tab)
        self.cnb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        f_sheet, f_shopee, f_fb, f_gen = (ttk.Frame(self.cnb, padding=14) for _ in range(4))
        self.cnb.add(f_sheet, text="  1. Google Sheet  ")
        self.cnb.add(f_shopee, text="  2. Shopee  ")
        self.cnb.add(f_fb, text="  3. Facebook  ")
        self.cnb.add(f_gen, text="  4. Chung  ")
        self._cfg_sheet(f_sheet)
        self._cfg_shopee(f_shopee)
        self._cfg_fb(f_fb)
        self._cfg_general(f_gen)
        bottom = ttk.Frame(tab)
        bottom.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(bottom, text="Lưu cấu hình", command=self.save_config).pack(side="right")
        ttk.Label(bottom, text="Cấu hình cũng được tự lưu khi bấm 'Bắt đầu' và khi đóng chương trình.",
                  style="Hint.TLabel").pack(side="left")

    def _entry(self, parent, r, label, key, width=50, show=None, hint=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=4)
        e = ttk.Entry(parent, textvariable=self.v[key], width=width, show=show or "")
        e.grid(row=r, column=1, sticky="ew", pady=4)
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(row=r, column=2, sticky="w", padx=8)
        return e

    def _secret_toggle(self, parent, r, entry):
        v = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Hiện", variable=v,
                        command=lambda: entry.configure(show="" if v.get() else "•")).grid(row=r, column=2, sticky="w", padx=8)

    def _cfg_sheet(self, f):
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Kết nối Google Sheet (miễn phí, qua Google Apps Script)", style="Big.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Chưa có? Làm theo tab Hướng dẫn > '3. Kết nối Google Sheet & Facebook Page'. "
                          "Tóm tắt: tạo token, bấm 'Sao chép mã Apps Script', dán vào Apps Script của sheet, "
                          "triển khai Web app, rồi dán URL vào đây.",
                  style="Hint.TLabel", wraplength=860, justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._entry(f, 2, "Web app URL (…/exec)", "sheet.url")
        e = self._entry(f, 3, "Token (mật khẩu tự đặt)", "sheet.token", show="•")
        self._secret_toggle(f, 3, e)
        self._entry(f, 4, "Tên tab (tùy chọn)", "sheet.tab", hint="để trống = tab đầu tiên")
        bar = ttk.Frame(f)
        bar.grid(row=5, column=0, columnspan=3, sticky="w", pady=14)
        ttk.Button(bar, text="Tạo token ngẫu nhiên", command=self.gen_token).pack(side="left")
        ttk.Button(bar, text="Sao chép mã Apps Script", command=self.copy_appscript).pack(side="left", padx=6)
        ttk.Button(bar, text="Kiểm tra kết nối", command=self.test_sheet).pack(side="left")
        ttk.Button(bar, text="Tạo tiêu đề cột trong sheet", command=self.init_sheet).pack(side="left", padx=6)
        ttk.Button(bar, text="Mở hướng dẫn kết nối", command=lambda: self.show_doc(2)).pack(side="left")
        self.sheet_msg = ttk.Label(f, text="", wraplength=860, justify="left")
        self.sheet_msg.grid(row=6, column=0, columnspan=3, sticky="w")

    def _cfg_shopee(self, f):
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Tải video từ Shopee", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(f, text="Thư mục lưu video").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.v["shopee.videos_dir"]).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(f, text="Chọn...", command=self.pick_videos_dir).grid(row=1, column=2, padx=8)
        ttk.Label(f, text="Trình duyệt dùng để tải").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(f, textvariable=self.v["shopee.browser"], values=list(BROWSER_LABELS), state="readonly",
                     width=34).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Checkbutton(f, text="Hiện cửa sổ trình duyệt khi tải (bỏ chọn = chạy ẩn, thu nhỏ ngoài màn hình)",
                        variable=self.v["shopee.show_browser"]).grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        nums = ttk.Frame(f)
        nums.grid(row=4, column=0, columnspan=3, sticky="w", pady=6)
        for c, (label, key, hi) in enumerate((("Chờ video tối đa (giây)", "shopee.wait_seconds", 600),
                                              ("Số link tối đa mỗi lần", "shopee.limit", 500),
                                              ("Nghỉ giữa 2 link: từ (giây)", "shopee.min_delay", 3600),
                                              ("đến (giây)", "shopee.max_delay", 3600))):
            ttk.Label(nums, text=label).grid(row=0, column=c * 2, sticky="w", padx=(0 if c == 0 else 16, 6))
            ttk.Spinbox(nums, from_=0, to=hi, width=6, textvariable=self.v[key]).grid(row=0, column=c * 2 + 1)
        box = ttk.LabelFrame(f, text=" Phiên đăng nhập Shopee ", padding=10)
        box.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        self.shopee_state_lbl = ttk.Label(box, text="")
        self.shopee_state_lbl.grid(row=0, column=0, sticky="w", columnspan=3)
        ttk.Button(box, text="Đăng nhập Shopee", command=self.shopee_login).grid(row=1, column=0, pady=8, sticky="w")
        ttk.Button(box, text="Xóa phiên đã lưu", command=self.shopee_clear).grid(row=1, column=1, padx=8, sticky="w")
        ttk.Label(box, text="Bấm 'Đăng nhập Shopee' → đăng nhập trong cửa sổ trình duyệt hiện ra → bấm 'Tôi đã đăng nhập xong'.\n"
                            "Phiên được lưu trên máy này. Nếu Shopee yêu cầu đăng nhập lại, làm lại bước này. "
                            "Nên dùng tài khoản phụ.", style="Hint.TLabel", justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w")
        self.env_lbl = ttk.Label(f, text="", wraplength=860, justify="left")
        self.env_lbl.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _cfg_fb(self, f):
        f.columnconfigure(0, weight=0)
        f.columnconfigure(1, weight=1)
        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        app = ttk.LabelFrame(left, text=" A. Ứng dụng Facebook (Meta) ", padding=10)
        app.pack(fill="x")
        app.columnconfigure(1, weight=1)
        self._entry(app, 0, "App ID", "facebook.app_id", width=26)
        e = self._entry(app, 1, "App Secret", "facebook.app_secret", width=26, show="•")
        self._secret_toggle(app, 1, e)
        self._entry(app, 2, "Phiên bản API", "facebook.api_version", width=10)

        get = ttk.LabelFrame(left, text=" B. Lấy danh sách Page ", padding=10)
        get.pack(fill="x", pady=(10, 0))
        get.columnconfigure(0, weight=1)
        ttk.Label(get, text="Dán token người dùng (từ Graph API Explorer):").grid(row=0, column=0, sticky="w")
        ttk.Entry(get, textvariable=self.fb_user_token, show="•", width=34).grid(row=1, column=0, sticky="ew", pady=3)
        ttk.Checkbutton(get, text="Token này đã là token dài hạn (bỏ qua bước đổi)",
                        variable=self.fb_token_is_long).grid(row=2, column=0, sticky="w")
        ttk.Button(get, text="Lấy Page", command=self.fb_fetch_pages).grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.fb_msg = ttk.Label(get, text="", wraplength=300, justify="left")
        self.fb_msg.grid(row=4, column=0, sticky="w", pady=(6, 0))

        post = ttk.LabelFrame(left, text=" C. Tùy chọn đăng bài ", padding=10)
        post.pack(fill="x", pady=(10, 0))
        post.columnconfigure(1, weight=1)
        ttk.Label(post, text="Hẹn giờ").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(post, textvariable=self.v["facebook.schedule_mode"], values=list(SCHEDULE_LABELS),
                     state="readonly", width=32).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Checkbutton(post, text="Đưa link vào bình luận đầu tiên (không áp dụng cho bài hẹn giờ)",
                        variable=self.v["facebook.link_in_comment"]).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(post, text="Chữ đứng trước link").grid(row=2, column=0, sticky="w", pady=3, padx=(0, 10))
        ttk.Entry(post, textvariable=self.v["facebook.link_prefix"], width=20).grid(row=2, column=1, sticky="w")
        n = ttk.Frame(post)
        n.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(n, text="Tối đa").grid(row=0, column=0)
        ttk.Spinbox(n, from_=1, to=500, width=5, textvariable=self.v["facebook.limit"]).grid(row=0, column=1, padx=4)
        ttk.Label(n, text="dòng/lần. Nghỉ giữa 2 bài:").grid(row=0, column=2)
        ttk.Spinbox(n, from_=0, to=3600, width=5, textvariable=self.v["facebook.min_delay"]).grid(row=0, column=3, padx=4)
        ttk.Label(n, text="-").grid(row=0, column=4)
        ttk.Spinbox(n, from_=0, to=3600, width=5, textvariable=self.v["facebook.max_delay"]).grid(row=0, column=5, padx=4)
        ttk.Label(n, text="giây").grid(row=0, column=6)

        ttk.Label(right, text="D. Danh sách Page", style="Big.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        wrap = ttk.Frame(right)
        wrap.grid(row=1, column=0, sticky="nsew")
        self.pages_tree = ttk.Treeview(wrap, columns=("on", "name", "id", "token", "check"), show="headings",
                                       selectmode="extended")
        for c, h, w in (("on", "Bật", 42), ("name", "Tên Page", 170), ("id", "Page ID", 125),
                        ("token", "Token", 100), ("check", "Kiểm tra", 150)):
            self.pages_tree.heading(c, text=h)
            self.pages_tree.column(c, width=w, anchor="w", stretch=(c == "check"))
        sb = ttk.Scrollbar(wrap, command=self.pages_tree.yview)
        self.pages_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.pages_tree.pack(side="left", fill="both", expand=True)
        self.pages_tree.tag_configure("off", foreground="#999999")
        self.pages_tree.tag_configure("bad", foreground="#b71c1c")
        self.pages_tree.tag_configure("good", foreground="#1b5e20")
        pb = ttk.Frame(right)
        pb.grid(row=2, column=0, sticky="w", pady=8)
        for text, cmd in (("Thêm thủ công", self.page_add), ("Đổi tên", self.page_rename),
                          ("Bật/Tắt", self.page_toggle), ("Xóa", self.page_delete),
                          ("Kiểm tra", self.page_check)):
            ttk.Button(pb, text=text, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Label(right, text="Tên Page ở cột F của sheet phải khớp với cột 'Tên' ở đây (hoặc dùng Page ID). "
                              "Bạn có thể đổi thành tên ngắn không dấu, ví dụ 'meo', 'tienich'.",
                  style="Hint.TLabel", wraplength=520, justify="left").grid(row=3, column=0, sticky="w")

    def _cfg_general(self, f):
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Dữ liệu & sao lưu", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(f, text="Thư mục dữ liệu").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(f, text=data_dir()).grid(row=1, column=1, sticky="w")
        bar = ttk.Frame(f)
        bar.grid(row=2, column=0, columnspan=3, sticky="w", pady=10)
        ttk.Button(bar, text="Mở thư mục dữ liệu", command=lambda: self.open_path(data_dir())).pack(side="left")
        ttk.Button(bar, text="Xuất cấu hình...", command=self.export_cfg).pack(side="left", padx=6)
        ttk.Button(bar, text="Nhập cấu hình...", command=self.import_cfg).pack(side="left")
        ttk.Label(f, text="Lưu ý: file cấu hình xuất ra CHỨA token và App Secret. Chỉ chép sang máy của bạn, không gửi cho người khác.\n"
                          "Muốn chuyển sang máy khác: chép cả thư mục chương trình (gồm thư mục 'data'), hoặc dùng Xuất/Nhập cấu hình "
                          "(phiên đăng nhập Shopee thì cần đăng nhập lại trên máy mới).",
                  style="Hint.TLabel", wraplength=860, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(f, text=f"{APP_TITLE} {VERSION}", style="Hint.TLabel").grid(row=4, column=0, columnspan=3, sticky="w")

    # ----- tab Hướng dẫn
    def _build_help(self, tab):
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        left = ttk.Frame(tab, padding=10)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Label(left, text="Tài liệu", style="Big.TLabel").pack(anchor="w", pady=(0, 6))
        self.doc_list = tk.Listbox(left, width=38, height=8, exportselection=False, activestyle="none",
                                   font=self.base_font, selectbackground="#1565c0")
        for title, _ in DOCS:
            self.doc_list.insert("end", title)
        self.doc_list.pack(fill="x")
        self.doc_list.bind("<<ListboxSelect>>", lambda e: self._doc_selected())
        ttk.Button(left, text="Mở thư mục tài liệu", command=lambda: self.open_path(resource_path("docs"))).pack(
            fill="x", pady=(10, 0))
        ttk.Button(left, text="Lưu bản sao tài liệu này...", command=self.save_doc_copy).pack(fill="x", pady=(6, 0))
        right = ttk.Frame(tab, padding=(0, 10, 10, 10))
        right.grid(row=0, column=1, sticky="nsew")
        self.doc_text = tk.Text(right, wrap="word", state="disabled", relief="solid", borderwidth=1,
                                padx=14, pady=10, background="#ffffff")
        sb = ttk.Scrollbar(right, command=self.doc_text.yview)
        self.doc_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.doc_text.pack(side="left", fill="both", expand=True)
        mdview.setup_tags(self.doc_text)
        self.show_doc(1, switch=False)

    def show_doc(self, index, switch=True):
        self.doc_list.selection_clear(0, "end")
        self.doc_list.selection_set(index)
        self.doc_list.activate(index)
        self._doc_selected()
        if switch:
            self.nb.select(self.tab_help)

    def _doc_path(self):
        sel = self.doc_list.curselection()
        idx = sel[0] if sel else 1
        return os.path.join(resource_path("docs"), DOCS[idx][1])

    def _doc_selected(self):
        path = self._doc_path()
        try:
            with open(path, encoding="utf-8") as f:
                mdview.render(self.doc_text, f.read())
        except OSError:
            mdview.render(self.doc_text, f"# Không tìm thấy tài liệu\n\nFile `{path}` không tồn tại.")

    def save_doc_copy(self):
        src = self._doc_path()
        dest = filedialog.asksaveasfilename(defaultextension=".md", initialfile=os.path.basename(src),
                                            filetypes=[("Markdown", "*.md"), ("Tất cả", "*.*")])
        if dest:
            try:
                with open(src, encoding="utf-8") as f, open(dest, "w", encoding="utf-8") as g:
                    g.write(f.read())
            except OSError as e:
                messagebox.showerror("Không lưu được", str(e))

    # ----- tab Hệ thống
    def _build_sys(self, tab):
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        bar = ttk.Frame(tab, padding=10)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Kiểm tra hệ thống", style="Big.TLabel").pack(side="left")
        ttk.Button(bar, text="Sao chép báo cáo hỗ trợ", command=self.copy_report).pack(side="right")
        ttk.Button(bar, text="Kiểm tra lại", command=self.refresh_sys).pack(side="right", padx=6)
        wrap = ttk.Frame(tab, padding=(10, 0, 10, 10))
        wrap.grid(row=1, column=0, sticky="nsew")
        self.sys_tree = ttk.Treeview(wrap, columns=("st", "item", "detail"), show="headings")
        for c, h, w in (("st", "Trạng thái", 90), ("item", "Mục", 280), ("detail", "Chi tiết", 700)):
            self.sys_tree.heading(c, text=h)
            self.sys_tree.column(c, width=w, anchor="w", stretch=(c == "detail"))
        self.sys_tree.pack(fill="both", expand=True)
        self.sys_tree.tag_configure("ok", foreground="#1b5e20")
        self.sys_tree.tag_configure("warn", foreground="#e65100")
        self.sys_tree.tag_configure("error", foreground="#b71c1c")
        self.refresh_sys()

    def refresh_sys(self):
        self.collect_cfg()
        self.sys_tree.delete(*self.sys_tree.get_children())
        names = {"ok": "OK", "warn": "Cảnh báo", "error": "Lỗi"}
        for name, st, detail in syscheck.check_all(self.cfg):
            self.sys_tree.insert("", "end", values=(names[st], name, detail), tags=(st,))

    def copy_report(self):
        self.collect_cfg()
        self.clip(syscheck.support_report(self.cfg))
        messagebox.showinfo("Đã sao chép", "Báo cáo (đã che thông tin bí mật) đã được sao chép. Bạn có thể dán để gửi hỗ trợ.")

    # ------------------------------------------------------------------ nhật ký / kết quả
    def log_line(self, level, msg, ts=None):
        ts = ts or datetime.now().strftime("%H:%M:%S")
        t = self.log_text
        t.configure(state="normal")
        t.insert("end", f"{ts}  ", "time")
        t.insert("end", msg + "\n", level)
        if int(t.index("end-1c").split(".")[0]) > 4000:
            t.delete("1.0", "600.0")
        t.configure(state="disabled")
        t.see("end")
        if level in ("warn", "error"):
            self.alert_count += 1
            self.alert_tree.insert("", 0, values=(ts, "Lỗi" if level == "error" else "Cảnh báo", msg), tags=(level,))
            self.rnb.tab(self.alert_tab, text=f"  Cảnh báo & lỗi ({self.alert_count})  ")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def save_log(self):
        dest = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"nhat_ky_{datetime.now():%Y%m%d_%H%M}.txt")
        if dest:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(self.log_text.get("1.0", "end"))

    def clear_alerts(self):
        self.alert_tree.delete(*self.alert_tree.get_children())
        self.alert_count = 0
        self.rnb.tab(self.alert_tab, text="  Cảnh báo & lỗi (0)  ")

    def copy_alerts(self):
        lines = [" | ".join(self.alert_tree.item(i, "values")) for i in self.alert_tree.get_children()]
        self.clip("\n".join(lines))

    def _show_alert(self, _evt):
        sel = self.alert_tree.selection()
        if sel:
            vals = self.alert_tree.item(sel[0], "values")
            messagebox.showinfo(f"{vals[1]} lúc {vals[0]}", vals[2])

    def _add_result(self, ev):
        status = ev["status"]
        tag = "ok" if status in OK_STATUS else ("warn" if status == "Một phần" else "error")
        self.res_tree.insert("", 0, values=(ev["time"], ev["job"], ev["row"], status, ev["note"]), tags=(tag,))
        kids = self.res_tree.get_children()
        if len(kids) > 600:
            self.res_tree.delete(*kids[500:])

    # ------------------------------------------------------------------ vòng lặp sự kiện
    def _poll(self):
        try:
            while True:
                ev = self.q.get_nowait()
                t = ev["type"]
                if t == "log":
                    self.log_line(ev["level"], ev["msg"], ev["time"])
                elif t == "result":
                    self._add_result(ev)
                elif t == "stats":
                    for k, var in self.stat_vars.items():
                        var.set(str(ev["stats"].get(k, 0)))
                elif t == "done":
                    self._on_done(ev)
                elif t == "call":
                    ev["fn"]()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _tick(self):
        if self.v["run.auto"].get() and not self.running and self.next_run_at:
            remain = int(self.next_run_at - time.time())
            if remain <= 0:
                self.start_run(auto=True)
            else:
                self.auto_info.set(f"Lần chạy tự động tiếp theo sau {remain // 60:02d}:{remain % 60:02d}")
        elif self.running:
            self.auto_info.set("Đang chạy..." if self.v["run.auto"].get() else "")
        elif not self.v["run.auto"].get():
            self.auto_info.set("Tự động đang tắt.")
        self.after(1000, self._tick)

    # ------------------------------------------------------------------ chạy / dừng
    def preflight(self, mode, dry, auto):
        c = self.cfg
        if not c["sheet"]["url"] or not c["sheet"]["token"]:
            return "Chưa cấu hình Google Sheet (URL và Token).\n\nVào Cấu hình > Google Sheet."
        if mode in ("post", "download_post", "parallel") and not dry:
            if not [p for p in c["pages"] if p.get("enabled", True)]:
                return "Chưa có Page Facebook nào đang bật.\n\nVào Cấu hình > Facebook > 'Lấy Page'."
        if mode in ("download", "download_post", "parallel") and not dry and not shopee.has_session() and not auto:
            if not messagebox.askyesno("Chưa đăng nhập Shopee",
                                       "Chưa có phiên đăng nhập Shopee. Video có thể không tải được nếu Shopee yêu cầu đăng nhập.\n\n"
                                       "Vẫn tiếp tục?"):
                return "cancel"
        return None

    def start_run(self, auto=False):
        if self.running:
            return
        self.save_config(quiet=True)
        mode = self.cfg["run"]["mode"]
        dry, retry = self.cfg["run"]["dry_run"], self.cfg["run"]["retry"]
        problem = self.preflight(mode, dry, auto)
        if problem:
            if problem != "cancel":
                if auto:
                    self.log_line("error", problem.replace("\n\n", " "))
                    self.v["run.auto"].set(False)
                else:
                    messagebox.showwarning("Chưa thể chạy", problem)
            return
        self.ctx = RunContext(emit=self.q.put)
        self.running, self.last_auto = True, auto
        self.next_run_at = None
        for var in self.stat_vars.values():
            var.set("0")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_var.set(f"Đang chạy: {MODES[mode]}" + (" (chạy thử)" if dry else ""))
        self.log_line("info", f"=== Bắt đầu: {MODES[mode]}{' (chạy thử)' if dry else ''}"
                              f"{' - tự động' if auto else ''} ===")
        threading.Thread(target=run_all, args=(copy.deepcopy(self.cfg), self.ctx, mode, dry, retry),
                         daemon=True).start()

    def stop_run(self):
        if self.ctx and self.running:
            self.ctx.cancel()
            self.v["run.auto"].set(False)
            self.next_run_at = None
            self.btn_stop.configure(state="disabled")
            self.status_var.set("Đang dừng... (chờ xong thao tác đang làm dở, ví dụ một video đang tải lên)")
            self.log_line("warn", "Đã yêu cầu dừng. Chương trình sẽ dừng sau khi xong thao tác hiện tại.")

    def _on_done(self, ev):
        self.running = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        s = ev["stats"]
        parts = [f"{label}: {s[k]}" for k, label in STAT_LABELS if s.get(k)]
        if s.get("dl_plan"):
            parts.append(f"Sẽ tải: {s['dl_plan']} link")
        if s.get("post_plan"):
            parts.append(f"Hợp lệ để đăng: {s['post_plan']} dòng")
        summary = ", ".join(parts) or "không có thay đổi nào"
        self.log_line("info", f"=== Kết thúc. {summary} ===")
        self.status_var.set(f"Hoàn tất lúc {datetime.now():%H:%M:%S}: {summary}")
        problems = s.get("dl_fail", 0) + s.get("post_fail", 0) + s.get("post_part", 0)
        if not self.last_auto:
            if ev.get("cancelled"):
                messagebox.showinfo("Đã dừng", f"Đã dừng theo yêu cầu.\n\n{summary}")
            elif problems:
                messagebox.showwarning("Hoàn tất - có cảnh báo/lỗi",
                                       f"{summary}\n\nXem chi tiết ở tab 'Cảnh báo & lỗi' và 'Kết quả từng dòng'.")
            else:
                messagebox.showinfo("Hoàn tất", summary)
        if self.v["run.auto"].get() and not ev.get("cancelled"):
            mins = cfgmod.to_int(self.v["run.auto_minutes"].get(), 30, 1)
            self.next_run_at = time.time() + mins * 60

    def _on_auto_toggle(self):
        if self.v["run.auto"].get():
            if not self.running:
                self.start_run(auto=True)
        else:
            self.next_run_at = None

    # ------------------------------------------------------------------ Google Sheet
    def gen_token(self):
        self.v["sheet.token"].set(secrets.token_urlsafe(18))
        self._sheet_msg("Đã tạo token mới. Bấm 'Sao chép mã Apps Script' để dán vào Apps Script (token sẽ được chèn sẵn).", "ok")

    def copy_appscript(self):
        tok = self.v["sheet.token"].get().strip()
        if not tok:
            tok = secrets.token_urlsafe(18)
            self.v["sheet.token"].set(tok)
        self.clip(APPSCRIPT_CODE.replace("__TOKEN__", tok))
        self._sheet_msg("Đã sao chép mã Apps Script (đã chèn token của bạn). Dán vào Apps Script của sheet rồi Triển khai "
                        "dạng Web app (xem hướng dẫn kết nối). Mỗi khi dán mã mới phải triển khai PHIÊN BẢN MỚI.", "ok")

    def _sheet_msg(self, text, kind="ok"):
        self.sheet_msg.configure(text=text, style={"ok": "Ok.TLabel", "err": "Err.TLabel"}.get(kind, "TLabel"))

    def _client(self):
        self.collect_cfg()
        return make_client(self.cfg)

    def test_sheet(self):
        try:
            client = self._client()
        except Exception as e:  # noqa: BLE001
            self._sheet_msg(str(e), "err")
            return
        self._sheet_msg("Đang kiểm tra kết nối...", "")
        self.bg(client.ping,
                lambda r: self._sheet_msg(f"Kết nối thành công: file '{r.get('name')}', tab '{r.get('tab')}', "
                                          f"{r.get('rows')} dòng.", "ok"),
                lambda e: self._sheet_msg(self.explain(e), "err"))

    def init_sheet(self):
        try:
            client = self._client()
        except Exception as e:  # noqa: BLE001
            self._sheet_msg(str(e), "err")
            return
        self._sheet_msg("Đang tạo tiêu đề cột...", "")
        self.bg(client.init_headers,
                lambda existed: self._sheet_msg("Đã ghi tiêu đề các cột F-N" + (" (cột A-E đã có sẵn)." if existed else " và A-E."), "ok"),
                lambda e: self._sheet_msg(self.explain(e), "err"))

    # ------------------------------------------------------------------ Shopee
    def pick_videos_dir(self):
        d = filedialog.askdirectory(initialdir=self.v["shopee.videos_dir"].get() or data_dir())
        if d:
            self.v["shopee.videos_dir"].set(d)

    def refresh_status_labels(self):
        if shopee.has_session():
            t = datetime.fromtimestamp(os.path.getmtime(cfgmod.state_file()))
            self.shopee_state_lbl.configure(text=f"Đã có phiên đăng nhập (lưu lúc {t:%d/%m/%Y %H:%M}).", style="Ok.TLabel")
        else:
            self.shopee_state_lbl.configure(text="Chưa có phiên đăng nhập Shopee.", style="Warn.TLabel")
        found = syscheck.found_browser_names()
        ff = shopee.find_ffmpeg()
        self.env_lbl.configure(
            text=("Trình duyệt tìm thấy: " + (", ".join(found) if found else f"KHÔNG CÓ. {BROWSER_MISSING_HINT}")
                  + ".   ffmpeg: " + ("có" if ff else "chưa có (chỉ cần cho video dạng m3u8)") + "."),
            style="Ok.TLabel" if found else "Err.TLabel")

    def shopee_login(self):
        if self.running:
            messagebox.showinfo("Đang chạy", "Hãy dừng lượt chạy hiện tại trước khi đăng nhập Shopee.")
            return
        self.save_config(quiet=True)
        ctx = RunContext(emit=self.q.put)
        done = threading.Event()
        win = tk.Toplevel(self)
        win.title("Đăng nhập Shopee")
        win.transient(self)
        win.resizable(False, False)
        f = ttk.Frame(win, padding=16)
        f.pack()
        ttk.Label(f, text="Một cửa sổ trình duyệt sẽ mở ra.\n\n1. Đăng nhập Shopee trong cửa sổ đó (xử lý xác minh nếu có).\n"
                          "2. Quay lại đây và bấm 'Tôi đã đăng nhập xong'.\n\nĐừng đóng cửa sổ trình duyệt trước khi bấm nút.",
                  justify="left").pack(anchor="w")
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(14, 0))
        ttk.Button(bar, text="Tôi đã đăng nhập xong", command=done.set).pack(side="left")
        ttk.Button(bar, text="Hủy", command=lambda: (ctx.cancel(), done.set())).pack(side="left", padx=8)

        def finish():
            try:
                win.destroy()
            except tk.TclError:
                pass
            self.refresh_status_labels()

        def work():
            try:
                shopee.login(self.cfg, ctx, done)
            except Cancelled:
                ctx.warn("Đã hủy đăng nhập Shopee.")
            except Exception as e:  # noqa: BLE001
                ctx.error(f"Đăng nhập Shopee: {e}")
            finally:
                self.q.put({"type": "call", "fn": finish})

        threading.Thread(target=work, daemon=True).start()

    def shopee_clear(self):
        if messagebox.askyesno("Xóa phiên", "Xóa phiên đăng nhập Shopee đã lưu trên máy này?"):
            shopee.clear_session()
            self.refresh_status_labels()

    # ------------------------------------------------------------------ Facebook
    def refresh_pages_tree(self):
        t = self.pages_tree
        t.delete(*t.get_children())
        for p in self.cfg["pages"]:
            tok = p.get("token", "")
            shown = (tok[:6] + "…" + tok[-4:]) if len(tok) > 12 else ("(đã lưu)" if tok else "(trống)")
            chk = self.fb_status.get(str(p["id"]), "")
            tag = "off" if not p.get("enabled", True) else ("bad" if chk.startswith("Lỗi") else ("good" if chk.startswith("OK") else ""))
            t.insert("", "end", iid=str(p["id"]), values=("Bật" if p.get("enabled", True) else "Tắt", p["name"], p["id"], shown, chk),
                     tags=(tag,) if tag else ())

    def _selected_pages(self):
        ids = self.pages_tree.selection()
        return [p for p in self.cfg["pages"] if str(p["id"]) in ids]

    def fb_fetch_pages(self):
        self.collect_cfg()
        tok = self.fb_user_token.get().strip()
        fc = self.cfg["facebook"]
        if not tok:
            self.fb_msg.configure(text="Hãy dán token người dùng (lấy từ Graph API Explorer) vào ô trên.", style="Err.TLabel")
            return
        long_already = self.fb_token_is_long.get()
        if not long_already and not (fc["app_id"] and fc["app_secret"]):
            self.fb_msg.configure(text="Cần nhập App ID và App Secret để đổi sang token dài hạn "
                                       "(hoặc tick 'Token này đã là token dài hạn').", style="Err.TLabel")
            return
        self.fb_msg.configure(text="Đang lấy danh sách Page...", style="TLabel")
        ver = fc["api_version"]

        def work():
            t = tok
            if not long_already:
                t, _ = fb.exchange_token(fc["app_id"], fc["app_secret"], tok, ver)
            return fb.fetch_pages(t, ver)

        def ok(found):
            by_id = {str(p["id"]): p for p in self.cfg["pages"]}
            added = 0
            for f in found:
                if str(f["id"]) in by_id:
                    by_id[str(f["id"])]["token"] = f["access_token"]
                else:
                    self.cfg["pages"].append({"name": f["name"], "id": str(f["id"]), "token": f["access_token"], "enabled": True})
                    added += 1
            self.save_config(quiet=True)
            self.refresh_pages_tree()
            if found:
                self.fb_user_token.set("")
                self.fb_msg.configure(text=f"Facebook trả về {len(found)} Page, thêm mới {added}, cập nhật token {len(found) - added}.",
                                      style="Ok.TLabel")
            else:
                self.fb_msg.configure(text="Facebook không trả về Page nào. Kiểm tra: lúc cấp quyền đã chọn Page chưa, token có quyền "
                                           "pages_show_list không, tài khoản có phải quản trị viên Page không (xem hướng dẫn kết nối).",
                                      style="Err.TLabel")

        self.bg(work, ok, lambda e: self.fb_msg.configure(text=self.explain(e), style="Err.TLabel"))

    def page_add(self):
        dlg = AddPageDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            r = dlg.result
            for p in self.cfg["pages"]:
                if str(p["id"]) == r["id"]:
                    p.update(name=r["name"], token=r["token"])
                    break
            else:
                self.cfg["pages"].append({"name": r["name"], "id": r["id"], "token": r["token"], "enabled": True})
            self.save_config(quiet=True)
            self.refresh_pages_tree()

    def page_rename(self):
        sel = self._selected_pages()
        if len(sel) != 1:
            messagebox.showinfo("Đổi tên", "Hãy chọn đúng một Page trong danh sách.")
            return
        name = simpledialog.askstring("Đổi tên Page", "Tên mới (dùng trong cột F của sheet):", initialvalue=sel[0]["name"], parent=self)
        if name and name.strip():
            sel[0]["name"] = name.strip()
            self.save_config(quiet=True)
            self.refresh_pages_tree()

    def page_toggle(self):
        sel = self._selected_pages()
        for p in sel:
            p["enabled"] = not p.get("enabled", True)
        if sel:
            self.save_config(quiet=True)
            self.refresh_pages_tree()

    def page_delete(self):
        sel = self._selected_pages()
        if sel and messagebox.askyesno("Xóa Page", f"Xóa {len(sel)} Page khỏi chương trình? (Không ảnh hưởng Page trên Facebook)"):
            ids = {str(p["id"]) for p in sel}
            self.cfg["pages"] = [p for p in self.cfg["pages"] if str(p["id"]) not in ids]
            self.save_config(quiet=True)
            self.refresh_pages_tree()

    def page_check(self):
        self.collect_cfg()
        targets = self._selected_pages() or list(self.cfg["pages"])
        if not targets:
            messagebox.showinfo("Kiểm tra token", "Chưa có Page nào.")
            return
        ver = self.cfg["facebook"]["api_version"]
        for p in targets:
            self.fb_status[str(p["id"])] = "Đang kiểm tra..."
        self.refresh_pages_tree()

        def work():
            res = {}
            for p in targets:
                try:
                    res[str(p["id"])] = "OK - " + (fb.check_page(p, ver) or "hợp lệ")
                except fb.FBError as e:
                    res[str(p["id"])] = f"Lỗi {e.code}: " + (fb.hint_for(e).split(":")[0] or str(e))[:60]
                except Exception:  # noqa: BLE001
                    res[str(p["id"])] = "Lỗi mạng"
            return res

        def ok(res):
            self.fb_status.update(res)
            self.refresh_pages_tree()

        self.bg(work, ok, self._default_err)

    # ------------------------------------------------------------------ chung
    def open_path(self, path):
        os.makedirs(path, exist_ok=True)
        try:
            open_path(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("Mở thư mục", f"{path}\n\n({e})")

    def open_videos(self):
        self.collect_cfg()
        self.open_path(cfgmod.videos_dir(self.cfg))

    def export_cfg(self):
        self.collect_cfg()
        dest = filedialog.asksaveasfilename(defaultextension=".json", initialfile="shopeefb_config.json",
                                            filetypes=[("JSON", "*.json")])
        if dest:
            cfgmod.export_to(self.cfg, dest)
            messagebox.showinfo("Đã xuất", "Đã xuất cấu hình. File này chứa token và App Secret, hãy giữ bí mật.")

    def import_cfg(self):
        src = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("Tất cả", "*.*")])
        if not src:
            return
        try:
            new = cfgmod.import_from(src)
        except (OSError, ValueError) as e:
            messagebox.showerror("Không đọc được file", str(e))
            return
        if not messagebox.askyesno("Nhập cấu hình", "Ghi đè cấu hình hiện tại bằng file này?"):
            return
        self.cfg = new
        cfgmod.save(self.cfg)
        for key, var in self.v.items():
            sec, k = key.split(".")
            val = self.cfg[sec][k]
            if key == "shopee.browser":
                val = label_of(BROWSER_LABELS, val)
            elif key == "facebook.schedule_mode":
                val = label_of(SCHEDULE_LABELS, val)
            elif key == "shopee.videos_dir" and not val:
                val = cfgmod.default_videos_dir()
            var.set(val)
        self.refresh_pages_tree()
        self.refresh_status_labels()
        self.dirty = False
        messagebox.showinfo("Đã nhập", "Đã nhập cấu hình.")

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("Đang chạy", "Chương trình đang chạy. Dừng và thoát?"):
                return
            if self.ctx:
                self.ctx.cancel()
        self.save_config(quiet=True)
        self.destroy()


def run():
    enable_dpi_awareness()
    app = App()
    app.mainloop()
