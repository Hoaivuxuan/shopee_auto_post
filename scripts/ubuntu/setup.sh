#!/usr/bin/env bash
# Cài môi trường chạy từ mã nguồn trên Ubuntu 22.04 / 24.04 (cần sudo và Internet).
# Tạo .venv ở thư mục dự án, cài thư viện Python và Chromium của Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Cài gói hệ thống ==="
sudo apt-get update
# python3-tk: giao diện Tkinter; ffmpeg: tải video m3u8; xvfb: chạy trình duyệt trên máy không có màn hình
sudo apt-get install -y python3 python3-venv python3-pip python3-tk ffmpeg xvfb

echo "=== Tạo môi trường ảo .venv ==="
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "=== Cài Chromium cho Playwright (kèm thư viện hệ thống) ==="
.venv/bin/python -m playwright install --with-deps chromium

echo
echo "Xong. Mở giao diện:   ./scripts/ubuntu/chay_ung_dung.sh"
echo "Dòng lệnh:           ./scripts/ubuntu/chay_ung_dung.sh cli check"
