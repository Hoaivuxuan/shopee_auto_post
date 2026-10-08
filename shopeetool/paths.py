"""Đường dẫn: thư mục chương trình, thư mục dữ liệu, tài nguyên đi kèm."""
import os
import sys

from .platforms import user_data_root

APP_NAME = "ShopeeFBTool"
_DATA_DIR = None


def app_dir():
    """Thư mục chứa file .exe (khi đã đóng gói) hoặc thư mục dự án (khi chạy từ mã nguồn)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel):
    """Đường dẫn tới tài nguyên đi kèm (docs...), dùng được cả khi chạy từ .exe."""
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, rel)


def data_dir():
    """Thư mục dữ liệu (cấu hình, phiên đăng nhập, video, nhật ký).
    Ưu tiên thư mục 'data' nằm cạnh chương trình để chép sang máy khác dễ dàng.
    Nếu không ghi được (vd cài trong Program Files hoặc /opt) thì dùng
    %LOCALAPPDATA%\\ShopeeFBTool (Windows) hoặc ~/.local/share/ShopeeFBTool (Ubuntu)."""
    global _DATA_DIR
    if _DATA_DIR:
        return _DATA_DIR
    candidates = [os.path.join(app_dir(), "data"), os.path.join(user_data_root(), APP_NAME)]
    for cand in candidates:
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            _DATA_DIR = cand
            return cand
        except OSError:
            continue
    raise RuntimeError("Không tạo được thư mục dữ liệu cho chương trình.")


def logs_dir():
    p = os.path.join(data_dir(), "logs")
    os.makedirs(p, exist_ok=True)
    return p
