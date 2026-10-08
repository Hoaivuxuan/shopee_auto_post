"""Shopee: đăng nhập, bắt link video bằng trình duyệt thật (Edge/Chrome/Chromium), tải video về máy."""
import os
import re
import shutil
import subprocess
import time

import requests

from .config import state_file
from .logger import Cancelled
from .paths import app_dir, data_dir, resource_path
from .platforms import (BROWSER_LABELS, BROWSER_MISSING_HINT, DEFAULT_BROWSER, FFMPEG_EXE, FFMPEG_INSTALL_HINT,
                        NO_WINDOW_FLAGS, PACKAGED_LABEL, SETUP_HINT)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
EXTS = (".mp4", ".m3u8")


class ShopeeError(Exception):
    pass


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ShopeeError(f"Thiếu thư viện 'playwright'. Nếu chạy từ mã nguồn: {SETUP_HINT} "
                          f"({PACKAGED_LABEL} đã có sẵn).") from e
    return sync_playwright


def launch_browser(p, cfg, headless=False, hide=False):
    """Mở trình duyệt thật. Ưu tiên loại đã chọn, tự thử loại khác nếu không có."""
    args = ["--start-minimized", "--window-position=-32000,-32000"] if hide else []
    pref = cfg["shopee"].get("browser", DEFAULT_BROWSER)
    order = [pref] + [c for c in BROWSER_LABELS.values() if c != pref]
    last = None
    for ch in order:
        try:
            if ch == "chromium":
                return p.chromium.launch(headless=headless, args=args)
            return p.chromium.launch(channel=ch, headless=headless, args=args)
        except Exception as e:  # noqa: BLE001
            last = e
    raise ShopeeError(f"Không mở được trình duyệt. {BROWSER_MISSING_HINT} Chi tiết: {str(last)[:200]}")


def has_session():
    return os.path.exists(state_file())


def clear_session():
    try:
        os.remove(state_file())
    except OSError:
        pass


def login(cfg, ctx, done_event, timeout=900):
    """Mở trình duyệt để người dùng tự đăng nhập Shopee, rồi lưu phiên khi done_event được bật."""
    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        browser = launch_browser(p, cfg, headless=False, hide=False)
        sf = state_file()
        context = browser.new_context(storage_state=sf if os.path.exists(sf) else None)
        page = context.new_page()
        page.goto("https://shopee.vn/buyer/login", wait_until="domcontentloaded")
        ctx.info("Đã mở trình duyệt. Hãy đăng nhập Shopee trong cửa sổ đó, rồi quay lại bấm 'Tôi đã đăng nhập xong'.")
        end = time.time() + timeout
        try:
            while not done_event.is_set():
                if ctx.cancelled() or time.time() > end:
                    raise Cancelled()
                page.wait_for_timeout(500)
        except Cancelled:
            raise
        except Exception:  # noqa: BLE001  (người dùng đóng cửa sổ trình duyệt)
            pass
        try:
            context.storage_state(path=sf)
        except Exception as e:  # noqa: BLE001
            raise ShopeeError("Cửa sổ trình duyệt đã bị đóng trước khi lưu phiên. Hãy đăng nhập lại và chỉ bấm "
                              "'Tôi đã đăng nhập xong' khi cửa sổ trình duyệt còn mở.") from e
        ctx.ok("Đã lưu phiên đăng nhập Shopee.")
        try:
            context.close()
            browser.close()
        except Exception:  # noqa: BLE001
            pass


class ShopeeSession:
    """Mở trình duyệt một lần cho cả lượt tải, mỗi link mở một tab mới."""

    def __init__(self, cfg, ctx):
        self.cfg = cfg
        self.ctx = ctx
        self._cm = self.p = self.browser = self.context = None

    def __enter__(self):
        sync_playwright = _import_playwright()
        self._cm = sync_playwright()
        self.p = self._cm.start()
        hide = not self.cfg["shopee"].get("show_browser", False)
        self.browser = launch_browser(self.p, self.cfg, headless=False, hide=hide)
        sf = state_file()
        self.context = self.browser.new_context(storage_state=sf if os.path.exists(sf) else None)
        return self

    def __exit__(self, *exc):
        try:
            self.context.storage_state(path=state_file())
        except Exception:  # noqa: BLE001
            pass
        for obj in (self.context, self.browser):
            try:
                obj.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._cm.stop()
        except Exception:  # noqa: BLE001
            pass

    def capture(self, url, wait):
        """Trả về (danh sách link video bắt được, thông tin chẩn đoán)."""
        found = []

        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "").lower()
            except Exception:  # noqa: BLE001
                ctype = ""
            base = resp.url.split("?")[0].lower()
            if (base.endswith(EXTS) or "video/" in ctype or "mpegurl" in ctype) and resp.url not in found:
                found.append(resp.url)

        page = self.context.new_page()
        page.on("response", on_response)
        info = ""
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:  # noqa: BLE001
                self.ctx.warn(f"Tải trang chậm hoặc lỗi ({str(e)[:100]}), vẫn thử chờ video...")
            deadline = time.time() + wait
            last_try = 0.0
            while time.time() < deadline and not found:
                self.ctx.check()
                page.wait_for_timeout(500)
                if time.time() - last_try > 5:
                    last_try = time.time()
                    try:
                        page.evaluate("() => document.querySelectorAll('video').forEach("
                                      "x => { x.muted = true; x.play().catch(() => {}); })")
                    except Exception:  # noqa: BLE001
                        pass
            if found:
                page.wait_for_timeout(3000)  # chờ thêm để gom đủ các link
            else:
                try:
                    info = f"{page.title()} | {page.url}"
                except Exception:  # noqa: BLE001
                    info = ""
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        return found, info


def pick_best(urls):
    for u in urls:
        if ".mp4" in u.split("?")[0].lower():
            return u
    return urls[0]


def find_ffmpeg():
    for cand in (shutil.which("ffmpeg"), os.path.join(app_dir(), FFMPEG_EXE),
                 os.path.join(data_dir(), FFMPEG_EXE), resource_path(FFMPEG_EXE)):
        if cand and os.path.isfile(cand):
            return cand
    return None


def download_file(video_url, dest, ctx):
    """Tải link .mp4 trực tiếp hoặc luồng .m3u8 (cần ffmpeg) về file dest."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    try:
        if ".m3u8" in video_url:
            ff = find_ffmpeg()
            if not ff:
                raise ShopeeError(f"Video dạng m3u8 cần ffmpeg: {FFMPEG_INSTALL_HINT} (xem tab Hệ thống).")
            cmd = [ff, "-y", "-user_agent", UA, "-i", video_url, "-c", "copy", "-f", "mp4", tmp]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=NO_WINDOW_FLAGS)
            while proc.poll() is None:
                if ctx.cancelled():
                    proc.kill()
                    raise Cancelled()
                time.sleep(0.5)
            if proc.returncode != 0:
                raise ShopeeError(f"ffmpeg không tải được video (mã {proc.returncode}); link có thể đã hết hạn.")
        else:
            try:
                with requests.get(video_url, stream=True, timeout=60,
                                  headers={"User-Agent": UA, "Referer": "https://shopee.vn/"}) as r:
                    if r.status_code in (401, 403):
                        raise ShopeeError(f"Link video bị từ chối (HTTP {r.status_code}), có thể đã hết hạn.")
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=256 * 1024):
                            if ctx.cancelled():
                                raise Cancelled()
                            f.write(chunk)
            except requests.RequestException as e:
                raise ShopeeError(f"Lỗi mạng khi tải video: {str(e)[:150]}") from e
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise ShopeeError("File video tải về bị rỗng.")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def product_id(link, row):
    m = re.search(r"i\.(\d+)\.(\d+)", link) or re.search(r"/product/(\d+)/(\d+)", link)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return f"row{row}"
