#!/usr/bin/env bash
# Chạy từ mã nguồn. Không tham số: mở giao diện. "cli <lệnh>": chạy bằng dòng lệnh.
#   ./scripts/ubuntu/chay_ung_dung.sh
#   ./scripts/ubuntu/chay_ung_dung.sh cli post --dry-run
# Máy không có màn hình (server, cron): xvfb-run -a ./scripts/ubuntu/chay_ung_dung.sh cli all
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    echo "Chưa cài môi trường. Chạy trước: ./scripts/ubuntu/setup.sh" >&2
    exit 1
fi
exec .venv/bin/python app.py "$@"
