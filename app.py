"""Điểm vào của chương trình.
  - Không có tham số: mở giao diện.
  - <chương trình> cli <lệnh> ...: chạy bằng dòng lệnh (xem tài liệu HUONG_DAN_COMMAND.md).
    Windows: ShopeeFBTool.exe cli ... | Ubuntu: ./ShopeeFBTool cli ... | mã nguồn: python app.py cli ..."""
import os
import sys

from shopeetool.platforms import attach_parent_console


def _fix_std_streams():
    # Bản đóng gói --windowed không có console: sys.stdout/sys.stderr có thể là None
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _use_utf8_console():
    # Console Windows mặc định dùng code page cũ (cp1252/cp437), in tiếng Việt sẽ lỗi UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main():
    _fix_std_streams()
    if len(sys.argv) > 1 and sys.argv[1] in ("cli", "--cli"):
        attach_parent_console()
        _use_utf8_console()
        from shopeetool.cli import main as cli_main
        sys.exit(cli_main(sys.argv[2:]))
    from shopeetool.gui import run
    run()


if __name__ == "__main__":
    main()
