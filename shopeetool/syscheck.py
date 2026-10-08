"""Kiểm tra môi trường: trình duyệt, ffmpeg, thư mục dữ liệu, thư viện..."""
import platform
import sys

from . import VERSION, config as cfgmod
from .logger import mask
from .paths import app_dir, data_dir
from .platforms import (BROWSER_LABELS, BROWSER_MISSING_HINT, BROWSER_NAMES, FFMPEG_INSTALL_HINT, OS_LABEL,
                        PACKAGED_LABEL, SETUP_HINT, SUPPORTED, detect_browsers)
from .shopee import find_ffmpeg, has_session


def found_browser_names():
    """Tên các trình duyệt dùng được trên máy, theo thứ tự ưu tiên của hệ điều hành."""
    br = detect_browsers()
    return [BROWSER_NAMES[c] for c in BROWSER_LABELS.values() if br.get(c)]


def check_all(cfg):
    """Trả về danh sách (mục, trạng thái 'ok'|'warn'|'error', chi tiết)."""
    out = []
    run_mode = f"đã đóng gói, {PACKAGED_LABEL}" if getattr(sys, "frozen", False) else "chạy từ mã nguồn"
    out.append(("Phiên bản chương trình", "ok", f"{VERSION} ({run_mode})"))
    out.append(("Hệ điều hành", "ok" if SUPPORTED else "warn",
                f"{OS_LABEL} - {platform.system()} {platform.release()}"
                + ("" if SUPPORTED else " (chương trình hỗ trợ Windows và Ubuntu)")))
    try:
        import playwright  # noqa: F401
        out.append(("Thư viện Playwright", "ok", "Đã có"))
    except ImportError:
        out.append(("Thư viện Playwright", "error", f"Chưa có ({SETUP_HINT}). {PACKAGED_LABEL.capitalize()} đã gồm sẵn."))
    names = found_browser_names()
    if names:
        out.append(("Trình duyệt để tải video", "ok", "Tìm thấy: " + ", ".join(names)))
    else:
        out.append(("Trình duyệt để tải video", "error", f"Không tìm thấy trình duyệt. {BROWSER_MISSING_HINT}"))
    ff = find_ffmpeg()
    out.append(("ffmpeg (chỉ cần cho video dạng m3u8)", "ok" if ff else "warn",
                ff or f"Chưa có. Video .mp4 vẫn tải bình thường. Muốn tải m3u8 thì {FFMPEG_INSTALL_HINT}."))
    try:
        out.append(("Thư mục dữ liệu", "ok", data_dir()))
    except Exception as e:  # noqa: BLE001
        out.append(("Thư mục dữ liệu", "error", str(e)))
    out.append(("Thư mục chương trình", "ok", app_dir()))
    out.append(("Thư mục lưu video", "ok", cfgmod.videos_dir(cfg)))
    out.append(("Phiên đăng nhập Shopee", "ok" if has_session() else "warn",
                "Đã có" if has_session() else "Chưa có: vào Cấu hình > Shopee > 'Đăng nhập Shopee'"))
    s = cfg["sheet"]
    out.append(("Google Sheet", "ok" if (s["url"] and s["token"]) else "warn",
                "Đã nhập URL và token" if (s["url"] and s["token"]) else "Chưa cấu hình (Cấu hình > Google Sheet)"))
    n = len(cfg.get("pages", []))
    out.append(("Facebook Page", "ok" if n else "warn", f"{n} Page" if n else "Chưa có Page (Cấu hình > Facebook > 'Lấy Page')"))
    return out


def support_report(cfg):
    lines = [f"Shopee → Facebook Tool {VERSION}", ""]
    for name, st, detail in check_all(cfg):
        lines.append(f"[{st.upper():5}] {name}: {detail}")
    lines += ["", "Cấu hình (đã che thông tin bí mật):",
              f"  sheet.url   : {'đã nhập' if cfg['sheet']['url'] else 'trống'}",
              f"  sheet.token : {'đã nhập' if cfg['sheet']['token'] else 'trống'}",
              f"  facebook    : api {cfg['facebook']['api_version']}, hẹn giờ={cfg['facebook']['schedule_mode']}, "
              f"nghỉ {cfg['facebook']['min_delay']}-{cfg['facebook']['max_delay']}s",
              f"  pages       : {[p['name'] for p in cfg.get('pages', [])]}",
              f"  chế độ chạy : {cfg['run']['mode']}"]
    return mask("\n".join(lines))
