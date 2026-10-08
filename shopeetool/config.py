"""Lưu / đọc cấu hình (config.json trong thư mục dữ liệu)."""
import copy
import json
import os
import shutil

from .paths import data_dir
from .platforms import DEFAULT_BROWSER

DEFAULTS = {
    "sheet": {"url": "", "token": "", "tab": ""},
    "shopee": {
        "videos_dir": "",
        "browser": DEFAULT_BROWSER,   # msedge | chrome | chromium
        "show_browser": False,
        "wait_seconds": 60,
        "limit": 10,
        "min_delay": 30,
        "max_delay": 90,
    },
    "facebook": {
        "app_id": "",
        "app_secret": "",
        "api_version": "v25.0",
        "limit": 5,
        "min_delay": 10,
        "max_delay": 30,
        "schedule_mode": "local",     # local | facebook
        "link_in_comment": False,
        "link_prefix": "Mua tại: ",
    },
    "run": {
        "mode": "download_post",      # download | post | download_post | parallel
        "dry_run": False,
        "retry": False,
        "auto": False,
        "auto_minutes": 30,
    },
    "pages": [],                      # [{"name","id","token","enabled"}]
}


def config_path():
    return os.path.join(data_dir(), "config.json")


def state_file():
    return os.path.join(data_dir(), "shopee_state.json")


def default_videos_dir():
    return os.path.join(data_dir(), "videos")


def videos_dir(cfg):
    return cfg["shopee"].get("videos_dir") or default_videos_dir()


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    """Đọc cấu hình; thiếu mục nào thì dùng mặc định. File hỏng sẽ được đổi tên thành .corrupt."""
    path = config_path()
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        try:
            shutil.copy(path, path + ".corrupt")
        except OSError:
            pass
        return copy.deepcopy(DEFAULTS)


def save(cfg):
    """Ghi an toàn: ghi file tạm rồi thay thế để không bị hỏng nếu mất điện giữa chừng."""
    path = config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def export_to(cfg, dest):
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def import_from(src):
    with open(src, encoding="utf-8") as f:
        return _merge(DEFAULTS, json.load(f))


def to_int(value, default, minimum=0, maximum=None):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        n = default
    n = max(minimum, n)
    if maximum is not None:
        n = min(maximum, n)
    return n
