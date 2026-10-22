"""Đường dẫn: thư mục chương trình, thư mục dữ liệu, tài nguyên đi kèm.

data_dir() trả về workspace của người dùng đang đăng nhập (ContextVar),
hoặc thư mục data dùng chung / workspace mặc định khi chạy CLI.
"""
import os
import sys
from contextvars import ContextVar

from .platforms import user_data_root

APP_NAME = "ShopeeFBTool"
_SHARED_DATA_DIR = None
_WORKSPACE: ContextVar = ContextVar("shopee_workspace_data_dir", default=None)


def app_dir():
    """Thư mục chứa file .exe (khi đã đóng gói) hoặc thư mục dự án (khi chạy từ mã nguồn)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel):
    """Đường dẫn tới tài nguyên đi kèm (docs...), dùng được cả khi chạy từ .exe."""
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, rel)


def _writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def shared_data_dir():
    """Thư mục data gốc (accounts, sessions, workspaces/)."""
    global _SHARED_DATA_DIR
    if _SHARED_DATA_DIR:
        return _SHARED_DATA_DIR
    candidates = [os.path.join(app_dir(), "data"), os.path.join(user_data_root(), APP_NAME)]
    writable = [path for path in candidates if _writable(path)]
    if not writable:
        raise RuntimeError("Không tạo được thư mục dữ liệu cho chương trình.")

    def score(path):
        points = 0
        if os.path.isdir(os.path.join(path, "workspaces")):
            points += 3
        catalog = os.path.join(path, "products_affiliate.json")
        config = os.path.join(path, "config.json")
        if os.path.isfile(catalog) and os.path.getsize(catalog) > 100:
            points += 2
        if os.path.isfile(config) and os.path.getsize(config) > 100:
            points += 1
        if os.path.isfile(os.path.join(path, "accounts.json")):
            points += 2
        return points

    _SHARED_DATA_DIR = max(writable, key=score)
    return _SHARED_DATA_DIR


def use_workspace(path: str):
    """Gắn thư mục workspace cho request / luồng hiện tại."""
    os.makedirs(path, exist_ok=True)
    return _WORKSPACE.set(os.path.realpath(path))


def reset_workspace(token) -> None:
    _WORKSPACE.reset(token)


def current_workspace() -> str | None:
    return _WORKSPACE.get()


def data_dir():
    """Thư mục dữ liệu làm việc (cấu hình, phiên, video, nhật ký) của người dùng hiện tại."""
    workspace = _WORKSPACE.get()
    if workspace:
        os.makedirs(workspace, exist_ok=True)
        return workspace

    shared = shared_data_dir()
    # Dữ liệu cũ còn nằm ở gốc data/
    if os.path.isfile(os.path.join(shared, "products_affiliate.json")) or os.path.isfile(
        os.path.join(shared, "config.json")
    ):
        return shared

    default_name = (os.environ.get("SHOPEE_WORKSPACE") or "admin").strip().lower() or "admin"
    default_path = os.path.join(shared, "workspaces", default_name)
    if os.path.isdir(default_path):
        return default_path
    return shared


def logs_dir():
    p = os.path.join(data_dir(), "logs")
    os.makedirs(p, exist_ok=True)
    return p
