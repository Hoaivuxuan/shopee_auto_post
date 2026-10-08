"""Khác biệt giữa Windows và Ubuntu/Linux: thư mục dữ liệu, trình duyệt, ffmpeg, mở thư mục, font, gợi ý cài đặt.
Mọi chỗ cần rẽ nhánh theo hệ điều hành đều gọi vào module này."""
import glob
import os
import shutil
import subprocess
import sys

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
OS_LABEL = "Windows" if IS_WINDOWS else ("Ubuntu/Linux" if IS_LINUX else sys.platform)
SUPPORTED = IS_WINDOWS or IS_LINUX

# ----------------------------------------------------------------- chạy / đóng gói
CLI_PROG = "ShopeeFBTool.exe cli" if IS_WINDOWS else "./ShopeeFBTool cli"
PACKAGED_LABEL = "bản .exe" if IS_WINDOWS else "bản đóng gói"
SETUP_HINT = "py -m pip install -r requirements.txt" if IS_WINDOWS else "./scripts/ubuntu/setup.sh"
# CREATE_NO_WINDOW: không bật cửa sổ console khi gọi ffmpeg
NO_WINDOW_FLAGS = 0x08000000 if IS_WINDOWS else 0


def attach_parent_console():
    """Bản .exe --windowed không có console riêng: gắn vào Command Prompt đang mở để thấy kết quả lệnh cli."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stdin = open("CONIN$", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def user_data_root():
    """Thư mục dữ liệu theo chuẩn của hệ điều hành (dùng khi không ghi được cạnh chương trình)."""
    if IS_WINDOWS:
        return os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


# ----------------------------------------------------------------- ffmpeg
FFMPEG_EXE = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
FFMPEG_INSTALL_HINT = ("cài bằng lệnh 'winget install ffmpeg' hoặc đặt file ffmpeg.exe cạnh chương trình"
                       if IS_WINDOWS else "cài bằng lệnh 'sudo apt install ffmpeg'")

# ----------------------------------------------------------------- trình duyệt
BROWSER_NAMES = {"msedge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Chromium của Playwright"}
if IS_WINDOWS:
    DEFAULT_BROWSER = "msedge"
    BROWSER_LABELS = {"Microsoft Edge (khuyên dùng)": "msedge", "Google Chrome": "chrome",
                      "Chromium của Playwright": "chromium"}
    BROWSER_MISSING_HINT = "Hãy cài Microsoft Edge hoặc Google Chrome."
else:
    DEFAULT_BROWSER = "chrome"
    BROWSER_LABELS = {"Google Chrome (khuyên dùng)": "chrome", "Chromium của Playwright": "chromium",
                      "Microsoft Edge": "msedge"}
    BROWSER_MISSING_HINT = ("Hãy cài Google Chrome (file .deb từ google.com/chrome) hoặc chạy "
                            "./scripts/ubuntu/setup.sh để cài Chromium của Playwright.")


def _playwright_browsers_dir():
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom and custom != "0":
        return custom
    if IS_WINDOWS:
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    return os.path.expanduser("~/.cache/ms-playwright")


def _which(*names):
    return [shutil.which(n) or "" for n in names]


def browser_candidates():
    """{'msedge'|'chrome'|'chromium': [đường dẫn có thể có]} theo hệ điều hành."""
    pw = _playwright_browsers_dir()
    if IS_WINDOWS:
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        return {
            "msedge": [os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe"),
                       os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"), *_which("msedge")],
            "chrome": [os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
                       os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
                       os.path.join(local, r"Google\Chrome\Application\chrome.exe"), *_which("chrome")],
            "chromium": glob.glob(os.path.join(pw, "chromium-*", "chrome-win*", "chrome.exe")),
        }
    # Playwright chỉ nhận Chrome/Edge cài ở /opt (gói .deb), không nhận bản snap
    return {
        "msedge": ["/opt/microsoft/msedge/msedge", *_which("microsoft-edge-stable", "microsoft-edge")],
        "chrome": ["/opt/google/chrome/chrome", *_which("google-chrome-stable", "google-chrome")],
        "chromium": glob.glob(os.path.join(pw, "chromium-*", "chrome-linux*", "chrome")),
    }


def detect_browsers():
    """{'msedge'|'chrome'|'chromium': đường dẫn hoặc None}."""
    return {name: next((p for p in paths if p and os.path.isfile(p)), None)
            for name, paths in browser_candidates().items()}


# ----------------------------------------------------------------- giao diện
UI_FONTS = ("Segoe UI", "Arial") if IS_WINDOWS else ("Ubuntu", "Noto Sans", "DejaVu Sans", "Liberation Sans")
MONO_FONTS = ("Consolas", "Cascadia Mono") if IS_WINDOWS else ("Ubuntu Mono", "DejaVu Sans Mono", "Liberation Mono")


def open_path(path):
    """Mở thư mục/tệp bằng trình quản lý tệp mặc định."""
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def enable_dpi_awareness():
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
