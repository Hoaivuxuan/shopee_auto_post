#!/usr/bin/env bash
# Đóng gói thành thư mục chạy được trên máy Ubuntu khác (không cần cài Python).
# Kết quả: dist/ShopeeFBTool/ShopeeFBTool và dist/ShopeeFBTool-<phiên bản>-ubuntu.tar.gz
# Máy đích cần Google Chrome (gói .deb) hoặc Chromium của Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    echo "Chưa cài môi trường. Chạy trước: ./scripts/ubuntu/setup.sh" >&2
    exit 1
fi

echo "=== Cài PyInstaller ==="
.venv/bin/python -m pip install pyinstaller

echo "=== Đóng gói (mất vài phút) ==="
.venv/bin/python scripts/build.py
