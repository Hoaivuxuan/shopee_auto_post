"""Đăng nhập Facebook từ trình duyệt của người dùng, dù server không có màn hình.

Chrome chạy trên server. Trang quản trị gửi ảnh màn hình ra laptop và nhận lại
cú bấm, chữ gõ. Khi thấy cookie đăng nhập, phiên được lưu vào data/facebook_state.json.
"""
import os
import queue
import shutil
import subprocess
import threading
import time

from .fb_group import (
    FBGroupError,
    _import_playwright,
    _launch,
    _logged_in,
    _new_context,
    _save_state,
    fetch_in_progress,
    profile_name_from_page,
    remember_account,
    session_path,
)

VIEWPORT = {"width": 1100, "height": 720}
_KEYS = {"Enter", "Backspace", "Tab", "Escape", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"}


class _Xvfb:
    def __init__(self):
        self.proc = None
        self.display = ":95"

    def start(self):
        if not shutil.which("Xvfb"):
            return None
        self.proc = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.8)
        if self.proc.poll() is not None:
            self.proc = None
            return None
        return self.display

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


class RemoteFacebookLogin:
    def __init__(self):
        self._lock = threading.Lock()
        self._commands = queue.Queue()
        self._thread = None
        self._jpeg = b""
        self._fields = {}
        self._status = "idle"
        self._message = ""
        self._stop = False

    def public(self):
        with self._lock:
            return {"status": self._status, "message": self._message, "fields": self._fields}

    def frame(self):
        with self._lock:
            return self._jpeg

    def start(self):
        if fetch_in_progress():
            raise FBGroupError("Đang lấy bài nhóm. Hãy đợi xong rồi đăng nhập.")
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"status": self._status, "message": self._message}
            self._stop = False
            self._jpeg = b""
            self._fields = {}
            self._status = "starting"
            self._message = "Đang mở trang đăng nhập Facebook..."
            self._thread = threading.Thread(target=self._run, name="fb-login", daemon=True)
            self._thread.start()
            return {"status": self._status, "message": self._message}

    def cancel(self):
        self._stop = True
        self._commands.put(("stop",))
        with self._lock:
            if self._status in ("starting", "waiting"):
                self._status = "closed"
                self._message = "Đã đóng cửa sổ đăng nhập."
        return self.public()

    def event(self, body):
        action = str(body.get("action") or "")
        if action == "click":
            x = _coord(body.get("x"))
            y = _coord(body.get("y"))
            self._commands.put(("click", x, y))
        elif action == "type":
            text = str(body.get("text") or "")
            if not text or len(text) > 300:
                raise FBGroupError("Nội dung gõ không hợp lệ")
            self._commands.put(("type", text))
        elif action == "fill":
            name = str(body.get("field") or "")
            if name not in ("email", "pass"):
                raise FBGroupError("Ô nhập không hợp lệ")
            text = "" if body.get("text") is None else str(body.get("text"))
            if len(text) > 300:
                raise FBGroupError("Nội dung gõ không hợp lệ")
            self._commands.put(("fill", name, text))
        elif action == "press":
            key = str(body.get("key") or "")
            if key not in _KEYS:
                raise FBGroupError("Phím không được hỗ trợ")
            self._commands.put(("press", key))
        elif action == "submit":
            self._commands.put(("submit",))
        elif action == "scroll":
            dy = _coord(body.get("dy"), limit=800)
            self._commands.put(("scroll", dy))
        else:
            raise FBGroupError("Thao tác không hợp lệ")
        return self.public()

    def _set(self, status, message):
        with self._lock:
            self._status = status
            self._message = message

    def _captcha_only(self):
        with self._lock:
            return "captcha" in self._fields and "email" not in self._fields

    def _store_frame(self, data):
        with self._lock:
            self._jpeg = data

    def _store_fields(self, page):
        fields = {}
        for name in ("email", "pass"):
            field = page.locator(f'input[name="{name}"]')
            try:
                if field.count() == 0:
                    continue
                box = field.bounding_box()
            except Exception:
                continue
            if not box:
                continue
            fields[name] = {key: round(box[key], 1) for key in ("x", "y", "width", "height")}
        try:
            button = _login_button(page)
            if button.count():
                box = button.first.bounding_box()
                if box and box["width"] > 20 and box["height"] > 20:
                    fields["login"] = {key: round(box[key], 1) for key in ("x", "y", "width", "height")}
        except Exception:
            pass
        try:
            captcha = page.locator('iframe[src*="recaptcha" i], iframe[title*="captcha" i]')
            if captcha.count() == 0:
                captcha = page.locator("iframe")
            if captcha.count():
                box = captcha.first.bounding_box()
                if box and box["width"] > 40 and box["height"] > 40:
                    fields["captcha"] = {key: round(box[key], 1) for key in ("x", "y", "width", "height")}
        except Exception:
            pass
        with self._lock:
            self._fields = fields

    def _run(self):
        xvfb = _Xvfb()
        browser = None
        try:
            sync_playwright = _import_playwright()
            with sync_playwright() as playwright:
                display = xvfb.start()
                if display:
                    os.environ["DISPLAY"] = display
                browser = _launch(playwright, headless=not bool(display))
                context = _new_context(browser, None, VIEWPORT)
                page = context.new_page()
                page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=60000)
                self._set("waiting", "Gõ vào ô viền xanh, rồi bấm nút Đăng nhập màu xanh.")
                deadline = time.time() + 600
                last_shot = 0.0
                while not self._stop and time.time() < deadline:
                    self._apply(page)
                    if _logged_in(context):
                        _save_state(context, session_path())
                        name = ""
                        try:
                            page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=20000)
                            name = profile_name_from_page(page)
                        except Exception:
                            name = ""
                        try:
                            info = remember_account(name)
                        except Exception:
                            info = {}
                        label = info.get("name") or name or "Facebook"
                        self._set("logged_in", f"Đã lưu tài khoản {label}.")
                        break
                    now = time.time()
                    if now - last_shot > 0.45:
                        try:
                            self._store_frame(page.screenshot(type="jpeg", quality=55))
                            self._store_fields(page)
                            if self._captcha_only():
                                self._set(
                                    "waiting",
                                    "Facebook đang hỏi xác nhận. Bấm trực tiếp lên ô vuông hoặc các hình trong ảnh.",
                                )
                        except Exception:
                            pass
                        last_shot = now
                    time.sleep(0.05)
                else:
                    if not self._stop and self._status == "waiting":
                        self._set("error", "Hết thời gian đăng nhập. Bấm Đăng nhập Facebook để mở lại.")
                try:
                    browser.close()
                except Exception:
                    pass
        except Exception as exc:
            self._set("error", str(exc)[:180])
        finally:
            xvfb.stop()

    def _apply(self, page):
        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            kind = cmd[0]
            try:
                if kind == "stop":
                    self._stop = True
                elif kind == "click":
                    _focus_click(page, cmd[1], cmd[2])
                elif kind == "type":
                    page.keyboard.insert_text(cmd[1])
                elif kind == "fill":
                    page.locator(f'input[name="{cmd[1]}"]').fill(cmd[2], timeout=3000)
                elif kind == "press":
                    if cmd[1] == "Enter":
                        _submit_login(page)
                    else:
                        page.keyboard.press(cmd[1])
                elif kind == "submit":
                    _submit_login(page)
                elif kind == "scroll":
                    page.mouse.wheel(0, cmd[1])
            except Exception:
                continue


def _login_button(page):
    return page.get_by_role("button", name="Đăng nhập", exact=True)


def _submit_login(page):
    """Nút Đăng nhập của Facebook là một div, phím Enter trên trang không bấm nó."""
    button = _login_button(page)
    if button.count():
        button.first.click(timeout=3000)
        return
    field = page.locator('input[name="pass"]')
    if field.count():
        field.press("Enter", timeout=3000)
        return
    page.keyboard.press("Enter")


def _focus_click(page, x, y):
    """Bấm đúng ô email/mật khẩu nếu cú bấm rơi vào khung ô, rồi mới bấm tọa độ."""
    try:
        button = _login_button(page)
        if button.count():
            box = button.first.bounding_box()
            if box and box["x"] <= x <= box["x"] + box["width"] and box["y"] <= y <= box["y"] + box["height"]:
                button.first.click(timeout=3000)
                return
    except Exception:
        pass
    for name in ("email", "pass"):
        field = page.locator(f'input[name="{name}"]')
        try:
            if field.count() == 0:
                continue
            box = field.bounding_box()
        except Exception:
            continue
        if not box:
            continue
        inside = (
            box["x"] - 20 <= x <= box["x"] + box["width"] + 20
            and box["y"] - 16 <= y <= box["y"] + box["height"] + 16
        )
        if inside:
            field.click(timeout=3000)
            return
    page.mouse.click(x, y)
    try:
        page.evaluate(
            """([px, py]) => {
                const el = document.elementFromPoint(px, py);
                const input = el && el.closest ? el.closest('input, textarea') : null;
                (input || el)?.focus?.();
            }""",
            [x, y],
        )
    except Exception:
        pass


def _coord(value, limit=2000):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FBGroupError("Tọa độ không hợp lệ") from exc
    if number < -limit or number > limit:
        raise FBGroupError("Tọa độ không hợp lệ")
    return number


def _resize(context):
    """Context mới đã có viewport mặc định. Trang đăng nhập dùng kích thước cố định để khớp cú bấm."""
    return context


_LOGINS = {}
_LOGINS_LOCK = threading.Lock()


def _login_for_user() -> RemoteFacebookLogin:
    """Mỗi tài khoản admin có phiên đăng nhập Facebook riêng."""
    try:
        from .auth import current_username
        key = current_username() or "_"
    except (ImportError, ValueError):
        key = "_"
    with _LOGINS_LOCK:
        login = _LOGINS.get(key)
        if login is None:
            login = RemoteFacebookLogin()
            _LOGINS[key] = login
        return login


def login_status():
    return _login_for_user().public()


def login_frame():
    return _login_for_user().frame()


def login_start():
    return _login_for_user().start()


def login_cancel():
    return _login_for_user().cancel()


def login_event(body):
    return _login_for_user().event(body)
