"""Ngữ cảnh chạy: ghi nhật ký, kết quả, thống kê, hủy giữa chừng."""
import os
import re
import threading
import time
from datetime import datetime

from .paths import logs_dir

_SECRET_PATTERNS = [
    (re.compile(r"EA[A-Za-z0-9]{20,}"), "EA***"),                        # token Facebook
    (re.compile(r"(access_token=)[^&\s]+"), r"\1***"),
    (re.compile(r"(script\.google\.com/macros/s/)[A-Za-z0-9_\-]+"), r"\1***"),
]


def mask(text):
    s = str(text)
    for pat, rep in _SECRET_PATTERNS:
        s = pat.sub(rep, s)
    return s


class Cancelled(Exception):
    """Người dùng bấm Dừng."""


class RunContext:
    def __init__(self, emit=None):
        self.emit = emit or (lambda ev: None)
        self.cancel_event = threading.Event()
        self.stats = {}
        self._lock = threading.Lock()

    # ----- nhật ký
    def log(self, level, msg, job=None, row=None):
        msg = mask(msg)
        now = datetime.now()
        self.emit({"type": "log", "level": level, "msg": msg, "time": now.strftime("%H:%M:%S"),
                   "job": job, "row": row})
        try:
            path = os.path.join(logs_dir(), f"shopeefb_{now:%Y%m%d}.log")
            with self._lock, open(path, "a", encoding="utf-8") as f:
                f.write(f"{now:%Y-%m-%d %H:%M:%S} [{level.upper()}] {msg}\n")
        except OSError:
            pass

    def info(self, msg, **kw):
        self.log("info", msg, **kw)

    def ok(self, msg, **kw):
        self.log("ok", msg, **kw)

    def warn(self, msg, **kw):
        self.log("warn", msg, **kw)

    def error(self, msg, **kw):
        self.log("error", msg, **kw)

    # ----- kết quả & thống kê
    def result(self, job, row, status, note=""):
        self.emit({"type": "result", "job": job, "row": row, "status": status,
                   "note": mask(note), "time": datetime.now().strftime("%H:%M:%S")})

    def stat(self, key, inc=1):
        with self._lock:
            self.stats[key] = self.stats.get(key, 0) + inc
            snapshot = dict(self.stats)
        self.emit({"type": "stats", "stats": snapshot})

    def set_stat(self, key, value):
        with self._lock:
            self.stats[key] = value
            snapshot = dict(self.stats)
        self.emit({"type": "stats", "stats": snapshot})

    # ----- hủy
    def cancel(self):
        self.cancel_event.set()

    def cancelled(self):
        return self.cancel_event.is_set()

    def check(self):
        if self.cancelled():
            raise Cancelled()

    def sleep(self, seconds):
        """Nghỉ nhưng thoát ngay khi bị hủy. Trả về False nếu bị hủy."""
        end = time.time() + max(0, seconds)
        while time.time() < end:
            if self.cancelled():
                return False
            time.sleep(min(0.3, max(0.0, end - time.time())))
        return not self.cancelled()
