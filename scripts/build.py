"""Đóng gói chương trình bằng PyInstaller cho hệ điều hành đang chạy (Windows hoặc Ubuntu), rồi nén lại.
Gọi qua scripts/windows/build_exe.bat hoặc scripts/ubuntu/build.sh (PyInstaller không build chéo hệ điều hành).
Kết quả:
  Windows: dist/ShopeeFBTool/ShopeeFBTool.exe  + dist/ShopeeFBTool-<phiên bản>-windows.zip
  Ubuntu : dist/ShopeeFBTool/ShopeeFBTool      + dist/ShopeeFBTool-<phiên bản>-ubuntu.tar.gz"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from shopeetool import VERSION  # noqa: E402
from shopeetool.paths import APP_NAME  # noqa: E402
from shopeetool.platforms import IS_WINDOWS  # noqa: E402


def main():
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", APP_NAME,
           "--collect-all", "playwright", "--add-data", f"docs{os.pathsep}docs", "app.py"]
    if IS_WINDOWS:
        cmd.insert(3, "--windowed")
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    dist = os.path.join(ROOT, "dist")
    suffix, fmt = ("windows", "zip") if IS_WINDOWS else ("ubuntu", "gztar")
    archive = shutil.make_archive(os.path.join(dist, f"{APP_NAME}-{VERSION}-{suffix}"), fmt,
                                  root_dir=dist, base_dir=APP_NAME)
    print(f"\nXong. Thư mục: {os.path.join(dist, APP_NAME)}\nBản nén   : {archive}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nĐóng gói thất bại (mã {e.returncode}).")
        sys.exit(1)
